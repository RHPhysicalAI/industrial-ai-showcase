// This project was developed with assistance from AI tools.
import Fastify from "fastify";
import fastifyCors from "@fastify/cors";

import { loadConfig } from "./config.js";
import { FleetStream, type FleetMessage } from "./kafkaStream.js";
import { registerStreamRoutes } from "./stream.js";
import { ArgoSync } from "./argoSync.js";
import { getGovernanceStatus } from "./governance.js";

const config = loadConfig();
const fastify = Fastify({
  logger: { level: config.logLevel, name: "showcase-console" },
});
const log = fastify.log;
await fastify.register(fastifyCors, { origin: true });

const argoSync = new ArgoSync(config.githubToken, config.githubRepo, log);
log.info({ argoEnabled: argoSync.enabled }, "argo sync initialized");

const stream = new FleetStream(
  config.kafkaBootstrapServers,
  config.kafkaTopics,
  config.kafkaConsumerGroup,
  config.kafkaClientId,
  log,
);
stream.demoState.argoSync = argoSync;
stream.demoState.wmsStubBaseUrl = config.wmsStubBaseUrl;
stream.demoState.log = log;

fastify.get("/healthz", async () => ({ status: "ok" }));
fastify.get("/readyz", async () => ({ status: "ready" }));

fastify.get("/api/topology", async () => ({
  hub: {
    name: "Hub — factory operations",
    namespace: "fleet-ops",
    workloads: ["fleet-manager", "wms-stub", "camera-adapter", "fleet (kafka)"],
  },
  companion: {
    name: "Companion — robot edge",
    namespace: "robot-edge",
    workloads: ["mission-dispatcher", "openvla-server (host-native)"],
  },
  teasers: ["Retrain & promote", "Multi-site rollout", "Agentic operator"],
}));

fastify.get("/api/scenarios", async () => {
  const resp = await fetch(`${config.wmsStubBaseUrl}/scenarios`);
  return resp.json();
});

fastify.get<{ Params: { name: string } }>(
  "/api/scenarios/:name",
  async (request, reply) => {
    const { name } = request.params;
    const resp = await fetch(
      `${config.wmsStubBaseUrl}/scenarios/${encodeURIComponent(name)}`,
    );
    const body = await resp.text();
    reply.code(resp.status).type("application/json").send(body);
  },
);

fastify.post<{ Params: { action: string }; Body: Record<string, unknown> }>(
  "/api/action/:action",
  async (request, reply) => {
    const { action } = request.params;
    const resp = await fetch(
      `${config.wmsStubBaseUrl}/${encodeURIComponent(action)}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request.body ?? {}),
      },
    );
    const body = await resp.text();
    reply.code(resp.status).type("application/json").send(body);
  },
);

fastify.get("/api/argo-status", async () => {
  return argoSync.getArgoAppStatus();
});

fastify.get("/api/governance", async () => {
  return getGovernanceStatus();
});

fastify.get("/api/fleet", async () => {
  const telemetry = stream.getLatestTelemetry();
  const ds = stream.demoState;
  const fb = ds.factories["factory-b"];
  const d = config.clusterAppsDomain;
  const links = d
    ? {
        argoFleetManager: `https://openshift-gitops-server-openshift-gitops.${d}/applications/openshift-gitops/workloads-fleet-manager`,
        ocpFleetManager: `https://console-openshift-console.${d}/k8s/ns/fleet-ops/apps~v1~Deployment/fleet-manager`,
        rhoaiDashboard: `https://rhods-dashboard-redhat-ods-applications.${d}`,
        argoConsole: `https://openshift-gitops-server-openshift-gitops.${d}/applications/openshift-gitops/workloads-console`,
      }
    : null;
  return {
    demoPhase: ds.phase,
    anomalyHistory: ds.anomalyHistory,
    statusLog: ds.statusLog,
    links,
    factories: [
      {
        name: "Factory A",
        namespace: "robot-edge",
        policyVersion: telemetry["fl-07"]?.policyVersion ?? "vla-warehouse-v1.3",
        robotId: "fl-07",
        robotStatus: telemetry["fl-07"]?.robotStatus ?? "idle",
        anomalyScore: telemetry["fl-07"]?.anomalyScore ?? 0.05,
        argoSyncStatus: "synced",
        lastHeartbeat: telemetry["fl-07"]?.lastHeartbeat ?? new Date().toISOString(),
      },
      {
        name: "Factory B",
        namespace: "factory-b",
        policyVersion: fb?.policyVersion ?? telemetry["fl-08"]?.policyVersion ?? "vla-warehouse-v1.3",
        robotId: "fl-08",
        robotStatus: telemetry["fl-08"]?.robotStatus ?? "idle",
        anomalyScore: telemetry["fl-08"]?.anomalyScore ?? 0.03,
        argoSyncStatus: fb?.argoSyncStatus ?? "synced",
        lastHeartbeat: telemetry["fl-08"]?.lastHeartbeat ?? new Date().toISOString(),
      },
    ],
  };
});

