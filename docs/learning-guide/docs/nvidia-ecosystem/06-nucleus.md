# Nucleus & Asset Management

## What Nucleus does

Nucleus is the collaborative asset management server in the NVIDIA
Omniverse ecosystem. It stores, versions, and serves OpenUSD scenes
and associated assets (textures, materials, models) to connected
applications.

For a Kubernetes engineer, the closest analogy is an object store (like
S3 or SeaweedFS) with real-time collaboration features (like a shared
document server). Nucleus stores the 3D world that Isaac Sim loads,
Omniverse renders, and connected tools modify.

## Core concepts

### Asset storage

Nucleus organizes assets in a hierarchical file system accessible via
`omniverse://` URIs:

```
omniverse://nucleus.example.com/
├── Projects/
│   └── warehouse-twin/
│       ├── scenes/
│       │   └── warehouse_main.usd
│       ├── assets/
│       │   ├── forklift.usd
│       │   ├── pallet.usd
│       │   └── racking/
│       │       ├── rack_4m.usd
│       │       └── rack_6m.usd
│       └── materials/
│           └── concrete_floor.mdl
└── NVIDIA/
    └── Isaac/
        └── Robots/
            └── Unitree/
                └── G1/
                    └── g1.usd
```

Applications open USD files from Nucleus by URI. When the file
references other USD files (via composition arcs), Nucleus resolves
those references and serves the dependent assets.

### Live collaboration

When multiple clients connect to the same Nucleus server and open the
same USD stage, they enter a **live session**. Changes made by one
client (moving an object, adjusting a light, modifying a material)
propagate to all connected clients in real time.

This enables collaborative digital twin construction: a layout
engineer places equipment while a simulation engineer configures
physics properties, both working on the same scene simultaneously.

### Checkpointing and versioning

Nucleus maintains a history of changes, enabling rollback to previous
scene states. This is coarser than Git-level version control (you
cannot diff individual USD opinions) but provides a recovery mechanism
for collaborative work.

For production deployments, many teams store USD files in Git (`.usda`
format for diff-ability) and use Nucleus for runtime serving and
collaboration. Git provides the formal version history; Nucleus
provides the real-time serving and collaboration layer.

## Nucleus deployment on Kubernetes

Enterprise Nucleus Server deploys as a set of containers:

- **Nucleus API server**: The main service handling file operations,
  authentication, and live sessions
- **Nucleus Discovery**: Service registry for connected clients
- **Nucleus Auth**: Authentication backend (LDAP, SSO integration)
- **Nucleus Cache**: Caches frequently accessed assets closer to
  clients, reducing latency and Nucleus server load

On OpenShift, Nucleus deploys as a set of Deployments with Services,
Routes (for external access from connected tools), and PersistentVolumes
for asset storage. The Nucleus API uses both HTTP (for file operations)
and WebSocket (for live session events).

### Storage considerations

Digital twin assets can be large:

- A single warehouse scene with detailed geometry: 100 MB – 1 GB
- NVIDIA's Isaac asset libraries: 10–50 GB
- Textures and materials: can dominate total storage

PersistentVolumes should be sized accordingly, and network storage
(NFS, block storage) should provide sufficient IOPS for scene loading.

## Nucleus in the physical AI workflow

1. **Asset authoring**: Engineers create or import 3D assets (from CAD,
   Blender, or asset libraries) and store them in Nucleus.
2. **Scene composition**: USD scenes reference assets from Nucleus via
   `omniverse://` URIs. Scenes compose via sublayers and references.
3. **Simulation**: Isaac Sim opens scenes from Nucleus and runs
   physics simulation, sensor capture, and RL training.
4. **Synthetic data**: Replicator generates training data from
   Nucleus-hosted scenes with domain randomization.
5. **Monitoring**: In a live digital twin, Nucleus serves the scene
   that reflects the real-time state of the physical facility.

## Key takeaways

- Nucleus is the asset server for Omniverse — storing, serving, and
  enabling collaboration on OpenUSD scenes and assets.
- It provides hierarchical file storage with `omniverse://` URI access,
  real-time collaboration via live sessions, and checkpointing.
- On Kubernetes, Nucleus deploys as a set of containers with persistent
  storage for assets.
- In the physical AI workflow, Nucleus is the source of truth for the
  3D world that simulation, training, and monitoring all reference.

## Further reading

- [Nucleus Documentation](https://docs.omniverse.nvidia.com/nucleus/latest/index.html) —
  Architecture, deployment, and API reference.
- [Nucleus Architecture](https://docs.omniverse.nvidia.com/nucleus/latest/architecture.html) —
  Component architecture and deployment topology.
- [Enterprise Nucleus Server](https://docs.omniverse.nvidia.com/nucleus/latest/enterprise/index.html) —
  Deployment guide for production environments.
