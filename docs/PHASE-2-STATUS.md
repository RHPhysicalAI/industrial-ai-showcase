# Phase 2 - Complete Status Report

**Last Updated:** 2026-06-25  
**Phase 1 Status:** ✅ Complete (95% - hub-only working demo)  
**Phase 2 Status:** 🟡 50% code ready, 0% infrastructure

---

## Quick Summary

**Goal:** Multi-site fleet operations with policy training, promotion, and auto-rollback

**Current State:**
- ✅ **Good news:** ~50% of application code already exists
- ✅ **Better news:** Some Phase 2 features already deployed in Phase 1!
- ⚠️ **Blocker:** Multi-cluster infrastructure (companion + Factory B)
- ⏱️ **Timeline:** 6-9 weeks from infrastructure availability

**Key Finding:** Much more Phase 2 code exists than expected. Several components are deployment-ready TODAY.

---

## What Phase 2 Delivers

### Demo Story: 20-Minute Architecture Walkthrough

**Segment 1: Multi-Site Fleet** (5 min)
- Hub coordinates multiple factory sites
- Real-time fleet status across Factory A + Factory B
- Unified mission orchestration

**Segment 2: MLOps Pipeline** (5 min)
- Train new policy in Isaac Lab
- Full lineage: training data → model → metrics
- Register in MLflow with approver

**Segment 3: Policy Rollout + Auto-Rollback** (5 min)
- Promote policy: hub → spoke-a → spoke-b
- Anomaly detected on telemetry
- Automatic rollback in <30 seconds
- Git-based rollout (Argo CD syncs)

**Segment 4: Brownfield Integration** (5 min)
- MES orders drive robot missions
- Legacy PLC/HMI VM coexists with containers
- Purdue model overlay shows factory architecture

---

## Component Status Matrix

| Component | Code | Manifests | Deployed | Status | Can Deploy Now? |
|-----------|------|-----------|----------|--------|-----------------|
| **MES Stub** | 100% ✅ | 100% ✅ | ❌ | Ready | ✅ YES |
| **Auto-Rollback** | 100% ✅ | N/A | ✅ | **Running!** | Already deployed |
| **Fleet Mgr MES Integration** | 100% ✅ | N/A | ✅ | **Running!** | Already deployed |
| **VLA Training Pipeline** | 70% 🟡 | 100% ✅ | ❌ | Needs Kubeflow YAML | 🟡 Partial |
| **Factory B Services** | 100% ✅ | 100% ✅ | ❌ | Needs cluster | ❌ No |
| **Kafka `mes.orders` Topic** | N/A | 100% ✅ | ❌ | Ready | ✅ YES |
| **Console Architecture View** | 0% ❌ | N/A | N/A | Not started | ❌ No |
| **Console Lineage View** | 0% ❌ | N/A | N/A | Not started | ❌ No |
| **Console Fleet View** | 0% ❌ | N/A | N/A | Not started | ❌ No |
| **Policy Rollout Automation** | 20% 🟡 | 0% ❌ | ❌ | Needs tooling | ❌ No |
| **PLC Gateway VM** | 0% ❌ | 30% 🟡 | ❌ | Needs OpenShift Virt | ❌ No |
| **Cosmos Transfer** | 0% ❌ | 0% ❌ | ❌ | Needs NGC access | ❌ No |
| **Isaac Lab Orchestration** | 30% 🟡 | 100% ✅ | ❌ | Needs pipeline YAML | ❌ No |
| **Enhanced Observability** | 20% 🟡 | 0% ❌ | ❌ | Needs federation | ❌ No |
| **MicroShift Edge** | 0% ❌ | 0% ❌ | ❌ | Optional Phase 2 | ❌ No |
| **Documentation** | 0% ❌ | N/A | N/A | Not written | ✅ Can start |

**Overall:** 50% application code, 80% manifests, 0% infrastructure

---

## What Code Exists (Surprises!)

### 1. ✅ MES Stub - COMPLETE & READY

**Location:** `workloads/mes-stub/src/mes_stub/`

**What it does:**
- Simulates Manufacturing Execution System (SAP PP/DS style)
- Publishes production orders to Kafka `mes.orders` topic
- Two modes: on-demand or streaming

