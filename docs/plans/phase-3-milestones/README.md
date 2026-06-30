# Phase 3 Milestone Implementation Plans

> [!NOTE]
> This project was developed with assistance from AI tools.

This directory contains week-by-week implementation plans for Phase 3 agentic orchestration.

**Parent Document**: `../phase-3-agentic-implementation.md`

---

## Directory Structure

- **`week-0-validation.md`** - Infrastructure validation spikes (see `spikes/week0-validation/`)
- **`milestone-1-read-only-agent.md`** - Weeks 1-2: Read-only agent (LangGraph + mcp-mlflow)
- **`milestone-2-hil-gate.md`** - Weeks 3-4: Llama Stack HIL gate + 3-pane drawer
- **`milestone-3-agent-opens-pr.md`** - Weeks 5-6: GitHub integration + mcp-fleet
- **`milestone-4-full-drawer-trustyai.md`** - Weeks 7-8: 6-pane drawer + TrustyAI eval
- **`milestone-5-cosmos-nims.md`** - Weeks 9-10: Cosmos Predict/Transfer + synthetic data
- **`buffer-weeks.md`** - Weeks 11-12: Integration, rehearsal, polish

---

## How to Use These Plans

Each milestone plan includes:

1. **Goal** - What you're building this week
2. **Entry Criteria** - What must be complete before starting
3. **Day-by-Day Breakdown** - Specific tasks per day
4. **Exit Criteria** - How you know the milestone is done
5. **Troubleshooting** - Common issues and solutions
6. **Handoff to Next Milestone** - What the next milestone depends on

---

## Solo Developer Adaptation

These plans assume **1 FTE solo developer**. Multi-person team adaptations:

- **Backend Engineer** - Handles LangGraph, MCP servers, Llama Stack
- **Frontend Engineer** - Handles HIL drawer (Milestone 2+)
- **Platform Engineer** - Handles GitHub API, Vault, GitOps (Milestone 3+)

If you're solo, you'll do all roles sequentially. The plans account for this.

---

## Milestone Dependencies

```
Week 0 (Validation)
    ↓
Milestone 1 (Weeks 1-2): Read-Only Agent
    ↓
Milestone 2 (Weeks 3-4): HIL Gate
    ↓
Milestone 3 (Weeks 5-6): Agent-Opens-PR
    ↓
Milestone 4 (Weeks 7-8): Full Drawer + TrustyAI  ← Can defer if needed
    ↓
Milestone 5 (Weeks 9-10): Cosmos NIMs             ← Can defer if NGC blocked
    ↓
Buffer (Weeks 11-12): Integration + Demo Rehearsal
```

**Critical Path**: Week 0 → M1 → M2 → M3 (non-negotiable)  
**Negotiable**: M4, M5 can be deferred to Phase 4 if blocked

---

## Status Tracking

Update this table as you complete milestones:

| Milestone | Weeks | Status | Completion Date | Notes |
|-----------|-------|--------|----------------|-------|
| Week 0 (Validation) | Week 0 | 🚧 In Progress | - | See `spikes/week0-validation/VALIDATION-RESULTS.md` |
| M1: Read-Only Agent | 1-2 | 🔜 Not Started | - | - |
| M2: HIL Gate | 3-4 | 🔜 Not Started | - | - |
| M3: Agent-Opens-PR | 5-6 | 🔜 Not Started | - | - |
| M4: Full Drawer + TrustyAI | 7-8 | 🔜 Not Started | - | - |
| M5: Cosmos NIMs | 9-10 | 🔜 Not Started | - | - |
| Buffer: Integration | 11-12 | 🔜 Not Started | - | - |

**Legend**:
- 🔜 Not Started
- 🚧 In Progress
- ✅ Complete
- ⚠️ Blocked (see Notes)
- ❌ Deferred to Phase 4

---

## Related Documents

- **Phase 3 Plan**: `../phase-3-agentic-implementation.md` (architectural decisions, requirements)
- **Validation Spikes**: `../../../spikes/week0-validation/` (infrastructure validation)
- **Component Catalog**: `../../03-component-catalog.md` (what each component does)
- **GPU Scheduling**: `../../08-gpu-resource-planning.md` (GPU allocation)

---

**Current Phase**: Week 0 Validation (see `week-0-validation.md`)
