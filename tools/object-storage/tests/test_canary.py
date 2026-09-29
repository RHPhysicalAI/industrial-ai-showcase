"""Local unit tests: python3 -m unittest discover -s tools/object-storage/tests -v."""

import copy
import hashlib
import importlib.util
import io
import json
import shutil
import subprocess
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

MODULE = Path(__file__).resolve().parents[1] / "canary.py"
spec = importlib.util.spec_from_file_location("storage_canary", MODULE)
canary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(canary)


def response(value=None, code=None):
    return subprocess.CompletedProcess([], 1 if code else 0, json.dumps(value) if value is not None else "",
                                       f"An error occurred ({code}) when calling the operation" if code else "")


def resource(kind, name, owned=True, spec=None):
    return {"apiVersion": "v1", "kind": kind,
            "metadata": {"name": name, "namespace": "showcase-storage-canary", "uid": f"uid-{name}",
                         "resourceVersion": "1", "labels": {canary.MANAGED: canary.MANAGER} if owned else {}},
            "spec": spec or {}}


def base_resources(owned=True):
    return [resource("NetworkPolicy", "seaweedfs-s3-only", owned, {"podSelector": {"matchLabels": {"app": "seaweedfs"}}}),
            resource("Service", "seaweedfs", owned, {"ports": [{"port": 8333, "targetPort": "s3"}]}),
            resource("PersistentVolumeClaim", "seaweedfs-data", owned, {"resources": {"requests": {"storage": "5Gi"}}}),
            resource("Deployment", "seaweedfs", owned,
                     {"template": {"metadata": {"labels": {"app": "seaweedfs", **({canary.MANAGED: canary.MANAGER} if owned else {})}},
                                   "spec": {"containers": [{"name": "seaweedfs", "image": "seaweedfs:test",
                                                            "envFrom": [{"secretRef": {"name": "s3-credentials"}}],
                                                            "resources": {"requests": {"cpu": "100m", "memory": "256Mi"}}}]}}})]


