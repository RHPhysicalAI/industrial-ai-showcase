# mlflow (platform layer)

RHOAI-managed MLflow uses CNPG Postgres and S3 artifact storage. Session 06 established the backend; Session 08b moved placeholder S3 Secrets into Vault. Those historical sessions did not deploy SeaweedFS.

The 2026-09-29 migration target references the shared `infrastructure/gitops/components/seaweedfs/` Kustomize base and patches its credential Secret name and `200Gi` PVC capacity. It runs one replica of `docker.io/chrislusf/seaweedfs:4.48` in `mini` mode. The S3-only Service is `http://seaweedfs.mlflow.svc.cluster.local:8333`; `mlflow-s3-credentials` and `s3://mlflow-artifacts/` stay unchanged. DSPA shares this endpoint and uses `vla-training/s3-credentials` with `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`. Bucket Jobs use `public.ecr.aws/aws-cli/aws-cli:2.34.0`.

The isolated S3 canary passed, including access from `vla-training`; see [validation evidence](../../../../../tools/object-storage/VALIDATION.md). Existing cluster stores are upstream-managed and shared; follow the [controlled copy/cutover guide](../../../../../tools/object-storage/README.md) before migrating live data or consumers.

Bucket-init Jobs are Argo CD `Sync` hooks in wave `1`, with bounded retries and a 600-second timeout. This creates buckets during Sync, before dependent applications must become healthy; deferring creation until after health would deadlock a new DSPA waiting for its missing bucket.

## Accepted Phase-0 concessions

Two items are intentionally NOT fully automated in Phase 0. Both are marked `TODO(phase-1)` in the manifests and documented here.

### 1. `redhat-ods-applications/mlflow-db-app` is manually mirrored

**Why**: RHOAI places the MLflow pod in its own managed namespace (`redhat-ods-applications`), not in `mlflow`. The pod's `backendStoreUriFrom` Secret lookup is namespace-local, so the CNPG-generated `mlflow/mlflow-db-app` Secret has to be copied across. CNPG generates this Secret itself; we can't source it from Vault without putting CNPG's password under our control (which `spec.managed.roles` makes possible but adds churn).

**Pattern**: a one-off `oc` pipeline that copies the Secret, stripping owner-refs, and appends `?sslmode=disable` to the URI (see concession #2).

```bash
# Run once after CNPG Cluster comes up, and whenever the password rotates.
uri=$(oc get secret -n mlflow mlflow-db-app -o jsonpath='{.data.uri}' | base64 -d)
new_uri="${uri}?sslmode=disable"

oc get secret -n mlflow mlflow-db-app -o json \
  | jq 'del(.metadata.ownerReferences, .metadata.resourceVersion, .metadata.uid, .metadata.creationTimestamp, .metadata.managedFields) | .metadata.namespace="redhat-ods-applications"' \
  | oc apply -f -

oc patch secret -n redhat-ods-applications mlflow-db-app \
  --type=json \
  -p "[{\"op\":\"replace\",\"path\":\"/data/uri\",\"value\":\"$(echo -n "$new_uri" | base64 -w0)\"}]"

# Bounce the MLflow pod to pick up changes:
oc delete pod -n redhat-ods-applications -l app=mlflow
```

### 2. Postgres connection uses `sslmode=disable`

**Why**: CNPG serves Postgres with a self-signed CA that MLflow's psycopg2 doesn't trust. Full fix requires extracting CNPG's `ca.crt` from `mlflow/mlflow-db-ca` into a ConfigMap in `redhat-ods-applications`, wiring it into the MLflow CR via `caBundleConfigMap`, and flipping to `sslmode=verify-full`.

Intra-cluster traffic is mesh-mTLS-protected (Service Mesh 3 per ADR-020), so disabling Postgres-level TLS for this specific hop doesn't open a real exposure — the mesh is the security boundary. Flip to `verify-full` when the first workload that genuinely needs end-to-end TLS lands (Phase 1+).

## When CNPG rotates the password

CNPG regenerates `mlflow/mlflow-db-app` if:
- The Cluster CR's bootstrap changes.
- A `.spec.managed.roles[]` directive reshapes the `mlflow` role.

After any regeneration, re-run the script above. Adopting `spec.managed.roles` to control the password ourselves is the Phase-1 fix that makes this automatic.

## Upstream references

- CNPG auto-generated Secrets: https://cloudnative-pg.io/documentation/current/applications/#secrets
- MLflow CR `caBundleConfigMap` field: `oc explain mlflow.spec.caBundleConfigMap --api-version=mlflow.opendatahub.io/v1`
- RHOAI managed-namespace placement: `.status.components.mlflowoperator` in the DataScienceCluster CR.
