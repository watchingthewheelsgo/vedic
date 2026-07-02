import type { CoreJobResponse, SkillSessionResponse } from "../../shared/domain";

export type RunMetrics = {
  status?: string;
  calculator?: { durationSeconds?: number | null } | null;
  durationSeconds?: number | null;
  progress?: { total?: number; completed?: number; failed?: number } | null;
  nodes?: Array<{
    id: string;
    label?: string;
    wave?: number;
    status?: string;
    durationSeconds?: number | null;
  }>;
};

export type PipelineNode = {
  id: string;
  label: string;
  wave: number;
  status: string;
  durationSeconds?: number | null;
};

export type PipelineData = {
  nodes: PipelineNode[];
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
  runMetrics: RunMetrics | null
): PipelineData | null {
  if (coreJob && coreJob.nodes.length > 0) {
    return {
      nodes: coreJob.nodes.map((node) => ({
        id: node.id,
        label: node.label,
        wave: node.wave,
        status: node.status,
        durationSeconds: node.durationSeconds
      })),
      percent: coreJob.progress.percent,
      completed: coreJob.progress.completed,
      total: coreJob.progress.total,
      failed: coreJob.progress.failed,
      durationSeconds: coreJob.durationSeconds
    };
  }

  const nodes = runMetrics?.nodes;
  if (nodes && nodes.length > 0) {
    const normalized: PipelineNode[] = nodes.map((node) => ({
      id: node.id,
      label: node.label ?? node.id,
      wave: node.wave ?? 1,
      status: node.status ?? "pending",
      durationSeconds: node.durationSeconds ?? null
    }));
    const total = runMetrics?.progress?.total ?? normalized.length;
    const completed =
      runMetrics?.progress?.completed ??
      normalized.filter((node) => node.status === "completed" || node.status === "skipped").length;
    const failed =
      runMetrics?.progress?.failed ??
      normalized.filter((node) => node.status === "failed").length;
    return {
      nodes: normalized,
      percent: total > 0 ? Math.round((completed / total) * 100) : 0,
      completed,
      total,
      failed,
      durationSeconds: runMetrics?.durationSeconds ?? null
    };
  }

  return null;
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
