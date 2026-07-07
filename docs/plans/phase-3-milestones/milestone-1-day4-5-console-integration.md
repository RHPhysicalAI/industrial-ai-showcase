# Milestone 1: Day 4-5 - Console Integration

> [!NOTE]
> This project was developed with assistance from AI tools.

**Days**: 4-5 (Wednesday-Thursday)  
**Duration**: 8-12 hours  
**Goal**: Add "Agent Assistant" panel to Showcase Console for natural language queries

---

## Overview

Integrate the agentic orchestrator into the existing Showcase Console so operators can:
1. Ask questions in natural language
2. See agent responses with tool call context
3. View conversation history
4. See agent status (thinking, calling tools, responding)

**Pattern**: Chat-style UI panel similar to GitHub Copilot Chat, but read-only for Milestone 1.

---

## Architecture

```
┌─────────────────────────────────────────┐
│ Showcase Console Frontend               │
│  ┌───────────────────────────────────┐  │
│  │ Existing Views (Stage/Fleet/etc)  │  │
│  └───────────────────────────────────┘  │
│  ┌───────────────────────────────────┐  │
│  │ NEW: Agent Assistant Panel        │  │
│  │  - Chat input                     │  │
│  │  - Message history                │  │
│  │  - Tool call indicators           │  │
│  └───────────────────────────────────┘  │
└──────────────┬──────────────────────────┘
               │ HTTP /api/agent/query
               ↓
┌─────────────────────────────────────────┐
│ Showcase Console Backend                │
│  - Proxy to agentic-orchestrator        │
│  - Session management                   │
└──────────────┬──────────────────────────┘
               │ HTTP POST /query
               ↓
┌─────────────────────────────────────────┐
│ Agentic Orchestrator Service            │
│  - LangGraph agent                      │
│  - Tool calling                         │
└─────────────────────────────────────────┘
```

---

## Day 4 (Wednesday): Backend Integration

### Task 4.1: Add Agent Proxy Route to Console Backend

**File**: `console/backend/src/server.ts`

Add a new endpoint that proxies to the agentic-orchestrator:

```typescript
// Agent assistant endpoint
fastify.post<{ Body: { query: string; sessionId?: string } }>(
  "/api/agent/query",
  async (request, reply) => {
    const { query, sessionId } = request.body;
    
    try {
      const resp = await fetch(
        `${config.agenticOrchestratorUrl}/query`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query }),
        }
      );
      
      if (!resp.ok) {
        reply.code(resp.status).send({ error: "Agent query failed" });
        return;
      }
      
      const data = await resp.json();
      return {
        query: data.query,
        response: data.response,
        timestamp: new Date().toISOString(),
      };
    } catch (err) {
      log.error({ err }, "agent query error");
      reply.code(500).send({ error: "Agent service unavailable" });
    }
  }
);

// Agent health check
fastify.get("/api/agent/health", async () => {
  try {
    const resp = await fetch(`${config.agenticOrchestratorUrl}/health`);
    if (resp.ok) {
      return { status: "ready" };
    }
    return { status: "unavailable" };
  } catch {
    return { status: "unavailable" };
  }
});
```

### Task 4.2: Add Configuration for Orchestrator URL

**File**: `console/backend/src/config.ts`

Add environment variable for orchestrator service:

```typescript
export interface Config {
  // ... existing fields
  agenticOrchestratorUrl: string;
}

export function loadConfig(): Config {
  return {
    // ... existing config
    agenticOrchestratorUrl: process.env.AGENTIC_ORCHESTRATOR_URL || 
      "http://agentic-orchestrator.agentic-ops.svc.cluster.local:8080",
  };
}
```

### Task 4.3: Update Console Backend Deployment

**File**: `infrastructure/gitops/apps/workloads/console/deployment.yaml`

Add environment variable:

```yaml
env:
  # ... existing vars
  - name: AGENTIC_ORCHESTRATOR_URL
    value: "http://agentic-orchestrator.agentic-ops.svc.cluster.local:8080"
```

