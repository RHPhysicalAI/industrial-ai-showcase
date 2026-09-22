#!/usr/bin/env bash
set -euo pipefail

# Temporary fork-side validation of the original openvla-server contracts.

namespace="${VLA_CANARY_NAMESPACE:-robot-edge}"
canary_name="${VLA_CANARY_NAME:-openvla-smoke-canary}"
artifact_uri="${VLA_CANARY_ARTIFACT_URI:-}"
local_port="${VLA_CANARY_LOCAL_PORT:-18000}"
mode="${VLA_CANARY_MODE:-groot}"
model_cache_dir="${VLA_CANARY_MODEL_CACHE_DIR:-/models}"
embodiment_tag="${VLA_CANARY_EMBODIMENT_TAG:-NEW_EMBODIMENT}"
video_key="${VLA_CANARY_VIDEO_KEY:-rs_view}"
inference_timeout="${VLA_CANARY_INFERENCE_TIMEOUT:-300}"
canary_image="${VLA_CANARY_IMAGE:-}"
use_live_image="${VLA_CANARY_USE_LIVE_IMAGE:-false}"
allow_tag_image="${VLA_CANARY_ALLOW_TAG_IMAGE:-false}"
keep=false

usage() {
  cat <<'EOF'
Usage: tools/vla-training/canary-check.sh --artifact-uri s3://bucket/prefix [--mode groot|onnx] [--keep]

The canary validates the original GR00T serving contract by default. Use
--mode onnx only for the optional legacy ONNX adapter diagnostic.
Resources are deleted automatically unless --keep is used. Optional
environment variables: VLA_OC_CONTEXT, VLA_CANARY_NAMESPACE,
VLA_CANARY_NAME, VLA_CANARY_LOCAL_PORT, VLA_CANARY_MODE, and
VLA_CANARY_MODEL_CACHE_DIR, VLA_CANARY_EMBODIMENT_TAG,
VLA_CANARY_VIDEO_KEY, VLA_CANARY_INFERENCE_TIMEOUT, VLA_CANARY_IMAGE, and
VLA_CANARY_ALLOW_TAG_IMAGE.
The canary requires an explicit fork-built image. Set
VLA_CANARY_USE_LIVE_IMAGE=true only when intentionally testing the currently
deployed image. Image references must be immutable digests unless
VLA_CANARY_ALLOW_TAG_IMAGE=true is explicitly set for a controlled diagnostic.
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

if [[ "$mode" == "groot" && ! "$artifact_uri" =~ /model/?$ ]]; then
  echo "BLOCKED: GR00T canary requires the native .../model artifact, not .../onnx or .../checkpoint." >&2
  echo "Use the versioned serving URI ending in /model." >&2
  exit 2
fi

oc_args=()
[[ -n "${VLA_OC_CONTEXT:-}" ]] && oc_args+=(--context "$VLA_OC_CONTEXT")
oc_cmd() { oc "${oc_args[@]}" "$@"; }

if ! oc_cmd whoami >/dev/null 2>&1; then
  echo "BLOCKED: oc is not authenticated to the target cluster." >&2
  exit 2
fi

if ! live_replicas="$(oc_cmd -n "$namespace" get deployment/openvla-server -o jsonpath='{.spec.replicas}')"; then
  echo "BLOCKED: $namespace/openvla-server is missing; refusing to infer the live-demo state." >&2
  exit 2
fi
if [[ "$live_replicas" != "0" ]]; then
  echo "BLOCKED: $namespace/openvla-server has replicas=$live_replicas." >&2
  echo "The live serving deployment must remain stopped during this isolated check." >&2
  exit 2
fi

if ! gpu_nodes="$(oc_cmd get nodes -l nvidia.com/gpu.product=NVIDIA-L40S --no-headers 2>/dev/null | awk 'NF {count++} END {print count+0}')"; then
  echo "BLOCKED: unable to inspect the NVIDIA-L40S node pool." >&2
  exit 2
fi
if [[ "$gpu_nodes" -lt 1 ]]; then
  echo "BLOCKED: no NVIDIA-L40S node is currently registered for the canary." >&2
  echo "Do not consume a GPU run until the intended Hub GPU pool is available." >&2
  exit 2
fi

for resource in secret/storage-config secret/hf-token pvc/model-cache; do
  oc_cmd -n "$namespace" get "$resource" >/dev/null 2>&1 || {
    echo "BLOCKED: $namespace/$resource is missing." >&2
    exit 2
  }
done

if [[ "$mode" == "groot" && -z "$(oc_cmd -n "$namespace" get secret/hf-token -o jsonpath='{.data.token}')" ]]; then
  echo "BLOCKED: $namespace/secret/hf-token has no non-empty token key." >&2
  echo "Provide the approved Hugging Face credential without printing it." >&2
  exit 2
fi
for storage_key in AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY; do
  if [[ -z "$(oc_cmd -n "$namespace" get secret/storage-config -o jsonpath="{.data.${storage_key}}")" ]]; then
    echo "BLOCKED: $namespace/secret/storage-config has no non-empty ${storage_key} key." >&2
    exit 2
  fi
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

if [[ "$canary_image" != *@sha256:* && "$allow_tag_image" != true ]]; then
  echo "BLOCKED: VLA_CANARY_IMAGE must be an immutable @sha256 image digest." >&2
  echo "Resolve the fork ImageStream tag to its digest before running the canary." >&2
  echo "Set VLA_CANARY_ALLOW_TAG_IMAGE=true only for an intentional diagnostic." >&2
  exit 2
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

init_container_yaml=""
if [[ "$mode" == "groot" ]]; then
  init_container_yaml="$(cat <<'EOF'
      initContainers:
      - name: hf-access-check
        image: curlimages/curl:8.12.1
        imagePullPolicy: IfNotPresent
        command: ["/bin/sh", "-ec"]
        args:
        - |
          status="$(curl -sS --connect-timeout 10 --max-time 30 \
            -o /dev/null -w '%{http_code}' \
            -H "Authorization: Bearer ${HF_TOKEN}" \
            https://huggingface.co/api/models/nvidia/Cosmos-Reason2-2B)"
          if [ "$status" = 200 ]; then exit 0; fi
          if [ "$status" = 401 ]; then
            echo "Hugging Face token authentication failed (HTTP 401)." >&2
            exit 1
          fi
          if [ "$status" = 403 ]; then
            echo "Hugging Face account has not accepted the gated model terms (HTTP 403)." >&2
            exit 1
          fi
          echo "Hugging Face model access preflight failed (HTTP $status)." >&2
          exit 1
        env:
        - name: HF_TOKEN
          valueFrom: {secretKeyRef: {name: hf-token, key: token}}
EOF
)"
fi

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
$init_container_yaml
      containers:
      - name: openvla-server
        image: $canary_image
        imagePullPolicy: IfNotPresent
        env:
        - {name: SERVICE_NAME, value: $canary_name}
        - {name: VLA_MODE, value: "$mode"}
        - {name: OPENVLA_WEIGHTS, value: $artifact_uri}
        - {name: GROOT_MODEL_PATH, value: $artifact_uri}
        - {name: GROOT_EMBODIMENT_TAG, value: "$embodiment_tag"}
        - {name: GROOT_VIDEO_KEY, value: "$video_key"}
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
  if curl -fsS "http://localhost:${local_port}/healthz" >/dev/null 2>&1; then
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

