# This project was developed with assistance from AI tools.
"""Fleet Manager entrypoint.

Consumes four Kafka topics concurrently:
  - fleet.missions   (DISPATCH from wms-stub → track + await approach-point)
  - fleet.safety.alerts (SafetyAlert from obstruction-detector → replan / clear)
  - fleet.telemetry  (FleetTelemetry from mission-dispatcher → approach-point arrival)
  - mes.orders       (MesOrder from mes-stub → translate to DISPATCH missions)

Emits to fleet.missions:
  - DISPATCH when MES orders are translated into missions
  - PROCEED  when approach-point clearance is granted
  - REROUTE  when an obstruction forces replanning
"""

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI

from common_lib.events import (
    EventClass,
    FleetEvent,
    FleetMission,
    FleetTelemetry,
    MesOrder,
    MissionKind,
    SafetyAlert,
)
from common_lib.kafka import JsonConsumer, JsonProducer
from common_lib.logging import configure_logging
from fleet_manager import __version__
from fleet_manager.planner import MissionPlanner
from fleet_manager.rollback import should_rollback, trigger_rollback
from fleet_manager.settings import FleetManagerSettings

if TYPE_CHECKING:
    from structlog.stdlib import BoundLogger

APPROACH_POINT_RADIUS = 1.5


def _near_approach_point(pose: dict[str, float], aisle: str) -> tuple[bool, str]:
    """Check if a robot pose is within APPROACH_POINT_RADIUS of a known approach-point.

    Returns (is_near, aisle_id). Hard-coded for Phase-1 topology; Phase-2 loads
    from warehouse-topology.yaml at startup.
    """
    x = pose.get("x", 0.0)
    y = pose.get("y", 0.0)
    ap_coords = {
        "aisle-3": (-16.82, 5.8),
    }
    for aisle_id, (ax, ay) in ap_coords.items():
        if ((x - ax) ** 2 + (y - ay) ** 2) ** 0.5 <= APPROACH_POINT_RADIUS:
            return True, aisle_id
    return False, ""


def _emit(producer: JsonProducer, topic: str, mission: FleetMission, log: "BoundLogger") -> None:
    producer.send(topic, key=mission.robot_id, value=mission)
    producer.flush(timeout=2.0)
    log.info(
        "mission.emitted",
        mission_id=str(mission.mission_id),
        robot_id=mission.robot_id,
        kind=mission.kind,
    )


async def _consume_missions(
    consumer: JsonConsumer[FleetMission],
    planner: MissionPlanner,
    log: "BoundLogger",
) -> None:
    """Consume DISPATCH missions from wms-stub and register them in the planner."""
    loop = asyncio.get_running_loop()
    while True:
        mission = await loop.run_in_executor(None, consumer.poll, 1.0)
        if mission is None:
            await asyncio.sleep(0)
            continue
        if mission.kind == MissionKind.DISPATCH:
            planner.dispatch(mission, log)
        consumer.commit()


async def _consume_alerts(
    consumer: JsonConsumer[SafetyAlert],
    producer: JsonProducer,
    planner: MissionPlanner,
    missions_topic: str,
    log: "BoundLogger",
) -> None:
    """Consume SafetyAlerts and trigger replan or clearance release."""
    loop = asyncio.get_running_loop()
    while True:
        alert = await loop.run_in_executor(None, consumer.poll, 1.0)
        if alert is None:
            await asyncio.sleep(0)
            continue
        log.info(
            "alert.received",
            alert_id=str(alert.alert_id),
            aisle=alert.aisle_id,
            obstructed=alert.obstructed,
        )
        result = planner.handle_alert(alert, log)
        if result is not None:
            _emit(producer, missions_topic, result, log)
        consumer.commit()


