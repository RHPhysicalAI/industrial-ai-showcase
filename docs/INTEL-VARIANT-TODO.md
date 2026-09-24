# Intel Variant - Next Steps TODO

**Status:** Ready to Start  
**Updated:** September 24, 2026  
**Team:** R&D Validation Team

---

## 🎯 This Week: Get Started

### Hardware & Intel Coordination
- [ ] Contact Intel to request Panther Lake availability timeline
- [ ] Ask Intel for access to Intel Robotics AI Suite repositories (if private)
- [ ] Identify fallback hardware options (Meteor Lake, Raptor Lake with iGPU)
- [ ] Set up Intel DevCloud account (if available for testing)

### Development Environment Setup
- [ ] Provision RHEL 9 workstation for R&D validation
- [ ] Install Python 3.11, Docker/Podman, Git
- [ ] Clone repositories:
  - `git clone https://github.com/huggingface/lerobot.git`
  - `git clone https://github.com/unitreerobotics/unitree_mujoco.git`
- [ ] Verify OpenShift AI cluster access

### Team Readiness
- [ ] Identify 2-3 engineers for R&D phase (names: ____________)
- [ ] Share technical reference document with team for review
  - `docs/10-intel-variant-technical-reference.md`
- [ ] Schedule R&D phase kickoff meeting (date: ____________)
- [ ] Set up communication channels:
  - [ ] Slack channel or MS Teams channel
  - [ ] GitHub project board for tracking

---

## 🔬 Week 1: Local Technology Validation

### MuJoCo Setup
- [ ] Install MuJoCo: `pip install mujoco`
- [ ] Test MuJoCo installation:
  ```bash
  python3 -c "import mujoco; import mujoco.viewer; print('MuJoCo OK')"
  ```
- [ ] Install unitree_mujoco dependencies
- [ ] Run MuJoCo visualizer with Unitree G1 model
- [ ] Verify interactive viewer works (rotate, zoom, pause)

### LeRobot Setup
- [ ] Create Python virtual environment:
  ```bash
  python3.11 -m venv ~/venv-intel-poc
  source ~/venv-intel-poc/bin/activate
  ```
- [ ] Install LeRobot: `cd lerobot && pip install -e .`
- [ ] Run LeRobot quickstart tutorial
- [ ] Train simple imitation learning policy with synthetic data
- [ ] Verify training completes without errors

### OpenVINO Setup
- [ ] Install OpenVINO toolkit: `pip install openvino openvino-dev`
- [ ] Test OpenVINO installation:
  ```bash
  python3 -c "import openvino; print('OpenVINO OK')"
  ```
- [ ] Export a sample PyTorch model to ONNX
- [ ] Convert ONNX → OpenVINO IR format
- [ ] Test OpenVINO inference locally (CPU mode)
- [ ] Verify inference produces output

