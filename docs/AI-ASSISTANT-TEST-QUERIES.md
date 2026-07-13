# AI Assistant - Test Query Reference

Quick reference for testing the Phase 3 Milestone 1 AI Assistant.

## Access

**URL:** https://showcase-console-fleet-ops.apps.g4h4d3j7q1c9f7m.cimo.p1.openshiftapps.com

**How to Open:**
1. Click the **blue floating chat button** in the bottom-right corner
2. Drawer slides in from the right with chat interface
3. Type your question and click "Ask"
4. Click the **×** button in the header to close

---

## Test Queries

### ✅ 1. List All Experiments (VERIFIED)
```
What experiments are available?
```

**Expected Response:**
- Lists 3 experiments
- Experiment IDs: exp-001, exp-002, exp-003
- Names: robot-navigation-training, object-detection-vla, manipulation-policy
- Natural language description

**Tool Called:** `list_experiments`

---

### 2. Get Runs for Experiment
```
Show me runs for experiment exp-001
```

**Expected Response:**
- Lists 2 runs: run-001-a (FINISHED), run-001-b (RUNNING)
- Shows status, start time, parameters
- Mentions metrics (accuracy, loss)

**Tool Called:** `list_runs`

---

### 3. Get Specific Run Details
```
Tell me about run run-001-a
```

**Expected Response:**
- Full run details
- Parameters: learning_rate=0.001, batch_size=32, epochs=100
- Metrics: accuracy=0.956, loss=0.045
- Status: FINISHED
- Tags: model=GR00T-N1.7, gpu=L40S

**Tool Called:** `get_run`

---

### 4. Get Metrics for Run
```
What are the metrics for run run-001-a?
```

**Expected Response:**
- Metrics dictionary
- loss: 0.045
- accuracy: 0.956
- val_loss: 0.052
- val_accuracy: 0.948

**Tool Called:** `get_metrics`

---

### 5. Multi-Step Reasoning
```
Which run in experiment exp-001 has the best accuracy?
```

**Expected Response:**
- Agent calls `list_runs` to get runs
- Agent calls `get_metrics` for each run
- Compares accuracy values
- Answers: "run-001-b has the best accuracy (0.962)"

**Tools Called:** `list_runs`, `get_metrics` (multiple times)

---

### 6. Natural Language Variation
```
Tell me about the VLA training experiments
```

**Expected Response:**
- Agent interprets "VLA" as related to vision-language-action
- Searches through experiments
- Highlights relevant experiments (exp-002: object-detection-vla)

**Tools Called:** `list_experiments`, possibly `get_experiment`

---

### 7. Specific Experiment Details
```
What's in the manipulation-policy experiment?
```

**Expected Response:**
- Agent searches for experiment by name
- Returns exp-003 details
- Mentions team: manipulation, project: phase2

**Tool Called:** `get_experiment`

---

### 8. Running vs Finished Status
```
Which runs are currently running?
```

**Expected Response:**
- Agent searches across experiments
- Identifies run-001-b (status: RUNNING)
- Mentions it started on 2026-07-01

**Tool Called:** `list_runs` (for all experiments)

---

### 9. Parameter Comparison
```
What learning rate was used in exp-001 runs?
```

**Expected Response:**
- Agent gets runs for exp-001
- Extracts learning_rate parameter
- run-001-a: 0.001
- run-001-b: 0.0005

**Tools Called:** `list_runs`, `get_run` (possibly)

---

### 10. Edge Case - Invalid Run ID
```
Show me metrics for run xyz-999
```

**Expected Response:**
- Agent calls `get_metrics` with run_id=xyz-999
- MCP server returns 404
- Agent handles error gracefully
- Response: "Run xyz-999 not found" or similar

**Tool Called:** `get_metrics` (returns error)

---

## Mock Data Reference

### Experiments
| ID | Name | Team | Project |
|----|------|------|---------|
| exp-001 | robot-navigation-training | robotics | phase3 |
| exp-002 | object-detection-vla | perception | phase1 |
| exp-003 | manipulation-policy | manipulation | phase2 |

### Runs (exp-001)
| Run ID | Status | Accuracy | Loss | Learning Rate | Batch Size |
|--------|--------|----------|------|---------------|------------|
| run-001-a | FINISHED | 0.956 | 0.045 | 0.001 | 32 |
| run-001-b | RUNNING | 0.962 | 0.038 | 0.0005 | 64 |

### Runs (exp-002)
| Run ID | Status | mAP | Precision | Recall |
|--------|--------|-----|-----------|--------|
| run-002-a | FINISHED | 0.782 | 0.845 | 0.812 |

---

## What to Look For

### ✅ Good Signs
- **Fast response** (<3 seconds)
- **Natural language** (not just JSON dumps)
- **Tool selection** (agent picks correct tool)
- **Multi-step reasoning** (chains tools together)
- **Error handling** (graceful 404 responses)
- **Contextual awareness** ("Would you like to see runs for this experiment?")

### ❌ Issues to Report
- **Timeout** (>10 seconds)
- **JSON in response** (should be natural language)
- **Wrong tool called** (e.g., get_run when should call list_experiments)
- **Infinite loop** (agent keeps calling same tool)
- **Error messages exposed** (should be user-friendly)
- **No response** (silent failure)

---

## Known Limitations (By Design)

1. **Read-Only:** Cannot create experiments or log new runs
2. **Mock Data:** Returns fake data, not real MLflow
3. **No Session Memory:** Each query is independent
4. **Simple Chains:** 2-step tool calling pattern (no complex workflows)
5. **No HIL:** Tool calls execute automatically (Phase 3 Milestone 2 adds Llama Stack)

---

## Troubleshooting

### "Agent service unavailable"
**Check:**
```bash
oc get pods -n agentic-ops -l app=agentic-orchestrator
oc get pods -n agentic-ops -l app=vllm-agent-brain
oc get pods -n agentic-ops -l app=mcp-mlflow-server
```

### "Agent thinking..." forever
**Likely cause:** vLLM timeout or model crash

**Check vLLM logs:**
```bash
oc logs -n agentic-ops -l app=vllm-agent-brain --tail=50
```

### "Error: Agent query failed"
**Check orchestrator logs:**
```bash
oc logs -n agentic-ops -l app=agentic-orchestrator --tail=50
```

---

**Last Updated:** 2026-07-08  
**Milestone:** Phase 3 Milestone 1 (Days 4-5 Console Integration)