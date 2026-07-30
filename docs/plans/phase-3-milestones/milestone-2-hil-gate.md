# Phase 3 Milestone 2: Human-in-the-Loop (HIL) Approval Gate

> [!NOTE]
> This project was developed with assistance from AI tools.

**Status**: Planning → Implementation  
**Duration**: 5 days (1 week)  
**Prerequisites**: Milestone 1 complete ✅  
**Target Completion**: TBD

---

## Executive Summary

Milestone 2 introduces **Human-in-the-Loop (HIL) approval** for state-modifying agentic actions. When the AI assistant proposes a write operation (e.g., registering a model, updating fleet configuration), the operator must explicitly approve or reject the action before it executes. Read-only queries continue to bypass the approval gate.

**Key Deliverable**: 3-pane approval drawer in Showcase Console that pauses agent execution, displays proposed action details, and records approval decisions in an immutable audit trail.

**Simplified vs Full**: This Milestone implements a **simplified HIL pattern** to prove the approval workflow. Full governance with Llama Stack (guardrails, blast-radius analysis, TrustyAI evaluation) happens in Phase 3 Milestone 3+.

---

## Goals

### Primary Goal
Enable human oversight of state-modifying agentic actions through a clear approval workflow.

### Technical Goals
1. ✅ Add at least 1 state-modifying MCP tool (`register_model`)
2. ✅ Orchestrator detects state-modifying tools and pauses execution
3. ✅ 3-pane HIL drawer opens in Console UI
4. ✅ Operator can approve or reject from drawer
5. ✅ Audit trail records all approval decisions (Postgres)
6. ✅ Read-only tools bypass HIL gate (no approval required)

### Non-Goals (Deferred to Later Milestones)
- ❌ Llama Stack Agents API integration (Milestone 3)
- ❌ Guardrails (PII scan, safety checks) (Milestone 4)
- ❌ Blast-radius analysis (Milestone 4)
- ❌ TrustyAI evaluation (Milestone 4)
- ❌ 6-pane drawer with full context (Milestone 4)
- ❌ CAC/PIV identity binding (Phase 3 later)

---

## Architecture

### Current Flow (Milestone 1 - Read-Only)
```
User query → Console → Orchestrator → vLLM (tool calling) → MCP server → Response
```

### New Flow (Milestone 2 - With HIL)
```
User: "Register model from run run-001-a as 'test-model'"
   ↓
Console → Orchestrator → vLLM (proposes tool call)
   ↓
Is tool state-modifying? (Check MCP schema)
   ↙ No                    ↘ Yes
Execute immediately    Store pending approval in audit service
Return response        Create approval request ID
                       Return "waiting_for_approval" to Console
                              ↓
                       HIL Drawer Opens (3 panes):
                         - Proposed Action Summary
                         - Approval Reasoning
                         - Recent Audit History
                              ↓
                       Operator Reviews & Decides
                              ↓
                    ┌─────────┴─────────┐
                Approve              Reject
                    ↓                   ↓
            POST /api/approval/     POST /api/approval/
            {id}/approve            {id}/reject
                    ↓                   ↓
            Audit: status=approved  Audit: status=rejected
                    ↓                   ↓
            Execute tool            Return rejection message
                    ↓                   ↓
            Return response         User sees "Action rejected"
```

---

## Components

### 1. MCP MLflow Server (Extended)

**Location**: `infrastructure/gitops/apps/workloads/mcp-mlflow-server/src/mcp_server.py`

**New State-Modifying Tool**:
```python
@app.post("/tools/register_model")
async def register_model(run_id: str, model_name: str):
    """
    Register a model from a run (state-modifying).
    
    In mock implementation, returns success.
    In real MLflow, would call mlflow.register_model().
    """
    return {
        "model_name": model_name,
        "version": 1,
        "run_id": run_id,
        "status": "registered",
        "message": f"Model '{model_name}' registered from run {run_id}"
    }
```

**Updated Tool Discovery** (`/mcp/tools`):
```json
{
  "tools": [
    {
      "name": "register_model",
      "description": "Register a model from a run",
      "state_modifying": true,  // NEW FIELD
      "parameters": {
        "run_id": {"type": "string", "required": true},
        "model_name": {"type": "string", "required": true}
      },
      "endpoint": "/tools/register_model"
    }
  ]
}
```

**Deployment**:
- Already running in `agentic-ops` namespace
- No new resources needed (code change only)

---

### 2. Audit Service (New Component)

**Location**: `infrastructure/gitops/apps/workloads/audit-service/`

