# Object-storage migration validation — 2026-09-29

## Outcome

The shared SeaweedFS deployment ran successfully on OpenShift. The standard AWS
S3 client completed authenticated upload/download checks from both the isolated
storage namespace and the existing RHOAI training namespace. No GPU was requested
or changed, and no model training or inference was run.

| Validation | Result |
| --- | --- |
| SeaweedFS `4.48` Deployment | Ready, one replica, OpenShift `restricted-v2` SCC |
| Persistent storage | New 5Gi `gp3` PVC in `showcase-storage-canary` |
| Server request | 100m CPU, 256Mi memory; no GPU |
| AWS CLI `2.34.0`, sandbox + restart | **15 passed, 0 failures** |
| Same AWS CLI canary from `vla-training` | **13 passed, 0 failures** |
| Updated DSPA S3 configuration | Accepted by installed RHOAI API with `oc apply --dry-run=server` |
| KFP definition | Recompiled with KFP 2.17.0; matches committed YAML |
| Local regression tests | **139 passed, 17 subtests passed**; manifest, transfer, canary, training artifact and prerequisite regressions |

Self-review added fail-closed checks against outdated sandbox manifests,
UID-guarded transfer-helper deletion, and termination-signal cleanup, with
regression tests. No shared storage or GPU workloads were changed by this review.
Both live canaries were rerun after those changes and passed with the counts above.
RHOAI DSPA and serving/Loki Vault projections also passed server-side dry-run
validation. New and modified local documentation links resolve.

The pre-commit review covered the pending additions, not Git history. No new
private endpoints, deployment IPs, credentials, keys, or certificates were found;
local `.env` files remain ignored. Loopback/bind addresses and reserved test
fixtures are intentional. The current tracked/new source tree contains no
references to the retired storage provider; historical commits are unchanged.

The client used ordinary Signature V4 requests and path-style addressing with the
AWS CLI's default checksum behavior. The CSV fixture was 45 bytes. The multipart
fixture contained a 5MiB first part and a 1MiB final part.

## Observed output

```text
PASS owned SeaweedFS sandbox ready (CPU only)
PASS AWS CLI client ready with Secret references and restricted Pod settings
PASS bucket create / head / list
PASS HeadObject CSV content length / content type
PASS tiny CSV put / get SHA256 integrity
PASS Range GET exact bytes
PASS wrong credentials rejected
PASS anonymous credentials rejected
PASS CopyObject SHA256 integrity
PASS multipart upload / complete: 5 MiB + 1 MiB, SHA256 integrity
PASS aborted multipart upload cleanup
PASS paginated ListObjectsV2 with explicit continuation tokens
PASS persistence: same PVC and all SHA256 digests after owned Deployment restart
PASS delete objects / multipart cleanup / delete test bucket
PASS owned temporary client Pod removed
PASS S3 canary: 15 checks passed; 0 failures
```

The second run used `--existing --namespace vla-training` against the isolated
SeaweedFS endpoint, with a uniquely named temporary credential Secret. It skipped
server creation/restart, passed the same API tests, and removed its test bucket,
objects, multipart sessions, client Pod, and temporary Secret.

## Repeat the checks

```bash
bash tools/object-storage/canary.sh --check-persistence

# With the documented local test dependencies installed:
PYTHONPATH=workloads/vla-serving-host/src:workloads/vla-training/src \
  .venv/bin/python -m pytest \
    tools/cloud-vm-setup/tests tools/object-storage/tests \
    workloads/vla-serving-host/tests/test_s3_loader.py \
    workloads/vla-training/tests/test_fine_tune_artifacts.py \
    tools/preflight/tests -q
```

Local tests require Python 3, pytest, PyYAML, boto3, `oc`, and `kustomize`.
The live canary only requires Python 3 and `oc`; its client image contains the
AWS CLI, so nothing is installed at runtime. Use the [runbook](README.md) for
configuration and cleanup.

## What this proves and what remains

This verifies SeaweedFS deployment, persistence, authentication, and the S3
operations exercised by the canary, including connectivity from the RHOAI
namespace. It is not a full AWS S3 conformance test or a vendor support
certification. RHOAI's real DSPA pipeline, MLflow, Loki/Thanos, GPU serving, and
VM transfer were not executed against the new backend in this validation.

The three repository storage definitions, consumers, setup jobs, transfer tools,
and documentation now target SeaweedFS. The live stores managed by upstream Argo
applications were not deleted, repointed, or copied. Their existing data and
consumer cutover require the controlled migration steps in the runbook. Retaining
them protects shared data and provides a rollback path; this report does not claim
that live data migration has already completed.

Remaining validation resources: the `showcase-storage-canary` namespace, generated
credential Secret, SeaweedFS Deployment/Service/NetworkPolicy, and 5Gi PVC. All test
data and temporary client resources were removed after successful runs.
