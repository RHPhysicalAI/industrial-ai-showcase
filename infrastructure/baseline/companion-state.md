# Companion Cluster Baseline

Captured state of the self-managed companion SNO. Counterpart to `osd-hub-state.md` — structure is intentionally mirrored so drift from the hub is obvious at a glance. Living documentation — re-capture when material state changes (operator installs, FIPS/STIG remediations applied, reboots to accommodate MachineConfigs).

- **Captured**: 2026-04-17
- **Captured by**: Session 10 (`feat/p0-session-10-companion-baseline`)
- **Cluster role**: companion (per ADR-017)
- **Companion purpose**: MachineConfig-dependent work (FIPS, STIG), air-gap validation, customer-parity self-managed demo. See ADR-017.

Capture is produced by `tools/companion-install/capture-baseline.sh`:

```bash
export KUBECONFIG=~/.kube/companion.kubeconfig
tools/companion-install/capture-baseline.sh > /tmp/companion-baseline-raw.txt
```

The raw output is reviewed, then its facts land in the sections below.

---

## 1. Cluster identity and version

| Field | Value |
|---|---|
| Product | OpenShift Container Platform (self-managed, agent-based install) |
| OCP version | 4.21.5 |
| Kubernetes version | v1.34.4 |
| Container runtime | cri-o 1.34.5-3.rhaos4.21.gita8af6ea.el9 |
| Node OS | Red Hat Enterprise Linux CoreOS 9.6.20260303-1 (Plow) |
| Node kernel | 5.14.0-570.96.1.el9_6.x86_64 (identical to hub) |
| Release image digest | `quay.io/openshift-release-dev/ocp-release@sha256:ae0711cb2b35d8661d086945e0578f9cd2d417093e910e47169447db5dd9f8bd` |
| Substrate | KVM VM on Fedora 43 (GMKTec Evo-X2, AMD Ryzen AI Max+ 395) |
| VM network | macvtap on host `eno1`; VM IP static `10.0.0.80` (nmstate) |
| Cluster name / baseDomain | `companion` / `lab.local` |
| API endpoint | `https://api.companion.lab.local:6443` (workstation `/etc/hosts` mapping → 10.0.0.80) |
| Infrastructure name | `companion-hhfr7` |
| Platform | `None` (bare-metal / agent-based) |
| FIPS mode | **enabled at install (day-1)**; install-host crypt check bypassed — see §9b + ADR-017 amendment |

---

## 2. Access verification

- User: `system:admin` (via kubeconfig cert-auth)
- `oc auth can-i '*' '*' --all-namespaces`: **yes** (cluster-admin confirmed)
- `oc debug node/companion-0`: **works** (unlike OSD, which SRE restricts). Load-bearing for §9b FIPS kernel-cmdline verification and Session 11 Compliance Operator remediations.

---

## 3. Node inventory

1 node (SNO — master + worker role on the same node).

| Node | Status | Roles | vCPU | RAM | Disk | GPU | Age at capture |
|---|---|---|---|---|---|---|---|
| companion-0 | Ready | control-plane,master,worker | 16 | 64 GiB (65,821,332 Ki) | 250 GB (qcow2, /dev/vda; ephemeral-storage 249 GiB allocatable) | — | 51m |

Allocatable (after kube/system reservations): 15500m CPU, 64,670,356 Ki memory, 239,973,624,229 bytes ephemeral-storage, 250 pods.

No GPUs — companion is CPU-only for Phase 0-3. The Fedora host's Ryzen AI Max+ iGPU is not passed through.

---

## 4. GPU inventory and canonical product strings

**None.** No GPU-bearing nodes on companion. `nvidia.com/gpu.present=true` label count: **0** (confirmed).

This is recorded explicitly so Session 12 (KubeVirt) does not attempt GPU passthrough on the companion, and so workload scheduling logic that branches on GPU class (ADR-018) correctly treats the companion as a CPU-only cluster.

---

## 5. NVIDIA GPU Operator

**Not installed.** `clusterpolicy` CRD absent. Expected — no GPUs. Session 12 revisits only if we add KubeVirt GPU passthrough; not expected in Phase 0.

---

## 6. Node Feature Discovery (NFD)

**Not installed.** `nodefeature` CRD absent. No GPU → no GFD need. May be installed alongside KubeVirt in Session 12 if we need hardware-feature labels for VM placement.

---

## 7. Red Hat OpenShift AI (RHOAI)

**Not installed.** `datasciencecluster` CRD absent. RHOAI is an OSD-hub-only component per the layered plan. Companion does not host ML workloads in Phase 0-3.

---

## 8. OpenShift Virtualization (KubeVirt)

Installed in Session 12 (2026-04-18). The companion is the designated KubeVirt cluster per ADR-017; hub does not run VM workloads.

