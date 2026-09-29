# Phase 0 Kickoff Plan — Session Backlog

> Storage terminology updated 2026-09-29: historical sessions below established the S3 services. SeaweedFS is the current migration target in ADR-021, not a claim about what those sessions deployed. Current setup and validation are in the [object-storage migration guide](../../tools/object-storage/README.md).

This plan orders the remaining Phase 0 work (post–Session 01) into concrete Claude Code sessions. It is the backlog Session 02 onward works through in order, with explicit parallel tracks where the work is genuinely independent.

- **Source of truth for Phase 0 scope**: `docs/04-phased-plan.md` (Phase 0 section).
- **Baseline of current cluster state**: `infrastructure/baseline/osd-hub-state.md`.
- **Authoritative decisions**: `docs/07-decisions.md`. Pay attention to ADR-017, ADR-018, ADR-019, **ADR-020** (Service Mesh 3).

---

## Purpose

Session 01 delivered: repo scaffold, OSD hub baseline capture with OD-9 resolution, ADR-020 adoption of Service Mesh 3, and this backlog document. What remains is everything else Phase 0 requires to exit — GitOps, platform operators, mesh, RHOAI validation, observability, security baseline, companion provisioning, multi-cluster federation, and a final exit review.

Each session below is scoped to fit in a single Claude Code session with human supervision. Where a single phase item would clearly overrun a session (e.g. companion provisioning), it is split across numbered sub-sessions.

---

## Phase 0 exit criteria (from `docs/04-phased-plan.md`) — with Session 01 annotations

| Exit criterion | Satisfied by |
|---|---|
| Every installed operator on hub + companion is healthy and reconciled from Git. | Sessions 02 – 05 (hub), 11 – 12 (companion), 13 (cross-cluster apps). |
| DCGM exporter shows all GPUs visible in Grafana, grouped by `nvidia.com/gpu.product`. | Session 07 (baseline Grafana dashboards). |
| A test Job using `nvidia.com/gpu: 1` and the appropriate `nvidia.com/gpu.product` nodeSelector runs successfully on both an L40S and an L4 node and reports the correct device via `nvidia-smi`. | Session 06 for L40S immediately; L4 portion runs once L4 nodes are self-provisioned (Finding 1, `infrastructure/baseline/osd-hub-state.md`). |
| **OpenShift Virtualization availability question for the OSD instance is answered and documented.** | **Done in Session 01 (OD-9 resolved: installable but unusable on AWS Nitro; KubeVirt lives on companion per ADR-017).** |
| ACM on OSD has registered the companion cluster; cross-cluster Argo CD Application reconciles to companion. | Session 13. |
| A developer can bring up a clone of hub state using only what's in Git (plus documented out-of-band steps for secrets and any SRE-ticketed infrastructure provisioning). | Incrementally satisfied; validated in Session 15 (exit review). |
| Companion cluster has MachineConfig STIG profile applied; FIPS-mode status documented. | Session 11. |

---

## Parallel tracks

Three tracks run in parallel once Session 02 establishes GitOps bootstrap.

```
Session 01 (done)
   |
   v
Session 02  — GitOps bootstrap (blocks everything downstream)
   |
   +---> HUB TRACK:         03 -> 04 -> 05 -> 06 -> 07 -> 08
   |
   +---> COMPANION TRACK:   09 -> 10 -> 11 -> 12
   |                        (starts as soon as OD-8 is resolvable;
   |                         independent of hub track 03-08)
   |
   +---> (once both tracks reach their endpoints:)
         INTEGRATION TRACK: 13 -> 14 -> 15
```

The hub track and companion track **do not block each other** after Session 02. Hub track sessions 03 – 08 can run sequentially while companion track sessions 09 – 12 run in parallel with them. Integration sessions 13 – 15 need both tracks to have reached their respective endpoints.

---

## Session-by-session backlog

