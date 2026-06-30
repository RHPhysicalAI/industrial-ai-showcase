# Phase 3: Agentic Orchestration — Implementation Plan

> [!NOTE]
> This project was developed with assistance from AI tools.

**Status**: Planning (Phase 2 in progress)  
**Target Start**: Upon Phase 2 completion  
**Target Duration**: 8-10 weeks  
**Primary Deliverable**: 60-minute technical deep-dive demo running live

**📋 Implementation Plans**: See `phase-3-milestones/` directory for week-by-week execution guides:
- `week-0-validation.md` - Infrastructure validation spikes (3-5 days)
- `milestone-1-read-only-agent.md` - Weeks 1-2
- `milestone-2-hil-gate.md` - Weeks 3-4
- `milestone-3-agent-opens-pr.md` - Weeks 5-6
- `milestone-4-full-drawer-trustyai.md` - Weeks 7-8
- `milestone-5-cosmos-nims.md` - Weeks 9-10

---

## Executive Summary

Phase 3 delivers the agentic orchestration layer — the capability for operators to interact with the industrial AI stack via natural language, with human-in-the-loop (HIL) governance for state-modifying actions. This is the most architecturally complex phase, introducing a two-layer stack (LangGraph + Llama Stack), three MCP servers, a six-pane HIL approval drawer, and end-to-end observability for agent reasoning.

**Architectural Approach**: The agent never touches the cluster API directly. State-modifying actions flow through Git (agent opens PR → operator reviews in HIL drawer → PR merges → Argo CD reconciles). This reframes "LLM touching OT" as "LLM participating in code review."

**Critical Constraint**: Llama Stack governance operates on the GitOps / PR-open path **only**, never inline in the 10Hz+ VLA serving-time robot command flow. Violating this invariant breaks credibility with technical audiences (Archetype C).

**Complexity Budget**: This phase introduces 10+ new components across 4 segments. The implementation strategy prioritizes **incremental integration** — get the simplest end-to-end flow working first, then layer in complexity.

---

## Entry Criteria

Before Phase 3 starts, these **must** be complete:

1. ✅ **Phase 2 complete** — 20-minute demo runs reliably end-to-end
2. ✅ **HIL Approval Drawer Design Spec merged** (Phase 2 deliverable at `docs/plans/hil-approval-drawer-design.md`)
3. ✅ **NGC entitlements resolved** for Cosmos Predict 2.5 and Cosmos Transfer 2.5
4. ✅ **Performance envelope doc v1** published with measured baseline latencies (Phase 2 deliverable)
5. ✅ **Security posture doc** published with STIG profile, FIPS component-level status, Sigstore admission baseline (Phase 2 deliverable)
6. ✅ **Multi-cluster infrastructure operational** (hub + companion + spoke-a + spoke-b, Kafka federation, ACM, Thanos)

**Hard Blocker**: If NGC entitlements for Cosmos NIMs are not available, Segment 1 of the 60-min demo cannot proceed. Mitigation: start with Segments 2-4 (agentic + security + operational depth), defer Segment 1 to Phase 4 or deliver a limited synthetic-data story with existing tools.

---

## Pre-Implementation Decisions & Readiness

Before writing code, the team must align on five critical architectural decisions. This section frames the questions, presents options with tradeoffs, and captures decisions for future reference.

### Decision 1: Agent Brain LLM Selection

**The Question**: Which LLM should power the LangGraph agent (tool calling, natural language understanding)?

**Options**:

| Model | Size | Memory (fp16) | Tool-Use Quality | Speed | Notes |
|-------|------|---------------|------------------|-------|-------|
| **Llama-3.1-8B-Instruct** | 8B | ~16 GB | Excellent (proven) | Medium | Meta's flagship, well-documented tool-use |
| **Llama-3.2-3B-Instruct** | 3B | ~6 GB | Good | Fast | Smaller, faster, less capable reasoning |
| **Qwen2.5-7B-Instruct** | 7B | ~14 GB | Excellent | Medium | Strong tool-use benchmarks, non-Meta |
| **Mistral-7B-Instruct-v0.3** | 7B | ~14 GB | Good | Medium | Solid tool-use, Apache 2.0 license |

**Constraints**:
- GPU Budget: 1× L4 (24 GB VRAM) dedicated to agent brain
- Latency Target: Read-only queries < 5 seconds p50
- Tool-Calling Format: Must emit valid MCP protocol JSON

**Recommendation**: Start with **Llama-3.1-8B-Instruct** (proven tool-use, fits L4, large community support). Fallback to Llama-3.2-3B if memory pressure.

**Questions for Team**:
- **Q1**: Do we have strong reasons to prefer a non-Meta model (licensing, RHEL productization concerns)?
- **Q2**: Should we benchmark multiple models in Milestone 1, or commit to one and optimize?
- **Q3**: Is quantization (int8/int4) acceptable if it reduces latency, or do we need full fp16 quality?

**Decision**: *(To be filled after team discussion)*

---

### Decision 2: MCP Protocol Implementation

**The Question**: How should we implement the MCP (Model Context Protocol) interface between LangGraph and tool servers?

**Options**:

#### Option A: Use Anthropic's Official `mcp` Python SDK
- **Pros**: Vendor-supported, handles schema validation, active development
- **Cons**: External dependency, potential version mismatch, optimized for Claude

#### Option B: Implement Custom JSON-RPC Layer
- **Pros**: Full control, optimized for Llama 3.1, no external dependency churn
- **Cons**: More upfront work, need to maintain MCP spec compatibility

#### Option C: Hybrid (MCP SDK for servers, custom client for LangGraph)
- **Pros**: MCP servers are portable, LangGraph client optimized for our LLM
- **Cons**: More complexity, schema mismatch risk

