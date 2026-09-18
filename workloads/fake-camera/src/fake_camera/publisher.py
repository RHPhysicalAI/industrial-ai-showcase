# This project was developed with assistance from AI tools.
"""Publish loop — emits the currently-selected frame to Kafka at `publish_hz`.

State is a single string keyed off `FakeCameraSettings.frame_map_json`. The
HTTP `/state` endpoint mutates `StateHolder.current`; this loop reads it on
each tick. No locks needed — single writer (HTTP handler thread), single
reader (publish task), primitive string type is atomic enough for the demo.
"""

from __future__ import annotations

import asyncio
import base64
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from common_lib.events import CameraCommand, CameraFrameEvent
from common_lib.kafka import JsonConsumer, JsonProducer

if TYPE_CHECKING:
    from structlog.stdlib import BoundLogger

    from fake_camera.settings import FakeCameraSettings


@dataclass
class StateHolder:
    """Thread-safe-enough current-state reference for the publish loop."""

    current: str


def command_consumer_loop(
    settings: "FakeCameraSettings",
    frames: dict[str, bytes],
    state: StateHolder,
    extra_config: dict[str, str | int | bool],
    log: "BoundLogger",
) -> None:
    """Blocking loop — run in a daemon thread. Consumes CameraCommand from Kafka."""
    consumer = JsonConsumer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        # Commands are edge-triggered demo controls. A fresh process group
        # prevents a restart from replaying retained Reset/Drop commands and
        # oscillating the camera between historical states.
        group_id=f"{settings.service_name}-cmd-{uuid.uuid4().hex[:8]}",
        topic=settings.command_topic,
        model=CameraCommand,
        auto_offset_reset="latest",
        extra_config=extra_config,
    )
    log.info("command_consumer.started", topic=settings.command_topic)
    try:
        for cmd in consumer.iter(timeout=1.0):
            if cmd.state not in frames:
                log.warning("command_consumer.unknown_state", state=cmd.state, known=list(frames.keys()))
                continue
            previous = state.current
            state.current = cmd.state
            log.info("command_consumer.state_changed", from_=previous, to=cmd.state, trace_id=cmd.trace_id)
            consumer.commit()
    finally:
        consumer.close()


async def publish_loop(
    settings: "FakeCameraSettings",
    frames: dict[str, bytes],
    state: StateHolder,
    producer: JsonProducer,
    log: "BoundLogger",
) -> None:
    interval = 1.0 / settings.publish_hz
    while True:
        name = state.current
        jpeg = frames.get(name)
        if jpeg is None:
            log.warning("frame.missing", state=name, known=list(frames.keys()))
            await asyncio.sleep(interval)
            continue
        event = CameraFrameEvent(
            trace_id=str(uuid.uuid4()),
            camera_id=settings.camera_id,
            aisle_id=settings.aisle_id,
            state=name,
            frame_b64=base64.b64encode(jpeg).decode("ascii"),
        )
        producer.send(settings.topic, key=settings.camera_id, value=event)
        # Non-blocking flush — let librdkafka's background thread do the work.
        producer.flush(timeout=0.0)
        log.debug("frame.sent", state=name, bytes=len(jpeg))
        await asyncio.sleep(interval)