Every session is: **one feature branch, one PR, DCO-signed, `Co-Authored-by: Claude` trailer, Conventional Commits title**. Branch naming: `feat/p0-session-NN-<short-slug>`.

### Session 02 — GitOps bootstrap

- **Scope**: Install OpenShift GitOps (Argo CD) on the hub. Define the ApplicationSet pattern and seed the cluster directory structure under `infrastructure/gitops/clusters/hub/`. Bootstrap Argo CD from `infrastructure/gitops/bootstrap/`.
- **Deliverables**:
  - Subscription + Operator install manifests under `infrastructure/gitops/bootstrap/`.
  - Root ApplicationSet seeds, targeting `infrastructure/gitops/apps/`.
  - `clusters/hub/` layout populated with an initial `AppProject` and SSO integration if relevant.
  - `infrastructure/gitops/README.md` authored (currently absent; intentional per Session 01 cut).
- **Depends on**: Session 01.
- **OSD vs companion**: hub.
- **GPU workload?**: No.
- **Estimated sessions**: 1.

### Session 03 — Platform operators wave 1

- **Scope**: Install the "platform plumbing" operators that every application needs. Reshape per Session 03 cluster recon (2026-04-17): ODF dropped in favor of a lightweight S3 service (ADR-021, now updated for SeaweedFS); OpenTelemetry+Tempo+Grafana individual operators replaced by Cluster Observability Operator (Red Hat-supported, subsumes the individual pieces); Grafana decision deferred to Session 07.
- **Operators landed**:
  - `cloud-native-postgresql` (certified, channel `stable-v1.29`) — Postgres for MLflow, Fleet Manager state, LangGraph state.
  - The original commercial object-store operator was **removed in Session 06b**. S3 storage uses plain manifests; the current SeaweedFS replacement follows ADR-021 and requires no storage operator.
  - `cluster-logging` (redhat, channel `stable-6.5`) — log routing via `ClusterLogForwarder`.
  - `loki-operator` (redhat, channel `stable-6.5`) — log storage via `LokiStack`.
  - `cluster-observability-operator` (redhat, channel `stable`) — Prometheus / OTel / Tempo in one operator.
- **Deliverables**:
  - One Application per operator under `infrastructure/gitops/apps/operators/<name>/` (namespace + OperatorGroup + Subscription). Picked up automatically by the `operators` ApplicationSet.
  - ADR-021 (in-cluster S3, now SeaweedFS on hub; no ODF).
- **Depends on**: Session 02.
- **OSD vs companion**: hub.
- **GPU workload?**: No.
- **Estimated sessions**: 1 (completed as one PR).
- **Note**: user-workload monitoring was found **already enabled** by SRE on this OSD hub (`enableUserWorkload: true`, Prometheus + Thanos pods running, remote-writing to Red Hat Observatorium). Session 07 scope shrinks correspondingly — no enablement step needed there.

### Session 04 — Service Mesh 3 control plane

- **Scope**: Stand up the east-west mesh per ADR-020. Deliberate choice not to enable ambient mode; ambient adoption per-workload needs its own ADR.
- **Landed** (under `infrastructure/gitops/apps/operators/service-mesh/`, reconciled via the `operators` ApplicationSet):
  - `Istio` CR `default` (cluster-scoped), spec.namespace `istio-system`, profile `default` (openshift profile layered on top automatically on OCP), version pinned `v1.28.5`.
  - `IstioCNI` CR `default`, spec.namespace `istio-cni`, matching version.
  - `IstioRevisionTag` `default` → `Istio/default`, enabling both `istio.io/rev: default` and the legacy `istio-injection: enabled` labels.
- **Recon finding**: RHOAI 3.4 EA1 pre-ships an Istio instance named `openshift-gateway` in `openshift-ingress`, owned by the `data-science-gateway-class` GatewayClass. It backs the Data Science Gateway / Models-as-a-Service ingress. Session 04 creates a **separate** instance; the two coexist. Future sessions touching ingress or MaaS should respect RHOAI's instance.
- **Deferred to Session 08 (security baseline)**: mesh-scoped `PeerAuthentication` STRICT, default-deny `AuthorizationPolicy`. Lands when there are workloads to policy-test against.
- **Depends on**: Session 02. Independent of Session 03.
- **OSD vs companion**: hub. Companion mesh install is folded into Session 12.
- **Estimated sessions**: 1 (completed as one PR).

