# Component Knowledge Guide - Industrial AI Showcase

**Purpose:** What you need to know about each component after going through the installation  
**Audience:** Yourself, team members, demo presenters  
**Last Updated:** 2026-06-24

---

## Overview: What Did You Actually Deploy?

You deployed a **complete industrial AI warehouse automation system** running on Red Hat OpenShift. Here's the high-level picture:

- **25+ pods running** across 5 namespaces
- **3 GPU workloads** (Isaac Sim, Cosmos Reason, potentially VLA)
- **Event-driven architecture** with Kafka as the backbone
- **Digital twin simulation** with real-time video streaming
- **AI perception** with vision-language models
- **Fleet orchestration** with mission planning and safety alerts

---

## Component Categories

### 1. Platform Layer (Phase 0 - Foundation)
### 2. Storage & Data (Phase 0)
### 3. AI/ML Services (Phase 1)
### 4. Application Services (Phase 1)
### 5. UI & Observability (Phase 1)

---

## 1. Platform Layer (What Makes It All Work)

### Red Hat OpenShift AI (RHOAI) 3.4.1
**What it is:** Platform for AI/ML workloads on OpenShift  
**Namespace:** `redhat-ods-applications`, `redhat-ods-operator`

**What you should know:**
- Provides MLflow, Model Registry, and serving infrastructure
- KServe for model serving (not used in Phase 1, ready for Phase 3)
- Kubeflow Training Operator (for Phase 2 training pipelines)
- Installed via operator, configured via DataScienceCluster CR

**Key components it provides:**
- MLflow tracking server
- Model Registry
- Jupyter notebooks (not used in warehouse demo)
- TrustyAI (Phase 3+)

**Where it shows up in demo:**
- Model tracking (not visible in Phase 1 demo yet)
- Future: Model versioning and promotion

**Troubleshooting tips:**
- Check DataScienceCluster status: `oc get datasciencecluster`
- Operator in `redhat-ods-operator` namespace
- Applications in `redhat-ods-applications` namespace

---

### NVIDIA GPU Operator
**What it is:** Automates GPU management on OpenShift  
**Namespace:** `nvidia-gpu-operator`

**What you should know:**
- Automatically labels GPU nodes with `nvidia.com/gpu.product` (NVIDIA-L40S, NVIDIA-L4)
- Installs NVIDIA drivers on nodes
- Provides DCGM for GPU monitoring
- Enables GPU sharing via device plugin

**Key concepts:**
- **L40S GPUs** (48GB) - Used for: Isaac Sim, Cosmos Reason, large models
- **L4 GPUs** (24GB) - Used for: Inference, smaller models, VLA (future)
- **No MIG, no time-slicing** - One pod per GPU

**Where it shows up in demo:**
- GPU workloads schedule automatically to right GPU class
- Isaac Sim uses L40S for ray tracing
- Cosmos Reason uses L40S for vision inference

**Troubleshooting tips:**
- Check ClusterPolicy: `oc get clusterpolicy -n nvidia-gpu-operator`
- Verify GPU labels: `oc get nodes -L nvidia.com/gpu.product`
- DCGM metrics in Prometheus

---

### AMQ Streams (Kafka)
**What it is:** Event streaming platform (Apache Kafka)  
**Namespace:** `fleet-ops`

**What you should know:**
- **3-broker cluster** for high availability
- **13 Kafka topics** for different event types
- Acts as the "nervous system" of the architecture
- All services communicate via Kafka events

**Key topics:**
- `fleet.missions` - Mission commands (DISPATCH, PROCEED, REROUTE)
- `fleet.telemetry` - Robot position updates (5 Hz from waypoint planner)
- `fleet.safety.alerts` - Obstruction alerts from Cosmos Reason
- `warehouse.cameras.aisle3` - Camera image frames
- `fleet.ops.events` - Operational events
- `mes.orders` - Production orders (Phase 2)

