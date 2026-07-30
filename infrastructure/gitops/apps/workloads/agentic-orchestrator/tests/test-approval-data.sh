#!/bin/bash
# This project was developed with assistance from AI tools.
#
# Quick Test: Approval Data Completeness
#
# Tests that approvals are created with:
# - blast_radius (factory, robot_count, versions, impact_level)
# - moderation_results (input/output checks)
#
# Usage:
#   ./test-approval-data.sh [factory]

set -euo pipefail

FACTORY="${1:-Factory A}"
NAMESPACE="agentic-ops"

echo "=== Testing Approval Data Completeness ==="
echo "Factory: $FACTORY"
echo

# Cleanup
cleanup() {
  pkill -f "port-forward.*agentic" 2>/dev/null || true
}
trap cleanup EXIT

# Create approval
echo "Creating approval request..."
oc port-forward -n $NAMESPACE svc/agentic-orchestrator 18080:8080 >/dev/null 2>&1 &
sleep 3

SESSION_ID="test-data-$(date +%s)"
VERSION="test-$(date +%s | tail -c 4)"

RESPONSE=$(curl -s -X POST http://localhost:18080/query \
  -H "Content-Type: application/json" \
  -d "{\"query\": \"Promote model vla-warehouse version $VERSION to $FACTORY\", \"session_id\": \"$SESSION_ID\"}")

APPROVAL_ID=$(echo "$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('pending_approval_id', 0))" 2>/dev/null || echo "0")

if [ "$APPROVAL_ID" = "0" ]; then
  echo "❌ FAILED: No approval ID returned"
  echo "Response: $RESPONSE"
  exit 1
fi

echo "✓ Created approval #$APPROVAL_ID"
echo

# Wait for async processes to complete
sleep 2

# Check blast_radius
echo "Checking blast_radius..."
BLAST_DATA=$(oc exec -n mlflow mlflow-db-1 -- psql -U postgres -d mlflow -t -c \
  "SELECT blast_radius FROM hil_audit WHERE id = $APPROVAL_ID" 2>/dev/null)

if [ -z "$BLAST_DATA" ] || [ "$BLAST_DATA" = " " ]; then
  echo "❌ FAILED: blast_radius is NULL"
  exit 1
fi

# Parse blast_radius JSON
FACTORY_NAME=$(echo "$BLAST_DATA" | python3 -c "import sys, json; print(json.loads(sys.stdin.read()).get('factory', 'MISSING'))" 2>/dev/null || echo "PARSE_ERROR")
ROBOT_COUNT=$(echo "$BLAST_DATA" | python3 -c "import sys, json; print(json.loads(sys.stdin.read()).get('robot_count', 'MISSING'))" 2>/dev/null || echo "PARSE_ERROR")
IMPACT_LEVEL=$(echo "$BLAST_DATA" | python3 -c "import sys, json; print(json.loads(sys.stdin.read()).get('impact_level', 'MISSING'))" 2>/dev/null || echo "PARSE_ERROR")

if [ "$FACTORY_NAME" = "MISSING" ] || [ "$FACTORY_NAME" = "PARSE_ERROR" ]; then
  echo "❌ FAILED: blast_radius missing 'factory' field"
  echo "Data: $BLAST_DATA"
  exit 1
fi

if [ "$ROBOT_COUNT" = "MISSING" ] || [ "$ROBOT_COUNT" = "PARSE_ERROR" ]; then
  echo "❌ FAILED: blast_radius missing 'robot_count' field"
  exit 1
fi

if [ "$IMPACT_LEVEL" = "MISSING" ] || [ "$IMPACT_LEVEL" = "PARSE_ERROR" ]; then
  echo "❌ FAILED: blast_radius missing 'impact_level' field"
  exit 1
fi

echo "✓ blast_radius complete:"
echo "  - Factory: $FACTORY_NAME"
echo "  - Robots: $ROBOT_COUNT"
echo "  - Impact: $IMPACT_LEVEL"
echo

# Check moderation_results
echo "Checking moderation_results..."
MOD_DATA=$(oc exec -n mlflow mlflow-db-1 -- psql -U postgres -d mlflow -t -c \
  "SELECT moderation_results FROM hil_audit WHERE id = $APPROVAL_ID" 2>/dev/null)

if [ -z "$MOD_DATA" ] || [ "$MOD_DATA" = " " ]; then
  echo "❌ FAILED: moderation_results is NULL"
  exit 1
fi

# Parse moderation_results JSON
INPUT_DECISION=$(echo "$MOD_DATA" | python3 -c "import sys, json; print(json.loads(sys.stdin.read()).get('input', {}).get('decision', 'MISSING'))" 2>/dev/null || echo "PARSE_ERROR")
OUTPUT_DECISION=$(echo "$MOD_DATA" | python3 -c "import sys, json; print(json.loads(sys.stdin.read()).get('output', {}).get('decision', 'MISSING'))" 2>/dev/null || echo "PARSE_ERROR")

if [ "$INPUT_DECISION" = "MISSING" ] || [ "$INPUT_DECISION" = "PARSE_ERROR" ]; then
  echo "❌ FAILED: moderation_results missing input.decision"
  exit 1
fi

if [ "$OUTPUT_DECISION" = "MISSING" ] || [ "$OUTPUT_DECISION" = "PARSE_ERROR" ]; then
  echo "❌ FAILED: moderation_results missing output.decision"
  exit 1
fi

echo "✓ moderation_results complete:"
echo "  - Input: $INPUT_DECISION"
echo "  - Output: $OUTPUT_DECISION"
echo

echo "=========================================="
echo "✅ All Data Checks Passed!"
echo "=========================================="
echo "Approval #$APPROVAL_ID has complete data:"
echo "  ✓ blast_radius (factory, robot_count, impact_level)"
echo "  ✓ moderation_results (input/output decisions)"
echo
