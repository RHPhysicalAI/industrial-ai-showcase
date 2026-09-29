import numpy as np
import pytest

from openvla_server.action_contract import (
    LEGACY_ACTION_DIM,
    TELEOP_G1_ACTION_DIM,
    TELEOP_G1_ACTION_HORIZON,
    TELEOP_G1_ACTION_KEYS,
    legacy_7_value_compatibility_projection,
    validate_teleop_g1_action_chunk,
)


def _valid_action_chunk() -> dict[str, np.ndarray]:
    widths = (6, 6, 3, 7, 7, 7, 7)
    return {
        key: np.zeros((1, TELEOP_G1_ACTION_HORIZON, width), dtype=np.float32)
        for key, width in zip(TELEOP_G1_ACTION_KEYS, widths, strict=True)
    }


def test_teleop_g1_contract_is_43_dof_and_16_steps() -> None:
    chunk = _valid_action_chunk()

    validate_teleop_g1_action_chunk(chunk)

    assert sum(values.shape[-1] for values in chunk.values()) == TELEOP_G1_ACTION_DIM


def test_teleop_g1_contract_rejects_legacy_or_wrong_keys() -> None:
    chunk = _valid_action_chunk()
    chunk.pop("left_leg")
    chunk["ego_view"] = np.zeros((1, TELEOP_G1_ACTION_HORIZON, 6), dtype=np.float32)

    with pytest.raises(ValueError, match="action keys"):
        validate_teleop_g1_action_chunk(chunk)


def test_legacy_projection_is_explicitly_only_a_shape_compatibility() -> None:
    action = list(range(TELEOP_G1_ACTION_DIM))

    projected = legacy_7_value_compatibility_projection(action)

    assert len(projected) == LEGACY_ACTION_DIM
    assert projected == action[:LEGACY_ACTION_DIM]
