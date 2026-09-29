# warehouse

Topology-as-data for the Phase-1 warehouse obstruction demo. Per ADR-027, `warehouse-topology.yaml` is the single source of truth for every named location, robot, camera, and scenario that the demo references.

## Why this exists as its own file

Six components reference the same aisle / dock / approach-point / camera / forklift by name. Hard-coding coordinates in each would drift the moment we adjusted the scene. Centralizing here means "move aisle-3 by one meter" is a one-line edit + re-sync everywhere.

## Consumers

| Component | What it reads from topology |
|---|---|
| Scene-pack overlay USD (`workloads/isaac-sim/scene-pack/`) | Dock + aisle placement, approach-point marker prims, camera prims, forklift initial transform |
| `wms-stub` (`workloads/wms-stub/`) | Named `missions.*` definitions for scripted scenario emission |
| `fleet-manager` | `aisles.*.centerline` + `approach_points.*.gates_aisle` for routing; `missions.*.alternate_routes` for replan logic |
| `mission-dispatcher` (+ waypoint-planner) | `aisles.*.centerline` to emit 5 Hz pose interpolation |
| Isaac Sim twin-update subscriber | `robots.fl-07` transform source; `pallets.pallet-a47.obstruction_position` on alert |
| `obstruction-detector` | `cameras.*.publishes_topic` to know which Kafka topic → which aisle |
| `fake-camera` service | `cameras.*.frame_library` to pick the baked-in frame per commanded state; filenames match the target SeaweedFS S3 library |
| Showcase Console | `scenarios.*.buttons` for the presenter UI wiring |

## Coordinate frame

Meters, right-handed, Z-up. World origin = warehouse floor-center. Coordinates are authored **against the scene-pack overlay USD's placement of the warehouse**, not against the raw `small_warehouse_digital_twin.usd` which arrives in its own frame. Move the warehouse in the overlay and this file comes with it.

## Schema stability

- `version: 1` at the root — bump + add migration notes here if a schema change breaks consumers.
- Logical asset ids (e.g. `nvidia/Forklift_A01`) are resolved to `omniverse://` URLs by each consumer using its own Nucleus root — keeps the yaml portable across Nucleus deployments.
- All new `aisles` / `cameras` / `approach_points` entries should follow the existing shape without introducing new top-level keys unless the change is discussed first.

## Validation

Consumers that depend on this file should validate at startup:
- Referenced `gates_aisle` / `preferred_route` / `alternate_routes` point at aisles that exist.
- Every `missions.*.{origin,destination}` resolves to a known dock.
- Every `buttons.*.camera` resolves to a known camera.

A validation helper (`topology.py`) will land with the first consumer that needs it (likely `fleet-manager` — first to ship after the scene-pack overlay).
