# companion-install

**Roadmap context:** [Project roadmap](../../roadmaps/README.md). This is the
historical self-managed Fedora/KVM path; the current supported hosted-demo path
starts with [Goal 3](../../roadmaps/README.md#goal-3--prepare-the-hosted-companion-sno).

One-time install of the self-managed OpenShift companion cluster per ADR-017. Source material lives here so rebuilds from scratch are reproducible.

This README is the self-managed Fedora/KVM installation path. The canonical hosted SNO setup is documented in [`tools/demo-redhat-sno/`](../demo-redhat-sno/); do not use the hosted path's values as inputs to these VM-install files.

## Self-managed Companion SNO path

There are two supported ways to obtain the Companion SNO:

| Path | What this directory does | When to use it |
|---|---|---|
| Hosted demo SNO | Nothing at the infrastructure layer; the SNO is already provisioned by the demo environment | Short-lived demos, integration testing, and fast validation |
| Self-managed Fedora/KVM SNO | Creates the OpenShift SNO VM and installs the cluster using the files below | Reproducible rebuilds, FIPS/compliance, virtualization, and infrastructure demonstrations |

The hosted path is intentionally documented here because it uses the same Companion workload contract, but it skips Fedora, libvirt, agent ISO generation, the static `10.0.0.80` address, and `companion.lab.local` DNS records.

## Hosted demo SNO (`demo.redhat.com`) — legacy reference

The canonical hosted-SNO setup is [`tools/demo-redhat-sno/`](../demo-redhat-sno/). The material below is retained as historical context; use the new directory for the hosted environment and use this directory's later sections only for the self-managed Fedora/KVM path.

This path assumes the demo provider has already created an OpenShift SNO and gives us:

- a SNO kubeconfig or API login details;
- cluster-admin access, or an explicit list of permitted cluster-scoped actions;
- the cluster API and console endpoints;
- the OpenShift version and expiration/lease time;
- confirmation that the SNO can pull the required images and reach the Hub and VLA endpoint.

Before touching GitOps, capture the SNO baseline:

```bash
export DEMO_SNO_KUBECONFIG="$HOME/.kube/demo-sno.kubeconfig"

KUBECONFIG="$DEMO_SNO_KUBECONFIG" oc whoami
KUBECONFIG="$DEMO_SNO_KUBECONFIG" oc get clusterversion
KUBECONFIG="$DEMO_SNO_KUBECONFIG" oc get nodes -o wide
KUBECONFIG="$DEMO_SNO_KUBECONFIG" oc get clusteroperators
KUBECONFIG="$DEMO_SNO_KUBECONFIG" oc get storageclass
KUBECONFIG="$DEMO_SNO_KUBECONFIG" oc get pods -A
```

Record the actual cluster name, API URL, console URL, ingress domain, storage classes, and expiration time. Do not assume the self-managed values `companion`, `lab.local`, or `10.0.0.80` apply.

### ACM onboarding

If the Hub already runs ACM and OpenShift GitOps, register the hosted SNO using the Hub-side manifests. The current manifests use the name `companion`; if the demo cluster needs a different name, create an overlay or parameterize the managed-cluster, placement, GitOps, and ApplicationSet resources before applying them.

On the Hub:

```bash
oc apply -k infrastructure/gitops/apps/hub-acm/clusterset
oc apply -k infrastructure/gitops/apps/hub-acm/managedcluster
```

Wait for ACM to generate the import material, then apply it to the hosted SNO:

```bash
oc get secret -n companion companion-import \
  -o jsonpath='{.data.crds\.yaml}' | base64 -d > /tmp/klusterlet-crds.yaml
oc get secret -n companion companion-import \
  -o jsonpath='{.data.import\.yaml}' | base64 -d > /tmp/klusterlet-import.yaml

KUBECONFIG="$DEMO_SNO_KUBECONFIG" oc apply -f /tmp/klusterlet-crds.yaml
KUBECONFIG="$DEMO_SNO_KUBECONFIG" oc apply -f /tmp/klusterlet-import.yaml
```

Finish the Hub-side GitOps wiring:

```bash
oc apply -k infrastructure/gitops/apps/hub-acm/gitops-integration
oc apply -k infrastructure/gitops/apps/hub-acm/appset-companion
```

Verify the registration before syncing workloads:

```bash
oc get managedcluster companion
oc get gitopscluster -n openshift-gitops companion-gitops
oc get applications.argoproj.io -n openshift-gitops
```

### Hosted SNO configuration requirements

Before enabling the warehouse workload, configure these values for the actual demo environment:

1. **Hub Kafka Route** — the SNO must reach the Hub's external Kafka listener on port `443`. Copy the Hub Kafka CA into the SNO workload namespace and configure the fake camera and Mission Dispatcher with the real Route hostname.
2. **VLA endpoint** — configure Mission Dispatcher with the reachable URL of the separate VLA VM, for example `http://<vla-vm-address>:8000/act`. Do not use the self-managed host address or the Hub-local OpenVLA service unless that is the chosen topology.
3. **Git source** — use the repository and credentials for the fork that should build the workload images. Do not rely on the upstream URL embedded in older manifests.
4. **Routes and DNS** — use the hosted SNO ingress domain for workload Routes. Do not add the self-managed `*.apps.companion.lab.local` entries.
5. **Provider restrictions** — confirm whether the demo SNO permits ACM klusterlet import, operator subscriptions, BuildConfigs, custom Routes, cluster policies, and workload monitoring.

For the first demo, deploy only the required edge workload path. Defer KubeVirt, HyperConverged, LVMS, the `/dev/vdb`-based LVMCluster, PLC Gateway VM, compliance scans, and cluster image policy until the hosted SNO capabilities are confirmed. Several of those are infrastructure demonstrations rather than prerequisites for the warehouse event loop.

The current repository still needs a hosted-SNO overlay before this flow is fully automated: Companion fake-camera configuration contains a hardcoded Hub Route and repository URL, while Mission Dispatcher and OpenVLA manifests currently live under the Hub workload ApplicationSet. Track that overlay as deployment work rather than applying the existing Companion ApplicationSet blindly.

## Target shape

- **Host**: Fedora 43 on GMKTec Evo-X2 (AMD Ryzen AI Max+ 395, 32 threads, 124 GiB RAM, 1.9 TB NVMe).
- **Topology**: Single-Node OpenShift in a KVM VM on the Fedora host. VM network: macvtap on `eno1` (direct LAN attach).
- **Version**: OCP 4.21.5 — matches the hub per Session 09 plan D3.
- **Cluster name / baseDomain**: `companion` / `lab.local` → `api.companion.lab.local`, `*.apps.companion.lab.local`.
- **Node IP**: static `10.0.0.80` (nmstate in agent-config).
- **FIPS mode**: `fips: true`, day-1-only. Per ADR-017 the companion is where the FIPS demo lives. The Fedora install host is not itself in FIPS mode, so ISO rendering sets `OPENSHIFT_INSTALL_SKIP_HOSTCRYPT_VALIDATION=1` to skip the installer's host-crypt gate (the static `openshift-install` binary enforces it; the FIPS-capable variant from the `openshift-install-rhel9` tarball would not). The cluster itself comes up genuinely FIPS-enabled (`fips=1` on the RHCOS kernel cmdline, FIPS-validated crypto in the payload); only ignition-bootstrap key generation was off a non-FIPS host, which leaves `install.openshift.io/hostcrypt-check-bypassed=true` on the cluster. Immaterial for demonstrating posture; material for a formal CNSA audit.

## Prerequisites

1. Fedora host with libvirt/QEMU:
   ```bash
   sudo dnf install -y @virtualization nmstate
   sudo systemctl enable --now libvirtd
   sudo usermod -aG libvirt,kvm $USER
   echo 'export LIBVIRT_DEFAULT_URI=qemu:///system' >> ~/.bashrc
   ```
   Fresh shell after the group change. `virt-host-validate qemu` should show no fatals.

2. Red Hat pull secret at `~/companion-install/pull-secret.txt` (download from `console.redhat.com/openshift/install/pull-secret`).

3. Your own SSH public key at `~/.ssh/id_ed25519.pub` (or equivalent). Used as the `core` user's authorized key on the SNO node. The template carries a `__SSH_KEY__` placeholder; the render step substitutes it.

## Install

```bash
cd ~/companion-install
# Download installer + oc client (pinned to hub version)
curl -sLO https://mirror.openshift.com/pub/openshift-v4/x86_64/clients/ocp/4.21.5/openshift-install-linux-4.21.5.tar.gz
curl -sLO https://mirror.openshift.com/pub/openshift-v4/x86_64/clients/ocp/4.21.5/openshift-client-linux-4.21.5.tar.gz
tar xzf openshift-install-linux-4.21.5.tar.gz openshift-install
tar xzf openshift-client-linux-4.21.5.tar.gz oc
sudo mv oc /usr/local/bin/

# Render install-config.yaml from the template (substitutes pull secret + SSH key)
mkdir -p config
PS=$(jq -c . pull-secret.txt | sed 's|[/&]|\\&|g')
KEY=$(cat ~/.ssh/id_ed25519.pub | sed 's|[/&]|\\&|g')
sed -e "s/__PULL_SECRET__/$PS/" -e "s|__SSH_KEY__|$KEY|" install-config.template.yaml > config/install-config.yaml
cp agent-config.yaml config/

# Generate the ISO (consumes both YAMLs). The env var bypasses the static
# installer's host-FIPS check — see "FIPS mode" note at top of file.
OPENSHIFT_INSTALL_SKIP_HOSTCRYPT_VALIDATION=1 ./openshift-install agent create image --dir config

# Stage ISO in libvirt's pool for SELinux labelling
sudo install -m 0644 -o qemu -g qemu config/agent.x86_64.iso /var/lib/libvirt/images/companion-agent.iso

# Create + boot the VM
bash virt-install.sh
```

## Post-install

```bash
# Install completes in ~45 min. Watch progress from the Fedora host:
./openshift-install agent wait-for bootstrap-complete --dir config
./openshift-install agent wait-for install-complete --dir config

# Kubeconfig lands in config/auth/kubeconfig + config/auth/kubeadmin-password.
# Copy kubeconfig to your workstation:
scp daddo@<host>:~/companion-install/config/auth/kubeconfig ~/.kube/companion.kubeconfig
```

On your workstation, add to `/etc/hosts`:
```
10.0.0.80 api.companion.lab.local
10.0.0.80 oauth-openshift.apps.companion.lab.local
10.0.0.80 console-openshift-console.apps.companion.lab.local
```

Verify:
```bash
KUBECONFIG=~/.kube/companion.kubeconfig oc --insecure-skip-tls-verify get nodes
```

(`--insecure-skip-tls-verify` needed because the cluster cert is for `api.companion.lab.local` but the kubeconfig's server URL was re-pointed. Session 10 captures the proper pattern.)

## What's NOT in this directory

- `pull-secret.txt` — never committed.
- Generated `agent.x86_64.iso` — 1.4 GB, regenerated from templates.
- `config/auth/` — rendered kubeconfigs; workstation copy only.
