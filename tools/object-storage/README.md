# SeaweedFS object storage

The fork uses SeaweedFS's AWS S3-compatible endpoint for artifacts, datasets,
camera frames, and observability data. Validate storage independently of model
training and inference: the canary below needs **no GPU, model download, AWS VM,
or change to Isaac Sim/Cosmos**.

## What uses it

| Store namespace | Buckets / consumers | Endpoint | PVC requested in Git |
| --- | --- | --- | --- |
| `mlflow` | `mlflow-artifacts` for MLflow; `vla-training` for DSPA/KFP datasets, checkpoints, models and serving canaries | `http://seaweedfs.mlflow.svc.cluster.local:8333` | 200Gi |
| `warehouse-data` | `warehouse-camera-library` for image staging | `http://seaweedfs.warehouse-data.svc.cluster.local:8333` | 5Gi |
| `obs-storage` | `loki-logs` and `thanos` | `http://seaweedfs.obs-storage.svc.cluster.local:8333` | 100Gi |

The [shared Kustomize base](../../infrastructure/gitops/components/seaweedfs/)
runs `docker.io/chrislusf/seaweedfs:4.48` with `weed mini`. Master, volume data,
and filer metadata live on the **new** `seaweedfs-data` PVC. This single-instance
demo topology is not a highly available storage service. Consumer overlays set
capacity and credentials; override capacity to fit actual source data plus headroom.
Do not shrink an existing larger claim to the repository default.

Only the authenticated S3 port is exposed. A NetworkPolicy blocks external access
to the raw filer, master, and volume APIs. Containers run under OpenShift's
`restricted-v2` SCC with an assigned non-root UID; no privileged SCC is needed.
The endpoint is internal HTTP. External clients need an explicitly configured TLS
endpoint or an authenticated tunnel; no public Route is created by default.

## Run the CPU-only canary

Prerequisites: local Python 3, `oc`, and a cluster login with permission to create
a namespace, Secret, Deployment, Service, NetworkPolicy, PVC, and client Pod.
The cluster needs a default StorageClass and access to the pinned images.

```bash
oc whoami
bash tools/object-storage/canary.sh --check-persistence
oc -n showcase-storage-canary get pods,pvc,svc
```

Use `--context CONTEXT` to select a kubeconfig context, or `--storage-class CLASS`
for a new sandbox without a default StorageClass. The helper generates random
credentials in memory and passes them to an OpenShift Secret. Credentials do not
enter Git, command-line arguments, or test output. It refuses to take over an
unrelated namespace. No package installation occurs inside the client Pod.
On reruns, retained resources must match the current shared base; otherwise the
canary stops before testing. Reconcile that owned sandbox deliberately or choose
a new `--namespace`. This prevents a passing result against an outdated deployment.
Interrupts and termination signals trigger best-effort cleanup; forced kills or
lost cluster access may still leave the uniquely named test resources for inspection.

The official `public.ecr.aws/aws-cli/aws-cli:2.34.0` client exercises the API:

- Signed bucket creation, discovery, and listing.
- Upload/download of a tiny CSV dataset with byte/hash verification.
- Object listing with pagination, metadata lookup, copy, and ranged download.
- A small multipart upload, completion, and download, plus aborting an incomplete upload.
- Rejection of unsigned requests and invalid credentials.
- With `--check-persistence`, data verification after restarting **only the owned
  SeaweedFS sandbox Deployment**.
- Cleanup of the uniquely named test bucket, objects, upload sessions, and client Pod.

The sandbox server and 5Gi PVC remain for inspection. See [validation results](VALIDATION.md)
for the recorded run and its limits. To remove the sandbox after inspection:

```bash
# Deletes only this sandbox, including its test-only PVC and generated credentials.
oc delete namespace showcase-storage-canary
```

To test an existing endpoint, put the corresponding AWS credentials in a Secret
in the client namespace, then run:

```bash
bash tools/object-storage/canary.sh --existing \
  --namespace vla-training --secret s3-credentials \
  --endpoint http://seaweedfs.mlflow.svc.cluster.local:8333
```

Existing-endpoint mode creates its own client Pod and disposable bucket. It never
deploys or restarts the storage server. Do not combine it with `--check-persistence`.

## RHOAI connection contract