**Purpose**: Manage approval requests and persist audit trail.

**API Endpoints**:
```
POST   /audit/pending          - Create pending approval request
GET    /audit/pending          - List all pending approvals
POST   /audit/approve/{id}     - Approve request
POST   /audit/reject/{id}      - Reject request with reason
GET    /audit/history          - Query audit history
GET    /health                 - Health check
```

**Database**: Reuses existing `mlflow-db` CloudNativePG cluster

**Schema** (new table):
```sql
CREATE TABLE IF NOT EXISTS hil_audit (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT now(),
    session_id TEXT NOT NULL,
    user_identity TEXT NOT NULL DEFAULT 'demo-operator',
    tool_name TEXT NOT NULL,
    tool_arguments JSONB NOT NULL,
    approval_status TEXT NOT NULL,  -- 'pending' | 'approved' | 'rejected'
    approval_timestamp TIMESTAMPTZ,
    approver_identity TEXT,
    rejection_reason TEXT,
    result JSONB,
    error TEXT
);

CREATE INDEX idx_hil_audit_session ON hil_audit(session_id);
CREATE INDEX idx_hil_audit_timestamp ON hil_audit(timestamp DESC);
CREATE INDEX idx_hil_audit_status ON hil_audit(approval_status);
```

**Deployment Manifest**:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: audit-service
  namespace: agentic-ops
spec:
  replicas: 1
  selector:
    matchLabels:
      app: audit-service
  template:
    metadata:
      labels:
        app: audit-service
    spec:
      containers:
      - name: audit-service
        image: image-registry.openshift-image-registry.svc:5000/agentic-ops/audit-service:latest
        ports:
        - containerPort: 8090
          name: http
        env:
        - name: POSTGRES_HOST
          valueFrom:
            secretKeyRef:
              name: mlflow-db-app
              key: host
        - name: POSTGRES_USER
          valueFrom:
            secretKeyRef:
              name: mlflow-db-app
              key: username
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: mlflow-db-app
              key: password
        - name: POSTGRES_DB
          value: mlflow
        resources:
          requests:
            cpu: 500m
            memory: 1Gi
          limits:
            cpu: 1
            memory: 2Gi
---
apiVersion: v1
kind: Service
metadata:
  name: audit-service
  namespace: agentic-ops
spec:
  selector:
    app: audit-service
  ports:
  - port: 8090
    targetPort: 8090
    name: http
```

---

### 3. Agentic Orchestrator (Extended)

**Location**: `infrastructure/gitops/apps/workloads/agentic-orchestrator/src/orchestrator.py`

**Changes**:

1. **Add tool schema cache** (from MCP discovery):
```python
# Cache tool schemas on startup
TOOL_SCHEMAS = {}

def discover_tools():
    """Discover MCP tools and cache schemas."""
    response = mcp_client.client.get(f"{MCP_BASE_URL}/mcp/tools")
    tools_data = response.json()["tools"]
    for tool in tools_data:
        TOOL_SCHEMAS[tool["name"]] = tool
```

2. **Add conditional routing after tool execution**:
```python
def should_wait_for_approval(state: AgentState) -> str:
    """
    Check if last tool call requires approval.
    Route to 'pending_approval' if state-modifying, else 'continue'.
    """
    last_message = state["messages"][-1]
    
    if isinstance(last_message, ToolMessage):
        tool_name = last_message.name
        tool_schema = TOOL_SCHEMAS.get(tool_name, {})
        
        if tool_schema.get("state_modifying", False):
            # Create approval request in audit service
            approval_id = create_approval_request(
                tool_name=tool_name,
                arguments=last_message.additional_kwargs.get("tool_call", {}),
                session_id=state.get("session_id", "demo-session")
            )
            
            # Store in state
            state["pending_approval_id"] = approval_id
            state["pending_tool_call"] = last_message
            
            return "pending_approval"
    
    return "continue"

# Update workflow graph
workflow.add_conditional_edges(
    "tools",
    should_wait_for_approval,
    {
        "continue": "agent",
        "pending_approval": "await_approval"
    }
)
```

3. **Add await_approval node**:
```python
def await_approval(state: AgentState) -> AgentState:
    """
    Pause execution, return 'waiting' status to frontend.
    Execution resumes when /approval/{id}/resume is called.
    """
    approval_id = state["pending_approval_id"]
    
    state["messages"].append(
        AIMessage(content=f"⏸️ Waiting for operator approval (request ID: {approval_id})")
    )
    
    return state
