// This project was developed with assistance from AI tools.
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Flex,
  FlexItem,
  Label,
  Modal,
  ModalVariant,
  ProgressStepper,
  ProgressStep,
  Spinner,
  Stack,
  StackItem,
  TextInput,
} from "@patternfly/react-core";
import type {
  ArgoAppStatus,
  ArgoResourceStatus,
  ButtonDef,
  DemoLinks,
  FactoryStatus,
  FleetMessage,
  FleetStatus,
  ScenarioDetail,
  StatusLogEntry,
} from "./types.js";
import {
  executeAction,
  fetchArgoStatus,
  fetchFleetStatus,
  fetchScenarioDetail,
} from "./api.js";

const POLL_INTERVAL = 3000;

interface DemoStep {
  id: string;
  label: string;
  action: string;
  preText: string;
  activeText: string;
  doneText: string;
  lookFor: string;
}

const DEMO_STEPS: DemoStep[] = [
  {
    id: "promote",
    label: "Promote v1.4",
    action: "promote-policy",
    preText:
      "Push the new VLA policy version to Factory A via GitOps. This commits a version change to Git and triggers a real Argo CD sync.",
    activeText:
      "Deploying — watch the activity log and Argo sync panel below for real-time progress.",
    doneText:
      "Factory A is now running v1.4. Argo CD sync completed successfully.",
    lookFor:
      "Watch the Activity feed & Status panel below - Deployment resource will cycle through Synced → OutOfSync → Synced as the new policy version rolls out.",
  },
  {
    id: "anomaly",
    label: "Trigger Anomaly",
    action: "trigger-anomaly",
    preText:
      "Inject a high anomaly score to simulate a failing policy. This triggers an automatic rollback via GitOps.",
    activeText:
      "Anomaly detected — the system is automatically reverting Factory A to v1.3 via GitOps.",
    doneText: "Factory A rolled back to v1.3 automatically.",
    lookFor:
      "Watch the Argo panel — a second sync cycle will appear as the rollback commits v1.3 back to Git.",
  },
  {
    id: "reset",
    label: "Rollback Complete",
    action: "reset-fleet-demo",
    preText: "Return all systems to baseline for the next run.",
    activeText: "Resetting…",
    doneText: "Demo reset to baseline.",
    lookFor: "",
  },
];

function phaseToStepIndex(phase: string): number {
  if (phase === "promoting") return 0;
  if (phase === "promoted") return 1;
  if (phase === "anomaly-detected" || phase === "rolling-back") return 1;
  if (phase === "rolled-back") return 2;
  return 0;
}

function isPhaseTransitioning(phase: string): boolean {
  return (
    phase === "promoting" ||
    phase === "anomaly-detected" ||
    phase === "rolling-back"
  );
}

function stepVariant(
  stepIdx: number,
  currentIdx: number,
  transitioning: boolean,
): "success" | "info" | "pending" | "danger" {
  if (stepIdx < currentIdx) return "success";
  if (stepIdx === currentIdx && transitioning) return "info";
  if (stepIdx === currentIdx) return "info";
  return "pending";
}

function statusColor(
  status: string,
): "green" | "blue" | "orange" | "red" | "grey" {
  if (status === "active") return "green";
  if (status === "idle") return "blue";
  if (status === "rerouting") return "orange";
  if (status === "reverting") return "red";
  if (status === "syncing") return "orange";
  if (status === "synced") return "green";
  return "grey";
}

function ProofLink({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="showcase-proof-link"
    >
      {label} ↗
    </a>
  );
}

function ActivityLog({ entries }: { entries: StatusLogEntry[] }) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries.length]);

  return (
    <div className="showcase-activity-log">
      <div className="showcase-activity-log-title">Activity</div>
      <div className="showcase-activity-log-entries">
        {entries.length === 0 ? (
          <div className="showcase-activity-log-entry">
            <span style={{ color: "#8A8D90", fontStyle: "italic" }}>
              Argo CD sync activity will appear here
            </span>
          </div>
        ) : (
          entries.map((e, i) => {
            const time = new Date(e.ts).toLocaleTimeString();
            return (
              <div key={i} className="showcase-activity-log-entry">
                <span className="showcase-activity-log-time">{time}</span>
                <span>{e.message}</span>
              </div>
            );
          })
        )}
        <div ref={endRef} />
      </div>
    </div>
  );
}

