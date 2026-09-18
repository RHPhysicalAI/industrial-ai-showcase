# Prerequisite Readiness Roadmap

## Terminology

- **Local workstation** — the developer machine running the checker, Git, and OpenShift client commands.
- **Cloud VLA VM** — the separate Ubuntu/NVIDIA VM running the VLA service.
- **Companion SNO** — the hosted/demo Single Node OpenShift cluster supplied through `demo.redhat.com`, representing the factory edge. Short form: **Companion**.
- **Hub** — the primary OpenShift Dedicated (OSD) cluster where the central workloads run. It is not an SNO in the current topology.
- **Supported topology** — Local workstation, Hub, hosted Companion SNO, and separate Cloud VLA VM. Fedora/bare-metal self-managed infrastructure is not the supported deployment path for this checker.

Use `Hub`, `Companion`, `Cloud VLA VM`, and `Local workstation` consistently. Use `SNO` only when describing the Companion's single-node architecture.

## Purpose

Create a safe, profile-aware prerequisite system that tells an operator whether the environment is ready for a given deployment profile, identifies blocking gaps, and provides the exact next action to resolve each gap.

The first target is the `demo-workload` warehouse baseline. The system must understand the local developer workstation, the OpenShift Hub, the hosted Companion SNO, and the separate Cloud VLA VM:

1. **Hosted demo SNO** — an already-provisioned SNO obtained through `demo.redhat.com`. The provider supplies the cluster endpoint and credentials; there is no local VM or Fedora/libvirt installation step.
2. **Cloud VLA VM** — an Ubuntu/NVIDIA VM provisioned by `tools/cloud-vm-setup/`, running the OpenVLA service separately from the Companion SNO.

The earlier Fedora/libvirt/ROCm and bare-metal implementation remains historical reference material only. It is explicitly unsupported by `tools/preflight/check.py`.

## Current state

The repository does not currently have a unified prerequisite checker.

Existing capabilities are distributed across:

- `tools/companion-install/capture-baseline.sh` — reports Companion cluster state but does not enforce readiness or return profile-specific results.
- `tools/companion-install/virt-install.sh` — creates the companion VM and is intentionally environment-specific.
- `tools/demo-redhat-sno/capture-baseline.sh` — captures the externally provisioned hosted SNO without assuming Fedora, bare-metal networking, FIPS, LVMS, or KubeVirt.
- `infrastructure/gitops/bootstrap/` — bootstraps OpenShift GitOps.
- Component READMEs and manifests — document local prerequisites and deployment details independently.
- `infrastructure/baseline/` — records known hub and companion state.

The hosted demo SNO path starts after cluster provisioning. The Cloud VLA VM is provisioned independently; the checker validates its SSH, Ubuntu, NVIDIA runtime, service, and endpoint readiness.

The deployment experience is therefore knowledgeable but fragmented. An operator must manually interpret several documents and infer whether the next deployment step is safe.

## Implementation status

The first read-only checker slice is implemented in `tools/preflight/`.

Run it with:

```bash
python3 tools/preflight/check.py --profile demo-workload --explain
```

V1 currently checks local tooling and repository paths, GitOps ApplicationSet source alignment, OpenShift API access, ClusterOperator health, GPU labels/capacity, core resource readiness, profile-specific Deployments, selected projected secrets, ACM Companion registration, and Cloud VLA VM readiness. It does not mutate cluster state. The `factory` and `agentic` profiles cover the Factory B/PLC gateway and agentic-ops manifests respectively.

The local-scope smoke run passes in the current workspace. Hub and companion results depend on the active kubeconfigs and cluster availability.

## Goals

1. Detect missing or unhealthy prerequisites before deployment.
2. Distinguish blocking failures, warnings, and informational drift.
3. Cover local tools, hosted Companion API access, Hub, Cloud VLA VM readiness, credentials, networking, storage, GPU capacity, and workload readiness.
4. Be profile-aware: `demo-workload` checks must not require `factory` or `agentic` capabilities.
5. Provide actionable remediation text for every failure.
6. Produce both human-readable output and machine-readable JSON.
7. Preserve GitOps as the source of truth.
8. Support air-gapped and disconnected-install workflows.
9. Avoid exposing secret values in output.
10. Make later roadmaps and deployment automation consume the same readiness model.

