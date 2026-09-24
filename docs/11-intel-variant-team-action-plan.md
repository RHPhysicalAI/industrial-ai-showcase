# Intel Physical AI Variant - Team Action Plan

**Status:** Architecture Defined - Ready for R&D Validation  
**Date:** September 24, 2026  
**Team:** Red Hat Physical AI Showcase  
**Context:** Intel variant of industrial-ai-showcase reference implementation

---

## 📋 What We've Completed

### ✅ Strategic Architecture & Evaluation Framework
- **Intel variant architecture documented** (`docs/10-intel-variant-technical-reference.md`)
- **Component mapping defined** (NVIDIA → Intel across all seven layers)
- **Three strategic scenarios evaluated**:
  - Scenario 1: Parallel Variant (both NVIDIA + Intel)
  - Scenario 2: Intel-First Pivot (not recommended)
  - Scenario 3: Hybrid (NVIDIA datacenter + Intel edge) — **recommended**
- **The four core loops analyzed** for Intel feasibility:
  - Loop 1 (Operational Inference): ✅ Implementable
  - Loop 2 (Training & Promotion): ✅ Implementable
  - Loop 3 (Synthetic Data): ❌ Not implementable (no Cosmos equivalent)
  - Loop 4 (Agentic Orchestration): ✅ Implementable
- **R&D validation areas identified** (technical unknowns requiring investigation)
- **Go/No-Go decision framework** established

**Documents:** 
- Architecture: `docs/10-intel-variant-technical-reference.md` (~675 lines, strategic focus)

---

## 🔬 R&D Validation Phase (4-6 Weeks)

**Goal:** De-risk technical unknowns before committing to full implementation.

This phase answers: "Can the Intel stack deliver what the architecture promises?"

**What to validate:** See detailed technical questions in `docs/10-intel-variant-technical-reference.md` (Technical Validation & Research Areas section).

---

## 🛠️ R&D Phase: Recommended 4-Step Approach

### **Step 1: Local Technology Validation (Week 1)**

**Goal:** Prove core stack works on developer workstation before OpenShift integration.

**Tasks:**
- [ ] Install MuJoCo + unitree_mujoco on local workstation
- [ ] Run MuJoCo visualizer with Unitree G1 model
- [ ] Install LeRobot framework locally
- [ ] Train simple imitation learning policy (synthetic demo data)
- [ ] Export trained PyTorch model to ONNX
- [ ] Install OpenVINO toolkit
- [ ] Convert ONNX → OpenVINO IR
- [ ] Test OpenVINO inference locally (CPU mode)
- [ ] Document setup procedures and findings

**Success Criteria:**
- MuJoCo renders Unitree G1 in interactive viewer
- LeRobot trains a policy without errors
- PyTorch → ONNX → OpenVINO conversion completes
- OpenVINO inference produces action predictions

