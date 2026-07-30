# This project was developed with assistance from AI tools.
"""Mission Dispatcher entrypoint.

Consumes fleet.missions and drives the forklift along planned routes:
  - DISPATCH  → plan route via waypoint planner, drive to approach-point, pause
  - PROCEED   → grant approach-point clearance, enter aisle, drive to destination
  - REROUTE   → cancel current route, plan new route via alternate aisle
  - PICKUP    → call VLA for manipulation action at destination

Emits fleet.ops.events (lifecycle transitions) and fleet.telemetry (5 Hz poses).
"""

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI

from common_lib.events import FleetMission, FleetOpsEvent, FleetTelemetry, MissionKind, OpsEventKind
from common_lib.kafka import JsonConsumer, JsonProducer
from common_lib.logging import configure_logging
from mission_dispatcher import __version__
from mission_dispatcher.settings import MissionDispatcherSettings
from mission_dispatcher.vla_client import VlaClient
from mission_dispatcher.waypoint_planner import RouteExecution, execute_route, plan_route

if TYPE_CHECKING:
    from structlog.stdlib import BoundLogger

_PLACEHOLDER_IMAGE_B64 = ""


class Dispatcher:
    """Coordinates route execution with incoming mission commands."""

    def __init__(
        self,
        producer: JsonProducer,
        vla: VlaClient,
        settings: MissionDispatcherSettings,
        log: "BoundLogger",
    ) -> None:
        self._producer = producer
        self._vla = vla
        self._settings = settings
        self._log = log
        self._active: dict[str, RouteExecution] = {}
        self._route_tasks: dict[str, asyncio.Task] = {}  # type: ignore[type-arg]

    def _emit_ops(self, trace_id: str, mission_id: str, robot_id: str, kind: OpsEventKind, detail: str = "") -> None:
        self._producer.send(
            self._settings.ops_events_topic,
            key=robot_id,
            value=FleetOpsEvent(
                trace_id=trace_id,
                mission_id=mission_id,
                kind=kind,
                detail=detail or None,
            ),
        )

    async def handle_dispatch(self, mission: FleetMission) -> None:
        route_aisle = str(mission.params.get("route_aisle", "aisle-3"))
        self._log.info(
            "dispatch.starting",
            robot_id=mission.robot_id,
            route=route_aisle,
            destination=mission.params.get("destination", ""),
        )
        self._emit_ops(mission.trace_id, str(mission.mission_id), mission.robot_id, OpsEventKind.MISSION_RECEIVED)

        execution = plan_route(
            robot_id=mission.robot_id,
            trace_id=mission.trace_id,
            mission_id=str(mission.mission_id),
            route_aisle=route_aisle,
            speed_mps=self._settings.waypoint_speed_mps,
            hz=self._settings.waypoint_hz,
        )
        self._active[mission.robot_id] = execution
        self._emit_ops(mission.trace_id, str(mission.mission_id), mission.robot_id, OpsEventKind.MISSION_STARTED)

        task = asyncio.create_task(self._run_route(mission, execution))
        self._route_tasks[mission.robot_id] = task

    async def _run_route(self, mission: FleetMission, execution: RouteExecution) -> None:
        completed = await execute_route(
            execution,
            self._producer,
            self._settings.telemetry_topic,
            self._settings.waypoint_hz,
            self._settings.policy_version,
            self._log,
        )
        if not completed:
            return

        try:
            self._emit_ops(mission.trace_id, str(mission.mission_id), mission.robot_id, OpsEventKind.VLA_CALL_STARTED)
            action = await self._vla.act(
                image_b64=_PLACEHOLDER_IMAGE_B64,
                instruction=f"PICKUP: retrieve pallet at {mission.params.get('destination', 'dock-b')}",
                trace_id=mission.trace_id,
            )
            self._log.info("vla.action.received", robot_id=mission.robot_id, model=action.model_version)
            self._emit_ops(
                mission.trace_id, str(mission.mission_id), mission.robot_id,
                OpsEventKind.VLA_CALL_COMPLETED, detail=action.model_version,
            )
        except Exception as exc:  # noqa: BLE001
            self._log.exception("vla.call.failed", robot_id=mission.robot_id, error=str(exc))
            self._emit_ops(
                mission.trace_id, str(mission.mission_id), mission.robot_id,
                OpsEventKind.VLA_CALL_FAILED, detail=str(exc)[:200],
            )

        self._emit_ops(mission.trace_id, str(mission.mission_id), mission.robot_id, OpsEventKind.MISSION_COMPLETED)
        self._producer.flush(timeout=2.0)
        self._active.pop(mission.robot_id, None)
        self._route_tasks.pop(mission.robot_id, None)

    def handle_proceed(self, mission: FleetMission) -> None:
        execution = self._active.get(mission.robot_id)
        if execution and execution.paused:
            self._log.info("clearance.granting", robot_id=mission.robot_id)
            execution.grant_clearance()

    async def handle_reroute(self, mission: FleetMission) -> None:
        old = self._active.pop(mission.robot_id, None)
        if old:
            old.cancel()
            task = self._route_tasks.pop(mission.robot_id, None)
            if task:
                await asyncio.gather(task, return_exceptions=True)

        route_aisle = str(mission.params.get("route_aisle", "aisle-4"))
        self._log.info("reroute.starting", robot_id=mission.robot_id, new_route=route_aisle)

        execution = plan_route(
            robot_id=mission.robot_id,
            trace_id=mission.trace_id,
            mission_id=str(mission.mission_id),
            route_aisle=route_aisle,
            speed_mps=self._settings.waypoint_speed_mps,
            hz=self._settings.waypoint_hz,
        )
        self._active[mission.robot_id] = execution
        task = asyncio.create_task(self._run_route(mission, execution))
        self._route_tasks[mission.robot_id] = task

    async def process(self, mission: FleetMission) -> None:
        if mission.kind == MissionKind.DISPATCH:
            await self.handle_dispatch(mission)
        elif mission.kind == MissionKind.PROCEED:
            self.handle_proceed(mission)
        elif mission.kind == MissionKind.REROUTE:
            await self.handle_reroute(mission)
        else:
            self._log.warning("mission.unknown_kind", kind=mission.kind, robot_id=mission.robot_id)


