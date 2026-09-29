# This project was developed with assistance from AI tools.
"""Deterministic scene-state events used by the scripted WMS demo actions."""

from common_lib.events import SafetyAlert
from wms_stub.settings import WmsStubSettings


def build_scene_alert(
    settings: WmsStubSettings,
    trace_id: str,
    target_state: str,
) -> SafetyAlert | None:
    """Build the twin/Fleet Manager transition for a supported scripted state."""
    if target_state not in {"empty", "obstructed"}:
        return None
    return SafetyAlert(
        trace_id=trace_id,
        aisle_id=settings.camera_aisle_id,
        camera_id=settings.camera_id,
        detection_label="pallet" if target_state == "obstructed" else "scene-clear",
        confidence=1.0,
        source_model="wms-stub",
        obstructed=target_state == "obstructed",
        detail=f"explicit demo camera state: {target_state}",
    )
