# Network policy templates

Workload namespaces adopt zero-trust east-west by importing the templates in this directory via Kustomize:

```yaml
# apps/<layer>/<workload>/network-policies.yaml (as part of the workload's kustomization)
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../../../../../infrastructure/security/network-policies/default-deny.yaml
  - ../../../../../infrastructure/security/network-policies/allow-argocd-sync.yaml
  - ../../../../../infrastructure/security/network-policies/allow-platform-monitoring.yaml
  - ../../../../../infrastructure/security/network-policies/allow-dns-egress.yaml
  - <workload-specific allowlist>.yaml
```

The `default-deny-all` policy denies all ingress + egress. The three `allow-*` companions unblock the reconcile + metrics + DNS paths every workload needs. Workload-specific allowlists (e.g., MLflow → SeaweedFS, Loki → obs-storage SeaweedFS) live next to the workload's other manifests.

## Retroactive application

Session 08 provides the templates. Existing workload namespaces (`mlflow`, `obs-storage`, `cnpg-system`, `istio-system`, etc.) are NOT auto-covered — applying default-deny retroactively risks breaking running traffic. Each workload's next PR after Session 08 adopts these templates + tests its own allowlist.

## Production tightening

Phase 0 scope is "establish the template." Phase 1+ workloads adopt per-workload. FIPS + STIG + strict mTLS combinations live on the companion cluster per ADR-017.
