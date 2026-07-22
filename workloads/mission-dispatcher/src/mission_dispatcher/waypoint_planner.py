# This project was developed with assistance from AI tools.
"""Waypoint planner — interpolates poses along a route and emits telemetry.

Phase 1 topology is hard-coded from the warehouse scene layout. Phase 2
loads from warehouse-topology.yaml at startup.

Tick rate is configurable via WAYPOINT_HZ (default 5 Hz). Each tick publishes
a FleetTelemetry message with the current interpolated pose including yaw.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from common_lib.events import FleetTelemetry

if TYPE_CHECKING:
    from common_lib.kafka import JsonProducer
    from structlog.stdlib import BoundLogger

COORDS: dict[str, tuple[float, float, float, float]] = {
    "dock-a": (-22.82, 5.8, 0.0, 90.0),
    "aisle-3-approach": (-16.82, 5.8, 0.0, 90.0),
    "aisle-3-end": (-7.82, 5.8, 0.0, 90.0),
    "dock-b-3": (4.18, 5.8, 0.0, 90.0),
    "aisle-4-turn-in": (-7.82, 5.8, 0.0, 180.0),
    "aisle-4-end": (-7.82, 27.8, 0.0, 180.0),
    "aisle-4-turn-out": (-7.82, 27.8, 0.0, 90.0),
    "aisle-4-exit": (4.18, 27.8, 0.0, 90.0),
}

ROUTES: dict[str, list[str]] = {
    "aisle-3": ["dock-a", "aisle-3-approach", "aisle-3-end", "dock-b-3"],
    "aisle-4": [
        "aisle-3-approach", "aisle-3-end", "aisle-4-turn-in",
        "aisle-4-end", "aisle-4-turn-out", "aisle-4-exit",
    ],
}

APPROACH_POINTS = {"aisle-3-approach"}

ANGULAR_SPEED_DPS = 90.0


@dataclass
class Waypoint:
    x: float
    y: float
    z: float
    yaw: float = 0.0
    is_approach_point: bool = False
    name: str = ""


def _shortest_yaw_delta(start: float, end: float) -> float:
    delta = (end - start) % 360.0
    if delta > 180.0:
        delta -= 360.0
    return delta


def _build_waypoints(route_name: str, speed_mps: float, hz: float) -> list[Waypoint]:
    """Generate interpolated waypoints along a named route."""
    names = ROUTES.get(route_name, ROUTES["aisle-3"])
    waypoints: list[Waypoint] = []
    step_dist = speed_mps / hz
    step_angle = ANGULAR_SPEED_DPS / hz

    for i in range(len(names) - 1):
        sx, sy, sz, syaw = COORDS[names[i]]
        ex, ey, ez, eyaw = COORDS[names[i + 1]]
        dx, dy, dz = ex - sx, ey - sy, ez - sz
        seg_len = math.sqrt(dx * dx + dy * dy + dz * dz)
        dyaw = _shortest_yaw_delta(syaw, eyaw)

        dist_steps = max(1, int(seg_len / step_dist)) if seg_len > 0.01 else 1
        angle_steps = max(1, int(abs(dyaw) / step_angle)) if abs(dyaw) > 0.5 else 1
        steps = max(dist_steps, angle_steps)

        for s in range(steps):
            t = s / steps
            waypoints.append(Waypoint(
                x=sx + dx * t,
                y=sy + dy * t,
                z=sz + dz * t,
                yaw=syaw + dyaw * t,
                is_approach_point=(s == steps - 1 and names[i + 1] in APPROACH_POINTS),
                name=names[i + 1] if s == steps - 1 else "",
            ))

    fx, fy, fz, fyaw = COORDS[names[-1]]
    waypoints.append(Waypoint(x=fx, y=fy, z=fz, yaw=fyaw, name=names[-1]))
    return waypoints


@dataclass
class RouteExecution:
    """Manages the execution of a route with pause-at-approach-point semantics."""

    robot_id: str
    trace_id: str
    mission_id: str
    route_name: str
    waypoints: list[Waypoint]
    index: int = 0
    paused: bool = False
    cancelled: bool = False
    clearance_event: asyncio.Event = field(default_factory=asyncio.Event)

    def grant_clearance(self) -> None:
        self.paused = False
        self.clearance_event.set()

    def cancel(self) -> None:
        self.cancelled = True
        self.clearance_event.set()


async def execute_route(
    execution: RouteExecution,
    producer: JsonProducer,
    telemetry_topic: str,
    hz: float,
    policy_version: str,
    log: BoundLogger,
) -> bool:
    """Drive a robot along waypoints, pausing at approach-points.

    Returns True if the route completed, False if cancelled (e.g. reroute).
    """
    interval = 1.0 / hz
    log.info(
        "route.started",
        robot_id=execution.robot_id,
        route=execution.route_name,
        waypoints=len(execution.waypoints),
    )

    while execution.index < len(execution.waypoints):
        if execution.cancelled:
            log.info("route.cancelled", robot_id=execution.robot_id)
            return False

        wp = execution.waypoints[execution.index]

        producer.send(
            telemetry_topic,
            key=execution.robot_id,
            value=FleetTelemetry(
                trace_id=execution.trace_id,
                robot_id=execution.robot_id,
                mission_id=execution.mission_id,
                pose={"x": wp.x, "y": wp.y, "z": wp.z, "yaw": wp.yaw},
                policy_version=policy_version,
            ),
        )
        producer.flush(timeout=0.0)

        if wp.is_approach_point:
            execution.paused = True
            log.info(
                "route.approach_point",
                robot_id=execution.robot_id,
                waypoint=wp.name,
                x=wp.x, y=wp.y,
            )
            execution.clearance_event.clear()
            await execution.clearance_event.wait()
            if execution.cancelled:
                return False
            log.info("route.clearance_received", robot_id=execution.robot_id)

        execution.index += 1
        await asyncio.sleep(interval)

    log.info("route.completed", robot_id=execution.robot_id, route=execution.route_name)
    return True


def plan_route(
    robot_id: str,
    trace_id: str,
    mission_id: str,
    route_aisle: str,
    speed_mps: float = 2.0,
    hz: float = 5.0,
) -> RouteExecution:
    """Create a RouteExecution for a given aisle route."""
    waypoints = _build_waypoints(route_aisle, speed_mps, hz)
    return RouteExecution(
        robot_id=robot_id,
        trace_id=trace_id,
        mission_id=str(mission_id),
        route_name=route_aisle,
        waypoints=waypoints,
    )
