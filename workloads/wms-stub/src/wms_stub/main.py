# This project was developed with assistance from AI tools.
"""WMS-Stub entrypoint — demo control panel for the Phase-1 showcase.

Provides two categories of actions for the Showcase Console buttons:
  - Dispatch: sends a FleetMission (DISPATCH) to fleet.missions
  - Camera state: publishes CameraCommand to Kafka, consumed by fake-camera
    on the companion cluster to toggle between "empty" and "obstructed"

The scenario catalog (GET /scenarios) tells the Console which buttons
to render and what actions they trigger.
"""

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from common_lib.events import (
    CameraCommand,
    EventClass,
    FleetEvent,
    FleetMission,
    FleetTelemetry,
    MissionKind,
    SafetyAlert,
)
from common_lib.kafka import JsonProducer
from common_lib.logging import configure_logging
from wms_stub import __version__
from wms_stub.scenarios import get_scenario, list_scenarios
from wms_stub.scene import build_scene_alert
from wms_stub.settings import WmsStubSettings

if TYPE_CHECKING:
    from structlog.stdlib import BoundLogger


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = WmsStubSettings()
    log = configure_logging(settings.service_name, settings.log_level)
    log.info(
        "startup",
        version=__version__,
        missions_topic=settings.missions_topic,
        camera_commands_topic=settings.camera_commands_topic,
    )

    producer = JsonProducer(settings.kafka_bootstrap_servers, client_id=settings.service_name)

    app.state.settings = settings
    app.state.log = log
    app.state.producer = producer
    try:
        yield
    finally:
        producer.flush(timeout=5.0)
        log.info("shutdown")


app = FastAPI(title="wms-stub", version=__version__, lifespan=lifespan)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    return {"status": "ready"}


# ---------------------------------------------------------------------------
# Scenario catalog (Console reads this to render buttons)
# ---------------------------------------------------------------------------

@app.get("/scenarios")
async def get_scenarios() -> dict[str, list[str]]:
    return {"scenarios": list_scenarios()}


@app.get("/scenarios/{name}")
async def get_scenario_detail(name: str) -> dict:
    try:
        s = get_scenario(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "name": s.name,
        "buttons": [{"label": b.label, "action": b.action, "params": b.params} for b in s.buttons],
    }


# ---------------------------------------------------------------------------
# Dispatch mission
# ---------------------------------------------------------------------------

class DispatchRequest(BaseModel):
    robot_id: str = Field(default="")
    route_aisle: str = Field(default="")
    destination: str = Field(default="")


@app.post("/dispatch")
async def dispatch_mission(req: DispatchRequest | None = None) -> dict[str, str]:
    settings: WmsStubSettings = app.state.settings
    log: "BoundLogger" = app.state.log
    producer: JsonProducer = app.state.producer

    robot_id = (req.robot_id if req and req.robot_id else settings.default_robot_id)
    route_aisle = (req.route_aisle if req and req.route_aisle else settings.default_route_aisle)
    destination = (req.destination if req and req.destination else settings.default_destination)
    trace_id = uuid4().hex

    mission = FleetMission(
        trace_id=trace_id,
        kind=MissionKind.DISPATCH,
        robot_id=robot_id,
        policy_version=settings.policy_version,
        params={
            "route_aisle": route_aisle,
            "destination": destination,
        },
    )
    producer.send(settings.missions_topic, key=robot_id, value=mission)
    producer.flush(timeout=2.0)

    log.info(
        "dispatch.sent",
        trace_id=trace_id,
        mission_id=str(mission.mission_id),
        robot_id=robot_id,
        route_aisle=route_aisle,
    )
    return {
        "status": "dispatched",
        "trace_id": trace_id,
        "mission_id": str(mission.mission_id),
        "robot_id": robot_id,
        "route_aisle": route_aisle,
    }


# ---------------------------------------------------------------------------
# Camera state toggle (fake-camera on companion)
# ---------------------------------------------------------------------------

class CameraStateRequest(BaseModel):
    state: str = Field(description="Target state: 'obstructed' or 'empty'.")


