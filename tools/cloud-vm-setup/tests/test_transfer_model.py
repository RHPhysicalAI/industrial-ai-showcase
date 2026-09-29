"""Offline checks for the S3 transfer boundary and actual atomic installer."""

import hashlib
import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

SETUP = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("transfer_model", SETUP / "transfer_model.py")
transfer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(transfer)
PREFIX = "run/artifacts/model/"


@pytest.fixture
def config():
    return {
        "HUB_CONTEXT": "test-hub", "VLA_VM_IP": "vm.example.test",
        "VLA_VM_SSH_USER": "tester", "VLA_VM_SSH_KEY": "/keys/test key",
        "VLA_GROOT_MODEL_PATH": "/var/cache/vla-models/run/model",
        "port": "2222", "endpoint": transfer.ENDPOINT, "region": "us-east-1",
    }


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    monkeypatch.setattr(transfer.time, "sleep", lambda seconds: None)


@pytest.mark.parametrize("uri", [
    "s3://bucket/run/artifacts/model", "s3://bucket/run/artifacts/model/",
])
def test_native_artifact_uri(uri):
    assert transfer.artifact_location(uri) == ("bucket", PREFIX)


@pytest.mark.parametrize("uri", [
    "https://bucket/run/model", "s3://bucket/model", "s3://bucket/run/checkpoint",
    "s3://bucket/../model", "s3://bucket/run//model", "s3://bucket/run/./model",
    "s3://bucket/run/model//", "s3://bucket/run\\bad/model",
])
def test_invalid_artifact_uri(uri):
    with pytest.raises(transfer.TransferError):
        transfer.artifact_location(uri)


@pytest.mark.parametrize("relative", [
    "../outside", "a/../../outside", "/absolute", "./config.json", "a//b",
    "a/./b", "a\\..\\b", "a\nb", "a\x00b", "a\tb", "a/", "",
])
def test_rejects_unsafe_keys(relative):
    with pytest.raises(transfer.TransferError):
        transfer.object_relative(PREFIX + relative, PREFIX)


def test_key_prefix_boundary_and_literal_names():
    with pytest.raises(transfer.TransferError):
        transfer.object_relative(PREFIX[:-1] + "-other/config.json", PREFIX)
    name = "nested/weights ' $(literal); ü.bin"
    assert transfer.object_relative(PREFIX + name, PREFIX) == name
    assert transfer.object_relative(PREFIX + "%2e%2e/literal", PREFIX) == "%2e%2e/literal"


def test_helper_security_and_secret_references():
    manifest = transfer.pod_manifest("test-pod", "owner", "us-east-1")
    spec = manifest["spec"]
    container = spec["containers"][0]
    assert manifest["metadata"]["namespace"] == "mlflow"
    assert container["image"] == "public.ecr.aws/aws-cli/aws-cli:2.34.0"
    assert spec["automountServiceAccountToken"] is False
    assert spec["securityContext"]["runAsNonRoot"] is True
    assert spec["securityContext"]["seccompProfile"]["type"] == "RuntimeDefault"
    assert container["securityContext"] == {
        "allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True,
        "capabilities": {"drop": ["ALL"]},
    }
    env = {entry["name"]: entry for entry in container["env"]}
    for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"):
        assert env[key] == {"name": key, "valueFrom": {
            "secretKeyRef": {"name": "mlflow-s3-credentials", "key": key}}}
    assert "addressing_style = path" in container["command"][2]
    assert env["AWS_EC2_METADATA_DISABLED"]["value"] == "true"


def test_list_paginates_and_skips_directory_markers(config):
    helper = transfer.S3Helper(config)
    helper.json_request = Mock(side_effect=[
        {"Contents": [{"Key": PREFIX, "Size": 0}, {"Key": PREFIX + "a/", "Size": 0},
                      {"Key": PREFIX + "a/config.json", "Size": 7}],
         "IsTruncated": True, "NextContinuationToken": "opaque/token"},
        {"Contents": [{"Key": PREFIX + "weights.bin", "Size": 9}], "IsTruncated": False},
    ])
    assert helper.objects("bucket", PREFIX) == [
        (PREFIX + "a/config.json", "a/config.json", 7),
        (PREFIX + "weights.bin", "weights.bin", 9),
    ]
    calls = [call.args for call in helper.json_request.call_args_list]
    assert all("--no-paginate" in call and "--max-keys" in call for call in calls)
    assert "--continuation-token" not in calls[0]
    assert calls[1][-2:] == ("--continuation-token", "opaque/token")


