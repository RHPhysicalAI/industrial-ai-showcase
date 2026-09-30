# obstruction-detector-intel (GitOps)

Intel variant perception workload: YOLOv8m OpenVINO IR served by OpenVINO Model
Server under KServe, with a Kafka-driven detector consuming
`warehouse.cameras.aisle3` and emitting to `fleet.safety.alerts`.

Picked up automatically by the `workloads` ApplicationSet
(`infrastructure/gitops/clusters/hub/appsets/workloads.yaml`), which discovers
every directory under `infrastructure/gitops/apps/workloads/*` on `main`. No
per-app `Application` manifest is needed — **but note the appset syncs from
`main`, so nothing here is reconciled until merge.**

> **Status:** Task 4.1 was validated on 2026-09-29 and the recommendation is
> **NO-GO** for this detector as the warehouse obstruction path — see
> `docs/13-intel-task4-validation-report.md`. These manifests are retained
> because Task 4.2 reuses the serving and Kafka scaffolding.

## Prerequisite: the S3 credential secret

Everything in this directory is reconciled from git **except** the MinIO
credential, which is deliberately not committed. Create it before first sync,
or the predictor's storage-initializer will fail to pull the model.

```bash
oc create secret generic minio-s3-secret \
  -n intel-vla-training \
  --from-literal=AWS_ACCESS_KEY_ID='<access-key>' \
  --from-literal=AWS_SECRET_ACCESS_KEY='<secret-key>'

# KServe's pod mutator reads S3 settings from annotations on the SECRET.
# Putting them on the InferenceService or the ServiceAccount does nothing.
oc annotate secret minio-s3-secret -n intel-vla-training \
  serving.kserve.io/s3-endpoint=minio.mlflow.svc.cluster.local:9000 \
  serving.kserve.io/s3-usehttps=0 \
  serving.kserve.io/s3-verifyssl=0 \
  serving.kserve.io/s3-region=us-east-1
```

⚠️ The credential currently in the cluster is a **known placeholder pending
rotation**. Rotating it is an open action item.

## Gotchas worth knowing before you debug this

Each of these cost hours during Task 4.1:

- **`storageUri` must point at the parent prefix.** OVMS resolves the numbered
  version directory itself. Weights live at `s3://models/yolov8m/1/`, so the
  URI is `s3://models/yolov8m`. A wrong prefix surfaces as a *credentials*
  error, which sends you chasing the wrong problem — verify the object exists
  (`mc ls`) before touching credentials.
- **S3 annotations belong on the Secret**, bound via
  `spec.predictor.serviceAccountName`. Not on the InferenceService (silently
  ignored, then fails with an SSL error against a plaintext endpoint), and not
  via `spec.predictor.model.storageSecret` (not a valid field).
- **OVMS ports are inverted from the KServe default.** gRPC on 8080, REST on
  8081. The KServe-managed `yolov8-detector-predictor` Service maps port 80 to
  8080 and reconciles away hand edits, so REST clients use the separately-named
  `yolov8-detector-rest` Service defined in `yolov8-inference-service.yaml`.
- **The detector's probe timeouts are deliberately wide.** Tensor parsing blocks
  the asyncio event loop for seconds; at the default `timeoutSeconds: 1` the pod
  was liveness-killed roughly every 80s. Don't "fix" them back down without
  first moving parsing off the event loop.

## Validation

Reproduction procedure and measured results:
`docs/13-intel-task4-validation-report.md` §5. The probe script and its recorded
outputs live in `workloads/obstruction-detector-intel/validation/`.
