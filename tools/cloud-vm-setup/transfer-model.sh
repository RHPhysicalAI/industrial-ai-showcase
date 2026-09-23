#!/usr/bin/env bash
set -euo pipefail

# Transfer a versioned native GR00T artifact from Hub MinIO to the cloud VM.
# MinIO is ClusterIP-only, so the transfer is performed through oc exec.
# Multipart objects are downloaded one part per oc exec session because long
# binary oc exec streams can truncate without returning a useful error.

setup_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$setup_dir/../.." && pwd)"

usage() {
  cat <<'EOF'
Usage: tools/cloud-vm-setup/transfer-model.sh --artifact-uri s3://bucket/prefix/model

Required local ignored configuration:
  tools/demo-redhat-sno/.env   HUB_CONTEXT
  tools/cloud-vm-setup/.env    VLA_VM_IP, VLA_VM_SSH_USER, VLA_VM_SSH_KEY,
                               VLA_GROOT_MODEL_PATH

The helper stages each object locally, verifies its exact source byte count,
then copies it to the VM with scp. Credentials are read inside the MinIO pod
and are never printed or written to tracked files.
EOF
}

artifact_uri=""
while (($# > 0)); do
  case "$1" in
    --artifact-uri)
      [[ $# -ge 2 ]] || { echo "Missing --artifact-uri value" >&2; exit 2; }
      artifact_uri="$2"
      shift 2
      ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ "$artifact_uri" =~ ^s3://[A-Za-z0-9._-]+/[A-Za-z0-9._/-]+/model/?$ ]] || {
  echo "A native GR00T artifact URI ending in /model is required." >&2
  exit 2
}

# shellcheck disable=SC1091
source "$repo_root/tools/demo-redhat-sno/.env"
# shellcheck disable=SC1091
source "$setup_dir/.env"

: "${HUB_CONTEXT:?HUB_CONTEXT is required in tools/demo-redhat-sno/.env}"
: "${VLA_VM_IP:?VLA_VM_IP is required in tools/cloud-vm-setup/.env}"
: "${VLA_VM_SSH_USER:?VLA_VM_SSH_USER is required in tools/cloud-vm-setup/.env}"
: "${VLA_VM_SSH_KEY:?VLA_VM_SSH_KEY is required in tools/cloud-vm-setup/.env}"
: "${VLA_GROOT_MODEL_PATH:?VLA_GROOT_MODEL_PATH is required in tools/cloud-vm-setup/.env}"

command -v oc >/dev/null 2>&1 || { echo "oc is required." >&2; exit 2; }
command -v jq >/dev/null 2>&1 || { echo "jq is required." >&2; exit 2; }
command -v scp >/dev/null 2>&1 || { echo "scp is required." >&2; exit 2; }

source_path="${artifact_uri#s3://}"
bucket="${source_path%%/*}"
prefix="${source_path#*/}"
minio_target="local/${bucket}/${prefix}"
oc_args=(--context "$HUB_CONTEXT")
oc_cmd() { oc "${oc_args[@]}" "$@"; }

minio_pod="$(oc_cmd -n mlflow get pod -l app.kubernetes.io/name=minio -o jsonpath='{.items[0].metadata.name}')"
[[ -n "$minio_pod" ]] || { echo "No Hub MinIO pod found." >&2; exit 2; }

mc_json() {
  local command="$1"
  oc_cmd -n mlflow exec "$minio_pod" -- sh -ec \
    "mc alias set local http://127.0.0.1:9000 \"\$MINIO_ROOT_USER\" \"\$MINIO_ROOT_PASSWORD\" >/dev/null; $command"
}

ssh_opts=(-o BatchMode=yes -o ConnectTimeout=10 -i "$VLA_VM_SSH_KEY")
ssh_target="$VLA_VM_SSH_USER@$VLA_VM_IP"
remote_tmp_dir="/tmp/vla-model-transfer-$$"
local_tmp_dir="$(mktemp -d /private/tmp/vla-model-transfer.XXXXXX)"
cleanup() { rm -rf "$local_tmp_dir"; }
trap cleanup EXIT

ssh "${ssh_opts[@]}" "$ssh_target" "mkdir -p '$remote_tmp_dir'"

mc_json "mc ls --recursive --json '$minio_target'" \
  | jq -r 'select(.type == "file") | [.key, (.size | tostring)] | @tsv' \
  | while IFS=$'\t' read -r object_key object_size; do
      relative="${object_key#"$prefix/"}"
      [[ "$relative" != "$object_key" ]] || { echo "Unexpected object outside artifact prefix: $object_key" >&2; exit 1; }
      local_file="$local_tmp_dir/$relative"
      mkdir -p "$(dirname "$local_file")"

      etag="$(mc_json "mc stat --json 'local/$object_key'" | jq -r '.etag')"
      parts=1
      if [[ "$etag" =~ -([0-9]+)$ ]]; then
        parts="${BASH_REMATCH[1]}"
      fi

      echo "Staging $relative ($object_size bytes, $parts multipart part(s))"
      : > "$local_file"
      for part in $(seq 1 "$parts"); do
        if ((parts == 1)); then
          mc_json "mc cat 'local/$object_key'" >> "$local_file"
        else
          mc_json "mc cat --part-number $part 'local/$object_key'" >> "$local_file"
        fi
      done

      actual_size="$(stat -f '%z' "$local_file")"
      [[ "$actual_size" == "$object_size" ]] || {
        echo "Integrity check failed for $relative: got $actual_size, expected $object_size" >&2
        exit 1
      }

      remote_file="$VLA_GROOT_MODEL_PATH/$relative"
      remote_parent="${remote_file%/*}"
      remote_upload="$remote_tmp_dir/$(basename "$relative")"
      ssh "${ssh_opts[@]}" "$ssh_target" "sudo mkdir -p '$remote_parent'"
      scp "${ssh_opts[@]}" "$local_file" "$ssh_target:$remote_upload" >/dev/null
      ssh "${ssh_opts[@]}" "$ssh_target" \
        "sudo mv '$remote_upload' '$remote_file'; sudo chown 1500:0 '$remote_file'; test \"\$(sudo stat -c %s '$remote_file')\" = '$object_size'"
    done

ssh "${ssh_opts[@]}" "$ssh_target" "rmdir '$remote_tmp_dir' 2>/dev/null || true"
echo "PASS: transferred and verified $artifact_uri to $VLA_VM_IP:$VLA_GROOT_MODEL_PATH"
