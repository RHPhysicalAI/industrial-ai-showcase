# Phase 3: Agentic Orchestration — Implementation Plan

> [!NOTE]
> This project was developed with assistance from AI tools.

**Status**: Milestones 1-3 Complete (Milestones 4-5 deferred)  
**Started**: 2026-07-01  
**Target Duration**: 8-10 weeks  
**Primary Deliverable**: 60-minute technical deep-dive demo running live  
**Last Updated**: 2026-07-27

**📋 Implementation Plans**: See `phase-3-milestones/` directory for week-by-week execution guides:
- `week-0-validation.md` - Infrastructure validation spikes (3-5 days)
- `milestone-1-read-only-agent.md` - Weeks 1-2
- `milestone-2-hil-gate.md` - Weeks 3-4
- `milestone-3-agent-opens-pr.md` - Weeks 5-6
- `milestone-4-full-drawer-trustyai.md` - Weeks 7-8
- `milestone-5-cosmos-nims.md` - Weeks 9-10

---

## Executive Summary

Phase 3 delivers the agentic orchestration layer — the capability for operators to interact with the industrial AI stack via natural language, with human-in-the-loop (HIL) governance for state-modifying actions.

**What was built**: A LangGraph-based agent orchestrator with custom HIL gate, two MCP tool servers (fleet + MLflow), Llama Guard 3-8B content moderation, a PostgreSQL-backed audit service, and a 7-pane HIL approval drawer in the Showcase Console. The planned Llama Stack Agents API (OGX) was non-functional — the `rh` distribution did not expose the `/v1/agents/*` endpoints — so a custom Python HIL implementation replaced it.

**Architectural Approach**: The agent never touches the cluster API directly. State-modifying actions flow through Git (agent opens PR → operator reviews in HIL drawer → PR auto-merges → Argo CD reconciles). This reframes "LLM touching OT" as "LLM participating in code review."

**Critical Constraint**: HIL governance operates on the GitOps / PR-open path **only**, never inline in the 10Hz+ VLA serving-time robot command flow. Violating this invariant breaks credibility with technical audiences (Archetype C).

**Implementation approach**: Incremental integration — the thinnest vertical slice first (Milestone 1), then layered complexity. Milestones 1-3 are complete and verified end-to-end. Milestones 4-5 (TrustyAI, Cosmos NIMs) are deferred.

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

**Decision**: **Llama-3.1-8B-Instruct** confirmed and deployed on 1x L40S GPU (not L4 — L40S was used for VRAM headroom). Served via vLLM v0.6.3 with `--enable-auto-tool-choice --tool-call-parser=llama3_json`, float16, max-model-len 4096. Known limitation: 8B model has recursion issues with complex agentic queries; upgrade to 70B blocked by single-GPU VRAM limit.

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

**Decision**: **Option B — Custom FastAPI HTTP endpoints**. MCP servers are plain FastAPI services exposing `/tools/{tool_name}` endpoints with query parameters. The orchestrator uses a custom `MCPClient` class making HTTP GET/POST requests. Tools are wrapped as LangChain `@tool` functions and bound to the LLM via `llm.bind_tools()`. No Anthropic SDK dependency.

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

**Decision**: Simplified approach — **audit-service** with a single `hil_approvals` table in the shared MLflow PostgreSQL database. Schema stores: session_id, tool_name, tool_arguments (JSONB), git_diff, summary, blast_radius (JSONB), tool_call_trace (JSONB), reasoning_summary, status (pending/approved/rejected/merge_failed), and timestamps. No separate `agent_sessions` table — LangGraph state is ephemeral (single-turn conversations, no long-running sessions).

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

