# nucleus-seeder

One-shot Job that mirrors the Phase-1 warehouse asset tree from the Isaac asset CDN into our Nucleus, so the environment is **air-gap-capable** from demo time onward.

Per ADR-027: `small_warehouse_digital_twin.usd` + `Forklift_A01` + pallet variants.

## How it runs

`seed.py` inside the `nvcr.io/nvidia/isaac-sim:5.0.0` container (same image used by `workloads/isaac-sim/`), invoked via `isaac-sim/python.sh`. We reuse that image so we inherit `pxr.Usd` (for walking USD references) and `omni.client` (for uploading to Nucleus) without building a separate artifact.

Co-located with its Kubernetes `Job` + `ConfigMap` in this directory (deployment glue, not a fleet workload). Run-once; `ttlSecondsAfterFinished` cleans up the pod after success.

## Stages

1. **Enumerate + download**. For each prefix in `SEED_ROOTS`, list the S3 bucket (`omniverse-content-production` / us-west-2) via anonymous HTTP `GET ?list-type=2`, then download every object preserving its Isaac-rooted path layout into `/staging`.
2. **Walk USD deps**. For every `.usd`/`.usda`/`.usdc` under `/staging`, open with `Sdf.Layer` and enumerate `GetCompositionAssetDependencies()`. Any relative ref that resolves inside `/staging` but isn't present is logged so its parent prefix can be added to `SEED_ROOTS` on a follow-up run. Remote refs (`omniverse://`, `http://`) are ignored by design.
3. **Upload to Nucleus**. Use `omni.client.copy_async` to mirror `/staging` to `omniverse://<host><NUCLEUS_ROOT>`. Target structure preserves Isaac paths so scenes that load `Isaac/Environments/Digital_Twin_Warehouse/...` resolve unchanged.

## Config (env vars)

| Var | Default | Purpose |
|---|---|---|
| `ISAAC_VERSION` | `6.0` | Isaac asset-tree version on the CDN. |
| `LOCAL_STAGING` | `/staging` | Scratch dir (emptyDir volume in the Job). |
| `NUCLEUS_HOST` | `nucleus-api.omniverse-nucleus.svc.cluster.local:3009` | Nucleus API service. In-cluster — bypasses the Route. |
| `NUCLEUS_USER` | `omniverse` | Nucleus client user in the `nucleus-passwords` Secret. |
| `NUCLEUS_PASS` | — | Pulled from `nucleus-passwords.master-password` for the `omniverse` client user. |
| `NUCLEUS_ROOT` | `/Projects/showcase/custom` | Path root for the seeded asset tree and `Warehouse_edit.usd` scene used by the standalone Isaac Sim workload. |

## Re-running

Safe to re-run — local staging is a scratch `emptyDir` so the Job re-downloads each time, and Nucleus upload uses `OVERWRITE` behavior. To expand coverage (additional forklifts, pallet variants, etc.), add prefixes to `SEED_ROOTS` and re-apply the Job.

## Air-gap posture

Once this Job has succeeded, Nucleus holds the authoritative copy of the Phase-1 asset tree. Scenes in `workloads/isaac-sim/scenarios/` must reference the `omniverse://` URL, not `get_assets_root_path_async()` (which resolves to NVIDIA's CDN). Re-pointing is tracked in ADR-027 implementation order step 5 (scene-pack overlay USD authoring).
