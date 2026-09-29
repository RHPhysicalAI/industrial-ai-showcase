# obstruction-detector

Hub-side perception service. Consumes camera frames from `warehouse.cameras.aisle3`, calls **Cosmos Reason 2-8B** for a per-frame obstruction verdict, and publishes a `SafetyAlert` to `fleet.safety.alerts` on state change. Per ADR-027 step 8.

## What it is not

- Not the camera source. The companion-side `fake-camera` service (step 7) publishes frames; this service only consumes them.
- Not a `KServe` predictor. Cosmos Reason is served separately in `cosmos/reason-2`; we're an HTTP client over its OpenAI-compatible `/v1/chat/completions` endpoint.
- Not the consumer of alerts. That's Fleet Manager (step 9) — this service emits the alerts, not the mission reroutes.

## Pipeline

```
warehouse.cameras.aisle3   ── Kafka ──►  obstruction-detector
                                           │
                                           ▼ httpx POST /v1/chat/completions (image + prompt)
                                         cosmos-reason (vLLM, Cosmos-Reason2-8B on L40S)
                                           │
                                           ▼ parse {"obstruction": bool, ...}
                                         dwell debounce (default 2 consecutive frames)
                                           │
                                           ▼ on state transition
fleet.safety.alerts        ◄── Kafka ──  SafetyAlert
```

## Key design points

- **JSON-on-the-wire.** The frame envelope (`CameraFrameEvent`) carries base64 JPEG + metadata. Matches the Phase-1 JSON-over-Kafka convention; Avro lands with Schema Registry in Phase 2.
- **Dwell-based debounce.** A single-frame VLM hiccup shouldn't wake up Fleet Manager. `dwell_frames: 2` means we need two consecutive same-verdict frames before flipping state. Configurable via env.
- **Scripted-state precedence.** Fake-camera frames carry an explicit `empty` or `obstructed` state for the deterministic showcase. The detector still calls Cosmos and records its verdict, but uses that explicit state when the model disagrees so a false clear cannot undo the scripted twin update. Unknown/live states continue to use Cosmos.
- **Live-tail startup.** The detector uses a fresh per-process consumer group with `auto.offset.reset=latest`, so a restart does not resume an old backlog, replay retained historical scene states, or toggle the twin with stale alerts.
- **Cold-start OK.** Initial state is "unknown"; the first N matching frames establish a baseline silently. Only transitions emit alerts.
- **Stateful by design.** Each (camera, aisle) needs its own detector instance. Phase-1 ships one instance for aisle-3.
- **Prompt pinned to what was validated.** The prompt text comes from `workloads/obstruction-detector/trial.py` which was validated on-cluster against Cosmos Reason 2-8B using the 1920×1080 JPEG pair in `test-images/`.

## Manual trial harness

`trial.py` is kept in this directory for ad-hoc one-shot VLM checks. Usage:

```bash
oc port-forward -n cosmos svc/cosmos-reason 8000:8000 &
python3 trial.py
```

Feeds every image under `test-images/` to the running Cosmos Reason deployment and prints the parsed verdict. Used to pin the prompt + sanity-check a model swap.

## Env contract

| Var | Default | Purpose |
|---|---|---|
| `KAFKA_BOOTSTRAP_SERVERS` | (required) | Kafka cluster addr |
| `FRAMES_TOPIC` | `warehouse.cameras.aisle3` | Frame source |
| `ALERTS_TOPIC` | `fleet.safety.alerts` | Alert destination |
| `CONSUMER_GROUP` | `obstruction-detector` | Kafka consumer group |
| `AISLE_ID` | `aisle-3` | Logical aisle this instance covers |
| `COSMOS_ENDPOINT_URL` | `http://cosmos-reason.cosmos.svc.cluster.local:8000/v1/chat/completions` | vLLM OpenAI-compat endpoint |
| `COSMOS_MODEL` | `cosmos-reason-2` | Served model name |
| `COSMOS_REQUEST_TIMEOUT_S` | `20.0` | httpx timeout |
| `DWELL_FRAMES` | `2` | State-flip debounce |
| `DEFAULT_PROMPT` | (see settings.py) | Single-frame prompt |

## Deploy

GitOps manifests are at `infrastructure/gitops/apps/workloads/obstruction-detector/`.
