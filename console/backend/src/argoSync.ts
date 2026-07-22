// This project was developed with assistance from AI tools.
import { readFileSync } from "node:fs";
import type { SimpleLogger } from "./kafkaStream.js";

const FLEET_MANAGER_DEPLOY_PATH =
  "infrastructure/gitops/apps/workloads/fleet-manager/deployment.yaml";
const ARGO_APP_NAME = "workloads-fleet-manager";
const ARGO_NAMESPACE = "openshift-gitops";

// Map factory names to Argo application names
const FACTORY_ARGO_APP_MAP: Record<string, string> = {
  "factory-a": "workloads-robot-edge", // Factory A uses robot-edge namespace
  "factory-b": "workloads-factory-b",
  "robot-edge": "workloads-robot-edge", // Alias
  "Factory A": "workloads-robot-edge",
  "Factory B": "workloads-factory-b",
};

export interface ArgoResourceStatus {
  kind: string;
  name: string;
  syncStatus: string;
  healthStatus: string;
  message?: string;
}

export interface ArgoAppStatus {
  syncStatus: string;
  healthStatus: string;
  operationPhase: string;
  operationMessage: string;
  operationStartedAt: string;
  operationFinishedAt: string;
  resources: ArgoResourceStatus[];
  syncRevision: string;
}

interface ArgoApplicationCR {
  status?: {
    sync?: { status?: string; revision?: string };
    health?: { status?: string };
    operationState?: {
      phase?: string;
      message?: string;
      startedAt?: string;
      finishedAt?: string;
      syncResult?: {
        resources?: Array<{
          kind?: string;
          name?: string;
          status?: string;
          message?: string;
        }>;
      };
    };
    resources?: Array<{
      kind?: string;
      name?: string;
      status?: string;
      health?: { status?: string };
    }>;
  };
}

interface GitHubFileResponse {
  sha: string;
  content: string;
}

interface GitHubCommitResponse {
  commit: { html_url: string };
}

export class ArgoSync {
  private readonly k8sApiBase: string;
  private readonly k8sToken: string;

  constructor(
    private readonly githubToken: string,
    private readonly githubRepo: string,
    private readonly log: SimpleLogger,
  ) {
    this.k8sApiBase = "https://kubernetes.default.svc";
    try {
      this.k8sToken = readFileSync(
        "/var/run/secrets/kubernetes.io/serviceaccount/token",
        "utf-8",
      );
    } catch {
      this.k8sToken = "";
      this.log.warn({}, "argoSync: no SA token — k8s API calls will fail");
    }
  }

  get enabled(): boolean {
    return this.githubToken.length > 0;
  }

  async commitPolicyVersion(
    version: string,
  ): Promise<{ ok: boolean; commitUrl?: string }> {
    if (!this.enabled) return { ok: false };

    try {
      const file = await this.getFileFromGitHub(FLEET_MANAGER_DEPLOY_PATH);
      const content = Buffer.from(file.content, "base64").toString("utf-8");
      const updated = content.replace(
        /POLICY_VERSION\n(\s+)value:\s*\S+/,
        `POLICY_VERSION\n$1value: ${version}`,
      );

      if (updated === content) {
        this.log.info({ version }, "argoSync: POLICY_VERSION already set");
        return { ok: true };
      }

      const commitUrl = await this.putFileToGitHub(
        FLEET_MANAGER_DEPLOY_PATH,
        updated,
        file.sha,
        `chore: promote policy to ${version}`,
      );
      this.log.info({ version, commitUrl }, "argoSync: committed");
      return { ok: true, commitUrl };
    } catch (err) {
      this.log.error(
        { err: (err as Error).message },
        "argoSync: failed to commit policy version",
      );
      return { ok: false };
    }
  }

