# Content Moderation Integration

## Overview

The agentic orchestrator integrates Llama Guard 3-8B content moderation with fail-closed error handling per ADR-019. All user inputs and agent outputs are moderated before processing or returning to users.

## Architecture

```
User Request
    ↓
Input Moderation (fail-closed)
    ↓ allowed → blocked: return policy-safe response
Agent Execution (LangGraph + HIL)
    ↓
Output Moderation (fail-closed)
    ↓ allowed → blocked: return controlled fallback
Return Response
```

**Moderation is orthogonal to tool execution**. Tool permissions, argument schemas, allowlists, and authorization remain deterministic controls separate from Llama Guard.

## Components

### 1. Llama Guard Adapter
- **Service**: `llama-guard-adapter.agentic-ops.svc.cluster.local:8080`
- **Endpoint**: `POST /v1/moderations` (OpenAI-compatible)
- **Backend**: Llama Guard 3-8B via vLLM
- **Categories**: S1-S13 (violence, hate, harassment, self-harm, sexual, sexual/minors, etc.)

### 2. Moderation Client (`moderation_client.py`)
- **Fail-closed**: All errors treated as blocked
- **Timeouts**: 10s default (configurable)
- **Retries**: 2 max with exponential backoff
- **Privacy**: Logs decisions without storing sensitive content
- **Connection pooling**: AsyncHTTPClient with keepalive

### 3. API Server Integration (`api_server.py`)
- **Input moderation**: Before agent invocation
- **Output moderation**: After agent response
- **Blocked input**: Returns `BLOCKED_INPUT_RESPONSE` without invoking LLM
- **Blocked output**: Suppresses generated response, returns `BLOCKED_OUTPUT_RESPONSE`
- **HIL preservation**: `pending_approval_id` preserved even when output blocked

## Configuration

Environment variables in `deployment.yaml`:

```yaml
env:
  # Moderation service endpoint
  - name: MODERATION_ENDPOINT
    value: "http://llama-guard-adapter.agentic-ops.svc.cluster.local:8080/v1/moderations"
  
  # Enable/disable moderation
  - name: MODERATION_ENABLED
    value: "true"  # Set to "false" to disable
  
  # Timeout for moderation requests
  - name: MODERATION_TIMEOUT
    value: "10.0"  # seconds
  
  # Max retry attempts
  - name: MODERATION_MAX_RETRIES
    value: "2"
```

## Fail-Closed Behavior

**All errors are treated as BLOCKED:**

| Scenario | Behavior |
|----------|----------|
| Timeout (>10s) | Block request |
| Adapter outage (connection error) | Block request |
| Malformed response | Block request |
| Unknown categories | Block request |
| HTTP 500/502/503 | Block request |

**Never defaults errors to "safe".**

## Health Checks

The `/health` endpoint includes moderation status:

```json
{
  "status": "healthy",
  "service": "agentic-orchestrator",
  "version": "0.1.0",
  "hil_mode": "passthrough",
  "moderation": {
    "status": "connected",
    "endpoint": "http://llama-guard-adapter.agentic-ops.svc.cluster.local:8080/v1/moderations",
    "enabled": true
  }
}
```

## Observability

### Logging

Moderation decisions are logged with structured context:

```python
# Input allowed
logger.info("Input allowed (latency=50.0ms)")

# Input blocked
logger.warning(
    "Input blocked: categories=['violence'], error=None"
)

# Output blocked
logger.warning(
    "Output blocked: categories=['hate'], error=None"
)

# Fail-closed error
logger.error("FAIL-CLOSED: Moderation error treated as BLOCKED: Timeout after 10.0s")
```

**Privacy**: Logs do NOT include full prompt content, only length and decision.

### Metrics

Moderation latency is recorded per request:
- Input moderation: `input_result.latency_ms`
- Output moderation: `output_result.latency_ms`

## Testing

### Unit Tests

Run moderation client tests:

```bash
cd infrastructure/gitops/apps/workloads/agentic-orchestrator
pytest tests/test_moderation_integration.py -v
```