fastify.get("/api/lineage", async () => {
  const ls = stream.demoState.lineageStatuses;
  const d = config.clusterAppsDomain;
  const links = d
    ? {
        mlflowExperiment: `https://data-science-gateway.${d}/mlflow/redhat-ods-applications/mlflow/#/experiments`,
        modelRegistry: `https://rhods-dashboard-redhat-ods-applications.${d}/modelRegistry`,
        pipelineRuns: `https://rh-ai.${d}/develop-train/pipelines/runs/vla-training`,
        rhoaiDashboard: `https://rh-ai.${d}/projects/vla-training`,
      }
    : null;
  return {
    nodes: [
      {
        id: "dataset",
        type: "dataset",
        label: "G1 Teleop Dataset",
        status: ls["dataset"] ?? "completed",
        metadata: {
          repo: "nvidia/PhysicalAI-Robotics-GR00T-Teleop-G1",
          episodes: "311",
          modality: "video + joint positions (43 DOF)",
        },
      },
      {
        id: "pipeline",
        type: "pipeline",
        label: "KFP Pipeline Run",
        status: ls["pipeline"] ?? "completed",
        metadata: {
          pipeline: "vla-finetune",
          namespace: "vla-training",
          steps: "data_prep → fine_tune → validate → register",
        },
      },
      {
        id: "training",
        type: "training",
        label: "GR00T N1.7-3B Fine-Tune",
        status: ls["training"] ?? "completed",
        metadata: {
          base_model: "nvidia/GR00T-N1.7-3B",
          embodiment: "UNITREE_G1",
          max_steps: "2000",
          batch_size: "64",
          gpu: "NVIDIA L40S",
          final_loss: "0.051",
          duration: "29m 42s",
          throughput: "1.12 steps/sec",
        },
      },
      {
        id: "validation",
        type: "validation",
        label: "ONNX Validation",
        status: ls["validation"] ?? "completed",
        metadata: {
          checks: "structure, inference, finite outputs, determinism",
          result: "PASSED",
        },
      },
      {
        id: "model",
        type: "model",
        label: "g1-vla-finetune v1",
        status: ls["model"] ?? "completed",
        metadata: {
          registry: "RHOAI Model Registry",
          format: "ONNX",
          uri: "s3://vla-training/vla-finetune/onnx",
          base_model: "nvidia/GR00T-N1.7-3B",
          dataset: "nvidia/PhysicalAI-Robotics-GR00T-Teleop-G1",
          training_steps: "2000",
          embodiment: "UNITREE_G1",
        },
      },
    ],
    edges: [
      { source: "dataset", target: "pipeline" },
      { source: "pipeline", target: "training" },
      { source: "training", target: "validation" },
      { source: "validation", target: "model" },
    ],
    links,
  };
});

