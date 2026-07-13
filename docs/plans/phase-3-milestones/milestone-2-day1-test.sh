#!/bin/bash
# This project was developed with assistance from AI tools.
#
# Milestone 2 Day 1 - Testing Script
# Tests MCP server state-modifying tool and audit service

set -e

echo "=========================================="
echo "Milestone 2 Day 1 - Testing"
echo "=========================================="
echo ""

# Test 1: MCP Server Tool Discovery
echo "Test 1: MCP Server Tool Discovery"
echo "-----------------------------------"
oc exec -n agentic-ops deployment/agentic-orchestrator -- python -c "
import requests, json

resp = requests.get('http://mcp-mlflow-server.agentic-ops.svc.cluster.local:8080/mcp/tools')
tools = resp.json()['tools']

print(f'✅ Total tools: {len(tools)}')
print()

# Check state_modifying field
read_only = [t for t in tools if not t.get('state_modifying', False)]
state_mod = [t for t in tools if t.get('state_modifying', False)]

print(f'📖 Read-only tools: {len(read_only)}')
for t in read_only:
    print(f'   - {t[\"name\"]}')
print()

print(f'🔒 State-modifying tools: {len(state_mod)}')
for t in state_mod:
    print(f'   - {t[\"name\"]}')
print()

# Verify register_model exists
if any(t['name'] == 'register_model' for t in tools):
    print('✅ register_model tool found')
else:
    print('❌ register_model tool NOT found')
    exit(1)
"

echo ""

# Test 2: MCP Server register_model Endpoint
echo "Test 2: MCP Server register_model Endpoint"
echo "-------------------------------------------"
oc exec -n agentic-ops deployment/agentic-orchestrator -- python -c "
import requests, json

# Test register_model with valid run
resp = requests.post(
    'http://mcp-mlflow-server.agentic-ops.svc.cluster.local:8080/tools/register_model',
    params={'run_id': 'run-001-a', 'model_name': 'test-model-v1'}
)

if resp.ok:
    result = resp.json()
    print(f'✅ Status: {result[\"status\"]}')
    print(f'✅ Model: {result[\"model_name\"]} v{result[\"version\"]}')
    print(f'✅ Message: {result[\"message\"]}')
else:
    print(f'❌ Error: {resp.status_code} - {resp.text}')
    exit(1)
"

echo ""

# Test 3: Audit Service Health Check
echo "Test 3: Audit Service Health Check"
echo "-----------------------------------"
oc exec -n agentic-ops deployment/agentic-orchestrator -- python -c "
import requests

resp = requests.get('http://audit-service.agentic-ops.svc.cluster.local:8090/health')

if resp.ok:
    health = resp.json()
    print(f'✅ Status: {health[\"status\"]}')
    print(f'✅ Service: {health[\"service\"]}')
    print(f'✅ Database: {health[\"database\"]}')
else:
    print(f'❌ Health check failed: {resp.status_code}')
    exit(1)
"

echo ""

# Test 4: Create Pending Approval
echo "Test 4: Create Pending Approval"
echo "--------------------------------"
oc exec -n agentic-ops deployment/agentic-orchestrator -- python -c "
import requests, json

# Create pending approval
create_resp = requests.post(
    'http://audit-service.agentic-ops.svc.cluster.local:8090/audit/pending',
    json={
        'session_id': 'test-session-001',
        'user_identity': 'demo-operator',
        'tool_name': 'register_model',
        'tool_arguments': {'run_id': 'run-001-a', 'model_name': 'test-model-v1'}
    }
)

if create_resp.ok:
    approval = create_resp.json()
    approval_id = approval['id']
    print(f'✅ Approval created: ID={approval_id}')
    print(f'✅ Tool: {approval[\"tool_name\"]}')
    print(f'✅ Status: {approval[\"approval_status\"]}')

    # Store ID for next test
    with open('/tmp/approval_id.txt', 'w') as f:
        f.write(str(approval_id))
else:
    print(f'❌ Failed to create approval: {create_resp.status_code}')
    exit(1)
"

echo ""

# Test 5: List Pending Approvals
echo "Test 5: List Pending Approvals"
echo "-------------------------------"
oc exec -n agentic-ops deployment/agentic-orchestrator -- python -c "
import requests

resp = requests.get('http://audit-service.agentic-ops.svc.cluster.local:8090/audit/pending')

if resp.ok:
    data = resp.json()
    pending_count = len(data['pending'])
    print(f'✅ Pending approvals: {pending_count}')

    if pending_count > 0:
        latest = data['pending'][-1]
        print(f'✅ Latest: ID={latest[\"id\"]}, Tool={latest[\"tool_name\"]}')
else:
    print(f'❌ Failed to list pending: {resp.status_code}')
    exit(1)
"

echo ""

# Test 6: Approve Request
echo "Test 6: Approve Request"
echo "-----------------------"
oc exec -n agentic-ops deployment/agentic-orchestrator -- python -c "
import requests

# Get approval ID
with open('/tmp/approval_id.txt', 'r') as f:
    approval_id = f.read().strip()

# Approve
resp = requests.post(
    f'http://audit-service.agentic-ops.svc.cluster.local:8090/audit/approve/{approval_id}',
    json={'approver_identity': 'demo-operator'}
)

if resp.ok:
    result = resp.json()
    print(f'✅ Approval status: {result[\"status\"]}')
    print(f'✅ Approval ID: {result[\"id\"]}')
else:
    print(f'❌ Failed to approve: {resp.status_code}')
    exit(1)
"

echo ""

# Test 7: Query Audit History
echo "Test 7: Query Audit History"
echo "----------------------------"
oc exec -n agentic-ops deployment/agentic-orchestrator -- python -c "
import requests

resp = requests.get('http://audit-service.agentic-ops.svc.cluster.local:8090/audit/history?limit=5')

if resp.ok:
    data = resp.json()
    history_count = len(data['history'])
    print(f'✅ Audit history records: {history_count}')

    if history_count > 0:
        latest = data['history'][0]
        print(f'✅ Latest: Tool={latest[\"tool_name\"]}, Status={latest[\"approval_status\"]}')
else:
    print(f'❌ Failed to query history: {resp.status_code}')
    exit(1)
"

echo ""

# Test 8: Rejection Flow
echo "Test 8: Rejection Flow"
echo "----------------------"
oc exec -n agentic-ops deployment/agentic-orchestrator -- python -c "
import requests

# Create another approval
create_resp = requests.post(
    'http://audit-service.agentic-ops.svc.cluster.local:8090/audit/pending',
    json={
        'session_id': 'test-session-002',
        'user_identity': 'demo-operator',
        'tool_name': 'register_model',
        'tool_arguments': {'run_id': 'run-001-b', 'model_name': 'test-model-v2'}
    }
)

if not create_resp.ok:
    print(f'❌ Failed to create approval: {create_resp.status_code}')
    exit(1)

approval_id = create_resp.json()['id']
print(f'✅ Created approval ID={approval_id}')

# Reject it
reject_resp = requests.post(
    f'http://audit-service.agentic-ops.svc.cluster.local:8090/audit/reject/{approval_id}',
    json={
        'approver_identity': 'demo-operator',
        'reason': 'Test rejection - not ready for production'
    }
)

if reject_resp.ok:
    result = reject_resp.json()
    print(f'✅ Rejection status: {result[\"status\"]}')
    print(f'✅ Reason: {result[\"reason\"]}')
else:
    print(f'❌ Failed to reject: {reject_resp.status_code}')
    exit(1)
"

echo ""
echo "=========================================="
echo "✅ All Day 1 Tests Passed!"
echo "=========================================="
