# This project was developed with assistance from AI tools.
"""Tests for the waypoint planner module."""

import asyncio
from unittest.mock import MagicMock
from uuid import uuid4

import structlog

from mission_dispatcher.waypoint_planner import (
    COORDS,
    RouteExecution,
    Waypoint,
    _build_waypoints,
    execute_route,
    plan_route,
)

log = structlog.get_logger()


def test_build_waypoints_aisle_3_has_approach_point() -> None:
    """Route through aisle-3 includes an approach-point waypoint."""
    wps = _build_waypoints("aisle-3", speed_mps=2.0, hz=5.0)
    approach = [wp for wp in wps if wp.is_approach_point]
    assert len(approach) == 1
    assert approach[0].name == "aisle-3-west"


def test_build_waypoints_aisle_4_has_approach_point() -> None:
    """Route through aisle-4 includes an approach-point waypoint."""
    wps = _build_waypoints("aisle-4", speed_mps=2.0, hz=5.0)
    approach = [wp for wp in wps if wp.is_approach_point]
    assert len(approach) == 1
    assert approach[0].name == "aisle-4-west"


def test_build_waypoints_starts_at_dock_a() -> None:
    """First waypoint is at dock-a coordinates."""
    wps = _build_waypoints("aisle-3", speed_mps=2.0, hz=5.0)
    assert wps[0].x == COORDS["dock-a"][0]
    assert wps[0].y == COORDS["dock-a"][1]


def test_build_waypoints_ends_at_dock_b() -> None:
    """Last waypoint is at dock-b coordinates."""
    wps = _build_waypoints("aisle-3", speed_mps=2.0, hz=5.0)
    assert wps[-1].x == COORDS["dock-b"][0]
    assert wps[-1].y == COORDS["dock-b"][1]


def test_plan_route_creates_execution() -> None:
    """plan_route returns a RouteExecution with correct metadata."""
    ex = plan_route("fl-07", "t1", "m1", "aisle-3")
    assert ex.robot_id == "fl-07"
    assert ex.route_name == "aisle-3"
    assert len(ex.waypoints) > 0
    assert ex.index == 0
    assert not ex.paused


def test_route_execution_cancel() -> None:
    """Cancelling a route execution sets the flag and unblocks the event."""
    ex = plan_route("fl-07", "t1", "m1", "aisle-3")
    ex.cancel()
    assert ex.cancelled
    assert ex.clearance_event.is_set()


def test_route_execution_grant_clearance() -> None:
    """Granting clearance unblocks the approach-point wait."""
    ex = plan_route("fl-07", "t1", "m1", "aisle-3")
    ex.paused = True
    ex.grant_clearance()
    assert not ex.paused
    assert ex.clearance_event.is_set()


def test_route_arms_clearance_before_approach_telemetry() -> None:
    """Immediate PROCEED responses cannot race the approach-point pause."""
    execution = RouteExecution(
        robot_id="fl-07",
        trace_id="t1",
        mission_id=str(uuid4()),
        route_name="aisle-3",
        waypoints=[
            Waypoint(x=-22.82, y=5.8, z=0.0),
            Waypoint(x=-16.82, y=5.8, z=0.0, is_approach_point=True, name="approach"),
            Waypoint(x=4.18, y=5.8, z=0.0),
        ],
    )

    class ImmediateClearanceProducer:
        saw_paused = False

        def send(self, _topic: str, *, key: str, value: object) -> None:
            if execution.waypoints[execution.index].is_approach_point:
                self.saw_paused = execution.paused
                execution.grant_clearance()

        def flush(self, *, timeout: float = 0.0) -> None:
            pass

    producer = ImmediateClearanceProducer()
    completed = asyncio.run(
        asyncio.wait_for(
            execute_route(execution, producer, "fleet.telemetry", 100.0, "v1", log),
            timeout=1.0,
        )
    )

    assert completed
    assert producer.saw_paused


def test_route_preserves_clearance_granted_before_approach_wait() -> None:
    """A valid early PROCEED remains latched until the approach-point wait."""
    execution = RouteExecution(
        robot_id="fl-07",
        trace_id="t1",
        mission_id=str(uuid4()),
        route_name="aisle-3",
        waypoints=[
            Waypoint(x=-22.82, y=5.8, z=0.0),
            Waypoint(x=-16.82, y=5.8, z=0.0, is_approach_point=True, name="approach"),
            Waypoint(x=4.18, y=5.8, z=0.0),
        ],
    )
    execution.grant_clearance()

    completed = asyncio.run(
        asyncio.wait_for(
            execute_route(execution, MagicMock(), "fleet.telemetry", 100.0, "v1", log),
            timeout=1.0,
        )
    )

    assert completed
