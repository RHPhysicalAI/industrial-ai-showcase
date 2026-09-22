# Goal 7 — Upstream-to-Fork ML Pipeline Inventory

Status: 🔄 Planning

This document is the controlled inventory for the ML/training work. It maps
the upstream implementation to this fork before any training or serving change
is applied. The purpose is to preserve upstream behavior, isolate fork-specific
deployment configuration, and avoid spending GPU time on an unverified contract.

## Source repositories

| Role | URL | Working rule |
| --- | --- | --- |
| Upstream reference | <https://github.com/RHPhysicalAI/industrial-ai-showcase> | Read and compare; do not push changes here. |
| Working fork | <https://github.com/rhkp/industrial-ai-showcase> | All changes and validation commits land here. |
| Upstream main tree | <https://github.com/RHPhysicalAI/industrial-ai-showcase/tree/main> | Source-of-truth reference for intended implementation. |
| Fork main tree | <https://github.com/rhkp/industrial-ai-showcase/tree/main> | Deployment-ready version for our topology. |

Comparison snapshot: the fork `main` contains upstream `main` plus six fork
commits. There are currently no upstream-only commits missing from the fork.
This is a planning snapshot and must be refreshed before implementation starts.

## Change-control rules

1. Preserve upstream training logic unless a reproducible test proves it cannot
   run in the selected Hub environment.
2. Put topology-specific changes in GitOps overlays, environment configuration,
   or narrowly scoped adapters; do not rewrite the upstream pipeline to fit
   the current demo.
3. Keep the working Mission Dispatch and Drop Pallet baseline unchanged while
   training is validated.
4. Treat the cloud VLA VM as the current serving baseline. A trained-model
   canary must use an isolated target before it can replace that VM path.
5. Record secret names and required permissions, never secret values, tokens,
   keys, certificates, or private endpoints.
6. Every stage needs a read-only prerequisite check and a concrete artifact or
   log that proves it succeeded before the next GPU-consuming stage begins.

## Upstream-to-fork source map

