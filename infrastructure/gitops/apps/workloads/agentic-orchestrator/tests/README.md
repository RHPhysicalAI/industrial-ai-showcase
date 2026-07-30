# Agentic Orchestrator Tests

This directory contains tests for the Phase 3 HIL (Human-in-the-Loop) approval workflow.

## Test Scripts

### 1. `test-approval-data.sh` - Quick Data Completeness Check (~10 seconds)

**Purpose**: Verify that approval requests contain complete blast_radius and moderation_results data.

**Usage**:
```bash
./test-approval-data.sh ["Factory A"|"Factory B"]
```

**What it tests**:
- ✅ Approval request created successfully
- ✅ `blast_radius` field present with: factory, robot_count, impact_level
- ✅ `moderation_results` field present with: input.decision, output.decision

**Example**:
```bash
# Test Factory A
./test-approval-data.sh "Factory A"

# Test Factory B
./test-approval-data.sh "Factory B"
```

---

### 2. `test-hil-e2e.sh` - Full End-to-End Flow (~2-3 minutes)

**Purpose**: Verify the complete HIL approval → PR merge → Argo CD sync → InferenceService update flow.

**Usage**:
```bash
./test-hil-e2e.sh [factory] [version]
```

**What it tests**:
1. ✅ Agent creates approval with complete data
2. ✅ Approval has blast_radius + moderation_results
3. ✅ Agent opens PR when approved
4. ✅ PR merges successfully
5. ✅ Argo CD detects Git change
6. ✅ Argo CD syncs to new commit
7. ✅ InferenceService updates to new model version

**Example**:
```bash
# Promote version 10 to Factory A
./test-hil-e2e.sh "Factory A" 10

# Promote version 3 to Factory B
./test-hil-e2e.sh "Factory B" 3
```

**Note**: This test will:
- Create a real PR in GitHub
- Merge the PR (creates a new commit)
- Trigger Argo CD sync
- Update the actual InferenceService

---

### 3. `test-moderation-e2e.sh` - Guardrails Integration Test (~30 seconds)

**Purpose**: Verify Llama Guard content moderation integration.

**Usage**:
```bash
./test-moderation-e2e.sh
```

**What it tests**:
- ✅ Safe input allowed
- ✅ Unsafe input blocked
- ✅ Health check includes moderation status
- ✅ Moderation logs visible

---

## Test Requirements

### Prerequisites

1. **Cluster Access**: Logged into OpenShift cluster with `oc`
2. **GitHub CLI**: `gh` installed and authenticated
3. **Python 3**: For JSON parsing
4. **Network Access**: Port-forwarding to services

### Namespaces Used

- `agentic-ops` - Orchestrator and Audit services
- `mlflow` - PostgreSQL database
- `robot-edge` - Factory A InferenceServices
- `factory-b` - Factory B InferenceServices
- `openshift-gitops` - Argo CD Applications

---

## CI/CD Integration

### Running in CI Pipeline

These tests can be integrated into a CI pipeline:

```yaml
# Example GitHub Actions
test-hil-approval:
  runs-on: ubuntu-latest
  steps:
    - name: Login to OpenShift
      run: oc login --token=${{ secrets.OC_TOKEN }} ${{ secrets.OC_URL }}
    
    - name: Run Approval Data Test
      run: ./test-approval-data.sh
      timeout-minutes: 1
    
    - name: Run E2E Test
      run: ./test-hil-e2e.sh "Factory A" 100
      timeout-minutes: 5
```

### Test Isolation

- Use unique version numbers for each test run to avoid conflicts
- Tests create real PRs - consider using a test repository fork
- Cleanup: Tests do not auto-delete created resources

---

## Troubleshooting

### Test Fails: "No approval ID returned"

**Cause**: Orchestrator service not reachable

**Fix**:
```bash
# Check orchestrator is running
oc get pods -n agentic-ops -l app=agentic-orchestrator

# Check service
oc get svc agentic-orchestrator -n agentic-ops
```

### Test Fails: "blast_radius is NULL"

**Cause**: Network policy blocking MCP Fleet → Console Backend

**Fix**:
```bash
# Verify network connectivity
oc exec -n agentic-ops deployment/mcp-fleet-server -- \
  curl -m 5 http://showcase-console-backend.fleet-ops.svc.cluster.local:8090/api/fleet

# Should return fleet data, not timeout
```

### Test Fails: "Argo CD did not sync"

**Cause**: Auto-sync not enabled for target application

**Fix**:
```bash
# Enable auto-sync for robot-edge
oc patch application workloads-robot-edge -n openshift-gitops --type merge \
  -p '{"spec":{"syncPolicy":{"automated":{"prune":true,"selfHeal":true}}}}'

# Enable auto-sync for factory-b
oc patch application workloads-factory-b -n openshift-gitops --type merge \
  -p '{"spec":{"syncPolicy":{"automated":{"prune":true,"selfHeal":true}}}}'
```

### Test Fails: "InferenceService not found"

**Cause**: Namespace doesn't exist

**Fix**:
```bash
# Create namespace if missing
oc create namespace robot-edge
oc create namespace factory-b
```

---

## Test Data Cleanup

Tests create persistent data:

**Approvals in PostgreSQL**:
```sql
-- View recent test approvals
SELECT id, session_id, tool_name, approval_status, timestamp 
FROM hil_audit 
WHERE session_id LIKE 'test-%' 
ORDER BY timestamp DESC 
LIMIT 10;

-- Clean up test approvals (optional)
DELETE FROM hil_audit WHERE session_id LIKE 'test-%';
```

**GitHub PRs**:
```bash
# List recent test PRs
gh pr list --limit 20

# PRs are merged, not deleted - safe to leave
```

**InferenceServices**:
```bash
# Check current model versions
oc get inferenceservice vla-warehouse -n robot-edge \
  -o jsonpath='{.spec.predictor.model.storageUri}'

# Tests increment version numbers - no cleanup needed
```

---

## Performance Benchmarks

Measured on OSD hub cluster (phase3 branch):

| Test | Duration | API Calls | GPU Usage |
|------|----------|-----------|-----------|
| `test-approval-data.sh` | ~10s | 3 | None |
| `test-moderation-e2e.sh` | ~30s | 5 | L40S (Llama Guard) |
| `test-hil-e2e.sh` | ~2-3min | 10+ | None (ISVC pending GPU) |

---

## Contributing

When adding new tests:

1. Follow the naming convention: `test-<feature>-<type>.sh`
2. Include usage instructions in the header
3. Add cleanup trap for port-forwards
4. Use meaningful exit codes (0 = success, 1 = failure)
5. Print ✓/❌ for each validation step
6. Update this README with test documentation
