# This project was developed with assistance from AI tools.
"""Core detector loop: consume camera frames → YOLOv8 → emit alerts."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from common_lib.events import CameraFrameEvent, SafetyAlert
from common_lib.kafka import JsonConsumer, JsonProducer

from obstruction_detector_intel.debounce import DebounceState
from obstruction_detector_intel.yolo_client import ObstructionVerdict, YoloClient

if TYPE_CHECKING:
    from structlog.stdlib import BoundLogger

    from obstruction_detector_intel.settings import ObstructionDetectorSettings


async def run(
    settings: ObstructionDetectorSettings,
    consumer: JsonConsumer[CameraFrameEvent],
    producer: JsonProducer,
    yolo: YoloClient,
    log: BoundLogger,
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
            verdict = await yolo.reason(frame.frame_b64)
        except Exception as exc:
            log.exception(
                "yolo.call.failed",
                trace_id=frame.trace_id,
                camera_id=frame.camera_id,
                error=str(exc),
            )
            consumer.commit()
            continue

        log.info(
            "frame.reasoned",
            trace_id=frame.trace_id,
            camera_id=frame.camera_id,
            obstructed=verdict.obstruction,
            confidence=round(verdict.confidence, 3),
            label=verdict.label,
        )

        if state.observe(verdict.obstruction):
            _emit_alert(frame, verdict, producer, settings, log)

        consumer.commit()


def _emit_alert(
    frame: CameraFrameEvent,
    verdict: ObstructionVerdict,
    producer: JsonProducer,
    settings: ObstructionDetectorSettings,
    log: BoundLogger,
) -> None:
    alert = SafetyAlert(
        trace_id=frame.trace_id,
        aisle_id=frame.aisle_id,
        camera_id=frame.camera_id,
        detection_label=verdict.label or ("obstruction" if verdict.obstruction else "clear"),
        confidence=verdict.confidence,
        source_model=settings.yolo_model,
        obstructed=verdict.obstruction,
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