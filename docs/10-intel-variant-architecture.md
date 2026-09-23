# 10 — Intel Physical AI Variant Architecture

## Overview

This document describes an Intel-based variant of the industrial-ai-showcase reference architecture. While the primary implementation uses NVIDIA's Mega Omniverse Blueprint (GPUs + Isaac Sim + Cosmos + GR00T), this variant demonstrates how the same Red Hat substrate and operational patterns apply to Intel's Physical AI stack built on Core Ultra processors with heterogeneous NPU/iGPU/CPU compute.

**Status**: Architectural proposal  
**Date**: 2026-09-23  
**Source**: Intel Physical AI on Red Hat specification (GitHub Gist: redhatHameed/441dc8ca5614fa50d9f7977f49424cdd)

## Executive Summary

The Intel variant is **not a configuration swap** — it's a parallel architecture with significant component replacements in the AI/simulation layer. The Red Hat platform substrate (OpenShift, RHOAI, ACM, GitOps, security, observability) remains **100% identical**. The value proposition shifts from "NVIDIA Mega on Red Hat" to "heterogeneous edge AI on Red Hat with Intel silicon."

### What Remains Identical

- OpenShift 4.17+ orchestration
- OpenShift AI 3.4+ MLOps platform
- RHEL Edge 10.2+ and MicroShift runtime
- GitOps (Argo CD), ACM/FlightCtl federation
- Ansible Automation Platform provisioning
- OpenShift Data Foundation storage
- AMQ Streams (Kafka) messaging
- Service Mesh (Istio) for mTLS and observability
- MLflow model registry and experiment tracking
- All security, provenance, and air-gap patterns
- All Red Hat differentiators except vGPU workstation story

### What Changes Completely

| Component Class | NVIDIA Variant | Intel Variant |
|----------------|----------------|---------------|
| **Hardware** | L40S/L4 discrete GPUs | Core Ultra (Panther Lake) NPU + iGPU + CPU heterogeneous |
| **Simulation** | NVIDIA Omniverse Isaac Sim | MuJoCo + unitree_mujoco |
| **RL Training Framework** | Isaac Lab 3.0 | LeRobot (Hugging Face) |
| **VLA Model** | GR00T N1.7 / OpenVLA | LeRobot-trained policies |
| **World Models** | Cosmos Predict 2.5 / Cosmos Transfer 2.5 | (Not available) |
| **Vision/VLM** | Cosmos Reason 2-8B | Intel Robotics AI Suite (25+ models) |
| **Model Optimization** | TensorRT | PyTorch → ONNX → OpenVINO IR |
| **Inference Runtime** | vLLM (CUDA) | OpenVINO Model Server |
| **USD Collaboration** | Nucleus / ovstorage | (Not applicable) |
| **Robotics Middleware** | Isaac Cortex / ROS 2 | ROS 2 Lyrical + Nav2 + SLAM |

## Deployment Topology

The federated hub-and-spoke topology is **preserved**:

- **Hub cluster (datacenter)**: OpenShift with Intel infrastructure nodes for LeRobot training, OpenVINO model conversion, model registry, fleet coordination
- **Spoke clusters (factory sites)**: Single-Node or compact OpenShift clusters for local orchestration
- **Edge devices (robots)**: RHEL Edge 10.2 + MicroShift on Panther Lake hardware (NPU/iGPU-accelerated inference)

