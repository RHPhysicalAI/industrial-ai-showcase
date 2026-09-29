# 03 — Data Flows

Four loops animate this system. Each is described here with component participants, event semantics, and the demo beats it supports.

## Loop 1 — Operational inference (factory runtime)

This is the "this is physical AI running right now" loop. It's what Archetype A sees in the first 30 seconds. Phase 1 wires it as a real event-driven pipeline across hub + companion per ADR-027 — every visible scene change in the demo is the effect of a real Kafka event traveling through the production topology.

### Participants

- **Companion (on-site warehouse edge)**:
  - Fake-camera service — publishes AI-generated photorealistic warehouse frames to Kafka (simulating on-site cameras; an HTTP `POST /state` endpoint switches the emitted frame)
  - Mission Dispatcher — consumes missions, drives the Waypoint Planner, calls OpenVLA on pick
  - Waypoint Planner (inside Mission Dispatcher) — 5 Hz pose emission along the current route
  - OpenVLA (host-native on Fedora / ROCm) — manipulation policy, not navigation (per ADR-026 + ADR-027)
  - Kafka (companion side of federation)
- **Hub (HQ data center)**:
  - Cosmos Reason 2-8B on L40S — VLM obstruction detection via OpenAI-compat `/v1/chat/completions` (Qwen3-VL-derivative; vLLM 0.11.0 + `--reasoning-parser qwen3`)
  - Obstruction-detector pod — consumes `warehouse.cameras.aisle3`, calls Cosmos Reason, publishes `fleet.safety.alerts`
  - Fleet Manager — consumes `fleet.missions` + `fleet.safety.alerts`, replans on alert
  - WMS-stub — presenter-driven mission trigger
  - Isaac Sim on L40S — digital twin; twin-update subscriber consumes telemetry + alerts + camera topics and reflects reality in the scene
  - Showcase Console — two demo buttons (Dispatch Mission / Drop Pallet), event stream, MJPEG viewport embed
- **Cross-cluster**:
  - MirrorMaker2 federation carries `warehouse.cameras.*` + `warehouse.telemetry.forklifts.*` edge→hub and `fleet.missions` + `fleet.safety.alerts` hub→edge
  - Kafka topics: `warehouse.cameras.aisle3`, `fleet.missions`, `fleet.safety.alerts`, `warehouse.telemetry.forklifts.fl-07`, `fleet.ops.events`
  - `warehouse-topology.yaml` is the single source of truth for aisle/dock/approach-point coordinates + forklift id

### Flow

```
FACTORY EDGE (companion)                  HQ DATA CENTER (hub)
──────────────────────────────            ──────────────────────────────
[presenter: Dispatch Mission] → WMS-stub → fleet.missions
                                                ↓ (federation)
Mission Dispatcher ←───────── fleet.missions
  ├─ Waypoint Planner (5 Hz)
  ├─ forklift drives to aisle-3 approach-point, pauses for clearance
  └─ publishes telemetry → warehouse.telemetry.forklifts.fl-07
                                                ↓ (federation)
                                          Fleet Manager consumes telemetry
                                          Isaac Sim twin-update moves forklift prim

[presenter: Drop Pallet] → POST /state → Fake-camera service
  switches published frame: aisle3_empty.jpg → aisle3_pallet.jpg
  publishes → warehouse.cameras.aisle3
                                                ↓ (federation)
                                          Obstruction-detector pod consumes frame
                                          calls Cosmos Reason 2-8B → {"obstruction": true}
                                          publishes → fleet.safety.alerts
                                                ↓
                                          Fleet Manager replans via aisle-4,
                                          issues reroute mission instead of clearance
                                                ↓ (federation back down)
Mission Dispatcher ←───────── reroute mission
  Waypoint Planner picks up new route
  OpenVLA called in the loop on pick (manipulation policy)
  telemetry continues → warehouse.telemetry.forklifts.fl-07
                                                ↓
                                          Isaac Sim twin:
                                            - places pallet prim in aisle-3
                                            - reroutes forklift prim via aisle-4
                                            - reaches Dock-B
                                          Observability (Prometheus, Tempo) +
                                          Showcase Console event stream
```

The only scripted inputs are the two presenter buttons. Everything downstream — Cosmos Reason inference, Fleet Manager replan, Waypoint Planner emission, twin update — is real Kafka events.

### Key event schemas

Defined in `workloads/fleet-manager/schemas/` as Avro. Core event types:

