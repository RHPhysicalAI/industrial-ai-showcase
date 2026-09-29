# OSD Hub Cluster Baseline

> Storage note (2026-09-29): this captures historical cluster observations. The current S3 migration target is SeaweedFS per [ADR-021](../../docs/07-decisions.md#adr-021-seaweedfs-for-in-cluster-s3-odf-not-installed-here); it was not verified in the sessions recorded below.

Captured state of the OpenShift Dedicated hub cluster. This file is living documentation — re-capture when material state changes (operator upgrades, GPU node replacement, RHOAI version bumps).

- **Captured**: 2026-04-17
- **Captured by**: Session 01 (feat/p0-session-01-foundation)
- **Cluster role**: hub (per ADR-017)

---

## 1. Cluster identity and version

| Field | Value |
|---|---|
| Product | OpenShift Dedicated (internal Red Hat instance) |
| OCP version | 4.21.5 |
| Kubernetes version | v1.34.4 |
| Container runtime | cri-o 1.34.5-3.rhaos4.21.gita8af6ea.el9 |
| Node OS | Red Hat Enterprise Linux CoreOS 9.6.20260303-1 (Plow) |
| Node kernel | 5.14.0-570.96.1.el9_6.x86_64 |
| Cloud substrate | AWS (`ec2.internal` node hostnames) |
| Region / AZ | us-east-1 / **us-east-1a (single AZ — see Findings)** |
| `oc` client version | 4.17.11 |

---

## 2. Access verification

- User: `jary@redhat.com`
- `oc auth can-i '*' '*' --all-namespaces`: **yes** (cluster-admin confirmed per ADR-017)
- `oc debug node/<node>`: **denied** by SRE (first concrete OSD restriction observed — see Findings, item 5)

---

## 3. Node inventory

12 nodes total: 3 masters, 2 infra/worker, 7 workers. All single AZ (`us-east-1a`).

| Node | Role | Instance type | GPU | Age |
|---|---|---|---|---|
| ip-10-0-0-125 | master | _(SRE-managed, opaque)_ | — | 25d |
| ip-10-0-42-47 | master | _(SRE-managed, opaque)_ | — | 25d |
| ip-10-0-53-188 | master | _(SRE-managed, opaque)_ | — | 25d |
| ip-10-0-32-46 | infra,worker | r5.xlarge | — | 25d |
| ip-10-0-51-63 | infra,worker | r5.xlarge | — | 25d |
| ip-10-0-23-31 | worker | m5.2xlarge | — | 25d |
| ip-10-0-33-214 | worker | m5.2xlarge | — | 25d |
| ip-10-0-5-155 | worker | m5.2xlarge | — | 2d |
| ip-10-0-62-118 | worker | m5.2xlarge | — | 4d |
| ip-10-0-4-55 | worker | **g6e.4xlarge** | **1× NVIDIA-L40S** | 44h |
| ip-10-0-55-35 | worker | **g6e.4xlarge** | **1× NVIDIA-L40S** | 4d |
| ip-10-0-57-143 | worker | **g6e.4xlarge** | **1× NVIDIA-L40S** | 2d 22h |

(Master instance types are not visible to cluster-admin on OSD; node-label `instance-type` is absent on masters. Treat as SRE-managed.)

---

## 4. GPU inventory and canonical product strings

**These strings are load-bearing for ADR-018.** All workload charts pin GPU class with `nodeSelector: { nvidia.com/gpu.product: <string> }`. The canonical strings on this cluster, confirmed verbatim via `oc get nodes -l nvidia.com/gpu.present=true -o json | jq '.items[].metadata.labels'` on 2026-04-17, are:

```yaml
# L40S pool (3 nodes currently):
nodeSelector:
  nvidia.com/gpu.product: NVIDIA-L40S

# L4 pool (2 nodes, confirmed Session 06 on 2026-04-17):
nodeSelector:
  nvidia.com/gpu.product: NVIDIA-L4
```

Per-L40S-node GFD labels (identical across all three L40S workers):

| Label | Value |
|---|---|
| `nvidia.com/gpu.present` | `true` |
| `nvidia.com/gpu.product` | `NVIDIA-L40S` |
| `nvidia.com/gpu.memory` | `46068` (MiB) |
| `nvidia.com/gpu.family` | `ada-lovelace` |
| `nvidia.com/gpu.count` | `1` |
| `nvidia.com/gpu.machine` | `g6e.4xlarge` |
| `nvidia.com/mig.strategy` | `single` |
| `feature.node.kubernetes.io/pci-10de.present` | `true` |
| `.status.capacity["nvidia.com/gpu"]` | `1` |

Per-L4-node GFD labels (identical across both L4 workers, captured Session 06):

| Label | Value |
|---|---|
| `nvidia.com/gpu.product` | `NVIDIA-L4` |
| `nvidia.com/gpu.memory` | `23034` (MiB) |
| `nvidia.com/gpu.family` | `ada-lovelace` |
| `nvidia.com/gpu.count` | `1` |
| `nvidia.com/gpu.machine` | `g6.2xlarge` |
| `.status.capacity["nvidia.com/gpu"]` | `1` |

MIG strategy `single` means one GPU per node exposed as one resource — consistent with ADR-018's "no MIG, no time-slicing, no vGPU splitting" rule.

---

## 5. NVIDIA GPU Operator

| Field | Value |
|---|---|
| Operator CSV | `gpu-operator-certified.v25.10.1` |
| Channel | `v25.10` (certified-operators catalog) |
| Namespace | `nvidia-gpu-operator` |
| ClusterPolicy name | `gpu-cluster-policy` |
| ClusterPolicy state | `ready` (last reconciled 2026-04-15T20:13:53Z) |
| DCGM enabled | true |
| DCGM exporter enabled | true |
| MIG manager enabled | true (`mig.strategy: single`) |
| Driver / toolkit / device-plugin / GFD versions | bundled in operator v25.10.1; no per-component pinning |

No re-install required; validated only.

---

## 6. Node Feature Discovery

| Field | Value |
|---|---|
| Operator subscription | `nfd` (openshift-nfd namespace) |
| Channel | `stable` (redhat-operators) |
| Status | reconciled; GFD labels present on GPU nodes as expected |

---

## 7. Red Hat OpenShift AI (RHOAI)

| Field | Value |
|---|---|
| Operator CSV | `rhods-operator.3.4.0-ea.1` |
| Channel | `beta` (redhat-operators) |
| Namespace | `redhat-ods-operator` |
| DataScienceCluster name | `default-dsc` |
| DSC phase | `Ready` |
| Reported release | `OpenShift AI Self-Managed` v`3.4.0-ea.1` |

DSC component matrix:

| Component | managementState |
|---|---|
| `aipipelines` | Managed |
| `dashboard` | Managed |
| `feastoperator` | Managed |
| `kserve` | Managed |
| `kueue` | **Unmanaged** |
| `llamastackoperator` | Managed |
| `mlflowoperator` | **Managed** (already enabled — see Findings) |
| `modelregistry` | Managed |
| `ray` | Managed |
| `sparkoperator` | **null (not configured)** |
| `trainer` | Managed |
| `trainingoperator` | Managed |
| `trustyai` | Managed |
| `workbenches` | Managed |

Against the `CLAUDE.md` expectations:
- `trainer = Managed` ✓
- `spark` disabled ✓ (managementState is null, i.e. not configured)
- `mlflowoperator = Managed` ✓ (Phase 1 Work Item 0 is effectively already done; Phase 1 just needs to validate backend config)
- `llamastackoperator = Managed` — ready for ADR-019 Phase 3 work
- `trustyai = Managed` — ready for ADR-019 evaluation signal integration
- `ray = Managed` and `trainingoperator = Managed` — ready for Phase 2 Isaac Lab distributed training
- `kueue = Unmanaged` — note; could be flipped to Managed if Phase 2 queueing needs arise

---

## 8. OpenShift Virtualization availability — **OD-9 ANSWER**

| Check | Result |
|---|---|
| `kubevirt-hyperconverged` in `redhat-operators` catalog | **Yes, installable** |
| `kubevirt-hyperconverged` installed (CSV present) | No |
| `HyperConverged` CRD present | No (operator not installed) |
| Node CPU virt extensions (VMX/SVM) visible | **Cannot verify — `oc debug node` denied by SRE**; however, AWS `g6e.4xlarge`, `m5.2xlarge`, `r5.xlarge` are all Nitro-virtualized instance families and do **not** expose nested virtualization to workloads. Running KubeVirt VMs would require `.metal` bare-metal instance families. |

### OD-9 resolution

**OpenShift Virtualization is not a viable use of this OSD hub.** The operator is installable from the catalog, but the underlying AWS Nitro instance families do not expose hardware virtualization extensions to the guest kernel, so KubeVirt VMs would fail to start (or run in dramatically degraded software-emulation mode). Switching the MachinePool to `.metal` would require an SRE request and is a large ask.

**Implication**: per ADR-017, the self-managed companion cluster is where OpenShift Virtualization lives in this reference. OD-9 is **resolved in favor of the companion-cluster design**; this is no longer a "TBD" in the component catalog. The "one platform for containers, VMs, and vGPU workstations" differentiator is demonstrated across the hub+companion pair rather than on the hub alone — which is consistent with the hub+companion talk-track that ADR-017 already anticipated.

---

## 9. Other operators installed (SRE-managed or pre-existing workload operators)

**Workload-relevant (pre-existing, usable for Phase 0+):**

| Operator | CSV / version | Channel | Namespace |
|---|---|---|---|
| NVIDIA GPU Operator | `gpu-operator-certified.v25.10.1` | v25.10 | nvidia-gpu-operator |
| NFD | latest via subscription | stable | openshift-nfd |
| RHOAI | `rhods-operator.3.4.0-ea.1` | beta | redhat-ods-operator |
| OpenShift Pipelines (Tekton) | `openshift-pipelines-operator-rh.v1.21.1` | latest | openshift-operators |
| **Red Hat OpenShift Service Mesh 3** | `servicemeshoperator3.v3.3.1` | stable | openshift-operators |
| Kueue | `kueue-operator.v1.3.1` | stable-v1.3 | openshift-kueue-operator |
| Kernel Module Management | `kernel-module-management.v2.6.0` | stable | openshift-kmm |
| JobSet | via subscription | stable-v1.0 | openshift-jobset-operator |
| Authorino | `authorino-operator.v1.3.0` | stable | openshift-operators |
| cert-manager | `cert-manager-operator.v1.18.1` | stable-v1 | openshift-cert-manager-operator |
| Limitador | `limitador-operator.v1.3.0` | stable | openshift-operators |
| Red Hat Connectivity Link (Gateway API) | `rhcl-operator.v1.3.2` | stable | openshift-operators |
| DNS Operator | `dns-operator.v1.3.0` | stable | openshift-operators |

**OSD-managed (SRE operators — don't touch):**
- cloud-ingress-operator, custom-domains-operator, deployment-validation-operator, managed-upgrade-operator, configure-alertmanager-operator, must-gather-operator, osd-metrics-exporter, rbac-permissions-operator, route-monitor-operator, splunk-forwarder-operator, managed-velero-operator

**Catalog sources active:** `certified-operators`, `community-operators`, `redhat-marketplace`, `redhat-operators` — all READY.

**NOT yet installed** (Phase 0 sessions 2–3 will install these):
- OpenShift GitOps (Argo CD) — Session 2
- OpenShift Data Foundation — Session 3 (or accept OSD-provided StorageClasses + provision S3 separately)
- OpenShift Logging + LokiStack — Session 3
- OpenTelemetry Operator + Tempo Operator — Session 3
- Grafana Operator — Session 5
- CloudNativePG — Session 3
- Red Hat Advanced Cluster Management — Session 3
- Ansible Automation Platform — Session 3
- Streams for Apache Kafka (AMQ Streams) — Session 3

---

## 10. Sigstore admission state

- CRDs matching `sigstore` or `policy-controller`: **none**.
- Admission webhook for image signing: not installed.

Baseline: nothing in place yet. Phase 0 Session 6 installs `policy.sigstore.dev` in warn mode; graduates to enforce in Phase 1.

---

## 11. Findings that need action

These are the items that need follow-up before Phase 0 can be called complete.

### Finding 1 — **L4 GPU nodes — RESOLVED as of Session 06 (2026-04-17)**

Original state: 3× L40S + 0× L4. User self-provisioned 2× `g6.2xlarge` L4 nodes on 2026-04-17; labels confirmed: `nvidia.com/gpu.product: NVIDIA-L4`, 23 GiB memory, ada-lovelace family. See Section 4 for the full label table.

Canonical GPU product strings for ADR-018 are both now live and verified on-cluster.

### Finding 2 — **Service Mesh 3 is installed; ADR-006 is superseded by ADR-020**

The installed operator is **OpenShift Service Mesh 3** (`servicemeshoperator3.v3.3.1`) rather than v2 as ADR-006 originally specified. Service Mesh 3 is the Istio-based `sail-operator` version with both sidecar and ambient options, strategically aligned with where Red Hat is taking the mesh story. Installing v2 alongside v3 would be an anti-pattern.

**Status**: **Resolved.** ADR-020 (added in the same commit as this finding update) accepts Service Mesh 3, marks ADR-006 as superseded, and preserves sidecar-default as the workload-participation mode. See `docs/07-decisions.md` for the full ADR text.

All Service Mesh-dependent work from Phase 0 Session 03 onward proceeds against Service Mesh 3 CRs (`Istio` + `IstioCNI` + `IstioRevision` + `IstioRevisionTags`), not v2's `ServiceMeshControlPlane`.

### Finding 3 — **OpenShift GitOps (Argo CD) is not yet installed**

No GitOps Subscription present. This is the first work item for Phase 0 Session 2. No action needed in Session 01 beyond noting it.

### Finding 4 — **Single-AZ deployment (`us-east-1a` only)**

All 12 nodes live in `us-east-1a`. A full-AZ outage takes the entire hub down. For an internal reference this is low-stakes, but worth noting in the field-team talk track: customer-facing production references would span AZs.

**Recommended action**: no immediate change; note in the one-pager as a known Phase-0-appropriate simplification.

### Finding 5 — **`oc debug node/...` is denied by SRE**

First concrete OSD SRE restriction encountered. ADR-017 anticipated this class of friction ("MachineConfigs on OSD are fragile; SRE's automation manages the underlying infrastructure"). `oc debug node` is a softer restriction than MachineConfig but confirms SRE has trimmed some host-level debugging paths.

**Recommended action**: none direct. Note for future sessions that any host-level inspection (kernel params, CPU features, IOMMU state) cannot be done via `oc debug node` on this hub and should be done on the companion cluster where we own the substrate.

### Finding 6 — **MLflow backend wired in Session 06**

`mlflowoperator` Managed in DSC, MLflow v3.9.0 per `.status.components.mlflowoperator.releases`. Session 06 landed the backend: CNPG `Cluster/mlflow-db` in `mlflow` namespace, the original object-store deployment with bucket `mlflow-artifacts`, and a cluster-scoped `MLflow/mlflow` CR wired to both. That historical backend is superseded by the 2026-09-29 SeaweedFS decision; this baseline is not evidence of its deployment. Prior residue (cluster-scoped `MLflow/mlflow` from the abandoned three-chart Helm release + empty `ai-showcase-mlops` namespace) was removed as a pre-apply step.

The `workloads/common/python-lib/tracking/` abstraction (Phase 1 scope) reads from this MLflow instance.

### DSC drift check — 2026-04-17 (Session 06)

Re-ran Section 7 checks against the running DSC. No drift: `trainer`, `mlflowoperator`, `llamastackoperator`, `trustyai`, `kserve`, `ray`, `trainingoperator`, `modelregistry`, `workbenches`, `aipipelines`, `feastoperator`, `dashboard` — all Managed; `sparkoperator` unset; `kueue` Unmanaged. Release banner: `OpenShift AI Self-Managed v3.4.0-ea.1`.

---

## 12. SRE ticket queue

No tickets required from Session 01 findings. L4 provisioning is self-service on this instance; the `oc debug node` restriction is accepted as-is per ADR-017.

Any future SRE-request needs will be captured in the relevant session's work notes.

---

## References

- `CLAUDE.md` — hard constraints (GPU budget, preferred technologies, hub/companion split)
- `docs/04-phased-plan.md` — Phase 0 work breakdown
- `docs/07-decisions.md` — ADR-017 (hub + companion), ADR-018 (GFD label GPU targeting), ADR-015 (RHOAI 3.4.0 EA1 + MLflow)
- `docs/08-gpu-resource-planning.md` — L40S/L4 workload placement
- `docs/09-risks-and-open-questions.md` — OD-8 (companion host), OD-9 (OpenShift Virtualization — **resolved here**)