function StepDescription({
  step,
  isActive,
  isDone,
  isBusy,
  isTransitioning,
  onAction,
}: {
  step: DemoStep;
  isActive: boolean;
  isDone: boolean;
  isBusy: boolean;
  isTransitioning: boolean;
  onAction: () => void;
}) {
  if (!isActive && !isDone) return null;

  if (isDone) {
    return (
      <div className="showcase-step-guidance">
        <span style={{ color: "#3E8635" }}>{step.doneText}</span>
      </div>
    );
  }

  return (
    <div className="showcase-step-guidance">
      <div style={{ marginBottom: 8 }}>
        {isTransitioning ? step.activeText : step.preText}
      </div>
      {step.lookFor && (
        <div className="showcase-look-for">
          <strong>What to look for:</strong> {step.lookFor}
        </div>
      )}
      {!isTransitioning && (
        <Button
          variant="primary"
          size="sm"
          isLoading={isBusy}
          isDisabled={isBusy}
          onClick={onAction}
          style={{ marginTop: 8 }}
        >
          {step.label}
        </Button>
      )}
    </div>
  );
}

function AnomalyBar({ score }: { score: number }) {
  const pct = Math.min(score * 100, 100);
  const color =
    score >= 0.85 ? "#A30000" : score >= 0.5 ? "#F0AB00" : "#3E8635";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div
        style={{
          width: 120,
          height: 8,
          backgroundColor: "#E0E0E0",
          borderRadius: 4,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: "100%",
            backgroundColor: color,
            borderRadius: 4,
            transition: "width 0.3s ease",
          }}
        />
      </div>
      <span style={{ fontSize: 12, color: "#6A6E73" }}>
        {score.toFixed(2)}
      </span>
    </div>
  );
}

function syncBadgeColor(
  status: string,
): "green" | "orange" | "red" | "grey" {
  if (status === "Synced") return "green";
  if (status === "OutOfSync") return "orange";
  return "grey";
}

function healthBadgeColor(
  status: string,
): "green" | "blue" | "orange" | "red" | "grey" {
  if (status === "Healthy") return "green";
  if (status === "Progressing") return "blue";
  if (status === "Degraded") return "red";
  if (status === "Suspended") return "orange";
  return "grey";
}

function opPhaseBadgeColor(
  phase: string,
): "green" | "blue" | "orange" | "red" | "grey" {
  if (phase === "Succeeded") return "green";
  if (phase === "Running") return "blue";
  if (phase === "Failed" || phase === "Error") return "red";
  return "grey";
}

function ResourceRow({ r }: { r: ArgoResourceStatus }) {
  const syncColor = syncBadgeColor(r.syncStatus);
  const healthColor = r.healthStatus ? healthBadgeColor(r.healthStatus) : null;
  return (
    <div className="showcase-argo-resource-row">
      <span className="showcase-argo-resource-kind">{r.kind}</span>
      <span className="showcase-argo-resource-name">{r.name}</span>
      <Label color={syncColor} isCompact>
        {r.syncStatus}
      </Label>
      {healthColor && (
        <Label color={healthColor} isCompact>
          {r.healthStatus}
        </Label>
      )}
    </div>
  );
}

function ArgoSyncPanel({
  argo,
  links,
}: {
  argo: ArgoAppStatus | null;
  links: DemoLinks | null;
}) {
  if (!argo || argo.syncStatus === "Unknown") return null;

  const rev = argo.syncRevision ? argo.syncRevision.slice(0, 7) : "";
  const opTime =
    argo.operationStartedAt && argo.operationFinishedAt
      ? `${Math.round(
          (new Date(argo.operationFinishedAt).getTime() -
            new Date(argo.operationStartedAt).getTime()) /
            1000,
        )}s`
      : argo.operationStartedAt
        ? "in progress…"
        : "";

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <Flex
            alignItems={{ default: "alignItemsCenter" }}
            spaceItems={{ default: "spaceItemsSm" }}
          >
            <FlexItem>Argo CD: fleet-manager</FlexItem>
            <FlexItem>
              <Label color={syncBadgeColor(argo.syncStatus)} isCompact>
                {argo.syncStatus}
              </Label>
            </FlexItem>
            <FlexItem>
              <Label color={healthBadgeColor(argo.healthStatus)} isCompact>
                {argo.healthStatus}
              </Label>
            </FlexItem>
            <FlexItem>
              <Label color={opPhaseBadgeColor(argo.operationPhase)} isCompact>
                {argo.operationPhase}
              </Label>
            </FlexItem>
            {rev && (
              <FlexItem>
                <span
                  style={{
                    fontFamily: "monospace",
                    fontSize: 12,
                    color: "#6A6E73",
                  }}
                >
                  {rev}
                </span>
              </FlexItem>
            )}
            {opTime && (
              <FlexItem>
                <span style={{ fontSize: 12, color: "#6A6E73" }}>
                  {opTime}
                </span>
              </FlexItem>
            )}
            <FlexItem align={{ default: "alignRight" }}>
              <Flex spaceItems={{ default: "spaceItemsSm" }}>
                {links?.argoFleetManager && (
                  <FlexItem>
                    <ProofLink
                      href={links.argoFleetManager}
                      label="Open in Argo CD"
                    />
                  </FlexItem>
                )}
                {links?.ocpFleetManager && (
                  <FlexItem>
                    <ProofLink
                      href={links.ocpFleetManager}
                      label="fleet-manager pods"
                    />
                  </FlexItem>
                )}
              </Flex>
            </FlexItem>
          </Flex>
        </CardTitle>
      </CardHeader>
      <CardBody className="showcase-card-body-flush">
        <div className="showcase-argo-resource-list">
          {argo.resources.map((r) => (
            <ResourceRow key={`${r.kind}/${r.name}`} r={r} />
          ))}
        </div>
      </CardBody>
    </Card>
  );
}

