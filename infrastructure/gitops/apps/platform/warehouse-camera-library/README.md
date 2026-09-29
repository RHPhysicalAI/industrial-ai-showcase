# warehouse-camera-library

Phase-1 image library backing the companion-side fake-camera service. Per ADR-027 step 6.

## What it is

A single-replica SeaweedFS `mini` instance in `warehouse-data`, with one bucket (`warehouse-camera-library`) holding the AI-generated photorealistic warehouse frames used by the demo. The target image is `docker.io/chrislusf/seaweedfs:4.48` with a `5Gi` RWO PVC and an S3-only `seaweedfs` Service on port `8333`.

This describes the 2026-09-29 migration target. The shared base passed the isolated [S3 canary](../../../../../tools/object-storage/VALIDATION.md). Existing stores are upstream-managed and shared; follow the [controlled copy/cutover guide](../../../../../tools/object-storage/README.md) before migrating live data or consumers.

- `aisle3_empty.jpg` — clean baseline (camera sees no obstruction).
- `aisle3_pallet.jpg` — obstructed state (Drop Pallet button target).

## Storage ownership

The warehouse library has its own namespace and lifecycle, independent of MLflow artifacts and observability data. The existing live stores may serve other consumers; migrating this repository does not authorize their removal.

## Contents

- `kustomization.yaml` references the shared `infrastructure/gitops/components/seaweedfs/` base (`deployment.yaml`, `service.yaml`, `pvc.yaml`, `networkpolicy.yaml`). Its `5Gi` capacity and `s3-credentials` Secret name are already the warehouse defaults, so no capacity or credential-name patch is needed here.
- A `VaultStaticSecret` projects Vault mount `kv`, path `warehouse/s3`, into `warehouse-data/s3-credentials` with keys `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`. Seed values out of band; no credentials belong in Git.
- `bucket-init-job.yaml` — Argo CD `Sync` hook in wave `1`, using `public.ecr.aws/aws-cli/aws-cli:2.34.0`, bounded retries, and a 600-second timeout. It waits for S3 readiness, checks/creates the bucket with `aws s3api head-bucket` / `create-bucket`, and uploads the generated `warehouse-camera-frames` ConfigMap with `aws s3 cp`.

## Adding / changing frames

Update or add JPEGs under `workloads/obstruction-detector/test-images/` (the canonical frame source), update `kustomization.yaml`'s `configMapGenerator` to include the new file, re-sync. The `bucket-init-job` re-runs and overwrites.

## Build notes

`kustomize build --load-restrictor=LoadRestrictionsNone …/warehouse-camera-library/` — same reason as `scene-pack-builder`: lets kustomize read the JPEG sources from their canonical location outside this kustomization root.

## Consumer contract

S3 tooling accesses the bucket through `http://seaweedfs.warehouse-data.svc.cluster.local:8333` using `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` from `s3-credentials`. Use signed AWS CLI / SDK requests; this is not a public image endpoint.

The current fake-camera image reads its baked-in `/frames/` copies, as described in [its README](../../../../../workloads/fake-camera/README.md). The bucket provides the corresponding S3 library for browsing and staging; updating it alone does not update an already-built camera image. Frame names come from `warehouse-topology.yaml`'s `cameras.*.frame_library`, which maps scenario state to filename.