  async triggerSync(): Promise<boolean> {
    try {
      const body = JSON.stringify({
        operation: {
          initiatedBy: { username: "showcase-console" },
          sync: {
            syncOptions: ["CreateNamespace=true", "ServerSideApply=true"],
          },
        },
      });

      const resp = await fetch(
        `${this.k8sApiBase}/apis/argoproj.io/v1alpha1/namespaces/${ARGO_NAMESPACE}/applications/${ARGO_APP_NAME}`,
        {
          method: "PATCH",
          headers: {
            Authorization: `Bearer ${this.k8sToken}`,
            "Content-Type": "application/merge-patch+json",
          },
          body,
        },
      );

      if (!resp.ok) {
        const text = await resp.text();
        this.log.warn(
          { status: resp.status, body: text.slice(0, 200) },
          "argoSync: sync trigger failed",
        );
        return false;
      }
      this.log.info({}, "argoSync: sync triggered");
      return true;
    } catch (err) {
      this.log.error(
        { err: (err as Error).message },
        "argoSync: sync trigger error",
      );
      return false;
    }
  }

  async getArgoSyncStatus(): Promise<{
    syncStatus: string;
    healthStatus: string;
    operationPhase: string;
  }> {
    const full = await this.getArgoAppStatus();
    return {
      syncStatus: full.syncStatus,
      healthStatus: full.healthStatus,
      operationPhase: full.operationPhase,
    };
  }

  async getArgoAppStatus(): Promise<ArgoAppStatus> {
    const empty: ArgoAppStatus = {
      syncStatus: "Unknown",
      healthStatus: "Unknown",
      operationPhase: "Unknown",
      operationMessage: "",
      operationStartedAt: "",
      operationFinishedAt: "",
      resources: [],
      syncRevision: "",
    };
    try {
      const resp = await fetch(
        `${this.k8sApiBase}/apis/argoproj.io/v1alpha1/namespaces/${ARGO_NAMESPACE}/applications/${ARGO_APP_NAME}`,
        { headers: { Authorization: `Bearer ${this.k8sToken}` } },
      );

      if (!resp.ok) {
        const text = await resp.text();
        this.log.warn(
          { status: resp.status, body: text.slice(0, 200) },
          "argoSync: k8s API error",
        );
        return empty;
      }

      const app = (await resp.json()) as ArgoApplicationCR;
      const resources: ArgoResourceStatus[] = (
        app.status?.resources ?? []
      ).map((r) => ({
        kind: r.kind ?? "",
        name: r.name ?? "",
        syncStatus: r.status ?? "Unknown",
        healthStatus: r.health?.status ?? "",
      }));

      const opResources = app.status?.operationState?.syncResult?.resources;
      if (opResources) {
        for (const or of opResources) {
          const match = resources.find(
            (r) => r.kind === or.kind && r.name === or.name,
          );
          if (match && or.message) {
            match.message = or.message;
          }
        }
      }

      return {
        syncStatus: app.status?.sync?.status ?? "Unknown",
        healthStatus: app.status?.health?.status ?? "Unknown",
        operationPhase:
          app.status?.operationState?.phase ?? "Unknown",
        operationMessage:
          app.status?.operationState?.message ?? "",
        operationStartedAt:
          app.status?.operationState?.startedAt ?? "",
        operationFinishedAt:
          app.status?.operationState?.finishedAt ?? "",
        resources,
        syncRevision:
          app.status?.sync?.revision ?? "",
      };
    } catch (err) {
      this.log.error(
        { err: (err as Error).message },
        "argoSync: failed to get app status",
      );
      return empty;
    }
  }

