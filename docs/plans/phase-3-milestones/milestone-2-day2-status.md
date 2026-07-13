# Milestone 2 Day 2 - Status Report

**Date:** 2026-07-09  
**Status:** ✅ COMPLETE - HIL Gate Working  
**Progress:** 100% Complete

---

## ✅ Completed

### 1. Orchestrator Extended with HIL Gate

**Files Modified:**
- `infrastructure/gitops/apps/workloads/agentic-orchestrator/src/orchestrator.py`
- `infrastructure/gitops/apps/workloads/agentic-orchestrator/src/api_server.py`
- `infrastructure/gitops/apps/workloads/agentic-orchestrator/Dockerfile`

**Key Changes:**

#### Added State-Modifying Tool
```python
@tool
def register_model(run_id: str, model_name: str) -> str:
    """Register a model from a run (state-modifying action - requires approval)"""
    return _register_model_impl(run_id, model_name)

STATE_MODIFYING_TOOLS = {"register_model"}
```

#### Custom Tool Node for HIL Interception
```python
def custom_tool_node(state: AgentState) -> dict:
    """
    Intercepts state-modifying tools BEFORE execution.
    Creates approval request instead of executing tool.
    """
    for tool_call in last_message.tool_calls:
        if tool_name in STATE_MODIFYING_TOOLS:
            # Create approval request
            response = audit_client.post(
                f"{AUDIT_SERVICE_URL}/audit/pending",
                json={
                    "session_id": session_id,
                    "user_identity": "demo-operator",
                    "tool_name": tool_name,
                    "tool_arguments": tool_args
                }
            )
            # Return APPROVAL_REQUIRED marker
            return {"messages": [ToolMessage(
                content=f"APPROVAL_REQUIRED: Request #{approval_id}",
                tool_call_id=tool_call_id,
                name=tool_name
            )]}
```

#### Updated LangGraph Workflow
```python
# Separate read-only and state-modifying tools
read_only_tools = [list_experiments, get_experiment, list_runs, get_run, get_metrics]
state_modifying_tools_list = [register_model]
all_tools = read_only_tools + state_modifying_tools_list

# LLM knows about ALL tools
llm_with_tools = llm.bind_tools(all_tools)

# But ToolNode only executes read-only tools
workflow.add_node("tools", custom_tool_node)
```

#### HIL Gate Conditional Routing
```python
def check_hil_gate(state: AgentState) -> str:
    """Check if approval required after tool execution"""
    if last_message.content.startswith("APPROVAL_REQUIRED:"):
        return "pending_approval"
    return "continue"

workflow.add_conditional_edges(
    "tools",
    check_hil_gate,
    {
        "continue": "agent",
        "pending_approval": "await_approval"
    }
)
```

#### Await Approval Node
```python
def await_approval(state: AgentState) -> dict:
    """Returns message indicating approval needed"""
    approval_id = state.get("pending_approval_id")
    waiting_message = AIMessage(
        content=f"⏸️  This action requires operator approval (Request #{approval_id}). "
                f"Please review and approve/reject in the console."
    )
    return {"messages": [waiting_message]}
```

---

### 2. API Server Updated

**File:** `infrastructure/gitops/apps/workloads/agentic-orchestrator/src/api_server.py`

**Changes:**
- Switched from `simple_orchestrator` to full `orchestrator` module
- Added `session_id` parameter to QueryRequest
- Passes session_id to `run_agent()` for approval tracking

```python
from orchestrator import run_agent, mcp_client  # Was: from simple_orchestrator

class QueryRequest(BaseModel):
    query: str
    session_id: str | None = None

async def query(request: QueryRequest):
    response = run_agent(request.query, session_id=request.session_id)
    return QueryResponse(query=request.query, response=response)
```

---

### 3. MCP Client Enhanced

**Added Features:**
- Tool schema caching (`_tool_schemas`)
- `get_tool_schema()` method to check `state_modifying` field
- POST for state-modifying tools, GET for read-only

```python
class MCPClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.client = httpx.Client(timeout=30.0)
        self._tool_schemas = {}  # Cache tool schemas

    def get_tool_schema(self, tool_name: str) -> dict:
        """Get cached tool schema (includes state_modifying field)"""
        if not self._tool_schemas:
            self.discover_tools()
        return self._tool_schemas.get(tool_name, {})

    def invoke_tool(self, tool_name: str, arguments: dict) -> dict:
        """Use POST for state-modifying, GET for read-only"""
        tool_schema = self.get_tool_schema(tool_name)
        if tool_schema.get("state_modifying", False):
            response = self.client.post(...)
        else:
            response = self.client.get(...)
```

---

### 4. AgentState Extended

**Added Fields:**
```python
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], "The messages in the conversation"]
    session_id: str  # Session ID for tracking approval requests
    pending_approval_id: int | None  # ID of pending approval request
```

---

## 🧪 Testing Results

### Test 1: Read-Only Tool (Should NOT Trigger Approval)
```bash
Query: "List all experiments"
Result: ✅ Executed immediately, no approval request
```

### Test 2: State-Modifying Tool (SHOULD Trigger Approval)
```bash
Query: "Register model from run FINAL-RUN as FINAL-SUCCESS-MODEL"
Session: "final-test-session"

Response: "⏸️  This action requires operator approval (Request #4). 
           Please review and approve/reject in the console."

Audit Service Check:
  ✅ Pending approvals: 1
  ✅ ID=4, Session=final-test-session
  ✅ Tool=register_model, Status=pending
  ✅ Arguments: {'run_id': 'FINAL-RUN', 'model_name': 'FINAL-SUCCESS-MODEL'}

Orchestrator Logs:
  ✅ "HIL GATE: Created approval request #4 for register_model"
```

