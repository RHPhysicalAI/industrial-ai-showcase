# 02 — Component Catalog

Every deployable component in the reference, with a canonical entry. New components get added here first, then implemented.

Entry template:

```
### [N]. Component Name
- **Category**: Foundation | Platform | NVIDIA | Integration | Edge | Experience | Observability
- **Purpose**: one-sentence description
- **Source**: upstream chart / operator / custom
- **License**: if relevant
- **Resource profile**: CPU / RAM / GPU / storage
- **GPU**: yes/no; if yes, how many and why
- **Deployment**: Operator / Helm chart / manifest / custom
- **Dependencies**: what must already be running
- **Dependents**: what depends on this
- **Persistence**: what state must survive pod restart / cluster upgrade
- **Network exposure**: internal / Route / vLAN / Multus
- **Phase**: when in the plan this enters the cluster
- **Notes**: anything non-obvious
```

---

## Foundation layer

### 1. OpenShift — Hub (OpenShift Dedicated; we have cluster-admin)
- **Category**: Foundation
- **Purpose**: Kubernetes substrate with enterprise lifecycle, RBAC. The primary platform surface of the reference. Red Hat-managed OSD instance; we operate with `cluster-admin`.
- **Source**: Red Hat OpenShift Dedicated (internal Red Hat instance).
- **Resource profile**: 2–3 × L40S GPU nodes + 2–3 × L4 GPU nodes + standard non-GPU workers. SRE-managed control plane and cloud-resource layer.
- **GPU**: L40S + L4 on the GPU-bearing workers.
- **Deployment**: managed by Red Hat SRE at the infrastructure layer; we manage at the cluster-content layer with cluster-admin.
- **Constraints**: cluster-admin clears most permission gates. Persistent caveats: MachineConfigs are fragile due to SRE's infrastructure automation (prefer companion for MachineConfig-dependent work); OSD is internet-adjacent, so air-gap validation goes on companion; GPU / node provisioning is SRE-managed cloud resources. See ADR-017.
- **Dependencies**: none (this is the substrate).
- **Dependents**: most workloads in this reference.
- **Persistence**: SRE-managed control plane; workload persistence via available StorageClasses.
- **Network exposure**: Routes, Services, standard Ingress.
- **Phase**: 0 (already provisioned).
- **Notes**: capture the exact OSD version, instance family for each MachinePool, and present operator/component versions in `infrastructure/baseline/osd-hub-state.md` at Phase 0.

### 1a. OpenShift — Companion (self-managed)
- **Category**: Foundation
- **Purpose**: Host the OSD-incompatible differentiators — MachineConfig STIG, FIPS mode, OpenShift Virtualization for Kit workstations, cluster-scoped Sigstore admission, true air-gap validation. Per ADR-017.
- **Source**: self-managed OpenShift (SNO or small compact cluster) on on-prem hardware.
- **Resource profile**: modest — CPU/RAM-focused for most demos, plus optional NVIDIA GPU for the vGPU workstation demonstration. Candidate hosts: GMKTec Evo-X2 Mini PC, ORIGIN PC (RTX 5090), or dedicated lab box.
- **GPU**: optional — NVIDIA GPU required if demonstrating vGPU-backed Kit workstation.
- **Deployment**: manual or assisted install; managed by this project, not by Red Hat SRE.
- **Dependencies**: none.
- **Dependents**: Kit workstation VM, MachineConfig/FIPS/STIG demos, air-gap validation runs.
- **Persistence**: local NVMe + ODF on the companion if cluster-scale warrants.
- **Network exposure**: Routes; optionally Multus NetworkAttachmentDefinitions for the shop-floor network story that OSD cannot demonstrate.
- **Phase**: 0 (provision alongside OSD baseline).
- **Notes**: companion host selection is an open decision deferred to Phase 0 provisioning. Document the chosen host, version, and node specs in `infrastructure/baseline/companion-state.md`.

### 1b. OpenShift — Spoke clusters (A and B, self-managed)
- **Category**: Foundation
- **Purpose**: Represent "Factory A" and "Factory B" for the multi-site federation story.
- **Source**: self-managed OpenShift; SNO instances are acceptable.
- **Deployment**: separate hardware preferred; nested-on-companion-via-Virtualization as a fallback for one of them.
- **Phase**: 2.