class FakeCluster(canary.Canary):
    def __init__(self, argv=(), base_owned=True):
        super().__init__(canary.parse_args(list(argv)))
        self.cluster = {(r["kind"].lower(), r["metadata"]["name"]): r for r in base_resources(base_owned)}
        self.cluster[("namespace", self.args.namespace)] = resource("Namespace", self.args.namespace)
        secret = resource("Secret", self.args.secret)
        secret["data"] = {"AWS_ACCESS_KEY_ID": "test-base64-key", "AWS_SECRET_ACCESS_KEY": "test-base64-secret"}
        self.cluster[("secret", self.args.secret)] = secret
        self.created, self.calls = [], []

    def get(self, kind, name, namespaced=True):
        kind = {"pvc": "persistentvolumeclaim"}.get(kind.lower(), kind.lower())
        return copy.deepcopy(self.cluster.get((kind, name), {}))

    def render_base(self):
        return base_resources()

    def create(self, obj):
        self.created.append(copy.deepcopy(obj))
        obj = copy.deepcopy(obj)
        obj["metadata"].update(uid=f"uid-{obj['metadata']['name']}", resourceVersion="1")
        if obj["kind"] == "Secret":
            obj["data"] = obj.pop("stringData")
        self.cluster[(obj["kind"].lower(), obj["metadata"]["name"])] = obj
        return obj

    def oc(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if args[0] == "patch":
            live = self.cluster[(args[1].lower(), args[2])]
            changes = json.loads(args[args.index("-p") + 1])
            for change in changes:
                if change["path"] == "/metadata/labels":
                    live["metadata"]["labels"] = change["value"]
            return response(live)
        return response()


class CanaryTests(unittest.TestCase):
    def test_defaults_and_existing_endpoint_guards(self):
        default = canary.parse_args([])
        self.assertEqual(default.namespace, "showcase-storage-canary")
        self.assertIsNone(default.context)
        self.assertEqual(default.endpoint, "http://seaweedfs.showcase-storage-canary.svc:8333")
        self.assertFalse(default.existing)
        for argv in (["--endpoint", "https://s3.example.test"], ["--existing"]):
            self.assertTrue(canary.parse_args(argv).existing)
            for extra in (["--check-persistence"], ["--storage-class", "gp3"], ["--server-image", "mirror/seaweedfs:4.48"]):
                with self.subTest(argv=argv, extra=extra), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    canary.parse_args(argv + extra)

    def test_rejects_unsafe_inputs_before_oc(self):
        cases = [["--endpoint", "https://key:secret@s3.example.test"],
                 ["--endpoint", "https://s3.example.test?X-Amz-Signature=secret"],
                 ["--endpoint", "https://s3.example.test/path"], ["--endpoint", "http://s3:bad"],
                 ["--namespace", "../../other"], ["--namespace", ""], ["--secret", "bad/name"],
                 ["--secret", "another-secret"], ["--timeout", "0"]]
        for argv in cases:
            with self.subTest(argv=argv), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                canary.parse_args(argv)

    def test_foreign_namespace_fails_without_mutation(self):
        runner = FakeCluster()
        runner.cluster[("namespace", runner.args.namespace)]["metadata"]["labels"] = {}
        with self.assertRaisesRegex(canary.CanaryError, "foreign namespace"):
            runner.prepare_storage()
        self.assertFalse(runner.created or runner.calls)

    def test_foreign_secret_fails_before_base_adoption(self):
        runner = FakeCluster(base_owned=False)
        runner.cluster[("secret", runner.args.secret)]["metadata"]["labels"] = {}
        with self.assertRaisesRegex(canary.CanaryError, "foreign credential Secret"):
            runner.prepare_storage()
        self.assertFalse(runner.created or runner.calls)

    def test_owned_namespace_and_secret_reuse_applied_base(self):
        runner = FakeCluster(base_owned=False)
        original_secret = copy.deepcopy(runner.cluster[("secret", runner.args.secret)])
        # Admission defaults do not prevent adoption of the user's exact shared base.
        runner.cluster[("service", "seaweedfs")]["spec"]["clusterIP"] = "192.0.2.5"
        with redirect_stdout(io.StringIO()):
            runner.prepare_storage()
        self.assertFalse(runner.created)
        self.assertEqual(original_secret, runner.cluster[("secret", runner.args.secret)])
        patches = [args for args, _ in runner.calls if args[0] == "patch"]
        self.assertEqual(len(patches), 4)
        for args in patches:
            changes = json.loads(args[args.index("-p") + 1])
            self.assertEqual([x["path"] for x in changes], ["/metadata/uid", "/metadata/resourceVersion", "/metadata/labels"])
            self.assertEqual(changes[-1]["value"][canary.MANAGED], "showcase-s3-canary")
        self.assertEqual(runner.deployment_uid, "uid-seaweedfs")

    def test_unlabeled_mismatching_resource_is_not_adopted(self):
        runner = FakeCluster(base_owned=False)
        runner.cluster[("deployment", "seaweedfs")]["spec"]["template"]["spec"]["containers"][0]["image"] = "unrelated:latest"
        with self.assertRaisesRegex(canary.CanaryError, "foreign Deployment"):
            runner.prepare_storage()
        self.assertFalse(runner.created or runner.calls)

    def test_resource_owned_by_another_manager_is_not_adopted(self):
        runner = FakeCluster()
        runner.cluster[("service", "seaweedfs")]["metadata"]["labels"][canary.MANAGED] = "somebody-else"
        with self.assertRaisesRegex(canary.CanaryError, "foreign Service"):
            runner.prepare_storage()
        self.assertFalse(runner.created or runner.calls)

    def test_missing_secret_never_rotates_retained_storage(self):
        runner = FakeCluster()
        del runner.cluster[("secret", runner.args.secret)]
        with self.assertRaisesRegex(canary.CanaryError, "refusing to rotate"):
            runner.prepare_storage()
        self.assertFalse(runner.created or runner.calls)

    def test_missing_secret_field_is_actionable(self):
        runner = FakeCluster()
        del runner.cluster[("secret", runner.args.secret)]["data"]["AWS_SECRET_ACCESS_KEY"]
        with self.assertRaisesRegex(canary.CanaryError, "AWS_SECRET_ACCESS_KEY"):
            runner.prepare_storage()

    def test_owned_rerun_does_not_reapply_resources_or_secret(self):
        runner = FakeCluster()
        with redirect_stdout(io.StringIO()):
            runner.prepare_storage()
        self.assertFalse(runner.created)
        self.assertEqual([args[0] for args, _ in runner.calls], ["wait", "rollout"])

    def test_owned_but_outdated_base_is_not_certified_or_overwritten(self):
        for kind, name in (("deployment", "seaweedfs"), ("networkpolicy", "seaweedfs-s3-only")):
            runner = FakeCluster()
            runner.cluster[(kind, name)]["spec"] = {}
            with self.subTest(kind=kind), self.assertRaisesRegex(canary.CanaryError, "differs from the current base"):
                runner.prepare_storage()
            self.assertFalse(runner.created or runner.calls)

    def test_sigterm_runs_cleanups_and_restores_previous_handler(self):
        runner = FakeCluster()
        runner.prepare_storage = Mock()
        runner.prepare_client = Mock()
        runner.cleanup_bucket = Mock()
        runner.cleanup_pod = Mock()
        previous = canary.signal.getsignal(canary.signal.SIGTERM)

        def terminate():
            canary.signal.getsignal(canary.signal.SIGTERM)(canary.signal.SIGTERM, None)

        runner.exercise = terminate
        with patch.object(canary, "Canary", return_value=runner), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(canary.main([]), 1)
        runner.cleanup_bucket.assert_called_once()
        runner.cleanup_pod.assert_called_once()
        self.assertEqual(canary.signal.getsignal(canary.signal.SIGTERM), previous)

    def test_storage_class_mismatch_fails_before_mutation(self):
        runner = FakeCluster(["--storage-class", "other"])
        runner.cluster[("persistentvolumeclaim", "seaweedfs-data")]["spec"]["storageClassName"] = "gp3"
        with self.assertRaisesRegex(canary.CanaryError, "different StorageClass"):
            runner.prepare_storage()
        self.assertFalse(runner.created or runner.calls)

    def test_existing_mode_does_not_render_deploy_label_or_restart(self):
        runner = FakeCluster(["--endpoint", "http://external.svc:8333", "--secret", "external-secret"])
        for obj in runner.cluster.values():
            obj["metadata"]["labels"] = {}
        runner.render_base = Mock(side_effect=AssertionError("must not render"))
        runner.prepare_storage()
        self.assertFalse(runner.created or runner.calls)
        with self.assertRaisesRegex(canary.CanaryError, "owned sandbox"):
            runner.check_persistence()

    def test_new_credentials_are_random_and_use_rhoai_fields(self):
        credentials = []
        for _ in range(2):
            runner = FakeCluster()
            runner.cluster.clear()
            output = io.StringIO()
            with redirect_stdout(output):
                runner.prepare_storage()
            secret = next(obj for obj in runner.created if obj["kind"] == "Secret")
            self.assertEqual(secret["metadata"]["labels"][canary.MANAGED], "showcase-s3-canary")
            fields = secret["stringData"]
            self.assertEqual(set(fields), {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_DEFAULT_REGION", "AWS_S3_ENDPOINT", "AWS_S3_BUCKET"})
            self.assertNotIn(fields["AWS_ACCESS_KEY_ID"], output.getvalue())
            self.assertNotIn(fields["AWS_SECRET_ACCESS_KEY"], output.getvalue())
            self.assertGreaterEqual(len(fields["AWS_SECRET_ACCESS_KEY"]), 40)
            credentials.append(fields)
        self.assertNotEqual(credentials[0]["AWS_ACCESS_KEY_ID"], credentials[1]["AWS_ACCESS_KEY_ID"])
        self.assertNotEqual(credentials[0]["AWS_SECRET_ACCESS_KEY"], credentials[1]["AWS_SECRET_ACCESS_KEY"])

    def test_secret_is_created_via_stdin_and_failure_does_not_leak(self):
        runner = canary.Canary(canary.parse_args(["--context", "hub"]))
        secret = {"kind": "Secret", "stringData": {"AWS_SECRET_ACCESS_KEY": "SENSITIVE-SENTINEL"}}
        failed = subprocess.CompletedProcess([], 1, "SENSITIVE-SENTINEL", "invalid: SENSITIVE-SENTINEL")
        with patch.object(canary.subprocess, "run", return_value=failed) as run, self.assertRaises(canary.CanaryError) as raised:
            runner.create(secret)
        self.assertNotIn("SENSITIVE-SENTINEL", str(raised.exception))
        command = run.call_args.args[0]
        self.assertEqual(command[:3], ["oc", "--context", "hub"])
        self.assertIn("--request-timeout=90s", command)
        self.assertNotIn("SENSITIVE-SENTINEL", " ".join(command))
        self.assertEqual(json.loads(run.call_args.kwargs["input"]), secret)
        self.assertTrue(run.call_args.kwargs["capture_output"])
        self.assertEqual(run.call_args.kwargs["timeout"], 95)

    def test_missing_oc_and_timeout_are_safe_failures(self):
        runner = canary.Canary(canary.parse_args([]))
        failures = [FileNotFoundError(), subprocess.TimeoutExpired(["oc"], 1, output="SENSITIVE")]
        for failure in failures:
            with patch.object(canary.subprocess, "run", side_effect=failure), self.assertRaises(canary.CanaryError) as raised:
                runner.oc("get", "pod")
            self.assertNotIn("SENSITIVE", str(raised.exception))

    def test_client_is_cpu_only_arbitrary_uid_restricted_and_secret_referenced(self):
        runner = canary.Canary(canary.parse_args([]))
        spec = runner.client_manifest()["spec"]
        container = spec["containers"][0]
        self.assertEqual(container["image"], "public.ecr.aws/aws-cli/aws-cli:2.34.0")
        self.assertFalse(spec["automountServiceAccountToken"])
        self.assertTrue(spec["securityContext"]["runAsNonRoot"])
        self.assertNotIn("runAsUser", spec["securityContext"])
        self.assertNotIn("runAsUser", container["securityContext"])
        self.assertFalse(container["securityContext"]["allowPrivilegeEscalation"])
        self.assertEqual(container["securityContext"]["capabilities"]["drop"], ["ALL"])
        self.assertTrue(container["securityContext"]["readOnlyRootFilesystem"])
        self.assertEqual(spec["securityContext"]["seccompProfile"]["type"], "RuntimeDefault")
        for values in container["resources"].values():
            self.assertEqual(set(values), {"cpu", "memory"})
        env = {item["name"]: item for item in container["env"]}
        for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
            self.assertEqual(env[key]["valueFrom"]["secretKeyRef"], {"name": "s3-credentials", "key": key})
        self.assertEqual(env["HOME"]["value"], "/tmp")
        self.assertEqual(env["AWS_CONFIG_FILE"]["value"], "/tmp/aws-config")
        self.assertNotIn("AWS_REQUEST_CHECKSUM_CALCULATION", env)
        self.assertNotIn("AWS_RESPONSE_CHECKSUM_VALIDATION", env)
        self.assertIn("signature_version = s3v4", container["args"][0])
        self.assertEqual(container["workingDir"], "/tmp")
        self.assertEqual(container["volumeMounts"], [{"name": "tmp", "mountPath": "/tmp"}])
        self.assertGreater(spec["activeDeadlineSeconds"], 0)

    def test_rendered_overlay_overrides_namespace_and_only_explicit_storage_class(self):
        for argv in ([], ["--storage-class", "gp3"], ["--server-image", "mirror/seaweedfs:4.48"]):
            runner = canary.Canary(canary.parse_args(argv))
            roots = []

            def oc(*args, roots=roots, runner=runner, argv=argv, **kwargs):
                if args[0] == "kustomize":
                    root = Path(args[1])
                    roots.append(root)
                    overlay = json.loads((root / "kustomization.yaml").read_text())
                    self.assertTrue((root / "base/kustomization.yaml").is_file())
                    self.assertEqual(overlay["namespace"], runner.args.namespace)
                    self.assertEqual(overlay["labels"][0]["pairs"], {canary.MANAGED: canary.MANAGER})
                    if "--storage-class" in argv:
                        self.assertEqual(json.loads(overlay["patches"][0]["patch"])[0]["value"], "gp3")
                    elif "--server-image" in argv:
                        deployment = json.loads(overlay["patches"][0]["patch"])
                        self.assertEqual(deployment["spec"]["template"]["spec"]["containers"][0]["image"], "mirror/seaweedfs:4.48")
                    else:
                        self.assertNotIn("patches", overlay)
                    return subprocess.CompletedProcess([], 0, "rendered-base", "")
                self.assertIn("--dry-run=client", args)
                self.assertEqual(kwargs["stdin"], "rendered-base")
                return response({"kind": "List", "items": base_resources()})

            runner.oc = oc
            self.assertEqual(len(runner.render_base()), 4)
            self.assertTrue(all(not root.exists() for root in roots))

    @unittest.skipUnless(shutil.which("oc"), "oc required for local Kustomize smoke test")
    def test_actual_kustomize_discovers_overlay_and_renders_overrides(self):
        runner = canary.Canary(canary.parse_args(["--storage-class", "gp3", "--server-image", "mirror/seaweedfs:4.48"]))
        real_run = subprocess.run
        rendered = []

        def local_run(command, **kwargs):
            if "kustomize" in command:
                result = real_run(command, **kwargs)
                self.assertEqual(result.returncode, 0, result.stderr)
                rendered.append(result.stdout)
                return result
            # Never contact a cluster: only the YAML-to-JSON conversion is mocked.
            self.assertIn("--dry-run=client", command)
            self.assertEqual(kwargs["input"], rendered[0])
            return response({"kind": "List", "items": base_resources()})

        with patch.object(canary.subprocess, "run", side_effect=local_run):
            self.assertEqual(len(runner.render_base()), 4)
        self.assertIn("namespace: showcase-storage-canary", rendered[0])
        self.assertIn("storageClassName: gp3", rendered[0])
        self.assertIn("image: mirror/seaweedfs:4.48", rendered[0])
        self.assertIn("app.kubernetes.io/managed-by: showcase-s3-canary", rendered[0])

    def test_mirrored_images_override_client_and_owned_server(self):
        runner = FakeCluster(["--client-image", "mirror/aws-cli:2.34.0", "--server-image", "mirror/seaweedfs:4.48"])
        self.assertEqual(runner.client_manifest()["spec"]["containers"][0]["image"], "mirror/aws-cli:2.34.0")
        with redirect_stdout(io.StringIO()):
            runner.prepare_storage()
        args = next(args for args, _ in runner.calls if args[0] == "patch")
        changes = json.loads(args[args.index("-p") + 1])
        self.assertEqual(changes[0]["path"], "/metadata/uid")
        self.assertEqual(changes[1]["path"], "/metadata/resourceVersion")
        self.assertEqual(changes[2], {"op": "replace", "path": "/spec/template/spec/containers/0/image", "value": "mirror/seaweedfs:4.48"})

    def test_s3_calls_disable_automatic_pagination_and_bound_network_time(self):
        runner = canary.Canary(canary.parse_args([]))
        runner.exec = Mock(return_value=response({}))
        runner.s3_result("list-objects-v2", "--max-keys", "1")
        args = runner.exec.call_args.args
        self.assertIn("--no-paginate", args)
        self.assertIn("--cli-connect-timeout", args)
        self.assertIn("--cli-read-timeout", args)
        self.assertEqual(args[args.index("--endpoint-url") + 1], runner.args.endpoint)
        runner.s3_result("get-object", auth="wrong")
        self.assertEqual(runner.exec.call_args.args[0], "env")
        runner.s3_result("get-object", auth="anonymous")
        self.assertIn("--no-sign-request", runner.exec.call_args.args)

    def test_missing_or_repeated_pagination_token_fails(self):
        for page in ({"IsTruncated": True}, {"IsTruncated": True, "NextContinuationToken": "same"}):
            runner = canary.Canary(canary.parse_args([]))
            runner.s3 = Mock(return_value=page)
            with self.assertRaisesRegex(canary.CanaryError, "continuation token"):
                runner.objects(page_size=1)
            self.assertLessEqual(runner.s3.call_count, 2)

    def test_pagination_follows_service_token_without_duplicates(self):
        runner = canary.Canary(canary.parse_args([]))
        runner.s3 = Mock(side_effect=[{"Contents": [{"Key": "a"}], "IsTruncated": True, "NextContinuationToken": "next"},
                                      {"Contents": [{"Key": "b"}], "IsTruncated": False}])
        self.assertEqual(runner.objects(page_size=1), ["a", "b"])
        self.assertEqual(runner.s3.call_args.args[-2:], ("--continuation-token", "next"))

    def test_persistence_rejects_replaced_or_foreign_deployment(self):
        for foreign in (True, False):
            runner = FakeCluster(["--check-persistence"])
            runner.deployment_uid = "uid-seaweedfs"
            live = runner.cluster[("deployment", "seaweedfs")]
            if foreign:
                live["metadata"]["labels"] = {}
            else:
                live["metadata"]["uid"] = "replacement"
            with self.assertRaisesRegex(canary.CanaryError, "foreign/replaced Deployment"):
                runner.check_persistence()
            self.assertFalse(runner.calls)

    def test_persistence_tests_uid_and_version_preserves_annotations_checks_data(self):
        runner = FakeCluster(["--check-persistence"])
        runner.deployment_uid = "uid-seaweedfs"
        runner.pvc_uid = "uid-seaweedfs-data"
        runner.cluster[("deployment", "seaweedfs")]["spec"]["template"]["metadata"]["annotations"] = {"keep": "value"}
        runner.expected = {"sample.csv": "digest", "multipart.bin": "digest2"}
        runner.verify_object = Mock()
        with redirect_stdout(io.StringIO()):
            runner.check_persistence()
        args = runner.calls[0][0]
        changes = json.loads(args[args.index("-p") + 1])
        self.assertEqual(changes[0], {"op": "test", "path": "/metadata/uid", "value": "uid-seaweedfs"})
        self.assertEqual(changes[1]["path"], "/metadata/resourceVersion")
        self.assertEqual(changes[2]["value"]["keep"], "value")
        self.assertEqual(runner.verify_object.call_count, 2)

    def test_client_deletion_is_uid_guarded_and_never_deletes_storage(self):
        runner = FakeCluster()
        pod = runner.create(runner.client_manifest())
        runner.pod_uid = pod["metadata"]["uid"]
        with redirect_stdout(io.StringIO()):
            runner.cleanup_pod()
        args, kwargs = runner.calls[0]
        self.assertEqual(args[0:2], ("delete", "--raw"))
        self.assertTrue(args[2].endswith(f"/pods/{runner.pod}"))
        self.assertEqual(json.loads(kwargs["stdin"])["preconditions"], {"uid": runner.pod_uid})
        self.assertNotIn("--force", args)
        runner.cluster[("pod", runner.pod)]["metadata"]["uid"] = "replacement"
        runner.calls.clear()
        with self.assertRaisesRegex(canary.CanaryError, "foreign/replaced client Pod"):
            runner.cleanup_pod()
        self.assertFalse(runner.calls)

    def test_failure_runs_both_cleanups_and_does_not_report_success(self):
        runner = canary.Canary(canary.parse_args([]))
        runner.prepare_storage = Mock()
        runner.prepare_client = Mock()
        runner.exercise = Mock(side_effect=canary.CanaryError("object integrity failed"))
        runner.cleanup_bucket = Mock(side_effect=canary.CanaryError("cleanup unavailable"))
        runner.cleanup_pod = Mock()
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            result = runner.run()
        self.assertEqual(result, 1)
        runner.cleanup_bucket.assert_called_once()
        runner.cleanup_pod.assert_called_once()
        self.assertIn("object integrity failed", errors.getvalue())
        self.assertIn("cleanup unavailable", errors.getvalue())
        self.assertIn("FAIL S3 canary", output.getvalue())


class FakeS3(canary.Canary):
    """In-memory S3 boundary: exercise real orchestration, hashing and cleanup."""
    def __init__(self, denied="AccessDenied", corrupt=False):
        super().__init__(canary.parse_args([]))
        self.files, self.data, self.uploads = {}, {}, {}
        self.bucket_exists = False
        self.denied, self.corrupt = denied, corrupt
        self.operations, self.part_sizes = [], []

    def exec(self, *args, stdin=None, check=True):
        if args[0] == "sha256sum":
            digest = hashlib.sha256(self.files[args[1]].encode()).hexdigest()
            return subprocess.CompletedProcess([], 0, f"{digest}  {args[1]}", "")
        self.files[args[-1]] = stdin
        return response()

    def s3_result(self, operation, *args, auth="valid"):
        self.operations.append((operation, args, auth))
        if auth != "valid":
            return response(code=self.denied) if self.denied else subprocess.CompletedProcess([], 1, "", "connection timed out")
        options = {args[i]: args[i + 1] for i in range(len(args) - 1) if args[i].startswith("--")}
        key = options.get("--key")
        if operation == "list-buckets":
            return response({"Buckets": [{"Name": self.bucket}] if self.bucket_exists else []})
        if operation == "head-bucket":
            return response({}) if self.bucket_exists else response(code="404")
        if operation == "create-bucket":
            self.bucket_exists = True
        elif operation == "put-object":
            self.data[key] = self.files[options["--body"]]
        elif operation == "get-object":
            if key not in self.data:
                return response(code="NoSuchKey")
            data = self.data[key]
            if "--range" in options:
                start, end = map(int, options["--range"].removeprefix("bytes=").split("-"))
                data = data[start:end + 1]
            self.files[args[-1]] = "corrupted" if self.corrupt else data
        elif operation == "copy-object":
            self.data[key] = self.data[options["--copy-source"].split("/", 1)[1]]
        elif operation == "create-multipart-upload":
            self.uploads[key] = []
            return response({"UploadId": key})
        elif operation == "upload-part":
            data = self.files[options["--body"]]
            self.part_sizes.append(len(data))
            self.uploads[key].append(data)
            return response({"ETag": f'"part-{options["--part-number"]}"'})
        elif operation == "complete-multipart-upload":
            parts = json.loads(options["--multipart-upload"])["Parts"]
            if [p["PartNumber"] for p in parts] != [1, 2]:
                return response(code="InvalidPartOrder")
            self.data[key] = "".join(self.uploads.pop(key))
        elif operation == "abort-multipart-upload":
            self.uploads.pop(key)
        elif operation == "list-multipart-uploads":
            return response({"Uploads": [{"Key": k, "UploadId": k} for k in self.uploads]})
        elif operation == "head-object":
            return response({"ContentLength": len(self.data[key]), "ContentType": "text/csv"}) if key in self.data else response(code="404")
        elif operation == "list-objects-v2":
            start, size = int(options.get("--continuation-token", 0)), int(options["--max-keys"])
            keys = sorted(self.data)
            return response({"Contents": [{"Key": k} for k in keys[start:start + size]], "IsTruncated": start + size < len(keys),
                             "NextContinuationToken": str(start + size)})
        elif operation == "delete-object":
            self.data.pop(key)
        elif operation == "delete-bucket":
            if self.data or self.uploads:
                return response(code="BucketNotEmpty")
            self.bucket_exists = False
        else:
            raise AssertionError(f"unexpected operation {operation}")
        return response({})


class ProtocolTests(unittest.TestCase):
    def test_complete_suite_and_cleanup(self):
        runner = FakeS3()
        with redirect_stdout(io.StringIO()):
            runner.exercise()
            self.assertEqual(runner.part_sizes, [5 * 1024 * 1024, 1024 * 1024, 5 * 1024 * 1024])
            self.assertEqual(set(runner.data), {"sample.csv", "copy.csv", "multipart.bin"})
            self.assertFalse(runner.uploads)
            runner.cleanup_bucket()
        self.assertFalse(runner.bucket_exists or runner.data or runner.uploads or runner.bucket_owned)
        self.assertEqual(runner.passed, 11)

    def test_transport_error_does_not_pass_negative_auth_test(self):
        runner = FakeS3(denied=None)
        with redirect_stdout(io.StringIO()), self.assertRaisesRegex(canary.CanaryError, "not explicitly rejected"):
            runner.exercise()
        with redirect_stdout(io.StringIO()):
            runner.cleanup_bucket()
        self.assertFalse(runner.bucket_exists)

    def test_corruption_is_detected_and_bucket_can_be_cleaned(self):
        runner = FakeS3(corrupt=True)
        with redirect_stdout(io.StringIO()), self.assertRaisesRegex(canary.CanaryError, "SHA256 mismatch"):
            runner.exercise()
        with redirect_stdout(io.StringIO()):
            runner.cleanup_bucket()
        self.assertFalse(runner.bucket_exists)

    def test_bucket_collision_is_never_adopted_or_deleted(self):
        runner = FakeS3()
        runner.bucket_exists = True
        with self.assertRaisesRegex(canary.CanaryError, "already exists"):
            runner.exercise()
        runner.cleanup_bucket()
        self.assertTrue(runner.bucket_exists)
        self.assertNotIn("delete-bucket", [op for op, _, _ in runner.operations])

    def test_cleanup_aborts_partially_finished_uploads(self):
        runner = FakeS3()
        runner.bucket_exists = runner.bucket_owned = True
        runner.uploads["unfinished"] = ["part"]
        with redirect_stdout(io.StringIO()):
            runner.cleanup_bucket()
        self.assertFalse(runner.bucket_exists or runner.uploads)


if __name__ == "__main__":
    unittest.main()
