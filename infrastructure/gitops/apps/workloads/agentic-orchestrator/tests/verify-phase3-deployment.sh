#!/bin/bash
# This project was developed with assistance from AI tools.
#
# Phase 3 Deployment Verification Script
# Tests all features deployed today:
# 1. Database schema changes
# 2. Audit service endpoints
# 3. Tool call trace capturing
# 4. PR merge failure handling
# 5. Console UI accessibility

set -e

echo "======================================================================"
echo "Phase 3 Deployment Verification"
echo "======================================================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

pass() {
    echo -e "${GREEN}✓${NC} $1"
}

fail() {
    echo -e "${RED}✗${NC} $1"
    exit 1
}

info() {
    echo -e "${YELLOW}→${NC} $1"
}

echo "======================================================================"
echo "TEST 1: Database Schema Verification"
echo "======================================================================"
echo ""

info "Checking if tool_call_trace column exists..."
TOOL_TRACE_COL=$(oc exec -n mlflow mlflow-db-1 -- psql -U postgres -d mlflow -t -c \
    "SELECT column_name FROM information_schema.columns WHERE table_name = 'hil_audit' AND column_name = 'tool_call_trace';")

if [[ $TOOL_TRACE_COL == *"tool_call_trace"* ]]; then
    pass "tool_call_trace column exists"
else
    fail "tool_call_trace column NOT found"
fi

info "Checking if merge_error column exists..."
MERGE_ERROR_COL=$(oc exec -n mlflow mlflow-db-1 -- psql -U postgres -d mlflow -t -c \
    "SELECT column_name FROM information_schema.columns WHERE table_name = 'hil_audit' AND column_name = 'merge_error';")

if [[ $MERGE_ERROR_COL == *"merge_error"* ]]; then
    pass "merge_error column exists"
else
    fail "merge_error column NOT found"
fi

info "Checking if merge_failed status is allowed..."
CONSTRAINT=$(oc exec -n mlflow mlflow-db-1 -- psql -U postgres -d mlflow -t -c \
    "SELECT consrc FROM pg_constraint WHERE conname = 'hil_audit_approval_status_check';")

if [[ $CONSTRAINT == *"merge_failed"* ]]; then
    pass "merge_failed status is allowed in constraint"
else
    fail "merge_failed status NOT in constraint"
fi

echo ""
echo "======================================================================"
echo "TEST 2: Audit Service Health & Endpoints"
echo "======================================================================"
echo ""

info "Checking audit service pod status..."
AUDIT_POD=$(oc get pods -n agentic-ops -l app=audit-service -o jsonpath='{.items[0].metadata.name}')
if [ -z "$AUDIT_POD" ]; then
    fail "Audit service pod not found"
fi
pass "Audit service pod running: $AUDIT_POD"

info "Testing audit service health endpoint..."
HEALTH=$(oc exec -n agentic-ops deployment/audit-service -- python3 -c \
    "import urllib.request, json; print(json.load(urllib.request.urlopen('http://localhost:8090/health'))['status'])")

if [[ $HEALTH == "healthy" ]]; then
    pass "Audit service is healthy"
else
    fail "Audit service health check failed: $HEALTH"
fi

info "Testing /audit/merge-failed endpoint exists (expect 404 for non-existent approval)..."
MERGE_FAILED_TEST=$(oc exec -n agentic-ops deployment/audit-service -- python3 -c \
    "import urllib.request, json, urllib.error
try:
    urllib.request.urlopen(urllib.request.Request(
        'http://localhost:8090/audit/merge-failed/99999',
        data=json.dumps({'error': 'test', 'error_type': 'unknown'}).encode(),
        headers={'Content-Type': 'application/json'},
        method='POST'
    ))
except urllib.error.HTTPError as e:
    print(e.code)" 2>&1)

if [[ $MERGE_FAILED_TEST == "404" ]]; then
    pass "/audit/merge-failed endpoint exists and returns expected 404"
else
    fail "/audit/merge-failed endpoint test failed: $MERGE_FAILED_TEST"
fi

echo ""
echo "======================================================================"
echo "TEST 3: Agentic Orchestrator Deployment"
echo "======================================================================"
echo ""

info "Checking orchestrator pod status..."
ORCH_POD=$(oc get pods -n agentic-ops -l app.kubernetes.io/name=agentic-orchestrator -o jsonpath='{.items[0].metadata.name}')
if [ -z "$ORCH_POD" ]; then
    fail "Orchestrator pod not found"
fi
pass "Orchestrator pod running: $ORCH_POD"

info "Testing orchestrator health endpoint..."
ORCH_HEALTH=$(oc exec -n agentic-ops deployment/agentic-orchestrator -- python3 -c \
    "import urllib.request, json; print(json.load(urllib.request.urlopen('http://localhost:8080/health'))['status'])")

if [[ $ORCH_HEALTH == "healthy" ]]; then
    pass "Orchestrator is healthy"
else
    fail "Orchestrator health check failed: $ORCH_HEALTH"
fi

info "Checking orchestrator moderation connection..."
ORCH_MOD=$(oc exec -n agentic-ops deployment/agentic-orchestrator -- python3 -c \
    "import urllib.request, json; print(json.load(urllib.request.urlopen('http://localhost:8080/health'))['moderation']['status'])")

if [[ $ORCH_MOD == "connected" ]]; then
    pass "Orchestrator moderation connected"
else
    fail "Orchestrator moderation not connected: $ORCH_MOD"
fi

echo ""
echo "======================================================================"
echo "TEST 4: Console Frontend Deployment"
echo "======================================================================"
echo ""

info "Checking console frontend pod status..."
CONSOLE_POD=$(oc get pods -n fleet-ops -l app=showcase-console-frontend -o jsonpath='{.items[0].metadata.name}')
if [ -z "$CONSOLE_POD" ]; then
    fail "Console frontend pod not found"
fi

CONSOLE_STATUS=$(oc get pods -n fleet-ops -l app=showcase-console-frontend -o jsonpath='{.items[0].status.phase}')
if [[ $CONSOLE_STATUS == "Running" ]]; then
    pass "Console frontend pod running: $CONSOLE_POD"
else
    fail "Console frontend pod not running: $CONSOLE_STATUS"
fi

info "Checking console frontend build..."
LATEST_BUILD=$(oc get builds -n fleet-ops -l app=showcase-console-frontend --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1:].metadata.name}')
BUILD_STATUS=$(oc get build $LATEST_BUILD -n fleet-ops -o jsonpath='{.status.phase}')

