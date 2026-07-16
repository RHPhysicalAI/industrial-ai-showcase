#!/bin/bash
# This project was developed with assistance from AI tools.
#
# End-to-End HIL Approval → PR → Argo CD Sync Test
#
# Tests the complete flow:
# 1. Agent receives promotion request
# 2. Creates approval with blast_radius + moderation_results
# 3. Operator approves
# 4. Agent opens PR and merges it
# 5. Argo CD syncs the change
# 6. InferenceService updates with new model version
#
# Usage:
#   ./test-hil-e2e.sh [factory] [version]
#
# Examples:
#   ./test-hil-e2e.sh "Factory A" 9
#   ./test-hil-e2e.sh "Factory B" 2

set -euo pipefail

# Configuration
FACTORY="${1:-Factory A}"
VERSION="${2:-9}"
NAMESPACE_ORCHESTRATOR="agentic-ops"
NAMESPACE_AUDIT="agentic-ops"
TIMEOUT_APPROVAL=30
TIMEOUT_PR=60
TIMEOUT_ARGO=120

# Determine target namespace from factory
case "$FACTORY" in
  "Factory A")
    TARGET_NAMESPACE="robot-edge"
    ;;
  "Factory B")
    TARGET_NAMESPACE="factory-b"
    ;;
  *)
    echo "ERROR: Unknown factory: $FACTORY"
    echo "Supported: 'Factory A', 'Factory B'"
    exit 1
    ;;
esac

echo "=========================================="
echo "HIL End-to-End Test"
echo "=========================================="
echo "Factory: $FACTORY"
echo "Version: vla-warehouse version $VERSION"
echo "Target Namespace: $TARGET_NAMESPACE"
echo "=========================================="
echo

# Cleanup function
cleanup() {
  echo
  echo "Cleaning up port-forwards..."
  pkill -f "port-forward.*agentic" 2>/dev/null || true
}
trap cleanup EXIT

# Step 1: Send promotion request to agent
echo "=== Step 1: Send Promotion Request to Agent ==="
oc port-forward -n $NAMESPACE_ORCHESTRATOR svc/agentic-orchestrator 18080:8080 &
sleep 3

SESSION_ID="test-e2e-$(date +%s)"
QUERY="Promote model vla-warehouse version $VERSION to $FACTORY"

echo "Query: $QUERY"
RESPONSE=$(curl -s -X POST http://localhost:18080/query \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"$QUERY\", \"session_id\": \"$SESSION_ID\"}")

echo "Response:"
echo "$RESPONSE" | python3 -m json.tool

APPROVAL_ID=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('pending_approval_id', 0))")

if [ "$APPROVAL_ID" = "0" ] || [ -z "$APPROVAL_ID" ]; then
  echo "ERROR: No approval ID returned"
  exit 1
fi

echo "✓ Approval request created: #$APPROVAL_ID"
echo

# Step 2: Verify approval has complete data
echo "=== Step 2: Verify Approval Data ==="
sleep 2

HAS_BLAST=$(oc exec -n mlflow mlflow-db-1 -- psql -U postgres -d mlflow -t -c \
  "SELECT blast_radius IS NOT NULL FROM hil_audit WHERE id = $APPROVAL_ID")
HAS_MODERATION=$(oc exec -n mlflow mlflow-db-1 -- psql -U postgres -d mlflow -t -c \
  "SELECT moderation_results IS NOT NULL FROM hil_audit WHERE id = $APPROVAL_ID")

HAS_BLAST=$(echo "$HAS_BLAST" | tr -d '[:space:]')
HAS_MODERATION=$(echo "$HAS_MODERATION" | tr -d '[:space:]')

if [ "$HAS_BLAST" != "t" ]; then
  echo "ERROR: Approval #$APPROVAL_ID missing blast_radius"
  exit 1
fi

if [ "$HAS_MODERATION" != "t" ]; then
  echo "ERROR: Approval #$APPROVAL_ID missing moderation_results"
  exit 1
fi

echo "✓ Approval has blast_radius"
echo "✓ Approval has moderation_results"
echo

# Get blast radius details
echo "Blast Radius:"
oc exec -n mlflow mlflow-db-1 -- psql -U postgres -d mlflow -c \
  "SELECT jsonb_pretty(blast_radius) FROM hil_audit WHERE id = $APPROVAL_ID" | grep -v "row\|---\|jsonb_pretty"
echo

# Step 3: Approve the request
echo "=== Step 3: Approve Request ==="
APPROVAL_RESPONSE=$(curl -s -X POST http://localhost:18080/approval/$APPROVAL_ID/resume \
  -H "Content-Type: application/json" \
  -d '{"decision": "approved"}')

echo "Approval Response:"
echo "$APPROVAL_RESPONSE" | python3 -m json.tool

PR_URL=$(echo "$APPROVAL_RESPONSE" | python3 -c "import sys, json, re; r = json.load(sys.stdin).get('response', ''); m = re.search(r'https://github.com/[^)]+', r); print(m.group(0) if m else '')")

