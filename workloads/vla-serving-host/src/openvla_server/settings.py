# This project was developed with assistance from AI tools.
"""OpenVLA server settings."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class OpenvlaSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    service_name: str = "openvla-server"
    log_level: str = "INFO"
    port: int = 8000

    # Phase 1 starts in mock mode so the wiring (SNO pod → host bridge → this server)
    # can be verified without the 14 GB OpenVLA weight download + ROCm inference
    # bring-up gating the whole demo. Flip to `openvla` once the wiring is green.
    # Future values: `smolvla`, `pi0`.
    vla_mode: str = Field(default="mock", description="mock | openvla | smolvla | pi0")

    openvla_weights: str = Field(
        default="openvla/openvla-7b",
        description="Model source: HuggingFace id (openvla/openvla-7b), local path, or s3:// URI.",
    )

    s3_endpoint: str = Field(default="", description="S3-compatible endpoint URL for s3:// model URIs.")
    model_cache_dir: str = Field(default="/tmp/model_cache", description="Local directory to cache S3-downloaded models.")
    openvla_unnorm_key: str = Field(
        default="bridge_orig",
        description="Action-normalization dataset key; 'bridge_orig' matches the OpenVLA paper defaults.",
    )
    openvla_device: str = Field(default="cuda", description="cuda | cpu. ROCm presents as cuda via PyTorch.")
    openvla_torch_dtype: str = Field(
        default="fp16",
        description="fp16 | bf16 | fp32. fp16 is more stable than bf16 on early gfx1151 ROCm.",
    )
