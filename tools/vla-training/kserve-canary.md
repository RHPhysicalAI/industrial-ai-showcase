# Isolated KServe canary

This canary validates the legacy document's KServe `InferenceService` serving
contract without changing the working demo path.

It creates a temporary `vla-kserve-canary` namespace, copies the existing
object-store and approved Hugging Face Secret objects without printing their
values, preserves the legacy MinIO endpoint through KServe storage annotations,
and attaches a temporary copy of the existing `robot-edge` image-pull Secret,
and deploys a custom KServe predictor using the fork-built
`openvla-server` image. KServe's custom-predictor storage initializer downloads
the supplied native GR00T `.../model` artifact to `/mnt/models`. The server's
KServe v1 adapter translates `/v1/models/<name>:predict` to the unchanged
`/act` implementation and verifies the existing seven-value response shape.

This is deliberately not part of the live GitOps kustomization yet. It does
not change the AWS VM, Companion SNO, Hub `robot-edge/openvla-server`, Cosmos,
Isaac Sim, or Argo applications. Resources are deleted automatically unless
`--keep` is supplied.

The canary needs a free NVIDIA L40S GPU. Keep the live Hub VLA Deployment at
zero replicas while running it; do not take a GPU from Cosmos or Isaac Sim
without an approved GPU window.

```bash
source tools/demo-redhat-sno/.env

VLA_OC_CONTEXT="$HUB_CONTEXT" \
bash tools/vla-training/kserve-canary.sh \
  --artifact-uri s3://vla-training/<run-prefix>/<version>/model \
  --image <fork-image>@sha256:<immutable-digest>
```

The endpoint defaults to the repository's existing `http://minio.mlflow.svc:9000`
contract. Override it with `VLA_KSERVE_S3_ENDPOINT` only when the target Hub
uses a different object-store endpoint.

Success requires:

- the KServe `InferenceService` becomes Ready;
- `GET /v1/models/<name>` reports `ready: true`;
- `POST /v1/models/<name>:predict` returns one prediction;
- the prediction preserves the existing seven-value action contract and trace ID.

The canary is an isolated artifact-to-KServe-inference proof. It is not yet a
promotion, Argo/HIL change, AWS VM update, or Mission Dispatcher endpoint
change.