### Session 05 — Orchestration operators

- **Scope**: Install ACM, AMQ Streams, AAP; bring up the ACM hub.
- **Landed** (under `infrastructure/gitops/apps/operators/`, picked up by the `operators` ApplicationSet):
  - `acm/` — ACM v2.16.0 (`release-2.16`) in `open-cluster-management` + `MultiClusterHub` CR with `disableHubSelfManagement: true` (sync-wave 1 + SkipDryRunOnMissingResource so Argo CD waits for the CRD).
  - `amq-streams/` — v3.1.0-14 (`stable`) in `amq-streams` namespace, AllNamespaces mode.
  - `aap/` — v2.6.0 (`stable-2.6-cluster-scoped`) in `aap` namespace, AllNamespaces-capable channel.
- **Auto-installed**: MCE (MultiCluster Engine) comes up as an ACM dependency.
- **Deferred**: Kafka CRs (Phase 1), AutomationController (Phase 2), MultiClusterObservability (Session 14), AMQ Streams Console operator (Phase 1+).
- **Depends on**: Session 02 (GitOps), Session 04b (cluster-admin RBAC for Argo CD — required for ACM CRDs).
- **OSD vs companion**: hub.
- **GPU workload?**: No.
- **Estimated sessions**: 1 (completed as one PR).

### Session 06 — RHOAI DSC validation + GPU smoke tests + MLflow backend

- **Landed**:
  - `tests/smoke/gpu/{l40s,l4}.yaml` — plain Jobs (`oc apply -f` on demand). L40S runs immediately. L4 nodes now present (user self-provisioned 2× `g6.2xlarge` during the session); both classes smoke-testable.
  - DSC drift re-check in `infrastructure/baseline/osd-hub-state.md` — no drift from Session 01.
  - New `platform` ApplicationSet layer (`clusters/hub/appsets/platform.yaml` + `apps/platform/*` generator).
  - `apps/platform/mlflow/` backend: CNPG Cluster + S3 storage + bucket-init Job + MLflow CR wiring `backendStoreUriFrom` → CNPG Secret, `artifactsDestination: s3://mlflow-artifacts/`, `envFrom: mlflow-s3-credentials`. Current migration target: single-replica `docker.io/chrislusf/seaweedfs:4.48` `mini`, `200Gi`, Service `seaweedfs:8333`; bucket initialization uses `aws s3api head-bucket` / `create-bucket` from `public.ecr.aws/aws-cli/aws-cli:2.34.0` as a `Sync` hook in wave `1`, with bounded retries and a 600-second timeout.
  - Cleanup pre-apply: `oc delete mlflow/mlflow` + `oc delete namespace ai-showcase-mlops` (residue from abandoned three-chart Helm release).
- **Security shortcut**: placeholder credentials in Git. Session 08 swaps to Vault-sourced ExternalSecrets.
- **Depends on**: Sessions 03 (CNPG and storage prerequisites) + 04b (Argo CD cluster-admin RBAC).
- **OSD vs companion**: hub.
- **Estimated sessions**: 1 (completed as one PR).

### Session 07 — Observability baseline