function FactoryPanel({ factory }: { factory: FactoryStatus }) {
  const prevVersion = useRef(factory.policyVersion);
  const [pillClass, setPillClass] = useState("");
  const [showPromoteModal, setShowPromoteModal] = useState(false);
  const [newVersion, setNewVersion] = useState("");
  const [promoting, setPromoting] = useState(false);

  useEffect(() => {
    if (prevVersion.current !== factory.policyVersion) {
      const cls =
        factory.policyVersion < prevVersion.current
          ? "showcase-policy-pill--reverting"
          : "showcase-policy-pill--promoting";
      setPillClass(cls);
      prevVersion.current = factory.policyVersion;
      const timer = setTimeout(() => setPillClass(""), 600);
      return () => clearTimeout(timer);
    }
  }, [factory.policyVersion]);

  const handlePromoteClick = () => {
    // Pre-fill with next version (e.g., v1.3 → v1.4)
    const currentVer = factory.policyVersion.match(/v(\d+)\.(\d+)/);
    if (currentVer) {
      const nextMinor = parseInt(currentVer[2]) + 1;
      setNewVersion(`v${currentVer[1]}.${nextMinor}`);
    } else {
      setNewVersion("v1.4");
    }
    setShowPromoteModal(true);
  };

  const handlePromoteSubmit = async () => {
    if (!newVersion.trim()) return;
    setPromoting(true);

    try {
      // Call agent query API with promote command
      const query = `Promote model ${newVersion} to ${factory.name}`;
      const resp = await fetch("/api/agent/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });

      if (!resp.ok) {
        console.error("Failed to initiate promotion");
      }

      // Close modal - HIL drawer will open automatically
      setShowPromoteModal(false);
    } catch (err) {
      console.error("Promotion error:", err);
    } finally {
      setPromoting(false);
    }
  };

  const argoClass =
    factory.argoSyncStatus === "syncing" ||
    factory.argoSyncStatus === "reverting"
      ? "showcase-argo-pulse"
      : "";

  return (
    <Card isFullHeight>
      <CardHeader>
        <CardTitle>
          {factory.name}
          <Label
            color={statusColor(factory.argoSyncStatus)}
            isCompact
            className={argoClass}
            style={{ marginLeft: 8 }}
          >
            {factory.argoSyncStatus}
          </Label>
        </CardTitle>
      </CardHeader>
      <CardBody>
        <Stack hasGutter>
          <StackItem>
            <Flex>
              <FlexItem>
                <div style={{ fontSize: 13, color: "#6A6E73" }}>
                  Policy version
                </div>
                <div className={`showcase-policy-pill ${pillClass}`}>
                  {factory.policyVersion}
                </div>
              </FlexItem>
              <FlexItem>
                <div style={{ fontSize: 13, color: "#6A6E73" }}>Robot</div>
                <div>
                  {factory.robotId}{" "}
                  <Label color={statusColor(factory.robotStatus)} isCompact>
                    {factory.robotStatus}
                  </Label>
                </div>
              </FlexItem>
            </Flex>
          </StackItem>

          <StackItem>
            <div style={{ fontSize: 13, color: "#6A6E73" }}>Anomaly score</div>
            <AnomalyBar score={factory.anomalyScore} />
          </StackItem>

          <StackItem>
            <div style={{ fontSize: 12, color: "#6A6E73" }}>
              Last heartbeat: {factory.lastHeartbeat || "—"}
            </div>
          </StackItem>

          <StackItem>
            <Button
              variant="secondary"
              isSmall
              onClick={handlePromoteClick}
              style={{ marginTop: 8 }}
            >
              Promote New Version
            </Button>
          </StackItem>
        </Stack>
      </CardBody>

      {/* Promote Modal */}
      <Modal
        variant={ModalVariant.small}
        title={`Promote Model to ${factory.name}`}
        isOpen={showPromoteModal}
        onClose={() => setShowPromoteModal(false)}
      >
        <Stack hasGutter>
          <StackItem>
            <div style={{ marginBottom: 8 }}>
              <strong>Current version:</strong> {factory.policyVersion}
            </div>
            <div style={{ marginBottom: 16, fontSize: 14, color: "#6A6E73" }}>
              Enter the new model version to promote:
            </div>
            <TextInput
              value={newVersion}
              onChange={(_event, value) => setNewVersion(value)}
              placeholder="v1.4"
              autoFocus
            />
          </StackItem>
          <StackItem>
            <div
              style={{
                fontSize: 13,
                color: "#6A6E73",
                backgroundColor: "#F5F5F5",
                padding: 12,
                borderRadius: 4,
              }}
            >
              This will trigger the Human-in-the-Loop approval flow. You'll
              review the proposed Git changes before the PR is created.
            </div>
          </StackItem>
          <StackItem>
            <Flex justifyContent={{ default: "justifyContentFlexEnd" }}>
              <FlexItem>
                <Button
                  variant="link"
                  onClick={() => setShowPromoteModal(false)}
                >
                  Cancel
                </Button>
              </FlexItem>
              <FlexItem>
                <Button
                  variant="primary"
                  onClick={handlePromoteSubmit}
                  isDisabled={!newVersion.trim() || promoting}
                  isLoading={promoting}
                >
                  Initiate Promotion
                </Button>
              </FlexItem>
            </Flex>
          </StackItem>
        </Stack>
      </Modal>
    </Card>
  );
}

export function FleetView({ events }: { events: FleetMessage[] }) {
  const [fleet, setFleet] = useState<FleetStatus | null>(null);
  const [argo, setArgo] = useState<ArgoAppStatus | null>(null);
  const [scenario, setScenario] = useState<ScenarioDetail | null>(null);
  const [actionBusy, setActionBusy] = useState<string | null>(null);

  const refresh = useCallback(() => {
    fetchFleetStatus().then(setFleet).catch(() => undefined);
    fetchArgoStatus().then(setArgo).catch(() => undefined);
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [refresh]);

  useEffect(() => {
    fetchScenarioDetail("fleet-demo").then(setScenario).catch(() => undefined);
  }, []);

  useEffect(() => {
    const hasFleetEvent = events.some(
      (e) => e.topic === "fleet.events" || e.topic === "fleet.telemetry",
    );
    if (hasFleetEvent) refresh();
  }, [events, refresh]);

  const onStepAction = useCallback(
    async (action: string) => {
      if (!scenario) return;
      const btn = scenario.buttons.find((b: ButtonDef) => b.action === action);
      if (!btn) return;
      setActionBusy(action);
      try {
        await executeAction(btn.action, btn.params);
        setTimeout(refresh, 500);
      } catch {
        // action failed — poll will show current state
      } finally {
        setActionBusy(null);
      }
    },
    [scenario, refresh],
  );

  const demoPhase = fleet?.demoPhase ?? "idle";
  const currentStepIdx = phaseToStepIndex(demoPhase);
  const transitioning = isPhaseTransitioning(demoPhase);

  return (
    <Stack hasGutter>
      <StackItem>
        <Card>
          <CardHeader>
            <CardTitle>Fleet Demo — Policy Promotion & Auto-Rollback</CardTitle>
          </CardHeader>
          <CardBody>
            <ProgressStepper>
              {DEMO_STEPS.map((step, i) => (
                <ProgressStep
                  key={step.id}
                  id={step.id}
                  titleId={`step-${step.id}`}
                  variant={stepVariant(i, currentStepIdx, transitioning)}
                  isCurrent={i === currentStepIdx}
                  description={
                    <StepDescription
                      step={step}
                      isActive={i === currentStepIdx}
                      isDone={i < currentStepIdx}
                      isBusy={actionBusy === step.action}
                      isTransitioning={i === currentStepIdx && transitioning}
                      onAction={() => void onStepAction(step.action)}
                    />
                  }
                >
                  {step.label}
                </ProgressStep>
              ))}
            </ProgressStepper>
            <ActivityLog entries={fleet?.statusLog ?? []} />
          </CardBody>
        </Card>
      </StackItem>

      <StackItem>
        <Flex spaceItems={{ default: "spaceItemsLg" }}>
          {fleet?.factories.map((f) => (
            <FlexItem key={f.name} flex={{ default: "flex_1" }}>
              <FactoryPanel factory={f} />
            </FlexItem>
          )) ?? (
            <FlexItem>
              <Card>
                <CardBody>
                  <Spinner size="md" /> Loading fleet status…
                </CardBody>
              </Card>
            </FlexItem>
          )}
        </Flex>
      </StackItem>

      <StackItem>
        <ArgoSyncPanel argo={argo} links={fleet?.links ?? null} />
      </StackItem>
    </Stack>
  );
}
