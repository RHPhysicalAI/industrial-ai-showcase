"""Unit tests for the dependency-free preflight checker."""

from __future__ import annotations

import json
from pathlib import Path

from tools.preflight.check import (
    CommandResult,
    CommandRunner,
    CheckResult,
    PreflightChecker,
    condition_true,
    exit_code,
    normalize_repo_url,
    parse_args,
    render_text,
    resource_readiness,
    selected_scopes,
)


class FakeRunner(CommandRunner):
    def __init__(self, responses: dict[tuple[str, ...], CommandResult]) -> None:
        self.responses = responses

    def run(self, args: list[str] | tuple[str, ...], timeout: int = 20) -> CommandResult:
        del timeout
        return self.responses.get(tuple(args), CommandResult(0, "{}", ""))


def test_blocking_failure_returns_exit_code_two() -> None:
    checker = PreflightChecker(
        repo_root=Path("."),
        profile="demo-workload",
        scopes={"cloud-vm"},
        hub_kubeconfig=None,
        companion_kubeconfig=None,
        vla_health_url=None,
    )
    results = checker.run()
    assert any(result.id == "cloud-vm.target" and result.status == "fail" for result in results)
    assert exit_code(results) == 2


def test_nonblocking_failure_returns_exit_code_one() -> None:
    result = CheckResult("local.command.jq", "local", "warning", "fail", "jq is not installed")
    assert exit_code([result]) == 1


def test_json_results_are_serializable() -> None:
    checker = PreflightChecker(
        repo_root=Path("."),
        profile="demo-workload",
        scopes={"cloud-vm"},
        hub_kubeconfig=None,
        companion_kubeconfig=None,
        vla_health_url=None,
    )
    results = checker.run()
    encoded = json.dumps([result.to_dict() for result in results])
    assert "cloud-vm.target" in encoded


def test_text_renderer_includes_remediation() -> None:
    checker = PreflightChecker(
        repo_root=Path("."),
        profile="demo-workload",
        scopes={"cloud-vm"},
        hub_kubeconfig=None,
        companion_kubeconfig=None,
        vla_health_url=None,
    )
    results = checker.run()
    output = render_text(results, explain=True)
    assert "Action:" in output
    assert "cloud VM connection" in output


def test_text_renderer_groups_results_by_status() -> None:
    checker = PreflightChecker(
        repo_root=Path("."),
        profile="demo-workload",
        scopes={"cloud-vm"},
        hub_kubeconfig=None,
        companion_kubeconfig=None,
        vla_health_url=None,
    )
    output = render_text(
        [
            CheckResult("cloud-vm.target", "cloud-vm", "blocking", "fail", "VM target missing"),
            CheckResult("cloud-vm.vla.mode", "cloud-vm", "warning", "warn", "Mock mode"),
        ],
        explain=False,
    )
    assert "FAILING" in output
    assert "WARNINGS" in output


def test_text_renderer_supports_explicit_color() -> None:
    checker = PreflightChecker(
        repo_root=Path("."),
        profile="demo-workload",
        scopes={"cloud-vm"},
        hub_kubeconfig=None,
        companion_kubeconfig=None,
        vla_health_url=None,
    )
    output = render_text(
        [
            CheckResult(
                "cloud-vm.target",
                "cloud-vm",
                "blocking",
                "fail",
                "VM target missing",
                action="Configure the VM",
                source="tools/cloud-vm-setup/.env.example",
            ),
            CheckResult(
                "cloud-vm.vla.mode",
                "cloud-vm",
                "warning",
                "warn",
                "Mock mode",
                action="Use OpenVLA",
                source="tools/cloud-vm-setup/README.md",
            ),
        ],
        explain=True,
        color=True,
    )
    assert "\033[31m" in output
    assert "\033[33mAction:" in output
    assert "\033[36mSource:" in output
    assert "Result: BLOCKED" in output


def test_text_renderer_identifies_readiness_profile() -> None:
    result = CheckResult("local.example", "local", "informational", "pass", "Example check")
    output = render_text([result], explain=False, profile="basic-infra")
    assert "Profile: basic-infra" in output
    assert "foundational local, cloud VM, and cluster infrastructure" in output
    assert "Unsupported here:" in output


def test_readiness_profiles_and_manifest_contracts() -> None:
    assert parse_args([]).profile == "basic-infra"
    assert parse_args(["--profile", "agentic"]).profile == "agentic"
    assert parse_args(["--profile", "factory"]).profile == "factory"
    assert resource_readiness(
        "statefulset/vault",
        {"spec": {"replicas": 1}, "status": {"readyReplicas": 1}},
    ) == (True, "ready=1, desired=1")
    assert resource_readiness(
        "kafka/fleet",
        {"status": {"conditions": [{"type": "Ready", "status": "True"}]}},
    )[0]


def test_acm_condition_names_are_matched_by_suffix() -> None:
    values = {
        "ManagedClusterJoined": "True",
        "ManagedClusterConditionAvailable": "True",
    }
    assert condition_true(values, "joined")
    assert condition_true(values, "available")


def test_git_remote_forms_normalize_to_same_repository() -> None:
    assert normalize_repo_url("https://github.com/rhkp/industrial-ai-showcase.git") == normalize_repo_url(
        "git@github.com:rhkp/industrial-ai-showcase.git"
    )


def test_fedora_scope_is_explicitly_unsupported() -> None:
    assert selected_scopes("fedora") == {"unsupported"}
    assert selected_scopes("host") == {"unsupported"}
    assert "cloud-vm" in selected_scopes("all")
    assert "fedora" not in selected_scopes("all")


def test_ml_training_scope_is_explicit() -> None:
    assert selected_scopes("ml-training") == {"ml-training"}
    assert "ml-training" not in selected_scopes("all")