### 2. NVIDIA GPU Operator
- **Category**: Foundation
- **Purpose**: Manages driver, CUDA, container runtime, device plugin, DCGM exporter on GPU nodes. Includes GPU Feature Discovery (GFD) which applies `nvidia.com/gpu.product`, `nvidia.com/gpu.memory`, `nvidia.com/gpu.family`, and related labels automatically.
- **Source**: OperatorHub (NVIDIA).
- **Resource profile**: DaemonSet on GPU nodes.
- **GPU**: n/a (it's the thing that exposes GPUs).
- **Deployment**: **already installed on OSD hub**; GFD labels are already in place on L40S and L4 nodes. Validate the existing ClusterPolicy in Phase 0; don't reinstall.
- **Dependencies**: Node Feature Discovery (also already installed).
- **Dependents**: every GPU-consuming workload.
- **Persistence**: none.
- **Network exposure**: DCGM exporter on Service for Prometheus scraping.
- **Phase**: 0 (pre-existing; validate only).
- **Notes**: GFD's native labels (`nvidia.com/gpu.product=NVIDIA-L40S` and `nvidia.com/gpu.product=NVIDIA-L4`) are the sole mechanism for GPU class targeting — no custom `gpu-class` labels anywhere. See ADR-018. Confirm the exact product-label string values during Phase 0 baseline capture, as GPU Operator versions occasionally vary the exact casing/format.

### 3. Node Feature Discovery
- **Category**: Foundation
- **Purpose**: Labels nodes with hardware features so schedulers target correctly.
- **Source**: OperatorHub (Red Hat).
- **Deployment**: Operator + NodeFeatureDiscovery CR.
- **Dependencies**: none.
- **Dependents**: GPU Operator.
- **Phase**: 0.

### 4. OpenShift Virtualization
- **Category**: Foundation
- **Purpose**: Run VMs on OpenShift alongside containers, with vGPU support for Omniverse Kit workstations.
- **Source**: OperatorHub (Red Hat).
- **Deployment**: Operator + HyperConverged CR. **Target cluster is TBD** — check whether the operator is available and installable on this OSD instance; if yes, install on hub; if no, install on companion.
- **Dependencies**: IOMMU enabled on hosts (MachineConfig adjustment if needed — companion-side if we go that route).
- **Dependents**: Omniverse Kit workstation VMs (Phase 2+).
- **Persistence**: DataVolumes backed by local storage (companion) or ODF (OSD if available).
- **Phase**: 0 (determine target cluster in baseline capture), 2+ (actively used).
- **Notes**: Phase 0 deliverable is a definitive answer on whether OpenShift Virtualization is available on this OSD instance. If yes, the vGPU Kit workstation story simplifies. If no, the companion cluster is the host. The vGPU capability additionally requires a suitable NVIDIA GPU on whatever cluster hosts it — L40S nodes on OSD support vGPU; GMKTec Evo-X2 on companion does not (integrated Radeon, no NVIDIA vGPU), so if companion hosts Virtualization and we want vGPU workstations, the ORIGIN PC (RTX 5090) is the practical companion host for that specific demo. See OD-8.

### 5. OpenShift Data Foundation
- **Category**: Foundation
- **Purpose**: Block (Ceph RBD), file (CephFS), and object (Ceph RGW, S3-compatible) storage for the cluster.
- **Source**: OperatorHub (Red Hat).
- **Resource profile**: 3+ OSD nodes; depends on cluster size.
- **Deployment**: Operator + StorageCluster CR.
- **Dependents**: Nucleus (backing store), USD asset bucket, training datasets, MLflow artifacts.
- **Phase**: 0.

### 6. OpenShift GitOps (Argo CD)
- **Category**: Foundation
- **Purpose**: Declarative reconciliation of all cluster state from this Git repo.
- **Source**: OperatorHub (Red Hat).
- **Deployment**: Operator + ArgoCD CR.
- **Dependents**: everything deployed after Phase 0.
- **Persistence**: Argo CD state in PVCs.
- **Phase**: 0.
- **Notes**: the GitOps structure is defined in `docs/06-repo-structure.md`. Primary pattern: ApplicationSets per layer, pointing at `infrastructure/gitops/`.

### 7. OpenShift Pipelines (Tekton)
- **Category**: Foundation
- **Purpose**: CI/CD inside the cluster — container builds, image signing, SBOM generation, Helm chart packaging.
- **Source**: OperatorHub (Red Hat).
- **Deployment**: Operator.
- **Dependencies**: internal registry, Sigstore integration.
- **Phase**: 0.

### 8. Red Hat Advanced Cluster Management
- **Category**: Foundation
- **Purpose**: Multi-cluster management for hub/spoke federation, policy distribution, fleet-wide GitOps.
- **Source**: Red Hat product (not OperatorHub community).
- **Resource profile**: sizeable — runs on the hub.
- **Deployment**: Operator + MultiClusterHub CR.
- **Dependents**: all spoke cluster lifecycle, Submariner federation if enabled, multi-cluster applications.
- **Phase**: 0 (install on hub), 2+ (actively registers spokes and federates workloads).

### 9. Red Hat Ansible Automation Platform
- **Category**: Foundation
- **Purpose**: Day-1 provisioning of edge devices, image builds for MicroShift, shop-floor integration automation.
- **Source**: Red Hat.
- **Deployment**: AAP instance; can run on-cluster via OperatorHub.
- **Dependents**: MicroShift provisioning, edge device configuration.
- **Phase**: 0 (install), 2+ (actively used for edge).

### 10. OpenShift Service Mesh (Istio)
- **Category**: Foundation
- **Purpose**: East-west mTLS, zero-trust policies, distributed tracing via Jaeger/Tempo, traffic shaping.
- **Source**: OperatorHub (Red Hat).
- **Deployment**: Operator + ServiceMeshControlPlane CR + ServiceMeshMember resources.
- **Dependents**: every workload participating in the mesh.
- **Phase**: 0.
- **Notes**: use v2 (Istio-based). Sidecar injection for all workload namespaces; ambient mesh as a future option.

### 11. Streams for Apache Kafka (AMQ Streams)
- **Category**: Foundation
- **Purpose**: Event streaming for fleet events, mission dispatch, telemetry, policy updates.
- **Source**: OperatorHub (Red Hat).
- **Deployment**: Operator + Kafka CR.
- **Resource profile**: 3-broker cluster minimum on hub.
- **Dependents**: fleet manager, mission dispatcher, obstruction-detector, fake-camera service, Isaac Sim twin-update subscriber, agentic orchestrator.
- **Persistence**: PVs per broker.
- **Phase**: 1.
- **Notes**: MirrorMaker 2 for hub ↔ spoke replication in Phase 2.

---

## Observability

### 12. OpenShift Monitoring (Prometheus + Alertmanager + Thanos)
- **Category**: Observability
- **Purpose**: Metrics collection, alerting, long-term storage.
- **Source**: built-in.
- **Deployment**: ClusterMonitoringConfig + UserWorkloadMonitoring.
- **Phase**: 0.

### 13. OpenShift Logging (Loki)
- **Category**: Observability
- **Purpose**: Centralized logs.
- **Source**: OperatorHub (Red Hat).
- **Deployment**: Logging Operator + LokiStack CR.
- **Phase**: 0.

### 14. OpenTelemetry + Tempo
- **Category**: Observability
- **Purpose**: Distributed tracing across services, especially through the agentic and fleet pathways.
- **Source**: OperatorHub (Red Hat).
- **Deployment**: OpenTelemetry Operator + Tempo Operator.
- **Phase**: 1.

### 15. Grafana
- **Category**: Observability
- **Purpose**: Dashboards for operator, data-scientist, and sales views.
- **Source**: OperatorHub (community or Red Hat).
- **Deployment**: Operator + Grafana CR.
- **Phase**: 1.
- **Notes**: the sales-view dashboards are embedded into the Showcase Console via iframe or direct Grafana panel API.

### 16. GPU DCGM Exporter
- **Category**: Observability
- **Purpose**: GPU-level metrics (utilization, memory, temperature, ECC).
- **Source**: deployed by GPU Operator.
- **Dependents**: Grafana GPU dashboard.
- **Phase**: 0.

---

## Platform / MLOps

### 17. Red Hat OpenShift AI (RHOAI) 3.4
- **Category**: Platform
- **Purpose**: The MLOps platform — notebooks, pipelines, model registry, serving.
- **Source**: Red Hat; **already installed** on the OSD hub at version 3.4.
- **Deployment**: DataScienceCluster CR — validate current state; enable MLflow component if not yet enabled (see ADR-015).
- **Dependents**: MLflow, KServe, Kubeflow Pipelines, model registry, notebook servers.
- **Phase**: 0 (validate pre-existing install); 1 (verify/enable MLflow, configure data science cluster components).
- **Notes**: ADR-015 covers the MLflow availability investigation; if the 3.4 installed build doesn't carry MLflow, Phase 1 has a fallback work item to stand up MLflow alongside. The tracking abstraction in `workloads/common/python-lib/tracking/` isolates consumers from this detail.

### 18. KServe (shipped with RHOAI)
- **Category**: Platform
- **Purpose**: Kubernetes-native model serving with autoscaling.
- **Source**: RHOAI's inclusion.
- **Dependents**: vLLM runtime, Cosmos NIM wrappers, GR00T serving.
- **Phase**: 1.

### 19. vLLM Runtime
- **Category**: Platform
- **Purpose**: High-throughput LLM and VLA inference with paged attention, tensor parallelism.
- **Source**: upstream vLLM project; RHOAI includes a supported runtime.
- **GPU**: yes — 1 L40S per served model instance in the reference footprint.
- **Phase**: 1.
- **Notes**: GR00T served via vLLM with an action-head wrapper; see `docs/03-data-flows.md` for the serving shape.

### 20. Kubeflow Pipelines (shipped with RHOAI)
- **Category**: Platform
- **Purpose**: Training orchestration — the pipeline that runs Isaac Lab training jobs, logs to MLflow, registers models.
- **Source**: RHOAI's inclusion.
- **Dependents**: Isaac Lab training jobs.
- **Phase**: 2.

### 21. MLflow (from RHOAI 3.4 EA1)
- **Category**: Platform
- **Purpose**: Experiment tracking, artifact store, model registry.
- **Source**: Red Hat-published container `rhoai/odh-mlflow-rhel9:v3.4.0-ea.1` (Beta release phase), shipped with RHOAI 3.4 EA1.
- **Deployment**: enabled via the DataScienceCluster CR's MLflow component toggle. Not a separate Helm chart install.
- **Dependents**: training pipelines, the policy-promotion workflow.
- **Persistence**: Postgres backend via CloudNativePG; S3-compatible artifact store (ODF or OSD-equivalent).
- **Phase**: 1 (enablement + configuration); referenced from Phase 2 onward.

### 22. CloudNativePG
- **Category**: Platform
- **Purpose**: Postgres for MLflow, Nucleus metadata where applicable, and the Showcase Console backend.
- **Source**: OperatorHub (community).
- **Deployment**: Operator + Cluster CR.
- **Phase**: 1.

---

## NVIDIA stack

### 23. Enterprise Nucleus Server
- **Category**: NVIDIA
- **Purpose**: The database and collaboration engine for USD assets.
- **Source**: NVIDIA (NGC); existing deployment from prior work.
- **Resource profile**: CPU-heavy, needs significant storage.
- **GPU**: none (CPU service).
- **Deployment**: existing Helm-based deployment. Treat as pre-existing dependency.
- **Persistence**: ODF-backed PV for the Nucleus data volumes.
- **Network exposure**: Route with SNI for WebSocket + HTTPS.
- **Phase**: 0 (pre-existing), re-validated in Phase 1.
- **Notes**: document the existing deployment in `workloads/nucleus/` so future Claude Code sessions can reason about it.

### 24. USD Search API
- **Category**: NVIDIA
- **Purpose**: Semantic search over USD assets in Nucleus or an S3 backend.
- **Source**: NVIDIA (Helm chart available in their docs).
- **GPU**: yes (embedding generation).
- **Deployment**: NVIDIA's published Helm chart; we provide overrides.
- **Dependencies**: Nucleus (or an S3 bucket if going `ovstorage` path).
- **Dependents**: asset browser in the Showcase Console; agentic asset queries.
- **Phase**: 1.

### 25. USD Code / USD Verify NIMs
- **Category**: NVIDIA
- **Purpose**: Generate or validate OpenUSD snippets from text prompts.
- **Source**: NVIDIA NIM catalog.
- **GPU**: yes.
- **Deployment**: NIM as KServe InferenceService where possible, else standalone Deployment.
- **Phase**: 2 — used in the agentic pathway.

### 26. Isaac Sim 6.0
- **Category**: NVIDIA
- **Purpose**: Physically accurate simulation and sensor rendering.
- **Source**: `nvcr.io/nvidia/isaac-sim:6.0.x`.
- **License**: NVIDIA EULA (ACCEPT_EULA=Y).
- **GPU**: yes, passthrough; 1 GPU per simulation.
- **Deployment**: Headless mode as Jobs (for batch simulations) or Deployments (for the live demo sim).
- **Dependencies**: Nucleus (or cloud assets).
- **Dependents**: sensor-data consumers (Metropolis path), policy validation jobs.
- **Persistence**: cache volumes on PVC to avoid cold shader recompilation per launch.
- **Network exposure**: WebRTC streaming via Route when used live; headless when used as batch.
- **Phase**: 1.
- **Notes**: see `docs/08-gpu-resource-planning.md` for scheduling discipline.

### 27. Isaac Lab 3.0 (on Newton 1.0 physics)
- **Category**: NVIDIA
- **Purpose**: RL and imitation-learning training frameworks atop Isaac Sim.
- **Source**: built from source (upstream repo) or `nvcr.io/nvidia/isaac-lab` where available.
- **GPU**: yes; 1+ per parallel env worker.
- **Deployment**: Kubeflow Pipelines jobs that launch Isaac Lab training processes.
- **Phase**: 2.

### 28. Omniverse Kit App Streaming
- **Category**: NVIDIA
- **Purpose**: Stream Kit-based applications (e.g., the live factory twin viewer) to web clients.
- **Source**: NVIDIA — Kubernetes-native with CRDs and Helm charts.
- **GPU**: yes; 1 per active streaming session in the reference footprint.
- **Deployment**: NVIDIA's Helm charts + custom Kit app container image.
- **Dependents**: the Showcase Console embeds the streaming viewport.
- **Network exposure**: WebRTC signaling + data plane via Routes.
- **Phase**: 1.

### 29. Cosmos Predict 2.5 NIM
- **Category**: NVIDIA
- **Purpose**: Physically based synthetic world generation; action-conditioned video prediction.
- **Source**: NVIDIA NIM catalog.
- **GPU**: yes; sizeable.
- **Deployment**: NIM as Deployment with KServe observability wrapper.
- **Phase**: 2.

### 30. Cosmos Transfer NIM
- **Category**: NVIDIA
- **Purpose**: Synthetic-to-real domain adaptation for training data.
- **Source**: NVIDIA NIM catalog.
- **GPU**: yes.
- **Phase**: 2.

### 31. Cosmos Reason 2-8B (VLM perception)
- **Category**: NVIDIA (model) + Platform (serving)
- **Purpose**: **Qwen3-VL-derivative** vision-language model for obstruction / safety perception on camera frames. Replaces the earlier Metropolis VSS plan per ADR-027 — the narrow "event from camera" job doesn't justify VSS's 8-GPU footprint.
- **Source**: `nvidia/Cosmos-Reason2-8B` served via **`vllm/vllm-openai:v0.11.0`** (Qwen3-VL support lands in 0.11.0; 0.8.x doesn't load it), OpenAI-compatible `/v1/chat/completions` with image + prompt, `--reasoning-parser qwen3`.
- **GPU**: 1 × **L40S** (bfloat16, `--max-model-len=8192`, `--gpu-memory-utilization=0.9`). NVIDIA specs 32 GB minimum; does not fit L4's 24 GB. The 2B variant was trialed on L4 and failed the quality bar (couldn't distinguish empty from pallet-blocked aisle), so 8B on L40S is the Phase-1 choice.
- **Dependents**: obstruction-detector pod (consumes frames and calls Cosmos Reason; publishes `fleet.safety.alerts`), Showcase Console (shows detection overlays).
- **Phase**: 1.

### 32. GR00T N1.7 served via vLLM
- **Category**: NVIDIA (model) + Platform (serving)
- **Purpose**: Humanoid VLA foundation model; the primary "robot brain" for the Unitree G1 scenario.
- **Source**: model from Hugging Face / NGC; serving via vLLM with action-head wrapper.
- **GPU**: yes; 1 L40S for the reference footprint.
- **Deployment**: KServe InferenceService with vLLM runtime, custom preprocessing for robot observations.
- **Phase**: 1 (basic serving), 2 (lifecycle integration).
- **Notes**: requires the commercial licensing route; Pi-0 and OpenVLA configured as BYO alternatives.

### 33. NVIDIA Holoscan
- **Category**: NVIDIA
- **Purpose**: Real-time sensor-processing framework at the edge.
- **Source**: NVIDIA SDK.
- **Phase**: 3+ (edge use cases where latency requires it).

---

## Integration layer (custom / glue)

### 34. Fleet Manager Service
- **Category**: Integration
- **Purpose**: Receives `fleet.safety.alerts` (from the obstruction-detector) + `fleet.events` + WMS missions, decides dispatch, issues missions and reroutes. Phase-1 replan-on-alert logic: when an active mission's route crosses an alerted zone, replan via an alternate aisle instead of issuing the pending approach-point clearance.
- **Source**: custom (Python, FastAPI; LangGraph upgrade in Phase 3 per ADR-005).
- **Dependencies**: Kafka, robot-brain serving endpoints (via Mission Dispatcher), Nucleus (for current world state), `warehouse-topology.yaml`.
- **Dependents**: mission dispatcher, Showcase Console state, Isaac Sim twin-update subscriber.
- **Phase**: 1.
- **Notes**: kept deliberately vendor-neutral — integrations to specific WMS/MES systems live as adapters, not in the core service.

### 35. Mission Dispatcher
- **Category**: Integration
- **Purpose**: Translates fleet-manager decisions into concrete robot commands and tracks execution.
- **Source**: custom (Python).
- **Dependencies**: Kafka, robot-brain endpoints.
- **Phase**: 1.

### 36. WMS Stub
- **Category**: Integration
- **Purpose**: Mock warehouse management system that emits orders/missions for demo purposes.
- **Source**: custom.
- **Phase**: 1.
- **Notes**: real customer integrations (to KION, SAP, or homegrown WMSs) replace this via an adapter layer in Phase 4+.

### 37. LangGraph Agentic Orchestrator
- **Category**: Integration
- **Purpose**: Long-running agents that orchestrate sim experiments, synthetic-data generation, and fleet interventions using MCP tool access.
- **Source**: custom (Python, LangGraph).
- **Dependencies**: vLLM-served LLM (Nemotron or equivalent as the agent brain), MCP servers.
- **Phase**: 3.

### 38. MCP Servers
- **Category**: Integration
- **Purpose**: Expose Isaac Sim control, Fleet Manager operations, and Nucleus asset operations to LLM agents.
- **Source**: custom wrappers over NVIDIA's Omniverse MCP examples.
- **Specific MCP servers**:
  - `mcp-isaac-sim`: scenario control, scene loading, policy rollout
  - `mcp-fleet`: read fleet state, issue overrides
  - `mcp-nucleus`: browse and stage USD assets
  - `mcp-mlflow`: inspect experiments, promote models
- **Phase**: 3.

### 39. Showcase Console
- **Category**: Experience
- **Purpose**: The sales-facing web application — audience-aware, scenario-driven, context-switching. The primary deliverable for field use.
- **Source**: custom (React + TypeScript front end, Fastify back end).
- **Dependencies**: every other component directly or indirectly — it's the conductor.
- **Phase**: 1 (skeletal MVP), 2+ (grows with each phase).
- **Notes**: specified in detail in `docs/05-sales-enablement.md`.

---

## Edge layer

### 40. Red Hat Device Edge + MicroShift
- **Category**: Edge
- **Purpose**: Lightweight Kubernetes for factory-edge and robot-side workloads.
- **Source**: Red Hat.
- **Resource profile**: small — runs on Jetson-class or x86 edge hardware.
- **Deployment**: image-mode RHEL with MicroShift RPMs; Ansible playbooks for provisioning.
- **Phase**: 2.

### 41. Edge GitOps Agent (Argo CD spoke / ACM-driven ApplicationSet)
- **Category**: Edge
- **Purpose**: Pull-based reconciliation of edge workloads from the hub.
- **Source**: Argo CD + ACM integration.
- **Phase**: 2.

### 42. Runtime Telemetry Agent (OTel Collector on edge)
- **Category**: Edge
- **Purpose**: Ship traces, metrics, logs from edge nodes back to hub.
- **Source**: OTel Collector.
- **Phase**: 2.

---

## Assets (not deployed, but versioned and important)

### 43. Warehouse Reference USD Scene
- **Category**: Asset
- **Purpose**: The canonical demo scene — NVIDIA's digital-twin-branded small warehouse with aisles, docks, and loading zones.
- **Source**: `Isaac/Environments/Digital_Twin_Warehouse/small_warehouse_digital_twin.usd` (44 MB) from the Isaac Sim 6.0 asset CDN. Composed with a scene-pack overlay USD (see #46a) that places the forklift, approach-point markers, aisle signage, and cameras.
- **Storage**: fetched from Isaac assets CDN once, then re-hosted on our Nucleus per ADR-027 to keep Nucleus in the architectural story.
- **Phase**: 1.

### 44. Unitree G1 USD + Policy Bundle
- **Category**: Asset
- **Purpose**: Unitree G1 humanoid description, URDF, and companion base policy.
- **Source**: Unitree's published descriptions + conversions.
- **Phase**: 1 (sim-only); 4+ (hardware, if pursued).

### 45. Forklift_A01 USD
- **Category**: Asset
- **Purpose**: Autonomous forklift (`fl-07` in scenarios) — the right actor for the "retrieve pallet from Dock-B" warehouse narrative. Replaces Nova Carter throughout per ADR-027 (AMRs are delivery platforms; forklifts pick pallets).
- **Source**: `NVIDIA/Assets/DigitalTwin/Assets/Warehouse/Equipment/Forklifts/Forklift_A01_PR_V_NVD_01.usd` (B variant also available).
- **Phase**: 1.

### 46. Pallet and Cargo Assets
- **Category**: Asset
- **Purpose**: USD pallets + cargo variants (cardboard boxes on pallet, wood crate on pallet) placed in the scene; the cardboard-boxes-on-pallet prim is the "dropped pallet" that materializes in aisle-3 when the obstruction scenario fires.
- **Source**: `NVIDIA/Assets/DigitalTwin/Assets/Warehouse/Shipping/Pallets/`, `.../Cardboard_Boxes_on_Pallet/`, `.../Wood_Crate_on_Pallet/`.
- **Phase**: 1.

### 46a. Scene-Pack Overlay USD
- **Category**: Asset
- **Purpose**: Overlay USD that references `small_warehouse_digital_twin.usd` and places the Forklift_A01 prim, approach-point markers, aisle signage, cameras, and docks per `warehouse-topology.yaml` coordinates. The scene-pack is what the Isaac Sim runner actually loads; the raw warehouse USD is never opened directly in Phase 1.
- **Storage**: Nucleus.
- **Phase**: 1.

### 46b. warehouse-topology.yaml
- **Category**: Asset / config
- **Purpose**: Single source of truth for aisle/dock/approach-point/camera coordinates + forklift id. Imported by wms-stub, Fleet Manager, Mission Dispatcher, scene-pack overlay USD generator, and the Console. Prevents drift between components referencing named locations.
- **Storage**: Git (`workloads/warehouse/warehouse-topology.yaml`).
- **Phase**: 1.

### 46c. Fake-Camera Service (companion)
- **Category**: Runtime service
- **Purpose**: Python service on the companion cluster. Publishes AI-generated photorealistic warehouse JPEGs to `warehouse.cameras.aisle3` (and siblings) at ~1 Hz, simulating on-site cameras. HTTP `POST /state` endpoint switches the emitted frame (steady: `aisle3_empty.jpg`; triggered: `aisle3_pallet.jpg`). Reads baked-in `/frames/` images; the matching hub S3 library targets SeaweedFS under ADR-021. Per ADR-027.
- **Source**: `workloads/fake-camera/` (new in Phase 1).
- **Phase**: 1.

### 46d. Obstruction-Detector Service (hub)
- **Category**: Runtime service
- **Purpose**: Dedicated pod (not folded into Fleet Manager — perception is a distinct role per ADR-027) that consumes `warehouse.cameras.aisle3`, calls Cosmos Reason 2-8B via OpenAI-compatible `/v1/chat/completions` with image + prompt, parses the fenced JSON response, and publishes `fleet.safety.alerts` on positive detections.
- **Source**: `workloads/obstruction-detector/` (new in Phase 1).
- **Phase**: 1.

### 46e. Waypoint Planner Module (inside Mission Dispatcher)
- **Category**: Runtime library
- **Purpose**: Emits pose updates at 5 Hz (configurable via env var) along the current mission's route. Handles mobile-base navigation in the Phase-1 stack; OpenVLA is not called for navigation (per ADR-027, VLAs aren't trained for mobile-base nav).
- **Source**: `workloads/mission-dispatcher/src/.../waypoint_planner.py` (new module in Phase 1).
- **Phase**: 1.

### 46f. Twin-Update Subscriber (inside Isaac Sim scenario)
- **Category**: Runtime / Kit scenario module
- **Purpose**: Consumes `warehouse.telemetry.forklifts.*` + `fleet.safety.alerts` + `warehouse.cameras.*` and reflects reality in the twin — moves the forklift prim to reported pose, places the pallet prim when an alert fires. Replaces the Phase-0 camera-orbit smoke test.
- **Source**: `workloads/isaac-sim/scenarios/twin_update.py` (new in Phase 1).
- **Phase**: 1.

### 46g. Sensor Assets (cameras, lidars)
- **Category**: Asset
- **Purpose**: USD representations of industrial sensors placed in the warehouse scene via the scene-pack overlay.
- **Source**: NVIDIA sample library + custom placements.
- **Phase**: 1.

---

## Scenario packs (assets + configuration that compose into complete demos)

### 47. "Warehouse — Baseline" Scenario Pack
- **Phase**: 1.
- **Contents**: `small_warehouse_digital_twin.usd` + scene-pack overlay (Forklift_A01 as `fl-07`, Unitree G1 for background presence, fixed cameras, approach-point markers, aisle signage, docks), `warehouse-topology.yaml`, baseline policies, WMS mission stream with the aisle-3-obstruction variant, baseline dashboards. The starting point for all scripted demos.

### 48. "Warehouse — Bottleneck and Recovery" Scenario Pack
- **Phase**: 2.
- **Contents**: extends the baseline with a scripted bottleneck event at Zone B, demonstrating fleet manager re-routing and policy-level adaptation.

### 49. "Warehouse — New Policy Rollout" Scenario Pack
- **Phase**: 2.
- **Contents**: extends the baseline with a fresh policy version published through MLflow, GitOps promotion to hub serving, then ACM rollout to spokes.

### 50. "Electronics Manufacturing Line" Scenario Pack
- **Phase**: 4.
- **Contents**: electronics assembly line variation — relevant to Foxconn/Pegatron-class conversations.

### 51. "Automotive Subassembly" Scenario Pack
- **Phase**: 4.
- **Contents**: sub-assembly cell variation — relevant to BMW/Mercedes/Hyundai-class conversations.

---

## RHOAI 3.4 EA1 components worth knowing about

The following are components present in the installed RHOAI 3.4 EA1 that are relevant to later phases. They are not deployed in Phase 1.

### 52. Llama Stack (from RHOAI 3.4 EA1)
- **Category**: Platform
- **Purpose**: Governance layer wrapping LangGraph-driven agents — HIL tool-call approval, safety guardrails, PII detection, TrustyAI evaluation, FIPS-compatible deployment. See ADR-019.
- **Source**: RHOAI 3.4 EA1; upstream Llama Stack 0.3.5.
- **Dependencies**: vLLM-served LLM (shared with or distinct from the LangGraph agent brain), Llama Stack distribution configuration via DSC.
- **Dependents**: Showcase Console agent view (the HIL UX), LangGraph orchestrator (emits tool calls through Llama Stack's approval flow).
- **Phase**: 3.

### 53. Feature Store (Feast, from RHOAI 3.4 EA1 — Technology Preview)
- **Category**: Platform
- **Purpose**: Centralized, role-based feature repository for reusable ML features across training and serving. Candidate home for fleet-telemetry-derived features consumed by robot-brain preprocessors.
- **Source**: RHOAI 3.4 EA1 (Tech Preview).
- **Phase**: 2+ (evaluate against Kafka→Postgres pattern currently planned in Phase 1 fleet manager; only adopt if Feature Store demonstrates clear advantage).
- **Notes**: the Phase 1 fleet manager does not use Feature Store. Revisiting in Phase 2 is tracked in U-7.

### 54. Models-as-a-Service (MaaS, from RHOAI 3.4 EA1 — Technology Preview)
- **Category**: Platform
- **Purpose**: Managed API endpoints for LLMs with centralized access control and consumption policies. Candidate for the customer-handoff auth story (OD-7).
- **Source**: RHOAI 3.4 EA1 (Tech Preview).
- **Phase**: 3 (evaluated for Showcase Console customer-handoff option c).

### 55. LLM Compressor (from RHOAI 3.4 EA1 — Developer Preview)
- **Category**: Platform tooling
- **Purpose**: Workbench image and pipeline runtime for compressing LLMs for efficient vLLM deployment. Candidate tool for fitting agent brain models on L4.
- **Source**: RHOAI 3.4 EA1 (Dev Preview); upstream `opendatahub/llmcompressor-workbench` and `opendatahub/llmcompressor-pipeline-runtime`.
- **Phase**: 3 (as needed for agent brain model selection — see OD-5).

---

## Numbering discipline

When adding components, continue the numeric series. Never renumber — consumers of this catalog (tests, dashboards, docs) reference components by number.
