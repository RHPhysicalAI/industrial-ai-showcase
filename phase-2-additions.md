# Phase 2 additions

> Storage terminology updated 2026-09-29: SeaweedFS references describe the current migration target, not what historical Phase 2 sessions deployed. CPU-only S3 validation in `showcase-storage-canary` passed; live data/consumer cutover remains pending; see the [storage guide](tools/object-storage/README.md).

This document describes every capability added in Phase 2 of the Physical AI Showcase, what each piece does for the showcase story, and where the gaps are.

All Phase 2 work is currently uncommitted — ~35 modified and new files across the working tree.

---

## 1. MES-Stub (brownfield integration pattern)

**Files added**: `workloads/mes-stub/` (6 files), `infrastructure/gitops/apps/workloads/mes-stub/` (6 manifests)

**What it is**: A standalone FastAPI microservice simulating a SAP PP/DS manufacturing execution system. It emits `MesOrder` events to a `mes.orders` Kafka topic representing production orders from an enterprise ERP layer. Three modes: on-demand single order (`POST /emit`), steady-stream every 15 seconds (`POST /stream/start`), and stop (`POST /stream/stop`). Five pre-built order templates cycle through realistic material codes (BEARING-ASSY-7200, MOTOR-CTRL-X10, etc.) between dock-a and dock-b.

**Showcase value**: Demonstrates that the fleet coordination layer can consume orders from enterprise systems, not just from a demo button. This is the "brownfield integration" talking point — the system doesn't require ripping out existing MES/ERP infrastructure. It slots into existing factory data flows.

**How it's used**: MES-Stub publishes orders → Fleet Manager consumes them → translates to robot DISPATCH missions. In a demo, you can show orders flowing from a simulated SAP system through Kafka to the robot fleet, which is a story industrial customers immediately relate to.

**Criticality**: **Supporting**. The Phase 1 demo loop works without it. Its value is in the sales conversation — it answers "how does this integrate with our existing SAP/MES?" before the customer asks.

**Phase 1 mitigation**: Fully additive. Deploys into the existing `fleet-ops` namespace. No changes to existing manifests. The `MesOrder` and `MesOrderPriority` models added to `common_lib/events.py` are new classes with no modifications to existing models. The GitOps ApplicationSet auto-discovers it.

---

## 2. Fleet Manager — MES consumer

**Files modified**: `workloads/fleet-manager/src/fleet_manager/main.py`, `planner.py`, `settings.py`, `pyproject.toml`

**What it is**: A 4th Kafka consumer loop (`_consume_mes_orders()`) in the fleet-manager that reads `MesOrder` events from the `mes.orders` topic. The planner's new `handle_mes_order()` translates each order into a `DISPATCH` FleetMission, mapping factory to robot via a static lookup (`factory-a → fl-07`, `factory-b → fl-08`). Order metadata (material, quantity, source/destination, priority) passes through as mission params.

**Showcase value**: Closes the MES-Stub story. Without this consumer, MES-Stub publishes into the void. Together they show an end-to-end flow from enterprise order to robot mission.

**How it's used**: Orders from MES-Stub arrive on Kafka → fleet-manager translates them → emits DISPATCH missions that the mission-dispatcher picks up. The Console's event stream shows these flowing through in real time.

**Criticality**: **Supporting**. Same as MES-Stub — strengthens the brownfield narrative but isn't required for the core Phase 1 obstruction demo.

**Phase 1 mitigation**: The new consumer is an additional `asyncio.create_task` alongside the existing three. Existing consumer loops are unchanged. The MES consumer connects to `mes.orders` with its own consumer group (`fleet-manager-mes`). **Risk**: if the `mes.orders` topic doesn't exist on the cluster when the fleet-manager starts, the consumer will log connection errors. It won't crash the process (KafkaJS retries indefinitely), but it will produce noisy logs. The topic is created by the Kafka topics manifest, which syncs via the same Argo CD cycle, so in practice they deploy together. The `handle_mes_order()` and `_pick_robot_for_factory()` methods are additive — no existing planner methods were modified.

---

## 3. Fleet Manager — auto-rollback