- **Landed** (under `infrastructure/gitops/apps/observability/`, new `observability` ApplicationSet):
  - `storage/` — dedicated S3 storage in `obs-storage` namespace, backs Loki. Current target: shared SeaweedFS `mini` base, existing `100Gi` capacity retained, S3-only Service `seaweedfs:8333`, credentials in `obs-s3-credentials`. Isolated S3 validation passed in `showcase-storage-canary`; live data/consumer cutover remains pending.
  - `loki/` — `LokiStack` (`1x.demo`, S3-backed), Logging 6.x `ClusterLogForwarder` with application+infrastructure pipelines, collector SA + required ClusterRoleBindings.
  - `ui-plugins/` — Logging + Monitoring UIPlugins (CoO-provided; Red Hat-supported path; no standalone Grafana needed for Phase 0 per D3).
  - `rules/` — `GpuIdleLongRunning` PrometheusRule (powers the 30m-idle signal for GPU scale-down); `GpuClassMismatchPlaceholder` stub for the ADR-018 alert that unlocks once Session 14 Thanos federation exposes kube-state-metrics to UWM.
- **Scope narrowing (vs original plan)**: Tempo + OpenTelemetryCollector dropped. Cluster Observability Operator doesn't bundle them; the `tempo-product` + `opentelemetry-product` Red Hat operators are available in the catalog but installing them with zero trace-emitting workloads wastes operator slots. Defer to the Phase-1 session that introduces the first span-emitter.
- **Still deferred**: standalone Grafana (Phase 1+ when Showcase Console needs an embeddable URL), app-workload ServiceMonitors (per-workload sessions).
- **Depends on**: Session 03 (Loki + CoO), Session 04b (Argo CD cluster-admin RBAC).
- **OSD vs companion**: hub. Companion observability rolls in via Session 14 (Thanos federation).
- **Estimated sessions**: 1 (completed as one PR).

### Session 08 — Hub security baseline

- **Landed**:
  - `apps/operators/vault-secrets/` — HashiCorp Vault Secrets Operator (certified, `stable` channel).
  - `apps/platform/vault/` — single-replica, file-backed Vault StatefulSet + Service + K8s auth SA + runbook README (image pinned `docker.io/hashicorp/vault:1.18.4`; `quay.io/hashicorp/vault` is 401).
  - `infrastructure/security/network-policies/` — `default-deny-all` + companion allowlists (argocd-sync, platform-monitoring, dns-egress) that workloads import via Kustomize.
  - `infrastructure/security/scc/README.md` — scaffold pattern; no custom SCCs yet.
  - ADR-022 (CoO UIPlugin over standalone Grafana, retrospective from Session 07) and ADR-023 (Vault + VSO).
- **Sigstore deferred out of Phase 0**: The `policy-controller-operator` v1.0.0 from redhat-operators ships CRDs whose conversion-webhook `clientConfig` references a `webhook` service the operator never creates, plus a cert SAN mismatch. OCP 4.21 **already has** Sigstore admission via the platform `config.openshift.io/v1 ClusterImagePolicy` API (the preloaded `openshift` CIP enforces OCP release signatures through it) — a completely separate stack from the `policy.sigstore.dev/v1beta1` CRDs the operator would add. Platform CIPs have **no warn mode** — they're enforce-only, so shipping one scoped to our registry without real signing material would block Phase 1 image pulls the instant Phase 1 began. Correct move: **introduce `config.openshift.io/v1 ClusterImagePolicy` alongside the first signed image in Phase 1**, with keys sourced from Vault (now available post-Session-08b).
- **Scope-split decision**: the Phase-0-shortcut cleanup (placeholder Secrets → VaultStaticSecrets, MLflow CA trust fix) moves to Session 08b because Vault requires a manual init/unseal step that isn't automatable by an ApplicationSet sync. Session 08 lands the infrastructure; 08b runs after the user initializes Vault.
- **Session 08c (doc-only)**: After 08b migrated the object-store and Loki Secrets to Vault, two MLflow-specific shortcuts remained — `redhat-ods-applications/mlflow-db-app` is a manual cross-namespace mirror of a CNPG-generated Secret, and the Postgres URI carries `?sslmode=disable` to skip verification of CNPG's self-signed CA. Both are accepted as Phase-0 concessions (intra-cluster traffic is mesh-mTLS-protected) and documented in `infrastructure/gitops/apps/platform/mlflow/README.md`. Full fix (CNPG `managed.roles` + CA-bundle ConfigMap + `sslmode=verify-full`) lands in Phase 1+ alongside the first workload that genuinely demands end-to-end TLS.
- **Depends on**: Session 02 (GitOps), Session 04b (Argo CD cluster-admin RBAC).
- **OSD vs companion**: hub. Companion security (STIG, FIPS, Sigstore **enforce** mode) is Session 11.
- **GPU workload?**: No.
- **Estimated sessions**: 1 (done, with 08b follow-up for credential migration).

