# Industrial AI Showcase Roadmaps

This directory is the human-friendly roadmap for the Industrial AI Showcase.
It is designed to hold multiple goals, each with a clear outcome, ordered
steps, dependencies, and a definition of done.

If you arrived here from GitHub, this is the roadmap landing page linked from
the repository [home page](../README.md). It is the right place to understand
the work sequence before opening a component-specific README.

The roadmap describes the work at a program level. Detailed implementation
contracts remain in component READMEs, manifests, ADRs, and the individual
roadmap documents linked below.

## How to use this roadmap

Each goal should answer five questions:

1. What are we trying to achieve?
2. Why does it matter?
3. What steps get us there?
4. What is already complete?
5. What proves the goal is done?

Use the following status labels:

- ✅ **Complete** — the goal has been achieved and verified.
- 🔄 **In progress** — work is actively under way.
- ⏭️ **Next** — the next practical goal on the current path.
- ⏸️ **Deferred** — intentionally postponed; not required for the current demonstration.

## Current deployment path

The current path is the hosted-demo topology. It intentionally avoids the
historical Fedora/bare-metal Companion implementation.

```text
Local workstation
  ├── Git + preflight checker
  ├── Hub kubeconfig ───────────────► Hub OpenShift / ACM / Kafka
  └── Companion kubeconfig ─────────► Hosted Companion SNO

Hosted Companion SNO ── Kafka TLS route ──► Hub Kafka
Hosted Companion SNO ── HTTP /act ────────► Cloud GPU VM / OpenVLA
```

The current VLA path uses a separate NVIDIA cloud VM running pretrained
OpenVLA-7B. The full training, MLflow registration, MinIO promotion, and
production-model lifecycle are future work; they are not required to prove
the initial hosted demo loop.

## Goal overview