**Recommendation**: **Option A** (Anthropic's `mcp` SDK). Faster time-to-value, build Milestone 1 as protocol validation spike.

**Mitigation for Version Mismatch Risk**:
- Pin exact SDK version in `requirements.txt`
- Abstract MCP calls behind interface (`src/agentic_orchestrator/mcp_client.py`)
- If SDK fails in Milestone 1, rewrite is cheap (only one component)

**Questions for Team**:
- **Q4**: Do we have any Red Hat productization concerns with using Anthropic's SDK directly?
- **Q5**: Should we plan for a "MCP compatibility test suite" to validate multiple LLMs?
- **Q6**: Is there value in contributing to the MCP SDK upstream (if we hit issues)?

**Decision**: *(To be filled after team discussion)*

---

### Decision 3: State Persistence Strategy

**The Question**: LangGraph needs to persist session state (conversation history, tool calls, pending HIL requests). What's the schema and storage approach?

**Proposed Postgres Schema**:

```sql
-- Agent sessions (one per operator conversation)
CREATE TABLE agent_sessions (
  session_id UUID PRIMARY KEY,
  operator_identity TEXT NOT NULL,  -- OAuth sub or CAC/PIV DN
  started_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL,
  state JSONB NOT NULL,  -- LangGraph checkpointer state (opaque blob)
  audit_trail JSONB[] NOT NULL  -- array of tool calls + results
);

-- HIL audit trail (one per approval/rejection)
CREATE TABLE hil_audit (
  action_id UUID PRIMARY KEY,
  timestamp TIMESTAMP NOT NULL,
  session_id UUID REFERENCES agent_sessions(session_id),
  operator_identity TEXT NOT NULL,
  tool_call JSONB NOT NULL,
  classification TEXT NOT NULL,  -- 'read-only' | 'state-modifying'
  guardrail_results JSONB NOT NULL,
  decision TEXT NOT NULL,  -- 'approved' | 'rejected'
  rejection_reason TEXT,
  pr_url TEXT,  -- populated if agent-opens-PR pattern
  context_trail_hash TEXT NOT NULL  -- sha256 of MCP trace
);
```

**Key Design Decisions**:

1. **Session State as JSONB Blob vs. Normalized Tables?**
   - **Proposed**: JSONB blob (LangGraph checkpointer expects full state serialize/deserialize)
   - **Tradeoff**: Harder to debug (can't SQL query into blob), but keeps schema stable

2. **Audit Trail as JSONB Array vs. Separate Table?**
   - **Proposed**: JSONB array within `agent_sessions`
   - **Rationale**: Tool calls always queried in context of session (co-located = better performance)
   - **Alternative**: Separate `tool_calls` table for cross-session analytics

3. **HIL Audit as Separate Table?**
   - **Proposed**: Yes, separate table (immutable for compliance, queried independently)

**Questions for Team**:
- **Q7**: Should we normalize the audit trail into a separate `tool_calls` table, or is JSONB array acceptable?
- **Q8**: Do we need a retention policy for `agent_sessions`? (e.g., archive sessions > 90 days old)
- **Q9**: Should `hil_audit` be in a separate database (for compliance isolation), or same DB as agent state?

**Decision**: *(To be filled after team discussion)*

---

### Decision 4: Integration Testing Strategy

**The Question**: Phase 3 has 10+ new components. How do we validate incrementally without waiting for the full 60-min demo?

**Proposed Testing Tiers**:

#### Tier 1: Unit Tests (Per Component)
- Each component ships with unit tests (80% line coverage minimum)
- `workloads/agentic-orchestrator/tests/` — LangGraph graph execution, tool calling
- `workloads/llama-stack/tests/` — HIL gate logic, guardrail evaluation
- `workloads/mcp-*/tests/` — MCP tool endpoints, read/write classification

#### Tier 2: Integration Tests (Cross-Component, In-Memory)
- Test LangGraph + MCP servers **without** real backend systems
- Mock MLflow, Fleet Manager, Isaac Sim APIs (returns canned data)
- Fast feedback loop, runs in CI

**Example Test**:
```python
def test_read_only_agent_query():
    # Given: LangGraph + mocked mcp-mlflow
    agent = create_test_agent(mcp_mlflow=mock_mlflow_server)
    
    # When: Operator asks question
    response = agent.ask("What's the pick-success rate for v1.3?")
    
    # Then: Agent calls correct tool, returns answer
    assert "mcp-mlflow.get_run_metrics" in agent.tool_calls
    assert "0.76" in response.text  # from mock data
    assert response.latency_ms < 5000
```

#### Tier 3: End-to-End Tests (Real Cluster, Milestone Checkpoints)
- At end of each Milestone, validate against **real** backend
- Milestone 1: Real MLflow, agent queries work
- Milestone 2: Real Llama Stack, HIL gate triggers
- Milestone 3: Real GitHub, PRs open and merge

#### Tier 4: Demo Rehearsals (Weeks 11-12)
- Full 60-minute demo, all 4 segments, recorded for fallback

**Open Question**: Should we build a test harness (`tests/integration/harness/`) with mock MCP servers + test scenarios? Effort: ~1 week. Benefit: Faster iteration, safer refactoring.

**Questions for Team**:
- **Q10**: Is 80% unit test coverage the right target, or should we aim higher (90%)?
- **Q11**: Should we invest in the test harness upfront (Milestone 1), or defer to Milestone 3?
- **Q12**: How do we validate latency targets (< 5 sec p50) in CI? (Need load testing infra?)

**Decision**: *(To be filled after team discussion)*

---

### Decision 5: Milestone Sequencing & Scope Flexibility

**The Question**: Phase 3 is 8-10 weeks. If we hit blockers (NGC entitlements delayed, Llama Stack API changes), what scope can we defer to Phase 4?

**Proposed Critical Path (Non-Negotiable)**:

1. **Milestone 1: Read-Only Agent** (weeks 1-2) — LangGraph + mcp-mlflow read-only tools
2. **Milestone 2: HIL Gate** (weeks 3-4) — Llama Stack + 3-pane drawer + audit trail
3. **Milestone 3: Agent-Opens-PR** (weeks 5-6) — GitHub integration + mcp-fleet

**Negotiable Scope (Can Defer to Phase 4 If Needed)**:

4. **Milestone 4: Full Drawer + TrustyAI** (weeks 7-8)
   - **Risk**: TrustyAI eval latency may exceed 10 seconds
   - **Fallback**: Show "Eval score: pending" in drawer, complete eval async
   - **Defer to Phase 4**: Real-time eval scores (if latency > 30 seconds consistently)

5. **Milestone 5: Cosmos NIMs** (weeks 9-10)
   - **Risk**: NGC entitlements not available
   - **Fallback**: Deploy mock Cosmos API (returns canned predictions/images)
   - **Defer to Phase 4**: Real Cosmos Predict/Transfer integration

**Buffer Weeks (11-12)**: Integration polish, demo rehearsals, performance optimization, docs.

**Questions for Team**:
- **Q13**: Are we aligned on the Critical Path (M1-M3 non-negotiable, M4-M5 negotiable)?
- **Q14**: If NGC entitlements are delayed, do we proceed with mock Cosmos API, or pause Phase 3?
- **Q15**: Should we set a "no-go decision point" at Week 6? (If M1-M3 aren't working, we reassess)

**Decision**: *(To be filled after team discussion)*

---

### Risk Analysis

**High-Impact Risks** (Could Block Phase 3):

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **Llama Stack API breaks** (RHOAI 3.4 EA1 → EA2 upgrade) | Medium | High | Abstract HIL gate behind interface, pin exact version |
| **NGC entitlements delayed** (Cosmos NIMs unavailable) | Medium | High | Start with M1-M3 (no Cosmos dependency), deploy mock API for M5 |
| **MCP protocol version mismatch** (LangGraph ↔ MCP server) | Medium | Medium | Use Anthropic's SDK, build M1 as validation spike |
| **L4 GPU unavailable** (provisioning delay) | Low | High | Validate GPU allocation before starting M1 |

**Medium-Impact Risks** (Could Delay, But Recoverable):

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| **TrustyAI eval latency > 10 sec** | High | Medium | Run eval async, show spinner, cache results |
| **GitHub API rate limits** | Low | Medium | Use dedicated bot account, rate-limit PRs to 10/hour |
| **Operator approval fatigue** (HIL UX issues) | Medium | Medium | Only state-modifying tools require approval |

---

### Implementation Readiness Checklist

Before starting Milestone 1, these **must** be true:

#### Infrastructure Readiness
- [ ] **L4 GPU allocated** (1× L4 with 24 GB VRAM available on hub cluster)
- [ ] **Postgres deployed** (either new instance or shared MLflow Postgres)
- [ ] **Vault access configured** (secrets for GitHub token, Postgres credentials)
- [ ] **vLLM deployment tested** (can we serve Llama-3.1-8B on L4 and hit < 5 sec latency?)

#### Dependency Readiness
- [ ] **Phase 2 complete** (20-minute demo runs reliably end-to-end)
- [ ] **MLflow operational** (API accessible, has experiment data for mcp-mlflow to query)
- [ ] **Fleet Manager API stable** (mcp-fleet needs read-only endpoints)
- [ ] **GitHub bot account created** (with permissions to create PRs in `infrastructure/gitops/`)

#### Team Readiness
- [ ] **LangGraph knowledge transfer** (team has read docs, understands graphs/checkpointers)
- [ ] **MCP protocol familiarity** (team has reviewed Anthropic's MCP examples)
- [ ] **HIL drawer design spec approved** (frontend engineer has reviewed 6-pane spec)

#### Architectural Alignment
- [ ] **Team alignment** on:
  - Agent brain LLM choice (Decision 1)
  - MCP SDK approach (Decision 2)
  - State persistence schema (Decision 3)
  - Milestone sequencing (Decision 5)

---

### Resource Requirements Validation

**Team Allocation**:
- **Backend Engineer** (Python, LangGraph, FastAPI): 1 FTE × 10 weeks
- **Frontend Engineer** (React, TypeScript, HIL drawer): 0.5 FTE × 10 weeks
- **ML/AI Engineer** (TrustyAI, Cosmos NIMs, model eval): 0.5 FTE × 10 weeks
- **Platform Engineer** (GitOps, Argo CD, GitHub API, Vault): 0.25 FTE × 10 weeks
- **QA/Integration Tester**: 0.25 FTE × weeks 9-12

**Total**: ~2.5 FTE over 10 weeks

**Infrastructure Requirements**:
- **GPU**: 1× L4 (24 GB) for agent brain, 2× L40S (48 GB each) for Cosmos NIMs (M5 only, not concurrent)
- **Compute** (non-GPU): 15 CPU, 26 GB RAM total (LangGraph + Llama Stack + MCP servers + TrustyAI)
- **Storage**: Postgres 20 GB, Nucleus 50 GB (Cosmos Transfer outputs)

**External Dependencies**:
- NGC Entitlements: Cosmos Predict 2.5, Cosmos Transfer 2.5 (for Milestone 5)
- GitHub: API access, bot account, CODEOWNERS approval workflow
- Vault: Secrets for GitHub token, Postgres credentials

**Questions for Team**:
- **Q16**: Do we have L4 GPU allocation confirmed? (Need to validate before Week 1)
- **Q17**: Do we have NGC entitlement timeline? (Informs whether M5 is feasible)
- **Q18**: Is 2.5 FTE realistic, or do we need to re-scope? (Current team capacity?)

**Decisions on Resource Allocation**: *(To be filled after team discussion)*

---

### Open Questions Summary

All questions from Pre-Implementation Decisions, consolidated:

**LLM Selection (Decision 1)**:
- Q1: Non-Meta model preference due to licensing/productization?
- Q2: Benchmark multiple models in M1, or commit to one?
- Q3: Quantization (int8/int4) acceptable, or full fp16 required?

**MCP Protocol (Decision 2)**:
- Q4: Red Hat productization concerns with Anthropic's SDK?
- Q5: Plan for MCP compatibility test suite across LLMs?
- Q6: Value in contributing to MCP SDK upstream?

**State Persistence (Decision 3)**:
- Q7: Normalize audit trail to separate `tool_calls` table, or JSONB array?
- Q8: Retention policy for `agent_sessions` (e.g., 90 days)?
- Q9: `hil_audit` in separate database for compliance isolation?

**Testing Strategy (Decision 4)**:
- Q10: 80% unit test coverage target, or 90%?
- Q11: Invest in test harness upfront (M1) or defer (M3)?
- Q12: How to validate latency targets in CI (need load testing)?

**Milestone Sequencing (Decision 5)**:
- Q13: Aligned on Critical Path (M1-M3 non-negotiable, M4-M5 negotiable)?
- Q14: NGC entitlements delayed → proceed with mock or pause Phase 3?
- Q15: Set no-go decision point at Week 6?

**Resource Validation**:
- Q16: L4 GPU allocation confirmed?
- Q17: NGC entitlement timeline available?
- Q18: 2.5 FTE realistic, or need to re-scope?

---

## Architecture Overview

### Two-Layer Agentic Stack

```
┌─────────────────────────────────────────────────────────┐
│ Operator (Showcase Console)                            │
│  - Natural language input                              │
│  - HIL Approval Drawer (6 panes)                       │
└────────────────┬────────────────────────────────────────┘
                 │
                 ↓
┌─────────────────────────────────────────────────────────┐
│ Llama Stack Governance Layer (ADR-019)                 │
│  - HIL approval gate for state-modifying tools         │
│  - Safety guardrails (PII scan, policy checks)         │
│  - TrustyAI evaluation integration                     │
│  - Audit trail (immutable, CAC/PIV-bound)              │
└────────────────┬────────────────────────────────────────┘
                 │
                 ↓
┌─────────────────────────────────────────────────────────┐
│ LangGraph Orchestrator (ADR-005)                       │
│  - Agent brain: vLLM-served LLM (L4 GPU)               │
│  - Tool calling via MCP protocol                       │
│  - State persistence: Postgres                         │
│  - Plan composition + execution                        │
└────────────────┬────────────────────────────────────────┘
                 │
        ┌────────┴────────┬──────────────┐
        ↓                 ↓              ↓
   ┌─────────┐      ┌──────────┐   ┌──────────┐
   │ mcp-    │      │ mcp-     │   │ mcp-     │
   │ fleet   │      │ isaac-sim│   │ mlflow   │
   └────┬────┘      └────┬─────┘   └────┬─────┘
        │                │              │
        ↓                ↓              ↓
  Fleet Manager    Isaac Sim       MLflow
```

### Agent-Opens-a-PR Pattern

```
1. Operator: "Promote v1.4 to Factory A"
         ↓
2. LangGraph: Plans approach
   - Queries mcp-mlflow (read-only: get v1.4 metrics)
   - Queries mcp-fleet (read-only: get Factory A state)
   - Proposes action: promote_model_version (state-modifying)
         ↓
3. Llama Stack: HIL gate triggered
   - Runs guardrails (PII scan, safety checks)
   - Computes blast radius (queries mcp-fleet)
   - Invokes TrustyAI eval (v1.4 vs v1.3 score)
         ↓
4. HIL Drawer Opens (6 panes populated)
   - Operator reviews proposed Git diff
   - Checks blast radius (1 factory, 3 robots)
   - Verifies MCP trace (what agent queried)
   - Sees guardrail outcomes (all PASS)
   - Reviews TrustyAI eval (0.87 vs 0.76)
         ↓
5. Operator: Clicks "Approve"
         ↓
6. Agent: Opens PR to infrastructure/gitops/
         ↓
7. PR merges (via GitHub API or webhook)
         ↓
8. Argo CD: Syncs Factory A to v1.4
         ↓
9. Audit record written (immutable, CAC/PIV-bound)
```

**Key Insight**: The agent never calls `oc apply`. Every change is Git-mediated. The cluster API is read-only from the agent's perspective.

---

## Implementation Strategy: Incremental Integration

Phase 3 is complex enough that a waterfall "build all components then integrate" approach will fail. Instead: **build the thinnest possible vertical slice first**, then expand.

### Milestone 1: "Hello World" Agent Loop (Weeks 1-2)

**Goal**: Operator types a read-only question, agent answers. No HIL, no state changes. Proves LangGraph → MCP → data source → response path works.

**Components**:
- LangGraph orchestrator (minimal: one agent, one tool)
- `mcp-mlflow` server (read-only tools only: `query_experiments`, `get_run_metrics`)
- Agent brain: vLLM serving `meta-llama/Llama-3.1-8B-Instruct` on L4
- Showcase Console: text input box + agent response panel

**Test Case**:
```
Operator: "What's the pick-success rate for vla-warehouse-v1.3?"
Agent: [Calls mcp-mlflow.get_run_metrics("v1.3")]
Agent: "Pick-success rate for v1.3 is 0.76 across 200 eval episodes."
```

**Success Criteria**:
- Agent can call MCP tool, parse response, generate natural-language answer
- Console displays agent's plan + tool calls + result
- Round-trip latency < 5 seconds p50

**Risk**: MCP protocol version mismatches, LangGraph tool-calling format issues. Mitigation: use well-known models (Llama 3.1/3.2 with proven tool-use) and vendor MCP SDKs.

---

### Milestone 2: Llama Stack HIL Gate (Weeks 3-4)

**Goal**: Operator asks agent to do something state-modifying. HIL gate triggers, drawer opens (simplified 3-pane version), operator approves, action executes.

**Components Added**:
- Llama Stack governance layer (minimal config: HIL enabled, guardrails placeholder)
- HIL drawer (3 panes only: proposed action summary, proposed diff, approve/reject buttons)
- `mcp-mlflow` state-modifying tool: `register_model` (safe, doesn't touch production)
- Audit trail: Postgres table (JSON blob per approval/rejection)

**Test Case**:
```
Operator: "Register the checkpoint from run abc123 as model 'test-vla'"
Agent: [Plans tool call to mcp-mlflow.register_model]
Llama Stack: [Classifies as state-modifying, triggers HIL]
HIL Drawer: Opens with:
  - Summary: "Register checkpoint abc123 as 'test-vla'"
  - Diff: (shows MLflow model registry entry JSON)
  - Buttons: Approve | Reject
Operator: [Clicks Approve]
Agent: [Executes mcp-mlflow.register_model]
Audit: Record written with operator identity + timestamp
```

**Success Criteria**:
- HIL gate correctly classifies read vs. write tools
- Drawer opens, displays real data (not placeholders)
- Approval triggers action; rejection blocks action
- Audit record written to Postgres

**Risk**: Llama Stack API surface is evolving (0.3.5 in RHOAI 3.4 EA1). Mitigation: pin to exact version, abstract HIL gate behind an interface so we can swap implementations if needed.

---

### Milestone 3: Agent-Opens-a-PR Pattern (Weeks 5-6)

**Goal**: Agent doesn't call cluster API directly — it opens a PR. Operator approves in drawer, PR merges, Argo CD syncs.

**Components Added**:
- GitHub API integration (create PR, merge PR)
- Kustomize overlay generator (MLflow model URI → InferenceService YAML)
- HIL drawer: add "Proposed Diff" pane showing actual Git diff
- `mcp-fleet` server (read-only tools: `get_fleet_status`, `get_factory_config`)

**Test Case**:
```
Operator: "Promote vla-warehouse-v1.4 to Factory A"
Agent: 
  1. Calls mcp-mlflow.get_run_metrics("v1.4") [read-only]
  2. Calls mcp-fleet.get_factory_config("factory-a") [read-only]
  3. Proposes: mcp-fleet.promote_policy_version (state-modifying)
Llama Stack: [HIL gate triggers]
HIL Drawer: Opens with:
  - Summary: "Promote v1.4 to Factory A"
  - Diff: (shows Git diff of policy-version.yaml)
  - MCP Trace: (lists steps 1-2 above)
Operator: [Approves]
Agent: [Opens PR to infrastructure/gitops/apps/workloads/factory-a/]
GitHub: PR created, auto-merged (via CODEOWNERS approval)
Argo CD: Syncs Factory A to v1.4
```

**Success Criteria**:
- Agent opens real PR (visible in GitHub UI)
- PR contains correct Kustomize overlay diff
- Argo CD picks up merged PR and syncs
- Audit record includes PR URL

**Risk**: GitHub token permissions, branch protection rules. Mitigation: use a dedicated bot account with limited scope (write to `infrastructure/gitops/apps/workloads/*` only).

---

### Milestone 4: Full HIL Drawer (6 Panes) + TrustyAI (Weeks 7-8)

**Goal**: HIL drawer shows all six panes per the design spec. TrustyAI evaluation runs on proposed policy vs. incumbent.

**Components Added**:
- HIL drawer: add remaining 3 panes (blast radius, guardrail outcomes, TrustyAI eval)
- Blast-radius analyzer (queries `mcp-fleet` to determine affected resources)
- TrustyAI integration (eval API call, score comparison)
- Llama Stack guardrails: PII scan (via Presidio or equivalent), safety policy checks

**Test Case**:
```
Same as Milestone 3, but drawer now shows:
  1. Proposed Action Summary
  2. Proposed Diff (Git)
  3. Blast Radius:
     - Affected factories: Factory A (companion cluster)
     - Affected robots: 3 (G1-01, G1-02, G1-03)
     - Rollback path: git revert (measured <20s)
  4. MCP Trace: (tool calls 1-2 from Milestone 3)
  5. Guardrail Outcomes:
     - PII scan: PASS
     - Safety policy: PASS
  6. TrustyAI Eval:
     - Proposed (v1.4): 0.87
     - Incumbent (v1.3): 0.76
     - Improvement: +14%
```

**Success Criteria**:
- All 6 panes populated from real data sources
- Blast-radius query completes < 2 seconds
- TrustyAI eval completes < 10 seconds (or shows "evaluating..." spinner)
- Guardrail failure blocks approval (test with injected PII)

**Risk**: TrustyAI eval latency. If evaluation takes 60+ seconds, the drawer UX breaks. Mitigation: run eval asynchronously, show progress indicator, allow operator to approve "pending eval" with a warning.

---

### Milestone 5: Cosmos NIMs + Synthetic Data Pipeline (Weeks 9-10)

**Goal**: Segment 1 of 60-min demo runs — Cosmos Predict 2.5 as pre-dispatch admission check, Cosmos Transfer 2.5 generating scenario variations.

**Components Added**:
- Cosmos Predict 2.5 NIM (KServe InferenceService on L40S)
- Cosmos Transfer 2.5 NIM (KServe InferenceService on L40S, not concurrent with Predict — see GPU scheduling doc)
- `mcp-isaac-sim` server (tools: `list_scenes`, `launch_sim_run`, `generate_scenario_manifest`)
- Mission admission hook: Fleet Manager calls Cosmos Predict before dispatching

**Test Case (Cosmos Predict Admission)**:
```
Fleet Manager: Receives mission "Retrieve pallet A47 via aisle-3"
Fleet Manager: Calls Cosmos Predict NIM with mission params
Cosmos Predict: Simulates mission, predicts collision at t=12s
Fleet Manager: Rejects mission, proposes alternate via aisle-4
```

**Test Case (Cosmos Transfer)**:
```
Operator (via agent): "Generate night-lighting variant of warehouse scene"
Agent: Calls mcp-isaac-sim.generate_scenario_manifest
Isaac Sim: Exports base scene frames
Agent: Calls Cosmos Transfer NIM with frames + "night lighting" prompt
Cosmos Transfer: Returns 4 variant images
Agent: Uploads to Nucleus, registers in MLflow as dataset
```

**Success Criteria**:
- Cosmos Predict rejects unsafe mission (measured, not aspirational)
- Cosmos Transfer produces 4 visually distinct variants in < 60s
- Variants are consumable by Isaac Lab training pipeline
- GPU scheduling: only 1 Cosmos NIM runs at a time (documented in `docs/08-gpu-resource-planning.md`)

**Risk**: NGC entitlement delays. Mitigation: if NIMs unavailable, use placeholder REST API (returns mock data) and document as "NIM integration pending NGC access."

---

## Component Breakdown

### 1. LangGraph Orchestrator

**Repository**: `workloads/agentic-orchestrator/`

**Tech Stack**:
- Python 3.11+
- LangGraph 0.2.x
- vLLM serving `meta-llama/Llama-3.1-8B-Instruct` (or `Llama-3.2-3B-Instruct` for lower memory footprint)
- Postgres for state persistence

**Key Files**:
- `src/agentic_orchestrator/agent.py` — LangGraph graph definition
- `src/agentic_orchestrator/tools.py` — MCP tool wrappers
- `src/agentic_orchestrator/planner.py` — Plan composition logic
- `src/agentic_orchestrator/state.py` — Agent session state schema

**Deployment**:
- Helm chart: `infrastructure/gitops/apps/workloads/agentic-orchestrator/`
- Namespace: `agentic-ops`
- Resources: 2 CPU, 4 GB RAM (agent logic is lightweight; LLM is separate pod)
- Service: ClusterIP, port 8080
- Service Mesh: sidecar injected, mTLS enforced

**Environment Variables**:
```yaml
MCP_FLEET_URL: http://mcp-fleet.agentic-ops.svc:8081
MCP_ISAAC_SIM_URL: http://mcp-isaac-sim.agentic-ops.svc:8082
MCP_MLFLOW_URL: http://mcp-mlflow.agentic-ops.svc:8083
LLAMA_STACK_URL: http://llama-stack.agentic-ops.svc:8090
AGENT_BRAIN_URL: http://vllm-agent-brain.agentic-ops.svc:8000/v1
POSTGRES_SECRET: vault-agentic-orchestrator-db
GITHUB_TOKEN_SECRET: vault-github-bot-token
```

**State Schema** (Postgres table `agent_sessions`):
```sql
CREATE TABLE agent_sessions (
  session_id UUID PRIMARY KEY,
  operator_identity TEXT NOT NULL,
  started_at TIMESTAMP NOT NULL,
  updated_at TIMESTAMP NOT NULL,
  state JSONB NOT NULL, -- LangGraph checkpointer state
  audit_trail JSONB[] NOT NULL -- array of tool calls + results
);
```

**Tool Call Format** (MCP protocol):
```json
{
  "tool": "mcp-mlflow.get_run_metrics",
  "parameters": {
    "run_id": "abc123",
    "metrics": ["pick_success_rate", "grasp_precision"]
  }
}
```

**Open Questions**:
- Which LLM to use for agent brain? Options:
  - `Llama-3.1-8B-Instruct` (proven tool-use, fits L4 24GB in bfloat16)
  - `Llama-3.2-3B-Instruct` (smaller, faster, less capable)
  - `Qwen2.5-7B-Instruct` (excellent tool-use benchmarks, non-Meta)
  - **Recommendation**: Start with Llama 3.1-8B; fall back to 3.2-3B if memory pressure.

---

### 2. Llama Stack Governance Layer

**Repository**: `workloads/llama-stack/`

**Tech Stack**:
- RHOAI 3.4 EA1 ships Llama Stack 0.3.5
- Python 3.11+
- Llama Stack Agents API
- Presidio for PII detection (or Llama Guard for safety)

**Key Files**:
- `src/llama_stack/hil_gate.py` — HIL approval logic
- `src/llama_stack/guardrails.py` — PII scan, safety checks
- `src/llama_stack/audit.py` — Immutable audit trail writer
- `src/llama_stack/blast_radius.py` — Queries MCP to compute impact

**Deployment**:
- Helm chart: `infrastructure/gitops/apps/workloads/llama-stack/`
- Namespace: `agentic-ops`
- Resources: 4 CPU, 8 GB RAM
- Service: ClusterIP, port 8090

**Guardrail Pipeline**:
```python
def evaluate_proposal(tool_call, context):
    # 1. PII scan on tool parameters
    pii_result = presidio_scan(tool_call.parameters)
    if pii_result.has_pii:
        return GuardrailFailure("PII detected in parameters")
    
    # 2. Safety policy check
    safety_result = check_safety_policy(tool_call)
    if not safety_result.safe:
        return GuardrailFailure(safety_result.reason)
    
    # 3. Blast-radius analysis (queries mcp-fleet)
    blast_radius = compute_blast_radius(tool_call)
    
    # 4. TrustyAI evaluation (if model promotion)
    if tool_call.tool == "mcp-mlflow.promote_model_version":
        eval_score = trustyai_eval(
            proposed_model=tool_call.parameters.model,
            incumbent_model=get_current_production_model()
        )
    else:
        eval_score = None
    
    return GuardrailPass(
        blast_radius=blast_radius,
        eval_score=eval_score
    )
```

**Audit Record Schema** (Postgres table `hil_audit`):
```sql
CREATE TABLE hil_audit (
  action_id UUID PRIMARY KEY,
  timestamp TIMESTAMP NOT NULL,
  session_id UUID REFERENCES agent_sessions(session_id),
  operator_identity TEXT NOT NULL, -- CAC/PIV cert DN or OAuth sub
  tool_call JSONB NOT NULL,
  classification TEXT NOT NULL, -- 'read-only' | 'state-modifying'
  guardrail_results JSONB NOT NULL,
  decision TEXT NOT NULL, -- 'approved' | 'rejected'
  rejection_reason TEXT, -- populated if decision='rejected'
  pr_url TEXT, -- populated if agent-opens-PR pattern
  context_trail_hash TEXT NOT NULL -- sha256 of MCP trace
);
```

**CAC/PIV Identity Binding**:
- In production: extract DN from client certificate
- In demo: use OpenShift OAuth token `sub` claim
- Store raw cert or token in separate `identity_proofs` table (WORM storage)

**Open Questions**:
- PII detection: Presidio vs. Llama Guard? Presidio is rule-based (fast, deterministic), Llama Guard is LLM-based (slower, more nuanced).
  - **Recommendation**: Start with Presidio for Phase 3 (latency budget), evaluate Llama Guard in Phase 4.

---

### 3. MCP Servers

Each MCP server is a standalone FastAPI service that exposes tools via the MCP protocol.

#### 3a. `mcp-mlflow`

**Purpose**: Read MLflow experiments, runs, metrics; register and promote models.

**Tools**:
```python
# Read-only
query_experiments(name_filter: str) -> List[Experiment]
get_run_metrics(run_id: str, metrics: List[str]) -> Dict[str, float]
get_model_versions(model_name: str) -> List[ModelVersion]

# State-modifying
register_model(run_id: str, model_name: str) -> ModelVersion
promote_model_version(model_name: str, version: str, stage: str) -> None
```

**Deployment**:
- Namespace: `agentic-ops`
- Resources: 1 CPU, 2 GB RAM
- Connects to: MLflow service in `mlflow` namespace

#### 3b. `mcp-fleet`

**Purpose**: Query fleet status; propose fleet interventions.

**Tools**:
```python
# Read-only
get_fleet_status(factory: str = None) -> FleetStatus
get_factory_config(factory: str) -> FactoryConfig
get_robot_telemetry(robot_id: str, hours: int = 24) -> Telemetry
get_anomaly_history(factory: str, hours: int = 24) -> List[Anomaly]

# State-modifying
override_mission_params(factory: str, params: Dict) -> None
propose_fleet_intervention(factory: str, action: str, robots: List[str]) -> None
promote_policy_version(factory: str, version: str) -> None  # opens PR
```

**Deployment**:
- Namespace: `agentic-ops`
- Resources: 1 CPU, 2 GB RAM
- Connects to: Fleet Manager API, Kafka (for status queries)

**Special Case: `promote_policy_version`**:
This tool **does not** call the cluster API. Instead:
1. Generates Kustomize overlay diff
2. Opens PR to `infrastructure/gitops/apps/workloads/{factory}/`
3. Returns PR URL
4. GitHub webhook → Argo CD syncs on merge

#### 3c. `mcp-isaac-sim`

**Purpose**: Launch sim runs, generate scenario manifests, query scene library.

**Tools**:
```python
# Read-only
list_scenes() -> List[Scene]
get_scenario_manifest(scenario_id: str) -> Manifest

# State-modifying
launch_sim_run(scene: str, policy: str, episodes: int) -> RunID
generate_scenario_manifest(base_scene: str, variations: List[str]) -> Manifest
```

**Deployment**:
- Namespace: `agentic-ops`
- Resources: 1 CPU, 2 GB RAM
- Connects to: Isaac Sim headless API, Nucleus (for scene assets)

**Note**: `launch_sim_run` is state-modifying (spins up GPU workload), so triggers HIL gate.

---

### 4. HIL Approval Drawer (Showcase Console)

**Location**: `workloads/showcase-console/frontend/src/components/HILDrawer.tsx`

**State Management**: React Context + WebSocket to backend

**Six Panes** (per design spec):

#### Pane 1: Proposed Action Summary
- Agent's natural-language explanation
- Example: "Promote vla-warehouse-v1.4 to Factory A based on 14% pick-success improvement"

#### Pane 2: Proposed Diff
- Git diff if agent-opens-PR pattern
- YAML diff if Kustomize overlay
- JSON diff if MLflow model registry

#### Pane 3: Blast-Radius Analysis
- Table format:
  ```
  Affected Factories: Factory A (companion cluster)
  Affected Robots: 3 (G1-01, G1-02, G1-03)
  Rollback Path: git revert + Argo sync (<20s measured)
  Service Disruption: None (hot-swap, no pod restart)
  ```

#### Pane 4: MCP Tool-Call Trace
- Chronological list of read-only tool calls:
  ```
  1. mcp-mlflow: get_run_metrics("v1.4") → pick_success=0.87
  2. mcp-fleet: get_factory_config("factory-a") → 3 robots
  3. mcp-fleet: get_anomaly_history("factory-a", 24h) → 0 anomalies
  ```
- Each entry links to source (MLflow run URL, fleet status snapshot)

#### Pane 5: Guardrail Outcomes
- Table format:
  ```
  PII Scan: PASS (no PII detected)
  Safety Policy: PASS (no violations)
  Blocked Tool Calls: 0
  ```
- If any guardrail fails, the "Approve" button is disabled

#### Pane 6: TrustyAI Eval + CAC/PIV Identity
- Proposed vs. incumbent score
- Operator identity (from OAuth or client cert)
- Timestamp
- Approval will write immutable audit record

**Drawer Behavior**:
- Opens on right side (~480px width)
- Expand-to-full-page toggle for large diffs
- No timeout — pending approval persists until operator acts
- "Reject" requires reason (textarea input)

**Backend API** (`workloads/showcase-console/backend/src/routes/hil.ts`):
```typescript
POST /api/hil/approve
{
  action_id: string,
  operator_identity: string,
  signature?: string  // for CAC/PIV environments
}

POST /api/hil/reject
{
  action_id: string,
  operator_identity: string,
  reason: string
}

GET /api/hil/pending
→ List<PendingApproval>
```

**Open Questions**:
- Drawer refresh behavior: if blast-radius data is 30 minutes stale, do we re-query on approval?
  - **Recommendation**: Show staleness warning if drawer open > 10 minutes, offer "Refresh Analysis" button.

---

### 5. TrustyAI Integration

**Purpose**: Evaluate proposed model vs. incumbent on held-out scenario suite.

**Deployment**:
- RHOAI 3.4 EA1 includes TrustyAI operator
- Custom evaluation pipeline: `workloads/trustyai-eval/`

**Evaluation Flow**:
```python
def evaluate_model(model_uri: str, scenario_suite: str) -> float:
    # 1. Load model from MLflow
    model = mlflow.pyfunc.load_model(model_uri)
    
    # 2. Load scenario suite from Nucleus
    scenarios = load_scenarios(scenario_suite)
    
    # 3. Run model on each scenario, measure success rate
    results = []
    for scenario in scenarios:
        result = run_scenario(model, scenario)
        results.append(result.success)
    
    # 4. Return aggregate score
    return sum(results) / len(results)
```

**Latency Budget**:
- Target: < 10 seconds for 20-scenario suite
- If exceeds, show "Evaluating..." spinner in HIL drawer
- Cache eval results for 1 hour (same model + same suite = cached)

**Integration Point**:
- Llama Stack calls TrustyAI eval API when tool is `mcp-mlflow.promote_model_version`
- Eval score displayed in HIL drawer Pane 6

**Open Questions**:
- Scenario suite selection: fixed suite per factory, or dynamic based on recent failures?
  - **Recommendation**: Fixed suite for Phase 3 (deterministic eval), dynamic in Phase 4.

---

### 6. Cosmos NIMs

#### 6a. Cosmos Predict 2.5

**Purpose**: World-model simulation for pre-dispatch mission admission.

**Deployment**:
- KServe InferenceService
- Namespace: `cosmos-nims`
- GPU: 1x L40S (48 GB)
- Model: `nvcr.io/nvidia/cosmos/predict:2.5`

**Integration**:
- Fleet Manager calls Cosmos Predict **before** dispatching mission
- If predicted outcome violates safety/latency envelope, mission rejected

**Example Call**:
```python
# Fleet Manager receives mission
mission = {
  "robot_id": "fl-07",
  "action": "retrieve_pallet",
  "pallet_id": "A47",
  "route": ["dock-b", "aisle-3", "storage-a"]
}

# Call Cosmos Predict
prediction = cosmos_predict_client.predict(
  scene_state=get_current_scene_state(),
  mission=mission,
  horizon_seconds=60
)

# Check prediction
if prediction.collision_detected or prediction.duration > mission.sla:
  # Reject mission, propose alternate
  alternate_mission = replan_mission(mission, avoid=prediction.collision_location)
  return alternate_mission
else:
  # Dispatch mission
  dispatch_to_robot(mission)
```

**GPU Scheduling Note**:
- Cosmos Predict and Cosmos Transfer both require L40S
- **Cannot run concurrently** in demo environment (only 2-3 L40S total, Isaac Sim + Kit streaming consume 1-2)
- Mitigation: deploy one at a time, or use `PriorityClass` to preempt lower-priority workloads

#### 6b. Cosmos Transfer 2.5

**Purpose**: Generate synthetic scenario variations (lighting, weather, clutter).

**Deployment**:
- KServe InferenceService
- Namespace: `cosmos-nims`
- GPU: 1x L40S (48 GB)
- Model: `nvcr.io/nvidia/cosmos/transfer:2.5`

**Integration**:
- Agent calls `mcp-isaac-sim.generate_scenario_manifest`
- Isaac Sim exports base scene frames
- MCP server calls Cosmos Transfer with frames + variation prompt
- Cosmos Transfer returns augmented images
- MCP server uploads to Nucleus, registers in MLflow

**Example Call**:
```python
# Base scene frames
frames = isaac_sim.export_frames(scene="warehouse", camera="aisle-3", count=10)

# Variation prompts
variations = [
  "night lighting, dark warehouse, minimal ambient light",
  "rainy loading dock, wet floors, puddles",
  "morning fog, reduced visibility",
  "busy warehouse, workers in background"
]

# Generate variants
for i, prompt in enumerate(variations):
  variant_frames = cosmos_transfer_client.transfer(
    source_frames=frames,
    target_description=prompt
  )
  
  # Upload to Nucleus
  nucleus.upload(f"warehouse_variants/variant_{i}/", variant_frames)
  
  # Register in MLflow
  mlflow.log_artifact(f"warehouse_variants/variant_{i}/", run_id=current_run)
```

---

## Testing Strategy

### Unit Tests (Per Component)

Each component has its own test suite:
- `workloads/agentic-orchestrator/tests/` — LangGraph tool calling, plan composition
- `workloads/llama-stack/tests/` — HIL gate logic, guardrail evaluation
- `workloads/mcp-*/tests/` — MCP tool endpoints, read/write classification

**Coverage Target**: 80% line coverage minimum

### Integration Tests (Cross-Component)

**Test Suite 1: Read-Only Agent Query**
```gherkin
Given LangGraph orchestrator is running
And mcp-mlflow is running
When operator asks "What's the pick-success rate for v1.3?"
Then agent should call mcp-mlflow.get_run_metrics
And agent should return natural-language answer
And no HIL gate should trigger
And response time < 5 seconds p50
```

**Test Suite 2: HIL Gate Triggers**
```gherkin
Given LangGraph + Llama Stack running
When agent proposes state-modifying tool call
Then Llama Stack should intercept
And HIL drawer should open
And all 6 panes should be populated
And "Approve" button should be enabled (if guardrails pass)
```

**Test Suite 3: Agent Opens PR**
```gherkin
Given operator approves HIL request
When agent executes mcp-fleet.promote_policy_version
Then PR should be created in GitHub
And PR diff should match proposed change
And PR should auto-merge (CODEOWNERS approval)
And Argo CD should sync within 30 seconds
```

**Test Suite 4: Guardrail Failure Blocks**
```gherkin
Given tool call parameters contain PII
When Llama Stack evaluates guardrails
Then PII scan should FAIL
And HIL drawer should show guardrail failure
And "Approve" button should be disabled
```

### End-to-End Tests (60-Min Demo Segments)

Each segment of the 60-min demo has a rehearsal script:

**Segment 1 Rehearsal** (Cosmos Predict + Transfer):
- [ ] Cosmos Predict rejects unsafe mission
- [ ] Cosmos Transfer generates 4 variants in < 60s
- [ ] Variants uploaded to Nucleus
- [ ] Variants registered in MLflow

**Segment 2 Rehearsal** (Agentic HIL):
- [ ] Read-only query completes in < 5s
- [ ] State-modifying query triggers HIL
- [ ] All 6 drawer panes populated
- [ ] Approval opens PR
- [ ] PR merges, Argo syncs

**Segment 3 Rehearsal** (Security):
- [ ] Tampered artifact rejected at admission
- [ ] Air-gap walkthrough runs on companion
- [ ] Compliance evidence displays in Console
- [ ] Policy-artifact provenance chain navigable

**Segment 4 Rehearsal** (VLA swap + trace):
- [ ] Kustomize overlay swap completes
- [ ] New model profile visible in KServe
- [ ] End-to-end mission trace in Tempo

---

## Risk Register

### Risk 1: Llama Stack API Evolution (HIGH)

**Problem**: RHOAI 3.4 EA1 ships Llama Stack 0.3.5. Upstream is moving fast; API may change.

**Mitigation**:
- Pin exact version in deployment
- Abstract HIL gate behind interface (`workloads/llama-stack/src/llama_stack/hil_gate.py`)
- If API breaks, implement shim layer or swap to alternative HIL implementation

**Fallback**: If Llama Stack unusable, implement custom HIL gate (Postgres-backed approval queue + FastAPI)

---

### Risk 2: TrustyAI Eval Latency (MEDIUM)

**Problem**: Evaluating proposed model on 20+ scenarios may take 30-60 seconds.

**Mitigation**:
- Run eval asynchronously (show spinner in drawer)
- Cache eval results (same model + same suite = cached for 1 hour)
- Pre-compute eval scores for known model versions during training

**Fallback**: Skip TrustyAI eval in Phase 3, show placeholder "Eval score: pending" in drawer, complete in Phase 4.

---

### Risk 3: MCP Protocol Version Mismatch (MEDIUM)

**Problem**: LangGraph's MCP client expects different format than MCP server emits.

**Mitigation**:
- Use well-known MCP SDKs (Anthropic's `mcp` Python package)
- Test with multiple LLMs (Llama 3.1, Qwen 2.5) to verify tool-calling compatibility
- Document exact MCP protocol version in `workloads/mcp-*/README.md`

**Fallback**: If MCP breaks, implement simpler JSON-RPC tool protocol.

---

### Risk 4: NGC Entitlement Delays (HIGH)

**Problem**: Cosmos Predict/Transfer NIMs require NGC entitlement. May not be available at Phase 3 start.

**Mitigation**:
- Start Milestones 1-4 (agentic layer) first — Cosmos NIMs land in Milestone 5
- If entitlement unavailable, deploy mock Cosmos API (returns placeholder predictions/images)
- Document as "NIM integration pending NGC access" in demo script

**Fallback**: Defer Segment 1 of 60-min demo to Phase 4, deliver Segments 2-4 only in Phase 3.

---

### Risk 5: GitHub API Rate Limits (LOW)

**Problem**: Agent opening many PRs could hit GitHub rate limit (5000/hour for authenticated user).

**Mitigation**:
- Use dedicated bot account (separate from human users)
- Cache PR results (don't re-open identical PRs)
- Rate-limit agent tool calls (max 10 PRs/hour)

**Fallback**: If rate limit hit, queue PR requests, process in batches.

---

### Risk 6: Operator Approval Fatigue (MEDIUM, long-term)

**Problem**: If every agent action requires approval, operators stop paying attention ("click through" without reading).

**Mitigation** (Phase 3):
- Only state-modifying tools require approval
- Read-only queries pass through instantly
- Drawer shows enough context to make informed decision

**Future Enhancement** (Phase 4+):
- Risk-based approval: low-risk actions (register test model) auto-approve
- Approval delegation: junior operator forwards to senior for high-risk actions
- Batch approvals: "approve all 3 pending Factory A policy updates"

---

## Known Gaps & Phase 4+ Enhancements

### Gap 1: Multi-Operator Workflows

**Current State** (Phase 3): Single-operator approval. If operator A starts session, only operator A can approve.

**Production Requirement**: 
- Shift handoffs (operator A starts, operator B approves)
- Escalation (junior → senior)
- Notifications (Slack when HIL pending)

**Phase 4 Enhancement**:
- RBAC-gated approval (any operator with role `fleet-approver` can approve any pending request)
- Notification webhooks (Slack/email on HIL trigger)
- Approval queue UI (all pending approvals visible to all operators)

---

### Gap 2: Rollback of Approved Actions

**Current State** (Phase 3): Auto-rollback on detected anomaly (Phase 2 feature). No operator-initiated rollback of approved HIL actions.

**Scenario**: Operator approves "promote v1.4 to Factory A" at 10:00. At 10:15, realizes it was wrong (misread eval score). No easy undo.

**Phase 4 Enhancement**:
- "Recent Approvals" panel in Console
- One-click revert (opens revert PR, same workflow)
- Audit trail links original approval to revert

---

### Gap 3: Agent Memory Across Sessions

**Current State** (Phase 3): Each agent session is independent. Agent doesn't remember previous approvals/rejections.

**Scenario**: Agent proposes action X, operator rejects with reason "don't promote during shift change." Next day, agent proposes same action at same time, no memory of rejection.

**Phase 4 Enhancement**:
- Long-term memory store (vector DB of approval/rejection history)
- Agent queries memory before proposing (RAG-style)
- "You rejected this action yesterday with reason X. That concern still applies?"

---

### Gap 4: Batch Approvals

**Current State** (Phase 3): Drawer shows one proposal at a time. Agent blocks until operator acts.

**Scenario**: Agent wants to promote policy to Factory A, then Factory B, then Factory C. Operator must approve three times in sequence.

**Phase 4 Enhancement**:
- Agent proposes batch: "promote to all 3 factories"
- Single HIL drawer with combined blast radius
- One approval merges 3 PRs
- Trade-off: simpler for operator, more complex audit trail

---

## Success Criteria (Phase 3 Exit)

Phase 3 is **complete** when all of these are true:

### Demo Criteria

1. ✅ **60-minute demo runs end-to-end live** on hub + companion + spoke clusters
2. ✅ **Segment 1 (Cosmos)**: Cosmos Predict rejects unsafe mission, Cosmos Transfer generates variants, Isaac Lab trains on augmented data
3. ✅ **Segment 2 (Agentic HIL)**: Operator asks NL question, agent proposes state-modifying action, HIL drawer opens with all 6 panes populated from real data, operator approves, PR merges, Argo syncs
4. ✅ **Segment 3 (Security)**: Tampered artifact rejected at admission (live event trace visible), air-gap walkthrough on companion, Compliance Operator scan results in Console, policy-artifact provenance chain navigable
5. ✅ **Segment 4 (VLA swap)**: Kustomize overlay swap live, new model visible in KServe, end-to-end mission trace in Tempo

### Technical Criteria

6. ✅ **HIL drawer behaves per design spec**: 6 panes, all real data (no placeholders), approval writes audit record with CAC/PIV identity, rejection requires reason
7. ✅ **Agent-opens-PR pattern works**: Agent never calls cluster API directly, all state changes via Git, PR URL in audit record
8. ✅ **Llama Stack governance on GitOps path only**: Measured VLA inference latency p99 is **independent** of HIL enablement (governance adds zero latency to serving-time robot command flow)
9. ✅ **Guardrail failure blocks approval**: Injected PII triggers guardrail fail, drawer shows failure, "Approve" button disabled
10. ✅ **TrustyAI eval completes**: Proposed vs. incumbent score displayed in drawer (or "evaluating..." if async)

### Deliverable Criteria

11. ✅ **`demos/60-min-deep-dive/script.md` runs live + recorded**: Recorded fallback has all 4 segments, timed to match script
12. ✅ **Performance envelope doc v2**: HIL round-trip latency (drawer open → approval → PR merge → Argo sync), agentic flow end-to-end, VLA hot-swap measured p50/p99
13. ✅ **Blog post series (3 minimum)**: Agent-opens-PR pattern, synthetic-data factory, policy provenance chain
14. ✅ **Phase 3 components documented**: ADR for any new decisions, component catalog updated, `workloads/*/README.md` complete

### Quality Criteria

15. ✅ **Integration test suite passes**: All 4 test suites (read-only query, HIL gate, agent-opens-PR, guardrail failure) green
16. ✅ **Segment rehearsals complete**: Each 60-min segment rehearsed 3+ times, timing validated
17. ✅ **No placeholders in HIL drawer**: If a pane can't be populated with real data, the beat is cut (don't ship fake UX)

---

## Timeline (8-10 Weeks)

### Weeks 1-2: Milestone 1 (Hello World Agent)
- LangGraph orchestrator (minimal)
- `mcp-mlflow` (read-only tools)
- Agent brain (vLLM Llama 3.1-8B on L4)
- Console text input + response panel
- **Deliverable**: Read-only agent query works end-to-end

### Weeks 3-4: Milestone 2 (HIL Gate)
- Llama Stack deployment
- HIL drawer (3 panes)
- `mcp-mlflow` state-modifying tool
- Audit trail (Postgres)
- **Deliverable**: HIL gate triggers, operator approves/rejects

### Weeks 5-6: Milestone 3 (Agent Opens PR)
- GitHub API integration
- Kustomize overlay generator
- `mcp-fleet` server (read + write tools)
- HIL drawer: add Git diff pane
- **Deliverable**: Agent opens PR, Argo syncs

### Weeks 7-8: Milestone 4 (Full Drawer + TrustyAI)
- HIL drawer: 3 remaining panes (blast radius, guardrails, TrustyAI)
- Blast-radius analyzer
- TrustyAI integration
- Llama Stack guardrails (PII scan)
- **Deliverable**: Full 6-pane drawer with real data

### Weeks 9-10: Milestone 5 (Cosmos NIMs)
- Cosmos Predict 2.5 deployment + mission admission hook
- Cosmos Transfer 2.5 deployment + scenario variation pipeline
- `mcp-isaac-sim` server
- **Deliverable**: Segment 1 of 60-min demo works

### Weeks 11-12: Integration, Rehearsal, Polish (BUFFER)
- End-to-end integration testing
- 60-min demo rehearsals (all 4 segments)
- Performance measurements (latency, GPU utilization)
- Blog posts + docs
- **Deliverable**: Phase 3 exit criteria met

---

## Resource Requirements

### Team

- **Backend Engineer** (Python, LangGraph, FastAPI): 1 FTE for 10 weeks
- **Frontend Engineer** (React, TypeScript, HIL drawer): 0.5 FTE for 10 weeks
- **ML/AI Engineer** (TrustyAI, Cosmos NIMs, model eval): 0.5 FTE for 10 weeks
- **Platform Engineer** (GitOps, Argo CD, GitHub API, Vault): 0.25 FTE for 10 weeks
- **QA/Integration Tester**: 0.25 FTE for weeks 9-12

**Total**: ~2.5 FTE over 10 weeks

### Infrastructure

**GPU Allocation** (see `docs/08-gpu-resource-planning.md`):
- **L4**: 1 GPU for agent brain (vLLM Llama 3.1-8B)
- **L40S**: 2 GPUs for Cosmos Predict + Transfer (not concurrent)

**Compute** (non-GPU):
- LangGraph orchestrator: 2 CPU, 4 GB RAM
- Llama Stack: 4 CPU, 8 GB RAM
- MCP servers (3x): 3 CPU, 6 GB RAM total
- TrustyAI eval workers: 4 CPU, 8 GB RAM

**Storage**:
- Postgres (agent sessions + audit trail): 20 GB
- Cosmos Transfer outputs (cached): 50 GB (Nucleus storage)

### External Dependencies

- **NGC Entitlements**: Cosmos Predict 2.5, Cosmos Transfer 2.5
- **GitHub**: API access, bot account, CODEOWNERS approval workflow
- **Vault**: Secrets for GitHub token, Postgres credentials

---

## Appendix A: MCP Tool Classification Matrix

| MCP Server | Tool | Classification | Triggers HIL? | Reason |
|------------|------|---------------|---------------|--------|
| mcp-mlflow | query_experiments | read-only | No | Query only, no state change |
| mcp-mlflow | get_run_metrics | read-only | No | Query only |
| mcp-mlflow | get_model_versions | read-only | No | Query only |
| mcp-mlflow | register_model | state-modifying | Yes | Creates MLflow model registry entry |
| mcp-mlflow | promote_model_version | state-modifying | Yes | Changes model stage (to Production) |
| mcp-fleet | get_fleet_status | read-only | No | Query only |
| mcp-fleet | get_factory_config | read-only | No | Query only |
| mcp-fleet | get_robot_telemetry | read-only | No | Query only |
| mcp-fleet | get_anomaly_history | read-only | No | Query only |
| mcp-fleet | override_mission_params | state-modifying | Yes | Changes factory config (speed limits, etc.) |
| mcp-fleet | propose_fleet_intervention | state-modifying | Yes | Reassigns robots, changes zones |
| mcp-fleet | promote_policy_version | state-modifying | Yes | Opens PR to change policy-version.yaml |
| mcp-isaac-sim | list_scenes | read-only | No | Query only |
| mcp-isaac-sim | get_scenario_manifest | read-only | No | Query only |
| mcp-isaac-sim | launch_sim_run | state-modifying | Yes | Spins up GPU workload (Isaac Lab Job) |
| mcp-isaac-sim | generate_scenario_manifest | state-modifying | Yes | Calls Cosmos Transfer, uploads to Nucleus |

**Rule**: Any tool that creates, updates, or deletes cluster resources, opens PRs, or launches workloads is **state-modifying** and triggers HIL.

---

## Appendix B: Guardrail Evaluation Logic

```python
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

class GuardrailEvaluator:
    def __init__(self):
        self.pii_analyzer = AnalyzerEngine()
        self.pii_anonymizer = AnonymizerEngine()
    
    def evaluate(self, tool_call, context):
        """
        Evaluate guardrails for a proposed tool call.
        Returns GuardrailResult.
        """
        results = {
            "pii_scan": self._scan_pii(tool_call),
            "safety_policy": self._check_safety(tool_call),
            "blocked_tools": self._check_blocked_tools(tool_call),
        }
        
        # If any guardrail fails, approval blocked
        if any(not r.passed for r in results.values()):
            return GuardrailResult(
                passed=False,
                failures=[r for r in results.values() if not r.passed]
            )
        
        return GuardrailResult(passed=True, results=results)
    
    def _scan_pii(self, tool_call) -> GuardrailCheck:
        """
        Scan tool call parameters for PII.
        Uses Presidio to detect names, emails, phone numbers, SSNs, etc.
        """
        # Flatten tool call to text
        text = json.dumps(tool_call.parameters)
        
        # Analyze
        results = self.pii_analyzer.analyze(
            text=text,
            language="en",
            entities=["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "US_SSN"]
        )
        
        if results:
            return GuardrailCheck(
                name="pii_scan",
                passed=False,
                detail=f"PII detected: {[r.entity_type for r in results]}"
            )
        
        return GuardrailCheck(
            name="pii_scan",
            passed=True,
            detail="No PII detected"
        )
    
    def _check_safety(self, tool_call) -> GuardrailCheck:
        """
        Check tool call against safety policy.
        Example policies:
        - Don't promote models during shift change (6-7am, 2-3pm, 10-11pm)
        - Don't override mission params that increase speed > 2.0 m/s
        - Don't launch sim runs > 1000 episodes (resource limit)
        """
        # Check time-based policy
        current_hour = datetime.now().hour
        if current_hour in [6, 14, 22]:  # shift change hours
            if tool_call.tool == "mcp-fleet.promote_policy_version":
                return GuardrailCheck(
                    name="safety_policy",
                    passed=False,
                    detail="Policy promotion blocked during shift change"
                )
        
        # Check parameter-based policy
        if tool_call.tool == "mcp-fleet.override_mission_params":
            if tool_call.parameters.get("max_speed", 0) > 2.0:
                return GuardrailCheck(
                    name="safety_policy",
                    passed=False,
                    detail="Speed override > 2.0 m/s not allowed"
                )
        
        if tool_call.tool == "mcp-isaac-sim.launch_sim_run":
            if tool_call.parameters.get("episodes", 0) > 1000:
                return GuardrailCheck(
                    name="safety_policy",
                    passed=False,
                    detail="Sim runs > 1000 episodes require manual approval"
                )
        
        return GuardrailCheck(
            name="safety_policy",
            passed=True,
            detail="No safety policy violations"
        )
    
    def _check_blocked_tools(self, tool_call) -> GuardrailCheck:
        """
        Check if tool is on blocklist.
        Example: mcp-nucleus tools are blocked in Phase 3 (not shipped yet).
        """
        blocked_prefixes = ["mcp-nucleus"]
        
        for prefix in blocked_prefixes:
            if tool_call.tool.startswith(prefix):
                return GuardrailCheck(
                    name="blocked_tools",
                    passed=False,
                    detail=f"Tool {tool_call.tool} is blocked in current phase"
                )
        
        return GuardrailCheck(
            name="blocked_tools",
            passed=True,
            detail="Tool is allowed"
        )
```

---

## Appendix C: Agent Session State Schema

```python
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from datetime import datetime

@dataclass
class ToolCall:
    tool: str  # e.g. "mcp-mlflow.get_run_metrics"
    parameters: Dict[str, Any]
    result: Optional[Any] = None
    error: Optional[str] = None
    timestamp: datetime = None
    duration_ms: int = 0

@dataclass
class AgentPlan:
    """Agent's proposed plan before execution."""
    goal: str  # Natural-language goal
    steps: List[str]  # List of steps agent will take
    tools_needed: List[str]  # Tools this plan requires
    estimated_duration: int  # Seconds

@dataclass
class HILRequest:
    """Pending HIL approval request."""
    action_id: str
    tool_call: ToolCall
    summary: str  # Natural-language explanation
    proposed_diff: str  # Git diff or YAML diff
    blast_radius: Dict[str, Any]
    mcp_trace: List[ToolCall]  # Read-only calls that led to this
    guardrail_results: Dict[str, Any]
    trustyai_eval: Optional[float]
    created_at: datetime
    status: str  # "pending" | "approved" | "rejected"

@dataclass
class AgentSession:
    """Full agent session state (persisted to Postgres)."""
    session_id: str
    operator_identity: str  # OAuth sub or CAC/PIV DN
    started_at: datetime
    updated_at: datetime
    
    # Current state
    current_plan: Optional[AgentPlan]
    tool_call_history: List[ToolCall]
    pending_hil_requests: List[HILRequest]
    
    # LangGraph checkpointer state (opaque blob)
    langgraph_state: Dict[str, Any]
    
    # Metadata
    total_tool_calls: int
    total_hil_approvals: int
    total_hil_rejections: int
```

---

## Appendix D: Performance Targets

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| Read-only agent query (p50) | < 5 seconds | Prometheus histogram `agent_query_duration_seconds` |
| Read-only agent query (p99) | < 10 seconds | Same |
| HIL drawer open latency | < 2 seconds | Time from tool-call to drawer-visible event |
| Blast-radius analysis | < 2 seconds | Time to query `mcp-fleet` and compute impact |
| TrustyAI eval (20 scenarios) | < 10 seconds | Time to run eval pipeline |
| PR creation latency | < 3 seconds | GitHub API call duration |
| Argo CD sync (p50) | < 20 seconds | Time from PR merge to pod-ready |
| Guardrail evaluation | < 500 ms | PII scan + safety checks |
| Agent-opens-PR full cycle (p50) | < 30 seconds | Drawer open → approval → PR merge → Argo sync |
| VLA inference p99 | **unchanged** | Must be independent of HIL enablement |

**Critical Invariant**: VLA inference latency (10Hz+ robot command path) must be **unaffected** by Llama Stack governance. If p99 increases when HIL is enabled, the architecture is broken.

---

**Document Status**: Planning draft for Phase 3 kickoff  
**Next Review**: At Phase 2 exit (before Phase 3 starts)  
**Owner**: Agentic orchestration workstream lead  
**Last Updated**: 2026-06-25
