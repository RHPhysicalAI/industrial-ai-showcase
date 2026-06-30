# Week 0 Validation - Quick Start Guide

> [!NOTE]
> This project was developed with assistance from AI tools.

**Goal**: Get from zero to validated infrastructure in ~3-5 days (solo developer).

**Outcome**: You'll know if Phase 3 Milestone 1 is feasible before writing production code.

---

## Day 1: vLLM on L4 GPU

### Morning: Prerequisites

1. **Get HuggingFace Token**
   - Go to https://huggingface.co/join
   - Create free account
   - Accept Llama 3.1 license: https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct
   - Create token: https://huggingface.co/settings/tokens (read permission)

2. **Check GPU Availability**
   ```bash
   oc get nodes -l nvidia.com/gpu.product=NVIDIA-L4 -o wide
   ```
   
   If no nodes found → **Stop, resolve GPU provisioning first**.

3. **Create Namespace & Secret**
   ```bash
   oc create namespace agentic-ops
   oc create secret generic hf-token \
     -n agentic-ops \
     --from-literal=token='hf_YourTokenHere'
   ```

### Afternoon: Deploy & Test vLLM

1. **Deploy vLLM**
   ```bash
   cd spikes/week0-validation/vllm-test
   oc apply -f vllm-pod.yaml
   
   # Watch logs (model download takes ~5 min)
   oc logs -f vllm-test -n agentic-ops
   ```

2. **Wait for Ready**
   Look for: `INFO: Application startup complete`

3. **Port-Forward & Test**
   ```bash
   # Terminal 1: Port-forward
   oc port-forward vllm-test 8000:8000 -n agentic-ops
   
   # Terminal 2: Test
   curl http://localhost:8000/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "meta-llama/Llama-3.1-8B-Instruct",
       "messages": [{"role": "user", "content": "What is 2+2?"}],
       "max_tokens": 50
     }' | jq .
   ```

4. **Document Results**
   - Edit `VALIDATION-RESULTS.md` → Section 1
   - Record: latency, GPU memory, any errors

**Success criteria**: Latency < 5 seconds, response is coherent.

**If failed**: See `vllm-test/README.md` troubleshooting section.

---

## Day 2: LangGraph Basics

### Morning: Setup

1. **Create Virtual Environment**
   ```bash
   cd spikes/week0-validation/langgraph-hello
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Test 1: Pure LangGraph**
   ```bash
   python 01_hello_agent.py
   ```
   
   Expected: "Planning step..." → "Executing step..." → Final result

### Afternoon: vLLM Integration

1. **Ensure vLLM port-forward is running** (from Day 1)

2. **Test 2: LangGraph + vLLM**
   ```bash
   python 02_agent_with_llm.py
   ```
   
   Expected: "The capital of France is Paris."

3. **Test 3: Tool Calling**
   ```bash
   python 03_agent_with_tools.py
   ```
   
   Expected: Agent calls `get_temperature` tool, composes response

4. **Document Results**
   - Edit `VALIDATION-RESULTS.md` → Sections 2-4
   - Note: Did tool calling work reliably?

**Success criteria**: All 3 tests pass, tool calling works.

**If failed**: Check `langgraph-hello/README.md` troubleshooting.

---

## Day 3: Postgres & Schema

### Morning: Deploy Postgres

1. **Create Postgres Pod**
   ```bash
   cd spikes/week0-validation/postgres-setup
   oc apply -f postgres.yaml  # (You'll create this)
   ```

2. **Port-Forward**
   ```bash
   oc port-forward svc/postgres 5432:5432 -n agentic-ops
   ```

3. **Create Schema**
   ```bash
   psql postgresql://agent:changeme123@localhost:5432/agentic_orchestrator \
     -f schema.sql
   ```

### Afternoon: Test Schema

1. **Test JSONB Inserts**
   ```bash
   psql postgresql://agent:changeme123@localhost:5432/agentic_orchestrator \
     -f test_schema.sql
   ```

2. **Document Results**
   - Edit `VALIDATION-RESULTS.md` → Section 5

**Success criteria**: Schema created, JSONB array writes work.

---

## Day 4: MCP Protocol (Optional)

**Decision Point**: Do you need MCP protocol in Milestone 1?

- **Option A**: Skip MCP, use simple HTTP endpoints (faster to Milestone 1)
- **Option B**: Test MCP SDK integration (slower, but closer to final design)

If **Option A**: Skip Day 4, mark MCP as "deferred to Milestone 2" in VALIDATION-RESULTS.md.

If **Option B**: Create simple MCP server, test with LangGraph.

---

## Day 5: Review & Decision

### Morning: Complete Documentation

1. **Fill in all sections of `VALIDATION-RESULTS.md`**
   - Status for each spike
   - Metrics (latency, memory, etc.)
   - Decisions (proceed / block / caveat)

2. **Answer the Key Question**
   > Can we proceed to Milestone 1?
   
   If YES → List recommended next steps  
   If NO → List blockers and alternatives

### Afternoon: Team Check-In

1. **Schedule 30-minute meeting with team lead**
2. **Share `VALIDATION-RESULTS.md`**
3. **Discuss open questions** (from Phase 3 plan, Decision Points 1-5)
4. **Get alignment on Milestone 1 start**

---

## Expected Timeline

| Day | Focus | Deliverable | Time |
|-----|-------|-------------|------|
| **1** | vLLM on L4 | vLLM serves Llama-3.1-8B | 4-6 hours |
| **2** | LangGraph | Tool calling works | 4-6 hours |
| **3** | Postgres | Schema validated | 2-4 hours |
| **4** | MCP (optional) | MCP SDK tested | 4 hours (or skip) |
| **5** | Review | VALIDATION-RESULTS.md complete | 2 hours |

**Total**: 3-5 days (assuming no blockers)

---

## Troubleshooting Common Issues

### vLLM Pod Stuck in Pending

```bash
oc describe pod vllm-test -n agentic-ops | grep -A 10 Events
```

**Common causes**:
- No L4 GPU available → Provision GPU node
- GPU already allocated → Check other pods using GPU
- Insufficient memory → Increase memory request

### Port-Forward Connection Refused

```bash
# Check pod is running
oc get pod vllm-test -n agentic-ops