- `CameraFrameEvent`: the current publisher embeds JPEG bytes as base64 in `frame_b64`, with `camera_id`, `aisle_id`, `state`, and `emitted_at`; the SeaweedFS camera library is a separate S3 staging copy, not a per-frame read dependency.
- `SafetyAlert`: `{alert_id, timestamp, aisle_id, camera_id, detection_label, confidence, source_model}`
- `Mission`: `{mission_id, target_robot_id, mission_type, parameters, deadline}` — `target_robot_id` is the forklift id (`fl-07` in Phase 1)
- `TelemetryEvent`: `{robot_id, timestamp, pose, joint_state, battery, current_mission_id, status}`

### Demo beats this supports

- "What physical AI looks like running" (Archetype A)
- "Watch as the system detects a bottleneck and reroutes fleet autonomously" (Archetype A/B)
- "Observability and trace across all layers in one pane" (Archetype C — open the Tempo view, show the full trace)
- "Cross-site event correlation" in multi-site mode (Archetype C — Loop 1 happens on Spoke A while being observed from hub)

### Failure modes the demo intentionally surfaces

- **Camera-to-obstruction-detector outage**: show fake-camera or obstruction-detector going unready, fallback to historical alerts in Grafana, and the fleet-manager holding missions at approach-points until detection recovers.
- **Robot-brain unavailable**: show KServe autoscaling spinning up a replacement, and fleet manager throttling mission issuance until it's back.
- **Kafka broker lost**: show the 3-broker replication and zero-downtime continuation.

Each is scripted into the Showcase Console as a "introduce fault" button with a clear narrative.

---

## Loop 2 — Policy training and promotion

This is the MLOps backbone loop. It's what Archetype B and C recognize as the "this is actually operationalized" moment.

### Participants

- Kubeflow Pipelines (orchestration)
- Isaac Lab (training)
- Isaac Sim (as training env)
- MLflow (tracking + registry)
- ODF S3 bucket (artifact store, checkpoints)
- KServe + vLLM (serving)
- Argo CD (promotion via GitOps)
- ACM (multi-site rollout)

### Flow

```
Data scientist launches Kubeflow Pipeline
(or: agent-triggered pipeline — Loop 4 integrates here)
  ↓
Pipeline step 1: Launch Isaac Lab training job
  ↓ parallel envs (N * Isaac Sim headless workers)
Isaac Lab: checkpoint every K steps → S3 bucket
  ↓ metrics stream to MLflow Tracking
Pipeline step 2: Evaluation run
  ↓ curated evaluation scenarios (a subset of Mega's Isaac Lab-Arena equivalent)
Pipeline step 3: Register candidate in MLflow Model Registry
  ↓ lineage: scenario manifest versions, sim-sha, parent-model-sha
Pipeline step 4: Validation gate
  ↓ automated (metric thresholds) or human-approval
Pipeline step 5: Produce serving manifest (Kustomize overlay)
  ↓ commit to infrastructure/gitops/apps/robot-brain/ (PR)
Merge → Argo CD syncs to hub serving
  ↓ ACM PolicyGenerator propagates serving manifest to spokes
Edge rollout via ACM ManifestWork to MicroShift targets
```

### Governance embedded

- Every promotion produces an MLflow-recorded artifact pinned to a Git SHA.
- Every edge deployment is traceable to an MLflow model version and the sim episodes that validated it.
- Rollback is a `git revert` — Argo CD reconciles the previous version back.

### Demo beats this supports

- "Here's how we train a robot policy" (Archetype B)
- "Every deployment is traceable to the simulated scenarios that validated it" (Archetype C)
- "Safe rollout across factories: canary to Spoke A, observe, promote to Spoke B" (Archetype C)
- "Rollback: this model started performing worse in production — watch the rollback propagate in under 2 minutes" (Archetype C)

---

## Loop 3 — Synthetic data generation and distribution expansion

This is the "the stack teaches itself" loop. It's the GTC 2026 story made tangible for customers.

### Participants

- Cosmos Predict 2.5 NIM (world model for video generation)
- Cosmos Transfer NIM (domain adaptation)
- Isaac Sim (as scenario runner for Cosmos-seeded worlds)
- MLflow (tracking the dataset lineage)
- S3 buckets (staged scenarios, generated videos, curated datasets)
- LangGraph agent (the coordinator — this loop is usually agent-driven)

### Flow

