# Week 0: Infrastructure Validation

> [!NOTE]
> This project was developed with assistance from AI tools.

**Duration**: 3-5 days  
**Goal**: Validate infrastructure works before writing production code  
**Status**: 🚧 In Progress

---

## Overview

Week 0 is a **gate** before Milestone 1. You're validating:
- vLLM can serve Llama-3.1-8B on L4 GPU with acceptable latency
- LangGraph can call tools (the pattern for MCP servers)
- Postgres JSONB schema works for audit trails

**This is NOT production code.** It's experimental validation in `spikes/week0-validation/`.

---

## Entry Criteria

Before starting Week 0:

- [ ] Phase 3 plan approved (`../phase-3-agentic-implementation.md`)
- [ ] Architectural decisions made (see Pre-Implementation Decisions in Phase 3 plan)
- [ ] L4 GPU node available in cluster
- [ ] HuggingFace account created (for Llama 3.1 download)
- [ ] Namespace `agentic-ops` created

---

## Day-by-Day Breakdown

### Day 1: vLLM on L4 GPU

**Goal**: Prove vLLM can serve Llama-3.1-8B with < 5 sec latency.

**Morning (2-3 hours)**:
1. Get HuggingFace token
   - Create account: https://huggingface.co/join
   - Accept Llama 3.1 license: https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct
   - Create token: https://huggingface.co/settings/tokens

2. Check GPU availability
   ```bash
   oc get nodes -l nvidia.com/gpu.product=NVIDIA-L4 -o wide
   ```

3. Create secret
   ```bash
   oc create secret generic hf-token \
     -n agentic-ops \
     --from-literal=token='hf_YourTokenHere'
   ```

**Afternoon (2-3 hours)**:
4. Deploy vLLM pod
   ```bash
   cd spikes/week0-validation/vllm-test
   oc apply -f vllm-pod.yaml
   oc logs -f vllm-test -n agentic-ops
   ```

5. Wait for model load (~5 minutes)

6. Test inference
   ```bash
   oc port-forward vllm-test 8000:8000 -n agentic-ops
   curl http://localhost:8000/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"model": "meta-llama/Llama-3.1-8B-Instruct", "messages": [{"role": "user", "content": "What is 2+2?"}], "max_tokens": 50}' | jq .
   ```

7. Measure latency (run 10 requests, calculate p50/p99)

**Deliverable**: vLLM serving Llama-3.1-8B, latency documented

**Blockers**:
- No L4 GPU → Provision GPU node (SRE ticket)
- Model download fails → Check HF token, accept license
- High latency → Try Llama-3.2-3B (smaller model)

---

### Day 2: LangGraph Tool Calling

**Goal**: Prove LangGraph can call tools (pattern for MCP servers).

