# vLLM Agent Brain - Helm Chart

> [!NOTE]
> This project was developed with assistance from AI tools.

**Purpose**: Production deployment of vLLM serving Llama-3.1-8B-Instruct for Phase 3 agentic orchestration.

**Status**: Milestone 1 - Read-Only Agent

---

## Overview

This Helm chart deploys vLLM to serve the LLM "brain" for Phase 3 agents. Configuration is based on Week 0 validation results (`spikes/week0-validation/vllm-test/`).

**Validated Performance**:
- Model load time: ~90 seconds
- Inference latency: **0.19s average** (target: <5s)
- GPU: L40S (48GB VRAM)
- vLLM version: 0.6.3.post1

---

## Quick Start

### Prerequisites

- OpenShift cluster with `agentic-ops` namespace
- L40S GPU nodes (or update `values.yaml` for L4)
- HuggingFace token secret: `hf-token` in `agentic-ops` namespace

### Install

```bash
# From repository root
cd infrastructure/gitops/apps/workloads/vllm-agent-brain

# Test template rendering
helm template vllm-agent-brain . --namespace agentic-ops

# Install via Helm (for testing)
helm install vllm-agent-brain . --namespace agentic-ops

# Or let Argo CD manage it (production)
# Just commit this chart and Argo CD will sync
```

### Verify

```bash
# Check pod status
oc get pod -n agentic-ops -l app.kubernetes.io/name=vllm-agent-brain

# Watch logs (model loads in ~90 seconds)
oc logs -f -n agentic-ops -l app.kubernetes.io/name=vllm-agent-brain

# Port-forward and test
oc port-forward -n agentic-ops svc/vllm-agent-brain 8000:8000
curl http://localhost:8000/health
```

---

## Configuration

### Key Values

| Parameter | Description | Default | Week 0 Validated |
|-----------|-------------|---------|------------------|
| `model.name` | HuggingFace model ID | `meta-llama/Llama-3.1-8B-Instruct` | ✅ |
| `model.dtype` | Model precision | `float16` | ✅ |
| `model.maxModelLen` | Max sequence length | `4096` | ✅ |
| `gpu.product` | GPU node selector | `NVIDIA-L40S` | ✅ (not L4!) |
| `gpu.count` | GPUs per pod | `1` | ✅ |
| `replicas` | Number of replicas | `1` | - |

### Critical Flags (From Week 0)

These flags are **required** based on Week 0 validation:

```yaml
model:
  disableFrontendMultiprocessing: true  # Prevents HTTP 500 errors
  enableAutoToolChoice: true             # Enables tool calling
  toolCallParser: hermes                 # Tool call format
```

### Cache Configuration

EmptyDir volumes are **required** for rootless containers:

```yaml
storage:
  hfCache:
    enabled: true
    sizeLimit: 20Gi
  numbaCache:
    enabled: true
    sizeLimit: 1Gi
  outlinesCache:
    enabled: true
    sizeLimit: 5Gi
```

---

## Override Examples

### Use Different Model

```bash
helm install vllm-agent-brain . \
  --set model.name=meta-llama/Llama-3.2-3B-Instruct \
  --namespace agentic-ops
```

### Use L4 GPU Instead of L40S

```bash
helm install vllm-agent-brain . \
  --set gpu.product=NVIDIA-L4 \
  --namespace agentic-ops
```

### Enable OpenShift Route

```bash
helm install vllm-agent-brain . \
  --set route.enabled=true \
  --set route.host=vllm.apps.cluster.example.com \
  --namespace agentic-ops
```

### Multiple Replicas (for load balancing)

```bash
helm install vllm-agent-brain . \
  --set replicas=2 \
  --namespace agentic-ops
```

**Note**: Each replica needs 1 GPU. With 3 L40S GPUs, max replicas = 3.

---

## Architecture

```
┌────────────────────────────────────┐
│ vllm-agent-brain Service           │
│  ClusterIP: vllm-agent-brain:8000  │
└────────────┬───────────────────────┘
             │
             ↓
┌────────────────────────────────────┐
│ vllm-agent-brain Deployment        │
│  - vLLM 0.6.3.post1                │
│  - Llama-3.1-8B-Instruct           │
│  - L40S GPU (48GB)                 │
│  - EmptyDir caches                 │
└────────────────────────────────────┘
```

