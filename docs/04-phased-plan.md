# 04 — Phased Plan

Five pre-launch phases plus a formal post-launch iteration bucket. Each pre-launch phase ends in a demoable state and at least one sales-enablement artifact. The three demo scripts in `demos/` are the scope gates: Phase 1 delivers what the 5-min script needs, Phase 2 delivers the 20-min, Phase 3 delivers the 60-min. Nothing lands in a phase that doesn't earn its way into one of those three scripts or explicitly support them.

Phase 5 is new. It exists because the showcase is a living artifact — it goes public with what Phases 0–4 produce, and it keeps getting better afterward. Items that matter for long-term credibility but don't gate a demo land there.

## Phase 0 — Foundation

**Status**: complete as of Session 15 close (2026-04-18).

**Goal**: both clusters (OSD hub + self-managed companion) are fit for purpose. GitOps, operators, observability, storage, security baseline, and cross-cluster registration are all in place. Nothing application-level yet.

**Entry criteria**
- Hub OSD cluster is provisioned with 2–3 L40S and 2–3 L4 GPU nodes.
- Existing Nucleus deployment is identified and documented.
- NVIDIA GPU Operator is already installed on OSD hub (pre-existing).
- Red Hat OpenShift AI 3.4 is already installed on OSD hub (pre-existing).
- Companion cluster host is selected (per ADR-017).
- Git repository is initialized following `docs/06-repo-structure.md`.

**Work breakdown**

1. **Hub (OSD) validation and documentation** — hardware inventory, GFD label confirmation (`nvidia.com/gpu.product`), GPU Operator ClusterPolicy verification, RHOAI 3.4 EA1 DataScienceCluster state confirmation, GPU scheduling smoke tests, OpenShift Virtualization availability check.
2. **Companion cluster provisioning** — self-managed OpenShift on the selected companion host, MachineConfig STIG baseline, FIPS mode where applicable, GPU Operator on companion if GPU present, OpenShift Virtualization (HyperConverged CR), state captured in `infrastructure/baseline/companion-state.md`.
3. **Operator installs via OpenShift GitOps bootstrap** — NFD, ODF (or delta to SRE-provided StorageClasses), Pipelines, Service Mesh, Logging (Loki), OpenTelemetry + Tempo, Grafana, CloudNativePG, ACM (hub), AAP, AMQ Streams operator.
4. **GitOps skeleton** — Argo CD installed, ApplicationSet pattern established, cluster dirs `clusters/hub/`, `clusters/companion/`, `clusters/spoke-a/` and `clusters/spoke-b/` scaffolded for Phase 2.
5. **Security baseline** — Cosign keys, `policy.sigstore.dev` admission (warn on hub, enforce on companion), default-deny NetworkPolicy, least-privilege SCCs, internal registry on both clusters.
6. **Observability baseline** — user-workload monitoring on OSD, Thanos federation (hub↔companion, spokes added Phase 2), Grafana dashboards including GPU-class allocation.
7. **Multi-cluster registration** — ACM on OSD registers companion; cross-cluster Argo reconciliation validated.
8. **Documentation** — prerequisites, cluster-setup, gitops topology README, baseline state docs.

**Exit criteria**: every installed operator on both clusters healthy and Git-reconciled; DCGM exporter shows all GPUs in Grafana grouped by `nvidia.com/gpu.product`; test Jobs schedule correctly on both L40S and L4 classes; OpenShift Virt availability answered and documented; ACM cross-cluster reconciliation working; STIG baseline + FIPS status documented on companion.

**Phase 0 artifact**: internal one-pager — "OpenShift as the substrate for NVIDIA Physical AI." Not customer-facing. For internal field alignment. `docs/sales-enablement/one-pagers/phase-0-foundation.md`.

---

## Phase 1 — 5-minute Warehouse Baseline

**Goal**: the operational inference loop runs end-to-end, driven by the `demos/warehouse-baseline/script.md` narrative. A Red Hat seller can open the Showcase Console in novice mode and walk Archetype A (the "what is industrial physical AI?" audience) through a 5-minute scripted loop. Everything in this phase is justified by a beat in that script.

**Entry criteria**
- Phase 0 complete.
- Nucleus operational and accessible from new namespaces.
- `demos/warehouse-baseline/script.md` signed off as the scope gate.

**Work breakdown**

1. **RHOAI MLflow enablement and configuration** — backend Postgres (CNPG), S3 artifact store (ODF RGW), `workloads/common/python-lib/tracking/` abstraction so downstream code is insulated from RHOAI-internal details. Needed as a hub for model artifacts even though training lives in Phase 2.

2. **Nucleus validation and codification** — formalize the pre-existing deployment as a chart in `workloads/nucleus/`, Argo-reconciled. Service Mesh membership with mTLS enforcement for consumers.