```

**API Changes** (`api_server.py`):

Add approval resume endpoint:
```python
@app.post("/approval/{approval_id}/resume")
async def resume_after_approval(
    approval_id: str,
    decision: str,
    reason: Optional[str] = None
):
    """
    Resume agent execution after approval/rejection.
    """
    if decision == "approved":
        # Load pending state
        state = load_pending_state(approval_id)
        
        # Execute the pending tool call
        result = execute_tool(state["pending_tool_call"])
        
        # Update audit record
        update_audit_result(approval_id, result)
        
        # Continue agent execution
        final_state = workflow.invoke(state)
        
        return extract_final_response(final_state)
    else:
        # Record rejection
        update_audit_rejection(approval_id, reason)
        
        return {
            "query": "...",
            "response": f"Action rejected by operator. Reason: {reason}"
        }
```

---

### 4. Console Backend (Extended)

**Location**: `console/backend/src/server.ts`

**Add Config**:
```typescript
// In config.ts
export interface AppConfig {
  // ... existing fields
  agenticOrchestratorUrl: string;
  auditServiceUrl: string;  // NEW
}

export const config: AppConfig = {
  // ... existing config
  auditServiceUrl:
    process.env.AUDIT_SERVICE_URL ??
    "http://audit-service.agentic-ops.svc.cluster.local:8090",
};
```

**Add Approval Endpoints**:
```typescript
// Get pending approvals
fastify.get("/api/approval/pending", async () => {
  try {
    const resp = await fetch(`${config.auditServiceUrl}/audit/pending`);
    if (!resp.ok) {
      return { pending: [] };
    }
    return await resp.json();
  } catch (err) {
    log.error({ err }, "Failed to fetch pending approvals");
    return { pending: [] };
  }
});

// Approve request
fastify.post<{ Params: { id: string } }>(
  "/api/approval/:id/approve",
  async (request, reply) => {
    const { id } = request.params;
    
    try {
      // Record approval in audit service
      await fetch(`${config.auditServiceUrl}/audit/approve/${id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          approver_identity: "demo-operator",  // TODO: Extract from auth
        }),
      });
      
      // Resume orchestrator
      const result = await fetch(
        `${config.agenticOrchestratorUrl}/approval/${id}/resume`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ decision: "approved" }),
        }
      );
      
      if (!result.ok) {
        throw new Error(`Resume failed: ${result.statusText}`);
      }
      
      return await result.json();
    } catch (err) {
      log.error({ err, id }, "Approval failed");
      reply.code(500).send({ error: "Approval processing failed" });
    }
  }
);

// Reject request
fastify.post<{ Params: { id: string }; Body: { reason: string } }>(
  "/api/approval/:id/reject",
  async (request, reply) => {
    const { id } = request.params;
    const { reason } = request.body;
    
    if (!reason || typeof reason !== "string") {
      reply.code(400).send({ error: "Rejection reason required" });
      return;
    }
    
    try {
      // Record rejection in audit service
      await fetch(`${config.auditServiceUrl}/audit/reject/${id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          approver_identity: "demo-operator",
          reason,
        }),
      });
      
      // Resume orchestrator with rejection
      const result = await fetch(
        `${config.agenticOrchestratorUrl}/approval/${id}/resume`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ decision: "rejected", reason }),
        }
      );
      
      if (!result.ok) {
        throw new Error(`Resume failed: ${result.statusText}`);
      }
      
      return await result.json();
    } catch (err) {
      log.error({ err, id }, "Rejection failed");
      reply.code(500).send({ error: "Rejection processing failed" });
    }
  }
);
```

**Update Deployment**:
```yaml
# In infrastructure/gitops/apps/workloads/console/deployments.yaml
# Add to backend container env:
- name: AUDIT_SERVICE_URL
  value: http://audit-service.agentic-ops.svc.cluster.local:8090
```

---

### 5. Console Frontend (Extended)

**New Component**: `console/frontend/src/HILDrawer.tsx`

**Interface**:
```typescript
interface ApprovalRequest {
  id: string;
  timestamp: string;
  tool_name: string;
  tool_arguments: Record<string, any>;
  session_id: string;
  user_identity: string;
}

