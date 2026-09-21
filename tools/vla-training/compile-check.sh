#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
compiler_python="${VLA_PIPELINE_PYTHON:-python3}"
output_dir="$(mktemp -d -t vla-finetune-pipeline.XXXXXX)"
output_file="${output_dir}/pipeline.yaml"
trap 'rm -f "$output_file"; rmdir "$output_dir" 2>/dev/null || true' EXIT

# The compiler entrypoint imports the package from the repository's src layout.
# Keep this validation wrapper self-contained without requiring an editable install.
export PYTHONPATH="${repo_root}/workloads/vla-training/src${PYTHONPATH:+:${PYTHONPATH}}"

if ! "$compiler_python" -c 'import kfp' >/dev/null 2>&1; then
  echo "BLOCKED: KFP is not available in $compiler_python" >&2
  echo "Create an isolated environment and install the pipeline extras; see tools/vla-training/README.md." >&2
  exit 2
fi

"$compiler_python" \
  "$repo_root/workloads/vla-training/src/vla_training/pipeline.py" \
  "$output_file"

for marker in \
  'name: vla-finetune' \
  'nvidia/GR00T-N1.7-3B' \
  'nvidia/PhysicalAI-Robotics-GR00T-Teleop-G1' \
  'vla-training' \
  'g1-vla-finetune'; do
  if ! grep -Fq "$marker" "$output_file"; then
    echo "FAIL: compiled pipeline is missing expected contract marker: $marker" >&2
    exit 1
  fi
done

echo "PASS: pipeline compiled successfully"
echo "Compiled artifact: $output_file"
echo "Committed artifact: $repo_root/workloads/vla-training/vla_finetune_pipeline.yaml"
echo "Review the temporary artifact before replacing the committed YAML."