**Where it shows up in demo:**
- Click "Dispatch Mission" → event to `fleet.missions`
- Robot moves → telemetry to `fleet.telemetry`
- Obstruction detected → alert to `fleet.safety.alerts`
- Live Fleet Events panel shows Kafka message flow

**Troubleshooting tips:**
- Check cluster: `oc get kafka -n fleet-ops`
- Check topics: `oc get kafkatopic -n fleet-ops`
- Entity operator must be Running (2/2) for topics to be Ready
- Bootstrap server: `fleet-kafka-bootstrap.fleet-ops.svc:9092`

---

### Argo CD (GitOps)
**What it is:** Continuous deployment from Git  
**Namespace:** `openshift-gitops`

**What you should know:**
- Every deployed component comes from `infrastructure/gitops/apps/`
- Changes to Git → Argo CD auto-syncs to cluster
- ApplicationSets manage multiple apps
- **Don't `oc apply` manifests directly** - use Git commits

**Key concepts:**
- Applications organized by phase (`phase: phase-0`, `phase: phase-1`)
- Kustomize for manifest generation
- Sync waves control deployment order

**Where it shows up in demo:**
- Not visible to end users
- You use it for deployment and updates

**Troubleshooting tips:**
- UI: `oc get route -n openshift-gitops openshift-gitops-server`
- Check app sync status: `oc get applications -n openshift-gitops`
- Out-of-sync means Git doesn't match cluster

---

### CloudNativePG (CNPG)
**What it is:** PostgreSQL operator for databases  
**Namespace:** `cnpg-system` (operator), various (clusters)

**What you should know:**
- Provides PostgreSQL databases for stateful services
- Auto-generates credentials in secrets
- High availability with replicas
- Used by MLflow, Model Registry, Fleet Manager

**Key clusters deployed:**
- `mlflow-postgres` (MLflow tracking server)
- `wbc-model-registry-postgres` (Model Registry)

**Where it shows up in demo:**
- Backend databases (not visible)
- Services depend on these being healthy

**Troubleshooting tips:**
- Check cluster status: `oc get cluster -A`
- Check generated secrets: `<name>-app` and `<name>-superuser`
- Service name pattern: `<name>-rw` (read-write), `<name>-ro` (read-only)

---

## 2. Storage & Data

### NVIDIA Omniverse Nucleus
**What it is:** Asset management and collaboration server for USD files  
**Namespace:** `omniverse-nucleus`

**What you should know:**
- **12 pods** running various Nucleus services
- Stores **2360 USD assets** (warehouse scene, robots, props)
- Uses S3-compatible storage (ODF RGW)
- Navigator web UI for browsing assets
- All pods co-located on same node (NVIDIA RWO PVC constraint)

**Key services:**
- `nucleus-api` - Core API server
- `nucleus-navigator` - Web UI
- `nucleus-lft` - Large File Transfer
- `nucleus-search` - Asset search
- `nucleus-auth` - Authentication

**Where it shows up in demo:**
- Isaac Sim loads warehouse scene from Nucleus
- Asset URL: `omniverse://nucleus.apps.<domain>/NVIDIA/Assets/Isaac/...`
- Navigator UI: `http://nucleus.apps.<domain>/`

**Troubleshooting tips:**
- All pods must be on same node (check pod affinity)
- Check routes resolve to correct cluster domain
- Nucleus-seeder job populates initial assets

---

### MLflow
**What it is:** Model lifecycle management and tracking  
**Namespace:** `redhat-ods-applications`

**What you should know:**
- Tracks experiments, models, and metrics
- Backed by PostgreSQL (CNPG) for metadata
- S3 (ODF RGW) for artifacts
- Shipped with RHOAI 3.4.1

**Where it shows up in demo:**
- Not visible in Phase 1 Showcase Console
- Backend for model tracking
- Phase 2: Training runs will log here

**Troubleshooting tips:**
- Check deployment: `oc get deployment mlflow -n redhat-ods-applications`
- Database connection to `mlflow-postgres-rw`