fastify.get("/api/pipeline-runs", async () => {
  const dspaUrl = "https://ds-pipeline-dspa.vla-training.svc:8443";
  try {
    const { readFile } = await import("node:fs/promises");
    const { Agent } = await import("node:https");
    const token = (await readFile("/var/run/secrets/kubernetes.io/serviceaccount/token", "utf-8")).trim();
    const agent = new Agent({ rejectUnauthorized: false });
    const url = `${dspaUrl}/apis/v2beta1/runs?page_size=10&sort_by=created_at%20desc`;
    const { default: https } = await import("node:https");
    const body = await new Promise<string>((resolve, reject) => {
      const req = https.get(url, { headers: { Authorization: `Bearer ${token}` }, agent }, (res) => {
        let data = "";
        res.on("data", (chunk: Buffer) => { data += chunk.toString(); });
        res.on("end", () => resolve(data));
      });
      req.on("error", reject);
      req.setTimeout(5000, () => { req.destroy(); reject(new Error("timeout")); });
    });
    const data = JSON.parse(body) as {
      runs?: Array<{
        run_id: string;
        display_name: string;
        state: string;
        created_at: string;
        finished_at: string;
        error?: { message?: string };
      }>;
    };
    return {
      runs: (data.runs ?? []).map((r) => ({
        id: r.run_id,
        name: r.display_name,
        state: r.state,
        createdAt: r.created_at,
        finishedAt: r.finished_at ?? null,
        error: r.error?.message ?? null,
      })),
    };
  } catch (err) {
    log.warn({ err }, "pipeline-runs fetch failed");
    return { runs: [] };
  }
});

registerStreamRoutes(fastify, config);

fastify.get("/api/camera/frame", async (_request, reply) => {
  const frame = stream.getCameraFrame();
  if (!frame) {
    reply.code(503).send({ error: "no camera frame available" });
    return reply;
  }
  reply
    .header("Content-Type", "image/jpeg")
    .header("Cache-Control", "no-cache, no-store")
    .send(frame);
  return reply;
});

fastify.get("/api/events", async (_request, reply) => {
  reply.raw.setHeader("Content-Type", "text/event-stream");
  reply.raw.setHeader("Cache-Control", "no-cache, no-transform");
  reply.raw.setHeader("Connection", "keep-alive");
  reply.raw.setHeader("X-Accel-Buffering", "no");
  reply.raw.flushHeaders();
  // Disable Nagle's algorithm so each SSE event chunk flushes to the TCP
  // socket immediately. Without this, Node buffers small writes (~40ms+)
  // before sending — enough that a whole scenario's events bunch into
  // one batch delivered on completion.
  reply.raw.socket?.setNoDelay(true);

  let sseMsgCount = 0;
  const sseConnectTs = Date.now();
  log.info({ sseListeners: stream.listenerCount("message") + 1 }, "sse.client.connected");

  const onMessage = (msg: FleetMessage): void => {
    sseMsgCount++;
    reply.raw.write(`event: message\ndata: ${JSON.stringify(msg)}\n\n`);
  };
  const onClose = (): void => {
    const durationSec = ((Date.now() - sseConnectTs) / 1000).toFixed(0);
    log.info({ sseMsgCount, durationSec, sseListeners: stream.listenerCount("message") - 1 }, "sse.client.disconnected");
    stream.off("message", onMessage);
  };

  stream.on("message", onMessage);
  reply.raw.on("close", onClose);

  reply.raw.write(`event: hello\ndata: ${JSON.stringify({ topics: config.kafkaTopics })}\n\n`);
  const heartbeat = setInterval(() => {
    reply.raw.write(`event: ping\ndata: ${Date.now()}\n\n`);
  }, 15_000);
  reply.raw.on("close", () => clearInterval(heartbeat));

  return reply;
});

// Agent assistant endpoints
fastify.post<{ Body: { query: string; sessionId?: string } }>(
  "/api/agent/query",
  async (request, reply) => {
    const { query, sessionId } = request.body;

    if (!query || typeof query !== "string") {
      reply.code(400).send({ error: "query is required" });
      return;
    }

    try {
      const resp = await fetch(
        `${config.agenticOrchestratorUrl}/query`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query, session_id: sessionId }),
        }
      );

      if (!resp.ok) {
        const errorText = await resp.text();
        log.warn({ status: resp.status, error: errorText }, "agent query failed");
        reply.code(resp.status).send({ error: "Agent query failed" });
        return;
      }

      const data = await resp.json() as { query: string; response: string };
      return {
        query: data.query,
        response: data.response,
        timestamp: new Date().toISOString(),
      };
    } catch (err) {
      log.error({ err }, "agent query error");
      reply.code(500).send({ error: "Agent service unavailable" });
    }
  }
);