@pytest.mark.parametrize("page", [
    {"IsTruncated": False},
    {"IsTruncated": True},
    {"IsTruncated": True, "NextContinuationToken": ""},
    {"IsTruncated": "false"},
    {"Contents": "invalid", "IsTruncated": False},
    {"Contents": [{"Key": PREFIX + "../x", "Size": 1}], "IsTruncated": False},
    {"Contents": [{"Key": "other/", "Size": 0}], "IsTruncated": False},
    {"Contents": [{"Key": PREFIX + "../", "Size": 0}], "IsTruncated": False},
    {"Contents": [{"Key": PREFIX + "a", "Size": -1}], "IsTruncated": False},
    {"Contents": [{"Key": PREFIX + "a", "Size": True}], "IsTruncated": False},
    {"Contents": [{"Key": PREFIX + "a", "Size": 1}] * 2, "IsTruncated": False},
    {"Contents": [{"Key": PREFIX + "a", "Size": 1}, {"Key": PREFIX + "a/b", "Size": 1}],
     "IsTruncated": False},
])
def test_bad_listings_fail_closed(config, page):
    helper = transfer.S3Helper(config)
    helper.json_request = Mock(return_value=page)
    with pytest.raises(transfer.TransferError):
        helper.objects("bucket", PREFIX)


def test_repeated_continuation_token_fails(config):
    helper = transfer.S3Helper(config)
    helper.json_request = Mock(return_value={"IsTruncated": True, "NextContinuationToken": "same"})
    with pytest.raises(transfer.TransferError, match="continuation"):
        helper.objects("bucket", PREFIX)
    assert helper.json_request.call_count == 2


@pytest.mark.parametrize("malformed", [b"truncated{", b"[]", b"null"])
def test_metadata_retries_bad_json_and_exec_failure(config, malformed):
    runner = Mock(side_effect=[malformed, transfer.TransferError("network"), b'{"ok":true}'])
    helper = transfer.S3Helper(config, runner)
    assert helper.json_request("head-object", "--bucket", "bucket") == {"ok": True}
    assert runner.call_count == 3
    assert "--endpoint-url" in runner.call_args.args[0]


@pytest.mark.parametrize("etag", ['"opaque"', '"not-an-md5-912"'])
def test_ranges_are_fixed_size_independent_of_etag(config, tmp_path, monkeypatch, etag):
    monkeypatch.setattr(transfer, "CHUNK_BYTES", 4)
    helper = transfer.S3Helper(config)
    helper.json_request = Mock(return_value={"ContentLength": 10, "ETag": etag})
    helper.execute = Mock(side_effect=[b"ab", b"abcd", transfer.TransferError("timeout"), b"efgh", b"ij"])
    target = tmp_path / "payload"
    digest = helper.download("bucket", PREFIX + "weights", 10, target)
    assert target.read_bytes() == b"abcdefghij"
    assert digest == hashlib.sha256(b"abcdefghij").hexdigest()
    commands = [call.args[0] for call in helper.execute.call_args_list]
    assert [cmd[cmd.index("--range") + 1] for cmd in commands] == [
        "bytes=0-3", "bytes=0-3", "bytes=4-7", "bytes=4-7", "bytes=8-9",
    ]
    assert all(cmd[cmd.index("--if-match") + 1] == etag for cmd in commands)
    assert all("--part-number" not in cmd for cmd in commands)
    assert helper.json_request.call_count == 2


