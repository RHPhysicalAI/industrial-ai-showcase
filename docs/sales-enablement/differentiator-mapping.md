# Differentiator → Physical AI concern mapping

Every Red Hat differentiator claim in `docs/00-project-charter.md` §22 filtered through the question: **is this on-story for a Physical AI / industrial customer conversation, or generic Red Hat flex that doesn't belong in a demo?**

For each differentiator: the industrial concern it actually maps to, how it's framed in customer language, whether it earns a demo beat (and in which demo), and what gets cut from the surface even if the underlying capability stays in the stack.

## Summary table

| # | Differentiator | Industrial concern it maps to | Demo surface |
|---|---|---|---|
| 1 | On-prem + air-gapped first-class | Factory twins hold IP; defense/regulated manufacturing can't use cloud | All three demos |
| 2 | Containers + VMs + vGPU one platform | Legacy PLC/SCADA/HMI coexist with modern AI workloads on the factory floor | 20-min + 60-min |
| 3 | Hybrid cloud → factory edge → robot | Multi-site fleet operations across real factories | 5-min + 20-min core |
| 4 | OpenShift AI as MLOps backbone | Robot-brain policies need lineage to sim episodes + synthetic data that validated them | 20-min core |
| 5 | Security / supply-chain for OT | OT-grade provenance for every model / policy / command crossing into the factory floor | 60-min only (reframed) |
| 6 | Open model choice | Customers may bring own VLA / world model from their own partnerships | 60-min beat |
| 7 | Agentic orchestration via MCP | LLM agents operate the factory, not just infrastructure — with HIL | 60-min core |
| 8 | Day-2 lifecycle done right | Factory uptime — roll out new policies without stopping the line | 20-min + 60-min |

---

## 1. On-prem and air-gapped first-class

**Industrial concern**: Factory digital twins embed IP — plant layouts, trade-secret processes, proprietary asset geometries. Defense-primed and regulated-manufacturing (aerospace, pharmaceutical, battery, semiconductor) customers can't send that data to a cloud vendor. A "runs fine on DGX Cloud" reference is non-starter for these conversations; the stack must run fully inside the customer's datacenter with no outbound dependencies.

**Customer-language framing**:
> "Your warehouse floor plan and robot policies never leave your walls. The entire reference — simulation, training, inference, orchestration — runs on-prem. We've validated a full rebuild from a local artifact mirror with zero internet access."

**Demo surface**:
- **5-min**: implicit — mention "this runs entirely on-prem" once at the top.
- **20-min**: explicit demo beat — show the companion cluster operating with outbound-disabled networking.
- **60-min**: deep beat — walk through the mirror of every image, SBOM, and dataset, and the rebuild runbook.

**What stays in the stack but off the surface**: specific mirror tooling (`oc-mirror v2`, Quay mirror registries) — technical, named only when an engineer asks.

---

## 2. One platform for containers, VMs, and vGPU workstations

**Industrial concern**: The factory floor is a heterogeneous mess — SCADA HMIs running on Windows VMs that can't be touched, PLCs with vendor-shipped control software, CAD/Omniverse Kit workstations for engineers, modern containerized AI workloads. Customers are *today* managing these on separate stacks (ESXi for the VMs, a Kubernetes cluster for the containers, Citrix for the workstations). Consolidating to one platform directly reduces operational cost.

**Customer-language framing**:
> "The PLC gateway VM, the Omniverse Kit workstation your engineer uses, and the VLA model inference pod for your robot all run on the same cluster. One team operates it, one set of tools, one security boundary."

**Demo surface**:
- **5-min**: not surfaced.
- **20-min**: one beat — show the companion cluster running Isaac Sim (container workload), an inference serving pod (container workload), and a KubeVirt VM representing a legacy PLC controller, side-by-side in the console.
- **60-min**: expanded — add the vGPU Kit workstation streamed via Kit App Streaming to the operator; show how engineers author scenes against the same Nucleus the sim reads from.

**What stays off the surface**: KubeVirt implementation details, QEMU specifics, vGPU partitioning — unless the engineer asks.

---

## 3. Hybrid cloud → factory edge → robot, one operational model

