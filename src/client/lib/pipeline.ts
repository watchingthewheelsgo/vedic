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
  const readerNode = readerPipelineNode(options.session ?? null, Boolean(options.readerRunning));

  if (coreJob && coreJob.nodes.length > 0) {
    const coreNodes = coreJob.nodes.map((node) => ({
      id: node.id,
      label: node.label,
      wave: node.wave + 1,
      status: node.status,
      files: node.files,
      dependencies: node.dependencies,
      startedAt: node.startedAt,
      finishedAt: node.finishedAt,
      durationSeconds: node.durationSeconds,
      error: node.error
    }));
    const nodes = readerNode ? [readerNode, ...coreNodes] : coreNodes;
    const readerComplete = readerNode?.status === "completed" ? 1 : 0;
    const readerFailed = readerNode?.status === "failed" ? 1 : 0;
    const total = coreJob.progress.total + (readerNode ? 1 : 0);
    const completed = coreJob.progress.completed + readerComplete;
    const failed = coreJob.progress.failed + readerFailed;
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
      wave: (node.wave ?? 1) + 1,
      status: persistedFailed && node.status === "running" ? "pending" : node.status ?? "pending",
      files: node.files ?? [],
      dependencies: node.dependencies ?? [],
      startedAt: node.startedAt ?? null,
      finishedAt: node.finishedAt ?? null,
      error: node.error ?? null,
      durationSeconds: node.durationSeconds ?? null
    }));
    const allNodes = readerNode ? [readerNode, ...normalized] : normalized;
    const total = runMetrics?.progress?.total ?? normalized.length;
    const completed =
      runMetrics?.progress?.completed ??
      normalized.filter((node) => node.status === "completed" || node.status === "skipped").length;
    const failed =
      runMetrics?.progress?.failed ??
      normalized.filter((node) => node.status === "failed").length;
    const adjustedTotal = total + (readerNode ? 1 : 0);
    const adjustedCompleted = completed + (readerNode?.status === "completed" ? 1 : 0);
    const adjustedFailed = failed + (readerNode?.status === "failed" ? 1 : 0);
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

  if (readerNode) {
    const completed = readerNode.status === "completed" ? 1 : 0;
    const failed = readerNode.status === "failed" ? 1 : 0;
    return {
      nodes: [readerNode],
      status: readerNode.status,
      percent: completed ? 100 : 0,
      completed,
      total: 1,
      failed,
      durationSeconds: null
    };
  }

  return null;
}

function readerPipelineNode(
  session: SkillSessionResponse | null,
  readerRunning: boolean
): PipelineNode | null {
  const artifacts = session?.artifacts ?? [];
  const hasStructuredData = artifacts.some((artifact) => artifact.path === "structured_data.md");
  if (!hasStructuredData) return null;
  const prevalidation = artifacts.find((artifact) => artifact.path === "reader_prevalidation.md");
  const feedback = artifacts.find((artifact) => artifact.path === "user_context.md");
  let status = "pending";
  if (feedback) status = "completed";
  else if (prevalidation) status = "waiting";
  else if (readerRunning) status = "running";

  return {
    id: "reader_prevalidation",
    label: "Reader pre-validation",
    wave: 1,
    status,
    files: ["reader_prevalidation.md", "user_context.md"],
    dependencies: ["structured_data.md"],
    startedAt: null,
    finishedAt: feedback?.updatedAt ?? prevalidation?.updatedAt ?? null,
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