**Code highlights:**
```python
# main.py - 180 lines, fully implemented
@app.post("/emit")
async def emit_order(req: EmitRequest | None = None):
    """Emit a single MES order. Uses template defaults if fields are empty."""
    order = MesOrder(
        trace_id=uuid4().hex,
        material=req.material,
        quantity=req.quantity or 1,
        source_location=req.source_location,
        destination_location=req.destination_location,
        priority=req.priority,
        factory=req.factory or settings.default_factory,
    )
    producer.send(settings.orders_topic, key=order.factory, value=order)
    # ...
```

**Deployment manifests:**
- `infrastructure/gitops/apps/workloads/mes-stub/deployment.yaml` ✅
- `infrastructure/gitops/apps/workloads/mes-stub/buildconfig.yaml` ✅
- `infrastructure/gitops/apps/workloads/mes-stub/imagestream.yaml` ✅

**Deploy today:**
```bash
oc apply -k infrastructure/gitops/apps/workloads/mes-stub/
```

---

### 2. ✅ Auto-Rollback - ALREADY DEPLOYED!

**Location:** `workloads/fleet-manager/src/fleet_manager/rollback.py`

**What it does:**
- Monitors telemetry anomaly scores
- Triggers git revert when anomaly exceeds threshold (0.85)
- Creates revert commit via GitHub API
- Argo CD syncs rollback automatically

**Code highlights:**
```python
# rollback.py - 85 lines, fully implemented
ANOMALY_THRESHOLD = 0.85

def should_rollback(anomaly_score: float | None) -> bool:
    """Return True if anomaly score exceeds the rollback threshold."""
    if anomaly_score is None:
        return False
    return anomaly_score >= ANOMALY_THRESHOLD

async def trigger_rollback(
    factory: str, robot_id: str, anomaly_score: float, trace_id: str, log
) -> bool:
    """Create a git revert of the latest policy-version commit via GitHub API."""
    # Finds latest policy-version.yaml commit
    # Creates revert via GitHub API
    # Returns True if successful
```

**Status:** ✅ **ALREADY RUNNING** in Fleet Manager pod!

**What's missing:**
- GITHUB_TOKEN environment variable
- policy-version.yaml files per factory
- Testing on real anomaly

**Test it:**
```bash
# Set GitHub token
oc set env deployment/fleet-manager -n fleet-ops GITHUB_TOKEN=<token>

# Simulate anomaly in telemetry (would need to inject high anomaly score)
# Auto-rollback will trigger at threshold
```

---

### 3. ✅ Fleet Manager MES Integration - ALREADY DEPLOYED!

**Location:** `workloads/fleet-manager/src/fleet_manager/main.py`

**What it does:**
- Consumes `mes.orders` Kafka topic
- Translates production orders into robot missions
- Assigns missions to factory-specific robots

**Code highlights:**
```python
# main.py - already in deployed code
async def _consume_mes_orders(
    consumer: JsonConsumer[MesOrder],
    producer: JsonProducer,
    planner: MissionPlanner,
    missions_topic: str,
    policy_version: str,
    log: "BoundLogger",
) -> None:
    """Consume MES orders and translate them into DISPATCH missions."""
    while True:
        order = await loop.run_in_executor(None, consumer.poll, 1.0)
        if order is None:
            await asyncio.sleep(0)
            continue
        log.info("mes_order.received", order_id=str(order.order_id), ...)
        mission = planner.handle_mes_order(order, policy_version, log)
        if mission is not None:
            _emit(producer, missions_topic, mission, log)
        consumer.commit()
```

**Status:** ✅ **ALREADY RUNNING** in Fleet Manager pod!

**What's missing:**
- MES Stub deployment (to send orders)
- `mes.orders` Kafka topic creation

**Activate it:**
```bash
# 1. Create topic
oc apply -f - <<EOF
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: mes-orders
  namespace: fleet-ops
  labels:
    strimzi.io/cluster: fleet-kafka
spec:
  partitions: 3
  replicas: 3
EOF

# 2. Deploy MES Stub (see above)

# 3. Send test order
curl -X POST http://mes-stub-route/emit

# 4. Watch Fleet Manager logs
oc logs -n fleet-ops -l app=fleet-manager --tail=20 | grep mes_order
```

---

### 4. 🟡 VLA Training Pipeline - 70% COMPLETE

