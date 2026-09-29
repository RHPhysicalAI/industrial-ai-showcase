# This project was developed with assistance from AI tools.
"""Tests for MissionPlanner approach-point clearance and replan logic."""

import structlog

from common_lib.events import FleetMission, MissionKind, SafetyAlert
from fleet_manager.planner import MissionPlanner, Phase

log = structlog.get_logger()


def _dispatch_mission(planner: MissionPlanner) -> FleetMission:
    mission = FleetMission(
        trace_id="t1",
        kind=MissionKind.DISPATCH,
        robot_id="fl-07",
        policy_version="vla-warehouse-v1.3",
        params={
            "route_aisle": "aisle-3",
            "alternate_aisle": "aisle-4",
            "destination": "dock-b",
        },
    )
    planner.dispatch(mission, log)
    return mission


def test_dispatch_registers_mission() -> None:
    """Dispatching a mission registers the robot in the planner."""
    planner = MissionPlanner()
    _dispatch_mission(planner)
    assert "fl-07" in planner.robots
    assert planner.robots["fl-07"].phase == Phase.DISPATCHED


def test_approach_point_clears_when_aisle_unobstructed() -> None:
    """Robot at approach-point gets PROCEED when aisle is clear."""
    planner = MissionPlanner()
    _dispatch_mission(planner)
    result = planner.robot_at_approach_point("fl-07", "aisle-3", log)
    assert result is not None
    assert result.kind == MissionKind.PROCEED
    assert planner.robots["fl-07"].phase == Phase.IN_AISLE


def test_repeated_approach_telemetry_does_not_emit_duplicate_proceed() -> None:
    """Repeated telemetry near the approach-point is idempotent after PROCEED."""
    planner = MissionPlanner()
    _dispatch_mission(planner)

    first = planner.robot_at_approach_point("fl-07", "aisle-3", log)
    duplicate = planner.robot_at_approach_point("fl-07", "aisle-3", log)

    assert first is not None
    assert first.kind == MissionKind.PROCEED
    assert duplicate is None
    assert planner.robots["fl-07"].phase == Phase.IN_AISLE


def test_approach_point_holds_when_aisle_obstructed() -> None:
    """Robot at approach-point is held when aisle is obstructed."""
    planner = MissionPlanner()
    _dispatch_mission(planner)
    alert = SafetyAlert(
        trace_id="t2", aisle_id="aisle-3", camera_id="cam-aisle-3",
        detection_label="stacked boxes", confidence=0.98,
        source_model="cosmos-reason-2-8b", obstructed=True,
    )
    planner.handle_alert(alert, log)
    result = planner.robot_at_approach_point("fl-07", "aisle-3", log)
    assert result is None
    assert planner.robots["fl-07"].phase == Phase.AWAITING_CLEARANCE


def test_alert_triggers_reroute_during_clearance() -> None:
    """Obstruction alert while awaiting clearance triggers a REROUTE."""
    planner = MissionPlanner()
    _dispatch_mission(planner)
    planner.robot_at_approach_point("fl-07", "aisle-3", log)
    # Robot got PROCEED (aisle was clear), but let's test the replan path:
    # Reset to awaiting clearance
    planner.robots["fl-07"].phase = Phase.AWAITING_CLEARANCE

    alert = SafetyAlert(
        trace_id="t3", aisle_id="aisle-3", camera_id="cam-aisle-3",
        detection_label="stacked boxes", confidence=0.98,
        source_model="cosmos-reason-2-8b", obstructed=True,
    )
    result = planner.handle_alert(alert, log)
    assert result is not None
    assert result.kind == MissionKind.REROUTE
    assert result.params["route_aisle"] == "aisle-4"
    assert result.params["obstructed_aisle"] == "aisle-3"
    assert planner.robots["fl-07"].phase == Phase.DISPATCHED


def test_clear_alert_releases_held_robot() -> None:
    """A clear alert releases a robot held at approach-point."""
    planner = MissionPlanner()
    _dispatch_mission(planner)
    planner.obstructed_aisles.add("aisle-3")
    planner.robot_at_approach_point("fl-07", "aisle-3", log)
    assert planner.robots["fl-07"].phase == Phase.AWAITING_CLEARANCE

    clear = SafetyAlert(
        trace_id="t4", aisle_id="aisle-3", camera_id="cam-aisle-3",
        detection_label="aisle", confidence=0.98,
        source_model="cosmos-reason-2-8b", obstructed=False,
    )
    result = planner.handle_alert(clear, log)
    assert result is not None
    assert result.kind == MissionKind.PROCEED
    assert planner.robots["fl-07"].phase == Phase.IN_AISLE


def test_alert_on_unrelated_aisle_is_ignored() -> None:
    """Alert on aisle-4 doesn't affect robot awaiting clearance on aisle-3."""
    planner = MissionPlanner()
    _dispatch_mission(planner)
    planner.robots["fl-07"].phase = Phase.AWAITING_CLEARANCE

    alert = SafetyAlert(
        trace_id="t5", aisle_id="aisle-4", camera_id="cam-aisle-4",
        detection_label="stacked boxes", confidence=0.95,
        source_model="cosmos-reason-2-8b", obstructed=True,
    )
    result = planner.handle_alert(alert, log)
    assert result is None
    assert planner.robots["fl-07"].phase == Phase.AWAITING_CLEARANCE


def test_mission_completed_removes_robot() -> None:
    """Completing a mission removes the robot from tracking."""
    planner = MissionPlanner()
    _dispatch_mission(planner)
    planner.mission_completed("fl-07", log)
    assert "fl-07" not in planner.robots


def test_reset_clears_active_missions_and_obstructions() -> None:
    """An explicit demo reset clears all in-memory planner state."""
    planner = MissionPlanner()
    _dispatch_mission(planner)
    planner.obstructed_aisles.add("aisle-3")

    planner.reset(log)

    assert planner.robots == {}
    assert planner.obstructed_aisles == set()