### Session 09 — Companion cluster provisioning (OD-8 resolution + install)

- **Scope**: Resolve OD-8 (companion host selection among GMKTec Evo-X2, ORIGIN PC, or dedicated lab hardware). Install self-managed OpenShift on the selected host (SNO pattern for GMKTec; 3-node compact for others if hardware allows). Register access (kubeconfig; if remote, ngrok or equivalent exposure path documented).
- **Deliverables**:
  - OD-8 resolution noted in `docs/09-risks-and-open-questions.md`.
  - Installer artifacts / Assisted Installer ISO preserved under `tools/companion-install/` (create as needed).
  - Companion kubeconfig on the user's workstation; access path documented for future sessions.
  - Draft `infrastructure/baseline/companion-state.md` stub (populated properly in Session 10).
- **Depends on**: Can start in parallel with Session 02 — only user decision + physical/remote hardware action. Claude Code sessions support the installer workflow.
- **OSD vs companion**: companion.
- **GPU workload?**: Depends on host choice. GMKTec Evo-X2 has no NVIDIA GPU (Intel/AMD integrated); ORIGIN PC with NVIDIA GPU is the only companion option that enables vGPU Kit workstation demos.
- **Estimated sessions**: 2 — one for OD-8 + install; one for post-install validation.
- **Note**: this session can be partially async while the installer runs; reconvene Claude Code session once the companion API is reachable.

### Session 10 — Companion baseline capture