@pytest.mark.parametrize("bad_chunk", [b"abc", b"abcde", transfer.TransferError("failed exec")])
def test_range_retries_never_append_bad_bytes(config, tmp_path, monkeypatch, bad_chunk):
    monkeypatch.setattr(transfer, "CHUNK_BYTES", 4)
    helper = transfer.S3Helper(config)
    helper.json_request = Mock(return_value={"ContentLength": 4, "ETag": '"opaque"'})
    helper.execute = Mock(side_effect=[bad_chunk] * transfer.ATTEMPTS)
    target = tmp_path / "payload"
    with pytest.raises(transfer.TransferError, match="after 3 attempts"):
        helper.download("bucket", PREFIX + "weights", 4, target)
    assert target.read_bytes() == b""
    assert helper.execute.call_count == transfer.ATTEMPTS


def test_zero_byte_object_needs_no_range(config, tmp_path):
    helper = transfer.S3Helper(config)
    helper.json_request = Mock(return_value={"ContentLength": 0, "ETag": '"opaque"'})
    helper.execute = Mock()
    target = tmp_path / "payload"
    assert helper.download("bucket", PREFIX + "empty", 0, target) == hashlib.sha256(b"").hexdigest()
    assert target.read_bytes() == b""
    helper.execute.assert_not_called()


def test_changed_object_is_rejected(config, tmp_path):
    helper = transfer.S3Helper(config)
    helper.json_request = Mock(side_effect=[
        {"ContentLength": 1, "ETag": '"before"'}, {"ContentLength": 1, "ETag": '"after"'},
    ])
    helper.execute = Mock(return_value=b"x")
    with pytest.raises(transfer.TransferError, match="changed during"):
        helper.download("bucket", PREFIX + "weights", 1, tmp_path / "payload")


def test_list_head_size_mismatch_is_rejected(config, tmp_path):
    helper = transfer.S3Helper(config)
    helper.json_request = Mock(return_value={"ContentLength": 2, "ETag": '"opaque"'})
    helper.execute = Mock()
    with pytest.raises(transfer.TransferError, match="size changed"):
        helper.download("bucket", PREFIX + "weights", 1, tmp_path / "payload")
    helper.execute.assert_not_called()


@pytest.mark.parametrize("payload,expected,success", [("abcd", 4, True), ("abc", 4, False), ("abcde", 4, False)])
def test_range_shell_keeps_json_out_of_binary_stream(tmp_path, payload, expected, success):
    chunk = tmp_path / "scratch"
    prelude = f'''
mktemp() {{ printf '%s' {shlex.quote(str(chunk))}; }}
aws() {{ for last; do :; done; printf '%s' {shlex.quote(payload)} > "$last"; printf '{{"ContentLength":4}}'; }}
'''
    result = subprocess.run(["sh", "-c", prelude + transfer.RANGE_SCRIPT, "range", str(expected)], capture_output=True, check=False)
    assert (result.returncode == 0) == success
    assert result.stdout == (payload.encode() if success else b"")
    assert not chunk.exists()


def execute_installer(root, relative, upload, content, token="test-token", mode="install"):
    args = ["installer", str(root), relative, str(upload), str(len(content)), hashlib.sha256(content).hexdigest(), token, mode]
    # Exercise real reads, fd-relative writes, hashing and rename without root.
    with patch.object(sys, "argv", args), patch.object(os, "fchown") as chown, patch.object(transfer.signal, "signal"):
        exec(compile(transfer.INSTALL_SCRIPT, "<remote installer>", "exec"), {})  # noqa: S102 - Tests only repository-owned installer code.
    return chown


def test_installer_atomically_replaces_verified_file(tmp_path):
    root = tmp_path.resolve() / "model"
    root.mkdir()
    old = root / "config.json"
    old.write_bytes(b"old")
    upload = tmp_path / "upload"
    upload.write_bytes(b"new")
    replace = os.replace

    def checked_replace(source, target, **kwargs):
        assert old.read_bytes() == b"old"
        assert kwargs["src_dir_fd"] == kwargs["dst_dir_fd"]
        return replace(source, target, **kwargs)

    with patch.object(os, "replace", side_effect=checked_replace) as replaced:
        chown = execute_installer(root, "config.json", upload, b"new")
    assert old.read_bytes() == b"new"
    assert old.stat().st_mode & 0o777 == 0o644
    assert chown.call_args.args[1:] == (1500, 0)
    assert replaced.call_count == 1
    assert sorted(p.name for p in root.iterdir()) == ["config.json"]


