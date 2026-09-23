# fake-camera

Companion-side "on-site" warehouse camera. Per ADR-027 step 7.

## What it does

Publishes the currently-selected JPEG frame to `warehouse.cameras.aisle3` at 1 Hz (configurable). HTTP `POST /state {"state": "<name>"}` switches which frame is emitted — that's the mechanism behind the Console's **Drop Pallet** button in the demo narrative.

The Phase-1 frame library is baked into the container image at `/frames/`. JPEG sources live under `workloads/obstruction-detector/test-images/` (same pair the Cosmos Reason 2-8B trial was validated with, also present in the hub MinIO `warehouse-camera-library` for operator browsing).

## Why not stream from an actual camera

The Session-18 demo story is "on-site edge captures real camera frames, hub-side VLM perception flags obstructions." There is no physical warehouse in our lab; fake-camera stands in for the real thing with *photorealistic* AI-generated frames. The twin-vs-reality visual split (clean USD twin vs grimy photo frames) is intentional and realistic — that's how real digital-twin deployments look.

## Deployment target

**Companion cluster**, namespace `warehouse-edge` (Phase-1). The fake-camera pod connects outbound to the hub's Kafka external listener (TLS over port 443 Route) to publish frames. No MirrorMaker2 required — the edge is a direct producer to the hub cluster's `warehouse.cameras.*` topic. A Phase-2+ upgrade to a per-site Kafka + MM2 would bring queuing at the edge for connectivity lapses; Phase-1 simplicity keeps that deferred.

## Consumer

`workloads/obstruction-detector/` on the hub consumes `warehouse.cameras.aisle3` and calls Cosmos Reason 2-8B. See its README for the rest of the pipeline.

## Env contract

| Var | Default | Purpose |
|---|---|---|
| `KAFKA_BOOTSTRAP_SERVERS` | (required) | Hub's external Route bootstrap, e.g. `fleet-kafka-bootstrap-fleet-ops.apps.<cluster>:443` |
| `KAFKA_SECURITY_PROTOCOL` | `SSL` | `SSL` for external Route, `PLAINTEXT` for in-cluster (hub-local dev) |
| `KAFKA_CA_CERT_PATH` | `/etc/kafka/ca.crt` | Path to the Strimzi cluster CA cert (mounted from secret) |
| `TOPIC` | `warehouse.cameras.aisle3` | Target topic |
| `CAMERA_ID` | `cam-aisle-3` | Matches key in warehouse-topology.yaml cameras.* |
| `AISLE_ID` | `aisle-3` | Logical aisle this camera watches |
| `FRAMES_DIR` | `/frames` | Container path the image library is baked into |
| `FRAME_MAP_JSON` | `{"empty":"aisle3_empty.jpg","obstructed":"aisle3_pallet.jpg"}` | Logical state → filename |
| `INITIAL_STATE` | `empty` | State on startup |
| `PUBLISH_HZ` | `1.0` | Frame rate |
| `HTTP_PORT` | `8085` | Control endpoint port |

## HTTP API

- `GET /healthz` — liveness, returns `{"status":"ok","version":...}`
- `GET /readyz` — returns `ready` only while the publish loop is running
- `GET /state` — current state name
- `POST /state {"state":"obstructed"}` — switches emitted frame; 400 if unknown state

The command consumer uses a fresh per-process group and starts at the live tail, so restarting the service does not replay retained historical camera commands.

## Deploy

GitOps manifests at `infrastructure/gitops/apps/companion/fake-camera/`. Target companion kubeconfig:

```
KUBECONFIG=~/.kube/companion.kubeconfig kustomize build \
  infrastructure/gitops/apps/companion/fake-camera/ | oc apply -f -
oc start-build -n warehouse-edge fake-camera --from-dir=. \
  --kubeconfig=~/.kube/companion.kubeconfig
```

Requires a CA cert secret + a bootstrap pointing at hub's external Route — see the deployment manifest + namespace README for one-time setup.
