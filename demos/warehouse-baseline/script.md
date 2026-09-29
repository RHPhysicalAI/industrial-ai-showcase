# 5-min Warehouse Baseline demo script

> Storage terminology updated 2026-09-29: SeaweedFS names the migration target in ADR-021, not a backend verified by the historical demo sessions. CPU-only S3 validation in `showcase-storage-canary` passed; live data/consumer cutover remains pending; see the [storage guide](../../tools/object-storage/README.md).

**Audience**: Archetype A — "What is industrial physical AI?"
**Length**: 5 minutes. Hard cap — this is the session that has to fit in a hallway conversation or the first 5 minutes of a longer meeting.
**Venue**: the Showcase Console, novice mode. Single demo path, scripted, no improvised navigation.

## What this demo substantiates

A lean subset of the charter differentiators, hit contextually rather than announced:

- **#3 Hybrid cloud → factory edge → robot, one operational model** — core visual: hub and companion cluster running together, a mission crossing between them.
- **#1 On-prem and air-gapped first-class** — mentioned once, early, as a positioning line.
- **#8 Day-2 lifecycle done right** — mentioned once as closing line.

Everything else is off-surface for this demo. No security, no MLOps, no agentic. Those are 20-min and 60-min territory.

## The customer concern we lead with

**Not**: "look at this Red Hat stack."
**Yes**: "this is a warehouse with physical AI running. Let me show you what that means, and where Red Hat fits."

## Scene + robots + components

Per `assets/README.md` and ADR-027:
- Scene: NVIDIA Digital Twin Warehouse (`Isaac/Environments/Digital_Twin_Warehouse/small_warehouse_digital_twin.usd`), composed with a scene-pack overlay that places forklift, approach-point markers, aisle signage, cameras, and docks per `warehouse-topology.yaml`.
- Primary robot: Forklift_A01 (scenario id `fl-07`) — retrieves pallets from docks via aisles.
- Secondary robot: Unitree G1 humanoid (visible in scene but not active in the 5-min script).
- Cameras: fake-camera service on the companion publishes AI-generated photorealistic warehouse frames to Kafka at ~1 Hz; the twin shows clean USD. That twin-vs-reality separation is intentional — real cameras show grime, twins don't.

Components exercised (and only these):
- **Hub**: Nucleus (scene assets), Isaac Sim on L40S (digital twin + MJPEG viewport), Cosmos Reason 2-8B on L40S (Qwen3-VL-derivative; 2B trial on L4 failed the quality bar, see ADR-027), obstruction-detector pod (Kafka camera consumer → Cosmos Reason → safety-alert publisher), Fleet Manager (replan-on-alert), WMS-stub (mission trigger), SeaweedFS (camera-image library), Showcase Console.
- **Companion**: fake-camera service (Kafka publisher + HTTP state endpoint), Mission Dispatcher with Waypoint Planner (5 Hz pose emission), OpenVLA host-native (manipulation policy, called on pick — not for navigation).
- **Cross-cluster**: MirrorMaker2 federation on `warehouse.cameras.*`, `warehouse.telemetry.forklifts.*`, `fleet.missions`, `fleet.safety.alerts`.

The only scripted inputs during the demo are two presenter buttons. Everything downstream is real Kafka events and real inference.

## Minute-by-minute script

### Minute 0:00 – 0:45 — Opening line and scene establishment

**Narration** (seller speaks; the exact words are a template, not a teleprompter):