RHOAI supports configurable S3-compatible object stores; SeaweedFS is accessed
through that interface. This is API compatibility, not a claim of Red Hat vendor
certification. See [Red Hat's S3 connection documentation](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_self-managed/2.16/html/working_on_data_science_projects/using-connections_projects).

| Setting | Value for the training store |
| --- | --- |
| Workbench/SDK endpoint (`AWS_S3_ENDPOINT` or `S3_ENDPOINT`) | `http://seaweedfs.mlflow.svc.cluster.local:8333` |
| DSPA externalStorage host / port / scheme | `seaweedfs.mlflow.svc.cluster.local` / `8333` / `http` |
| Region | `us-east-1` |
| Bucket | `vla-training` |
| Credential Secret in `vla-training` | `s3-credentials` |
| Secret keys | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` |
| SDK requests | Signature V4, path-style bucket addressing |
| MLflow artifact endpoint | `MLFLOW_S3_ENDPOINT_URL` |

The [DSPA manifest](../../infrastructure/gitops/apps/platform/dspa/dspa.yaml),
KFP source and compiled YAML, MLflow, VLA serving manifests, and serving-canary
helpers use this contract. Recompile/re-import pipeline versions after changing
the endpoint: previously uploaded KFP definitions and existing serving images do
not change when local source files change.

Vault remains the credential authority. The `mlflow/s3` KV path supplies
`mlflow-s3-credentials`, training `s3-credentials`, and serving `storage-config`.
Observability uses `obs/s3`; camera storage uses `warehouse/s3`. Seed the camera
keys out of band before its first sync. Server credential updates require a
controlled restart and a repeat of the signed/unsigned canary tests.

## Deploy and migrate existing data

The validation sandbox is separate from the live demo stores. An existing S3
store's PVC cannot be mounted as SeaweedFS data: its filesystem layout is different.
Use the S3 API to copy objects, preserving bucket names and keys so registered
`s3://bucket/prefix` artifact URIs remain valid.

1. Inventory the source buckets, object counts/bytes, versioning, policies,
   retention, and consumers. Confirm ownership on shared clusters. Pause relevant
   training jobs and other writers for the final copy; no GPU validation is needed.
2. Protect the old PVCs from Argo pruning/deletion before changing GitOps resources.
   Take a backup/snapshot and disable automatic pruning for the affected application
   during cutover. Keep the source deployment, endpoint, secrets, and volume available
   until the copy and consumer checks have passed.
3. Deploy the new SeaweedFS resources with a **separate** PVC and the appropriate
   Vault Secret. Stage storage separately before syncing consumer endpoint changes.
   Fresh deployments use the three consumer kustomizations; their bounded AWS CLI
   bucket Jobs are Sync hooks at wave 1, before dependent DSPA/MLflow resources.
4. Use a trusted S3 migration client with distinct source/target endpoints. Copy
   only the agreed buckets. Verify the complete object inventory, byte counts, and
   content checksums; multipart ETags are not portable content hashes. A basic
   latest-object copy does not migrate old versions, bucket policies, or retention
   rules; handle those explicitly if present. Do not use a destructive mirror option.
5. Run the canary against the new endpoint from the consumer namespace. Update
   GitOps endpoints/Secret references and recompile the KFP definition. Loki's
   Vault projection supplies the new endpoint; update the imperative Thanos
   `thanos-object-storage` Secret using its [runbook](../../infrastructure/gitops/apps/hub-acm/observability/README.md).
6. Confirm DSPA `ObjectStoreAvailable=True`, MLflow artifact access, and the
   relevant CPU-only consumers. The storage canary alone does not certify all
   historical data, Loki/Thanos behavior, or a full training/inference cycle.
7. Retire the exact old deployment/service/secrets/PVC only after ownership,
   migration verification, backup retention, and deletion are explicitly agreed.
   Rollback before new writes means restoring the old endpoints. After new writes,
   reconcile the data delta before switching back.

The VM continues loading locally staged model files. The
[model transfer helper](../cloud-vm-setup/transfer-model.sh) now uses the standard
AWS S3 client in a temporary Pod, reads bounded byte ranges through `oc exec`,
verifies each range, and stages via the workstation before SCP to the VM.

## Offline deployment

Mirror the pinned SeaweedFS and AWS CLI images to the site's registry and override
the Kustomize image references. Override the helper client image as documented by
its `--help` if using a mirrored registry. No server runtime package downloads or
GPU images are needed. See the upstream [SeaweedFS mini guide](https://github.com/seaweedfs/seaweedfs/wiki/Quick-Start-with-weed-mini)
and [S3 credentials guide](https://github.com/seaweedfs/seaweedfs/wiki/S3-Credentials).
