# Phase 2 Plan — 20-minute Architecture + Fleet Operations

> Storage update (2026-09-29): historical observations below predate SeaweedFS. Current endpoint and Secret names describe the migration target; isolated CPU-only S3 validation in `showcase-storage-canary` passed; live data/consumer cutover remains pending. See the [object-storage guide](../../tools/object-storage/README.md).

This document is the single source of truth for Phase 2 execution. It consolidates all planning, analysis, and decisions made during the Phase 2 planning session. If context is lost, start here.

## Scope gate

Phase 2 exists to deliver the 20-minute demo defined in `demos/20-min-architecture/script.md`. Every work item must earn its place in one of that script's four segments or directly support the exit criteria. The audience is Archetype B — "we're evaluating or piloting physical AI." The demo is four roughly-5-minute segments:

| Segment | Title | What the audience sees |
|---------|-------|----------------------|
| 1 | The operating picture | Two factory sites running, policy version timeline, fleet health |
| 2 | Training a new policy with lineage | Kubeflow pipeline, MLflow registry, model traceability |
| 3 | Promotion, rollout, rollback | PR merge → Argo sync → version pill change → anomaly → auto-rollback |
| 4 | Brownfield reality + close | KubeVirt VM (PLC gateway), MES-stub orders, Purdue overlay, air-gap mention |

---

## Phase 1 current state (what exists)

### Operational services

| Service | Cluster | Namespace | Role |
|---------|---------|-----------|------|
| fleet-manager | Hub | fleet-ops | Rule-based mission planning, consumes safety alerts, emits missions + reroutes |
| wms-stub | Hub | fleet-ops | Scripted mission-stream generator, drives demo scenarios |
| obstruction-detector | Hub | fleet-ops | Consumes camera frames, calls Cosmos Reason 2-8B, emits `fleet.safety.alerts` |
| camera-adapter | Hub | fleet-ops | Bridges camera feeds into Kafka |
| Cosmos Reason 2-8B | Hub (L40S) | fleet-ops | vLLM ≥0.11.0, bfloat16, visual reasoning for obstruction detection |
| Isaac Sim | Hub (L40S) | isaac-sim | Digital twin, MJPEG viewport capture, twin-update subscriber |
| Console frontend | Hub | showcase-console | React + TypeScript + PatternFly, Stage view with MJPEG canvas |
| Console backend | Hub | showcase-console | Fastify, SSE events, Kafka consumer, scenario actions API |
| fake-camera | Companion | warehouse-edge | Publishes photorealistic warehouse JPEGs to `warehouse.cameras.aisle3` at ~0.7 Hz |
| mission-dispatcher | Companion | robot-edge | Consumes `fleet.missions`, Waypoint Planner (5 Hz), calls host-native VLA on pick |
| OpenVLA (host-native) | Companion host | systemd | PyTorch + transformers + ROCm on Fedora 43, bridge-network accessible |

### Platform infrastructure (hub)

- AMQ Streams (Kafka): 3-broker cluster in `fleet-ops` with topics `fleet.events`, `fleet.missions`, `fleet.telemetry`, `fleet.ops.events`, `fleet.safety.alerts`, `warehouse.cameras.aisle3`, `warehouse.cameras.commands`
- MLflow: deployed with Postgres (CNPG) backend + S3 artifact store at the time of this plan — operational but not wired to any training pipeline. SeaweedFS is the later migration target, not that historical deployment.
- Nucleus: Kubernetes-native deployment (ADR-024), scene assets seeded
- RHOAI 3.4 EA1: installed with all components including KFP (DSPA), Kubeflow Training Operator
- Vault + Vault Secrets Operator: operational
- Service Mesh 3: operational (sail-operator v3.3.1)
- ACM: hub managing companion as spoke

### Platform infrastructure (companion)

- OpenShift Virtualization: operator installed (KubeVirt + HyperConverged CR), no VMs deployed yet
- Compliance Operator + STIG scan: operational
- Cluster Image Policy: Sigstore enforcement mode
- LVMS: local volume storage
- User workload monitoring: Thanos federation to hub

### Kafka cross-cluster connectivity

Companion workloads connect to hub Kafka via **TLS-passthrough OpenShift Route** (`fleet-kafka-bootstrap-fleet-ops.apps.<hub-domain>:443`). There is no local Kafka on the companion and no MirrorMaker2 — it's direct point-to-point SSL.

### Console state

The Console has a working **Stage view** only:
- MJPEG canvas for Isaac Sim viewport
- Camera feed card (real-time warehouse images from fake-camera via Kafka)
- Event trace panel (colored by topic, collapsing consecutive duplicates)
- Scenario panel with "Dispatch Mission", "Drop Pallet", "Reset Scene" buttons
- Topology diagram (static PNG)
- Audience-mode toggle (novice/evaluator/expert — all show the same content currently)

**Not yet built**: Architecture view, Lineage view, Fleet view, scene selector.

### Single source of truth for coordinates

`workloads/warehouse/warehouse-topology.yaml` — aisles, docks, approach points, camera positions, robot IDs, pallet IDs. All components import from this file.