**Morning (2 hours)**:
1. Set up Python environment
   ```bash
   cd spikes/week0-validation/langgraph-hello
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. Test 1: Pure LangGraph (no LLM)
   ```bash
   python 01_hello_agent.py
   ```
   Expected: Graph executes, state persists across nodes

**Afternoon (2-3 hours)**:
3. Ensure vLLM port-forward is running (from Day 1)

4. Test 2: LangGraph + vLLM
   ```bash
   python 02_agent_with_llm.py
   ```
   Expected: LangGraph calls vLLM, gets coherent response

5. Test 3: Tool calling
   ```bash
   python 03_agent_with_tools.py
   ```
   Expected: Agent calls `get_temperature` tool, composes answer

**Deliverable**: Tool calling pattern validated

**Blockers**:
- Import errors → Check Python version (3.11+), reinstall deps
- vLLM connection fails → Restart port-forward
- Tool calling doesn't work → Try different model (Qwen2.5-7B has strong tool-use)

---

### Day 3: Postgres Schema

**Goal**: Validate JSONB schema for agent sessions and audit trail.

**Morning (1-2 hours)**:
1. Deploy Postgres (you'll need to create `postgres.yaml` based on Phase 3 plan schema)
   ```bash
   cd spikes/week0-validation/postgres-setup
   oc apply -f postgres.yaml
   oc port-forward svc/postgres 5432:5432 -n agentic-ops
   ```

2. Create schema
   ```bash
   psql postgresql://agent:changeme123@localhost:5432/agentic_orchestrator \
     -f schema.sql
   ```

**Afternoon (1-2 hours)**:
3. Test JSONB inserts
   ```sql
   INSERT INTO agent_sessions VALUES (
     gen_random_uuid(),
     'test@redhat.com',
     NOW(),
     NOW(),
     '{"step": 1}'::jsonb,
     ARRAY['{"tool": "test", "result": "ok"}'::jsonb]
   );
   
   SELECT * FROM agent_sessions;
   ```

4. Test audit trail table

**Deliverable**: Postgres schema validated

---

### Day 4: MCP Protocol (Optional)

**Decision Point**: Do you need MCP protocol compliance in Milestone 1?

**Option A (Recommended)**: Skip Day 4, use simple HTTP endpoints for mcp-mlflow in M1, refactor to MCP in M2.

**Option B**: Spend Day 4 testing Anthropic's MCP SDK integration with LangGraph.

Most solo developers should choose **Option A** (faster to Milestone 1).

---

### Day 5: Review & Decision

**Morning (1 hour)**:
1. Complete `spikes/week0-validation/VALIDATION-RESULTS.md`
   - Fill in all sections (vLLM, LangGraph, Postgres, MCP)
   - Document metrics (latency, memory usage)
   - Make decisions: proceed / caveat / blocked

2. Answer the gate question:
   > **Can we proceed to Milestone 1?**

**Afternoon (1 hour)**:
3. Team check-in
   - Share VALIDATION-RESULTS.md
   - Discuss Phase 3 plan Decision Points 1-5
   - Get alignment on Milestone 1 start

**Deliverable**: Go/No-Go decision for Milestone 1

---

## Exit Criteria

Week 0 is complete when:

- [ ] vLLM serves Llama-3.1-8B on L4 GPU
- [ ] Inference latency p50 < 5 seconds (or documented caveat)
- [ ] LangGraph tool calling works reliably
- [ ] Postgres JSONB schema validated
- [ ] `VALIDATION-RESULTS.md` filled out with decisions
- [ ] Team alignment on proceeding to Milestone 1

---

## Common Issues & Solutions

### Issue: vLLM OOMKilled

**Symptom**: Pod crashes, `oc get pod` shows `OOMKilled`

**Solution**:
```bash
# Reduce model context length
# Edit vllm-pod.yaml, change --max-model-len=2048
# Or try smaller model: Llama-3.2-3B
```

### Issue: LangGraph doesn't call tools

**Symptom**: Agent returns answer directly instead of calling tool

**Solution**:
- Check system prompt includes "You have access to tools"
- Try different model (Qwen2.5-7B has better tool-use)
- Verify vLLM version supports tool calling format

### Issue: High latency (> 10 seconds)

**Symptom**: First token takes 8+ seconds

**Solution**:
```bash
# Check GPU utilization
oc exec vllm-test -n agentic-ops -- nvidia-smi

# If GPU util is low, try:
# - Reduce --max-num-seqs (less batching overhead)
# - Enable --enable-chunked-prefill
# - Try quantization: --dtype=int8
```

---

## Handoff to Milestone 1

If Week 0 validation passes, you're ready for **Milestone 1: Read-Only Agent** (Weeks 1-2).

**What Milestone 1 depends on from Week 0**:
- vLLM deployment pattern (copy from `vllm-test/vllm-pod.yaml`)
- LangGraph tool calling code (copy from `langgraph-hello/03_agent_with_tools.py`)
- Postgres schema (copy from `postgres-setup/schema.sql`)

**What changes in Milestone 1**:
- Production Helm charts (not standalone YAML)
- Error handling, logging, monitoring
- Real mcp-mlflow server (not mock tools)
- Deployed to cluster (not just port-forward)

See `milestone-1-read-only-agent.md` for detailed M1 plan.

---

## Time Tracking

**Estimated vs. Actual**:

| Day | Task | Estimated | Actual | Notes |
|-----|------|-----------|--------|-------|
| 1 | vLLM validation | 4-6h | *(fill in)* | *(blockers?)* |
| 2 | LangGraph tools | 4-6h | *(fill in)* | *(blockers?)* |
| 3 | Postgres schema | 2-4h | *(fill in)* | *(blockers?)* |
| 4 | MCP protocol | 4h (optional) | *(fill in)* | *(skipped?)* |
| 5 | Review | 2h | *(fill in)* | - |

**Total**: 16-22 hours (3-5 days for solo developer)

---

**Status**: Update this when complete:
- [ ] Week 0 started: *(date)*
- [ ] Week 0 completed: *(date)*
- [ ] Decision: ✅ Proceed to M1 / ⚠️ Proceed with caveats / ❌ Blocked