**Files added**: `workloads/fleet-manager/src/fleet_manager/rollback.py`
**Files modified**: `workloads/fleet-manager/src/fleet_manager/main.py`

**What it is**: When telemetry arrives with `anomaly_score >= 0.85`, the fleet-manager calls `trigger_rollback()`, which hits the GitHub API to find the latest commit touching that factory's `policy-version.yaml` and creates a revert. Argo CD syncs the revert, rolling the factory back to the previous VLA policy version. The threshold and GitHub integration are in `rollback.py`; the check is inserted into the existing `_consume_telemetry()` loop.

**Showcase value**: This is the "closed-loop safety" story — a bad model promotion produces anomalous behavior, the system detects it, and GitOps automatically rolls it back without human intervention. It ties together model promotion, fleet telemetry, and GitOps into a single narrative arc.

**How it's used**: Presenter clicks "Trigger Anomaly" in the Console (which calls wms-stub's `POST /trigger-anomaly`) → wms-stub publishes a high-anomaly telemetry event → fleet-manager detects score >= 0.85 → calls GitHub API to create a revert commit → Argo CD syncs it → factory's policy-version.yaml rolls back to the previous version.

**Criticality**: **Demo narrative**. This flow requires a GitHub token secret to function. Without it, `trigger_rollback()` logs a warning and silently no-ops. The core Phase 1 demo is unaffected either way.

**Phase 1 mitigation**: The rollback check is a 7-line `if should_rollback(...)` block inserted before the existing approach-point logic in `_consume_telemetry()`. During normal Phase 1 operation, `anomaly_score` from real telemetry is either `None` or well below 0.85, so `should_rollback()` returns `False` and execution falls through to the existing code unchanged. Even if a high score arrives, the absence of `GITHUB_TOKEN` in the deployment env means it logs a warning and returns. **Honest gap**: the deployment manifest (`infrastructure/gitops/apps/workloads/fleet-manager/deployment.yaml`) has no env vars for `GITHUB_TOKEN`, `GITHUB_REPO`, or `GITHUB_BRANCH`. The rollback code silently does nothing until those are added — likely via a VaultStaticSecret that hasn't been created yet.

---

## 4. WMS-Stub — anomaly trigger endpoint

**Files modified**: `workloads/wms-stub/src/wms_stub/main.py`, `scenarios.py`, `settings.py`

**What it is**: A new `POST /trigger-anomaly` endpoint on wms-stub that publishes a synthetic `FleetTelemetry` event with a high `anomaly_score` (default 0.95). Also adds a new `POLICY_ROLLOUT` scenario to the catalog with three buttons: "Dispatch Mission", "Trigger Anomaly", and "Reset Scene".

**Showcase value**: Provides the presenter-controlled trigger for the auto-rollback demo beat. Without it, there's no way to inject a high anomaly score through the Console.

**How it's used**: The Console renders the "Trigger Anomaly" button from the scenario catalog. Clicking it calls `POST /api/action/trigger-anomaly` → backend proxies to wms-stub → publishes telemetry → fleet-manager detects → rollback fires.

**Criticality**: **Demo narrative**. Only matters if you're showing the auto-rollback flow.

**Phase 1 mitigation**: The endpoint is purely additive — no existing routes were modified. The `POLICY_ROLLOUT` scenario is appended to the catalog after `AISLE_3_OBSTRUCTION`. The Console loads `scenarios[0]` as the default scenario, and since Python dicts preserve insertion order, `aisle-3-obstruction` stays first. **However**: the Console currently has no scenario selector UI. The `policy-rollout` scenario is unreachable from the Console unless the backend changes which scenario is returned first, or a selector is added. The endpoint itself works fine via curl, but the presenter can't switch to it in the UI today.

---

## 5. Factory B — multi-site pattern

**Files added**: `infrastructure/gitops/apps/workloads/factory-b/` (13 manifests), `infrastructure/gitops/apps/workloads/mission-dispatcher/policy-version.yaml`

**What it is**: A second factory namespace (`factory-b`) on the hub cluster with its own mission-dispatcher-b, fake-camera-b, and policy-version ConfigMap. Mirrors the Factory A edge pattern to demonstrate multi-site fleet coordination from a single control plane. Uses factory-b-prefixed Kafka topics (`factory-b.missions`, `factory-b.telemetry`, etc.) for isolation.

