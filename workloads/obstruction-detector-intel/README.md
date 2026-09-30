t# obstruction-detector-intel

**Intel variant** of the obstruction detector using **YOLOv8 OpenVINO** instead of NVIDIA Cosmos Reason.

## Overview

Consumes `warehouse.cameras.aisle3` events (base64 JPEG frames), runs YOLOv8 object detection via KServe/OVMS, and emits `fleet.safety.alerts` on obstruction state change.

## Architecture

```
Kafka (camera.frames) → obstruction-detector-intel → YOLOv8 KServe → Kafka (safety.alerts)
```

### Components

- **YOLOv8m OpenVINO IR**: Object detection model (80 COCO classes)
- **OVMS (OpenVINO Model Server)**: Inference runtime via KServe
- **FastAPI**: Health probes for K8s liveness/readiness
- **Kafka**: Event ingestion and emission

## Model Details

- **Model**: YOLOv8m (medium variant)
- **Format**: OpenVINO IR (.xml + .bin)
- **Input**: 640x640 RGB image (normalized, NCHW format)
- **Output**: Detections with bounding boxes and class probabilities
- **Obstruction Classes**: person, bicycle, car, motorcycle, truck, chair, couch, potted plant, backpack, suitcase, handbag

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SERVICE_NAME` | Service name for logging | `obstruction-detector-intel` |
| `LOG_LEVEL` | Log level | `INFO` |
| `KAFKA_BOOTSTRAP_SERVERS` | Kafka brokers | `kafka-cluster-kafka-bootstrap.kafka:9092` |
| `FRAMES_TOPIC` | Camera frames topic | `warehouse.cameras.aisle3` |
| `ALERTS_TOPIC` | Safety alerts topic | `fleet.safety.alerts` |
| `CONSUMER_GROUP` | Kafka consumer group | `obstruction-detector-intel` |
| `YOLO_ENDPOINT_URL` | YOLOv8 KServe endpoint | `http://yolov8-detector-predictor.intel-vla-training.svc:8081` |
| `YOLO_MODEL` | Model name | `yolov8m-openvino` |
| `YOLO_REQUEST_TIMEOUT_S` | Inference timeout | `10.0` |
| `DWELL_FRAMES` | Frames before state change | `2` |
| `AISLE_ID` | Aisle identifier | `aisle-3` |

## Building

The container is built via OpenShift BuildConfig from the main repo:

```bash
oc start-build obstruction-detector-intel -n intel-vla-training --follow
```

## Deployment

Deployed via GitOps from `infrastructure/gitops/apps/workloads/obstruction-detector-intel/`:

```bash
oc apply -k infrastructure/gitops/apps/workloads/obstruction-detector-intel/
```

## Health Checks

- `GET /healthz` - Always returns `200 OK` if server is running
- `GET /readyz` - Returns `200` if background Kafka consumer is running, `503` otherwise

## Development

```bash
# Create venv
python3.12 -m venv .venv
source .venv/bin/activate

# Install in editable mode
pip install -e .
pip install -e ../../common/python-lib

# Run locally (requires Kafka and YOLOv8 endpoint)
python -m obstruction_detector_intel.main
```

## Testing

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/

# Type checking
mypy src/

# Linting
ruff check src/
```

## Performance (measured 2026-09-29 — both gates FAIL)

Measured on-cluster, not projected. Full method, environment and counterexamples
in `docs/13-intel-task4-validation-report.md`.

| Metric | Gate | Measured | Result |
|---|---|---|---|
| Detection accuracy | ≥ 80% | 50% on the demo frames (1/2) | **FAIL** |
| Latency (`YoloClient.reason()` entry→return, excl. Kafka) | < 500 ms | 6 619 – 9 509 ms median | **FAIL (13–21×)** |

The accuracy failure is structural, not a tuning problem: YOLOv8 is a
closed-vocabulary COCO-80 detector and a warehouse pallet is not a COCO class.
The latency is dominated by JSON float (de)serialisation of the `[1, 84, 8400]`
output tensor, not by OpenVINO inference.

**Task 4.1 recommendation is NO-GO**; the open-vocabulary successor is Task 4.2
(FastSAM + CLIP). This workload stays in-tree as the working reference for the
KServe/OVMS serving path, which does work end to end.

## Related

- **NVIDIA variant**: `workloads/obstruction-detector/` (Cosmos Reason 2-8B)
- **Validation report**: `docs/13-intel-task4-validation-report.md`
- **Architecture**: `docs/10-intel-variant-architecture.md`