if [ -z "$PR_URL" ]; then
  echo "ERROR: No PR URL in response"
  exit 1
fi

echo "✓ PR created and merged: $PR_URL"
PR_NUMBER=$(echo "$PR_URL" | grep -o '[0-9]*$')
echo

# Step 4: Verify PR was merged
echo "=== Step 4: Verify PR Merged ==="
sleep 3

PR_STATE=$(gh pr view "$PR_NUMBER" --json state --jq '.state')
if [ "$PR_STATE" != "MERGED" ]; then
  echo "ERROR: PR #$PR_NUMBER not merged (state: $PR_STATE)"
  exit 1
fi

echo "✓ PR #$PR_NUMBER merged successfully"
echo

# Step 5: Get expected Git commit SHA
echo "=== Step 5: Get Expected Git Commit ==="
git fetch origin phase3 >/dev/null 2>&1
EXPECTED_COMMIT=$(git rev-parse origin/phase3)
SHORT_COMMIT=${EXPECTED_COMMIT:0:7}
echo "Expected commit: $SHORT_COMMIT ($EXPECTED_COMMIT)"
echo

# Step 6: Wait for Argo CD to sync
echo "=== Step 6: Wait for Argo CD Sync ==="
ARGO_APP="workloads-$TARGET_NAMESPACE"
echo "Watching Argo Application: $ARGO_APP"

# Check if auto-sync is enabled
AUTO_SYNC=$(oc get application "$ARGO_APP" -n openshift-gitops -o jsonpath='{.spec.syncPolicy.automated}' 2>/dev/null || echo "")
if [ -z "$AUTO_SYNC" ]; then
  echo "⚠️  Auto-sync not enabled for $ARGO_APP"
  echo "   Triggering manual sync..."
  oc patch application "$ARGO_APP" -n openshift-gitops --type merge \
    -p '{"operation": {"initiatedBy": {"username": "test-e2e"}, "sync": {}}}' >/dev/null
fi

SYNCED=false
for i in $(seq 1 $TIMEOUT_ARGO); do
  SYNC_STATUS=$(oc get application "$ARGO_APP" -n openshift-gitops -o jsonpath='{.status.sync.status}' 2>/dev/null || echo "Unknown")
  SYNC_REVISION=$(oc get application "$ARGO_APP" -n openshift-gitops -o jsonpath='{.status.sync.revision}' 2>/dev/null || echo "")

  echo -ne "\rAttempt $i/$TIMEOUT_ARGO: Status=$SYNC_STATUS, Revision=${SYNC_REVISION:0:7}"

  if [ "$SYNC_STATUS" = "Synced" ] && [[ "$SYNC_REVISION" == "$EXPECTED_COMMIT"* ]]; then
    SYNCED=true
    echo
    break
  fi

  sleep 1
done

if [ "$SYNCED" = false ]; then
  echo
  echo "ERROR: Argo CD did not sync to commit $SHORT_COMMIT within ${TIMEOUT_ARGO}s"
  echo "Current status: $SYNC_STATUS"
  echo "Current revision: ${SYNC_REVISION:0:7}"
  exit 1
fi

echo "✓ Argo CD synced to commit $SHORT_COMMIT"
echo

# Step 7: Verify InferenceService updated
echo "=== Step 7: Verify InferenceService Updated ==="
sleep 5

if ! oc get inferenceservice vla-warehouse -n "$TARGET_NAMESPACE" >/dev/null 2>&1; then
  echo "ERROR: InferenceService vla-warehouse not found in $TARGET_NAMESPACE"
  exit 1
fi

ACTUAL_VERSION=$(oc get inferenceservice vla-warehouse -n "$TARGET_NAMESPACE" -o jsonpath='{.spec.predictor.model.storageUri}')
EXPECTED_VERSION="s3://mlflow/models/vla-warehouse/vla-warehouse version $VERSION"

if [ "$ACTUAL_VERSION" != "$EXPECTED_VERSION" ]; then
  echo "ERROR: InferenceService has wrong model version"
  echo "  Expected: $EXPECTED_VERSION"
  echo "  Actual:   $ACTUAL_VERSION"
  exit 1
fi

echo "✓ InferenceService updated to: $ACTUAL_VERSION"
echo

# Step 8: Summary
echo "=========================================="
echo "✅ All Tests Passed!"
echo "=========================================="
echo
echo "Summary:"
echo "  1. ✓ Agent created approval #$APPROVAL_ID"
echo "  2. ✓ Approval has blast_radius + moderation_results"
echo "  3. ✓ Agent opened and merged PR #$PR_NUMBER"
echo "  4. ✓ Argo CD synced to commit $SHORT_COMMIT"
echo "  5. ✓ InferenceService updated to version $VERSION"
echo
echo "Full flow working end-to-end!"
echo "=========================================="