---

## Decisions made during planning

### D1: Factory B is a namespace on the hub cluster

Factory B is represented by a dedicated namespace (e.g., `factory-b`) on the hub cluster, not a separate cluster. This exercises the real operational pattern — separate deployments, separate telemetry, ordered GitOps rollout, per-site version tracking — without requiring a second companion cluster we don't have.

**What Factory B mirrors from the companion (Factory A):**

The companion runs exactly two workloads: fake-camera (in `warehouse-edge`) and mission-dispatcher (in `robot-edge`). Factory B needs:

- A `fake-camera-b` deployment — new camera ID, publishes to a different Kafka topic or partition. Since it's on the hub, it uses internal cluster Kafka DNS instead of the external TLS route.
- A `mission-dispatcher-b` deployment — different robot ID (e.g., `fl-08`), publishes telemetry to a different topic.
- Factory B does **not** need an active VLA endpoint. The 20-min script says Factory B shows "idle-but-healthy telemetry" in Segment 1. In Segment 3, it receives a policy promotion but doesn't need to execute a live mission. The dispatcher can publish idle heartbeat telemetry without VLA calls.

**No MirrorMaker needed** — both factories talk to the same hub Kafka. Topic naming (e.g., `factory-a.telemetry.*` vs `factory-b.telemetry.*`) or partition-based separation handles isolation.

**Narration honesty**: "same coordination pattern, different deployment targets." The fleet-scale operating-math doc carries multi-cluster credibility, not the live demo.

### D2: Training pipeline uses GR00T N1.7 VLA for Unitree G1 humanoid

Phase 1 demos a **forklift warehouse** scenario. Phase 2's training beat uses a **G1 humanoid VLA fine-tuning pipeline** adapted from a sibling project (`nvidia-industrial-wbc-pipeline`). This is not a conflict — it's a narrative strength:

**The narrative bridge**: "Your warehouse doesn't have one robot type — it has forklifts for transport and humanoids for manipulation. You saw the forklift fleet running. Now an engineer needs to fine-tune the humanoid's pick policy on new teleoperation data. Here's the pipeline."

This is stronger than a forklift retrain because:
1. **"One platform, many robot types"** — complementary stories, not competing
2. **Real training on real data** — 311 real teleoperation episodes, 3B-parameter model, actual GPU training on L40S
3. **The Red Hat value prop is infrastructure, not the robot** — Kubeflow orchestration, MLflow tracking, model registry with lineage, GitOps promotion

The 20-min script's Segment 2 scenario was already flagged as a placeholder ("AMRs hesitating at a specific turn in dense traffic" — explicitly marked "pick something visualizable"). The G1 VLA fine-tuning fills this slot.

### D3: Pipeline code is self-contained in this repo

We borrow structural patterns from the sibling project but maintain no runtime dependency. This project stays self-contained and GitOps-driven. See Workstream B for what we take, what we skip, and what we build ourselves.

### D4: Reuse MLflow and its S3 artifact store

The training pipeline shares MLflow's S3 endpoint, with a separate `vla-training` bucket. The current migration replaces that store with SeaweedFS while retaining the MLflow service and existing artifact URIs. Observability and warehouse images use their own storage namespaces. Phase 1's historical deployment is not evidence that the replacement is live.

### D5: Demo shows pre-computed training + live kick-off

GPU scheduling: the demo shows a completed pipeline run's lineage (pre-computed), then kicks off a new run live to show "this is how an engineer starts one." The audience sees it start; they don't need to watch it finish. This avoids GPU contention with Isaac Sim and Cosmos Reason 2-8B during the live demo.

A third L40S on the cluster is currently used by the sibling project to resolve the GR00T fine-tune blocker. Once that's resolved and the fix is inherited into this project, the third L40S can produce a completed run's lineage. This L40S is **not a prerequisite** for this project's work — we can build the pipeline infrastructure and Console views without it.

### D6: Console views built sequentially

Architecture view → Fleet view → Lineage view.
- Architecture is most visually impactful and supports the non-negotiable brownfield beat (Segment 4)
- Fleet supports Segments 1 & 3
- Lineage is most dependent on the MLOps pipeline being operational, so building it last means backend data is real

### D7: HuggingFace and NGC credentials are available

- `HF_TOKEN` in `.env` — valid, for gated model downloads (GR00T N1.7 uses Cosmos-Reason2-2B as VLM backbone)
- `NGC_API_KEY` in `.env` — valid, for Cosmos Transfer 2.5 NIM access
- Neither should be echoed to context or committed to the repo

### D8: No "Mega" branding

Do not reference NVIDIA's "Mega Omniverse Blueprint" by name anywhere in Phase 2 work or new artifacts. Though the showcase resembles that blueprint, it is not called out as the source of truth. Existing references in older docs are a separate cleanup task tracked outside this plan.

### D9: Concept over pure functionality, but honest

The primary goal is conveying Red Hat's role to potential customers and partners. Concept is more important than legitimate end-to-end functionality — but corner-cutting is limited to only what's necessary to deliver the vision. Don't overdo it. If something is a representation rather than a real cross-cluster operation, the narration says so.

