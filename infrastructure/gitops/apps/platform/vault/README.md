# vault

HashiCorp Vault, single-replica, file-backed, for the Phase 0 Secrets substrate. Swap to HA Raft + KMS-backed unseal for production per customer site.

There is no external Route; Vault is reached in-cluster at `http://vault.vault.svc.cluster.local:8200`. All setup happens via `oc exec` into the pod.

## One-time init + unseal (after first sync)

```bash
# 1. Initialize
oc exec -n vault vault-0 -- vault operator init -key-shares=5 -key-threshold=3

# Record the 5 unseal keys and the initial root token somewhere durable.
# Never commit them.

# 2. Unseal (three of the five keys)
for key in KEY1 KEY2 KEY3; do
  oc exec -n vault vault-0 -- vault operator unseal "$key"
done
```

## One-time KV engine + K8s auth setup

Do this work inside the pod — the container's `VAULT_ADDR` is already set to `http://127.0.0.1:8200`, and the pod's `sh` is BusyBox which doesn't tolerate backslash-continuations or indented heredoc terminators.

```bash
oc exec -n vault -it vault-0 -- sh
# inside the pod:

export VAULT_TOKEN=<initial-root-token>

vault secrets enable -path=kv kv-v2

vault auth enable kubernetes

vault write auth/kubernetes/config kubernetes_host=https://kubernetes.default.svc:443 disable_iss_validation=true

# Pipe the policy body; heredoc terminators with leading whitespace don't close in BusyBox sh.
printf 'path "kv/data/*" {\n  capabilities = ["read"]\n}\n' | vault policy write vso-read -

# One-liner role binding (no backslash continuations).
vault write auth/kubernetes/role/vso-read bound_service_account_names='*' bound_service_account_namespaces='*' policies=vso-read ttl=24h
```

## Seed storage credentials out of band

VSO projects these KV paths into Kubernetes Secrets in the consumer namespaces. Supply approved credential values through local shell variables; do not commit them or enable shell tracing. The historical Phase-0 placeholders are not valid setup instructions. Coordinate credential rotation and endpoint changes with the [storage copy/cutover procedure](../../../../../tools/object-storage/README.md); the SeaweedFS migration has not yet been validated against live consumers.

```bash
# Still inside the pod shell from the previous step
: "${MLFLOW_S3_ACCESS_KEY_ID:?Supply the approved MLflow S3 access key}"
: "${MLFLOW_S3_SECRET_ACCESS_KEY:?Supply the approved MLflow S3 secret}"
: "${OBS_S3_ACCESS_KEY_ID:?Supply the approved observability S3 access key}"
: "${OBS_S3_SECRET_ACCESS_KEY:?Supply the approved observability S3 secret}"
: "${WAREHOUSE_S3_ACCESS_KEY_ID:?Supply the approved warehouse S3 access key}"
: "${WAREHOUSE_S3_SECRET_ACCESS_KEY:?Supply the approved warehouse S3 secret}"
vault kv put kv/mlflow/s3 AWS_ACCESS_KEY_ID="$MLFLOW_S3_ACCESS_KEY_ID" AWS_SECRET_ACCESS_KEY="$MLFLOW_S3_SECRET_ACCESS_KEY"
vault kv put kv/obs/s3 AWS_ACCESS_KEY_ID="$OBS_S3_ACCESS_KEY_ID" AWS_SECRET_ACCESS_KEY="$OBS_S3_SECRET_ACCESS_KEY"
vault kv put kv/loki/s3 access_key_id="$OBS_S3_ACCESS_KEY_ID" access_key_secret="$OBS_S3_SECRET_ACCESS_KEY" bucketnames=loki-logs endpoint=http://seaweedfs.obs-storage.svc.cluster.local:8333 region=us-east-1
vault kv put kv/warehouse/s3 AWS_ACCESS_KEY_ID="$WAREHOUSE_S3_ACCESS_KEY_ID" AWS_SECRET_ACCESS_KEY="$WAREHOUSE_S3_SECRET_ACCESS_KEY"
```

The storage Secrets are `mlflow-s3-credentials` for MLflow (unchanged), `vla-training/s3-credentials` for training, `obs-storage/obs-s3-credentials`, and `warehouse-data/s3-credentials`. They expose `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`; Loki's Secret uses its own schema shown above. The warehouse `VaultStaticSecret` uses mount `kv`, path `warehouse/s3`. The CRs live with MLflow, DSPA, observability storage/Loki, and the warehouse camera library.

Loki's `VaultStaticSecret` template fixes the projected `endpoint` to `http://seaweedfs.obs-storage.svc.cluster.local:8333`; an old value in `kv/loki/s3` cannot keep the consumer on the retired endpoint. Credentials remain Vault-sourced. The seed example includes the same endpoint for consistency, but the projection template controls the Kubernetes Secret value.

Seed unrelated service credentials separately, for example `kv/coturn/credentials`, using an approved password rather than a committed placeholder.

## After a pod restart

Vault re-seals. Re-run the unseal step above. Production deploys use KMS-backed auto-unseal to avoid this.
