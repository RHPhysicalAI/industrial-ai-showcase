# apps/isaac-sim

Standalone Isaac Sim deployment for the Phase-1 demo pipeline. The default showcase mode loads the warehouse scene from the Isaac asset CDN, subscribes to Kafka for live twin updates (forklift pose + pallet obstruction), and serves an MJPEG viewport stream to the Showcase Console.

**Phase**: 1 (plan item 3).

## Why standalone (not KAS)

KAS (Kit App Streaming, in `apps/workloads/kit-appstreaming/`) manages on-demand Kit sessions and is useful for tinkering, multi-viewer WebRTC, and troubleshooting the streaming pipeline. But KAS-managed pods are constrained by the ApplicationProfile — injecting custom env vars (Nucleus auth, Kafka bootstrap, pallet asset URLs) and pip-installing `confluent-kafka` at startup is awkward through that layer.

The standalone Deployment gives full control over the pod spec: env vars from Vault secrets, startup commands, extra ports, volume mounts. For the Phase-1 demo pipeline — where a single always-on Kit process needs Kafka consumers, Nucleus scene-pack auth, and an MJPEG broadcaster — this is the simpler path.

Both share the same scenario scripts (`workloads/isaac-sim/scenarios/`). The standalone deployment also falls back to the CDN warehouse when `SCENE_PACK_URL` is unset. A Nucleus-backed scene-pack can be enabled through a site overlay after the Isaac Sim/Nucleus client compatibility has been validated.

## What's here

- `namespace.yaml` — `isaac-sim` namespace, PSA=privileged + SCC-sync disabled (Isaac Sim runs as root).
- `vault-auth.yaml` + `vault-static-secret-ngc.yaml` — Vault-backed NGC API key.
- `vault-static-secret-nucleus.yaml` — Vault-backed Nucleus credentials for scene-pack auth.
- `ngc-pullsecret-render-job.yaml` — Argo pre-sync hook that renders `ngc-pull-secret`.
- `serviceaccount.yaml` + `scc-anyuid-binding.yaml` — SA + anyuid grant.
- `pvc.yaml` — two PVCs: 50 Gi shader/asset cache, 10 Gi logs.
- `deployment.yaml` — single-replica Deployment (Recreate strategy), L40S GPU, pip-installs `confluent-kafka` at startup, env vars for Nucleus + Kafka + pallet asset.
- `service.yaml` — ClusterIP: WebRTC (8011, 49100) + MJPEG (8090).
- `networkpolicy.yaml` — permissive egress (Phase 1); ingress scoped to fleet-ops / openshift-ingress / cluster-monitoring.
- `kustomization.yaml` — uses `configMapGenerator` to build the scenarios ConfigMap from `workloads/isaac-sim/scenarios/` (requires `--load-restrictor=LoadRestrictionsNone`).

## Kit startup

Startup command pip-installs `confluent-kafka`, then runs `runheadless.sh` with WebRTC enabled and `--exec /scenarios/warehouse_baseline.py`. The scenario:

1. Registers Nucleus auth callback (from `NUCLEUS_USER`/`NUCLEUS_PASS` env vars)
2. Opens the scene-pack overlay from `SCENE_PACK_URL` (or falls back to the CDN warehouse)
3. Starts two Kafka consumer daemon threads:
   - `fleet.telemetry` — moves `/World/Robots/fl_07` to reported pose each tick
   - `fleet.safety.alerts` — shows/hides pallet prim at aisle-3 obstruction position
4. Chains `viewport_mjpeg.py` (MJPEG on port 8090) and camera orbit

## Cold start

First boot compiles shaders for every USD asset referenced by the scene; this is CPU + GPU heavy and can take 5-10 minutes. The `confluent-kafka` pip install adds ~30 seconds. The readiness probe targets the HLS/MJPEG listener and its failure budget still covers a full cold start.

## Known rough edges

- **Image pull is huge**: `nvcr.io/nvidia/isaac-sim` is ~20 GB. First pull on a cold node takes a long time.
- **pip install needs network**: `confluent-kafka` is fetched from PyPI at startup. Air-gapped deployments would need a pre-built image or vendored wheel (Phase 2).
- **Nucleus-backed scene-pack**: this is an opt-in overlay. The Hub currently runs Nucleus 2023.2.9 while the showcase uses Isaac Sim 6.0; validate the client/server compatibility before enabling it. The default CDN path keeps the showcase runnable while that compatibility work is open.
- **Readiness**: the demo route serves HLS/MJPEG on port 8090, so readiness and liveness probe that listener rather than the optional WebRTC listener.
