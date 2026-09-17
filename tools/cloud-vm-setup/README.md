# cloud-vm-setup

Provisioning flow for the separate cloud GPU VM used by the hosted `demo.redhat.com` SNO.

This is intentionally separate from [`tools/companion-install/`](../companion-install/) and [`tools/demo-redhat-sno/`](../demo-redhat-sno/):

- `companion-install` provisions the old self-managed Fedora/KVM Companion SNO;
- `demo-redhat-sno` configures the externally provisioned SNO;
- `cloud-vm-setup` provisions the external VLA serving VM.

## Current target

The current target is the confirmed Ubuntu cloud GPU VM: an AWS
`g4dn.2xlarge` with an NVIDIA Tesla T4. The playbook installs the Ubuntu host
prerequisites, installs the NVIDIA server driver when needed, reboots once if
configured, installs the NVIDIA Container Toolkit and CDI configuration,
builds or uses the VLA container image, creates a systemd Quadlet unit, and
restricts TCP `8000` to the SNO egress CIDR.

The current repository's `workloads/vla-serving-host/ansible/` playbook is not
reused directly because it targets the old AMD/ROCm Fedora host and hardcodes
the old SSH/LAN assumptions. This directory is the Ubuntu/NVIDIA adaptation.

## Configure

```bash
cd tools/cloud-vm-setup
cp .env.example .env
${EDITOR:-vi} .env
source .env
```

Required values before running:

- `VLA_VM_IP`
- `VLA_VM_SSH_USER`
- `VLA_VM_SSH_KEY`
- `VLA_GPU_MODEL`
- `VLA_ALLOWED_SOURCE_CIDR`

`VLA_ALLOWED_SOURCE_CIDR` must be the public egress address used by the
Companion SNO, written as a single-host CIDR. Discover it from the SNO with:

```bash
oc run egress-ip-check \
  --rm -i --restart=Never \
  --image=curlimages/curl:8.12.1 \
  --command -- curl -4sS https://checkip.amazonaws.com
```

If that returns `203.0.113.10`, set
`VLA_ALLOWED_SOURCE_CIDR="203.0.113.10/32"`. Use the same value in the AWS
Security Group as an inbound Custom TCP rule for port `8000`; Ansible can
configure the VM's `firewalld`, but it cannot change the AWS Security Group.

Install the collection used by the firewall task once on the workstation:

```bash
./setup.sh --install-collections
```

The AWS security group must also permit TCP `8000` from the same restricted SNO egress address/CIDR. The Ansible firewalld rule cannot change an AWS security group.

## First run: wiring validation

On a fresh VM, run the normal setup first. It may reboot the VM after installing
the NVIDIA driver:

```bash
./setup.sh --install-collections
./setup.sh
```

The example configuration builds the small mock image on the VM when it is
absent. Mock mode validates SSH, Podman, systemd, firewall, DNS, and SNO-to-VM
networking without downloading model weights. After the first successful run,
use `./setup.sh --check` for a dry-run review.

The real VM address is read from the ignored `.env`; it is deliberately not
written into the tracked playbook or committed to Git.

For a reproducible VM build, use `VLA_BUILD_SOURCE_MODE=git` and a committed
repository ref. For local iteration before pushing a change, use
`VLA_BUILD_SOURCE_MODE=working-tree`; the wrapper syncs the current checkout to
the VM while excluding `.git`, `.env`, and kubeconfig files.

Verify from the VM:

```bash
ssh -i "$VLA_VM_SSH_KEY" \
  -p "$VLA_VM_SSH_PORT" \
  "$VLA_VM_SSH_USER@$VLA_VM_IP" \
  'curl -fsS http://127.0.0.1:8000/healthz'
```

Then verify from a workload or diagnostic pod running on the SNO:

```bash
curl -fsS "${VLA_ENDPOINT_URL%/act}/healthz"
```

## Real OpenVLA mode

After mock mode is healthy:

1. Confirm `nvidia-smi` reports the Tesla T4.
2. Confirm Podman CDI exposes `nvidia.com/gpu`.
3. Set `VLA_BASE_FLAVOR=cuda` and `VLA_CONTAINER_IMAGE=localhost/openvla-server:cuda`.
4. Set `VLA_MODE=openvla`.
5. Provide `VLA_HF_TOKEN` locally in `.env` if the selected model requires it.
6. Keep `VLA_BUILD_IMAGE=true` or pre-load the CUDA image on the VM.
7. Re-run `./setup.sh`.

The CUDA image can be large and may require NVIDIA NGC access because the Containerfile uses an NVIDIA PyTorch base. Model weights are cached under `VLA_MODEL_CACHE`.
The service loads `openvla/openvla-7b` lazily on the first `/act` request; a
successful `/readyz` response confirms the configured mode, not completed model
loading or inference.

## Safety boundaries

- `.env` is ignored; real IPs, SSH paths, and tokens must not be committed.
- The playbook assumes passwordless sudo for the configured SSH user.
- The playbook does not create AWS infrastructure or modify security groups.
- TCP `8000` must not be opened to the whole Internet.
- `VLA_MODE=mock` is a wiring check, not evidence that real VLA inference is working.
- Do not run the old AMD/ROCm playbook against this cloud VM.