**Decision**: End-to-end manual validation against real cluster, no formal test harness. Testing validated through manual HIL promotion workflows (PRs #72-75 verified correct behavior). Unit tests deferred in favor of rapid iteration.

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

**Decision**: M1-M3 completed. M4 (TrustyAI) and M5 (Cosmos NIMs) deferred to Phase 4+. NGC entitlements not yet available for Cosmos. TrustyAI integration not prioritized — the demo works without it.

---

### Risk Analysis (Pre-Implementation — see Risk Register below for outcomes)

**High-Impact Risks** (Could Block Phase 3):

| Risk | Likelihood | Impact | Outcome |
|------|-----------|--------|---------|
| **Llama Stack API breaks** | Medium | High | 🔴 MATERIALIZED — OGX Agents API returned 404, replaced with custom HIL |
| **NGC entitlements delayed** | Medium | High | 🔴 MATERIALIZED — Cosmos NIMs deferred to Phase 4+ |
| **MCP protocol version mismatch** | Medium | Medium | 🟢 Avoided — used custom HTTP endpoints, no MCP SDK |
| **L4 GPU unavailable** | Low | High | 🟢 Avoided — used L40S instead |

**Medium-Impact Risks** (Could Delay, But Recoverable):

| Risk | Likelihood | Impact | Outcome |
|------|-----------|--------|---------|
| **TrustyAI eval latency > 10 sec** | High | Medium | ⚪ Not tested — deferred with M4 |
| **GitHub API rate limits** | Low | Medium | 🟢 Not an issue |
| **Operator approval fatigue** | Medium | Medium | 🟢 Mitigated — only promote_policy_version triggers HIL |

---

### Implementation Readiness Checklist — All Met

#### Infrastructure Readiness
- [x] **L40S GPU allocated** (used L40S instead of planned L4 for VRAM headroom)
- [x] **Postgres deployed** (shared MLflow Postgres instance)
- [x] **GitHub token configured** (personal access token via OpenShift Secret)
- [x] **vLLM deployment tested** (Llama-3.1-8B-Instruct serving on L40S)

#### Dependency Readiness
- [x] **Phase 2 complete**
- [x] **MLflow operational** (mcp-mlflow uses mock data, but MLflow instance exists)
- [x] **Fleet Manager API stable** (Console backend provides fleet status)
- [x] **GitHub access configured** (personal access token, not bot account)

#### Architectural Alignment
- [x] All 5 decisions resolved through implementation (see Decision sections above)

---

### Resource Requirements Validation — Resolved

**Actual Staffing**: Single engineer with AI code assistance (Claude Code). The 2.5 FTE estimate was based on a traditional team structure and proved overly conservative for M1-M3 scope.

**Actual GPU Usage**: 1× L40S for agent brain (Llama-3.1-8B-Instruct via vLLM). Cosmos NIMs GPUs not allocated.

**Actual Compute**: ~5 CPU, ~12 GB RAM total across agentic-ops namespace services.

**External Dependencies Resolved**:
- GitHub: Personal access token (not bot account, no CODEOWNERS)
- PostgreSQL: Shared MLflow instance
- NGC: Not available — Cosmos deferred

---

### Open Questions Summary — All Resolved

**LLM Selection (Decision 1)**:
- Q1: ✅ Resolved — Meta model (Llama-3.1-8B-Instruct) selected. No licensing concerns for internal demo.
- Q2: ✅ Resolved — Committed to Llama-3.1-8B-Instruct without benchmarking alternatives.
- Q3: ✅ Resolved — Full fp16. No quantization needed — L40S has 48 GB VRAM.

**MCP Protocol (Decision 2)**:
- Q4: ✅ Resolved — Did not use Anthropic's SDK. Custom FastAPI HTTP endpoints.
- Q5: ✅ N/A — No MCP protocol to test (plain HTTP).
- Q6: ✅ N/A — Not using MCP SDK.

**State Persistence (Decision 3)**:
- Q7: ✅ Resolved — Single `hil_approvals` table with JSONB columns. No separate tool_calls table.
- Q8: ✅ Deferred — No retention policy needed for demo. Data volume is minimal.
- Q9: ✅ Resolved — Shared MLflow database. Separate DB for compliance isolation is Phase 4+ work.

**Testing Strategy (Decision 4)**:
- Q10: ✅ Resolved — No unit test coverage target. Manual E2E validation.
- Q11: ✅ Resolved — No test harness built.
- Q12: ✅ Deferred — No load testing. Performance measured manually.

**Milestone Sequencing (Decision 5)**:
- Q13: ✅ Resolved — M1-M3 completed. M4-M5 deferred.
- Q14: ✅ Resolved — Proceeded without NGC entitlements. Cosmos NIMs deferred.
- Q15: ✅ N/A — No formal no-go decision point needed.

**Resource Validation**:
- Q16: ✅ Resolved — L40S GPU used (not L4). Available on hub cluster.
- Q17: ✅ Resolved — NGC entitlements not available. Cosmos deferred.
- Q18: ✅ Resolved — Work done by single engineer with AI assistance. 2.5 FTE plan was overly conservative.

---

## Architecture Overview

### Agentic Stack (As Built)

```
┌─────────────────────────────────────────────────────────┐
│ Operator (Showcase Console)                            │
│  - AgentAssistant chat panel (natural language)        │
│  - HIL Approval Drawer (7+ panes)                      │
│  - Rollback Analysis Drawer                            │
└────────────────┬────────────────────────────────────────┘
                 │
                 ↓
┌─────────────────────────────────────────────────────────┐
│ LangGraph Orchestrator + Custom HIL Gate               │
│  - Agent brain: vLLM Llama-3.1-8B (L40S GPU)          │
│  - Tool calling via MCP HTTP endpoints                 │
│  - Custom HIL: intercepts state-modifying tools        │
│  - Llama Guard 3-8B content moderation (input+output)  │
│  - Kafka event listener (rollback analysis)            │
│  - Audit trail: PostgreSQL via audit-service           │
└────────────────┬────────────────────────────────────────┘
                 │
        ┌────────┴────────┐
        ↓                 ↓
   ┌─────────┐      ┌──────────┐
   │ mcp-    │      │ mcp-     │
   │ fleet   │      │ mlflow   │
   │ (real)  │      │ (mock)   │
   └────┬────┘      └────┬─────┘
        │                │
        ↓                ↓
  Fleet Manager      MLflow (mock data)
  Console Backend
  GitHub API
```

**Note**: The planned Llama Stack (OGX) governance layer was deployed but the `rh` distribution's Agents API (`/v1/agents/*`) returned 404. The HIL gate was implemented as a custom Python node in the LangGraph graph instead. Llama Guard 3-8B is deployed separately for content moderation (not through OGX). See `llama_stack_adapter.py` for the unused OGX client code preserved for future reference.

### Agent-Opens-a-PR Pattern (As Implemented)

```
1. Operator: "Promote v1.5 to Factory A"
         ↓
2. Llama Guard: Scans input for safety/content moderation
         ↓
3. LangGraph Orchestrator: Receives query
   - Calls agent brain (vLLM Llama-3.1-8B-Instruct)
   - Agent selects tool: promote_policy_version (state-modifying)
         ↓
4. Custom HIL Gate: Intercepts state-modifying tool call
   - Calls mcp-fleet-server POST /tools/promote_policy_version
     with dry_run=true (generates diff without creating PR)
   - Gets back: git_diff, summary, blast_radius, reasoning
   - Records pending approval in audit-service (PostgreSQL)
   - Returns HIL request to Console via SSE/polling
         ↓
5. HIL Drawer Opens (7+ panes populated)
   - Summary: "Promote v1.5 to Factory A"
   - Git diff: policy-version.yaml change only
   - Blast radius: affected factory, robots, rollback path
   - MCP tool call trace
   - Agent reasoning summary
   - Approve / Reject buttons
         ↓
6. Operator: Clicks "Approve"
         ↓
7. Orchestrator: Calls mcp-fleet-server POST /tools/promote_policy_version
   with dry_run=false (creates real PR)
   - kustomize_generator.py generates policy-version.yaml overlay
   - github_client.py creates PR via GitHub API
   - PR auto-merges via GitHub API (no CODEOWNERS, bot has write access)
         ↓
8. Argo CD: Auto-syncs within ~3 min poll cycle
   - Reconciles ConfigMap from merged policy-version.yaml
         ↓
9. Audit record updated: status → approved, pr_url populated
         ↓
10. Console UI: Shows success alert with PR link
    - Factory version updates in Fleet Overview
```

**Key Insight**: The agent never calls `oc apply`. Every change is Git-mediated. The cluster API is read-only from the agent's perspective. PRs auto-merge via GitHub API after HIL approval — no separate CODEOWNERS review step.

---

## Implementation Strategy: Incremental Integration

Phase 3 is complex enough that a waterfall "build all components then integrate" approach will fail. Instead: **build the thinnest possible vertical slice first**, then expand.

### Milestone 1: "Hello World" Agent Loop (Weeks 1-2) ✅ Complete

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

### Milestone 2: Custom HIL Gate (Weeks 3-4) ✅ Complete

**Goal**: Operator asks agent to do something state-modifying. HIL gate triggers, drawer opens, operator approves, action executes.

**Implementation Note**: Originally "Llama Stack HIL Gate" — replaced with custom HIL implementation after OGX Agents API returned 404.

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

### Milestone 3: Agent-Opens-a-PR Pattern (Weeks 5-6) ✅ Complete

**Goal**: Agent doesn't call cluster API directly — it opens a PR. Operator approves in drawer, PR merges, Argo CD syncs.

**Verified**: PRs #72-75 confirmed correct behavior. Factory A promoted to v1.6, Factory B to v1.7.

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

### Milestone 4: Full HIL Drawer (6 Panes) + TrustyAI (Weeks 7-8) ⏳ Deferred

**Goal**: HIL drawer shows all six panes per the design spec. TrustyAI evaluation runs on proposed policy vs. incumbent.

**Status**: Deferred to Phase 4+. The HIL drawer was implemented with 7+ panes (exceeding the 6-pane spec in some areas), but TrustyAI integration and Presidio/guardrail-outcome panes were not built. See Component 4 for pane-by-pane status.

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

### Milestone 5: Cosmos NIMs + Synthetic Data Pipeline (Weeks 9-10) ⏳ Deferred

**Goal**: Segment 1 of 60-min demo runs — Cosmos Predict 2.5 as pre-dispatch admission check, Cosmos Transfer 2.5 generating scenario variations.

**Status**: Deferred to Phase 4+. NGC entitlements not available. See Component 6.

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

### 1. LangGraph Orchestrator ✅ Implemented

**Repository**: `infrastructure/gitops/apps/workloads/agentic-orchestrator/`

**Tech Stack**:
- Python 3.11
- LangGraph + LangChain
- vLLM serving `meta-llama/Llama-3.1-8B-Instruct` on L40S GPU
- Custom HIL gate (replaces planned Llama Stack Agents API)
- Llama Guard 3-8B content moderation via `llama-guard-adapter`
- Kafka consumer for rollback analysis events

**Key Files (Actual)**:
- `src/agent_graph.py` — LangGraph graph definition with HIL gate node
- `src/api_server.py` — FastAPI server exposing `/chat`, `/approve`, `/reject`, `/pending-approvals`
- `src/mcp_client.py` — HTTP client for MCP fleet + MLflow servers
- `src/github_client.py` — GitHub API for PR creation + auto-merge
- `src/kustomize_generator.py` — Generates policy-version.yaml Kustomize overlays
- `src/llama_stack_adapter.py` — Unused OGX client (preserved for future reference)
- `src/llama_guard_client.py` — Llama Guard 3-8B integration for input/output moderation
- `src/kafka_listener.py` — Kafka consumer for anomaly/rollback events

**Deployment**:
- BuildConfig + ImageStream (OpenShift S2I, not Helm)
- Namespace: `agentic-ops`
- Resources: 2 CPU, 4 GB RAM
- Service: ClusterIP, port 8080
- No service mesh sidecar (not yet configured)

**Key Environment Variables (Actual)**:
```yaml
MCP_FLEET_URL: http://mcp-fleet-server:8081
MCP_MLFLOW_URL: http://mcp-mlflow-server:8083
VLLM_URL: http://vllm-agent-brain:8000/v1
LLAMA_GUARD_URL: http://llama-guard-adapter:8085
AUDIT_SERVICE_URL: http://audit-service:8090
GITHUB_TOKEN: (from Secret)
GITHUB_REPO: (owner/repo)
KAFKA_BOOTSTRAP_SERVERS: amq-streams-kafka-bootstrap.amq-streams.svc:9092
SHOWCASE_MODE: "true"  # Uses HuggingFace model URIs instead of MLflow/MinIO
```

**State Model**: Ephemeral — single-turn conversations, no persistent LangGraph checkpointer. Audit trail stored via audit-service (see Component 7).

---

### 2. Llama Stack Governance Layer ⚠️ Not Functional — Replaced by Custom HIL

**Planned Repository**: `workloads/llama-stack/`

**What Happened**: The RHOAI 3.4 EA1 `rh` distribution of Llama Stack was deployed to `agentic-ops` namespace, but the Agents API (`/v1/agents/*`) returned **404 for all endpoints**. The `rh` distribution only exposed the inference and safety APIs, not the Agents/HIL APIs needed for governance. Since the Agents API was the critical dependency for HIL gate integration, a custom Python implementation was built instead.

**What Was Built Instead**:
- **Custom HIL gate**: A node in the LangGraph graph (`agent_graph.py`) that intercepts state-modifying tool calls, generates a dry-run diff, and pauses execution until operator approval
- **Llama Guard 3-8B**: Deployed as a separate service (`llama-guard-adapter`) for input/output content moderation — NOT through OGX/Llama Stack
- **audit-service**: Custom FastAPI service with PostgreSQL for approval tracking (see Component 7)

**Preserved Code**: `llama_stack_adapter.py` in the orchestrator source contains the OGX client code, preserved for future integration if the Agents API becomes available in a later RHOAI release.

**Future**: If RHOAI ships a functional Agents API with HIL capabilities, the custom HIL gate can be replaced. The interface is clean — swap the `hil_gate` node implementation in `agent_graph.py`.

---

### 3. MCP Servers

Each MCP server is a standalone FastAPI service exposing tools as HTTP endpoints (`/tools/{tool_name}`). The orchestrator calls them via `MCPClient` (HTTP GET/POST), not the Anthropic MCP SDK.

#### 3a. `mcp-mlflow` ✅ Implemented (Mock Data)

**Repository**: `infrastructure/gitops/apps/workloads/mcp-mlflow-server/`

**Purpose**: Read MLflow experiments, runs, metrics. Returns mock data — does not connect to real MLflow.

**Tools (Actual)**:
- `GET /tools/query_experiments` — returns mock experiment list
- `GET /tools/get_run_metrics` — returns mock metrics (pick_success_rate, grasp_precision, etc.)
- `GET /tools/get_model_versions` — returns mock model version list

**Deployment**:
- BuildConfig + ImageStream (OpenShift S2I)
- Namespace: `agentic-ops`
- Resources: 1 CPU, 2 GB RAM
- Service: port 8083

**Note**: State-modifying tools (`register_model`, `promote_model_version`) were not implemented. Model promotion goes through `mcp-fleet-server` → `promote_policy_version` instead.

#### 3b. `mcp-fleet` ✅ Implemented (Real)

**Repository**: `infrastructure/gitops/apps/workloads/mcp-fleet-server/`

**Purpose**: Query fleet status; create model promotion PRs via GitHub API.

**Tools (Actual)**:
- `GET /tools/get_fleet_status` — queries Console backend for factory/robot status
- `GET /tools/get_factory_config?factory=factory-a` — returns factory configuration
- `POST /tools/promote_policy_version` — **the key HIL tool**:
  - `dry_run=true`: generates Kustomize overlay diff without creating PR
  - `dry_run=false`: creates PR via GitHub API, auto-merges

**Key Implementation Detail**: The MCP fleet server's Dockerfile copies `kustomize_generator.py` and `github_client.py` at build time. The BuildConfig only triggers on ConfigChange (YAML edits), NOT source code changes. No GitHub webhook is configured. This means **source code changes require a manual build trigger** (`oc start-build mcp-fleet-server`).

**Deployment**:
- BuildConfig + ImageStream (OpenShift S2I)
- Namespace: `agentic-ops`
- Resources: 1 CPU, 2 GB RAM
- Service: port 8081
- Connects to: Console backend API, GitHub API

**Special Case: `promote_policy_version`**:
This tool **does not** call the cluster API. Instead:
1. `kustomize_generator.py` generates only `policy-version.yaml` (ConfigMap with model version + HF URI)
2. Creates PR to `infrastructure/gitops/apps/workloads/{factory}/policy-version.yaml`
3. Auto-merges PR via GitHub API
4. Argo CD auto-syncs ConfigMap within ~3 min poll cycle

**Known Issue (Fixed)**: Early PRs (#70, #71) included InferenceService YAML and kustomization.yaml modifications. Fixed in `kustomize_generator.py` to generate only `policy-version.yaml`. Verified with PRs #72-75.

#### 3c. `mcp-isaac-sim` ❌ Not Implemented (Deferred to Phase 4+)

**Purpose (Planned)**: Launch sim runs, generate scenario manifests, query scene library.

**Why Deferred**: Isaac Sim integration depends on Cosmos NIMs (NGC entitlements not available) and a running Isaac Sim headless instance (not yet deployed on OpenShift). Milestones 4-5 which would have used this server were deferred.

**Planned Tools** (preserved for future implementation):
- `list_scenes()`, `get_scenario_manifest()` — read-only
- `launch_sim_run()`, `generate_scenario_manifest()` — state-modifying (would trigger HIL)

---

### 4. HIL Approval Drawer (Showcase Console) ✅ Implemented

**Location**: `showcase-ui/src/components/AgentAssistant/HILApprovalDrawer.tsx`

**State Management**: React state + polling orchestrator `/pending-approvals` endpoint

**Seven+ Panes** (exceeded original 6-pane spec):

#### Pane 1: Proposed Action Summary ✅
- Agent's natural-language explanation of the proposed action

#### Pane 2: Proposed Diff ✅
- Syntax-highlighted Git diff of `policy-version.yaml`

#### Pane 3: Blast-Radius Analysis ✅
- Affected factories, robots, rollback path
- Data computed by `mcp-fleet-server` during dry-run

#### Pane 4: MCP Tool-Call Trace ✅
- Chronological list of tool calls the agent made

#### Pane 5: Agent Reasoning Summary ✅ (Added — not in original spec)
- Agent's reasoning for why it chose this action

#### Pane 6: Merge Error Display ✅ (Added — not in original spec)
- Shows PR merge failures with retry option

#### Pane 7: Rollback Analysis ✅ (Added — not in original spec)
- Kafka-driven anomaly analysis results

#### Not Implemented (Deferred):
- **TrustyAI Eval pane**: Proposed vs. incumbent score — deferred with M4
- **Guardrail Outcomes pane**: PII scan / safety policy results — Llama Guard moderation happens at input/output level, not per-tool-call
- **CAC/PIV Identity binding**: Demo uses simple operator identity, no certificate-based auth

**Drawer Behavior (Actual)**:
- Opens on right side as PatternFly Drawer
- Approve / Reject buttons with confirmation
- "Reject" requires reason (textarea input)
- Pending approval persists until operator acts

**Backend API**: The Console frontend communicates directly with the orchestrator:
- `POST /approve` — approve pending HIL request
- `POST /reject` — reject with reason
- `GET /pending-approvals` — list pending HIL requests
- `POST /chat` — send natural language query

No separate HIL routes in the Console backend — the orchestrator IS the HIL backend.

---

### 5. TrustyAI Integration ❌ Not Implemented (Deferred to Phase 4+)

**Purpose (Planned)**: Evaluate proposed model vs. incumbent on held-out scenario suite.

**Why Deferred**: TrustyAI integration was planned for Milestone 4, which was deferred. The HIL workflow works without it — operators review the Git diff, blast radius, and agent reasoning to make approval decisions. TrustyAI eval scores would add quantitative comparison but aren't blocking.

**Future Integration Point**: When implemented, eval scores would appear as an additional pane in the HIL drawer, comparing proposed model metrics against the incumbent.

---

### 6. Cosmos NIMs ❌ Not Implemented (Deferred to Phase 4+ — NGC entitlements pending)

**Purpose (Planned)**: Cosmos Predict 2.5 for pre-dispatch mission admission; Cosmos Transfer 2.5 for synthetic scenario generation.

**Why Deferred**: NGC entitlements for Cosmos NIMs were not available at Phase 3 start. This was an identified risk (see Risk 4). The mitigation path was followed — Milestones 1-3 (agentic layer) proceeded without Cosmos dependency. Segment 1 of the 60-min demo is deferred.

**What Would Be Needed to Resume**:
1. NGC entitlements for Cosmos Predict 2.5 + Cosmos Transfer 2.5
2. `mcp-isaac-sim` server implementation (see 3c above)
3. 2× L40S GPUs available (not concurrent with agent brain or VLA serving)
4. Isaac Sim headless instance on OpenShift
5. Fleet Manager integration for mission admission hook

---

### 7. Audit Service ✅ Implemented

**Repository**: `infrastructure/gitops/apps/workloads/audit-service/`

**Purpose**: PostgreSQL-backed service for recording HIL approval/rejection decisions. Provides the immutable audit trail for all state-modifying actions.

**Tech Stack**: Python 3.11 + FastAPI

**Key Endpoints**:
- `POST /approvals` — record a new pending approval
- `GET /approvals/{id}` — retrieve approval record
- `PATCH /approvals/{id}` — update status (pending → approved/rejected)
- `GET /health` — health check

**Database**: Shares PostgreSQL instance with MLflow (`mlflow-db-rw.mlflow.svc.cluster.local`). Single `hil_approvals` table with: session_id, tool_name, tool_arguments (JSONB), git_diff, summary, blast_radius (JSONB), tool_call_trace (JSONB), reasoning_summary, status, timestamps.

**Deployment**:
- BuildConfig + ImageStream
- Namespace: `agentic-ops`
- Resources: 100m-500m CPU, 512Mi-1Gi RAM
- Service: port 8090

---

### 8. Llama Guard Content Moderation ✅ Implemented

**Repository**: `infrastructure/gitops/apps/workloads/llama-guard-adapter/`

**Purpose**: Content moderation for agent input and output using Llama Guard 3-8B model.

**How It Works**: The orchestrator sends user input and agent output to the Llama Guard adapter, which calls the Llama Guard 3-8B model (served via vLLM or the OGX safety API) and returns safe/unsafe classification.

**Note**: This replaces the originally planned Presidio PII detection. Llama Guard is LLM-based (more nuanced, slightly slower) vs. Presidio which is rule-based (faster, deterministic). The trade-off was acceptable given that moderation happens once per query, not per tool call.

**Deployment**:
- Namespace: `agentic-ops`
- Service: port 8085

---

### 9. VLA Model Serving ✅ Implemented (Custom Pattern)

**Repository**: `infrastructure/gitops/apps/workloads/robot-edge/` (Factory A), `infrastructure/gitops/apps/workloads/factory-b/` (Factory B)

**Model**: `openvla/openvla-7b` served via custom `openvla-server` (NOT KServe vLLM InferenceService).

**Why Custom**: OpenVLA requires a custom `/act` endpoint for robot action prediction, which doesn't fit the standard KServe predict/explain API. The `openvla-server` is a custom FastAPI service with model loading and inference logic.

**Policy Version Flow**: Each factory has a `policy-version.yaml` ConfigMap that specifies the active model version and HuggingFace URI. When promoted via the HIL workflow, only this ConfigMap changes. The `openvla-server` deployment reads the ConfigMap to know which model to serve.

**Deployment per factory**:
- `openvla-server-imagestream.yaml`
- `openvla-server-buildconfig.yaml`
- `openvla-server-deployment.yaml`
- `openvla-server-service.yaml`
- `policy-version.yaml` (ConfigMap — managed by HIL promotion workflow)

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

### Risk 1: Llama Stack API Evolution (HIGH) — 🔴 MATERIALIZED

**Problem**: RHOAI 3.4 EA1 ships Llama Stack 0.3.5. Upstream is moving fast; API may change.

**What Happened**: The `rh` distribution's Agents API (`/v1/agents/*`) returned 404 for all endpoints. The distribution only exposed inference and safety APIs, not the Agents/HIL APIs. This was worse than an API change — the feature was entirely absent.

**Resolution**: Used the documented fallback — implemented custom HIL gate as a LangGraph node with FastAPI endpoints + PostgreSQL-backed audit trail via `audit-service`. The custom implementation is cleaner and simpler than the Llama Stack integration would have been.

---

### Risk 2: TrustyAI Eval Latency (MEDIUM) — ⚪ Not Tested (Deferred)

**Problem**: Evaluating proposed model on 20+ scenarios may take 30-60 seconds.

**What Happened**: TrustyAI integration was deferred with Milestone 4. Risk not tested. The HIL workflow works without eval scores — operators review diff, blast radius, and agent reasoning instead.

---

### Risk 3: MCP Protocol Version Mismatch (MEDIUM) — 🟢 Avoided

**Problem**: LangGraph's MCP client expects different format than MCP server emits.

**What Happened**: Risk avoided by choosing custom FastAPI HTTP endpoints instead of the Anthropic MCP SDK. Tools are simple HTTP GET/POST endpoints. The orchestrator wraps them as LangChain `@tool` functions and binds them to the LLM via `llm.bind_tools()`. No MCP protocol version to mismatch.

---

### Risk 4: NGC Entitlement Delays (HIGH) — 🔴 MATERIALIZED

**Problem**: Cosmos Predict/Transfer NIMs require NGC entitlement. May not be available at Phase 3 start.

**What Happened**: NGC entitlements were not available. Milestone 5 and Segment 1 of 60-min demo deferred to Phase 4+. The mitigation worked as designed — Milestones 1-3 proceeded independently of Cosmos.

---

### Risk 5: GitHub API Rate Limits (LOW) — 🟢 Not an Issue

**Problem**: Agent opening many PRs could hit GitHub rate limit (5000/hour for authenticated user).

**What Happened**: Not an issue. Demo usage generates ~5-10 PRs per session, far below the 5000/hour limit.

---

### Risk 6 (New): MCP Server Code Caching — 🔴 MATERIALIZED

**Problem**: MCP fleet server Dockerfile copies Python source files at build time. BuildConfig only triggers on ConfigChange (YAML changes), not source code changes. No GitHub webhook configured.

**What Happened**: After fixing `kustomize_generator.py` to generate only `policy-version.yaml` (instead of InferenceService + kustomization.yaml), the MCP server pod continued using the OLD code. PRs #70 and #71 contained wrong changes. Root cause: the pod was 2 days old with cached stale code.

**Resolution**: Manual build trigger (`oc start-build mcp-fleet-server`), pod restart. PRs #72-75 verified correct behavior.

**Recommendation for Phase 4**: Add GitHub webhook to BuildConfig, or switch to a CI pipeline that rebuilds on source changes.

---

### Risk 7 (New): Argo CD Shared Resource Conflicts — 🔴 MATERIALIZED

**Problem**: The `policy-version.yaml` ConfigMap was listed in TWO Argo applications (`workloads-robot-edge` AND `workloads-mission-dispatcher`), both managing the same resource.

**What Happened**: After PR #73 merged, the Factory A ConfigMap did not update. Argo CD showed the resource as managed by `workloads-mission-dispatcher` which had a stale version. The conflict prevented `workloads-robot-edge` from reconciling.

**Resolution**: Removed `policy-version.yaml` from `mission-dispatcher/kustomization.yaml` and deleted the duplicate file. Each Argo application now manages distinct resources.

---

### Risk 8: Operator Approval Fatigue (MEDIUM, long-term)

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

1. ⏳ **60-minute demo runs end-to-end live** — Segments 2-4 functional, Segment 1 deferred (Cosmos NIMs)
2. ⏳ **Segment 1 (Cosmos)**: Deferred — NGC entitlements not available
3. ✅ **Segment 2 (Agentic HIL)**: Operator asks NL question, agent proposes state-modifying action, HIL drawer opens with 7+ panes, operator approves, PR auto-merges, Argo syncs. Verified with PRs #72-75.
4. ⏳ **Segment 3 (Security)**: Infrastructure exists (Sigstore, Compliance Operator), Console integration in progress
5. ⏳ **Segment 4 (VLA swap)**: Kustomize overlay swap works via HIL promotion. Custom openvla-server (not KServe). Tempo tracing not yet connected.

### Technical Criteria

6. ✅ **HIL drawer behaves per design spec**: 7+ panes (exceeded 6-pane spec), real data, approval writes audit record, rejection requires reason. CAC/PIV identity binding deferred.
7. ✅ **Agent-opens-PR pattern works**: Agent never calls cluster API directly, all state changes via Git, PR URL in audit record. Verified end-to-end.
8. ✅ **Custom HIL governance on GitOps path only**: VLA inference latency is independent of HIL enablement (governance operates on PR-open path only, never in 10Hz+ serving-time loop).
9. ⏳ **Guardrail failure blocks approval**: Llama Guard content moderation deployed, but per-tool-call guardrail evaluation (Presidio PII scan) not implemented. Deferred with M4.
10. ⏳ **TrustyAI eval completes**: Deferred with M4.

### Deliverable Criteria

11. ⏳ **`demos/60-min-deep-dive/script.md`**: Not yet written — agentic segment functional, other segments in progress
12. ⏳ **Performance envelope doc v2**: Measurements not yet documented (see Task #34)
13. ⏳ **Blog post series**: Not yet started
14. ⏳ **Phase 3 components documented**: This document updated, component catalog TBD

### Quality Criteria

15. ⏳ **Integration test suite**: Manual E2E validation done (PRs #72-75), no automated test suite
16. ⏳ **Segment rehearsals**: Not yet conducted
17. ✅ **No placeholders in HIL drawer**: All displayed panes show real data. Panes that couldn't be populated (TrustyAI, guardrail outcomes) were not shipped.

---

## Timeline (Actual)

### Weeks 1-2: Milestone 1 (Hello World Agent) ✅ Complete
- LangGraph orchestrator with agent brain (vLLM Llama-3.1-8B on L40S)
- `mcp-mlflow` server (mock data)
- Console AgentAssistant chat panel
- **Delivered**: Read-only agent query works end-to-end

### Weeks 3-4: Milestone 2 (Custom HIL Gate) ✅ Complete
- Custom HIL gate (Llama Stack OGX non-functional — see Risk 1)
- HIL drawer (initial panes)
- Llama Guard 3-8B content moderation
- audit-service (PostgreSQL)
- **Delivered**: HIL gate triggers, operator approves/rejects

### Weeks 5-6: Milestone 3 (Agent Opens PR) ✅ Complete
- GitHub API integration (create PR + auto-merge)
- Kustomize overlay generator (policy-version.yaml only)
- `mcp-fleet` server (fleet status + promote_policy_version)
- HIL drawer: Git diff, blast radius, reasoning, merge error panes
- **Delivered**: Agent opens PR, auto-merges, Argo syncs. Verified PRs #72-75.

### Weeks 7-8: Milestone 4 (Full Drawer + TrustyAI) ⏳ Deferred
- TrustyAI integration not prioritized
- Guardrail outcome panes deferred
- HIL drawer already has 7+ panes from M2-M3 work

### Weeks 9-10: Milestone 5 (Cosmos NIMs) ⏳ Deferred
- NGC entitlements not available
- `mcp-isaac-sim` not built

### Weeks 11-12: Integration, Rehearsal, Polish
- ⏳ In progress — fixing operational issues (shared resource conflicts, code caching, Argo sync)
- Performance measurements pending
- Blog posts + docs pending

---

## Resource Requirements (Actual)

### Infrastructure (As Deployed)

**GPU Allocation**:
- **L40S**: 1 GPU for agent brain (vLLM Llama-3.1-8B-Instruct) — originally planned for L4, but L40S used for VRAM headroom
- **L40S**: 1 GPU for VLA model serving (openvla-7b) — shared across factories
- Cosmos NIMs GPUs not allocated (deferred)

**Compute** (non-GPU, `agentic-ops` namespace):
- LangGraph orchestrator: 2 CPU, 4 GB RAM
- MCP fleet server: 1 CPU, 2 GB RAM
- MCP MLflow server: 1 CPU, 2 GB RAM
- audit-service: 100m-500m CPU, 512Mi-1Gi RAM
- Llama Guard adapter: ~1 CPU, 2 GB RAM

**Storage**:
- PostgreSQL (shared MLflow instance): `hil_approvals` table, minimal storage

### External Dependencies (Actual)

- **GitHub**: API access with personal access token (not bot account, no CODEOWNERS)
- **PostgreSQL**: Shared with MLflow (`mlflow-db-rw.mlflow.svc.cluster.local`)
- **Kafka**: AMQ Streams for rollback analysis events

---

## Appendix A: MCP Tool Classification Matrix (As Implemented)

| MCP Server | Tool | Classification | Triggers HIL? | Status |
|------------|------|---------------|---------------|--------|
| mcp-mlflow | query_experiments | read-only | No | ✅ Implemented (mock) |
| mcp-mlflow | get_run_metrics | read-only | No | ✅ Implemented (mock) |
| mcp-mlflow | get_model_versions | read-only | No | ✅ Implemented (mock) |
| mcp-mlflow | register_model | state-modifying | Yes | ❌ Not implemented |
| mcp-mlflow | promote_model_version | state-modifying | Yes | ❌ Not implemented (promotion via mcp-fleet instead) |
| mcp-fleet | get_fleet_status | read-only | No | ✅ Implemented |
| mcp-fleet | get_factory_config | read-only | No | ✅ Implemented |
| mcp-fleet | get_robot_telemetry | read-only | No | ❌ Not implemented |
| mcp-fleet | get_anomaly_history | read-only | No | ❌ Not implemented |
| mcp-fleet | override_mission_params | state-modifying | Yes | ❌ Not implemented |
| mcp-fleet | propose_fleet_intervention | state-modifying | Yes | ❌ Not implemented |
| mcp-fleet | promote_policy_version | state-modifying | Yes | ✅ Implemented (opens PR) |
| mcp-isaac-sim | * | * | * | ❌ Not implemented (deferred) |

**Rule**: Any tool that creates, updates, or deletes cluster resources, opens PRs, or launches workloads is **state-modifying** and triggers HIL.

---

## Appendix B: Guardrail Evaluation Logic (Planned — Not Implemented As Shown)

**Status**: The Presidio-based guardrail pipeline below was **not implemented**. Content moderation uses Llama Guard 3-8B instead (see Component 8). Per-tool-call guardrail evaluation (PII scan, safety policy, blocked tools) was deferred with Milestone 4.

```python
# PLANNED CODE — not implemented. Preserved for Phase 4+ reference.
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

## Appendix C: Agent Session State Schema (Planned — Simplified in Implementation)

**Status**: The full session state schema below was **not implemented**. The actual implementation uses:
- Ephemeral LangGraph state (single-turn, no checkpointer)
- `hil_approvals` table in audit-service for approval tracking (see Component 7)
- No `agent_sessions` table — sessions are not persisted

Planned schema preserved for Phase 4+ reference (long-running sessions, agent memory):

```python
# PLANNED CODE — not implemented as shown.
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from datetime import datetime

@dataclass
class ToolCall:
    tool: str
    parameters: Dict[str, Any]
    result: Optional[Any] = None
    error: Optional[str] = None
    timestamp: datetime = None
    duration_ms: int = 0

@dataclass
class HILRequest:
    action_id: str
    tool_call: ToolCall
    summary: str
    proposed_diff: str
    blast_radius: Dict[str, Any]
    mcp_trace: List[ToolCall]
    guardrail_results: Dict[str, Any]
    trustyai_eval: Optional[float]
    created_at: datetime
    status: str  # "pending" | "approved" | "rejected"
```

---

## Appendix D: Performance Targets

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Read-only agent query (p50) | < 5 seconds | ~3-8 seconds | ⚠️ Varies with LLM response time |
| Read-only agent query (p99) | < 10 seconds | Not measured | ⏳ Needs measurement |
| HIL drawer open latency | < 2 seconds | ~1-2 seconds | ✅ Met |
| Blast-radius analysis | < 2 seconds | < 1 second | ✅ Met |
| TrustyAI eval (20 scenarios) | < 10 seconds | N/A | ❌ Deferred |
| PR creation latency | < 3 seconds | ~2-4 seconds | ⚠️ Close to target |
| Argo CD sync (p50) | < 20 seconds | ~3 minutes | ⚠️ Argo poll cycle, not instant |
| Guardrail evaluation | < 500 ms | N/A (Llama Guard only) | ⚠️ Different implementation |
| Agent-opens-PR full cycle (p50) | < 30 seconds | ~3-5 minutes | ⚠️ Dominated by Argo sync delay |
| VLA inference p99 | **unchanged** | **unchanged** | ✅ Met — HIL on GitOps path only |

**Critical Invariant**: VLA inference latency (10Hz+ robot command path) is **unaffected** by HIL governance. The custom HIL gate operates on the PR-open path only, never in the serving-time loop. This invariant holds.

**Note**: Argo CD sync time (~3 min) dominates the full cycle. This is the Argo poll interval, not a performance issue. Could be reduced with webhook-based sync trigger.

---

**Document Status**: Implementation record — Milestones 1-3 complete, 4-5 deferred  
**Next Review**: Phase 4 planning  
**Owner**: Agentic orchestration workstream lead  
**Last Updated**: 2026-07-27
