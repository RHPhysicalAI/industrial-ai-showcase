#!/usr/bin/env bash
set -euo pipefail

# Isolated KServe validation for the native GR00T artifact. This intentionally
# does not touch the live robot-edge Deployment, AWS VM, Companion SNO, or Argo.

namespace="${VLA_KSERVE_NAMESPACE:-vla-kserve-canary}"
isvc_name="${VLA_KSERVE_NAME:-trained-model-kserve-canary}"
artifact_uri="${VLA_KSERVE_ARTIFACT_URI:-}"
image="${VLA_KSERVE_IMAGE:-}"
local_port="${VLA_KSERVE_LOCAL_PORT:-18080}"
s3_endpoint="${VLA_KSERVE_S3_ENDPOINT:-http://minio.mlflow.svc:9000}"
keep=false

usage() {
  cat <<'EOF'
Usage: tools/vla-training/kserve-canary.sh \
  --artifact-uri s3://bucket/prefix/model \
  --image registry.example/image@sha256:digest [--keep]

The canary creates a temporary namespace and KServe InferenceService, copies
only the existing storage and approved Hugging Face Secret objects into that
namespace, validates the KServe v1 model and predict endpoints, then removes
the namespace unless --keep is supplied.

The live robot-edge/openvla-server must be scaled to zero and a free NVIDIA
L40S GPU must be available. No live workload or Argo application is changed.
EOF
}

