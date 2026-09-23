# This project was developed with assistance from AI tools.
"""State precedence for deterministic and live camera frames."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from structlog.stdlib import BoundLogger


def effective_obstruction(
    frame_state: str,
    model_obstructed: bool,
    trace_id: str,
    log: "BoundLogger",
) -> bool:
    """Use scripted camera state when present; otherwise trust the VLM verdict.

    Fake-camera carries its selected logical state in the frame envelope. That
    state is authoritative for the deterministic demo: Cosmos still runs and
    is logged, but a model disagreement must not emit a false clear event that
    immediately undoes the scripted pallet transition. Live/unknown states
    continue to use the VLM result.
    """
    scripted_state = frame_state.strip().lower()
    if scripted_state in {"empty", "obstructed"}:
        obstructed = scripted_state == "obstructed"
        if obstructed != model_obstructed:
            log.warning(
                "frame.state_overrode_model",
                trace_id=trace_id,
                frame_state=scripted_state,
                model_obstructed=model_obstructed,
            )
        return obstructed
    return model_obstructed
