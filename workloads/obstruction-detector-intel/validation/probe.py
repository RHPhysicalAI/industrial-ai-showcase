# This project was developed with assistance from AI tools.
"""Quality + latency probe for the YOLOv8/OVMS obstruction detector.

Runs *inside* the detector pod so it exercises the real `YoloClient` code path
against the in-cluster OVMS endpoint. Emits one JSON line per image.

Measurement boundary: `YoloClient.reason(image_b64)` entry to return. That
covers JPEG decode, preprocessing, KServe v2 REST round-trip, and detection
parsing -- i.e. everything the detector does per frame except Kafka I/O.

Usage (see docs/13-intel-task4-validation-report.md for the full procedure):

    oc cp probe.py <ns>/<detector-pod>:/tmp/probe.py
    oc exec -n <ns> <detector-pod> -- python /tmp/probe.py /tmp/testimg/frame.jpg

One image per invocation is deliberate: the detector pod is capped at 1Gi and
the v2 REST response for a [1,84,8400] output is ~700k floats, so batching
several images into a single process OOMKills it.
"""

import asyncio
import base64
import gc
import json
import sys
import time
from pathlib import Path

import cv2

from obstruction_detector_intel.yolo_client import YoloClient

ENDPOINT = "http://yolov8-detector-rest.intel-vla-training.svc.cluster.local:8081"
RUNS = 3


async def main() -> None:
    path = Path(sys.argv[1])
    img = cv2.imread(str(path))
    if img is None:
        raise SystemExit(f"could not decode {path}")
    dims = f"{img.shape[1]}x{img.shape[0]}"
    del img
    gc.collect()

    client = YoloClient(endpoint_url=ENDPOINT, timeout_s=120.0)
    image_b64 = base64.b64encode(path.read_bytes()).decode()

    latencies_ms = []
    verdict = None
    for _ in range(RUNS):
        start = time.perf_counter()
        verdict = await client.reason(image_b64)
        latencies_ms.append((time.perf_counter() - start) * 1000)
        gc.collect()

    print(json.dumps({
        "image": path.name,
        "dims": dims,
        "obstructed": verdict.obstruction,
        "label": verdict.label,
        "confidence": round(verdict.confidence, 4),
        "latency_ms_runs": [round(x, 1) for x in latencies_ms],
        "latency_ms_median": round(sorted(latencies_ms)[len(latencies_ms) // 2], 1),
    }))
    await client.aclose()


asyncio.run(main())
