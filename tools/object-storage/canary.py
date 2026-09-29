#!/usr/bin/env python3
"""CPU-only S3 canary; requires local Python 3 and an authenticated oc CLI.

By default, create/reuse an owned SeaweedFS sandbox and retain its storage.
--endpoint (or --existing) uses an existing server and Secret without changing
either. Only the random test bucket and this invocation's client Pod are deleted.
No credentials are written to local files, command arguments, or logs.
"""

import argparse
import hashlib
import json
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

BASE = Path(__file__).resolve().parents[2] / "infrastructure/gitops/components/seaweedfs"
IMAGE = "public.ecr.aws/aws-cli/aws-cli:2.34.0"
MANAGED = "app.kubernetes.io/managed-by"
MANAGER = "showcase-s3-canary"
RESOURCES = {
    ("Deployment", "seaweedfs"),
    ("Service", "seaweedfs"),
    ("PersistentVolumeClaim", "seaweedfs-data"),
    ("NetworkPolicy", "seaweedfs-s3-only"),
}
CSV = "sensor,value\ntemperature,21.5\npressure,101.3\n"
AUTH_ERRORS = {"AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch", "403"}
MISSING_ERRORS = {"NoSuchBucket", "NoSuchKey", "NotFound", "404"}


class CanaryError(RuntimeError):
    pass


def decode_resources(text):
    """oc create -o json emits consecutive objects for a multi-document input."""
    decoder = json.JSONDecoder()
    resources = []
    remaining = text.strip()
    try:
        while remaining:
            document, end = decoder.raw_decode(remaining)
            resources.extend(document.get("items", [document]))
            remaining = remaining[end:].lstrip()
    except (ValueError, AttributeError, TypeError):
        raise CanaryError("manifest renderer returned invalid JSON (output suppressed)") from None
    return resources


def require(condition, message):
    if not condition:
        raise CanaryError(message)


def error_code(result):
    """Extract a safe S3 code, never echo CLI stderr (which can contain secrets)."""
    match = re.search(r"An error occurred \(([A-Za-z0-9]+)\)", result.stderr)
    return match.group(1) if match else "unknown"


def contains_spec(actual, desired):
    """Compare base fields while allowing API-defaulted fields in live resources."""
    if isinstance(desired, dict):
        return isinstance(actual, dict) and all(k in actual and contains_spec(actual[k], v) for k, v in desired.items())
    if isinstance(desired, list):
        return isinstance(actual, list) and len(actual) == len(desired) and all(contains_spec(a, d) for a, d in zip(actual, desired))
    return actual == desired


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", help="oc context; defaults to the current context")
    parser.add_argument("--namespace", default="showcase-storage-canary")
    parser.add_argument("--secret", default="s3-credentials", help="AWS credential Secret in the client namespace")
    parser.add_argument("--endpoint", help="existing S3 URL reachable from the client Pod; implies --existing")
    parser.add_argument("--existing", action="store_true", help="client only; never deploy or restart storage")
    parser.add_argument("--storage-class", help="explicit class for a new sandbox PVC")
    parser.add_argument("--client-image", default=IMAGE, help="pinned AWS CLI image, optionally from an offline mirror")
    parser.add_argument("--server-image", help="pinned SeaweedFS image override for the owned sandbox")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--timeout", type=int, default=300, help="seconds per readiness/rollout wait (default: 300)")
    parser.add_argument("--check-persistence", action="store_true", help="restart the owned sandbox Deployment and verify stored bytes")
    args = parser.parse_args(argv)
    args.existing = args.existing or args.endpoint is not None
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    for name, value, limit in (("namespace", args.namespace, 63), ("secret", args.secret, 253)):
        parts = value.split(".") if name == "secret" else [value]
        if len(value) > limit or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", p) for p in parts):
            parser.error(f"invalid --{name}")
    if args.existing and (args.check_persistence or args.storage_class is not None or args.server_image):
        parser.error("--check-persistence, --storage-class and --server-image require an owned sandbox (no --endpoint/--existing)")
    if not args.existing and args.secret != "s3-credentials":
        parser.error("custom --secret requires --endpoint or --existing")
    args.endpoint = args.endpoint or f"http://seaweedfs.{args.namespace}.svc:8333"
    try:
        url = urlsplit(args.endpoint)
        valid = (url.scheme in {"http", "https"} and url.hostname and url.port != 0
                 and not url.username and not url.password and not url.query and not url.fragment
                 and url.path in {"", "/"})
    except ValueError:
        valid = False
    if not valid:
        parser.error("--endpoint must be an http(s) origin without credentials, query, fragment, or path")
    return args