---

### Model Registry
**What it is:** Central registry for versioned models  
**Namespace:** `redhat-ods-applications`

**What you should know:**
- Registers trained models with metadata
- Versioning and lineage tracking
- Integrates with MLflow
- Custom resource: `ModelRegistry` CR

**Where it shows up in demo:**
- Not visible in Phase 1
- Phase 2: Model promotion workflow
- Phase 3: Provenance chain for policies

**Troubleshooting tips:**
- Check CR status: `oc get modelregistry -n redhat-ods-applications`
- Requires CNPG database `wbc-model-registry-postgres`

---

## 3. AI/ML Services (The "Brains")

### Isaac Sim (Digital Twin)
**What it is:** NVIDIA physics-accurate simulation and digital twin  
**Namespace:** `isaac-sim`  
**GPU:** L40S (48GB)

**What you should know:**
- Renders the warehouse environment in real-time
- Runs **headless** (no GUI, video streaming only)
- Consumes telemetry from Kafka → moves robot in sim
- Publishes video via MJPEG → HLS streaming
- Scene: `small_warehouse_digital_twin.usd` from Nucleus

**Key capabilities:**
- Physics simulation (gravity, collisions)
- Ray-traced rendering (requires RTX GPU)
- Robot visualization (Forklift_A01, Unitree G1)
- Camera simulation

**Where it shows up in demo:**
- Main video feed in Showcase Console
- Shows robot moving in response to missions
- Real-time visualization of telemetry

**Technical details:**
- Scenario: `warehouse_baseline.py` (701 lines)
- Video: `viewport_mjpeg.py` (CPU encoding, 60fps, 4Mbps)
- Cosmos capture: `cosmos_capture.py` (Phase 3)
- NVENC hardware encoding disabled (driver API mismatch)

**Troubleshooting tips:**
- Check logs for telemetry: `recv=X, moves=Y`
- Video streaming: Check `/hls/stream.m3u8` endpoint
- Nucleus connection: Check `asset_root` URL in deployment

---

### Cosmos Reason 2-8B (Vision Perception)
**What it is:** NVIDIA vision-language model for scene understanding  
**Namespace:** `cosmos`  
**GPU:** L40S (48GB)  
**Model:** Qwen3-VL-derivative, 8B parameters

**What you should know:**
- Analyzes camera images to detect obstructions
- VQA (Visual Question Answering) model
- Served via vLLM ≥ 0.11.0
- Responds to prompt: "Is there an obstruction in this warehouse aisle?"

**Key specs:**
- Precision: bfloat16
- Max model length: 8192 tokens (for image embeddings)
- GPU memory utilization: 90%
- Reasoning parser: `qwen3`

**Where it shows up in demo:**
- Obstruction Detector service calls this
- Detects pallets/boxes in camera images
- Triggers safety alerts and reroutes

**API endpoint:**
- `http://cosmos-reason.cosmos.svc.cluster.local:8000/v1/chat/completions`
- OpenAI-compatible chat completions format

**Troubleshooting tips:**
- Logs show VQA confidence scores
- vLLM ≥ 0.11.0 required for Cosmos Reason 2.x
- 8B variant needed (2B failed quality bar on L4)

---

### Mock VLA Service (Manipulation "Brain")
**What it is:** Stub VLA endpoint returning dummy manipulation actions  
**Namespace:** `fleet-ops`  
**GPU:** None (CPU only)

**What you should know:**
- **This is a mock** - not real AI inference
- Returns pre-programmed 7-DOF action vectors
- Real VLA (OpenVLA-7B) designed to run on companion cluster host
- Parses instruction text to determine action type

**Action mappings:**
- "PICKUP"/"retrieve" → `[0.0, 0.0, -0.15, 0.0, 0.0, 0.0, 1.0]` (pick)
- "PLACE"/"drop" → `[0.0, 0.0, -0.10, 0.0, 0.0, 0.0, -1.0]` (place)
- "GRASP" → `[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]` (grasp)