> "What you're looking at is a warehouse. A forklift is picking pallets, a humanoid is standing by for tasks that need dexterity, and ceiling cameras are watching the aisles. Every piece you see — the simulation, the AI that interprets the cameras, the decisioning, the commands going back to the robot — is running on Red Hat OpenShift. Not on cloud services somewhere. On this cluster, which could be sitting in that customer's facility." *[differentiator #1 surfaces here, one sentence, no dwelling]*

**Note (post-review)**: the prior version of this narration generalized to "logistics, automotive parts, manufacturing line." Archetype-A persona review (automotive OEM) flagged this as a tell — the visual is warehouse, not an assembly line, and hedging loses credibility. Commit to warehouse here; cross-vertical credibility comes from the Phase-2 scene-pack decision (second scene) and the 20-min brownfield beat, not from overgeneralized narration on a warehouse visual.

**Console view**: Stage view. The Isaac Sim viewport (MJPEG from the hub-side digital twin) dominates the screen, showing the warehouse interior from an overhead camera angle. Forklift `fl-07` visible at its home position. Unitree G1 visible at a workstation. Lower bar shows two cluster-health dots labeled "Hub — factory operations" and "Companion — robot edge." Two demo buttons visible: **Dispatch Mission** and **Drop Pallet**.

### Minute 0:45 – 1:45 — Dispatch, then narrate the detection infrastructure

**Narration** (presenter clicks **Dispatch Mission**):

> "I'm dispatching a mission — retrieve pallet A47 from Dock-B. The forklift is picking up the mission, routing via aisle-3." *[forklift drives partway down aisle-3 and stops]* "It's paused at the aisle-3 approach-point. This is standard practice in real AMR fleets — robots wait at approach-points for clearance from the fleet coordinator before entering shared corridors. While it's waiting, let me show you what's actually happening behind the camera feed: every frame from these ceiling cameras is flowing from the on-site edge into a visual reasoning model at HQ, which is watching for anything that would make this aisle unsafe."

**Console view**: Stage view. Forklift prim visibly drives up aisle-3 and stops at the marked approach-point. Event stream on the right shows mission dispatch → telemetry ticks coming back at 5 Hz. A subtle indicator on camera 2 shows "frames flowing, no alert."

### Minute 1:45 – 2:30 — The interrupt fires, the system replans

**Narration** (presenter clicks **Drop Pallet**):

> "Something just shifted into the aisle." *[pallet prim appears in aisle-3 in the twin; camera-2 indicator flips]* "The camera saw it, the visual reasoning model flagged it — 'aisle-3, obstruction' — and that safety alert flowed to the Fleet Manager. It's replanning: the forklift can't proceed via aisle-3, so instead of the clearance it was waiting for, it's getting a reroute — aisle-4. Watch."

**Console view**: Pallet prim materializes in aisle-3 (driven by the real `fleet.safety.alerts` event reaching the Isaac Sim twin-update subscriber). Overlay on camera 2 shows "Alert: aisle-3-obstruction — conf 0.91" with the model tag "cosmos-reason-2." Event stream shows the alert → Fleet Manager replan → reroute mission. Forklift prim pulls back and takes aisle-4 to Dock-B.

*[differentiator #3 surfaces as the visual itself — the alert crossed edge→hub and the reroute crossed hub→edge]*

### Minute 2:30 – 3:30 — The hybrid topology, narrated

**Narration**:

> "Here's the part Red Hat makes possible. The heavy visual reasoning runs at HQ on a data-center GPU — that's where you want big models. The fleet coordinator runs at HQ because it aggregates signal from every warehouse you operate. But the robot's control runtime runs on the edge node physically at the warehouse, because you don't want 300 milliseconds of cloud round-trip between an alert and a reroute on a moving forklift. Two clusters, one operational model — same Kubernetes, same images, same tooling — because real factories have both a datacenter and an edge, and this mirrors that honestly. You can't do this on a cloud service; the edge piece is physically at the factory."

**Console view**: Stage view transitions briefly to Architecture view (a simple two-cluster topology diagram with a link between them). Camera frames animate companion → hub; the safety alert animates hub → hub (perception on hub); the reroute mission animates hub → companion; telemetry animates companion → hub. Transition back to Stage view.

### Minute 3:30 – 4:15 — Telemetry + observability as the closing concrete

**Narration**:

> "The forklift just reached Dock-B on the rerouted path. Every event you just saw — the camera frame, the safety alert, the replan, the reroute, the telemetry coming back — carries a correlation ID. If the forklift does something unexpected tomorrow, an engineer pulls that trace: which policy version, which model inferred what, which decision, which command. That's the kind of auditability OT environments need."

**Console view**: Stage view. A mini-panel on the right shows a trace with an actual correlation ID (e.g., `trace-id: 4f3a…c917`): event → decision → mission → robot action → completion. Timestamps visible. One specific telemetry entry highlighted. Phase 1 ships real OpenTelemetry trace IDs — not mock — so this beat survives scrutiny.

**Note (post-review)**: Archetype-B persona review flagged the original "trace back through every step" line as a promise the visual didn't substantiate. Fix: show a real correlation ID on-screen, matching what the OTel pipeline actually produces.

### Minute 4:15 – 4:45 — The "what else is possible" teaser

**Narration**:

> "What you just saw is the operational loop — one robot, one event, one decision, one action. The full picture also includes: retraining the robot's policy when the model gets stale, rolling out a new policy to every factory at once, letting an AI assistant help operators explore what-if scenarios before committing changes. If any of that's worth 20 minutes of a deeper conversation, that's the next step."

**Console view**: Stage view with three pill-teasers appearing at the top of the panel, each labeled — "Retrain & promote", "Multi-site rollout", "Agentic operator". These are not clickable in the novice-mode 5-min script; they foreshadow the 20-min and 60-min demos.

### Minute 4:45 – 5:00 — Close

**Narration**:

> "Everything you saw runs on-prem, air-gap-capable, with the same operational model Red Hat already supports for thousands of production customers. The fleet moves; the line doesn't stop when you update it. That's what we bring to the physical-AI conversation." *[differentiator #8 surfaces in one sentence]*

**Console view**: Stage view holds. Seller closes the Console or transitions to follow-up — "would you like the 20-minute deeper look, or should I leave you with the repo?"

## Beat → differentiator map (grep-able by script author and reviewer)

```
BEAT 00:00 — differentiator #1 (on-prem / air-gap)
BEAT 01:45 — differentiator #3 (hybrid → edge → robot) — core visual (alert edge→hub, reroute hub→edge)
BEAT 02:30 — differentiator #3 (topology diagram)
BEAT 03:30 — differentiator #5 (OT-grade provenance — one-line surface only; not core)
BEAT 04:45 — differentiator #8 (day-2 lifecycle)
```

## Hard constraints

- **No agentic panel open**. Phase-1-skeletal Console; agentic is 60-min territory.
- **No MLflow / model-registry UI**. 20-min territory.
- **No security-checkbox content**. No FIPS, no STIG, no Sigstore. If the customer asks, redirect to 60-min follow-up.
- **No multi-site visible**. Hub + companion is the topology; no spokes. Multi-site is 20-min territory.
- **No scene authoring beyond the scene-pack overlay**. Uses Digital_Twin_Warehouse + Forklift_A01 + Unitree G1 + stock pallets only.
- **No live model training or inference-metric dashboards**. The trace panel shows operational events, not model metrics.
- **Presenter controls pacing via the two buttons** — no hard-coded timers. The approach-point pause is narrated, not clocked.
- **Offline-fallback recording must be seamless** — per charter success criterion. Script length above is a target; the recorded fallback matches.

## What this demo's existence gates (scope on Phase 1 implementation)

For the 5-min script to be runnable, Phase 1 must deliver (per `docs/04-phased-plan.md` and ADR-027):

1. `small_warehouse_digital_twin.usd` + Forklift_A01 + pallet variants uploaded to Nucleus.
2. Scene-pack overlay USD composing the above with approach-point markers, aisle signage, cameras, and docks.
3. `warehouse-topology.yaml` as the single source of truth for coordinates.
4. Isaac Sim 6.0 runner on hub with the MJPEG viewport server and the twin-update subscriber (consumes telemetry + alerts).
5. AI-generated photorealistic warehouse frames (`aisle3_empty.jpg`, `aisle3_pallet.jpg`, siblings) staged on SeaweedFS.
6. Fake-camera service on companion publishing to `warehouse.cameras.aisle3` with HTTP `POST /state` endpoint.
7. Cosmos Reason 2-8B on hub L40S (served via vLLM 0.11.0 + `--reasoning-parser qwen3`).
8. Obstruction-detector pod on hub consuming camera frames and publishing `fleet.safety.alerts`.
9. Fleet Manager v1 with replan-on-alert logic.
10. Mission Dispatcher on companion with the Waypoint Planner module (5 Hz pose emission, configurable).
11. OpenVLA host-native on companion Fedora host — called on pick for manipulation policy (not for navigation).
12. Kafka (AMQ Streams) with MirrorMaker2 federation across `warehouse.cameras.*`, `warehouse.telemetry.forklifts.*`, `fleet.missions`, `fleet.safety.alerts`.
13. WMS Stub on hub (`fl-07`, `fire_at_seconds=0`, topology-yaml-sourced ids).
14. Showcase Console skeletal — Stage view with MJPEG canvas, two demo buttons (Dispatch Mission, Drop Pallet), event-trace right panel, two-cluster topology dots, three closing teaser pills.

**Not required for the 5-min demo** (and therefore not Phase 1 critical path):
- USD Search API (cut).
- Full Metropolis VSS 8-GPU pipeline (cut; Cosmos Reason 2-8B replaces for the narrow "event from camera" job).
- Kit App Streaming WebRTC surfaced in the UI (plumbing stays, UI hidden — MJPEG is the Phase-1 path).
- MLflow backend beyond what's needed to serve the VLA (artifact store; no training demo in Phase 1).
- Isaac Lab training pipeline (Phase 2).
- LangGraph + MCP + Llama Stack (Phase 3).
- ACM multi-site spoke provisioning (Phase 2).
- Cosmos Predict / Cosmos Transfer (Phase 3).
- Cluster Compliance Operator / FIPS / STIG demo surfacing (kept in stack, not surfaced in this demo).

## Open items to resolve before recording the demo as an offline-fallback

- **Nucleus credentials** for USD upload. Fallback: bundle USD into the Isaac Sim Kit container image.
- **AI image set**: user produces the `aisle3_empty.jpg` / `aisle3_pallet.jpg` (and siblings) photorealistic set with SDXL/Flux/Midjourney; we wire the SeaweedFS bucket + upload path.
- **Cosmos Reason 2-8B runtime** (validated on 2026-04-20): Qwen3-VL-derivative, served via `vllm/vllm-openai:v0.11.0` + `--reasoning-parser qwen3` + `--max-model-len=8192` on L40S (bfloat16, `gpu-memory-utilization=0.9`). Per-frame latency ~3-6 s. The 2B variant was trialed on L4 and missed pallet detection outright; 8B is the Phase-1 choice.
- **Narration copy**: the template above is guidance; refine with specific wording when the pipeline is end-to-end working.
