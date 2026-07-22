# VLA Model Deployment Modes

This project was developed with assistance from AI tools.

## Overview

The VLA (Vision-Language-Action) models used by factory InferenceServices can operate in two modes:

1. **Showcase Mode** (default) - Fast startup, no GPU training required
2. **Production Mode** - Full training pipeline with MLflow model registry

## Current Configuration: Showcase Mode

The InferenceServices in `factory-b` and `robot-edge` are configured to use **Hugging Face placeholder models** for instant startup:

```yaml
storageUri: hf://microsoft/Phi-3-mini-4k-instruct
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
MinIO S3 Storage
  ↓ (stores model weights at s3://mlflow/models/vla-warehouse/vX.Y)
  ↓
KServe InferenceService
  ↓ (downloads from MinIO, serves via vLLM)
  ↓
Factory edge locations consume model
```

## Switching to Production Mode

To use real GR00T VLA models from the training pipeline:

### 1. Ensure Training Pipeline Has Run

The training pipeline must have successfully uploaded at least one model version to MLflow/MinIO:

```bash
# Check if models exist in MinIO
oc exec -n mlflow minio-<pod-name> -- mc ls local/mlflow/models/vla-warehouse/

# Check MLflow model registry
oc exec -n mlflow mlflow-db-1 -- psql -d mlflow -c "SELECT name, version FROM model_versions WHERE name='vla-warehouse';"
```

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
- Download model weights from MinIO (s3://mlflow/...)
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
4. KServe downloads the NEW model version from the EXISTING path in MLflow/MinIO
5. Factory switches to the new model version

**The model must already exist in MLflow/MinIO** before promotion. Models are uploaded by:
- The VLA training pipeline (workloads/vla-training)
- Manual upload via `mc` or `mlflow` CLI (for testing)

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

### Model download fails from MinIO

**Symptom:** `Init:Error`, logs show "Failed to fetch model. No model found in models/vla-warehouse/vX.Y"

**Cause:** Model doesn't exist at the specified path in MinIO

**Fix:**
- Run the training pipeline to upload a model, OR
- Switch back to Showcase Mode (HF model)

## Summary Table

| Aspect | Showcase Mode | Production Mode |
|--------|---------------|-----------------|
| **Model Source** | Hugging Face (`hf://microsoft/Phi-3-mini-4k-instruct`) | MLflow/MinIO (`s3://mlflow/models/vla-warehouse/vX.Y`) |
| **Startup Time** | ~2-5 minutes (HF download + vLLM load) | ~2-5 minutes (MinIO download + vLLM load) |
| **Prerequisites** | Internet access to Hugging Face | Training pipeline has run, models in MLflow |
| **Use Case** | Sales demos, partner showcases, quick deployments | Real production deployments, customer sites |
| **Model Quality** | Generic Phi-3 (not task-specific) | Fine-tuned GR00T VLA (warehouse-specific) |
| **Training Required** | No | Yes (60-90 min on L40S) |

## References

- VLA Training Pipeline: `workloads/vla-training/`
- InferenceService Manifests: `infrastructure/gitops/apps/workloads/{factory-b,robot-edge}/model-vla-warehouse-isvc.yaml`
- MLflow Model Registry Code: `workloads/vla-training/src/vla_training/register_model.py`
- GPU Resource Planning: `docs/08-gpu-resource-planning.md`