**Showcase value**: The "how does this scale to multiple factories?" question. Shows that each factory site gets its own namespace, its own set of Kafka topics, its own policy version, and its own robot — all managed from one hub. This is the ACM multi-cluster story projected onto a single cluster for demo purposes.

**How it's used**: Factory B appears in the Console's Fleet view as a second panel alongside Factory A. Each factory has independent policy versioning, independent anomaly tracking, and independent robot status. The mission-dispatcher-b sends idle heartbeat telemetry.

**Criticality**: **Supporting**. Strengthens the fleet-scale narrative but the Phase 1 demo loop doesn't need it.

**Phase 1 mitigation**: Entirely new namespace and manifests — no changes to existing Factory A resources. The only modification to an existing file is adding `policy-version.yaml` to Factory A's `mission-dispatcher/kustomization.yaml`, which is additive (new resource entry, no changes to existing resources). **Honest gap**: the `factory-b` BuildConfigs reference `sourceSecret: git-source-secret`, but `infrastructure/gitops/apps/workloads/build-secrets/` only provisions that secret in `fleet-ops`, `robot-edge`, and `omni-streaming`. Builds in the `factory-b` namespace will fail until a `vault-factory-b.yaml` is added to the build-secrets kustomization. **Also**: Factory B has no Isaac Sim instance and no VLA endpoint, so `mission-dispatcher-b` will be unable to call the VLA and will just emit idle telemetry. `fake-camera-b` will run but has no camera frames to serve. These are expected — Factory B is a topology/fleet-management story, not a second sim environment.

---

## 6. Kafka topics — Phase 2 additions

**Files modified**: `infrastructure/gitops/apps/platform/kafka/topics.yaml`

**What it is**: Seven new KafkaTopic CRs added to the existing `topics.yaml`: `mes.orders` (6 partitions) and five Factory B topics (`factory-b.cameras.dock1`, `factory-b.cameras.commands`, `factory-b.missions`, `factory-b.telemetry`, `factory-b.ops.events`), plus `factory-b.ops.events`.

**Showcase value**: Infrastructure backing for MES-Stub and Factory B. Without the topics, the producers have nowhere to write.

**How it's used**: Strimzi reconciles these topic CRs on the existing `fleet` Kafka cluster. All topics are in the `fleet-ops` namespace with the `strimzi.io/cluster: fleet` label, matching the Phase 1 pattern.

**Criticality**: **Required** for items 1, 2, and 5 above. Without them, those features produce Kafka errors.

**Phase 1 mitigation**: Additive only — existing topic definitions are unchanged. The new topics are appended after the existing Phase 1 + Session-18 topics. Strimzi creates new topics without affecting existing ones.

---

## 7. VLA training pipeline

**Files added**: `workloads/vla-training/` (14 files including compiled pipeline YAML)

**What it is**: A KFP v2 pipeline that fine-tunes NVIDIA's GR00T N1.7-3B VLA on 311 Unitree G1 teleop episodes. Four container-component stages: `data_prep` (download from HuggingFace, convert to LeRobot format, upload to S3), `fine_tune` (GR00T training on L40S, logs to MLflow with `dspa_run_id` tag), `validate_onnx` (structure/inference/determinism checks), `register_model` (writes to RHOAI Model Registry with lineage metadata). Also includes `promote.py` for GitOps-native model promotion (reads model URI → writes Kustomize patch → creates PR) and a pre-compiled `vla_finetune_pipeline.yaml`.

**Showcase value**: This is the "how did we get the model?" traceability story. Every piece of the chain — from training data to deployed policy — is traceable, auditable, and reproducible. It demonstrates RHOAI's DSPA, Model Registry, and MLflow working together for AI/ML governance. The promote.py script closes the loop: a validated model becomes a GitOps PR, which Argo CD syncs to the factory's policy-version ConfigMap.

**How it's used**: The pipeline runs on DSPA in the `vla-training` namespace. The Lineage view in the Console visualizes the chain. In a demo, you walk through dataset → pipeline → training → validation → model → promotion → deployment, showing full provenance at each step.