## Non-goals

- A replacement for Argo CD, ACM, OpenShift installers, or cloud provisioning systems.
- A fully automatic installer for every prerequisite.
- Automatic mutation of production clusters by default.
- Automatic cloud GPU provisioning or SRE-managed node changes.
- Automatic secret generation, rotation, or printing.
- Hiding environment-specific exceptions behind a green status.

## Readiness model

Each check should have a stable identifier and the following attributes:

```yaml
id: hub.gpu.l40s
scope: hub
profile: demo-workload
severity: blocking
status: pass | warn | fail | skipped | unknown
check: gpu_product_capacity
remediation: "Provision or request an NVIDIA L40S node"
source: docs/08-gpu-resource-planning.md
```

Severity meanings:

- **blocking** — the target profile cannot be deployed safely or cannot complete its demo path.
- **warning** — deployment may proceed, but the limitation must be acknowledged.
- **informational** — useful inventory or drift information.

The checker should exit with:

- `0` when no blocking checks fail.
- `1` when warnings exist but no blocking checks fail.
- `2` when one or more blocking checks fail.
- `3` for checker/configuration errors, such as an invalid kubeconfig or malformed requirements file.

## Proposed interface

Read-only checks are the default:

```bash
python tools/preflight/check.py --profile demo-workload
python tools/preflight/check.py --scope hub --profile demo-workload
python tools/preflight/check.py --scope companion --profile demo-workload
python tools/preflight/check.py --format json --output preflight.json
```

Guided remediation should be explicit:

```bash
python tools/preflight/check.py --profile demo-workload --explain
```

Safe fixes, when implemented, must require an explicit flag:

```bash
python tools/preflight/check.py --profile demo-workload --fix-safe
```

The checker must never perform destructive actions or mutate secrets without a separate, narrowly scoped command and confirmation.

## Check domains

### 1. Local workstation

- Required commands exist: `oc`, `kubectl`, `kustomize`, `jq`, `git`, `curl`.
- Command versions are compatible with the documented OpenShift version.
- Hub kubeconfig is usable.
- Companion kubeconfig exists and is usable.
- Git repository is clean or the operator has acknowledged local changes.
- Required repository paths and Kustomizations exist.
- Container tooling is available when local image builds are requested.

### 2. Hub cluster

- API is reachable and the current identity has the required permissions.
- OpenShift version matches the supported baseline.
- Required cluster operators are Available and not Degraded.
- Argo CD is Available.
- GPU Operator and NFD are healthy.
- Required L40S and L4 capacity exists.
- Exact `nvidia.com/gpu.product` labels match the documented values.
- RHOAI components required by the target profile are enabled.
- Storage classes exist and have usable capacity.
- Kafka, CNPG, Vault, Service Mesh, observability, and ACM prerequisites are healthy.
- Required CRDs exist before dependent applications are synced.

### 3. Companion cluster

- API is reachable through the companion kubeconfig.
- SNO node is Ready and has sufficient CPU, memory, and storage.
- Hosted SNO storage is healthy; the provider's Ceph-backed classes are sufficient for the initial workload slice.
- KubeVirt/HyperConverged, LVMS, Compliance Operator, and self-managed image-policy prerequisites are optional for the hosted `demo-workload` path and are not blocking checks.
- FIPS and STIG state are reported with caveats, not reduced to a generic green status.
- Required namespaces, service accounts, and policies are present.
- ACM reports the companion as joined and available.
- The selected deployment path is recorded as `hosted-demo-sno`; the historical self-managed Fedora path is not supported by this checker.
- Hosted SNO identity, API/console endpoints, version, storage classes, and provider restrictions are recorded before GitOps sync.

