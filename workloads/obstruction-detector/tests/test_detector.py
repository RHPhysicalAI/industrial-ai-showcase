# This project was developed with assistance from AI tools.
"""Unit tests for the debounce state machine and frame-state precedence."""

from unittest.mock import Mock

from obstruction_detector.debounce import DebounceState
from obstruction_detector.state import effective_obstruction


def test_dwell_2_fires_after_two_consecutive():
    s = DebounceState(dwell_frames=2)
    assert s.observe(True) is False  # first obstructed frame — no fire yet
    assert s.observe(True) is True  # second — fire
    assert s.obstructed is True


def test_single_transient_does_not_flip():
    s = DebounceState(dwell_frames=2)
    s.observe(True)
    s.observe(True)  # established as obstructed
    assert s.observe(False) is False  # single clear frame — no flip
    assert s.observe(True) is False  # back to obstructed — state unchanged
    assert s.obstructed is True


def test_stable_transition_back_to_clear():
    s = DebounceState(dwell_frames=2)
    s.observe(True)
    s.observe(True)  # obstructed
    assert s.observe(False) is False  # pending clear #1
    assert s.observe(False) is True  # pending clear #2 → flip
    assert s.obstructed is False


def test_dwell_1_fires_immediately():
    s = DebounceState(dwell_frames=1)
    assert s.observe(True) is True
    assert s.observe(True) is False  # already set; no re-emit


def test_initial_clear_state_does_not_fire_on_first_clear_frames():
    s = DebounceState(dwell_frames=2)
    assert s.observe(False) is False  # initial: unknown → clear pending
    assert s.observe(False) is True  # established as clear
    assert s.obstructed is False


def test_alternating_never_fires():
    s = DebounceState(dwell_frames=3)
    for _ in range(10):
        assert s.observe(True) is False
        assert s.observe(False) is False
    assert s.obstructed is None


def test_scripted_obstructed_frame_overrides_false_vlm_verdict() -> None:
    assert effective_obstruction("obstructed", False, "trace", Mock()) is True


def test_live_frame_state_uses_vlm_verdict() -> None:
    assert effective_obstruction("live", True, "trace", Mock()) is True
