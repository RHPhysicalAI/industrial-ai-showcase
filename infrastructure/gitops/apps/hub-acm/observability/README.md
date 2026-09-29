# hub-acm/observability — MultiClusterObservability

Hub-side MCO manifests deploy the Thanos stack + Grafana on the hub and auto-deploy the `metrics-collector` addon onto every ACM-managed cluster. Managed clusters `remote_write` their platform metrics to the hub Thanos Receiver; the storage migration targets SeaweedFS in `obs-storage`, bucket `thanos`.

The 2026-09-29 target uses the shared SeaweedFS Kustomize base, `docker.io/chrislusf/seaweedfs:4.48` `mini`, one replica, and a new `100Gi` PVC matching the repository's previous capacity. The isolated [S3 canary passed](../../../../../tools/object-storage/VALIDATION.md); Thanos itself was not migrated in that test. Existing upstream-managed stores are shared. Follow the [controlled copy/cutover guide](../../../../../tools/object-storage/README.md) before changing the live Thanos Secret or endpoint.

Storage bucket-init Jobs run as Argo CD `Sync` hooks in wave `1`, with bounded retries and a 600-second timeout. Loki's `VaultStaticSecret` template fixes the projected endpoint to `http://seaweedfs.obs-storage.svc.cluster.local:8333`, overriding any stale endpoint stored in Vault. Thanos's imperative Secret below must still be updated as part of the controlled cutover.

## What reconciles from Git

- `namespace.yaml` — `open-cluster-management-observability`
- `multiclusterobservability.yaml` — the MCO CR (Thanos sizing, storage config, addon spec, retention)

## What's imperative (one-time setup, kept out of Git)

Two secrets in `open-cluster-management-observability` that contain credentials and are created imperatively to avoid committing secret material:

### 1. `multiclusterhub-operator-pull-secret`

MCO needs the cluster pull-secret in its own namespace. Copy from `openshift-config`:

```bash
oc get secret -n openshift-config pull-secret -o yaml | \
  sed -e 's/namespace: openshift-config/namespace: open-cluster-management-observability/' \
      -e 's/name: pull-secret/name: multiclusterhub-operator-pull-secret/' \
      -e '/resourceVersion:/d' -e '/uid:/d' -e '/creationTimestamp:/d' | \
  oc apply -f -
```

### 2. `thanos-object-storage`

After copying and verifying the data, Thanos targets SeaweedFS in `obs-storage`. Sessions 07 and 14 established the historical observability storage and `thanos` bucket; the endpoint and Secret below describe the current migration contract:

```bash
AK=$(oc get secret -n obs-storage obs-s3-credentials -o jsonpath='{.data.AWS_ACCESS_KEY_ID}' | base64 -d)
SK=$(oc get secret -n obs-storage obs-s3-credentials -o jsonpath='{.data.AWS_SECRET_ACCESS_KEY}' | base64 -d)
cat <<EOF | oc apply -f -
apiVersion: v1
kind: Secret
metadata:
  name: thanos-object-storage
  namespace: open-cluster-management-observability
type: Opaque
stringData:
  thanos.yaml: |
    type: s3
    config:
      bucket: thanos
      endpoint: seaweedfs.obs-storage.svc.cluster.local:8333
      insecure: true
      access_key: $AK
      secret_key: $SK
EOF
unset AK SK
```

The target bucket must exist first. During controlled target setup, use the official AWS CLI image and project credentials from the Secret without placing values in the command line:

```bash
oc run -n obs-storage s3-bucket-init --rm --restart=Never -i --attach \
  --image=public.ecr.aws/aws-cli/aws-cli:2.34.0 \
  --overrides='{
    "spec": {
      "containers": [{
        "name": "s3-bucket-init",
        "image": "public.ecr.aws/aws-cli/aws-cli:2.34.0",
        "envFrom": [{"secretRef": {"name": "obs-s3-credentials"}}],
        "env": [
          {"name": "AWS_DEFAULT_REGION", "value": "us-east-1"},
          {"name": "AWS_EC2_METADATA_DISABLED", "value": "true"},
          {"name": "AWS_PAGER", "value": ""}
        ],
        "command": ["/bin/sh", "-ec"],
        "args": ["aws --endpoint-url http://seaweedfs:8333 s3api head-bucket --bucket thanos || aws --endpoint-url http://seaweedfs:8333 s3api create-bucket --bucket thanos"]
      }]
    }
  }'
```

## What MCO deploys

On the hub (`open-cluster-management-observability` namespace):

- `observability-thanos-receive-default-*` (3 replicas by default; tune via spec for SNO-equivalent sizing)
- `observability-thanos-store-memcached-*`
- `observability-thanos-query`
- `observability-thanos-query-frontend`
- `observability-thanos-compact`
- `observability-thanos-rule`
- `observability-alertmanager`
- `observability-observatorium-operator`
- `grafana-*`
- `rbac-query-proxy`

On each ACM-managed cluster (via the `observability-controller` addon): `metrics-collector` DaemonSet that reads local Prometheus (both `openshift-monitoring` and `openshift-user-workload-monitoring`) and remote_writes to hub Thanos Receiver.

## Retention (this deployment)

- `retentionResolutionRaw: 30d` — raw samples kept 30 days in ingesters.
- `retentionResolution5m: 60d` — 5-minute downsampled, 60 days.
- `retentionResolution1h: 90d` — 1-hour downsampled, 90 days.
- `retentionInLocal: 1d` — local PVC retention (ingester-side), 1 day.

All three downsamples use the S3 store for long-term retention. Preserve that data during migration to SeaweedFS; size capacity and retention for real workloads.

## Unified Grafana

MCO ships its own Grafana (branded as "ACM Grafana" or "Observatorium") reachable via the console's Observe → Virtual Machines/Observability menu, or via the `grafana-route` in `open-cluster-management-observability`. Dashboards include a `cluster` selector so the same dashboard renders per-cluster views of hub + companion.

Per ADR-022 we keep the Cluster Observability Operator (COO) UIPlugin for hub-local metrics drill-downs; MCO Grafana is the multi-cluster dashboard surface. Two panes of glass, different scopes, both sanctioned Red Hat patterns.

## Companion side

`infrastructure/gitops/apps/companion/user-workload-monitoring/` enables user-workload monitoring on companion so workload metrics (not just platform metrics) are scraped and made available to metrics-collector for remote_write.

## Verification

```bash
oc get mco observability -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
# → True

oc get managedclusteraddon observability-controller -n companion -o jsonpath='{.status.conditions[?(@.type=="Available")].status}'
# → True (metrics-collector running on companion)

oc exec -n open-cluster-management-observability deploy/observability-thanos-query -- \
  curl -sG 'http://localhost:10902/api/v1/query' --data-urlencode 'query=up{cluster="companion"}' | jq '.data.result | length'
# → >0 (hub Thanos has companion metrics)
```