def test_installer_preserves_nested_native_paths(tmp_path):
    root = tmp_path.resolve() / "model"
    upload = tmp_path / "upload"
    upload.write_bytes(b"content")
    relative = "experiment_cfg/metadata ' $(literal).json"
    execute_installer(root, relative, upload, b"content")
    assert (root / relative).read_bytes() == b"content"


@pytest.mark.parametrize("corrupt", [b"BAD", b"wrong size"])
def test_corruption_preserves_old_file_and_removes_partial(tmp_path, corrupt):
    root = tmp_path.resolve() / "model"
    root.mkdir()
    old = root / "weights.bin"
    old.write_bytes(b"original")
    upload = tmp_path / "upload"
    upload.write_bytes(corrupt)
    with pytest.raises(RuntimeError, match="mismatch"):
        execute_installer(root, "weights.bin", upload, b"new")
    assert old.read_bytes() == b"original"
    assert list(root.iterdir()) == [old]


def test_installer_rejects_destination_symlink(tmp_path):
    root = tmp_path.resolve() / "model"
    root.mkdir()
    outside = tmp_path.resolve() / "outside"
    outside.mkdir()
    (root / "redirect").symlink_to(outside, target_is_directory=True)
    upload = tmp_path / "upload"
    upload.write_bytes(b"new")
    with pytest.raises(OSError):
        execute_installer(root, "redirect/config.json", upload, b"new")
    assert list(outside.iterdir()) == []


def test_installer_cleanup_only_removes_owned_temporary_file(tmp_path):
    root = tmp_path.resolve() / "model"
    root.mkdir()
    owned = root / ".model-transfer-test-token"
    owned.write_bytes(b"partial")
    unrelated = root / ".model-transfer-other-token"
    unrelated.write_bytes(b"other")
    with pytest.raises(SystemExit) as result:
        execute_installer(root, "weights", tmp_path / "missing", b"new", mode="cleanup")
    assert result.value.code == 0
    assert not owned.exists()
    assert unrelated.read_bytes() == b"other"


def test_ssh_and_scp_use_vm_port_and_quote_arguments(config, tmp_path):
    runner = Mock(return_value=b"")
    config["VLA_GROOT_MODEL_PATH"] = "/var/cache/model ' $(literal)"
    vm = transfer.VM(config, runner)
    local = tmp_path / "payload"
    relative = "nested/weight ' $(literal).bin"
    vm.install(local, relative, 1, "digest")
    scp = runner.call_args_list[0].args[0]
    ssh = runner.call_args_list[1].args[0]
    assert scp[scp.index("-P") + 1] == "2222"
    assert ssh[ssh.index("-p") + 1] == "2222"
    assert scp[scp.index("-i") + 1] == "/keys/test key"
    assert scp[-1] == "tester@vm.example.test:" + vm.stage + "/payload"
    remote = shlex.split(ssh[-1])
    assert remote[:4] == ["sudo", "-n", "python3", "-"]
    assert remote[4:6] == [config["VLA_GROOT_MODEL_PATH"], relative]
    assert runner.call_args_list[1].kwargs["input"] == transfer.INSTALL_SCRIPT.encode()
    assert not any("StrictHostKeyChecking=no" in arg for arg in scp + ssh)


def test_helper_cleanup_checks_owner_and_exact_name(config):
    runner = Mock(return_value=b"")
    helper = transfer.S3Helper(config, runner)
    runner.side_effect = [json.dumps({"metadata": {"name": helper.name, "uid": "test-uid", "labels": {transfer.OWNER_LABEL: helper.token}}}).encode(), b"", b""]
    helper.close()
    deleted = runner.call_args_list[1].args[0]
    assert deleted[deleted.index("delete") + 1:][:2] == ["--raw", f"/api/v1/namespaces/mlflow/pods/{helper.name}"]
    assert json.loads(runner.call_args_list[1].kwargs["input"])["preconditions"] == {"uid": "test-uid"}
    assert "--all" not in deleted and "-l" not in deleted


