# Security Posture

> [!NOTE]
> This project was developed with assistance from AI tools.

This document describes the security controls in the Warehouse Blueprint
architecture. Every claim is either **implemented in this repository**,
**provided by the OpenShift platform**, or **cited from upstream documentation**.
Where a control is planned but not yet deployed, we say so.

## Secrets Management — HashiCorp Vault + VSO

All sensitive credentials are stored in HashiCorp Vault and projected into
Kubernetes Secrets via the Vault Secrets Operator (VSO).

| Property | Implementation |
|----------|----------------|
| Vault deployment | Single-node StatefulSet in the `vault` namespace, Argo CD–managed |
| Auth method | Kubernetes auth — pods authenticate via their ServiceAccount token (600s TTL) |
| Secret engine | KV v2 (versioned key-value store) |
| Projection | `VaultStaticSecret` CRs per namespace — each creates a Kubernetes Secret and refreshes it hourly |
| Rotation | VSO re-reads from Vault every `refreshAfter: 1h`; Vault-side rotation is independent |

**Credentials managed by Vault (deployed):**

- Argo CD repository credentials (GitHub PAT)
- SeaweedFS/S3 access keys (MLflow, DSPA, warehouse camera library, observability storage)
- NGC API keys (Isaac Sim, Kit App Streaming, Nucleus)
- HuggingFace tokens (gated model downloads for VLA training, Cosmos)
- Nucleus service passwords and crypto material
- Git source secrets for BuildConfigs (hub and companion via ACM policy)

**Zero secrets are stored in Git.** The one exception is the Model Registry
Postgres password (`db-secret.yaml`), which uses a non-sensitive default for
the RHOAI-operator-managed database. Production deployments would Vault-manage
this credential.

