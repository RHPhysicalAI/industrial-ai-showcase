# ML pipeline validation

**Roadmap:** [Goal 7](../../roadmaps/ml-training.md) ·
[upstream-to-fork inventory](../../roadmaps/ml-training-inventory.md)

## What this step is

This is a fork-side validation layer around the existing upstream ML pipeline
under [`workloads/vla-training/`](../../workloads/vla-training/). It verifies
that the source, compiled artifact, Hub services, secret objects, and GPU
capacity agree before a pipeline run is submitted.

It is not a new training pipeline. The fork keeps the upstream training flow
and adds narrowly scoped artifact/serving-contract hardening around it.

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

The pipeline's default embodiment is `NEW_EMBODIMENT`, matching the bundled
`nvidia/PhysicalAI-Robotics-GR00T-Teleop-G1` modality definition. That dataset
uses a 43-DOF joint state/action schema and the `rs_view` video key. `UNITREE_G1`
is a different locomotion schema and must not be substituted without a matching
modality definition.

GR00T also loads the gated `nvidia/Cosmos-Reason2-2B` VLM backbone during
inference. Before running the canary, accept the model's terms while signed in
to the Hugging Face account that owns the token used by the Hub Secret:

<https://huggingface.co/nvidia/Cosmos-Reason2-2B>

Model-page approval and token authentication are separate requirements. A
valid token without account approval returns HTTP 403; an invalid token returns
HTTP 401. Keep the token in the local ignored environment/cluster Secret only;
never commit or print it.

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

The full training output, including optimizer and scheduler state for resume or
debugging, remains under `.../checkpoint`. It is intentionally not copied into
`.../model`: the earlier run uploaded a nested `checkpoint-10` tree and
training state into the serving prefix, which made the artifact unnecessarily
large and obscured the files that `Gr00tPolicy` loads. The fine-tuning step now
selects the highest numbered `checkpoint-*`, validates its configuration,
processor metadata, and weights, and uploads only that model directory to the
serving prefix.

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
Provide the image as an immutable `@sha256:` digest so a moving tag cannot
silently test an older image. `VLA_CANARY_ALLOW_TAG_IMAGE=true` is reserved for
an explicitly intentional diagnostic. The helper also refuses a GR00T artifact
unless its URI ends in `/model`, checks that an L40S node is registered, and
checks the required Secret keys without revealing their values.
`VLA_CANARY_USE_LIVE_IMAGE=true` is available only for an intentional baseline
comparison. The helper creates a uniquely named temporary
Deployment and Service, sets `VLA_MODE=groot`, checks `/healthz` and `/readyz`,
then sends one representative `/act` request through a local port-forward.
For the Teleop-G1 artifact, it sets `GROOT_VIDEO_KEY=rs_view`; the live
`REAL_G1` deployment retains its original `ego_view` default.
The canary's embodiment and video key are configurable with
`VLA_CANARY_EMBODIMENT_TAG` and `VLA_CANARY_VIDEO_KEY`, but the Teleop-G1
defaults should remain `NEW_EMBODIMENT` and `rs_view`. Its `/act` request has a
bounded timeout controlled by `VLA_CANARY_INFERENCE_TIMEOUT` (default 300
seconds).

The serving loader now uses an exact-prefix completion marker and checks for
model metadata plus weight files (or an ONNX file) before reusing a cache. A
partial or interrupted download is removed and retried automatically. This
replaces the old unsafe rule that any non-empty cache directory was complete;
manual deletion of stale cache directories is no longer part of the normal
train-to-canary workflow. Cleanup is scoped to the requested artifact, not the
PVC or other model caches.
The canary also sets the same writable `HF_HOME` used by the live deployment;
without it, Hugging Face can fall back to the unwritable `/.cache` path.
The canary injects the existing `robot-edge/hf-token` Secret because GR00T
loads the gated `nvidia/Cosmos-Reason2-2B` backbone on first inference. The
token must have access to that repository. For GR00T, a lightweight init
container checks the gated-model HTTP access before the GPU-serving container
starts, distinguishing invalid credentials (401) from missing model approval
(403) without printing the token. The final `/act` response is also checked
for the established seven-value JSON shape, finite numeric values, and trace
metadata. Resources are deleted automatically on exit. Use `--keep` only when
debugging.

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
It is a secondary diagnostic and does not replace the native GR00T canary.

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

The first fork-side end-to-end proof is complete: a bounded KFP run completed
training, export, validation, and registration, and the native GR00T canary
then passed `/healthz`, `/readyz`, and one `/act` inference request using the
versioned `.../model` artifact. This proves the train-to-artifact-to-inference
contract; it does not yet prove robot-control semantics or promotion to the
live deployment.

The next integration gate is the action-space contract. The trained Teleop-G1
policy is validated as a 43-DOF, 16-step action chunk before the server keeps
the existing seven-value HTTP response for compatibility. That seven-value
response is deliberately treated as a shape-preserving compatibility projection
only; a real mapping to the downstream robot-control command must be designed
and validated separately before promotion.

## Lessons now encoded in the fork

These are the concrete failures and fixes from the first end-to-end canary, so
a future run does not depend on shell patches or operator memory:

| Observation | Permanent guard/fix |
| --- | --- |
| A slim serving image failed with `No module named gr00t`. | Build the fork serving image with the CUDA base (`BASE_FLAVOR=cuda`) and use that explicit image for the canary; the helper refuses an implicit live-image fallback. |
| The first model download left configuration files but not all weights. | `s3_loader.py` validates metadata and weights, writes a completion marker only after a full download, and removes an exact-prefix partial cache before retrying. |
| An invalid or missing gated-model credential caused Cosmos loading to fail. | The Hub `hf-token` Secret remains an external prerequisite; its value is never committed or printed. The canary injects the existing Secret and the runtime reports the actual model-load error. |
| The Teleop-G1 model rejected the default `ego_view` key. | The training default and isolated canary use `NEW_EMBODIMENT` with `rs_view`; the live `REAL_G1` deployment keeps its existing contract. |
| The custom modality expects one video frame, while the built-in REAL_G1 path expects two. | `GR00TAdapter` chooses the observation horizon from the selected embodiment instead of duplicating frames for every model. |
| The pipeline previously hard-coded `NEW_EMBODIMENT` while its configuration default said `UNITREE_G1`. | Fine-tuning/export now use `VLA_EMBODIMENT_TAG`, and the pipeline default matches the Teleop-G1 modality. |
| Training state inflated the serving prefix and made its layout ambiguous. | The latest numeric checkpoint is validated and copied cleanly to `.../model`; resume/debug state stays under `.../checkpoint`. |
| Successful HTTP inference did not prove robot behavior. | The canary is explicitly an inference-contract gate. The existing public API remains 7 values; mapping the Teleop-G1 43-DOF action space to downstream robot controls is a separate integration gate. |
| The original model-registry client tried a newer API than the Hub exposes. | Keep `model-registry==0.3.14` pinned until the cluster registry is upgraded. |
| A 120Gi object-store claim reached the free-space threshold during checkpoint upload. | The fork uses a 200Gi MinIO claim and retains cleanup/retention as an operational follow-up rather than deleting unknown artifacts. |

The canary proves that a versioned trained artifact can be downloaded, loaded,
and queried by the original GR00T serving runtime. It does not claim that the
trained 43-DOF policy is already wired into the live 7-value Mission
Dispatcher/Drop Pallet control path.