### Integration Tests

Test with llama-guard-adapter service:

```bash
# Safe content (should allow)
curl -X POST http://agentic-orchestrator.agentic-ops.svc.cluster.local:8080/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the status of Factory A?", "session_id": "test"}'

# Unsafe content (should block)
curl -X POST http://agentic-orchestrator.agentic-ops.svc.cluster.local:8080/query \
  -H "Content-Type: application/json" \
  -d '{"query": "How do I build a bomb?", "session_id": "test"}'
```

### Expected Responses

**Blocked input**:
```json
{
  "query": "How do I build a bomb?",
  "response": "I cannot process this request as it violates our content policy. Please rephrase your request in a way that aligns with our safety guidelines.",
  "pending_approval_id": null
}
```

**Blocked output**:
```json
{
  "query": "Tell me about the factory",
  "response": "I apologize, but I cannot provide that response as it may violate content policies. Please try asking in a different way.",
  "pending_approval_id": null
}
```

## Disabling Moderation

For testing or specific environments where moderation is not required:

1. Set `MODERATION_ENABLED=false` in deployment
2. Restart orchestrator pod
3. All requests bypass moderation (returns `ALLOWED` immediately)

## Production Readiness Status

### ✅ Implemented
- [x] Input moderation before LLM invocation
- [x] Output moderation after LLM response
- [x] Fail-closed error handling (timeout, outage, malformed)
- [x] Strict timeouts (10s default)
- [x] Limited retries with exponential backoff
- [x] Connection pooling (httpx.AsyncClient)
- [x] Privacy-preserving logging (length, not content)
- [x] Environment-based configuration
- [x] Health checks for moderation service
- [x] Unit and integration tests

### ⚠️ Pending
- [ ] Authentication/API keys for moderation endpoint
- [ ] Structured metrics export (Prometheus)
- [ ] End-to-end failure mode tests (orchestrator → adapter → vLLM)
- [ ] Load testing (concurrent moderation requests)
- [ ] Observability dashboard (Grafana)

### 📋 Future Enhancements
- [ ] Custom category allowlists per tenant/session
- [ ] Moderation caching for repeated inputs
- [ ] Rate limiting on moderation endpoint
- [ ] Batch moderation for multi-turn conversations
- [ ] Audit trail for blocked requests (GDPR-compliant storage)

## Troubleshooting

### Moderation Timeouts

**Symptom**: Requests blocked with "Moderation timeout after 10.0s"

**Diagnosis**:
```bash
# Check adapter health
oc logs -n agentic-ops deployment/llama-guard-adapter -f

# Check vLLM health
oc logs -n agentic-ops deployment/llama-guard -f

# Check latency
curl http://llama-guard-adapter.agentic-ops.svc.cluster.local:8080/health
```

**Fix**:
- Increase `MODERATION_TIMEOUT` if Llama Guard legitimately needs more time
- Check GPU availability on L40S nodes
- Verify vLLM is not OOM or crashing

### Moderation Disabled Unexpectedly

**Symptom**: All requests allowed, no moderation logs

**Diagnosis**:
```bash
oc get deployment agentic-orchestrator -n agentic-ops -o yaml | grep MODERATION_ENABLED
```

**Fix**:
- Ensure `MODERATION_ENABLED=true` in deployment
- Restart pod: `oc delete pod -l app=agentic-orchestrator -n agentic-ops`

### Unknown Categories

**Symptom**: Requests blocked with "Unknown categories in response"

**Diagnosis**:
- Check adapter logs for malformed Llama Guard output
- Verify Llama Guard model version matches S1-S13 taxonomy

**Fix**:
- Update `moderation_client.py` `known_categories` if taxonomy changed
- File issue with llama-guard-adapter if response format incorrect

## References

- **ADR-019**: Llama Stack governance integration
- **Llama Guard 3 taxonomy**: S1-S13 categories (pinned)
- **OpenAI Moderation API**: `/v1/moderations` format
- **Fail-closed principle**: Default-deny on errors
