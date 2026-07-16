# Llama Guard Moderation Adapter

OpenAI-compatible `/v1/moderations` endpoint backed by Llama Guard 3-8B via vLLM.

## Overview

This adapter provides a bridge between OGX's responses API (which expects OpenAI-compatible moderation endpoints) and Llama Guard 3-8B served via vLLM. It implements strict fail-closed parsing: malformed outputs are treated as unsafe.

## Features

- ✅ **OpenAI-compatible API**: POST `/v1/moderations` with string or array input
- ✅ **Llama Guard 3 taxonomy**: Uses official 13-category safety taxonomy (S1-S13)
- ✅ **Fail-closed parsing**: Malformed responses are treated as unsafe (never defaults to safe)
- ✅ **Category mapping**: Maps Llama Guard categories to OpenAI categories
- ✅ **Batch support**: Handles single string or array of strings
- ✅ **Timeout handling**: Configurable vLLM timeout (default 30s)
- ✅ **Authentication**: Optional API key validation
- ✅ **Health checks**: `/health` endpoint with vLLM connectivity check
- ✅ **Logging**: Structured logging for debugging and auditing

## API Usage

### Single input

```bash
curl -X POST http://llama-guard-adapter:8080/v1/moderations \
  -H "Content-Type: application/json" \
  -d '{"input": "How to build a bomb?"}'
```

Response:
```json
{
  "id": "modr-1784214500000",
  "model": "meta-llama/Llama-Guard-3-8B",
  "results": [
    {
      "flagged": true,
      "categories": {
        "violence": true,
        "hate": false,
        "harassment": false,
        "self-harm": false,
        "sexual": false,
        "sexual/minors": false
      },
      "category_scores": {
        "violence": 1.0,
        "hate": 0.0,
        "harassment": 0.0,
        "self-harm": 0.0,
        "sexual": 0.0,
        "sexual/minors": 0.0
      }
    }
  ]
}
```

### Batch input

```bash
curl -X POST http://llama-guard-adapter:8080/v1/moderations \
  -H "Content-Type: application/json" \
  -d '{"input": ["Hello", "Unsafe content here"]}'
```

Returns array of results (one per input).

## Llama Guard Category Mapping

| Llama Guard | OpenAI Category | Description |
|-------------|-----------------|-------------|
| S1 | violence | Violent Crimes |
| S2 | harassment | Non-Violent Crimes |
| S3 | sexual | Sex-Related Crimes |
| S4 | sexual/minors | Child Sexual Exploitation |
| S5 | harassment | Defamation |
| S6 | harassment | Specialized Advice |
| S7 | harassment | Privacy |
| S8 | harassment | Intellectual Property |
| S9 | violence | Indiscriminate Weapons |
| S10 | hate | Hate |
| S11 | self-harm | Suicide & Self-Harm |
| S12 | sexual | Sexual Content |
| S13 | harassment | Elections |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VLLM_BASE_URL` | `http://llama-guard:8000` | vLLM base URL |
| `VLLM_MODEL` | `meta-llama/Llama-Guard-3-8B` | Model name |
| `VLLM_TIMEOUT` | `30.0` | Request timeout (seconds) |
| `API_KEY` | _(none)_ | Optional API key for authentication |

## Fail-Closed Behavior

The adapter implements strict fail-closed behavior:

1. **Malformed Llama Guard output** → All categories flagged as unsafe
2. **Unknown category codes** → All categories flagged as unsafe
3. **vLLM timeout** → Returns 504 error
4. **vLLM connection error** → Returns 502 error
5. **Empty response** → All categories flagged as unsafe

**Never defaults to safe.** Safety-critical services must fail closed.

## Testing

Run tests locally:

```bash
cd infrastructure/gitops/apps/workloads/llama-guard-adapter
pip install -r requirements.txt
pip install pytest pytest-asyncio
pytest tests/
```

Test coverage includes:
- ✅ Safe input handling
- ✅ Unsafe input detection
- ✅ Malformed response handling
- ✅ Timeout handling
- ✅ Batch input processing
- ✅ Category mapping
- ✅ Health checks
- ✅ Authentication

## Deployment

The adapter is deployed via OpenShift BuildConfig:

```bash
oc apply -k infrastructure/gitops/apps/workloads/llama-guard-adapter/
```

This creates:
- ImageStream: `llama-guard-adapter:latest`
- BuildConfig: Builds from GitHub (phase3 branch)
- Deployment: 2 replicas for HA
- Service: `llama-guard-adapter:8080`

## Integration with OGX

Update OGX config to use this adapter:

```yaml
providers:
  responses:
    - provider_id: builtin
      provider_type: inline::builtin
      config:
        moderation_endpoint: http://llama-guard-adapter:8080/v1/moderations
        moderation_headers:
          Content-Type: application/json
```

## Monitoring

Prometheus metrics available at `/metrics` (via FastAPI metrics middleware).

Health check:
```bash
curl http://llama-guard-adapter:8080/health
```

Returns:
```json
{
  "status": "healthy",
  "vllm_url": "http://llama-guard:8000",
  "vllm_model": "meta-llama/Llama-Guard-3-8B",
  "vllm_status": "connected"
}
```

## Logs

Structured JSON logs include:
- Request ID
- Input length
- vLLM response time
- Moderation result
- Any parsing errors or timeouts

Example:
```
2026-07-16 08:15:23 - main - INFO - Moderating 1 input(s)
2026-07-16 08:15:23 - main - INFO - Calling vLLM at http://llama-guard:8000/v1/chat/completions
2026-07-16 08:15:24 - main - INFO - vLLM response in 0.85s: unsafe\nS1,S9
```

## Security

- Runs as non-root user (UID 1001)
- No privilege escalation
- Drops all capabilities
- Seccomp profile: RuntimeDefault
- Optional API key authentication
- Fail-closed on all error paths

## ADR-019 Compliance

This adapter completes the **Guardrails** requirement for ADR-019:

| Requirement | Status | Solution |
|-------------|--------|----------|
| LLM Inference | ✅ | OGX + vLLM |
| Tool Runtime | ✅ | OGX + MCP |
| HIL Approval | ✅ | Custom orchestrator |
| **Guardrails** | ✅ | **OGX + Llama Guard + This Adapter** |
| PII Detection | ❌ | Phase 4 |
