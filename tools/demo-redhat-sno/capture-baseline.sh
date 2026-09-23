#!/usr/bin/env bash
# Capture a hosted demo.redhat.com SNO baseline.
#
# Usage:
#   cp .env.example .env
#   ${EDITOR:-vi} .env
#   tools/demo-redhat-sno/capture-baseline.sh > baseline-demo-redhat-sno.txt
#
# This script is read-only. It does not install operators, apply manifests,
# register ACM, or change cluster configuration.
set -uo pipefail

setup_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
env_file="${DEMO_SNO_CONFIG:-$setup_dir/.env}"

if [[ -f "$env_file" ]]; then
  # shellcheck disable=SC1090
  source "$env_file"
fi

if [[ -n "${DEMO_SNO_KUBECONFIG:-}" ]]; then
  export KUBECONFIG="$DEMO_SNO_KUBECONFIG"
fi

: "${DEMO_SNO_CONTEXT:?Set DEMO_SNO_CONTEXT in .env}"

oc_run() {
  oc --context="$DEMO_SNO_CONTEXT" "$@" 2>&1 || true
}

section() {
  printf '\n=== %s ===\n' "$*"
}

section "Hosted SNO identity and access"
oc_run whoami
oc_run whoami --show-server
oc_run version
oc_run auth can-i get nodes
oc_run auth can-i create namespaces
oc_run auth can-i create subscriptions.operators.coreos.com -A
oc_run auth can-i create managedclusters.cluster.open-cluster-management.io

section "Cluster version and infrastructure"
oc_run get clusterversion
oc_run get infrastructure cluster -o jsonpath='platform={.status.platform} name={.status.infrastructureName}{"\n"}'
oc_run get network.config cluster -o jsonpath='{.spec}{"\n"}'

section "Node inventory and capacity"
oc_run get nodes -o wide
oc_run get nodes -o json 2>/dev/null | jq -r '.items[] | {name:.metadata.name, capacity:.status.capacity, allocatable:.status.allocatable}' 2>/dev/null || true

section "Cluster operators"
oc_run get clusteroperators

section "Storage"
oc_run get storageclass
oc_run get namespace openshift-storage
oc_run get namespace openshift-cnv

section "Relevant platform capabilities"
oc_run get crd clusterimagepolicies.config.openshift.io
oc_run get crd hyperconverged.hco.kubevirt.io
oc_run get subscriptions.operators.coreos.com -A
oc_run get csv -A
oc_run get catalogsource -n openshift-marketplace

section "Existing demo namespaces and workloads"
oc_run get namespace warehouse-edge
oc_run get namespace robot-edge
oc_run get namespace factory-floor
oc_run get pods -A
oc_run get routes -A

section "Hosted SNO handoff values"
printf 'DEMO_SNO_NAME=%s\n' "${DEMO_SNO_NAME:-<unset>}"
printf 'DEMO_SNO_API_URL=%s\n' "${DEMO_SNO_API_URL:-<unset>}"
printf 'DEMO_SNO_CONSOLE_URL=%s\n' "${DEMO_SNO_CONSOLE_URL:-<unset>}"
printf 'DEMO_SNO_INGRESS_DOMAIN=%s\n' "${DEMO_SNO_INGRESS_DOMAIN:-<unset>}"
printf 'DEMO_SNO_EXPIRES_AT=%s\n' "${DEMO_SNO_EXPIRES_AT:-<unset>}"
printf 'HUB_KAFKA_ROUTE=%s\n' "${HUB_KAFKA_ROUTE:-<unset>}"
printf 'VLA_VM_IP=%s\n' "${VLA_VM_IP:-<unset>}"
printf 'VLA_VM_PORT=%s\n' "${VLA_VM_PORT:-<unset>}"
printf 'VLA_VM_SSH_HOST=%s\n' "${VLA_VM_SSH_HOST:-<unset>}"
printf 'VLA_VM_SSH_USER=%s\n' "${VLA_VM_SSH_USER:-<unset>}"
printf 'VLA_VM_OS=%s\n' "${VLA_VM_OS:-<unset>}"
printf 'VLA_GPU_VENDOR=%s\n' "${VLA_GPU_VENDOR:-<unset>}"
printf 'VLA_GPU_MODEL=%s\n' "${VLA_GPU_MODEL:-<unset>}"
printf 'VLA_MODE=%s\n' "${VLA_MODE:-<unset>}"
printf 'VLA_ENDPOINT_URL=%s\n' "${VLA_ENDPOINT_URL:-<unset>}"
printf 'GIT_REPO_URL=%s\n' "${GIT_REPO_URL:-<unset>}"
printf 'GIT_REPO_REF=%s\n' "${GIT_REPO_REF:-<unset>}"

section "DONE"
