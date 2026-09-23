# This project was developed with assistance from AI tools.
"""Download model artifacts from S3-compatible storage to a local directory."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from urllib.parse import urlparse

_CACHE_MARKER = ".download-complete"


def parse_s3_uri(uri: str) -> tuple[str, str]:
    """Parse an s3://bucket/prefix URI into (bucket, prefix)."""
    parsed = urlparse(uri)
    if parsed.scheme != "s3":
        raise ValueError(f"Not an S3 URI: {uri!r}")
    bucket = parsed.netloc
    prefix = parsed.path.lstrip("/")
    return bucket, prefix


def _artifact_is_complete(cache_path: Path) -> bool:
    """Return whether a cached prefix contains a usable serving artifact.

    A previous interrupted download can leave only config files behind.  A
    non-empty directory is therefore not sufficient evidence that a model is
    ready.  GR00T requires model metadata plus weights; the legacy ONNX path
    requires at least one ONNX file.
    """
    if any(cache_path.glob("**/*.onnx")):
        return True

    has_config = (cache_path / "config.json").is_file()
    has_processor = (cache_path / "processor_config.json").is_file()
    has_sharded_weights = False
    index_path = cache_path / "model.safetensors.index.json"
    if index_path.is_file():
        try:
            weight_map = json.loads(index_path.read_text()).get("weight_map", {})
            referenced_files = set(weight_map.values())
            has_sharded_weights = bool(referenced_files) and all(
                (cache_path / name).is_file() for name in referenced_files
            )
        except (AttributeError, OSError, TypeError, ValueError):
            has_sharded_weights = False
    has_single_weights = any(
        (cache_path / name).is_file() for name in ("model.safetensors", "pytorch_model.bin")
    )
    return has_config and has_processor and (has_sharded_weights or has_single_weights)


def download_model_from_s3(
    uri: str,
    local_dir: str,
    endpoint: str = "",
    access_key: str = "",
    secret_key: str = "",
) -> str:
    """Download all objects under an S3 prefix to a local directory.

    Returns the local directory path. A cache hit requires a complete model
    artifact, not merely a non-empty directory. Incomplete downloads are
    removed and retried on the next call.
    """
    bucket, prefix = parse_s3_uri(uri)

    cache_path = Path(local_dir) / bucket / prefix.replace("/", "_")
    marker = cache_path / _CACHE_MARKER

    if marker.is_file() and _artifact_is_complete(cache_path):
        return str(cache_path)

    # Preserve a valid cache created by an older image, then add the marker so
    # future calls have an explicit completion signal.
    if cache_path.is_dir() and _artifact_is_complete(cache_path):
        marker.touch()
        return str(cache_path)

    # This is deliberately scoped to the one exact prefix cache. It removes
    # stale/partial model files, never the parent PVC or another artifact.
    if cache_path.exists():
        if cache_path.is_dir():
            shutil.rmtree(cache_path)
        else:
            cache_path.unlink()
    cache_path.mkdir(parents=True, exist_ok=True)

    endpoint = endpoint or os.environ.get("S3_ENDPOINT", "")
    access_key = access_key or os.environ.get("AWS_ACCESS_KEY_ID", "")
    secret_key = secret_key or os.environ.get("AWS_SECRET_ACCESS_KEY", "")

    if not endpoint:
        raise RuntimeError("S3_ENDPOINT is required for s3:// model URIs")

    import boto3
    from botocore.config import Config as BotoConfig

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=BotoConfig(s3={"addressing_style": "path"}),
    )

    paginator = s3.get_paginator("list_objects_v2")
    norm_prefix = prefix.rstrip("/") + "/"
    downloaded = 0

    try:
        for page in paginator.paginate(Bucket=bucket, Prefix=norm_prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                rel_path = key[len(norm_prefix) :]
                if not rel_path:
                    continue
                local_file = cache_path / rel_path
                local_file.parent.mkdir(parents=True, exist_ok=True)
                s3.download_file(bucket, key, str(local_file))
                downloaded += 1

        if downloaded == 0:
            raise RuntimeError(f"No objects found at s3://{bucket}/{norm_prefix}")
        if not _artifact_is_complete(cache_path):
            raise RuntimeError(
                f"Downloaded artifact at s3://{bucket}/{norm_prefix} is incomplete; "
                "expected GR00T model metadata/weights or an ONNX file"
            )
        marker.write_text("complete\n")
    except Exception:
        # Do not leave a misleading partial cache after a failed or full-disk
        # download. The next attempt will start with a clean exact-prefix dir.
        shutil.rmtree(cache_path, ignore_errors=True)
        raise

    return str(cache_path)