| Workstream | Upstream source | Fork path/status | Important contract/config | First action |
| --- | --- | --- | --- | --- |
| Pipeline definition | [pipeline.py](https://github.com/RHPhysicalAI/industrial-ai-showcase/blob/main/workloads/vla-training/src/vla_training/pipeline.py) | Same path; currently aligned | Pipeline name `vla-finetune`; default base model `nvidia/GR00T-N1.7-3B`; dataset `nvidia/PhysicalAI-Robotics-GR00T-Teleop-G1`; bucket `vla-training`; prefix `vla-finetune`; model `g1-vla-finetune`; version `v1` | Compile and inspect parameters without running GPU work. |
| Pipeline artifact | [vla_finetune_pipeline.yaml](https://github.com/RHPhysicalAI/industrial-ai-showcase/blob/main/workloads/vla-training/vla_finetune_pipeline.yaml) | Same path; currently aligned | Four stages: data preparation → fine-tune/export → model registration → ONNX validation. Uses in-cluster image `image-registry.openshift-image-registry.svc:5000/vla-training/vla-training:latest` | Compare compiled YAML with source and verify image availability. |
| Training image | [Containerfile](https://github.com/RHPhysicalAI/industrial-ai-showcase/blob/main/workloads/vla-training/container/Containerfile) | Same path; currently aligned | Clones `https://github.com/NVIDIA/Isaac-GR00T.git`; installs GPU ONNX Runtime from the documented package index | Verify build network access and package compatibility before building. |
| Runtime configuration | [config.py](https://github.com/RHPhysicalAI/industrial-ai-showcase/blob/main/workloads/vla-training/src/vla_training/config.py) and [constants.py](https://github.com/RHPhysicalAI/industrial-ai-showcase/blob/main/workloads/vla-training/src/vla_training/constants.py) | Same paths; currently aligned | MinIO endpoint `http://minio.mlflow.svc:9000`; MLflow endpoint `https://mlflow.redhat-ods-applications.svc:8443`; Model Registry endpoint `http://wbc-model-registry.rhoai-model-registries.svc:8080` | Verify these services resolve and authenticate from `vla-training`. |
| Data preparation | [data_prep.py](https://github.com/RHPhysicalAI/industrial-ai-showcase/blob/main/workloads/vla-training/src/vla_training/data_prep.py) | Same path; currently aligned | Downloads/caches the base model and dataset, then writes to S3-compatible storage under configured prefixes | Run only after storage and HF access checks pass. |
| Fine-tuning/export | [fine_tune.py](https://github.com/RHPhysicalAI/industrial-ai-showcase/blob/main/workloads/vla-training/src/vla_training/fine_tune.py) | Fork adds serving-artifact hardening | Produces full resume state under `checkpoint/`, a validated clean GR00T serving directory under `model/`, and ONNX under `onnx/`; GPU and step count must be explicit for a smoke run | Start with a short, bounded smoke run and verify the model prefix contains weights at its root. |
| ONNX validation | [validate_onnx.py](https://github.com/RHPhysicalAI/industrial-ai-showcase/blob/main/workloads/vla-training/src/vla_training/validate_onnx.py) | Same path; currently aligned | Reads the generated ONNX artifact from S3-compatible storage and validates model inputs/outputs | Make this the first post-training acceptance gate. |
| Model registration | [register_model.py](https://github.com/RHPhysicalAI/industrial-ai-showcase/blob/main/workloads/vla-training/src/vla_training/register_model.py) | Same path; currently aligned | Registers `g1-vla-finetune` with a version and URI in the RHOAI Model Registry; records lineage metadata | Verify registry API and database readiness before the run. |
| Promotion tooling | [promote.py](https://github.com/RHPhysicalAI/industrial-ai-showcase/blob/main/workloads/vla-training/src/vla_training/promote.py) | Same path; contract not yet approved | Existing code assumes an older promotion/serving shape; it must not be run blindly | Reconcile it with the active Deployment-based serving manifests. |
| DSPA/KFP platform | [platform/dspa](https://github.com/RHPhysicalAI/industrial-ai-showcase/tree/main/infrastructure/gitops/apps/platform/dspa) | Same structure; fork BuildConfig source points to `https://github.com/rhkp/industrial-ai-showcase.git` | Namespace `vla-training`; pipeline image `vla-training:latest`; secrets `git-source-secret`, `minio-credentials`, and `hf-credentials` | Verify DSPA, BuildConfig, image, service account, and secret projections. |
| MLflow/MinIO | [platform/mlflow](https://github.com/RHPhysicalAI/industrial-ai-showcase/tree/main/infrastructure/gitops/apps/platform/mlflow) | Same path; currently aligned | Artifact destination `s3://mlflow-artifacts/`; MinIO service is in namespace `mlflow`; credentials are Vault-sourced | Verify pods, bucket initialization, S3 credentials, and tracking health. |
| Model Registry | [platform/model-registry](https://github.com/RHPhysicalAI/industrial-ai-showcase/tree/main/infrastructure/gitops/apps/platform/model-registry) | Same path; currently aligned | Registry `wbc-model-registry` in `rhoai-model-registries`; database secret is externalized | Verify service, database, and registry API health. |
| Serving manifests | [factory-b workloads](https://github.com/RHPhysicalAI/industrial-ai-showcase/tree/main/infrastructure/gitops/apps/workloads/factory-b) and [robot-edge workloads](https://github.com/RHPhysicalAI/industrial-ai-showcase/tree/main/infrastructure/gitops/apps/workloads/robot-edge) | Same paths; fork adds isolated canary helper | Current manifests use `openvla-server` Deployments, model cache PVCs, `policy-version`, and `s3://vla-training/vla-finetune/...` model paths | Select an isolated canary target; do not alter the live Cloud VLA VM. |
| Deployment-mode contract | [vla-model-deployment-modes.md](https://github.com/RHPhysicalAI/industrial-ai-showcase/blob/main/docs/vla-model-deployment-modes.md) | Same path; documentation needs reconciliation | Describes KServe `InferenceService` examples, while active manifests use `openvla-server` Deployments | Update documentation only after the serving target is selected and verified. |

## External URLs and access contracts

These are implementation dependencies, not secrets:

| Dependency | URL or identifier | Required access |
| --- | --- | --- |
| Training base model | `nvidia/GR00T-N1.7-3B` | Hugging Face read access through the `hf-credentials` Secret. |
| Training dataset | `nvidia/PhysicalAI-Robotics-GR00T-Teleop-G1` | Hugging Face read access through the `hf-credentials` Secret. |
| GR00T source | <https://github.com/NVIDIA/Isaac-GR00T.git> | Build-time Git access. |
| ONNX Runtime package index | <https://aiinfra.pkgs.visualstudio.com/PublicPackages/_packaging/onnxruntime-cuda-12/pypi/simple/> | Build-time package access. |
| MinIO API | `http://minio.mlflow.svc:9000` | `minio-credentials`; bucket `vla-training`. |
| MLflow tracking | `https://mlflow.redhat-ods-applications.svc:8443` | Tracking access from pipeline components. |
| Model Registry | `http://wbc-model-registry.rhoai-model-registries.svc:8080` | Registry API access and database readiness. |
| Git source for DSPA build | Upstream: `https://github.com/RHPhysicalAI/industrial-ai-showcase.git`; fork: `https://github.com/rhkp/industrial-ai-showcase.git` | `git-source-secret`; fork is the intended build source. |

## Execution gates

### Gate 0 — Snapshot and parity

- Refresh `upstream/main` and `origin/main` references.
- Re-run the source map and record any upstream-only changes.
- Confirm the working tree changes are understood before any training change.

### Gate 1 — Read-only Hub readiness

- DSPA/KFP API and dashboard are available.
- `vla-training` namespace and pipeline image are ready.
- MinIO, MLflow, and Model Registry are healthy.
- Required Secret names exist without printing values.
- One intended L40S GPU is available without evicting Isaac Sim or Cosmos.

### Gate 2 — Compile and submit without GPU execution

- Compile the pipeline from source.
- Compare the compiled YAML with the committed artifact.
- Upload or register the pipeline without starting a training run.
- Confirm the run parameters are explicit: model, dataset, bucket, prefix,
  version, step count, and GPU selector.

### Gate 3 — Bounded smoke run

- Use a small step count and a dedicated model version such as `smoke-<date>`.
- Confirm each component starts, reaches its intended endpoint, and writes
  artifacts under a unique prefix.
- Stop and diagnose on the first failed component; do not repeatedly retry a
  GPU-consuming run.

### Gate 4 — Artifact and lineage acceptance

- Verify base model, dataset/cache, checkpoint, and ONNX objects in MinIO.
- Verify ONNX validation output.
- Verify MLflow metrics and Model Registry version/URI/lineage.
- Record run ID, artifact URI, model version, and validation result without
  recording credentials.

### Gate 5 — Isolated canary

- Deploy the trained artifact to an inactive or isolated Hub serving target.
- Verify readiness and one representative action request.
- Keep the Cloud VLA VM and hosted Mission Dispatch/Drop Pallet path intact.
- Only after acceptance, decide whether promotion automation needs changes.

### Gate 6 — Repeatability and action-space review

- Repeat the canary using only the versioned `.../model` URI and the fork-built
  CUDA image; no manual cache cleanup or in-place pod patch should be needed.
- Capture the canary's model version, readiness response, and `/act` result.
- Before promoting beyond inference validation, reconcile the Teleop-G1
  43-DOF action space with the existing 7-value robot-edge API. Do not claim
  robot-control correctness from an HTTP 200 alone.
- Current audit result: the dispatcher validates and records the existing
  seven-value response, while Isaac Sim consumes `fleet.telemetry` poses from
  the waypoint planner. No repository-defined manipulation command schema or
  action consumer exists yet, so promotion to actuation is intentionally
  blocked pending that design decision.

## Explicit non-goals for the first training run

- No replacement of the Cloud VLA VM.
- No change to the working Companion SNO mission path.
- No change to the Hub Kafka topology.
- No change to upstream source behavior solely to match the current demo.
- No full production-duration training run before the bounded smoke run passes.
- No secret values, tokens, keys, certificates, or private IP addresses in Git.

## Evidence to capture

- Upstream/fork commit SHAs and comparison date.
- Read-only prerequisite output.
- Pipeline compile hash or artifact name.
- KFP run ID and component status.
- GPU node/product used for the run.
- MinIO artifact prefixes and object existence checks.
- ONNX validation result.
- MLflow run ID and Model Registry version.
- Canary endpoint readiness and representative response.