**Location:** `workloads/vla-training/src/vla_training/`

**What exists:**
- `fine_tune.py` - Training logic ✅
- `data_prep.py` - Dataset preparation ✅
- `register_model.py` - MLflow registration ✅
- `promote.py` - Model promotion logic ✅
- `pipeline.py` - Orchestration skeleton 🟡
- `validate_onnx.py` - Model validation ✅
- `g1_teleop_modality.py` - Humanoid robot config ✅

**What's missing:**
- Kubeflow Pipeline YAML (to orchestrate the components)
- Isaac Lab scenario generation
- End-to-end testing

**Deployment manifests ready:**
```
infrastructure/gitops/apps/platform/dspa/
├── namespace.yaml       ✅ vla-training namespace
├── buildconfig.yaml     ✅
├── imagestream.yaml     ✅
└── serviceaccount.yaml  ✅
```

**What to do:**
1. Deploy namespace + build infrastructure
2. Write Kubeflow Pipeline YAML to orchestrate components
3. Test training run

**Effort:** 1-2 weeks to complete

---

### 5. ✅ Factory B Services - CODE READY

**Location:** Reuses `workloads/fake-camera/` and `workloads/mission-dispatcher/`

**Deployment manifests ready:**
```
infrastructure/gitops/apps/workloads/factory-b/
├── namespace.yaml                        ✅
├── fake-camera-b-deployment.yaml         ✅
├── fake-camera-b-buildconfig.yaml        ✅
├── fake-camera-b-imagestream.yaml        ✅
├── mission-dispatcher-b-deployment.yaml  ✅
├── mission-dispatcher-b-buildconfig.yaml ✅
└── mission-dispatcher-b-imagestream.yaml ✅
```

**Status:** Ready to deploy once Factory B cluster exists

**Blocker:** Factory B spoke cluster provisioning

---

## What's Missing

### Infrastructure (CRITICAL BLOCKERS)

#### 1. ❌ Companion Cluster
**What's needed:**
- Single Node OpenShift (SNO) on Fedora 43 host (10.0.0.73)
- OpenShift Virtualization (KubeVirt) for PLC VM
- GPU Operator (AMD ROCm support if available)
- ACM registration to hub

**Why it blocks:**
- Real VLA serving (OpenVLA-7B on AMD GPU)
- PLC Gateway VM (brownfield story)
- Edge pattern demonstration

**Effort:** 1-2 weeks provisioning

---

#### 2. ❌ Factory B Spoke Cluster
**What's needed:**
- Third OpenShift cluster (OCP, OSD, ARO, ROSA, or Kind)
- ACM registration
- GitOps sync from hub
- Kafka federation

**Why it blocks:**
- Multi-site demo (core Phase 2 value)
- Policy rollout across sites
- Fleet-scale demonstration

**Effort:** 3-5 days provisioning

**Alternative:** Use Kind cluster for development/testing

---

#### 3. ❌ Multi-Cluster Networking
**What's needed:**
- MirrorMaker2 for Kafka federation
- Thanos for cross-cluster metrics
- OpenTelemetry distributed tracing
- Service mesh federation (optional)

**Why it blocks:**
- Event flow between sites
- Unified observability
- Cross-cluster mission coordination

**Effort:** 1 week setup

---

#### 4. ❌ ACM (Advanced Cluster Management)
**What's needed:**
- ACM operator on hub
- Hub registered as ACM hub
- Companion + Factory B registered as managed clusters
- Policy distribution configured

**Why it blocks:**
- Centralized cluster management
- Policy rollout automation
- Multi-site monitoring

**Effort:** 3-5 days setup

---

### Application Gaps

#### 5. ❌ Console UI Enhancements
**Missing views:**
- **Architecture View** - Purdue model overlay, cluster topology
- **Lineage View** - Training data → model → deployment chain
- **Fleet View** - Per-site version pills, anomaly sparklines

**Current state:**
- Basic console exists (Phase 1)
- Stage view, events, demo buttons working

**Effort:** 2-3 weeks React development

---

#### 6. ❌ Policy Rollout Automation
**Missing:**
- Kustomize overlay generator (MLflow URI → InferenceService)
- GitOps rollout sequencing (hub → spoke-a → spoke-b)
- Argo CD sync wave coordination