while ((${#} > 0)); do
  case "${1}" in
    --artifact-uri)
      [[ ${#} -ge 2 ]] || { echo "Missing --artifact-uri value" >&2; exit 2; }
      artifact_uri="${2}"
      shift 2
      ;;
    --image)
      [[ ${#} -ge 2 ]] || { echo "Missing --image value" >&2; exit 2; }
      image="${2}"
      shift 2
      ;;
    --keep) keep=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: ${1}" >&2; usage >&2; exit 2 ;;
  esac
done

[[ "$artifact_uri" =~ ^s3://[A-Za-z0-9._-]+/[A-Za-z0-9._/-]+/model/?$ ]] || {
  echo "A native GR00T artifact ending in /model is required: $artifact_uri" >&2
  exit 2
}
[[ "$image" == *@sha256:* ]] || {
  echo "An immutable @sha256 image is required: $image" >&2
  exit 2
}

oc_args=()
[[ -n "${VLA_OC_CONTEXT:-}" ]] && oc_args+=(--context "$VLA_OC_CONTEXT")
oc_cmd() { oc "${oc_args[@]}" "$@"; }

oc_cmd whoami >/dev/null 2>&1 || {
  echo "BLOCKED: oc is not authenticated to the target Hub cluster." >&2
  exit 2
}

live_replicas="$(oc_cmd -n robot-edge get deployment/openvla-server -o jsonpath='{.spec.replicas}')"
[[ "$live_replicas" == "0" ]] || {
  echo "BLOCKED: robot-edge/openvla-server has replicas=$live_replicas; refusing to compete with the live path." >&2
  exit 2
}

gpu_nodes="$(oc_cmd get nodes -l nvidia.com/gpu.product=NVIDIA-L40S --no-headers | awk 'NF {count++} END {print count+0}')"
[[ "$gpu_nodes" -gt 0 ]] || {
  echo "BLOCKED: no NVIDIA-L40S node is registered." >&2
  exit 2
}

if oc_cmd get namespace "$namespace" >/dev/null 2>&1; then
  echo "BLOCKED: namespace $namespace already exists; refusing to overwrite it." >&2
  exit 2
fi

cleanup() {
  [[ -n "${port_forward_pid:-}" ]] && kill "$port_forward_pid" 2>/dev/null || true
  rm -f "${port_log:-}"
  if [[ "$keep" == true ]]; then
    echo "Keeping KServe canary namespace: $namespace"
  else
    oc_cmd delete namespace "$namespace" --ignore-not-found=true >/dev/null 2>&1 || true
    echo "Removed isolated KServe canary namespace: $namespace"
  fi
}
trap cleanup EXIT

oc_cmd apply -f - <<EOF
apiVersion: v1
kind: Namespace
metadata:
  name: $namespace
  labels:
    app.kubernetes.io/part-of: vla-training
    showcase.redhat.com/canary: kserve
EOF

# Copy secret metadata and data in-process without printing secret values.
registry_secret="$(oc_cmd -n robot-edge get serviceaccount default -o jsonpath='{.imagePullSecrets[0].name}')"
[[ -n "$registry_secret" ]] || {
  echo "BLOCKED: robot-edge/default has no image-pull Secret." >&2
  exit 2
}

for secret_name in storage-config hf-token-trained-model "$registry_secret"; do
  target_name="$secret_name"
  [[ "$secret_name" == "$registry_secret" ]] && target_name=robot-edge-registry-pull
  oc_cmd -n robot-edge get secret "$secret_name" -o json \
    | jq --arg namespace "$namespace" --arg target_name "$target_name" --arg s3_endpoint "$s3_endpoint" \
      'del(.metadata.creationTimestamp, .metadata.managedFields, .metadata.ownerReferences, .metadata.resourceVersion, .metadata.uid, .metadata.annotations)
       | .metadata.namespace = $namespace
       | .metadata.name = $target_name
       | if .metadata.name == "storage-config" then
           .metadata.annotations = {"serving.kserve.io/s3-endpoint": $s3_endpoint, "serving.kserve.io/s3-usehttps": "0", "serving.kserve.io/s3-verifyssl": "0"}
         else . end' \
    | oc_cmd apply -f - >/dev/null
done
oc_cmd -n "$namespace" patch serviceaccount/default --type merge \
  -p '{"imagePullSecrets":[{"name":"robot-edge-registry-pull"}]}' >/dev/null

oc_cmd apply -f - <<EOF
apiVersion: serving.kserve.io/v1beta1
kind: InferenceService
metadata:
  name: $isvc_name
  namespace: $namespace
  labels:
    app.kubernetes.io/part-of: vla-training
    showcase.redhat.com/canary: kserve
  annotations:
    serving.kserve.io/deploymentMode: RawDeployment
    serving.kserve.io/storageSecretName: storage-config
spec:
  predictor:
    minReplicas: 1
    maxReplicas: 1
    timeout: 600
    nodeSelector:
      nvidia.com/gpu.product: NVIDIA-L40S
    tolerations:
    - key: nvidia.com/gpu
      operator: Exists
      effect: NoSchedule
    containers:
    - name: kserve-container
      image: $image
      imagePullPolicy: IfNotPresent
      command: ["uvicorn"]
      args: ["openvla_server.main:app", "--host", "0.0.0.0", "--port", "8080"]
      env:
      # KServe's custom-predictor storage initializer downloads this URI to
      # /mnt/models before starting the predictor container.
      - name: STORAGE_URI
        value: $artifact_uri
      - name: VLA_MODE
        value: groot
      - name: SERVICE_NAME
        value: $isvc_name
      - name: PORT
        value: "8080"
      - name: GROOT_MODEL_PATH
        value: /mnt/models
      - name: GROOT_EMBODIMENT_TAG
        value: NEW_EMBODIMENT
      - name: GROOT_VIDEO_KEY
        value: rs_view
      - name: HF_HOME
        value: /tmp/hf_cache
      - name: HF_TOKEN
        valueFrom:
          secretKeyRef:
            name: hf-token-trained-model
            key: token
      - name: HUGGINGFACE_HUB_TOKEN
        valueFrom:
          secretKeyRef:
            name: hf-token-trained-model
            key: token
      - name: AWS_ACCESS_KEY_ID
        valueFrom:
          secretKeyRef:
            name: storage-config
            key: AWS_ACCESS_KEY_ID
      - name: AWS_SECRET_ACCESS_KEY
        valueFrom:
          secretKeyRef:
            name: storage-config
            key: AWS_SECRET_ACCESS_KEY
      ports:
      - name: http
        containerPort: 8080
      resources:
        requests:
          cpu: "2"
          memory: 8Gi
          nvidia.com/gpu: "1"
        limits:
          cpu: "4"
          memory: 16Gi
          nvidia.com/gpu: "1"
      readinessProbe:
        httpGet:
          path: /readyz
          port: 8080
        initialDelaySeconds: 30
        periodSeconds: 10
EOF

echo "Waiting for KServe InferenceService/$isvc_name..."
if ! oc_cmd -n "$namespace" wait --for=condition=Ready "inferenceservice/$isvc_name" --timeout=15m; then
  oc_cmd -n "$namespace" get inferenceservice "$isvc_name" -o yaml >&2 || true
  oc_cmd -n "$namespace" get pods -o wide >&2 || true
  oc_cmd -n "$namespace" get events --sort-by=.lastTimestamp | tail -60 >&2 || true
  exit 1
fi

predictor_service="$(oc_cmd -n "$namespace" get service \
  -l "serving.kserve.io/inferenceservice=$isvc_name" \
  -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
if [[ -z "$predictor_service" ]]; then
  predictor_service="$(oc_cmd -n "$namespace" get service "$isvc_name-predictor" \
    -o jsonpath='{.metadata.name}' 2>/dev/null || true)"
fi
[[ -n "$predictor_service" ]] || {
  echo "FAIL: KServe predictor Service was not created." >&2
  exit 1
}
predictor_pod="$(oc_cmd -n "$namespace" get pod \
  -l "serving.kserve.io/inferenceservice=$isvc_name" \
  -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
[[ -n "$predictor_pod" ]] || {
  echo "FAIL: KServe predictor pod was not created." >&2
  exit 1
}

port_log="$(mktemp -t kserve-canary-port-forward.XXXXXX)"
oc_cmd -n "$namespace" port-forward "pod/$predictor_pod" "$local_port:8080" >"$port_log" 2>&1 &
port_forward_pid=$!

for _ in {1..30}; do
  if curl -fsS --connect-timeout 2 --max-time 5 \
      "http://localhost:${local_port}/v1/models/${isvc_name}" >/dev/null 2>&1; then break; fi
  sleep 2
done

if ! model_status="$(curl -fsS --connect-timeout 2 --max-time 30 \
    "http://localhost:${local_port}/v1/models/${isvc_name}")"; then
  echo "FAIL: KServe port-forward did not become reachable." >&2
  cat "$port_log" >&2 || true
  exit 1
fi
[[ "$model_status" == *'"ready":true'* ]] || {
  echo "FAIL: KServe model status was not ready: $model_status" >&2
  exit 1
}

image_b64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
predict_response="$(curl -fsS --max-time 600 -X POST \
  "http://localhost:${local_port}/v1/models/${isvc_name}:predict" \
  -H 'Content-Type: application/json' \
  -d "{\"instances\":[{\"image\":\"${image_b64}\",\"instruction\":\"pick up the pallet\",\"trace_id\":\"kserve-canary\"}]}" )"

if ! printf '%s' "$predict_response" | python3 -c '
import json
import math
import sys

response = json.load(sys.stdin)
predictions = response.get("predictions")
if not isinstance(predictions, list) or len(predictions) != 1:
    raise SystemExit("expected one KServe prediction")
result = predictions[0]
action = result.get("action")
if not isinstance(action, list) or len(action) != 7:
    raise SystemExit("KServe prediction did not preserve the seven-value response contract")
if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in action):
    raise SystemExit("KServe prediction contains a non-finite or non-numeric action")
if result.get("trace_id") != "kserve-canary":
    raise SystemExit("KServe prediction did not preserve trace metadata")
'; then
  echo "FAIL: KServe prediction contract failed: $predict_response" >&2
  exit 1
fi

echo "PASS: isolated KServe InferenceService responded with the trained native GR00T artifact"
echo "Model status: $model_status"
echo "Prediction: $predict_response"