- **Scope**: Mirror of Session 01 for the companion cluster. Run equivalent `oc` commands; populate `infrastructure/baseline/companion-state.md` with node inventory, operator state, GPU inventory (if any), SCC posture, OCP Virt availability on companion (likely yes, since it's self-managed bare metal or close to it).
- **Deliverables**: `infrastructure/baseline/companion-state.md` living document.
- **Depends on**: Session 09.
- **OSD vs companion**: companion.
- **GPU workload?**: No; inventory only.
- **Estimated sessions**: 1.

### Session 11 — Companion security baseline (STIG + FIPS + Sigstore enforce)

- **Scope**: Apply the STIG-aligned MachineConfig profile (this is the substantive companion-only capability per ADR-017 — MachineConfigs are fragile on OSD). Validate FIPS mode if the companion host supports it. Install Sigstore policy-controller in **enforce mode** (stricter than hub's warn mode).
- **Deliverables**:
  - STIG MachineConfig manifests in `infrastructure/security/stig-machineconfig/`.
  - FIPS validation notes in `infrastructure/security/fips/` (empty today; populated this session).
  - Sigstore policy-controller config (enforce) under `infrastructure/security/sigstore/policy-controller/` targeted at companion via ApplicationSet.
- **Depends on**: Session 09, Session 10.
- **OSD vs companion**: companion.
- **GPU workload?**: No.
- **Estimated sessions**: 1–2.

### Session 12 — Companion OpenShift Virtualization + mesh

- **Scope**: Install OpenShift Virtualization on the companion per ADR-017 (this is where VM-based demos live). `HyperConverged` CR configured. If the companion host is ORIGIN PC with NVIDIA GPU, also configure vGPU (`NodeFeatureDiscovery` + GPU Operator + vGPU driver baked into MachineOSConfig or similar). Service Mesh 3 control plane on companion (mirror of Session 04).
- **Deliverables**:
  - KubeVirt operator Subscription + HyperConverged CR under `infrastructure/operators/openshift-virt/`.
  - vGPU configuration (if applicable) documented.
  - Service Mesh 3 CRs on companion under `infrastructure/operators/service-mesh/` with companion overlay.
- **Depends on**: Session 11.
- **OSD vs companion**: companion.
- **GPU workload?**: vGPU configuration if ORIGIN PC.
- **Estimated sessions**: 1–2 depending on vGPU complexity.

### Session 13 — ACM registration of companion; cross-cluster Argo CD

- **Scope**: Register companion cluster as a managed cluster under ACM on the hub. Verify a cross-cluster Argo CD Application reconciles to companion via ACM's ApplicationSet delivery pattern.
- **Deliverables**:
  - `ManagedCluster` + `ManagedClusterSet` + `Klusterlet` manifests.
  - Example Argo CD Application that reconciles to companion and is observable from the hub.
  - `docs/deployment/cluster-setup.md` chapter on multi-cluster federation.
- **Depends on**: Session 05 (ACM hub), Session 12 (companion fully up).
- **OSD vs companion**: both.
- **GPU workload?**: No.
- **Estimated sessions**: 1.

### Session 14 — Thanos federation + companion user-workload monitoring

- **Scope**: Enable user-workload monitoring on companion. Federate hub ↔ companion metrics via Thanos. Extend the baseline Grafana dashboards to differentiate per-cluster.
- **Deliverables**:
  - Thanos sidecar + querier config.
  - Hub Grafana datasource updated to query cross-cluster.
  - Dashboard variant with `cluster` selector.
- **Depends on**: Session 07 (hub observability), Session 13 (ACM federation live).
- **OSD vs companion**: both.
- **GPU workload?**: No.
- **Estimated sessions**: 1.

### Session 15 — Phase 0 exit review + one-pager

- **Scope**: Walk every Phase 0 exit criterion; confirm satisfied or document waiver. Produce the "OpenShift as the foundation for NVIDIA Physical AI" internal one-pager artifact (Phase 0 demo per `docs/04-phased-plan.md`). Pre-flight for Phase 1.
- **Deliverables**:
  - Exit checklist under `docs/deployment/phase-0-exit-review.md`.
  - One-pager under `docs/sales-enablement/one-pagers/phase-0-foundation.md`.
  - List of Phase 1 preconditions (e.g., L4 nodes present, NGC credentials configured, Nucleus deployment codified).
- **Depends on**: Sessions 02 – 14.
- **OSD vs companion**: both.
- **GPU workload?**: No.
- **Estimated sessions**: 0.5 (smaller than a typical session).

---

## Summary table

| # | Title | Depends on | Cluster | GPU class used | Est. sessions |
|---|---|---|---|---|---|
| 02 | GitOps bootstrap | 01 | hub | — | 1 (done) |
| 03 | Platform operators and storage prerequisites (CNPG, S3, Logging, Loki, CoO) | 02 | hub | — | 1 (done) |
| 04 | Service Mesh 3 control plane | 02 | hub | — | 1 (done) |
| 05 | Orchestration operators (ACM, AMQ Streams, AAP) | 03 | hub | — | 1 (done) |
| 06 | RHOAI DSC validation + GPU smoke tests + MLflow backend | 03 | hub | L40S + L4 | 1 (done) |
| 07 | Observability baseline (Loki + UIPlugins + GPU rules; Tempo/OTel deferred) | 03 | hub | — | 1 (done) |
| 08 | Hub security baseline: Vault + VSO + policy-controller + templates | 03 | hub | — | 1 (done) |
| 08b | Vault init/unseal + migrate Phase-0 placeholder Secrets to VSO | 08 | hub | — | 1 (done) |
| 08c | MLflow DB cross-namespace mirror + `sslmode=disable` accepted as Phase-0 concessions; doc-only | 08b | hub | — | 0.25 (done) |
| 09 | Companion provisioning (OD-8 + install) | (parallel with 02) | companion | — | 2 |
| 10 | Companion baseline capture | 09 | companion | — | 1 |
| 11 | Companion security (STIG, FIPS, Sigstore enforce) | 10 | companion | — | 1–2 |
| 12 | Companion OpenShift Virt + Service Mesh 3 | 11 | companion | vGPU if ORIGIN PC | 1–2 |
| 13 | ACM companion registration + cross-cluster Argo CD | 05, 12 | both | — | 1 |
| 14 | Thanos federation + companion monitoring | 07, 13 | both | — | 1 |
| 15 | Phase 0 exit review + one-pager | 02–14 | both | — | 0.5 |

Total: **14 sessions, roughly 14–18 session-weeks** depending on how the parallel tracks sequence.

---

## Preconditions the user manages (not Claude sessions)

These are user actions that do not map to Claude Code sessions; they gate or unblock specific sessions above.

- **L4 node self-provisioning**: user adds `g6.xlarge` (or equivalent) L4-bearing worker nodes directly when a session needs them. First session that requires L4: Session 06 (L4 portion of smoke tests), but the critical consumer is Phase 1 Metropolis VSS.
- **Companion host selection (OD-8)**: user decides GMKTec Evo-X2 vs ORIGIN PC vs dedicated lab hardware. This decision is made during Session 09.
- **NGC API key provisioning**: required from Phase 1 for pulling NVIDIA images. Not a Phase 0 gate, but land in Vault during Session 08 so it's ready.
- **Cosign signing identity**: user decides keyless (Fulcio in GitHub Actions) vs key-based (Vault-stored private key for in-cluster Tekton). ADR-016 allows both; Session 08 pins per-environment.
- **SRE tickets**: none required for Phase 0.

---

## Cross-cutting notes

- **Branch naming**: `feat/p0-session-NN-<slug>`. Example: `feat/p0-session-02-gitops-bootstrap`.
- **PR titles**: Conventional Commits (`feat:`, `chore:`, `docs:`, `fix:`, `refactor:`). Each PR links its phase + workstream.
- **Commit trailers**: `Co-Authored-by: Claude` (no model name, per `.claude/rules/ai-compliance.md`).
- **Every session starts with**: (a) read `CLAUDE.md`, (b) read the target session's entry in this file, (c) re-confirm the baseline file reflects current cluster state, (d) author `.plans/session-NN-plan.md` for user approval before touching code.
- **Every session ends with**: one squash-merged PR, the baseline file updated if cluster state changed, this document updated if scope shifted, and a clear handoff for the next session in its description.
- **Session scope creep**: if a session starts spilling into the next one's scope, STOP, surface the boundary to the user, and either close the current session with a partial PR or formally re-scope.
- **ADR contradictions**: STOP and surface; never work around. Session 01 hit this with ADR-006 vs the installed Service Mesh 3, resolved via ADR-020. Expect one or two more through Phase 0 as real state meets assumptions.

---

## Known open questions beyond this backlog

These are deliberately not Phase 0 session topics; noted so they don't get lost.

- **OD-5** (agent brain model selection for Loop 4) — Phase 3 concern; constraint added by ADR-019 (must be Llama Stack Agents API compatible).
- **Nucleus codification** — pre-existing deployment, formalized Phase 1 rather than Phase 0.
- **CI workflows** (Sigstore signing + SBOM generation in GitHub Actions) — deliberately deferred from Session 01 per the Session 01 plan; plausible Phase 0 addition as a 16th session if we want signing posture to exist before Phase 1 image builds begin. Flag for the user.

---

## References

- `docs/04-phased-plan.md` — Phase 0 work breakdown and exit criteria (authoritative).
- `docs/07-decisions.md` — ADR-017 (hub + companion), ADR-018 (GFD GPU class targeting), ADR-019 (Llama Stack HIL), **ADR-020 (Service Mesh 3)**.
- `infrastructure/baseline/osd-hub-state.md` — current hub state; findings that shaped this plan.
- `CLAUDE.md` — hard constraints every session must respect.