**Where it shows up in demo:**
- Mission Dispatcher calls VLA after route completion
- Action logged but not animated in Isaac Sim
- Proves integration is correct

**Real VLA (future):**
- OpenVLA-7B on companion Fedora host via ROCm
- PyTorch + transformers runtime
- Host-native systemd service (not Kubernetes pod)

**Troubleshooting tips:**
- Endpoint: `http://mock-vla-service.fleet-ops.svc:8000/act`
- Check Mission Dispatcher config for VLA URL
- Logs show instruction and returned action

---

## 4. Application Services (The "Workers")

### Fleet Manager (Orchestration)
**What it is:** Central orchestration and mission management  
**Namespace:** `fleet-ops`

**What you should know:**
- Consumes 4 Kafka topics concurrently:
  - `fleet.missions` (DISPATCH from wms-stub)
  - `fleet.safety.alerts` (SafetyAlert from obstruction-detector)
  - `fleet.telemetry` (robot positions)
  - `mes.orders` (production orders, Phase 2)
- Emits mission commands: DISPATCH, PROCEED, REROUTE
- Tracks robot state machine per robot

**Key logic:**
- Robot reaches approach point → auto-grants PROCEED if clear
- Obstruction detected → issues REROUTE to alternate aisle
- Maintains `obstructed_aisles` set for clearance decisions

**State machine:**
```
IDLE → DISPATCHED → AWAITING_CLEARANCE → IN_AISLE → COMPLETED
                         ↓
                    (obstruction) → REROUTE → DISPATCHED
```

**Where it shows up in demo:**
- Receives missions from WMS Stub
- Grants clearance at approach points
- Issues reroutes when obstructions detected

**Troubleshooting tips:**
- Logs show clearance decisions: `clearance.auto_granted` or `clearance.requested`
- Check planner state for active missions
- Database: PostgreSQL (future - currently in-memory)

---

### Mission Dispatcher (Robot Control)
**What it is:** Waypoint planning and robot control  
**Namespace:** `fleet-ops` (hub-only workaround)  
**Designed for:** Companion cluster (edge)

**What you should know:**
- Waypoint Planner generates 68-118 waypoints per route
- Publishes telemetry at **5 Hz** (configurable)
- Calls VLA for pick/place actions
- Handles DISPATCH, PROCEED, REROUTE missions

**Key routes:**
- `aisle-3` → 68 waypoints
- `aisle-4` → 118 waypoints (alternate/longer route)
- Approach points pause for clearance

**Where it shows up in demo:**
- Drives robot movement in digital twin
- Telemetry shows robot position updates
- VLA calls at route completion

**Troubleshooting tips:**
- Check VLA endpoint config in ConfigMap
- Logs show waypoint generation and telemetry publish rate
- Kafka consumer group: tracks mission progress

---

### Obstruction Detector (Safety)
**What it is:** Camera image analysis for safety alerts  
**Namespace:** `fleet-ops`

**What you should know:**
- Consumes `warehouse.cameras.aisle3` topic
- Sends images to Cosmos Reason 2-8B
- Publishes `SafetyAlert` events when obstructed
- Runs continuously at camera frame rate (~1 Hz)

**Detection logic:**
- Prompt: "Is there an obstruction blocking this warehouse aisle?"
- Parses Cosmos Reason response for "yes"/"no"
- Publishes alert with obstruction status + confidence

**Where it shows up in demo:**
- Detects pallets dropped in aisle
- Triggers Fleet Manager reroutes
- Safety alerts visible in console event trace

**Troubleshooting tips:**
- Logs show confidence scores (0-1.0)
- Check Cosmos Reason endpoint connectivity
- Alert frequency matches camera publish rate

---

### Fake-Camera (Image Publisher)
**What it is:** Simulated camera publishing warehouse images  
**Namespace:** `fleet-ops` (hub-only workaround)  
**Designed for:** Companion cluster (edge)

