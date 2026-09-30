# Task 4.1 Validation Report — YOLOv8 OpenVINO Obstruction Detection

**Status:** Complete — recommendation is **NO-GO on Task 4.1 as the warehouse obstruction detector; proceed to Task 4.2 (FastSAM + CLIP)**
**Date of measurement:** 2026-09-29
**Phase / workstream:** Intel variant, Task 4.1 — YOLOv8m OpenVINO perception baseline (architecture context in `docs/10-intel-variant-architecture.md`)
**Disposition:** Pending lead sign-off (see [Lead disposition](#lead-disposition))

**Agreed acceptance gates, as set when Task 4.1 was scoped:** detection accuracy **≥ 80%** on the agreed input set, and Loop 1 end-to-end latency **< 500 ms**. The agreed go/no-go rule was likewise fixed in advance: **accuracy below 80% means YOLOv8 is not the warehouse detector and the team proceeds to Task 4.2 (open-vocabulary FastSAM + CLIP)**. Both gates and the decision rule are restated here verbatim so this report stands alone as the record.

---

## 1. Summary

The Task 4.1 pipeline is **operationally complete**: YOLOv8m OpenVINO IR is served by OpenVINO Model Server under KServe on the OSD hub, and the detector consumes `warehouse.cameras.aisle3` and emits to `fleet.safety.alerts` end to end. Infrastructure is not the blocker.

Both agreed acceptance gates **fail** on the workload we actually care about:

| Gate | Agreed threshold | Measured | Result |
|---|---|---|---|
| Detection accuracy | ≥ 80% | 100% on COCO-object images (3/3); **50% on the demo frames (1/2)** | **FAIL** |
| End-to-end latency (Loop 1) | < 500 ms | **6 619 – 9 509 ms median** | **FAIL (13–21×)** |

The accuracy failure is not a tuning problem. YOLOv8 is a closed-vocabulary COCO-80 detector, and the primary obstruction in the demo scenario — a warehouse pallet — is not a COCO class. No confidence-threshold change, no larger YOLOv8 variant, and no preprocessing fix can make a COCO detector emit a class it was never trained on. This is the precise failure mode Task 4.2 (open-vocabulary FastSAM + CLIP) exists to address.

---

## 2. Test environment

Recorded so another engineer can judge whether their numbers are comparable.

**Serving (OVMS predictor)**

| Item | Value |
|---|---|
| Platform | OpenShift Dedicated hub, RHOAI 3.4.0 EA1 |
| Node kernel / OS | `5.14.0-570.113.1.el9_6.x86_64` / RHEL CoreOS 9.6.20260510-0 |
| Kubelet | v1.34.7 |
| Node instance type | AWS `m5.2xlarge`, 8 vCPU |
| CPU | Intel Xeon Platinum 8259CL @ 2.50 GHz (Cascade Lake) |
| Accelerator | **None — CPU inference only** |
| Pod resources | requests 2 CPU / 4 Gi; limits 4 CPU / 8 Gi |
| Runtime | OpenVINO Model Server 2026.4.0.869b2186a |
| OpenVINO backend | 2026.4.0-22959 |
| Runtime image | `docker.io/openvino/model_server:latest` — see [§6 Support status](#6-support-status) |
| Deployment mode | KServe `RawDeployment` |

**Model**

| Item | Value |
|---|---|
| Model | YOLOv8m, OpenVINO IR, FP32 |
| Input | `x.1`, FP32, `[1, 3, 640, 640]` |
| Output | `out_0`, FP32, `[1, 84, 8400]` (4 bbox + 80 class scores, **no NMS in-graph**) |
| Model `rt_info` | `resize_type=fit_to_window_letterbox`, `pad_value=114`, `scale_values=255`, `reverse_input_channels=YES` |
| Storage | S3/MinIO, `s3://models/yolov8m` (OVMS resolves version dir `1/`) |

**Client (detector)**

| Item | Value |
|---|---|
| Image | `obstruction-detector-intel@sha256:1a9aec35…` |
| Pod resources | requests 250m CPU / 512 Mi; limits **500m CPU** / 1 Gi |
| Protocol | KServe v2 REST, JSON tensors (`POST /v2/models/yolov8-detector/infer`) |
| Confidence threshold | 0.5 (`yolo_client.py`) |
| Debounce | `DWELL_FRAMES=2` |

---

## 3. Quality results

### 3.1 Per-image outcomes

All rows produced by the real `YoloClient.reason()` path inside the detector pod against the in-cluster OVMS endpoint — not a local or simulated harness.

| Image | Provenance | Dimensions | Verdict | Confidence | Ground truth | Correct? |
|---|---|---|---|---|---|---|
| `warehouse_1.jpg` | COCO val2017 `000000000285` | 586 × 640 | clear | — | bear (0.958) — not an obstruction class | ✅ TN |
| `warehouse_2.jpg` | COCO val2017 `000000000632` | 640 × 483 | **obstructed** — chair | 0.9197 | chair / potted plant / bed | ✅ TP |
| `warehouse_3.jpg` | COCO val2017 `000000001000` | 640 × 480 | **obstructed** — person | 0.9301 | person (0.932) | ✅ TP |
| `aisle3_pallet.jpg` | `fake-camera` demo asset | 1920 × 1080 | clear | — | **pallet — the designated obstruction** | ❌ **FN** |
| `aisle3_empty.jpg` | `fake-camera` demo asset | 1920 × 1080 | clear | — | empty aisle | ✅ TN |

- **Demo frames (`fake-camera` assets): 1/2 (50%)** — below the ≥80% gate. **These are the frames the gate is about.**
- **COCO val2017 images: 3/3 (100%)** — but read this narrowly. Despite the `warehouse_*.jpg` filenames these are **not warehouse scenes**; they are COCO val2017 validation images that the original Task 4.1 setup steps downloaded and renamed to `warehouse_*.jpg` (IDs in §5). `warehouse_1.jpg` is a bear. Scoring 3/3 by running a COCO-trained model against COCO validation images is close to tautological: it confirms the **serving path is wired correctly end to end**, and nothing about warehouse perception capability. It is a smoke test, not an accuracy result.

> ⚠️ An earlier draft of this report described `warehouse_1..3.jpg` as "generic warehouse scenes". That was wrong. The filenames are misleading and the provenance above is the correct reading.

### 3.2 The counterexample that decides the gate

`aisle3_pallet.jpg` is the frame the `fake-camera` workload serves in its `obstructed` state (`workloads/fake-camera/src/fake_camera/settings.py`). It contains a pallet. `pallet` is not one of the COCO-80 classes, so no detection clears the 0.5 threshold and the detector reports `clear`.

**This was confirmed live, not just in the probe harness.** With `fake-camera` held in `obstructed` state, the running pipeline emitted `clear` on every frame:

```json
{"camera_id": "cam-aisle-3", "obstructed": false, "confidence": 1.0,
 "label": "clear", "event": "frame.reasoned",
 "timestamp": "2026-09-29T18:50:24.650723Z"}
```

A safety detector that silently reports "clear" while an obstruction is present is the worst failure direction for Loop 1. This is a blocking defect, not a tuning gap.

### 3.2a The detector cannot stay running in steady state

Discovered after the initial write-up, and it is a consequence of §4, not an unrelated bug.

The detector enters **CrashLoopBackOff** on its own, with no test harness attached. The sequence, from the pod's own logs and events:

1. Frames are consumed and inferred correctly (`HTTP/1.1 200 OK`, `frame.reasoned` every ~4.7 s).
2. Detection parsing is **synchronous CPU-bound work on the asyncio event loop** — ~706 K floats decoded from JSON via numpy, taking seconds.
3. Both probes are configured `timeoutSeconds: 1`. While the loop is blocked, `/healthz` cannot answer inside 1 s.
4. Three consecutive failures → `Container detector failed liveness probe, will be restarted` → SIGTERM, graceful exit 0 → restart → repeat.

Observed: 7 restarts in 22 minutes. Exit code 0 throughout, which is why this initially looked benign — it is a liveness kill, not a crash.

**Why it matters for the gate:** inference latency does not merely exceed the 500 ms target, it exceeds the liveness probe budget by enough that the workload is **not viable as a long-running service** in its current configuration. A perception service that restarts every ~80 seconds drops frames on every restart.

Two independent things would need to change to make this path viable: moving tensor parsing off the event loop (or to gRPC/binary tensors), and raising the probe timeouts. Both are tractable — and both are work on a path §7 recommends abandoning.

> An earlier turn of this investigation attributed these restarts to the validation probe competing for CPU. That was wrong: the restarts continue with no probe running.

### 3.3 Other observations

**`confidence: 1.0` on clear verdicts is cosmetic, not a measurement.** The `clear` branch of `yolo_client.py` returns a hardcoded `1.0`. It does not represent model confidence and should not be read as one. Worth fixing so logs are not misleading, tracked separately from the gate decision.

**Preprocessing mismatch is real but not material.** `yolo_client.py` uses a naive stretch resize to 640×640, while the model's `rt_info` asks for `fit_to_window_letterbox` with pad 114. Testing both variants against the same endpoint: `warehouse_2.jpg` scored 0.9197 (stretch) vs 0.9109 (letterbox). The mismatch is a correctness wart worth fixing, but it does not change any verdict and does not explain the false negative.

**`YOLO_MODEL` env var is inert.** `yolo_client.py` hardcodes the model name in the request URL, so `YOLO_MODEL=yolov8m-openvino` in the deployment has no effect. Cosmetic; flagged to avoid a future engineer trusting it.

---

## 4. Latency results

### 4.1 Declared measurement boundary

**Entry to return of `YoloClient.reason(image_b64)`**, measured with `time.perf_counter()` inside the detector pod. That span covers JPEG decode → preprocess → KServe v2 REST round-trip → detection parse. It **excludes** Kafka consume/produce, so true camera-to-alert latency is somewhat higher than the figures below. Three runs per image; median reported.

### 4.2 Measurements

Two independent sessions, the second run with the committed `probe.py` verbatim as a reproduction check.

| Image | Session | Run 1 (ms) | Run 2 (ms) | Run 3 (ms) | Median (ms) |
|---|---|---|---|---|---|
| `warehouse_3.jpg` | first | 4 714 | 6 956 | 11 219 | **6 956** |
| `warehouse_3.jpg` | repro | 7 121 | 9 380 | 8 088 | **8 088** |
| `aisle3_pallet.jpg` | first | 6 708 | 6 619 | 6 619 | **6 619** |
| `aisle3_pallet.jpg` | repro | 10 295 | 8 302 | 9 509 | **9 509** |
| `aisle3_empty.jpg` | first | 7 811 | 9 591 | 9 908 | **9 591** |
| `aisle3_empty.jpg` | repro | 6 975 | 6 785 | 6 521 | **6 785** |

**Against the < 500 ms Loop 1 gate: 13–21× over. FAIL.**

Run-to-run spread is wide (6.5–10.3 s on the same image) — consistent with CPU contention on a 500m-limited pod rather than a stable inference cost. Verdicts and confidences were **bit-identical across sessions** (`person` @ 0.9301 both times); only latency varied.

### 4.3 Where the time goes

This is **not** OpenVINO inference cost. YOLOv8m on this class of Xeon is normally tens of milliseconds. The cost is transport and client-side compute:

1. **JSON tensor serialization.** KServe v2 REST sends 1 × 3 × 640 × 640 = **1 228 800 float32 values as a JSON array**, and the response carries 1 × 84 × 8400 = **705 600 floats** back (~6.6 MB gzipped response observed). Encoding and parsing these in Python dominates the measurement.
2. **The detector pod is capped at 500m CPU.** Half a core doing JSON float parsing on ~700k values is the single biggest contributor.

Both are fixable — gRPC or binary v2 extension instead of JSON, and a higher CPU limit — and would likely bring this into the hundreds of milliseconds. **But fixing latency does not fix the accuracy gate**, so this work is not worth doing on the YOLOv8 path.

> ⚠️ An earlier informal note circulated a "~500 ms" figure for this pipeline. That number was an unmeasured estimate and should be disregarded. The table above is the first properly instrumented measurement.

---

## 5. Reproducing this result

Another engineer can repeat the measurement as follows.

**Prerequisites:** `oc` logged in to the hub with access to `intel-vla-training`; the `yolov8-detector` InferenceService Ready; the `obstruction-detector-intel` deployment running.

```bash
NS=intel-vla-training
POD=$(oc get pods -n $NS -l app=obstruction-detector-intel -o name | head -1 | cut -d/ -f2)

# 1. Confirm the model is loaded and inspect its expected I/O + rt_info
PRED=$(oc get pods -n $NS -l serving.kserve.io/inferenceservice=yolov8-detector -o name | head -1)
oc exec -n $NS $PRED -c kserve-container -- \
  curl -s http://localhost:8081/v2/models/yolov8-detector

# 2. Stage the probe and the test frames in the detector pod
oc cp workloads/obstruction-detector-intel/validation/probe.py $NS/$POD:/tmp/probe.py
oc exec -n $NS $POD -- mkdir -p /tmp/testimg
oc cp <your-image>.jpg $NS/$POD:/tmp/testimg/<your-image>.jpg

# 3. One image per invocation (the pod's 1Gi limit will not survive batching)
oc exec -n $NS $POD -- python /tmp/probe.py /tmp/testimg/<your-image>.jpg
```

Each invocation prints a single JSON line with verdict, confidence, three run latencies, and the median.

**Live end-to-end check of the false negative:**

```bash
CAM=$(oc get pods -n fleet-ops -l app=fake-camera -o name | head -1 | cut -d/ -f2)

# Hold the camera on the pallet frame
oc exec -n fleet-ops $CAM -- curl -s -X POST http://localhost:8085/state \
  -H 'Content-Type: application/json' -d '{"state":"obstructed"}'

sleep 20
oc logs -n intel-vla-training deployment/obstruction-detector-intel --since=20s \
  | grep frame.reasoned | tail -3
# Expected (the defect): every line shows "obstructed": false, "label": "clear"
```

**Sample data.**

- `warehouse_1..3.jpg` are **COCO val2017 images** (`000000000285`, `000000000632`, `000000001000`), downloaded and renamed by the original Task 4.1 setup steps. The `warehouse_` prefix is a misnomer — none of them depicts a warehouse. Retrievable from `images.cocodataset.org/val2017/<id>.jpg`. COCO images are sourced from Flickr under per-image terms; **dataset licensing has not been vetted for redistribution and is a human review item** (`docs/licensing-gates.md`). They are therefore referenced by ID here, not committed to the repo.
- `aisle3_pallet.jpg` / `aisle3_empty.jpg` are baked into the `fake-camera` workload image at `/frames/` and are the authoritative demo inputs. Pull them with `oc cp fleet-ops/<cam-pod>:/frames/aisle3_pallet.jpg ./`.
- No customer imagery or PII was used.

**Representative outputs** are committed at `workloads/obstruction-detector-intel/validation/results-2026-09-29.json`, including per-run latencies, ground truth, and TP/TN/FN classification for all five images.

**Note on the detector pod's `/tmp`.** It is wiped on restart, so staged assets must be re-copied after any pod recycle.

---

## 5a. Limitations of this validation

Stated plainly so the lead can weigh how much the recommendation rests on.

| # | Limitation | Effect on the recommendation |
|---|---|---|
| 1 | **Only 5 images tested; the agreed minimum was 10.** Of those 5, only 2 are demo frames. | The 50% demo-frame figure rests on a 2-image denominator. **Weakens the precision of the number, not the conclusion** — the conclusion rests on the *structural* argument in §3.2 (pallet ∉ COCO-80), which more images cannot change. |
| 2 | **The latency gate is specified end-to-end (camera → alert); the measured boundary excludes Kafka.** True E2E is *higher* than reported. | None. The measured subset is already 13–21× over budget, so the gate fails a fortiori. |
| 3 | **No false-positive rate characterised.** 5 images cannot support an FP estimate; zero FPs were observed but that is not evidence of a low rate. | Unaddressed gap. Does not affect the NO-GO, but Task 4.2 should establish an FP baseline properly. |
| 4 | **Cosmos Reason 2-8B baseline not run.** | The Intel-vs-NVIDIA comparison this task was meant to inform is still unanswered. Independent of the 4.1/4.2 decision. |
| 5 | **Three runs per image, two sessions, no concurrency.** No p95/p99, no load behaviour. | Sufficient for a 13–21× miss; insufficient for capacity planning. |
| 6 | Detector probes flapped throughout measurement and the pod restarted repeatedly. **This was initially and wrongly attributed to the probe script competing for the 500m CPU limit; the restarts continued with nothing attached.** Root cause was event-loop blocking (§3.2a), fixed after measurement by widening the probe budgets. | Latency figures were taken from inside `YoloClient.reason()` and are unaffected by the restarts. The fix changed probe timeouts only — no code path touched — so the numbers still stand. |

**What would change the recommendation:** evidence that the demo obstruction vocabulary is in fact COCO-expressible, or a decision to redefine the demo scenario around COCO classes. Neither is currently true.

---

## 6. Support status

**Distinguishing what we observed from what is vendor-supported — these are not the same thing.**

| Component | Status |
|---|---|
| RHOAI 3.4.0 EA1, KServe `RawDeployment` | Red Hat **Early Access**. EA terms, not GA support. |
| OpenVINO Model Server runtime image | `docker.io/openvino/model_server@sha256:11d3acf` — **upstream community image, not a Red Hat-shipped or Red Hat-supported artifact.** Measurements were taken against this digest; it ran as `:latest` at measurement time and was pinned to the same build afterwards. |
| YOLOv8m OpenVINO IR weights | Upstream model. Licensing not vetted — see `docs/licensing-gates.md`. **Human review item.** |
| CPU-only inference on `m5.2xlarge` | Observed to work. Not a performance-validated or vendor-sized configuration. |

Items that carry forward regardless of the Task 4.1 / 4.2 decision:

1. ~~The `:latest` tag must be pinned to a digest.~~ **Done** (commit `75fda9f`) — pinned to `sha256:11d3acf`. `:latest` is not reproducibly mirrorable and violated the repo's air-gap constraint.
2. **The MinIO credential used by the storage-initializer is a known placeholder pending rotation.** It is held cluster-side only and is deliberately not committed to this repo. **Still open — human item.**
3. **YOLOv8m weight licensing is unvetted.** Blocks redistribution, not experimentation. **Still open — human item.**

---

## 7. Recommendation

**NO-GO on Task 4.1 as the warehouse obstruction detector. Proceed to Task 4.2 (FastSAM + CLIP).**

This follows the go/no-go rule agreed when Task 4.1 was scoped (restated at the head of this report): *accuracy < 80% → proceed to Task 4.2*. The rule was fixed **before** measurement, so this recommendation applies a pre-agreed criterion rather than rationalising the result after the fact.

Rationale:

1. **Accuracy gate fails on the frames that matter, for a structural reason.** 50% on the demo frames vs the ≥80% gate. The cause is closed-vocabulary COCO-80, and pallets, crates, spills, and debris — the actual warehouse obstruction vocabulary — are not in it. The listed remediations (lower confidence threshold, YOLOv8l) cannot fix a missing class, so `REFINE` is not a viable branch here.
2. **Latency gate fails by 13–21×.** Fixable via gRPC/binary tensors and a higher CPU limit, but not worth the engineering spend on a path we are not keeping.
3. **The failure direction is unsafe.** A false negative on a safety detector is materially worse than a false positive.

**What Task 4.1 nevertheless bought us — keep it:**

- A working KServe + OVMS serving path on RHOAI 3.4 EA1, with the S3 credential-resolution pattern solved (annotations on the Secret bound via ServiceAccount, *not* on the InferenceService).
- A working detector → Kafka → alerts pipeline that Task 4.2 can reuse by swapping the perception client.
- A measured CPU-inference baseline on Intel hardware for the Intel variant narrative.

**Proposed next actions, in order:**

| # | Action | Owner | Blocking? |
|---|---|---|---|
| 1 | Obtain lead disposition on this NO-GO | Lead | **Yes** — gates everything below |
| 2 | Begin Task 4.2 (FastSAM + CLIP open-vocabulary), reusing the serving + Kafka scaffolding | Eng | After #1 |
| 3 | Pin the OVMS runtime image to a digest (air-gap constraint) | Eng | No — but do it |
| 4 | Rotate the placeholder MinIO credential | Eng | No |
| 5 | Cosmos Reason 2-8B baseline comparison — **still not run** | Eng | No — but needed for a complete Intel-vs-NVIDIA story |
| 6 | Fix `yolo_client.py`: letterbox preprocessing, hardcoded `confidence=1.0`, inert `YOLO_MODEL` | Eng | Only if any YOLOv8 path is retained |

Items 3 and 4 are carry-forward regardless of the decision. Item 5 is an outstanding gap in the Intel variant evidence base and should be scheduled independently of the Task 4.1/4.2 outcome.

---

## Lead disposition

*To be completed by the workstream lead.*

- [ ] **Accept NO-GO** — proceed to Task 4.2
- [ ] **Override** — retain YOLOv8 path with stated rationale
- [ ] **Defer** — pending additional evidence (specify)

**Lead:**
**Date:**
**Notes:**