@app.post("/drop-pallet")
async def drop_pallet() -> dict[str, str]:
    return await _set_camera_state("obstructed")


@app.post("/clear-pallet")
async def clear_pallet() -> dict[str, str]:
    return await _set_camera_state("empty")


@app.post("/camera/state")
async def set_camera_state(req: CameraStateRequest) -> dict[str, str]:
    return await _set_camera_state(req.state)


@app.post("/reset-scene")
async def reset_scene() -> dict[str, str]:
    """Reset demo to starting state: camera→empty + immediate scene-clear alert."""
    settings: WmsStubSettings = app.state.settings
    log: "BoundLogger" = app.state.log
    producer: JsonProducer = app.state.producer
    trace_id = uuid4().hex

    cmd = CameraCommand(
        trace_id=trace_id,
        camera_id=settings.camera_id,
        state="empty",
    )
    producer.send(settings.camera_commands_topic, key=settings.camera_id, value=cmd)

    alert = SafetyAlert(
        trace_id=trace_id,
        aisle_id="aisle-3",
        camera_id=settings.camera_id,
        detection_label="scene-reset",
        confidence=1.0,
        source_model="wms-stub",
        obstructed=False,
        detail="manual scene reset via console",
    )
    event = FleetEvent(
        trace_id=trace_id,
        event_class=EventClass.DEMO_RESET,
        source="wms-stub",
        location="hub",
        confidence=1.0,
        payload={"reason": "manual scene reset via console"},
    )
    producer.send("fleet.events", key="demo", value=event)
    producer.send("fleet.safety.alerts", key=settings.camera_id, value=alert)
    producer.flush(timeout=2.0)

    log.info("scene.reset", trace_id=trace_id)
    return {"status": "ok", "trace_id": trace_id}


# ---------------------------------------------------------------------------
# Anomaly trigger (auto-rollback demo beat, Segment 3)
# ---------------------------------------------------------------------------

class TriggerAnomalyRequest(BaseModel):
    anomaly_score: float = Field(default=0.95, ge=0.0, le=1.0)
    robot_id: str = Field(default="")
    factory: str = Field(default="factory-a")


@app.post("/trigger-anomaly")
async def trigger_anomaly(req: TriggerAnomalyRequest | None = None) -> dict[str, str]:
    """Inject a high anomaly-score telemetry event to trigger auto-rollback."""
    settings: WmsStubSettings = app.state.settings
    log: "BoundLogger" = app.state.log
    producer: JsonProducer = app.state.producer

    robot_id = (req.robot_id if req and req.robot_id else settings.default_robot_id)
    anomaly_score = req.anomaly_score if req else 0.95
    trace_id = uuid4().hex

    telemetry = FleetTelemetry(
        trace_id=trace_id,
        robot_id=robot_id,
        anomaly_score=anomaly_score,
        pose={"x": 0.0, "y": 0.0, "z": 0.0},
    )
    producer.send(settings.telemetry_topic, key=robot_id, value=telemetry)
    producer.flush(timeout=2.0)

    log.info(
        "anomaly.triggered",
        trace_id=trace_id,
        robot_id=robot_id,
        anomaly_score=anomaly_score,
    )
    return {
        "status": "anomaly_triggered",
        "trace_id": trace_id,
        "robot_id": robot_id,
        "anomaly_score": str(anomaly_score),
    }


# ---------------------------------------------------------------------------
# Policy promotion + lineage advancement (Fleet demo, Segments 2–3)
# ---------------------------------------------------------------------------

class PromotePolicyRequest(BaseModel):
    factory: str = Field(default="factory-a")
    version: str = Field(default="vla-warehouse-v1.4")


