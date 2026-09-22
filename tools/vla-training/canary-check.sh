#!/usr/bin/env bash
set -euo pipefail

# Temporary fork-side validation of the original openvla-server contracts.

namespace="${VLA_CANARY_NAMESPACE:-robot-edge}"
canary_name="${VLA_CANARY_NAME:-openvla-smoke-canary}"
artifact_uri="${VLA_CANARY_ARTIFACT_URI:-}"
local_port="${VLA_CANARY_LOCAL_PORT:-18000}"
mode="${VLA_CANARY_MODE:-groot}"
model_cache_dir="${VLA_CANARY_MODEL_CACHE_DIR:-/models}"
canary_image="${VLA_CANARY_IMAGE:-}"
use_live_image="${VLA_CANARY_USE_LIVE_IMAGE:-false}"
keep=false

usage() {
  cat <<'EOF'
Usage: tools/vla-training/canary-check.sh --artifact-uri s3://bucket/prefix [--mode groot|onnx] [--keep]

The canary validates the original GR00T serving contract by default. Use
--mode onnx only for the optional legacy ONNX adapter diagnostic.
Resources are deleted automatically unless --keep is used. Optional
environment variables: VLA_OC_CONTEXT, VLA_CANARY_NAMESPACE,
VLA_CANARY_NAME, VLA_CANARY_LOCAL_PORT, VLA_CANARY_MODE, and
VLA_CANARY_MODEL_CACHE_DIR, and VLA_CANARY_IMAGE. The canary requires an
explicit fork-built image. Set VLA_CANARY_USE_LIVE_IMAGE=true only when
intentionally testing the currently deployed image.
EOF
}

