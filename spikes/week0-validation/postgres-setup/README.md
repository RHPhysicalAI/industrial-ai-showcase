# Postgres Schema Validation - Week 0 Day 3

**Purpose**: Validate that Postgres can store LangGraph agent session state and HIL audit trails using JSONB.

**Status**: ✅ Complete (all 6 tests passed)

---

## What This Validates

This spike proves that Postgres 15 can handle the Phase 3 agent orchestration persistence requirements:

1. **Agent Session State** - Store LangGraph checkpointer state as JSONB
2. **Audit Trails** - Append-only JSONB arrays for tool call history
3. **HIL Approvals** - Immutable audit log of human-in-the-loop decisions
4. **JSONB Queries** - Fast queries on nested JSON structures
5. **Integrity** - Foreign keys, CHECK constraints, indexes

---

## Quick Start

### 1. Deploy Postgres to Cluster

```bash
oc apply -f postgres.yaml
oc get pod -n agentic-ops -l app=postgres  # Wait for Running
```

### 2. Port-Forward

```bash
oc port-forward -n agentic-ops svc/postgres 5432:5432 &
```

### 3. Load Schema

```bash
python -m venv .venv
source .venv/bin/activate
pip install psycopg2-binary  # or: uv pip install psycopg2-binary

python load_schema.py
```

### 4. Run Tests

```bash
python test_schema.py
```

Expected output:
```
✅ Test 1: Inserted agent session
✅ Test 2: Found fleet manager sessions
✅ Test 3: Appended to audit trail
✅ Test 4: Inserted HIL audit record
✅ Test 5: Found approved state-modifying actions
✅ Test 6: Deep JSONB query works

All 6 tests passed!
```

---

## File Structure

```
postgres-setup/
├── README.md              # This file
├── postgres.yaml          # K8s deployment (Secret, Deployment, Service)
├── schema.sql             # DDL for agent_sessions + hil_audit tables
├── load_schema.py         # Python script to load schema.sql
├── test_schema.py         # 6 tests validating JSONB operations
├── check_permissions.py   # Debug script (permission checker)
└── DAY3-RESULTS.md        # Full test results and learnings
```

---

## Connection Details

**After port-forward is active:**

```python
import psycopg2

conn = psycopg2.connect(
    "postgresql://agent:changeme123@localhost:5432/agentic_orchestrator"
)
```

**From within the cluster:**

```
Host: postgres.agentic-ops.svc
Port: 5432
Database: agentic_orchestrator
Username: agent
Password: changeme123  (from postgres-secret)
```

---

## Schema Overview

### Table: `agent_sessions`

Stores LangGraph agent execution state.

```sql
CREATE TABLE agent_sessions (
  session_id UUID PRIMARY KEY,
  operator_identity TEXT NOT NULL,        -- CAC/PIV DN or OAuth sub
  started_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
  state JSONB NOT NULL,                   -- LangGraph checkpointer state
  audit_trail JSONB[] NOT NULL DEFAULT '{}' -- Array of tool calls
);
```

**Example JSONB state:**
```json
{
  "graph": "fleet_manager_agent",
  "checkpoint": {
    "messages": [
      {"role": "user", "content": "Show me robot status"},
      {"role": "assistant", "content": "I'll check the fleet API"}
    ],
    "next_step": "call_fleet_api"
  }
}
```

**Indexes:**
- `idx_agent_sessions_operator` on `operator_identity`
- `idx_agent_sessions_updated` on `updated_at DESC`

---

### Table: `hil_audit`

Immutable audit log of human-in-the-loop approvals/rejections.

```sql
CREATE TABLE hil_audit (
  action_id UUID PRIMARY KEY,
  timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
  session_id UUID REFERENCES agent_sessions(session_id),
  operator_identity TEXT NOT NULL,
  tool_call JSONB NOT NULL,
  classification TEXT NOT NULL CHECK (classification IN ('read-only', 'state-modifying')),
  guardrail_results JSONB NOT NULL,
  decision TEXT NOT NULL CHECK (decision IN ('approved', 'rejected')),
  rejection_reason TEXT,
  pr_url TEXT,                            -- GitHub PR URL for agent-opens-PR pattern
  context_trail_hash TEXT NOT NULL        -- SHA256 of MCP trace
);
```

**Example tool_call JSONB:**
```json
{
  "tool": "mcp.update_robot_config",
  "args": {
    "robot_id": "robot-001",
    "speed_limit": 0.5
  }
}
```