**What you should know:**
- Publishes pre-generated JPEG images to Kafka
- Two states: `aisle3_empty.jpg` / `aisle3_pallet.jpg`
- HTTP control endpoint to switch images
- Publishes at ~1 Hz

**Where it shows up in demo:**
- "Drop Pallet" button switches image state
- Triggers obstruction detection
- Simulates real camera feed

**Control endpoint:**
- `POST /state` with `{"state": "obstructed"}` or `{"state": "clear"}`

**Troubleshooting tips:**
- Images stored in MinIO bucket
- Check Kafka topic for published frames
- State persists until explicitly changed

---

### WMS Stub (Mission Generator)
**What it is:** Simulated Warehouse Management System  
**Namespace:** `fleet-ops`

**What you should know:**
- Generates DISPATCH missions on demand
- Triggered by Showcase Console "Dispatch Mission" button
- Publishes to `fleet.missions` Kafka topic
- Pre-configured scenarios (pallet retrieval)

**Mission parameters:**
- Robot: `fl-07`
- Destination: `dock-b`
- Route: `aisle-3` (primary)
- Alternate: `aisle-4` (for reroutes)

**Where it shows up in demo:**
- Backend for demo buttons
- Mission stream generator
- Phase 2: Integrates with MES Stub

**Troubleshooting tips:**
- HTTP endpoint: `http://wms-stub.fleet-ops.svc:8082`
- Check Showcase Console backend `WMS_STUB_BASE_URL` config
- Logs show mission generation

---

## 5. UI & Observability

### Showcase Console (Web UI)
**What it is:** Demo web interface for showcase  
**Namespace:** `fleet-ops`  
**Components:** Frontend (React) + Backend (Fastify)

**What you should know:**
- Main demo interface for presenters
- Three audience modes: Novice, Evaluator, Expert
- Real-time event streaming from Kafka
- Embedded Isaac Sim video feed

**Key features:**
- **Stage View** - Digital twin video player
- **Live Fleet Events** - Kafka message stream
- **Demo Buttons** - Dispatch Mission, Drop Pallet, Reset Scene
- **Cluster Topology** - Hub/Companion visualization

**Where it shows up in demo:**
- Primary interface for presenters
- Shows complete system state
- Real-time event correlation

**Technical stack:**
- Frontend: React + TypeScript + PatternFly
- Backend: Fastify + TypeScript
- Video: HLS.js player for Isaac Sim stream
- Events: Server-sent events (SSE) from Kafka

**Routes:**
- Frontend: `https://showcase-console-fleet-ops.apps.<domain>/`
- Backend API: `https://showcase-console-backend-fleet-ops.apps.<domain>/`

**Troubleshooting tips:**
- Check backend WMS_STUB_BASE_URL config
- Video player needs HLS stream at `/hls/stream.m3u8`
- Event stream endpoint: `/api/events`

---

## Component Interaction Flow

### Normal Mission Flow (No Obstruction)

```
1. User clicks "Dispatch Mission" in Console
   ↓
2. Console → WMS Stub HTTP call
   ↓
3. WMS Stub → DISPATCH event to fleet.missions (Kafka)
   ↓
4. Fleet Manager consumes DISPATCH
   - Registers mission for robot fl-07
   - Tracks as DISPATCHED state
   ↓
5. Mission Dispatcher consumes DISPATCH
   - Waypoint Planner generates 68 waypoints
   - Starts publishing telemetry at 5 Hz
   ↓
6. Telemetry → fleet.telemetry (Kafka)
   ↓
7. Isaac Sim consumes telemetry
   - Moves robot prim to new position
   - Renders updated scene
   - Streams video via MJPEG/HLS
   ↓
8. Console displays video with moving robot
   ↓
9. Robot reaches approach point (-17.22, 5.8)
   - Telemetry shows position near approach
   ↓
10. Fleet Manager detects approach point arrival
    - Checks: is aisle-3 obstructed?
    - aisle-3 NOT in obstructed_aisles
    - Auto-grants PROCEED
    ↓
11. Fleet Manager → PROCEED event to fleet.missions
    ↓
12. Mission Dispatcher continues waypoints into aisle
    ↓
13. Robot reaches destination (dock-b)
    ↓
14. Mission Dispatcher calls Mock VLA
    - Instruction: "PICKUP: retrieve pallet at dock-b"
    - VLA returns: [0.0, 0.0, -0.15, 0.0, 0.0, 0.0, 1.0]
    ↓
15. Mission complete
```