### Task 4.4: Build and Deploy Backend Changes

```bash
cd console/backend
npm run build

# Trigger rebuild via Argo CD or BuildConfig
oc start-build showcase-console-backend -n fleet-ops --follow
```

**Validation**:
```bash
# Port-forward console backend
oc port-forward -n fleet-ops svc/showcase-console-backend 8090:8090

# Test agent health
curl http://localhost:8090/api/agent/health

# Test agent query (will fail if vLLM is scaled down)
curl -X POST http://localhost:8090/api/agent/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What experiments are available?"}'
```

---

## Day 5 (Thursday): Frontend UI

### Task 5.1: Create AgentAssistant Component

**File**: `console/frontend/src/AgentAssistant.tsx`

```typescript
// This project was developed with assistance from AI tools.
import { useState } from "react";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Flex,
  FlexItem,
  Form,
  FormGroup,
  Spinner,
  Stack,
  StackItem,
  TextArea,
} from "@patternfly/react-core";
import { queryAgent } from "./api.js";

interface Message {
  role: "user" | "assistant";
  content: string;
  timestamp: string;
  status?: "thinking" | "complete" | "error";
}

export function AgentAssistant() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMessage: Message = {
      role: "user",
      content: input,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);

    try {
      const response = await queryAgent(input);
      const assistantMessage: Message = {
        role: "assistant",
        content: response.response,
        timestamp: response.timestamp,
        status: "complete",
      };
      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err) {
      const errorMessage: Message = {
        role: "assistant",
        content: `Error: ${err instanceof Error ? err.message : "Agent unavailable"}`,
        timestamp: new Date().toISOString(),
        status: "error",
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card isFullHeight>
      <CardHeader>
        <CardTitle>Agent Assistant</CardTitle>
      </CardHeader>
      <CardBody>
        <Stack hasGutter style={{ height: "100%" }}>
          <StackItem isFilled style={{ overflowY: "auto", minHeight: 300, maxHeight: 500 }}>
            {messages.length === 0 ? (
              <p style={{ color: "#6a6e73", fontStyle: "italic" }}>
                Ask a question about MLflow experiments, runs, or metrics...
              </p>
            ) : (
              <Stack hasGutter>
                {messages.map((msg, idx) => (
                  <StackItem key={idx}>
                    <div
                      style={{
                        padding: 12,
                        borderRadius: 4,
                        backgroundColor: msg.role === "user" ? "#f0f0f0" : "#e7f1fa",
                      }}
                    >
                      <strong>{msg.role === "user" ? "You" : "Agent"}:</strong>{" "}
                      {msg.content}
                      {msg.status === "error" && (
                        <span style={{ color: "#c9190b", marginLeft: 8 }}>(Error)</span>
                      )}
                    </div>
                  </StackItem>
                ))}
                {loading && (
                  <StackItem>
                    <Flex alignItems={{ default: "alignItemsCenter" }}>
                      <FlexItem>
                        <Spinner size="md" />
                      </FlexItem>
                      <FlexItem>
                        <span style={{ color: "#6a6e73" }}>Agent thinking...</span>
                      </FlexItem>
                    </Flex>
                  </StackItem>
                )}
              </Stack>
            )}
          </StackItem>
          <StackItem>
            <Form onSubmit={handleSubmit}>
              <FormGroup>
                <Flex>
                  <FlexItem flex={{ default: "flex_1" }}>
                    <TextArea
                      value={input}
                      onChange={(_, value) => setInput(value)}
                      placeholder="Ask about experiments, runs, metrics..."
                      rows={2}
                      disabled={loading}
                    />
                  </FlexItem>
                  <FlexItem>
                    <Button type="submit" isDisabled={loading || !input.trim()}>
                      Ask
                    </Button>
                  </FlexItem>
                </Flex>
              </FormGroup>
            </Form>
          </StackItem>
        </Stack>
      </CardBody>
    </Card>
  );
}
```