class Canary:
    def __init__(self, args):
        self.args = args
        self.run_id = secrets.token_hex(16)
        self.pod = f"s3-canary-{self.run_id}"
        self.bucket = f"storage-canary-{self.run_id}"
        self.pod_uid = None
        self.deployment_uid = None
        self.pvc_uid = None
        self.bucket_owned = False
        self.expected = {}
        self.passed = 0

    def pass_check(self, message):
        self.passed += 1
        print(f"PASS {message}", flush=True)

    def oc(self, *args, stdin=None, timeout=90, check=True):
        command = ["oc"]
        if self.args.context:
            command += ["--context", self.args.context]
        command += [f"--request-timeout={timeout}s", *args]
        try:
            result = subprocess.run(command, input=stdin, text=True, capture_output=True, timeout=timeout + 5, check=False)
        except FileNotFoundError:
            raise CanaryError("oc was not found on PATH") from None
        except subprocess.TimeoutExpired:
            raise CanaryError(f"oc {args[0]} timed out after {timeout}s") from None
        if check and result.returncode:
            # Even API errors may echo a Secret submitted on stdin. Never print them.
            raise CanaryError(f"oc {args[0]} failed (exit {result.returncode}); inspect cluster access/resource status")
        return result

    def decode(self, text):
        try:
            return json.loads(text) if text.strip() else {}
        except ValueError:
            raise CanaryError("command returned invalid JSON (output suppressed)") from None

    def get(self, kind, name, namespaced=True):
        scope = ["-n", self.args.namespace] if namespaced else []
        return self.decode(self.oc("get", kind, name, *scope, "--ignore-not-found", "-o", "json").stdout)

    def labels(self):
        return {MANAGED: MANAGER}

    def owned(self, resource):
        labels = resource.get("metadata", {}).get("labels", {})
        return labels.get(MANAGED) == MANAGER

    def matches_base(self, live, desired):
        # Support a user-prepared sandbox: namespace + Secret are explicitly owned,
        # and unlabeled base objects must match the shared base before adoption.
        if live.get("metadata", {}).get("labels", {}).get(MANAGED):
            return False
        return self.matches_spec(live, desired)

    def matches_spec(self, live, desired, allow_image_override=False):
        spec = json.loads(json.dumps(desired["spec"]))
        if desired["kind"] == "Deployment":
            spec["template"]["metadata"]["labels"].pop(MANAGED, None)
            if allow_image_override:
                for container in spec["template"]["spec"]["containers"]:
                    if container["name"] == "seaweedfs":
                        container.pop("image", None)
        return contains_spec(live.get("spec"), spec)

    def mark_owned(self, live):
        metadata = live["metadata"]
        patch = [{"op": "test", "path": "/metadata/uid", "value": metadata["uid"]},
                 {"op": "test", "path": "/metadata/resourceVersion", "value": metadata["resourceVersion"]},
                 {"op": "add", "path": "/metadata/labels", "value": {**metadata.get("labels", {}), **self.labels()}}]
        return self.decode(self.oc("patch", live["kind"], metadata["name"], "-n", self.args.namespace,
                                   "--type=json", "-p", json.dumps(patch), "-o", "json").stdout)

    def create(self, resource):
        # Create, never apply/upsert: a concurrent foreign resource must cause a conflict.
        return self.decode(self.oc("create", "-f", "-", "-o", "json", stdin=json.dumps(resource)).stdout)

    def render_base(self):
        require(BASE.is_dir(), "shared SeaweedFS base is missing")
        with tempfile.TemporaryDirectory(prefix="storage-canary-") as directory:
            root = Path(directory)
            shutil.copytree(BASE, root / "base")
            overlay = {
                "apiVersion": "kustomize.config.k8s.io/v1beta1", "kind": "Kustomization",
                "resources": ["base"], "namespace": self.args.namespace,
                "labels": [{"pairs": self.labels(), "includeSelectors": False, "includeTemplates": True}],
            }
            if self.args.storage_class is not None:
                overlay["patches"] = [{"target": {"kind": "PersistentVolumeClaim", "name": "seaweedfs-data"},
                                       "patch": json.dumps([{"op": "add", "path": "/spec/storageClassName", "value": self.args.storage_class}])}]
            if self.args.server_image:
                overlay.setdefault("patches", []).append({
                    "patch": json.dumps({"apiVersion": "apps/v1", "kind": "Deployment", "metadata": {"name": "seaweedfs"},
                                         "spec": {"template": {"spec": {"containers": [{"name": "seaweedfs", "image": self.args.server_image}]}}}})
                })
            # This temporary overlay contains only public manifests, never credentials.
            # JSON is valid YAML, but Kustomize only discovers these YAML filenames.
            (root / "kustomization.yaml").write_text(json.dumps(overlay))
            rendered = self.oc("kustomize", str(root)).stdout
        resources = decode_resources(self.oc("create", "--dry-run=client", "--validate=false", "-f", "-", "-o", "json", stdin=rendered).stdout)
        require(len(resources) == len(RESOURCES) and {(r["kind"], r["metadata"]["name"]) for r in resources} == RESOURCES,
                "base must contain only the expected Deployment, Service, PVC, and NetworkPolicy")
        for resource in resources:
            require(resource["metadata"].get("namespace") == self.args.namespace and self.owned(resource),
                    "rendered base has an unexpected namespace or ownership")
            if resource["kind"] == "Deployment":
                spec = resource["spec"]["template"]["spec"]
                for container in spec.get("containers", []) + spec.get("initContainers", []):
                    for values in container.get("resources", {}).values():
                        require(set(values) <= {"cpu", "memory", "ephemeral-storage"}, "base must use CPU-only container resources")
        return resources

    def check_secret(self, secret, owned=False):
        require(bool(secret), f"credential Secret {self.args.secret} is missing")
        if owned:
            require(self.owned(secret), "refusing to reuse or overwrite a foreign credential Secret")
        require(all(secret.get("data", {}).get(key) for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")),
                "credential Secret needs nonempty AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY fields")

    def prepare_storage(self):
        namespace = self.get("namespace", self.args.namespace, namespaced=False)
        if self.args.existing:
            require(bool(namespace), "existing client namespace is missing")
            self.check_secret(self.get("secret", self.args.secret))
            return
        if namespace:
            labels = namespace.get("metadata", {}).get("labels", {})
            require(labels.get(MANAGED) == MANAGER,
                    "refusing to deploy into a foreign namespace; choose a new namespace or use --existing")
        resources = self.render_base()
        existing = {}
        for resource in resources:
            key = (resource["kind"], resource["metadata"]["name"])
            found = self.get(*key) if namespace else {}
            require(not found or self.owned(found) or self.matches_base(found, resource),
                    f"refusing to overwrite foreign {key[0]} {key[1]}")
            existing[key] = found
        secret = self.get("secret", self.args.secret) if namespace else {}
        if secret:
            self.check_secret(secret, owned=True)
        else:
            require(not any(existing.values()), "credentials missing for retained storage; refusing to rotate them")
        pvc = existing[("PersistentVolumeClaim", "seaweedfs-data")]
        if pvc and self.args.storage_class is not None:
            require(pvc["spec"].get("storageClassName") == self.args.storage_class,
                    "retained PVC uses a different StorageClass; use a new sandbox namespace")
        # A rerun must not certify an old deployment against a newer checkout.
        # Never silently replace retained storage or undo a user's customization.
        for resource in resources:
            live = existing[(resource["kind"], resource["metadata"]["name"])]
            if live and self.owned(live):
                require(self.matches_spec(live, resource, allow_image_override=bool(self.args.server_image)),
                        f"retained {resource['kind']} differs from the current base; reconcile the owned sandbox "
                        "explicitly or use a new --namespace before validating")
        if not namespace:
            self.create({"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": self.args.namespace, "labels": self.labels()}})
        if not secret:
            # RHOAI S3 connection fields. The bucket is temporary and removed at exit.
            self.create({"apiVersion": "v1", "kind": "Secret", "type": "Opaque",
                         "metadata": {"name": self.args.secret, "namespace": self.args.namespace, "labels": self.labels()},
                         "stringData": {"AWS_ACCESS_KEY_ID": secrets.token_hex(16),
                                        "AWS_SECRET_ACCESS_KEY": secrets.token_urlsafe(36),
                                        "AWS_DEFAULT_REGION": self.args.region,
                                        "AWS_S3_ENDPOINT": self.args.endpoint, "AWS_S3_BUCKET": self.bucket}})
        order = {"NetworkPolicy": 0, "PersistentVolumeClaim": 1, "Service": 2, "Deployment": 3}
        for resource in sorted(resources, key=lambda r: order[r["kind"]]):
            key = (resource["kind"], resource["metadata"]["name"])
            live = existing[key] or self.create(resource)
            if not self.owned(live):
                live = self.mark_owned(live)
            if resource["kind"] == "Deployment":
                self.deployment_uid = live["metadata"]["uid"]
                if self.args.server_image:
                    containers = live["spec"]["template"]["spec"]["containers"]
                    index = next(i for i, container in enumerate(containers) if container["name"] == "seaweedfs")
                    if containers[index]["image"] != self.args.server_image:
                        patch = [{"op": "test", "path": "/metadata/uid", "value": self.deployment_uid},
                                 {"op": "test", "path": "/metadata/resourceVersion", "value": live["metadata"]["resourceVersion"]},
                                 {"op": "replace", "path": f"/spec/template/spec/containers/{index}/image", "value": self.args.server_image}]
                        self.oc("patch", "deployment", "seaweedfs", "-n", self.args.namespace, "--type=json", "-p", json.dumps(patch))
            elif resource["kind"] == "PersistentVolumeClaim":
                self.pvc_uid = live["metadata"]["uid"]
        self.wait_storage()
        self.pass_check("owned SeaweedFS sandbox ready (CPU only)")

    def wait_storage(self):
        self.oc("wait", "-n", self.args.namespace, "pvc/seaweedfs-data", "--for=jsonpath={.status.phase}=Bound",
                f"--timeout={self.args.timeout}s", timeout=self.args.timeout + 10)
        self.oc("rollout", "status", "-n", self.args.namespace, "deployment/seaweedfs",
                f"--timeout={self.args.timeout}s", timeout=self.args.timeout + 10)

    def client_manifest(self):
        env = {"HOME": "/tmp", "TMPDIR": "/tmp", "AWS_CONFIG_FILE": "/tmp/aws-config",
               "AWS_SHARED_CREDENTIALS_FILE": "/tmp/no-credentials", "AWS_DEFAULT_REGION": self.args.region,
               "AWS_EC2_METADATA_DISABLED": "true", "AWS_MAX_ATTEMPTS": "1", "AWS_PAGER": "",
               "AWS_CLI_AUTO_PROMPT": "off"}
        return {"apiVersion": "v1", "kind": "Pod",
                "metadata": {"name": self.pod, "namespace": self.args.namespace,
                             "labels": {**self.labels(), "showcase.redhat.com/storage-canary-run": self.run_id}},
                "spec": {"restartPolicy": "Never", "automountServiceAccountToken": False,
                         "activeDeadlineSeconds": 2 * self.args.timeout + 1800,
                         "securityContext": {"runAsNonRoot": True, "seccompProfile": {"type": "RuntimeDefault"}},
                         "containers": [{"name": "aws", "image": self.args.client_image, "workingDir": "/tmp",
                                         "command": ["/bin/sh", "-ec"],
                                         "args": ["umask 077; printf '[default]\\ns3 =\\n    addressing_style = path\\n    signature_version = s3v4\\n' > /tmp/aws-config; exec sleep 86400"],
                                         "env": [{"name": k, "value": v} for k, v in env.items()] + [
                                             {"name": k, "valueFrom": {"secretKeyRef": {"name": self.args.secret, "key": k}}}
                                             for k in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")],
                                         "securityContext": {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True,
                                                             "capabilities": {"drop": ["ALL"]}},
                                         "resources": {"requests": {"cpu": "100m", "memory": "128Mi"},
                                                       "limits": {"cpu": "1", "memory": "512Mi"}},
                                         "volumeMounts": [{"name": "tmp", "mountPath": "/tmp"}]}],
                         "volumes": [{"name": "tmp", "emptyDir": {"sizeLimit": "128Mi"}}]}}

    def prepare_client(self):
        live = self.create(self.client_manifest())
        self.pod_uid = live["metadata"]["uid"]
        self.oc("wait", "-n", self.args.namespace, f"pod/{self.pod}", "--for=condition=Ready",
                f"--timeout={self.args.timeout}s", timeout=self.args.timeout + 10)
        self.exec("aws", "--version")
        self.pass_check("AWS CLI client ready with Secret references and restricted Pod settings")

    def exec(self, *args, stdin=None, check=True):
        return self.oc("exec", "-i", "-n", self.args.namespace, self.pod, "-c", "aws", "--", *args, stdin=stdin, check=check)

    def s3_result(self, operation, *args, auth="valid"):
        command = ["aws", "--endpoint-url", self.args.endpoint, "--region", self.args.region,
                   "--output", "json", "--no-cli-pager", "--no-paginate", "--cli-connect-timeout", "10", "--cli-read-timeout", "30"]
        if auth == "anonymous":
            command += ["--no-sign-request"]
        if auth == "wrong":
            command = ["env", "AWS_ACCESS_KEY_ID=canary-invalid-key", "AWS_SECRET_ACCESS_KEY=canary-invalid-secret", *command]
        return self.exec(*command, "s3api", operation, *args, check=False)

    def s3(self, operation, *args):
        result = self.s3_result(operation, *args)
        require(result.returncode == 0, f"S3 {operation} failed ({error_code(result)}; raw output suppressed)")
        return self.decode(result.stdout)

    def write(self, path, data):
        self.exec("/bin/sh", "-ec", 'cat > "$1"', "canary-write", path, stdin=data)

    def verify_object(self, key, digest=None, byte_range=None):
        extra = ["--range", byte_range] if byte_range else []
        self.s3("get-object", "--bucket", self.bucket, "--key", key, *extra, "/tmp/download")
        actual = self.exec("sha256sum", "/tmp/download").stdout.split()[0]
        require(actual == (digest or self.expected[key]), f"SHA256 mismatch for {key}")

    def objects(self, page_size=1000):
        objects, token, seen = [], None, set()
        for _ in range(100):
            args = ["--continuation-token", token] if token else []
            page = self.s3("list-objects-v2", "--bucket", self.bucket, "--max-keys", str(page_size), *args)
            items = page.get("Contents", [])
            require(len(items) <= page_size, "ListObjectsV2 ignored --max-keys")
            objects.extend(item["Key"] for item in items)
            if not page.get("IsTruncated", False):
                return objects
            token = page.get("NextContinuationToken")
            require(bool(token) and token not in seen, "ListObjectsV2 returned a missing/repeated continuation token")
            seen.add(token)
        raise CanaryError("ListObjectsV2 exceeded 100 pages")

    def exercise(self):
        buckets = self.s3("list-buckets")
        require(self.bucket not in {b["Name"] for b in buckets.get("Buckets", [])}, "random bucket name already exists; refusing to reuse it")
        before = self.s3_result("head-bucket", "--bucket", self.bucket)
        require(before.returncode != 0 and error_code(before) in MISSING_ERRORS, "cannot establish that the random test bucket is absent")
        extra = [] if self.args.region == "us-east-1" else ["--create-bucket-configuration", json.dumps({"LocationConstraint": self.args.region})]
        self.s3("create-bucket", "--bucket", self.bucket, *extra)
        self.bucket_owned = True
        self.s3("head-bucket", "--bucket", self.bucket)
        require(self.bucket in {b["Name"] for b in self.s3("list-buckets").get("Buckets", [])}, "created bucket missing from ListBuckets")
        self.pass_check("bucket create / head / list")

        self.write("/tmp/sample.csv", CSV)
        self.expected["sample.csv"] = hashlib.sha256(CSV.encode()).hexdigest()
        self.s3("put-object", "--bucket", self.bucket, "--key", "sample.csv", "--body", "/tmp/sample.csv", "--content-type", "text/csv")
        metadata = self.s3("head-object", "--bucket", self.bucket, "--key", "sample.csv")
        require(metadata.get("ContentLength") == len(CSV.encode()) and metadata.get("ContentType") == "text/csv",
                "HeadObject CSV content length/type mismatch")
        self.pass_check("HeadObject CSV content length / content type")
        self.verify_object("sample.csv")
        self.pass_check("tiny CSV put / get SHA256 integrity")
        self.verify_object("sample.csv", hashlib.sha256(CSV.encode()[7:20]).hexdigest(), "bytes=7-19")
        self.pass_check("Range GET exact bytes")

        for mode in ("wrong", "anonymous"):
            result = self.s3_result("get-object", "--bucket", self.bucket, "--key", "sample.csv", "/tmp/denied", auth=mode)
            require(result.returncode != 0 and error_code(result) in AUTH_ERRORS,
                    f"{mode} credentials were not explicitly rejected by S3")
            self.pass_check(f"{mode} credentials rejected")

        self.s3("copy-object", "--bucket", self.bucket, "--key", "copy.csv", "--copy-source", f"{self.bucket}/sample.csv")
        self.expected["copy.csv"] = self.expected["sample.csv"]
        self.verify_object("copy.csv")
        self.pass_check("CopyObject SHA256 integrity")

        parts = ["a" * (5 * 1024 * 1024), "b" * (1024 * 1024)]
        upload = self.s3("create-multipart-upload", "--bucket", self.bucket, "--key", "multipart.bin")["UploadId"]
        completed = []
        for number, data in enumerate(parts, 1):
            path = f"/tmp/part{number}"
            self.write(path, data)
            part = self.s3("upload-part", "--bucket", self.bucket, "--key", "multipart.bin", "--upload-id", upload,
                           "--part-number", str(number), "--body", path)
            completed.append({"PartNumber": number, "ETag": part["ETag"]})
        self.s3("complete-multipart-upload", "--bucket", self.bucket, "--key", "multipart.bin", "--upload-id", upload,
                "--multipart-upload", json.dumps({"Parts": completed}))
        self.expected["multipart.bin"] = hashlib.sha256("".join(parts).encode()).hexdigest()
        self.verify_object("multipart.bin")
        self.pass_check("multipart upload / complete: 5 MiB + 1 MiB, SHA256 integrity")

        upload = self.s3("create-multipart-upload", "--bucket", self.bucket, "--key", "aborted.bin")["UploadId"]
        self.s3("upload-part", "--bucket", self.bucket, "--key", "aborted.bin", "--upload-id", upload,
                "--part-number", "1", "--body", "/tmp/part1")
        self.s3("abort-multipart-upload", "--bucket", self.bucket, "--key", "aborted.bin", "--upload-id", upload)
        uploads = self.s3("list-multipart-uploads", "--bucket", self.bucket)
        require(not uploads.get("Uploads") and not uploads.get("IsTruncated"), "multipart uploads remain after abort/complete")
        absent = self.s3_result("head-object", "--bucket", self.bucket, "--key", "aborted.bin")
        require(absent.returncode != 0 and error_code(absent) in MISSING_ERRORS, "aborted multipart upload left a visible object")
        self.pass_check("aborted multipart upload cleanup")

        listed = self.objects(page_size=1)
        require(len(listed) == len(self.expected) and set(listed) == set(self.expected), "paginated ListObjectsV2 returned missing/duplicate/unexpected keys")
        self.pass_check("paginated ListObjectsV2 with explicit continuation tokens")

    def check_persistence(self):
        require(not self.args.existing and self.deployment_uid is not None, "persistence restart requires an owned sandbox")
        live = self.get("deployment", "seaweedfs")
        require(self.owned(live) and live["metadata"]["uid"] == self.deployment_uid, "refusing to restart a foreign/replaced Deployment")
        metadata = live["spec"]["template"]["metadata"]
        annotations = {**metadata.get("annotations", {}), "showcase.redhat.com/storage-canary-restart": self.run_id}
        patch = [{"op": "test", "path": "/metadata/uid", "value": self.deployment_uid},
                 {"op": "test", "path": "/metadata/resourceVersion", "value": live["metadata"]["resourceVersion"]},
                 {"op": "add", "path": "/spec/template/metadata/annotations", "value": annotations}]
        self.oc("patch", "deployment", "seaweedfs", "-n", self.args.namespace, "--type=json", "-p", json.dumps(patch))
        self.wait_storage()
        pvc = self.get("pvc", "seaweedfs-data")
        require(self.owned(pvc) and pvc["metadata"]["uid"] == self.pvc_uid, "PVC identity changed during persistence check")
        for key in self.expected:
            self.verify_object(key)
        self.pass_check("persistence: same PVC and all SHA256 digests after owned Deployment restart")

    def cleanup_bucket(self):
        if not self.bucket_owned:
            return
        uploads = self.s3("list-multipart-uploads", "--bucket", self.bucket)
        require(not uploads.get("IsTruncated"), "unexpectedly truncated upload cleanup; test bucket retained")
        for upload in uploads.get("Uploads", []):
            self.s3("abort-multipart-upload", "--bucket", self.bucket, "--key", upload["Key"], "--upload-id", upload["UploadId"])
        for key in self.objects():
            self.s3("delete-object", "--bucket", self.bucket, "--key", key)
        require(not self.objects(), "objects remain after delete")
        self.s3("delete-bucket", "--bucket", self.bucket)
        result = self.s3_result("head-bucket", "--bucket", self.bucket)
        require(result.returncode != 0 and error_code(result) in MISSING_ERRORS, "deleted bucket is still present or its absence cannot be verified")
        self.bucket_owned = False
        self.pass_check("delete objects / multipart cleanup / delete test bucket")

    def cleanup_pod(self):
        if not self.pod_uid:
            return
        live = self.get("pod", self.pod)
        if not live:
            return
        require(self.owned(live) and live["metadata"]["uid"] == self.pod_uid
                and live["metadata"]["labels"].get("showcase.redhat.com/storage-canary-run") == self.run_id,
                "refusing to delete a foreign/replaced client Pod")
        # API preconditions close the read/delete race; no broad selectors or force.
        self.oc("delete", "--raw", f"/api/v1/namespaces/{self.args.namespace}/pods/{self.pod}", "-f", "-",
                stdin=json.dumps({"apiVersion": "v1", "kind": "DeleteOptions", "preconditions": {"uid": self.pod_uid}}))
        self.oc("wait", "-n", self.args.namespace, f"pod/{self.pod}", "--for=delete", "--timeout=60s", timeout=70)
        self.pass_check("owned temporary client Pod removed")

    def run(self):
        errors = []
        try:
            self.prepare_storage()
            self.prepare_client()
            self.exercise()
            if self.args.check_persistence:
                self.check_persistence()
        except (CanaryError, OSError, KeyError, IndexError, TypeError, KeyboardInterrupt) as exc:
            errors.append(str(exc) if isinstance(exc, CanaryError) else f"{type(exc).__name__} (details suppressed)")
        finally:
            for cleanup in (self.cleanup_bucket, self.cleanup_pod):
                try:
                    cleanup()
                except (CanaryError, OSError, KeyError, IndexError, TypeError, KeyboardInterrupt) as exc:
                    errors.append(str(exc) if isinstance(exc, CanaryError) else f"cleanup {type(exc).__name__} (details suppressed)")
        if self.bucket_owned:
            print(f"FAIL test bucket retained after cleanup failure: {self.bucket}", file=sys.stderr)
        for error in errors:
            print(f"FAIL {error}", file=sys.stderr)
        if not self.args.existing:
            print(f"INFO sandbox retained for inspection: namespace {self.args.namespace}; SeaweedFS / PVC / Secret retained if created")
        print(f"{'FAIL' if errors else 'PASS'} S3 canary: {self.passed} checks passed; {len(errors)} failures")
        return 1 if errors else 0


def main(argv=None):
    args = parse_args(argv)

    def interrupted(signum, frame):
        raise KeyboardInterrupt()

    previous = signal.signal(signal.SIGTERM, interrupted)
    try:
        return Canary(args).run()
    finally:
        signal.signal(signal.SIGTERM, previous)


if __name__ == "__main__":
    sys.exit(main())