### Obstruction/Reroute Flow

```
1. User clicks "Drop Pallet" in Console
   ↓
2. Console → Fake-Camera HTTP POST /state {"state": "obstructed"}
   ↓
3. Fake-Camera switches to aisle3_pallet.jpg
   - Publishes image to warehouse.cameras.aisle3 (Kafka)
   ↓
4. Obstruction Detector consumes camera frame
   - Sends image to Cosmos Reason 2-8B
   - Prompt: "Is there an obstruction?"
   - Response: "Yes, stacked boxes" (confidence: 0.98)
   ↓
5. Obstruction Detector → SafetyAlert to fleet.safety.alerts
   - aisle_id: aisle-3
   - obstructed: true
   - label: "stacked boxes"
   ↓
6. Fleet Manager consumes SafetyAlert
   - Adds aisle-3 to obstructed_aisles set
   - Checks: any robot at approach point for aisle-3?
   - Robot fl-07 is AWAITING_CLEARANCE at aisle-3
   ↓
7. Fleet Manager → REROUTE event to fleet.missions
   - new_route: aisle-4
   - reason: "aisle-obstruction"
   ↓
8. Mission Dispatcher consumes REROUTE
   - Cancels current route
   - Waypoint Planner generates 118 waypoints (aisle-4)
   - Resumes telemetry publishing
   ↓
9. Robot takes alternate route via aisle-4
   ↓
10. Reaches destination via longer path
```

---

## What You Should Be Able to Explain

### To Non-Technical Audiences:

1. **What is this demo showing?**
   - Autonomous warehouse robot automation
   - AI vision detects safety hazards
   - System automatically reroutes robots around obstacles
   - All running on Red Hat OpenShift

2. **What's the value proposition?**
   - Reduces warehouse accidents (safety alerts)
   - Increases uptime (automatic rerouting)
   - Scales to multiple sites (multi-cluster ready)
   - Open standards (Kafka, Kubernetes, open models)

3. **Why Red Hat OpenShift?**
   - Enterprise Kubernetes with support
   - Hybrid cloud (data center + edge + cloud)
   - GPU orchestration (NVIDIA GPU Operator)
   - Security (FIPS, STIG, RBAC)

### To Technical Audiences:

1. **Architecture Pattern:**
   - Event-driven (Kafka backbone)
   - Microservices (each component independent)
   - GitOps (Argo CD reconciliation)
   - Cloud-native (12-factor apps, containers)

2. **AI/ML Stack:**
   - Isaac Sim for digital twin (physics + ray tracing)
   - Cosmos Reason for vision perception (VLM)
   - VLA for manipulation (OpenVLA/SmolVLA/π0)
   - MLflow + Model Registry for lifecycle

3. **Why This Architecture:**
   - **Kafka** - Decouples services, enables replay, audit trail
   - **Digital Twin** - Validate before deploying to physical robots
   - **Multi-cluster** - Hub (data center) + Edge (factory floor)
   - **GPU Classes** - Right-size workloads (L40S for sim, L4 for inference)

### To Your Team Lead:

1. **What's deployed:** Phase 0 + Phase 1 (25+ pods, 5 namespaces)
2. **What works:** End-to-end demo loop with rerouting
3. **What's mocked:** VLA (real version on companion cluster)
4. **What's next:** Phase 2 multi-site, Phase 3 agentic orchestration

