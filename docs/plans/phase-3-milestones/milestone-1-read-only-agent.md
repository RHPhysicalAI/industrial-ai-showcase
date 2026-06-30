# Milestone 1: Read-Only Agent (Weeks 1-2)

> [!NOTE]
> This project was developed with assistance from AI tools.

**Duration**: 2 weeks (10 working days)  
**Goal**: Operator asks a question → Agent calls mcp-mlflow (read-only) → Agent answers  
**Status**: 🔜 Not Started

---

## Overview

Milestone 1 is the **simplest possible end-to-end flow**:
- No HIL gate (no Llama Stack)
- No state-modifying actions (read-only tools only)
- No production UI (minimal HTML form for testing)

**You're building**:
1. LangGraph orchestrator (Python FastAPI service)
2. mcp-mlflow server (mock data, HTTP endpoints)
3. vLLM deployment (Helm chart, production-ready)
4. Minimal Console test UI (HTML + JavaScript)

**Pattern validation**: "Agent calls tool → tool returns data → agent composes answer"

---

## Entry Criteria

Before starting Milestone 1:

- [ ] Week 0 validation passed (see `VALIDATION-RESULTS.md`)
- [ ] vLLM latency < 5 sec p50 (or documented caveat)
- [ ] LangGraph tool calling works
- [ ] Team alignment on proceeding

**Hard Blocker**: If Week 0 failed, **do not** start M1. Resolve blockers first.

---

## Architecture (Milestone 1 Scope)

```
┌─────────────────────────────────────┐
│ Minimal Console (HTML form)        │
│  - Input: operator question        │
│  - Output: agent response           │
└────────────┬────────────────────────┘
             │ HTTP POST /ask
             ↓
┌─────────────────────────────────────┐
│ Agentic Orchestrator (FastAPI)     │
│  - LangGraph agent                  │
│  - Calls tools                      │
│  - Returns natural language         │
└────────────┬────────────────────────┘
             │
      ┌──────┴──────┐
      ↓             ↓
┌──────────┐   ┌─────────────┐
│ vLLM     │   │ mcp-mlflow  │
│ (L4 GPU) │   │ (mock data) │
└──────────┘   └─────────────┘
```

**Not in Milestone 1**: Llama Stack, HIL drawer, GitHub API, TrustyAI, real MLflow.

---

## Week 1: Core Components

### Day 1 (Monday): vLLM Production Deployment

**Goal**: Move vLLM from spike pod to production Helm chart.

**Tasks** (4-6 hours):

1. **Create Helm chart structure**
   ```bash
   mkdir -p infrastructure/gitops/apps/workloads/vllm-agent-brain
   cd infrastructure/gitops/apps/workloads/vllm-agent-brain
   
   # Create chart files
   touch Chart.yaml values.yaml
   mkdir templates
   touch templates/deployment.yaml templates/service.yaml templates/secret.yaml
   ```

2. **Copy vLLM config from spike**
   - Base `deployment.yaml` on `spikes/week0-validation/vllm-test/vllm-pod.yaml`
   - Add: resource limits, readiness/liveness probes, monitoring annotations

3. **Parameterize with values.yaml**
   ```yaml
   # values.yaml
   model:
     name: meta-llama/Llama-3.1-8B-Instruct
     dtype: float16
     maxModelLen: 4096
   
   resources:
     limits:
       nvidia.com/gpu: 1
       memory: 20Gi
     requests:
       cpu: 4
       memory: 16Gi
   
   nodeSelector:
     nvidia.com/gpu.product: NVIDIA-L4
   ```

4. **Deploy via Argo CD**
   ```bash
   # Test locally first
   helm template . | oc apply -f - --dry-run=client
   
   # Commit and let Argo CD sync
   git add .
   git commit -m "feat: add vLLM Helm chart for agent brain"
   git push
   ```

5. **Validate**
   ```bash
   oc get pod -n agentic-ops -l app=vllm-agent-brain
   oc logs -f <pod-name> -n agentic-ops
   
   # Port-forward test
   oc port-forward svc/vllm-agent-brain 8000:8000 -n agentic-ops
   curl http://localhost:8000/health
   ```

**Deliverable**: vLLM running via Helm chart, managed by Argo CD.

---

### Day 2 (Tuesday): mcp-mlflow Server (Mock)