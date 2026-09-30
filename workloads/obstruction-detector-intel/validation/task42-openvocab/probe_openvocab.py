# This project was developed with assistance from AI tools.
"""FastSAM + CLIP open-vocabulary probe, binary transport + urllib3 client.

Supersedes the JSON/`requests` version. Root-causing showed that path spent
~75% of wall clock encoding floats as decimal text and a further ~790 ms in
`requests`' response handling -- neither is a property of the models. This
measures the same pipeline over the KServe v2 binary extension with urllib3.

Boundary matches Task 4.1: per-stage timing covers request build, in-cluster
round trip and server inference; it excludes Kafka.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time

import numpy as np
import urllib3
from PIL import Image

POOL = urllib3.PoolManager(maxsize=8)
FASTSAM = "http://fastsam-rest:8081/v2/models/fastsam/infer"
CLIP = "http://clip-rest:8081/v2/models/clip/infer"

CONF_THRESHOLD = 0.4
IOU_THRESHOLD = 0.5
# Cap on segments sent to CLIP. Cost is roughly linear in segment count, so this
# is the main latency lever -- see the sweep in results-2026-09-30.json.
MAX_SEGMENTS = int(os.environ.get("MAX_SEG", "20"))

OBSTRUCTION_PROMPTS = {0, 1, 2, 3, 4, 7}
CLIP_MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
CLIP_STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)

DTYPE = {"FP32": np.float32, "INT64": np.int64}


def infer(url: str, inputs: list[tuple[str, np.ndarray]],
          outputs: list[str]) -> tuple[dict[str, np.ndarray], float]:
    """POST via the KServe v2 binary extension; return {name: array}, elapsed ms."""
    blobs, specs = [], []
    for name, arr in inputs:
        raw = np.ascontiguousarray(arr).tobytes()
        blobs.append(raw)
        specs.append({
            "name": name,
            "shape": list(arr.shape),
            "datatype": "INT64" if arr.dtype == np.int64 else "FP32",
            "parameters": {"binary_data_size": len(raw)},
        })
    header = json.dumps({
        "inputs": specs,
        # Every output must be requested binary: OVMS returns any output you
        # omit as JSON text in the header, which inflated one run to 17.9 MB.
        "outputs": [{"name": n, "parameters": {"binary_data": True}} for n in outputs],
    }).encode()
    body = header + b"".join(blobs)

    t0 = time.perf_counter()
    r = POOL.request("POST", url, body=body, headers={
        "Content-Type": "application/octet-stream",
        "Inference-Header-Content-Length": str(len(header)),
    }, preload_content=True)
    elapsed = (time.perf_counter() - t0) * 1000
    if r.status != 200:
        raise RuntimeError(f"{r.status}: {r.data[:300]!r}")

    hlen = int(r.headers["Inference-Header-Content-Length"])
    meta = json.loads(r.data[:hlen])
    raw = r.data[hlen:]
    out: dict[str, np.ndarray] = {}
    off = 0
    for spec in meta["outputs"]:
        size = spec.get("parameters", {}).get("binary_data_size")
        if size is None:
            # OVMS declined binary for this output and inlined it as JSON.
            arr = np.array(spec["data"], dtype=DTYPE[spec["datatype"]])
        else:
            arr = np.frombuffer(raw[off:off + size], dtype=DTYPE[spec["datatype"]])
            off += size
        out[spec["name"]] = arr.reshape(spec["shape"])
    return out, elapsed


def letterbox(img: Image.Image, size: int = 640):
    w, h = img.size
    scale = min(size / w, size / h)
    nw, nh = round(w * scale), round(h * scale)
    canvas = Image.new("RGB", (size, size), (114, 114, 114))
    pad_x, pad_y = (size - nw) // 2, (size - nh) // 2
    canvas.paste(img.resize((nw, nh), Image.BILINEAR), (pad_x, pad_y))
    arr = np.asarray(canvas, dtype=np.float32) / 255.0
    return arr.transpose(2, 0, 1)[None], scale, pad_x, pad_y


def nms(boxes: np.ndarray, scores: np.ndarray, iou_thr: float) -> list[int]:
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size:
        i = order[0]
        keep.append(int(i))
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        inter = np.clip(xx2 - xx1, 0, None) * np.clip(yy2 - yy1, 0, None)
        order = order[1:][inter / (areas[i] + areas[order[1:]] - inter + 1e-9) < iou_thr]
    return keep


def segment(path: str):
    img = Image.open(path).convert("RGB")
    tensor, scale, pad_x, pad_y = letterbox(img)
    out, ms = infer(FASTSAM, [("x.1", tensor)], ["out_0", "input"])
    det = out["out_0"][0].reshape(37, 8400)
    scores = det[4]
    sel = scores > CONF_THRESHOLD
    if not sel.any():
        return [], ms
    cx, cy, w, h = det[0][sel], det[1][sel], det[2][sel], det[3][sel]
    boxes = np.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], axis=1)
    keep = nms(boxes, scores[sel], IOU_THRESHOLD)[:MAX_SEGMENTS]
    iw, ih = img.size
    crops = []
    for i in keep:
        b = boxes[i]
        x0 = int(max(0, (b[0] - pad_x) / scale))
        y0 = int(max(0, (b[1] - pad_y) / scale))
        x1 = int(min(iw, (b[2] - pad_x) / scale))
        y1 = int(min(ih, (b[3] - pad_y) / scale))
        if x1 - x0 >= 8 and y1 - y0 >= 8:
            crops.append((x0, y0, x1, y1))
    return crops, ms


def classify(path: str, crops, tokens):
    img = Image.open(path).convert("RGB")
    batch = []
    for box in crops:
        crop = img.crop(box).resize((224, 224), Image.BICUBIC)
        arr = (np.asarray(crop, dtype=np.float32) / 255.0 - CLIP_MEAN) / CLIP_STD
        batch.append(arr.transpose(2, 0, 1))
    pixel = np.ascontiguousarray(np.stack(batch), dtype=np.float32)
    ids = np.array(tokens["input_ids"], dtype=np.int64)
    att = np.array(tokens["attention_mask"], dtype=np.int64)
    out, ms = infer(CLIP,
                    [("pixel_values", pixel), ("input_ids", ids), ("attention_mask", att)],
                    ["logits_per_image", "image_embeds", "text_embeds", "logits_per_text"])
    logits = out["logits_per_image"].reshape(len(crops), len(tokens["prompts"]))
    exp = np.exp(logits - logits.max(axis=1, keepdims=True))
    probs = exp / exp.sum(axis=1, keepdims=True)
    return [(int(p.argmax()), float(p.max())) for p in probs], ms


def main() -> None:
    with open("/work/clip_tokens.json") as fh:
        tokens = json.load(fh)
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    report = []
    for name in ("aisle3_pallet.jpg", "aisle3_empty.jpg"):
        path = f"/work/{name}"
        segment(path)  # warm
        seg, cl, tot = [], [], []
        crops, labels = [], []
        for _ in range(runs):
            t0 = time.perf_counter()
            crops, s_ms = segment(path)
            labels, c_ms = classify(path, crops, tokens) if crops else ([], 0.0)
            tot.append((time.perf_counter() - t0) * 1000)
            seg.append(s_ms)
            cl.append(c_ms)
        hits = [(tokens["prompts"][i], round(p, 3)) for i, p in labels
                if i in OBSTRUCTION_PROMPTS]
        entry = {
            "image": name,
            "segments": len(crops),
            "fastsam_ms_median": round(statistics.median(seg), 1),
            "clip_ms_median": round(statistics.median(cl), 1),
            "total_ms_median": round(statistics.median(tot), 1),
            "total_ms_runs": [round(x, 1) for x in tot],
            "obstructed": bool(hits),
            "top_labels": sorted({(tokens["prompts"][i], round(p, 2)) for i, p in labels},
                                 key=lambda t: -t[1])[:5],
        }
        report.append(entry)
        print(json.dumps(entry), flush=True)
    with open("/work/results-fast.json", "w") as fh:
        json.dump(report, fh, indent=2)


if __name__ == "__main__":
    main()
