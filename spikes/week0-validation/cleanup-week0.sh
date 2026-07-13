#!/bin/bash
# This project was developed with assistance from AI tools.
#
# Cleanup Week 0 validation resources
#
# Usage: bash cleanup-week0.sh

set -euo pipefail

echo "🧹 Cleaning up Week 0 validation resources..."

# Check if logged in
if ! oc whoami &>/dev/null; then
    echo "❌ Not logged in to OpenShift cluster"
    echo "Run: oc login <cluster-url>"
    exit 1
fi

# Check current namespace
CURRENT_NS=$(oc project -q)
echo "📍 Current namespace: $CURRENT_NS"

# List Week 0 resources
echo ""
echo "📋 Week 0 resources in agentic-ops namespace:"
echo "─────────────────────────────────────────────"

# vLLM test pod
if oc get pod vllm-test -n agentic-ops &>/dev/null; then
    echo "✅ Found: vllm-test (Pod)"
else
    echo "⏭️  Not found: vllm-test"
fi

# Postgres
if oc get deployment postgres -n agentic-ops &>/dev/null; then
    echo "✅ Found: postgres (Deployment)"
else
    echo "⏭️  Not found: postgres"
fi

if oc get svc postgres -n agentic-ops &>/dev/null; then
    echo "✅ Found: postgres (Service)"
else
    echo "⏭️  Not found: postgres"
fi

if oc get secret postgres-secret -n agentic-ops &>/dev/null; then
    echo "✅ Found: postgres-secret (Secret)"
else
    echo "⏭️  Not found: postgres-secret"
fi

echo ""
read -p "🗑️  Delete all Week 0 resources? (y/N): " -n 1 -r
echo

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Aborted - no resources deleted"
    exit 0
fi

echo ""
echo "🗑️  Deleting Week 0 resources..."

# Delete vLLM test pod
if oc get pod vllm-test -n agentic-ops &>/dev/null; then
    oc delete pod vllm-test -n agentic-ops
    echo "✅ Deleted: vllm-test (Pod)"
fi

# Delete Postgres
if oc get deployment postgres -n agentic-ops &>/dev/null; then
    oc delete deployment postgres -n agentic-ops
    echo "✅ Deleted: postgres (Deployment)"
fi

if oc get svc postgres -n agentic-ops &>/dev/null; then
    oc delete svc postgres -n agentic-ops
    echo "✅ Deleted: postgres (Service)"
fi

if oc get secret postgres-secret -n agentic-ops &>/dev/null; then
    oc delete secret postgres-secret -n agentic-ops
    echo "✅ Deleted: postgres-secret (Secret)"
fi

echo ""
echo "✅ Week 0 cleanup complete!"
echo ""
echo "📝 Note: This does NOT delete:"
echo "  - hf-token secret (needed for production vLLM)"
echo "  - agentic-ops namespace"
echo "  - Week 0 spike files in spikes/week0-validation/"