async def _consume_loop(
    consumer: JsonConsumer[FleetMission],
    dispatcher: Dispatcher,
    log: "BoundLogger",
) -> None:
    loop = asyncio.get_running_loop()
    while True:
        mission = await loop.run_in_executor(None, consumer.poll, 1.0)
        if mission is None:
            await asyncio.sleep(0)
            continue
        log.info("mission.received", kind=mission.kind, robot_id=mission.robot_id)
        await dispatcher.process(mission)
        consumer.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = MissionDispatcherSettings()
    log = configure_logging(settings.service_name, settings.log_level)
    log.info(
        "startup",
        version=__version__,
        vla_endpoint=settings.vla_endpoint_url,
        waypoint_hz=settings.waypoint_hz,
    )

    extra_kafka: dict[str, str | int | bool] = {}
    if settings.kafka_security_protocol.upper() in {"SSL", "SASL_SSL"}:
        extra_kafka["security.protocol"] = settings.kafka_security_protocol
        extra_kafka["ssl.endpoint.identification.algorithm"] = (
            settings.kafka_ssl_endpoint_identification_algorithm
        )
        extra_kafka["enable.ssl.certificate.verification"] = (
            settings.kafka_enable_ssl_certificate_verification
        )

    producer = JsonProducer(
        settings.kafka_bootstrap_servers,
        client_id=settings.service_name,
        extra_config=extra_kafka or None,
    )
    consumer = JsonConsumer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.consumer_group_id,
        topic=settings.missions_topic,
        model=FleetMission,
        extra_config=extra_kafka or None,
    )
    vla = VlaClient(settings.vla_endpoint_url, timeout_s=settings.vla_request_timeout_s)
    dispatcher = Dispatcher(producer, vla, settings, log)

    app.state.settings = settings
    app.state.log = log
    app.state.dispatcher = dispatcher

    task = asyncio.create_task(_consume_loop(consumer, dispatcher, log))
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        consumer.close()
        producer.flush(timeout=5.0)
        await vla.aclose()
        log.info("shutdown")


app = FastAPI(title="mission-dispatcher", version=__version__, lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    return {"status": "ready"}