### Documentation
- [ ] Document setup procedures (what worked, what didn't)
- [ ] Note any installation issues or blockers
- [ ] Record MuJoCo visual quality assessment
- [ ] Record LeRobot training time and stability

**Week 1 Checkpoint:**
- [ ] All three tools installed and working locally
- [ ] End-to-end flow validated: LeRobot → ONNX → OpenVINO → inference
- [ ] Technical validation report written (1-2 pages)

---

## 📦 Week 2-3: OpenShift Integration

### Containerization
- [ ] Create Dockerfile for MuJoCo simulation environment
- [ ] Build and test MuJoCo container locally
- [ ] Push container to Quay.io or internal registry
- [ ] Deploy MuJoCo container to OpenShift (test deployment)

### OpenShift AI Setup
- [ ] Access OpenShift AI Workbench
- [ ] Create Jupyter notebook with LeRobot installed
- [ ] Test LeRobot training on OpenShift AI (single-GPU)
- [ ] Verify GPU scheduling works

### Kubeflow Pipeline
- [ ] Create Kubeflow Pipeline for model conversion
  - Step 1: Train with LeRobot
  - Step 2: Export to ONNX
  - Step 3: Convert to OpenVINO IR
- [ ] Test pipeline runs end-to-end
- [ ] Register output model in MLflow

### OpenVINO Model Server
- [ ] Deploy OpenVINO Model Server on OpenShift
- [ ] Load converted model into OVMS
- [ ] Test inference via REST API:
  ```bash
  curl http://ovms-service:8001/v1/models/model-name
  ```
- [ ] Measure inference latency and throughput

**Week 2-3 Checkpoint:**
- [ ] Complete training workflow runs on OpenShift AI
- [ ] Models stored in MLflow with lineage
- [ ] OVMS serving models and responding to requests
- [ ] Performance benchmarks documented

---

## 🔍 Week 3-4: Perception Stack Validation

### Intel Robotics AI Suite
- [ ] Download Intel pre-optimized models:
  - [ ] YOLOv8 (object detection)
  - [ ] SAM (segmentation)
  - [ ] CLIP (zero-shot classification)
- [ ] Deploy models via OpenVINO Model Server
- [ ] Test each model individually

### Obstruction Detector Pipeline
- [ ] Build multi-model pipeline service:
  - Camera frames → YOLOv8 detection
  - YOLOv8 output → SAM segmentation
  - Combined → CLIP classification
  - Final → Structured alert
- [ ] Test with sample images/video
- [ ] Measure end-to-end latency (camera → alert)
- [ ] Test on iGPU if available, otherwise CPU

### Performance Validation
- [ ] Compare accuracy vs Cosmos Reason 2-8B baseline (if available)
- [ ] Verify latency meets Loop 1 requirements (< 500ms)
- [ ] Document perception pipeline architecture
- [ ] Record accuracy/latency benchmarks

**Week 3-4 Checkpoint:**
- [ ] Perception pipeline produces structured alerts
- [ ] Accuracy acceptable for obstruction detection
- [ ] Latency meets requirements
- [ ] Pipeline architecture documented

---

## 🎬 Week 4: Decision Checkpoint

### Findings Report
- [ ] Compile technical validation results:
  - [ ] What worked end-to-end?
  - [ ] What performance metrics achieved?
  - [ ] What blockers or gaps found?
- [ ] Assess Loop 3 gap impact (synthetic data generation)
- [ ] Evaluate visual fidelity gap (MuJoCo vs Isaac Sim)

### Go/No-Go Decision
- [ ] Schedule decision checkpoint meeting
- [ ] Present findings to stakeholders
- [ ] Answer decision questions:
  - [ ] Technical feasibility confirmed?
  - [ ] Performance acceptable?
  - [ ] Loop 3 gap acceptable or requires Hybrid scenario?
  - [ ] Resource allocation feasible?
- [ ] Document decision and rationale

### Next Steps (If GO)
- [ ] Scope full implementation phase
- [ ] Define timeline and milestones
- [ ] Assign team roles
- [ ] Update project plan

---

## 📝 Notes & Blockers

**Blockers:**
- (Add blockers here as they arise)

**Key Contacts:**
- Intel liaison: ___________________
- OpenShift AI team: ___________________
- Project lead: ___________________

**Meeting Schedule:**
- Weekly standup: ___________________
- Checkpoint meetings: ___________________

---

## 📚 Quick Reference

**Documents:**
- Technical Reference: `docs/10-intel-variant-technical-reference.md`
- Team Action Plan: `docs/11-intel-variant-team-action-plan.md`

**Key Tools:**
- MuJoCo: https://mujoco.readthedocs.io/
- LeRobot: https://github.com/huggingface/lerobot
- OpenVINO: https://docs.openvino.ai/

**Slack/Teams Channel:** ___________________  
**GitHub Project Board:** ___________________

---

**Last Updated:** September 24, 2026  
**Next Review:** End of Week 1 (Step 1 checkpoint)
