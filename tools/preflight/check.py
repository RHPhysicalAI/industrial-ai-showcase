#!/usr/bin/env python3
"""Read-only prerequisite checks for the Industrial AI Showcase.

This is intentionally dependency-free: it uses the Python standard library and
the OpenShift CLI rather than requiring a Python Kubernetes client. The checker
reports readiness; it does not install, apply, delete, or modify cluster state.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence


PROFILES = {
    "basic-infra": "foundational local, cloud VM, and cluster infrastructure",
    "demo-workload": "warehouse demonstration workload",
    "factory": "Factory B and PLC gateway workload",
    "agentic": "agentic operations workload",
}
SCOPES = {"local", "hub", "companion", "cloud-vm"}
SPECIAL_SCOPES = {"ml-training"}
LEGACY_SCOPES = {"fedora", "host"}
DEFAULT_COMPANION_KUBECONFIG = Path.home() / ".kube" / "companion.kubeconfig"
SUPPORTED_TOPOLOGY = "local workstation + Hub + hosted Companion SNO + separate cloud VLA VM"
UNSUPPORTED_PATH = "Fedora/bare-metal self-managed Companion and host-native VLA implementation"
UPSTREAM_REPOSITORY_URL = "https://github.com/RHPhysicalAI/industrial-ai-showcase.git"
FORK_REPOSITORY_URL = "https://github.com/rhkp/industrial-ai-showcase.git"

DEMO_WORKLOAD_HUB_DEPLOYMENTS = (
    ("fleet-manager", "fleet-ops"),
    ("wms-stub", "fleet-ops"),
    ("mes-stub", "fleet-ops"),
    ("obstruction-detector", "fleet-ops"),
    ("isaac-sim", "isaac-sim"),
    ("cosmos-reason", "cosmos"),
    ("showcase-console-backend", "fleet-ops"),
    ("showcase-console-frontend", "fleet-ops"),
)

DEMO_WORKLOAD_COMPANION_DEPLOYMENTS = (
    ("fake-camera", "warehouse-edge"),
    ("mission-dispatcher", "robot-edge"),
)

FACTORY_HUB_DEPLOYMENTS = (
    ("fake-camera-b", "factory-b"),
    ("mission-dispatcher-b", "factory-b"),
)

AGENTIC_HUB_DEPLOYMENTS = (
    ("agentic-orchestrator", "agentic-ops"),
    ("audit-service", "agentic-ops"),
    ("mcp-fleet-server", "agentic-ops"),
    ("mcp-mlflow-server", "agentic-ops"),
    ("llama-guard", "agentic-ops"),
    ("llama-guard-adapter", "agentic-ops"),
    ("vllm-agent-brain", "agentic-ops"),
)

REQUIRED_REPO_PATHS = (
    "infrastructure/gitops/bootstrap",
    "infrastructure/gitops/clusters/hub",
    "infrastructure/gitops/apps/platform/kafka",
    "infrastructure/gitops/apps/platform/vault",
    "infrastructure/gitops/apps/workloads/console",
)

GITOPS_REPOSITORY_PATHS = {
    "upstream": (
        "infrastructure/gitops/bootstrap/root-application.yaml",
        "infrastructure/gitops/clusters/hub/appsets/operators.yaml",
        "infrastructure/gitops/clusters/hub/appsets/platform.yaml",
        "infrastructure/gitops/clusters/hub/appsets/observability.yaml",
        "infrastructure/gitops/clusters/hub/appsets/workloads.yaml",
        "infrastructure/gitops/clusters/hub/appsets/hub-acm.yaml",
        "infrastructure/gitops/clusters/hub/vault-static-secret-argocd-repo.yaml",
        "infrastructure/gitops/apps/hub-acm/appset-companion/applicationset.yaml",
    ),
    "fork": (
        "infrastructure/gitops/bootstrap/root-application-rhkp.yaml",
    ),
}

ML_TRAINING_PATHS = (
    "workloads/vla-training/src/vla_training/pipeline.py",
    "workloads/vla-training/src/vla_training/config.py",
    "workloads/vla-training/src/vla_training/constants.py",
    "workloads/vla-training/src/vla_training/data_prep.py",
    "workloads/vla-training/src/vla_training/fine_tune.py",
    "workloads/vla-training/src/vla_training/validate_onnx.py",
    "workloads/vla-training/src/vla_training/register_model.py",
    "workloads/vla-training/src/vla_training/promote.py",
    "workloads/vla-training/vla_finetune_pipeline.yaml",
    "infrastructure/gitops/apps/platform/dspa/dspa.yaml",
    "infrastructure/gitops/apps/platform/mlflow/mlflow.yaml",
    "infrastructure/gitops/apps/platform/model-registry/model-registry.yaml",
)

ML_TRAINING_GIT_SOURCE_PATHS = (
    "infrastructure/gitops/apps/platform/dspa/buildconfig.yaml",
)


@dataclass(frozen=True)
class CheckResult:
    id: str
    scope: str
    severity: str
    status: str
    summary: str
    detail: str = ""
    action: str = ""
    source: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class CommandRunner:
    """Small subprocess boundary that can be replaced by tests."""

    def run(self, args: Sequence[str], timeout: int = 20) -> CommandResult:
        try:
            completed = subprocess.run(
                list(args),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError:
            return CommandResult(127, "", f"command not found: {args[0]}")
        except subprocess.TimeoutExpired:
            return CommandResult(124, "", f"command timed out after {timeout}s")
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)


class PreflightChecker:
    def __init__(
        self,
        repo_root: Path,
        profile: str,
        scopes: set[str],
        hub_kubeconfig: str | None,
        companion_kubeconfig: str | None,
        vla_health_url: str | None,
        cloud_vm_host: str | None = None,
        cloud_vm_user: str | None = None,
        cloud_vm_key: str | None = None,
        cloud_vm_port: int = 22,
        cloud_vm_gpu_model: str | None = None,
        cloud_vm_vla_port: int = 8000,
        gitops_profile: str = "auto",
        runner: CommandRunner | None = None,
    ) -> None:
        self.repo_root = repo_root
        self.profile = profile
        self.scopes = scopes
        self.hub_kubeconfig = hub_kubeconfig
        self.companion_kubeconfig = companion_kubeconfig
        self.vla_health_url = vla_health_url
        self.cloud_vm_host = cloud_vm_host
        self.cloud_vm_user = cloud_vm_user
        self.cloud_vm_key = cloud_vm_key
        self.cloud_vm_port = cloud_vm_port
        self.cloud_vm_gpu_model = cloud_vm_gpu_model
        self.cloud_vm_vla_port = cloud_vm_vla_port
        self.gitops_profile = gitops_profile
        self.runner = runner or CommandRunner()
        self.results: list[CheckResult] = []

    def add(
        self,
        check_id: str,
        scope: str,
        severity: str,
        status: str,
        summary: str,
        detail: str = "",
        action: str = "",
        source: str = "",
    ) -> None:
        self.results.append(
            CheckResult(
                id=check_id,
                scope=scope,
                severity=severity,
                status=status,
                summary=summary,
                detail=detail,
                action=action,
                source=source,
            )
        )

    def run(self) -> list[CheckResult]:
        if "local" in self.scopes:
            self.check_local()
        if "hub" in self.scopes:
            self.check_cluster("hub", self.hub_kubeconfig)
        if "companion" in self.scopes:
            self.check_cluster("companion", self.companion_kubeconfig)
        if "cloud-vm" in self.scopes:
            self.check_cloud_vm()
        if "unsupported" in self.scopes:
            self.check_unsupported_path()
        if "ml-training" in self.scopes:
            self.check_ml_training()
        return self.results

    def check_local(self) -> None:
        self.add(
            "local.repo-root",
            "local",
            "blocking",
            "pass" if (self.repo_root / ".git").exists() else "fail",
            "Repository root detected" if (self.repo_root / ".git").exists() else "Repository root is not a Git checkout",
            detail=str(self.repo_root),
            action="Run the checker from the repository or pass --repo-root.",
        )

        required_commands = ("oc", "git", "jq", "curl", "ssh")
        for command in required_commands:
            found = shutil.which(command) is not None
            self.add(
                f"local.command.{command}",
                "local",
                "blocking" if command in {"oc", "git", "ssh"} else "warning",
                "pass" if found else "fail",
                f"{command} is available" if found else f"{command} is not installed",
                action=f"Install {command} using the supported workstation procedure.",
            )

        kustomize_found = shutil.which("kustomize") is not None
        oc_found = shutil.which("oc") is not None
        self.add(
            "local.command.kustomize",
            "local",
            "informational",
            "pass" if kustomize_found else "warn",
            "Standalone kustomize is available" if kustomize_found else "Standalone kustomize is not installed",
            detail="oc kustomize may still be used." if not kustomize_found and oc_found else "",
            action="Install kustomize if standalone manifest rendering is required.",
        )

        for relative_path in REQUIRED_REPO_PATHS:
            exists = (self.repo_root / relative_path).exists()
            self.add(
                f"local.repo-path.{relative_path.replace('/', '.')}",
                "local",
                "blocking",
                "pass" if exists else "fail",
                f"Repository path exists: {relative_path}" if exists else f"Required repository path is missing: {relative_path}",
                action="Update the fork or restore the missing repository path.",
            )
        self.check_gitops_source()
        self.add(
            "local.companion.endpoint-check",
            "local",
            "informational",
            "skipped",
            "Static Fedora/bare-metal Companion DNS checks are not supported",
            detail="Use --scope companion with the hosted SNO kubeconfig to validate the Companion API.",
            action="Do not add the old companion.lab.local entries for the hosted demo path.",
            source="tools/demo-redhat-sno/README.md",
        )

    def check_gitops_source(self) -> None:
        origin_result = self.runner.run(["git", "config", "--get", "remote.origin.url"])
        origin = origin_result.stdout.strip()
        origin_key = normalize_repo_url(origin)
        if self.gitops_profile == "auto":
            fork_key = normalize_repo_url(FORK_REPOSITORY_URL)
            profile = "fork" if origin_key == fork_key else "upstream"
        else:
            profile = self.gitops_profile
        repo_urls: set[str] = set()
        source_paths = GITOPS_REPOSITORY_PATHS[profile]
        missing_paths: list[str] = []
        for relative_path in source_paths:
            path = self.repo_root / relative_path
            if not path.exists():
                missing_paths.append(relative_path)
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                for marker in ("repoURL:", "value:"):
                    if marker not in line or "github.com/" not in line:
                        continue
                    value = line.split(marker, 1)[1].strip().strip("\"'")
                    if value.startswith("https://github.com/"):
                        repo_urls.add(value)

        source_keys = {normalize_repo_url(url) for url in repo_urls}
        aligned = bool(origin_key and source_keys and origin_key in source_keys and not missing_paths)
        if aligned:
            self.add(
                "local.gitops-source",
                "local",
                "blocking",
                "pass",
                f"GitOps {profile} profile points at the configured origin repository",
                detail=f"profile={profile}; origin={origin}",
                source=", ".join(sorted(repo_urls)),
            )
            return
        detail = (
            f"profile={profile}; origin={origin or 'unavailable'}; "
            f"sources={', '.join(sorted(repo_urls)) or 'not found'}"
        )
        if missing_paths:
            detail += f"; missing={', '.join(missing_paths)}"
        self.add(
            "local.gitops-source",
            "local",
            "blocking",
            "fail",
            f"GitOps {profile} profile does not point at this checkout's origin repository",
            detail=detail,
            action="Use the upstream root application for the legacy repository or root-application-rhkp.yaml for the fork profile.",
            source=", ".join(source_paths),
        )

    def check_cloud_vm(self) -> None:
        required = {
            "VLA_VM_IP": self.cloud_vm_host,
            "VLA_VM_SSH_USER": self.cloud_vm_user,
            "VLA_VM_SSH_KEY": self.cloud_vm_key,
            "VLA_GPU_MODEL": self.cloud_vm_gpu_model,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            self.add(
                "cloud-vm.target",
                "cloud-vm",
                "blocking",
                "fail",
                "Cloud VLA VM configuration is incomplete",
                detail=f"missing {', '.join(missing)}",
                action="Source tools/cloud-vm-setup/.env or pass the cloud VM connection and GPU arguments.",
                source="tools/cloud-vm-setup/.env.example",
            )
            return

        key_path = Path(os.path.expanduser(self.cloud_vm_key or ""))
        key_readable = key_path.is_file() and os.access(key_path, os.R_OK)
        self.add(
            "cloud-vm.ssh-key",
            "cloud-vm",
            "blocking",
            "pass" if key_readable else "fail",
            "Cloud VM SSH key is readable" if key_readable else "Cloud VM SSH key is missing or unreadable",
            detail=str(key_path),
            action="Verify VLA_VM_SSH_KEY points to the private key for the cloud VM.",
            source="tools/cloud-vm-setup/README.md",
        )
        if not key_readable:
            return

        host = self.cloud_vm_host or ""
        try:
            socket.getaddrinfo(host, self.cloud_vm_port, type=socket.SOCK_STREAM)
            resolved = True
            resolution_detail = f"{host} resolved"
        except socket.gaierror as error:
            resolved = False
            resolution_detail = str(error)
        self.add(
            "cloud-vm.resolve",
            "cloud-vm",
            "blocking",
            "pass" if resolved else "fail",
            "Cloud VLA VM target resolves" if resolved else "Cloud VLA VM target does not resolve",
            detail=resolution_detail,
            action="Verify the cloud VM public IP/hostname and local DNS/VPN connectivity.",
            source="tools/cloud-vm-setup/.env.example",
        )

        if resolved:
            try:
                with socket.create_connection((host, self.cloud_vm_port), timeout=5):
                    tcp_reachable = True
                tcp_detail = f"{host}:{self.cloud_vm_port} reachable"
            except OSError as error:
                tcp_reachable = False
                tcp_detail = str(error)
        else:
            tcp_reachable = False
            tcp_detail = "target did not resolve"
        self.add(
            "cloud-vm.tcp.ssh",
            "cloud-vm",
            "blocking",
            "pass" if tcp_reachable else "fail",
            "Cloud VLA VM SSH port is reachable" if tcp_reachable else "Cloud VLA VM SSH port is not reachable",
            detail=tcp_detail,
            action="Verify the cloud security group, VM firewall, routing, and SSH daemon.",
        )
        if not tcp_reachable:
            return

        ssh_result = self.cloud_vm_run(["true"])
        ssh_ok = ssh_result.returncode == 0
        self.add(
            "cloud-vm.ssh",
            "cloud-vm",
            "blocking",
            "pass" if ssh_ok else "fail",
            "SSH session to cloud VLA VM succeeded" if ssh_ok else "SSH session to cloud VLA VM failed",
            detail=clean_error(ssh_result.stderr or ssh_result.stdout),
            action="Verify VLA_VM_SSH_USER, VLA_VM_SSH_KEY, SSH authorization, and host-key policy.",
            source="tools/cloud-vm-setup/README.md",
        )
        if not ssh_ok:
            return

        self.check_cloud_vm_os()
        for command in ("podman", "systemctl", "nvidia-smi", "nvidia-ctk", "curl"):
            result = self.cloud_vm_run(["sh", "-lc", f"command -v {command}"])
            found = result.returncode == 0
            self.add(
                f"cloud-vm.command.{command}",
                "cloud-vm",
                "blocking",
                "pass" if found else "fail",
                f"{command} is available on the cloud VLA VM" if found else f"{command} is not installed on the cloud VLA VM",
                detail=clean_error(result.stderr or result.stdout),
                action="Run tools/cloud-vm-setup/setup.sh to install the cloud VM prerequisites.",
                source="tools/cloud-vm-setup/ansible/site.yml",
            )

        gpu = self.cloud_vm_run(
            ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"]
        )
        gpu_detail = clean_error(gpu.stdout or gpu.stderr)
        gpu_ok = gpu.returncode == 0 and bool(gpu.stdout.strip())
        expected_gpu = re.sub(r"\bnvidia\b", "", self.cloud_vm_gpu_model or "", flags=re.IGNORECASE).strip()
        gpu_matches = gpu_ok and (not expected_gpu or expected_gpu.lower() in gpu.stdout.lower())
        self.add(
            "cloud-vm.gpu",
            "cloud-vm",
            "blocking",
            "pass" if gpu_matches else "fail",
            f"Expected NVIDIA GPU is visible ({expected_gpu})" if gpu_matches else "Expected NVIDIA GPU is not visible",
            detail=gpu_detail,
            action="Verify the VM GPU attachment, NVIDIA server driver, and instance type.",
            source="tools/cloud-vm-setup/README.md",
        )

        cdi = self.cloud_vm_run(["nvidia-ctk", "cdi", "list"])
        cdi_ok = cdi.returncode == 0 and "nvidia.com/gpu" in cdi.stdout
        self.add(
            "cloud-vm.nvidia-cdi",
            "cloud-vm",
            "blocking",
            "pass" if cdi_ok else "fail",
            "Podman NVIDIA CDI exposes nvidia.com/gpu" if cdi_ok else "Podman NVIDIA CDI is not available",
            detail=clean_error(cdi.stdout or cdi.stderr),
            action="Regenerate the NVIDIA CDI specification with nvidia-ctk and rerun the cloud VM setup.",
            source="tools/cloud-vm-setup/ansible/site.yml",
        )

        service = self.cloud_vm_run(["systemctl", "is-active", "openvla-server.service"])
        service_ok = service.returncode == 0 and service.stdout.strip() == "active"
        self.add(
            "cloud-vm.vla.service",
            "cloud-vm",
            "blocking",
            "pass" if service_ok else "fail",
            "OpenVLA service is active" if service_ok else "OpenVLA service is not active",
            detail=clean_error(service.stderr or service.stdout),
            action="Run the cloud VM setup and inspect journalctl -u openvla-server.service.",
            source="tools/cloud-vm-setup/ansible/templates/openvla-server.container.j2",
        )
        self.check_cloud_vm_endpoint("healthz", blocking=True)
        self.check_cloud_vm_endpoint("readyz", blocking=True)
        self.check_cloud_vm_mode()

        if self.vla_health_url:
            external = self.runner.run(
                ["curl", "--fail", "--silent", "--show-error", "--max-time", "10", self.vla_health_url]
            )
            external_ok = external.returncode == 0
            self.add(
                "cloud-vm.external-health",
                "cloud-vm",
                "warning",
                "pass" if external_ok else "warn",
                "VLA endpoint is reachable from the workstation" if external_ok else "VLA endpoint is not reachable from the workstation",
                detail=clean_error(external.stderr or external.stdout),
                action="Validate the endpoint from a Companion SNO workload; the cloud VM firewall is intentionally restricted to the SNO egress CIDR.",
                source="tools/cloud-vm-setup/README.md",
            )

    def check_cloud_vm_os(self) -> None:
        result = self.cloud_vm_run(["cat", "/etc/os-release"])
        values: dict[str, str] = {}
        for line in result.stdout.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                values[key] = value.strip().strip('"')
        ubuntu = result.returncode == 0 and values.get("ID", "").lower() == "ubuntu"
        self.add(
            "cloud-vm.os",
            "cloud-vm",
            "blocking",
            "pass" if ubuntu else "fail",
            f"Ubuntu cloud VM detected ({values.get('VERSION_ID', 'unknown')})" if ubuntu else "Cloud VM is not the supported Ubuntu target",
            detail=values.get("PRETTY_NAME", clean_error(result.stderr or result.stdout)),
            action="Use the supported Ubuntu cloud GPU VM profile documented in tools/cloud-vm-setup/README.md.",
            source="tools/cloud-vm-setup/README.md",
        )

    def check_cloud_vm_endpoint(self, endpoint: str, blocking: bool) -> None:
        port = str(self.cloud_vm_vla_port)
        result = self.cloud_vm_run(
            ["curl", "--fail", "--silent", "--show-error", "--max-time", "15", f"http://127.0.0.1:{port}/{endpoint}"]
        )
        ok = result.returncode == 0
        self.add(
            f"cloud-vm.vla.{endpoint}",
            "cloud-vm",
            "blocking" if blocking else "warning",
            "pass" if ok else "fail",
            f"Cloud VLA /{endpoint} endpoint is healthy" if ok else f"Cloud VLA /{endpoint} endpoint is not healthy",
            detail=clean_error(result.stderr or result.stdout) if not ok else clean_error(result.stdout),
            action="Inspect the OpenVLA service logs and confirm the configured VLA port.",
            source="workloads/vla-serving-host/README.md",
        )

    def check_cloud_vm_mode(self) -> None:
        result = self.cloud_vm_run(
            ["curl", "--fail", "--silent", "--show-error", "--max-time", "15", f"http://127.0.0.1:{self.cloud_vm_vla_port}/readyz"]
        )
        try:
            mode = str(json.loads(result.stdout).get("vla_mode", "unknown"))
        except json.JSONDecodeError:
            mode = "unknown"
        supported = {"mock", "openvla", "smolvla", "pi0", "groot", "onnx"}
        self.add(
            "cloud-vm.vla.mode",
            "cloud-vm",
            "warning",
            "pass" if mode in supported and mode != "mock" else "warn",
            f"Cloud VLA mode is {mode}" if mode != "mock" else "Cloud VLA service is configured for mock mode",
            action="Set VLA_MODE=openvla and rerun the cloud VM setup after GPU/model validation." if mode == "mock" else "Set VLA_MODE to a supported serving mode if this is not intentional.",
            source="tools/cloud-vm-setup/.env.example",
        )

    def cloud_vm_run(self, args: Sequence[str]) -> CommandResult:
        command = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=5",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-i",
            str(Path(os.path.expanduser(self.cloud_vm_key or ""))),
            "-p",
            str(self.cloud_vm_port),
            f"{self.cloud_vm_user}@{self.cloud_vm_host}",
            "--",
            *args,
        ]
        return self.runner.run(command, timeout=30)

    def check_unsupported_path(self) -> None:
        self.add(
            "unsupported.fedora-bare-metal",
            "unsupported",
            "informational",
            "skipped",
            "Fedora/bare-metal implementation is not supported by this checker",
            detail="This checker validates the hosted Companion SNO plus separate cloud NVIDIA VLA VM topology only.",
            action="Use --scope cloud-vm for the VLA VM. The old Fedora/libvirt/ROCm path is outside the supported deployment.",
            source="tools/cloud-vm-setup/README.md",
        )

    def check_ml_training(self) -> None:
        """Validate the ML pipeline contract without submitting a pipeline run."""
        for relative_path in ML_TRAINING_PATHS:
            path = self.repo_root / relative_path
            exists = path.is_file()
            self.add(
                f"ml-training.repo-path.{relative_path.replace('/', '.')}",
                "ml-training",
                "blocking",
                "pass" if exists else "fail",
                f"ML training path exists: {relative_path}" if exists else f"ML training path is missing: {relative_path}",
                action="Restore the upstream-aligned training path or update the fork before compiling.",
                source=relative_path,
            )

        compiler = self.runner.run(
            [
                sys.executable,
                "-c",
                "import kfp; print(getattr(kfp, '__version__', 'installed'))",
            ]
        )
        compiler_ok = compiler.returncode == 0
        self.add(
            "ml-training.kfp-compiler",
            "ml-training",
            "blocking",
            "pass" if compiler_ok else "fail",
            "KFP compiler is available" if compiler_ok else "KFP compiler is not available",
            detail=clean_error(compiler.stderr or compiler.stdout),
            action="Use the isolated compiler environment described in tools/vla-training/README.md; do not install into the system Python.",
            source="workloads/vla-training/pyproject.toml",
        )

        self.check_ml_training_git_source()

        if self.check_oc_access("ml-training", self.hub_kubeconfig):
            self.check_resources(
                "ml-training",
                self.hub_kubeconfig,
                (
                    ("ml-training.namespace", "namespace/vla-training", None),
                    ("ml-training.dspa", "dspa/dspa", "vla-training"),
                    ("ml-training.image", "imagestream/vla-training", "vla-training"),
                    ("ml-training.mlflow", "namespace/mlflow", None),
                    ("ml-training.registry", "namespace/rhoai-model-registries", None),
                ),
            )
            self.check_secrets(
                "ml-training",
                self.hub_kubeconfig,
                (
                    ("ml-training.secret.hf", "hf-credentials", "vla-training"),
                    ("ml-training.secret.minio", "minio-credentials", "vla-training"),
                    ("ml-training.secret.git", "git-source-secret", "vla-training"),
                ),
            )
            self.check_gpu_capacity(self.hub_kubeconfig)

    def check_ml_training_git_source(self) -> None:
        origin_result = self.runner.run(["git", "config", "--get", "remote.origin.url"])
        origin = origin_result.stdout.strip()
        origin_key = normalize_repo_url(origin)
        configured: set[str] = set()
        for relative_path in ML_TRAINING_GIT_SOURCE_PATHS:
            path = self.repo_root / relative_path
            if not path.exists():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                if "uri:" not in line:
                    continue
                value = line.split("uri:", 1)[1].strip().strip("\"'")
                if value.startswith(("http://", "https://", "git@")):
                    configured.add(value)
        aligned = bool(origin_key and configured and origin_key in {normalize_repo_url(value) for value in configured})
        self.add(
            "ml-training.git-source",
            "ml-training",
            "blocking",
            "pass" if aligned else "fail",
            "Training image BuildConfig points at this fork" if aligned else "Training image BuildConfig does not point at this fork",
            detail=f"origin={origin or 'unavailable'}; configured={', '.join(sorted(configured)) or 'not found'}",
            action="Update only the fork-specific BuildConfig repository URL; keep the upstream training code unchanged.",
            source=", ".join(ML_TRAINING_GIT_SOURCE_PATHS),
        )


    def check_oc_access(self, scope: str, kubeconfig: str | None) -> bool:
        result = self.oc(["whoami"], kubeconfig)
        if result.returncode == 0:
            identity = result.stdout.strip() or "authenticated identity"
            self.add(
                f"{scope}.api-access",
                scope,
                "blocking",
                "pass",
                f"{scope.capitalize()} OpenShift API is reachable",
                detail=identity,
            )
            return True
        self.add(
            f"{scope}.api-access",
            scope,
            "blocking",
            "fail",
            f"{scope.capitalize()} OpenShift API is not reachable",
            detail=clean_error(result.stderr or result.stdout),
            action=f"Log in to the {scope} cluster and verify the kubeconfig.",
        )
        return False

    def check_cluster(self, scope: str, kubeconfig: str | None) -> None:
        if shutil.which("oc") is None:
            return
        if not self.check_oc_access(scope, kubeconfig):
            return

        if scope == "hub":
            self.check_cluster_operators(scope, kubeconfig)
            self.check_gpu_capacity(kubeconfig)
            self.check_resources(
                scope,
                kubeconfig,
                (
                    ("hub.gitops", "namespace/openshift-gitops", None),
                    ("hub.kafka", "kafka/fleet", "fleet-ops"),
                    ("hub.vault", "statefulset/vault", "vault"),
                    ("hub.mlflow", "namespace/mlflow", None),
                ),
            )
            if self.profile in {"demo-workload", "factory", "agentic"}:
                self.check_deployments(scope, kubeconfig, DEMO_WORKLOAD_HUB_DEPLOYMENTS)
                self.check_secrets(scope, kubeconfig, (("hub.cosmos-hf", "hf-token", "cosmos"),))
                self.check_acm_companion(kubeconfig)
            if self.profile == "factory":
                self.check_deployments(scope, kubeconfig, FACTORY_HUB_DEPLOYMENTS)
                self.check_resources(scope, kubeconfig, (("hub.factory-b", "namespace/factory-b", None),))
            if self.profile == "agentic":
                self.check_deployments(scope, kubeconfig, AGENTIC_HUB_DEPLOYMENTS)
                self.check_secrets(
                    scope,
                    kubeconfig,
                    (
                        ("hub.agentic-hf", "hf-token", "agentic-ops"),
                        ("hub.agentic-github", "github-bot-token", "agentic-ops"),
                    ),
                )
        else:
            self.check_cluster_operators(scope, kubeconfig)
            self.check_resources(
                scope,
                kubeconfig,
                (
                    ("companion.kubevirt", "hyperconverged/kubevirt-hyperconverged", "openshift-cnv"),
                    ("companion.storage", "namespace/openshift-storage", None),
                    ("companion.robot-edge", "namespace/robot-edge", None),
                    ("companion.warehouse-edge", "namespace/warehouse-edge", None),
                ),
                optional_ids={"companion.kubevirt"}
                if self.profile in {"basic-infra", "demo-workload", "agentic"}
                else None,
            )
            if self.profile in {"demo-workload", "factory", "agentic"}:
                self.check_deployments(scope, kubeconfig, DEMO_WORKLOAD_COMPANION_DEPLOYMENTS)
                self.check_resources(
                    scope,
                    kubeconfig,
                    (
                        ("companion.kafka-ca", "secret/hub-kafka-ca", "warehouse-edge"),
                        ("companion.dispatcher-config", "configmap/mission-dispatcher-config", "robot-edge"),
                    ),
                )
            if self.profile == "factory":
                self.check_resources(
                    scope,
                    kubeconfig,
                    (
                        ("companion.factory-floor", "namespace/factory-floor", None),
                        ("companion.plc-vm", "virtualmachine/plc-gateway-01", "factory-floor"),
                    ),
                )

    def check_cluster_operators(self, scope: str, kubeconfig: str | None) -> None:
        result = self.oc(["get", "clusteroperators", "-o", "json"], kubeconfig)
        if result.returncode != 0:
            self.add(
                f"{scope}.cluster-operators",
                scope,
                "blocking",
                "fail",
                "ClusterOperator health could not be read",
                detail=clean_error(result.stderr or result.stdout),
                action="Verify cluster permissions and OpenShift API availability.",
            )
            return
        try:
            items = json.loads(result.stdout).get("items", [])
        except json.JSONDecodeError:
            self.add(
                f"{scope}.cluster-operators",
                scope,
                "blocking",
                "fail",
                "OpenShift returned invalid ClusterOperator JSON",
                action="Inspect the oc client/API response before deploying.",
            )
            return
        if not items:
            self.add(
                f"{scope}.cluster-operators",
                scope,
                "blocking",
                "fail",
                "OpenShift returned no ClusterOperators",
                action="Verify that the target is an OpenShift cluster and that the API response is complete.",
            )
            return
        unhealthy: list[str] = []
        for item in items:
            name = item.get("metadata", {}).get("name", "unknown")
            conditions = {c.get("type"): c.get("status") for c in item.get("status", {}).get("conditions", [])}
            if conditions.get("Available") != "True" or conditions.get("Degraded") == "True":
                unhealthy.append(name)
        self.add(
            f"{scope}.cluster-operators",
            scope,
            "blocking",
            "pass" if not unhealthy else "fail",
            "All ClusterOperators are available" if not unhealthy else "Some ClusterOperators are unhealthy",
            detail=", ".join(unhealthy),
            action="Resolve degraded or unavailable ClusterOperators before syncing applications.",
        )

    def check_gpu_capacity(self, kubeconfig: str | None) -> None:
        result = self.oc(["get", "nodes", "-o", "json"], kubeconfig)
        if result.returncode != 0:
            self.add(
                "hub.gpu.capacity",
                "hub",
                "blocking",
                "fail",
                "GPU inventory could not be read",
                detail=clean_error(result.stderr or result.stdout),
                action="Verify node-list permissions and GPU Operator health.",
            )
            return
        try:
            nodes = json.loads(result.stdout).get("items", [])
        except json.JSONDecodeError:
            self.add("hub.gpu.capacity", "hub", "blocking", "fail", "GPU inventory JSON is invalid")
            return
        products = [
            item.get("metadata", {}).get("labels", {}).get("nvidia.com/gpu.product", "")
            for item in nodes
        ]
        l40s = sum("L40S" in product for product in products)
        l4 = sum(product == "NVIDIA-L4" for product in products)
        self.add(
            "hub.gpu.l40s",
            "hub",
            "blocking",
            "pass" if l40s else "fail",
            f"NVIDIA L40S capacity detected ({l40s} node(s))" if l40s else "No NVIDIA L40S node detected",
            detail=", ".join(sorted({product for product in products if product})) or "no GPU product labels found",
            action="Provision or request an NVIDIA L40S node with the standard GFD product label.",
            source="docs/08-gpu-resource-planning.md",
        )
        self.add(
            "hub.gpu.l4",
            "hub",
            "warning",
            "pass" if l4 else "warn",
            f"NVIDIA L4 capacity detected ({l4} node(s))" if l4 else "No NVIDIA L4 node detected",
            detail="L4 is useful for supporting services but is not required by the minimum demo-workload runtime path.",
            action="Provision L4 capacity if the target demo profile requires it.",
            source="docs/08-gpu-resource-planning.md",
        )

    def check_resources(
        self,
        scope: str,
        kubeconfig: str | None,
        resources: Iterable[tuple[str, str, str | None]],
        optional_ids: set[str] | None = None,
    ) -> None:
        optional_ids = optional_ids or set()
        for check_id, resource, namespace in resources:
            optional = check_id in optional_ids
            args = ["get", resource, "-o", "json"]
            if namespace:
                args.extend(["-n", namespace])
            result = self.oc(args, kubeconfig)
            ok = result.returncode == 0
            ready = True
            readiness_detail = ""
            if ok:
                try:
                    data = json.loads(result.stdout)
                except json.JSONDecodeError:
                    ok = False
                    data = {}
                    readiness_detail = "resource returned invalid JSON"
                if ok:
                    ready, readiness_detail = resource_readiness(resource, data)
            self.add(
                check_id,
                scope,
                "warning" if optional else "blocking",
                "pass" if ok and ready else ("warn" if optional else "fail"),
                f"{resource} is present and ready" if ok and ready else (
                    f"Optional {resource} is not present or not ready"
                    if optional
                    else f"{resource} is missing or not ready"
                ),
                detail=(clean_error(result.stderr or result.stdout) if not ok else readiness_detail),
                action=(
                    f"Install {resource} only if this hosted-SNO profile needs it."
                    if optional
                    else f"Sync or repair the GitOps application that provides {resource}."
                ),
            )

    def check_deployments(
        self,
        scope: str,
        kubeconfig: str | None,
        deployments: Iterable[tuple[str, str]],
    ) -> None:
        for name, namespace in deployments:
            result = self.oc(["get", "deployment", name, "-n", namespace, "-o", "json"], kubeconfig)
            if result.returncode != 0:
                self.add(
                    f"{scope}.deployment.{namespace}.{name}",
                    scope,
                    "blocking",
                    "fail",
                    f"Deployment {namespace}/{name} is missing",
                    detail=clean_error(result.stderr or result.stdout),
                    action=f"Sync the GitOps workload for {name} and inspect its build/image status.",
                )
                continue
            try:
                data = json.loads(result.stdout)
            except json.JSONDecodeError:
                self.add(
                    f"{scope}.deployment.{namespace}.{name}",
                    scope,
                    "blocking",
                    "fail",
                    f"Deployment {namespace}/{name} returned invalid JSON",
                )
                continue
            desired = data.get("spec", {}).get("replicas", 1)
            available = data.get("status", {}).get("availableReplicas", 0)
            ready = available >= desired and desired > 0
            self.add(
                f"{scope}.deployment.{namespace}.{name}",
                scope,
                "blocking",
                "pass" if ready else "fail",
                f"Deployment {namespace}/{name} is ready" if ready else f"Deployment {namespace}/{name} is not ready",
                detail=f"available={available}, desired={desired}",
                action="Inspect pods, image pulls, readiness probes, and recent events.",
            )

    def check_secrets(
        self,
        scope: str,
        kubeconfig: str | None,
        secrets: Iterable[tuple[str, str, str]],
    ) -> None:
        for check_id, name, namespace in secrets:
            result = self.oc(["get", "secret", name, "-n", namespace, "-o", "name"], kubeconfig)
            ok = result.returncode == 0
            self.add(
                check_id,
                scope,
                "blocking",
                "pass" if ok else "fail",
                f"Required projected secret exists: {namespace}/{name}" if ok else f"Required projected secret is missing: {namespace}/{name}",
                action="Verify Vault initialization, VaultStaticSecret reconciliation, and the required secret path.",
            )

    def check_acm_companion(self, kubeconfig: str | None) -> None:
        result = self.oc(["get", "managedcluster", "companion", "-o", "json"], kubeconfig)
        if result.returncode != 0:
            self.add(
                "hub.acm.companion",
                "hub",
                "blocking",
                "fail",
                "ACM companion registration is missing or unreadable",
                detail=clean_error(result.stderr or result.stdout),
                action="Register the companion using infrastructure/gitops/apps/hub-acm/.",
                source="infrastructure/gitops/apps/hub-acm/README.md",
            )
            return
        try:
            conditions = json.loads(result.stdout).get("status", {}).get("conditions", [])
            values = {c.get("type"): c.get("status") for c in conditions}
        except json.JSONDecodeError:
            values = {}
        joined = condition_true(values, "joined")
        available = condition_true(values, "available", "managedclusterinfo")
        self.add(
            "hub.acm.companion",
            "hub",
            "blocking",
            "pass" if joined and available else "fail",
            "ACM reports the companion joined and available" if joined and available else "ACM companion is not fully joined and available",
            detail=f"Joined={condition_value(values, 'joined')}, Available={condition_value(values, 'available', 'managedclusterinfo')}",
            action="Complete the manual klusterlet import and ACM GitOps integration.",
            source="infrastructure/gitops/apps/hub-acm/README.md",
        )

    def oc(self, args: Sequence[str], kubeconfig: str | None) -> CommandResult:
        command = ["oc"]
        if kubeconfig:
            command.extend(["--kubeconfig", kubeconfig])
        command.extend(args)
        return self.runner.run(command)


def normalize_repo_url(value: str) -> str:
    """Compare HTTPS and SSH Git remotes by their host/path identity."""
    normalized = value.strip().strip("\"'").lower()
    if normalized.startswith("git@"):
        normalized = normalized[4:].replace(":", "/", 1)
    else:
        normalized = re.sub(r"^[a-z][a-z0-9+.-]*://", "", normalized)
        normalized = re.sub(r"^[^@]+@", "", normalized)
    return normalized.rstrip("/").removesuffix(".git")


def resource_readiness(resource: str, data: dict[str, Any]) -> tuple[bool, str]:
    """Apply readiness checks only where the resource exposes a stable status contract."""
    kind = resource.split("/", 1)[0].lower()
    status = data.get("status", {}) or {}

    if kind == "statefulset":
        desired = int((data.get("spec", {}) or {}).get("replicas", 1) or 0)
        ready = int(status.get("readyReplicas", 0) or 0)
        return ready >= desired and desired > 0, f"ready={ready}, desired={desired}"

    if kind in {"kafka", "hyperconverged"}:
        conditions = status.get("conditions", []) or []
        ready = any(
            str(condition.get("type", "")).lower() in {"ready", "available"}
            and condition.get("status") == "True"
            for condition in conditions
        )
        degraded = any(
            str(condition.get("type", "")).lower() == "degraded"
            and condition.get("status") == "True"
            for condition in conditions
        )
        if not conditions:
            return False, "status.conditions is not populated"
        return ready and not degraded, f"ready={ready}, degraded={degraded}"

    if kind == "dspa":
        conditions = status.get("conditions", []) or []
        ready = any(condition.get("type") == "Ready" and condition.get("status") == "True" for condition in conditions)
        return ready, f"Ready={ready}"

    if kind == "virtualmachine":
        printable = str(status.get("printableStatus", "")).lower()
        ready = any(
            str(condition.get("type", "")).lower().endswith("ready")
            and condition.get("status") == "True"
            for condition in status.get("conditions", []) or []
        )
        return printable == "running" or ready, f"printableStatus={printable or 'unknown'}, ready={ready}"

    return True, ""


def condition_value(values: dict[str, str], *suffixes: str) -> str:
    for key, value in values.items():
        normalized = str(key).lower()
        if any(normalized == suffix or normalized.endswith(suffix) for suffix in suffixes):
            return str(value)
    return "unknown"


def condition_true(values: dict[str, str], *suffixes: str) -> bool:
    return condition_value(values, *suffixes) == "True"


def clean_error(value: str) -> str:
    """Keep command output useful while preventing accidental secret dumps."""
    text = " ".join(value.strip().split())
    if len(text) > 300:
        return f"{text[:297]}..."
    return text


def selected_scopes(raw_scope: str) -> set[str]:
    if raw_scope == "all":
        return set(SCOPES)
    if raw_scope in LEGACY_SCOPES:
        return {"unsupported"}
    return {raw_scope}


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILES),
        default="basic-infra",
        help="readiness profile: basic-infra, demo-workload, factory, or agentic",
    )
    parser.add_argument(
        "--scope",
        choices=["all", *sorted(SCOPES | SPECIAL_SCOPES), *sorted(LEGACY_SCOPES)],
        default="all",
        help="supported scopes: local, hub, companion, cloud-vm, ml-training; fedora/host are reported as unsupported",
    )
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument(
        "--gitops-profile",
        choices=("auto", "upstream", "fork"),
        default=os.environ.get("GITOPS_REPOSITORY_PROFILE", "auto"),
        help="GitOps source profile: auto-detect from origin, upstream legacy, or rhkp fork",
    )
    parser.add_argument("--hub-kubeconfig", default=os.environ.get("KUBECONFIG"))
    parser.add_argument(
        "--companion-kubeconfig",
        default=os.environ.get("COMPANION_KUBECONFIG") or str(DEFAULT_COMPANION_KUBECONFIG),
    )
    parser.add_argument("--cloud-vm-host", default=os.environ.get("VLA_VM_IP"))
    parser.add_argument("--cloud-vm-user", default=os.environ.get("VLA_VM_SSH_USER"))
    parser.add_argument("--cloud-vm-key", default=os.environ.get("VLA_VM_SSH_KEY"))
    parser.add_argument("--cloud-vm-port", type=int, default=int(os.environ.get("VLA_VM_SSH_PORT", "22")))
    parser.add_argument("--cloud-vm-gpu-model", default=os.environ.get("VLA_GPU_MODEL"))
    parser.add_argument("--vla-port", type=int, default=int(os.environ.get("VLA_PORT", "8000")))
    parser.add_argument("--vla-health-url", default=os.environ.get("VLA_HEALTH_URL"))
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--explain", action="store_true", help="include remediation and source details")
    parser.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="colorize text output; auto enables color only for an interactive terminal",
    )
    args = parser.parse_args(argv)
    if args.profile not in PROFILES:
        parser.error(f"unknown readiness profile: {args.profile}")
    return args


ANSI = {
    "red": "\033[31m",
    "yellow": "\033[33m",
    "green": "\033[32m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "bold": "\033[1m",
    "reset": "\033[0m",
}

SCOPE_COLORS = {
    "local": "cyan",
    "companion": "blue",
    "hub": "cyan",
    "cloud-vm": "magenta",
    "unsupported": "yellow",
    "ml-training": "magenta",
}


def paint(value: str, color: str, enabled: bool) -> str:
    if not enabled:
        return value
    return f"{ANSI[color]}{value}{ANSI['reset']}"


def render_text(
    results: Sequence[CheckResult],
    explain: bool,
    color: bool = False,
    profile: str | None = None,
) -> str:
    counts = {status: sum(result.status == status for result in results) for status in ("pass", "warn", "fail", "unknown", "skipped")}
    groups: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
        ("FAILING", "red", "❌", ("fail",)),
        ("WARNINGS", "yellow", "⚠️", ("warn",)),
        ("PASSING", "green", "✅", ("pass",)),
        ("OTHER", "cyan", "ℹ️", ("unknown", "skipped")),
    )
    lines = [
        paint("Industrial AI Showcase prerequisite preflight", "bold", color),
        "=" * 48,
        paint(f"Supported topology: {SUPPORTED_TOPOLOGY}", "green", color),
        paint(f"Unsupported here: {UNSUPPORTED_PATH}", "yellow", color),
    ]
    if profile:
        description = PROFILES.get(profile)
        label = f"Profile: {paint(profile, 'cyan', color)}"
        lines.append(f"{label} — {description}" if description else label)
    lines.extend(
        [
            paint("Legend: ✅ passing  ⚠️ warning  ❌ failing  ℹ️ informational", "cyan", color),
            "",
        ]
    )
    for heading, heading_color, icon, statuses in groups:
        grouped = [result for result in results if result.status in statuses]
        if not grouped:
            continue
        lines.append(paint(f"{icon} {heading} ({len(grouped)})", heading_color, color))
        for result in grouped:
            marker = {"pass": "PASS", "warn": "WARN", "fail": "FAIL", "unknown": "????", "skipped": "SKIP"}.get(result.status, "????")
            marker_color = {"pass": "green", "warn": "yellow", "fail": "red"}.get(result.status, "cyan")
            scope = paint(f"[{result.scope:9}]", SCOPE_COLORS.get(result.scope, "cyan"), color)
            lines.append(
                f"  {paint(marker, marker_color, color):4} {scope} {result.id}: {result.summary}"
            )
            if result.detail:
                detail_label = "Err:" if result.status == "fail" else "Detail:"
                detail_color = "red" if result.status == "fail" else "cyan"
                lines.append(
                    f"       {paint(detail_label, detail_color, color)} {paint(result.detail, detail_color, color)}"
                )
            if explain and result.action and result.status in {"fail", "warn"}:
                lines.append(
                    f"       {paint('Action:', 'yellow', color)} {paint(result.action, 'yellow', color)}"
                )
            if explain and result.source:
                lines.append(
                    f"       {paint('Source:', 'cyan', color)} {paint(result.source, 'cyan', color)}"
                )
        lines.append("")
    lines.append("")
    if any(result.status == "fail" and result.severity == "blocking" for result in results):
        outcome, outcome_color = "BLOCKED", "red"
    elif any(result.status in {"fail", "warn"} for result in results):
        outcome, outcome_color = "READY WITH WARNINGS", "yellow"
    else:
        outcome, outcome_color = "READY", "green"
    lines.append(paint(f"Result: {outcome}", outcome_color, color))
    lines.append("Summary: " + ", ".join(f"{key}={value}" for key, value in counts.items() if value))
    return "\n".join(lines)


def exit_code(results: Sequence[CheckResult]) -> int:
    if any(result.status == "fail" and result.severity == "blocking" for result in results):
        return 2
    if any(
        result.status == "fail" and result.severity != "blocking"
        or result.status == "warn" and result.severity != "informational"
        for result in results
    ):
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    checker = PreflightChecker(
        repo_root=args.repo_root.resolve(),
        profile=args.profile,
        scopes=selected_scopes(args.scope),
        hub_kubeconfig=args.hub_kubeconfig,
        companion_kubeconfig=args.companion_kubeconfig,
        vla_health_url=args.vla_health_url,
        cloud_vm_host=args.cloud_vm_host,
        cloud_vm_user=args.cloud_vm_user,
        cloud_vm_key=args.cloud_vm_key,
        cloud_vm_port=args.cloud_vm_port,
        cloud_vm_gpu_model=args.cloud_vm_gpu_model,
        cloud_vm_vla_port=args.vla_port,
        gitops_profile=args.gitops_profile,
    )
    results = checker.run()
    if args.format == "json":
        rendered = json.dumps(
            {
                "profile": args.profile,
                "profile_description": PROFILES[args.profile],
                "supported_topology": SUPPORTED_TOPOLOGY,
                "unsupported_paths": [UNSUPPORTED_PATH],
                "scopes": sorted(checker.scopes),
                "results": [result.to_dict() for result in results],
                "exit_code": exit_code(results),
            },
            indent=2,
        )
    else:
        color = args.color == "always" or (args.color == "auto" and sys.stdout.isatty() and args.output is None)
        rendered = render_text(results, args.explain, color=color, profile=args.profile)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return exit_code(results)


if __name__ == "__main__":
    raise SystemExit(main())