**Industrial concern**: Every industrial customer runs N factories. Each factory has local robots. Each robot has on-board compute. Policy changes need to propagate with deterministic ordering. Failures at one site shouldn't block others. This is the *defining* architectural concern for fleet-scale Physical AI deployment — and Red Hat's ACM + GitOps + Device Edge story is uniquely positioned to address it because no cloud-only provider can honestly claim the factory-edge piece.

**Customer-language framing**:
> "From the hub that trains policies, through ACM to each factory's local cluster, through MicroShift to the compute on the robot itself — one image, signed once, deploys everywhere. A new VLA policy goes to one factory first, runs for a week, then promotes to the rest via Git PR."

**Demo surface**:
- **5-min**: core beat — show the hub→companion flow for a single mission, emphasize "this would replicate across every factory site."
- **20-min**: expanded — show ACM multi-site rollout to a second simulated spoke.
- **60-min**: deep — walk the actual deployment topology; show a policy promoted to factory A, observed in MLflow, then promoted to factory B via PR merge.

**What stays off the surface**: Argo internals, ACM control-plane specifics, Submariner — engineer-only detail.

---

## 4. OpenShift AI as MLOps backbone for robot brains

**Industrial concern**: When a robot behaves unexpectedly on the factory floor, the first question is "which policy version is it running, and what data trained it?" Customers need full lineage from live robot telemetry → deployed policy version → MLflow registry → training run → sim episodes / synthetic-data batch → hyperparameters. Without this trace, debugging a production robot incident is impossible.

**Customer-language framing**:
> "When this robot makes a decision you don't expect, we can trace back: which policy version, what metrics did it score in sim validation, what data did it train on, who approved the promotion, which PR merged it to production. Same MLOps story you'd want for any model — extended to robot policies."

**Demo surface**:
- **5-min**: not surfaced (too much depth).
- **20-min**: core beat — show a policy being retrained from a scenario, landing in MLflow with metrics, promoted via GitOps PR, rolled out to a spoke.
- **60-min**: deep — include the rollback flow when validation regresses.

**What stays off the surface**: MLflow schema internals, model registry backend (Postgres), artifact store (SeaweedFS/ODF) — engineers care, customers don't unless asked.

---

## 5. Security and supply-chain posture — REFRAMED FROM GENERIC TO OT-GRADE

**The reframing the customer needs**: Industrial customers do not hear "Sigstore" or "SBOM" and think "I need that." They hear "a model from the cloud told my $2M humanoid to do something it wasn't supposed to" and think "how do I stop that?" Security framing that works in industrial Physical AI conversations:

- **Supply-chain attestation for AI artifacts** — not "we sign container images" but "every VLA / world-model / scene-reasoning update that can command a physical robot has cryptographic provenance traceable to the training run that produced it, and is refused at admission if the chain breaks."
- **Air-gap as operational default** — "your factory doesn't phone home. Not to us, not to NVIDIA, not to anyone. All updates are pulled from a mirror you control."
- **Network segmentation appropriate to OT** — "the robot-brain inference endpoint talks only to the mission dispatcher, only on mTLS, only from your specific service accounts. The factory-floor VLAN is isolated by NetworkPolicy; nothing reaches it that you didn't explicitly authorize."

**What gets CUT from the demo surface even though it stays in the stack**:

- **FIPS mode** — only surfaced if the customer is defense-primed (Lockheed, Boeing, DoD manufacturing). Otherwise no sell; keep the capability, drop the demo beat.
- **STIG profile compliance** — same. Keep the capability, surface only for regulated-manufacturing / defense conversations. Reference to Compliance Operator scan results stays in the Console as "evidence available on request."
- **Cluster-scoped admission controllers / custom SCCs** — engineer-level detail; 60-min deep-dive only.
- **Service Mesh mTLS** — surfaces only if there's a specific "robot-to-controller trust boundary" demo beat. Otherwise out of demo surface.

**Demo surface**:
- **5-min**: not surfaced.
- **20-min**: not surfaced.
- **60-min**: the ONLY demo where security surfaces as a beat. Specific moment: show a tampered-with VLA model rejected at admission because the signature chain doesn't trace back to a known training run. Or: an agent trying to command a fleet intervention is intercepted by Llama Stack's HIL approval gate — security as *operational control*, not as policy checkboxes.

**Charter item §5 text should be revised** to remove the shopping list (Sigstore / SBOMs / STIG / FIPS / Multus / Istio) from the headline framing and replace with "OT-appropriate provenance + air-gap + segmentation." The underlying technologies stay, but the sales pitch is about the customer's concern, not our feature list.

