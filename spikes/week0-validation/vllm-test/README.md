# vLLM Test Spike - Llama-3.1-8B on L4 GPU

> [!NOTE]
> This project was developed with assistance from AI tools.

**Goal**: Validate that vLLM can serve Llama-3.1-8B-Instruct on an L4 GPU with < 5 second p50 latency for inference.

**Status**: 🚧 Not yet run (awaiting validation)

---

## Prerequisites

### 1. HuggingFace Token

Llama models are gated. You need to:

1. Create a HuggingFace account: https://huggingface.co/join
2. Accept the Llama 3.1 license: https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct
3. Create an access token: https://huggingface.co/settings/tokens (read permission is sufficient)

### 2. Create Namespace & Secret

```bash
# Create namespace
oc create namespace agentic-ops

# Store your HuggingFace token
oc create secret generic hf-token \
  -n agentic-ops \
  --from-literal=token='hf_YourTokenGoesHere'
```

### 3. Verify L4 GPU Availability

```bash
# Check for L4 GPU nodes
oc get nodes -l nvidia.com/gpu.product=NVIDIA-L4 -o wide

# Expected output:
# NAME           STATUS   ROLES    AGE   VERSION   GPU
# worker-gpu-1   Ready    worker   5d    v1.28.0   NVIDIA-L4
```

If no nodes are found, check GPU operator installation or provision L4 nodes before proceeding.

---

## Deployment

### Deploy vLLM Pod

```bash
cd spikes/week0-validation/vllm-test

# Deploy
oc apply -f vllm-pod.yaml

# Watch pod startup
oc get pod vllm-test -n agentic-ops -w

# Watch logs (model download + loading takes ~5 minutes)
oc logs -f vllm-test -n agentic-ops
```

**Expected log output**:
```
INFO: Started server process
INFO: Waiting for application startup
INFO: Loading model meta-llama/Llama-3.1-8B-Instruct
INFO: Model loaded successfully in 287.3s
INFO: Application startup complete
```

### Port-Forward for Testing

Once the pod is ready (readiness probe passes):

```bash
# Forward port 8000 to your workstation
oc port-forward vllm-test 8000:8000 -n agentic-ops
```

Leave this terminal open. You'll test in a new terminal.

---

## Validation Tests

### Test 1: Basic Inference

```bash
# Simple completion test
curl http://localhost:8000/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "meta-llama/Llama-3.1-8B-Instruct",
    "prompt": "What is 2+2?",
    "max_tokens": 50,
    "temperature": 0.7
  }' | jq .

# Expected output:
# {
#   "id": "cmpl-...",
#   "object": "text_completion",
#   "created": 1719705600,
#   "model": "meta-llama/Llama-3.1-8B-Instruct",
#   "choices": [
#     {
#       "text": " 4",
#       ...
#     }
#   ]
# }
```

### Test 2: Chat Completion (Preferred for Agents)

```bash
# Chat-style API (what LangGraph will use)
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "meta-llama/Llama-3.1-8B-Instruct",
    "messages": [
      {"role": "user", "content": "What is the capital of France?"}
    ],
    "max_tokens": 100,
    "temperature": 0.7
  }' | jq .

# Expected output:
# {
#   "id": "chatcmpl-...",
#   "choices": [
#     {
#       "message": {
#         "role": "assistant",
#         "content": "The capital of France is Paris."
#       },
#       ...
#     }
#   ],
#   ...
# }
```

### Test 3: Latency Measurement

```bash
# Run 10 requests and measure latency
for i in {1..10}; do
  echo "Request $i:"
  time curl -s http://localhost:8000/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{
      "model": "meta-llama/Llama-3.1-8B-Instruct",
      "messages": [{"role": "user", "content": "Hello, world!"}],
      "max_tokens": 20
    }' | jq -r '.choices[0].message.content'
  echo "---"
done
```

**Target**: < 5 seconds per request (p50)

### Test 4: Tool Calling Format (Critical for LangGraph)

```bash
# Test that Llama 3.1 can emit tool calls
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "meta-llama/Llama-3.1-8B-Instruct",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant with access to tools."},
      {"role": "user", "content": "What is the temperature in Boston?"}
    ],
    "tools": [
      {
        "type": "function",
        "function": {
          "name": "get_temperature",
          "description": "Get the current temperature for a location",
          "parameters": {
            "type": "object",
            "properties": {
              "location": {"type": "string", "description": "The city name"}
            },
            "required": ["location"]
          }
        }
      }
    ],
    "tool_choice": "auto",
    "max_tokens": 100
  }' | jq .

# Expected: Model should call the tool, not answer directly
```

---

## Success Criteria

- [ ] Pod starts successfully on L4 GPU node
- [ ] Model loads in < 10 minutes
- [ ] Basic inference returns coherent responses
- [ ] Chat completion API works
- [ ] Latency p50 < 5 seconds (p99 < 10 seconds)
- [ ] Tool calling format is supported
- [ ] GPU memory usage is reasonable (~16 GB / 24 GB)

---

## Troubleshooting

### Pod stuck in "Pending"

```bash
# Check why pod isn't scheduled
oc describe pod vllm-test -n agentic-ops | grep -A 10 Events

# Common issues:
# - No L4 GPU nodes available
# - GPU already allocated to another pod
# - Insufficient CPU/memory
```

### Model download fails

```bash
# Check logs for HuggingFace token errors
oc logs vllm-test -n agentic-ops | grep -i "authentication\|token\|403"

# Verify secret exists
oc get secret hf-token -n agentic-ops -o yaml

# Common issues:
# - HuggingFace token not accepted for Llama 3.1 (need to accept license)
# - Token has wrong permissions (need 'read' permission)
# - Token stored incorrectly in secret
```

### OOMKilled (Out of Memory)

```bash
# Check if pod was killed due to memory
oc get pod vllm-test -n agentic-ops -o jsonpath='{.status.containerStatuses[0].lastState.terminated.reason}'

# If OOMKilled:
# - Reduce --max-model-len (try 2048 instead of 4096)
# - Reduce --gpu-memory-utilization (try 0.7 instead of 0.85)
# - Increase memory request/limit
```

### High latency (> 5 seconds)

Check GPU utilization:

```bash
# Get GPU metrics (if NVIDIA DCGM exporter is running)
oc exec vllm-test -n agentic-ops -- nvidia-smi

# Look for:
# - GPU utilization should be 80-100% during inference
# - GPU memory should be ~16 GB used
# - Temperature should be reasonable (< 80°C)
```

---

## Cleanup

```bash
# Delete pod
oc delete pod vllm-test -n agentic-ops

# (Optional) Delete service
oc delete svc vllm-test -n agentic-ops

# Keep namespace and secret for next spike
```

---

## Next Steps

Once validated:
- [ ] Document results in `../VALIDATION-RESULTS.md`
- [ ] If successful: Create Helm chart for production vLLM deployment
- [ ] If failed: Try alternative (smaller model, different serving framework)
- [ ] Proceed to `langgraph-hello` spike (LangGraph calling vLLM)