# Goal 7 — ML and Training Model Lifecycle

Status: ⏭️ Next

## Objective

Enable the Hub cluster to run the VLA training pipeline, store and register a
versioned model, and prove that the resulting artifact can be consumed by a
serving deployment without disrupting the working hosted demo.

Before any implementation or GPU-consuming run, use the companion
[upstream-to-fork ML pipeline inventory](ml-training-inventory.md). It records
the source URLs, fork paths, runtime configuration contracts, access
dependencies, and validation gates for this goal.

The fork-side [ML pipeline validation step](../tools/vla-training/README.md)
exists to catch configuration and infrastructure failures before consuming GPU
time. It is read-only and does not alter the upstream training implementation.

## Scope boundary

The current Mission Dispatch and Drop Pallet demo remains the baseline. The
cloud VM VLA service stays in place while this work proceeds. Training and
model promotion are a separate Hub workstream until a canary deployment has
been validated.

## What the repository already contains

- A KFP v2 pipeline under `workloads/vla-training/`:
  data preparation → GR00T fine-tuning → ONNX validation → model registration.
- The fine-tuning step preserves a deployable GR00T model directory at a
  versioned `.../model` URI and keeps ONNX as a secondary validation artifact.
- A compiled pipeline YAML at
  `workloads/vla-training/vla_finetune_pipeline.yaml`.
- GitOps resources for DSPA, the `vla-training` namespace, MinIO access,
  Hugging Face credentials, and the pipeline image build.
- MLflow and RHOAI Model Registry integration code.
- Hub serving manifests based on `openvla-server` Deployments.

## Known contract gaps to resolve first

1. The deployment-mode document refers to KServe `InferenceService` manifests
   that are not present in the current tree. The active manifests use
   `openvla-server` Deployments.
2. The deployed `robot-edge/openvla-server` uses `VLA_MODE=groot` and expects
   a GR00T model directory, while the earlier pipeline only registered its
   ONNX bundle. The pipeline now emits both, but staging consumption is still
   to be proven.
3. The current serving and promotion code must agree on whether the trained
   model is consumed by the Hub deployment or the separate cloud VM service.
4. `promote.py` assumes an older overlay and InferenceService structure and
   must be treated as a candidate for alignment, not used blindly.
5. GPU scheduling must explicitly target the intended L40S pool for training;
   the compiled pipeline currently leaves the GPU node selector implicit.

## Next-week work plan

### 1. Freeze the source and fork map

- Refresh the upstream comparison and record any upstream-only changes.
- Confirm that all training-related paths are aligned before changing them.
- Separate fork-specific topology/configuration work from upstream pipeline
  logic.
- Preserve the current Mission Dispatch and Drop Pallet baseline as a control.

### 2. Reconcile the deployment contract

- Update `docs/vla-model-deployment-modes.md` to describe the current
  Deployment-based serving path accurately.
- Choose one versioned model URI convention and apply it consistently to the
  pipeline, policy ConfigMaps, serving deployment, and promotion tooling.
- Decide whether the first trained-model canary targets the Hub deployment or
  the cloud VM; do not change the live demo until this is explicit.

### 3. Validate Hub prerequisites

- Confirm DSPA/Kubeflow Pipelines is available and accepting runs.
- Confirm the `vla-training` namespace and pipeline image build are healthy.
- Confirm MinIO bucket access, MLflow tracking, and Model Registry access.
- Confirm Vault-sourced Hugging Face and object-storage credentials exist.
- Confirm an available L40S GPU and a non-conflicting training window.

### 4. Run the pipeline incrementally

- Compile and upload the pipeline.
- Run data preparation first and verify model/dataset objects in MinIO.
- Run a short fine-tuning smoke test with a small step count.
- Run ONNX validation.
- Register the versioned GR00T model URI with lineage metadata; retain the
  ONNX URI as a secondary artifact reference.
- Only after the smoke test succeeds, schedule a longer training run.

### 5. Prove a safe canary deployment

- Deploy the registered `.../model` artifact to an isolated staging copy of
  the original `openvla-server` with `VLA_MODE=groot`.
- Verify model download, readiness, and a representative action request.
- Confirm the existing Mission Dispatch and Drop Pallet path is unchanged.
- Record the model version, artifact URI, registry ID, and validation result.

### 6. Finish promotion automation

- Align `workloads/vla-training/src/vla_training/promote.py` with the actual
  serving manifests.
- Generate a GitOps change that updates only the intended model version.
- Validate Argo sync and rollback using a canary target first.

## Definition of done

- A real KFP run completes through registration.
- Artifacts exist at a versioned MinIO URI.
- Metrics and lineage are visible in MLflow/Model Registry.
- A serving deployment can load and answer with the trained artifact.
- Promotion changes are GitOps-managed and reversible.
- The existing hosted Mission Dispatch and Drop Pallet demo remains healthy.

## References

- [`docs/vla-model-deployment-modes.md`](../docs/vla-model-deployment-modes.md)
- [`roadmaps/ml-training-inventory.md`](ml-training-inventory.md)
- [`docs/plans/phase-2-plan.md`](../docs/plans/phase-2-plan.md)
- [`docs/08-gpu-resource-planning.md`](../docs/08-gpu-resource-planning.md)
- [`workloads/vla-training/`](../workloads/vla-training/)
- [`infrastructure/gitops/apps/platform/dspa/`](../infrastructure/gitops/apps/platform/dspa/)
