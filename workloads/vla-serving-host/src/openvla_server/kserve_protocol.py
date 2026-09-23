# This project was developed with assistance from AI tools.
"""Small KServe v1 request contract for the existing ``/act`` server."""

from uuid import uuid4

from pydantic import BaseModel, Field


class KServeInstance(BaseModel):
    """One KServe instance translated to the server's established /act input."""

    image: str = Field(description="Base64-encoded RGB image bytes.")
    instruction: str = Field(description="Natural-language action instruction.")
    trace_id: str = Field(default_factory=lambda: f"kserve-{uuid4().hex}")


class KServePredictRequest(BaseModel):
    """KServe v1 REST request with a bounded batch for the canary."""

    instances: list[KServeInstance] = Field(min_length=1, max_length=8)
