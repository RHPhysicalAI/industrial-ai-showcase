# fleet-manager

**Role**: the hub-side decisioning service. Consumes camera/scene events and work-order intents, emits missions.

**Phase**: 1 (5-min Warehouse Baseline — plan item 7).

## Interfaces

- **Consumes**: Kafka topic `fleet.events` (camera/scene events from `camera-adapter`), Kafka topic `fleet.telemetry` (robot telemetry echoed back from `mission-dispatcher`). Optional in Phase 2+: `mes.orders` (brownfield beat).
- **Produces**: Kafka topic `fleet.missions` (routed to the companion cluster for execution).
- **Reset behavior**: `demo.reset` on `fleet.events` clears active missions and obstruction state held by the in-memory demo planner.
- **HTTP**: `GET /healthz`, `GET /metrics` (Prometheus), `POST /internal/decisions/simulate` (dev/demo only).
- **State**: PostgreSQL via CloudNativePG — mission history, decision audit log, policy-version pins.

## Decisioning v1 (Phase 1)

Single rule per `demos/warehouse-baseline/script.md` Segment 2 beat: **aisle-obstruction event → reroute AMR on an alternate path**. WMS-Stub drives the deterministic scenario; Fleet Manager's rule engine emits the reroute mission. Extension pattern documented (not implemented); additional rules land when a demo beat earns them — per user guidance 2026-04-19.

LangGraph-based agentic decisioning lives in `langgraph-orchestrator/` and arrives Phase 3 (ADR-005, ADR-019). Fleet Manager v2 becomes a hybrid fast-path-plus-agentic-path service at that point; v1 stays rule-based.

## Deployment

- Cluster: OSD hub, namespace `fleet-ops`.
- Chart: `chart/`, Argo-managed from `infrastructure/gitops/apps/workloads/fleet-manager/`.
- GPU: none.
- Service Mesh member; default-deny NetworkPolicy + explicit allowlists to Kafka and Postgres.

## Local development

```
cd workloads/fleet-manager
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pytest
uvicorn fleet_manager.main:app --reload --port 8080
```

## Status

Phase 1 scaffolding only. Implementation lands after Kafka topics are up (plan item 5) and schema registry has Avro schemas registered.
