# Week 0 Validation - Final Summary

> [!NOTE]
> This project was developed with assistance from AI tools.

**Dates**: June 30 - July 2, 2026  
**Duration**: 3 days (Days 1-3 complete, Day 4 skipped as optional)  
**Validator**: Ahmad Hameed  
**Status**: ✅ **COMPLETE - Ready for Milestone 1**

---

## Executive Summary

Week 0 successfully validated the core infrastructure stack for Phase 3 agentic orchestration:

- ✅ **vLLM serving** - Llama-3.1-8B on L40S GPU with 0.19s latency (10x better than target)
- ✅ **LangGraph orchestration** - StateGraph pattern validated
- ✅ **Postgres persistence** - JSONB schema for agent sessions and HIL audit trails validated
- ⚠️ **Tool calling** - Known issue with vLLM chat endpoint when tools enabled (documented, can debug in Milestone 1)

**Recommendation**: **Proceed to Milestone 1** (read-only agent implementation).

---

## Day-by-Day Results

### Day 1: vLLM on L40S GPU ✅

**Goal**: Serve Llama-3.1-8B-Instruct with < 5 sec latency

**Results**:
- ✅ Model loads in ~90 seconds
- ✅ Inference latency: **0.19s average** (target: <5s)
- ✅ p50: 0.17s, p99: 0.31s
- ✅ GPU memory: 39GB / 46GB (L40S)
- ✅ Responses are coherent and accurate

**Issues Resolved**:
1. GPU targeting: Changed from L4 to L40S (better! 48GB vs 24GB)
2. HuggingFace cache permissions: Added EmptyDir volume + env vars
3. Multiprocessing frontend: Added `--disable-frontend-multiprocessing`
4. Numba cache: Set `NUMBA_CACHE_DIR=/tmp/numba`
5. Outlines cache: Set `OUTLINES_CACHE_DIR=/tmp/outlines`
6. Tool calling flags: Added `--enable-auto-tool-choice --tool-call-parser=hermes`

**Files**: `vllm-test/vllm-pod.yaml`, `vllm-test/test_vllm.sh`

**Verdict**: ✅ **EXCELLENT** - Exceeds all criteria

---

### Day 2: LangGraph + vLLM ⚠️

**Goal**: Validate LangGraph can orchestrate agents and call vLLM

**Results**:
- ✅ Test 1 (Pure LangGraph): StateGraph works perfectly
- ✅ Test 2 (LangGraph + vLLM): Simple HTTP calls work
- ⚠️ Test 3 (Tool calling): langchain-openai compatibility issues

**What Works**:
- LangGraph StateGraph pattern (nodes, edges, state)
- Direct HTTP calls to vLLM `/v1/completions` endpoint
- Python environment with `uv` (super fast package management)

**Known Issue**:
- vLLM `/v1/chat/completions` endpoint has issues when tool calling is enabled
- Likely related to Outlines/Numba caching (same root cause as Day 1 issues)
- Workaround: Use direct HTTP calls for now, debug when building actual agent

**Files**: 
- `langgraph-hello/01_hello_agent.py` (✅ working)
- `langgraph-hello/02_agent_with_llm.py` (✅ working with simple HTTP)
- `langgraph-hello/03_agent_with_tools.py` (⚠️ has known issue)
- `langgraph-hello/requirements.txt` (pinned versions)

**Verdict**: ⚠️ **PARTIAL** - Core patterns validated, tool calling needs debugging

---

### Day 3: Postgres Schema ✅

**Goal**: Validate JSONB schema for agent sessions and HIL audit

**Results**: ✅ **All 6 tests passed**

1. ✅ Insert agent session with JSONB state
2. ✅ Query JSONB with `->` and `->>` operators
3. ✅ Append to JSONB[] array with `||` operator
4. ✅ Insert HIL audit with foreign keys + CHECK constraints
5. ✅ Query HIL audit by classification and decision
6. ✅ Deep JSONB path queries with `#>>` operator

**Infrastructure**:
- Deployed: Postgres 15 to `agentic-ops` namespace
- Storage: EmptyDir 5Gi (spike-grade, not production)
- Image: `registry.redhat.io/rhel9/postgresql-15:latest`
- Connection: `postgres.agentic-ops.svc:5432/agentic_orchestrator`

**Schema Highlights**:
- `agent_sessions` table with JSONB state + JSONB[] audit trail
- `hil_audit` table for immutable approval log
- Indexes on operator, timestamp, decision
- Foreign keys and CHECK constraints work

**Files**: `postgres-setup/` (README, schema.sql, test_schema.py, DAY3-RESULTS.md)

**Verdict**: ✅ **SUCCESS** - Schema is production-ready (pending HA upgrade)

---

### Day 4: MCP Protocol