**Criticality**: **Core narrative**. This is the central "responsible AI" story — the thing that differentiates "we put a model on a robot" from "we have a governed, traceable, reproducible AI pipeline." The pipeline code itself won't run until DSPA infrastructure is deployed and the training image is built, but the talk-track can reference the lineage view and the pipeline structure today.

**Phase 1 mitigation**: Completely isolated. New package in `workloads/vla-training/` with no imports from or modifications to any Phase 1 code. No changes to any existing deployment manifests. The compiled pipeline YAML is checked into the repo but has no effect until someone submits it to DSPA.

---

## 8. DSPA infrastructure

**Files added**: `infrastructure/gitops/apps/platform/dspa/` (5 manifests)

**What it is**: A `DataSciencePipelinesApplication` CR in the `vla-training` namespace, backed by an auto-deployed MariaDB for pipeline metadata and shared S3 storage in `mlflow` (SeaweedFS is the migration target) for artifacts. VaultStaticSecrets project S3 credentials into `vla-training/s3-credentials` (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) and supply the HuggingFace token. The bucket-init Job uses `public.ecr.aws/aws-cli/aws-cli:2.34.0` as an Argo CD `Sync` hook in wave `1`, with bounded retries and a 600-second timeout. Creating the `vla-training` bucket during Sync prevents a new DSPA from waiting for a bucket whose creation is gated on application health.

**Showcase value**: DSPA is the execution environment for the VLA training pipeline. It's what lets you say "this runs on RHOAI, not on someone's laptop." The Vault integration for secrets demonstrates production-grade credential management.

**How it's used**: The pipeline YAML is submitted to DSPA's API server, which orchestrates the four container steps. Pipeline run metadata is stored in MariaDB; artifacts (model weights, validation reports) land in SeaweedFS.

**Criticality**: **Required for pipeline execution**. Without it, the training pipeline has no runtime. The Lineage view in the Console works without DSPA (it uses seed data), but actually running the pipeline requires DSPA to be deployed and healthy.

**Phase 1 mitigation**: The training namespace has its own resources but shares the storage service with MLflow. The migration endpoint is `http://seaweedfs.mlflow.svc.cluster.local:8333`; training reads and writes the `vla-training` bucket while MLflow keeps `mlflow-artifacts`. Separate buckets preserve object naming, but capacity and availability are shared, so migration requires controlled copy/cutover for both consumers. The ApplicationSet auto-discovers the directory. **Dependency**: the HuggingFace token must be pre-seeded in Vault at `kv/vla-training/hf`; if absent, that VaultStaticSecret fails to reconcile in `vla-training`.

---

## 9. Model Registry

**Files added**: `infrastructure/gitops/apps/platform/model-registry/` (2 manifests)

**What it is**: A `ModelRegistry` CR in `redhat-ods-applications` backed by the existing CNPG Postgres cluster (`mlflow-db-rw.mlflow.svc.cluster.local:5432`). Exposes gRPC (9090) and REST (8080) endpoints with a service route.

**Showcase value**: The model registry is where trained models get versioned and tracked with metadata. It's the "where does the model live after training?" answer, and it's the data source for the promote.py script that turns a registered model into a GitOps PR.

**How it's used**: The pipeline's `register_model` step writes model metadata here. The promote.py script reads from here. The Console's Lineage view (currently) uses static seed data rather than querying the registry live.

**Criticality**: **Required for pipeline + promotion**. Without it, the training pipeline's final step fails and promote.py has nothing to read.

**Phase 1 mitigation**: The ModelRegistry CR deploys into `redhat-ods-applications` (the RHOAI operator namespace). It creates a new database (`model_registry`) on the existing CNPG Postgres cluster. The CNPG operator handles database creation via the CR — but this database doesn't exist yet, and creating it is a side effect of the ModelRegistry CR reconciling. The existing `mlflow` database on the same Postgres cluster is unaffected. **Risk**: if the CNPG Postgres cluster is resource-constrained or the ModelRegistry operator isn't installed, this CR will sit in a degraded state. That's contained — it won't affect the mlflow database or any Phase 1 workload.