def test_helper_cleanup_refuses_foreign_pod(config):
    runner = Mock(return_value=b'{"metadata":{"name":"someone-else","labels":{}}}')
    helper = transfer.S3Helper(config, runner)
    with pytest.raises(transfer.TransferError, match="ownership"):
        helper.close()
    assert runner.call_count == 1


@pytest.mark.parametrize("failure", [None, "create", "ready", "download", "scp", "install", "interrupt"])
def test_orchestration_cleanup_on_success_and_failures(config, failure, capsys):
    calls, manifest, staged = [], {}, []

    def runner(args, **kwargs):
        calls.append((args, kwargs))
        if args[0] == "oc":
            if "create" in args:
                manifest.update(json.loads(kwargs["input"]))
                if failure == "create":
                    raise transfer.TransferError("lost create response")
            elif "wait" in args and failure == "ready":
                raise transfer.TransferError("not ready")
            elif "get" in args:
                manifest["metadata"]["uid"] = "test-uid"
                return json.dumps(manifest).encode()
            elif "list-objects-v2" in args:
                return json.dumps({"Contents": [{"Key": PREFIX + "config.json", "Size": 3}], "IsTruncated": False}).encode()
            elif "head-object" in args:
                return b'{"ContentLength":3,"ETag":"opaque"}'
            elif "get-object" in args:
                if failure == "download":
                    return b"x"
                if failure == "interrupt":
                    raise KeyboardInterrupt()
                return b"abc"
        elif args[0] == "scp":
            staged.append(Path(args[-2]))
            assert staged[-1].read_bytes() == b"abc"
            if failure == "scp":
                raise transfer.TransferError("scp failed")
        elif (args[0] == "ssh" and kwargs.get("input")
              and failure == "install" and shlex.split(args[-1])[-1] == "install"):
            raise transfer.TransferError("install failed")
        return b""

    if failure:
        with pytest.raises(KeyboardInterrupt if failure == "interrupt" else transfer.TransferError):
            transfer.transfer(config, "s3://bucket/run/artifacts/model", runner)
    else:
        transfer.transfer(config, "s3://bucket/run/artifacts/model", runner)
    deletes = [args for args, _ in calls if args[0] == "oc" and "delete" in args]
    assert len(deletes) == 1
    assert any(arg.endswith("/pods/" + manifest["metadata"]["name"]) for arg in deletes[0])
    for path in staged:
        assert not path.parent.exists()
    if failure not in {"create", "ready"}:
        assert any(args[0] == "ssh" and "cleanup" in shlex.split(args[-1]) for args, _ in calls)
    if failure == "install":
        assert any(kwargs.get("input") and shlex.split(args[-1])[-1] == "cleanup" for args, kwargs in calls)
    assert ("PASS:" in capsys.readouterr().out) == (failure is None)


def test_command_errors_do_not_expose_output_or_secrets():
    completed = subprocess.CompletedProcess(["oc"], 1, b"ACCESS_SECRET", b"PASSWORD_SECRET")
    with patch.object(subprocess, "run", return_value=completed), pytest.raises(transfer.TransferError) as result:
        transfer.run(["oc", "dummy"])
    assert "SECRET" not in str(result.value)


@pytest.fixture
def wrapper_tree(tmp_path):
    setup = tmp_path / "tools" / "cloud-vm-setup"
    setup.mkdir(parents=True)
    shutil.copy2(SETUP / "transfer-model.sh", setup)
    shutil.copy2(SETUP / "transfer_model.py", setup)
    return setup