interface HILDrawerProps {
  approvalRequest: ApprovalRequest;
  onApprove: () => void;
  onReject: (reason: string) => void;
  onClose: () => void;
}
```

**Component Structure**:
```typescript
export function HILDrawer({
  approvalRequest,
  onApprove,
  onReject,
  onClose,
}: HILDrawerProps) {
  const [rejectReason, setRejectReason] = useState("");
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [auditHistory, setAuditHistory] = useState([]);
  
  useEffect(() => {
    // Fetch recent audit history
    fetch("/api/approval/history?limit=5")
      .then(r => r.json())
      .then(data => setAuditHistory(data.history || []));
  }, []);
  
  return (
    <Stack hasGutter>
      {/* Pane 1: Proposed Action Summary */}
      <StackItem>
        <Card>
          <CardHeader>
            <CardTitle>Proposed Action</CardTitle>
          </CardHeader>
          <CardBody>
            <DescriptionList>
              <DescriptionListGroup>
                <DescriptionListTerm>Tool</DescriptionListTerm>
                <DescriptionListDescription>
                  <Code>{approvalRequest.tool_name}</Code>
                </DescriptionListDescription>
              </DescriptionListGroup>
              <DescriptionListGroup>
                <DescriptionListTerm>Arguments</DescriptionListTerm>
                <DescriptionListDescription>
                  <CodeBlock>
                    <CodeBlockCode>
                      {JSON.stringify(approvalRequest.tool_arguments, null, 2)}
                    </CodeBlockCode>
                  </CodeBlock>
                </DescriptionListDescription>
              </DescriptionListGroup>
              <DescriptionListGroup>
                <DescriptionListTerm>Session</DescriptionListTerm>
                <DescriptionListDescription>
                  {approvalRequest.session_id}
                </DescriptionListDescription>
              </DescriptionListGroup>
            </DescriptionList>
          </CardBody>
        </Card>
      </StackItem>
      
      {/* Pane 2: Approval Reasoning */}
      <StackItem>
        <Card>
          <CardHeader>
            <CardTitle>Review</CardTitle>
          </CardHeader>
          <CardBody>
            {approvalRequest.tool_name === "register_model" && (
              <Alert variant="info" isInline title="Action Impact">
                This action will register a new model in MLflow from run{" "}
                <strong>{approvalRequest.tool_arguments.run_id}</strong> as{" "}
                <strong>{approvalRequest.tool_arguments.model_name}</strong>.
                This creates a new model registry entry.
              </Alert>
            )}
            <p style={{ marginTop: 16 }}>
              Review the proposed action above and approve if the change is
              intended and safe to execute.
            </p>
          </CardBody>
        </Card>
      </StackItem>
      
      {/* Pane 3: Recent Audit History */}
      <StackItem>
        <Card>
          <CardHeader>
            <CardTitle>Recent Approvals</CardTitle>
          </CardHeader>
          <CardBody>
            {auditHistory.length === 0 ? (
              <EmptyState variant="small">
                <EmptyStateHeader titleText="No recent activity" />
              </EmptyState>
            ) : (
              <DataList isCompact>
                {auditHistory.map((entry: any) => (
                  <DataListItem key={entry.id}>
                    <DataListItemRow>
                      <DataListItemCells
                        dataListCells={[
                          <DataListCell key="timestamp">
                            <small>{new Date(entry.timestamp).toLocaleString()}</small>
                          </DataListCell>,
                          <DataListCell key="tool">
                            {entry.tool_name}
                          </DataListCell>,
                          <DataListCell key="status">
                            <Label
                              color={
                                entry.approval_status === "approved"
                                  ? "green"
                                  : entry.approval_status === "rejected"
                                  ? "red"
                                  : "orange"
                              }
                            >
                              {entry.approval_status}
                            </Label>
                          </DataListCell>,
                        ]}
                      />
                    </DataListItemRow>
                  </DataListItem>
                ))}
              </DataList>
            )}
          </CardBody>
        </Card>
      </StackItem>
      
      {/* Action Buttons */}
      <StackItem>
        <ActionGroup>
          <Button variant="primary" onClick={onApprove}>
            Approve
          </Button>
          <Button variant="danger" onClick={() => setShowRejectModal(true)}>
            Reject
          </Button>
          <Button variant="link" onClick={onClose}>
            Close
          </Button>
        </ActionGroup>
      </StackItem>
      
      {/* Reject Modal */}
      <Modal
        title="Reject Action"
        isOpen={showRejectModal}
        onClose={() => setShowRejectModal(false)}
        actions={[
          <Button
            key="confirm"
            variant="danger"
            onClick={() => {
              onReject(rejectReason);
              setShowRejectModal(false);
            }}
            isDisabled={!rejectReason.trim()}
          >
            Confirm Rejection
          </Button>,
          <Button
            key="cancel"
            variant="link"
            onClick={() => setShowRejectModal(false)}
          >
            Cancel
          </Button>,
        ]}
      >
        <Form>
          <FormGroup label="Rejection Reason" isRequired>
            <TextArea
              value={rejectReason}
              onChange={(_e, value) => setRejectReason(value)}
              placeholder="Explain why this action is being rejected..."
              rows={4}
            />
          </FormGroup>
        </Form>
      </Modal>
    </Stack>
  );
}
```

**Integration into AgentAssistant.tsx**:
```typescript
// In AgentAssistant.tsx, add state:
const [pendingApproval, setPendingApproval] = useState<ApprovalRequest | null>(null);