---

## Quick Reference: Key Commands

```bash
# Check all deployed applications
oc get applications -n openshift-gitops

# Check GPU allocation
oc get nodes -L nvidia.com/gpu.product
oc describe node <node-name> | grep -A 5 "Allocated resources"

# Check Kafka cluster
oc get kafka -n fleet-ops
oc get kafkatopic -n fleet-ops

# Check Isaac Sim video streaming
oc logs -n isaac-sim -l app=isaac-sim --tail=50 | grep "HLS\|viewport"

# Check mission flow
oc logs -n fleet-ops -l app=fleet-manager --tail=30
oc logs -n fleet-ops -l app=mission-dispatcher --tail=30

# Check Cosmos Reason inference
oc logs -n cosmos -l app=cosmos-reason --tail=20

# Get Showcase Console URL
oc get route -n fleet-ops showcase-console -o jsonpath='{.spec.host}'

# Check all Phase 1 components
oc get pods -A -l phase=phase-1
```

---

## Component Dependencies

```
Platform Layer (must be first):
  ├─ OpenShift AI → MLflow, Model Registry
  ├─ GPU Operator → GPU nodes labeled
  ├─ CNPG → Databases for MLflow, Model Registry
  └─ AMQ Streams → Kafka cluster + topics

Storage Layer:
  ├─ Nucleus → USD assets for Isaac Sim
  └─ MinIO → Images for fake-camera

AI/ML Services (need GPU + Nucleus):
  ├─ Isaac Sim (L40S) → needs Nucleus
  └─ Cosmos Reason (L40S) → standalone

Application Services (need Kafka):
  ├─ Fleet Manager → consumes missions, alerts, telemetry
  ├─ Mission Dispatcher → consumes missions, publishes telemetry
  ├─ Obstruction Detector → consumes camera, publishes alerts
  ├─ Fake-Camera → publishes camera images
  ├─ WMS Stub → publishes missions
  └─ Mock VLA → called by Mission Dispatcher

UI (needs all above):
  └─ Showcase Console → displays everything
```

---

## Common Questions & Answers

**Q: Why does the robot stop at the approach point sometimes?**  
A: Fleet Manager checks if the aisle is obstructed. If `aisle-3` is in the `obstructed_aisles` set, it waits. This is the safety feature working correctly.

**Q: What's the difference between L40S and L4 GPUs?**  
A: L40S (48GB) for heavy workloads (sim, large models). L4 (24GB) for inference and smaller models. We schedule based on `nvidia.com/gpu.product` label.

**Q: Why is VLA a mock service?**  
A: Real VLA (OpenVLA-7B) designed for companion cluster's AMD GPU (ROCm). Mock proves integration works on hub-only setup.

**Q: What happens if Kafka goes down?**  
A: Services queue messages, wait for reconnection. Kafka is the single point of failure in current design. Phase 2 adds multi-cluster federation for resilience.

**Q: Can I change the warehouse scene?**  
A: Yes, modify `SCENE_PACK_URL` in Isaac Sim deployment. Scene must be USD format on Nucleus server.

**Q: How do I add a second robot?**  
A: Add robot ID to Fleet Manager, create mission with new robot_id, Mission Dispatcher handles concurrency.

---

## What to Study Next

**If you're doing demos:**
- Practice the Console UI flow (Dispatch → Drop Pallet → Reset)
- Understand the event trace in Live Fleet Events panel
- Know the reroute story (aisle-3 obstructed → aisle-4)

**If you're doing troubleshooting:**
- Learn Kafka topic inspection (`kafkacat` or console consumers)
- Understand pod logs for each service
- Know GPU scheduling (nodeSelector + tolerations)

**If you're extending the system:**
- Read ADR docs in `docs/07-decisions.md`
- Understand Phase 2 plan (`docs/04-phased-plan.md`)
- Review component catalog (`docs/02-component-catalog.md`)

---

**You now know more about this system than most people who will use it!** 🎉