  async getFactoryArgoSyncStatus(factory: string): Promise<{
    syncStatus: string;
    healthStatus: string;
    operationPhase: string;
  }> {
    const argoAppName = FACTORY_ARGO_APP_MAP[factory];
    if (!argoAppName) {
      this.log.warn({ factory }, "argoSync: unknown factory, cannot determine Argo app");
      return {
        syncStatus: "Unknown",
        healthStatus: "Unknown",
        operationPhase: "Unknown",
      };
    }

    try {
      const resp = await fetch(
        `${this.k8sApiBase}/apis/argoproj.io/v1alpha1/namespaces/${ARGO_NAMESPACE}/applications/${argoAppName}`,
        { headers: { Authorization: `Bearer ${this.k8sToken}` } },
      );

      if (!resp.ok) {
        this.log.warn(
          { status: resp.status, factory, argoApp: argoAppName },
          "argoSync: failed to get factory app status",
        );
        return {
          syncStatus: "Unknown",
          healthStatus: "Unknown",
          operationPhase: "Unknown",
        };
      }

      const app: ArgoApplicationCR = await resp.json();
      return {
        syncStatus: app.status?.sync?.status ?? "Unknown",
        healthStatus: app.status?.health?.status ?? "Unknown",
        operationPhase: app.status?.operationState?.phase ?? "Unknown",
      };
    } catch (err) {
      this.log.error(
        { err: (err as Error).message, factory, argoApp: argoAppName },
        "argoSync: failed to get factory app status",
      );
      return {
        syncStatus: "Unknown",
        healthStatus: "Unknown",
        operationPhase: "Unknown",
      };
    }
  }

  async triggerFactorySync(factory: string): Promise<boolean> {
    const argoAppName = FACTORY_ARGO_APP_MAP[factory];
    if (!argoAppName) {
      this.log.warn({ factory }, "argoSync: unknown factory, cannot trigger sync");
      return false;
    }

    try {
      const body = JSON.stringify({
        operation: {
          initiatedBy: { username: "showcase-console" },
          sync: {
            syncOptions: ["CreateNamespace=true", "ServerSideApply=true"],
          },
        },
      });

      const resp = await fetch(
        `${this.k8sApiBase}/apis/argoproj.io/v1alpha1/namespaces/${ARGO_NAMESPACE}/applications/${argoAppName}`,
        {
          method: "PATCH",
          headers: {
            Authorization: `Bearer ${this.k8sToken}`,
            "Content-Type": "application/merge-patch+json",
          },
          body,
        },
      );

      if (!resp.ok) {
        const text = await resp.text();
        this.log.warn(
          { status: resp.status, body: text.slice(0, 200), factory, argoApp: argoAppName },
          "argoSync: factory sync trigger failed",
        );
        return false;
      }
      this.log.info({ factory, argoApp: argoAppName }, "argoSync: factory sync triggered");
      return true;
    } catch (err) {
      this.log.error(
        { err: (err as Error).message, factory, argoApp: argoAppName },
        "argoSync: factory sync trigger error",
      );
      return false;
    }
  }

  private async getFileFromGitHub(path: string): Promise<GitHubFileResponse> {
    const resp = await fetch(
      `https://api.github.com/repos/${this.githubRepo}/contents/${path}?ref=main`,
      {
        headers: {
          Authorization: `Bearer ${this.githubToken}`,
          Accept: "application/vnd.github.v3+json",
        },
      },
    );
    if (!resp.ok) {
      throw new Error(
        `GitHub GET ${path}: ${resp.status} ${await resp.text()}`,
      );
    }
    return (await resp.json()) as GitHubFileResponse;
  }

  private async putFileToGitHub(
    path: string,
    content: string,
    sha: string,
    message: string,
  ): Promise<string> {
    const resp = await fetch(
      `https://api.github.com/repos/${this.githubRepo}/contents/${path}`,
      {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${this.githubToken}`,
          Accept: "application/vnd.github.v3+json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message,
          content: Buffer.from(content).toString("base64"),
          sha,
          branch: "main",
        }),
      },
    );
    if (!resp.ok) {
      throw new Error(
        `GitHub PUT ${path}: ${resp.status} ${await resp.text()}`,
      );
    }
    const data = (await resp.json()) as GitHubCommitResponse;
    return data.commit?.html_url ?? "";
  }
}
