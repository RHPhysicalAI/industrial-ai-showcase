# 07 — Decisions (ADR log)

Architecture decisions recorded here. Each entry follows a lightweight ADR format: context, decision, consequences, status.

When a new material decision is made, add an entry. When a decision is superseded, mark the old one and add a new one.

---

## ADR-001: NVIDIA Mega Omniverse Blueprint as the canonical reference

**Status**: Accepted

**Context**: Choosing the organizing reference architecture for the showcase. Options considered: (a) a custom industrial-AI reference built from scratch, (b) NVIDIA's Mega Omniverse Blueprint, (c) NVIDIA's DSX Blueprint, (d) a broader "Omniverse Enterprise" generic reference.

**Decision**: We implement NVIDIA's Mega Omniverse Blueprint as the canonical reference and position Red Hat as its first-class enterprise substrate.

**Consequences**:
- Every customer conversation about Mega becomes a conversation where Red Hat has relevant substance.
- We are dependent on Mega's ongoing evolution; we adopt updates as they ship.
- We do not compete with Mega or propose an alternative; we implement it better operationally.
- DSX is deliberately out of scope as a primary reference but we may position OpenShift as relevant to DSX in talk tracks.

---

## ADR-002: Keep Nucleus for Phase 1; introduce `ovstorage` variant in Phase 2

**Status**: Accepted

**Context**: NVIDIA introduced modular libraries at GTC 2026, including `ovstorage` as a Kubernetes-native replacement for parts of Nucleus's functionality. Customers today are on Nucleus; the strategic direction is toward `ovstorage`.

**Decision**: The reference implements Nucleus first (Phase 1) because it matches the current customer install base. In Phase 2, we add an `ovstorage`-based variant as an alternate path. Both remain supported going forward.

**Consequences**:
- Customers currently on Nucleus have a clean migration story.
- Customers adopting `ovstorage` greenfield have a direct path.
- We carry a documentation burden of maintaining two patterns; this is an acceptable cost for customer optionality.

---

## ADR-003: GR00T primary; Pi-0 and OpenVLA as BYO alternatives

**Status**: Accepted

**Context**: The "robot brain" is a pivotal component. Choices: serve only GR00T, serve only open models, or serve GR00T with architectural BYO support.

**Decision**: GR00T N1.7 is the primary VLA served in the reference. The serving layer (vLLM + KServe) is architecturally model-agnostic; Pi-0, OpenVLA, and customer-fine-tuned models plug in through configuration without code changes outside a YAML.

**Consequences**:
- Default demos use GR00T, reflecting NVIDIA's flagship status in customer conversations.
- Customers concerned about model vendor lock-in see a concrete BYO path.
- Serving-layer code must remain model-agnostic; don't bake GR00T assumptions into the serving wrappers.

---

## ADR-004: MLflow (RHOAI Early Access) for experiment tracking and model registry

**Status**: Accepted

**Context**: Prior evaluation compared MLflow and Langfuse. Both have advocates. RHOAI Early Access ships with MLflow integrated.

**Decision**: MLflow is the single tracking and registry choice. Do not introduce Langfuse alongside.

