import { useMemo } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps
} from "@xyflow/react";
import dagre from "dagre";
import "@xyflow/react/dist/style.css";
import { formatDuration, type PipelineData, type PipelineNode } from "../lib/pipeline";

type StageStatus = "done" | "running" | "failed" | "pending";

type StageDef = {
  id: string;
  label: string;
  sub: string;
  seed?: boolean;
  match: (id: string) => boolean;
};

// Logical stages shown on the canvas. Each aggregates one group of backend
// batch nodes, mirroring docs/pipeline.md so the graph stays readable while the
// underlying DAG has ~48 nodes.
const STAGES: StageDef[] = [
  { id: "src", label: "Birth Data", sub: "structured_data", seed: true, match: () => false },
  { id: "p1", label: "Identity", sub: "P1", match: (id) => id === "p1" },
  { id: "yoga", label: "Yoga Pre-scan", sub: "P2 · pre", match: (id) => id === "p2_yoga" },
  { id: "p2", label: "Planet Audit", sub: "9 planets", match: (id) => id.startsWith("p2_") && id !== "p2_yoga" },
  { id: "d9", label: "D9 per-planet", sub: "Navamsha", match: (id) => id.startsWith("p3a_d9_") },
  { id: "div", label: "D10 / D4 / D5", sub: "divisional", match: (id) => id.startsWith("p3b_") },
  { id: "house", label: "House Diagnosis", sub: "12 houses", match: (id) => id.startsWith("p4_house_") },
  { id: "dasha", label: "Dasha Review", sub: "Step 4", match: (id) => id === "dasha_review" },
  { id: "pari", label: "Parivartana", sub: "exchange scan", match: (id) => id === "p4_parivartana" },
  { id: "life", label: "Life Blocks", sub: "10 domains", match: (id) => id.startsWith("p5_block_") },
  { id: "appx", label: "Appendix", sub: "technical", match: (id) => id === "appendix" }
];

const STAGE_EDGES: Array<[string, string]> = [
  ["src", "p1"],
  ["src", "yoga"],
  ["p1", "p2"],
  ["yoga", "p2"],
  ["p2", "d9"],
  ["p2", "div"],
  ["d9", "house"],
  ["div", "house"],
  ["d9", "dasha"],
  ["div", "dasha"],
  ["house", "pari"],
  ["pari", "life"],
  ["dasha", "life"],
  ["life", "appx"]
];

const NODE_W = 186;
const NODE_H = 56;

const STATUS_STROKE: Record<StageStatus, string> = {
  done: "#C9A96E",
  running: "#E8C877",
  failed: "#B04A38",
  pending: "#4A3E2C"
};

type StageAgg = { status: StageStatus; done: number; total: number };
type StageData = { label: string; sub: string; status: StageStatus; seed: boolean; badge: string };
type StageFlowNode = Node<StageData, "stage">;

function aggregateStages(nodes: PipelineNode[]): Record<string, StageAgg> {
  const result: Record<string, StageAgg> = {};
  for (const stage of STAGES) {
    if (stage.seed) {
      result[stage.id] = { status: "done", done: 0, total: 0 };
      continue;
    }
    const matched = nodes.filter((node) => stage.match(node.id));
    const total = matched.length;
    const done = matched.filter(
      (node) => node.status === "completed" || node.status === "skipped"
    ).length;
    let status: StageStatus = "pending";
    if (total === 0) status = "pending";
    else if (matched.some((node) => node.status === "running")) status = "running";
    else if (matched.some((node) => node.status === "failed")) status = "failed";
    else if (done === total) status = "done";
    result[stage.id] = { status, done, total };
  }
  return result;
}

// Deterministic top-to-bottom layout via dagre. Graph shape is fixed, so
// positions compute once; only node data (status/badge) changes on poll.
function computeLayout(): Record<string, { x: number; y: number }> {
  const graph = new dagre.graphlib.Graph();
  graph.setGraph({ rankdir: "TB", nodesep: 40, ranksep: 52, marginx: 24, marginy: 24 });
  graph.setDefaultEdgeLabel(() => ({}));
  for (const stage of STAGES) graph.setNode(stage.id, { width: NODE_W, height: NODE_H });
  for (const [source, target] of STAGE_EDGES) graph.setEdge(source, target);
  dagre.layout(graph);
  const positions: Record<string, { x: number; y: number }> = {};
  for (const stage of STAGES) {
    const node = graph.node(stage.id);
    positions[stage.id] = { x: node.x - NODE_W / 2, y: node.y - NODE_H / 2 };
  }
  return positions;
}

function nodeStatusClass(status: StageStatus): StageStatus {
  return status;
}

function StageNode({ data }: NodeProps<StageFlowNode>) {
  return (
    <div className={`stage-node ${data.seed ? "seed" : nodeStatusClass(data.status)}`}>
      <Handle type="target" position={Position.Top} isConnectable={false} />
      <div className="stage-node-title">{data.label}</div>
      <div className="stage-node-sub">{data.sub}</div>
      {data.badge && <span className="stage-node-badge">{data.badge}</span>}
      <Handle type="source" position={Position.Bottom} isConnectable={false} />
    </div>
  );
}

const nodeTypes = { stage: StageNode };

export function PipelineFlow({ data }: { data: PipelineData }) {
  const positions = useMemo(() => computeLayout(), []);
  const agg = useMemo(() => aggregateStages(data.nodes), [data.nodes]);

  const nodes = useMemo<StageFlowNode[]>(
    () =>
      STAGES.map((stage) => {
        const stat = agg[stage.id];
        return {
          id: stage.id,
          type: "stage",
          position: positions[stage.id],
          width: NODE_W,
          height: NODE_H,
          draggable: false,
          data: {
            label: stage.label,
            sub: stage.sub,
            status: stat.status,
            seed: Boolean(stage.seed),
            badge: stat.total > 1 ? `${stat.done}/${stat.total}` : ""
          }
        };
      }),
    [agg, positions]
  );

  const edges = useMemo<Edge[]>(
    () =>
      STAGE_EDGES.map(([source, target]) => {
        const running = agg[target]?.status === "running";
        const stroke = running ? STATUS_STROKE.running : STATUS_STROKE.pending;
        return {
          id: `${source}-${target}`,
          source,
          target,
          animated: running,
          markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16, color: stroke },
          style: { stroke, strokeWidth: running ? 2 : 1.5 }
        };
      }),
    [agg]
  );

  return (
    <div className="pipeline-flow">
      <div className="flow-head">
        <div className="flow-head-row">
          <span>Progress</span>
          <b>{data.percent}%</b>
        </div>
        <div
          className="progress-track"
          role="progressbar"
          aria-valuenow={data.percent}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <span style={{ width: `${data.percent}%` }} />
        </div>
        <div className="flow-head-meta">
          <span>
            {data.completed}/{data.total} steps{data.failed > 0 ? ` · ${data.failed} failed` : ""}
          </span>
          <span>{formatDuration(data.durationSeconds)}</span>
        </div>
      </div>
      <div className="flow-canvas">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.18 }}
          onInit={(instance) => instance.fitView({ padding: 0.18 })}
          minZoom={0.3}
          maxZoom={2}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          proOptions={{ hideAttribution: true }}
        >
          <Background variant={BackgroundVariant.Dots} gap={20} size={1.2} color="#3A2F20" />
          <Controls showInteractive={false} />
          <MiniMap
            pannable
            zoomable
            maskColor="rgba(15,12,9,0.7)"
            nodeColor={(node) => STATUS_STROKE[(node.data as StageData).status] ?? "#4A3E2C"}
          />
        </ReactFlow>
      </div>
    </div>
  );
}
