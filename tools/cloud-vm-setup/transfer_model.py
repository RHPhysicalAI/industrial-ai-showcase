#!/usr/bin/env python3
"""Transfer native GR00T files through an ephemeral, restricted S3 helper pod.

Only the shell wrapper sources configuration. No SDK or local S3 credentials are
needed: the helper receives credentials through Kubernetes secretKeyRef entries.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

IMAGE = "public.ecr.aws/aws-cli/aws-cli:2.34.0"
ENDPOINT = "http://seaweedfs.mlflow.svc.cluster.local:8333"
NAMESPACE = "mlflow"
CHUNK_BYTES = 8 * 1024 * 1024
ATTEMPTS = 3
OWNER_LABEL = "app.kubernetes.io/instance"


class TransferError(Exception):
    """An actionable, credential-free transfer failure."""


def run(args, *, input=None, timeout=180):
    """Never forward command diagnostics: they can contain credential material."""
    try:
        result = subprocess.run(
            args, input=input, capture_output=True,
            timeout=timeout, check=False,
        )
    except subprocess.TimeoutExpired:
        raise TransferError(f"{args[0]} timed out") from None
    except OSError:
        raise TransferError(f"Unable to execute {args[0]}") from None
    if result.returncode:
        raise TransferError(f"{args[0]} failed (exit {result.returncode}); diagnostics suppressed")
    return result.stdout


def relative_parts(value):
    # S3 keys are literal strings, never URL-decoded or normalized into paths.
    if (not isinstance(value, str) or not value or "\\" in value
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise TransferError("Unsafe artifact path")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise TransferError("Unsafe artifact path")
    return parts


def artifact_location(uri):
    match = re.fullmatch(r"s3://([A-Za-z0-9][A-Za-z0-9._-]*)/(.+?)/?", uri)
    if not match:
        raise TransferError("A native GR00T s3://bucket/prefix/model URI is required")
    bucket, prefix = match.groups()
    parts = relative_parts(prefix)
    if len(parts) < 2 or parts[-1] != "model":
        raise TransferError("The native GR00T artifact URI must end in /model")
    return bucket, prefix + "/"


def object_relative(key, prefix):
    if not isinstance(key, str) or not key.startswith(prefix):
        raise TransferError("Object is outside the artifact prefix")
    relative = key[len(prefix):]
    relative_parts(relative)
    return relative


def config_from_env(endpoint):
    names = ("HUB_CONTEXT", "VLA_VM_IP", "VLA_VM_SSH_USER", "VLA_VM_SSH_KEY", "VLA_GROOT_MODEL_PATH")
    config = {name: os.environ.get(name, "") for name in names}
    for name, value in config.items():
        if not value or "<" in value or any(ord(c) < 32 for c in value):
            raise TransferError(f"Missing or invalid {name}; use the configured shell wrapper")
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", config["VLA_VM_SSH_USER"]):
        raise TransferError("Invalid VLA_VM_SSH_USER")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.:-]*", config["VLA_VM_IP"]):
        raise TransferError("Invalid VLA_VM_IP")
    root = config["VLA_GROOT_MODEL_PATH"]
    if not root.startswith("/"):
        raise TransferError("VLA_GROOT_MODEL_PATH must be an absolute directory")
    relative_parts(root[1:])
    config["VLA_VM_SSH_KEY"] = os.path.expanduser(config["VLA_VM_SSH_KEY"])
    if not Path(config["VLA_VM_SSH_KEY"]).is_file() or not os.access(config["VLA_VM_SSH_KEY"], os.R_OK):
        raise TransferError("VLA_VM_SSH_KEY must identify a readable private key")
    port = os.environ.get("VLA_VM_SSH_PORT", "22") or "22"
    if not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise TransferError("Invalid VLA_VM_SSH_PORT")
    config["port"] = port
    try:
        parsed = urlsplit(endpoint)
        valid_endpoint = (parsed.scheme in {"http", "https"} and parsed.hostname
                          and not parsed.username and not parsed.password
                          and not parsed.query and not parsed.fragment)
        _ = parsed.port  # Validate without displaying a credential-bearing URL.
    except ValueError:
        valid_endpoint = False
    if not valid_endpoint or any(c.isspace() for c in endpoint):
        raise TransferError("Invalid S3 endpoint URL (embedded credentials are not allowed)")
    config["endpoint"] = endpoint
    config["region"] = os.environ.get("AWS_DEFAULT_REGION", "us-east-1") or "us-east-1"
    config["image"] = os.environ.get("VLA_S3_CLIENT_IMAGE") or IMAGE
    return config


def pod_manifest(name, token, region, image=IMAGE):
    return {
        "apiVersion": "v1", "kind": "Pod",
        "metadata": {"name": name, "namespace": NAMESPACE, "labels": {OWNER_LABEL: token}},
        "spec": {
            "restartPolicy": "Never", "automountServiceAccountToken": False,
            "activeDeadlineSeconds": 86400,
            "securityContext": {"runAsNonRoot": True, "seccompProfile": {"type": "RuntimeDefault"}},
            "containers": [{
                "name": "s3", "image": image,
                "command": ["/bin/sh", "-ec", "umask 077; printf '[default]\\ns3 =\\n    addressing_style = path\\n    signature_version = s3v4\\n' > /tmp/aws-config; exec sleep 86400"],
                "env": [
                    {"name": key, "valueFrom": {"secretKeyRef": {"name": "mlflow-s3-credentials", "key": key}}}
                    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")
                ] + [
                    {"name": "AWS_DEFAULT_REGION", "value": region},
                    {"name": "AWS_EC2_METADATA_DISABLED", "value": "true"},
                    {"name": "AWS_CONFIG_FILE", "value": "/tmp/aws-config"},
                    {"name": "HOME", "value": "/tmp"},
                    {"name": "AWS_PAGER", "value": ""},
                    {"name": "AWS_MAX_ATTEMPTS", "value": "1"},
                ],
                "securityContext": {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True,
                                    "capabilities": {"drop": ["ALL"]}},
                "resources": {"requests": {"cpu": "100m", "memory": "128Mi"},
                              "limits": {"cpu": "1", "memory": "512Mi"}},
                "volumeMounts": [{"name": "scratch", "mountPath": "/tmp"}],
            }],
            "volumes": [{"name": "scratch", "emptyDir": {"sizeLimit": "64Mi"}}],
        },
    }


# Fresh scratch files prevent collisions when an earlier exec timed out. Keep
# AWS JSON metadata off the binary channel and check the byte count in the pod.
RANGE_SCRIPT = r"""
set -eu
umask 077
expected="$1"
shift
chunk=$(mktemp /tmp/s3-range.XXXXXXXX)
trap 'rm -f -- "$chunk"' EXIT
trap 'exit 1' HUP INT TERM
aws "$@" "$chunk" >/dev/null
test "$(wc -c < "$chunk")" -eq "$expected"
cat -- "$chunk"
"""


class S3Helper:
    def __init__(self, config, runner=run):
        self.runner = runner
        self.token = uuid.uuid4().hex
        self.name = "model-transfer-" + self.token
        self.config = config
        self.oc = ["oc", "--context", config["HUB_CONTEXT"], "-n", NAMESPACE]

    def start(self):
        self.runner(self.oc + ["create", "-f", "-"], input=json.dumps(
            pod_manifest(self.name, self.token, self.config["region"], self.config.get("image", IMAGE))).encode())
        self.runner(self.oc + ["wait", "--for=condition=Ready", "pod/" + self.name, "--timeout=120s"], timeout=150)

    def close(self):
        # Also handles a create that succeeded server-side but lost its response.
        raw = self.runner(self.oc + ["get", "pod", self.name, "--ignore-not-found", "-o", "json"], timeout=30)
        if not raw.strip():
            return
        try:
            metadata = json.loads(raw)["metadata"]
            uid = metadata["uid"]
            owned = bool(uid) and metadata["name"] == self.name and metadata["labels"][OWNER_LABEL] == self.token
        except (ValueError, KeyError, TypeError):
            owned = False
        if not owned:
            raise TransferError("Refusing to delete a helper pod without matching ownership")
        self.runner(self.oc + ["delete", "--raw", f"/api/v1/namespaces/{NAMESPACE}/pods/{self.name}", "-f", "-"],
                    input=json.dumps({"apiVersion": "v1", "kind": "DeleteOptions",
                                      "preconditions": {"uid": uid}}).encode(), timeout=45)
        self.runner(self.oc + ["wait", "--for=delete", "pod/" + self.name, "--timeout=30s"], timeout=45)

    def aws_args(self, operation, *args):
        return ["--endpoint-url", self.config["endpoint"], "--no-cli-pager", "--no-cli-auto-prompt",
                "--cli-connect-timeout", "10", "--cli-read-timeout", "60", "--output", "json",
                "s3api", operation, *args]

    def execute(self, command):
        return self.runner(self.oc + ["exec", self.name, "-c", "s3", "--", *command])

    def json_request(self, operation, *args):
        for attempt in range(ATTEMPTS):
            try:
                data = json.loads(self.execute(["aws", *self.aws_args(operation, *args)]))
                if not isinstance(data, dict):
                    raise TypeError()
                return data
            except (TransferError, ValueError, TypeError):
                if attempt + 1 == ATTEMPTS:
                    raise TransferError(f"S3 {operation} failed after {ATTEMPTS} attempts") from None
                time.sleep(attempt + 1)

    def objects(self, bucket, prefix):
        objects, seen, tokens = [], set(), set()
        token = None
        while True:
            args = ["--bucket", bucket, "--prefix", prefix, "--no-paginate", "--max-keys", "1000"]
            if token:
                args += ["--continuation-token", token]
            page = self.json_request("list-objects-v2", *args)
            contents = page.get("Contents", [])
            if not isinstance(contents, list):
                raise TransferError("Invalid S3 object listing")
            for entry in contents:
                if not isinstance(entry, dict):
                    raise TransferError("Invalid S3 object listing")
                key, size = entry.get("Key"), entry.get("Size")
                if type(size) is not int or size < 0:
                    raise TransferError("Invalid S3 object size")
                # Ignore only valid empty directory markers, including the prefix itself.
                if isinstance(key, str) and key.endswith("/") and size == 0:
                    if key != prefix:
                        object_relative(key[:-1], prefix)
                    continue
                relative = object_relative(key, prefix)
                if relative in seen:
                    raise TransferError("Duplicate S3 object in listing")
                seen.add(relative)
                objects.append((key, relative, size))
            if page.get("IsTruncated") is False:
                break
            token = page.get("NextContinuationToken")
            if page.get("IsTruncated") is not True or not isinstance(token, str) or not token or token in tokens:
                raise TransferError("Invalid S3 listing continuation token")
            tokens.add(token)
        if not objects:
            raise TransferError("No files found under the artifact prefix")
        for relative in seen:
            if any(str(parent) in seen for parent in PurePosixPath(relative).parents):
                raise TransferError("Artifact contains conflicting file and directory paths")
        return objects

    def download(self, bucket, key, size, target):
        head = self.json_request("head-object", "--bucket", bucket, "--key", key)
        etag = head.get("ETag")
        if head.get("ContentLength") != size or not isinstance(etag, str) or not etag:
            raise TransferError("Object size changed or S3 metadata is invalid")
        digest = hashlib.sha256()
        with target.open("xb") as output:
            for offset in range(0, size, CHUNK_BYTES):
                length = min(CHUNK_BYTES, size - offset)
                args = self.aws_args("get-object", "--bucket", bucket, "--key", key,
                                     "--range", f"bytes={offset}-{offset + length - 1}", "--if-match", etag)
                for attempt in range(ATTEMPTS):
                    try:
                        chunk = self.execute(["/bin/sh", "-c", RANGE_SCRIPT, "range", str(length), *args])
                        if len(chunk) != length:
                            raise TransferError("S3 range stream has an incorrect byte count")
                        break
                    except TransferError:
                        if attempt + 1 == ATTEMPTS:
                            raise TransferError(f"S3 range at byte {offset} failed after {ATTEMPTS} attempts") from None
                        time.sleep(attempt + 1)
                output.write(chunk)
                digest.update(chunk)
        if target.stat().st_size != size:
            raise TransferError("Staged file has an incorrect total byte count")
        after = self.json_request("head-object", "--bucket", bucket, "--key", key)
        if after.get("ContentLength") != size or after.get("ETag") != etag:
            raise TransferError("Source object changed during transfer")
        return digest.hexdigest()


# Sent over SSH stdin, never stored in the model. Relative paths are arguments,
# not shell source. Directory FDs prevent symlinks from redirecting root writes.
INSTALL_SCRIPT = r'''
import hashlib
import os
import signal
import stat
import sys

def interrupted(signum, frame):
    raise InterruptedError("Install interrupted")

for signum in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
    signal.signal(signum, interrupted)

root, relative, upload, expected_size, expected_hash, token, mode = sys.argv[1:]
size = int(expected_size)
parts = root[1:].split("/") + relative.split("/")
if not root.startswith("/") or any(p in ("", ".", "..") or "\\" in p for p in parts):
    raise RuntimeError("Unsafe destination")
flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
directory = os.open("/", flags)
temporary = ".model-transfer-" + token
created = False
try:
    for part in parts[:-1]:
        if mode != "cleanup":
            try:
                os.mkdir(part, 0o755, dir_fd=directory)
            except FileExistsError:
                pass
        try:
            child = os.open(part, flags, dir_fd=directory)
        except FileNotFoundError:
            if mode == "cleanup":
                sys.exit(0)
            raise
        os.close(directory)
        directory = child
    if mode == "cleanup":
        try:
            os.unlink(temporary, dir_fd=directory)
        except FileNotFoundError:
            pass
        sys.exit(0)
    source_fd = os.open(upload, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(source_fd, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size != size:
            raise RuntimeError("Upload byte count mismatch")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        created = True
        with os.fdopen(fd, "wb") as output:
            digest = hashlib.sha256()
            count = 0
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                output.write(chunk)
                digest.update(chunk)
                count += len(chunk)
            if count != size or digest.hexdigest() != expected_hash:
                raise RuntimeError("Upload SHA-256 mismatch")
            output.flush()
            os.fchown(output.fileno(), 1500, 0)
            os.fchmod(output.fileno(), 0o644)
            os.fsync(output.fileno())
    # Verify the actual destination-side bytes before the atomic replacement.
    fd = os.open(temporary, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
    with os.fdopen(fd, "rb") as installed:
        digest = hashlib.sha256()
        for chunk in iter(lambda: installed.read(1024 * 1024), b""):
            digest.update(chunk)
        if os.fstat(installed.fileno()).st_size != size or digest.hexdigest() != expected_hash:
            raise RuntimeError("Installed bytes failed verification")
    os.replace(temporary, parts[-1], src_dir_fd=directory, dst_dir_fd=directory)
    created = False
    os.fsync(directory)
finally:
    if created:
        os.unlink(temporary, dir_fd=directory)
    os.close(directory)
'''


class VM:
    def __init__(self, config, runner=run):
        self.config, self.runner = config, runner
        self.token = uuid.uuid4().hex
        self.stage = "/tmp/vla-model-transfer-" + self.token
        self.stage_attempted = False
        self.pending_install = None
        self.target = config["VLA_VM_SSH_USER"] + "@" + config["VLA_VM_IP"]
        host = config["VLA_VM_IP"]
        self.scp_target = config["VLA_VM_SSH_USER"] + "@" + (f"[{host}]" if ":" in host else host)
        self.options = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "IdentitiesOnly=yes",
                        "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3", "-i", config["VLA_VM_SSH_KEY"]]

    def ssh(self, args, **kwargs):
        return self.runner(["ssh", *self.options, "-p", self.config["port"], self.target, shlex.join(args)], **kwargs)

    def start(self):
        self.ssh(["sudo", "-n", "python3", "-c", "import hashlib, os; assert hasattr(os, 'O_NOFOLLOW')"])
        self.stage_attempted = True
        self.ssh(["sh", "-ec", 'umask 077; mkdir -- "$1"; printf "%s" "$2" > "$1/owner"', "stage", self.stage, self.token])

    def install(self, local, relative, size, digest):
        object_relative("model/" + relative, "model/")
        upload = self.stage + "/payload"
        self.runner(["scp", *self.options, "-P", self.config["port"], str(local), self.scp_target + ":" + upload], timeout=3600)
        self.pending_install = (relative, upload, str(size), digest, self.token)
        self.ssh(["sudo", "-n", "python3", "-", self.config["VLA_GROOT_MODEL_PATH"], relative,
                  upload, str(size), digest, self.token, "install"], input=INSTALL_SCRIPT.encode(), timeout=3600)
        self.pending_install = None
        self.ssh(["rm", "-f", "--", upload])

    def close(self):
        if not self.stage_attempted:
            return
        try:
            if self.pending_install:
                self.ssh(["sudo", "-n", "python3", "-", self.config["VLA_GROOT_MODEL_PATH"],
                          *self.pending_install, "cleanup"], input=INSTALL_SCRIPT.encode(), timeout=30)
        finally:
            self.remove_stage()

    def remove_stage(self):
        # Delete only the exact private stage with our marker, never a glob/tree.
        self.ssh(["sh", "-ec", '''
if [ ! -e "$1" ]; then exit 0; fi
test ! -L "$1"
test "$(cat -- "$1/owner")" = "$2"
rm -f -- "$1/payload" "$1/owner"
rmdir -- "$1"
''', "cleanup", self.stage, self.token], timeout=30)


def transfer(config, artifact_uri, runner=run):
    bucket, prefix = artifact_location(artifact_uri)
    helper, vm = S3Helper(config, runner), VM(config, runner)
    cleanup_errors = []
    try:
        helper.start()
        objects = helper.objects(bucket, prefix)
        vm.start()
        with tempfile.TemporaryDirectory(prefix="vla-model-transfer-") as local_dir:
            for key, relative, size in objects:
                # One private local filename avoids workstation filesystem aliases;
                # only validated relative keys are used for VM destination paths.
                local = Path(local_dir) / "payload"
                print(f"Staging {relative} ({size} bytes)", flush=True)
                digest = helper.download(bucket, key, size, local)
                vm.install(local, relative, size, digest)
                local.unlink()
    finally:
        for resource in (vm, helper):
            try:
                resource.close()
            except (TransferError, OSError):
                name = vm.stage if resource is vm else helper.name
                cleanup_errors.append(name)
                print(f"WARNING: cleanup could not be confirmed for {name}", file=sys.stderr)
    if cleanup_errors:
        raise TransferError("Transfer completed but temporary resource cleanup failed")
    print(f"PASS: transferred and SHA-256 verified {artifact_uri} to {config['VLA_VM_IP']}:{config['VLA_GROOT_MODEL_PATH']}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                    formatter_class=argparse.RawDescriptionHelpFormatter, epilog=(
        "The shell wrapper sources:\n"
        "  tools/demo-redhat-sno/.env: HUB_CONTEXT\n"
        "  tools/cloud-vm-setup/.env: VLA_VM_IP, VLA_VM_SSH_USER, VLA_VM_SSH_KEY,\n"
        "    VLA_GROOT_MODEL_PATH; optional VLA_VM_SSH_PORT.\n"
        "VLA_VM_CONFIG overrides the VM config file.\n\n"
        "Set VLA_S3_CLIENT_IMAGE in the VM .env or exported environment to use an\n"
        "offline mirror of the AWS CLI image.\n"
        f"  Default: {IMAGE}\n\n"
        "oc, ssh, scp and Python 3 are required locally; the VM requires Python 3\n"
        "and noninteractive sudo. Credentials come from\n"
        "mlflow/mlflow-s3-credentials inside the helper pod."))
    parser.add_argument("--artifact-uri", required=True, help="s3://bucket/prefix/model")
    parser.add_argument("--endpoint-url", default=os.environ.get("MLFLOW_S3_ENDPOINT_URL") or ENDPOINT,
                        help=f"S3 endpoint (MLFLOW_S3_ENDPOINT_URL or {ENDPOINT})")
    args = parser.parse_args(argv)

    def interrupted(signum, frame):
        raise KeyboardInterrupt()

    previous = signal.signal(signal.SIGTERM, interrupted)
    try:
        artifact_location(args.artifact_uri)
        config = config_from_env(args.endpoint_url)
        for command in ("oc", "ssh", "scp"):
            if shutil.which(command) is None:
                raise TransferError(f"{command} is required")
        transfer(config, args.artifact_uri)
    except TransferError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    except OSError:
        print("ERROR: local staging failed; check permissions and free disk space", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("ERROR: transfer interrupted", file=sys.stderr)
        return 130
    finally:
        signal.signal(signal.SIGTERM, previous)
    return 0


if __name__ == "__main__":
    sys.exit(main())
