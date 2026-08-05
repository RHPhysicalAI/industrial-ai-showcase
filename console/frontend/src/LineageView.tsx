// This project was developed with assistance from AI tools.
import { useCallback, useEffect, useState } from "react";
import {
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Flex,
  FlexItem,
  Label,
  Split,
  SplitItem,
  Stack,
  StackItem,
} from "@patternfly/react-core";
import type { LineageGraph, LineageLinks, LineageNode, PipelineRun } from "./types.js";
import { fetchLineage, fetchPipelineRuns } from "./api.js";

const POLL_INTERVAL = 5000;

const SVG_W = 1000;
const SVG_H = 190;
const NODE_R = 36;
const NODE_CY = 72;

function nodeColor(type: LineageNode["type"]): string {
  const colors: Record<string, string> = {
    dataset: "#0066CC",
    pipeline: "#6A6E73",
    training: "#3E8635",
    validation: "#F0AB00",
    model: "#EE0000",
    synthetic: "#8A4FBF",
  };
  return colors[type] ?? "#6A6E73";
}

function statusLabelColor(status: LineageNode["status"]): "green" | "blue" | "orange" | "red" {
  if (status === "completed") return "green";
  if (status === "running") return "blue";
  if (status === "pending") return "orange";
  return "red";
}

function statusDotColor(status: LineageNode["status"]): string {
  if (status === "completed") return "#3E8635";
  if (status === "running") return "#0066CC";
  if (status === "pending") return "#F0AB00";
  return "#C9190B";
}

function runStateColor(state: string): "green" | "blue" | "red" | "orange" | "grey" {
  if (state === "SUCCEEDED") return "green";
  if (state === "RUNNING" || state === "PENDING") return "blue";
  if (state === "FAILED") return "red";
  if (state === "CANCELING" || state === "CANCELED") return "orange";
  return "grey";
}

function NodeIconPath({ type, cx, cy }: { type: string; cx: number; cy: number }) {
  const s = "white";
  const sw = 1.8;
  switch (type) {
    case "dataset":
      return (
        <g stroke={s} strokeWidth={sw} fill="none" strokeLinecap="round">
          <ellipse cx={cx} cy={cy - 7} rx={10} ry={4} />
          <path d={`M${cx - 10},${cy - 7} L${cx - 10},${cy + 5}`} />
          <path d={`M${cx + 10},${cy - 7} L${cx + 10},${cy + 5}`} />
          <ellipse cx={cx} cy={cy + 5} rx={10} ry={4} />
        </g>
      );
    case "pipeline":
      return (
        <g stroke={s} strokeWidth={sw} fill="none" strokeLinecap="round" strokeLinejoin="round">
          <polyline points={`${cx - 10},${cy - 6} ${cx - 4},${cy} ${cx - 10},${cy + 6}`} />
          <polyline points={`${cx - 3},${cy - 6} ${cx + 3},${cy} ${cx - 3},${cy + 6}`} />
          <polyline points={`${cx + 4},${cy - 6} ${cx + 10},${cy} ${cx + 4},${cy + 6}`} />
        </g>
      );
    case "training":
      return (
        <polygon
          points={`${cx + 2},${cy - 10} ${cx - 4},${cy} ${cx},${cy} ${cx - 2},${cy + 10} ${cx + 6},${cy} ${cx + 2},${cy}`}
          fill={s}
        />
      );
    case "validation":
      return (
        <polyline
          points={`${cx - 7},${cy} ${cx - 2},${cy + 6} ${cx + 8},${cy - 6}`}
          fill="none"
          stroke={s}
          strokeWidth={2.5}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      );
    case "model":
      return (
        <g stroke={s} strokeWidth={sw} fill="none" strokeLinejoin="round">
          <polygon points={`${cx},${cy - 10} ${cx + 10},${cy - 3} ${cx + 10},${cy + 5} ${cx},${cy + 12} ${cx - 10},${cy + 5} ${cx - 10},${cy - 3}`} />
          <line x1={cx - 10} y1={cy - 3} x2={cx} y2={cy + 4} />
          <line x1={cx + 10} y1={cy - 3} x2={cx} y2={cy + 4} />
          <line x1={cx} y1={cy + 4} x2={cx} y2={cy + 12} />
        </g>
      );
    default:
      return <circle cx={cx} cy={cy} r={6} fill={s} />;
  }
}

