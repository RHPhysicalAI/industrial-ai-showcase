# Preflight checker

## Environment terminology

The checker uses four supported scopes:

- `local` — developer workstation
- `cloud-vm` — separate Ubuntu/NVIDIA VM running the VLA service
- `companion` — Companion SNO OpenShift cluster
- `hub` — primary OSD/OpenShift cluster

“SNO” describes the Companion topology; it is not a second name for the Hub.

The supported deployment path is a hosted SNO from `demo.redhat.com` plus a
separate cloud NVIDIA VM for VLA serving. The earlier Fedora/bare-metal,
libvirt/KVM, and host-native ROCm implementation is not supported by this
checker and is reported as skipped when explicitly selected.

Hosted-SNO setup values and baseline capture live in
`tools/demo-redhat-sno/README.md`.

Read-only prerequisite checks for the Industrial AI Showcase. This is the first implementation of the prerequisite roadmap in `roadmaps/prereq.md`.

## Why this is a new tool

`tools/companion-install/capture-baseline.sh` remains useful for capturing detailed companion state, but it is not a deployment gate. It is companion-specific, report-only, and does not provide stable check IDs, readiness profiles, actionable remediation, or machine-readable status.

The preflight checker is intentionally separate so the baseline capture script can keep its existing purpose while this tool grows into a profile-aware readiness contract.

## Usage

Run from the repository root:

```bash
python3 tools/preflight/check.py --explain
```

The default profile is `basic-infra`, which validates foundational infrastructure.
Use `--profile demo-workload` for the first warehouse demonstration,
`--profile factory` for Factory B, or `--profile agentic` for agentic operations.

Target one scope:

```bash
python3 tools/preflight/check.py --scope local
python3 tools/preflight/check.py --scope hub --hub-kubeconfig "$KUBECONFIG"
python3 tools/preflight/check.py --scope companion \
  --companion-kubeconfig "$HOME/.kube/companion.kubeconfig"
python3 tools/preflight/check.py --scope cloud-vm \
  --cloud-vm-host "$VLA_VM_IP" \
  --cloud-vm-user "$VLA_VM_SSH_USER" \
  --cloud-vm-key "$VLA_VM_SSH_KEY" \
  --cloud-vm-gpu-model "$VLA_GPU_MODEL"
```

The cloud VM scope checks SSH reachability, Ubuntu, Podman, NVIDIA driver and
GPU visibility, NVIDIA CDI, the `openvla-server` systemd service, `/healthz`,
`/readyz`, and the reported VLA mode. It never prints the SSH key contents or
secret values.

When using the repository's ignored cloud VM configuration, source it first:

```bash
set -a
source tools/cloud-vm-setup/.env
set +a
python3 tools/preflight/check.py --scope cloud-vm
```

For a hosted demo SNO:

```bash
python3 tools/preflight/check.py --scope companion \
  --companion-kubeconfig "$HOME/.kube/demo-sno.kubeconfig"
```

Do not run the old Fedora/bare-metal path for the hosted deployment. The
hosted SNO has provider-specific API/console endpoints, storage, image-pull
egress, ACM eligibility, and network reachability to the Hub and cloud VLA VM.
Use the Companion kubeconfig rather than assuming `companion.lab.local` or a
static private IP.

For a complete supported run from the developer workstation:

```bash
python3 tools/preflight/check.py \
  --profile demo-workload \
  --scope all \
  --companion-kubeconfig "$HOME/.kube/companion.kubeconfig" \
  --explain
```

The old commands `--scope fedora` and `--scope host` are accepted only to
explain that the Fedora/bare-metal implementation is unsupported; they do not
run libvirt, ROCm, or host-native VLA checks.

Write a machine-readable report:

```bash
python3 tools/preflight/check.py \
  --profile demo-workload \
  --format json \
  --output preflight.json
```

Human-readable output is grouped into `FAILING`, `WARNINGS`, `PASSING`, and
`OTHER` sections. Terminal output uses icons and colors when stdout is an
interactive terminal. Control this explicitly when needed:

```bash
python3 tools/preflight/check.py --color always
python3 tools/preflight/check.py --color never
```

Use `--color always` when output is being viewed through a log pane, pipe, or
captured terminal that is not detected as interactive. JSON output is never
colorized.

The checker is read-only. It does not install operators, apply manifests, mutate secrets, sync Argo applications, or modify VMs.

## Exit codes

- `0` — no blocking failures and no warnings.
- `1` — warnings exist, but no blocking failures.
- `2` — one or more blocking checks failed.
- `3` — checker/configuration error.

## V1 coverage

The readiness profiles build on the common platform checks:

- `basic-infra` — local/repository and platform connectivity baseline
- `demo-workload` — the warehouse baseline, including MES, Hub/Companion workloads, ACM registration, and cloud VLA VM
- `factory` — the demo workload plus Factory B and the Companion PLC gateway VM
- `agentic` — the demo workload plus agentic-ops services and projected credentials

V1 checks:

- Local commands and repository paths
- GitOps ApplicationSet repository alignment with the checkout's `origin`
- Cloud VLA VM SSH, Ubuntu, Podman, NVIDIA driver/CDI, systemd service, health, readiness, and VLA mode
- Hub and companion OpenShift API access
- ClusterOperator health
- L40S/L4 GPU labels and capacity
- Core GitOps, Kafka, Vault, MLflow, and storage resources, including readiness where the API exposes it; KubeVirt is optional for hosted-SNO `basic-infra`, `demo-workload`, and `agentic` profiles
- Profile-specific Hub and Companion Deployment readiness
- Selected projected secrets
- ACM companion registration
- Cloud VLA mode and optional workstation-originated endpoint check

V1 deliberately does not attempt a real mission, inspect secret values, or install missing prerequisites. Those are later roadmap milestones.
