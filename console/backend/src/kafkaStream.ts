// This project was developed with assistance from AI tools.
import { Kafka, type Consumer, type EachMessagePayload } from "kafkajs";
import { EventEmitter } from "node:events";
import { DemoState } from "./demoState.js";

export interface SimpleLogger {
  info(obj: unknown, msg?: string): void;
  warn(obj: unknown, msg?: string): void;
  error(obj: unknown, msg?: string): void;
}

export interface FleetMessage {
  receivedAt: string;
  topic: string;
  partition: number;
  offset: string;
  key: string | null;
  payload: unknown;
}

interface RobotTelemetrySnapshot {
  robotStatus: "active" | "idle" | "rerouting";
  anomalyScore: number;
  policyVersion: string;
  lastHeartbeat: string;
}

export class FleetStream extends EventEmitter {
  private readonly kafka: Kafka;
  private consumer: Consumer | undefined;
  private diagMsgCount = 0;
  private diagLastReportTs = Date.now();
  private readonly DIAG_INTERVAL_MS = 30_000;
  private latestCameraFrame: Buffer | null = null;
  private robotTelemetry: Record<string, RobotTelemetrySnapshot> = {};
  readonly demoState = new DemoState();

  constructor(
    bootstrapServers: string,
    private readonly topics: string[],
    private readonly groupId: string,
    private readonly clientId: string,
    private readonly log: SimpleLogger,
  ) {
    super();
    this.kafka = new Kafka({
      clientId: this.clientId,
      brokers: bootstrapServers.split(","),
    });
  }

  async start(): Promise<void> {
    this.consumer = this.kafka.consumer({
      groupId: `${this.groupId}-${Date.now()}`,
      sessionTimeout: 45_000,
      heartbeatInterval: 5_000,
      allowAutoTopicCreation: false,
      // Lower than the kafkajs default (5s) so the UI feels responsive.
      // At 200ms each poll returns quickly; with nothing pending, the
      // consumer is in a tight loop but it's trivial work on a backend
      // that's already idle most of the time.
      maxWaitTimeInMs: 200,
    });

    this.consumer.on(this.consumer.events.CRASH, (event) => {
      this.log.error({ err: event.payload.error?.message, groupId: event.payload.groupId }, "fleet-stream.crash");
    });
    this.consumer.on(this.consumer.events.DISCONNECT, () => {
      this.log.warn({}, "fleet-stream.disconnect");
    });
    this.consumer.on(this.consumer.events.GROUP_JOIN, (event) => {
      this.log.info({ groupId: event.payload.groupId }, "fleet-stream.group-join");
    });

    await this.consumer.connect();
    for (const topic of this.topics) {
      // fromBeginning:false — only tail new messages. Historical messages in
      // these topics may be zstd-compressed from earlier producer versions;
      // kafkajs 2.x doesn't decode zstd natively. New messages use gzip.
      await this.consumer.subscribe({ topic, fromBeginning: false });
    }
    this.log.info({ topics: this.topics }, "fleet-stream subscribed");

    await this.consumer.run({
      autoCommit: true,
      eachMessage: async (payload: EachMessagePayload) => {
        try {
          const msg = this.decode(payload);
          this.diagMsgCount++;
          const now = Date.now();
          if (now - this.diagLastReportTs >= this.DIAG_INTERVAL_MS) {
            const elapsed = (now - this.diagLastReportTs) / 1000;
            this.log.info(
              {
                totalMessages: this.diagMsgCount,
                rate: (this.diagMsgCount / elapsed).toFixed(1),
                sseListeners: this.listenerCount("message"),
              },
              "fleet-stream.diag",
            );
            this.diagLastReportTs = now;
          }
          if ((msg.topic === "fleet.telemetry" || msg.topic === "factory-b.telemetry") && msg.payload && typeof msg.payload === "object") {
            const p = msg.payload as Record<string, unknown>;
            const robotId = typeof p["robot_id"] === "string" ? (p["robot_id"] as string) : null;
            if (robotId) {
              this.robotTelemetry[robotId] = {
                robotStatus: typeof p["mission_id"] === "string" ? "active" : "idle",
                anomalyScore: typeof p["anomaly_score"] === "number" ? (p["anomaly_score"] as number) : 0,
                policyVersion: typeof p["policy_version"] === "string" ? (p["policy_version"] as string) : "vla-warehouse-v1.3",
                lastHeartbeat: new Date().toISOString(),
              };
              if (typeof p["anomaly_score"] === "number") {
                this.demoState.recordAnomaly(robotId, p["anomaly_score"] as number);
              }
            }
          }
          if (msg.topic === "fleet.events" && msg.payload && typeof msg.payload === "object") {
            const p = msg.payload as Record<string, unknown>;
            const eventType = p["type"] as string | undefined;
            const ec = p["event_class"] as string | undefined;
            const payload = (p["payload"] ?? {}) as Record<string, unknown>;

            // Handle new-style events (type field)
            if (eventType === "rollback.analysis") {
              this.demoState.recordRollbackAnalysis({
                timestamp: (p["timestamp"] as string) ?? new Date().toISOString(),
                factory: (p["factory"] as string) ?? "unknown",
                from_version: (p["from_version"] as string) ?? "unknown",
                to_version: (p["to_version"] as string) ?? "unknown",
                trigger: (p["trigger"] as string) ?? "unknown",
                agent_analysis: (p["agent_analysis"] as string) ?? "",
                session_id: (p["session_id"] as string) ?? "",
              });
            }
            // Handle legacy event_class events
            else if (ec === "policy.promoted") {
              // skipGitCommit=true because PR was already merged by orchestrator
              this.demoState.promotePolicy(
                (payload["factory"] as string) ?? "factory-a",
                (payload["version"] as string) ?? "vla-warehouse-v1.4",
                true, // skipGitCommit - PR already merged by orchestrator
              );
            } else if (ec === "lineage.advance") {
              this.demoState.advanceLineage((payload["phase"] as string) ?? "training-running");
            } else if (ec === "demo.reset") {
              this.demoState.reset();
            }
          }
          if (msg.topic.startsWith("warehouse.cameras.") && msg.payload && typeof msg.payload === "object") {
            const p = msg.payload as Record<string, unknown>;
            if (typeof p["frame_b64"] === "string") {
              this.latestCameraFrame = Buffer.from(p["frame_b64"] as string, "base64");
              delete p["frame_b64"];
            }
          }
          this.emit("message", msg);
        } catch (err) {
          this.log.error({ err: (err as Error).message, topic: payload.topic }, "fleet-stream.each-error");
        }
      },
    });
  }

  private decode(payload: EachMessagePayload): FleetMessage {
    let parsed: unknown = null;
    const raw = payload.message.value?.toString("utf-8") ?? "";
    if (raw) {
      try {
        parsed = JSON.parse(raw);
      } catch {
        parsed = raw;
      }
    }
    return {
      receivedAt: new Date().toISOString(),
      topic: payload.topic,
      partition: payload.partition,
      offset: payload.message.offset,
      key: payload.message.key?.toString("utf-8") ?? null,
      payload: parsed,
    };
  }

  getCameraFrame(): Buffer | null {
    return this.latestCameraFrame;
  }

  getLatestTelemetry(): Record<string, RobotTelemetrySnapshot> {
    return { ...this.robotTelemetry };
  }

  async stop(): Promise<void> {
    if (this.consumer) {
      try {
        await this.consumer.disconnect();
      } catch (err) {
        this.log.warn({ err }, "fleet-stream disconnect failed");
      }
    }
  }
}
