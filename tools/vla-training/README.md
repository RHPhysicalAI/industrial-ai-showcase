# ML pipeline validation

**Roadmap:** [Goal 7](../../roadmaps/ml-training.md) ·
[upstream-to-fork inventory](../../roadmaps/ml-training-inventory.md)

## What this step is

This is a fork-side validation layer around the existing upstream ML pipeline
under [`workloads/vla-training/`](../../workloads/vla-training/). It verifies
that the source, compiled artifact, Hub services, secret objects, and GPU
capacity agree before a pipeline run is submitted.

It is not a new training pipeline and it does not change the upstream training
logic.

## Why it matters

A training run consumes scarce GPU time and can create large intermediate
artifacts. A missing compiler, stale BuildConfig source, unavailable DSPA,
missing object-store credentials, or absent GPU can fail the run before useful
training starts. This validation step catches those conditions earlier and
provides a repeatable record of what was checked.

The MLflow MinIO claim is sized at **200Gi** for the training workflow. A run
temporarily retains the downloaded base model and dataset, fine-tuning
checkpoints, the native GR00T model used by serving, and the secondary ONNX
export. The smaller 120Gi claim reached MinIO's minimum-free-space threshold
while uploading checkpoints, even though training and export had succeeded.

The training image pins `model-registry==0.3.14` because this Hub currently
serves the Model Registry `v1alpha3` API. Do not broaden this dependency range
without first upgrading the cluster-side registry: newer clients may call the
`v1` API and fail registration after the GPU work has already completed.

It also protects the working hosted demo: validation is read-only and does not
submit runs, scale workloads, modify secrets, sync GitOps, or replace the Cloud
VLA VM.

## Run the preflight scope

From the repository root:

```bash
python3 tools/preflight/check.py \
  --scope ml-training \
  --explain \
  --color always
```

The command uses the current `oc` context unless `--hub-kubeconfig` is passed.
It never prints secret values; it checks only the presence of required Secret
objects.

## Compile-only validation

The KFP compiler is an optional dependency of the training package. Use an
isolated environment for it rather than modifying the workstation's system
Python:

```bash
VLA_VENV_DIR="$(mktemp -d)/venv"
python3 -m venv "$VLA_VENV_DIR"
source "$VLA_VENV_DIR/bin/activate"
python -m pip install --upgrade pip
python -m pip install 'kfp>=2.14.3,<3.0' 'kfp-kubernetes>=2.14.3,<3.0'
python workloads/vla-training/src/vla_training/pipeline.py /tmp/vla_finetune_pipeline.yaml
deactivate
```

Or use the non-destructive wrapper:

```bash
VLA_PIPELINE_PYTHON=python tools/vla-training/compile-check.sh
```

The output is temporary by design. Review it against the committed
`workloads/vla-training/vla_finetune_pipeline.yaml` before replacing anything.
Do not submit the compiled pipeline until the roadmap gates have passed.

## Output contract for the deployed runtime

The deployed `robot-edge/openvla-server` uses `VLA_MODE=groot` and the
original `GR00TAdapter`. The smoke pipeline now preserves the fine-tuned
GR00T model directory in its native format at:

```text
s3://<bucket>/<prefix>/model
```

That is the deployable artifact. The pipeline also produces the secondary
ONNX export at:

```text
s3://<bucket>/<prefix>/onnx
```

The ONNX export remains useful for component-level validation, but it is not
the artifact consumed by the deployed GR00T serving contract. A future
staging validation should point the original runtime at the versioned
`.../model` URI with `VLA_MODE=groot` and issue the existing `/act` request.

## Serving canary

The fork includes a temporary canary for the original `openvla-server`
deployment contract. It uses `VLA_MODE=groot` by default and expects the
versioned native GR00T model directory:

```text
s3://<bucket>/<prefix>/model
```

Run it only during an approved GPU window, after confirming the live
`robot-edge/openvla-server` deployment is stopped:

```bash
bash tools/vla-training/canary-check.sh \
  --artifact-uri s3://vla-training/vla-finetune-smoke-20260921/model
```

The helper uses the fork-built serving image, storage configuration, model-cache
PVC, and L40S scheduling conventions. Set `VLA_CANARY_IMAGE` to the image built
from this checkout; it refuses to silently fall back to the live upstream image.
`VLA_CANARY_USE_LIVE_IMAGE=true` is available only for an intentional baseline
comparison. The helper creates a uniquely named temporary
Deployment and Service, sets `VLA_MODE=groot`, checks `/healthz` and `/readyz`,
then sends one representative `/act` request through a local port-forward.
For the Teleop-G1 artifact, it sets `GROOT_VIDEO_KEY=rs_view`; the live
`REAL_G1` deployment retains its original `ego_view` default.
Set `VLA_CANARY_MODEL_CACHE_DIR` to a new directory under the mounted cache PVC
when validating a changed artifact or recovering from an interrupted download;
the serving loader treats any non-empty cache directory as complete.
The canary also sets the same writable `HF_HOME` used by the live deployment;
without it, Hugging Face can fall back to the unwritable `/.cache` path.
The canary injects the existing `robot-edge/hf-token` Secret because GR00T
loads the gated `nvidia/Cosmos-Reason2-2B` backbone on first inference. The
token must have access to that repository. Resources are deleted automatically
on exit. Use `--keep` only when debugging.

The ONNX bundle remains a secondary TensorRT/component artifact. The optional
legacy adapter diagnostic can still be run explicitly:

```bash
bash tools/vla-training/canary-check.sh \
  --mode onnx \
  --artifact-uri s3://vla-training/vla-finetune-smoke-20260921/onnx
```

The ONNX diagnostic is not the production acceptance gate: GR00T's exported
BF16 ONNX bundle is intended for its TensorRT path, while the generic legacy
ONNX adapter expects FP32 inputs.
is necessary; it leaves the canary resources in `robot-edge` for inspection.

This is a validation aid, not promotion. It does not change the live Mission
Dispatch / Drop Pallet deployment or update GitOps.
The helper refuses to run if the live `openvla-server` has replicas, required
resource objects are missing, or its own canary name is already present.

## What success means

For the smoke pipeline, success means a bounded run completes training,
preserves the versioned GR00T model directory, exports the secondary ONNX
bundle, validates the ONNX components, and registers the GR00T model URI.
Serving acceptance is a separate staging gate using the original GR00T
runtime.
