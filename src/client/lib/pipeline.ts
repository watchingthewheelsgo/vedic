import type { CoreJobResponse, SkillSessionResponse } from "../../shared/domain";

export type RunMetrics = {
  status?: string;
  calculator?: { durationSeconds?: number | null } | null;
  durationSeconds?: number | null;
  progress?: { total?: number; completed?: number; failed?: number } | null;
  nodes?: Array<{
    id: string;
    label?: string;
    files?: string[];
    dependencies?: string[];
    wave?: number;
    status?: string;
    startedAt?: string | null;
    finishedAt?: string | null;
    durationSeconds?: number | null;
    error?: string | null;
  }>;
};

export type PipelineNode = {
  id: string;
  label: string;
  wave: number;
  status: string;
  files: string[];
  dependencies: string[];
  startedAt?: string | null;
  finishedAt?: string | null;
  durationSeconds?: number | null;
  error?: string | null;
};

export type PipelineData = {
  nodes: PipelineNode[];
  status?: string;
  percent: number;
  completed: number;
  total: number;
  failed: number;
  durationSeconds?: number | null;
};

export function parseRunMetrics(session: SkillSessionResponse | null): RunMetrics | null {
  const artifact = session?.artifacts.find((item) => item.path === "run_metrics.json");
  if (!artifact) return null;
  try {
    return JSON.parse(artifact.content) as RunMetrics;
  } catch {
    return null;
  }
}

// Normalize a pipeline view from either the live core job or, when no job is in
// memory (e.g. reopened session), the persisted run_metrics.json.
export function getPipelineData(
  coreJob: CoreJobResponse | null,
  runMetrics: RunMetrics | null,
  options: { session?: SkillSessionResponse | null; readerRunning?: boolean } = {}
): PipelineData | null {
  const session = options.session ?? null;
  const calculatorNode = calculatorPipelineNode(session);
  const readerNode = readerPipelineNode(session, Boolean(options.readerRunning));
  const setupNodes = [calculatorNode, readerNode].filter((node): node is PipelineNode =>
    Boolean(node)
  );

  if (coreJob && coreJob.nodes.length > 0) {
    const coreNodes = coreJob.nodes.map((node) => ({
      id: node.id,
      label: node.label,
      wave: node.wave + setupNodes.length,
      status: node.status,
      files: node.files,
      dependencies: node.dependencies,
      startedAt: node.startedAt,
      finishedAt: node.finishedAt,
      durationSeconds: node.durationSeconds,
      error: node.error
    }));
    const nodes = [...setupNodes, ...coreNodes];
    const setupComplete = setupNodes.filter((node) => node.status === "completed").length;
    const setupFailed = setupNodes.filter((node) => node.status === "failed").length;
    const total = coreJob.progress.total + setupNodes.length;
    const completed = coreJob.progress.completed + setupComplete;
    const failed = coreJob.progress.failed + setupFailed;
    return {
      nodes,
      status: coreJob.status,
      percent: total > 0 ? Math.round((completed / total) * 100) : 0,
      completed,
      total,
      failed,
      durationSeconds: coreJob.durationSeconds
    };
  }

  const nodes = runMetrics?.nodes;
  if (nodes && nodes.length > 0) {
    const persistedFailed = runMetrics?.status === "failed";
    const normalized: PipelineNode[] = nodes.map((node) => ({
      id: node.id,
      label: node.label ?? node.id,
      wave: (node.wave ?? 1) + setupNodes.length,
      status: persistedFailed && node.status === "running" ? "pending" : (node.status ?? "pending"),
      files: node.files ?? [],
      dependencies: node.dependencies ?? [],
      startedAt: node.startedAt ?? null,
      finishedAt: node.finishedAt ?? null,
      error: node.error ?? null,
      durationSeconds: node.durationSeconds ?? null
    }));
    const allNodes = [...setupNodes, ...normalized];
    const total = runMetrics?.progress?.total ?? normalized.length;
    const completed =
      runMetrics?.progress?.completed ??
      normalized.filter((node) => node.status === "completed" || node.status === "skipped").length;
    const failed =
      runMetrics?.progress?.failed ?? normalized.filter((node) => node.status === "failed").length;
    const adjustedTotal = total + setupNodes.length;
    const adjustedCompleted =
      completed + setupNodes.filter((node) => node.status === "completed").length;
    const adjustedFailed = failed + setupNodes.filter((node) => node.status === "failed").length;
    return {
      nodes: allNodes,
      status: runMetrics?.status,
      percent: adjustedTotal > 0 ? Math.round((adjustedCompleted / adjustedTotal) * 100) : 0,
      completed: adjustedCompleted,
      total: adjustedTotal,
      failed: adjustedFailed,
      durationSeconds: runMetrics?.durationSeconds ?? null
    };
  }

  if (setupNodes.length > 0) {
    const completed = setupNodes.filter((node) => node.status === "completed").length;
    const failed = setupNodes.filter((node) => node.status === "failed").length;
    return {
      nodes: setupNodes,
      status: readerNode?.status ?? calculatorNode?.status,
      percent: Math.round((completed / setupNodes.length) * 100),
      completed,
      total: setupNodes.length,
      failed,
      durationSeconds: null
    };
  }

  return null;
}

