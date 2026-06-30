# LangGraph Hello World Spike

> [!NOTE]
> This project was developed with assistance from AI tools.

**Goal**: Validate LangGraph tool calling patterns work before implementing full agent orchestrator.

**Status**: 🚧 Not yet run (awaiting validation)

---

## What We're Testing

This spike has 3 progressive tests:

1. **`01_hello_agent.py`** - Pure LangGraph (no LLM, no tools)
   - Validates: StateGraph, nodes, edges work
   - Runs on: Your workstation (no cluster dependency)

2. **`02_agent_with_llm.py`** - LangGraph + vLLM
   - Validates: LangGraph can call vLLM via port-forward
   - Runs on: Your workstation → vLLM in cluster

3. **`03_agent_with_tools.py`** - LangGraph + vLLM + Tools
   - Validates: Agent can call tools (the pattern for MCP servers)
   - Runs on: Your workstation → vLLM in cluster

---

## Setup

### 1. Create Virtual Environment

```bash
cd spikes/week0-validation/langgraph-hello

# Create venv
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Start vLLM Port-Forward (for tests 2 & 3)

In a **separate terminal**:

```bash
# Ensure vLLM pod is running (from ../vllm-test/)
oc get pod vllm-test -n agentic-ops

# Port-forward
oc port-forward vllm-test 8000:8000 -n agentic-ops
```

Leave this running while you test.

---

## Test 1: Pure LangGraph (No LLM)

```bash
python 01_hello_agent.py
```

**Expected output**:
```
Planning step...
Executing step...
Final result: {'messages': ['User asked a question', 'I am planning...'], 'result': 'Task complete!'}
```

**Success criteria**:
- [x] Script runs without errors
- [x] You see "Planning step..." → "Executing step..."
- [x] Final result contains both messages and result

**What this validates**: Basic LangGraph StateGraph pattern works.

---

## Test 2: LangGraph + vLLM

```bash
python 02_agent_with_llm.py
```

**Expected output**:
```
Calling vLLM...
Assistant: The capital of France is Paris.
```

**Success criteria**:
- [x] vLLM responds via port-forward
- [x] Response is coherent
- [x] Latency is reasonable (< 5 seconds)

**Troubleshooting**:
- If connection refused: Check port-forward is running
- If 404 error: vLLM might not be ready (check `oc logs vllm-test`)
- If timeout: vLLM might be overloaded or model not loaded

---

## Test 3: LangGraph + Tools

```bash
python 03_agent_with_tools.py
```

**Expected output**:
```
============================================================
Test 1: Get temperature in Boston
============================================================
Tool returned: Temperature in Boston is 72°F