def test_wrapper_help_without_env_or_infrastructure(wrapper_tree):
    result = subprocess.run(["bash", str(wrapper_tree / "transfer-model.sh"), "--help"], capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert "--artifact-uri" in result.stdout
    assert transfer.ENDPOINT in result.stdout
    assert "VLA_S3_CLIENT_IMAGE" in result.stdout
    assert "offline mirror" in result.stdout
    assert transfer.IMAGE in result.stdout
    assert not result.stderr


def test_wrapper_sources_shell_env_without_leaking_secrets(wrapper_tree):
    hub = wrapper_tree.parent / "demo-redhat-sno"
    hub.mkdir()
    (hub / ".env").write_text('HUB_CONTEXT="shell-expanded-$USER"\nHUB_SECRET=do-not-print-hub\necho "$HUB_SECRET"\n')
    (wrapper_tree / ".env").write_text('VLA_VM_IP=localhost\nVLA_VM_SSH_USER=tester\nVLA_VM_SSH_KEY=/missing-test-key\nVLA_GROOT_MODEL_PATH=/models/model\nVM_SECRET=do-not-print-vm\necho "$VM_SECRET"\n')
    result = subprocess.run(["bash", "-x", str(wrapper_tree / "transfer-model.sh"), "--artifact-uri", "s3://bucket/run/model"], capture_output=True, text=True, check=False)
    assert result.returncode == 1
    assert "readable private key" in result.stderr
    assert "do-not-print" not in result.stdout + result.stderr


def test_vm_config_values_and_port_are_validated(config, tmp_path, monkeypatch):
    key = tmp_path / "test-key"
    key.touch()
    for name, value in config.items():
        if name.startswith("VLA_") or name == "HUB_CONTEXT":
            monkeypatch.setenv(name, value)
    monkeypatch.setenv("VLA_VM_SSH_KEY", str(key))
    monkeypatch.setenv("VLA_VM_SSH_PORT", "2222")
    actual = transfer.config_from_env(transfer.ENDPOINT)
    assert actual["port"] == "2222"
    monkeypatch.setenv("VLA_VM_SSH_PORT", "0")
    with pytest.raises(transfer.TransferError, match="SSH_PORT"):
        transfer.config_from_env(transfer.ENDPOINT)


@pytest.mark.parametrize("image", [None, "", "registry.internal:5000/mirrors/aws-cli:2.34.0",
                                   "registry.internal/aws-cli@sha256:" + "a" * 64])
def test_image_override_reaches_created_pod(config, tmp_path, monkeypatch, image):
    key = tmp_path / "key"
    key.touch()
    for name, value in config.items():
        if name.startswith("VLA_") or name == "HUB_CONTEXT":
            monkeypatch.setenv(name, value)
    monkeypatch.setenv("VLA_VM_SSH_KEY", str(key))
    if image is None:
        monkeypatch.delenv("VLA_S3_CLIENT_IMAGE", raising=False)
    else:
        monkeypatch.setenv("VLA_S3_CLIENT_IMAGE", image)
    runner = Mock(return_value=b"")
    helper = transfer.S3Helper(transfer.config_from_env(transfer.ENDPOINT), runner)
    helper.start()
    manifest = json.loads(runner.call_args_list[0].kwargs["input"])
    assert manifest["spec"]["containers"][0]["image"] == (image or transfer.IMAGE)


@pytest.mark.parametrize("source", ["vm_config", "environment"])
def test_wrapper_exports_image_override(wrapper_tree, monkeypatch, source):
    hub = wrapper_tree.parent / "demo-redhat-sno"
    hub.mkdir()
    (hub / ".env").write_text("HUB_CONTEXT=test-hub\n")
    image = "registry.internal:5000/mirrors/aws-cli:2.34.0"
    if source == "vm_config":
        monkeypatch.delenv("VLA_S3_CLIENT_IMAGE", raising=False)
        (wrapper_tree / ".env").write_text(f'VLA_S3_CLIENT_IMAGE="{image}"\n')
    else:
        monkeypatch.setenv("VLA_S3_CLIENT_IMAGE", image)
        (wrapper_tree / ".env").touch()
    # Observe the actual shell-to-Python environment handoff without infrastructure.
    (wrapper_tree / "transfer_model.py").write_text(
        'import os\nprint(os.environ["VLA_S3_CLIENT_IMAGE"])\n')
    result = subprocess.run(["bash", str(wrapper_tree / "transfer-model.sh"),
                             "--artifact-uri", "s3://bucket/run/model"], capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert result.stdout.strip() == image


def test_python_help_without_environment():
    result = subprocess.run([sys.executable, str(SETUP / "transfer_model.py"), "--help"], env={"PATH": os.environ["PATH"]}, capture_output=True, check=False)
    assert result.returncode == 0
    assert b"mlflow-s3-credentials" in result.stdout