```
Trigger: scheduled, manual, or agent decision (Loop 4)
  ↓
Agent asks Cosmos Predict to generate N scenarios with prompt seeds
  ↓ generated action-conditioned videos → S3
Agent asks Cosmos Transfer to domain-adapt against real images
  ↓ adapted video/image frames → S3
Agent composes Isaac Sim scenario manifests referencing the adapted content
  ↓ scenario manifests → Nucleus
Agent launches Isaac Lab training runs on the expanded scenario set
  ↓ joins Loop 2 for the remainder
```

### Demo beats this supports

- "The training distribution isn't limited by what we've physically recorded" (Archetype B/C)
- "The agent can explore the edge of the operational envelope autonomously" (Archetype C)
- "Synthetic data is traced to real-world anchors — no ungrounded hallucination" (Archetype C)

### Important boundaries

- Cosmos NIMs are GPU-heavy. In reference footprint, they share GPU with Isaac Sim via scheduling queues — they don't run concurrently with live demo sims. See `docs/08-gpu-resource-planning.md`.
- Generated datasets are explicitly marked as synthetic in MLflow metadata so customers can filter by provenance.

---

## Loop 4 — Agentic orchestration

This is the most contemporary / Red Hat-distinctive loop. It's where LangGraph agents become operators of the physical-AI stack through MCP.

### Participants

- LangGraph agent runtime (on OpenShift AI)
- Agent brain (vLLM-served Nemotron or equivalent)
- MCP servers:
  - `mcp-isaac-sim` (scenario control)
  - `mcp-fleet` (fleet state, overrides)
  - `mcp-mlflow` (experiments, models)
  - `mcp-nucleus` (assets)
- The Showcase Console (issues commands, observes)

### Flow

```
Trigger: user command in Showcase Console or scheduled run
  ↓
LangGraph agent receives high-level goal
  e.g., "Evaluate whether adding 2 more humanoids changes throughput"
  ↓
Agent plans — breaks down into concrete MCP calls
  ↓
mcp-nucleus: stage a scene variant with 2 extra G1s
mcp-isaac-sim: launch N parallel simulation runs
mcp-fleet: observe resulting throughput over the runs
mcp-mlflow: log results
  ↓
Agent summarizes outcome
  ↓
Showcase Console displays — with citations to scenarios, MLflow run IDs, telemetry excerpts
```

### Why this loop matters

Two reasons. First, it's a walkable answer to "what's the agentic AI story for physical operations?" — a question every customer asks in 2026, and one where NVIDIA's answer is mostly aspirational. Second, it closes the storytelling loop for Red Hat: it uses LangGraph (the team's standard), MCP (the emerging tool-access standard), OpenShift AI (the MLOps substrate), and the entire Mega implementation underneath — one coherent narrative.

### Demo beats this supports

- "Ask the system a what-if question and watch it answer" (every archetype, but especially Archetype C)
- "The agent isn't a chatbot — it's running experiments in a real physics sim and summarizing results" (Archetype C)
- "This is what agentic AI looks like when it's grounded in the physical world" (Archetype B)

---

## Cross-loop interactions

Loops are not isolated. The interesting stories happen at the seams:

- **Loop 1 anomaly → Loop 4 investigation**: Fleet Manager detects an anomalous pattern; agent is invoked to investigate by running sim experiments; produces a hypothesis.
- **Loop 3 scenario → Loop 2 training → Loop 1 deployment**: Agent generates edge-case scenarios; they feed into a training run; resulting policy deploys to edge; Loop 1 behavior visibly improves.
- **Loop 2 promotion → Loop 1 observation**: A new policy promoted through Loop 2 is observed in action through Loop 1; metrics visibly change.

These cross-seams are the scripted demo climaxes.

---

## Timing expectations (for scripting)

Each loop has a characteristic time budget. The Showcase Console uses these to avoid over-promising in demo timing:

- **Loop 1 event-to-action**: seconds. Can be shown live in any demo.
- **Loop 2 training → promotion → edge deployment**: minutes for the deploy portion (shown live), hours-to-days for real training (pre-computed for demos; the live demo uses a precomputed training run that "just finished"). Script accordingly.
- **Loop 3 synthetic-data generation**: minutes per small batch, hours for a meaningful dataset expansion. Demo uses pre-staged outputs; the process itself is illustrated in recorded clips.
- **Loop 4 agentic investigation**: variable — a simple query is a minute or two; a serious what-if is 10–30 minutes. Script a "short agent run" for live demos; keep the longer-running investigations as case studies.

Honesty about these time budgets in sales conversations is a feature, not a bug. Customers can smell a faked demo immediately.
