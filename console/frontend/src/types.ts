// This project was developed with assistance from AI tools.
export type AudienceMode = "novice" | "evaluator" | "expert";

export interface Topology {
  hub: { name: string; namespace: string; workloads: string[] };
  companion: { name: string; namespace: string; workloads: string[] };
  teasers: string[];
}

export interface FleetMessage {
  receivedAt: string;
  topic: string;
  partition: number;
  offset: string;
  key: string | null;
  payload: Record<string, unknown> | string | null;
}

export interface ButtonDef {
  label: string;
  action: string;
  params: Record<string, string>;
}

export interface ScenarioDetail {
  name: string;
  buttons: ButtonDef[];
}

export type ViewName = "stage" | "architecture" | "fleet" | "lineage";

export interface FactoryStatus {
  name: string;
  namespace: string;
  policyVersion: string;
  robotId: string;
  robotStatus: "active" | "idle" | "rerouting";
  anomalyScore: number;
  argoSyncStatus: "synced" | "syncing" | "reverting";
  lastHeartbeat: string;
  links?: {
    argoApp: string;
  };
}

export interface AnomalyPoint {
  t: number;
  v: number;
}

export interface DemoLinks {
  argoFleetManager: string;
  ocpFleetManager: string;
  rhoaiDashboard: string;
  argoConsole: string;
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

export interface FleetStatus {
  demoPhase: string;
  anomalyHistory: AnomalyPoint[];
  statusLog: StatusLogEntry[];
  rollbackAnalyses: RollbackAnalysis[];
  links: DemoLinks | null;
  factories: FactoryStatus[];
}

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

export interface LineageNode {
  id: string;
  type: "dataset" | "pipeline" | "training" | "validation" | "model" | "synthetic";
  label: string;
  status: "completed" | "running" | "failed" | "pending";
  metadata: Record<string, string>;
}

export interface LineageEdge {
  source: string;
  target: string;
}

export interface LineageLinks {
  mlflowExperiment: string;
  modelRegistry: string;
  pipelineRuns: string;
  rhoaiDashboard: string;
}

export interface LineageGraph {
  nodes: LineageNode[];
  edges: LineageEdge[];
  links: LineageLinks | null;
}

export interface PipelineRun {
  id: string;
  name: string;
  state: string;
  createdAt: string;
  finishedAt: string | null;
  error: string | null;
}

export interface ManagedClusterStatus {
  name: string;
  role: string;
  available: boolean;
  joined: boolean;
  lastHeartbeat: string;
}

export interface PolicyComplianceStatus {
  name: string;
  displayName: string;
  nistFamily: string;
  remediationAction: "enforce" | "inform";
  clusterCompliance: {
    cluster: string;
    compliant: boolean | null;
  }[];
}

export interface SecurityControl {
  name: string;
  scope: string;
  status: "active" | "degraded" | "static";
  detail: string;
}

export interface StigProfile {
  profile: string;
  cluster: string;
  schedule: string;
  lastScan: string | null;
  pass: number | null;
  fail: number | null;
  remediation: number | null;
}

export interface GovernanceStatus {
  managedClusters: ManagedClusterStatus[];
  policies: PolicyComplianceStatus[];
  securityControls: SecurityControl[];
  supplyChain: {
    baseImages: string[];
    signingMethod: string;
    verificationPolicy: string;
  };
  stigCompliance: StigProfile[];
  observability: {
    enabled: boolean;
    retentionRaw: string;
    collectorHealthy: boolean | null;
  };
}
