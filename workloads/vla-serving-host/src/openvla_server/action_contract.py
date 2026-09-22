# This project was developed with assistance from AI tools.
"""Action-space contracts shared by the GR00T adapter and its tests.

The trained Teleop-G1 policy emits a 43-DOF, 16-step action chunk.  The
existing Mission Dispatcher HTTP API still exposes a legacy seven-value list.
These are different contracts; this module validates the trained contract and
keeps the compatibility boundary explicit instead of silently treating the
first seven values as a robot-safe Cartesian action.
"""

from collections.abc import Mapping
from typing import Any

import numpy as np

TELEOP_G1_ACTION_DIMS: dict[str, int] = {
    "left_leg": 6,
    "right_leg": 6,
    "waist": 3,
    "left_arm": 7,
    "left_hand": 7,
    "right_arm": 7,
    "right_hand": 7,
}
TELEOP_G1_ACTION_KEYS = tuple(TELEOP_G1_ACTION_DIMS)
TELEOP_G1_ACTION_DIM = sum(TELEOP_G1_ACTION_DIMS.values())
TELEOP_G1_ACTION_HORIZON = 16
LEGACY_ACTION_DIM = 7


def validate_teleop_g1_action_chunk(action_chunk: Mapping[str, Any]) -> None:
    """Validate the shape and keys emitted by the trained Teleop-G1 policy.

    GR00T may return each modality as ``(batch, horizon, width)`` or a shape
    with equivalent leading dimensions.  Only the final dimension is fixed;
    all modalities must share the same horizon.
    """

    actual_keys = tuple(action_chunk)
    expected_keys = TELEOP_G1_ACTION_KEYS
    missing = [key for key in expected_keys if key not in action_chunk]
    unexpected = [key for key in actual_keys if key not in expected_keys]
    if missing or unexpected:
        raise ValueError(
            "Teleop-G1 action keys do not match the training contract: "
            f"missing={missing or []}, unexpected={unexpected or []}"
        )

    horizons: set[int] = set()
    for key, width in TELEOP_G1_ACTION_DIMS.items():
        values = np.asarray(action_chunk[key])
        if values.ndim == 0 or values.shape[-1] != width:
            raise ValueError(
                f"Teleop-G1 action key {key!r} has shape {values.shape}; "
                f"expected a final dimension of {width}"
            )
        horizons.add(int(np.prod(values.shape[:-1])))

    if len(horizons) != 1:
        raise ValueError(f"Teleop-G1 action modalities have inconsistent horizons: {sorted(horizons)}")


def legacy_7_value_compatibility_projection(action: list[float]) -> list[float]:
    """Preserve the legacy HTTP shape without implying a semantic mapping.

    This is intentionally only a compatibility projection.  The first seven
    values of a 43-DOF joint action are not a validated ``dx,dy,dz,...`` robot
    command and must not be promoted to live control without a real mapping.
    """

    return action[:LEGACY_ACTION_DIM] if len(action) >= LEGACY_ACTION_DIM else action