3. **Isaac Sim headless runner (hub, digital twin)** — image built on `nvcr.io/nvidia/isaac-sim` loading `Isaac/Environments/Digital_Twin_Warehouse/small_warehouse_digital_twin.usd` + `Forklift_A01` + Unitree G1 + pallet variants + cameras + approach-point markers (composed via a **scene-pack overlay USD** on Nucleus). Cosign-signed, SBOM generated, deployed as a `Deployment` on L40S. Kit scenario includes a **twin-update subscriber** that consumes `warehouse.telemetry.forklifts.*` + `fleet.safety.alerts` + `warehouse.cameras.*` and reflects reality in the twin (move forklift prim to telemetry pose; place pallet prim when alert fires). Per ADR-027 the twin runs on hub because companion hardware (Strix Halo) has no NVIDIA GPU; Phase-2+ Thor would move it to companion.

4. **Showcase Console viewport via MJPEG** — Isaac Sim's active viewport is captured each frame and served as `multipart/x-mixed-replace` MJPEG from within the Kit process. The Console embeds it via a `<canvas>`-based parser (not `<img>` — dodges Firefox's periodic MJPEG cycling). Kit App Streaming's WebRTC path stays plumbed but hidden from UI; OCP HTTPS-only Routes can't carry the UDP data plane reliably without an NLB, which is out of scope.

5. **Kafka (AMQ Streams) core topics + federation** — 3-broker cluster with topics `fleet.events`, `fleet.missions`, `fleet.telemetry`, `fleet.ops.events`, `fleet.safety.alerts`, and `warehouse.cameras.aisle3` (plus siblings). MirrorMaker2 federates the cross-cluster topics between hub and companion — camera frames flow edge→hub, reroute missions flow hub→edge. Schema Registry deployed with Avro schemas from `workloads/fleet-manager/schemas/`. `warehouse-topology.yaml` is the single source of truth for aisle/dock/approach-point/camera coordinates + forklift id; every component imports it so named locations don't drift.

6. **Fake-camera service (companion)** — Python service on the companion cluster that publishes selected pre-generated JPEGs to `warehouse.cameras.aisle3` at ~1 Hz, with an HTTP `POST /state` endpoint to switch the emitted frame (steady: `aisle3_empty.jpg`; triggered: `aisle3_pallet.jpg`). Images are AI-generated photorealistic warehouse photos baked into the camera image, with a matching S3 library targeting SeaweedFS under the updated ADR-021 — the twin-vs-reality visual separation is intentional and realistic.

7. **Obstruction-detector service (hub)** — separate pod (not folded into Fleet Manager — perception is a distinct role per ADR-027). Consumes `warehouse.cameras.aisle3`, calls **Cosmos Reason 2-8B** via OpenAI-compatible `/v1/chat/completions` with image + prompt, parses the fenced JSON response, publishes structured events to `fleet.safety.alerts`. Cosmos Reason 2-8B is a **Qwen3-VL-derivative** and runs on **L40S** as a `Deployment` (bfloat16, `--max-model-len=8192`, `--gpu-memory-utilization=0.9`, `--reasoning-parser qwen3`) on **vLLM ≥ 0.11.0** — supersedes Cosmos Reason 1-7B in the same namespace. The 2B variant was trialed on L4 and failed the quality bar (see ADR-027).

8. **Fleet Manager v1** — Python + FastAPI. Consumes `fleet.events` + `fleet.missions` + **`fleet.safety.alerts`** (new), emits missions and reroutes. Rule-based decisioning only at this stage (LangGraph upgrade lands in Phase 3 per ADR-005). Handles the replan-on-alert path: when an active mission's route crosses an aisle flagged by a safety alert, replan via an alternate aisle and issue a reroute instead of the pending approach-point clearance. Postgres state.

9. **Mission Dispatcher v1 (companion)** — Python service on the companion cluster per ADR-025. Consumes `fleet.missions`, runs them through a new **Waypoint Planner module** (5 Hz pose emission along the current route, tick rate configurable via env var), HTTP-calls the host-native OpenVLA endpoint on pick to represent the manipulation policy, publishes telemetry to `warehouse.telemetry.forklifts.fl-07`. OpenVLA's role is explicitly manipulation, not navigation — VLAs aren't trained for mobile-base nav; Nav2-class planners (our Waypoint Planner) are. Emits execution events to `fleet.ops.events`.

10. **WMS Stub** — scripted mission-stream generator on the hub driving deterministic demo scenarios. Primary Phase-1 scenario is `fl-07` retrieves pallet A47 from Dock-B via aisle-3; the aisle-3-obstruction variant is triggered by the Console's "Drop Pallet" button, not a hard-coded timer. Scenario coordinates come from `warehouse-topology.yaml`; `fire_at_seconds=0` (presenter controls pacing via approach-point pause, not a scripted delay).