@app.post("/promote-policy")
async def promote_policy(req: PromotePolicyRequest | None = None) -> dict[str, str]:
    """Signal a policy promotion for the fleet demo."""
    log: "BoundLogger" = app.state.log
    producer: JsonProducer = app.state.producer

    factory = req.factory if req else "factory-a"
    version = req.version if req else "vla-warehouse-v1.4"
    trace_id = uuid4().hex

    event = FleetEvent(
        trace_id=trace_id,
        event_class=EventClass.POLICY_PROMOTED,
        source="wms-stub",
        location=factory,
        confidence=1.0,
        payload={"factory": factory, "version": version},
    )
    producer.send("fleet.events", key=factory, value=event)
    producer.flush(timeout=2.0)

    log.info("policy.promoted", trace_id=trace_id, factory=factory, version=version)
    return {"status": "promoted", "trace_id": trace_id, "factory": factory, "version": version}


class AdvanceLineageRequest(BaseModel):
    phase: str = Field(default="training-running")


@app.post("/advance-lineage")
async def advance_lineage(req: AdvanceLineageRequest | None = None) -> dict[str, str]:
    """Advance the lineage view to show training progress."""
    log: "BoundLogger" = app.state.log
    producer: JsonProducer = app.state.producer

    phase = req.phase if req else "training-running"
    trace_id = uuid4().hex

    event = FleetEvent(
        trace_id=trace_id,
        event_class=EventClass.LINEAGE_ADVANCE,
        source="wms-stub",
        location="hub",
        confidence=1.0,
        payload={"phase": phase},
    )
    producer.send("fleet.events", key="lineage", value=event)
    producer.flush(timeout=2.0)

    log.info("lineage.advanced", trace_id=trace_id, phase=phase)
    return {"status": "ok", "trace_id": trace_id, "phase": phase}


@app.post("/reset-fleet-demo")
async def reset_fleet_demo() -> dict[str, str]:
    """Reset the fleet demo state machine and camera."""
    settings: WmsStubSettings = app.state.settings
    log: "BoundLogger" = app.state.log
    producer: JsonProducer = app.state.producer
    trace_id = uuid4().hex

    event = FleetEvent(
        trace_id=trace_id,
        event_class=EventClass.DEMO_RESET,
        source="wms-stub",
        location="hub",
        confidence=1.0,
    )
    producer.send("fleet.events", key="demo", value=event)

    cmd = CameraCommand(
        trace_id=trace_id,
        camera_id=settings.camera_id,
        state="empty",
    )
    producer.send(settings.camera_commands_topic, key=settings.camera_id, value=cmd)

    alert = SafetyAlert(
        trace_id=trace_id,
        aisle_id="aisle-3",
        camera_id=settings.camera_id,
        detection_label="demo-reset",
        confidence=1.0,
        source_model="wms-stub",
        obstructed=False,
        detail="fleet demo reset",
    )
    producer.send("fleet.safety.alerts", key=settings.camera_id, value=alert)
    producer.flush(timeout=2.0)

    log.info("fleet-demo.reset", trace_id=trace_id)
    return {"status": "ok", "trace_id": trace_id}


async def _set_camera_state(target_state: str) -> dict[str, str]:
    settings: WmsStubSettings = app.state.settings
    log: "BoundLogger" = app.state.log
    producer: JsonProducer = app.state.producer

    trace_id = uuid4().hex
    cmd = CameraCommand(
        trace_id=trace_id,
        camera_id=settings.camera_id,
        state=target_state,
    )
    producer.send(settings.camera_commands_topic, key=settings.camera_id, value=cmd)

    # The camera command changes the on-site image, but the digital twin and
    # Fleet Manager consume SafetyAlert events.  Emit the deterministic demo
    # transition here as well so the scripted button does not depend on a
    # later VLM classification to update the twin.  Real camera frames still
    # flow through fake-camera → obstruction-detector → the same topic.
    alert = build_scene_alert(settings, trace_id, target_state)
    if alert is not None:
        producer.send(settings.alerts_topic, key=settings.camera_id, value=alert)

    producer.flush(timeout=2.0)

    log.info(
        "camera.command.sent",
        trace_id=trace_id,
        target=target_state,
        safety_alert_emitted=alert is not None,
    )
    return {"status": "ok", "camera_state": target_state}