# Check readiness
oc get pod vllm-test -n agentic-ops -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}'
```

**Common causes**:
- Pod not ready yet → Wait for model to load
- Port-forward died → Restart port-forward command
- Wrong namespace → Verify `-n agentic-ops`

### LangGraph Import Errors

```bash
# Verify venv is activated
which python
# Should show: .../venv/bin/python

# Reinstall if needed
pip install --upgrade -r requirements.txt
```

### Latency Too High (> 5 seconds)

**Quick checks**:
1. Is GPU being used? `oc exec vllm-test -n agentic-ops -- nvidia-smi`
2. Is model quantized? Try `--dtype=float16` (already in YAML)
3. Is max-model-len too high? Try `--max-model-len=2048`

**If still slow**: Consider Llama-3.2-3B (smaller model).

---

## What's Next After Week 0?

### If Validation Passed

1. **Commit results**
   ```bash
   git add spikes/week0-validation/VALIDATION-RESULTS.md
   git commit -m "spikes: Week 0 validation complete - ready for Milestone 1"
   ```

2. **Start Milestone 1** (Week 1-2)
   - Copy validated patterns to `workloads/agentic-orchestrator/`
   - Add production error handling, logging, tests
   - Build mock `mcp-mlflow` server (HTTP endpoints, canned data)
   - Deploy to cluster (not just port-forward)

### If Validation Blocked

1. **Document blockers** in VALIDATION-RESULTS.md
2. **Propose alternatives**:
   - Different model? (Llama-3.2-3B, Qwen2.5-7B)
   - Different GPU? (L40S instead of L4)
   - Defer feature? (Skip tool calling in M1, add later)
3. **Schedule follow-up** with team lead to re-scope

---

## Quick Reference: Commands You'll Use Daily

```bash
# Check vLLM pod status
oc get pod vllm-test -n agentic-ops

# View vLLM logs
oc logs vllm-test -n agentic-ops | tail -20

# Port-forward vLLM
oc port-forward vllm-test 8000:8000 -n agentic-ops

# Port-forward Postgres
oc port-forward svc/postgres 5432:5432 -n agentic-ops

# Activate Python venv
cd spikes/week0-validation/langgraph-hello
source venv/bin/activate

# Test vLLM health
curl http://localhost:8000/health

# Test LangGraph
python 03_agent_with_tools.py
```

---

**Ready to start?** Begin with Day 1 → `vllm-test/README.md`