11. **Robot Brain serving v1 — OpenVLA primary, host-native on companion node (per ADR-026)** — for Phase 1 the VLA runtime runs as a podman systemd unit on the companion's Fedora 43 host, *outside* the SNO cluster. Runtime is PyTorch + transformers + ROCm (HIP backend) wrapping OpenVLA's reference `deploy.py` REST server. Exposed on the host bridge network; the in-cluster Mission Dispatcher (item 9) HTTP-calls it on pick to represent the manipulation policy (not for mobile-base navigation — the Waypoint Planner handles that, per ADR-027). **Not** a KServe InferenceService in Phase 1 — rationale in ADR-026: AMD consumer/APU hardware lacks first-class NVIDIA-parity operator coverage on OpenShift, vLLM upstream parked OpenVLA support as "not planned," and RHCOS 5.14 inside the SNO VM can't reach the host's iGPU. The host-level serving runtime is described in `workloads/vla-serving-host/` and provisioned via Ansible, separate from the cluster GitOps. Pluggable alternatives: **SmolVLA-450M** and **π0** (Physical Intelligence open weights) pre-provisioned for the 60-min live-swap beat. **GR00T N1.7** slotted as an optional swap-in that requires the customer's own NGC entitlement (not active by default). KServe + custom-predictor pod-native serving returns as a parallel Phase-3 path when the Jetson Thor edge arrives (see item 14 below and ADR-026's Thor-arrival notes).

