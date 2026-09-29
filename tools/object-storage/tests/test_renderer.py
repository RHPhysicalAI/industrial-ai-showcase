"""Cover the oc multi-resource JSON format used by the live canary."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("s3_canary_renderer", Path(__file__).parents[1] / "canary.py")
CANARY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CANARY)


def test_consecutive_json_resources_and_list():
    docs = [{"kind": "Service"}, {"kind": "Deployment"}]
    assert CANARY.decode_resources("\n".join(json.dumps(d) for d in docs)) == docs
    assert CANARY.decode_resources(json.dumps({"kind": "List", "items": docs})) == docs
    with pytest.raises(CANARY.CanaryError):
        CANARY.decode_resources('{"kind":"Service"}\ninvalid')


def test_real_oc_dry_run_output_is_readable():
    rendered = subprocess.run(["oc", "kustomize", str(CANARY.BASE)], check=True, capture_output=True, text=True).stdout
    result = subprocess.run(
        ["oc", "create", "--dry-run=client", "--validate=false", "-f", "-", "-o", "json"],
        input=rendered, check=True, capture_output=True, text=True,
    )
    resources = CANARY.decode_resources(result.stdout)
    assert {(r["kind"], r["metadata"]["name"]) for r in resources} == CANARY.RESOURCES