**Status**: ⏭️ **Skipped** (marked as optional in plan)

**Reasoning**: 
- MCP is an integration detail, not a blocker
- Can validate MCP SDK during Milestone 1 implementation
- Core stack (vLLM + LangGraph + Postgres) is proven

---

## Overall Assessment

### ✅ Can We Proceed to Milestone 1?

**YES** - All critical components validated:

| Component | Status | Confidence |
|-----------|--------|------------|
| Model Serving (vLLM) | ✅ Excellent | **High** - 10x better than target |
| Orchestration (LangGraph) | ✅ Good | **High** - StateGraph pattern clear |
| Persistence (Postgres) | ✅ Excellent | **High** - All JSONB tests passed |
| Tool Calling | ⚠️ Partial | **Medium** - Known issue, can debug |

**Blockers**: None

**Risks**:
- Tool calling issue needs resolution before agent can call MCP servers
- vLLM chat endpoint stability under load is untested
- No load testing or concurrency validation

---

## Lessons Learned

### ✅ What Worked Well

1. **L40S > L4** - Lucky break! 48GB vs 24GB, same cost
2. **uv is FAST** - 65ms install vs pip's 10-20 seconds
3. **JSONB is powerful** - Nested queries, array operations all work smoothly
4. **Spike-first approach** - Found all the sharp edges before production
5. **EmptyDir for caches** - Solves rootless container permission issues
6. **Pinning versions** - Critical for langchain compatibility

### ⚠️ What Was Harder Than Expected

1. **vLLM multiprocessing** - Needed `--disable-frontend-multiprocessing`
2. **Cache permissions** - Multiple caches (HF, Numba, Outlines) needed explicit paths
3. **langchain-openai versions** - Breaking changes between 0.2.9 and 1.3.3
4. **Tool calling flags** - Not documented clearly, found via trial and error
5. **Port-forward stability** - Keeps dying, need to use services not pods

### 💡 Would Do Differently Next Time

1. **Start with latest langchain-openai** - We pinned to 0.2.9, should test newer versions first
2. **Load testing** - Week 0 didn't test concurrency or sustained load
3. **Document workarounds immediately** - Lost time re-discovering same issues
4. **Test tool calling earlier** - Saved it for Test 3, should have been Test 1

---

## Known Issues & Workarounds

### Issue 1: vLLM Chat Endpoint When Tools Enabled

**Symptom**: HTTP 500 errors on `/v1/chat/completions` when `--enable-auto-tool-choice` is set

**Root Cause**: Likely Outlines/Numba caching issue (same as Day 1 cache errors)

**Workaround**: Use `/v1/completions` endpoint or simple HTTP calls instead of langchain-openai

**Resolution Plan**: 
- Debug in Milestone 1 when building actual tool-calling agent
- May need to upgrade vLLM or disable Outlines backend
- Fallback: Use llama.cpp or TGI instead of vLLM

**Impact**: Medium - Blocks LangGraph → MCP → vLLM full integration

---

### Issue 2: langchain-openai Version Compatibility

**Symptom**: `langchain-openai >= 1.0.0` uses `max_completion_tokens` parameter that vLLM 0.6.3 doesn't support

**Root Cause**: vLLM API lags behind OpenAI API spec

**Workaround**: Pin to `langchain-openai==0.2.9` (last stable before breaking changes)

**Resolution Plan**: 
- Upgrade vLLM to 0.7.x when released
- Or use direct HTTP calls and skip langchain-openai

**Impact**: Low - Workaround is stable

---

### Issue 3: Port-Forward Instability

**Symptom**: `oc port-forward` connections drop after a few minutes

**Root Cause**: OpenShift idle timeout or network issue

**Workaround**: 
- Use `svc/postgres` not `pod/postgres-xyz`
- Re-run port-forward when it dies
- For production: Use Routes or Ingress, not port-forward

**Impact**: Low - Only affects local testing

---

## Recommendations for Milestone 1

### 1. Start with Read-Only Agent (per plan)

Build the agent that:
- ✅ Can query fleet status (read-only MCP tools)
- ✅ Uses vLLM for reasoning
- ✅ Stores session state in Postgres
- ⚠️ **Skip tool calling** until Issue 1 is resolved
  - Use mock tool responses for now
  - Or implement direct HTTP tool calls (not via langchain)

### 2. Upgrade vLLM Configuration

Productionize the vLLM deployment:
- Use Deployment (not Pod)
- Add liveness/readiness probes
- Set resource limits based on Day 1 metrics
- Add Prometheus metrics scraping
- Consider multiple replicas behind a Service

### 3. Upgrade Postgres Configuration

Move from spike-grade to production:
- Deploy Crunchy Postgres Operator
- Create PostgresCluster with HA
- Use PVC (ODF block storage), not EmptyDir
- Enable TLS
- Set up WAL archiving