---

## 10. PLC Gateway VM

**Files added**: `infrastructure/gitops/apps/companion/plc-gateway-vm/` (5 manifests)

**What it is**: A KubeVirt VirtualMachine running Fedora 40 as a containerDisk on the companion cluster. Cloud-init installs Python 3 and starts a minimal OPC-UA server on port 4840 with four PLC variables: ConveyorSpeed, RobotArmPosition, EmergencyStop, CycleCount. NetworkPolicy restricts ingress to `factory-floor` and monitoring namespaces.

**Showcase value**: This is the "brownfield coexistence" talking point — OpenShift Virtualization can run legacy VMs alongside container pods. The OPC-UA protocol is what PLCs actually speak in factories. It shows that customers don't have to containerize everything on day one.

**How it's used**: It appears in the Architecture view's "KubeVirt VM" card. In a demo, you mention it exists and possibly show `oc get vm` on the companion cluster. The OPC-UA server runs, but nothing in the showcase consumes its data.

**Criticality**: **Pure talking point**. The VM has zero functional integration with any other showcase component. Nothing reads from port 4840. Nothing consumes the PLC variables. It exists to prove the concept is possible and to have a VM show up in `oc get vm` output during a demo.

**Phase 1 mitigation**: Deploys to the companion cluster via the `companion-apps` ApplicationSet. Completely isolated from the hub cluster where Phase 1 runs. New namespace (`factory-floor`), new VM — no contact with any Phase 1 resource.

**Honest assessment**: This is the most extraneous item in Phase 2. It has no data flow, no API consumer, and no integration surface. It's a standalone VM that runs a Python script. Its value is entirely in the conversation — "and we can run legacy PLC gateways as VMs right alongside the containerized workloads." If that talking point matters, the VM needs to exist. If it doesn't, this is dead weight in the manifests.

---

## 11. Console — view navigation + audience gating

**Files modified**: `console/frontend/src/App.tsx`, `types.ts`

**What it is**: The masthead now has two toggle groups: a view selector and the existing audience-mode selector. Views are gated by audience mode — novice sees only Stage, evaluator adds Fleet and Architecture, expert adds Lineage. The view selector only appears when there's more than one available view. When switching audience modes, if the current view isn't available in the new mode, it resets to Stage.

**Showcase value**: This is the core "progressive disclosure" mechanism for the Console. Different audiences see different depths of the system. A novice customer sees the simple demo. An evaluator sees fleet status and architecture. An expert sees the full lineage chain.

**How it's used**: Presenter switches audience modes during the demo to reveal more of the system as the conversation deepens.

**Criticality**: **Critical to Console**. This is the navigation framework for all Phase 2 Console views.

**Phase 1 mitigation**: The Stage view content is unchanged — it's wrapped in `{currentView === "stage" && (...)}` but renders identically when selected. Default state is `audience: "novice"` and `currentView: "stage"`, so a cold load shows exactly the Phase 1 UI. **Behavior change**: the teaser badges section (showing "Retrain & promote", "Multi-site rollout", "Agentic operator" at the bottom) was removed. Those badges were Phase 1 placeholders for future capabilities — now replaced by actual views. This is intentional, not accidental.

---

## 12. Console — Fleet view

**Files added**: `console/frontend/src/FleetView.tsx`
**Files modified**: `console/backend/src/server.ts`, `console/backend/src/kafkaStream.ts`, `console/frontend/src/api.ts`, `types.ts`, `showcase.css`

**What it is**: Two side-by-side factory panels (Factory A, Factory B), each showing: policy version in a dark pill, robot ID with status label (green=active, blue=idle, orange=rerouting), anomaly score bar (color-coded: green below 0.5, orange below 0.85, red above), Argo sync status badge, and last heartbeat timestamp. Polls `GET /api/fleet` every 5 seconds. An anomaly alert card shows recent high-anomaly events.

The backend's `/api/fleet` endpoint reads live telemetry from `stream.getLatestTelemetry()` (which tracks per-robot snapshots from `fleet.telemetry` Kafka messages) and returns factory status for fl-07 and fl-08 with sensible fallback defaults.

