# vla-serving-host

**Role**: OpenVLA-7B serving runtime, **host-native on the companion Fedora 43 node**. Not a KServe InferenceService. Per ADR-026.

**Phase**: 1 (5-min Warehouse Baseline — plan item 10).

## Why host-native and not in-cluster

The companion SNO runs on RHCOS 9.6 (kernel 5.14). The AMD Radeon 8060S iGPU is reachable only from the Fedora 43 host (kernel 6.19.8) via ROCm HIP. The AMD GPU Operator for OpenShift is Instinct-only (MI2xx/MI3xx) and does not cover RDNA/APU hardware. vLLM upstream closed OpenVLA support as "not planned" (`vllm-project/vllm#14739`, 2026-03-30) and vLLM on gfx1151 crashes at startup. Given those three, the serving runtime moves to the host; Mission Dispatcher HTTP-calls it across the bridge network. Full reasoning in ADR-026.

A pod-native KServe custom-predictor path returns in Phase 3 when the Jetson Thor Developer Kit arrives and provides a second, CUDA-native edge target (see `workloads/vla-serving-pod/`).

## Interfaces

- **HTTP server** on the companion Fedora host, bound to a bridge network address reachable from the SNO CNI range.
  - `POST /act` — input: `{image: base64-encoded RGB, instruction: str}`, output: `{action: list[float], model_version: str, trace_id: str}`.
  - `GET /healthz`, `GET /metrics`.

### Action-space boundary

The legacy Mission Dispatcher contract exposes seven numeric values, historically
described as `dx, dy, dz, droll, dpitch, dyaw, dgrasp`. That shape is still
preserved for compatibility.

The trained Teleop-G1 GR00T policy does not natively emit that contract. It
emits a 16-step action chunk with seven named modalities totaling 43 joint
values: `left_leg`, `right_leg`, `waist`, `left_arm`, `left_hand`, `right_arm`,
and `right_hand`. The server now validates those keys and dimensions before
returning the legacy-shaped response, but the current seven-value response is
only a compatibility projection. It is not a validated 43-DOF-to-Cartesian
robot-control mapping and must not be promoted as live robot control until the
downstream mapping is implemented and tested.

## Primary model

OpenVLA-7B in bf16 (per licensing-gates.md — open license, redistributable). Weights fit comfortably in the 102 GiB GTT-addressable memory reported by the ROCm HIP backend. Reference code derives from the OpenVLA project's `deploy.py` wrapped in a minimal FastAPI layer.

## Pluggable alternatives (pre-provisioned for 60-min live-swap beat, Phase 3)

- **SmolVLA-450M** — HuggingFace LeRobot. CPU-capable fallback. 15–30 Hz on this hardware.
- **π0 (openpi)** — Physical Intelligence, 3.3B PaliGemma-based. Remote-websocket serving pattern.
- **GR00T N1.7** — NVIDIA, optional swap-in requiring the customer's own NGC entitlement. Not active by default.

Model selection via `VLA_MODEL` env var; no code change, no rebuild.

## Packaging

- **`ansible/`** — playbook that provisions the Fedora host: installs ROCm prereqs (already present), Python 3.12 venv, systemd unit, firewalld rule for bridge-network access, health-check script.
- **`systemd/`** — the podman-managed systemd unit file. Container image is `quay.io/redhat-physical-ai-reference/vla-serving-host:<sha>`.
- **`src/openvla_server/`** — the FastAPI wrapper around OpenVLA's reference code.

## Not GitOps-reconciled

The host runtime is outside the OpenShift-managed layer and so outside Argo CD's reconciliation loop. It is managed via Ansible + systemd. This is an honest departure from the "GitOps-first" convention in `CLAUDE.md` and is justified per ADR-026 — AMD consumer/APU hardware does not currently have a Kubernetes-native device-plugin path on OpenShift. Argo reconciles the cluster-side components (Mission Dispatcher, Fleet Manager, Kafka); Ansible reconciles the host.

## Local development

```
cd workloads/vla-serving-host
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
# Model weights: pulled on first run via HuggingFace hub; cached at /var/cache/vla-models/.
OPENVLA_WEIGHTS=openvla/openvla-7b python -m openvla_server.main --port 8000
```

## Status

Phase 1 scaffolding only. Depends on host Ansible automation + firewalld/bridge-network configuration.
