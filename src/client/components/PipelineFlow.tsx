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
import { cn } from "../lib/cn";

export type StageStatus = "done" | "running" | "waiting" | "failed" | "pending";

export type StageDef = {
  id: string;
  label: string;
  sub: string;
  seed?: boolean;
  match: (id: string) => boolean;
};

// Logical stages shown on the canvas. Each aggregates one group of backend
// batch nodes, mirroring docs/pipeline.md so the graph stays readable while the
// underlying DAG has ~48 nodes.
export const WORKSHOP_STAGES: StageDef[] = [
  { id: "src", label: "Birth Data", sub: "structured_data", seed: true, match: () => false },
  { id: "reader", label: "Pre-validation", sub: "vedic-reader", match: (id) => id === "reader_prevalidation" },
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

export const WORKSHOP_STAGE_EDGES: Array<[string, string]> = [
  ["src", "reader"],
  ["reader", "p1"],
  ["reader", "yoga"],
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
  waiting: "#C9A96E",
  failed: "#B04A38",
  pending: "#4A3E2C"
};

type StageAgg = { status: StageStatus; done: number; total: number };
type StageData = {
  label: string;
  sub: string;
  status: StageStatus;
  seed: boolean;
  selected: boolean;
  badge: string;
};
type StageFlowNode = Node<StageData, "stage">;

export function aggregateWorkshopStages(nodes: PipelineNode[]): Record<string, StageAgg> {
  const result: Record<string, StageAgg> = {};
  for (const stage of WORKSHOP_STAGES) {
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
    else if (matched.some((node) => node.status === "waiting")) status = "waiting";
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
  for (const stage of WORKSHOP_STAGES) graph.setNode(stage.id, { width: NODE_W, height: NODE_H });
  for (const [source, target] of WORKSHOP_STAGE_EDGES) graph.setEdge(source, target);
  dagre.layout(graph);
  const positions: Record<string, { x: number; y: number }> = {};
  for (const stage of WORKSHOP_STAGES) {
    const node = graph.node(stage.id);
    positions[stage.id] = { x: node.x - NODE_W / 2, y: node.y - NODE_H / 2 };
  }
  return positions;
}

function nodeStatusClass(status: StageStatus): StageStatus {
  return status;
}

function StageNode({ data }: NodeProps<StageFlowNode>) {
  const statusClass: Record<StageStatus, string> = {
    done: "border-gold bg-linear-to-b from-gold/15 to-night-3 text-gold-light",
    running: "border-gold bg-night-3 text-white shadow-[0_0_0_1px_var(--color-gold),0_4px_18px_rgba(201,169,110,0.35)]",
    waiting: "border-gold bg-linear-to-b from-gold/10 to-night-3 text-gold-light",
    failed: "border-red bg-night-3 text-cream",
    pending: "border-gold/25 bg-night-3 text-cream opacity-60"
  };
  return (
    <div
      className={cn(
        "relative min-h-14 w-[186px] cursor-pointer rounded-lg border-[1.5px] px-3 py-2 font-sans shadow-[0_4px_14px_rgba(0,0,0,0.3)] transition hover:-translate-y-px hover:border-gold/75",
        data.seed ? "border-gold bg-night text-gold" : statusClass[nodeStatusClass(data.status)],
        data.selected && "shadow-[0_0_0_2px_var(--color-gold),0_10px_28px_rgba(201,169,110,0.28)]"
      )}
    >
      <Handle type="target" position={Position.Top} isConnectable={false} />
      <div className="text-sm font-semibold">{data.label}</div>
      <div className="mt-0.5 text-[11px] text-cream/45">{data.sub}</div>
      {data.badge && (
        <span
          className={cn(
            "absolute right-3 top-2 rounded-lg bg-gold px-2 py-0.5 text-[10.5px] font-extrabold tabular-nums text-night",
            data.status === "failed" && "bg-red text-white",
            data.status === "pending" && "bg-gold/40"
          )}
        >
          {data.badge}
        </span>
      )}
      <Handle type="source" position={Position.Bottom} isConnectable={false} />
    </div>
  );
}

const nodeTypes = { stage: StageNode };

export function PipelineFlow({
  data,
  selectedStageId = "src",
  onSelectStage
}: {
  data: PipelineData;
  selectedStageId?: string;
  onSelectStage?: (stageId: string) => void;
}) {
  const positions = useMemo(() => computeLayout(), []);
  const agg = useMemo(() => aggregateWorkshopStages(data.nodes), [data.nodes]);

  const nodes = useMemo<StageFlowNode[]>(
    () =>
      WORKSHOP_STAGES.map((stage) => {
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
            selected: selectedStageId === stage.id,
            badge: stat.status === "waiting" ? "input" : stat.total > 1 ? `${stat.done}/${stat.total}` : ""
          }
        };
      }),
    [agg, positions, selectedStageId]
  );

  const edges = useMemo<Edge[]>(
    () =>
      WORKSHOP_STAGE_EDGES.map(([source, target]) => {
        const running = agg[target]?.status === "running" || agg[target]?.status === "waiting";
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
    <div className="flex h-full flex-col">
      <div className="grid gap-2 border-b border-gold/15 bg-night-2 px-5 py-3.5">
        <div className="flex items-baseline justify-between">
          <span className="text-xs uppercase tracking-[1px] text-cream/50">Progress</span>
          <b className="text-2xl font-semibold text-gold">{data.percent}%</b>
        </div>
        <div
          className="h-[7px] overflow-hidden rounded-full bg-night-3"
          role="progressbar"
          aria-valuenow={data.percent}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <span
            className="block h-full bg-linear-to-r from-gold-dim to-gold transition-[width] duration-300"
            style={{ width: `${data.percent}%` }}
          />
        </div>
        <div className="flex justify-between text-xs text-cream/45">
          <span>
            {data.completed}/{data.total} steps{data.failed > 0 ? ` · ${data.failed} failed` : ""}
          </span>
          <span>{formatDuration(data.durationSeconds)}</span>
        </div>
      </div>
      <div className="flow-canvas relative min-h-0 flex-1">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodeClick={(_, node) => onSelectStage?.(node.id)}
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