| Goal | Outcome | Status |
| --- | --- | --- |
| [Goal 1 — Establish the supported topology](#goal-1--establish-the-supported-topology) | Agree on the machines, clusters, responsibilities, and terminology. | ✅ Complete |
| [Goal 2 — Make the Cloud VLA VM usable](#goal-2--make-the-cloud-vla-vm-usable) | Provision and validate the separate NVIDIA VM serving OpenVLA. | ✅ Complete |
| [Goal 3 — Prepare the hosted Companion SNO](#goal-3--prepare-the-hosted-companion-sno) | Record the SNO contract and keep its setup limited to the hosted-demo scope. | ✅ Complete |
| [Goal 4 — Connect the Companion SNO to Hub ACM](#goal-4--connect-the-companion-sno-to-hub-acm) | Register the SNO with ACM and verify it is joined and available. | ✅ Complete |
| [Goal 5 — Deploy the first hosted workload slice](#goal-5--deploy-the-first-hosted-workload-slice) | Run Fake Camera and Mission Dispatcher on the SNO using Hub Kafka and the cloud VLA endpoint. | ⏭️ Next |
| [Goal 6 — Prove the end-to-end demo loop](#goal-6--prove-the-end-to-end-demo-loop) | Validate the complete camera → Kafka → dispatcher → VLA action path. | ⏸️ Deferred until Goal 5 |
| [Goal 7 — Move toward the full model lifecycle](#goal-7--move-toward-the-full-model-lifecycle) | Add training, registry, storage, promotion, and production-model serving. | ⏸️ Deferred |

## Goal 1 — Establish the supported topology

### Objective

Define a deployment shape that can be reproduced without requiring a
specific private bare-metal machine.

### Steps

1. Use the local workstation for Git, OpenShift CLI access, and preflight checks.
2. Use the Hub cluster for central services, ACM, GitOps, and Kafka.
3. Use a hosted SNO from `demo.redhat.com` as the temporary Companion edge cluster.
4. Use a separate NVIDIA cloud VM for VLA serving.
5. Treat Fedora/bare-metal self-managed Companion and host-native ROCm serving as historical reference, not the supported current path.
6. Use `Hub`, `Companion`, `Cloud VLA VM`, and `Local workstation` consistently.

### Done when

- The topology is documented and agreed upon.
- Each environment has a clear responsibility.
- The checker and deployment documentation use the same terminology.

### References

- [`roadmaps/prereq.md`](prereq.md)
- [`tools/preflight/README.md`](../tools/preflight/README.md)

## Goal 2 — Make the Cloud VLA VM usable

### Objective

Provide a repeatable setup for a separate Ubuntu/NVIDIA VM that can serve
VLA actions to the Companion SNO.

### Steps

1. Record the VM connection details only in the ignored local `.env`.
2. Use the dedicated cloud VM Ansible setup under `tools/cloud-vm-setup/`.
3. Install or validate the NVIDIA driver, container runtime, and GPU runtime.
4. Build and start the VLA service as `openvla-server.service`.
5. Validate `/healthz` and `/readyz`.
6. Validate `/act` with a non-destructive action request.
7. Restrict inbound access to the SNO egress CIDR rather than opening the service to the Internet.

### Done when

- The VM is reachable over SSH.
- The GPU and NVIDIA container runtime are usable.
- The VLA service is active and reports healthy.
- A real OpenVLA action request succeeds.
- No VM IP, key, token, or credential is committed to Git.

### References

- [`tools/cloud-vm-setup/README.md`](../tools/cloud-vm-setup/README.md)
- [`tools/cloud-vm-setup/ansible/site.yml`](../tools/cloud-vm-setup/ansible/site.yml)
- [`docs/vla-model-deployment-modes.md`](../docs/vla-model-deployment-modes.md)

## Goal 3 — Prepare the hosted Companion SNO

### Objective

Use the temporary `demo.redhat.com` SNO as the Companion edge environment
without applying the old self-managed infrastructure assumptions.

### Steps

1. Obtain the SNO kubeconfig or API login details.
2. Record the cluster name, API URL, console URL, ingress domain, version, and expiry locally.
3. Capture a read-only baseline.
4. Confirm storage, image pulls, Git access, Hub access, and outbound reachability to the Cloud VLA VM.
5. Keep the initial scope limited to the hosted workload slice.
6. Do not install LVMS, KubeVirt, the PLC VM, compliance tooling, or the old Fedora/bare-metal stack unless a later goal explicitly requires them.

### Done when

- The SNO baseline is captured and reviewed.
- Provider restrictions are understood.
- The hosted overlay renders successfully.
- The SNO is ready for ACM enrollment and workload deployment.

### References

- [`tools/demo-redhat-sno/README.md`](../tools/demo-redhat-sno/README.md)
- [`tools/demo-redhat-sno/capture-baseline.sh`](../tools/demo-redhat-sno/capture-baseline.sh)
- [`infrastructure/gitops/apps/demo-redhat-sno/`](../infrastructure/gitops/apps/demo-redhat-sno/)

## Goal 4 — Connect the Companion SNO to Hub ACM

### Objective

Make the Hub aware of the hosted Companion and establish the ACM-managed
cluster relationship.

### Steps

1. Create the Hub-side `ManagedCluster` and `ManagedClusterSet` resources.
2. Retrieve the generated ACM import material from the Hub.
3. Apply the required ACM CRDs and import payload to the intended SNO.
4. Wait for the SNO klusterlet and registration agent to become healthy.
5. Verify `JOINED=True` and `AVAILABLE=True` on the Hub.
6. Record the successful registration in the deployment notes or baseline.

### Current result

The Companion SNO is registered successfully:

- Hub accepted the cluster.
- ACM import succeeded.
- The Companion reports `JOINED=True`.
- The Companion reports `AVAILABLE=True`.

### Done when

- Hub ACM can see the Companion as joined and available.
- The SNO agent is running.
- The connection can be rechecked using the preflight checker.

### References

- [`infrastructure/gitops/apps/hub-acm/`](../infrastructure/gitops/apps/hub-acm/)
- [`tools/preflight/check.py`](../tools/preflight/check.py)
- [`tools/demo-redhat-sno/README.md`](../tools/demo-redhat-sno/README.md)

## Goal 5 — Deploy the first hosted workload slice

### Objective

Deploy only the components required for the first warehouse event loop on
the hosted SNO.

### Steps

1. Ensure the fork changes are available in `rhkp/industrial-ai-showcase`.
2. Point the live Hub GitOps source at the fork in a controlled change.
3. Enable the hosted-SNO GitOps integration and ApplicationSet.
4. Deploy the hosted overlay from `infrastructure/gitops/apps/demo-redhat-sno/`.
5. Create runtime configuration from the ignored `.env` for Hub Kafka and the VLA endpoint.
6. Copy the required Hub Kafka CA material into the SNO workload namespace.
7. Build and deploy Fake Camera.
8. Build and deploy Mission Dispatcher.
9. Verify Routes, deployments, Kafka configuration, and VLA endpoint configuration.

### Done when

- Fake Camera is running in `warehouse-edge`.
- Mission Dispatcher is running in `robot-edge`.
- The hosted SNO uses the Hub Kafka TLS route.
- Mission Dispatcher points to the Cloud VLA VM.
- GitOps reports the hosted overlay as synced and healthy.

### References

- [`tools/demo-redhat-sno/deploy-workload.sh`](../tools/demo-redhat-sno/deploy-workload.sh)
- [`infrastructure/gitops/apps/demo-redhat-sno/`](../infrastructure/gitops/apps/demo-redhat-sno/)
- [`tools/demo-redhat-sno/README.md`](../tools/demo-redhat-sno/README.md)

## Goal 6 — Prove the end-to-end demo loop

### Objective

Demonstrate that the hosted Companion can consume simulated camera data,
communicate through Hub Kafka, call the real VLA service, and produce an
action response.

### Steps

1. Confirm Fake Camera publishes a healthy stream.
2. Confirm Mission Dispatcher consumes the expected Kafka topics.
3. Send a safe synthetic mission or camera-state event.
4. Confirm the dispatcher reaches the Cloud VLA VM over HTTP.
5. Confirm the VLA service returns a valid action vector.
6. Confirm the response is handled by the dispatcher without errors.
7. Capture logs and checker output as demonstration evidence.

### Done when

- The complete path works without a physical robot.
- The fake camera is clearly identified as a simulator.
- The action response is produced by the real OpenVLA service rather than mock mode.
- The result can be repeated from documented commands.

## Goal 7 — Move toward the full model lifecycle

### Objective

Add the full training and model-management path after the hosted demo loop
is stable.

### Steps

1. Validate the Hub RHOAI training prerequisites.
2. Run the GR00T/VLA training pipeline on an appropriate GPU environment.
3. Upload the resulting model to MinIO/S3.
4. Register the model in MLflow Model Registry.
5. Validate the model artifact and metadata.
6. Update the serving configuration to use a versioned model URI.
7. Promote the model through the GitOps/HIL workflow.
8. Validate rollback and model-version observability.

### Done when

- A versioned fine-tuned model exists in storage and the registry.
- The serving layer can load that model through a controlled configuration change.
- Promotion and rollback are reviewable and reproducible.

### Current status

Deferred. The current hosted path uses pretrained OpenVLA-7B on the Cloud VLA
VM. Do not switch to this goal until the hosted workload and end-to-end loop
are stable.

## Future roadmap documents

New roadmaps should be added under this directory and follow the same pattern:

1. Purpose and objective
2. Current state
3. Goals and non-goals
4. Dependencies and decisions
5. Ordered implementation steps
6. Definition of done
7. Risks and open questions
8. References and validation commands

Candidate documents:

- [`deployment.md`](deployment.md) — complete installation and rollout flow.
- [`demo-workload.md`](demo-workload.md) — operational warehouse demonstration.
- [`observability.md`](observability.md) — logs, metrics, traces, and evidence.
- [`security.md`](security.md) — signing, SBOMs, FIPS, STIG, and air-gap posture.
- [`multisite.md`](multisite.md) — Factory B, ACM policy rollout, and rollback.
- [`mlops.md`](mlops.md) — training, lineage, registry, promotion, and serving.
- [`agentic.md`](agentic.md) — LangGraph, MCP, HIL, and governance.