---

## 6. Open model choice

**Industrial concern**: The Physical AI model ecosystem is moving fast. Customers have partnerships — Siemens with its own model work, Foxconn with multiple vendors, defense customers with contractor-specific fine-tunes. A reference that locks them to NVIDIA's models is a reference they can't adopt.

**Customer-language framing**:
> "Your fine-tuned VLA slots in without code changes. The serving layer takes a model profile — checkpoint, tokenizer config, action-space spec — as configuration. Swap NVIDIA's GR00T for OpenVLA, pi-0, or your own model; same inference API, same observability, same MLOps trace."

**Demo surface**:
- **5-min**: not surfaced.
- **20-min**: one line during the MLOps beat — "this VLA is OpenVLA today; swap to any other is a config change."
- **60-min**: explicit demo beat — live-swap the served VLA between two model profiles mid-demo; Fleet Manager doesn't notice.

**What's on the surface vs off**: the framing we ship with is "open-model-first" per licensing-gates — OpenVLA primary, GR00T as one of several. Do not start the demo with "NVIDIA GR00T is primary and here are alternatives"; the platform posture is "bring any VLA" and NVIDIA's is one instance.

---

## 7. Agentic orchestration via MCP

**Industrial concern**: Factory operators today are flooded with dashboards, alerts, and tooling fragmentation. The real customer ask: "can a natural-language interface operate this factory safely, asking me to approve anything that matters?" This is the Llama-Stack HIL differentiator made concrete — agentic action on physical systems, with human-in-the-loop gates on anything that changes state.

**Customer-language framing**:
> "An operator types 'what if we added two more humanoids to Zone B?' The agent composes a sim experiment, runs scenario variants, summarizes findings, and drafts a fleet reconfiguration. The operator reviews and approves. Nothing state-changing happens without the HIL gate."

**Demo surface**:
- **5-min**: not surfaced.
- **20-min**: not surfaced.
- **60-min**: core beat — live agent run from the Console: natural-language input, agent plan visualization, MCP tool calls, HIL approval moment, results.

**What's on the surface**: the agent's outputs, the HIL approval drawer, what tools the agent called and why.
**What stays off**: the LangGraph internals, the MCP protocol wire format, the Llama Stack architecture — engineers ask, otherwise skip.

---

## 8. Day-2 lifecycle done right

**Industrial concern**: Factory uptime is the metric. A policy regression that takes an AMR fleet offline for an hour is real money. Rolling updates without stopping the line is table stakes; rollback in minutes when a policy regresses is the actual differentiator.

**Customer-language framing**:
> "New VLA policy rolls to Factory A's Zone 1 robots first. Fleet Manager observes telemetry. If anomaly score spikes, GitOps auto-rollbacks via Argo's last-known-good. No human intervention, no line stoppage. Promoted forward across factories only after the anomaly window clears."

**Demo surface**:
- **5-min**: not surfaced.
- **20-min**: one beat — show a policy promotion, then a rollback, via Git PR and revert.
- **60-min**: expanded — include the anomaly-triggered auto-rollback flow.

**What stays off the surface**: Argo sync-policy specifics, Kustomize overlay patterns — engineer detail.

---

## Crosscuts

**Things in the stack that earn zero demo surface**:
- Service Mesh control-plane specifics, operator lifecycle, every secondary operator (logging stack internals, mesh observability CRDs, etc.) — they exist because they support the surface capability, not because a customer asks about them.
- Internal image registry plumbing.
- Most monitoring / observability operators (they appear in the Console's metrics panels, not as a deploy-topology beat).

**Framing rules for every demo script (binding on tasks #14, #15, #16)**:
1. Open each demo with the **industrial customer concern** first, Red Hat answer second. Never "look at all these Red Hat features and let us show you how they fit Physical AI" — that's generic-Red-Hat-flex voice.
2. If a Red Hat differentiator doesn't have an industrial concern paragraph at the top of this mapping, it doesn't earn a demo beat. Talk-track only.
3. Security content (item #5) gets the "OT-grade" framing or it gets cut. Never surface FIPS/STIG/Sigstore as checkboxes — always as "here's the customer concern these solve."
4. Every beat names the differentiator number it substantiates, in a comment the script author can grep on.