**What exists:**
- Rollback logic (trigger function)
- Policy-version concept

**Effort:** 1 week tooling development

---

#### 7. ❌ PLC Gateway VM
**Missing:**
- VM image (Windows or legacy Linux)
- VirtualMachine CR
- NetworkPolicy configuration
- Console integration

**What exists:**
- Namespace manifest

**Blocker:** OpenShift Virtualization on companion cluster

**Effort:** 3-5 days VM setup

---

#### 8. ❌ Isaac Lab Pipeline Orchestration
**Missing:**
- Kubeflow Pipeline YAML
- Scenario manifest generator
- Evaluation framework
- Full MLflow lineage wiring

**What exists:**
- Individual components (70% of code)

**Effort:** 1-2 weeks orchestration

---

#### 9. ❌ Cosmos Transfer Integration
**Missing:**
- Cosmos Transfer NIM deployment
- Synthetic data pipeline
- Scenario variations
- Nucleus upload automation

**Blocker:** NGC entitlements

**Effort:** 1-2 weeks (if NGC access available)

---

#### 10. ❌ Enhanced Observability
**Missing:**
- MLflow UI in Console
- Thanos federation
- OpenTelemetry traces
- Multi-site Grafana dashboards

**Effort:** 1-2 weeks integration

---

#### 11. ❌ Documentation
**Missing:**
- Fleet-scale operating math (10/40 sites)
- Security posture (STIG, FIPS status)
- Performance envelope (measured p50/p99)
- HIL Approval Drawer design spec

**Effort:** 2-3 weeks research + writing

---

## What You Can Do RIGHT NOW

### Hub-Only Deployments (Today)

#### 1. Deploy MES Stub
```bash
# Apply manifests
oc apply -k infrastructure/gitops/apps/workloads/mes-stub/

# Wait for build
oc get builds -n fleet-ops -l app=mes-stub -w

# Check deployment
oc get pods -n fleet-ops -l app=mes-stub

# Get route
oc get route -n fleet-ops mes-stub
```

#### 2. Create `mes.orders` Kafka Topic
```bash
oc apply -f - <<EOF
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: mes-orders
  namespace: fleet-ops
  labels:
    strimzi.io/cluster: fleet-kafka
spec:
  partitions: 3
  replicas: 3
  config:
    retention.ms: 86400000
EOF

# Verify
oc get kafkatopic -n fleet-ops mes-orders
```

#### 3. Test MES → Fleet Manager Flow
```bash
# Emit test order
MES_URL=$(oc get route -n fleet-ops mes-stub -o jsonpath='{.spec.host}')
curl -X POST http://$MES_URL/emit

# Check Fleet Manager consumed it
oc logs -n fleet-ops -l app=fleet-manager --tail=30 | grep mes_order

# Check mission dispatched
oc logs -n fleet-ops -l app=mission-dispatcher --tail=30
```

#### 4. Test Auto-Rollback (Configure First)
```bash
# Set GitHub token
oc set env deployment/fleet-manager -n fleet-ops \
  GITHUB_TOKEN=<your-github-token> \
  GITHUB_REPO=<org>/<repo> \
  GITHUB_BRANCH=main

# Rollback will auto-trigger when anomaly score ≥ 0.85
# (Would need to inject high anomaly score in telemetry to test)
```

---

### Development Work (No Cluster Needed)

#### 1. Console UI Development
- Start React components locally
- Mock API responses
- Build Architecture/Lineage/Fleet views
- Test with local data

#### 2. Documentation
- Research fleet-scale operating math
- Audit security posture (STIG baseline)
- Begin performance envelope measurements
- Write HIL design spec

#### 3. Isaac Lab Pipeline
- Design Kubeflow Pipeline YAML
- Test training components locally
- Plan MLflow integration

---

## Dependencies Graph