### 4. Cloud VLA VM

- Cloud VM SSH target and key are configured without printing key contents.
- Ubuntu, Podman, NVIDIA driver, GPU model, and NVIDIA CDI are healthy.
- `openvla-server.service` is active and `/healthz` and `/readyz` succeed.
- VLA mode is reported explicitly: `mock`, `openvla`, `smolvla`, or `pi0`.
- The checker warns when the service is reachable but still in mock mode.
- An optional workstation-originated endpoint check is informational; SNO-originated reachability must be validated from a Companion workload.
- Fedora/bare-metal and host-native ROCm checks are out of scope.

### 5. Credentials and secrets

Check existence and usability without printing values:

- Red Hat pull secret.
- NGC credentials.
- Hugging Face token.
- Git repository credentials for Argo CD.
- Vault initialization and unseal state.
- Vault paths required by the selected profile.
- Kafka CA and client credentials.
- Nucleus credentials.

Credential checks should report the secret path, namespace, and required consumer—not the secret contents.

### 6. Networking and cross-cluster connectivity

- Hub Routes resolve.
- Companion can reach the hub Kafka TLS route.
- Kafka CA validation succeeds.
- Required OpenShift Routes are admitted and reachable.
- Companion can reach the hub API or ACM cluster-proxy path as appropriate.
- DNS and time synchronization are healthy.
- NetworkPolicies do not block required service paths.
- The host bridge path to VLA is reachable from the companion workload network.

### 7. Demo workload readiness

- Kafka cluster and required topics exist.
- Nucleus is healthy and the warehouse scene is seeded.
- Cosmos Reason endpoint is ready on the expected GPU class.
- Isaac Sim is ready on an L40S node.
- WMS Stub, Fleet Manager, Obstruction Detector, Fake Camera, and Mission Dispatcher are healthy.
- Showcase Console backend and frontend are reachable.
- Camera frame endpoint returns an image.
- Console SSE endpoint can connect.
- A non-destructive synthetic event path can be exercised.

The final `demo-workload` check should validate the dependency graph, not merely pod status.

## Roadmap tracks

### Roadmap A — Inventory and contract

Deliverables:

- Add `roadmaps/` as the home for implementation roadmaps.
- Add a prerequisite requirements catalog for `basic-infra` and `demo-workload`.
- Document the hosted `demo.redhat.com` Companion SNO and separate Cloud VLA VM handoff contracts.
- Define the hosted SNO handoff contract: kubeconfig, cluster-admin permissions, OpenShift version, API/console endpoints, storage, egress, ACM eligibility, and provider restrictions.
- Assign stable check IDs, scopes, severity, remediation text, and source documentation.
- Identify environment-specific values that must be configured rather than hardcoded.

Exit criteria:

- Every `demo-workload` prerequisite has an owner, a check definition, and a remediation reference.
- No check requires secret values to be printed.

### Roadmap B — Read-only preflight checker — V1 delivered

Deliverables:

- Add `tools/preflight/check.py`.
- Keep the first implementation dependency-free in `tools/preflight/check.py`; split into modules only when the check catalog warrants it.
- Keep the readiness profile data close to the checker until a versioned requirements schema is needed.
- Support hub, companion, local, and cloud-vm scopes.
- Support terminal and JSON output.
- Return documented exit codes.

Exit criteria:

- A clean `demo-workload` environment produces a passing report.
- A deliberately broken prerequisite produces a clear failure and non-zero exit code.
- The report identifies the exact remediation action and source document.

### Roadmap C — Guided remediation

Deliverables:

- Add `--explain` output with operator-friendly remediation steps.
- Add links to component READMEs and relevant ADRs.
- Detect whether a remediation is automated, manual, SRE-owned, or customer-owned.
- Add checks for common configuration drift, such as placeholder Kafka routes and mock VLA mode.
- Add and maintain the separate Cloud VLA VM setup contract; do not reuse the historical Fedora/ROCm host assumptions.

Exit criteria:

- A new operator can follow the report without searching the entire repository.
- Every blocking failure explains what the operator must do next.

### Roadmap D — Safe helper actions

Deliverables:

- Add narrowly scoped helpers for non-destructive actions:
  - render/validate Kustomize
  - validate GitOps bootstrap manifests
  - apply the initial GitOps bootstrap after confirmation
  - generate local config templates
  - verify Vault paths and required namespaces
  - trigger explicitly selected Argo syncs
- Add `--fix-safe` only for actions that are reversible and well-scoped.

Exit criteria:

- Helpers never bypass GitOps for long-lived application state.
- Helpers never delete or recreate clusters, VMs, disks, secrets, or namespaces without a dedicated confirmation flow.
- Dry-run behavior is available wherever the underlying command supports it.

### Roadmap E — Profile-aware deployment gates — initial profiles delivered

Deliverables:

- Extend the existing `basic-infra`, `demo-workload`, `factory`, and `agentic` profiles with the remaining network, credential-path, and manifest validation checks.
- Add a pre-sync or CI validation mode for manifests.
- Add a Console or deployment report link to the latest readiness result.
- Add CI checks for requirements-file and checker consistency.

Exit criteria:

- `demo-workload` deployment can be blocked before expensive GPU/model startup when prerequisites are missing.
- `factory` and `agentic` requirements do not accidentally become `demo-workload` blockers.

## Safety principles

1. Read-only by default.
2. Explicit `--fix` or `--apply` for mutations.
3. No secret values in logs, JSON reports, or error messages.
4. No destructive VM or disk operations from preflight.
5. No direct application deployment that bypasses Argo CD.
6. Air-gap checks must not assume internet access.
7. Warnings must preserve uncomfortable truths, such as mock VLA mode or unsupported model/GPU combinations.
8. Environment-specific exceptions must be encoded as documented profiles, not silent bypasses.

## Acceptance test scenarios

The checker should be tested against at least these cases:

1. Fully ready `demo-workload` environment.
2. Missing `oc` binary.
3. Expired or wrong kubeconfig.
4. Missing L40S node.
5. GPU present but incorrect GFD product label.
6. Argo CD installed but not Available.
7. Kafka operator installed but Kafka cluster not Ready.
8. Missing Vault path.
9. Companion joined to ACM but unavailable.
10. Hub Kafka route unreachable from companion.
11. VLA endpoint reachable but running in mock mode.
12. Required image/model pull secret missing.
13. NetworkPolicy blocks the expected service path.
14. A readiness profile requests a prerequisite belonging only to a later profile.

## Recommended first implementation slice

Start with a read-only `demo-workload` checker covering:

1. Local tools and kubeconfigs.
2. Hub/companion API access.
3. GPU capacity and labels.
4. Argo CD, Kafka, Vault, RHOAI, storage, and ACM health.
5. Required secrets by path.
6. Companion-to-hub Kafka connectivity.
7. Host VLA health and mode.
8. Demo workload health.

Do not begin with automatic installation. First make the readiness report trustworthy. Then add safe remediation for the small set of actions that are genuinely repeatable.

## Future roadmap convention

Additional roadmaps should live under `roadmaps/` and use this structure:

1. Purpose
2. Current state
3. Goals and non-goals
4. Dependencies and decisions
5. Sequenced deliverables
6. Acceptance criteria
7. Risks and open questions

Candidate future roadmaps:

- `roadmaps/deployment.md` — end-to-end installation and rollout flow.
- `roadmaps/demo-workload.md` — operational warehouse demo readiness.
- `roadmaps/observability.md` — metrics, logs, traces, and demo evidence.
- `roadmaps/security.md` — signing, SBOMs, FIPS, STIG, and air-gap posture.
- `roadmaps/multisite.md` — Factory B, ACM, policy rollout, and rollback.
- `roadmaps/mlops.md` — training, lineage, registry, promotion, and serving.
- `roadmaps/agentic.md` — LangGraph, MCP, Llama Stack, and HIL governance.