12. **Showcase Console (skeletal)** — React + TypeScript front, Fastify + TypeScript back. Stage view embeds the Isaac Sim viewport via `<canvas>`-based MJPEG parser, event-trace right panel, two-cluster topology dots, three closing teaser pills ("Retrain & promote", "Multi-site rollout", "Agentic operator"). Two demo buttons — **Dispatch Mission** and **Drop Pallet** — drive the real event pipeline (the second HTTP-POSTs to the companion fake-camera service's state endpoint). Audience-mode toggle present but all modes show the same content until Phase 2 enriches them. Offline-fallback mode detects cluster unavailability and plays the cached recording seamlessly.

13. **Cross-layer wiring: SNO pod ↔ host VLA** — podman network bridge + firewalld rule on the Fedora host permitting the SNO CNI range to reach the host's bridge IP on the VLA endpoint port. Mission Dispatcher's VLA client config points at the bridge-IP endpoint URL; health-check + retry + circuit-breaker semantics on the client. Documented in `workloads/vla-serving-host/README.md` under "bridge-network wiring." Honestly named in the narration for the 5-min and 20-min scripts per ADR-026.

14. **5-min demo lands** — `demos/warehouse-baseline/script.md` runs end-to-end live on the reference cluster; the same flow plays cleanly from the offline-fallback recording.

**Cut from Phase 1 (story-driven scope gate)**: USD Search API (no downstream consumer in any of the three scripts); Metropolis VSS full pipeline (replaced by Cosmos Reason 2-8B on a single L40S — the narrow "event from camera" job is the only beat we need, and the 8-GPU VSS footprint doesn't justify itself); pod-native VLA serving on the companion cluster (deferred to Phase 3 when Jetson Thor arrives — see ADR-026); Kit App Streaming WebRTC data-plane surfaced in the Console UI (plumbing stays, UI hidden — OCP HTTPS-only Routes can't carry the UDP data plane without an out-of-scope NLB; MJPEG viewport capture is the Phase-1 path per ADR-027).

**Jetson Thor (ordered, Phase 3/4 materialization)**: a Jetson AGX Thor Developer Kit has been ordered and will land the second edge pattern when it arrives (MicroShift + NVIDIA GPU Operator + KServe + vLLM/transformers with CUDA-native serving). Does not gate Phase 1. Phase 3's 60-min Segment-4 live-swap beat grows to *"same open VLA serving on the AMD edge host, then on the Thor edge pod"* once the hardware is online. Thor also unlocks moving Isaac Sim from hub to companion (per ADR-027) — camera federation collapses and the twin co-locates with robot control.

**Exit criteria**
- The 5-minute scripted loop — companion fake-camera → Kafka federation → hub obstruction-detector → Cosmos Reason 2-8B → `fleet.safety.alerts` → Fleet Manager replan → reroute mission → companion Mission Dispatcher → Waypoint Planner (and OpenVLA on pick) → telemetry back to hub → Isaac Sim twin update — runs end-to-end on the live cluster.
- A seller can open the Showcase Console, click "Warehouse — Baseline," and walk through the 5-minute script without touching anything outside the Console.
- Offline-fallback recording is seamless — a viewer can't tell it's pre-recorded.
- The reference is GitOps-deployable from scratch using the documented bootstrap.

**Phase 1 artifact**
- `demos/warehouse-baseline/script.md` executing live and recorded.
- `docs/sales-enablement/one-pagers/phase-1-warehouse-baseline.md` — the 5-min talk track.
- Architecture poster showing Phase-1 components on Red Hat substrate.

---

## Phase 2 — 20-minute Architecture + Fleet Operations

**Goal**: the policy training/promotion loop and fleet-operations story work end-to-end, driven by `demos/20-min-architecture/script.md`. A Red Hat seller + field SA can walk Archetype B (the "we're evaluating or piloting" audience) through a 20-minute four-segment walkthrough. Multi-site federation is live (hub + companion + at least one additional spoke). The brownfield integration story is a real beat, not a sentence.

The persona-review synthesis in `demos/review-synthesis.md` identified six convergent gaps in the 20-min demo. Phase 2 absorbs the tractable ones as first-class items.

**Entry criteria**
- Phase 1 complete — the 5-min demo runs reliably.
- RHOAI MLflow operational from Phase 1 item 1.
- Scene-pack decision made (Phase 2 item 1 below, research gate).

**Work breakdown**

1. **Scene-pack decision (research gate, before other Phase 2 work starts)** — inventory what SimReady publicly ships beyond the Warehouse Pack. Specifically: is there a discrete-assembly or process/packaging scene usable without authoring? If yes, Phase 2 commits to shipping a second scene pack sharing the 5-min script skeleton; the Isaac Sim runner becomes scene-configurable via ConfigMap and the Console novice mode gains a scene selector. If no, Phase 2 explicitly commits to warehouse-only and Scene Pack #2 moves to Phase 5. **Output**: a decision ADR + an entry in `assets/README.md` listing what's in or out. Addresses review Gap 1 (Linda, Marcus, Priya convergent: warehouse-only pigeonholes the field).

2. **Brownfield-integration beat (20-min Segment 4 promoted)** — what is today a 30-second mention of "the companion has a legacy PLC gateway VM" becomes a real 3–5 minute beat:
   - **KubeVirt VM on companion**: one Windows or legacy-Linux VM representing a factory-floor PLC/HMI gateway. Boots clean, exposed only to an internal factory-network NetworkPolicy segment, visible in the Console Architecture view side panel.
   - **MES-stub service** on the hub: FastAPI service emitting SAP-PP/DS-shaped order messages into a Kafka `mes.orders` topic. Fleet Manager consumes `mes.orders` and translates to mission scheduling — the demo beat shows "your existing MES drives the AI decisioning, it doesn't replace it."
   - **Purdue-model overlay** in the Console Architecture view — Level 1 (PLC VLAN), Level 2 (HMI/SCADA segment), Level 3 (MES/site-ops), Level 4 (enterprise/hub) — with the OpenShift deployment clearly sitting *alongside* existing L1/L2 rather than replacing it.
   - Addresses review Gap 3 (Linda's #1 ask: "no bridge from my current stack to this one"; Priya confirmed "don't let this get cut").

3. **Isaac Lab training pipeline** — Kubeflow Pipeline: scenario manifest → parallel Isaac Lab training Jobs → MLflow metrics streaming → candidate policy checkpoint → evaluation against scripted scenario suite → MLflow Model Registry with full lineage (training data, scenarios, metrics, approver). The 20-min Segment 2 "training a new policy with lineage" beat.

4. **Cosmos Transfer 2.5 (limited)** — one variation pass on existing sim frames feeding a scenario manifest. Not the full synthetic-data-factory pipeline (that's Phase 3). Enough to demonstrate "this policy knows which synthetic variations trained it" in Lineage view.

5. **Policy serving update flow + GitOps rollout** — Kustomize overlay generator produces an InferenceService manifest from an MLflow model URI; PR merges trigger Argo sync; rollout order hub → spoke-a → spoke-b is defined in `infrastructure/gitops/`; `git revert` is the rollback.

6. **Auto-rollback on anomaly** — the 20-min Segment 3 "rollback in under N seconds, robots never stopped" beat. Anomaly-score threshold on telemetry triggers an automatic `git revert` of the policy-version commit; Argo syncs back to last-known-good. **The N-second claim must be measured** (not aspirational) on the actual multi-site topology and scripted to match reality (see performance-envelope item below).

7. **Second spoke cluster (Factory B)** — provisioned via ACM per the existing `clusters/spoke-b/` scaffolding. Same GitOps patterns as companion. Cross-spoke Kafka MirrorMaker or equivalent for mission flow to multiple factories.

8. **Edge layer: MicroShift target (optional Phase 2 / required Phase 4)** — Ansible playbooks for MicroShift provisioning on x86 VMs or Jetson. Bootable-container image: one image signed once, deployable identically to hub workload, companion, spoke, or edge. In Phase 2 the "edge" target may be a MicroShift-in-a-VM stand-in; physical Jetson is Phase 4.

9. **ACM RBAC-based policy rollout** — the PR-merge-to-Argo-sync-to-spoke path including the anomaly-triggered rollback beat. Policies federated across spokes.

10. **Fleet-scale reference document (sidecar, not a demo)** — 5–10 pages. Operating math at 10/40 sites: ACM fan-out characteristics, Kafka partitioning strategy, hub control-plane sizing, spoke cluster footprint at the edge, bandwidth between hub and spoke under steady-state and during policy rollout, failure-mode behaviors (hub loss, partial spoke loss, regional outage), GitOps blast-radius analysis. Lands at `docs/sales-enablement/fleet-scale-operating-math.md`. Addresses review Gap 2 (Marcus: "I have 40 sites"; Aiko: "show me where your stack breaks").

11. **Security documentation pass** — name the STIG baseline (`ocp4-stig-node` profile version), list FIPS 140-3 validated crypto status for every component in the robot command path (RHCOS, OpenSSL, Go crypto, vLLM, KServe, Kafka TLS, Llama Stack when it lands), state the SLSA level targeted for image provenance, disposition every STIG FAIL with policy rationale. Document form, no new implementation. Lands at `docs/sales-enablement/security-posture.md`. Addresses review Gap 6 (Jim: "an SSP false-statement finding ends the program").

12. **HIL Approval Drawer Design Spec (preparatory for Phase 3)** — an ADR + design doc specifying exactly what the approval drawer in the Console shows when an agentic tool call requires HIL approval: the proposed diff, blast-radius analysis, MCP tool-call trace (which tools were called read-only to build context), guardrail-check outcomes, TrustyAI eval score of proposed policy vs. incumbent, what's writeable to an immutable audit store, CAC/PIV identity binding requirements. Ships end of Phase 2, implementation lands in Phase 3. Addresses review Gap 4 (Aiko's deal-killer: "that's where the demo lives or dies — don't leave this as a TBD").

13. **Performance envelope doc v1** — measure and publish real numbers for the hub+companion+Factory-B topology: end-to-end event-to-mission latency p50/p99, rollback elapsed time (actual, not aspirational), VLA inference p99, mission round-trip for multi-site deployments. Even small numbers beat "under 90 seconds" aspirational claims. Lands at `docs/sales-enablement/performance-envelope.md`. Addresses review Gap 5 (Aiko: "The script has zero numbers").

14. **Enhanced observability** — MLflow surfaces in Console data-scientist/engineer mode; multi-site dashboards (Thanos federation); OpenTelemetry traces spanning hub → spoke for mission round-trips (this powers the 5-min's "trace every step" promise).

15. **Showcase Console grows** — Architecture view, Lineage view, Fleet view (per-site version pills + anomaly sparklines), and the scene selector from item 1 if Scene Pack #2 is in. Audience modes differentiate: novice simplified, evaluator shows Fleet view, expert shows Architecture + Lineage overlay.

16. **20-min demo lands** — `demos/20-min-architecture/script.md` runs end-to-end live on the reference cluster; the recorded fallback has timed rollback numbers baked in per item 13.

**Exit criteria**
- The 20-min scripted flow runs end-to-end live on hub + companion + spoke-b.
- The rollback beat uses a real `git revert` and a real Argo sync; the elapsed-time number quoted in the script matches the measured p50 in the performance-envelope doc.
- Brownfield beat runs end-to-end: MES-stub emits orders, Fleet Manager consumes them, KubeVirt PLC-gateway VM is visible alongside container pods in the Architecture view.
- Fleet-scale operating-math doc is published and referenced from the Console's "how this scales" panel.
- HIL Approval Drawer Design Spec is merged as an ADR before Phase 3 starts.
- Scene-pack decision is made and documented.

**Phase 2 artifacts**
- `demos/20-min-architecture/script.md` live + recorded.
- `docs/sales-enablement/fleet-scale-operating-math.md`.
- `docs/sales-enablement/security-posture.md`.
- `docs/sales-enablement/performance-envelope.md` v1.
- HIL Approval Drawer Design Spec ADR.
- `docs/sales-enablement/one-pagers/phase-2-architecture-walkthrough.md`.
- Recorded "fully operationalized MLOps + fleet rollback" reel (~8 minutes) for public channels.

---

## Phase 3 — 60-minute Technical Deep Dive

**Goal**: the agentic orchestration loop and synthetic-data story work end-to-end, driven by `demos/60-min-deep-dive/script.md`. Archetype C (the Foxconn/Siemens-tier expert audience) gets a live, honest, engineer-to-engineer deep dive. The HIL governance story is substantive, not demo theater. The OT security story produces real artifacts, not gestures.

**Entry criteria**
- Phase 2 complete. The 20-min demo runs cleanly.
- HIL Approval Drawer Design Spec (Phase 2 item 12) is merged.
- Cosmos NIMs accessible (NGC entitlement resolved — see `docs/licensing-gates.md`).

**Work breakdown**

1. **Cosmos Predict 2.5 NIM deployment — positioned as pre-dispatch admission check**, not just a training aid. The differentiated beat per the 60-min Segment 1: a proposed mission is handed to Cosmos Predict as a world-model simulation *before* it's dispatched; if the predicted rollout violates safety/latency envelopes, the mission is rejected at the Fleet Manager boundary rather than sent to the robot. Aiko's persona review flagged this framing as one of only two non-table-stakes ideas in the 60-min. KServe-wrapped Deployment on L40S. GPU scheduling coordinates with live-demo allocation per `docs/08-gpu-resource-planning.md`.

2. **Cosmos Transfer NIM deployment (full pipeline)** — same pattern as Phase 2's limited deployment but now the full synthetic-data factory: Predict → Transfer → scenario manifest generation → Nucleus upload → MLflow dataset registry. Not concurrent with Cosmos Predict in the reference footprint (GPU budget).

3. **MCP servers** — `mcp-isaac-sim`, `mcp-fleet`, `mcp-mlflow`. (`mcp-nucleus` is conditional — add only if a specific 60-min beat needs it; otherwise defer to Phase 5 to avoid padding the surface.) Each its own workload, Service Mesh secured, read-only vs. state-modifying tool classifications explicit.

4. **LangGraph agentic orchestrator** — Python + LangGraph. Agent brain is a vLLM-served model sized for L4 by default (see `docs/08-gpu-resource-planning.md`). Tool access exclusively via MCP servers. State persistence to Postgres.

5. **Llama Stack governance layer (ADR-019)** — wraps LangGraph. Read-only MCP tool calls pass through; state-modifying tool calls are routed through HIL approval via the Llama Stack Agents API. Safety guardrails + PII detection on agent inputs/outputs. TrustyAI evaluation signal wired into observability. **Critical constraint from Aiko's persona review**: Llama Stack governance is on the *GitOps / PR-open path* only, not inline in serving-time robot command flow. The governance layer cannot add latency to 10Hz+ VLA inference. This is a design invariant — violating it is a deal-killer for the Archetype-C audience.

6. **HIL Approval Drawer implementation** — builds to the Phase 2 design spec. When a state-modifying tool call enters the HIL gate, the drawer renders: proposed diff, blast radius, MCP tool-call trace, guardrail outcomes, TrustyAI eval score vs. incumbent, CAC/PIV-bound approval that writes to an immutable audit store. The drawer is the 60-min's strongest beat per all three Archetype-C+ persona reviews — build it right.

7. **Agent-opens-a-PR pattern** — the operator-authored design where a state-modifying agentic action results in the agent opening a pull request to `infrastructure/gitops/`, not directly calling the cluster API. The PR triggers the HIL drawer; approval merges the PR; Argo CD reconciles the change. This reframes "LLM touching OT" as "LLM participating in the review process you already trust." Flagged as the single most-differentiating beat across personas.

8. **Fleet Manager v2 (hybrid)** — rule-based fast path for standard missions stays. Agentic path for anomaly investigation: events scoring above an anomaly threshold dispatch to the LangGraph orchestrator for hypothesis generation; investigation actions that propose fleet interventions route through the HIL gate + Llama Stack.

9. **Security posture execution (backing the Phase 2 documentation)** — the Phase 2 security-posture doc claims things; Phase 3 surfaces them live:
   - Real Sigstore admission rejecting a tampered artifact on-camera (the 60-min Segment 3 beat). The rejected-artifact event appears in the audit log visibly during the demo.
   - Live Compliance Operator scan results exported during the demo, matching the Phase 2 STIG baseline; the 19 FAILs have their Phase 2 dispositions visible.
   - `oc-mirror v2` air-gap walkthrough of the companion-side mirror registry. The script explicitly calls out that the live cluster under demo is OSD but the air-gap story runs on companion, so the viewer isn't misled.
   - Policy-artifact provenance chain from training scenario → MLflow registered model → signed InferenceService image → admitted-at-serving. Not just the image chain — the full training→deploy chain.

10. **OSCAL evidence bundle export (stretch)** — a Console feature that emits a signed bundle combining the SSP component definition + Compliance Operator results + Sigstore attestations + SBOMs + HIL approval log, OSCAL-formatted, auditor-consumable. **Stretch** means: if it's tractable with Phase-3 resources, it ships; if not, it formally moves to Phase 5 with a documented reason. Jim's persona flagged this as the single feature that moves defense-sector conversations from "interesting" to "I'd write a capability statement."

11. **Showcase Console agentic panel** — natural-language command box, agent plan visualization, HIL approval drawer surfacing pending tool calls, counterfactual reasoning panel, policy-lineage view wired to provenance chain from item 9. Expert-mode depth.

12. **60-min demo lands** — `demos/60-min-deep-dive/script.md` runs end-to-end live, four structurally-independent 15-min segments (synthetic-data factory, LangGraph+MCP+HIL, OT security, live VLA swap + trace + repo tour).

**Exit criteria**
- Live agentic run: operator types a natural-language question, agent composes and executes a sim experiment, results return, any proposed state change routes through HIL.
- Synthetic data produced via Cosmos Transfer/Predict can be consumed in an Isaac Lab training run; the resulting policy is traceable back to the synthetic scenarios that trained it and to the scenario manifests that validated it.
- Policy-artifact provenance chain is click-navigable from Console: registered model → scenario manifest → synthetic frames → signed artifact → admission event.
- HIL drawer behaves per its design spec.
- Tampered-artifact rejection is live and reproducible.

**Phase 3 artifacts**
- `demos/60-min-deep-dive/script.md` live + recorded.
- `docs/sales-enablement/one-pagers/phase-3-deep-dive.md`.
- Blog post series (three posts minimum) on the Red Hat Developer blog: the agent-opens-a-PR pattern, the synthetic-data factory, the multi-site policy provenance chain.
- Performance envelope doc v2 (with numbers for HIL round-trip, agentic flow, VLA hot-swap).

---

## Phase 4 — Verticalization and Physical Robot Integration

**Goal**: the reference becomes an enablement surface for partner-specific engagements. At least two vertical scenario packs exist beyond warehouse. A physical robot integration, if hardware budget allows, demonstrates sim-to-real policy transfer as the demo peak.

**Entry criteria**
- Phase 3 complete.
- The reference has been exercised in at least three Archetype-B or -C customer-facing engagements and received feedback.
- A decision has been made on physical robot hardware acquisition (Unitree G1 or alternative), or explicit deferral.

**Work breakdown**

1. **Vertical scenario pack #2 (whichever wasn't delivered in Phase 2)** — if Phase 2 shipped warehouse + discrete-assembly, Phase 4 adds process/packaging (or vice versa). Same script skeleton, scene-configurable Console. Gates on publicly available scenes only.

2. **Vertical scenario pack #3** — a third scene pack covering a different industrial mode (e.g., electronics SMT line or automotive subassembly) if SimReady or other publicly usable sources support it. Scene authoring remains out of scope.

3. **Physical robot integration (optional, hardware-gated)** — if hardware budget supports: one physical Unitree G1 or alternate humanoid integrated with the edge stack via MicroShift on a Jetson-class device. Sim-to-real policy transfer as the demo peak — a policy trained on SimReady scenes in Phase 2's Isaac Lab pipeline deploys to the physical robot and executes. If hardware isn't funded, the "real" side stays MicroShift-on-a-VM and the Phase 4 deliverable absorbs that explicitly.

4. **Partner enablement package** — SI enablement materials (deck + lab guide) for field delivery partners; reusable Ansible collection for customer-site deployment; published case-study templates. **No partner-specific overlays land in this phase** — the charter keeps Siemens-specific integration explicitly out of scope until the reference is mature and a formal partnership engagement is opened (charter §Non-goals).

5. **Red Hat Summit / GTC session track** — session materials drawn from this repo's demos with real-customer anonymized outcomes if engagement feedback from the entry criteria allows.

**Exit criteria**
- At least two vertical scenario packs beyond warehouse are Console-selectable.
- If physical hardware was acquired: sim-to-real loop works end-to-end from policy training to physical robot execution.
- Partner enablement materials are published and at least one SI partner has delivered a customer engagement using them.

**Phase 4 artifacts**
- Vertical-specific 20-min demo variants (same skeleton, different scenes).
- Sim-to-real recording (if physical hardware).
- Partner enablement lab guide.

---

## Phase 5 — Public-facing iteration (new; post-launch)

**Goal**: formalize the truth that the showcase keeps improving after it goes public. Items that matter for long-term credibility but don't gate any of the three pre-launch demo scripts live here. This phase has no end date — it continues as long as the showcase remains a Red Hat enablement asset.

**Work items (continuous, prioritized by field feedback)**

1. **Scene pack expansion** — add scenes as NVIDIA SimReady grows or as public industrial USD content becomes available. No scene authoring; public sources only.

2. **Fleet-scale reference doc v2+** — the Phase 2 doc is based on hub + companion + one spoke. As real customer deployments provide telemetry, update the doc with measured numbers at real-world scale. Target: named-customer reference numbers at 10+ site fan-out.

3. **Performance envelope doc v2+** — continuous measurement. Add numbers for every new Phase 3+ component under load. HIL round-trip with guardrails enabled; VLA hot-swap p99 at varying load; Cosmos Predict pre-flight overhead budget.

4. **OSCAL evidence bundle** — if the Phase 3 stretch item didn't land there, it lands here. Otherwise, expand to cover additional compliance frameworks as customer conversations demand (CMMC L3, IEC 62443, FedRAMP High cross-walks).

5. **HIL drawer content refinements** — field feedback on what's actually useful in the drawer vs. what's decoration. Iterate the spec as operators report.

6. **Customer-fork success recipes** — as Archetype-B and -C accounts clone the repo and stand up variants, capture their deltas (what they changed, what broke, what they had to document internally). Publish as `docs/sales-enablement/customer-fork-playbook.md`. This converts anecdotal "they got it running" into repeatable onboarding.

7. **Talk-track and one-pager refresh** — `docs/sales-enablement/talk-tracks/` and `one-pagers/` become living artifacts; every real customer conversation feeds back.

8. **NVIDIA stack version uplifts** — as Isaac Sim, Cosmos, and RHOAI release new versions, the reference pulls forward. Major version bumps that change demo beats trigger a script rev.

9. **Objection-cards and competitive doc** — currently stub directories under `docs/sales-enablement/`. Populate based on real field objections logged over time.

**Exit criteria**: there are no exit criteria. Phase 5 is perpetual.

---

## Explicit non-items (name them so scope creep doesn't reopen them)

These are deliberately out of scope across all phases. If a customer or field conversation requests them, the correct answer is to point at this list and at the reasoning, not to quietly add them:

- **Live N-site ACM deployment for any N > 3.** Multi-site credibility comes from the Phase 2 operating-math doc + real customer references, not from paying cloud bills to stand up a fake fleet. Demo shows hub + companion + one spoke. Doc covers the scale math.
- **USD scene authoring of any kind.** Scenes come from NVIDIA SimReady and other publicly available sources only. No contracts, no custom modeling work. If a demo beat wants something public assets can't support, the beat changes to fit what's available, not the other way around.
- **Training-data provenance attestation for ITAR- or export-controlled geometry.** The reference uses public scenes; provenance claims don't extend to classified-adjacent training corpora. Regulated-industry customers extend the attestation chain themselves for their own workloads.
- **Llama Stack governance inline in serving-time robot command flow.** HIL gating happens on the GitOps / PR-open path only. Adding approval latency to 10Hz+ VLA inference is explicitly excluded as a design invariant.
- **GR00T as the default served VLA.** OpenVLA is primary (open license, redistributable). GR00T slots in as a pluggable alternative gated on the customer's own NGC entitlement. See `docs/licensing-gates.md`.
- **Siemens-specific integrations, BMW-specific integrations, any named-partner-specific integrations.** The reference proves the substrate; named-partner overlays are separate engagements that come *after* the reference is mature and a formal partnership is opened.
- **Full Metropolis VSS 8-GPU deployment.** The narrow "event from a simulated camera" job is handled by Cosmos Reason 2-8B on a single L40S. The VSS footprint is unjustified by any beat in any of the three scripts.
- **USD Search API.** Cut in the Phase-1 story-driven audit — no downstream consumer in any of the three demos.
- **BONES-SEED / GEAR-SONIC-based beats.** Licensing is unresolved per `docs/licensing-gates.md`; do not design demo surface around unreleaseable dependencies.
- **Generic Red Hat security flex (FIPS/STIG/Sigstore as checklist items).** The differentiator-mapping doc §5 explicitly reframes security as OT-grade operational control. If a security beat doesn't map to a physical-AI concern (command-path integrity, policy-artifact provenance, air-gap for IP protection, OT segmentation), it doesn't land.

---

## Cross-phase concerns

Some work is continuous, not phase-scoped:

- **Documentation**: every new component or data flow updates the relevant doc in the same PR. Documentation rot is a bug.
- **Demos**: every pre-launch phase produces a video recording of its flagship demo. Recordings land in `demos/<name>/recordings/`.
- **Testing**: integration tests for each loop land incrementally; end-to-end tests follow in Phase 2+.
- **Security**: Sigstore enforcement tightens from warn → enforce in Phase 1; FIPS validation runs become continuous in Phase 2; STIG dispositions get refreshed with every OCP/RHCOS version bump.
- **Talk tracks**: every phase's sales-enablement artifact feeds back into the talk-tracks doc. Living document.
- **Honesty**: the charter's design principle "honest about limits" applies to every demo recording and every sales-enablement artifact. If a number is aspirational, it's marked aspirational. If a beat runs on companion not hub, the narration says so. Field teams who deliver with credibility compound; teams who oversell burn the reference. This is a cross-phase discipline, not a Phase N item.
