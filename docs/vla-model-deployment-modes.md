# VLA Model Deployment Modes

This project was developed with assistance from AI tools.

> Storage update (2026-09-29): SeaweedFS passed [isolated S3 validation](../tools/object-storage/VALIDATION.md) in `showcase-storage-canary`, including access from `vla-training`. Live data/consumer cutover remains pending. This document retains the earlier serving-mode design, not evidence of a full serving deployment on SeaweedFS. Use the [object-storage copy/cutover guide](../tools/object-storage/README.md) and [native GR00T canary](../tools/vla-training/kserve-canary.md) for current validation. Paths under `s3://mlflow/models/...` below are historical examples; use the artifact URI actually recorded by your training run, normally under `s3://vla-training/.../model`.

## Overview

The VLA (Vision-Language-Action) models used by factory InferenceServices can operate in two modes:

1. **Showcase Mode** (default) - Fast startup, no GPU training required
2. **Production Mode** - Full training pipeline with MLflow model registry

## Current Configuration: Showcase Mode

The InferenceServices in `factory-b` and `robot-edge` are configured to use **Hugging Face placeholder models** for instant startup:

```yaml
storageUri: hf://meta-llama/Llama-3.2-3B-Instruct
```

**Why:**
- Training the GR00T VLA model takes 60-90 minutes on L40S GPUs
- Not all demo environments have sufficient GPU bandwidth for training
- Showcase needs to deploy quickly for sales/partner demos

**Tradeoff:**
- Not showing the actual fine-tuned VLA model
- Still demonstrates the full HIL workflow (approve → PR → deploy → version update)

## Production Mode Architecture

In a real deployment, the flow is:

```
VLA Training Pipeline
  ↓ (runs on Trainer CRD)
  ↓ (1-2 hours on L40S)
  ↓
MLflow Model Registry
  ↓ (registers model metadata)
  ↓
SeaweedFS S3 Storage
  ↓ (stores model weights at s3://mlflow/models/vla-warehouse/vX.Y)
  ↓
KServe InferenceService
  ↓ (downloads from S3, serves via the configured runtime)
  ↓
Factory edge locations consume model
```

## Switching to Production Mode

To use real GR00T VLA models from the training pipeline:

### 1. Ensure Training Pipeline Has Run

The training pipeline must have uploaded at least one model version to S3 and recorded it in MLflow. After a validated cutover, inspect the target using standard AWS CLI tooling. In one terminal, forward the ClusterIP endpoint:

```bash
oc port-forward -n mlflow svc/seaweedfs 8333:8333
```

In another terminal, list the training bucket with credentials scoped to a subshell:

```bash
(
  export AWS_ACCESS_KEY_ID="$(oc get secret -n vla-training s3-credentials -o jsonpath='{.data.AWS_ACCESS_KEY_ID}' | base64 -d)"
  export AWS_SECRET_ACCESS_KEY="$(oc get secret -n vla-training s3-credentials -o jsonpath='{.data.AWS_SECRET_ACCESS_KEY}' | base64 -d)"
  export AWS_DEFAULT_REGION=us-east-1 AWS_EC2_METADATA_DISABLED=true AWS_PAGER=""
  aws --endpoint-url http://127.0.0.1:8333 s3 ls s3://vla-training/ --recursive
)
```

Keep shell tracing disabled and confirm the corresponding version and artifact URI in MLflow. In-cluster helper Jobs use `public.ecr.aws/aws-cli/aws-cli:2.34.0` with Secret references; do not assume a storage-server container includes a client CLI.

### 2. Update InferenceService storageUri

Edit the InferenceService manifests to point to MLflow:

```yaml
# infrastructure/gitops/apps/workloads/factory-b/model-vla-warehouse-isvc.yaml
spec:
  predictor:
    model:
      storageUri: s3://mlflow/models/vla-warehouse/v1.4  # Use real version from MLflow
```

### 3. Ensure S3 Credentials Exist

The `storage-config` secret must exist in each namespace:

```bash
# Already created in factory-b and robot-edge namespaces
oc get secret storage-config -n factory-b
oc get secret storage-config -n robot-edge
```

### 4. Trigger Deployment

Commit the change to Git and let Argo CD sync:

