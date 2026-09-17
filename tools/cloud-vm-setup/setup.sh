#!/usr/bin/env bash
set -euo pipefail

setup_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${1:-}" == "--install-collections" ]]; then
  command -v ansible-galaxy >/dev/null 2>&1 || {
    echo "ansible-galaxy is required to install Ansible collections." >&2
    exit 2
  }
  ansible-galaxy collection install -r "$setup_dir/ansible/requirements.yml"
  exit 0
fi

if [[ "${1:-}" != "" && "${1:-}" != "--check" ]]; then
  echo "Usage: $0 [--check|--install-collections]" >&2
  exit 2
fi

env_file="${VLA_VM_CONFIG:-$setup_dir/.env}"

if [[ ! -f "$env_file" ]]; then
  echo "Missing $env_file. Copy .env.example to .env and fill in the VM values." >&2
  exit 2
fi

# shellcheck disable=SC1090
source "$env_file"

required=(VLA_VM_IP VLA_VM_SSH_USER VLA_VM_SSH_KEY VLA_GPU_MODEL VLA_ALLOWED_SOURCE_CIDR)
for name in "${required[@]}"; do
  value="${!name:-}"
  if [[ -z "$value" || "$value" == *"<"* ]]; then
    echo "Missing or placeholder value: $name" >&2
    exit 2
  fi
done

command -v ansible-playbook >/dev/null 2>&1 || {
  echo "ansible-playbook is required. Install Ansible before running this setup." >&2
  exit 2
}

if [[ ! -r "$VLA_VM_SSH_KEY" ]]; then
  echo "SSH key is not readable: $VLA_VM_SSH_KEY" >&2
  exit 2
fi

build_source_mode="${VLA_BUILD_SOURCE_MODE:-git}"
if [[ "$build_source_mode" != "git" && "$build_source_mode" != "working-tree" ]]; then
  echo "VLA_BUILD_SOURCE_MODE must be git or working-tree." >&2
  exit 2
fi

check_mode=
if [[ "${1:-}" == "--check" ]]; then
  check_mode=--check
fi

if [[ "$build_source_mode" == "working-tree" && -z "$check_mode" && "${VLA_BUILD_IMAGE:-false}" == "true" ]]; then
  command -v rsync >/dev/null 2>&1 || {
    echo "rsync is required for VLA_BUILD_SOURCE_MODE=working-tree." >&2
    exit 2
  }
  repo_root="$(cd -- "$setup_dir/../.." && pwd)"
  rsync -az --delete \
    --exclude '.git/' \
    --exclude '.env' \
    --exclude '.env.*' \
    --exclude '*.kubeconfig' \
    -e "ssh -i $VLA_VM_SSH_KEY -p ${VLA_VM_SSH_PORT:-22} -o BatchMode=yes -o StrictHostKeyChecking=accept-new" \
    --rsync-path="sudo -n rsync" \
    "$repo_root/" \
    "${VLA_VM_SSH_USER}@${VLA_VM_IP}:/var/lib/vla-serving/source/"
fi

ansible-playbook \
  -i "${VLA_VM_IP}," \
  --limit all \
  --private-key "$VLA_VM_SSH_KEY" \
  -e "ansible_user=$VLA_VM_SSH_USER" \
  -e "ansible_port=${VLA_VM_SSH_PORT:-22}" \
  -e "vla_vm_ip=$VLA_VM_IP" \
  -e "cloud_vla_port=${VLA_PORT:-8000}" \
  -e "cloud_vla_mode=${VLA_MODE:-mock}" \
  -e "cloud_vla_base_flavor=${VLA_BASE_FLAVOR:-slim}" \
  -e "cloud_container_image=${VLA_CONTAINER_IMAGE:-localhost/openvla-server:slim}" \
  -e "cloud_model_weights=${VLA_MODEL_WEIGHTS:-openvla/openvla-7b}" \
  -e "cloud_model_cache=${VLA_MODEL_CACHE:-/var/cache/vla-models}" \
  -e "cloud_allowed_source_cidr=$VLA_ALLOWED_SOURCE_CIDR" \
  -e "cloud_git_repo_url=${VLA_GIT_REPO_URL:-https://github.com/rhkp/industrial-ai-showcase.git}" \
  -e "cloud_git_repo_ref=${VLA_GIT_REPO_REF:-main}" \
  -e "cloud_build_source_mode=$build_source_mode" \
  -e "cloud_build_image=${VLA_BUILD_IMAGE:-false}" \
  -e "cloud_force_image_build=${VLA_FORCE_IMAGE_BUILD:-false}" \
  -e "cloud_hf_token=${VLA_HF_TOKEN:-}" \
  -e "cloud_install_nvidia_driver=${VLA_INSTALL_NVIDIA_DRIVER:-true}" \
  -e "cloud_reboot_after_driver=${VLA_REBOOT_AFTER_DRIVER:-true}" \
  $check_mode \
  "$setup_dir/ansible/site.yml"