// Poll for pending approvals when message has "waiting_for_approval" status
useEffect(() => {
  if (messages.some(m => m.content.includes("Waiting for operator approval"))) {
    const interval = setInterval(async () => {
      const resp = await fetch("/api/approval/pending");
      const data = await resp.json();
      if (data.pending && data.pending.length > 0) {
        setPendingApproval(data.pending[0]);
      }
    }, 2000);  // Poll every 2 seconds
    
    return () => clearInterval(interval);
  }
}, [messages]);

// Show HIL drawer if pending approval exists
{pendingApproval && (
  <HILDrawer
    approvalRequest={pendingApproval}
    onApprove={async () => {
      const resp = await fetch(`/api/approval/${pendingApproval.id}/approve`, {
        method: "POST",
      });
      const result = await resp.json();
      setPendingApproval(null);
      // Add result to messages
      setMessages(prev => [...prev, {
        role: "assistant",
        content: result.response,
        timestamp: new Date().toISOString(),
        status: "complete",
      }]);
    }}
    onReject={async (reason) => {
      const resp = await fetch(`/api/approval/${pendingApproval.id}/reject`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason }),
      });
      const result = await resp.json();
      setPendingApproval(null);
      setMessages(prev => [...prev, {
        role: "assistant",
        content: result.response,
        timestamp: new Date().toISOString(),
        status: "error",
      }]);
    }}
    onClose={() => setPendingApproval(null)}
  />
)}
```

---

## Day-by-Day Implementation Plan

### Day 1: MCP Server State-Modifying Tool + Audit Service Skeleton

**Tasks**:
1. Add `register_model` tool to `mcp_server.py`
2. Update `/mcp/tools` discovery with `state_modifying` field
3. Create audit-service scaffolding (FastAPI + Postgres connection)
4. Create database migration file
5. Create audit-service deployment manifests

**Files to Create/Modify**:
- `infrastructure/gitops/apps/workloads/mcp-mlflow-server/src/mcp_server.py`
- `infrastructure/gitops/apps/workloads/audit-service/src/audit_server.py` (new)
- `infrastructure/gitops/apps/workloads/audit-service/migrations/001_create_hil_audit.sql` (new)
- `infrastructure/gitops/apps/workloads/audit-service/Containerfile` (new)
- `infrastructure/gitops/apps/workloads/audit-service/deployment.yaml` (new)
- `infrastructure/gitops/apps/workloads/audit-service/service.yaml` (new)
- `infrastructure/gitops/apps/workloads/audit-service/buildconfig.yaml` (new)
- `infrastructure/gitops/apps/workloads/audit-service/imagestream.yaml` (new)

**Testing**:
```bash
# Test MCP server
curl http://mcp-mlflow-server:8080/mcp/tools | jq '.tools[] | select(.name == "register_model")'

# Test audit service
curl http://audit-service:8090/health
curl -X POST http://audit-service:8090/audit/pending \
  -H "Content-Type: application/json" \
  -d '{"tool_name": "test", "tool_arguments": {}, "session_id": "test"}'
```

**Success Criteria**:
- ✅ MCP server returns `register_model` in tool discovery with `state_modifying: true`
- ✅ Audit service health check passes
- ✅ Can create and query pending approvals via audit service API

---

### Day 2: Orchestrator HIL Gate + Approval Resume Logic

**Tasks**:
1. Add tool schema caching in orchestrator
2. Implement `should_wait_for_approval()` conditional routing
3. Add `await_approval` node to LangGraph workflow
4. Add `/approval/{id}/resume` endpoint to API server
5. Implement state persistence for pending approvals

**Files to Modify**:
- `infrastructure/gitops/apps/workloads/agentic-orchestrator/src/orchestrator.py`
- `infrastructure/gitops/apps/workloads/agentic-orchestrator/src/api_server.py`

**Testing**:
```bash
# Test state-modifying tool triggers HIL gate
curl -X POST http://agentic-orchestrator:8080/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Register model from run run-001-a as test-model"}'

# Expected: Returns "Waiting for operator approval (request ID: ...)"

