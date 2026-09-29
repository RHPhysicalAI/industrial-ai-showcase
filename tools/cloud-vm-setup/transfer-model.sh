#!/usr/bin/env bash
# Keep shell configuration semantics; all transfer orchestration lives in Python.
set +x
set +v
set -euo pipefail

setup_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$setup_dir/../.." && pwd)"

command -v python3 >/dev/null 2>&1 || { echo "python3 is required." >&2; exit 2; }
for arg in "$@"; do
  case "$arg" in
    -h|--help) exec python3 "$setup_dir/transfer_model.py" "$@" ;;
  esac
done

hub_config="$repo_root/tools/demo-redhat-sno/.env"
vm_config="${VLA_VM_CONFIG:-$setup_dir/.env}"
[[ -r "$hub_config" && -r "$vm_config" ]] || {
  echo "Readable Hub and VM .env configuration files are required (see --help)." >&2
  exit 2
}
# Do not echo configuration output, including when invoked with bash -x.
# shellcheck disable=SC1090
source "$hub_config" >/dev/null 2>&1
# shellcheck disable=SC1090
source "$vm_config" >/dev/null 2>&1
set +x
set +v

export HUB_CONTEXT VLA_VM_IP VLA_VM_SSH_USER VLA_VM_SSH_KEY VLA_GROOT_MODEL_PATH
export VLA_VM_SSH_PORT VLA_S3_CLIENT_IMAGE MLFLOW_S3_ENDPOINT_URL AWS_DEFAULT_REGION
exec python3 "$setup_dir/transfer_model.py" "$@"
