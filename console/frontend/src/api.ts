// This project was developed with assistance from AI tools.
import type { ArgoAppStatus, FleetMessage, FleetStatus, GovernanceStatus, LineageGraph, PipelineRun, ScenarioDetail, Topology } from "./types.js";

export async function fetchTopology(): Promise<Topology> {
  const resp = await fetch("/api/topology");
  if (!resp.ok) throw new Error(`topology fetch failed: ${resp.status}`);
  return (await resp.json()) as Topology;
}

export async function fetchScenarios(): Promise<{ scenarios: string[] }> {
  const resp = await fetch("/api/scenarios");
  if (!resp.ok) throw new Error(`scenarios fetch failed: ${resp.status}`);
  return (await resp.json()) as { scenarios: string[] };
}

export async function fetchScenarioDetail(name: string): Promise<ScenarioDetail> {
  const resp = await fetch(`/api/scenarios/${encodeURIComponent(name)}`);
  if (!resp.ok) throw new Error(`scenario detail fetch failed: ${resp.status}`);
  return (await resp.json()) as ScenarioDetail;
}

export async function executeAction(
  action: string,
  params?: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const resp = await fetch(`/api/action/${encodeURIComponent(action)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params ?? {}),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`action failed: ${resp.status} ${text}`);
  }
  return (await resp.json()) as Record<string, unknown>;
}

export async function fetchFleetStatus(): Promise<FleetStatus> {
  const resp = await fetch("/api/fleet");
  if (!resp.ok) throw new Error(`fleet status fetch failed: ${resp.status}`);
  return (await resp.json()) as FleetStatus;
}

export async function fetchLineage(): Promise<LineageGraph> {
  const resp = await fetch("/api/lineage");
  if (!resp.ok) throw new Error(`lineage fetch failed: ${resp.status}`);
  return (await resp.json()) as LineageGraph;
}

export async function fetchPipelineRuns(): Promise<PipelineRun[]> {
  const resp = await fetch("/api/pipeline-runs");
  if (!resp.ok) return [];
  const data = (await resp.json()) as { runs: PipelineRun[] };
  return data.runs ?? [];
}

export async function fetchArgoStatus(): Promise<ArgoAppStatus> {
  const resp = await fetch("/api/argo-status");
  if (!resp.ok) throw new Error(`argo status fetch failed: ${resp.status}`);
  return (await resp.json()) as ArgoAppStatus;
}

export async function fetchGovernance(): Promise<GovernanceStatus> {
  const resp = await fetch("/api/governance");
  if (!resp.ok) throw new Error(`governance fetch failed: ${resp.status}`);
  return (await resp.json()) as GovernanceStatus;
}

export function subscribeEvents(onMessage: (m: FleetMessage) => void): () => void {
  const es = new EventSource("/api/events");
  es.addEventListener("message", (evt) => {
    try {
      const parsed = JSON.parse(evt.data) as FleetMessage;
      onMessage(parsed);
    } catch {
      // ignore malformed payloads
    }
  });
  return () => es.close();
}

export async function queryAgent(query: string): Promise<{
  query: string;
  response: string;
  timestamp: string;
}> {
  const resp = await fetch("/api/agent/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query }),
  });
  if (!resp.ok) {
    const errorData = await resp.json().catch(() => ({ error: resp.statusText })) as { error?: string };
    throw new Error(errorData.error ?? `Agent query failed: ${resp.statusText}`);
  }
  return (await resp.json()) as { query: string; response: string; timestamp: string };
}

export async function getAgentHealth(): Promise<{ status: string }> {
  const resp = await fetch("/api/agent/health");
  if (!resp.ok) {
    return { status: "unavailable" };
  }
  return (await resp.json()) as { status: string };
}

// HIL Approval API functions
export interface BlastRadius {
  factory: string;
  namespace: string;
  robot_count: number;
  current_version: string;
  target_version: string;
  impact_level: "low" | "medium" | "high";
}

export interface ModerationCheck {
  decision: "allowed" | "blocked" | "error";
  flagged: boolean;
  categories: string[];
  latency_ms: number;
}

export interface ModerationResults {
  input: ModerationCheck;
  output: ModerationCheck;
}

export interface ToolCallTraceEntry {
  tool_name: string;
  arguments: Record<string, unknown>;
  timestamp: string;
  duration_ms: number;
  response_summary: string;
  success: boolean;
}

export interface MergeError {
  error: string;
  error_type: "conflict" | "not_mergeable" | "checks_failed" | "unknown";
  status_code?: number;
  pr_number?: number;
  timestamp: string;
}

export interface PendingApproval {
  id: number;
  session_id: string;
  user_identity: string;
  tool_name: string;
  tool_arguments: Record<string, unknown>;
  approval_status: string;  // "pending" | "approved" | "rejected" | "merge_failed"
  timestamp: string;
  git_diff?: string;  // Git diff preview for promote_policy_version
  summary?: string;   // Human-readable summary for promote_policy_version
  blast_radius?: BlastRadius;  // Impact analysis for promote_policy_version (Milestone 4)
  moderation_results?: ModerationResults;  // Input/output safety checks (Milestone 4)
  tool_call_trace?: ToolCallTraceEntry[];  // Read-only tool calls before approval (Milestone 4)
  reasoning_summary?: string;  // Agent's explanation of WHY (Milestone 4)
  pr_url?: string;    // PR URL if already created (for approved requests)
  merge_error?: MergeError;  // PR merge failure details (Task #33)
}

export interface ApprovalResult {
  status: string;
  id: number;
  result?: string;
  reason?: string;
  timestamp: string;
}

export async function getPendingApprovals(): Promise<PendingApproval[]> {
  const resp = await fetch("/api/approval/pending");
  if (!resp.ok) {
    throw new Error(`Failed to fetch pending approvals: ${resp.status}`);
  }
  const data = (await resp.json()) as { pending: PendingApproval[] };
  return data.pending;
}

export async function approveRequest(id: number): Promise<ApprovalResult> {
  const resp = await fetch(`/api/approval/${id}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!resp.ok) {
    const errorData = await resp.json().catch(() => ({ error: resp.statusText })) as { error?: string };
    throw new Error(errorData.error ?? `Approval failed: ${resp.statusText}`);
  }
  return (await resp.json()) as ApprovalResult;
}

export async function rejectRequest(id: number, reason: string): Promise<ApprovalResult> {
  const resp = await fetch(`/api/approval/${id}/reject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason }),
  });
  if (!resp.ok) {
    const errorData = await resp.json().catch(() => ({ error: resp.statusText })) as { error?: string };
    throw new Error(errorData.error ?? `Rejection failed: ${resp.statusText}`);
  }
  return (await resp.json()) as ApprovalResult;
}