# Test resume endpoint
curl -X POST http://agentic-orchestrator:8080/approval/1/resume \
  -H "Content-Type: application/json" \
  -d '{"decision": "approved"}'
```

**Success Criteria**:
- ✅ State-modifying tool triggers `should_wait_for_approval()`
- ✅ Orchestrator creates pending approval in audit service
- ✅ Returns "waiting" response to frontend
- ✅ Resume endpoint completes tool execution after approval
- ✅ Read-only tools bypass HIL gate (immediate execution)

---

### Day 3: Console Backend Approval Endpoints + Database Migration

**Tasks**:
1. Add `auditServiceUrl` to console backend config
2. Implement `/api/approval/pending` endpoint
3. Implement `/api/approval/:id/approve` endpoint
4. Implement `/api/approval/:id/reject` endpoint
5. Run database migration on mlflow-db
6. Update console backend deployment with `AUDIT_SERVICE_URL` env var

**Files to Modify**:
- `console/backend/src/config.ts`
- `console/backend/src/server.ts`
- `infrastructure/gitops/apps/workloads/console/deployments.yaml`

**Testing**:
```bash
# Trigger approval flow via console backend
curl -X POST http://showcase-console-backend:8080/api/agent/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Register model from run run-001-a as test-model"}'

# Check pending approvals
curl http://showcase-console-backend:8080/api/approval/pending

# Approve
curl -X POST http://showcase-console-backend:8080/api/approval/1/approve

# Verify audit record
psql -h mlflow-db -U mlflow -d mlflow -c "SELECT * FROM hil_audit WHERE id = 1;"
```

**Success Criteria**:
- ✅ Console backend can query pending approvals from audit service
- ✅ Approve endpoint triggers orchestrator resume
- ✅ Reject endpoint records reason and blocks execution
- ✅ Audit records written to Postgres
- ✅ Database migration successful

---

### Day 4: Console Frontend HIL Drawer Component

**Tasks**:
1. Create `HILDrawer.tsx` component with 3-pane layout
2. Integrate HIL drawer into `AgentAssistant.tsx`
3. Add polling for pending approvals
4. Add approval/rejection API calls to `api.ts`
5. Style drawer with PatternFly components
6. Add rejection reason modal

**Files to Create/Modify**:
- `console/frontend/src/HILDrawer.tsx` (new)
- `console/frontend/src/AgentAssistant.tsx`
- `console/frontend/src/api.ts`

**Testing**:
```
1. Open Console in browser
2. Click floating chat button
3. Type: "Register model from run run-001-a as test-model-v1"
4. Verify HIL drawer opens with 3 panes:
   - Proposed Action (shows tool name + arguments)
   - Review (shows impact description)
   - Recent Approvals (shows audit history)
5. Click "Approve" → Verify tool executes, response returned
6. Try another state-modifying query, click "Reject" → Enter reason
7. Verify rejection recorded, tool does NOT execute
8. Try read-only query: "What experiments are available?"
9. Verify NO drawer opens, immediate response
```

**Success Criteria**:
- ✅ HIL drawer opens automatically when state-modifying tool proposed
- ✅ All 3 panes populated with real data
- ✅ Approve button triggers tool execution
- ✅ Reject button requires reason, blocks execution
- ✅ Read-only queries bypass drawer
- ✅ Drawer closes after approval/rejection
- ✅ Recent audit history displays correctly

---

### Day 5: Integration Testing + Bug Fixes

**Tasks**:
1. End-to-end test: approval flow
2. End-to-end test: rejection flow
3. End-to-end test: read-only bypass
4. Verify audit trail persistence
5. Test error handling (service unavailable, timeout)
6. Fix any UI/UX issues
7. Update documentation

**Test Cases**:

#### Test 1: Approval Flow
```
Given: Agent proposes "Register model from run run-001-a as test-model-v1"
When: HIL drawer opens
And: Operator clicks "Approve"
Then: Tool executes successfully
And: Audit record created with status="approved"
And: Response returned: "Model 'test-model-v1' registered from run run-001-a"
```

#### Test 2: Rejection Flow
```
Given: Agent proposes state-modifying action
When: Operator clicks "Reject" with reason "Not ready for production"
Then: Tool does NOT execute
And: Audit record created with status="rejected"
And: User sees "Action rejected by operator. Reason: Not ready for production"
```

#### Test 3: Read-Only Bypass
```
Given: Agent calls read-only tool "list_experiments"
When: Tool executes
Then: NO HIL drawer appears
And: Response immediate (<2 seconds)
And: No audit record created
```

#### Test 4: Concurrent Approvals
```
Given: Two browser tabs open
When: Both tabs trigger state-modifying queries
Then: Both see HIL drawers
And: Each can approve independently
And: Audit records distinct
```

**Success Criteria**:
- ✅ All test cases pass
- ✅ No console errors
- ✅ Audit trail queryable from Postgres
- ✅ Performance acceptable (<5s approval round-trip)
- ✅ Documentation updated

---

## Testing Strategy

### Unit Tests

**MCP Server**:
```python
def test_register_model_endpoint():
    response = client.post("/tools/register_model", params={
        "run_id": "run-001-a",
        "model_name": "test-model"
    })
    assert response.status_code == 200
    assert response.json()["status"] == "registered"