- CSV: `kubevirt-hyperconverged-operator.v4.21.3` (stable channel, redhat-operators catalog)
- `HyperConverged` CR: `openshift-cnv/kubevirt-hyperconverged` with default spec
- Nested virt on node: **`svm` present** (AMD SVM — confirmed pre-install).
- CDI uses default StorageClass (`lvms-vg1`) for DataVolumes.
- No vGPU (no NVIDIA GPU on this host — vGPU path is ORIGIN-PC-conditional per ADR-017).

---

## 9. Platform-shipped built-ins of interest

### 9a. Sigstore admission (`config.openshift.io/v1 ClusterImagePolicy`)

OCP 4.21 ships `ClusterImagePolicy` built-in. Companion is the target for **enforce-mode** image-policy demonstration (tighter than hub's posture). Session 11 authors additional CIPs per `.plans/session-11-research.md`.

- `clusterimagepolicies.config.openshift.io` CRD present: **yes**
- Platform's default `openshift` CIP enrolled: **yes** (age at capture: 57m)

### 9b. FIPS state

| Check | Expected | Actual |
|---|---|---|
| `fips=1` on RHCOS kernel cmdline | present | **present** |
| `/proc/sys/crypto/fips_enabled` on node | `1` | **`1`** |
| Install-config ConfigMap `fips:` field | `true` | **`true`** (confirmed in `kube-system/cluster-config-v1`) |
| `install.openshift.io/hostcrypt-check-bypassed` annotation on ClusterVersion | `"true"` | **empty** (annotation did not propagate to ClusterVersion metadata in 4.21; bypass evidence lives in the install-config record only) |

The cluster is genuinely FIPS-enabled at the kernel + crypto-provider level. The `hostcrypt-check-bypassed` signal is recorded only in the install-config ConfigMap in 4.21; it does not appear on the ClusterVersion object. Session 11's FIPS evidence bundle captures both locations.

---

## 10. Installed operators

| Operator | CSV | Namespace | Session | Purpose |
|---|---|---|---|---|
| LVM Storage (LVMS) | `lvms-operator.v4.21.0` | `openshift-storage` | 11 | SNO local-storage provisioner. Backs `lvms-vg1` StorageClass from `/dev/vdb` (100 GB qcow2). |
| Compliance Operator | `compliance-operator.v1.9.0` | `openshift-compliance` | 11 | STIG V2R3 scans + remediations. 105 auto-remediations applied; scan-only policy. |
| OpenShift Virtualization (KubeVirt) | `kubevirt-hyperconverged-operator.v4.21.3` | `openshift-cnv` | 12 | HyperConverged CR deploys virt-api, virt-controller, virt-handler, CDI, SSP, cluster-network-addons. |
| Klusterlet (ACM agent) | installed via import.yaml | `open-cluster-management-agent`, `-addon`, `-policies` | 13 | Pull-model registration to hub ACM. Addons: application-manager, cert-policy-controller, cluster-proxy, config-policy, governance-policy-framework, managed-serviceaccount, search, workmgr. |
| Observability-controller addon | `observability-controller` | `open-cluster-management-addon-observability` | 14 | Auto-deployed by ACM MCO on hub. Runs `metrics-collector` + `uwl-metrics-collector` which remote_write platform + user-workload metrics to hub Thanos Receiver. |

Platform defaults (always present): `packageserver` in `openshift-operator-lifecycle-manager`.

User-workload monitoring was enabled in Session 14 via `cluster-monitoring-config` ConfigMap in `openshift-monitoring` (see `infrastructure/gitops/apps/companion/user-workload-monitoring/`).

---

## 11. Catalog sources

All four default OperatorHub catalogs READY:

| Catalog | Display | Status |
|---|---|---|
| certified-operators | Certified Operators | READY |
| community-operators | Community Operators | READY |
| redhat-marketplace | Red Hat Marketplace | READY |
| redhat-operators | Red Hat Operators | READY |

Confirms outbound connectivity to `registry.redhat.io` / `quay.io` — the companion is **not** air-gapped at this point in its lifecycle. Air-gap validation (per ADR-017) is a later exercise that will involve catalog mirroring via `oc-mirror v2`.

---

## 12. Network

- CNI: **OVNKubernetes**
- Cluster network: `10.128.0.0/14`, hostPrefix `/23`
- Service network: `172.30.0.0/16`
- Machine network: `10.0.0.0/24` (LAN; static node IP `10.0.0.80`)

---

## 13. StorageClasses

| Name | Provisioner | Default | Session | Backing |
|---|---|---|---|---|
| `lvms-vg1` | `topolvm.io` | yes | 11 | LVMCluster `companion-storage` on `/dev/vdb` (100 GB qcow2, thin-provisioned, xfs, overprovision ratio 10). |

The 100 GB backing qcow2 was live-attached to the VM via `virsh attach-disk --persistent --live` in Session 11 (no VM downtime). Compliance Operator's `rawResultStorage` and KubeVirt CDI DataVolumes both use this default SC.

---

## 14. ClusterOperator rollup

All **34 of 34** cluster operators `AVAILABLE=True PROGRESSING=False DEGRADED=False`.

Oldest operator reported age at capture: 50m (`machine-config`). Newest: 26m (`monitoring`). Most settled in the 27-49m band, consistent with the observed bootstrap timeline:

- Initial ISO boot: ~18:16 local (2026-04-17)
- bootstrapInPlace shutdown: ~18:25 local (VM powered off mid-install as designed)
- Manual VM restart: ~18:29 local
- All COs Available: 18:56:54 local

Total wall-clock from ISO boot to all-Available: ~40 minutes (including the ~4-min human-in-the-loop restart gap).

---

## 15. Findings and drift from hub

Compared to `osd-hub-state.md`:

| Dimension | Hub (OSD) | Companion (this cluster) |
|---|---|---|
| Node count | 12 (3 master + 9 worker/infra) | 1 (control-plane + worker combined) |
| Cloud substrate | AWS `us-east-1a` (SRE-managed) | KVM VM on Fedora 43 (local) |
| GPU | 3 × L40S + 2 × L4 | none |
| RHOAI | 3.4.0 EA1 installed | not installed |
| Service Mesh | Service Mesh 3 installed | not installed |
| GPU Operator / NFD | installed + labels applied | not installed |
| `oc debug node` | **denied** by SRE | **permitted** — load-bearing for §9b + Session 11 |
| FIPS | not enabled | **enabled day-1** (with hostcrypt bypass caveat) |
| Platform | AWS/OSD | `None` (bare-metal / agent) |
| Ingress cert / DNS | OSD-managed cluster domain | self-signed, `/etc/hosts` override for `*.lab.local` |
| StorageClasses | ODF + AWS gp3 | `lvms-vg1` (LVMS) |
| Operator Subscriptions | many (RHOAI, CNPG, AMQ Streams, Vault, GPU Operator, NFD, Mesh, etc.) | LVMS, Compliance, KubeVirt |

Single-node topology is the biggest operational difference. Every MachineConfig change reboots the only node — there is no rolling drain. Session 11's 105-remediation batch absorbed this as a single reboot.

---

## 17. ACM registration + cross-cluster GitOps

Registered to the hub's ACM in Session 13 (2026-04-18):

- `ManagedCluster/companion` `HUB ACCEPTED=true JOINED=True AVAILABLE=True`
- In `ManagedClusterSet: clusters-companion` (role-based set, distinct from ACM defaults)
- Addons active: `application-manager`, `cert-policy-controller`, `cluster-proxy`, `config-policy-controller`, `governance-policy-framework`, `klusterlet-addon-search`, `klusterlet-addon-workmgr`, `managed-serviceaccount`
- Hub Argo CD reconciles all 7 `apps/companion/*` directories via ApplicationSet `companion-apps` in `openshift-gitops` on hub
- Argo destination uses ACM's cluster-proxy: `https://cluster-proxy-addon-user.multicluster-engine.svc.cluster.local:9092/companion`. No hub→companion direct connectivity needed (pull-model klusterlet + cluster-proxy).
- Klusterlet import was manual one-time — hub on OSD/AWS cannot push to 10.0.0.80 on local LAN. See `infrastructure/gitops/apps/hub-acm/README.md`.

---

## 19. Observability federation

Registered into hub ACM MCO in Session 14:

- `metrics-collector` + `uwl-metrics-collector` remote_write platform + workload metrics to hub Thanos Receiver via cluster-proxy.
- 95 `up` series from companion visible in hub Thanos. Grafana on hub dashboards render per-cluster views with a `cluster` selector.
- Long-term retention: `thanos` bucket on the hub's `obs-storage` S3 store. 30d raw / 60d 5m / 90d 1h per MCO CR. SeaweedFS is the 2026-09-29 migration target, not a deployment verified by this historical capture; see [ADR-021](../../docs/07-decisions.md#adr-021-seaweedfs-for-in-cluster-s3-odf-not-installed-here).

---

## 20. Known follow-ups (Phase 1+)

- Consider rebuilding host on RHEL 9 + FIPS-capable installer to drop the `hostcrypt-check-bypassed` caveat — Phase-1+ optional, not on critical path.
- Widen `ClusterImagePolicy` scope: `registry.redhat.io` (GPG signing chain) and showcase GHCR (Fulcio/Rekor identity) once signing material is locked.
- Wire an IdP, then remove kubeadmin, then apply the 13 deferred STIG remediations that depend on IdP / cluster-logging / registry allowlist.
- Migrate the two imperative secrets (`thanos-object-storage`, `multiclusterhub-operator-pull-secret`) to VaultStaticSecret pattern like other Phase-0 secrets.
