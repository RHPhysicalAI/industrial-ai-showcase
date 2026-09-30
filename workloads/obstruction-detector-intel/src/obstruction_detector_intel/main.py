# This project was developed with assistance from AI tools.
"""obstruction-detector-intel entrypoint.

FastAPI app just for `/healthz` and `/readyz` (K8s probes); the actual work
runs in an asyncio task that consumes camera frames, calls YOLOv8 via KServe,
and publishes `SafetyAlert` events to Kafka on state change.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from common_lib.events import CameraFrameEvent
from common_lib.kafka import JsonConsumer, JsonProducer
from common_lib.logging import configure_logging
from fastapi import FastAPI

from obstruction_detector_intel import __version__
from obstruction_detector_intel.detector import run
from obstruction_detector_intel.settings import ObstructionDetectorSettings
from obstruction_detector_intel.yolo_client import YoloClient


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = ObstructionDetectorSettings()
    log = configure_logging(settings.service_name, settings.log_level)
    log.info(
        "startup",
        version=__version__,
        frames_topic=settings.frames_topic,
        alerts_topic=settings.alerts_topic,
        yolo_endpoint=settings.yolo_endpoint_url,
        aisle=settings.aisle_id,
    )

    consumer = JsonConsumer[CameraFrameEvent](
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.consumer_group,
        topic=settings.frames_topic,
        model=CameraFrameEvent,
    )
    producer = JsonProducer(settings.kafka_bootstrap_servers, client_id=settings.service_name)
    yolo = YoloClient(
        endpoint_url=settings.yolo_endpoint_url,
        timeout_s=settings.yolo_request_timeout_s,
    )

    task = asyncio.create_task(run(settings, consumer, producer, yolo, log))
    app.state.settings = settings
    app.state.log = log
    app.state.task = task

    try:
        yield
    finally:
        task.cancel()
        # CancelledError is a BaseException, so it needs listing alongside
        # Exception rather than being covered by it.
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task
        consumer.close()
        producer.flush(timeout=5.0)
        await yolo.aclose()
        log.info("shutdown")


app = FastAPI(title="obstruction-detector-intel", version=__version__, lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    task = getattr(app.state, "task", None)
    if task is None or task.done():
        return {"status": "not-ready"}
    return {"status": "ready"}