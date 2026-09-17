# Red Hat Industrial AI Showcase

> [!NOTE]
> This project was developed with assistance from AI tools.

Working repository for an internal reference implementation of industrial-AI components on Red Hat OpenShift. Early development.

## Status

In active development. Architecture docs are living, and components land incrementally as the phased plan progresses. This is not a production deployment and not a released reference. Claims, diagrams, and component lists here reflect the current state of design rather than shipped capability.

## Layout

```
.
├── docs/              Architecture notes, phase plans, decision records
├── infrastructure/    GitOps manifests for hub + companion clusters
├── workloads/         Helm charts and manifests per component (populating)
├── assets/            Scene + asset material (populating)
├── demos/             Runbooks for scripted demo scenarios (populating)
├── console/           Web UI surface (populating)
├── edge/              Edge-cluster configs (populating)
├── tools/             Ancillary tooling
└── tests/             Smoke + CI
```

## Pointers for contributors

- `CLAUDE.md` — conventions for AI-assisted coding sessions.
- `docs/04-phased-plan.md` — phased delivery plan.
- `docs/07-decisions.md` — ADR log.
- `docs/plans/` — per-phase tactical plans, exit reviews.
- `infrastructure/baseline/` — current cluster state snapshots.
- `roadmaps/prereq.md` — prerequisite roadmap for the hosted `demo.redhat.com` SNO and separate cloud VLA VM. The older Fedora/KVM path is historical and unsupported by the checker.
- `tools/companion-install/README.md` — self-managed Fedora/KVM Companion SNO installation guide.
- `tools/demo-redhat-sno/README.md` — hosted `demo.redhat.com` SNO configuration and baseline guide.
