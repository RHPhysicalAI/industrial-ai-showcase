# Phase 0 Exit Review

> Historical review: the satisfied criteria below refer to the original Phase 0 sessions. S3 terminology was updated on 2026-09-29 for the SeaweedFS migration; those results do not validate the replacement. See the [CPU-only canary and controlled cutover guide](../../tools/object-storage/README.md).

Walks every exit criterion from `docs/04-phased-plan.md` Phase 0, marks status, cites the PR that satisfied it, and flags anything intentionally deferred.

- **Phase 0 started**: 2026-04-17 (Session 01 foundation capture).
- **Phase 0 completed**: 2026-04-18 (this session).
- **Wall-clock**: ~24 hours across 15 sessions (some ran back-to-back, several were single-commit sessions).
- **PRs merged**: #1–#23.

---

## Exit criteria status

| # | Criterion | Status | Satisfied by |
|---|---|---|---|
| 1 | Every installed operator on hub + companion is healthy and reconciled from Git. | **SATISFIED** | Hub operators (RHOAI, CNPG, AMQ Streams, Vault, Service Mesh 3, ACM, COO, GitOps) reconciled by hub Argo (PRs #2–#15). Companion operators (LVMS, Compliance, KubeVirt, UWM config) reconciled by cross-cluster ApplicationSet after Session 13 (PRs #20–#23). All 7 `apps/companion/*` Applications Synced + Healthy. |
| 2 | DCGM exporter shows all GPUs visible in Grafana, grouped by `nvidia.com/gpu.product`. | **SATISFIED** | Session 07 observability + Session 14 MCO expose GPU metrics in hub Grafana with `nvidia.com/gpu.product` label. Both classes present: `NVIDIA-L40S` and `NVIDIA-L4` nodes labeled by GFD, visible under their class strings. |
| 3 | Test Job with `nvidia.com/gpu: 1` + `nvidia.com/gpu.product` nodeSelector runs on both L40S and L4, `nvidia-smi` reports correctly. | **SATISFIED** | L40S Job scheduled + ran in Session 06 (PR #10). L4 smoke test in Session 15 on `ip-10-0-32-193.ec2.internal` — `nvidia-smi` reported `NVIDIA L4`, driver 580.105.08, CUDA 13.0, 23 GiB memory. |
| 4 | OpenShift Virtualization availability question for the OSD instance is answered and documented. | **SATISFIED** | Session 01 OD-9 resolution + ADR-017 amendment: OSD's AWS Nitro substrate cannot run KubeVirt; companion hosts the VM story. KubeVirt 4.21.3 installed on companion, HyperConverged Available (Session 12, PR #21). |
| 5 | ACM on OSD has registered the companion cluster; cross-cluster Argo CD Application reconciles to companion. | **SATISFIED** | Session 13 (PR #22): companion joined ACM `clusters-companion` set; `GitOpsCluster` auto-maintains Argo cluster secret; ApplicationSet matrix generator spawns 7 companion Applications, all Synced + Healthy. Cross-cluster reconciliation via ACM cluster-proxy (no hub→companion direct network). |
| 6 | A developer can bring up a clone of hub state using only what's in Git (plus documented out-of-band steps for secrets and SRE-ticketed infrastructure). | **SATISFIED (with explicit gaps)** | Every operator + CR is in Git under `infrastructure/gitops/apps/*`. Out-of-band documented: (a) two imperative secrets in `hub-acm/observability/README.md`, (b) manual klusterlet import in `hub-acm/README.md`, (c) Red Hat pull-secret prerequisite, (d) S3 bucket pre-creation, (e) SRE-ticketed GPU node additions. No undocumented dark magic. |
| 7 | Companion cluster has MachineConfig STIG profile applied; FIPS-mode status documented. | **SATISFIED** | Session 11 (PR #20): 105 of 106 auto-remediations applied (1 waiver — `sshd-disabled` strand risk); post-apply scan 137 PASS, 19 FAIL (all 19 accounted for: waivers, VM-topology N/A, intentional CIP scoping, Phase-1 deferrals). FIPS enabled day-1 (`fips: true`, kernel `fips=1`, `crypto.fips_enabled=1`) with documented `hostcrypt-check-bypassed` caveat (ADR-017 amendment). Evidence in `infrastructure/security/{fips,stig-machineconfig,sigstore}/README.md`. |

---

## Deferred items (explicitly not Phase 0)

Items that came up during Phase 0 and were intentionally pushed:

- **registry.redhat.io ClusterImagePolicy expansion** — different signing chain (GPG, not the release-signing sigstore key). Phase 1 when we validate the key retrieval story.
- **GHCR ClusterImagePolicy for showcase images** — depends on locked signing identity (Fulcio vs. cosign key in Vault per ADR-016/023). Phase 1 with first built showcase image.
- **IdP configuration** — unblocks kubeadmin removal and 13 deferred STIG remediations (OAuth templates, classification banner, cluster-logging rules). Phase 1.
- **Companion host RHEL 9 rebuild** — would close the FIPS `hostcrypt-check-bypassed` audit caveat. Not on critical path; Phase 1+.
- **MCO secrets to VaultStaticSecret** — two imperative secrets (`thanos-object-storage`, `multiclusterhub-operator-pull-secret`) should migrate to Vault pattern. Phase 1 tidy-up.
- **Service Mesh 3 on companion** — deliberately not installed. No workload on companion needs east-west mesh encryption. Add when a workload does.

---

## Documentation deliverables

All Phase 0 doc outputs in one place:

| File | Purpose |
|---|---|
| `docs/00-project-charter.md` through `docs/09-risks-and-open-questions.md` | Strategic + reference docs (Session 01) |
| `docs/plans/phase-0-plan.md` | Session-by-session backlog (this plan) |
| `docs/plans/phase-0-exit-review.md` | **This document** |
| `docs/sales-enablement/one-pagers/phase-0-foundation.md` | Internal one-pager (Session 15) |
| `docs/07-decisions.md` ADR-001 through ADR-023 (+ ADR-017 amendment) | Decisions log |
| `infrastructure/baseline/osd-hub-state.md` | Hub live state, refreshable |
| `infrastructure/baseline/companion-state.md` | Companion live state, refreshable |
| `infrastructure/gitops/apps/hub-acm/README.md` | Cross-cluster Argo CD + klusterlet import runbook |
| `infrastructure/gitops/apps/hub-acm/observability/README.md` | MCO setup + imperative secrets runbook |
| `infrastructure/security/fips/README.md` | FIPS evidence bundle + hostcrypt bypass disposition |
| `infrastructure/security/stig-machineconfig/README.md` | STIG scan disposition (waivers, deferrals) |
| `infrastructure/security/sigstore/README.md` | ClusterImagePolicy scope rationale |
| `infrastructure/gitops/apps/platform/mlflow/README.md` | MLflow Phase-0 concessions (DB mirror, sslmode) |

No `docs/deployment/prerequisites.md` or `docs/deployment/cluster-setup.md` written — the per-area READMEs cover their own prerequisites + setup inline, which is more discoverable than one monolithic setup doc. Phase 1 can still compile these if a demo operator needs a single "read this first" page.

---

## Phase 1 preconditions

Before Session 16 (first Phase 1 session) can productively start:

1. **NGC credentials in hub Vault** — API key from NGC catalog, stored at `kv/ngc/api-key`, VaultStaticSecret rendered into whatever namespace pulls NIMs. Needed for Cosmos NIM, VSS, GR00T image pulls.
2. **Nucleus deployment codified in Git** — the existing Nucleus install is pre-existing per ADR-002. Phase 1 expects it reconciled from Git like every other workload; Session 16 captures whatever's deployed today into `apps/platform/nucleus/`.
3. **First showcase image builds decided** — defines the GHCR signing identity story (Fulcio keyless vs. cosign + Vault key). Blocks the GHCR ClusterImagePolicy authoring.
4. **IdP choice confirmed** — OIDC provider TBD (Red Hat SSO? htpasswd bootstrap? GitHub OAuth?). Determines the OAuth template remediations and the kubeadmin-removal gate.

None of these are inside the team's direct control from a Claude Code session — all are product-level decisions. They're preconditions for Phase 1 session planning, not Phase 0 work items.

---

## Risk register deltas

`docs/09-risks-and-open-questions.md` items as of Phase 0 exit:

- **OD-8** (companion host selection) — RESOLVED (Session 09; GMKTec on Fedora 43).
- **OD-9** (KubeVirt on OSD) — RESOLVED (Session 01; lives on companion per ADR-017).
- **NEW: FIPS hostcrypt-check-bypass** — accepted Phase-0 caveat; documented in ADR-017 amendment. Closes when companion rebuilt on RHEL 9.
- **NEW: StorageClass on SNO** — RESOLVED (Session 11; LVMS provisioner on 100 GB qcow2 vdb).
- **NEW: Service Mesh 3 companion** — INTENTIONALLY DEFERRED (Session 12).

---

## Sign-off

All seven Phase 0 exit criteria are satisfied. The reference environment is fit for the Mega Core (Phase 1) work:

- Two clusters (OSD hub + self-managed SNO companion) reconciled from Git end-to-end.
- Cross-cluster federation live: one ACM, one Argo, two clusters, one repo.
- Unified observability via Thanos.
- Security baseline verified (FIPS on companion, STIG scan disposition, Sigstore enforce on companion component images).
- Customer-parity self-managed demo story available in addition to the managed OSD story.

Ready to start Phase 1.