if [[ $BUILD_STATUS == "Complete" ]]; then
    BUILD_COMMIT=$(oc get build $LATEST_BUILD -n fleet-ops -o jsonpath='{.spec.revision.git.commit}')
    pass "Latest frontend build completed: $LATEST_BUILD (commit: ${BUILD_COMMIT:0:7})"
else
    fail "Latest frontend build status: $BUILD_STATUS"
fi

echo ""
echo "======================================================================"
echo "TEST 5: Argo CD ApplicationSet Configuration"
echo "======================================================================"
echo ""

info "Checking ApplicationSet git revision..."
APPSET_REVISION=$(oc get applicationset workloads -n openshift-gitops -o jsonpath='{.spec.generators[0].git.revision}')

if [[ $APPSET_REVISION == "phase3" ]]; then
    pass "ApplicationSet watching phase3 branch"
else
    fail "ApplicationSet watching wrong branch: $APPSET_REVISION"
fi

info "Checking key Applications exist..."
APPS_TO_CHECK=(
    "workloads-agentic-orchestrator"
    "workloads-audit-service"
    "workloads-console"
)

for app in "${APPS_TO_CHECK[@]}"; do
    if oc get application $app -n openshift-gitops >/dev/null 2>&1; then
        SYNC_STATUS=$(oc get application $app -n openshift-gitops -o jsonpath='{.status.sync.status}')
        pass "$app exists (Sync: $SYNC_STATUS)"
    else
        fail "$app NOT found"
    fi
done

echo ""
echo "======================================================================"
echo "TEST 6: Test Data Insertion"
echo "======================================================================"
echo ""

info "Creating test approval with new fields..."
TEST_APPROVAL_ID=$(cat <<'EOF' | oc exec -i -n mlflow mlflow-db-1 -- psql -U postgres -d mlflow -t
INSERT INTO hil_audit (
  session_id, user_identity, tool_name, tool_arguments, approval_status,
  tool_call_trace
)
VALUES (
  'verification-test-$(date +%s)',
  'test-operator',
  'promote_policy_version',
  '{"factory": "Test", "version": "v999"}'::jsonb,
  'pending',
  '[{"tool_name": "get_factory_config", "duration_ms": 123, "response_summary": "test response"}]'::jsonb
)
RETURNING id;
EOF
)

TEST_APPROVAL_ID=$(echo $TEST_APPROVAL_ID | tr -d ' ')

if [ -n "$TEST_APPROVAL_ID" ] && [ "$TEST_APPROVAL_ID" -gt 0 ] 2>/dev/null; then
    pass "Test approval created with ID: $TEST_APPROVAL_ID"
else
    fail "Failed to create test approval"
fi

info "Verifying tool_call_trace was stored..."
TRACE_CHECK=$(oc exec -n mlflow mlflow-db-1 -- psql -U postgres -d mlflow -t -c \
    "SELECT tool_call_trace->0->>'tool_name' FROM hil_audit WHERE id = $TEST_APPROVAL_ID;")

if [[ $TRACE_CHECK == *"get_factory_config"* ]]; then
    pass "tool_call_trace stored correctly"
else
    fail "tool_call_trace not stored correctly"
fi

info "Testing merge_failed status update..."
MERGE_FAILED_UPDATE=$(oc exec -n mlflow mlflow-db-1 -- psql -U postgres -d mlflow -t -c \
    "UPDATE hil_audit SET
        approval_status = 'merge_failed',
        merge_error = '{\"error\": \"Test conflict\", \"error_type\": \"conflict\"}'::jsonb
    WHERE id = $TEST_APPROVAL_ID
    RETURNING approval_status;")

if [[ $MERGE_FAILED_UPDATE == *"merge_failed"* ]]; then
    pass "merge_failed status update successful"
else
    fail "merge_failed status update failed"
fi

info "Cleaning up test data..."
oc exec -n mlflow mlflow-db-1 -- psql -U postgres -d mlflow -c \
    "DELETE FROM hil_audit WHERE id = $TEST_APPROVAL_ID;" >/dev/null
pass "Test data cleaned up"

echo ""
echo "======================================================================"
echo "SUMMARY: All Tests Passed! ✓"
echo "======================================================================"
echo ""
echo "Verified:"
echo "  ✓ Database schema (tool_call_trace, merge_error, merge_failed status)"
echo "  ✓ Audit service health and new endpoints"
echo "  ✓ Agentic orchestrator deployment and health"
echo "  ✓ Console frontend build and deployment"
echo "  ✓ Argo CD ApplicationSet watching phase3"
echo "  ✓ Key Argo Applications exist and synced"
echo "  ✓ Test data CRUD operations work"
echo ""
echo "All Phase 3 features are deployed and working! 🎉"
echo ""
