# GitOps topology

Argo CD reconciles every cluster from this tree. See `docs/06-repo-structure.md` for the canonical layout.

## Two-step bootstrap (once per cluster)

```
oc apply -k infrastructure/gitops/bootstrap/
# wait for operator CSV Succeeded and ArgoCD CR Available

oc apply -f infrastructure/gitops/bootstrap/root-application.yaml
```

After step 2, every change under `infrastructure/gitops/clusters/<cluster>/` is Argo CD-reconciled. The bootstrap directory itself is never reconciled by Argo CD — it's the lever that brings Argo CD into existence.

Step 2 requires the referenced `clusters/<cluster>/` path to exist on the `main` branch (Argo CD resolves `targetRevision: main`). On the first session that introduces a cluster's GitOps content, apply step 2 **after** the PR merges.

## Repository profiles

The committed base is the legacy/upstream profile and points at
`RHPhysicalAI/industrial-ai-showcase`. The fork profile is an explicit root
Application; it keeps the live fork deployment on `rhkp` without changing the
upstream defaults.

For the upstream/legacy deployment, apply:

```bash
oc apply -f infrastructure/gitops/bootstrap/root-application.yaml
```

For the fork deployment, apply exactly one root Application instead:

```bash
oc apply -f infrastructure/gitops/bootstrap/root-application-rhkp.yaml
```

The fork root Application selects the fork repository sources and adds inline
Kustomize patches to generated Applications. Those patches rewrite
OpenShift BuildConfig Git sources to the fork at render time. No Jinja,
cross-tree component, or global Kustomize setting is required by Argo CD. The
direct hosted-SNO helper uses `GIT_REPO_URL` from its ignored `.env` for the
same selection.

## Argo CD instance choice

This reference uses the **default `openshift-gitops` Argo CD instance** the operator creates automatically. Per Red Hat's docs, that instance exists specifically for cluster-ops work (operators, OLM, cluster config) and ships with cluster-scoped permissions and OpenShift OAuth SSO wired up. Phase 0 is 100% cluster-ops.

The `openshift-gitops` namespace hosts only Argo CD's own workloads and the `Application` / `ApplicationSet` / `AppProject` CRs that Argo CD reads. No user workloads land there; every workload gets its own namespace and an Application that reconciles into it.

A second Argo CD instance for application-tier tenant isolation can be added later if future workload tiers demand it; the first instance would manage the second via an Application.

## Directory layout

```
gitops/
├── bootstrap/              two hand-applied manifests; not reconciled
├── clusters/<name>/        per-cluster aggregation (one ApplicationSet per layer)
├── apps/<layer>/<name>/    per-application manifests (Helm, Kustomize, plain YAML)
└── overlays/{dev,demo,prod}/   Kustomize overlays for env variance
```

Sessions 03+ populate `apps/operators/*` subdirectories; the `operators` ApplicationSet picks them up automatically via its Git generator.

## Sync policy

Every Application and ApplicationSet template uses **manual sync**, no `automated:` block. OutOfSync shows in the UI; a human clicks Sync. Rationale: catch misconfigurations at review time, not at reconciliation time. Per-Application auto-sync can be opted into later as confidence builds.

Sync options applied project-wide:
- `CreateNamespace=true` — operators that install into namespaces we own get them created on first sync.
- `ServerSideApply=true` — sidesteps the 256 KiB annotation limit for large CRs (cert-manager, mesh control plane, RHOAI DSC).

## Adding a new Application

For a new operator / workload in layer `<layer>` named `<name>`:

1. Create `apps/<layer>/<name>/` with Subscription / CR / Helm / Kustomize content.
2. If the ApplicationSet for that layer doesn't exist yet, add it under `clusters/<cluster>/appsets/<layer>.yaml` and reference it from `clusters/<cluster>/kustomization.yaml`.
3. PR.
4. After merge, click Sync in the Argo CD UI (or `argocd app sync operators-<name>` from CLI).

## Cross-cluster topology

Hub (`clusters/hub/`) and companion (`clusters/companion/`) are independent today. Once ACM is installed (Phase 0 Session 05) and the companion is registered as a managed cluster (Session 13), cross-cluster Applications land via ACM's ApplicationSet delivery pattern.

Spoke clusters (`clusters/spoke-a/`, `clusters/spoke-b/`) appear in Phase 2 per `docs/04-phased-plan.md`.

## References

- `docs/04-phased-plan.md` — Phase 0 scope and exit criteria.
- `docs/06-repo-structure.md` — canonical directory layout.
- `docs/07-decisions.md` — ADR-020 (Service Mesh 3) is the first post-Session-01 ADR that landed via this process.
- `docs/plans/phase-0-plan.md` — session-by-session backlog.
