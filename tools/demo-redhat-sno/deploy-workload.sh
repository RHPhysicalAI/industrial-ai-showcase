#!/usr/bin/env bash
# Deploy the first hosted-SNO workload slice.
#
# This script is intentionally separate from the read-only baseline capture.
# It creates the cross-cluster Kafka CA Secret, then applies the hosted-SNO
# overlay with environment-specific values rendered from the ignored .env.
set -euo pipefail

setup_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$setup_dir/../.." && pwd)"
env_file="${DEMO_SNO_CONFIG:-$setup_dir/.env}"

if [[ ! -f "$env_file" ]]; then
  printf 'Missing configuration: %s\n' "$env_file" >&2
  exit 2
fi

# shellcheck disable=SC1090
source "$env_file"

: "${DEMO_SNO_KUBECONFIG:?Set DEMO_SNO_KUBECONFIG in .env}"
: "${DEMO_SNO_CONTEXT:?Set DEMO_SNO_CONTEXT in .env}"
: "${HUB_CONTEXT:?Set HUB_CONTEXT in .env}"
: "${HUB_KAFKA_ROUTE:?Set HUB_KAFKA_ROUTE in .env}"
: "${VLA_ENDPOINT_URL:?Set VLA_ENDPOINT_URL in .env}"
export HUB_KAFKA_ROUTE VLA_ENDPOINT_URL

overlay_dir="$repo_root/infrastructure/gitops/apps/demo-redhat-sno"
hub_kafka_namespace="${HUB_KAFKA_NAMESPACE:-fleet-ops}"
hub_kafka_ca_secret="${HUB_KAFKA_CA_SECRET:-fleet-cluster-ca-cert}"
companion_namespace="warehouse-edge"
companion_secret="hub-kafka-ca"

export KUBECONFIG="$DEMO_SNO_KUBECONFIG"
oc_sno() {
  oc --context="$DEMO_SNO_CONTEXT" "$@"
}

printf '%s\n' 'Checking hosted SNO access...'
oc_sno whoami >/dev/null
oc_sno get clusterversion version >/dev/null

printf '%s\n' 'Checking Hub Kafka route and CA secret...'
hub_route="$(oc --context="$HUB_CONTEXT" get route fleet-kafka-bootstrap \
  -n "$hub_kafka_namespace" -o jsonpath='{.spec.host}')"
if [[ "$hub_route" != "$HUB_KAFKA_ROUTE" ]]; then
  printf 'HUB_KAFKA_ROUTE does not match the Hub route: %s\n' "$hub_route" >&2
  exit 2
fi
oc --context="$HUB_CONTEXT" get secret "$hub_kafka_ca_secret" \
  -n "$hub_kafka_namespace" >/dev/null

printf '%s\n' 'Applying hosted-SNO workload resources...'
# Kustomize preserves the two deliberate placeholders. Render only those
# values on stdout; no generated environment file is written to the repo.
oc kustomize "$overlay_dir" | python3 -c '
import os
import sys

text = sys.stdin.read()
for name in ("HUB_KAFKA_ROUTE", "VLA_ENDPOINT_URL"):
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"missing required environment variable: {name}")
    text = text.replace("${" + name + "}", value)
sys.stdout.write(text)
' | oc_sno apply -f -

printf '%s\n' 'Creating local runtime configuration in both workload namespaces...'
oc_sno create configmap mission-dispatcher-config -n warehouse-edge \
  --from-literal="kafka.bootstrap.servers=${HUB_KAFKA_ROUTE}:443" \
  --dry-run=client -o yaml | oc_sno apply -f -
oc_sno create configmap mission-dispatcher-config -n robot-edge \
  --from-literal="kafka.bootstrap.servers=${HUB_KAFKA_ROUTE}:443" \
  --from-literal=kafka.security.protocol=SSL \
  --from-literal="vla.endpoint.url=${VLA_ENDPOINT_URL}" \
  --dry-run=client -o yaml | oc_sno apply -f -

printf '%s\n' 'Copying Hub Kafka CA certificate into warehouse-edge...'
ca_file="$(mktemp)"
trap 'rm -f "$ca_file"' EXIT
oc --context="$HUB_CONTEXT" get secret "$hub_kafka_ca_secret" \
  -n "$hub_kafka_namespace" -o jsonpath='{.data.ca\.crt}' |
  python3 -c 'import base64, sys; sys.stdout.buffer.write(base64.b64decode(sys.stdin.read()))' \
  > "$ca_file"
oc_sno create secret generic "$companion_secret" -n "$companion_namespace" \
  --from-file=ca.crt="$ca_file" --dry-run=client -o yaml | oc_sno apply -f -

printf '%s\n' 'Refreshing workloads after the CA/configuration update...'
oc_sno rollout restart deployment/fake-camera -n warehouse-edge
oc_sno rollout restart deployment/mission-dispatcher -n robot-edge

printf '%s\n' 'Hosted-SNO workload resources applied.'
printf '%s\n' 'Next: inspect builds and rollout status with:'
printf '%s\n' '  oc get builds -A'
printf '%s\n' '  oc get pods -n warehouse-edge'
printf '%s\n' '  oc get pods -n robot-edge'