**Consumers**:
- `agentic-orchestrator` (LangGraph agent service)
- `llamastack` (Llama Stack governance layer)

---

## Health Checks

### Liveness Probe

```yaml
httpGet:
  path: /health
  port: 8000
initialDelaySeconds: 120  # Model loads in ~90s
periodSeconds: 30
failureThreshold: 3
```

### Readiness Probe

```yaml
httpGet:
  path: /health
  port: 8000
initialDelaySeconds: 100
periodSeconds: 10
failureThreshold: 3
```

---

## Resource Allocation

Based on Week 0 validation:

```yaml
resources:
  requests:
    cpu: "4"
    memory: 16Gi
    nvidia.com/gpu: 1
  limits:
    cpu: "8"
    memory: 20Gi
    nvidia.com/gpu: 1
```

**Observed Usage** (Week 0):
- GPU memory: 39GB / 46GB (84.6%)
- System memory: ~16GB
- CPU: Varies during inference

---

## Troubleshooting

### Pod stuck in Pending

```bash
# Check GPU node availability
oc get nodes -l nvidia.com/gpu.product=NVIDIA-L40S

# Check GPU allocation
oc describe node <gpu-node-name> | grep nvidia.com/gpu
```

**Solution**: Verify `gpu.product` matches your cluster's GPU labels.

---

### Model download fails

```bash
# Check HuggingFace token secret
oc get secret hf-token -n agentic-ops

# View pod logs
oc logs -n agentic-ops -l app.kubernetes.io/name=vllm-agent-brain
```

**Solution**: Ensure `hf-token` secret exists and contains valid token.

---

### HTTP 500 errors on /v1/chat/completions

**Symptom**: vLLM returns 500 errors despite model loading successfully.

**Root Cause**: One of these flags is missing:
- `disableFrontendMultiprocessing: true`
- `NUMBA_CACHE_DIR` env var
- `OUTLINES_CACHE_DIR` env var

**Solution**: Verify all Week 0 validated flags are present in deployment.

---

### Pod OOMKilled

**Symptom**: Pod restarts with `OOMKilled` status.

**Root Cause**: Model doesn't fit in allocated memory.

**Solution**:
1. Increase `resources.limits.memory` to `24Gi`
2. Or reduce `model.gpuMemoryUtilization` to `0.75`
3. Or use smaller model (Llama-3.2-3B)

---

## Upgrade Path

### Milestone 1 → Milestone 2

**Current**: Plain Deployment  
**Future**: KServe InferenceService

**Migration**:
1. Keep this chart for Milestone 1
2. Create new `vllm-kserve` chart in Milestone 2
3. Use KServe ServingRuntime + InferenceService
4. Point agentic-orchestrator to new service
5. Delete this deployment

**Reason**: KServe adds model versioning, canary deployments, autoscaling - not needed for M1.

---

## Monitoring

### Prometheus Metrics

vLLM exposes metrics at `/metrics`:

```yaml
annotations:
  prometheus.io/scrape: "true"
  prometheus.io/port: "8000"
  prometheus.io/path: "/metrics"
```

**Key Metrics**:
- `vllm_request_duration_seconds` - Inference latency
- `vllm_num_requests_running` - Concurrent requests
- `vllm_gpu_cache_usage_perc` - GPU KV cache usage

### Grafana Dashboard

**TODO**: Create Grafana dashboard in Milestone 2 with:
- Latency percentiles (p50, p95, p99)
- Throughput (requests/sec)
- GPU utilization
- Error rate

---

## Related Documentation

- **[Week 0 Validation](../../../../spikes/week0-validation/vllm-test/)** - Spike that validated this config
- **[Milestone 1 Plan](../../../../docs/plans/phase-3-milestones/milestone-1-read-only-agent.md)** - Overall M1 roadmap
- **[Component Catalog](../../../../docs/03-component-catalog.md)** - Where this fits in the architecture

---

## Known Limitations

1. **Single replica** - No load balancing in Milestone 1
2. **EmptyDir storage** - Model re-downloads on pod restart (~5GB, ~60s)
3. **No autoscaling** - Fixed 1 replica, manual scaling only
4. **No model versioning** - Redeploy required for model changes
5. **Tool calling issue** - `/v1/chat/completions` endpoint has known issues (see Week 0 SUMMARY)

**All will be addressed in Milestone 2 via KServe upgrade.**

---

**Status**: ✅ Ready for Milestone 1 deployment