# This project was developed with assistance from AI tools.
"""Host-native VLA serving entrypoint (per ADR-026).

Phase 1 ships with `VLA_MODE=mock` default so the wiring (SNO pod → host bridge →
this server) is verifiable without the 14 GB OpenVLA weight pull + ROCm inference
bring-up. Flip to `openvla` via env when you're ready for real inference.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING
from uuid import uuid4

import structlog
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from openvla_server import __version__
from openvla_server.model import VlaAdapter, build_adapter, decode_image_b64
from openvla_server.settings import OpenvlaSettings

if TYPE_CHECKING:
    from structlog.stdlib import BoundLogger


class ActRequest(BaseModel):
    image: str = Field(description="Base64-encoded RGB image bytes. Empty string acceptable in mock mode.")
    instruction: str = Field(description="Natural-language action instruction for the robot.")
    trace_id: str = Field(description="Upstream OpenTelemetry trace ID for end-to-end correlation.")


class ActResponse(BaseModel):
    action: list[float]
    model_version: str
    trace_id: str
    request_id: str


def _configure_logging(service_name: str, level: str) -> "BoundLogger":
    import logging
    import sys

    logging.basicConfig(stream=sys.stdout, level=getattr(logging, level.upper(), logging.INFO), format="%(message)s")
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    return structlog.get_logger().bind(service=service_name)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = OpenvlaSettings()
    log = _configure_logging(settings.service_name, settings.log_level)
    log.info("startup", version=__version__, vla_mode=settings.vla_mode, openvla_weights=settings.openvla_weights)

    adapter: VlaAdapter = build_adapter(
        mode=settings.vla_mode,
        weights=settings.openvla_weights,
        unnorm_key=settings.openvla_unnorm_key,
        device=settings.openvla_device,
        torch_dtype=settings.openvla_torch_dtype,
        s3_endpoint=settings.s3_endpoint,
        model_cache_dir=settings.model_cache_dir,
    )
    app.state.settings = settings
    app.state.log = log
    app.state.adapter = adapter
    try:
        yield
    finally:
        log.info("shutdown")


app = FastAPI(title="openvla-server", version=__version__, lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/readyz")
async def readyz() -> dict[str, str]:
    settings: OpenvlaSettings = app.state.settings
    return {"status": "ready", "vla_mode": settings.vla_mode}


@app.post("/act", response_model=ActResponse)
async def act(req: ActRequest) -> ActResponse:
    adapter: VlaAdapter = app.state.adapter
    log: BoundLogger = app.state.log
    request_id = uuid4().hex

    try:
        image = decode_image_b64(req.image)
    except Exception as exc:
        log.warning("image.decode.failed", trace_id=req.trace_id, error=str(exc))
        raise HTTPException(status_code=400, detail=f"Invalid image payload: {exc}") from exc

    loop = asyncio.get_running_loop()
    try:
        action = await loop.run_in_executor(None, adapter.infer, image, req.instruction)
    except Exception as exc:
        log.exception("inference.failed", trace_id=req.trace_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Inference failed: {exc}") from exc

    log.info(
        "act.completed",
        trace_id=req.trace_id,
        request_id=request_id,
        model_version=adapter.model_version,
        instruction=req.instruction[:80],
    )
    return ActResponse(
        action=action, model_version=adapter.model_version, trace_id=req.trace_id, request_id=request_id
    )