---

## 🔧 Build & Deployment

### Dockerfile Path Fixed
```dockerfile
# Changed from:
COPY requirements.txt .
COPY src/ ./src/

# To (for Binary source builds):
COPY infrastructure/gitops/apps/workloads/agentic-orchestrator/requirements.txt .
COPY infrastructure/gitops/apps/workloads/agentic-orchestrator/src/ ./src/
```

### BuildConfig Updated
```bash
oc patch buildconfig agentic-orchestrator -n agentic-ops --type=json -p='[
  {
    "op": "replace",
    "path": "/spec/strategy/dockerStrategy/dockerfilePath",
    "value": "infrastructure/gitops/apps/workloads/agentic-orchestrator/Dockerfile"
  }
]'
```

### Build History
- Builds 8-9: Failed (Dockerfile path issue)
- Builds 10-14: Successful
- Final working build: **agentic-orchestrator-14**

---

## 🐛 Issues Encountered & Resolved

### Issue 1: HIL Gate Not Triggering
**Root Cause:** `api_server.py` was importing from `simple_orchestrator` (Milestone 1 code) instead of the new `orchestrator` module.

**Solution:** Updated import statement:
```python
from orchestrator import run_agent, mcp_client
```

### Issue 2: Tool Executed Before Interception
**Root Cause:** LangGraph's `ToolNode` was executing ALL tools, including state-modifying ones.

**Solution:** Created separate tool lists:
- `read_only_tools` → passed to ToolNode for execution
- `state_modifying_tools_list` → intercepted in custom_tool_node
- `all_tools` → bound to LLM so it knows about both

### Issue 3: Dockerfile Path for Binary Builds
**Root Cause:** Binary source builds upload entire repo root, so COPY paths must be relative to repo root, not Dockerfile location.

**Solution:** Used full paths in Dockerfile COPY statements.

---

## 📊 Day 2 Success Criteria

| Criteria | Status |
|----------|--------|
| Orchestrator has HIL gate logic | ✅ Complete |
| State-modifying tools intercepted | ✅ Complete |
| Approval request created in audit service | ✅ Complete |
| Read-only tools bypass HIL gate | ✅ Complete |
| Agent returns "waiting for approval" message | ✅ Complete |
| Session ID tracked for approval requests | ✅ Complete |
| End-to-end test passing | ✅ Complete |

**Overall:** 100% complete

---

## 🎯 Key Deliverables

1. ✅ **HIL Gate Implementation** - Intercepts state-modifying tools before execution
2. ✅ **Approval Request Creation** - Posts to audit service with session tracking
3. ✅ **Conditional Routing** - Routes to await_approval node for state-modifying tools
4. ✅ **User Feedback** - Returns clear "⏸️ approval required" message
5. ✅ **Read-Only Bypass** - Read-only tools execute immediately without approval

---

## 🚀 What Works Now

### Flow for State-Modifying Tools:
```
User: "Register model from run X as Y"
  ↓
Orchestrator: Agent decides to call register_model
  ↓
custom_tool_node: Detects state-modifying tool
  ↓
Audit Service: Creates pending approval (ID=4)
  ↓
check_hil_gate: Routes to await_approval
  ↓
await_approval: Returns "⏸️ approval required" message
  ↓
User: Sees approval request in console (Day 3 work)
```

### Flow for Read-Only Tools:
```
User: "List all experiments"
  ↓
Orchestrator: Agent decides to call list_experiments
  ↓
custom_tool_node: Detects read-only tool
  ↓
ToolNode: Executes tool immediately
  ↓
Agent: Returns results
```

---

## 📝 Next Steps (Day 3)

**Console Backend Approval Endpoints:**
1. Add `/api/approval/pending` endpoint
2. Add `/api/approval/:id/approve` endpoint
3. Add `/api/approval/:id/reject` endpoint
4. Wire to audit service

**Approval Resume Logic:**
1. Add `/approval/{id}/resume` endpoint to orchestrator
2. Load pending state from approval record
3. Resume graph execution after approval
4. Return final result to user

**Estimated Time:** 1 day  
**Blockers:** None

---

## 🔗 Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     User Query                               │
│              "Register model X as Y"                         │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                  API Server                                  │
│         POST /query (session_id: "abc")                      │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│               Orchestrator (LangGraph)                       │
│                                                              │
│  ┌─────────┐      ┌──────────────┐      ┌────────────┐     │
│  │  Agent  │─────▶│ custom_tool_ │─────▶│   await_   │     │
│  │         │      │    node      │      │  approval  │     │
│  └─────────┘      └──────┬───────┘      └────────────┘     │
│                           │                                  │
│                           │ if register_model                │
│                           ▼                                  │
│                  ┌─────────────────┐                         │
│                  │  Create approval│                         │
│                  │  request        │                         │
│                  └────────┬────────┘                         │
└───────────────────────────┼──────────────────────────────────┘
                            │
                            ▼
                   ┌─────────────────┐
                   │  Audit Service  │
                   │  POST /audit/   │
                   │     pending     │
                   └────────┬────────┘
                            │
                            ▼
                   ┌─────────────────┐
                   │ PostgreSQL DB   │
                   │  hil_audit      │
                   │  (ID=4, status= │
                   │   "pending")    │
                   └─────────────────┘
```

---

**Last Updated:** 2026-07-09 16:00 UTC  
**Completed By:** Phase 3 Agentic Workstream  
**Build:** agentic-orchestrator-14