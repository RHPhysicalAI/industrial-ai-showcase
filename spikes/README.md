# Spikes & Experiments

> [!NOTE]
> This project was developed with assistance from AI tools.

This directory contains pre-implementation validation work and experimental code for Phase 3 agentic orchestration.

**Status**: Experimental / Educational  
**Purpose**: Validate technical feasibility before Milestone implementation

---

## Directory Structure

- **`week0-validation/`** - Infrastructure validation spikes (vLLM, LangGraph, Postgres, MCP)
  - `vllm-test/` - vLLM serving Llama-3.1-8B on L4 GPU
  - `langgraph-hello/` - LangGraph tool calling patterns
  - `postgres-setup/` - Postgres schema validation
  - `mcp-protocol/` - MCP protocol integration tests

Each spike includes documentation of what was learned (success or failure).

---

## Important Notes

- Code here is **NOT production-ready**
- Successful patterns are migrated to `workloads/` during implementation
- Failed experiments are kept for historical reference (with notes on why they failed)
- All spike code follows Red Hat AI compliance (marked as AI-assisted)

---

## Lifecycle

1. **Spike phase**: Experiment here (Week 0)
2. **Validation**: Document results in `VALIDATION-RESULTS.md`
3. **Migration**: Move validated patterns to `workloads/` (Week 1+)
4. **Archive**: Spike code stays here for reference

---

## Validation Criteria

Each spike must answer:
- ✅ **Does it work?** (yes/no, with evidence)
- ⏱️ **Does it meet performance targets?** (latency, throughput)
- 🔍 **What did we learn?** (insights, gotchas, recommendations)
- ➡️ **Next steps?** (migrate to production, iterate, or abandon)

See `week0-validation/VALIDATION-RESULTS.md` for consolidated outcomes.