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

## Seed the Phase-0 placeholder values

VSO projects these KV paths into Kubernetes Secrets in the consumer namespaces. Put the values once; rotation later is a `vault kv put` with new values + a pod restart of the consumer.

```bash
# Still inside the pod shell from the previous step
vault kv put kv/mlflow/s3 AWS_ACCESS_KEY_ID=mlflow-root AWS_SECRET_ACCESS_KEY=phase-0-placeholder-rotate-in-s08
vault kv put kv/obs/s3 AWS_ACCESS_KEY_ID=obs-root AWS_SECRET_ACCESS_KEY=phase-0-placeholder-rotate-in-s08
vault kv put kv/loki/s3 access_key_id=obs-root access_key_secret=phase-0-placeholder-rotate-in-s08 bucketnames=loki-logs endpoint=http://minio.obs-storage.svc.cluster.local:9000 region=us-east-1
vault kv put kv/coturn/credentials password=phase-0-placeholder-rotate-before-demo
```

The `VaultStaticSecret` CRs in `apps/platform/mlflow/`, `apps/observability/storage/`, and `apps/observability/loki/` reference these paths.

## After a pod restart

Vault re-seals. Re-run the unseal step above. Production deploys use KMS-backed auto-unseal to avoid this.