**Showcase value**: Real-time fleet visibility across multiple factories. Shows policy versions, robot health, and anomaly detection in one view. This is the "fleet operations dashboard" that demonstrates operational awareness at scale.

**How it's used**: Available in evaluator and expert modes. Shows live telemetry during demo. When the auto-rollback flow fires, the anomaly bar turns red and the alert card populates.

**Criticality**: **Demo narrative for multi-site and rollback stories**. Without it, those features have no visual representation.

**Phase 1 mitigation**: Frontend is a new component — additive. Backend changes: `kafkaStream.ts` adds telemetry tracking in the existing `eachMessage` handler. Every message still flows through to SSE unchanged — the telemetry extraction is read-only bookkeeping on the side. `server.ts` adds two new GET routes; existing routes are untouched. **Honest gap**: the backend's Kafka subscription (`config.ts` default topics) doesn't include any `factory-b.*` topics. Factory B's panel will only ever show fallback data (hardcoded defaults in `server.ts`) because the backend never receives Factory B telemetry. This is a wiring gap, not a design choice.

---

## 13. Console — Architecture view

**Files added**: `console/frontend/src/ArchitectureView.tsx`
**Files modified**: `console/frontend/src/showcase.css`

**What it is**: A static Purdue-model diagram showing four levels — Level 4 Enterprise/Hub (Fleet Manager, MLflow, DSPA, Model Registry, Console, Argo CD), Level 3 MES (MES-Stub, WMS-Stub, Kafka), Level 2 HMI/SCADA (PLC Gateway VM), Level 1 Field Devices (Mission Dispatchers + Fake Cameras for both factories). Below the diagram: three info cards for KubeVirt VM status, MES Order Flow, and Air-Gap Path.

**Showcase value**: Gives evaluators a system map. Answers "what are all the pieces and how do they relate?" without requiring the presenter to draw on a whiteboard. The Purdue model framing is deliberate — it's the mental model industrial customers already use.

**How it's used**: Available in evaluator and expert modes. The presenter walks through the architecture, pointing out Red Hat components at each level.