def test_tool_discovery_includes_state_modifying_flag():
    response = client.get("/mcp/tools")
    tools = response.json()["tools"]
    register_tool = next(t for t in tools if t["name"] == "register_model")
    assert register_tool["state_modifying"] == True
```

**Audit Service**:
```python
def test_create_pending_approval():
    response = client.post("/audit/pending", json={
        "tool_name": "register_model",
        "tool_arguments": {"run_id": "run-001-a"},
        "session_id": "test-session"
    })
    assert response.status_code == 200
    assert "id" in response.json()

def test_approve_request():
    # Create pending request
    create_resp = client.post("/audit/pending", json={...})
    request_id = create_resp.json()["id"]
    
    # Approve it
    approve_resp = client.post(f"/audit/approve/{request_id}", json={
        "approver_identity": "test-operator"
    })
    assert approve_resp.status_code == 200
    
    # Verify status
    audit_resp = client.get(f"/audit/history")
    record = next(r for r in audit_resp.json()["history"] if r["id"] == request_id)
    assert record["approval_status"] == "approved"
```

**Orchestrator**:
```python
def test_state_modifying_tool_triggers_hil_gate():
    state = {
        "messages": [
            HumanMessage(content="Register model from run run-001-a")
        ]
    }
    
    result = workflow.invoke(state)
    
    # Should pause at await_approval node
    last_message = result["messages"][-1]
    assert "Waiting for operator approval" in last_message.content
    assert "pending_approval_id" in result
```

---

### Integration Tests

**End-to-End Approval Flow**:
```bash
#!/bin/bash
set -e

