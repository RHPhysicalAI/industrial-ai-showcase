# Agentic Orchestrator

LangGraph-based read-only agent that orchestrates vLLM (language model) with MCP MLflow tools.

## Architecture

```
┌─────────────────────────────────────┐
│ Agentic Orchestrator (LangGraph)    │
│  - Agent decision loop              │
│  - Tool invocation                  │
│  - Response generation              │
└────────────┬────────────────────────┘
             │
      ┌──────┴──────┐
      ↓             ↓
┌──────────┐   ┌─────────────────┐
│ vLLM     │   │ mcp-mlflow      │
│ (Brain)  │   │ (Tools)         │
│ Llama    │   │ 5 MLflow tools  │
│ 3.1-8B   │   │  - experiments  │
│          │   │  - runs         │
│          │   │  - metrics      │
└──────────┘   └─────────────────┘
```

## Components

### 1. Orchestrator Service (`orchestrator.py`)
- **LangGraph workflow** with agent → tools → agent loop
- **ChatOpenAI** configured to connect to vLLM endpoint
- **MCP Client** for tool discovery and invocation
- **5 LangChain tools** wrapping MCP endpoints:
  - `list_experiments()` - List all experiments
  - `get_experiment(id)` - Get experiment details
  - `list_runs(experiment_id)` - List runs for experiment
  - `get_run(run_id)` - Get run details
  - `get_metrics(run_id)` - Get metrics for run

### 2. API Server (`api_server.py`)
- **FastAPI** REST API
- **Endpoints**:
  - `GET /health` - Health check
  - `POST /query` - Process agent query
  - `GET /tools` - List available MCP tools

## Configuration

Environment variables (set in deployment.yaml):

```yaml
VLLM_BASE_URL: "http://vllm-agent-brain.agentic-ops.svc.cluster.local:8000/v1"
MCP_BASE_URL: "http://mcp-mlflow-server.agentic-ops.svc.cluster.local:8080"
```

## Deployment

Built using OpenShift BuildConfig (binary source):

```bash
cd infrastructure/gitops/apps/workloads/agentic-orchestrator
oc apply -k .
oc start-build agentic-orchestrator --from-dir=. --follow
```

## Testing

### Health Check
```bash
curl http://agentic-orchestrator.agentic-ops.svc.cluster.local:8080/health
```

### List Tools
```bash
curl http://agentic-orchestrator.agentic-ops.svc.cluster.local:8080/tools
```

### Query Agent
```bash
curl -X POST http://agentic-orchestrator.agentic-ops.svc.cluster.local:8080/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What MLflow experiments are available?"}'
```

## Resource Limits

- **CPU**: 200m request, 1000m limit
- **Memory**: 512Mi request, 1Gi limit

## Dependencies

- `langchain==0.3.14` - LangChain framework
- `langchain-openai==0.2.14` - OpenAI/vLLM integration
- `langgraph==0.2.59` - LangGraph orchestration
- `fastapi==0.115.5` - Web framework
- `httpx==0.28.1` - HTTP client for MCP calls

## Milestone 1: Read-Only Agent

This component completes **Day 3** of Milestone 1:
- ✅ Day 1: vLLM deployment
- ✅ Day 2: MCP MLflow server  
- ✅ Day 3: Agentic orchestrator ← **You are here**

Next: Days 4-10 will expand this to support write operations, multi-agent coordination, and workflow integration.

## Phase 3 Context

Part of the **Agentic Orchestrator** system for Phase 3:
- **Phase**: 3 (Agentic Operations)
- **Milestone**: 1 (Read-only agent)
- **Component**: Agent orchestrator
- **Labels**: `phase: "3"`, `milestone: "1"`