// This project was developed with assistance from AI tools.
import type { ArgoSync } from "./argoSync.js";
import type { SimpleLogger } from "./kafkaStream.js";

export type DemoPhase =
  | "idle"
  | "training-running"
  | "training-complete"
  | "promoting"
  | "promoted"
  | "anomaly-detected"
  | "rolling-back"
  | "rolled-back";

export type ArgoSyncStatus = "synced" | "syncing" | "reverting";

export type LineageNodeStatus = "completed" | "running" | "pending";

export interface AnomalyPoint {
  t: number;
  v: number;
}

export interface StatusLogEntry {
  ts: number;
  message: string;
}

export interface RollbackAnalysis {
  timestamp: string;
  factory: string;
  from_version: string;
  to_version: string;
  trigger: string;
  agent_analysis: string;
  session_id: string;
}

interface FactoryState {
  policyVersion: string;
  argoSyncStatus: ArgoSyncStatus;
}

const BASELINE_VERSION = "vla-warehouse-v1.3";
const ANOMALY_RING_SIZE = 60;
const ARGO_POLL_MS = 3000;
const ARGO_FALLBACK_MS = 4000;

export class DemoState {
  phase: DemoPhase = "idle";
  factories: Record<string, FactoryState> = {
    "factory-a": { policyVersion: BASELINE_VERSION, argoSyncStatus: "synced" },
    "factory-b": { policyVersion: BASELINE_VERSION, argoSyncStatus: "synced" },
  };
  lineageStatuses: Record<string, LineageNodeStatus> = {
    dataset: "completed",
    pipeline: "completed",
    training: "completed",
    validation: "completed",
    model: "completed",
  };
  anomalyHistory: AnomalyPoint[] = [];
  statusLog: StatusLogEntry[] = [];
  rollbackAnalyses: RollbackAnalysis[] = [];
  private timers: ReturnType<typeof setTimeout>[] = [];
  private promotedVersion: string = BASELINE_VERSION;
  argoSync: ArgoSync | null = null;
  wmsStubBaseUrl: string = "";
  log: SimpleLogger | null = null;