---

## Workstream A — Multi-site Infrastructure

**Gates**: Segments 1 (operating picture) and 3 (promotion/rollback)

### A.1 — Factory B namespace and workload scaffolding

Create the namespace and parallel workload deployments on the hub cluster that represent Factory B.

**Deliverables:**
- Namespace `factory-b` (or similar) on hub
- `fake-camera-b` Deployment — reuses the same container image as companion's fake-camera, configured with a different camera ID (`cam-dock-b` or `cam-aisle-4`), publishing to a Factory-B-specific Kafka topic
- `mission-dispatcher-b` Deployment — reuses the same container image, configured with a different robot ID (`fl-08`), publishing idle telemetry. VLA endpoint URL left empty or pointed at a stub — Factory B doesn't execute active missions during the demo
- ConfigMaps for each, referencing hub-internal Kafka bootstrap (`fleet-kafka-bootstrap.fleet-ops.svc:9092`) instead of the external TLS route used by the companion
- ServiceAccounts + RBAC scoped to Factory B's namespace

**GitOps location:** `infrastructure/gitops/apps/workloads/factory-b/`

**`warehouse-topology.yaml` update:** Add a Factory B section with robot `fl-08`, camera positions, and zone definitions. Consider whether Factory B is a "different warehouse layout" or a "different zone in the same warehouse" — the demo script treats them as separate physical sites.

### A.2 — Kafka topic separation for multi-factory

Define the topic naming scheme that cleanly separates Factory A (companion) and Factory B (hub namespace) event streams.

**Options (pick one):**
1. **Topic-per-factory**: `factory-a.telemetry.forklifts.fl-07`, `factory-b.telemetry.forklifts.fl-08` — cleanest for the Console Fleet view
2. **Partition-per-factory on existing topics**: less topic sprawl but harder to visualize per-factory in the Console
3. **Existing topics + message-level factory ID**: least infrastructure change but requires consumer filtering

Recommendation: option 1 (topic-per-factory) for demo clarity. The Console Fleet view can subscribe to factory-specific topics directly.

**Deliverables:**
- KafkaTopic CRs in `infrastructure/gitops/apps/platform/kafka/topics.yaml` for Factory B topics
- Console backend SSE endpoint updated to report events per-factory
- Fleet Manager update: consume Factory B telemetry alongside Factory A for the fleet-wide view

### A.3 — GitOps policy rollout path

The PR-merge-to-Argo-sync-to-deployment path that the demo's Segment 3 exercises.

**Deliverables:**
- Kustomize overlay structure in `infrastructure/gitops/` that supports per-factory policy versions. A policy version change is a manifest update (InferenceService image tag or ConfigMap value) applied to one factory's overlay at a time.
- Argo CD Application (or ApplicationSet member) per factory, so sync status is visible per-site
- The rollout order (Factory A first, Factory B second) is enforced by PR sequencing, not automation — the demo operator merges to Factory A, observes, then merges to Factory B

**Narration support:** The Console Fleet view shows version pills per factory that update as Argo syncs. The demo operator narrates: "Factory A is now on v1.4. Factory B is still on v1.3."

### A.4 — Auto-rollback on anomaly

The Segment 3 "rollback in under N seconds, robots never stopped" beat. This is the single most technically demanding item in Workstream A.

**Mechanism:**
1. Telemetry from Factory A includes an anomaly score (could be mission failure rate, latency regression, or an explicit anomaly-score metric from the obstruction-detector or fleet-manager)
2. A threshold breach triggers an automated `git revert` of the policy-version commit in the GitOps repo
3. Argo CD syncs the reverted manifest, rolling Factory A back to the previous policy version
4. The Console Fleet view shows the version pill reverting and an "auto-rollback" indicator

