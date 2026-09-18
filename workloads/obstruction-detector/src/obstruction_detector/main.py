# This project was developed with assistance from AI tools.
"""obstruction-detector entrypoint.

FastAPI app just for `/healthz` and `/readyz` (K8s probes); the actual work
runs in an asyncio task that consumes camera frames, calls Cosmos Reason 2-8B,
and publishes `SafetyAlert` events to Kafka on state change.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

from common_lib.events import CameraFrameEvent
from common_lib.kafka import JsonConsumer, JsonProducer
from common_lib.logging import configure_logging
from fastapi import FastAPI

from obstruction_detector import __version__
from obstruction_detector.cosmos_client import CosmosClient
from obstruction_detector.detector import run
from obstruction_detector.settings import ObstructionDetectorSettings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = ObstructionDetectorSettings()
    log = configure_logging(settings.service_name, settings.log_level)
    log.info(
        "startup",
        version=__version__,
        frames_topic=settings.frames_topic,
        alerts_topic=settings.alerts_topic,
        cosmos=settings.cosmos_endpoint_url,
        aisle=settings.aisle_id,
    )

    consumer_group = f"{settings.consumer_group}-{uuid4().hex[:8]}"
    consumer = JsonConsumer[CameraFrameEvent](
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=consumer_group,
        topic=settings.frames_topic,
        model=CameraFrameEvent,
        auto_offset_reset="latest",
    )
    producer = JsonProducer(settings.kafka_bootstrap_servers, client_id=settings.service_name)
    cosmos = CosmosClient(
        endpoint_url=settings.cosmos_endpoint_url,
        model=settings.cosmos_model,
        timeout_s=settings.cosmos_request_timeout_s,
    )

    task = asyncio.create_task(run(settings, consumer, producer, cosmos, log))
    app.state.settings = settings
    app.state.log = log
    app.state.task = task

    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        consumer.close()
        producer.flush(timeout=5.0)
        await cosmos.aclose()
        log.info("shutdown")


app = FastAPI(title="obstruction-detector", version=__version__, lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    task = getattr(app.state, "task", None)
    if task is None or task.done():
        return {"status": "not-ready"}
    return {"status": "ready"}