  private async publishAnomalyScore(
    robotId: string,
    score: number,
  ): Promise<void> {
    if (!this.wmsStubBaseUrl) return;
    try {
      await fetch(`${this.wmsStubBaseUrl}/trigger-anomaly`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ robot_id: robotId, anomaly_score: score }),
      });
    } catch {
      this.log?.warn({}, "demoState: failed to publish anomaly score");
    }
  }

  private addLog(message: string): void {
    this.statusLog.push({ ts: Date.now(), message });
    if (this.statusLog.length > 20) this.statusLog.shift();
  }

  promotePolicy(factory: string, version: string, skipGitCommit: boolean = true): void {
    const f = this.factories[factory];
    if (!f) return;
    this.promotedVersion = version;
    this.phase = "promoting";
    f.argoSyncStatus = "syncing";
    this.statusLog = [];
    this.addLog(`Starting promotion of ${factory} to ${version}`);

    if (this.argoSync?.enabled && !skipGitCommit) {
      // Legacy path: console makes the Git commit (used by direct UI promotions, not HIL)
      void this.realArgoPromote(factory, version);
    } else if (this.argoSync?.enabled && skipGitCommit) {
      // HIL path: PR already merged by orchestrator, just watch Argo sync
      this.addLog("PR already merged — waiting for Argo CD sync");

      // Trigger factory-specific Argo sync
      void this.argoSync.triggerFactorySync(factory).then((triggered) => {
        if (triggered) {
          this.addLog("Argo CD factory sync triggered");
        } else {
          this.addLog("Argo sync trigger failed — will poll for natural sync");
        }
      });

      this.pollFactoryArgoUntilSynced(factory, () => {
        if (f) {
          f.policyVersion = version;
          f.argoSyncStatus = "synced";
        }
        this.phase = "promoted";
        this.addLog("Argo CD sync complete — promotion finished");
        this.log?.info({ factory, version }, "argoSync: promotion complete (HIL path)");
      });
    } else {
      this.addLog("Argo CD not configured — simulating sync");
      this.scheduleSettle(factory, "synced", () => {
        f.policyVersion = version;
        this.phase = "promoted";
        this.addLog("Simulated sync complete");
      });
    }
  }

  advanceLineage(phase: string): void {
    if (phase === "training-running") {
      this.phase = "training-running";
      this.lineageStatuses = {
        dataset: "completed",
        pipeline: "running",
        training: "running",
        validation: "pending",
        model: "pending",
      };
    } else if (phase === "training-complete") {
      this.phase = "training-complete";
      this.lineageStatuses = {
        dataset: "completed",
        pipeline: "completed",
        training: "completed",
        validation: "completed",
        model: "completed",
      };
    }
  }

  recordAnomaly(robotId: string, score: number): void {
    this.anomalyHistory.push({ t: Date.now(), v: score });
    if (this.anomalyHistory.length > ANOMALY_RING_SIZE) {
      this.anomalyHistory.shift();
    }
    if (score >= 0.85) {
      this.triggerRollback(robotId);
    }
  }

  recordRollbackAnalysis(analysis: RollbackAnalysis): void {
    this.rollbackAnalyses.push(analysis);
    // Keep only last 5 analyses
    if (this.rollbackAnalyses.length > 5) {
      this.rollbackAnalyses.shift();
    }
    this.addLog(`🔍 Agent analysis complete: ${analysis.factory} rollback`);
  }

  reset(): void {
    for (const timer of this.timers) clearTimeout(timer);
    this.timers = [];
    this.phase = "idle";
    this.promotedVersion = BASELINE_VERSION;
    for (const key of Object.keys(this.factories)) {
      this.factories[key] = {
        policyVersion: BASELINE_VERSION,
        argoSyncStatus: "synced",
      };
    }
    this.lineageStatuses = {
      dataset: "completed",
      pipeline: "completed",
      training: "completed",
      validation: "completed",
      model: "completed",
    };
    this.anomalyHistory = [];
    this.statusLog = [];
    this.rollbackAnalyses = [];

    if (this.argoSync?.enabled) {
      void this.realArgoReset();
    }
  }

  private triggerRollback(robotId: string): void {
    this.phase = "anomaly-detected";
    const factory = robotId === "fl-08" ? "factory-b" : "factory-a";
    const f = this.factories[factory];
    if (!f) return;
    this.addLog(`Anomaly detected on ${robotId} — initiating rollback`);

    setTimeout(() => {
      this.phase = "rolling-back";
      f.argoSyncStatus = "reverting";
      this.addLog(`Rolling back ${factory} to ${BASELINE_VERSION}`);

      if (this.argoSync?.enabled) {
        void this.realArgoRollback(factory, robotId);
      } else {
        this.scheduleSettle(factory, "synced", () => {
          f.policyVersion = BASELINE_VERSION;
          this.phase = "rolled-back";
          void this.publishAnomalyScore(robotId, 0.08);
          this.addLog("Simulated rollback complete");
        });
      }
    }, 3000);
  }

  private async realArgoPromote(
    factory: string,
    version: string,
  ): Promise<void> {
    const f = this.factories[factory];

    this.addLog("Committing policy version change to Git…");
    const result = await this.argoSync!.commitPolicyVersion(version);
    if (!result.ok) {
      this.addLog("⚠ Git commit failed — check token permissions (needs Contents: Read and write)");
      this.addLog("Falling back to simulated sync");
      this.scheduleSettle(factory, "synced", () => {
        if (f) f.policyVersion = version;
        this.phase = "promoted";
      });
      return;
    }
    if (!result.commitUrl) {
      if (f) {
        f.policyVersion = version;
        f.argoSyncStatus = "synced";
      }
      this.phase = "promoted";
      this.addLog("Policy version already at target in Git — no sync needed");
      return;
    }
    this.addLog(`Committed → ${result.commitUrl}`);
    if (f) f.policyVersion = version;

    this.addLog("Triggering Argo CD sync…");
    const synced = await this.argoSync!.triggerSync();
    if (!synced) {
      this.addLog("Argo sync trigger failed — will poll for natural sync");
    } else {
      this.addLog("Argo CD sync triggered — waiting for completion");
    }

    this.pollArgoUntilSynced(factory, () => {
      if (f) f.argoSyncStatus = "synced";
      this.phase = "promoted";
      this.addLog("Argo CD sync complete — promotion finished");
      this.log?.info({ factory, version }, "argoSync: promotion complete");
    });
  }

  private async realArgoRollback(
    factory: string,
    robotId: string,
  ): Promise<void> {
    const f = this.factories[factory];

    this.addLog("Committing rollback to Git…");
    const result = await this.argoSync!.commitPolicyVersion(BASELINE_VERSION);
    if (!result.ok) {
      this.addLog("⚠ Git commit failed — simulating rollback");
      this.scheduleSettle(factory, "synced", () => {
        if (f) {
          f.policyVersion = BASELINE_VERSION;
          f.argoSyncStatus = "synced";
        }
        this.phase = "rolled-back";
        void this.publishAnomalyScore(robotId, 0.08);
      });
      return;
    }
    if (!result.commitUrl) {
      if (f) {
        f.policyVersion = BASELINE_VERSION;
        f.argoSyncStatus = "synced";
      }
      this.phase = "rolled-back";
      void this.publishAnomalyScore(robotId, 0.08);
      this.addLog("Policy already at baseline in Git — rollback complete");
      return;
    }
    this.addLog(`Rollback committed → ${result.commitUrl}`);
    if (f) f.policyVersion = BASELINE_VERSION;

    this.addLog("Triggering Argo CD sync for rollback…");
    const synced = await this.argoSync!.triggerSync();
    if (!synced) {
      this.addLog("Argo sync trigger failed — will poll for natural sync");
    } else {
      this.addLog("Argo CD sync triggered — waiting for rollback");
    }

    this.pollArgoUntilSynced(factory, () => {
      if (f) f.argoSyncStatus = "synced";
      this.phase = "rolled-back";
      void this.publishAnomalyScore(robotId, 0.08);
      this.addLog("Rollback sync complete");
      this.log?.info({ factory }, "argoSync: rollback complete");
    });
  }

  private async realArgoReset(): Promise<void> {
    const result = await this.argoSync!.commitPolicyVersion(BASELINE_VERSION);
    if (result.ok) {
      await this.argoSync!.triggerSync();
    }
  }

  private pollArgoUntilSynced(factory: string, onDone: () => void): void {
    let attempts = 0;
    const maxAttempts = 40;
    let sawRunning = false;

    const poll = (): void => {
      attempts++;
      void this.argoSync!
        .getArgoSyncStatus()
        .then(({ syncStatus, healthStatus, operationPhase }) => {
          const f = this.factories[factory];
          if (attempts % 3 === 1) {
            this.addLog(
              `Argo: sync=${syncStatus} health=${healthStatus} op=${operationPhase}`,
            );
          }

          if (operationPhase === "Running") sawRunning = true;

          if (syncStatus === "Synced" && healthStatus === "Healthy") {
            onDone();
            return;
          }

          // Our triggered sync ran and completed
          if (
            sawRunning &&
            (operationPhase === "Succeeded" || operationPhase === "Failed")
          ) {
            onDone();
            return;
          }

          // After 5 polls (~15s) without seeing Running, sync was a no-op
          if (
            attempts >= 5 &&
            !sawRunning &&
            operationPhase === "Succeeded"
          ) {
            this.addLog("Argo sync settled (no new operation detected)");
            if (f) f.argoSyncStatus = "synced";
            onDone();
            return;
          }

          if (attempts >= maxAttempts) {
            this.log?.warn(
              { factory, syncStatus, healthStatus },
              "argoSync: poll timeout",
            );
            this.addLog("Argo poll timed out — marking complete");
            if (f) f.argoSyncStatus = "synced";
            onDone();
            return;
          }
          const timer = setTimeout(poll, ARGO_POLL_MS);
          this.timers.push(timer);
        });
    };
    const timer = setTimeout(poll, 2000);
    this.timers.push(timer);
  }

  private pollFactoryArgoUntilSynced(factory: string, onDone: () => void): void {
    let attempts = 0;
    let sawRunning = false;

    const poll = (): void => {
      attempts++;
      void this.argoSync!
        .getFactoryArgoSyncStatus(factory)
        .then(({ syncStatus, healthStatus, operationPhase }) => {
          const f = this.factories[factory];
          if (attempts % 3 === 1) {
            this.addLog(
              `Argo (${factory}): sync=${syncStatus} health=${healthStatus} op=${operationPhase}`,
            );
          }

          if (operationPhase === "Running") sawRunning = true;

          if (syncStatus === "Synced" && healthStatus === "Healthy") {
            if (f) f.argoSyncStatus = "synced";
            onDone();
            return;
          }

          // Our triggered sync ran and completed
          if (
            sawRunning &&
            (operationPhase === "Succeeded" || operationPhase === "Failed")
          ) {
            if (f) f.argoSyncStatus = "synced";
            onDone();
            return;
          }

          // After 5 polls (~15s) without seeing Running, sync was a no-op
          if (
            attempts >= 5 &&
            !sawRunning &&
            operationPhase === "Succeeded"
          ) {
            this.addLog("Argo sync settled (no new operation detected)");
            if (f) f.argoSyncStatus = "synced";
            onDone();
            return;
          }

          if (attempts >= ARGO_MAX_POLLS) {
            this.log?.warn(
              { factory, syncStatus, healthStatus },
              "argoSync: factory poll timeout",
            );
            this.addLog("Argo poll timed out — marking complete");
            if (f) f.argoSyncStatus = "synced";
            onDone();
            return;
          }
          const timer = setTimeout(poll, ARGO_POLL_MS);
          this.timers.push(timer);
        });
    };
    const timer = setTimeout(poll, 2000);
    this.timers.push(timer);
  }

  private scheduleSettle(
    factory: string,
    targetStatus: ArgoSyncStatus,
    onSettle?: () => void,
  ): void {
    const timer = setTimeout(() => {
      const f = this.factories[factory];
      if (f) f.argoSyncStatus = targetStatus;
      onSettle?.();
    }, ARGO_FALLBACK_MS);
    this.timers.push(timer);
  }
}
