# MCP MLflow Server (Mock) - Helm Chart

> [!NOTE]
> This project was developed with assistance from AI tools.

**Purpose**: Mock MCP server exposing MLflow-like read-only tools for Phase 3 Milestone 1.

**Status**: Milestone 1 - Read-Only Agent

---

## Overview

This is a **mock implementation** of an MCP server that exposes MLflow-like tools. It returns fake data for testing the agent pattern in Milestone 1.

**Real MLflow integration** happens in Milestone 2+.

---

## Tools Exposed

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_experiments` | List all MLflow experiments | None |
| `get_experiment` | Get details of a specific experiment | `experiment_id` |
| `list_runs` | List runs for an experiment | `experiment_id` |
| `get_run` | Get details of a specific run | `run_id` |
| `get_metrics` | Get metrics for a run | `run_id` |

---

## Quick Start

### 1. Build the Image

The chart includes a BuildConfig that builds from this repo:

```bash
# Install the chart (includes BuildConfig)
cd infrastructure/gitops/apps/workloads/mcp-mlflow-server
helm install mcp-mlflow-server . --namespace agentic-ops

# Trigger a build
oc start-build mcp-mlflow-server -n agentic-ops --follow
```

### 2. Verify Deployment

```bash
# Check pod status
oc get pod -n agentic-ops -l app.kubernetes.io/name=mcp-mlflow-server

# Check logs
oc logs -f -n agentic-ops -l app.kubernetes.io/name=mcp-mlflow-server

# Port-forward and test
oc port-forward -n agentic-ops svc/mcp-mlflow-server 8080:8080
curl http://localhost:8080/health
```

### 3. Test the Tools

```bash
# List experiments
curl http://localhost:8080/tools/list_experiments | jq '.'

# Get experiment details
curl "http://localhost:8080/tools/get_experiment?experiment_id=exp-001" | jq '.'

# List runs
curl "http://localhost:8080/tools/list_runs?experiment_id=exp-001" | jq '.'

# Get run details
curl "http://localhost:8080/tools/get_run?run_id=run-001-a" | jq '.'

# Get metrics
curl "http://localhost:8080/tools/get_metrics?run_id=run-001-a" | jq '.'

# MCP discovery
curl http://localhost:8080/mcp/tools | jq '.'
```

---

## Mock Data

The server returns fake data for 3 experiments:

1. **robot-navigation-training** (exp-001)
   - 2 runs (1 finished, 1 running)
   - Metrics: loss, accuracy, val_loss, val_accuracy

2. **object-detection-vla** (exp-002)
   - 1 run (finished)
   - Metrics: mAP, precision, recall

3. **manipulation-policy** (exp-003)
   - No runs yet

---

## Architecture

```
┌────────────────────────────────────┐
│ mcp-mlflow-server Service          │
│  ClusterIP: mcp-mlflow-server:8080 │
└────────────┬───────────────────────┘
             │
             ↓
┌────────────────────────────────────┐
│ mcp-mlflow-server Deployment       │
│  - FastAPI server                  │
│  - Mock MLflow tools               │
│  - Python 3.12                     │
└────────────────────────────────────┘
```

**Consumers**:
- `agentic-orchestrator` (LangGraph agent) - calls these tools via MCP protocol

---

## API Endpoints

### Health Check

```bash
GET /health
```

Returns:
```json
{
  "status": "healthy",
  "service": "mcp-mlflow-server",
  "version": "0.1.0"
}
```

### MCP Discovery

```bash
GET /mcp/tools
```

Returns list of available tools with schemas.

### Tool Endpoints

All tools are under `/tools/*`:

- `GET /tools/list_experiments`
- `GET /tools/get_experiment?experiment_id={id}`
- `GET /tools/list_runs?experiment_id={id}`
- `GET /tools/get_run?run_id={id}`
- `GET /tools/get_metrics?run_id={id}`

---

## Configuration

### Key Values

| Parameter | Description | Default |
|-----------|-------------|---------|
| `image.repository` | Image repository | `image-registry.openshift-image-registry.svc:5000/agentic-ops/mcp-mlflow-server` |
| `image.tag` | Image tag | `latest` |
| `replicas` | Number of replicas | `1` |
| `service.port` | Service port | `8080` |
| `resources.requests.memory` | Memory request | `256Mi` |
| `resources.limits.memory` | Memory limit | `512Mi` |

---

## Development

### Local Testing

```bash
# Run locally
cd infrastructure/gitops/apps/workloads/mcp-mlflow-server
pip install -r requirements.txt
python -m src.mcp_server

# Test
curl http://localhost:8080/health
```

### Building Manually

```bash
# Build with Docker/Podman
podman build -t mcp-mlflow-server:latest .

# Push to OpenShift registry
podman tag mcp-mlflow-server:latest image-registry.openshift-image-registry.svc:5000/agentic-ops/mcp-mlflow-server:latest
podman push image-registry.openshift-image-registry.svc:5000/agentic-ops/mcp-mlflow-server:latest
```

---

## Troubleshooting

### Build Failing

```bash
# Check build logs
oc logs -f bc/mcp-mlflow-server -n agentic-ops

# Rebuild
oc start-build mcp-mlflow-server -n agentic-ops --follow
```

### Pod Not Starting

```bash
# Check pod events
oc describe pod -n agentic-ops -l app.kubernetes.io/name=mcp-mlflow-server

# Check logs
oc logs -n agentic-ops -l app.kubernetes.io/name=mcp-mlflow-server
```

### Tools Not Working

```bash
# Test health endpoint first
oc port-forward -n agentic-ops svc/mcp-mlflow-server 8080:8080
curl http://localhost:8080/health

# Check tool discovery
curl http://localhost:8080/mcp/tools | jq '.'
```

---

## Upgrade Path

### Milestone 1 → Milestone 2

**Current**: Mock server with fake data  
**Future**: Real MLflow integration

**Migration**:
1. Keep this mock server for Milestone 1 testing
2. Create new `mcp-mlflow-real` chart in Milestone 2
3. Connect to actual MLflow tracking server
4. Point agentic-orchestrator to new service
5. Delete this mock deployment

---

## Related Documentation

- **[Milestone 1 Plan](../../../../docs/plans/phase-3-milestones/milestone-1-read-only-agent.md)** - Overall M1 roadmap
- **[Component Catalog](../../../../docs/03-component-catalog.md)** - Where this fits in the architecture
- **[MCP Protocol](https://github.com/anthropics/mcp)** - Model Context Protocol spec

---

**Status**: ✅ Ready for Milestone 1 deployment