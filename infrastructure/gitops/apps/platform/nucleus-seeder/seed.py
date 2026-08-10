# This project was developed with assistance from AI tools.
"""One-shot seeder: mirror the Phase-1 USD Explorer Warehouse collected scene
from the NVIDIA CDN into our Nucleus.

The collected scene bundles all referenced assets (textures, materials,
sublayer USDs) in a single flat directory. We download the entire directory
from the staging CDN and upload to Nucleus so the scene loads without any
external CDN dependency at demo time.

Runtime: `nvcr.io/nvidia/isaac-sim:6.0.0-dev2` running headless via
`isaacsim.SimulationApp` — required for `omni.client` auth + async engine.
"""

from __future__ import annotations

from isaacsim import SimulationApp  # noqa: E402
_app = SimulationApp({"headless": True})

import asyncio  # noqa: E402
import os  # noqa: E402
import pathlib  # noqa: E402
import sys  # noqa: E402
import urllib.parse  # noqa: E402
import urllib.request  # noqa: E402
import xml.etree.ElementTree as ET  # noqa: E402


CDN_HOST = "https://omniverse-content-staging.s3-us-west-2.amazonaws.com"
S3_NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"

S3_PREFIX = "Usd_Explorer/Samples/Examples/2023_2/Warehouse/"
STRIP_PREFIX = S3_PREFIX

LOCAL_STAGING = pathlib.Path(os.environ.get("LOCAL_STAGING", "/staging"))
CUSTOM_SCENE = pathlib.Path(os.environ.get("CUSTOM_SCENE_DIR", "/scene"))

NUCLEUS_HOST = os.environ.get("NUCLEUS_HOST", "nucleus.apps.g4h4d3j7q1c9f7m.cimo.p1.openshiftapps.com")
NUCLEUS_USER = os.environ.get("NUCLEUS_USER", "omniverse")
NUCLEUS_PASS = os.environ.get("NUCLEUS_PASS", "")
NUCLEUS_ROOT = os.environ.get("NUCLEUS_ROOT", "/Projects/showcase/custom")


def s3_list(prefix: str) -> list[tuple[str, int]]:
    keys: list[tuple[str, int]] = []
    token: str | None = None
    while True:
        q = f"list-type=2&prefix={urllib.parse.quote(prefix, safe='/')}"
        if token:
            q += f"&continuation-token={urllib.parse.quote(token, safe='')}"
        with urllib.request.urlopen(f"{CDN_HOST}/?{q}", timeout=30) as resp:
            root = ET.fromstring(resp.read())
        for obj in root.findall(S3_NS + "Contents"):
            key = obj.find(S3_NS + "Key").text
            size = int(obj.find(S3_NS + "Size").text)
            keys.append((key, size))
        is_truncated = root.findtext(S3_NS + "IsTruncated") == "true"
        if not is_truncated:
            break
        token = root.findtext(S3_NS + "NextContinuationToken")
    return keys


def download(key: str, out_path: pathlib.Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    url = f"{CDN_HOST}/{urllib.parse.quote(key, safe='/')}"
    with urllib.request.urlopen(url, timeout=300) as src, out_path.open("wb") as dst:
        while True:
            chunk = src.read(1 << 20)
            if not chunk:
                break
            dst.write(chunk)


def enumerate_and_download() -> tuple[list[str], int]:
    downloaded: list[str] = []
    total_bytes = 0
    print(f"[listing] {S3_PREFIX}", flush=True)
    entries = s3_list(S3_PREFIX)
    print(f"[listing] {len(entries)} objects", flush=True)
    for key, size in entries:
        if not key or key.endswith("/"):
            continue
        local = LOCAL_STAGING / key
        if local.exists() and local.stat().st_size == size:
            continue
        download(key, local)
        downloaded.append(key)
        total_bytes += size
        if len(downloaded) % 50 == 0:
            print(f"  [download] {len(downloaded)} files, {total_bytes / 1e6:.1f} MB", flush=True)
    return downloaded, total_bytes


def _auth_callback(url: str):
    return (NUCLEUS_USER, NUCLEUS_PASS)


async def upload_tree() -> int:
    import omni.client

    _sub = omni.client.register_authentication_callback(_auth_callback)  # noqa: F841
    base = f"omniverse://{NUCLEUS_HOST}{NUCLEUS_ROOT}"
    r = await omni.client.create_folder_async(base)
    if r not in (omni.client.Result.OK, omni.client.Result.ERROR_ALREADY_EXISTS):
        print(f"  [nucleus] create_folder {base}: {r}", flush=True)

    failures = 0
    count = 0
    for p in sorted(LOCAL_STAGING.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(LOCAL_STAGING).as_posix()
        if STRIP_PREFIX and rel.startswith(STRIP_PREFIX):
            rel = rel[len(STRIP_PREFIX):]
        target = f"{base}/{rel}"
        result = await omni.client.copy_async(
            str(p), target, behavior=omni.client.CopyBehavior.OVERWRITE
        )
        if result != omni.client.Result.OK:
            print(f"  [FAIL] {rel} -> {target}: {result}", flush=True)
            failures += 1
        count += 1
        if count % 50 == 0:
            print(f"  [upload] {count} files", flush=True)
    print(f"[upload] total {count} files, {failures} failures", flush=True)
    return failures


async def upload_custom_scene() -> int:
    """Upload the custom scene file(s) from the mounted volume to Nucleus."""
    import omni.client

    _sub = omni.client.register_authentication_callback(_auth_callback)  # noqa: F841
    base = f"omniverse://{NUCLEUS_HOST}{NUCLEUS_ROOT}"

    failures = 0
    if not CUSTOM_SCENE.exists():
        print("[custom] no custom scene directory mounted, skipping", flush=True)
        return 0

    for p in sorted(CUSTOM_SCENE.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(CUSTOM_SCENE).as_posix()
        target = f"{base}/{rel}"
        result = await omni.client.copy_async(
            str(p), target, behavior=omni.client.CopyBehavior.OVERWRITE
        )
        if result != omni.client.Result.OK:
            print(f"  [FAIL] {rel} -> {target}: {result}", flush=True)
            failures += 1
        else:
            print(f"  [custom] {rel} -> {target}", flush=True)
    return failures


def main() -> int:
    LOCAL_STAGING.mkdir(parents=True, exist_ok=True)

    print("== stage 1: enumerate + download from CDN ==", flush=True)
    files, total = enumerate_and_download()
    print(f"[download] complete: {len(files)} files, {total / 1e9:.2f} GB staged at {LOCAL_STAGING}", flush=True)

    print("== stage 2: upload CDN assets to Nucleus ==", flush=True)
    failures = asyncio.run(upload_tree())

    print("== stage 3: upload custom scene to Nucleus ==", flush=True)
    failures += asyncio.run(upload_custom_scene())

    return 1 if failures else 0


if __name__ == "__main__":
    try:
        rc = main()
    finally:
        _app.close()
    sys.exit(rc)
