# This project was developed with assistance from AI tools.
"""VLA fine-tuning configuration via environment variables."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"{name}={raw!r} is not a valid integer") from None


_S3_PREFIX_PATTERN = re.compile(r"^[a-zA-Z0-9._\-/]*$")


def _validate_s3_prefix(value: str, field_name: str) -> None:
    if ".." in value:
        raise ValueError(f"{field_name} must not contain '..': {value!r}")
    if value.startswith("/"):
        raise ValueError(f"{field_name} must not start with '/': {value!r}")
    if not _S3_PREFIX_PATTERN.match(value):
        raise ValueError(f"{field_name} contains invalid characters: {value!r}")


@dataclass
class S3Config:
    endpoint: str = field(default_factory=lambda: os.environ.get("S3_ENDPOINT", ""))
    bucket: str = field(default_factory=lambda: os.environ.get("S3_BUCKET", "vla-training"))
    access_key: str = field(default_factory=lambda: os.environ.get("AWS_ACCESS_KEY_ID", ""), repr=False)
    secret_key: str = field(default_factory=lambda: os.environ.get("AWS_SECRET_ACCESS_KEY", ""), repr=False)
    model_prefix: str = field(default_factory=lambda: os.environ.get("VLA_S3_MODEL_PREFIX", "vla/base-model"))
    dataset_prefix: str = field(default_factory=lambda: os.environ.get("VLA_S3_DATASET_PREFIX", "vla/dataset"))
    checkpoint_prefix: str = field(
        default_factory=lambda: os.environ.get("VLA_S3_CHECKPOINT_PREFIX", "vla-finetune")
    )

    def __post_init__(self) -> None:
        _validate_s3_prefix(self.model_prefix, "VLA_S3_MODEL_PREFIX")
        _validate_s3_prefix(self.dataset_prefix, "VLA_S3_DATASET_PREFIX")
        _validate_s3_prefix(self.checkpoint_prefix, "VLA_S3_CHECKPOINT_PREFIX")

    @property
    def enabled(self) -> bool:
        return bool(self.endpoint and self.access_key and self.secret_key)

    def create_client(self):
        import boto3
        from botocore.config import Config as BotoConfig

        return boto3.client(
            "s3",
            endpoint_url=self.endpoint,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            config=BotoConfig(s3={"addressing_style": "path"}),
        )


@dataclass
class MLflowConfig:
    tracking_uri: str = field(default_factory=lambda: os.environ.get("MLFLOW_TRACKING_URI", ""))
    experiment_name: str = field(
        default_factory=lambda: os.environ.get("MLFLOW_EXPERIMENT_NAME", "g1-vla-finetune")
    )
    insecure_tls: bool = field(
        default_factory=lambda: os.environ.get("MLFLOW_TRACKING_INSECURE_TLS", "false").lower() == "true"
    )

    @property
    def enabled(self) -> bool:
        return bool(self.tracking_uri)


@dataclass
class VlaTrainingConfig:
    s3: S3Config = field(default_factory=S3Config)
    mlflow: MLflowConfig = field(default_factory=MLflowConfig)
    base_model_repo: str = field(
        default_factory=lambda: os.environ.get("VLA_BASE_MODEL_REPO", "nvidia/GR00T-N1.7-3B")
    )
    dataset_repo: str = field(
        default_factory=lambda: os.environ.get("VLA_DATASET_REPO", "nvidia/PhysicalAI-Robotics-GR00T-Teleop-G1")
    )
    # The bundled dataset and modality definition are the Teleop-G1 schema,
    # which is registered by GR00T as NEW_EMBODIMENT.  Keep the default in
    # configuration aligned with the model that the pipeline actually trains.
    embodiment_tag: str = field(default_factory=lambda: os.environ.get("VLA_EMBODIMENT_TAG", "NEW_EMBODIMENT"))
    num_gpus: int = field(default_factory=lambda: _int_env("VLA_NUM_GPUS", 1))
    max_steps: int = field(default_factory=lambda: _int_env("VLA_MAX_STEPS", 2000))
    global_batch_size: int = field(default_factory=lambda: _int_env("VLA_GLOBAL_BATCH_SIZE", 64))
    hf_token: str = field(default_factory=lambda: os.environ.get("HF_TOKEN", ""))
