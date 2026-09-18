# This project was developed with assistance from AI tools.
"""Core detector loop: consume camera frames → Cosmos Reason → emit alerts."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from common_lib.events import CameraFrameEvent, SafetyAlert
from common_lib.kafka import JsonConsumer, JsonProducer

from obstruction_detector.cosmos_client import CosmosClient, ObstructionVerdict
from obstruction_detector.debounce import DebounceState
from obstruction_detector.state import effective_obstruction

if TYPE_CHECKING:
    from structlog.stdlib import BoundLogger

    from obstruction_detector.settings import ObstructionDetectorSettings


async def run(
    settings: "ObstructionDetectorSettings",
    consumer: JsonConsumer[CameraFrameEvent],
    producer: JsonProducer,
    cosmos: CosmosClient,
    log: "BoundLogger",
) -> None:
    state = DebounceState(dwell_frames=settings.dwell_frames)

    loop = asyncio.get_running_loop()

    await loop.run_in_executor(None, consumer.seek_to_end)
    log.info("consumer.seeked_to_end")

    while True:
        frame = await loop.run_in_executor(None, consumer.poll, 1.0)
        if frame is None:
            continue

        try:
            verdict = await cosmos.reason(frame.frame_b64, settings.default_prompt)
        except Exception as exc:
            log.exception(
                "cosmos.call.failed",
                trace_id=frame.trace_id,
                camera_id=frame.camera_id,
                error=str(exc),
            )
            consumer.commit()
            continue

        obstructed = effective_obstruction(frame.state, verdict.obstruction, frame.trace_id, log)
        log.info(
            "frame.reasoned",
            trace_id=frame.trace_id,
            camera_id=frame.camera_id,
            obstructed=obstructed,
            model_obstructed=verdict.obstruction,
            frame_state=frame.state,
            confidence=round(verdict.confidence, 3),
            label=verdict.label,
        )

        if state.observe(obstructed):
            _emit_alert(frame, verdict, obstructed, producer, settings, log)

        consumer.commit()


def _emit_alert(
    frame: CameraFrameEvent,
    verdict: ObstructionVerdict,
    obstructed: bool,
    producer: JsonProducer,
    settings: "ObstructionDetectorSettings",
    log: "BoundLogger",
) -> None:
    alert = SafetyAlert(
        trace_id=frame.trace_id,
        aisle_id=frame.aisle_id,
        camera_id=frame.camera_id,
        detection_label=verdict.label or ("obstruction" if obstructed else "clear"),
        confidence=verdict.confidence,
        source_model=settings.cosmos_model,
        obstructed=obstructed,
        detail=verdict.detail,
    )
    producer.send(settings.alerts_topic, key=alert.aisle_id, value=alert)
    producer.flush(timeout=2.0)
    log.info(
        "alert.emitted",
        alert_id=str(alert.alert_id),
        aisle_id=alert.aisle_id,
        obstructed=alert.obstructed,
        confidence=alert.confidence,
        label=alert.detection_label,
    )
