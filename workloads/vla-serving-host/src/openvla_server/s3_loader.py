# This project was developed with assistance from AI tools.
"""Download model artifacts from S3-compatible storage to a local directory."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse


def parse_s3_uri(uri: str) -> tuple[str, str]:
    """Parse an s3://bucket/prefix URI into (bucket, prefix)."""
    parsed = urlparse(uri)
    if parsed.scheme != "s3":
        raise ValueError(f"Not an S3 URI: {uri!r}")
    bucket = parsed.netloc
    prefix = parsed.path.lstrip("/")
    return bucket, prefix


def download_model_from_s3(
    uri: str,
    local_dir: str,
    endpoint: str = "",
    access_key: str = "",
    secret_key: str = "",
) -> str:
    """Download all objects under an S3 prefix to a local directory.

    Returns the local directory path. Skips download if the directory
    already contains files (cache hit).
    """
    bucket, prefix = parse_s3_uri(uri)

    cache_path = Path(local_dir) / bucket / prefix.replace("/", "_")
    cache_path.mkdir(parents=True, exist_ok=True)

    if any(cache_path.iterdir()):
        return str(cache_path)

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

    return str(cache_path)
