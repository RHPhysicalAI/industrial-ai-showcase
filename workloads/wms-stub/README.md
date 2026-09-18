# wms-stub

**Role**: mock Warehouse Management System. Emits scripted, deterministic mission scenarios that drive the 5-min demo loop reproducibly.

**Phase**: 1 (5-min Warehouse Baseline — plan item 9).

## Interfaces

- **Produces**: Kafka topic `fleet.events` — deterministic event stream matching the 5-min script's "aisle-3 obstruction" beat. Avro-schema'd.
- **HTTP**: `GET /healthz`, `POST /reset-scene`, `POST /reset-fleet-demo`, `POST /scenarios/{name}/run`, `POST /scenarios/{name}/cancel`, `GET /scenarios` (list available).

`POST /reset-scene` resets the camera and publishes a `demo.reset` event so Fleet Manager clears its in-memory mission and obstruction state before the next dispatch.

`POST /drop-pallet` and `POST /clear-pallet` publish both the camera-state command and a deterministic `SafetyAlert`. The camera command keeps the on-site camera view in sync; the alert updates Fleet Manager and the Isaac Sim digital twin immediately. The normal fake-camera → obstruction-detector → Cosmos path remains active for real camera-driven transitions, but scripted demo buttons do not have to wait for or depend on VLM classification.

## Why deterministic, not live

Per `demos/warehouse-baseline/script.md` open-items resolution: for the 5-min novice-audience demo, we prefer pre-scripted deterministic scenarios over live Cosmos Reason detection. Live detection is more impressive for Archetype C but less reliable for a 5-minute sales demo. WMS-Stub drives the canonical demo loop; `camera-adapter` handles the live-detection path for 20-min/60-min variants.

## Scenario catalog (Phase 1)

- `warehouse-baseline-aisle3-obstruction` — the 5-min script beat. Timing: event fires 45 s into the demo loop; AMR executes reroute by 90 s.

Additional scenarios added per demo beat as demos grow.

## Deployment

- Cluster: OSD hub, namespace `fleet-ops`.
- Chart: `chart/`, Argo-managed from `infrastructure/gitops/apps/workloads/wms-stub/`.
- GPU: none.

## Local development

```
cd workloads/wms-stub
python -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pytest
uvicorn wms_stub.main:app --reload --port 8082
```

## Status

Phase 1 scaffolding only.
