# Week 0 Validation Results

> [!NOTE]
> This project was developed with assistance from AI tools.

**Purpose**: Document outcomes from Week 0 infrastructure validation spikes.

**Date Started**: 2026-06-30  
**Date Completed**: *(To be filled)*  
**Validator**: *(Your name)*

---

## Summary

| Component | Status | Latency | Notes |
|-----------|--------|---------|-------|
| vLLM on L4 GPU | 🚧 Not yet run | TBD | See `vllm-test/` |
| LangGraph Basics | 🚧 Not yet run | TBD | See `langgraph-hello/01_hello_agent.py` |
| LangGraph + vLLM | 🚧 Not yet run | TBD | See `langgraph-hello/02_agent_with_llm.py` |
| LangGraph + Tools | 🚧 Not yet run | TBD | See `langgraph-hello/03_agent_with_tools.py` |
| Postgres Schema | 🚧 Not yet run | TBD | See `postgres-setup/` |
| MCP Protocol | 🚧 Not yet run | TBD | See `mcp-protocol/` |

**Legend**:
- ✅ Success (meets criteria)
- ⚠️ Partial (works with caveats)
- ❌ Failed (blocked, needs alternative)
- 🚧 Not yet run

---

## 1. vLLM on L4 GPU

**Goal**: Serve Llama-3.1-8B-Instruct with < 5 sec p50 latency.

### Results

**Status**: 🚧 *(To be filled after running vllm-test)*

**Metrics**:
- Model load time: *(TBD)*
- Inference latency p50: *(TBD)*
- Inference latency p99: *(TBD)*
- GPU memory usage: *(TBD)* / 24 GB
- GPU utilization: *(TBD)*%

**Test Commands**:
```bash
# (Document the exact commands you ran)
```

**Observed Behavior**:
*(What happened when you ran the test?)*

**Issues Encountered**:
*(List any problems, errors, or unexpected behavior)*

**Decision**:
- [ ] ✅ Proceed with Llama-3.1-8B on L4 (meets criteria)
- [ ] ⚠️ Proceed with caveats: *(describe)*
- [ ] ❌ Try alternative: *(which model or GPU?)*

---

## 2. LangGraph Basics

**Goal**: Validate StateGraph, nodes, edges pattern works.

### Results

**Status**: 🚧 *(To be filled after running 01_hello_agent.py)*

**Test**: `langgraph-hello/01_hello_agent.py`

**Observed Behavior**:
*(Did the graph execute? Did state persist across nodes?)*

**Issues Encountered**:
*(Any import errors, version conflicts, etc.?)*

**Decision**:
- [ ] ✅ LangGraph pattern is clear, ready to build on it
- [ ] ⚠️ Works but: *(note confusion or complexity)*
- [ ] ❌ Pattern unclear, need more learning time

---

## 3. LangGraph + vLLM Integration

**Goal**: Validate LangGraph can call vLLM via port-forward.

### Results

**Status**: 🚧 *(To be filled after running 02_agent_with_llm.py)*

**Test**: `langgraph-hello/02_agent_with_llm.py`

**Metrics**:
- First call latency: *(TBD)*
- Subsequent call latency: *(TBD)*
- Response quality: *(coherent? hallucinated?)*

**Observed Behavior**:
*(What did the LLM respond?)*

**Issues Encountered**:
*(Connection issues? Timeouts? Model errors?)*

**Decision**:
- [ ] ✅ Integration works, ready for Milestone 1
- [ ] ⚠️ Works but slow (> 5 sec) - optimize later
- [ ] ❌ Blocked - cannot connect LangGraph to vLLM

---

## 4. LangGraph + Tool Calling

**Goal**: Validate LangGraph agent can call tools (pattern for MCP servers).

### Results

**Status**: 🚧 *(To be filled after running 03_agent_with_tools.py)*

**Test**: `langgraph-hello/03_agent_with_tools.py`

**Observed Behavior**:
- Did agent call the tool? *(yes/no)*
- Did agent parse tool result? *(yes/no)*
- Did agent compose natural language response? *(yes/no)*

**Tool Call Trace**:
```
(Paste the tool call sequence you observed)
```

**Issues Encountered**:
*(Did model refuse to call tools? Did it hallucinate results instead?)*

**Decision**:
- [ ] ✅ Tool calling works reliably
- [ ] ⚠️ Works sometimes (model inconsistent) - need prompt tuning
- [ ] ❌ Model doesn't support tool calling - try different model

---

## 5. Postgres Schema

**Goal**: Validate JSONB schema works for agent sessions and audit trail.

### Results

**Status**: 🚧 *(To be filled after running postgres-setup tests)*

**Test**: `postgres-setup/test_schema.sql`

**Metrics**:
- Insert latency: *(TBD)*
- Query latency: *(TBD)*
- JSONB array size limit: *(tested? how many entries?)*

**Schema Issues**:
*(Did JSONB array work? Any index performance concerns?)*

**Decision**:
- [ ] ✅ Schema works, ready for Milestone 1
- [ ] ⚠️ Works but: *(note performance concern)*
- [ ] ❌ Need to revise schema: *(why?)*

---

## 6. MCP Protocol

**Goal**: Validate MCP SDK can integrate with LangGraph.

### Results

**Status**: 🚧 *(To be filled after running mcp-protocol tests)*

**Test**: `mcp-protocol/test_mcp_server.py`

**Observed Behavior**:
*(Did MCP server expose tools? Did LangGraph discover them?)*

**Issues Encountered**:
*(Protocol version mismatch? SDK bugs? Integration complexity?)*

**Decision**:
- [ ] ✅ MCP SDK works, use for Milestone 1
- [ ] ⚠️ MCP SDK has issues - use simple HTTP for now, refactor later
- [ ] ❌ MCP SDK blocked - implement custom JSON-RPC

---

## Overall Readiness Assessment

### Can We Proceed to Milestone 1?

- [ ] ✅ **YES** - All critical spikes passed (vLLM, LangGraph+tools, Postgres)
- [ ] ⚠️ **YES, with caveats** - *(list what needs workaround)*
- [ ] ❌ **NO** - Blocked on: *(list blockers)*

### Recommended Next Steps

1. *(e.g., "Start Milestone 1 with mock MCP server, real vLLM")*
2. *(e.g., "Investigate Llama-3.2-3B as fallback if latency too high")*
3. *(e.g., "Schedule Week 1 check-in with team lead to review results")*

### Open Questions for Team Discussion

1. *(e.g., "Should we quantize model to int8 for faster inference?")*
2. *(e.g., "Is 7-second p99 latency acceptable if p50 is 3 seconds?")*
3. *(e.g., "Do we need MCP protocol compliance in Milestone 1, or defer?")*

---

## Lessons Learned

### What Worked Well

*(List surprises, things that were easier than expected)*

### What Was Harder Than Expected

*(List challenges, things to watch out for in Milestone 1)*

### Would Do Differently Next Time

*(Retrospective notes for future spikes)*

---

**Next Milestone**: Move validated patterns to `workloads/agentic-orchestrator/` and build Milestone 1 (read-only agent).