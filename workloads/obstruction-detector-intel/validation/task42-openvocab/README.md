# Task 4.2 — open-vocabulary perception spike (FastSAM + CLIP)

Evidence and runnable example for the Task 4.2 evaluation recorded in
[`results-2026-09-30.json`](results-2026-09-30.json). Findings are summarised on PR #91.

> [!WARNING]
> This is a **spike**, hand-applied outside GitOps because Argo CD is not installed on the
> cluster it was run against. It is not a supported deployment and nothing here is
> reconciled. Treat the manifests as a reproduction recipe, not as a deployable component.

## What it measures

Two gates, both agreed when Task 4.1 was scoped: detection accuracy **≥ 80%** and
Loop 1 latency **< 500 ms**.

| Gate | Result | |
|---|---|---|
| Accuracy | 1/2 (50%) on the demo frames | **FAIL** |
| Latency | 1 062 ms median (best config) | **FAIL — 2.1×** |

The latency number matters less than *why* it moved. As first measured the pipeline took
8 282 ms. Two client-side defects — KServe v2 JSON transport, and the `requests` library —
accounted for ~92% of that. Neither is a property of the model. OVMS's own counters put
FastSAM inference at ~125 ms.

This is directly relevant to Task 4.1, whose NO-GO cited a 13–21× latency overrun and
attributed it to YOLOv8. That attribution does not survive this measurement.

## Reproducing

Requires `oc` with cluster-admin on a cluster running RHOAI with KServe in RawDeployment
mode. Roughly 15 minutes, no GPU needed.

### 1. Convert the models

Not committed — the two IR files total ~652 MB. Regenerate them:

```bash
python -m venv .venv && ./.venv/bin/pip install ultralytics optimum-intel openvino

# FastSAM-s -> OpenVINO IR (~47 MB)
./.venv/bin/python -c "
from ultralytics import FastSAM
FastSAM('FastSAM-s.pt').export(format='openvino')"

# CLIP ViT-B/32 -> OpenVINO IR (~605 MB)
./.venv/bin/python -c "
from optimum.intel import OVModelForZeroShotImageClassification as M
M.from_pretrained('openai/clip-vit-base-patch32', export=True).save_pretrained('clip_ov')"
```

### 2. Create storage and stage the models

```bash
oc apply -f manifests/01-storage.yaml
oc wait --for=condition=Ready pod/model-loader -n intel-vla-training --timeout=180s

# ubi-minimal has no tar, which `oc cp` requires
oc exec -n intel-vla-training model-loader -- microdnf install -y tar

NS=intel-vla-training
oc exec -n $NS model-loader -- mkdir -p /pvc/fastsam/fastsam/1 /pvc/clip/clip/1
oc cp FastSAM-s_openvino_model/FastSAM-s.xml $NS/model-loader:/pvc/fastsam/fastsam/1/FastSAM-s.xml
oc cp FastSAM-s_openvino_model/FastSAM-s.bin $NS/model-loader:/pvc/fastsam/fastsam/1/FastSAM-s.bin
oc cp clip_ov/openvino_model.xml $NS/model-loader:/pvc/clip/clip/1/openvino_model.xml
oc cp clip_ov/openvino_model.bin $NS/model-loader:/pvc/clip/clip/1/openvino_model.bin

# Verify, then release the volumes so the predictors can attach them
oc exec -n $NS model-loader -- sha256sum /pvc/fastsam/fastsam/1/FastSAM-s.bin
oc delete pod model-loader -n $NS
```

`storageUri` points at the **parent** prefix; OVMS expects `<name>/<version>/` beneath it.

### 3. Serve

```bash
oc apply -f manifests/02-serving.yaml
oc wait --for=condition=Ready isvc/fastsam isvc/clip -n intel-vla-training --timeout=600s
```

### 4. Run the probe

```bash
oc apply -f manifests/03-probe.yaml
oc wait --for=condition=Ready pod/ov-probe -n intel-vla-training --timeout=300s
oc exec -n intel-vla-training ov-probe -- pip install --quiet numpy pillow urllib3

NS=intel-vla-training
oc cp probe_openvocab.py $NS/ov-probe:/work/probe_openvocab.py
oc cp clip_tokens.json   $NS/ov-probe:/work/clip_tokens.json
oc cp ../../../obstruction-detector/test-images/aisle3_pallet.jpg $NS/ov-probe:/work/aisle3_pallet.jpg
oc cp ../../../obstruction-detector/test-images/aisle3_empty.jpg  $NS/ov-probe:/work/aisle3_empty.jpg

oc exec -n $NS ov-probe -- python /work/probe_openvocab.py 5
oc exec -n $NS ov-probe -- env MAX_SEG=5 python /work/probe_openvocab.py 3   # segment sweep
```

Run **from inside the cluster**. Measuring over `oc port-forward` puts a home-broadband
round trip on a multi-megabyte body and tells you nothing about cluster latency.

### 5. Reproduce the root-cause benchmarks

```bash
oc exec -n $NS ov-probe -- python /work/bench_transport.py <predictor-pod-ip>  # JSON vs binary, Service vs pod IP
oc exec -n $NS ov-probe -- python /work/bench_http_clients.py                  # requests vs urllib3 vs http.client
```

`bench_transport.py` reads OVMS's Prometheus counters and diffs them across a known request
count, so server-side time is measured by the server rather than inferred. It needs
`--metrics_enable` on the ServingRuntime (already set in `manifests/02-serving.yaml`).

## Files

| File | Purpose |
|---|---|
| `probe_openvocab.py` | The pipeline: FastSAM segment → NMS → crop → CLIP label → obstruction decision. Binary transport, urllib3. `MAX_SEG` env var sets the segment cap. |
| `bench_transport.py` | JSON vs binary transport; ClusterIP Service vs pod IP; OVMS server-side counters. |
| `bench_http_clients.py` | `requests` vs `urllib3` vs `http.client` on an identical payload. |
| `clip_tokens.json` | The 8 warehouse prompts, pre-tokenised, so the probe needs no tokenizer in-cluster. |
| `manifests/` | Namespace, PVCs, loader pod, ServingRuntime, two InferenceServices, probe pod. |
| `results-2026-09-30.json` | Full measurements, ruled-out hypotheses, serving gotchas, known gaps. |

## Gotchas worth knowing before you repeat this

- **OVMS inlines outputs you don't request as binary.** Asking for only `out_0` produced a
  17.86 MB JSON-padded response (1 923 ms) versus 9.71 MB (958 ms) with both requested
  binary. Request everything binary and discard what you don't need.
- **`pvc://` + RWO deadlocks rolling updates.** The new pod cannot attach while the old one
  holds the volume. Scale to 0 and back up, or use RWX/S3.
- **FastSAM's IR has unnamed output tensors** locally; OVMS names them on load. The
  mask-prototype output is confusingly called `input`.
- **CLIP's IR is ~605 MB** — the 1 Gi predictor limit from Task 4.1 will OOM it.

## Known gaps

Still only 2 demo frames, against an agreed set of ≥10. An 80% gate is not meaningfully
testable on 2 samples — which applies to the Task 4.1 result just as much as this one.
No false-positive rate, no Cosmos baseline, and CPU-only (this cluster has no GPU nodes).
