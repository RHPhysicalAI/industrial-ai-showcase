# This project was developed with assistance from AI tools.
"""Mission planner — tracks active missions and handles approach-point clearance / replan.

State machine per robot:

  IDLE → DISPATCHED → AWAITING_CLEARANCE → IN_AISLE → COMPLETED
                          │
                          └─ (obstruction alert) → emits REROUTE → DISPATCHED (new route)

The fleet-manager runs this planner on the hub. It consumes:
  - fleet.missions (DISPATCH from wms-stub)
  - fleet.safety.alerts (SafetyAlert from obstruction-detector)
  - fleet.telemetry (FleetTelemetry from mission-dispatcher — approach-point arrival)

It emits:
  - fleet.missions (PROCEED / REROUTE to mission-dispatcher)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from common_lib.events import FleetMission, MesOrder, MissionKind, SafetyAlert

if TYPE_CHECKING:
    from structlog.stdlib import BoundLogger


class Phase(str, Enum):
    IDLE = "idle"
    DISPATCHED = "dispatched"
    AWAITING_CLEARANCE = "awaiting_clearance"
    IN_AISLE = "in_aisle"
    COMPLETED = "completed"


@dataclass
class ActiveMission:
    mission: FleetMission
    route_aisle: str
    alternate_aisle: str
    phase: Phase = Phase.DISPATCHED


@dataclass
class MissionPlanner:
    """In-memory planner tracking one robot's active mission."""

    robots: dict[str, ActiveMission] = field(default_factory=dict)
    obstructed_aisles: set[str] = field(default_factory=set)

    def dispatch(self, mission: FleetMission, log: BoundLogger) -> None:
        """Register a new DISPATCH mission from wms-stub."""
        route = str(mission.params.get("route_aisle", "aisle-3"))
        alt = str(mission.params.get("alternate_aisle", "aisle-4"))
        self.robots[mission.robot_id] = ActiveMission(
            mission=mission, route_aisle=route, alternate_aisle=alt,
        )
        log.info(
            "mission.tracked",
            robot_id=mission.robot_id,
            route=route,
            alternate=alt,
        )

    def handle_mes_order(
        self, order: MesOrder, policy_version: str, log: BoundLogger,
    ) -> FleetMission | None:
        """Translate an MES production order into a DISPATCH mission.

        Assigns the order to the least-busy robot or a default robot for the
        target factory. Returns a DISPATCH FleetMission ready for emission.
        """
        robot_id = self._pick_robot_for_factory(order.factory)
        mission = FleetMission(
            trace_id=order.trace_id,
            kind=MissionKind.DISPATCH,
            robot_id=robot_id,
            policy_version=policy_version,
            params={
                "source": "mes",
                "order_id": str(order.order_id),
                "material": order.material,
                "quantity": order.quantity,
                "route_aisle": order.source_location,
                "alternate_aisle": order.destination_location,
                "destination": order.destination_location,
                "priority": order.priority.value,
            },
        )
        self.dispatch(mission, log)
        log.info(
            "mes_order.dispatched",
            order_id=str(order.order_id),
            robot_id=robot_id,
            material=order.material,
        )
        return mission

    def _pick_robot_for_factory(self, factory: str) -> str:
        """Return a robot ID for the given factory. Phase 2: static mapping."""
        factory_robots = {
            "factory-a": "fl-07",
            "factory-b": "fl-08",
        }
        return factory_robots.get(factory, "fl-07")

    def robot_at_approach_point(
        self, robot_id: str, aisle_id: str, log: BoundLogger,
    ) -> FleetMission | None:
        """Called when telemetry shows a robot has reached an approach-point.

        Returns a PROCEED mission if the aisle is clear, otherwise holds
        in AWAITING_CLEARANCE (replan will fire when the alert arrives).
        """
        active = self.robots.get(robot_id)
        if active is None:
            return None

        active.phase = Phase.AWAITING_CLEARANCE

        # AUTO-CLEARANCE: If the aisle is not obstructed, immediately grant PROCEED
        if active.route_aisle not in self.obstructed_aisles:
            log.info(
                "clearance.auto_granted",
                robot_id=robot_id,
                aisle=aisle_id,
                reason="aisle_not_obstructed"
            )
            return self._proceed(active, log)

        # Otherwise, wait for obstruction alert to clear
        log.info(
            "clearance.requested",
            robot_id=robot_id,
            aisle=aisle_id,
            obstructed=True
        )
        return None

    def handle_alert(
        self, alert: SafetyAlert, log: BoundLogger,
    ) -> FleetMission | None:
        """Process a SafetyAlert — replan any robot awaiting clearance on the affected aisle."""
        if alert.obstructed:
            self.obstructed_aisles.add(alert.aisle_id)
            return self._try_reroute(alert, log)

        # Only release clearance if we previously saw this aisle obstructed;
        # stale clear-alerts from prior test cycles must not trigger PROCEED.
        if alert.aisle_id not in self.obstructed_aisles:
            log.debug("alert.ignored_stale_clear", aisle=alert.aisle_id)
            return None
        self.obstructed_aisles.discard(alert.aisle_id)
        return self._try_release_clearance(alert.aisle_id, log)

    def _try_reroute(
        self, alert: SafetyAlert, log: BoundLogger,
    ) -> FleetMission | None:
        for robot_id, active in self.robots.items():
            if (
                active.phase == Phase.AWAITING_CLEARANCE
                and active.route_aisle == alert.aisle_id
            ):
                log.info(
                    "replan.triggered",
                    robot_id=robot_id,
                    obstructed_aisle=alert.aisle_id,
                    reroute_aisle=active.alternate_aisle,
                )
                reroute = FleetMission(
                    trace_id=alert.trace_id,
                    kind=MissionKind.REROUTE,
                    robot_id=robot_id,
                    triggered_by_event_id=alert.alert_id,
                    policy_version=active.mission.policy_version,
                    params={
                        "reason": "aisle-obstruction",
                        "obstructed_aisle": alert.aisle_id,
                        "route_aisle": active.alternate_aisle,
                        "alternate_aisle": active.route_aisle,
                        "destination": str(active.mission.params.get("destination", "")),
                    },
                )
                active.route_aisle, active.alternate_aisle = (
                    active.alternate_aisle, active.route_aisle,
                )
                active.phase = Phase.DISPATCHED
                return reroute
        return None

    def _try_release_clearance(
        self, aisle_id: str, log: BoundLogger,
    ) -> FleetMission | None:
        for robot_id, active in self.robots.items():
            if (
                active.phase == Phase.AWAITING_CLEARANCE
                and active.route_aisle == aisle_id
            ):
                return self._proceed(active, log)
        return None

    def _proceed(self, active: ActiveMission, log: BoundLogger) -> FleetMission:
        active.phase = Phase.IN_AISLE
        log.info("clearance.granted", robot_id=active.mission.robot_id, aisle=active.route_aisle)
        return FleetMission(
            trace_id=active.mission.trace_id,
            kind=MissionKind.PROCEED,
            robot_id=active.mission.robot_id,
            policy_version=active.mission.policy_version,
            params={
                "aisle": active.route_aisle,
                "destination": str(active.mission.params.get("destination", "")),
            },
        )

    def mission_completed(self, robot_id: str, log: BoundLogger) -> None:
        if robot_id in self.robots:
            self.robots[robot_id].phase = Phase.COMPLETED
            del self.robots[robot_id]
            log.info("mission.completed", robot_id=robot_id)