fastify.get("/api/agent/health", async () => {
  try {
    const resp = await fetch(`${config.agenticOrchestratorUrl}/health`, {
      signal: AbortSignal.timeout(3000),
    });
    if (resp.ok) {
      const data = await resp.json() as { status: string };
      return { status: "ready", service: data.status };
    }
    return { status: "unavailable" };
  } catch {
    return { status: "unavailable" };
  }
});

fastify.get("/api/agent/suggestions", async () => {
  const suggestions: Array<{
    category: string;
    icon: string;
    text: string;
    priority?: number;
  }> = [];

  try {
    // Get current fleet state
    const telemetry = stream.getLatestTelemetry();
    const ds = stream.demoState;
    const fb = ds.factories["factory-b"];

    // Factory B suggestions (Factory A removed - doesn't exist in cluster)
    const factoryBVersion = fb?.policyVersion ?? telemetry["fl-08"]?.policyVersion ?? "v1.3";
    const nextVersionB = getNextVersion(factoryBVersion);
    if (nextVersionB) {
      suggestions.push({
        category: "upgrade",
        icon: "🆙",
        text: `Promote vla-warehouse ${nextVersionB} to Factory B`,
        priority: 1,
      });
    }

    // Robot telemetry (fl-08 is Factory B robot)
    suggestions.push({
      category: "telemetry",
      icon: "🤖",
      text: "Show me telemetry for robot fl-08",
      priority: 3,
    });

    // Anomaly check (Factory B)
    const factoryBAnomalyScore = telemetry["fl-08"]?.anomalyScore ?? 0.12;
    if (factoryBAnomalyScore > 0.5) {
      suggestions.push({
        category: "anomaly",
        icon: "⚠️",
        text: `Check anomaly for Factory B (score: ${factoryBAnomalyScore.toFixed(2)})`,
        priority: 0, // Highest priority
      });
    } else {
      suggestions.push({
        category: "anomaly",
        icon: "📈",
        text: "Show me anomaly history for Factory B",
        priority: 4,
      });
    }

    // Help
    suggestions.push({
      category: "help",
      icon: "❓",
      text: "What can you help me with?",
      priority: 5,
    });

    // Sort by priority
    suggestions.sort((a, b) => (a.priority ?? 999) - (b.priority ?? 999));

    return { suggestions: suggestions.slice(0, 5) }; // Return top 5
  } catch (err) {
    log.error({ err }, "failed to generate suggestions");
    // Return static fallbacks
    return {
      suggestions: [
        { category: "help", icon: "❓", text: "What can you help me with?" },
        { category: "fleet-status", icon: "📊", text: "Show me all factory statuses" },
        { category: "telemetry", icon: "🤖", text: "Show me telemetry for robot fl-07" },
      ],
    };
  }
});

// Helper function to get next version
function getNextVersion(current: string): string | null {
  const match = current.match(/v(\d+)\.(\d+)/);
  if (match && match[1] && match[2]) {
    const major = match[1];
    const minor = match[2];
    return `v${major}.${parseInt(minor, 10) + 1}`;
  }
  return null;
}

// HIL Approval endpoints
fastify.get("/api/approval/pending", async (request, reply) => {
  try {
    const resp = await fetch(`${config.auditServiceUrl}/audit/pending`, {
      signal: AbortSignal.timeout(5000),
    });

    if (!resp.ok) {
      const errorText = await resp.text();
      log.warn({ status: resp.status, error: errorText }, "failed to fetch pending approvals");
      reply.code(resp.status).send({ error: "Failed to fetch pending approvals" });
      return;
    }

    const data = await resp.json() as { pending: Array<unknown> };
    return data;
  } catch (err) {
    log.error({ err }, "approval pending query error");
    reply.code(500).send({ error: "Audit service unavailable" });
  }
});