```
┌─────────────────────────────────────────────┐
│ FOUNDATION (MUST DEPLOY FIRST)              │
├─────────────────────────────────────────────┤
│ 1. Companion Cluster (SNO)                  │
│    ├─ OpenShift Virt                        │
│    └─ ACM registration                      │
│                                             │
│ 2. Factory B Cluster                        │
│    └─ ACM registration                      │
│                                             │
│ 3. ACM on Hub                               │
│    └─ Cluster management                    │
└─────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────┐
│ MULTI-CLUSTER NETWORKING                    │
├─────────────────────────────────────────────┤
│ 4. Kafka Federation (MirrorMaker2)          │
│ 5. Observability (Thanos)                   │
│ 6. Tracing (OpenTelemetry)                  │
└─────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────┐
│ CAN DEPLOY NOW (Hub-Only)                   │
├─────────────────────────────────────────────┤
│ ✅ MES Stub                                 │
│ ✅ mes.orders Kafka topic                   │
│ ✅ Test MES → Fleet Manager                 │
│ ✅ Test auto-rollback (with token)          │
└─────────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────┐
│ AFTER MULTI-CLUSTER READY                   │
├─────────────────────────────────────────────┤
│ 7. Factory B Services                       │
│ 8. PLC Gateway VM                           │
│ 9. VLA Training Pipeline                    │
│ 10. Policy Rollout Automation               │
│ 11. Console Enhancements                    │
│ 12. Enhanced Observability                  │
└─────────────────────────────────────────────┘
```

---

## Timeline Estimate

### Infrastructure (Critical Path): 3-4 weeks
- Companion cluster: 1-2 weeks
- Factory B cluster: 3-5 days
- ACM setup: 3-5 days
- Multi-cluster networking: 1 week

### Application Development (Parallel): 4-5 weeks
- Console UI (3 views): 2-3 weeks
- Policy rollout tooling: 1 week
- Isaac Lab orchestration: 1-2 weeks
- Observability federation: 1-2 weeks
- PLC Gateway VM: 3-5 days

### Documentation (Parallel): 2-3 weeks
- Fleet-scale math: 3-5 days
- Security posture: 3-5 days
- Performance envelope: 3-5 days
- HIL design spec: 1 week

### Integration & Testing: 2 weeks
- Multi-cluster validation
- End-to-end demo rehearsal
- Performance measurements
- Bug fixes

**Total: 6-9 weeks** (with parallelization)

---

## Revised Priorities

### Priority 1: Deploy What Exists (This Week)
1. ✅ MES Stub to hub
2. ✅ `mes.orders` Kafka topic
3. ✅ Test MES integration
4. ✅ Configure auto-rollback

### Priority 2: Infrastructure (Weeks 1-4)
1. Provision companion cluster
2. Provision Factory B cluster
3. Install ACM
4. Configure Kafka federation

### Priority 3: Application Completion (Weeks 5-7)
1. Console UI (Architecture/Lineage/Fleet views)
2. Policy rollout automation
3. Isaac Lab pipeline orchestration
4. PLC Gateway VM deployment

### Priority 4: Polish & Documentation (Weeks 8-9)
1. Enhanced observability
2. Documentation deliverables
3. Performance measurements
4. Demo rehearsal

---

## Key Questions to Answer

1. **Companion cluster timeline?**  
   When will SNO be provisioned and operational?

2. **Factory B approach?**  
   Real OCP cluster or Kind for testing?

3. **NGC access for Cosmos Transfer?**  
   Do we have entitlements? Priority?

4. **Resource allocation?**  
   Who works on infrastructure vs application vs documentation?

5. **Phase 2 deadline?**  
   What's the target completion date?

6. **GitHub token for rollback?**  
   Can we configure GITHUB_TOKEN now to test?

---

## Summary

### What We Discovered

✅ **Much more code exists than expected**  
- MES Stub: 100% complete
- Auto-rollback: 100% complete and DEPLOYED
- Fleet Manager MES: 100% complete and DEPLOYED
- VLA Training: 70% complete
- Factory B: Code ready

### Current Blockers

❌ **Multi-cluster infrastructure**
- Companion cluster (SNO)
- Factory B spoke cluster
- ACM + federation

### What You Can Do Now

✅ **Deploy 3-4 features today** (hub-only)
- MES Stub
- MES Kafka topic
- Test brownfield integration
- Test auto-rollback

### Timeline

📅 **6-9 weeks from infrastructure start** (revised from 8-12)

**Phase 2 is closer than expected!** 🎉

The hard work of coding many components is already done. Now it's primarily:
1. Infrastructure provisioning
2. Console UI development
3. Integration/wiring
4. Documentation

---

**Bottom Line:** Deploy what you can today, prepare infrastructure next week, complete Phase 2 in 6-9 weeks.