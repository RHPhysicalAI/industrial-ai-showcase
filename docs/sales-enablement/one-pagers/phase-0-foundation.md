# Phase 0 Foundation — OpenShift as the substrate for NVIDIA Physical AI

Internal Red Hat. Audience: SAs / AEs prepping for a customer conversation about NVIDIA's Mega / Omniverse blueprint on OpenShift.

## The 10-second version

Phase 0 stands up two Git-reconciled OpenShift clusters — an OSD hub with L40S GPUs and a self-managed companion SNO — federated by ACM, observability unified through Thanos, security baseline (FIPS day-1, STIG-scanned, Sigstore-enforcing) live on the self-managed side. Ready to host Mega workloads.

## What's demonstrable today

- **Two clusters, one repo, one Argo.** OSD hub + self-managed companion SNO, both reconciled from Git. 7 companion Applications `Synced + Healthy` via cross-cluster ApplicationSet (PR #22).
- **GPU.** L40S + L4 nodes labeled by GFD; smoke tests on both classes pass (`nvidia-smi` reports correctly on each). PR #10 (L40S) + Session 15 L4 verify.
- **OpenShift AI 3.4 EA1** on hub, full DSC including `trainer`. MLflow backend (CNPG Postgres + S3 artifact storage, Vault-sourced creds). PRs #13–#15 established the historical backend; SeaweedFS is the 2026-09-29 migration target and is not validated by those PRs.
- **Security on companion.** FIPS day-1 (`fips=1` cmdline, `crypto.fips_enabled=1`). DISA STIG V2R3 scan: FAIL 119 → 19 after one reboot (105 of 106 auto-remediations; 1 strand-risk waiver). Platform `ClusterImagePolicy` enforcing Red Hat release-signing key. PR #20.
- **Cross-cluster observability.** Hub Thanos returns `companion + local-cluster`; 95 companion `up` series flowing through ACM MCO (PR #23).
- **OpenShift Virtualization** on companion — HyperConverged reconciled, 28 pods running. VMs live here; hub is container-only by design (PR #21, ADR-017).

## Differentiator claim status (charter §22)

| # | Claim | Status | Phase-0 proof |
|---|---|---|---|
| 1 | On-prem / air-gapped first-class | Partial | Self-managed companion SNO demonstrated; true air-gap validation via `oc-mirror v2` is Phase 1. |
| 2 | Containers + VMs + vGPU on one cluster | Partial | KubeVirt live on companion; vGPU deferred (current companion host has no NVIDIA GPU). |
| 3 | Hybrid → edge → robot, one op model | Partial | Hub + companion federated via ACM + Argo; spoke-a / spoke-b scaffolded but not provisioned. |
| 4 | OpenShift AI as MLOps backbone | Substantiated | RHOAI 3.4 EA1 full DSC; MLflow backend + model registry wired. |
| 5 | Security / supply-chain posture | Substantiated | FIPS day-1, STIG scan + evidence bundle, Sigstore enforce on companion. |
| 6 | Open model choice | Aspirational | Serving layer arrives Phase 1 (vLLM via KServe). |
| 7 | Agentic orchestration via MCP | Aspirational | Phase 3 (LangGraph + Llama Stack per ADR-019). |
| 8 | Day-2 lifecycle done right | Substantiated | GitOps + ACM + operator-driven upgrades across both clusters. |

## Talk-track hooks by archetype

- **A (novice).** Two-cluster architecture + "containers, VMs, AI, robots on one platform, same tools on-prem or in cloud." Phase-0 is the foundation; visual demos in later phases.
- **B (evaluator).** Cross-cluster Argo view. One repo, one Argo, managed + self-managed substrates. This is what they'd run in production across factory + datacenter.
- **C (expert — Foxconn/Siemens-tier).** FIPS + STIG evidence bundle on a cluster they could operate themselves. `infrastructure/security/*/README.md` + the scan-delta numbers are auditable artifacts, not slideware.

## Caveats (mention before the customer asks)

- Companion FIPS install has `install.openshift.io/hostcrypt-check-bypassed=true` because the install host is Fedora 43, not RHEL 9. The running cluster is genuinely FIPS; the annotation is an install-chain audit breadcrumb (ADR-017 amendment).
- `kubeadmin` still present on companion (no IdP yet); 14 STIG rules gated on IdP remain FAIL until Phase 1.
- Service Mesh 3 is hub-only — no companion workload needs east-west mesh yet.
- Nucleus pre-existing (ADR-002); Phase 1 codifies its manifests into Git.

## Deeper reading

- `docs/plans/phase-0-exit-review.md` — full exit checklist with PR refs.
- `infrastructure/baseline/osd-hub-state.md`, `companion-state.md` — live state of both clusters.
- `docs/07-decisions.md` ADR-017 (OSD + companion), ADR-018 (GPU class targeting), ADR-023 (Vault).
- `infrastructure/security/{fips,stig-machineconfig,sigstore}/README.md` — the compliance artifact bundle.
