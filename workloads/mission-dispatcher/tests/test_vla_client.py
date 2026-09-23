# This project was developed with assistance from AI tools.
"""Tests for the VLA response boundary.

The dispatcher currently records the VLA result; it does not actuate a robot.
These tests protect the existing seven-value HTTP contract while the explicit
downstream command mapping is designed.
"""

import math

import pytest
from pydantic import ValidationError

from mission_dispatcher.vla_client import VlaAction


def _valid_action() -> dict[str, object]:
    return {
        "action": [0.0] * 7,
        "model_version": "groot-test",
        "trace_id": "trace-1",
    }


def test_vla_action_accepts_established_seven_value_contract() -> None:
    result = VlaAction.model_validate(_valid_action())

    assert len(result.action) == 7
    assert result.trace_id == "trace-1"


@pytest.mark.parametrize("count", [0, 6, 8])
def test_vla_action_rejects_wrong_action_width(count: int) -> None:
    payload = _valid_action()
    payload["action"] = [0.0] * count

    with pytest.raises(ValidationError):
        VlaAction.model_validate(payload)


def test_vla_action_rejects_non_finite_values() -> None:
    payload = _valid_action()
    payload["action"] = [0.0] * 6 + [math.nan]

    with pytest.raises(ValidationError):
        VlaAction.model_validate(payload)