**Consequences**:
- Simpler stack, one pane of experiment-tracking glass.
- Dependency on RHOAI's integrated MLflow build; revisit if RHOAI changes direction.
- If LLM-agentic observability (traditionally Langfuse's sweet spot) is needed, we lean on OpenTelemetry for agent traces instead.

---

## ADR-005: LangGraph as the agentic framework

**Status**: Accepted (see also ADR-019 for the Llama Stack wrapping pattern)

**Context**: The team has deep experience with LangGraph in other internal projects. Alternatives include CrewAI, AutoGen, LlamaIndex Agents, and raw LangChain.

**Decision**: LangGraph is the one agentic framework used in this reference.

**Consequences**:
- Consistent with team standards; existing patterns transfer.
- Agentic workflows are expressed as graphs; that mental model becomes part of the reference documentation.
- Llama Stack (ADR-019) wraps LangGraph for customer-facing governance (HIL, guardrails, PII detection) — the two compose rather than compete.
- If OpenClaw or similar frameworks mature, we evaluate them for interoperability, not replacement.

---

## ADR-006: OpenShift Service Mesh v2 (Istio-based) for east-west traffic

**Status**: Superseded by ADR-020

**Context**: Zero-trust and observability across many services are required. Options include OpenShift Service Mesh v2 (Istio), Service Mesh v3 if available, or no mesh with mTLS handled ad-hoc.

**Decision**: Service Mesh v2 is used from Phase 0.

**Consequences**:
- All workload namespaces participate via sidecar injection.
- We pay the complexity cost upfront; benefits (mTLS, tracing, traffic shaping) compound.
- Sidecar-based rather than ambient — revisit in a future ADR if ambient matures in Red Hat's offering.

**Superseded by ADR-020**: The 2026-04-17 hub baseline found Service Mesh 3 (the `sail-operator`-based Istio productization) already installed rather than v2. ADR-020 adopts Service Mesh 3 and preserves the sidecar-default posture this ADR established.

---

## ADR-007: AMQ Streams (Kafka) as the primary event bus

**Status**: Accepted

**Context**: Fleet events, missions, and telemetry need a durable, ordered, high-throughput event bus. Alternatives: AMQ Broker (JMS), NATS, RabbitMQ.

**Decision**: AMQ Streams (Kafka) is the single event-bus choice. MirrorMaker 2 federates hub ↔ spoke.

**Consequences**:
- Customers familiar with Kafka immediately recognize the pattern.
- Schema evolution governed via Schema Registry + Avro.
- Learning curve for teams new to Kafka; documented in component-level READMEs.

---

## ADR-008: Unitree G1 as the primary humanoid sim embodiment

**Status**: Accepted

**Context**: The reference includes a humanoid scenario. Options: NVIDIA-sampled models (GR1, H1), Unitree G1, Boston Dynamics Atlas (via public descriptions), Figure, 1X NEO. The choice affects USD asset quality, commercial availability (for eventual hardware use), and narrative breadth.

**Decision**: Unitree G1 is the primary humanoid in sim. Other humanoids (Agility Digit, Apptronik Apollo, Boston Dynamics Atlas) appear as secondary scenario variants as assets become available.

**Consequences**:
- Commercially purchasable if Phase 4+ wants hardware integration.
- Strong community interest and published references.
- Chosen despite GR00T being specifically trained/supported on multiple humanoids — the serving architecture is embodiment-pluggable so we can add others.

---

## ADR-009: Sigstore-based signing + SPDX SBOMs as the supply-chain posture

**Status**: Accepted

**Context**: Enterprise and regulated-industry customers expect a concrete supply-chain story. Options range from no signing, to GPG-signed RPMs only, to a full Sigstore/SPDX/SLSA story.

**Decision**: Every image built by this project is Cosign-signed; SBOMs in SPDX JSON generated with Syft; images carry SLSA provenance attestations; `policy.sigstore.dev` admission controller enforces signatures cluster-side.

**Consequences**:
- Phase 0 includes Sigstore infrastructure — not a "we'll do it later" topic.
- Third-party NVIDIA images are mirrored into our registry with annotations noting upstream signatures where present.
- This is a talking point for every security-conscious customer; supports the Archetype C expert conversation directly.

---

## ADR-010: Fleet manager stays vendor-neutral; integrations via adapters

**Status**: Accepted

**Context**: Real factories have specific WMS / MES / SCADA systems (SAP, Oracle, KION, rockwell). Options: bake in a reference integration to one system, stay vendor-neutral and provide adapter interfaces.

**Decision**: The fleet manager is vendor-neutral. Specific integrations (KION, SAP, Siemens) are adapters implementing a defined interface, added per customer engagement — not shipped in the core reference.

**Consequences**:
- The core reference doesn't privilege any specific partner.
- Accenture, IBM Consulting, Deloitte can deliver partner-specific adapters as engagement-specific value.
- WMS stub provides enough function for demos; real-system integrations are Phase 4 conversation starters.

---

## ADR-011: Multi-site from Phase 2, not optional

**Status**: Accepted

**Context**: The multi-site story is one of Red Hat's sharpest differentiators. It would be simpler to skip ACM federation in the reference and add it only in customer engagements.

**Decision**: Multi-site with at least two spokes is a Phase 2 deliverable, non-optional.

**Consequences**:
- Lab hardware budget must accommodate two spoke clusters (even if they're SNO VMs nested on the hub via OpenShift Virtualization).
- Demos that depend on multi-site become core, not bonus.
- If the federation doesn't work, we find out early rather than in a customer PoC.

---

## ADR-012: Omniverse Kit App Streaming over thick-client VDI for demo delivery

**Status**: Accepted

**Context**: Showing an interactive Omniverse Kit app during a demo requires either a thick-client workstation (local or VDI) or Kit App Streaming (browser-based WebRTC).

**Decision**: Kit App Streaming is the demo delivery path. Thick-client VDI is not part of the reference.

**Consequences**:
- No per-seller workstation setup required; any browser works.
- GPU usage: one L40S per active streaming session during demos. Schedule accordingly.
- Customer-facing stability depends on WebRTC + the Route configuration; document carefully.

---

## ADR-013: Showcase Console is a first-class deliverable

**Status**: Accepted

**Context**: The sales-enablement layer could be an afterthought (generic slides + pointing at the repo) or a first-class product deliverable (a purpose-built tool).

**Decision**: The Showcase Console is first-class — built from Phase 1, grown each subsequent phase, and treated as the primary interface between Red Hat field teams and customers.

**Consequences**:
- Engineering effort for the Console is non-trivial and must be budgeted.
- Every phase has a Console workstream.
- Sellers need training (the three-stage training path).
- Future hires for this project should include a frontend-capable engineer alongside the infrastructure and ML folk.

---

## ADR-014: Siemens Xcelerator integration is Phase 4, not earlier

**Status**: Accepted

**Context**: Red Hat already has a Siemens relationship (Amberg). The temptation is to lead with a Siemens-specific integration.

**Decision**: Siemens-specific integration waits until Phase 4. The reference must be proven first — multi-vertical, multi-scenario, production-credible — before approaching Siemens for joint artifacts.

**Consequences**:
- Phase 1–3 work is vendor-neutral and broadly applicable.
- The Siemens conversation, when opened, comes from a position of substance: "here's what we already built; let's integrate your Xcelerator stack" rather than "let's build something together."
- Other partner conversations (Foxconn Fii, KION, Accenture) may open in parallel during Phase 3–4.

---

## ADR-015: RHOAI 3.4.0 EA1 is the committed distribution; MLflow is shipped via `odh-mlflow-rhel9`

**Status**: Accepted

**Context**: Red Hat OpenShift AI 3.4.0 Early Access 1 is installed on the hub cluster. MLflow is shipped as a Red Hat-published container (`rhoai/odh-mlflow-rhel9:v3.4.0-ea.1`, Beta release phase) — available via the Red Hat Ecosystem Catalog. This closes what was a hedged-open question in earlier drafts of this ADR.

**Decision**: The reference runs on RHOAI 3.4.0 EA1 on the hub. MLflow is the committed tracking and model-registry layer, deployed via the Red Hat-published container. Phase 1 work verifies the component is enabled in the installed DataScienceCluster; if not enabled by default, we enable it via the DSC component toggle rather than falling back to a standalone community chart.

**Consequences**:
- No standalone MLflow Helm chart. The Red Hat container is the supported path.
- EA channel posture applies: no Red Hat support, no CVE backports, no supported in-place upgrade path to GA (moving to GA will require fresh install). See R-14.
- MLflow backend is Postgres via CloudNativePG; artifact store is an S3-compatible bucket (ODF or OSD-equivalent).
- The `workloads/common/python-lib/tracking/` abstraction remains in place so consumer code is insulated from future RHOAI-internal MLflow implementation changes.
- Additional RHOAI 3.4 EA1 components worth knowing about (Feature Store, Models-as-a-Service, LLM Compressor, Llama Stack) are addressed in their own ADRs or OD entries; this ADR is strictly about MLflow.

---

## ADR-016: Cosign + SBOM + SLSA — what "secure supply chain" means in this project

**Status**: Accepted (extends ADR-009)

**Context**: Supply-chain security is broadly scoped. This ADR locks the specifics of what we actually do.

**Decision**:
- **Signing**: Cosign keyless (Fulcio) when building in GitHub Actions; Cosign with Vault-stored private key when building in in-cluster Tekton.
- **SBOM**: Syft-generated SPDX JSON attached as an image attestation.
- **Provenance**: SLSA-style provenance attestation generated in CI; includes build environment, source commit, dependencies.
- **Verification**: `policy.sigstore.dev` admission controller on all clusters; policies require at least one valid signature from our identity.

**Consequences**:
- This is the concrete answer to "tell me about your supply chain" in every security conversation.
- CI complexity goes up; cost is acceptable.

---

## ADR-017: OSD hub with self-managed companion cluster — reasons for keeping the companion

**Status**: Accepted

**Context**: The hub cluster is an internal Red Hat OpenShift Dedicated (OSD) instance on which we hold `cluster-admin`. This is a favorable environment: most customer-facing OSD restrictions (namespace-scoped admission, restricted SCCs, managed operator catalogs) don't apply because cluster-admin clears them. However, three realities persist:

1. **MachineConfigs on OSD remain fragile.** Even with cluster-admin, SRE's infrastructure automation manages host state on OSD. Custom MachineConfigs for STIG profiles, FIPS toggles, kernel tuning, or IOMMU reconfiguration can be reverted or cause conflicts. Treating MachineConfig-dependent work as OSD-appropriate is risky.
2. **OSD is inherently internet-adjacent.** It's a Red Hat-managed service with egress to Red Hat's observability and subscription systems. Claiming "air-gapped" about an OSD cluster is misleading; serious air-gap validation needs an environment where we control every network egress.
3. **Customer-facing narrative demands self-managed substrate.** Real industrial customers run self-managed OpenShift in factory datacenters. The reference must demonstrate the full stack on that substrate, not just on managed OSD. Without a companion, the "Red Hat can do this on-prem" story is narrative rather than demonstrated.

**Decision**: The reference runs primarily on the OSD hub, and maintains a **self-managed companion cluster** for specific purposes that OSD cannot credibly serve regardless of permission level. The companion cluster:

- Hosts the MachineConfig-based hardening demonstrations (STIG profile, FIPS mode, kernel tuning) — work that would be fragile on OSD due to SRE's automation.
- Serves as the true air-gap validation environment where we control all egress.
- Provides the "customer parity" demonstration — the reference running on the same substrate a customer would run in their factory datacenter.
- Hosts OpenShift Virtualization + vGPU Kit workstations *if* that capability is unavailable on this specific OSD instance (TBD — verify early in Phase 0).

Everything else — Nucleus, Isaac Sim (digital twin per ADR-027), GR00T serving, Cosmos NIMs, Cosmos Reason 2-8B (perception), obstruction-detector, fleet manager, MCP servers, the LangGraph orchestrator, Llama Stack governance, the Showcase Console, ACM hub, cluster-scoped Sigstore admission, full NetworkPolicy mesh — runs on the OSD hub where cluster-admin makes it straightforward.

**Consequences**:
- The companion cluster is justified on merits (self-managed customer parity, MachineConfig safety, air-gap integrity) rather than forced by OSD permission limits.
- Phase 0 includes a "provision companion" work item, but its scope is narrower than an earlier draft assumed: MachineConfig work, air-gap test harness, and optionally OpenShift Virtualization.
- `infrastructure/gitops/clusters/` still has hub, companion, spoke-a, spoke-b — the topology is unchanged from earlier drafts.
- ACM on OSD manages the companion as a spoke; this is itself a useful demonstration of "Red Hat managing managed + self-managed OpenShift as one fleet."
- The talk track simplifies: "the reference deploys on any OpenShift substrate; we demonstrate it across managed (OSD) and self-managed footprints side-by-side." Honest and strong.
- Companion host selection remains OD-8. With the narrower scope, GMKTec Evo-X2 as the default host covers more of the companion's purpose (MachineConfig + air-gap) without needing an NVIDIA GPU; ORIGIN PC is only required if we specifically want to demonstrate vGPU Kit workstations and it's not available on OSD.

**Supersedes**: earlier drafts of this ADR that characterized OSD as heavily restricted and framed the companion as a forced workaround. Those assumptions were based on a dedicated-admin access model that doesn't apply here.

**Amendment (Session 09, 2026-04-17) — companion FIPS install-time caveat**:

The companion runs RHCOS with day-1 FIPS (`fips: true`, `fips=1` on kernel cmdline, FIPS-validated crypto providers in the payload). The *install host* — Fedora 43 on the GMKTec Evo-X2 — cannot itself run in FIPS mode with sanctioned tooling: Fedora 42+ removed `fips-mode-setup`, and the FIPS-capable `openshift-install` variant (`openshift-install-fips` from the `openshift-install-rhel9` tarball) requires a RHEL host, not Fedora. The static `openshift-install` binary we use therefore fails its host-crypt check with `fips: Forbidden: ... use the FIPS-capable installer binary for RHEL 9 on a host with FIPS enabled`.

We bypass this check at render time with `OPENSHIFT_INSTALL_SKIP_HOSTCRYPT_VALIDATION=1`. The installer logs the violation as a warning and sets `install.openshift.io/hostcrypt-check-bypassed=true` on the cluster. This means ignition-bootstrap key material was generated on a non-FIPS host — immaterial for demonstrating FIPS posture (the running cluster is genuinely FIPS-enabled and Compliance Operator will score it accordingly), but material for a real CNSA audit of the install chain.

Session 11 records the bypass annotation and FIPS evidence side-by-side so a viewer can see both the posture and its caveat. Session 10's baseline capture records the annotation explicitly. A future rebuild of the companion host on RHEL 9 + proper FIPS installer variant would close this gap; that work is not on the Phase-0 critical path.

---

## ADR-018: GPU class targeting via GFD-provided `nvidia.com/gpu.product` labels

**Status**: Accepted

**Context**: The hub has 2–3 L40S nodes and 2–3 L4 nodes. Workloads need to target the right class. The NVIDIA GPU Operator's GFD (GPU Feature Discovery) component automatically applies `nvidia.com/gpu.product` labels — `NVIDIA-L40S` and `NVIDIA-L4` respectively — plus related labels like `nvidia.com/gpu.memory`, `nvidia.com/gpu.family`, and `nvidia.com/gpu.count`. NFD applies `feature.node.kubernetes.io/pci-10de.present=true` on any NVIDIA-GPU-bearing node.

An earlier draft of this ADR proposed introducing a custom `gpu-class=l40s | l4` label. That's worse: it duplicates information GFD already provides, creates drift risk on node replacement, and requires maintaining a parallel labeling pipeline.

**Decision**: Workloads target GPU class exclusively via the standard GFD labels:

```yaml
nodeSelector:
  nvidia.com/gpu.product: NVIDIA-L40S   # or NVIDIA-L4
resources:
  limits:
    nvidia.com/gpu: 1
```

No custom labels. No taint+toleration layer on top — GFD's labels are the authoritative selector, and the existing GPU Operator `nvidia.com/gpu` resource request provides the GPU-requirement gate.

**L40S-targeted workloads** (use `nodeSelector: { nvidia.com/gpu.product: NVIDIA-L40S }`):
- Omniverse Kit App Streaming render session
- Isaac Sim live demo instance
- Cosmos Reason 2-8B (VLM for perception / obstruction detection — Qwen3-VL-derivative; trial confirmed 2B on L4 lacks visual acuity for warehouse-aisle obstruction detection; 8B needs L40S per NVIDIA spec)
- GR00T N1.7 serving
- Cosmos Predict 2.5 NIM
- Cosmos Transfer NIM
- Isaac Lab training workers

**L4-targeted workloads** (use `nodeSelector: { nvidia.com/gpu.product: NVIDIA-L4 }`):
- LangGraph agent brain LLM (when selected model fits 24 GB)
- USD Search API embedding generation
- USD Code / USD Verify NIMs

**Consequences**:
- Zero custom labeling infrastructure. Labels survive node replacement automatically because GFD reapplies them.
- Selector strings are the canonical GPU product names — stable across GPU Operator versions for a given GPU model.
- The exact product-label string (`NVIDIA-L40S` vs `NVIDIA-L40S-XX` variants) must be confirmed during Phase 0 baseline capture via `oc get nodes -l nvidia.com/gpu.present=true -o json | jq '.items[].metadata.labels'` — document the exact strings in `infrastructure/baseline/osd-hub-state.md`.
- The Helm chart library in `workloads/common/chart-library/` exposes `gpuProduct` as a required value (not a free-form custom label) to force explicit choice at install time. The class-imbalance alert (Grafana) monitors for mis-scheduled workloads by correlating `kube_pod_spec_nodeSelector` with actual node `gpu.product` labels.
- Dev Mode A/B/C allocation (in `docs/08-gpu-resource-planning.md`) remains conceptually correct — the "L40S pool" and "L4 pool" are the two `nvidia.com/gpu.product` partitions of the cluster.

---

## ADR-019: Llama Stack as the HIL + safety layer around LangGraph-driven agents

**Status**: Accepted (Phase 3 workstream; scaffolding begins Phase 1)

**Context**: RHOAI 3.4 EA1 ships Llama Stack (upstream 0.3.5) with a distribution of capabilities relevant to our agentic orchestration story: Human-in-the-Loop tool-call approval, safety guardrails, PII detection, TrustyAI integration for evaluation, and a FIPS-compatible deployment pattern. LangGraph (ADR-005) remains the orchestration framework the team has standardized on.

For Loop 4 (agentic orchestration on physical-AI operations), the question is whether Llama Stack replaces LangGraph (it doesn't — ADR-005 holds), runs in parallel (messy), or wraps LangGraph as a safety and governance layer (the right answer). Real industrial customers will not allow LLM agents to modify fleet state without an operator approving the action; HIL is not optional for serious enterprise deployments of Loop 4.

**Decision**: LangGraph remains the orchestration framework (ADR-005 holds). Llama Stack is added as a **wrapping layer** around agent-initiated operations in Loop 4. Specifically:

- LangGraph graphs define the agent logic (what to plan, which tools to call, how to compose results).
- Llama Stack's Agents API provides the customer-visible interface for operator interactions — the HIL approval UX, guardrails on inputs and outputs, PII detection on any text the agent touches, audit trail integration.
- Tool calls that modify state (fleet interventions via `mcp-fleet`, scenario launches via `mcp-isaac-sim`, model promotions via `mcp-mlflow`) must pass through HIL approval unless explicitly allowlisted.
- Tool calls that are purely read-only (inspect fleet state, query MLflow, browse Nucleus) bypass HIL — no operator would want to approve every read.
- TrustyAI integration provides evaluation signal for agent outputs, feeding back into observability.

**Consequences**:
- Loop 4 becomes a two-layer stack: LangGraph (orchestration) + Llama Stack (governance). Slightly more complex than LangGraph alone; dramatically more defensible to enterprise customers.
- Phase 1 does not deploy Llama Stack. Phase 1's agentic elements are placeholders; real agentic work is Phase 3. But the Showcase Console's agent panel is designed from Phase 1 to accommodate HIL interactions when they come online.
- The HIL pattern itself becomes a differentiator to talk about — "Red Hat's posture is that LLM agents should ask operators before touching production" lands well with security-conscious customers.
- Llama Stack is FIPS-compatible in 3.4 EA1, which aligns with the companion-cluster FIPS story (ADR-017). Agentic demos for regulated customers can demonstrate the combination.
- OD-5 (agent brain model selection) gains a new criterion: the model must be compatible with Llama Stack's Agents API (most open-weight models with good tool-use are; check compatibility before committing).

---

## ADR-020: OpenShift Service Mesh 3 supersedes v2 for east-west traffic

**Status**: Accepted (supersedes ADR-006)

**Context**: ADR-006 chose OpenShift Service Mesh v2 (the Maistra-based Istio variant) for east-west traffic, with an explicit note that Service Mesh v3 was a valid option "if available."

Phase 0 Session 01 baseline capture (2026-04-17) found that **Service Mesh 3 is the version installed on the OSD hub** — `servicemeshoperator3.v3.3.1`, via the `stable` channel of the `redhat-operators` catalog. Service Mesh 3 is the Red Hat productization of upstream Istio built on the `sail-operator` pattern and supports both sidecar injection (the default) and ambient mode. It is not backward-compatible with v2 at the operator or CR level.

Installing v2 alongside v3 on the same cluster would be an anti-pattern: two control planes, conflicting sidecar injection webhooks, doubled operational cost. The pragmatic and strategically aligned choice is to honor what is installed.

**Decision**: OpenShift Service Mesh 3 (the `servicemeshoperator3` operator, currently `v3.3.1` on the hub) is the single mesh for east-west traffic. Sidecar injection remains the default workload-participation mode, preserving ADR-006's operational posture (mTLS, workload identity, east-west tracing). Ambient mode is evaluated per-workload as the reference matures; no blanket commitment either direction.

ADR-006 is superseded. All prior references to "Service Mesh v2" in the project docs should be read as "Service Mesh 3" going forward; a doc sweep happens naturally as Phase 0 sessions touch the affected files.

**Consequences**:

- All workload namespaces still participate via sidecar injection. Zero-trust posture from ADR-006 is preserved; Service Mesh 3 is a capability superset of v2, so nothing is lost.
- The CR topology differs from v2: `ServiceMeshControlPlane` (v2) → `Istio` + `IstioCNI` + `IstioRevision` + `IstioRevisionTags` (v3). Any mesh CRs in this repo must use v3 shapes from the start; there are none yet (pre-implementation), so no migration burden.
- Ambient mode becomes available as an option for workloads where sidecar overhead is costly — a live-demo Isaac Sim or Kit App Streaming pod with sidecar-induced GPU-adjacent latency is a plausible candidate. Any adoption of ambient-per-workload requires its own ADR so we don't drift into a mixed-mode posture by accident.
- FIPS compatibility is unchanged — Service Mesh 3 is FIPS-compatible, aligning with ADR-017 (companion) and ADR-019 (Llama Stack).
- Doc updates: `docs/01-architecture-overview.md`, `docs/04-phased-plan.md`, and any other file referencing "Service Mesh v2" get corrected as the Phase 0 session that lands mesh CRs touches them.

---

## ADR-021: SeaweedFS for in-cluster S3; ODF not installed here

**Status**: Accepted; updated 2026-09-29 for the user-requested object-storage migration.

**Context**: MLflow artifacts, training data, observability, and the warehouse camera library need an S3-compatible object store. The OSD hub uses EBS-backed StorageClasses (`gp2`, `gp3`); the Session 03 baseline found no ODF / NooBaa / RGW / Ceph CRDs. The original Phase 0 work established the S3 consumer contracts. This update selects their replacement backend; it does not assert that SeaweedFS ran during those historical sessions.

**Decision**: Use the shared Kustomize base at `infrastructure/gitops/components/seaweedfs/` for **SeaweedFS**, pinned to `docker.io/chrislusf/seaweedfs:4.48`, running `mini` with one replica per storage namespace. Its `deployment.yaml`, `service.yaml`, `pvc.yaml`, and `networkpolicy.yaml` are referenced by three consumer kustomizations. Warehouse uses the base defaults (`5Gi`, `s3-credentials`); MLflow and observability patch their credential Secret names and capacities. No object-storage operator or commercial license Secret is required. SeaweedFS 4.48 is [Apache-2.0 licensed](https://github.com/seaweedfs/seaweedfs/blob/4.48/LICENSE).

| Namespace | PVC capacity | S3 endpoint | Kubernetes credentials |
|---|---|---|---|
| `mlflow` | `200Gi` | `http://seaweedfs.mlflow.svc.cluster.local:8333` | Existing `mlflow-s3-credentials`; training consumers use `vla-training/s3-credentials` |
| `obs-storage` | `100Gi` (retained) | `http://seaweedfs.obs-storage.svc.cluster.local:8333` | `obs-s3-credentials` |
| `warehouse-data` | `5Gi` | `http://seaweedfs.warehouse-data.svc.cluster.local:8333` | `s3-credentials`, sourced from Vault path `warehouse/s3` under mount `kv` |

All three expose an S3-only ClusterIP Service named `seaweedfs` on port `8333`; administrative ports are not exposed by that Service. Credentials use `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`, projected from Vault; do not commit credential values. Loki's `VaultStaticSecret` projection fixes its endpoint to `http://seaweedfs.obs-storage.svc.cluster.local:8333`, so a stale Vault endpoint cannot override the migration. MLflow keeps `s3://mlflow-artifacts/`, training keeps the `vla-training` bucket, observability keeps its existing buckets, and camera images keep `warehouse-camera-library`.

Bucket initialization and helper Jobs use the official `public.ecr.aws/aws-cli/aws-cli:2.34.0` image with standard `aws s3` / `aws s3api` commands. Bucket-init Jobs run as Argo CD `Sync` hooks in wave `1`, with bounded retries and a 600-second timeout. Creating buckets during Sync avoids a new DSPA waiting for a bucket whose creation would otherwise wait for application health. S3 clients use the new endpoint while preserving bucket names, object keys, and artifact URIs. ODF remains outside this reference deployment; this change does not add storage to the companion cluster.

**Consequences**:

- Single-replica `mini` is a reference topology with a single point of failure, not an HA storage service. Production sizing, replication, backup, and restore validation remain separate work.
- Existing cluster stores are upstream-managed and shared. Follow a controlled S3 copy, verification, and consumer cutover; do not delete live stores or reuse their data directories as SeaweedFS storage. Retain source data and rollback configuration. Git history remains intact.
- SeaweedFS runs under `restricted-v2` with a `5Gi` `gp3` PVC in the isolated `showcase-storage-canary` namespace. On 2026-09-29, the S3 canary passed 15 checks including restart persistence, and 13 checks from `vla-training`. See the [validation evidence](../tools/object-storage/VALIDATION.md) and [controlled migration procedure](../tools/object-storage/README.md). This proves the tested S3 contract; live shared data and consumer cutover remain separate.
- VM transfer stays **S3 → workstation → SCP → VM local model**. An in-cluster AWS CLI helper reads bounded byte ranges; the workstation verifies and assembles each file before SCP. No direct cluster S3 access is required from the VM.
- Air-gapped deployments must mirror the pinned SeaweedFS and AWS CLI images. Nucleus and its USD asset workflow remain separate from these three S3 stores.

---

## ADR-022: Cluster Observability Operator UIPlugin over standalone Grafana for Phase 0

**Status**: Accepted (Session 07)

**Context**: Phase 0 Session 07 needed a dashboard surface for cluster / DCGM / class-allocation panels. Options: (a) upstream Grafana Operator (Community Operators only — no Red Hat support); (b) standalone Grafana via Helm (more infrastructure; another Route to manage); (c) Cluster Observability Operator's `UIPlugin` mechanism, which embeds Red Hat-supported dashboards directly into the OpenShift Console's Observe view.

**Decision**: Use CoO `UIPlugin` for Phase 0. `UIPlugin/logging` + `UIPlugin/monitoring` land under `infrastructure/gitops/apps/observability/ui-plugins/`. No standalone Grafana instance.

**Consequences**:
- Zero extra operator overhead for Phase 0 dashboards; everything is in-Console.
- Loses a dedicated Grafana URL — the Showcase Console (Phase 1+) eventually needs an embeddable dashboard URL, which will revisit this decision. Likely answer: add a standalone Grafana instance specifically for sales-view dashboards at that point, so we have one.
- CoO also ships Perses (CNCF dashboard engine) as a secondary path; not used in Phase 0 but available if Perses becomes relevant.

---

## ADR-023: Vault + Vault Secrets Operator as the Phase 0 secrets substrate

**Status**: Accepted (Session 08)

**Context**: Phase 0 sessions 06, 06b, and 07 all shipped placeholder credentials committed to Git (object-store root credentials for `mlflow` and `obs-storage`, MLflow S3 credentials, Loki S3 credentials, and an imperative cross-namespace mirror for `mlflow-db-app`). This is a conscious shortcut — not acceptable as a production pattern. We need a real secrets substrate before Phase 1 workloads ship.

Options evaluated:
- **HashiCorp Vault + Vault Secrets Operator (VSO)** — certified in `certified-operators` (`vault-secrets-operator.v1.3.0`). HashiCorp's official K8s client; designed for this use case.
- **External Secrets Operator (ESO)** — community-operators only (`v0.11.0`, alpha channel). Cross-provider but unsupported.
- **Sealed Secrets** — fine for the "commit an encrypted Secret" case; doesn't help sync from an external source.
- **OpenShift Secrets Store CSI Driver** — mounts secrets at pod startup, no Secret CR projection; doesn't fit downstream consumers that expect `envFrom: secretRef`.

**Decision**: Deploy HashiCorp Vault in-cluster (bare StatefulSet, single replica, file-backed storage, manual init/unseal) and Vault Secrets Operator (VSO) from the certified catalog. VSO's `VaultConnection` + `VaultAuth` + `VaultStaticSecret` CRs read KV secrets from Vault and project them as Kubernetes Secrets into tenant namespaces.

Session 08 lands the infrastructure + the warn-mode Sigstore policy + the NetworkPolicy templates. **Session 08b (next) executes the placeholder-to-Vault migration** after the operator initializes Vault (init/unseal is manual-only for Phase 0; production customers plug in their own Vault or use KMS-backed auto-unseal).

**Consequences**:
- The Phase 0 placeholder pattern is explicitly time-boxed — every committed placeholder gets a `TODO(ADR-023)` note pointing here.
- Single-replica file-backed Vault is for reference only. Customer deployments substitute their own Vault (HA Raft + KMS-unseal, or an existing enterprise instance).
- VSO's Kubernetes auth method is the canonical auth path — ServiceAccount tokens prove identity, no static credentials needed.
- One operational gotcha carries forward: pod restart re-seals Vault. Documented in `infrastructure/gitops/apps/platform/vault/README.md`.
- Cross-cluster Vault (companion + hub sharing a single Vault) deferred — each cluster runs its own Vault substrate unless a customer specifies otherwise.

---

## ADR-024: Nucleus deployed as native Kubernetes workloads, not the NVIDIA-sanctioned Compose stack

**Status**: Accepted

**Context**: Nucleus is NVIDIA's Omniverse USD asset server and is a Phase-1 foundation dependency (Isaac Sim, Kit App Streaming, USD Search, and downstream agents all reach it via `omniverse://` URLs). NVIDIA ships Nucleus as a Docker Compose stack from `nvcr.io/nvidia/omniverse/nucleus-*`. The Enterprise Nucleus planning guide is explicit:

> Compose files are designed for Docker Compose environments only and are not compatible with Swarms.

Every NVIDIA K8s reference deployment that touches Nucleus (DSX Blueprint, OV Portal on DGX Cloud AKS, USD Search, Kit App Streaming, VSS) treats Nucleus as an **external FQDN** reached via `omniverse://`. NVIDIA does not publish a Helm chart, operator, or Kubernetes manifest set for Nucleus itself.

This leaves two realistic deployment paths on our Phase-1 reference:

- **Path A (NVIDIA-sanctioned)**: run Enterprise Nucleus in a KubeVirt VM on the companion cluster, expose via FQDN, all hub workloads consume the URL. Matches the OV Portal DGX Cloud pattern exactly. Zero off-spec risk.
- **Path B (Red Hat-differentiated)**: package the same `nvcr.io/nvidia/omniverse` container images as individual K8s Deployments on the hub, managed by Argo CD, mesh-enrolled, Sigstore-verified, observability-federated. Off-spec per NVIDIA; Red Hat owns the operational surface.

Red Hat's RHEcosystemAppEng team produced a proof-of-concept Helm chart for Path B (`github.com/RHEcosystemAppEng/nvidia-omniverse-nucleus/tree/main/deploy-native`). It is a PoC, not a product: it pins to 2023.2.7, omits two services from the 2023.2.9 stack (`ingress-router` and `auth-router-gateway`), uses imperative secret generation, and lacks Service Mesh / NetworkPolicy / Vault integration.

**Decision**: Adopt **Path B**. Phase 1 delivers a forked, completed Helm chart under `infrastructure/gitops/apps/platform/nucleus/`, reconciled by Argo CD, that runs NVIDIA's Nucleus 2023.2.9 container set as native Kubernetes workloads on the hub.

We accept that we own every consequence of diverging from NVIDIA's sanctioned packaging. We judge the differentiation worth it: K8s-native Nucleus is an operational surface NVIDIA itself does not provide, and is a concrete substantiation of the charter's differentiator #8 ("Day-2 lifecycle done right — operators for every component, GitOps-driven updates, rolling patches without stopping production") that Path A cannot match.

**Consequences**:

- **Off NVIDIA spec, permanently**. Red Hat owns the repair path for any Nucleus-internal behavior that changes between Compose releases. NVIDIA support will decline K8s-specific issues.
- **Version-drift maintenance is a running cost.** Every NVIDIA Nucleus patch means reading the Compose-file diff and mirroring changes (new env vars, new services, new args) into our chart. Acceptable because the release cadence is slow (2023.2.x has shipped 9 patches over 18 months) and the chart is small (~15 manifests).
- **Storage constraint is real and unfixed.** NVIDIA explicitly forbids NFS/SMB/iSCSI for Nucleus because of fsync semantics; customer-reproducible patterns are therefore RWO block + all pods co-located on one node via subPath mounts. This is a single-point-of-failure at the node level, it limits cross-node scaling, and it is the pattern we ship. We flag this in the chart README and the Session 16 baseline so reviewers understand the compromise.
- **Two services from NVIDIA's PB 25h1 Compose (`ingress-router:1.1.4`, `auth-router-gateway:1.4.7`) are intentionally not reproduced.** Session-16 follow-up research determined both are architecturally redundant on OpenShift: `ingress-router` is an NGINX path-based reverse proxy that our OpenShift Routes (`routes.yaml`) functionally replace; `auth-router-gateway` is a SAML SSO broker that's only active when the cluster is federated to an external SAML IdP. Phase-1 uses local Nucleus auth → zero runtime effect. If Phase 3+ demands SSO, we federate via Red Hat build of Keycloak → Nucleus's native OIDC flag rather than shipping SAML. The two images are also NGC-Enterprise-entitlement-gated, so adoption would require a rep-ask path we now avoid.
- **Companion's KubeVirt still has a VM demo story to own** (Phase 4+ legacy-MES emulation, Unitree G1 sim, VDI/Kit workstations). ADR-017's "companion hosts VMs" posture is unchanged; ADR-024 just chooses that Nucleus is not one of those VMs.
- **Imperative deploy script (`deploy.sh`) is discarded.** Argo reconciles. Every secret is VSS-sourced from Vault. Every manifest is kustomize-wrapped. GitOps is the authoritative state.
- **Showcase narrative gets strengthened.** An evaluator asking "why not just run the Compose stack on a VM?" gets a concrete answer: "because K8s-native is observable, mesh-protected, Sigstore-verified, and rolling-updatable per service — Red Hat built what NVIDIA didn't."
- **We will record any post-install operational friction** in an ongoing `infrastructure/gitops/apps/platform/nucleus/KNOWN-ISSUES.md` so the cost of Path B is visible, not hidden.

**Supersedes / interacts with**:

- Phase 1 work-item 1 in `docs/04-phased-plan.md` ("Nucleus validation and codification") — text said "existing Nucleus deployment"; there is none, so Session 16 is greenfield. No migration needed.
- ADR-017 (OSD hub + companion) — unchanged. Companion still hosts VMs (Phase 4 workloads), just not Nucleus.
- Session 16 is split into five PRs (A–E): ADR + NGC doc (this); chart foundation; router-gateway fill-in; security hardening; Service Mesh enrollment.

**Open items tracked separately** in `09-risks-and-open-questions.md`:

- Getting the PB 25h1 Compose manifest from NGC (requires authenticated pull; cross-check our 12-service tag set).
- Kit × Nucleus × Isaac Sim 6.0 compatibility matrix (unpublished; rep-ask).
- `ovstorage` GA timeline (H2 2026 targeted) and whether USD Search / Kit App Streaming adopt it as a backend (could supersede this ADR in Phase 3+).

---

## ADR-025: Companion cluster is the per-factory robot-edge deployment target

**Status**: Accepted

**Context**: ADR-017 established the hub-plus-companion topology. Through Phase 0 the companion earned the security-posture role (FIPS, STIG, air-gap, Sigstore enforce). Through Session 12 it gained KubeVirt. But up through the end of Session 16, the companion had no *workload role* in the demo narrative — it was a cluster with capabilities and no story. That was a smell.

The topology already tells the hybrid-cloud-to-factory-edge story we sell; it just needs workloads to fill it. The hub is the datacenter/cloud side — Isaac Sim (L40S-heavy), Kit streaming, MLflow, Fleet Manager, Mission Planner orchestration. The companion is the factory-edge side — closer to the robot by topology, latency-bounded, air-gap-capable, GPU-budget-appropriate for per-robot inference (single L4 class).

**Decision**: The companion cluster represents **the per-factory edge deployment target for robot workloads**. Concrete role assignments:

- **Robot-brain inference serving (VLA + scene reasoning)** runs on companion via RHOAI KServe + vLLM. Companion's L4-class GPU carries the load. Primary VLA is an open model (OpenVLA / pi-0 / SmolVLA) per licensing-gates doc; NVIDIA GR00T slots in as an interchangeable alternative if a commercial path resolves.
- **Cross-cluster message flow**: Fleet Manager on hub dispatches missions via Kafka MirrorMaker (or equivalent) to the companion's mission topic; Mission Dispatcher on companion routes to the local inference endpoint; action and telemetry flow back to hub for observability and MLOps feedback. This is the hybrid-cloud/factory-edge topology made concrete.
- **KubeVirt on companion hosts a legacy-controller VM** (ADR-017's "containers + VMs + vGPU on one platform" differentiator gets a concrete demo moment): a Windows or legacy-Linux VM that represents a factory-floor PLC / SCADA gateway the robot coexists with. This VM is Phase-2 scope; not a Phase-1 blocker.
- **Security posture framing shifts**: companion's FIPS / STIG / air-gap / Sigstore-enforce work is now positioned as "the factory-side cluster posture" — answers the OT / industrial-control-system security question specifically, not abstract Red Hat security flex. The sales differentiator-mapping task (#19) will formalize this framing.
- **Cross-cluster federation**: Fleet Manager on hub uses ACM-mediated connectivity; cross-cluster Argo (Session 13) already delivers companion manifests from Git; MCO (Session 14) already federates metrics. No new cross-cluster infrastructure needed — we fill the already-built plumbing with real workloads.

**Consequences**:

- **Every piece of companion infrastructure (Sessions 9–16) earns a demo role.** FIPS, STIG, Compliance Operator, mesh enrollment, KubeVirt, LVMS, cross-cluster Argo — each now has a sales story tied to "this is how you run the robot-edge side of a factory."
- **Phase-1 plan shifts for item 10 (Robot Brain serving)**: the InferenceService lives on companion, not hub. Fleet Manager and Mission Dispatcher on hub call it cross-cluster.
- **Phase-2 plan gains a VM workload**: one KubeVirt VM on companion standing in for a legacy controller. Low-cost to stand up; high-value demo moment.
- **The "hybrid cloud → factory edge → robot" differentiator** is no longer a diagram — it's a live topology a seller can walk through. Hub is the cloud/datacenter cluster; companion is the factory-edge cluster; Jetson-class edge is the eventual on-robot target (Phase 2+ MicroShift).
- **Companion's CPU-only posture stays intact** except for the one L4-class GPU we allocate for VLA serving. No L40S work moves to companion — Isaac Sim, Cosmos Predict/Transfer, Kit streaming all stay hub-side.
- **Air-gap demonstration story is strengthened**: "the robot-edge cluster at a real factory is air-gapped; the same reference ships there as to our hub." The companion is the site where air-gap validation happens.
- **This ADR does not commit to a physical second cluster** — the companion remains the GMKTec Evo-X2 KVM SNO per ADR-017 for now. Phase 2 may provision additional spoke clusters (spoke-a / spoke-b) representing additional factories, each a companion-like SNO.

**Supersedes / interacts with**:

- ADR-017 amendment (FIPS bypass) — unchanged. Companion's security role is re-framed but the technical posture is the same.
- Phase 1 work-item 10 — re-scoped: VLA + Cosmos Reason 2 deploy on companion, not hub. Phased-plan edit tracked in task #20.
- Optional demo-narration supplement: if a specific demo beat benefits from explaining model placement by frequency tier (mission planner at 0.25-1 Hz / VLA + scene reasoning at 10-50 Hz / on-robot WBC at 200-250 Hz), the cloud/datacenter vs factory-edge split this ADR commits to maps cleanly onto that framing. Use per beat; not an architectural commitment.

---

## ADR-026: VLA serving runs host-native on companion Fedora host; pod-native serving deferred to Jetson Thor (Phase 3/4)

**Status**: Accepted

**Context**: ADR-025 committed VLA serving to the companion cluster via RHOAI KServe + vLLM. Probing the companion hardware and researching the ecosystem for Phase-1 planning surfaced three facts that make the pod-native vLLM path unworkable on the current companion:

1. **The companion's actual OS stack is two-layer**: a Fedora 43 host (kernel 6.19.8, `amdgpu` + `amdxcp` loaded, ROCm HSA agents visible for Zen 5 CPU, Radeon 8060S gfx1151 iGPU, and XDNA 2 aie2 NPU) runs an SNO cluster as a RHCOS 9.6 VM (kernel 5.14). The host has a complete working ROCm stack — the user already serves 120B- and 235B-parameter LLMs via source-built llama.cpp (`GGML_HIP=ON`, linked to `libhipblas`/`librocblas`/`libamdhip64`/`libhsa-runtime64`) and ollama 0.18.1's ROCm runner. llama.cpp reports 102 400 MiB GTT-addressable memory. The SNO VM, on kernel 5.14, cannot reach the GPU — pods inside SNO see no AMD device, and no supported device-plugin path bridges the kernel gap.

2. **vLLM does not serve OpenVLA**, independent of hardware: upstream vLLM closed the OpenVLA support request as "not planned" on 2026-03-30 (issue `vllm-project/vllm#14739`). OpenVLA's fused DINOv2 + SigLIP vision tower is specifically the multi-vision-tower case vLLM has parked. Separately, vLLM on gfx1151 crashes at startup (`lemonade-sdk/vllm-rocm#3`, April 2026) — both a model-support gap and a hardware-support gap simultaneously.

3. **AMD GPU Operator for OpenShift is Instinct-only.** The 1.4.1 release notes and the Red Hat OpenShift 4.20 docs list MI210 / MI250 / MI300 / MI35X; no RDNA, no APU, no gfx1151. The supported consumer path is manual `ROCm/k8s-device-plugin` DaemonSet manifests — possible, but it's a blank-sheet integration, not a paved path. Operator-less parity with the NVIDIA GPU Operator story does not exist for Red Hat customers today on AMD consumer/APU edges.

A naive re-plan would propose replacing SNO with MicroShift directly on the Fedora host so pods inherit the modern kernel. That path was considered and rejected: MicroShift intentionally does not ship OpenShift Virtualization / KubeVirt, and the companion's KubeVirt role (legacy PLC-gateway VM, Purdue-model overlay beat in the 20-min demo's Segment 4) is a load-bearing brownfield-integration differentiator. Trading the brownfield story for ROCm parity would weaken a higher-value beat to fix a lower-value one.

A second alternative — iGPU passthrough into the SNO VM via VFIO — was considered and rejected: iGPU passthrough is fragile, strips the host of GPU access (breaking the user's existing LLM workflows), and does not remove the AMD-on-OpenShift operator gap. Would trade reliability for an architectural purity we don't need.

**Decision**: For Phase 1, **VLA serving on the companion runs as a host-native systemd service on the Fedora 43 host**, not as a KServe InferenceService inside the SNO cluster. Specifically:

- **Serving runtime**: PyTorch + transformers + ROCm (HIP backend), wrapping OpenVLA's reference `deploy.py` REST server. Exposed as an HTTP endpoint on the host bridge network. llama.cpp (already on the box) is used for non-multimodal model paths — e.g., text-only agent brains in Phase 3 — but not for OpenVLA's multimodal path in Phase 1.
- **Packaging**: podman-managed systemd unit in `workloads/vla-serving-host/`, Ansible-provisioned, described in Git. Not a Helm chart, not a KServe manifest. GitOps remains the source of truth for the cluster side; the host-level VLA runtime is managed parallel to it via Ansible.
- **Wiring**: **Mission Dispatcher pod inside the SNO cluster HTTP-calls the host VLA endpoint** via the bridge network. The cluster-side components (Mission Dispatcher, Fleet Manager, Kafka, MES-stub, KubeVirt PLC-gateway VM, Service Mesh) all continue to live inside SNO per ADR-025; only the inference runtime moves out.
- **Narration contract** (for demos that reference this): the 5-min and 20-min scripts surface this honestly — *"the robot-brain runtime lives on the edge node itself, using the ROCm stack that ships with the hardware. In this reference the serving is host-local because AMD consumer accelerators don't yet have first-class Kubernetes device-plugin parity with NVIDIA. On a Jetson edge it'd be a MicroShift pod; on a dedicated x86 + dGPU edge it'd be an SNO pod. The platform story is consistent — OpenShift orchestrates the cluster side, the serving runtime lives where the hardware is fastest."*
- **Phase 1 primary VLA**: OpenVLA-7B in bf16 as the default, sized to fit comfortably in the 102 GiB GTT-addressable memory. SmolVLA-450M and π0 provisioned as pluggable alternatives for the 60-min live-swap beat in Phase 3.
- **A second, pod-native edge pattern arrives with Jetson Thor**: a Jetson AGX Thor Developer Kit has been ordered. When it lands, it joins the reference as a second edge target running MicroShift + NVIDIA GPU Operator + KServe + vLLM-for-multimodal with CUDA-native serving. The 60-min Segment-4 live-swap beat then becomes *"the same open VLA serving on an AMD edge host, then on the Jetson Thor edge pod"* — demonstrating substrate-heterogeneity as an honest story, not a papered-over gap. Thor is a Phase 3 / Phase 4 materialization; it does not block Phase 1.

**Consequences**:

- **Phase 1 starts without waiting on hardware or on a companion rebuild.** The Fedora host already has the ROCm stack running workloads heavier than OpenVLA — inference on the iGPU is a known-working path. Phase 1 item 10 becomes "provision a host-native VLA systemd unit + bridge-network route from SNO"; no device-plugin integration, no SNO rebuild, no RHCOS kernel layering.
- **The brownfield + KubeVirt story is preserved intact**: SNO stays, `kubevirt-hyperconverged` keeps running in `openshift-cnv`, the 20-min Segment-4 PLC-gateway VM beat is unaffected.
- **ADR-025 remains correct in intent** (companion IS the per-factory edge target) but its claim that serving runs *inside the companion cluster* is partially superseded for Phase 1: serving runs on the companion *node*, not inside the companion *cluster*. The architectural distinction is worth naming honestly — serving lives at the edge (correct per ADR-025's intent), below the OpenShift layer (pragmatic given the AMD-consumer operator gap).
- **vLLM is off the Phase-1 VLA-serving path entirely.** It may return in Phase 3 for the Thor edge or for hub-side dev workloads (L4 / L40S) where the OpenVLA-support gap can be addressed with a custom vLLM build, but it's not the Phase 1 runtime. KServe's custom-predictor pattern remains the design target for *eventual* pod-native VLA serving.
- **A new differentiator surface emerges**: "substrate heterogeneity across edges" — the reference demonstrates two honest edge patterns (AMD consumer APU host-native via ROCm; NVIDIA Jetson Thor pod-native via CUDA). This reinforces differentiator #6 (open model choice) and adds a "choose-your-silicon" dimension to differentiator #3 (hybrid cloud → factory edge → robot, one operational model — across *heterogeneous* substrates, not uniform ones).
- **A gap is named honestly in the sales-enablement posture**: *"AMD consumer/APU hardware on OpenShift does not have first-class NVIDIA-parity operator coverage today."* Archetype-C customers evaluating AMD-edge deployments get a straight answer rather than vendor deflection. The `docs/sales-enablement/security-posture.md` Phase-2 doc and an objection-card entry will capture this.
- **Phase 2 gains no new items from this ADR.** Phase 2's multi-site + MLOps + brownfield beats are unaffected. Phase 3 gains a Thor-bring-up item when the hardware arrives (provision MicroShift, install NVIDIA GPU Operator, wire to ACM, deploy VLA via KServe custom predictor + vLLM-or-transformers); Phase 4's physical-robot integration (Unitree G1 or alternate) pairs with Thor as the compute brain.
- **XDNA 2 NPU exposure is explicitly deferred.** It's a DSP-class HSA agent visible to ROCm but has no production Kubernetes device-plugin story as of April 2026. Parked as a Phase-5 exploration item if FastFlowLM or equivalent upstream matures.

**Supersedes / interacts with**:

- ADR-025 — companion-as-robot-edge role intact; serving-location specifics for Phase 1 amended (host-native, not pod-native).
- ADR-024 — Nucleus codification unaffected.
- Phase 1 work-item 10 in `04-phased-plan.md` — rewritten to reflect host-native serving, bridge-network wiring, and Ansible-managed podman systemd unit.
- `docs/licensing-gates.md` — OpenVLA remains primary; GR00T remains optional-pluggable; SmolVLA + π0 added as pre-provisioned pluggable alternatives for the 60-min live-swap beat.
- Future Thor-arrival ADR will formalize the second edge pattern when the hardware is in hand.

---

## ADR-027: Warehouse-obstruction demo as a real closed-loop across hub + companion

**Status**: Accepted

**Context**: Phase 1's 5-min demo originally imagined a single Isaac Sim process on the hub emitting scripted camera events that Fleet Manager consumed directly. Session-18 planning retired that in favor of a real event-driven pipeline. Driving forces:

1. **"Smoke and mirrors" was explicitly rejected.** The showcase's value is demonstrating a substrate real customers can ship on; a scripted choreography where buttons trigger pre-recorded outcomes doesn't substantiate anything.
2. **The companion cluster's role was at risk of being faked as hub namespaces** — a suggested simplification for presenter portability. Rejected; the hub↔edge split is load-bearing for differentiator #3 and must stay real.
3. **Companion hardware can't run Isaac Sim.** The GMKtec Evo X-2 is Strix Halo / gfx1151 (AMD iGPU, no NVIDIA GPU); Isaac Sim requires CUDA + Omniverse RTX. Hosting the digital twin on the hub (where L40S lives) is the only option for Phase 1. Phase-2+ AGX Thor changes this.
4. **A single "obstruction" scenario needs presenter-controlled pacing** — a hard-coded timer kills the narration. Industrial AMR fleets use approach-point pauses for traffic coordination; that real pattern solves both the pacing problem and the architectural-parity problem.

**Decision**: For Phase 1, the warehouse-obstruction demo is wired as follows:

- **Hub (OSD, "HQ data center") runs**: Isaac Sim on L40S as digital twin, Cosmos Reason 2-8B on L40S for VQA obstruction detection (see trial note below), a dedicated `obstruction-detector` pod consuming camera frames and calling Cosmos Reason (separate from Fleet Manager — perception is its own service role), Fleet Manager with replan-on-alert logic, WMS-stub, Showcase Console, S3 storage for the camera-image library (SeaweedFS is the 2026-09-29 migration target per ADR-021), Nucleus for USD assets.
- **Companion ("on-site warehouse edge") runs**: a fake-camera service publishing AI-generated photorealistic warehouse photos to Kafka at ~1 Hz (with an HTTP control endpoint for state switching), the Mission Dispatcher with a new Waypoint Planner module (5 Hz pose emission, configurable), OpenVLA host-native for manipulation policy (not mobile-base navigation — Waypoint Planner handles navigation), and the companion side of Kafka federation.
- **Digital twin stays on hub** for Phase 1. In real deployments the twin co-locates with GPU hardware; the data-center digital-twin pattern is industry-standard (Siemens Teamcenter Digital Reality Viewer, the Mega Blueprint reference, Foxconn). Architecture is not locked out of moving Isaac Sim to companion when Thor arrives.
- **Robot is Forklift_A01 (`fl-07`), not Nova Carter.** Forklifts are the right actor for a "retrieve pallet" narrative; AMRs are delivery platforms that don't pick pallets. Nova Carter references throughout scenarios/events/Console UI are retired.
- **Warehouse USD** is `Isaac/Environments/Digital_Twin_Warehouse/small_warehouse_digital_twin.usd` (44 MB, NVIDIA's digital-twin-branded warehouse) fetched from Isaac assets CDN once, then re-hosted on Nucleus so Nucleus stays in the story.
- **Camera frames are AI-generated photorealistic images** (SDXL/Flux/Midjourney class), not renders from Isaac Sim. The twin-vs-reality visual separation is realistic — real cameras show grime, the twin shows clean USD. That separation reinforces the digital-twin narrative rather than weakening it.
- **Cosmos Reason 2-8B on L40S supersedes Cosmos Reason 1-7B on L4.** Cosmos-Reason2 is a Qwen3-VL-derivative (not Qwen2.5-VL as initially assumed); requires **vLLM ≥ 0.11.0** and the `--reasoning-parser qwen3` invocation. NVIDIA specs 32 GB minimum; does not fit L4's 24 GB. A trial of Cosmos-Reason2-**2B** on L4 confirmed it lacks the visual acuity to detect a pallet obstruction in a photorealistic warehouse aisle (0.97 "no obstruction" confidence on both empty and pallet-blocked images). The **8B on L40S** is the Phase-1 path: same `cosmos-reason` namespace, served-model-name `cosmos-reason-2` (stable across variants so downstream clients don't flip), bfloat16, `--max-model-len=8192` (image-token footprint exceeds the 4096 default), `--gpu-memory-utilization=0.9`, `--limit-mm-per-prompt '{"image":1}'` (JSON syntax required by vLLM 0.11).
- **`warehouse-topology.yaml` is the single source of truth** for aisle/dock/approach-point/camera coordinates + forklift id. Imported by every component that references a named location — wms-stub scenarios, Fleet Manager, Mission Dispatcher, scene-pack overlay USD, Console.
- **Approach-point pause pattern for presenter pacing**: forklift drives to the aisle-3 approach-point and pauses awaiting coordinator clearance (real AMR traffic-management behavior — Omron, Seegrid, MiR, AutoGuide all do this). Presenter narrates during the pause for as long as needed, then clicks "Drop Pallet" which switches the fake-camera's published frame. Cosmos Reason detects, Fleet Manager replans with aisle-4, forklift reroutes. Replan-in-flight is preserved as the demo's core beat.

**Consequences**:

- **Phase 1 work breakdown expands** with four new services/assets: fake-camera (companion), obstruction-detector (hub), Waypoint Planner module inside Mission Dispatcher, twin-update subscriber inside the Isaac Sim scenario. `warehouse-topology.yaml` and a scene-pack overlay USD join the asset set.
- **Cosmos Reason upgrade validated 2026-04-20.** Reason2 is Qwen3-VL-derivative (not Qwen2.5-VL as initially believed); vLLM image bumped from `v0.8.5` to `v0.11.0`. Args changed: added `--reasoning-parser qwen3`, changed `--limit-mm-per-prompt` to JSON syntax, raised `--max-model-len` from 4096 to 8192. The 2B variant was trialed on L4 and failed the visual-acuity bar; 8B on L40S is the Phase-1 choice.
- **Federation latency is narrated, not hidden.** MirrorMaker2 adds 200-800 ms between alert and reroute; that's realistic HQ↔edge behavior and part of the talk track.
- **OpenVLA's role is clarified**: it represents the manipulation policy (pick/place/grasp — where 7-DOF action vectors make sense), called in the loop on pick. It does not drive mobile-base navigation; the Waypoint Planner does. This matches how real AMR stacks layer VLA on top of Nav2-class planners.
- **Camera-orbit smoke test retires** once real telemetry drives forklift motion in the twin.
- **WebRTC "Open full Isaac Sim" path stays plumbed but hidden from UI** — revisited post-demo. MJPEG viewport-capture remains the Console's Stage view.
- **No Phase-2+ or later ADR is blocked.** When AGX Thor arrives on companion, Isaac Sim moves to companion, the `warehouse.cameras.*` federation hop drops, camera streams stay where they'd originate IRL. This ADR does not lock that out.

**Supersedes / interacts with**:

- ADR-017 — companion-cluster strategic rationale intact; Session 18 concretizes what companion runs for the warehouse demo.
- ADR-025 — companion-as-robot-edge role extended with fake-camera + Waypoint Planner responsibilities.
- ADR-026 — OpenVLA host-native serving unaffected; its role in the pipeline is now explicit (manipulation, not navigation).
- Phase 1 work-items 3, 6, 7, 8, 9 in `04-phased-plan.md` — rewritten to reflect the split services and topology.
- `demos/warehouse-baseline/script.md` — rewritten for the approach-point-pause + presenter-button narrative.
- `docs/02-component-catalog.md` — Nova Carter entry retired; Forklift_A01, fake-camera, obstruction-detector, Waypoint Planner, twin-update subscriber, warehouse-topology.yaml, scene-pack overlay USD added.

---

## ADR-028: Warehouse-only for Phase 2; second scene deferred to Phase 4

**Status**: Accepted

**Context**: The persona reviews flagged single-scene as a gap that could pigeonhole the platform as "a warehouse demo." Phase 2 plan item E.1 required researching what NVIDIA SimReady ships publicly beyond the Warehouse Pack — specifically whether a discrete-assembly or process/packaging scene exists that's usable without USD authoring.

**Research findings**:

1. **Isaac Sim 6.0 sample assets** ship one complete industrial environment: `Isaac/Environments/Digital_Twin_Warehouse/small_warehouse_digital_twin.usd`. This is what Phase 1 uses.
2. **SimReady on Omniverse Exchange** offers individual assets (robots, conveyors, shelving, sensors) but not composed scene packs ready to drop into a digital-twin pipeline. Building a second scene from SimReady primitives would require significant USD composition work — camera placement, navigation meshes, physics tuning, lighting.
3. **NVIDIA's published industrial reference architectures** (Mega Blueprint, Isaac Sim tutorials) all use the same warehouse scene or minor variations of it. No publicly available assembly-line or packaging-facility scene exists at the fidelity level needed for a believable demo.
4. **Third-party USD scenes** (TurboSquid, Sketchfab) exist for factories but lack SimReady metadata (physics properties, semantic labels) required by Isaac Sim's simulation pipeline.

**Decision**: Phase 2 commits to warehouse-only. The scene-pack infrastructure already supports multi-scene (ConfigMap-driven scene selection, `generate_overlay.py` parameterized by topology YAML). A second scene is deferred to Phase 4, where it can be authored as part of the vertical-expansion work or adopted if NVIDIA ships additional SimReady environments.

**Consequences**:
- D.4 (Console scene selector) is skipped for Phase 2 — no second scene to select.
- The demo narrative addresses the single-scene gap directly: "This warehouse is one vertical. The scene-pack infrastructure is parameterized — a packaging line, an assembly cell, or a customer's own USD scene plugs in through the same topology config."
- Phase 4 component catalog entries #50 ("Electronics Manufacturing Line") remain planned.
- The fleet-scale operating-math doc (E.2) can reference multi-scene as a scaling axis without requiring a live second scene.

---

These are decisions we're aware of but not yet making — they're documented in `09-risks-and-open-questions.md` rather than being forced here.

- Physical hardware: do we buy a Unitree G1 for Phase 4 hardware integration?
- Console naming: "Showcase Console" vs "Forge" vs other — marketing decision.
- Companion cluster host (ADR-017): GMKTec Evo-X2 vs ORIGIN PC vs dedicated lab hardware — deferred to Phase 0 provisioning.
- ACM's replacement (if one emerges in Red Hat's roadmap): not a current concern.

---

## ADR template for future additions

```
## ADR-NNN: Title

**Status**: Proposed | Accepted | Deprecated | Superseded by ADR-MMM

**Context**: What problem does this decision address?

**Decision**: What is the decision?

**Consequences**: What follows from it, positive and negative?
```
