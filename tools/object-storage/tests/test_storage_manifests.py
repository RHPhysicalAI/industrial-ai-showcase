"""Render real manifests to catch namespace, credential and pipeline drift."""

import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
APPS = ROOT / "infrastructure/gitops/apps"


def render(path):
    result = subprocess.run(
        ["kustomize", "build", "--load-restrictor", "LoadRestrictionsNone", str(APPS / path)],
        check=True, capture_output=True, text=True,
    )
    return list(yaml.safe_load_all(result.stdout))


@pytest.mark.parametrize("path,namespace,secret,capacity", [
    ("platform/mlflow", "mlflow", "mlflow-s3-credentials", "200Gi"),
    ("observability/storage", "obs-storage", "obs-s3-credentials", "100Gi"),
    ("platform/warehouse-camera-library", "warehouse-data", "s3-credentials", "5Gi"),
])
def test_storage_overlays_wire_scoped_credentials_and_preserved_data(path, namespace, secret, capacity):
    resources = render(path)
    deployment = next(r for r in resources if r["kind"] == "Deployment" and r["metadata"]["name"] == "seaweedfs")
    assert deployment["metadata"]["namespace"] == namespace
    pod = deployment["spec"]["template"]["spec"]
    assert pod["securityContext"]["runAsNonRoot"]
    assert not pod["automountServiceAccountToken"]
    container = pod["containers"][0]
    assert container["envFrom"][0]["secretRef"]["name"] == secret
    assert "nvidia.com/gpu" not in container["resources"]["limits"]
    assert not container["securityContext"]["allowPrivilegeEscalation"]
    assert any(r["kind"] == "VaultStaticSecret" and r["spec"]["destination"]["name"] == secret
               and r["metadata"]["namespace"] == namespace for r in resources)
    claim = next(r for r in resources if r["kind"] == "PersistentVolumeClaim" and r["metadata"]["name"] == "seaweedfs-data")
    assert claim["metadata"]["namespace"] == namespace
    assert claim["spec"]["resources"]["requests"]["storage"] == capacity
    assert "Prune=false" in claim["metadata"]["annotations"]["argocd.argoproj.io/sync-options"]
    service = next(r for r in resources if r["kind"] == "Service" and r["metadata"]["name"] == "seaweedfs")
    assert [p["port"] for p in service["spec"]["ports"]] == [8333]
    for job in (r for r in resources if r["kind"] == "Job"):
        annotations = job["metadata"]["annotations"]
        assert annotations["argocd.argoproj.io/hook"] == "Sync"
        assert job["spec"]["activeDeadlineSeconds"] <= 600


def test_mlflow_operator_secrets_keep_their_cross_namespace_target():
    resources = render("platform/mlflow")
    credentials = [r for r in resources if r["kind"] == "VaultStaticSecret"
                   and r["metadata"]["name"] == "mlflow-s3-credentials"]
    assert {r["metadata"]["namespace"] for r in credentials} == {"mlflow", "redhat-ods-applications"}


def test_dspa_and_compiled_kfp_share_storage_contract():
    resources = render("platform/dspa")
    dspa = next(r for r in resources if r["kind"] == "DataSciencePipelinesApplication")
    storage = dspa["spec"]["objectStorage"]["externalStorage"]
    assert (storage["host"], storage["port"], storage["scheme"]) == (
        "seaweedfs.mlflow.svc.cluster.local", "8333", "http")
    assert storage["s3CredentialsSecret"] == {
        "secretName": "s3-credentials", "accessKey": "AWS_ACCESS_KEY_ID", "secretKey": "AWS_SECRET_ACCESS_KEY"}
    compiled = list(yaml.safe_load_all((ROOT / "workloads/vla-training/vla_finetune_pipeline.yaml").read_text()))
    endpoints, credentials = [], []

    def visit(value):
        if isinstance(value, dict):
            if value.get("name") == "S3_ENDPOINT":
                endpoints.append(value["value"])
            if "secretName" in value and "keyToEnv" in value:
                credentials.append(value)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(compiled)
    assert len(endpoints) == 4
    assert set(endpoints) == {"http://seaweedfs.mlflow.svc:8333"}
    s3_credentials = [c for c in credentials if c["secretName"] == "s3-credentials"]
    assert len(s3_credentials) == 4
    for credential in s3_credentials:
        assert {v["secretKey"] for v in credential["keyToEnv"]} == {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"}
