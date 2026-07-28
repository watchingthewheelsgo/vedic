import type { PipelineNode } from "../lib/pipeline";

export type StageStatus = "done" | "running" | "waiting" | "failed" | "pending";

export type StageDef = {
  id: string;
  label: string;
  sub: string;
  seed?: boolean;
  match: (id: string) => boolean;
};

// Logical stages that aggregate the backend batch nodes into product-level
// reading moments. UI surfaces can render these as cards, progress, or chart
// reveal states without exposing the underlying DAG.
export const WORKSHOP_STAGES: StageDef[] = [
  {
    id: "src",
    label: "Personal Information",
    sub: "birth details",
    seed: true,
    match: () => false
  },
  {
    id: "chart",
    label: "Chart Facts",
    sub: "calculator",
    match: (id) => id === "chart_facts"
  },
  {
    id: "reader",
    label: "First Check",
    sub: "your replies",
    match: (id) => id === "reader_prevalidation"
  },
  { id: "p1", label: "Core Pattern", sub: "temperament", match: (id) => id === "p1" },
  { id: "yoga", label: "Major Patterns", sub: "chart themes", match: (id) => id === "p2_yoga" },
  {
    id: "p2",
    label: "Planet Signals",
    sub: "9 signals",
    match: (id) => id.startsWith("p2_") && id !== "p2_yoga"
  },
  { id: "d9", label: "Deeper Promise", sub: "D9 lens", match: (id) => id.startsWith("p3a_d9_") },
  {
    id: "div",
    label: "Life Context",
    sub: "career and home",
    match: (id) => id.startsWith("p3b_")
  },
  { id: "house", label: "Life Areas", sub: "12 houses", match: (id) => id.startsWith("p4_house_") },
  {
    id: "dasha",
    label: "Timing Guidance",
    sub: "life periods",
    match: (id) => id === "dasha_review"
  },
  { id: "pari", label: "Cross-checks", sub: "theme links", match: (id) => id === "p4_parivartana" },
  {
    id: "life",
    label: "Life Synthesis",
    sub: "10 domains",
    match: (id) => id.startsWith("p5_block_")
  },
  {
    id: "appx",
    label: "Final Reading",
    sub: "wrap-up",
    match: (id) => id === "appendix" || id === "report_quality_audit"
  }
];

export type StageAgg = { status: StageStatus; done: number; total: number };

export function aggregateWorkshopStages(
  nodes: PipelineNode[],
  stages: StageDef[] = WORKSHOP_STAGES
): Record<string, StageAgg> {
  const result: Record<string, StageAgg> = {};
  for (const stage of stages) {
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
    else if (matched.some((node) => node.status === "failed")) status = "failed";
    else if (matched.some((node) => node.status === "running")) status = "running";
    else if (matched.some((node) => node.status === "waiting")) status = "waiting";
    else if (done === total) status = "done";
    result[stage.id] = { status, done, total };
  }
  return result;
}