### Task 5.2: Add API Function

**File**: `console/frontend/src/api.ts`

Add:

```typescript
export async function queryAgent(query: string): Promise<{
  query: string;
  response: string;
  timestamp: string;
}> {
  const resp = await fetch("/api/agent/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  if (!resp.ok) {
    throw new Error(`Agent query failed: ${resp.statusText}`);
  }
  return resp.json();
}

export async function getAgentHealth(): Promise<{ status: string }> {
  const resp = await fetch("/api/agent/health");
  if (!resp.ok) {
    return { status: "unavailable" };
  }
  return resp.json();
}
```

### Task 5.3: Integrate into Architecture View

**File**: `console/frontend/src/ArchitectureView.tsx`

Add the Agent Assistant panel alongside the existing architecture diagram:

```typescript
import { AgentAssistant } from "./AgentAssistant.js";

export function ArchitectureView() {
  return (
    <Stack hasGutter>
      {/* Existing architecture diagram */}
      <StackItem>
        <Card>
          <CardHeader><CardTitle>System Architecture</CardTitle></CardHeader>
          <CardBody>
            {/* ... existing diagram ... */}
          </CardBody>
        </Card>
      </StackItem>
      
      {/* NEW: Agent Assistant */}
      <StackItem>
        <AgentAssistant />
      </StackItem>
    </Stack>
  );
}
```

### Task 5.4: Build and Deploy Frontend

```bash
cd console/frontend
npm run build

# Trigger rebuild
oc start-build showcase-console-frontend -n fleet-ops --follow
```

**Validation**:
```bash
# Port-forward console frontend
oc port-forward -n fleet-ops svc/showcase-console-frontend 3000:8080

# Open browser: http://localhost:3000
# Navigate to Architecture view
# Type: "What experiments are available?"
# Should see agent response with MLflow mock data
```

---

## Acceptance Criteria

Day 4-5 is complete when:

- [ ] `/api/agent/query` endpoint exists in console backend
- [ ] Console backend can reach agentic-orchestrator service
- [ ] `AgentAssistant` component renders in Architecture view
- [ ] User can type a question and see agent response
- [ ] Agent status shows "thinking" while processing
- [ ] Error states are handled gracefully (agent unavailable)
- [ ] Conversation history persists during session (in-memory for M1)
- [ ] Example queries work:
  - "What experiments are available?"
  - "Show me runs for experiment exp_001"
  - "What are the metrics for run run_001_001?"

---

## Known Limitations (Milestone 1)

- **No session persistence**: Refresh page = conversation lost
- **No streaming**: User waits for full response (up to 5 sec)
- **No tool call visibility**: User doesn't see which tools were called
- **No retry**: Failed query requires re-typing
- **vLLM must be running**: If scaled to 0, agent returns errors

These are addressed in Milestone 2 (Week 2).

---

## Next Steps

After Day 4-5:
- **Day 6-7**: Add write operations (MCP GitHub server, PR creation)
- **Day 8-10**: HIL drawer, end-to-end testing

---

## Troubleshooting

### "Agent unavailable" error
```bash
# Check orchestrator health
oc get pods -n agentic-ops -l app=agentic-orchestrator

# Check if vLLM is running (needed for agent to work)
oc get pods -n agentic-ops -l app=vllm-agent-brain

# Check logs
oc logs -n agentic-ops -l app=agentic-orchestrator --tail=50
```

### Agent times out
```bash
# Check vLLM response time
oc port-forward -n agentic-ops svc/vllm-agent-brain 8000:8000
curl -X POST http://localhost:8000/v1/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "meta-llama/Llama-3.1-8B-Instruct", "prompt": "Hello", "max_tokens": 10}'

# If > 5 sec, may need GPU or model optimization
```

### Console backend can't reach orchestrator
```bash
# Test from console backend pod
oc exec -n fleet-ops deployment/showcase-console-backend -- \
  wget -O- http://agentic-orchestrator.agentic-ops.svc.cluster.local:8080/health
```