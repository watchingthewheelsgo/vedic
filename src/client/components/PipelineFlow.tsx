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
    seed: true,
    match: (id) => id === "chart_facts"
  },
  {
    id: "reader",
    label: "Birth Time Check",
    sub: "lived evidence",
    seed: true,
    match: (id) => id === "reader_prevalidation"
  },
  {
    id: "judgement",
    label: "Evidence Synthesis",
    sub: "facts into claims",
    match: (id) => id === "vedicdust_judgement"
  },
  {
    id: "consultation",
    label: "Professional Reading",
    sub: "personal dossier",
    match: (id) => id === "vedicdust_consultation"
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
