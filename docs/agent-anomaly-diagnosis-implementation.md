# Agent Anomaly Diagnosis - Implementation Guide

> [!NOTE]
> This project was developed with assistance from AI tools.

**Status**: Day 1 in progress (2026-07-21)  
**Target**: 3-4 day demo implementation  
**Purpose**: Agent investigates and explains automatic rollbacks

---

## Feature Overview

When Fleet Manager automatically rolls back a model due to anomaly detection, the agent:
1. **Detects** the rollback event (via Kafka)
2. **Investigates** what happened (using MCP tools)
3. **Explains** the root cause to the operator (in Console UI)

**Key Design Principle**: Rollback is IMMEDIATE (safety first). Agent investigation happens AFTER (adds intelligence, doesn't block safety).

---

## Demo Flow

```
Operator promotes v1.4 to Factory B (normal HIL approval flow)
    ↓
[14 minutes later] Run: python scripts/demo-trigger-rollback.py
    ↓
Synthetic rollback event published to Kafka (fleet.events topic)
    ↓
Orchestrator receives event → triggers agent investigation
    ↓
Agent queries:
  - hil_audit table (when was v1.4 promoted?)
  - get_factory_config (what's current version?)
  - get_run (what were v1.4's training scenarios?)
    ↓
Agent generates analysis:
  "v1.4 was promoted 14 min before rollback
   Collision rate spiked 3x (0.05 → 0.15)
   Training lacked dense-obstacle scenarios
   Hypothesis: Reduced obstacle avoidance sensitivity"
    ↓
Console UI shows toast: "⚠️ Auto-rollback detected - Factory B v1.4 → v1.3"
    ↓
Click toast → Drawer opens with full agent analysis
```

---

## Implementation Timeline

### Day 1: Event Trigger + Listener (COMPLETE)

**Created**:
- ✅ `scripts/demo-trigger-rollback.py` - Synthetic event generator
- ✅ `event_listener.py` - Kafka consumer for fleet events

---

### Day 2: Agent Investigation Logic (COMPLETE)

**Built**:
- ✅ Integrated event_listener into api_server.py startup
- ✅ Added `handle_rollback_event()` async callback
- ✅ Agent investigation query with structured prompt
- ✅ Agent tool sequence (queries hil_audit, factory config, MLflow)
- ✅ Publish rollback.analysis event to Kafka
- ✅ Full logging for verification

---

### Day 3-4: UI Integration

**To Build**:
- [ ] Console backend: proxy rollback events to frontend
- [ ] Frontend: toast notification on rollback
- [ ] HILDrawer: new "Fleet Analysis" pane
- [ ] Display agent's evidence, hypothesis, recommendation

---

## File Inventory

### Scripts
- `scripts/demo-trigger-rollback.py` - Trigger synthetic rollback for demo

### Orchestrator
- `infrastructure/gitops/apps/workloads/agentic-orchestrator/src/event_listener.py` - Kafka consumer
- `infrastructure/gitops/apps/workloads/agentic-orchestrator/src/api_server.py` - (TO MODIFY) Start listener
- `infrastructure/gitops/apps/workloads/agentic-orchestrator/src/orchestrator.py` - (TO MODIFY) Investigation logic

### Console
- `console/backend/src/server.ts` - (TO MODIFY) Proxy events
- `console/frontend/src/HILDrawer.tsx` - (TO MODIFY) Fleet Analysis pane
- `console/frontend/src/FleetView.tsx` - (TO MODIFY) Toast notifications
- `console/frontend/src/api.ts` - (TO MODIFY) Type definitions

---

## Event Schema

**fleet.events topic - policy.rollback event**:
```json
{
  "type": "policy.rollback",
  "factory": "Factory B",
  "from_version": "v1.4",
  "to_version": "v1.3",
  "trigger": "collision_rate_threshold",
  "timestamp": "2026-07-21T10:00:00Z",
  "metrics": {
    "collision_rate_before": 0.05,
    "collision_rate_after": 0.15,
    "threshold": 0.10,
    "time_since_promotion_minutes": 14
  },
  "reason": "Collision rate exceeded threshold (0.15 > 0.10)",
  "auto_rollback": true
}
```

---

## Agent Analysis Output Schema

**What agent generates**:
```json
{
  "event": "rollback",
  "factory": "Factory B",
  "from_version": "v1.4",
  "to_version": "v1.3",
  "promotion_timestamp": "2026-07-21T09:46:00Z",
  "rollback_timestamp": "2026-07-21T10:00:00Z",
  "time_delta_minutes": 14,
  "evidence": [
    "v1.4 was promoted 14 minutes before rollback",
    "Collision rate: 0.05 → 0.15 (3x increase)",
    "v1.4 training: no dense-obstacle test scenarios in MLflow run"
  ],
  "hypothesis": "v1.4 may have reduced obstacle avoidance sensitivity",
  "recommendation": "Retrain v1.5 with Factory B obstacle density data",
  "mlflow_run_id": "abc123",
  "confidence": "medium"
}
```

---

## Testing

### Manual Test (Day 1)

```bash
# Terminal 1: Watch orchestrator logs
oc logs -f -n agentic-ops deployment/agentic-orchestrator

# Terminal 2: Trigger rollback
python scripts/demo-trigger-rollback.py

# Expected: See "Rollback detected: Factory B v1.4 → v1.3" in logs
```

### Demo Test (Day 4)

```bash
# Step 1: Promote v1.4 via Console UI (normal flow)
# Step 2: Wait 30 seconds for PR merge + Argo sync
# Step 3: Trigger rollback
python scripts/demo-trigger-rollback.py

# Expected: Toast appears in UI, click opens drawer with analysis
```

---

## Demo Script (60-min Deep Dive, Segment 2)

**[After showing normal promotion flow]**

Narrator: *"Now imagine 14 minutes later, sensors detect a collision rate spike..."*

**Action**: Run `python scripts/demo-trigger-rollback.py`

Narrator: *"Factory B's rule-based safety system IMMEDIATELY rolls back to v1.3 - no human approval needed, no delay. But watch what the agent does..."*

**[Toast appears in UI]**

Narrator: *"The agent didn't BLOCK the rollback - that would be dangerous. Instead, it's investigating WHY in the background. Click to see..."*

**[Click toast → Drawer opens]**

Narrator: *"The agent examined:
- When v1.4 was promoted (14 minutes ago)
- The collision rate spike (3x increase)
- The MLflow training run for v1.4
- Found the gap: no dense-obstacle scenarios in training

This is the differentiation. Not AI making safety decisions - AI explaining failures so engineers can prevent them next time."*

**Demo beat duration**: 2-3 minutes  
**Impact**: ⭐⭐⭐⭐⭐

---

## Next Session TODO (Day 3-4)

- [ ] Console backend: proxy rollback.analysis events to frontend
- [ ] Frontend: toast notification on rollback
- [ ] HILDrawer: new "Fleet Analysis" pane
- [ ] Test end-to-end demo flow

**Testing the agent logic (Day 2 verification)**:
```bash
# Terminal 1: Watch orchestrator logs
oc logs -f -n agentic-ops deployment/agentic-orchestrator

# Terminal 2: Trigger rollback event
python scripts/demo-trigger-rollback.py

# Expected in logs:
# - "🔍 Rollback event received: Factory B v1.4 → v1.3"
# - "Triggering agent investigation (session: rollback-analysis-...)"
# - "✅ Agent analysis complete"
# - "Published rollback.analysis event to Kafka"
```

---

**Implementation started**: 2026-07-21  
**Day 1-2 complete**: 2026-07-21  
**Target completion**: 2026-07-24 (3-4 days)