fastify.get<{ Querystring: { limit?: string } }>(
  "/api/audit/history",
  async (request, reply) => {
    const limit = parseInt(request.query.limit ?? "10", 10);

    try {
      const resp = await fetch(
        `${config.auditServiceUrl}/audit/history?limit=${limit}`,
        { signal: AbortSignal.timeout(5000) }
      );

      if (!resp.ok) {
        const errorText = await resp.text();
        log.warn({ status: resp.status, error: errorText }, "failed to fetch audit history");
        reply.code(resp.status).send({ error: "Failed to fetch audit history" });
        return;
      }

      const data = await resp.json() as { history: Array<unknown> };
      return data;
    } catch (err) {
      log.error({ err }, "audit history query error");
      reply.code(500).send({ error: "Audit service unavailable" });
    }
  }
);

fastify.post<{ Params: { id: string } }>(
  "/api/approval/:id/approve",
  async (request, reply) => {
    const { id } = request.params;

    try {
      // Record approval in audit service
      const auditResp = await fetch(
        `${config.auditServiceUrl}/audit/approve/${id}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ approver_identity: "demo-operator" }),
          signal: AbortSignal.timeout(5000),
        }
      );

      if (!auditResp.ok) {
        const errorText = await auditResp.text();
        log.warn({ status: auditResp.status, error: errorText, id }, "failed to approve request");
        reply.code(auditResp.status).send({ error: "Failed to approve request" });
        return;
      }

      // Resume orchestrator execution
      const resumeResp = await fetch(
        `${config.agenticOrchestratorUrl}/approval/${id}/resume`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ decision: "approved" }),
          signal: AbortSignal.timeout(30000),
        }
      );

      if (!resumeResp.ok) {
        const errorText = await resumeResp.text();
        log.warn({ status: resumeResp.status, error: errorText, id }, "failed to resume after approval");
        reply.code(resumeResp.status).send({ error: "Failed to resume execution" });
        return;
      }

      const result = await resumeResp.json() as { response: string };
      return {
        status: "approved",
        id: parseInt(id, 10),
        result: result.response,
        timestamp: new Date().toISOString(),
      };
    } catch (err) {
      log.error({ err, id }, "approval error");
      reply.code(500).send({ error: "Approval service unavailable" });
    }
  }
);

fastify.post<{ Params: { id: string }; Body: { reason: string } }>(
  "/api/approval/:id/reject",
  async (request, reply) => {
    const { id } = request.params;
    const { reason } = request.body;

    if (!reason || typeof reason !== "string") {
      reply.code(400).send({ error: "reason is required" });
      return;
    }

    try {
      // Record rejection in audit service
      const auditResp = await fetch(
        `${config.auditServiceUrl}/audit/reject/${id}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            approver_identity: "demo-operator",
            reason,
          }),
          signal: AbortSignal.timeout(5000),
        }
      );

      if (!auditResp.ok) {
        const errorText = await auditResp.text();
        log.warn({ status: auditResp.status, error: errorText, id }, "failed to reject request");
        reply.code(auditResp.status).send({ error: "Failed to reject request" });
        return;
      }

      // Notify orchestrator of rejection
      const resumeResp = await fetch(
        `${config.agenticOrchestratorUrl}/approval/${id}/resume`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ decision: "rejected", reason }),
          signal: AbortSignal.timeout(5000),
        }
      );

      if (!resumeResp.ok) {
        const errorText = await resumeResp.text();
        log.warn({ status: resumeResp.status, error: errorText, id }, "failed to notify orchestrator of rejection");
        // Don't fail - rejection is already recorded in audit service
      }

      return {
        status: "rejected",
        id: parseInt(id, 10),
        reason,
        timestamp: new Date().toISOString(),
      };
    } catch (err) {
      log.error({ err, id }, "rejection error");
      reply.code(500).send({ error: "Approval service unavailable" });
    }
  }
);

await stream.start();

const shutdown = async (signal: string): Promise<void> => {
  log.info({ signal }, "shutting down");
  await stream.stop();
  await fastify.close();
  process.exit(0);
};
process.on("SIGINT", () => void shutdown("SIGINT"));
process.on("SIGTERM", () => void shutdown("SIGTERM"));

await fastify.listen({ host: "0.0.0.0", port: config.port });
log.info({ port: config.port }, "showcase-console listening");