**Criticality**: **Presentation aid**. No live data, no backend calls (fetches topology but doesn't use it for the main diagram). It's a structured slide rendered in the browser.

**Phase 1 mitigation**: New component, additive CSS classes. No risk to Phase 1.

**Honest assessment**: The data in this view is hardcoded in the component. The namespace listed for the Console says `showcase-console` but it actually runs in `fleet-ops`. The KubeVirt VM card says "Running" but doesn't check actual VM status. The MES Order Flow and Air-Gap Path cards are static text. This view is useful for the demo talk-track but is not connected to any live system state.

---

## 14. Console — Lineage view

**Files added**: `console/frontend/src/LineageView.tsx`
**Files modified**: `console/backend/src/server.ts`, `console/frontend/src/api.ts`, `types.ts`, `showcase.css`

**What it is**: A horizontal DAG showing the pipeline chain — dataset → pipeline → training → validation → model — as clickable node cards color-coded by type (blue, grey, green, yellow, red). Clicking a node shows its metadata in a side panel via a PatternFly DescriptionList.

The backend's `/api/lineage` endpoint returns static seed data: 5 nodes with metadata fields matching what the real pipeline would produce (repo, episodes, modality, base_model, embodiment, max_steps, etc.) and 4 edges connecting them linearly.

**Showcase value**: Visualizes the "data → model" traceability chain. Shows that every piece of the AI pipeline is auditable — from the training dataset (NVIDIA G1 Teleop, 311 episodes) through fine-tuning (GR00T N1.7-3B, 2000 steps on L40S) through ONNX validation to the registered model artifact.

**How it's used**: Available in expert mode only. The presenter clicks through nodes to show metadata provenance. This is the "responsible AI" talking point — "you can trace every model back to its training data."

**Criticality**: **Core narrative for the AI governance story**. The view itself works with seed data today. When the pipeline actually runs, the data can shift to live Model Registry queries.

**Phase 1 mitigation**: New component + new backend route. Fully additive. The seed data in `server.ts` is a self-contained object literal with no dependencies on any external system.

**Honest assessment**: The lineage data is entirely static. The metadata values (final_loss: 0.0342, training_steps: 2000) are plausible but fabricated — they represent what a real pipeline run would produce, not an actual run. The view doesn't query Model Registry or DSPA. Connecting it to live data is future work.

---

## 15. Event model additions

**Files modified**: `workloads/common/python-lib/src/common_lib/events.py`

**What it is**: Two new models appended to the shared event library: `MesOrderPriority` (enum: low/normal/high/urgent) and `MesOrder` (frozen Pydantic model with order_id, trace_id, material, quantity, source/destination locations, priority, factory, due_at, emitted_at).

**Showcase value**: Shared data contract consumed by MES-Stub (producer) and Fleet Manager (consumer).

**Criticality**: **Required** for MES-Stub and Fleet Manager MES consumer.

**Phase 1 mitigation**: Purely additive — two new classes appended after the existing `CameraCommand` model. No modifications to `FleetMission`, `FleetTelemetry`, `SafetyAlert`, or any existing model. Existing imports across all Phase 1 workloads are unaffected because they import specific names, not `*`.

---

## 16. ADR-028

**Files modified**: `docs/07-decisions.md`

**What it is**: Records the decision to keep Phase 2 warehouse-only — no second simulation scene, no scene selector (D.4 skipped). Second scene deferred to Phase 4.

**Showcase value**: Decision hygiene. Explains why there's only one sim environment despite having two factories.

**Criticality**: Documentation only.

**Phase 1 mitigation**: Additive append to a docs file.

---

## Known gaps

### Resolved

1. ~~**Factory B build secrets**~~: Fixed — `vault-factory-b.yaml` added to `infrastructure/gitops/apps/workloads/build-secrets/`.

2. ~~**Fleet-manager deployment env vars**~~: Fixed — `GITHUB_TOKEN` (from VaultStaticSecret at `kv/fleet-manager/github`), `GITHUB_REPO`, and `GITHUB_BRANCH` added to deployment. Token is `optional: true` so the pod starts even if the Vault path doesn't exist yet.

3. ~~**Console Kafka topic subscription**~~: Fixed — backend now subscribes to `factory-b.telemetry`, `factory-b.missions`, `factory-b.ops.events`, and `mes.orders`. Kafka stream tracks telemetry from both `fleet.telemetry` and `factory-b.telemetry`. Event stream shows factory-b and MES events with appropriate colors and labels.

4. ~~**Architecture view stale data**~~: Fixed — Console namespace corrected to `fleet-ops`. KubeVirt VM card no longer claims "Running" status. Added Obstruction Detector and Cosmos Reason 2-8B to Level 4 components.

### Remaining

5. **No scenario selector**: The Console loads `scenarios[0]` as the default scenario. With `POLICY_ROLLOUT` added to the catalog, both scenarios exist on the backend, but the UI has no way to switch between them. The auto-rollback demo flow can't be triggered from the Console without either a scenario selector or changing the catalog order. Tracked in `docs/plans/phase-2-plan.md` under "Open items to circle back on."

6. **Lineage data is static**: The Lineage view uses seed data from a hardcoded object literal in `server.ts`. It doesn't query Model Registry or DSPA. The metadata is plausible but represents a hypothetical pipeline run, not a real one. When the sibling project (`nvidia-industrial-wbc-pipeline`) produces a completed fine-tuning run, real metrics should replace the placeholder values. Tracked in `docs/plans/phase-2-plan.md` under "Open items to circle back on."

7. **PLC Gateway VM has no integration surface**: The OPC-UA server runs, but nothing in the showcase reads from it. It's show-and-tell with no data flow. Accepted — the brownfield talking point is its purpose.

8. **Factory B has no sim environment**: `mission-dispatcher-b` will emit idle telemetry but can't complete VLA-driven missions. `fake-camera-b` has no camera frames to serve. This is by design (ADR-028) and accepted — Factory B is a topology/fleet-management story, not a second working demo loop.

9. **Vault path for GitHub token**: `kv/fleet-manager/github` needs to be seeded in Vault with a `token` key containing a GitHub PAT with repo write access. Without it, rollback silently no-ops (logged as warning).