### 4. Debug Tool Calling in Parallel

While building Milestone 1:
- Investigate vLLM chat endpoint issue
- Test with newer vLLM versions (0.7.x when available)
- Consider llama.cpp or TGI as fallback
- Document findings in ADR

### 5. Add Observability

Before demo:
- MLflow integration (RHOAI 3.4 EA1 has it)
- Prometheus metrics for vLLM
- OpenTelemetry traces for LangGraph
- Grafana dashboard for latency/throughput

---

## Open Questions for Team Discussion

1. **Tool calling resolution timeline**
   - Block Milestone 1 until fixed?
   - Or proceed with mock tools and fix later?
   - **Recommendation**: Proceed with mocks, fix in parallel

2. **vLLM alternatives**
   - Should we evaluate llama.cpp or TGI as fallback?
   - Or commit to debugging vLLM?
   - **Recommendation**: Stick with vLLM, it's the standard

3. **Load testing scope**
   - How many concurrent agents do we need to support?
   - What's the target throughput (requests/sec)?
   - **Recommendation**: Define in Milestone 1, test in Milestone 2

4. **MCP protocol compliance**
   - Is full MCP SDK required in Milestone 1?
   - Or is simple HTTP tool calling sufficient?
   - **Recommendation**: Simple HTTP for M1, MCP SDK for M2

5. **Postgres HA timeline**
   - When do we need production Postgres?
   - Milestone 1 or Milestone 2?
   - **Recommendation**: M2 (after read-only agent proves the pattern)

---

## Files Created During Week 0

```
spikes/week0-validation/
├── README.md                      # Spike overview (create this next)
├── VALIDATION-RESULTS.md          # Detailed test results
├── WEEK0-SUMMARY.md               # This file
│
├── vllm-test/
│   ├── vllm-pod.yaml              # Working vLLM config (L40S)
│   ├── test_vllm.sh               # Latency test script
│   └── DAY1-RESULTS.md            # Day 1 detailed results
│
├── langgraph-hello/
│   ├── 01_hello_agent.py          # ✅ Pure LangGraph test
│   ├── 02_agent_with_llm.py       # ⚠️ LangGraph + vLLM
│   ├── 02_agent_with_llm_simple.py # ✅ HTTP workaround
│   ├── 03_agent_with_tools.py     # ⚠️ Tool calling (has issue)
│   ├── requirements.txt           # Pinned versions
│   └── .venv/                     # uv venv
│
└── postgres-setup/
    ├── README.md                  # Postgres validation guide
    ├── postgres.yaml              # K8s deployment
    ├── schema.sql                 # DDL for tables
    ├── load_schema.py             # Schema loader
    ├── test_schema.py             # 6 JSONB tests
    ├── check_permissions.py       # Debug script
    ├── DAY3-RESULTS.md            # Day 3 detailed results
    └── .venv/                     # uv venv
```

---

## Next Steps

### Immediate (This Week)

1. ✅ **Week 0 complete** - This summary marks the end
2. 📝 **Review with team** - Share this summary
3. 🎯 **Decide**: Start Milestone 1 or debug tool calling first?

### Milestone 1 (Next 1-2 Weeks)

**Goal**: Read-only agent that queries fleet status

**Tasks**:
1. Create `workloads/agentic-orchestrator/` Helm chart
2. Deploy production vLLM (based on Day 1 config)
3. Build LangGraph agent with mock tools
4. Store sessions in Postgres (based on Day 3 schema)
5. Create minimal Showcase Console UI
6. Demo to team

**Exit Criteria**:
- Agent can answer "What's the fleet status?" using mock MCP calls
- Session state persists in Postgres
- vLLM latency < 5s (we already have 0.19s!)
- Showcase Console displays conversation

### Milestone 2 (Weeks 3-4)

**Goal**: State-modifying agent with HIL approval

**Tasks**:
1. Integrate Llama Stack for HIL gates
2. Implement agent-opens-PR pattern
3. Real MCP servers (not mocks)
4. Upgrade Postgres to HA (Crunchy Operator)
5. Add MLflow observability

---

## Conclusion

Week 0 successfully de-risked the Phase 3 agentic orchestration stack. We validated:

✅ **Model serving works** (vLLM + Llama-3.1-8B)  
✅ **Orchestration works** (LangGraph StateGraph)  
✅ **Persistence works** (Postgres JSONB)  

We identified one known issue (tool calling) that can be debugged in parallel with Milestone 1 implementation.

**Status**: ✅ **READY TO PROCEED**

---

**Signed off**: Ahmad Hameed, 2026-07-02  
**Next milestone**: Phase 3 Milestone 1 (read-only agent)