# 1. Trigger state-modifying query
echo "Triggering state-modifying query..."
RESPONSE=$(curl -s -X POST http://console-backend:8080/api/agent/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Register model from run run-001-a as test-model"}')

echo "Response: $RESPONSE"
echo "$RESPONSE" | jq -e '.response | contains("Waiting for operator approval")'

# 2. Check pending approvals
echo "Checking pending approvals..."
PENDING=$(curl -s http://console-backend:8080/api/approval/pending)
echo "$PENDING" | jq -e '.pending | length > 0'

APPROVAL_ID=$(echo "$PENDING" | jq -r '.pending[0].id')
echo "Approval ID: $APPROVAL_ID"

# 3. Approve request
echo "Approving request..."
APPROVE_RESULT=$(curl -s -X POST "http://console-backend:8080/api/approval/${APPROVAL_ID}/approve")
echo "Approval result: $APPROVE_RESULT"
echo "$APPROVE_RESULT" | jq -e '.response | contains("registered")'

# 4. Verify audit record
echo "Verifying audit record..."
AUDIT=$(curl -s "http://audit-service:8090/audit/history?limit=1")
echo "$AUDIT" | jq -e '.history[0].approval_status == "approved"'

echo "✅ End-to-end approval flow test PASSED"
```

---

## Acceptance Criteria

Milestone 2 is **complete** when all of these are true:

### Functional Criteria
1. ✅ MCP server exposes `register_model` tool marked as state-modifying
2. ✅ Orchestrator detects state-modifying tools and pauses execution
3. ✅ HIL drawer opens in Console with 3 panes populated from real data
4. ✅ Operator can approve actions → tool executes → response returned
5. ✅ Operator can reject actions → tool does NOT execute → rejection message shown
6. ✅ Read-only tools bypass HIL gate (no approval required)
7. ✅ Audit trail records all approval decisions with timestamps
8. ✅ Audit trail queryable from Postgres

### Quality Criteria
9. ✅ Approval round-trip latency < 5 seconds (drawer open → approve → response)
10. ✅ No console errors or warnings
11. ✅ Rejection reason captured and stored
12. ✅ Recent audit history displays in drawer Pane 3

### Documentation Criteria
13. ✅ All code includes AI compliance headers
14. ✅ This milestone document complete with testing instructions
15. ✅ Component README files updated

---

## Known Limitations

### Simplified HIL Pattern (vs Full Llama Stack)

This Milestone 2 implementation proves the approval workflow but lacks:

| Feature | Milestone 2 | Full (Phase 3) |
|---------|-------------|----------------|
| **HIL Drawer Panes** | 3 | 6 (adds blast-radius, guardrails, TrustyAI) |
| **Guardrails** | None | PII scan, safety checks, blocked tools |
| **Blast-Radius Analysis** | None | Query fleet impact, rollback path |
| **TrustyAI Evaluation** | None | Proposed vs incumbent model scoring |
| **Identity Binding** | Hardcoded "demo-operator" | CAC/PIV cert DN or OAuth sub |
| **Agent Framework** | LangGraph only | Llama Stack wrapping LangGraph |
| **Audit Immutability** | Postgres table | WORM storage, signed records |

These features layer on top in later milestones without rewriting the core flow.

---

## Troubleshooting

### Issue: HIL Drawer Never Opens

**Symptoms**: Agent executes state-modifying tool immediately, no approval requested.

**Diagnosis**:
```bash
# Check if tool marked as state-modifying in MCP discovery
curl http://mcp-mlflow-server:8080/mcp/tools | jq '.tools[] | select(.name == "register_model")'

# Expected: "state_modifying": true
```

**Fix**: Verify `state_modifying: true` in tool schema, rebuild MCP server.

---

### Issue: Approval Doesn't Resume Execution

**Symptoms**: Click "Approve" but no response, drawer stays open.

**Diagnosis**:
```bash
# Check orchestrator logs
oc logs -n agentic-ops -l app=agentic-orchestrator --tail=50

# Check audit service logs
oc logs -n agentic-ops -l app=audit-service --tail=50
```

**Common Causes**:
- Orchestrator `/approval/{id}/resume` endpoint not wired correctly
- State persistence not working (approval ID mismatch)
- Audit service not updating status to "approved"

**Fix**: Verify audit service API calls succeed, check orchestrator state management.

---

### Issue: Database Connection Failed

**Symptoms**: Audit service logs show "Connection refused" or "Authentication failed".

**Diagnosis**:
```bash
# Check secret exists
oc get secret mlflow-db-app -n mlflow -o yaml

# Check audit service can reach database
oc exec -n agentic-ops deployment/audit-service -- \
  psql "postgresql://mlflow:PASSWORD@mlflow-db.mlflow.svc:5432/mlflow" -c "SELECT 1"
```

**Fix**: Mount `mlflow-db-app` secret correctly, verify connection string format.

---

### Issue: Read-Only Tools Trigger HIL Gate

**Symptoms**: Every query opens HIL drawer, even `list_experiments`.

**Diagnosis**:
```bash
# Check tool schemas
curl http://mcp-mlflow-server:8080/mcp/tools | jq '.tools[] | .state_modifying'

# Expected: Only register_model should be true
```

**Fix**: Ensure read-only tools have `state_modifying: false` or field omitted.

---

## Performance Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| HIL drawer open latency | < 2 seconds | Time from "waiting" message to drawer visible |
| Approval round-trip | < 5 seconds | Drawer open → approve → response |
| Audit write latency | < 500 ms | POST /audit/pending → record written |
| Read-only tool bypass | < 2 seconds | No approval overhead for read-only queries |
| Database query | < 100 ms | SELECT from hil_audit |

---

## Next Steps After Milestone 2

### Milestone 3: Agent-Opens-a-PR Pattern (Weeks 5-6)
- GitHub API integration
- Kustomize overlay generator
- Git diff display in HIL drawer
- `mcp-fleet` server with write tools
- PR-based deployment changes

### Milestone 4: Full HIL Drawer + TrustyAI (Weeks 7-8)
- Llama Stack Agents API wrapping
- Guardrails (PII scan, safety checks)
- Blast-radius analysis
- TrustyAI model evaluation
- 6-pane drawer (expand from 3)

---

## References

- **Phase 3 Plan**: `docs/plans/phase-3-agentic-implementation.md`
- **Milestone 1 Doc**: `docs/plans/phase-3-milestones/milestone-1-day4-5-console-integration.md`
- **ADR-019**: Llama Stack HIL wrapping LangGraph
- **MCP Protocol**: Model Context Protocol specification
- **LangGraph**: State machine orchestration framework

---

**Document Status**: Planning complete, ready for implementation  
**Last Updated**: 2026-07-08  
**Owner**: Phase 3 Agentic Workstream