**Implementation options:**
- **Argo CD + webhook**: a lightweight service watches telemetry, on threshold breach calls the GitHub API to create a revert commit, Argo CD picks it up on next sync (or is webhook-notified)
- **Argo Rollouts analysis run**: if we use Argo Rollouts for the canary, the built-in analysis can trigger automatic rollback — but this adds a dependency we may not want
- **Manual-for-demo**: the presenter triggers the anomaly (like Phase 1's "Drop Pallet" button), a service creates the git revert, Argo syncs. Pre-scripted but reproducible.

Recommendation: the third option (manual trigger, real git revert, real Argo sync). Honest, reproducible, measurable. The presenter clicks "Trigger Anomaly" in the Console, a backend service creates the revert commit, and the audience watches Argo sync in the Fleet view.

**Measurement obligation:** The elapsed time from trigger to rollback-complete is measured on the actual topology and becomes the `{MEASURED_P50}` value in the demo script. This is a hard constraint from the persona review: "don't quote a number to me you haven't measured."

### A.5 — ACM policy federation pattern

Demonstrate ACM's role in multi-site governance, even though Factory B is a namespace rather than a separate cluster.

**Deliverables:**
- ACM Policy or PolicySet that enforces configuration consistency across Factory A (companion) and Factory B (hub namespace) — e.g., image signing requirements, network policy baseline, resource quotas
- The demo doesn't deep-dive ACM but references it: "ACM ensures every site meets the same governance baseline"

---

## Workstream B — MLOps Pipeline (VLA Training)

**Gates**: Segment 2 (training a new policy with lineage)

### The sibling project and what we inherit

The `nvidia-industrial-wbc-pipeline` project has a working KFP v2 pipeline for GR00T N1.7-3B VLA fine-tuning targeting the Unitree G1 humanoid. Current status:
- **Data-prep step**: works end-to-end (downloads GR00T N1.7-3B + 311-episode G1 teleop dataset from HuggingFace, caches in S3)
- **Fine-tune step**: actively being debugged — GR00T embodiment config mismatch. Fix expected; the third L40S on the cluster is being used for this work
- **ONNX validation step**: implemented, runs structurally (shape checks, inference, determinism)
- **Model registration step**: implemented, registers in RHOAI Model Registry with S3 URI + metadata

**What we take (adapted, not copied):**
- KFP v2 pipeline structure (`@dsl.pipeline` + `@dsl.container_component` pattern)
- Step pattern: data-prep → fine-tune → ONNX validate → register
- ONNX validation logic (model-agnostic structural/inference/determinism checks)
- Model Registry integration (`registry.py` pattern)
- Containerfile.vla (CUDA 12.8 + Isaac-GR00T n1.7-release base image recipe)

**What we skip:**
- SONIC import pipeline (whole-body controller, not in our demo narrative)
- RSL-RL pipeline (reinforcement learning, blocked on B200/PhysX, not relevant)
- Video gallery app (not in any demo script beat)
- B200-specific configuration (we're on L40S)
- The other project's namespace layout, secrets, or infrastructure

### B.1 — Scaffold `workloads/vla-training/`

Create the self-contained training workload in this repo.

**Directory structure:**
```
workloads/vla-training/
├── src/
│   └── vla_training/
│       ├── pipeline.py          # KFP v2 pipeline definition
│       ├── data_prep.py         # Download GR00T N1.7-3B + G1 teleop dataset → S3
│       ├── fine_tune.py         # torchrun + GR00T fine-tuning
│       ├── validate_onnx.py     # ONNX validation (lifted from sibling project)
│       ├── register_model.py    # Model Registry with lineage metadata
│       └── constants.py         # Cluster-internal service URLs for our infrastructure
├── Containerfile                # CUDA + GR00T base
├── pyproject.toml
└── README.md
```

Pipeline parameters (runtime-overridable):
- `base_model_repo`: `nvidia/GR00T-N1.7-3B`
- `dataset_repo`: `nvidia/PhysicalAI-Robotics-GR00T-Teleop-G1`
- `embodiment_tag`: `UNITREE_G1`
- `max_steps`: 2000
- `global_batch_size`: 64
- `num_gpus`: 1
- `model_name`: `g1-vla-finetune`
- `model_version`: auto-incremented

**When building this step, prompt the user** — they have the sibling project's code and will guide which parts to adapt vs. rewrite as the GR00T fine-tune fix lands.

### B.2 — DSPA + Model Registry GitOps

Deploy the pipeline execution infrastructure through Argo CD.

**Deliverables:**
- `infrastructure/gitops/apps/platform/dspa/` — DSPA CR sharing MLflow's S3 store, targeting `seaweedfs.mlflow.svc:8333` after controlled migration
- `infrastructure/gitops/apps/platform/model-registry/` — RHOAI Model Registry CR (if not already covered by the RHOAI DataScienceCluster)
- Compiled pipeline YAML stored in the repo
- Pipeline runs triggered by Console action or pre-demo prep Job

**Secrets needed:**
- `hf-credentials` — HuggingFace token for gated model downloads. Managed through Vault.
- Vault-sourced S3 credentials projected into `vla-training/s3-credentials` (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`); MLflow retains `mlflow-s3-credentials`.

### B.3 — Lineage stitching

The sibling project has three disconnected systems (DSPA, MLflow, Model Registry) with no cross-references. We fix that from the start.

**Deliverables:**
- MLflow tag `dspa_run_id` written by the pipeline's fine-tune step at training start
- Model Registry metadata dict includes `pipeline_run_id`, `dataset_repo`, `base_model_repo`, `training_steps`, `embodiment_tag`
- Console Lineage view (D.3) queries all three systems and joins on these IDs

**Lineage chain the Console renders:**
```
Dataset (HF repo) → KFP Run (DSPA) → Training Metrics (MLflow) → ONNX Artifact (S3) → Validation (pass/fail) → Registered Model (Model Registry)
```

**Data sources for each node:**

| Node | System | Query |
|------|--------|-------|
| Dataset | KFP run parameters | `dataset_repo` parameter value |
| Training run | DSPA | `GET /apis/v2beta1/runs/{run_id}` |
| Training metrics | MLflow | `mlflow.search_runs()` filtered by `dspa_run_id` tag |
| ONNX artifact | S3 (SeaweedFS) | S3 URI from Model Registry metadata |
| Validation | KFP step output | Step status + output parameters |
| Registered model | RHOAI Model Registry | `model-registry` Python SDK |

### B.4 — MLflow VLA metrics

GR00T's `launch_finetune.py` doesn't natively log to MLflow. For Phase 2, **post-hoc log scraping** is sufficient: parse GR00T's stdout or TensorBoard output after training completes, log summary metrics (loss curve, training steps completed, final loss) to MLflow. The demo beat is "metrics visible in MLflow with lineage," not "real-time training dashboard."

### B.5 — Cosmos Transfer 2.5 (limited)

Show Cosmos Transfer's contribution to synthetic data **as stills in the Lineage view**, not as a pipeline-integrated step.

**Deliverables:**
- Deploy Cosmos Transfer 2.5 NIM on hub (L40S) — `NGC_API_KEY` available in `.env`
- Generate a small set of scene variations from existing warehouse sim frames (one-time, pre-computed)
- Store original/transferred pairs in SeaweedFS
- Lineage view shows a "Synthetic Variations" node with side-by-side stills (original render vs. transferred variation)
- Narration: "This policy knows which synthetic variations trained it. The full synthetic-data factory is a Phase 3 conversation."

**Scope boundary**: Cosmos Transfer is NOT wired into the VLA training pipeline. It produces stills that are displayed in the Lineage view as context. The full Predict → Transfer → scenario manifest → training integration is Phase 3.

### B.6 — Policy serving update flow

The mechanism by which a trained model becomes a deployed policy.

**Deliverables:**
- A script or service that takes a Model Registry entry and produces a Kustomize overlay update (InferenceService manifest with the new model URI)
- This change is committed as a PR to the GitOps repo
- Merging the PR triggers Argo CD sync → new policy deployed to the target factory

This connects Workstream B (training produced a model) to Workstream A (GitOps rolls it out).

---

## Workstream C — Brownfield Integration

**Gates**: Segment 4 (brownfield reality + close). The persona review called this "the single most field-valuable beat in this demo." Non-negotiable once built.

### C.1 — KubeVirt VM on companion (PLC/HMI gateway)

One VM representing a factory-floor legacy controller, running alongside the container workloads on the companion cluster.

**Deliverables:**
- VirtualMachine CR in `infrastructure/gitops/apps/companion/plc-gateway-vm/`
- Boots a legacy Linux (or Windows if licensing allows) image with a visual PLC/HMI-like interface
- NetworkPolicy restricting the VM to an internal factory-network segment
- The VM is visible in the Console Architecture view side panel

**Open decision**: What does the visitor actually see inside the VM? Options:
- A Linux VM with a terminal showing simulated PLC communications (Modbus/OPC-UA stub)
- A Linux VM running an open-source SCADA/HMI interface (e.g., GRFICSv2, OpenPLC)
- A Windows VM with an HMI login screen (requires Windows licensing)
- A minimal Linux VM that's simply "named and visible" — the narration does the work, the Console shows it exists alongside containers

The choice affects visual impact. Decide before implementation.

### C.2 — MES-stub service

FastAPI service on the hub emitting SAP-PP/DS-shaped order messages to Kafka.

**Deliverables:**
- `workloads/mes-stub/` — Python + FastAPI service
- Publishes to `mes.orders` Kafka topic with messages shaped like SAP Production Planning/Detailed Scheduling orders (order ID, product, quantity, due date, priority)
- Configurable via file or API: can emit a steady stream of orders or be triggered by the Console
- Deployed via `infrastructure/gitops/apps/workloads/mes-stub/`

**Narration support**: "Your existing MES doesn't go away. In this reference, an MES-stub is emitting SAP-PP/DS-shaped order messages; Fleet Manager is consuming them as mission input alongside the camera events you saw earlier."

### C.3 — Fleet Manager update for MES consumption

Fleet Manager gains the ability to consume `mes.orders` and translate them into mission scheduling.

**Deliverables:**
- New Kafka consumer in Fleet Manager for `mes.orders` topic
- Translation logic: MES order → mission parameters (product → pallet type, destination → dock assignment)
- Missions from MES orders enter the same planning queue as missions from WMS-stub or camera-triggered reroutes
- The Console event trace shows MES-originated missions with a distinct visual indicator

---

## Workstream D — Console Views

**Gates**: All segments. Console views are the primary demo surface.

### Console design context

The Console follows a Red Hat product page aesthetic: clean, confident, enterprise-grade. Brand palette:
- Primary red `#EE0000` (accent only — buttons, active states)
- Dark charcoal `#151515` (masthead, primary text)
- Medium gray `#6A6E73` (secondary text, labels)
- Light gray `#F0F0F0` (card backgrounds)
- Green `#3E8635` (success/live states)
- Orange `#F0AB00` (warning)
- Danger red `#A30000` (alerts)

Cards are flat and structural — thin borders, no drop shadows, 4px max radius. PatternFly components where available.

### D.1 — Architecture view (built first)

The system topology diagram with Purdue-model overlay for the brownfield beat.

**Layout:**
- Primary frame: layered architecture diagram showing the system components across Purdue levels
  - Level 4 (Enterprise/Hub): Fleet Manager, MLflow, training pipeline, Showcase Console
  - Level 3 (Site Operations/MES): MES-stub, mission planning
  - Level 2 (HMI/SCADA): KubeVirt PLC-gateway VM representation
  - Level 1 (PLC/Field): Robot edge (companion), sensor feeds
- Side panels (togglable):
  - KubeVirt VM inspection: shows the VM is running alongside container pods
  - MES-stub order flow: stream of orders visible flowing into Kafka's `mes.orders` topic
  - Mirror-registry topology (brief): shows the air-gap deployment path

**Data sources:**
- Cluster topology: `/api/topology` endpoint (already exists, needs extension for Factory B and VM status)
- MES order stream: new SSE endpoint or extension of existing `/api/events`
- VM status: query companion cluster's KubeVirt API (or cached status in the backend)

**Implementation notes:**
- The diagram can be SVG-based (interactive, zoomable) or a structured React component tree
- Purdue levels are visual overlays on the architecture, not a separate diagram
- The Purdue overlay is the key Segment 4 visual — it must clearly show OpenShift sitting at Level 3 and above, not replacing Level 1/2

### D.2 — Fleet view (built second)

Multi-site operations dashboard for Segments 1 and 3.

**Layout:**
- Two factory panels side by side:
  - "Factory A" (companion): active mission telemetry, robot status, camera feed
  - "Factory B" (hub namespace): idle-but-healthy telemetry, heartbeat, policy version
- Per-factory elements:
  - Policy version pill (e.g., "v1.3" → animates to "v1.4" during promotion)
  - Anomaly-score sparkline (time series, compact)
  - Argo sync status indicator ("synced" / "syncing" / "reverting")
  - Robot status (active / idle / rerouting)
- Bottom timeline: policy version deployment history across the fleet, with timestamps
- "Trigger Anomaly" button (evaluator/expert mode only): kicks off the auto-rollback sequence

**Data sources:**
- Factory A telemetry: existing Kafka topics (`warehouse.telemetry.forklifts.fl-07`)
- Factory B telemetry: new Kafka topics (A.2)
- Policy versions: read from GitOps repo state or Argo CD API
- Anomaly scores: computed from telemetry by Fleet Manager or a dedicated service
- Argo sync status: Argo CD API

### D.3 — Lineage view (built last)

Directed graph showing the full provenance chain from training data to deployed model.

**Layout:**
- Directed acyclic graph (left to right):
  - Dataset node → KFP pipeline run node → MLflow experiment node → ONNX artifact node → Validation node → Model Registry node → (optional) Deployed policy node
  - Cosmos Transfer "Synthetic Variations" node branching into the graph with side-by-side stills
- Click any node to expand details in a side panel:
  - Dataset: HuggingFace repo ID, episode count, license
  - Pipeline run: parameters, step statuses, duration, GPU used
  - MLflow: loss curve chart, key metrics
  - Validation: pass/fail, checks performed
  - Registered model: version, S3 URI, metadata dict
- Graph should clearly show "every piece of this is traceable" — the Segment 2 core message

**Data sources:** See B.3 lineage stitching section for the full system-to-query mapping.

**Implementation notes:**
- Consider a graph rendering library (e.g., `dagre` / `elkjs` for layout, `reactflow` for interactive rendering)
- The graph is rendered from live data, not a static image — but the data comes from a completed pipeline run (pre-computed), not a live training job

### D.4 — Scene selector (conditional)

If the scene-pack decision (E.1) yields a second scene beyond warehouse, add a scene selector to the Console's novice mode. If warehouse-only, skip this item entirely.

### D.5 — Audience-mode differentiation

Phase 2 makes the audience modes meaningful:
- **Novice**: Stage view only (Phase 1 content), simplified event labels
- **Evaluator**: Stage + Fleet view, Architecture view available on request
- **Expert**: All views including Lineage, raw Kafka JSON visible, Grafana/Argo CD external links

---

## Workstream E — Documentation and Design

### E.1 — Scene-pack decision ADR

**Research gate — should be resolved early.**

Inventory what NVIDIA SimReady publicly ships beyond the Warehouse Pack. Specifically: is there a discrete-assembly or process/packaging scene usable without authoring? If yes, Phase 2 commits to a second scene pack. If no, Phase 2 explicitly commits to warehouse-only.

**Output:** ADR in `docs/07-decisions.md` + entry in `assets/README.md`.

### E.2 — Fleet-scale operating-math doc

`docs/sales-enablement/fleet-scale-operating-math.md` — 5-10 pages.

Content: ACM fan-out characteristics at 10/40 sites, Kafka partitioning strategy, hub control-plane sizing, spoke cluster footprint, bandwidth under steady-state and during policy rollout, failure-mode behaviors (hub loss, partial spoke loss, regional outage), GitOps blast-radius analysis.

This doc is referenced during the demo when an evaluator asks "what about 40 sites."

### E.3 — Security posture doc

`docs/sales-enablement/security-posture.md`

Content: name the STIG baseline (`ocp4-stig-node` profile version), list FIPS 140-3 validated crypto status for every component in the robot command path (RHCOS, OpenSSL, Go crypto, vLLM, KServe, Kafka TLS, Llama Stack when it lands), state the SLSA level targeted for image provenance, disposition every STIG FAIL with policy rationale.

Document form only — no new implementation. Phase 3 surfaces these claims live.

### E.4 — Performance envelope doc v1

`docs/sales-enablement/performance-envelope.md`

Content: measured numbers on the actual hub + companion + Factory B topology:
- End-to-end event-to-mission latency p50/p99
- Rollback elapsed time (the `{MEASURED_P50}` that goes into the demo script)
- VLA inference p99
- Mission round-trip for multi-site deployments
- Kafka cross-cluster latency

**Dependency:** Requires Workstream A to be operational for measurement. This is a "last" phase item.

### E.5 — HIL Approval Drawer design spec

An ADR + design doc specifying exactly what the Console's HIL approval drawer shows when an agentic tool call requires human-in-the-loop approval (Phase 3 implementation). Content per the phased plan:

- Proposed diff and blast-radius analysis
- MCP tool-call trace (which tools were called read-only to build context)
- Guardrail-check outcomes
- TrustyAI eval score of proposed policy vs. incumbent
- What's writeable to an immutable audit store
- CAC/PIV identity binding requirements

Ships end of Phase 2; implementation lands in Phase 3. This is a critical Phase 3 prerequisite — the persona review called it a deal-killer if left as TBD.

---

## Dependency graph

```
E.1 (scene-pack ADR) ──→ D.4 (scene selector, conditional)

A.1 (factory-b namespace) ──→ A.2 (topic separation) ──→ A.3 (GitOps rollout) ──→ A.4 (auto-rollback)
                                                                                  ──→ E.4 (perf measurement)

B.1 (scaffold vla-training) ──→ B.2 (DSPA + registry GitOps) ──→ B.3 (lineage stitching) ──→ D.3 (lineage view)
                                                                ──→ B.4 (MLflow metrics)
                                                                ──→ B.6 (policy serving flow) ──→ A.3 (GitOps rollout)

B.5 (Cosmos Transfer limited) ──→ D.3 (lineage view, synthetic variations node)

C.1 (KubeVirt VM) ──→ D.1 (architecture view, VM panel)
C.2 (MES-stub) ──→ C.3 (fleet-manager update) ──→ D.1 (architecture view, MES panel)

A.1-A.3 operational ──→ D.2 (fleet view)
A.4 (auto-rollback measured) ──→ E.4 (performance envelope)
                              ──→ demo script {MEASURED_P50} filled
```

## Execution order

### Batch 1 — parallel starts, minimal dependencies

| Item | Workstream | Effort | Notes |
|------|-----------|--------|-------|
| Scene-pack decision ADR | E.1 | Research only | Unblocks D.4 decision |
| MES-stub service | C.2 | Small (standalone FastAPI) | No dependencies |
| KubeVirt VM manifests | C.1 | Small-medium | Operator installed; needs VM CR + NetworkPolicy |
| Scaffold `workloads/vla-training/` | B.1 | Medium | **Prompt user for sibling project code** |
| Factory-B namespace + workloads | A.1 | Medium | Namespace + parallel deployments on hub |

### Batch 2 — depends on Batch 1

| Item | Workstream | Effort | Notes |
|------|-----------|--------|-------|
| Kafka topics for Factory B | A.2 | Small | Topic CRs + consumer config |
| Fleet Manager MES consumption | C.3 | Small-medium | New Kafka consumer + translation |
| DSPA + Model Registry GitOps | B.2 | Medium | Deploy pipeline infra through Argo CD |
| Console Architecture view | D.1 | Large | SVG/component diagram + Purdue overlay + side panels |
| Console Fleet view | D.2 | Large | Two-panel layout, wire to live data as multi-site lands |

### Batch 3 — depends on Batch 2

| Item | Workstream | Effort | Notes |
|------|-----------|--------|-------|
| GitOps policy rollout | A.3 | Medium | Kustomize overlays + Argo Application per factory |
| Auto-rollback on anomaly | A.4 | Medium-large | Git revert automation + Console trigger |
| Lineage stitching | B.3 | Small | Metadata tags across three systems |
| MLflow VLA metrics | B.4 | Small | Post-hoc log scraping |
| Cosmos Transfer 2.5 limited | B.5 | Medium | NIM deployment + one-time scene variation generation |
| Console Lineage view | D.3 | Large | DAG rendering + multi-system data queries |
| Enhanced observability | — | Medium | Thanos federation, OTel spans across hub → factory |

### Batch 4 — measurement and polish

| Item | Workstream | Effort | Notes |
|------|-----------|--------|-------|
| Performance envelope measurement | E.4 | Medium | Real numbers on actual topology |
| Fleet-scale operating-math doc | E.2 | Medium (writing) | 5-10 pages |
| Security posture doc | E.3 | Medium (writing) | Component-by-component audit |
| HIL Approval Drawer design spec | E.5 | Medium (design) | ADR + spec, no implementation |
| Policy serving update flow | B.6 | Medium | Model Registry → Kustomize → PR |
| Audience-mode differentiation | D.5 | Small | Gate views by mode |
| 20-min demo rehearsal + recording | — | — | Timing adjustment, `{MEASURED_P50}` filled |

---

## Risks and mitigations

### R1: GR00T fine-tune blocker

**Risk:** The VLA fine-tune step is blocked by a GR00T embodiment config mismatch in the sibling project. If unresolved when we reach B.1, we can't produce a completed training run.

**Mitigation:** The pipeline infrastructure (DSPA, MLflow, Model Registry, Lineage view) can all be built and tested with the data-prep step alone — it downloads real data and caches it in S3. The fine-tune step slots in when the fix lands. The demo can show the pipeline DAG with data-prep completed and narrate the training step. Story is weaker but honest.

### R2: GPU contention during demo

**Risk:** VLA fine-tuning, Isaac Sim, and Cosmos Reason 2-8B all want L40S GPUs. Live training during the demo could cause contention.

**Mitigation:** Decision D5 — show pre-computed lineage + live kick-off. Training runs during demo prep, not during the live demo. Two L40S are sufficient for Isaac Sim + Cosmos Reason 2-8B; the third L40S (currently with sibling project) produces the pre-computed run when available.

### R3: Factory-B fidelity

**Risk:** Namespace isolation on one cluster doesn't exercise real cross-cluster networking. A technical evaluator may notice.

**Mitigation:** Decision D1 — narration stays honest. The fleet-scale operating-math doc (E.2) carries multi-cluster credibility. The demo shows the coordination pattern; the doc shows the scale math.

### R4: Console view complexity

**Risk:** Three new views (Architecture, Fleet, Lineage) are substantial frontend work. Each has its own data sources and interaction patterns.

**Mitigation:** Decision D6 — sequential build order. Architecture first (most visual impact, supports non-negotiable brownfield beat), Fleet second, Lineage last. Each view can be demonstrated independently as it's completed.

### R5: Cosmos Transfer 2.5 scope creep

**Risk:** "Limited" deployment could expand into the full synthetic-data factory pipeline (Phase 3 territory).

**Mitigation:** Hard boundary: Cosmos Transfer produces stills shown in the Lineage view. It is NOT wired into the VLA training pipeline. The full Predict → Transfer → scenario manifest → training chain is Phase 3.

### R6: KubeVirt VM content

**Risk:** The VM's visual content (what the viewer sees) affects the brownfield beat's impact. A blank Linux terminal is less compelling than a PLC/HMI interface.

**Mitigation:** Decide before C.1 implementation. A lightweight open-source SCADA/HMI interface on Linux is the best balance of visual impact and licensing simplicity.

---

## Open items to circle back on

- **Scenario selector UI**: The Console currently loads `scenarios[0]` as the default and has no way to switch. With `POLICY_ROLLOUT` added to the WMS-Stub catalog, both scenarios exist on the backend, but the presenter can't reach the rollback demo beat from the Console without a selector. Revisit after reviewing current Console state — the selector should fit naturally into the existing scenario panel.
- **Lineage view seed data**: The Lineage view uses static placeholder data in `server.ts`. Once the sibling project (`nvidia-industrial-wbc-pipeline`) produces a completed fine-tuning run, pull real metrics (final loss, training steps, dataset stats) into the seed data so the numbers shown are representative of actual GR00T N1.7-3B training on the G1 teleop dataset. If the sibling project's blocker persists, the current plausible-but-fabricated values are acceptable for demo purposes — the narrative structure matters more than the exact numbers.

---

## Exit criteria (from phased plan, restated for tracking)

- [ ] The 20-min scripted flow runs end-to-end live on hub + companion + Factory B namespace
- [ ] The rollback beat uses a real `git revert` and a real Argo sync; elapsed time matches the measured p50 in the performance-envelope doc
- [ ] Brownfield beat runs end-to-end: MES-stub emits orders, Fleet Manager consumes them, KubeVirt PLC-gateway VM is visible alongside container pods in the Architecture view
- [ ] Fleet-scale operating-math doc is published and referenced from the Console
- [ ] HIL Approval Drawer Design Spec is merged as an ADR before Phase 3 starts
- [ ] Scene-pack decision is made and documented
- [ ] Performance envelope doc v1 published with real measured numbers
- [ ] Security posture doc published

---

## Artifacts Phase 2 produces

- `demos/20-min-architecture/script.md` — updated with real scenario, measured timing, Factory A/B names
- `demos/20-min-architecture/recordings/` — recorded demo
- `docs/sales-enablement/fleet-scale-operating-math.md`
- `docs/sales-enablement/security-posture.md`
- `docs/sales-enablement/performance-envelope.md` v1
- `docs/sales-enablement/one-pagers/phase-2-architecture-walkthrough.md`
- HIL Approval Drawer Design Spec ADR in `docs/07-decisions.md`
- Scene-pack decision ADR in `docs/07-decisions.md`