async def _consume_telemetry(
    consumer: JsonConsumer[FleetTelemetry],
    producer: JsonProducer,
    planner: MissionPlanner,
    missions_topic: str,
    log: "BoundLogger",
) -> None:
    """Consume telemetry: approach-point clearance + anomaly-triggered rollback."""
    loop = asyncio.get_running_loop()
    while True:
        telem = await loop.run_in_executor(None, consumer.poll, 1.0)
        if telem is None:
            await asyncio.sleep(0)
            continue

        if should_rollback(telem.anomaly_score):
            await trigger_rollback(
                factory="factory-a",
                robot_id=telem.robot_id,
                anomaly_score=telem.anomaly_score,
                trace_id=telem.trace_id,
                log=log,
            )

        near, aisle_id = _near_approach_point(telem.pose, telem.robot_id)
        if near:
            result = planner.robot_at_approach_point(telem.robot_id, aisle_id, log)
            if result is not None:
                _emit(producer, missions_topic, result, log)
        consumer.commit()


async def _consume_events(
    consumer: JsonConsumer[FleetEvent],
    planner: MissionPlanner,
    log: "BoundLogger",
) -> None:
    """Consume fleet lifecycle events that reset in-memory planner state."""
    loop = asyncio.get_running_loop()
    while True:
        event = await loop.run_in_executor(None, consumer.poll, 1.0)
        if event is None:
            await asyncio.sleep(0)
            continue
        if event.event_class == EventClass.DEMO_RESET:
            planner.reset(log)
            log.info(
                "demo.reset.received",
                event_id=str(event.event_id),
                trace_id=event.trace_id,
                source=event.source,
            )
        consumer.commit()


async def _consume_mes_orders(
    consumer: JsonConsumer[MesOrder],
    producer: JsonProducer,
    planner: MissionPlanner,
    missions_topic: str,
    policy_version: str,
    log: "BoundLogger",
) -> None:
    """Consume MES orders and translate them into DISPATCH missions."""
    loop = asyncio.get_running_loop()
    while True:
        order = await loop.run_in_executor(None, consumer.poll, 1.0)
        if order is None:
            await asyncio.sleep(0)
            continue
        log.info(
            "mes_order.received",
            order_id=str(order.order_id),
            material=order.material,
            factory=order.factory,
        )
        mission = planner.handle_mes_order(order, policy_version, log)
        if mission is not None:
            _emit(producer, missions_topic, mission, log)
        consumer.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = FleetManagerSettings()
    log = configure_logging(settings.service_name, settings.log_level)
    log.info("startup", version=__version__, environment=settings.environment)

    producer = JsonProducer(settings.kafka_bootstrap_servers, client_id=settings.service_name)
    planner = MissionPlanner()

    missions_consumer = JsonConsumer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=f"{settings.consumer_group_id}-missions",
        topic=settings.missions_topic,
        model=FleetMission,
    )
    alerts_consumer = JsonConsumer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=f"{settings.consumer_group_id}-alerts",
        topic=settings.alerts_topic,
        model=SafetyAlert,
    )
    telemetry_consumer = JsonConsumer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=f"{settings.consumer_group_id}-telemetry",
        topic=settings.telemetry_topic,
        model=FleetTelemetry,
    )
    events_consumer = JsonConsumer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=f"{settings.consumer_group_id}-events",
        topic=settings.events_topic,
        model=FleetEvent,
    )
    mes_consumer = JsonConsumer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=f"{settings.consumer_group_id}-mes",
        topic=settings.mes_orders_topic,
        model=MesOrder,
    )

    app.state.settings = settings
    app.state.log = log
    app.state.planner = planner

    tasks = [
        asyncio.create_task(_consume_missions(missions_consumer, planner, log)),
        asyncio.create_task(
            _consume_alerts(alerts_consumer, producer, planner, settings.missions_topic, log)
        ),
        asyncio.create_task(
            _consume_telemetry(telemetry_consumer, producer, planner, settings.missions_topic, log)
        ),
        asyncio.create_task(_consume_events(events_consumer, planner, log)),
        asyncio.create_task(
            _consume_mes_orders(
                mes_consumer, producer, planner, settings.missions_topic,
                settings.policy_version, log,
            )
        ),
    ]
    try:
        yield
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        missions_consumer.close()
        alerts_consumer.close()
        telemetry_consumer.close()
        events_consumer.close()
        mes_consumer.close()
        producer.flush(timeout=5.0)
        log.info("shutdown")


app = FastAPI(title="fleet-manager", version=__version__, lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    return {"status": "ready"}