health="$(curl -fsS --max-time 30 "http://localhost:${local_port}/healthz")"
ready_response="$(curl -fsS --max-time 30 "http://localhost:${local_port}/readyz")"
[[ "$ready_response" == *"\"vla_mode\":\"${mode}\""* ]] || {
  echo "FAIL: readiness did not report VLA_MODE=${mode}: $ready_response" >&2
  exit 1
}

image_b64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
act_response="$(curl -fsS --max-time "$inference_timeout" -X POST "http://localhost:${local_port}/act" \
  -H 'Content-Type: application/json' \
  -d "{\"image\":\"${image_b64}\",\"instruction\":\"pick up the pallet\",\"trace_id\":\"vla-smoke-canary\"}")"

if ! printf '%s' "$act_response" | python3 -c '
import json
import math
import sys

response = json.load(sys.stdin)
action = response.get("action")
if not isinstance(action, list) or len(action) != 7:
    raise SystemExit(f"expected exactly 7 action values, got {len(action) if isinstance(action, list) else type(action).__name__}")
if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in action):
    raise SystemExit("action contains a non-finite or non-numeric value")
if not response.get("model_version") or response.get("trace_id") != "vla-smoke-canary":
    raise SystemExit("response metadata is incomplete or trace_id was not preserved")
'; then
  echo "FAIL: /act returned an invalid legacy response contract: $act_response" >&2
  exit 1
fi

echo "PASS: original openvla-server ${mode} canary responded"
echo "Health: $health"
echo "Ready: $ready_response"
echo "Act: $act_response"
