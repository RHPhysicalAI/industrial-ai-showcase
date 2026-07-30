# This project was developed with assistance from AI tools.
"""RGB + depth capture for Cosmos Transfer input.

Chains from warehouse_baseline.py via import. Subscribes to Kit's update
loop and watches for a trigger file. When /tmp/start-cosmos-capture appears,
captures N frames of RGB + depth from the demo camera and encodes to MP4.

Trigger from outside the pod:
    oc exec <pod> -n isaac-sim -- touch /tmp/start-cosmos-capture
"""

import asyncio
import json
import os
import subprocess
import time
import traceback

import numpy as np

CAMERA_PRIM = "/OmniverseKit_Persp"
RESOLUTION = (1280, 720)
CAPTURE_FRAMES = 93
CAPTURE_FPS = 16
OUTPUT_DIR = "/tmp/cosmos-capture"
TRIGGER_FILE = "/tmp/start-cosmos-capture"
FFMPEG_PATH = "/tmp/ffmpeg"

_started = False
_capturing = False
_update_sub = None


def _encode_frames_to_mp4(frames, path, fps):
    """Encode list of uint8 RGB numpy frames to MP4."""
    h, w = frames[0].shape[:2]
    cmd = [
        FFMPEG_PATH, "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{w}x{h}", "-r", str(fps),
        "-i", "pipe:0",
        "-c:v", "libx264", "-preset", "medium",
        "-crf", "18", "-pix_fmt", "yuv420p",
        path,
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    for frame in frames:
        proc.stdin.write(frame.tobytes())
    proc.stdin.close()
    proc.wait()
    if proc.returncode != 0:
        print(f"[cosmos_capture] ffmpeg error: {proc.stderr.read().decode()[:200]}", flush=True)
    else:
        size = os.path.getsize(path)
        print(f"[cosmos_capture] wrote {path} ({size:,} bytes, {len(frames)} frames)", flush=True)


def _depth_to_rgb(depth):
    """Convert float32 depth to 3-channel grayscale uint8."""
    valid = depth[np.isfinite(depth)]
    if valid.size == 0:
        return np.zeros((*depth.shape, 3), dtype=np.uint8)
    d_min, d_max = float(valid.min()), float(valid.max())
    if d_max - d_min < 1e-6:
        return np.zeros((*depth.shape, 3), dtype=np.uint8)
    normalized = np.clip((depth - d_min) / (d_max - d_min), 0.0, 1.0)
    gray = (normalized * 255).astype(np.uint8)
    return np.stack([gray, gray, gray], axis=-1)


async def _do_capture():
    global _capturing
    _capturing = True
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"[cosmos_capture] starting: {CAPTURE_FRAMES} frames at {RESOLUTION[0]}x{RESOLUTION[1]}", flush=True)

    try:
        import omni.replicator.core as rep
        import omni.kit.app
    except Exception:
        print(f"[cosmos_capture] replicator not available: {traceback.format_exc()}", flush=True)
        _capturing = False
        return

    app = omni.kit.app.get_app()
    rp = rep.create.render_product(CAMERA_PRIM, resolution=RESOLUTION)
    rgb_ann = rep.AnnotatorRegistry.get_annotator("rgb")
    depth_ann = rep.AnnotatorRegistry.get_annotator("distance_to_camera")
    rgb_ann.attach([rp.path])
    depth_ann.attach([rp.path])

    for _ in range(15):
        await app.next_update_async()

    rgb_frames = []
    depth_frames = []

    print("[cosmos_capture] capturing...", flush=True)
    for i in range(CAPTURE_FRAMES):
        rgb_data = rgb_ann.get_data()
        depth_data = depth_ann.get_data()

        if rgb_data is None or depth_data is None:
            await app.next_update_async()
            continue

        if isinstance(rgb_data, dict):
            rgb_data = rgb_data.get("data", rgb_data)
        if isinstance(depth_data, dict):
            depth_data = depth_data.get("data", depth_data)

        if hasattr(rgb_data, "ndim") and rgb_data.ndim == 3:
            rgb_frames.append(np.array(rgb_data)[:, :, :3].copy())
        if hasattr(depth_data, "ndim"):
            d = np.array(depth_data, dtype=np.float32)
            if d.ndim == 3:
                d = d[:, :, 0]
            depth_frames.append(d)

        if (i + 1) % 20 == 0:
            print(f"[cosmos_capture] {i + 1}/{CAPTURE_FRAMES}", flush=True)

        # Advance sim ~1 frame at capture FPS
        ticks = max(1, int(60 / CAPTURE_FPS))
        for _ in range(ticks):
            await app.next_update_async()

    print(f"[cosmos_capture] captured {len(rgb_frames)} rgb + {len(depth_frames)} depth", flush=True)

    if not rgb_frames or not depth_frames:
        print("[cosmos_capture] no frames, aborting", flush=True)
        _capturing = False
        return

    rgb_path = os.path.join(OUTPUT_DIR, "warehouse_rgb.mp4")
    depth_path = os.path.join(OUTPUT_DIR, "warehouse_depth.mp4")

    _encode_frames_to_mp4(rgb_frames, rgb_path, CAPTURE_FPS)
    _encode_frames_to_mp4([_depth_to_rgb(d) for d in depth_frames], depth_path, CAPTURE_FPS)

    spec = {
        "name": "warehouse_depth",
        "prompt": "photorealistic warehouse interior, concrete floor with markings, "
                  "fluorescent overhead lighting, tall industrial racking with pallets, "
                  "forklift navigating narrow aisle, realistic shadows and reflections",
        "video_path": rgb_path,
        "guidance": 3,
        "depth": {
            "control_path": depth_path,
            "control_weight": 0.8,
        },
    }
    spec_path = os.path.join(OUTPUT_DIR, "warehouse_depth_spec.json")
    with open(spec_path, "w") as f:
        json.dump(spec, f, indent=2)

    print(f"[cosmos_capture] done. Files:", flush=True)
    for fn in sorted(os.listdir(OUTPUT_DIR)):
        sz = os.path.getsize(os.path.join(OUTPUT_DIR, fn))
        print(f"  {fn} ({sz:,} bytes)", flush=True)

    # Clean up trigger so it doesn't re-fire
    try:
        os.remove(TRIGGER_FILE)
    except OSError:
        pass
    _capturing = False


def _check_trigger(event):
    """Called on Kit update tick — checks for trigger file."""
    global _started
    try:
        if _capturing:
            return
        if os.path.exists(TRIGGER_FILE):
            if not _started:
                _started = True
                print("[cosmos_capture] trigger detected, starting capture", flush=True)
                asyncio.ensure_future(_do_capture())
    except Exception:
        print(f"[cosmos_capture] check_trigger error: {traceback.format_exc()}", flush=True)


def _init():
    global _update_sub
    try:
        import omni.kit.app
        app = omni.kit.app.get_app()
        _update_sub = app.get_update_event_stream().create_subscription_to_pop(
            _check_trigger, name="cosmos_capture-trigger-watch"
        )
        print("[cosmos_capture] trigger watcher installed (touch /tmp/start-cosmos-capture to capture)", flush=True)
    except Exception:
        print(f"[cosmos_capture] init failed: {traceback.format_exc()}", flush=True)


_init()