**Deliverable:** Technical validation report (what works, what doesn't, blockers identified)

---

### **Step 2: OpenShift Integration PoC (Week 2-3)**

**Goal:** Deploy core stack to OpenShift and validate platform integration.

**Tasks:**
- [ ] Containerize MuJoCo simulation environment
- [ ] Deploy MuJoCo container to OpenShift
- [ ] Set up LeRobot on OpenShift AI Workbench (Jupyter)
- [ ] Train policy on OpenShift AI (single-GPU)
- [ ] Create Kubeflow Pipeline for PyTorch → ONNX → OpenVINO conversion
- [ ] Register OpenVINO IR model in MLflow
- [ ] Deploy OpenVINO Model Server on OpenShift
- [ ] Test inference via REST API
- [ ] Measure inference latency and throughput

**Success Criteria:**
- Complete training workflow runs on OpenShift AI
- Model artifacts stored in MLflow with lineage
- OpenVINO Model Server serves model and responds to inference requests
- Inference latency measured and documented

**Deliverable:** OpenShift deployment patterns documented, performance benchmarks

---

### **Step 3: Perception Stack Validation (Week 3-4)**

**Goal:** Validate Intel Robotics AI Suite models for Loop 1 perception tasks.

**Tasks:**
- [ ] Download Intel pre-optimized models (YOLOv8, SAM, CLIP)
- [ ] Deploy models via OpenVINO Model Server
- [ ] Build obstruction-detector test service (replaces Cosmos Reason 2-8B)
- [ ] Test perception pipeline:
  - Camera frames → YOLOv8 object detection
  - SAM segmentation for boundaries
  - CLIP zero-shot classification
  - Combine into structured alert
- [ ] Compare accuracy vs. Cosmos Reason 2-8B baseline (if baseline available)
- [ ] Measure end-to-end latency (camera → alert)
- [ ] Test on iGPU if available, otherwise CPU

**Success Criteria:**
- Perception pipeline produces structured alerts from camera input
- Accuracy is acceptable for obstruction detection use case
- Latency meets Loop 1 requirements (< 500ms end-to-end)

**Deliverable:** Perception pipeline architecture, accuracy/latency benchmarks

---

### **Step 4: Strategic Decision Checkpoint (Week 4)**

**Goal:** Assess R&D findings and make Go/No-Go decision on full implementation.

**Review Questions:**

**Technical Feasibility:**
- ✅ Does MuJoCo + LeRobot + OpenVINO work end-to-end?
- ✅ Is performance acceptable (inference latency, training time)?
- ✅ Can Intel Robotics AI Suite replace Cosmos for perception?
- ❌ What critical gaps or blockers were found?

**Strategic Fit:**
- Does Loop 3 gap (no synthetic data) disqualify Intel variant for target customers?
- Is Scenario 3 (Hybrid: NVIDIA datacenter + Intel edge) the right path?
- Is visual fidelity gap (MuJoCo vs Isaac Sim) acceptable for demo audiences?

**Resource Assessment:**
- Can team support parallel NVIDIA + Intel work?
- Does NVIDIA variant maturity allow Intel work to proceed?

**Decision Options:**
1. ✅ **GO: Proceed to full implementation** (Scenario 1 or 3)
2. ⏸️ **DEFER: Wait for Panther Lake GA / Loop 3 alternative / NVIDIA maturity**
3. ❌ **NO-GO: Technical gaps too large or strategic fit unclear**

**Deliverable:** Go/No-Go decision with rationale, next phase scoped (if GO)

---

## 📚 Technologies to Learn (R&D Phase)

### **Critical Path (Must Learn)**

#### 1. MuJoCo (DeepMind/Google)
**What:** Physics simulation engine for robot training  
**Why:** Replaces Isaac Sim in Intel variant  
**Learn:**
- MJCF model format
- Simulation setup and rendering
- unitree_mujoco integration for Unitree G1
- Sensor and actuator simulation

**Resources:**
- MuJoCo docs: https://mujoco.readthedocs.io/
- unitree_mujoco: https://github.com/unitreerobotics/unitree_mujoco
- Example scenes and tutorials

**Time Estimate:** 1 week for basics, 2-3 weeks for proficiency

---

#### 2. LeRobot (Hugging Face)
**What:** Open-source imitation learning framework  
**Why:** Replaces Isaac Lab for policy training  
**Learn:**
- Dataset format (HDF5-based demonstrations)
- Supported policies (ACT, Diffusion Policy, BC)
- Training configuration and hyperparameters
- PyTorch integration

**Resources:**
- GitHub: https://github.com/huggingface/lerobot
- Hugging Face docs
- Example datasets

**Time Estimate:** 1-2 weeks for training workflows

---

#### 3. OpenVINO (Intel)
**What:** Inference optimization toolkit for Intel hardware  
**Why:** Core model optimization and serving layer  
**Learn:**
- Model conversion: PyTorch/ONNX → OpenVINO IR
- Optimization techniques (quantization INT8/FP16, pruning)
- Runtime API for inference
- Device targeting (NPU, iGPU, CPU)
- OpenVINO Model Server deployment

**Resources:**
- Docs: https://docs.openvino.ai/
- Intel DevCloud (for hardware testing)
- OpenVINO Model Server: https://docs.openvino.ai/latest/ovms_what_is_openvino_model_server.html

**Time Estimate:** 2 weeks for conversion pipeline + serving

---

#### 4. ROS 2 Lyrical (Robot Operating System 2)
**What:** Robotics middleware for robot control  
**Why:** Bridge between sim/inference and robot execution  
**Learn:**
- ROS 2 fundamentals (nodes, topics, services, actions)
- Cyclone DDS configuration
- ros2_control for actuation
- ROS 2 + MuJoCo bridge integration

**Resources:**
- Docs: https://docs.ros.org/
- ROS 2 on OpenShift patterns
- Cyclone DDS networking guide

**Time Estimate:** 2-3 weeks for robotics integration

---

### **Secondary Priority (For Step 3)**

#### 5. Intel Robotics AI Suite
**What:** Pre-optimized models and AMR components  
**Explore:**
- Pre-trained models: YOLOv8, SAM, CLIP, Qwen2.5VL
- AMR components: ITS-Planner, ADBScan, Collaborative-SLAM
- Model deployment patterns

**Resources:**
- Intel documentation (request access if needed)
- Pre-trained model zoo

**Time Estimate:** 1 week for evaluation

---

## 🚧 Known Blockers & Mitigations

### **Blocker 1: Panther Lake Hardware Unavailable**

**Impact:** Cannot test NPU inference; iGPU testing limited  
**Likelihood:** High (Q4 2026 availability uncertain)

**Mitigation:**
- Fallback to Meteor Lake (iGPU only, no NPU)
- CPU-only OpenVINO inference for initial validation
- Design abstraction so NPU vs CPU is config toggle
- Request Intel DevCloud access for remote testing

---

### **Blocker 2: LeRobot Maturity Gaps**

**Impact:** Training instability, missing features vs. Isaac Lab  
**Likelihood:** Medium

**Mitigation:**
- Validate with simple tasks first (imitation learning, basic manipulation)
- Contribute upstream fixes if gaps found
- Evaluate alternatives: Stable Baselines3, RLlib, custom PyTorch loops
- Document limitations transparently

---

### **Blocker 3: MuJoCo Visual Fidelity Insufficient**

**Impact:** Demo quality unacceptable for Archetype A customers  
**Likelihood:** Medium

**Mitigation:**
- Target Archetype B/C (operational depth) with Intel variant demos
- Use pre-recorded high-quality MuJoCo renders for slides
- Consider NVIDIA Isaac Sim for visualization only (hybrid approach)
- Lead with NVIDIA variant for visual-first demos

---

### **Blocker 4: No World Model Alternative (Loop 3)**

**Impact:** Synthetic data generation loop not implementable  
**Likelihood:** High (confirmed gap)

**Mitigation:**
- Accept Loop 3 omission for Intel-only variant (Scenario 1)
- Pursue Scenario 3 (Hybrid) to preserve Cosmos on NVIDIA datacenter
- Track open-source world model developments (Genie, etc.)
- Document this as known limitation

---

## 🎯 Success Metrics (R&D Phase)

### **Technical Validation Success:**
- [ ] MuJoCo simulates Unitree G1 with acceptable fidelity
- [ ] LeRobot trains a policy on OpenShift AI without errors
- [ ] PyTorch → ONNX → OpenVINO conversion works end-to-end
- [ ] OpenVINO inference latency < 100ms for perception models
- [ ] Intel Robotics AI Suite models achieve >80% accuracy vs. baseline
- [ ] Complete workflow demonstrated: train (LeRobot) → optimize (OpenVINO) → serve (OVMS) → execute (ROS 2 + MuJoCo)

### **Strategic Clarity Success:**
- [ ] Strategic intent confirmed (Intel partnership, customer requirement, or exploratory)
- [ ] Panther Lake availability timeline clarified
- [ ] Loop 3 gap assessed (acceptable limitation or requires Hybrid scenario)
- [ ] Resource allocation decided (parallel work or sequential)
- [ ] Go/No-Go decision made with stakeholder alignment

---

## 💼 Roles & Responsibilities

### **R&D Phase Team Structure**

**Tech Lead (1 person)**
- Overall R&D phase coordination
- Decision checkpoint facilitation
- Stakeholder communication

**Platform Engineer (1-2 people)**
- OpenShift AI setup and configuration
- Kubeflow Pipelines creation
- MLflow integration
- Container builds and deployment

**Robotics/AI Engineer (1-2 people)**
- MuJoCo + LeRobot local validation
- Policy training experiments
- OpenVINO model conversion and optimization
- ROS 2 integration

**Optional: Intel Liaison**
- Intel Robotics AI Suite guidance
- OpenVINO optimization support
- Hardware access coordination

---

## 🤝 External Dependencies & Collaboration

### **Intel (Critical)**

**Needed From Intel:**
- Access to Intel Robotics AI Suite (if repositories are private)
- OpenVINO optimization best practices for robotics models
- Panther Lake hardware access timeline
- Pre-optimized model catalog and documentation
- Technical support contact for blockers

**Action:** Schedule kickoff meeting with Intel Physical AI team

---

### **Hugging Face (Optional)**

**Needed From Hugging Face:**
- LeRobot technical support (if gaps found)
- Contribution guidelines (if upstream fixes needed)

**Action:** Join LeRobot Discord/community channels

---

### **Red Hat Internal**

**OpenShift AI Team:**
- Kubeflow Pipelines best practices
- MLflow integration patterns
- GPU scheduling on OpenShift

**Edge Team (If pursuing Scenario 3):**
- RHEL Edge image building
- MicroShift deployment patterns
- FlightCtl integration (if applicable)

---

## 🚀 Immediate Action Items (This Week)

### **Priority 1: Hardware & Access**
- [ ] Request Panther Lake availability timeline from Intel
- [ ] Identify fallback hardware options (Meteor Lake, Raptor Lake)
- [ ] Request access to Intel Robotics AI Suite repositories
- [ ] Set up Intel DevCloud account (if available)

### **Priority 2: Development Environment**
- [ ] Provision RHEL 9 workstation for R&D validation
- [ ] Install Python 3.11, Docker/Podman
- [ ] Clone LeRobot, MuJoCo, unitree_mujoco repos
- [ ] Verify OpenShift AI cluster access

### **Priority 3: Team Readiness**
- [ ] Identify 2-3 engineers for R&D phase
- [ ] Share architecture document for team review
- [ ] Schedule R&D phase kickoff meeting
- [ ] Set up communication channels (Slack, GitHub project board)

---

## 📊 Risk Assessment Summary

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **Panther Lake unavailable** | High | Medium | CPU/iGPU fallback, Intel DevCloud |
| **LeRobot maturity gaps** | Medium | Medium | Alternatives: SB3, RLlib, custom |
| **MuJoCo visual fidelity** | Medium | Medium | Target Archetype B/C, NVIDIA for visuals |
| **Loop 3 gap** | High | High | Scenario 3 (Hybrid) or accept omission |
| **Resource constraints** | Medium | High | Defer until NVIDIA variant matures |

---

## 💡 Key Principles for R&D Phase

1. **Fail Fast:** Validate critical unknowns first (MuJoCo fidelity, LeRobot stability, OpenVINO performance)
2. **Document Everything:** Findings, blockers, workarounds — valuable for decision checkpoint
3. **Stay Pragmatic:** Use CPU inference if NPU/iGPU unavailable; don't block on ideal hardware
4. **Communicate Openly:** Weekly updates to stakeholders on progress and blockers
5. **Make Data-Driven Decisions:** Performance benchmarks inform Go/No-Go, not assumptions

---

## 📝 Open Questions Log

Track questions as they arise during R&D phase:

1. **MuJoCo + Unitree G1:** Is simulation fidelity sufficient for training manipulation policies?
2. **LeRobot scaling:** Can it handle multi-hour training runs on OpenShift AI without instability?
3. **OpenVINO quantization:** What's the accuracy drop for INT8 quantization on robotics models?
4. **ROS 2 + MuJoCo:** Does the bridge work seamlessly or require custom integration?
5. **Intel models catalog:** Are all 25+ models publicly available, or only subset?
6. **NPU device plugin:** Does one exist for Kubernetes, or must we build it?

---

## 🎓 Recommended Learning Path

**Week 1 (Before R&D Starts):**
- Read architecture document (`10-intel-variant-technical-reference.md`)
- Set up local dev environment (Python, MuJoCo, LeRobot)
- Run MuJoCo "hello world" simulation
- Complete LeRobot quickstart tutorial

**Week 1 (R&D Phase):**
- MuJoCo + unitree_mujoco deep dive
- LeRobot training experiments
- OpenVINO conversion pipeline basics

**Week 2:**
- OpenShift AI Workbench setup
- Kubeflow Pipelines fundamentals
- MLflow model registry patterns

**Week 3:**
- ROS 2 fundamentals (if not already familiar)
- Intel Robotics AI Suite exploration
- OpenVINO Model Server deployment

**Week 4:**
- Findings synthesis and documentation
- Decision checkpoint preparation

---

## 📞 Questions & Escalation Path

**Technical Questions:**
- Platform/OpenShift: Contact OpenShift AI team
- Intel stack: Contact Intel liaison (once identified)
- Robotics/ROS 2: Consult internal robotics experts or external community

**Strategic Questions:**
- Resource allocation: Escalate to project lead
- Partnership coordination: Escalate to Intel partnership manager
- Go/No-Go decision: Full stakeholder review required

**Blockers:**
- Hardware access: Escalate to Intel immediately
- Critical technical gap: Evaluate alternatives, escalate to tech lead for pivot decision

---

**Document Owner:** Red Hat Physical AI Showcase Team  
**Next Review:** After Step 4 R&D validation decision checkpoint  
**Status:** Ready for R&D validation phase  
**Related Documents:** 
- Architecture: `docs/10-intel-variant-technical-reference.md`
- Original Intel spec: https://gist.github.com/redhatHameed/441dc8ca5614fa50d9f7977f49424cdd