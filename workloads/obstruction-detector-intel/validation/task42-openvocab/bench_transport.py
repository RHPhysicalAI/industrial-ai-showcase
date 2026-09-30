# This project was developed with assistance from AI tools.
"""Isolate the residual ~800 ms gap between client RTT and OVMS server time.

Diffs OVMS's own Prometheus counters across a known number of requests, so
server-side time is measured by the server rather than inferred. Compares the
ClusterIP Service path against the pod IP directly, and a 1-float payload
against the full 4.9 MB tensor to separate fixed overhead from transfer cost.
"""
from __future__ import annotations

import json
import statistics
import sys
import time

import numpy as np
import requests

N = 5
TENSOR = np.random.rand(1, 3, 640, 640).astype(np.float32)
RAW = TENSOR.tobytes()

HEADER = json.dumps({
    "inputs": [{"name": "x.1", "shape": [1, 3, 640, 640], "datatype": "FP32",
                "parameters": {"binary_data_size": len(RAW)}}],
    "outputs": [{"name": "out_0", "parameters": {"binary_data": True}},
                {"name": "input", "parameters": {"binary_data": True}}],
}).encode()
BODY = HEADER + RAW


def counters(base: str) -> tuple[float, int, float, int]:
    txt = requests.get(f"{base}/metrics", timeout=30).text
    out = {}
    for line in txt.splitlines():
        for key in ("ovms_request_time_us_sum", "ovms_request_time_us_count",
                    "ovms_inference_time_us_sum", "ovms_inference_time_us_count"):
            if line.startswith(key) and 'interface="gRPC"' not in line:
                out[key] = float(line.rsplit(" ", 1)[1])
    return (out["ovms_request_time_us_sum"], int(out["ovms_request_time_us_count"]),
            out["ovms_inference_time_us_sum"], int(out["ovms_inference_time_us_count"]))


def run(base: str, label: str, body: bytes, hlen: int) -> None:
    url = f"{base}/v2/models/fastsam/infer"
    headers = {"Content-Type": "application/octet-stream",
               "Inference-Header-Content-Length": str(hlen)}
    requests.post(url, data=body, headers=headers, timeout=300)  # warm

    rs0, rc0, is0, ic0 = counters(base)
    rtts = []
    for _ in range(N):
        t0 = time.perf_counter()
        r = requests.post(url, data=body, headers=headers, timeout=300)
        rtts.append((time.perf_counter() - t0) * 1000)
        r.raise_for_status()
    rs1, rc1, is1, ic1 = counters(base)

    server_ms = (rs1 - rs0) / max(rc1 - rc0, 1) / 1000
    infer_ms = (is1 - is0) / max(ic1 - ic0, 1) / 1000
    client_ms = statistics.median(rtts)
    print(f"{label:<34} payload={len(body)/1e6:6.2f}MB  "
          f"client={client_ms:8.1f}ms  server={server_ms:7.1f}ms  "
          f"infer={infer_ms:6.1f}ms  unaccounted={client_ms - server_ms:7.1f}ms")


if __name__ == "__main__":
    svc = "http://fastsam-rest:8081"
    pod = f"http://{sys.argv[1]}:8081" if len(sys.argv) > 1 else None

    tiny_raw = np.zeros((1, 3, 640, 640), dtype=np.float32).tobytes()
    run(svc, "full tensor via Service", BODY, len(HEADER))
    if pod:
        run(pod, "full tensor via pod IP", BODY, len(HEADER))
    run(svc, "zeros tensor via Service", HEADER + tiny_raw, len(HEADER))