```bash
git add infrastructure/gitops/apps/workloads/*/model-vla-warehouse-isvc.yaml
git commit -m "feat: switch to production VLA models from training pipeline"
git push
```

The InferenceService will:
- Download model weights from the configured SeaweedFS S3 artifact URI
- Load into vLLM engine (~2-5 minutes for model loading)
- Become Ready and serve inference requests

## GPU Node Tolerations

All VLA InferenceServices require GPU toleration for the L40S nodes:

```yaml
tolerations:
- key: nvidia.com/gpu
  operator: Equal
  value: L40S_SHARED
  effect: NoSchedule
```

This is already configured in both `factory-b` and `robot-edge` manifests.

## HIL Promotion Workflow

**Important:** The HIL (Human-in-the-Loop) promotion workflow does NOT upload models.

When an agent proposes promoting a factory to a new model version:
1. Agent generates a PR updating the `storageUri` in the InferenceService manifest
2. Operator approves the PR (or rejects it)
3. PR auto-merges and Argo CD syncs the change
4. KServe downloads the NEW model version from the EXISTING S3 path recorded in MLflow
5. Factory switches to the new model version

**The model must already exist in S3 and be recorded in MLflow** before promotion. Models are uploaded by:
- The VLA training pipeline (workloads/vla-training)
- Manual upload using `aws --endpoint-url <s3-endpoint> s3 cp --recursive <model-directory> s3://<bucket>/<version>/model/`, followed by the required MLflow registration (for testing)

## Troubleshooting

### InferenceService stuck in "Unknown" state

**Symptom:** Pod is Running and Ready, but InferenceService shows `READY: Unknown`

**Cause:** KServe controller is watching an old ReplicaSet

**Fix:**
```bash
# Delete old failed ReplicaSets
oc get replicasets -n factory-b | grep vla-warehouse | awk '{if ($2=="0") print $1}' | xargs -I {} oc delete replicaset {} -n factory-b

# Wait for KServe controller to reconcile
sleep 30
oc get inferenceservice vla-warehouse -n factory-b
```

### Pod stuck in Pending (FailedScheduling)

**Symptom:** `0/N nodes are available: N Insufficient nvidia.com/gpu`

**Cause:** GPU nodes have taints, InferenceService missing tolerations

**Fix:** Ensure tolerations are present in the InferenceService spec (already fixed in current manifests)

### Storage initialization failed

**Symptom:** `Init:CrashLoopBackOff`, logs show "S3 authentication failed"

**Cause:** Missing `storage-config` secret or ServiceAccount not configured

**Fix:**
```bash
# Create storage-config secret (see "Switching to Production Mode" section)
# Ensure InferenceService references the ServiceAccount:
spec:
  predictor:
    serviceAccountName: vla-warehouse-sa
```

### Model download fails from SeaweedFS

**Symptom:** `Init:Error`, logs show "Failed to fetch model. No model found in models/vla-warehouse/vX.Y"

**Cause:** Model doesn't exist at the specified S3 path, or the data has not been copied and verified on the target SeaweedFS store

**Fix:**
- Run the training pipeline to upload a model, OR
- Switch back to Showcase Mode (HF model)

## Summary Table

| Aspect | Showcase Mode | Production Mode |
|--------|---------------|-----------------|
| **Model Source** | Hugging Face (`hf://meta-llama/Llama-3.2-3B-Instruct`) | MLflow-recorded SeaweedFS S3 artifact URI |
| **Startup Time** | ~2-5 minutes (HF download + vLLM load) | Depends on S3 artifact size and serving runtime |
| **Prerequisites** | Internet access to Hugging Face | Training pipeline has run, models in MLflow |
| **Use Case** | Sales demos, partner showcases, quick deployments | Real production deployments, customer sites |
| **Model Quality** | Generic Llama 3.2 (not task-specific) | Fine-tuned GR00T VLA (warehouse-specific) |
| **Training Required** | No | Yes (60-90 min on L40S) |

## References

- VLA Training Pipeline: `workloads/vla-training/`
- InferenceService Manifests: `infrastructure/gitops/apps/workloads/{factory-b,robot-edge}/model-vla-warehouse-isvc.yaml`
- MLflow Model Registry Code: `workloads/vla-training/src/vla_training/register_model.py`
- GPU Resource Planning: `docs/08-gpu-resource-planning.md`
