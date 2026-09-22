# demo-redhat-sno

**Roadmap:** [Project roadmap — Goals 3–5](../../roadmaps/README.md#goal-3--prepare-the-hosted-companion-sno)

Hosted Single-Node OpenShift setup supplied through `demo.redhat.com`.

This directory is the hosted counterpart to [`tools/companion-install/`](../companion-install/). It does not provision OpenShift, create a VM, install Fedora, generate an agent ISO, or configure bare-metal networking. The demo provider supplies the SNO; this directory records and validates how we adapt that cluster for the Industrial AI Showcase.

## Target topology

```text
Local workstation
  ├── Hub kubeconfig ───────────────► Hub OpenShift / ACM
  └── Hosted SNO kubeconfig ────────► demo.redhat.com SNO

Hosted SNO ── external Kafka Route ──► Hub Kafka
Hosted SNO ── HTTP /act ─────────────► separate VLA VM
```

The hosted SNO is a temporary Companion environment. It is not assumed to have the self-managed Companion's static IP, `lab.local` DNS, Fedora host, `/dev/vdb`, LVMS, KubeVirt, FIPS, or STIG posture.

The VLA VM is a separate prerequisite. Its IP only identifies the machine; it does not mean that the VLA service, GPU runtime, model weights, firewall, or systemd service have been installed.

## Files

- `.env.example` — variable names and safe placeholders; copy to the ignored `.env`.
- `capture-baseline.sh` — read-only SNO inventory and capability capture.
- `deploy-workload.sh` — applies the first hosted-SNO workload slice and copies the Hub Kafka CA certificate into the Companion namespace.
- `.gitignore` — prevents local kubeconfigs and environment configuration from being committed.

## Required demo handoff

Before configuring the cluster, obtain:

- SNO kubeconfig or API login details;
- cluster-admin access, or an explicit list of permitted operations;
- API URL, console URL, and ingress domain;
- OpenShift version and expiry date;
- node capacity and available StorageClasses;
- confirmation that the SNO can pull images and access Git, the Hub, and the VLA VM;
- the VLA VM address and listening port;
- VLA VM SSH user/key, operating system, GPU vendor/model, VRAM, disk capacity, and AWS security-group ownership;
- confirmation that ACM klusterlet import, custom namespaces, Routes, BuildConfigs, and workload deployments are allowed.

## Configure the local setup

```bash
cd tools/demo-redhat-sno
cp .env.example .env
${EDITOR:-vi} .env
source .env
```

Do not commit `.env` or a kubeconfig. The hosted SNO values must not be replaced with the self-managed values from `tools/companion-install/`.
When the kubeconfig contains both Hub and Companion contexts, set
`DEMO_SNO_CONTEXT` explicitly; the deployment script uses that context for
every SNO operation.

## Capture the SNO baseline

```bash
tools/demo-redhat-sno/capture-baseline.sh \
  > tools/demo-redhat-sno/baseline-${DEMO_SNO_NAME}.txt
```

The capture is read-only and records the cluster version, node, storage, operator, Route, namespace, and permission state. Review it before installing any workload.

Direct checks can also be run with:

```bash
KUBECONFIG="$DEMO_SNO_KUBECONFIG" oc whoami
KUBECONFIG="$DEMO_SNO_KUBECONFIG" oc get clusterversion
KUBECONFIG="$DEMO_SNO_KUBECONFIG" oc get nodes -o wide
KUBECONFIG="$DEMO_SNO_KUBECONFIG" oc get clusteroperators
KUBECONFIG="$DEMO_SNO_KUBECONFIG" oc get storageclass
```

## Deploy the first hosted-SNO workload slice

After the baseline is healthy and the Hub Kafka route is available, apply the
hosted overlay:

```bash
source tools/demo-redhat-sno/.env
tools/demo-redhat-sno/deploy-workload.sh
```

This applies the Fake Camera, Mission Dispatcher, and policy-version resources.
It builds both images from the public `rhkp` fork, configures the Hub Kafka
external Route, points Mission Dispatcher at the separate cloud VLA VM, and
copies only the Hub Kafka CA certificate needed by Fake Camera. The Kafka and
VLA endpoint values are created as local runtime ConfigMaps from the ignored
`.env`; they are deliberately not embedded in the GitOps overlay. The script
does not install LVMS, KubeVirt, Compliance Operator, a PLC VM, or the old
Fedora/bare-metal Companion stack.

Inspect the result with:

```bash
oc get builds -A
oc get pods -n warehouse-edge
oc get pods -n robot-edge
oc get routes -n warehouse-edge
```

## What we install on the hosted SNO

### Initial hosted-demo scope

The hosted SNO needs only the workload-facing pieces for the first warehouse loop:

- `warehouse-edge` namespace;
- Fake Camera;
- `robot-edge` namespace;
- Mission Dispatcher;
- `policy-version` ConfigMap;
- service accounts, ImageStreams, BuildConfigs, Services, and Routes;
- Hub Kafka CA Secret;
- configuration for the external VLA endpoint.

The VM must be bootstrapped separately before Mission Dispatcher can pass a real action request. Start with `VLA_MODE=mock` to validate network and API wiring, then switch to `VLA_MODE=openvla` after the GPU runtime and model dependencies are ready.

OpenShift's built-in image/build and Route capabilities are sufficient for this initial scope. We do not install a second Kafka cluster on the SNO for this first pass; the current Phase-1 design uses the Hub's external Kafka listener. MirrorMaker2 is a later architecture step.

### Explicitly deferred

Do not apply the entire existing `infrastructure/gitops/apps/companion/` directory to the hosted SNO. Defer these until the hosted environment is explicitly approved and tested:

- LVMS and the `/dev/vdb`-based `LVMCluster`;
- KubeVirt and HyperConverged;
- PLC Gateway VM;
- Compliance Operator and STIG scans;
- additional ClusterImagePolicy enforcement;
- in-cluster NVIDIA OpenVLA.

These are self-managed infrastructure or later factory demonstrations, not requirements for the initial event loop. The hosted SNO's current Ceph-backed StorageClasses are not equivalent to the self-managed `lvms-vg1` contract.

## Repository adaptation required before deployment

The current manifests are not a drop-in hosted-SNO deployment. We need a dedicated hosted-SNO overlay that:

1. uses `https://github.com/rhkp/industrial-ai-showcase.git` and the intended ref;
2. replaces the hardcoded Hub Kafka hostname with the actual Hub external Route;
3. uses `SSL` for the cross-cluster Kafka connection;
4. supplies `hub-kafka-ca` in `warehouse-edge`;
5. points Mission Dispatcher at `VLA_ENDPOINT_URL`, such as `http://<vla-vm>:8000/act`;
6. uses the hosted SNO ingress domain for Routes;
7. deploys Mission Dispatcher without the in-cluster L40S OpenVLA Deployment;
8. carries `policy-version` as an explicit dependency instead of inheriting the full `robot-edge` bundle.

Set the actual hosted-demo values only in the local ignored `.env`:

```text
VLA_VM_IP=<vla-vm-ip>
VLA_VM_PORT=8000
VLA_ENDPOINT_URL=http://<vla-vm-ip>:8000/act
```

The workload overlay should consume `VLA_ENDPOINT_URL` rather than embedding the address in a manifest. `.env.example` contains no real environment values.

The existing host automation at [`workloads/vla-serving-host/ansible/`](../../workloads/vla-serving-host/ansible/) is a starting point, not a drop-in solution for this VM. It assumes the old Fedora/AMD host, old SSH inventory, old LAN source CIDR, ROCm device nodes, and a mock development image. The hosted GPU VM needs a separate NVIDIA-aware profile or a parameterized Ansible role.

The existing Companion fake-camera manifests contain hardcoded environment-specific values, and Mission Dispatcher currently lives under the Hub workload tree. Do not sync the existing Companion ApplicationSet blindly until this overlay exists.

## ACM connection comes later

Once the SNO baseline and hosted workload overlay are ready, connect the cluster to the Hub ACM using [`infrastructure/gitops/apps/hub-acm/README.md`](../../infrastructure/gitops/apps/hub-acm/README.md).

The ACM sequence is:

1. Create the Hub-side `ManagedCluster` and ClusterSet resources.
2. Retrieve the generated klusterlet import material.
3. Apply the import CRDs and manifests to this hosted SNO.
4. Verify `JOINED=True` and `AVAILABLE=True`.
5. Enable the Hub GitOps integration and hosted-SNO ApplicationSet.
6. Propagate required Git credentials and Kafka CA material.
7. Sync the hosted-SNO workload overlay.

The current ACM manifests use the name `companion`. If the demo cluster is registered as `demo-redhat-sno`, the ACM resources and selectors must be parameterized or overlaid before applying them.

### Hosted-demo ACM permission note

Some hosted SNO providers preinstall an ACM klusterlet agent. The one-time
import still requires cluster-scoped CRD and RBAC operations on the SNO. A
`dedicated-admin` account may be able to log in and deploy workloads but still
be forbidden from applying the import payload. In that case, have the demo
provider or a cluster administrator apply the generated `crds.yaml` and
`import.yaml`, or provide an approved ACM enrollment workflow. Do not work
around this by granting partial hand-written RBAC; the import payload must be
applied consistently.

## Preflight

Use the repository checker against the hosted kubeconfig:

```bash
python3 tools/preflight/check.py \
  --scope companion \
  --profile demo-workload \
  --companion-kubeconfig "$DEMO_SNO_KUBECONFIG" \
  --explain \
  --color always
```

The `fedora` scope is not applicable to this hosted path. The hosted-SNO
profiles treat KubeVirt, LVMS, and compliance capabilities as optional rather
than blocking; the first workload slice only requires the hosted cluster,
storage, namespaces, Hub Kafka CA, and cloud VLA endpoint.