function calculatorPipelineNode(session: SkillSessionResponse | null): PipelineNode | null {
  const artifacts = session?.artifacts ?? [];
  const structuredData = artifacts.find((artifact) => artifact.path === "structured_data.md");
  if (!structuredData) return null;
  const structuredJson = artifacts.find((artifact) => artifact.path === "structured_data.json");
  const inputContext = artifacts.find((artifact) => artifact.path === "birth_input_context.json");
  const sensitivity = artifacts.find((artifact) => artifact.path === "sensitivity_scan.json");
  const rectification = artifacts.find(
    (artifact) => artifact.path === "chart_rectification_state.json"
  );
  return {
    id: "chart_facts",
    label: "Chart Facts",
    wave: 1,
    status: "completed",
    files: [
      "structured_data.md",
      "structured_data.json",
      "birth_input_context.json",
      "sensitivity_scan.json",
      "chart_rectification_state.json"
    ],
    dependencies: [],
    startedAt: null,
    finishedAt:
      sensitivity?.updatedAt ??
      rectification?.updatedAt ??
      inputContext?.updatedAt ??
      structuredJson?.updatedAt ??
      structuredData.updatedAt,
    durationSeconds: null,
    error: null
  };
}

function readerPipelineNode(
  session: SkillSessionResponse | null,
  readerRunning: boolean
): PipelineNode | null {
  const artifacts = session?.artifacts ?? [];
  const hasStructuredData = artifacts.some((artifact) => artifact.path === "structured_data.md");
  if (!hasStructuredData) return null;
  const prevalidation = artifacts.find((artifact) => artifact.path === "reader_prevalidation.md");
  const validationResult = artifacts.find(
    (artifact) => artifact.path === "prevalidation_result.json"
  );
  const feedback = artifacts.find((artifact) => artifact.path === "user_context.md");
  let status = "pending";
  if (feedback) status = "completed";
  else if (prevalidation) status = "waiting";
  else if (readerRunning) status = "running";

  return {
    id: "reader_prevalidation",
    label: "First Check",
    wave: 2,
    status,
    files: [
      "reader_prevalidation.md",
      "prevalidation_result.json",
      "chart_rectification_state.json",
      "user_context.md"
    ],
    dependencies: ["chart_facts"],
    startedAt: null,
    finishedAt:
      feedback?.updatedAt ?? validationResult?.updatedAt ?? prevalidation?.updatedAt ?? null,
    durationSeconds: null,
    error: null
  };
}

export function formatDuration(seconds?: number | null): string {
  if (seconds == null) return "—";
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`;
  const minutes = Math.floor(seconds / 60);
  const remaining = Math.round(seconds % 60);
  if (minutes < 60) return `${minutes}m ${remaining}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}