Source: [HashiCorp Vault Secrets Operator docs](https://developer.hashicorp.com/vault/docs/platform/k8s/vso)

## GitOps as the Control Plane

All cluster state is declared in Git and reconciled by Argo CD. This is not
just a deployment convenience — it is the security enforcement mechanism.

| Property | Implementation |
|----------|----------------|
| Argo CD version | OpenShift GitOps (Red Hat-supported Argo CD distribution) |
| Reconciliation | ApplicationSets with git-directory generators auto-discover new components |
| Drift detection | Argo CD continuously compares live state to Git; manual cluster edits are flagged as OutOfSync |
| Rollback | `git revert` + Argo sync — policy changes revert in seconds, not hours |
| Audit trail | Every change is a Git commit with author, timestamp, and PR review history |

**What this means for security:**

- No `oc apply` by hand for long-lived state. If it's not in Git, it doesn't persist.
- Policy promotions (VLA model versions, safety thresholds) go through PR review before reaching any cluster.
- Rollback is a first-class operation — a policy that causes anomalies can be reverted by reverting a commit.

The ApplicationSet structure separates concerns by layer: `operators`, `platform`,
`workloads`, `observability`, `hub-acm`, and `companion`. Each layer can have
independent sync policies and approval gates.

Source: [Red Hat OpenShift GitOps docs](https://docs.redhat.com/en/documentation/red_hat_openshift_gitops/)

## Network Segmentation

### Kubernetes NetworkPolicies

Workloads are segmented by namespace with explicit ingress rules. NetworkPolicies
are deployed for:

- Fleet Manager (`fleet-ops`)
- Cosmos Reason (`cosmos`)
- WMS Stub, Camera Adapter, Obstruction Detector (workload namespaces)
- Isaac Sim (GPU workload namespace)
- Nucleus (with Istio mTLS overlay)
- MES Stub, PLC Gateway VM (companion)

**Pattern:** Each workload's NetworkPolicy allows ingress only from its own
namespace and from `openshift-monitoring` / `openshift-user-workload-monitoring`
(for Prometheus scraping). Cross-namespace access (e.g., fleet-ops → cosmos) is
declared explicitly by namespace label selector.

Egress is permissive in the current deployment — OVN-Kubernetes DNS resolution
makes precise egress rules non-trivial. Egress hardening is planned alongside
Service Mesh mTLS enforcement.

### Kafka Listener Isolation

AMQ Streams (Strimzi) Kafka deploys three listeners with different security postures:

| Listener | Port | TLS | Authentication | Purpose |
|----------|------|-----|----------------|---------|
| `plain` | 9092 | No | None | Intra-namespace workloads (co-located with Kafka) |
| `tls` | 9093 | Yes | mTLS (client certificate) | Authenticated intra-cluster communication |
| `external` | 9094 | Yes | Server-side TLS (no client auth) | Companion-to-hub via OpenShift Route passthrough |

The external listener uses TLS-passthrough Routes so the companion cluster
reaches the hub Kafka over encrypted connections. Client mTLS authentication on
the external listener is planned for Phase 2 alongside per-consumer `KafkaUser` CRs.

Kafka is configured with `auto.create.topics.enable: false` — topics must be
declared as `KafkaTopic` CRs in Git. This prevents accidental topic creation
from misconfigured producers.

Source: [AMQ Streams / Strimzi listener configuration](https://strimzi.io/docs/operators/latest/deploying#assembly-securing-access-str)

### Service Mesh (Istio)

OpenShift Service Mesh (Sail Operator, Istio v1.28.5) is deployed with:

- `IstioCNI` for transparent traffic interception (no init container privilege escalation)
- `PeerAuthentication` in PERMISSIVE mode for Nucleus namespace — mesh-enrolled
  pods communicate via mTLS automatically; non-mesh callers (e.g., OpenShift Router)
  can still reach services over plaintext

Moving to STRICT mTLS mesh-wide is a Phase 2+ hardening item that requires migrating
external access from OpenShift Routes to an Istio Ingress Gateway.

Source: [Red Hat OpenShift Service Mesh docs](https://docs.redhat.com/en/documentation/red_hat_openshift_service_mesh/)

## Compliance Scanning

The companion cluster runs the OpenShift Compliance Operator with DISA STIG profiles:

| Property | Implementation |
|----------|----------------|
| Profiles | `ocp4-stig-v2r3`, `ocp4-stig-node-v2r3`, `rhcos4-stig-v2r3` (pinned for reproducible evidence) |
| Schedule | Daily at 06:00 UTC |
| Auto-remediation | Disabled (`autoApplyRemediations: false`) — remediations are reviewed and applied under human supervision |
| Storage | Raw scan results stored in 2 Gi PVCs on LVMS, 10-rotation history |

The companion cluster is the compliance validation surface because it is
a self-managed OpenShift installation where MachineConfigs, kernel tuning, and
STIG remediations can be applied without conflicting with managed-service
automation.

Source: [OpenShift Compliance Operator docs](https://docs.redhat.com/en/documentation/openshift_container_platform/4.18/html/security_and_compliance/compliance-operator)

## Container Image Verification

### Companion cluster — ClusterImagePolicy

The companion cluster enforces Sigstore signature verification for OpenShift
component images via a `ClusterImagePolicy`:

- **Scope:** `quay.io/openshift-release-dev/ocp-v4.0-art-dev` (operator operand images pulled from the release payload)
- **Policy:** `PublicKey` root of trust using the Red Hat release-signing public key
- **Match:** `MatchRepoDigestOrExact` — images must have a valid signature matching their digest

This extends the platform-shipped `openshift` ClusterImagePolicy (which covers
release manifests at `ocp-release`) to include the individual component images
that CVO deploys.

### Container base images

All project-built container images use Red Hat Universal Base Image (UBI):

- Python workloads: `registry.access.redhat.com/ubi9/python-312:latest`
- Node.js workloads: `registry.access.redhat.com/ubi9/nodejs-22:latest`

UBI images receive Red Hat security errata and are rebuilt when CVEs are
published against included packages.

Source: [Red Hat UBI documentation](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/9/html/building_running_and_managing_containers/assembly_types-of-container-images_building-running-and-managing-containers)

## Identity and Access Control

### Per-workload ServiceAccounts

Every workload runs under a dedicated ServiceAccount — none use the namespace
`default` ServiceAccount. This is enforced by including a `serviceaccount.yaml`
in each workload's Kustomization. Dedicated ServiceAccounts enable:

- Fine-grained RBAC (each workload gets only the permissions it needs)
- Vault Kubernetes auth scoping (VSO authenticates as the workload's ServiceAccount)
- Audit log attribution (API server audit logs show which workload made each call)

### ACM Policy-Based Access

Red Hat Advanced Cluster Management propagates configuration to spoke clusters
via `Policy` CRs with `remediationAction: enforce`. The companion cluster
receives:

- Namespace and RBAC setup for workload namespaces
- Git source secrets (propagated from hub Vault via ACM policy templates, not stored in spoke Git)
- Compliance operator configuration

ACM policies reference NIST SP 800-53 control families in their annotations
(`policy.open-cluster-management.io/standards: NIST SP 800-53`).

Source: [Red Hat ACM Policy documentation](https://docs.redhat.com/en/documentation/red_hat_advanced_cluster_management_for_kubernetes/)

## Data Durability and Integrity

### Kafka

- Replication factor 3 across all topics (`default.replication.factor: 3`)
- `min.insync.replicas: 2` — producers block rather than accept data loss
- 7-day retention with 1 GB per-partition cap
- KRaft mode (no ZooKeeper dependency)

### Object Storage

The 2026-09-29 migration targets SeaweedFS for MLflow artifacts, training data,
DSPA pipeline artifacts, observability, and the warehouse camera library.
Its three storage namespaces use a shared Kustomize base with one replica each
and an S3-only Service on port `8333`. Credentials are Vault-managed; no access
key values are committed. Rotation must be coordinated with consumers that
load credentials at startup. CPU-only S3 validation passed in the isolated
namespace and from `vla-training`; see the [evidence](../../tools/object-storage/VALIDATION.md)
and [controlled copy/cutover guide](../../tools/object-storage/README.md).

### Database

- Model Registry: PostgreSQL managed by the RHOAI operator
- DSPA: MariaDB deployed by the DSPA operator
- MLflow: PostgreSQL via CloudNativePG operator (with WAL archiving to S3)

## Operator Lifecycle

All operators are installed via OperatorHub subscriptions managed in Git:

| Operator | Channel | Source |
|----------|---------|--------|
| AMQ Streams (Strimzi) | stable | redhat-operators |
| Red Hat ACM | release-2.16 | redhat-operators |
| Compliance Operator | stable | redhat-operators |
| CloudNativePG | stable-v1 | certified-operators |
| Ansible Automation Platform | stable-2.6-cluster-scoped | redhat-operators |
| Cluster Logging | stable-6.5 | redhat-operators |
| Loki Operator | stable-6.5 | redhat-operators |
| Vault Secrets Operator | stable | certified-operators |
| Service Mesh (Sail Operator) | — (Istio CR, not Subscription-managed) | — |

Operator subscriptions are Argo CD–managed. Version pinning and upgrade
policy are controlled via `installPlanApproval` and `startingCSV` in each
Subscription CR.

## What Is Not Yet Deployed

Transparency about what the architecture supports but is not yet implemented:

| Control | Status |
|---------|--------|
| STRICT mTLS mesh-wide | PERMISSIVE on Nucleus only |
| Kafka client mTLS (external listener) | Server-side TLS only |
| Egress NetworkPolicy hardening | Permissive egress |
| Image signing for project-built images | Not deployed |
| SBOMs per container image | Not deployed |
| Runtime threat detection (StackRox/ACS) | Not deployed |
| Human-in-the-loop approval for agent actions | Not deployed |
| FIPS 140-2 mode | Not enabled on hub |
| Vault HA (multi-node Raft) | Single-node Vault |

## Platform Security Inherited from OpenShift

These controls are provided by the OpenShift platform and do not require
project-specific configuration:

- **Cluster-wide TLS:** OpenShift's internal PKI issues certificates for all
  API server, etcd, and kubelet communication. Service-serving certificates
  are available via the `service.beta.openshift.io/serving-cert-secret-name`
  annotation.
- **SCC enforcement:** OpenShift's Security Context Constraints restrict
  container capabilities by default. Workloads run under `restricted-v2` SCC
  unless explicitly granted elevated access (e.g., GPU workloads via the
  NVIDIA GPU Operator's SCC).
- **etcd encryption:** OpenShift supports etcd encryption at rest (enabled
  via the API server encryption configuration).
- **Audit logging:** API server audit logs capture all authenticated requests.
  OpenShift Logging (deployed via Loki + ClusterLogForwarder) aggregates logs
  cluster-wide.
- **OAuth / OIDC:** OpenShift's built-in OAuth server handles user
  authentication. Identity providers (LDAP, OIDC, htpasswd) are
  configurable per cluster.
- **Node auto-updates:** The Machine Config Operator manages OS-level
  updates and security patching across all nodes.

Source: [OpenShift Security Guide](https://docs.redhat.com/en/documentation/openshift_container_platform/4.18/html/security_and_compliance/)