function PipelineGraph({
  nodes,
  selectedId,
  onSelect,
}: {
  nodes: LineageNode[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const pad = 80;
  const spacing = (SVG_W - 2 * pad) / Math.max(nodes.length - 1, 1);
  const positions = nodes.map((_, i) => ({ x: pad + i * spacing, y: NODE_CY }));

  return (
    <svg viewBox={`0 0 ${SVG_W} ${SVG_H}`} className="showcase-pipeline-svg">
      <defs>
        <marker id="arrow-completed" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
          <polygon points="0 0, 8 3, 0 6" fill="#8a8d90" />
        </marker>
        <marker id="arrow-active" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
          <polygon points="0 0, 8 3, 0 6" fill="#0066CC" />
        </marker>
        <marker id="arrow-pending" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
          <polygon points="0 0, 8 3, 0 6" fill="#d2d2d2" />
        </marker>
      </defs>

      {nodes.map((node, i) => {
        if (i === 0) return null;
        const prev = nodes[i - 1]!;
        const from = positions[i - 1]!;
        const to = positions[i]!;
        const isActive = prev.status === "completed" && node.status === "running";
        const isPending = node.status === "pending";
        const cls = isActive
          ? "showcase-connection-active"
          : isPending
            ? "showcase-connection-pending"
            : "showcase-connection-completed";
        const marker = isActive
          ? "url(#arrow-active)"
          : isPending
            ? "url(#arrow-pending)"
            : "url(#arrow-completed)";
        return (
          <line
            key={`conn-${i}`}
            x1={from.x + NODE_R + 6}
            y1={from.y}
            x2={to.x - NODE_R - 6}
            y2={to.y}
            className={cls}
            markerEnd={marker}
          />
        );
      })}

      {nodes.map((node, i) => {
        const pos = positions[i]!;
        const isSelected = selectedId === node.id;
        const isRunning = node.status === "running";
        const isPending = node.status === "pending";
        const color = nodeColor(node.type);
        return (
          <g
            key={node.id}
            className="showcase-pipeline-node"
            onClick={() => onSelect(node.id)}
            opacity={isPending ? 0.45 : 1}
          >
            {isSelected && (
              <circle
                cx={pos.x} cy={pos.y} r={NODE_R + 8}
                fill="none" stroke={color} strokeWidth="2" opacity="0.35" strokeDasharray="4 3"
              />
            )}
            {isRunning && (
              <>
                <circle
                  cx={pos.x} cy={pos.y} r={NODE_R + 5}
                  fill="none" stroke={color} strokeWidth="2" className="showcase-pulse-ring"
                />
                <g className="showcase-orbit-dot" style={{ transformOrigin: `${pos.x}px ${pos.y}px` }}>
                  <circle cx={pos.x} cy={pos.y - NODE_R - 8} r="3.5" fill={color} />
                </g>
              </>
            )}
            <circle
              cx={pos.x} cy={pos.y} r={NODE_R}
              fill={color} fillOpacity={0.15}
              stroke={color} strokeWidth={isSelected ? 3 : 2}
              className="showcase-node-circle"
            />
            <NodeIconPath type={node.type} cx={pos.x} cy={pos.y} />
            <text
              x={pos.x} y={pos.y + NODE_R + 20}
              textAnchor="middle" fill="#151515" fontSize="12.5" fontWeight="600"
            >
              {node.label}
            </text>
            <circle cx={pos.x - 20} cy={pos.y + NODE_R + 34} r="3.5" fill={statusDotColor(node.status)} />
            <text
              x={pos.x - 14} y={pos.y + NODE_R + 34}
              textAnchor="start" dominantBaseline="central" fill="#6A6E73" fontSize="10.5" fontWeight="500"
            >
              {node.status}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function ProofLink({ href, label }: { href: string; label: string }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="showcase-proof-link">
      {label} ↗
    </a>
  );
}

function MetricCard({
  label,
  value,
  highlight,
  mono,
}: {
  label: string;
  value: string | undefined;
  highlight?: boolean;
  mono?: boolean;
}) {
  const cls = [
    "showcase-metric-card",
    highlight ? "showcase-metric-card--highlight" : "",
    mono ? "showcase-metric-card--mono" : "",
  ].filter(Boolean).join(" ");
  return (
    <div className={cls}>
      <div className="showcase-metric-label">{label}</div>
      <div className="showcase-metric-value">{value ?? "—"}</div>
    </div>
  );
}

function LossSparkline({ finalLoss }: { finalLoss: string | undefined }) {
  const final = parseFloat(finalLoss ?? "0.05") || 0.05;
  const w = 300;
  const h = 56;
  const pad = 4;
  const startLoss = 0.8;
  const steps = 40;
  const points: string[] = [];
  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const loss = startLoss * Math.exp(t * Math.log(final / startLoss));
    const x = pad + t * (w - 2 * pad);
    const y = pad + (1 - (loss - final) / (startLoss - final)) * (h - 2 * pad);
    points.push(`${x.toFixed(1)},${y.toFixed(1)}`);
  }
  return (
    <div className="showcase-loss-chart">
      <div className="showcase-metric-label">Training Loss Curve</div>
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none">
        <defs>
          <linearGradient id="loss-grad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#3E8635" stopOpacity="0.25" />
            <stop offset="100%" stopColor="#3E8635" stopOpacity="0.03" />
          </linearGradient>
        </defs>
        <polygon
          points={`${pad},${h - pad} ${points.join(" ")} ${w - pad},${h - pad}`}
          fill="url(#loss-grad)"
        />
        <polyline points={points.join(" ")} fill="none" stroke="#3E8635" strokeWidth="2" />
        <circle
          cx={w - pad}
          cy={parseFloat(points[points.length - 1]?.split(",")[1] ?? "0")}
          r="3" fill="#3E8635"
        />
      </svg>
    </div>
  );
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return iso;
  }
}

function formatDuration(start: string, end: string | null): string {
  if (!end) return "in progress…";
  const ms = new Date(end).getTime() - new Date(start).getTime();
  if (ms < 0) return "—";
  const sec = Math.round(ms / 1000);
  if (sec < 60) return `${sec}s`;
  return `${Math.floor(sec / 60)}m ${sec % 60}s`;
}

function PipelineRunsPanel({ runs, links }: { runs: PipelineRun[]; links: LineageLinks | null }) {
  if (runs.length === 0) {
    return (
      <Card>
        <CardBody>
          <div style={{ color: "#6A6E73", fontSize: 13 }}>No pipeline runs found</div>
        </CardBody>
      </Card>
    );
  }
  return (
    <Card>
      <CardHeader>
        <Split hasGutter>
          <SplitItem isFilled>
            <CardTitle>Recent Pipeline Runs</CardTitle>
          </SplitItem>
          {links?.pipelineRuns && (
            <SplitItem>
              <ProofLink href={links.pipelineRuns} label="View All in OpenShift AI" />
            </SplitItem>
          )}
        </Split>
      </CardHeader>
      <CardBody className="showcase-card-body-flush">
        <div className="showcase-pipeline-runs-list">
          <div className="showcase-pipeline-runs-header">
            <span className="showcase-run-name">Run</span>
            <span className="showcase-run-status">Status</span>
            <span className="showcase-run-time">Started</span>
            <span className="showcase-run-duration">Duration</span>
          </div>
          {runs.map((run) => (
            <div key={run.id} className="showcase-pipeline-runs-row">
              <span className="showcase-run-name" title={run.name}>{run.name}</span>
              <span className="showcase-run-status">
                <Label color={runStateColor(run.state)} isCompact>{run.state}</Label>
              </span>
              <span className="showcase-run-time">{formatTime(run.createdAt)}</span>
              <span className="showcase-run-duration">{formatDuration(run.createdAt, run.finishedAt)}</span>
            </div>
          ))}
        </div>
      </CardBody>
    </Card>
  );
}

function DatasetDetail({ node }: { node: LineageNode }) {
  const m = node.metadata;
  return (
    <div className="showcase-detail-panel">
      <Card>
        <CardHeader>
          <CardTitle>
            {node.label}
            <Label color={statusLabelColor(node.status)} isCompact style={{ marginLeft: 12 }}>{node.status}</Label>
          </CardTitle>
        </CardHeader>
        <CardBody>
          <div style={{ fontSize: 14, lineHeight: 1.8 }}>
            <div><strong>Repository:</strong> {m.repo}</div>
            <div><strong>Episodes:</strong> {m.episodes}</div>
            <div><strong>Modality:</strong> {m.modality}</div>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}

function PipelineDetailPanel({
  node,
  runs,
  links,
}: {
  node: LineageNode;
  runs: PipelineRun[];
  links: LineageLinks | null;
}) {
  const m = node.metadata;
  return (
    <div className="showcase-detail-panel">
      <Stack hasGutter>
        <StackItem>
          <Card>
            <CardHeader>
              <CardTitle>
                {node.label}
                <Label color={statusLabelColor(node.status)} isCompact style={{ marginLeft: 12 }}>{node.status}</Label>
              </CardTitle>
            </CardHeader>
            <CardBody>
              <div style={{ fontSize: 14, lineHeight: 1.8 }}>
                <div><strong>Pipeline:</strong> {m.pipeline}</div>
                <div><strong>Namespace:</strong> {m.namespace}</div>
                <div><strong>Steps:</strong> {m.steps}</div>
                {m.duration && <div><strong>Duration:</strong> {m.duration}</div>}
                {m.started && <div><strong>Started:</strong> {formatTime(m.started)}</div>}
                {m.finished && <div><strong>Finished:</strong> {formatTime(m.finished)}</div>}
              </div>
            </CardBody>
          </Card>
        </StackItem>
        <StackItem>
          <PipelineRunsPanel runs={runs} links={links} />
        </StackItem>
      </Stack>
    </div>
  );
}

function TrainingDetail({ node, links }: { node: LineageNode; links: LineageLinks | null }) {
  const m = node.metadata;
  return (
    <div className="showcase-detail-panel">
      <Card>
        <CardHeader>
          <Split hasGutter>
            <SplitItem isFilled>
              <CardTitle>
                {node.label}
                <Label color={statusLabelColor(node.status)} isCompact style={{ marginLeft: 12 }}>{node.status}</Label>
              </CardTitle>
            </SplitItem>
            {links?.mlflowExperiment && (
              <SplitItem>
                <ProofLink href={links.mlflowExperiment} label="View in MLflow" />
              </SplitItem>
            )}
          </Split>
        </CardHeader>
        <CardBody>
          <Stack hasGutter>
            <StackItem>
              <div className="showcase-metric-grid">
                <MetricCard label="Base Model" value={m.base_model} />
                <MetricCard label="Embodiment" value={m.embodiment} />
                <MetricCard label="GPU" value={m.gpu} />
                <MetricCard label="Steps" value={m.max_steps} />
                <MetricCard label="Batch Size" value={m.batch_size} />
                <MetricCard label="Fine-Tune Duration" value={m.fine_tune_duration} />
                <MetricCard label="Pipeline Duration" value={m.pipeline_duration} />
                <MetricCard label="Pipeline Run" value={m.pipeline_run} />
                <MetricCard label="Pipeline State" value={m.pipeline_state} highlight />
              </div>
            </StackItem>
            <StackItem>
              <div className="showcase-loss-section">
                <MetricCard label="Final Loss" value={m.final_loss} highlight />
                <LossSparkline finalLoss={m.final_loss} />
              </div>
            </StackItem>
          </Stack>
        </CardBody>
      </Card>
    </div>
  );
}

function ValidationDetail({ node }: { node: LineageNode }) {
  const m = node.metadata;
  const passed = m.result === "PASSED";
  return (
    <div className="showcase-detail-panel">
      <Card>
        <CardHeader>
          <CardTitle>
            {node.label}
            <Label color={statusLabelColor(node.status)} isCompact style={{ marginLeft: 12 }}>{node.status}</Label>
          </CardTitle>
        </CardHeader>
        <CardBody>
          <div style={{ fontSize: 14, lineHeight: 1.8 }}>
            <div><strong>Checks:</strong> {m.checks}</div>
            <div>
              <strong>Result:</strong>{" "}
              <Label color={passed ? "green" : "red"} isCompact>{m.result}</Label>
            </div>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}

function ModelDetail({ node, links }: { node: LineageNode; links: LineageLinks | null }) {
  const m = node.metadata;
  return (
    <div className="showcase-detail-panel">
      <Card>
        <CardHeader>
          <Split hasGutter>
            <SplitItem isFilled>
              <CardTitle>
                {node.label}
                <Label color={statusLabelColor(node.status)} isCompact style={{ marginLeft: 12 }}>{node.status}</Label>
              </CardTitle>
            </SplitItem>
            {links?.modelRegistry && (
              <SplitItem>
                <ProofLink href={links.modelRegistry} label="View in Model Registry" />
              </SplitItem>
            )}
          </Split>
        </CardHeader>
        <CardBody>
          <Stack hasGutter>
            <StackItem>
              <div style={{ fontSize: 14, lineHeight: 1.8 }}>
                <div><strong>Format:</strong> {m.format}</div>
                <div><strong>Base Model:</strong> {m.base_model}</div>
                <div>
                  <strong>Artifact URI:</strong>{" "}
                  <span style={{ fontFamily: "monospace", fontSize: 13 }}>{m.uri}</span>
                </div>
              </div>
            </StackItem>
            <StackItem>
              <div style={{
                marginTop: 8,
                padding: "12px 16px",
                background: "var(--showcase--color--card-bg)",
                borderRadius: 8,
                borderLeft: "3px solid #0066CC",
                fontSize: 13,
                lineHeight: 1.6,
                color: "#151515",
              }}>
                This ONNX model is the final artifact of the training pipeline. Once registered,
                it becomes available for deployment to edge clusters via GitOps. The Fleet view
                tracks policy versions across factories — promoting this model triggers an Argo CD
                sync that rolls the new VLA policy to each site's robot fleet.
              </div>
            </StackItem>
          </Stack>
        </CardBody>
      </Card>
    </div>
  );
}

function NodeDetail({
  node,
  links,
  runs,
}: {
  node: LineageNode;
  links: LineageLinks | null;
  runs: PipelineRun[];
}) {
  if (node.id === "dataset") return <DatasetDetail node={node} />;
  if (node.id === "pipeline") return <PipelineDetailPanel node={node} runs={runs} links={links} />;
  if (node.id === "training") return <TrainingDetail node={node} links={links} />;
  if (node.id === "validation") return <ValidationDetail node={node} />;
  if (node.id === "model") return <ModelDetail node={node} links={links} />;
  return <DatasetDetail node={node} />;
}

export function LineageView() {
  const [graph, setGraph] = useState<LineageGraph | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [runs, setRuns] = useState<PipelineRun[]>([]);

  const refresh = useCallback(() => {
    fetchLineage().then(setGraph).catch(() => undefined);
    fetchPipelineRuns().then(setRuns).catch(() => undefined);
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, POLL_INTERVAL);
    return () => clearInterval(interval);
  }, [refresh]);

  const selectedNode = graph?.nodes.find((n) => n.id === selectedId) ?? null;

  return (
    <Stack hasGutter>
      <StackItem>
        <Split hasGutter>
          <SplitItem isFilled />
          {graph?.links && (
            <SplitItem>
              <Flex spaceItems={{ default: "spaceItemsSm" }}>
                {graph.links.rhoaiDashboard && (
                  <FlexItem>
                    <ProofLink href={graph.links.rhoaiDashboard} label="OpenShift AI Project" />
                  </FlexItem>
                )}
              </Flex>
            </SplitItem>
          )}
        </Split>
      </StackItem>

      <StackItem>
        <Card>
          <CardHeader>
            <CardTitle>Model Lineage — Dataset to Deployment</CardTitle>
          </CardHeader>
          <CardBody>
            {!graph ? (
              <div style={{ textAlign: "center", padding: 40, color: "#6A6E73" }}>
                Loading lineage...
              </div>
            ) : (
              <PipelineGraph
                nodes={graph.nodes}
                selectedId={selectedId}
                onSelect={(id) => setSelectedId(selectedId === id ? null : id)}
              />
            )}
          </CardBody>
        </Card>
      </StackItem>

      <StackItem>
        {selectedNode ? (
          <NodeDetail node={selectedNode} links={graph?.links ?? null} runs={runs} />
        ) : (
          <Card>
            <CardBody>
              <div className="showcase-lineage-prompt">
                Select a node above to view details, metrics, and proof links
              </div>
            </CardBody>
          </Card>
        )}
      </StackItem>
    </Stack>
  );
}
