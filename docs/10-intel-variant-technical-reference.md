# Intel Physical AI Variant - Technical Reference for R&D Team

**Purpose:** Technical guide for R&D validation phase  
**Audience:** Engineering team executing hands-on validation  
**Date:** September 24, 2026  
**Related:** Team Action Plan (`11-intel-variant-team-action-plan.md`)

---

## Overview

This document provides technical details needed for R&D validation of the Intel Physical AI variant. It covers:
- What components replace NVIDIA stack
- How the architecture layers map
- Which loops work (and which don't)
- What technologies to integrate
- What questions to answer during validation

**Key Point:** Intel variant replaces the AI/simulation layer (MuJoCo, LeRobot, OpenVINO) while keeping **100% of the Red Hat substrate** identical (OpenShift, RHOAI, GitOps, ACM, observability).

---

## Component Mapping: NVIDIA → Intel

| Component Class | NVIDIA Variant | Intel Variant |
|----------------|----------------|---------------|
| **Hardware** | L40S/L4 discrete GPUs | Core Ultra (Panther Lake) NPU + iGPU + CPU heterogeneous |
| **Simulation** | NVIDIA Omniverse Isaac Sim | **MuJoCo** + unitree_mujoco |
| **RL Training Framework** | Isaac Lab 3.0 | **LeRobot** (Hugging Face) |
| **VLA Model** | GR00T N1.7 / OpenVLA | LeRobot-trained policies |
| **World Models** | Cosmos Predict / Transfer | **(Not available)** ⚠️ |
| **Vision/VLM** | Cosmos Reason 2-8B | **Intel Robotics AI Suite** (25+ models) |
| **Model Optimization** | TensorRT | PyTorch → ONNX → **OpenVINO IR** |
| **Inference Runtime** | vLLM (CUDA) | **OpenVINO Model Server** |
| **Robotics Middleware** | Isaac Cortex / ROS 2 | **ROS 2 Lyrical** + Nav2 + SLAM |

**Red Hat Platform** (Unchanged):
- OpenShift 4.17+ orchestration
- OpenShift AI 3.4+ MLOps (Kubeflow, MLflow, Jupyter)
- RHEL Edge 10.2+ and MicroShift
- GitOps (Argo CD), ACM/FlightCtl
- AMQ Streams (Kafka), Service Mesh (Istio)
- OpenShift Data Foundation storage

---

## The Seven Layers (What Goes Where)

### Layer 1: Foundation (Identical)
- OpenShift 4.17+ with ACM
- GitOps via Argo CD
- OpenShift Data Foundation storage
- Observability: Prometheus, Loki, Tempo, OpenTelemetry
- Security: Sigstore admission, FIPS mode

### Layer 2: Platform Services (Identical)
- OpenShift AI 3.4+ (Kubeflow Pipelines, MLflow, Jupyter)
- Service Mesh 3 (Istio) for mTLS
- AMQ Streams 3.x (Kafka)
- External Secrets Operator + Vault

### Layer 3: Intel AI Stack ⚡ **(Where the work happens)**

**Simulation and Training:**
- **MuJoCo** physics engine + **unitree_mujoco** integration
- **LeRobot** for imitation learning and policy training
- **oneAPI** unified programming model
- **oneDNN** library for deep learning primitives

**Robotics Middleware:**
- **ROS 2 Lyrical** as robotics operating system
- **Nav2** for autonomous navigation
- **SLAM** (Simultaneous Localization and Mapping)
- **Cyclone DDS** for ROS 2 communication
- **ros2_control** for real-time control loops

**Model Optimization and Serving:**
- **OpenVINO** toolkit for model optimization
- Conversion: PyTorch → ONNX → OpenVINO IR
- **OpenVINO Model Server** for inference
- Quantization and pruning for edge deployment

**Vision and Perception (Intel Robotics AI Suite):**
- **Object Detection**: YOLOv8, YOLOv12, DETR
- **Segmentation**: SAM, SAM2, GroundFloor Segmentation
- **Vision-Language**: CLIP, Qwen2.5VL
- **Depth Estimation**: Depth Anything V2
- **Robotics Policies**: ACT, Diffusion Policy, iDP3, Pi0.5+RTC, RDT-1B
- **Navigation**: ITS-Planner, ADBScan, Collaborative-SLAM, FastMapping
- **Language**: Whisper, LLM/VLM integration

All models **OpenVINO-optimized** for NPU/iGPU execution.

### Layer 4: Integration Layer (Largely Unchanged)
- Fleet manager, mission dispatcher (same patterns)
- **MCP servers** wrapping MuJoCo APIs
- **LangGraph agents** for orchestration
- ROS 2 bridge for edge communication

### Layer 5: Edge Layer (Enhanced)
- RHEL Edge 10.2+ as device OS
- MicroShift for lightweight Kubernetes
- **Heterogeneous compute targeting**:
  - **NPU**: Compact perception models, low-power inference
  - **iGPU (Xe)**: Dense visual inference, multi-camera perception
  - **CPU P-cores**: State estimation, path planning, safety
  - **CPU E-cores**: Deterministic control loops, actuator interfaces
- FlightCtl option for fleet management
- GitOps-driven model deployment

### Layer 6: Experience Layer (Degraded)
- Fleet dashboard and MLflow integration preserved
- **Lost**: Kit App Streaming viewport, USD rendering
- **Replacement**: MuJoCo-rendered viewport (lower fidelity)

### Layer 7: Operations Layer (Identical)
- Observability dashboards (adapted for NPU/iGPU/CPU metrics)
- Same operational patterns

---

## The Four Core Loops: What Works, What Doesn't

### Loop 1: Operational Inference ✅ **Implementable**

**Flow**:
1. Cameras publish frames to Kafka
2. **Intel Robotics AI Suite models** (YOLOv8, SAM, CLIP) via **OpenVINO Model Server** detect obstructions
3. Alerts to fleet manager
4. Fleet manager replans routes, dispatches missions
5. Edge runs **LeRobot-trained policies** via **OpenVINO inference on NPU/iGPU**
6. **ROS 2 + Nav2** drives robot pose and navigation
7. Telemetry to Kafka
8. **MuJoCo digital twin** reflects reality

**What this validates**: Real-time physical AI operations on Intel silicon.

**R&D Focus**: Validate perception pipeline (Intel models replace Cosmos), inference latency acceptable.

---

### Loop 2: Policy Training and Promotion ✅ **Implementable**

**Flow**:
1. Generate demonstrations in **MuJoCo + unitree_mujoco**
2. **LeRobot training** on OpenShift AI
3. Store trained policy in **MLflow registry** (PyTorch checkpoint)
4. Pipeline step: **PyTorch → ONNX → OpenVINO IR** conversion
5. **OpenVINO Model Server** validates performance
6. Human/automated gate promotes policy
7. GitOps rolls out via Argo CD
8. **ACM or FlightCtl** deploys to edge (MicroShift + OpenVINO runtime)
9. **ROS 2 nodes** execute OpenVINO models on device

**What this validates**: MLOps for physical AI with Intel stack, full lineage, safe promotion.

**R&D Focus**: Validate LeRobot training works, PyTorch→ONNX→OpenVINO conversion succeeds, MLflow integration clean.

---

### Loop 3: Synthetic Data Generation ❌ **NOT Implementable**

**Why**: Intel stack has **no equivalent** to Cosmos Predict/Transfer for world-foundation-model-driven synthetic scene generation.

**Impact**: The "the stack learns from its own fleet" narrative is **lost** unless:
- Third-party world models integrated (Genie, etc.)
- MuJoCo procedural generation used (limited)
- **Scenario 3 (Hybrid)** pursued: NVIDIA datacenter for Cosmos + Intel edge

**R&D Focus**: Assess if Loop 3 omission is acceptable for target use cases.

---

### Loop 4: Agentic Orchestration ✅ **Implementable**

**Flow**:
1. **LangGraph agent** triggered by Console or schedule
2. Agent calls **MCP servers** exposing:
   - **MuJoCo APIs** (scenario composition, physics queries)
   - **Fleet manager APIs** (mission dispatch, route planning)
   - **MLflow APIs** (experiment retrieval, model comparison)
3. Agent composes what-if experiments, fleet interventions, data gathering
4. **Llama Stack HIL gate** (Phase 3+) wraps LangGraph for human-in-loop approval

**What this validates**: Self-hosted LLM agents operating physical AI infrastructure.

**R&D Focus**: MCP + MuJoCo integration, agent orchestration patterns.

---

## Model Lifecycle: Inner Loop / Outer Loop

### Inner Loop (Experimentation)
**Environment**: OpenShift AI Workbenches with Jupyter notebooks

**Activities**:
- Fast iteration (30 min - 4 hours per cycle)
- Interactive MuJoCo simulation
- LeRobot policy prototyping
- Manual validation and testing
- Developer-driven exploration

**Tooling**:
- Jupyter notebooks with LeRobot + MuJoCo SDKs
- OpenShift AI notebook images with oneAPI/OpenVINO pre-installed
- Direct MLflow access for experiment logging

**Output**: Candidate policy checkpoints and training configs

---

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

**Pipeline Steps** (Kubeflow Pipeline):
1. Data ingestion (demo trajectories or MuJoCo episodes)
2. LeRobot training (BC, Diffusion Policy, ACT)
3. Export to PyTorch
4. Convert to ONNX (`torch.onnx.export`)
5. Optimize with OpenVINO (ONNX → OpenVINO IR with quantization)
6. Validation (run in MuJoCo test scenarios, measure success rate + latency)
7. Register in MLflow (upload OpenVINO IR + metadata)
8. Human/automated gate (promotion decision based on metrics)
9. GitOps commit (update Argo CD ApplicationSet with new model version)
10. Staged rollout (ACM/FlightCtl deploys to edge fleet in waves)

**Output**: Production-ready OpenVINO IR models with full lineage

**R&D Focus**: Validate this pipeline works end-to-end, no broken steps.

---

## Data Flow and Communication

### Simulation-to-Real Transfer Pattern

**Key Principle**: "Write once, run in sim and real" via ROS 2

- Same ROS 2 code executes in **unitree_mujoco simulation** and on **real Unitree G1 hardware**
- DDS topics, services, actions remain identical across sim and real
- Only **sensor drivers** (MuJoCo mock vs real camera/lidar) and **actuator interfaces** (MuJoCo commands vs EtherCAT/CAN) differ
- Policy models are **environment-agnostic** — they consume ROS 2 topics, not raw hardware

**R&D Focus**: Validate ROS 2 + MuJoCo bridge works, policies transfer to edge execution.

---

### ROS 2 on OpenShift Deployment

**Considerations**:
- ROS 2 nodes as **containerized workloads** on OpenShift and MicroShift
- **DDS networking** options:
  - **Multus** with dedicated NetworkAttachmentDefinitions for DDS multicast
  - **Host network mode** for edge devices (network performance critical)
- **Shared memory** optimization for high-bandwidth topics (camera feeds)
- **Cyclone DDS** as DDS implementation (supports discovery and QoS tuning)

**Security**:
- **DDS Security** (OMG DDS-Security spec) for auth and encryption
- Service Mesh mTLS for containerized service-to-service traffic

---

### Kafka Integration (Unchanged)

Fleet telemetry and mission events via **AMQ Streams (Kafka)**:
- Edge devices publish telemetry (pose, sensor data, alerts) to Kafka topics
- Fleet manager subscribes to telemetry and mission-request topics
- Obstruction detector publishes alerts to Kafka
- Console subscribes for dashboard updates

**R&D Focus**: Kafka integration same as NVIDIA variant, no changes needed.

---

## Intel Robotics AI Suite: What Models Are Available

The **Intel Robotics AI Suite** provides **25+ pre-optimized robotics models** as OpenVINO IR packages.

### Vision Models (Object Detection, Segmentation)
- **YOLOv8, YOLOv12** (various sizes: nano, small, medium, large)
- **DETR** (DEtection TRansformer)
- **SAM, SAM2** (Segment Anything Model)
- **Depth Anything V2** (monocular depth estimation)
- **GroundFloor Segmentation** (floor-plane extraction for navigation)

### Vision-Language Models
- **CLIP** (image-text alignment for zero-shot classification)
- **Qwen2.5VL** (vision-language model for scene understanding)

### Robotics Policy Models
- **ACT** (Action Chunking Transformer) — imitation learning
- **Diffusion Policy** — denoising diffusion for action sequences
- **iDP3** (improved Diffusion Policy variant)
- **Pi0.5+RTC** (real-time control variant of Pi0)
- **RDT-1B** (Robotics Diffusion Transformer, 1B parameters)

### Navigation Components
- **ITS-Planner** (global path planning for structured environments)
- **ADBScan** (DBSCAN clustering for obstacle grouping)
- **Collaborative-SLAM** (multi-robot SLAM)
- **FastMapping** (rapid map generation from sensor data)
- **Multi-Camera Integration** (fused perception from camera arrays)

### Language and Interaction
- **Whisper** (speech recognition for voice commands)
- LLM/VLM integration hooks for task planning (customer brings their own LLM)

**Deployment**: Models deployed as **OpenVINO Model Server instances** on OpenShift, version-controlled in GitOps repo, promoted via MLflow + Argo CD.

---

### Replacing Cosmos Reason 2-8B (Obstruction Detector)

NVIDIA variant uses **Cosmos Reason 2-8B** for visual reasoning to detect obstructions.

Intel variant replaces with **multi-model pipeline**:

1. **YOLOv8** detects objects in camera frames (people, forklifts, pallets)
2. **SAM** segments detected objects for precise boundaries
3. **Depth Anything V2** estimates depth map to determine object distance
4. **CLIP** performs zero-shot classification ("is this a person?", "is this moving?")
5. **Custom logic** (Python service) combines detections + depth + classification → structured safety alert

**Deployment**: Kubeflow Pipeline or single service with OVMS sidecars (depending on latency requirements).

**R&D Focus**: Validate this multi-model pipeline achieves acceptable accuracy vs Cosmos baseline.

---

## Technical Validation & Research Areas

### Core Questions to Answer During R&D

#### MuJoCo + Unitree G1 Simulation
- Can MuJoCo simulate Unitree G1 with sufficient fidelity for policy training?
- Does unitree_mujoco support manipulation tasks for warehouse demos?
- How does visual quality compare to Isaac Sim for demos (acceptable degradation)?

#### LeRobot Training Framework
- Is LeRobot mature enough for production-grade policy training?
- What gaps exist vs Isaac Lab (RL algorithms, training stability, scenario config)?
- Can LeRobot scale to multi-GPU training on OpenShift AI?
- Are there alternatives if gaps found (Stable Baselines3, RLlib, custom PyTorch)?

#### PyTorch → ONNX → OpenVINO IR Conversion
- Does conversion work end-to-end for robotics policies (ACT, Diffusion Policy)?
- What accuracy/latency degradation occurs during quantization?
- Can this integrate cleanly into Kubeflow Pipelines with MLflow tracking?

#### Intel Hardware Availability and Performance
- Is Panther Lake (NPU/iGPU) accessible for Q4 2026 / Q1 2027 development?
- What fallback hardware exists (Meteor Lake, Raptor Lake, CPU-only)?
- Can NPU/iGPU device plugins integrate with OpenShift?
- How does OpenVINO inference latency compare to vLLM (CUDA) baseline?
- Can OpenVINO Model Server handle multi-robot fleet inference QPS?

#### Platform Integration
- Can OpenVINO IR models store in MLflow with full lineage?
- Does Kubeflow Pipelines support PyTorch → ONNX → OpenVINO workflow?
- Can ROS 2 nodes consume MuJoCo state and actuate robot in sim?
- Does ROS 2 bridge work identically in sim (MuJoCo) and real hardware (MicroShift)?

#### Intel Robotics AI Suite
- Are pre-optimized models (YOLOv8, SAM, CLIP) production-ready?
- Can they replace Cosmos Reason 2-8B with acceptable accuracy?
- How do we version and deploy Intel-provided models vs custom-trained policies?

#### Loop 3 Gap Assessment
- Can Intel variant succeed without synthetic data generation?
- Are there open-source world model alternatives (Genie, diffusion models)?
- Is Scenario 3 (Hybrid: NVIDIA datacenter for Cosmos + Intel edge) required?

---

## R&D Validation Approach (4 Steps)

### Step 1: Local Technology Validation
**Focus**: Prove core stack works on workstation before OpenShift

**What to Test**:
- MuJoCo + unitree_mujoco visualization
- LeRobot training (simple imitation learning policy)
- PyTorch → ONNX → OpenVINO IR conversion
- OpenVINO inference locally (CPU mode)

**Success**: End-to-end workflow completes without errors

---

### Step 2: OpenShift Integration PoC
**Focus**: Deploy to OpenShift AI, validate platform integration

**What to Test**:
- Containerize MuJoCo simulation
- LeRobot training on OpenShift AI Workbench
- Kubeflow Pipeline for model conversion
- MLflow model registry integration
- OpenVINO Model Server deployment
- Inference via REST API

**Success**: Complete training workflow on OpenShift, models in MLflow, serving works

---

### Step 3: Perception Stack Validation
**Focus**: Validate Intel Robotics AI Suite for Loop 1

**What to Test**:
- Deploy Intel models (YOLOv8, SAM, CLIP) via OVMS
- Build obstruction-detector pipeline
- Test perception accuracy vs Cosmos baseline
- Measure end-to-end latency (camera → alert)
- Test on iGPU if available, else CPU

**Success**: Perception pipeline produces accurate alerts, latency acceptable

---

### Step 4: Decision Checkpoint
**Focus**: Go/No-Go decision based on findings

**Review**:
- Does MuJoCo + LeRobot + OpenVINO work end-to-end?
- Is performance acceptable (latency, training time)?
- Can Intel models replace Cosmos?
- What critical gaps or blockers found?
- Is Loop 3 gap acceptable or dealbreaker?

**Decision**: GO (proceed to full implementation) / DEFER (wait for hardware/maturity) / NO-GO (gaps too large)

---

## Known Blockers & Mitigations

### Blocker 1: Panther Lake Hardware Unavailable
**Impact**: Cannot test NPU inference  
**Mitigation**: 
- Fallback to Meteor Lake (iGPU only)
- CPU-only OpenVINO for initial validation
- Design abstraction so NPU vs CPU is config toggle
- Request Intel DevCloud access

### Blocker 2: LeRobot Maturity Gaps
**Impact**: Training instability, missing features  
**Mitigation**:
- Start with simple tasks (imitation learning, basic manipulation)
- Contribute upstream fixes if needed
- Evaluate alternatives (Stable Baselines3, RLlib)
- Document limitations transparently

### Blocker 3: MuJoCo Visual Fidelity Insufficient
**Impact**: Demo quality unacceptable for early-stage customers  
**Mitigation**:
- Target operational depth demos (Archetype B/C), not visual-first
- Use pre-recorded high-quality MuJoCo renders for slides
- Lead with NVIDIA variant for visual demos

### Blocker 4: Loop 3 Gap (No World Model)
**Impact**: Synthetic data generation not possible  
**Mitigation**:
- Accept Loop 3 omission for Intel-only variant
- Pursue Scenario 3 (Hybrid: NVIDIA datacenter + Intel edge)
- Track open-source world model alternatives

---

## Success Metrics for R&D Phase

### Technical Validation Success:
- [ ] MuJoCo simulates Unitree G1 with acceptable fidelity
- [ ] LeRobot trains a policy on OpenShift AI without errors
- [ ] PyTorch → ONNX → OpenVINO conversion works end-to-end
- [ ] OpenVINO inference latency < 100ms for perception models
- [ ] Intel Robotics AI Suite models achieve >80% accuracy vs baseline
- [ ] Complete workflow: train (LeRobot) → optimize (OpenVINO) → serve (OVMS) → execute (ROS 2 + MuJoCo)

### Integration Success:
- [ ] Models stored in MLflow with full lineage
- [ ] Kubeflow Pipeline automates conversion workflow
- [ ] ROS 2 + MuJoCo bridge works in sim
- [ ] OpenVINO Model Server deployed on OpenShift

### Performance Success:
- [ ] Inference latency meets requirements (< 500ms end-to-end for Loop 1)
- [ ] Training time acceptable (comparable to Isaac Lab or within 2x)
- [ ] Perception accuracy acceptable (>80% vs Cosmos baseline)

---

## Key Technologies - Quick Reference

### MuJoCo
**What**: Physics simulation engine  
**Why**: Replaces Isaac Sim  
**Learn**: Simulation setup, unitree_mujoco integration, ROS 2 bridge  
**Docs**: https://mujoco.readthedocs.io/

### LeRobot
**What**: Imitation learning framework  
**Why**: Replaces Isaac Lab  
**Learn**: Dataset format, training workflows, supported policies (ACT, Diffusion Policy)  
**Docs**: https://github.com/huggingface/lerobot

### OpenVINO
**What**: Model optimization toolkit  
**Why**: Core optimization and serving layer  
**Learn**: PyTorch/ONNX → OpenVINO IR, quantization, device targeting (NPU/iGPU/CPU)  
**Docs**: https://docs.openvino.ai/

### ROS 2 Lyrical
**What**: Robotics middleware  
**Why**: Bridge between sim/inference and robot execution  
**Learn**: Nodes, topics, services, actions, Cyclone DDS, Nav2, ros2_control  
**Docs**: https://docs.ros.org/

### Intel Robotics AI Suite
**What**: Pre-optimized models and AMR components  
**Why**: Replaces Cosmos for perception  
**Learn**: Model deployment, YOLOv8/SAM/CLIP usage, performance tuning  
**Docs**: Request from Intel if private

---

## Related Documents

- **Team Action Plan**: `docs/11-intel-variant-team-action-plan.md` (4-step R&D approach, immediate actions)
- **Intel Physical AI Spec**: https://gist.github.com/redhatHameed/441dc8ca5614fa50d9f7977f49424cdd
- **Full Architecture** (strategic context): `docs/10-intel-variant-architecture.md` (if needed for background)

---

**Document Owner:** Red Hat Physical AI Showcase Team  
**Status:** Technical reference for R&D validation  
**Last Updated:** September 24, 2026