while (($# > 0)); do
  case "$1" in
    --artifact-uri)
      [[ $# -ge 2 ]] || { echo "Missing --artifact-uri value" >&2; exit 2; }
      artifact_uri="$2"
      shift 2
      ;;
    --mode)
      [[ $# -ge 2 ]] || { echo "Missing --mode value" >&2; exit 2; }
      mode="$2"
      shift 2
      ;;
    --keep) keep=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ "$mode" == "groot" || "$mode" == "onnx" ]] || {
  echo "Mode must be groot or onnx: $mode" >&2
  exit 2
}

if [[ -z "$artifact_uri" || ! "$artifact_uri" =~ ^s3://[A-Za-z0-9._-]+/[A-Za-z0-9._/-]+$ ]]; then
  echo "A valid --artifact-uri such as s3://vla-training/vla-finetune-smoke-20260921/model is required." >&2
  exit 2
fi

oc_args=()
[[ -n "${VLA_OC_CONTEXT:-}" ]] && oc_args+=(--context "$VLA_OC_CONTEXT")
oc_cmd() { oc "${oc_args[@]}" "$@"; }

if ! oc_cmd whoami >/dev/null 2>&1; then
  echo "BLOCKED: oc is not authenticated to the target cluster." >&2
  exit 2
fi

live_replicas="$(oc_cmd -n "$namespace" get deployment/openvla-server -o jsonpath='{.spec.replicas}')"
if [[ "$live_replicas" != "0" ]]; then
  echo "BLOCKED: $namespace/openvla-server has replicas=$live_replicas." >&2
  echo "The live serving deployment must remain stopped during this isolated check." >&2
  exit 2
fi

for resource in secret/storage-config secret/hf-token pvc/model-cache; do
  oc_cmd -n "$namespace" get "$resource" >/dev/null 2>&1 || {
    echo "BLOCKED: $namespace/$resource is missing." >&2
    exit 2
  }
done

if oc_cmd -n "$namespace" get deployment/"$canary_name" >/dev/null 2>&1 ||
   oc_cmd -n "$namespace" get service/"$canary_name" >/dev/null 2>&1; then
  echo "BLOCKED: $namespace/$canary_name already exists; refusing to overwrite it." >&2
  exit 2
fi

if [[ -z "$canary_image" ]]; then
  if [[ "$use_live_image" == true ]]; then
    canary_image="$(oc_cmd -n "$namespace" get deployment/openvla-server -o jsonpath='{.spec.template.spec.containers[?(@.name=="openvla-server")].image}')"
    [[ -n "$canary_image" ]] || { echo "BLOCKED: live openvla-server image could not be resolved." >&2; exit 2; }
    echo "WARNING: using the live image by explicit request; repository changes are not being tested."
  else
    echo "BLOCKED: VLA_CANARY_IMAGE is required; provide the fork-built serving image." >&2
    echo "Set VLA_CANARY_USE_LIVE_IMAGE=true only for an intentional upstream/runtime baseline check." >&2
    exit 2
  fi
fi

port_log="$(mktemp -t vla-canary-port-forward.XXXXXX)"
port_forward_pid=""
cleanup() {
  [[ -n "$port_forward_pid" ]] && kill "$port_forward_pid" 2>/dev/null || true
  rm -f "$port_log"
  if [[ "$keep" == true ]]; then
    echo "Keeping canary resources: $namespace/$canary_name"
  else
    oc_cmd -n "$namespace" delete deployment/"$canary_name" service/"$canary_name" \
      --ignore-not-found=true >/dev/null 2>&1 || true
    echo "Removed temporary canary resources."
  fi
}
trap cleanup EXIT

oc_cmd apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: $canary_name
  namespace: $namespace
  labels: {app: $canary_name, component: vla-canary}
spec:
  replicas: 1
  strategy: {type: Recreate}
  selector: {matchLabels: {app: $canary_name}}
  template:
    metadata: {labels: {app: $canary_name, component: vla-canary}}
    spec:
      nodeSelector: {nvidia.com/gpu.product: NVIDIA-L40S}
      tolerations:
      - {key: nvidia.com/gpu, operator: Exists, effect: NoSchedule}
      containers:
      - name: openvla-server
        image: $canary_image
        imagePullPolicy: IfNotPresent
        env:
        - {name: SERVICE_NAME, value: $canary_name}
        - {name: VLA_MODE, value: "$mode"}
        - {name: OPENVLA_WEIGHTS, value: $artifact_uri}
        - {name: GROOT_MODEL_PATH, value: $artifact_uri}
        - {name: GROOT_EMBODIMENT_TAG, value: "NEW_EMBODIMENT"}
        - {name: GROOT_VIDEO_KEY, value: "rs_view"}
        - {name: PORT, value: "8000"}
        - {name: OPENVLA_DEVICE, value: "cuda"}
        - {name: S3_ENDPOINT, value: "http://minio.mlflow.svc:9000"}
        - {name: MODEL_CACHE_DIR, value: "$model_cache_dir"}
        - {name: HF_HOME, value: "/tmp/hf_cache"}
        - name: AWS_ACCESS_KEY_ID
          valueFrom: {secretKeyRef: {name: storage-config, key: AWS_ACCESS_KEY_ID}}
        - name: AWS_SECRET_ACCESS_KEY
          valueFrom: {secretKeyRef: {name: storage-config, key: AWS_SECRET_ACCESS_KEY}}
        - name: HF_TOKEN
          valueFrom: {secretKeyRef: {name: hf-token, key: token}}
        ports: [{name: http, containerPort: 8000}]
        resources:
          requests: {cpu: "2", memory: 8Gi, nvidia.com/gpu: "1"}
          limits: {cpu: "4", memory: 16Gi, nvidia.com/gpu: "1"}
        volumeMounts: [{name: model-cache, mountPath: /models}]
        readinessProbe:
          httpGet: {path: /readyz, port: 8000}
          initialDelaySeconds: 10
          periodSeconds: 10
      volumes:
      - name: model-cache
        persistentVolumeClaim: {claimName: model-cache}
---
apiVersion: v1
kind: Service
metadata:
  name: $canary_name
  namespace: $namespace
  labels: {app: $canary_name, component: vla-canary}
spec:
  selector: {app: $canary_name}
  ports: [{name: http, port: 8000, targetPort: 8000}]
EOF

oc_cmd -n "$namespace" rollout status deployment/"$canary_name" --timeout=10m
canary_pod="$(oc_cmd -n "$namespace" get pod -l component=vla-canary \
  -o jsonpath='{.items[0].metadata.name}')"
[[ -n "$canary_pod" ]] || { echo "FAIL: ready canary pod could not be resolved." >&2; exit 1; }
oc_cmd -n "$namespace" port-forward pod/"$canary_pod" "${local_port}:8000" >"$port_log" 2>&1 &
port_forward_pid=$!

ready=false
for _ in {1..30}; do
  if curl -fsS "http://127.0.0.1:${local_port}/healthz" >/dev/null 2>&1; then
    ready=true
    break
  fi
  sleep 2
done
if [[ "$ready" != true ]]; then
  echo "FAIL: canary port-forward did not become reachable." >&2
  sed -n '1,80p' "$port_log" >&2 || true
  exit 1
fi

health="$(curl -fsS "http://127.0.0.1:${local_port}/healthz")"
ready_response="$(curl -fsS "http://127.0.0.1:${local_port}/readyz")"
[[ "$ready_response" == *"\"vla_mode\":\"${mode}\""* ]] || {
  echo "FAIL: readiness did not report VLA_MODE=${mode}: $ready_response" >&2
  exit 1
}

image_b64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
act_response="$(curl -fsS -X POST "http://127.0.0.1:${local_port}/act" \
  -H 'Content-Type: application/json' \
  -d "{\"image\":\"${image_b64}\",\"instruction\":\"pick up the pallet\",\"trace_id\":\"vla-smoke-canary\"}")"

echo "PASS: original openvla-server ${mode} canary responded"
echo "Health: $health"
echo "Ready: $ready_response"
echo "Act: $act_response"
