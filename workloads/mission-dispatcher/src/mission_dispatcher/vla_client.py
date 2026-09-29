# This project was developed with assistance from AI tools.
"""HTTP client for the host-native VLA serving endpoint (per ADR-026)."""

import math
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)


class VlaAction(BaseModel):
    """Response shape from POST /act on the host VLA server."""

    model_config = ConfigDict(protected_namespaces=())

    action: list[float] = Field(
        min_length=7,
        max_length=7,
        description="7-DOF action vector: dx, dy, dz, droll, dpitch, dyaw, dgrasp.",
    )
    model_version: str
    trace_id: str

    @field_validator("action")
    @classmethod
    def action_values_must_be_finite(cls, values: list[float]) -> list[float]:
        """Reject malformed model output before it reaches a future actuator."""
        if not all(math.isfinite(value) for value in values):
            raise ValueError("action values must be finite numbers")
        return values


class VlaClient:
    """Thin httpx-based client with retry on transient network errors."""

    def __init__(self, endpoint_url: str, timeout_s: float = 10.0) -> None:
        self._endpoint_url = endpoint_url
        self._client = httpx.AsyncClient(timeout=timeout_s)

    async def aclose(self) -> None:
        await self._client.aclose()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.2, max=2.0),
        retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
        reraise=True,
    )
    async def act(
        self, image_b64: str, instruction: str, trace_id: str
    ) -> VlaAction:
        payload: dict[str, Any] = {
            "image": image_b64,
            "instruction": instruction,
            "trace_id": trace_id,
        }
        response = await self._client.post(self._endpoint_url, json=payload)
        response.raise_for_status()
        return VlaAction.model_validate(response.json())