**Example guardrail_results JSONB:**
```json
{
  "pii_scan": {"found_pii": false},
  "safety_check": {"risk_level": "low"},
  "scope_check": {"approved_namespace": true}
}
```

**Indexes:**
- `idx_hil_audit_operator` on `operator_identity`
- `idx_hil_audit_timestamp` on `timestamp DESC`
- `idx_hil_audit_decision` on `decision`

---

## JSONB Query Examples

### Query agent sessions by graph type

```sql
SELECT session_id, operator_identity, state->>'graph' as graph_name
FROM agent_sessions
WHERE state->>'graph' = 'fleet_manager_agent';
```

### Deep nested query (checkpoint next_step)

```sql
SELECT session_id, state#>>'{checkpoint,next_step}' as next_step
FROM agent_sessions
WHERE state#>>'{checkpoint,next_step}' IS NOT NULL;
```

### Append to audit trail

```python
tool_call = {
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "tool": "mcp.fleet_status",
    "args": {"robot_id": "robot-001"},
    "result": {"status": "operational", "battery": 85}
}

cur.execute("""
    UPDATE agent_sessions
    SET audit_trail = audit_trail || %s::jsonb,
        updated_at = NOW()
    WHERE session_id = %s
""", (Json(tool_call), session_id))
```

### Find approved state-modifying actions

```sql
SELECT action_id, tool_call->>'tool' as tool_name, decision
FROM hil_audit
WHERE classification = 'state-modifying'
  AND decision = 'approved'
ORDER BY timestamp DESC;
```

---

## What The Tests Validate

| Test | What It Checks |
|------|----------------|
| Test 1 | Insert agent session with JSONB state |
| Test 2 | Query JSONB using `->` and `->>` operators |
| Test 3 | Append to JSONB[] array with `\|\|` operator |
| Test 4 | Insert HIL audit with foreign key + CHECK constraints |
| Test 5 | Query HIL audit by classification and decision |
| Test 6 | Deep JSONB path query with `#>>` operator |

---

## Prerequisites

- OpenShift cluster with `agentic-ops` namespace
- `oc` CLI logged in
- Python 3.8+ with `psycopg2-binary`

---

## Deployment Notes

⚠️ **This is a SPIKE deployment, not production-ready**

**Limitations:**
- EmptyDir storage (data lost on pod restart)
- No replicas, no backups
- Simple password authentication
- No TLS/SSL
- No resource quotas or limits tuning

**For production (Milestone 1+):**
- Use PVC with block storage (ODF)
- Deploy as StatefulSet with replicas
- Use Postgres Operator (Crunchy Data or CloudNativePG)
- Enable TLS
- Use cert-based auth or Vault integration
- Set up WAL archiving and point-in-time recovery

---

## Troubleshooting

### Port-forward keeps dying

```bash
# Kill any existing port-forwards
pkill -f "port-forward.*postgres"

# Use service, not pod
oc port-forward -n agentic-ops svc/postgres 5432:5432 &
```

### Connection refused

```bash
# Check pod is running
oc get pod -n agentic-ops -l app=postgres

# Check port-forward is listening
lsof -i :5432
```

### Permission denied errors

This spike deployment gives the `agent` user full CREATE privileges on the `public` schema. If you see permission errors, you might be connecting to a different database.

### psycopg2 UUID errors

```python
from psycopg2.extras import register_uuid
register_uuid()  # Call this before using uuid.uuid4()
```

---

## Next Steps After Week 0

**Milestone 1** will upgrade this to production-grade:

1. Deploy Crunchy Postgres Operator
2. Create PostgresCluster CR with HA + backups
3. Configure PVC storage (ODF block)
4. Enable TLS with cert-manager
5. Integrate with OpenShift OAuth or Vault
6. Set up monitoring (Prometheus + Grafana)
7. Configure WAL archiving to S3 (ODF RGW)

---

## Related Documentation

- [Week 0 Validation Plan](../../../docs/plans/phase-3-milestones/week-0-validation.md)
- [Phase 3 Implementation](../../../docs/plans/phase-3-agentic-implementation.md)
- [ADR-019: Llama Stack HIL](../../../docs/07-decisions.md) (HIL approval pattern)
- [Postgres JSONB Docs](https://www.postgresql.org/docs/15/datatype-json.html)

---

**Status**: ✅ All validation tests passed (2026-07-02)