The multi-site ACM federation pattern remains unchanged. FlightCtl (Intel's preference for edge fleet management) can optionally replace or augment ACM for edge rollouts.

## The Seven Layers — Intel Variant

### Layer 1: Foundation (Identical)

- OpenShift 4.17+ with ACM for multi-cluster federation
- GitOps via Argo CD across hub/spoke/edge
- OpenShift Data Foundation for storage
- Observability: Prometheus, Loki, Tempo, OpenTelemetry
- Security baseline: Sigstore admission, STIG profiles, FIPS mode
- No changes from NVIDIA variant

### Layer 2: Platform Services (Identical)

- OpenShift AI 3.4+ with Kubeflow Pipelines, MLflow, Jupyter
- Service Mesh 3 (Istio) for mTLS and traffic management
- AMQ Streams 3.x (Kafka) for event streaming
- External Secrets Operator + Vault for secrets management
- No changes from NVIDIA variant

### Layer 3: Intel AI Stack (Complete Replacement)

**Development Tools:**
- VS Code and Jupyter Notebooks (same as NVIDIA variant)
- Kubeflow Pipelines for workflow orchestration (same)
- Python-based scripting (same)

**Simulation and Training:**
- **MuJoCo** physics engine with **unitree_mujoco** integration (replaces Isaac Sim)
- **LeRobot (Hugging Face)** for imitation learning and policy training (replaces Isaac Lab)
- **oneAPI** unified programming model for heterogeneous compute
- **oneDNN** library for deep learning primitives
- **oneCCL** for distributed training coordination

**Robotics Middleware:**
- **ROS 2 Lyrical** as the robotics operating system
- **Nav2** for autonomous navigation
- **SLAM** (Simultaneous Localization and Mapping)
- **Cyclone DDS** for ROS 2 communication
- **ros2_control** for real-time control loops

**Model Optimization and Serving:**
- **OpenVINO** toolkit for model optimization targeting NPU/iGPU/CPU
- Conversion pipeline: PyTorch → ONNX → OpenVINO IR format
- **OpenVINO Model Server** for inference (replaces vLLM)
- Quantization and pruning optimizations for edge deployment

**Vision and Perception (Intel Robotics AI Suite):**
Pre-optimized models (25+ available):
- **Object Detection**: YOLOv8, YOLOv12, DETR
- **Segmentation**: SAM (Segment Anything), SAM2, GroundFloor Segmentation
- **Vision-Language**: CLIP, Qwen2.5VL
- **Depth Estimation**: Depth Anything V2
- **Robotics Policies**: ACT (Action Chunking Transformer), Diffusion Policy, iDP3, Pi0.5+RTC, RDT-1B
- **Navigation**: ITS-Planner, ADBScan clustering, Collaborative-SLAM, FastMapping
- **Language**: Whisper (speech recognition), LLM/VLM integration for task planning

All models are **OpenVINO-optimized** for NPU/iGPU execution.

### Layer 4: Integration Layer (Largely Unchanged)

- Fleet manager for mission coordination (same pattern)
- Mission dispatcher for robot task execution (same pattern)
- WMS/MES stub integrations (same)
- **MCP servers** wrapping MuJoCo APIs (replaces Omniverse MCP servers)
- **LangGraph agents** for orchestration (unchanged framework choice)
- ROS 2 bridge for edge communication (enhanced with Nav2 integration)

### Layer 5: Edge Layer (Enhanced)

- RHEL Edge 10.2+ as device operating system
- MicroShift for lightweight Kubernetes runtime
- **Heterogeneous compute scheduling**:
  - NPU: Compact perception models, low-power always-on inference
  - iGPU (Xe): Dense visual inference, multi-camera perception
  - CPU P-cores: State estimation, path planning, safety arbitration
  - CPU E-cores (isolated): Deterministic control loops, actuator interfaces
- **FlightCtl** option for fleet management and device orchestration (alternative to ACM on edge)
- GitOps-driven containerized model deployment
- EtherCAT/CAN interfaces for actuator communication

### Layer 6: Experience Layer (Degraded)

The **Showcase Console** remains but with reduced visual fidelity:

**Preserved Capabilities:**
- Fleet dashboard and mission control interface
- MLflow integration for experiment tracking and lineage
- Observability dashboards (GPU metrics replaced with NPU/iGPU/CPU metrics)
- Multi-site federation control via ACM or FlightCtl
- Security provenance visualization

**Lost Capabilities:**
- **Kit App Streaming viewport** (no Omniverse equivalent)
- Real-time USD scene rendering and collaboration
- Cosmos-generated synthetic scene visualization

**Replacement Approach:**
- MuJoCo-rendered viewport with static or custom WebGL streaming
- Screenshot-based simulation snapshots in the Console
- Lower visual fidelity than Omniverse but functional

### Layer 7: Operations Layer (Identical)

- Runbooks and deployment guides (adapted for Intel components)
- Demo scripts (re-targeted to MuJoCo/LeRobot/OpenVINO stack)
- Observability dashboards (GPU → NPU/iGPU/CPU metrics)
- Incident playbooks (same operational patterns)

## The Four Core Loops — Intel Variant

### Loop 1: Operational Inference (Factory Runtime)

**Status**: ✅ Fully implementable

**Flow**:
1. On-site cameras publish frames to Kafka (unchanged)
2. Hub-side obstruction-detector pod calls **Intel Robotics AI Suite models** (YOLOv8, SAM, CLIP) via **OpenVINO Model Server** on iGPU for visual reasoning (replaces Cosmos Reason 2-8B)
3. Structured safety alerts emitted to Kafka (unchanged)
4. Fleet manager consumes alerts, replans routes, dispatches missions (unchanged)
5. Edge MicroShift nodes run **LeRobot-trained policies** via **OpenVINO inference on NPU** for manipulation (replaces OpenVLA/GR00T)
6. **ROS 2 + Nav2** drives robot pose and navigation
7. Telemetry federates back to hub via Kafka (unchanged)
8. **MuJoCo digital twin** reflects reality (replaces Isaac Sim)

**What this demonstrates**: Real-time physical AI factory operations on heterogeneous Intel silicon, with the same Red Hat operational substrate.

### Loop 2: Policy Training and Promotion

**Status**: ✅ Fully implementable

**Flow**:
1. Developer collects demonstration data or generates in **MuJoCo + unitree_mujoco** simulation (replaces Isaac Sim)
2. Kubeflow Pipeline triggers **LeRobot training** on OpenShift AI (replaces Isaac Lab)
3. Trained policy stored in **MLflow registry** as PyTorch artifact (unchanged)
4. Pipeline step: **PyTorch → ONNX → OpenVINO IR** conversion (replaces TensorRT)
5. **OpenVINO Model Server** validates performance on OpenShift hub (replaces vLLM validation)
6. Human or automated gate promotes the policy (unchanged)
7. GitOps picks up new serving manifest and rolls out:
   - First to hub (OpenShift deployment)
   - Then via **ACM or FlightCtl** to RHEL Edge + MicroShift targets (unchanged pattern)
8. **ROS 2 nodes** load and execute OpenVINO models on device NPU/iGPU (replaces CUDA inference)

**What this demonstrates**: MLOps for physical AI with OpenShift AI, model registry lineage, and safe multi-site promotion — model-agnostic and infrastructure-agnostic.

### Loop 3: Synthetic Data Generation and Fleet Learning

**Status**: ❌ Not implementable as designed

**Reason**: Intel's stack has no equivalent to **Cosmos Predict 2.5** and **Cosmos Transfer 2.5** for world-foundation-model-driven synthetic scene and action-conditioned video generation.

**Mitigation Options**:
1. **Omit this loop** from the Intel variant (acceptable for demos focused on Loops 1, 2, 4)
2. **Integrate third-party world models** (e.g., open-source alternatives like Genie, SORA-like models if available, or academic research models) — requires significant custom integration work
3. **Leverage MuJoCo procedural generation** for limited synthetic scenario creation (not as powerful as Cosmos but provides some distribution expansion)

**Impact**: The "the stack learns from its own fleet" narrative (a key differentiator for Archetype C customers) is **lost** in the Intel variant unless third-party world models are integrated.

### Loop 4: Agentic Orchestration

**Status**: ✅ Fully implementable

**Flow**:
1. **LangGraph agent** triggered by Showcase Console or scheduled job (unchanged framework)
2. Agent calls **MCP servers** exposing:
   - **MuJoCo APIs** (sim scenario composition, physics queries) — replaces Omniverse MCP servers
   - **Fleet manager APIs** (mission dispatch, route planning) — unchanged
   - **MLflow APIs** (experiment retrieval, model comparison) — unchanged
3. Agent composes what-if experiments:
   - Spin up MuJoCo scenario (replaces Isaac Sim scenario)
   - Run policy variants via OpenVINO serving
   - Collect metrics, summarize results
4. Agent performs fleet interventions (route-around-incident, load-balance) — unchanged
5. Agent gathers data (coverage analysis of training distribution) — unchanged
6. **Llama Stack HIL gate** (Phase 3+) wraps LangGraph for human-in-the-loop approval of physical-state-changing actions (unchanged — wrapping pattern is framework-agnostic)

**What this demonstrates**: Self-hosted LLM agents operating physical AI infrastructure on Red Hat — same narrative, different simulation backend.

## Heterogeneous Compute Scheduling

Intel's stack requires **explicit device targeting** for NPU/iGPU/CPU workloads. This is a net-new operational pattern not present in the NVIDIA variant.

### Device Selection Strategy

OpenVINO's device plugins expose compute resources:

```yaml
# Example: Perception inference pod targeting iGPU
spec:
  containers:
  - name: perception
    image: quay.io/industrial-ai/perception-openvino:latest
    env:
    - name: OPENVINO_DEVICE
      value: "GPU"  # iGPU (Xe)
    resources:
      limits:
        gpu.intel.com/i915: 1  # Intel iGPU resource
```

```yaml
# Example: Compact always-on model targeting NPU
spec:
  containers:
  - name: compact-detector
    image: quay.io/industrial-ai/detector-openvino:latest
    env:
    - name: OPENVINO_DEVICE
      value: "NPU"  # Neural Processing Unit
    resources:
      limits:
        npu.intel.com/npu: 1  # Intel NPU resource
```

```yaml
# Example: Path planning on CPU P-cores
spec:
  containers:
  - name: path-planner
    image: quay.io/industrial-ai/planner:latest
    resources:
      requests:
        cpu: "2"  # P-cores via standard CPU scheduling
```

### Workload → Device Mapping

| Workload Type | Target Device | Rationale |
|---------------|---------------|-----------|
| Compact perception (YOLOv8-nano, small SAM variants) | **NPU** | Low-power, always-on inference; NPU is optimized for this |
| Dense visual inference (multi-camera, segmentation, VLMs) | **iGPU (Xe)** | Parallel processing for vision; iGPU has better throughput than NPU for larger models |
| State estimation, SLAM, path planning | **CPU P-cores** | Complex algorithms requiring general-purpose compute; CPU is most flexible |
| Real-time control loops, actuator interfaces | **CPU E-cores (isolated)** | Deterministic latency requirements; E-cores can be reserved via cpuset isolation |

### Scheduling Enforcement

Use **node labels** and **node selectors** to ensure workloads land on Panther Lake nodes:

```yaml
# Node labeling (applied by cluster admin)
apiVersion: v1
kind: Node
metadata:
  name: edge-robot-01
  labels:
    intel.feature.node.kubernetes.io/npu: "true"
    intel.feature.node.kubernetes.io/gpu: "true"
    hardware.platform: panther-lake
```

```yaml
# Pod targeting Panther Lake edge nodes
spec:
  nodeSelector:
    hardware.platform: panther-lake
  containers:
  - name: perception
    # ... (as above)
```

This is **architecturally similar** to the NVIDIA variant's `nvidia.com/gpu.product: NVIDIA-L40S` node selector pattern — same GitOps operational model, different labels.

## Model Lifecycle: Two-Loop Development

Intel's spec explicitly describes an **Inner Loop / Outer Loop** pattern that maps cleanly to OpenShift AI + Kubeflow Pipelines:

### Inner Loop (Experimentation)

**Environment**: OpenShift AI Workbenches with Jupyter notebooks

**Activities**:
- Fast iteration (30 minutes to 4 hours per cycle)
- Interactive MuJoCo simulation
- LeRobot policy prototyping
- Manual validation and testing
- Developer-driven exploration

**Tooling**:
- Jupyter notebooks with LeRobot + MuJoCo SDKs
- OpenShift AI notebook images with oneAPI/OpenVINO pre-installed
- Direct access to MLflow for experiment logging

**Output**: Candidate policy checkpoints and training configs

### Outer Loop (Production Pipeline)

**Environment**: Kubeflow Pipelines on OpenShift AI

**Activities**:
- Large-scale LeRobot training (multi-hour to multi-day)
- Automated model conversion: **PyTorch → ONNX → OpenVINO IR**
- Optimization: quantization (INT8, FP16), pruning, graph optimization
- Validation against curated scenario suite in MuJoCo
- MLflow model registry promotion
- GitOps-driven staged fleet rollout via ACM/FlightCtl
- Complete lineage and rollback capability

**Pipeline Steps** (Kubeflow Pipeline graph):
1. **Data ingestion**: Load demonstration trajectories or MuJoCo-generated episodes
2. **LeRobot training**: Train policy (BC, Diffusion Policy, ACT, etc.)
3. **Export to PyTorch**: Serialize trained model
4. **Convert to ONNX**: PyTorch → ONNX via `torch.onnx.export`
5. **Optimize with OpenVINO**: ONNX → OpenVINO IR with quantization
6. **Validation**: Run optimized model in MuJoCo test scenarios, measure task success rate + latency
7. **Register in MLflow**: Upload OpenVINO IR + metadata to model registry
8. **Human/automated gate**: Promotion decision based on validation metrics
9. **GitOps commit**: Update Argo CD ApplicationSet with new model version
10. **Staged rollout**: ACM/FlightCtl deploys to edge fleet in waves

**Output**: Production-ready OpenVINO IR models with full lineage back to training data

This is **identical in structure** to the NVIDIA variant's Isaac Lab → TensorRT → vLLM pipeline — only the specific tools change.

## Data Flow and Communication

### Simulation-to-Real Transfer

Intel's spec emphasizes **"Write once, run in sim and real"** via ROS 2:

**Pattern**:
- Same ROS 2 code executes in **unitree_mujoco simulation** and on **real Unitree G1 hardware**
- DDS topics, services, and actions remain identical across sim and real
- Only **sensor drivers** (MuJoCo mock vs. real camera/lidar) and **actuator interfaces** (MuJoCo joint commands vs. EtherCAT/CAN) differ
- Policy models are **environment-agnostic** — they consume ROS 2 topics, not raw hardware

This is the **same sim-to-real pattern** as the NVIDIA variant (Isaac Sim → Jetson) but with MuJoCo replacing Isaac Sim.

### ROS 2 on OpenShift

**Deployment Considerations**:
- ROS 2 nodes run as **containerized workloads** on OpenShift and MicroShift
- **DDS networking** via:
  - **Multus** with dedicated NetworkAttachmentDefinitions for DDS multicast (shop-floor network)
  - **Host network mode** for edge devices where network performance is critical
- **Shared memory optimization** for high-bandwidth topics (e.g., camera feeds) within a node
- **Cyclone DDS** as the DDS implementation (Intel's preference; supports discovery and QoS tuning)

**Security**:
- **DDS Security** (OMG DDS-Security spec) for authentication and encryption of ROS 2 traffic
- Service Mesh mTLS for containerized service-to-service traffic (orthogonal to DDS)

### Kafka Integration

Fleet telemetry and mission events continue to flow via **AMQ Streams (Kafka)**:

- Edge devices publish telemetry (pose, sensor data, alerts) to Kafka topics
- Fleet manager subscribes to telemetry and mission-request topics
- Obstruction detector publishes alerts to Kafka
- Showcase Console subscribes to relevant topics for dashboard updates

This is **unchanged** from the NVIDIA variant — Kafka is the event backbone regardless of simulation or inference stack.

## Intel Robotics AI Suite Integration

The **Intel Robotics AI Suite** is a collection of **25+ pre-optimized robotics models** delivered as OpenVINO IR packages. These replace NVIDIA's NIMs (Cosmos, Metropolis) in the Intel variant.

### Pre-Optimized Models Available

**Vision Models** (object detection, segmentation):
- YOLOv8, YOLOv12 (various sizes: nano, small, medium, large)
- DETR (DEtection TRansformer)
- SAM (Segment Anything Model), SAM2
- Depth Anything V2 (monocular depth estimation)
- GroundFloor Segmentation (floor-plane extraction for navigation)

**Vision-Language Models**:
- CLIP (image-text alignment for zero-shot classification)
- Qwen2.5VL (vision-language model for scene understanding)

**Robotics Policy Models**:
- ACT (Action Chunking Transformer) — imitation learning
- Diffusion Policy — denoising diffusion for action sequences
- iDP3 (improved Diffusion Policy variant)
- Pi0.5+RTC (real-time control variant of Pi0)
- RDT-1B (Robotics Diffusion Transformer, 1B parameters)

**Navigation Components**:
- ITS-Planner (global path planning for structured environments)
- ADBScan (DBSCAN clustering for obstacle grouping)
- Collaborative-SLAM (multi-robot SLAM)
- FastMapping (rapid map generation from sensor data)
- Multi-Camera Integration (fused perception from camera arrays)

**Language and Interaction**:
- Whisper (speech recognition for voice commands)
- LLM/VLM integration hooks for task planning (customer brings their own LLM)

### Deployment Pattern

These models are deployed as **OpenVINO Model Server instances** on OpenShift:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: yolov8-detector
  namespace: perception
spec:
  replicas: 2
  template:
    spec:
      containers:
      - name: ovms
        image: openvino/model_server:latest
        env:
        - name: MODEL_NAME
          value: yolov8n
        - name: MODEL_PATH
          value: /models/yolov8n  # OpenVINO IR from PVC
        - name: TARGET_DEVICE
          value: GPU  # iGPU
        volumeMounts:
        - name: model-store
          mountPath: /models
          readOnly: true
        resources:
          limits:
            gpu.intel.com/i915: 1
      volumes:
      - name: model-store
        persistentVolumeClaim:
          claimName: intel-robotics-ai-suite-models
```

Models are **version-controlled** in the GitOps repo and **promoted** via the same MLflow + Argo CD pattern as custom-trained policies.

### Replacing Cosmos Reason 2-8B (Obstruction Detector)

In the NVIDIA variant, **Cosmos Reason 2-8B** is used for visual reasoning to detect obstructions from camera feeds.

In the Intel variant, this is replaced with a **composition of Intel Robotics AI Suite models**:

**Pipeline**:
1. **YOLOv8** detects objects in camera frames (people, forklifts, pallets, etc.)
2. **SAM** segments detected objects for precise boundaries
3. **Depth Anything V2** estimates depth map to determine object distance
4. **CLIP** performs zero-shot classification (e.g., "is this object a person?", "is this object moving?")
5. **Custom logic** (Python service) combines detections + depth + classification → structured safety alert

This **multi-model pipeline** is more brittle than a single VLM (Cosmos Reason 2) but provides equivalent functionality. It's deployed as a **Kubeflow Pipeline** or a **single service with OVMS sidecars** depending on latency requirements.

## FlightCtl vs. ACM for Edge Fleet Management

Intel's spec highlights **FlightCtl** as their preferred edge fleet management tool. The current architecture uses **ACM (Advanced Cluster Management)** for multi-cluster federation.

### Comparison

| Capability | ACM | FlightCtl |
|------------|-----|-----------|
| **Multi-cluster federation** | ✅ Full (hub-spoke) | ⚠️ Limited (device-centric, not cluster-centric) |
| **GitOps integration** | ✅ Via Argo CD ApplicationSets | ✅ Native GitOps for device configs |
| **Policy enforcement** | ✅ Governance policies across clusters | ⚠️ Device-level config policies |
| **Edge device management** | ⚠️ Via MicroShift clusters as spokes | ✅ Native device lifecycle (enrollment, provisioning, updates) |
| **Bootable container updates** | ⚠️ Manual or Ansible-driven | ✅ Native OTA update orchestration |
| **Observability** | ✅ Cluster-level metrics via Thanos | ✅ Device-level telemetry and status |
| **Maturity** | ✅ GA product | ⚠️ Emerging (preview/EA status as of Sept 2026) |

### Recommendation: Hybrid Approach

**Hub and Spoke Clusters**: Continue using **ACM** for OpenShift-to-OpenShift federation (hub → spoke factory clusters). ACM's cluster-centric governance and policy enforcement are mature and aligned with the multi-site narrative.

**Edge Devices (MicroShift on Panther Lake robots)**: Adopt **FlightCtl** for device lifecycle management (enrollment, bootable container updates, OTA rollouts). FlightCtl's device-centric model maps cleanly to the "hundreds of robots per factory" scaling story.

**Integration Point**: ACM manages spoke clusters; spoke clusters run FlightCtl controllers that manage edge devices. This is a **two-tier federation**:
- Tier 1: Hub → Spokes (ACM)
- Tier 2: Spokes → Edge Devices (FlightCtl)

This approach preserves the ACM multi-cluster story (a Red Hat differentiator) while adopting FlightCtl's device-management strengths.

## Showcase Console Adaptations

The Showcase Console must adapt to the Intel variant's capabilities and limitations.

### Preserved Interfaces

- **Fleet Dashboard**: Mission status, robot telemetry, alerts — unchanged (data source is Kafka, independent of sim backend)
- **MLflow Integration**: Experiment tracking, model lineage, promotion workflow — unchanged
- **Observability Dashboards**: Cluster health, training progress, inference QPS/latency — metrics change (GPU → NPU/iGPU/CPU) but dashboard structure is the same
- **Multi-Site Federation View**: ACM/FlightCtl status, spoke cluster health — unchanged or enhanced with FlightCtl device view
- **Audience Mode Selector**: Three-depth presentation (Archetype A/B/C) — unchanged

### Degraded or Removed Interfaces

- **Kit App Streaming Viewport**: Removed (no Omniverse equivalent in Intel variant)
- **USD Scene Browser**: Removed (MuJoCo does not use USD)
- **Cosmos Synthetic Scene Gallery**: Removed (no Cosmos in Intel variant)

### New or Replacement Interfaces

- **MuJoCo Simulation Viewport**: Custom WebGL or Three.js-based renderer displaying MuJoCo simulation state
  - **Approach 1 (Static)**: MuJoCo renders frames server-side, streams JPEG/PNG to frontend — low fidelity but simple
  - **Approach 2 (Interactive)**: MuJoCo exports scene geometry, frontend renders with Three.js — higher fidelity, more complex
  - **Approach 3 (Hybrid)**: MuJoCo renders + overlays telemetry/annotations in frontend — good balance
- **Heterogeneous Compute Utilization**: New dashboard tile showing NPU/iGPU/CPU utilization and workload placement
- **FlightCtl Device Status**: If FlightCtl is adopted, dashboard shows device enrollment status, OTA update progress, fleet health

### Visual Fidelity Impact

The Intel variant **loses visual fidelity** compared to the NVIDIA variant:
- Omniverse Isaac Sim's photorealistic rendering → MuJoCo's functional but less polished rendering
- Kit App Streaming's interactive 3D viewport → Static or limited-interaction MuJoCo viewer

**Mitigation for Demos**:
- For **Archetype A** (conceptual) audiences: Static high-quality MuJoCo renders or pre-recorded videos are sufficient — the visual fidelity loss is acceptable
- For **Archetype B** (evaluating) audiences: Emphasize the **operational story** (MLOps, GitOps, multi-site) over visual polish — the architecture diagrams and Console interfaces matter more than sim beauty
- For **Archetype C** (deep-dive) audiences: They care about **operational substance, not visuals** — MuJoCo's simplicity may even be preferred (less "demo magic," more engineering reality)

**Strategic framing**: Position the Intel variant as the **"edge-first, lightweight, operationally-focused"** alternative to the NVIDIA variant's **"datacenter-scale, visually immersive, world-model-driven"** approach.

## Security and Provenance

The security and supply-chain posture is **identical** to the NVIDIA variant:

- All container images **Sigstore-signed** via Cosign in CI
- `policy.sigstore.dev` admission controller enforces signature verification
- **SBOMs** (SPDX JSON via Syft) attached as image attestations
- Base images: **UBI9-minimal** or **Intel-optimized UBI variants**
- **STIG-aligned MachineConfig** profiles for host nodes
- **FIPS mode** toggle available (Intel CPUs support AES-NI and other FIPS-required crypto)
- **mTLS via Service Mesh** for east-west traffic
- **Multus NetworkAttachmentDefinitions** for OT network segmentation
- **Secrets via Vault** (External Secrets Operator or in-cluster HashiCorp Vault)

The **"OT-grade provenance" differentiator** (charter §5) is fully preserved — every OpenVINO IR model carries cryptographic lineage back to its LeRobot training run.

## Air-Gap Deployment

Air-gap capability is **fully preserved**:

- All Intel Robotics AI Suite models are **mirrorable** (OpenVINO IR files on PVCs, synced via rsync or object storage)
- LeRobot training framework is **open-source** (no external API dependencies)
- MuJoCo is **open-source** (can be bundled in container images)
- OpenVINO toolkit is **open-source** (Intel's toolkit, no license servers)
- ROS 2 and all middleware are **open-source**
- Container images **mirrored to disconnected registries** via standard OpenShift patterns

The air-gap story is **stronger** with Intel than NVIDIA in some ways:
- No NVIDIA NIM containers (which may have licensing/internet-phone-home dependencies)
- No Omniverse Nucleus (which historically required NVIDIA licensing infrastructure)
- Fully open-source simulation and training stack (MuJoCo + LeRobot vs. Isaac Sim/Lab's proprietary components)

## Red Hat Differentiators — Impact Analysis

Reviewing the eight differentiators from `00-project-charter.md`:

| # | Differentiator | NVIDIA Variant | Intel Variant | Status |
|---|----------------|----------------|---------------|--------|
| **1** | **On-prem and air-gapped** | ✅ Full | ✅ Full (potentially stronger) | **Preserved** |
| **2** | **Containers + VMs + vGPU workstations** | ✅ Full (OpenShift Virt + GPU passthrough) | ⚠️ Partial (vGPU for iGPU exists but less mature than NVIDIA) | **Degraded** |
| **3** | **Hybrid cloud → edge → robot** | ✅ Full | ✅ Full (enhanced with FlightCtl) | **Preserved or Enhanced** |
| **4** | **OpenShift AI MLOps** | ✅ Full | ✅ Full | **Preserved** |
| **5** | **OT-grade provenance** | ✅ Full | ✅ Full | **Preserved** |
| **6** | **Open model choice** | ✅ Full (GR00T + BYO) | ✅ Full (LeRobot is OSS, Intel Suite is pluggable) | **Preserved** |
| **7** | **Agentic orchestration** | ✅ Full | ✅ Full | **Preserved** |
| **8** | **Day-2 lifecycle** | ✅ Full | ✅ Full | **Preserved** |

**Summary**: 7 of 8 differentiators are fully preserved. Only the **vGPU workstation story** (differentiator #2) is weaker, and this is a niche use case (legacy SCADA/PLC workstations with GPU acceleration).

## Strategic Deployment Scenarios

### Scenario 1: Parallel Intel Variant (Recommended)

**Approach**: Maintain the NVIDIA Mega reference as primary; create an Intel variant as a second reference in the same repo under `variants/intel/`.

**Repository Structure**:
```
industrial-ai-showcase/
├── docs/
│   ├── 00-project-charter.md          # Updated to mention both variants
│   ├── 01-architecture-overview.md   # NVIDIA variant (primary)
│   ├── 10-intel-variant-architecture.md  # This document
│   └── ...
├── infrastructure/
│   ├── gitops/                         # Shared GitOps structure
│   │   ├── apps/
│   │   │   ├── nvidia-variant/         # NVIDIA-specific apps
│   │   │   └── intel-variant/          # Intel-specific apps
│   │   └── platform/                   # Shared platform services (RHOAI, Service Mesh, etc.)
│   └── ...
├── components/
│   ├── nvidia/                          # Isaac Sim, GR00T, Cosmos
│   └── intel/                           # MuJoCo, LeRobot, OpenVINO
└── README.md                            # Updated to describe both variants
```

**Value Proposition**: Red Hat becomes the **only platform with both NVIDIA and Intel Physical AI references** — uniquely positioned to serve customers regardless of silicon choice.

**Effort**: ~60% new development (simulation + training + inference layers rebuild)

**Customer Narrative**: "Red Hat operationalizes physical AI on your chosen silicon — NVIDIA for datacenter-scale world models and photorealistic sim, Intel for edge-first heterogeneous compute and open-source stack. Same GitOps, same MLOps, same security — your choice of AI substrate."

### Scenario 2: Intel-First Pivot (Only if abandoning NVIDIA)

**Approach**: Replace the entire NVIDIA stack with Intel's.

**Impact**: All current NVIDIA-specific work (Nucleus, Isaac Sim, GR00T, Cosmos) is deprecated.

**Risk**: NVIDIA's ecosystem momentum (Mega, GR00T, Cosmos) is significantly stronger than Intel's robotics AI story as of Sept 2026. Abandoning NVIDIA means losing the "Mega Blueprint on Red Hat" positioning.

**Effort**: ~70% rewrite (more work to cleanly deprecate NVIDIA components)

**Recommendation**: **Not advised** unless there is a hard business requirement to exit NVIDIA (e.g., Intel partnership exclusivity, customer mandate).

### Scenario 3: Hybrid — Intel Edge, NVIDIA Datacenter (Best of Both Worlds)

**Approach**: Keep NVIDIA stack for datacenter (hub) training/simulation; deploy Intel-optimized inference to MicroShift edge devices.

**Architecture**:
- **Hub cluster**: NVIDIA L40S/L4 for Isaac Sim, GR00T training, Cosmos world models
- **Spoke clusters**: Either NVIDIA or Intel infrastructure (customer choice)
- **Edge devices (MicroShift on robots)**: RHEL Edge 10.2 + Panther Lake with NPU/iGPU inference

**Model Flow**:
1. Train policy in Isaac Lab (hub, NVIDIA GPUs)
2. Export to PyTorch checkpoint
3. Convert PyTorch → ONNX → OpenVINO IR (Kubeflow Pipeline step)
4. Validate OpenVINO model on hub (OpenVINO Model Server with CPU inference for verification)
5. Deploy OpenVINO IR to edge devices (NPU/iGPU inference on Panther Lake)

**Preserved**:
- Full Showcase Console with Kit App Streaming (NVIDIA sim on hub)
- All four loops (including Loop 3 — Cosmos synthetic data generation)
- Intel edge compute story

**Effort**: ~30% new development (edge deployment pipeline + OpenVINO conversion pipeline)

**Value Proposition**: **Best of both worlds** — NVIDIA's superior training/simulation/world-model ecosystem for the datacenter, Intel's edge compute efficiency and cost optimization for deployed robots.

**Customer Narrative**: "Train with NVIDIA's industry-leading simulation and world models in your datacenter on Red Hat OpenShift. Deploy to Intel-powered edge robots for cost-efficient, power-efficient inference at scale. Red Hat federates both seamlessly."

**Recommendation**: **Strongly consider this** if the goal is to demonstrate Red Hat's multi-vendor hardware flexibility while preserving the NVIDIA visual and world-model advantages.

## Implementation Roadmap

If proceeding with **Scenario 1 (Parallel Variant)** or **Scenario 3 (Hybrid)**:

### Phase 1: Proof of Concept (4-6 weeks)

**Goal**: Validate that MuJoCo + LeRobot + OpenVINO can deliver Loop 1 (operational inference) and Loop 2 (training/promotion) on OpenShift.

**Deliverables**:
1. MuJoCo + unitree_mujoco running in a container on OpenShift
2. LeRobot training a simple imitation learning policy in OpenShift AI Workbench
3. PyTorch → ONNX → OpenVINO IR conversion pipeline (manual or simple script)
4. OpenVINO Model Server serving the converted policy
5. ROS 2 node consuming the policy and driving a simulated Unitree G1 in MuJoCo
6. Telemetry flowing to Kafka and visible in a basic dashboard

**Success Criteria**: End-to-end loop from MuJoCo sim → LeRobot training → OpenVINO serving → ROS 2 execution, all on OpenShift.

### Phase 2: MLOps Integration (6-8 weeks)

**Goal**: Integrate LeRobot + OpenVINO into the existing OpenShift AI + MLflow + Kubeflow Pipelines infrastructure.

**Deliverables**:
1. Kubeflow Pipeline for LeRobot training → ONNX → OpenVINO IR → validation → MLflow registration
2. MLflow model registry storing OpenVINO IR models with lineage to training runs
3. GitOps integration: Argo CD ApplicationSet deploying OpenVINO Model Server instances from MLflow-registered models
4. Staged rollout to MicroShift edge nodes (simulated or real Panther Lake hardware if available)
5. Rollback capability tested

**Success Criteria**: Loop 2 (policy training and promotion) fully operational with the same MLOps rigor as the NVIDIA variant.

### Phase 3: Intel Robotics AI Suite Integration (4-6 weeks)

**Goal**: Replace Cosmos Reason 2-8B with Intel Robotics AI Suite models for Loop 1 perception.

**Deliverables**:
1. YOLOv8, SAM, Depth Anything V2, CLIP models deployed via OpenVINO Model Server
2. Obstruction-detector service refactored to call Intel models instead of Cosmos
3. iGPU targeting validated (workloads land on Intel GPU nodes)
4. Performance benchmarking: latency and throughput vs. Cosmos Reason baseline (accept degradation if minor)

**Success Criteria**: Loop 1 (operational inference) working with Intel perception stack, alerts flowing to fleet manager.

### Phase 4: Showcase Console Adaptations (6-8 weeks)

**Goal**: Adapt the Showcase Console to support both NVIDIA and Intel variants.

**Deliverables**:
1. Variant selector in Console (toggle between NVIDIA and Intel backends)
2. MuJoCo viewport integration (choose Approach 2 or 3 from earlier section)
3. Heterogeneous compute utilization dashboard (NPU/iGPU/CPU metrics)
4. FlightCtl integration (if adopting FlightCtl for Intel edge devices)
5. Updated demo scripts for all three audience archetypes (A/B/C) targeting Intel variant

**Success Criteria**: Console can drive a complete demo (Loops 1, 2, 4) for the Intel variant with the same audience-mode flexibility as the NVIDIA variant.

### Phase 5: Documentation and Sales Enablement (4 weeks)

**Goal**: Produce customer-ready documentation and sales materials for the Intel variant.

**Deliverables**:
1. Intel variant architecture diagram (equivalent to `06-mega-mapping.svg` for NVIDIA)
2. Component catalog addendum for Intel-specific components
3. Deployment quickstart for Intel variant
4. Differentiator mapping updated to show Intel variant coverage
5. Talk tracks for sales teams: when to lead with NVIDIA vs. Intel vs. hybrid
6. Reference customer narratives updated (identify Intel-relevant customer stories)

**Success Criteria**: Sales and field teams can present the Intel variant confidently; SAs can deploy it in customer labs.

### Phase 6 (Optional): FlightCtl Production Integration (6-8 weeks)

**Goal**: Replace or augment ACM with FlightCtl for edge device management in the Intel variant.

**Deliverables**:
1. FlightCtl deployed on spoke clusters
2. MicroShift edge devices enrolled in FlightCtl
3. Bootable container OTA updates via FlightCtl
4. GitOps-driven device config management
5. FlightCtl observability integrated into Showcase Console

**Success Criteria**: Edge fleet lifecycle (enrollment, update, rollback) managed by FlightCtl, demonstrated in a live Intel variant demo.

## Risks and Mitigations

### Risk 1: MuJoCo Visual Fidelity Insufficient for Archetype A Demos

**Impact**: Archetype A (early-stage) customers expect visually compelling demos; MuJoCo may feel "toy-like" compared to Omniverse.

**Likelihood**: Medium

**Mitigation**:
- Lead with NVIDIA variant for visual-first demos (Archetype A)
- Position Intel variant for Archetype B/C (operational depth, not visual polish)
- Use pre-recorded high-quality MuJoCo renders for static demo slides
- If budget allows, integrate **NVIDIA Isaac Sim for visualization only** (render frames from MuJoCo state) as a hybrid approach

### Risk 2: No Cosmos Equivalent Blocks Loop 3

**Impact**: The synthetic data generation loop (Loop 3) is a key differentiator for advanced customers (Archetype C); omitting it weakens the Intel variant's story.

**Likelihood**: High (no Intel equivalent exists)

**Mitigation**:
- Clearly scope Intel variant as "Loops 1, 2, 4 only" in documentation and sales materials
- Position Intel variant as "edge-first operational AI" vs. NVIDIA's "datacenter-scale generative AI"
- If Loop 3 is critical for a customer, recommend Scenario 3 (Hybrid: NVIDIA datacenter + Intel edge)
- Track open-source world model developments (Genie, diffusion-based world models) for potential future integration

### Risk 3: Panther Lake Hardware Availability

**Impact**: Intel Core Ultra (Panther Lake) with NPU/iGPU may not be generally available or accessible for development by Q4 2026.

**Likelihood**: Medium (Intel roadmaps are subject to change)

**Mitigation**:
- Validate Intel's Panther Lake availability before committing to Phase 1 PoC
- Fallback: Use Intel Meteor Lake or Raptor Lake with iGPU (no NPU) for initial validation
- Design scheduling abstraction so NPU vs. CPU inference is a config toggle (graceful degradation if NPU unavailable)
- Run initial PoC on OpenShift with CPU-only OpenVINO inference; optimize for NPU/iGPU later

### Risk 4: LeRobot Maturity vs. Isaac Lab

**Impact**: LeRobot (Hugging Face) is less mature than NVIDIA Isaac Lab; may lack features or stability.

**Likelihood**: Medium

**Mitigation**:
- Validate LeRobot in Phase 1 PoC with simple tasks (imitation learning, basic manipulation)
- Contribute upstream to LeRobot if gaps are found (aligns with Red Hat's open-source ethos)
- If LeRobot is insufficient, evaluate alternatives: **Stable Baselines3**, **RLlib**, or custom PyTorch training loops
- Document LeRobot limitations transparently; position as "emerging open-source alternative" rather than "NVIDIA replacement"

### Risk 5: Split Maintenance Burden

**Impact**: Maintaining two parallel variants (NVIDIA + Intel) doubles documentation, testing, and update effort.

**Likelihood**: High

**Mitigation**:
- Maximize code reuse: shared GitOps structure, shared platform layer (RHOAI, Service Mesh, ACM)
- Variant-specific code isolated in `components/nvidia/` and `components/intel/` directories
- Shared CI/CD pipelines with variant-specific test suites
- Prioritize NVIDIA variant as primary; Intel variant is "best-effort" unless customer demand justifies parity
- Consider Scenario 3 (Hybrid) instead of Scenario 1 (Parallel) to reduce scope

## Open Questions

1. **Strategic intent**: Is the Intel variant driven by a strategic Intel partnership, a specific customer requirement, or exploratory interest?
2. **Hardware access**: Do we have confirmed access to Panther Lake hardware with NPU/iGPU for development and testing?
3. **Loop 3 criticality**: Can the Intel variant succeed without synthetic data generation (Loop 3), or is this a dealbreaker for target customers?
4. **Variant prioritization**: If pursuing parallel variants, is the Intel variant equal priority to NVIDIA, or is it secondary/opportunistic?
5. **FlightCtl adoption**: Is FlightCtl integration a hard requirement (Intel partnership deliverable) or optional (nice-to-have for edge story)?
6. **Customer pipeline**: Are there specific customers or opportunities that require an Intel variant, or is this exploratory positioning?

## Recommendations

Based on the analysis:

1. **Pursue Scenario 3 (Hybrid: Intel Edge, NVIDIA Datacenter)** if the goal is to demonstrate multi-vendor hardware flexibility while preserving NVIDIA's visual and world-model strengths. This is the **lowest-risk, highest-value** path.

2. **Pursue Scenario 1 (Parallel Variant)** if there is a strategic Intel partnership or customer demand for a fully Intel-based stack. Accept the maintenance burden and Loop 3 omission as trade-offs.

3. **Avoid Scenario 2 (Intel-First Pivot)** unless there is a hard requirement to exit NVIDIA. The NVIDIA ecosystem's momentum and visual polish are significant advantages.

4. **Validate hardware availability** (Panther Lake NPU/iGPU access) before committing resources. If hardware is unavailable, defer Intel variant work until Q1-Q2 2027.

5. **Start with Phase 1 PoC** (4-6 weeks) to de-risk the technical unknowns (MuJoCo, LeRobot, OpenVINO integration) before committing to full implementation.

6. **Clarify strategic intent** with stakeholders: Is this a partnership deliverable, a customer requirement, or exploratory work? The answer shapes prioritization and scope.

## Conclusion

An Intel-based variant of the industrial-ai-showcase is **technically feasible** and **strategically valuable** as a demonstration of Red Hat's platform-agnostic approach to physical AI. The Red Hat substrate (OpenShift, RHOAI, GitOps, security, observability) is fully reusable; the AI/simulation layer requires significant rework but leverages open-source alternatives (MuJoCo, LeRobot, OpenVINO) that align with Red Hat's open-source values.

The primary trade-offs are:
- **Visual fidelity**: MuJoCo vs. Omniverse
- **World models**: No Cosmos equivalent (Loop 3 omitted)
- **Maintenance burden**: Dual-variant codebase

The primary gains are:
- **Multi-vendor positioning**: "Run physical AI on NVIDIA or Intel — Red Hat federates both"
- **Edge compute efficiency**: NPU/iGPU heterogeneous scheduling story
- **Open-source alignment**: Fully OSS simulation/training stack (stronger air-gap story)

**Next step**: Clarify strategic intent and hardware availability, then proceed with Phase 1 PoC if validated.