import { UserButton } from "@clerk/clerk-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Download,
  ExternalLink,
  FileArchive,
  FileText,
  LoaderCircle,
  RefreshCw,
  Timer
} from "lucide-react";
import { api } from "../api";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { cn } from "../lib/cn";
import { formatDuration } from "../lib/pipeline";
import type {
  AdminArtifactSummary,
  AdminExportSummary,
  AdminSessionDetailResponse,
  AdminSessionSummary,
  CoreJobNode
} from "../../shared/domain";
import { StatusBadge, formatDateTime } from "./AdminSessions";

type MetricNode = {
  id: string;
  label?: string;
  wave?: number;
  files?: string[];
  dependencies?: string[];
  status?: string;
  startedAt?: string | null;
  finishedAt?: string | null;
  durationSeconds?: number | null;
  error?: string | null;
};

export function AdminSessionDetail() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<AdminSessionDetailResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [exporting, setExporting] = useState(false);

  async function load(options: { quiet?: boolean } = {}) {
    if (!id) return;
    setError("");
    if (options.quiet) setRefreshing(true);
    else setLoading(true);
    try {
      setDetail(await api.getAdminSession(id));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load admin session.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    void load();
  }, [id]);

  useEffect(() => {
    if (!detail || !["queued", "running", "stalled"].includes(detail.summary.status)) return;
    const timer = window.setInterval(() => void load({ quiet: true }), 5000);
    return () => window.clearInterval(timer);
  }, [detail?.summary.status, id]);

  const nodes = useMemo(() => resolveNodes(detail), [detail]);

  async function downloadPdf() {
    if (!id || exporting) return;
    setError("");
    setExporting(true);
    try {
      await api.downloadReportPdf(id);
      await load({ quiet: true });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not download PDF.");
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="min-h-screen bg-cream-2 text-ink">
      <header className="border-b border-gold/25 bg-cream/95 px-5 py-4 backdrop-blur-lg sm:px-8">
        <div className="mx-auto flex max-w-[1440px] flex-wrap items-center gap-3">
          <Button
            variant="ghost"
            size="icon"
            title="Back to sessions"
            onClick={() => navigate("/admin/sessions")}
          >
            <ArrowLeft size={17} />
          </Button>
          <div>
            <div className="text-[10px] uppercase tracking-[2.2px] text-gold">Admin session</div>
            <h1 className="font-mono text-lg font-semibold tracking-normal">{id}</h1>
          </div>
          <div className="flex-1" />
          <Button
            variant="outline"
            size="sm"
            onClick={() => void load({ quiet: true })}
            disabled={refreshing}
          >
            {refreshing ? (
              <LoaderCircle className="size-4 animate-spin" />
            ) : (
              <RefreshCw size={14} />
            )}
            Refresh
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate(`/session/${encodeURIComponent(id)}`)}
          >
            <ExternalLink size={14} />
            Open Reading
          </Button>
          <Button size="sm" onClick={() => void downloadPdf()} disabled={exporting}>
            {exporting ? <LoaderCircle className="size-4 animate-spin" /> : <Download size={14} />}
            PDF
          </Button>
          <UserButton afterSignOutUrl="/" />
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-5 py-6 sm:px-8">
        {error && (
          <div className="rounded-md border border-red/30 bg-red/10 px-4 py-3 text-sm text-red">
            {error}
          </div>
        )}

        {loading ? (
          <div className="grid min-h-[420px] place-items-center text-muted">
            <div className="text-center">
              <LoaderCircle className="mx-auto size-8 animate-spin text-gold" />
              <p className="mt-2 text-sm">Loading session detail...</p>
            </div>
          </div>
        ) : detail ? (
          <>
            <SessionOverview summary={detail.summary} />
            <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
              <RunNodesPanel nodes={nodes} summary={detail.summary} />
              <div className="flex flex-col gap-5">
                <SubjectPanel summary={detail.summary} />
                <ExportsPanel
                  exports={detail.exports}
                  sessionId={id}
                  onDownloadPdf={() => void downloadPdf()}
                />
                <ArtifactsPanel artifacts={detail.artifacts} />
              </div>
            </div>
          </>
        ) : null}
      </main>
    </div>
  );
}

function SessionOverview({ summary }: { summary: AdminSessionSummary }) {
  return (
    <section className="grid gap-3 lg:grid-cols-5">
      <OverviewTile
        label="Status"
        value={<StatusBadge status={summary.status} />}
        icon={<Activity size={15} />}
      />
      <OverviewTile label="Stage" value={summary.stage} icon={<FileText size={15} />} />
      <OverviewTile
        label="Progress"
        value={`${summary.progress.percent}%`}
        detail={`${summary.progress.completed}/${summary.progress.total || 0} tasks`}
        icon={<CheckCircle2 size={15} />}
      />
      <OverviewTile
        label="Duration"
        value={formatDuration(summary.durationSeconds)}
        icon={<Timer size={15} />}
      />
      <OverviewTile
        label="Updated"
        value={formatDateTime(summary.updatedAt)}
        icon={<RefreshCw size={15} />}
      />
    </section>
  );
}

function OverviewTile({
  label,
  value,
  detail,
  icon
}: {
  label: string;
  value: ReactNode;
  detail?: string;
  icon: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-gold/25 bg-cream px-4 py-4 shadow-[0_14px_36px_rgba(44,31,15,0.06)]">
      <div className="mb-2 flex items-center justify-between text-[10px] uppercase tracking-[1.8px] text-muted">
        {label}
        <span className="grid size-7 place-items-center rounded-full border border-gold/25 bg-cream-2 text-gold-dim">
          {icon}
        </span>
      </div>
      <div className="text-lg font-semibold tracking-normal">{value}</div>
      {detail && <div className="mt-1 text-xs text-muted">{detail}</div>}
    </div>
  );
}

function RunNodesPanel({ nodes, summary }: { nodes: MetricNode[]; summary: AdminSessionSummary }) {
  return (
    <section className="rounded-lg border border-gold/25 bg-cream shadow-[0_18px_48px_rgba(44,31,15,0.07)]">
      <div className="flex items-start justify-between gap-4 border-b border-gold/20 px-4 py-4">
        <div>
          <div className="text-[10px] uppercase tracking-[2.2px] text-gold">Execution</div>
          <h2 className="mt-1 text-lg font-semibold tracking-normal">Run Tasks</h2>
        </div>
        <div className="w-[220px] pt-1">
          <div className="mb-1 flex justify-between text-[11px] text-muted">
            <span>{summary.progress.percent}%</span>
            <span>{summary.progress.failed} failed</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-cream-3">
            <div
              className={cn(
                "h-full rounded-full",
                summary.status === "failed" ? "bg-red" : "bg-gold"
              )}
              style={{ width: `${Math.min(100, Math.max(0, summary.progress.percent))}%` }}
            />
          </div>
        </div>
      </div>

      {summary.error && (
        <div className="mx-4 mt-4 rounded-md border border-red/25 bg-red/10 px-3 py-2 text-xs leading-relaxed text-red">
          {summary.error}
        </div>
      )}

      {nodes.length === 0 ? (
        <div className="grid min-h-[240px] place-items-center px-6 text-center text-muted">
          <p>No reading tasks have been written yet.</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-gold/20 bg-cream-2/70 text-[10px] uppercase tracking-[1.8px] text-muted">
                <th className="px-4 py-3 font-semibold">Task</th>
                <th className="px-4 py-3 font-semibold">Phase</th>
                <th className="px-4 py-3 font-semibold">Status</th>
                <th className="px-4 py-3 font-semibold">Duration</th>
                <th className="px-4 py-3 font-semibold">Files</th>
              </tr>
            </thead>
            <tbody>
              {nodes.map((node) => (
                <tr key={node.id} className="border-b border-gold/15 align-top">
                  <td className="px-4 py-3">
                    <div className="font-medium text-ink">{node.label ?? node.id}</div>
                    <div className="mt-1 font-mono text-[10px] text-muted">{node.id}</div>
                    {node.error && (
                      <div className="mt-2 flex gap-1.5 rounded-md border border-red/20 bg-red/10 px-2 py-1.5 text-xs leading-relaxed text-red">
                        <AlertTriangle className="mt-0.5 size-3 shrink-0" />
                        <span>{node.error}</span>
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-body">{node.wave ?? "-"}</td>
                  <td className="px-4 py-3">
                    <NodeBadge status={node.status ?? "pending"} />
                  </td>
                  <td className="px-4 py-3 text-body">
                    {formatDuration(node.durationSeconds)}
                    <div className="mt-1 text-[11px] text-muted">
                      {formatDateTime(node.finishedAt)}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex max-w-[260px] flex-wrap gap-1.5">
                      {(node.files ?? []).map((file) => (
                        <span
                          key={file}
                          className="rounded-full border border-gold/20 bg-cream-2 px-2 py-1 font-mono text-[10px] text-body"
                        >
                          {file}
                        </span>
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function SubjectPanel({ summary }: { summary: AdminSessionSummary }) {
  const subject = summary.subject;
  return (
    <section className="rounded-lg border border-gold/25 bg-cream p-4 shadow-[0_18px_48px_rgba(44,31,15,0.07)]">
      <div className="mb-4 text-[10px] uppercase tracking-[2.2px] text-gold">Input</div>
      <InfoRow label="Birth place" value={subject?.birthPlace} />
      <InfoRow label="Birth date" value={subject?.birthDate} />
      <InfoRow label="Birth time" value={subject?.birthTime} />
      <InfoRow label="Time precision" value={subject?.timePrecision} />
      <InfoRow label="Time source" value={subject?.timeSource} />
      <InfoRow label="Timezone" value={subject?.timezone} />
      <InfoRow label="Gender" value={subject?.gender} />
      <InfoRow label="Relationship" value={subject?.relationship} />
    </section>
  );
}

function ExportsPanel({
  exports,
  sessionId,
  onDownloadPdf
}: {
  exports: AdminExportSummary[];
  sessionId: string;
  onDownloadPdf: () => void;
}) {
  return (
    <section className="rounded-lg border border-gold/25 bg-cream p-4 shadow-[0_18px_48px_rgba(44,31,15,0.07)]">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-[2.2px] text-gold">Exports</div>
          <h3 className="mt-1 text-base font-semibold tracking-normal">Generated Files</h3>
        </div>
        <Button variant="outline" size="sm" onClick={onDownloadPdf}>
          <Download size={14} />
          PDF
        </Button>
      </div>
      {exports.length === 0 ? (
        <div className="rounded-md border border-dashed border-gold/30 px-3 py-4 text-sm text-muted">
          No export files yet.
        </div>
      ) : (
        <div className="grid gap-2">
          {exports.map((item) => (
            <div
              key={item.path}
              className="flex items-center justify-between gap-3 rounded-md bg-cream-2 px-3 py-2"
            >
              <div className="min-w-0">
                <div className="truncate font-mono text-xs text-ink">{item.name}</div>
                <div className="mt-0.5 text-[11px] text-muted">
                  {formatBytes(item.sizeBytes)} · {formatDateTime(item.updatedAt)}
                </div>
              </div>
              {item.path.endsWith(".pdf") && (
                <a
                  className="text-xs font-semibold text-gold-dim hover:text-gold"
                  href={`/api/skill-sessions/${encodeURIComponent(sessionId)}/report.pdf`}
                >
                  Download
                </a>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function ArtifactsPanel({ artifacts }: { artifacts: AdminArtifactSummary[] }) {
  return (
    <section className="rounded-lg border border-gold/25 bg-cream p-4 shadow-[0_18px_48px_rgba(44,31,15,0.07)]">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <div className="text-[10px] uppercase tracking-[2.2px] text-gold">Files</div>
          <h3 className="mt-1 text-base font-semibold tracking-normal">Session Files</h3>
        </div>
        <Badge variant="neutral">{artifacts.length}</Badge>
      </div>
      <div className="max-h-[420px] overflow-y-auto">
        {artifacts.map((artifact) => (
          <div
            key={artifact.path}
            className="flex items-center gap-3 border-b border-gold/15 py-2.5 last:border-0"
          >
            <span className="grid size-8 shrink-0 place-items-center rounded-md border border-gold/20 bg-cream-2 text-gold-dim">
              {artifact.kind === "pdf" ? <FileArchive size={15} /> : <FileText size={15} />}
            </span>
            <div className="min-w-0 flex-1">
              <div className="truncate font-mono text-xs text-ink" title={artifact.path}>
                {artifact.path}
              </div>
              <div className="mt-0.5 text-[11px] text-muted">
                {artifact.kind} · {formatBytes(artifact.sizeBytes)} ·{" "}
                {formatDateTime(artifact.updatedAt)}
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function InfoRow({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="grid grid-cols-[130px_1fr] gap-3 border-b border-gold/15 py-2.5 text-sm last:border-0">
      <div className="text-xs uppercase tracking-[1.4px] text-muted">{label}</div>
      <div className="min-w-0 text-body">{value || "-"}</div>
    </div>
  );
}

function NodeBadge({ status }: { status: string }) {
  if (status === "completed" || status === "skipped") return <Badge variant="done">{status}</Badge>;
  if (status === "failed") return <Badge variant="error">failed</Badge>;
  if (status === "running") return <Badge variant="gold">running</Badge>;
  return <Badge variant="neutral">{status}</Badge>;
}

function resolveNodes(detail: AdminSessionDetailResponse | null): MetricNode[] {
  if (!detail) return [];
  if (detail.activeJob?.nodes?.length) {
    return detail.activeJob.nodes.map((node: CoreJobNode) => ({
      id: node.id,
      label: node.label,
      wave: node.wave,
      files: node.files,
      dependencies: node.dependencies,
      status: node.status,
      startedAt: node.startedAt,
      finishedAt: node.finishedAt,
      durationSeconds: node.durationSeconds,
      error: node.error
    }));
  }
  const nodes = isRecord(detail.runMetrics) ? detail.runMetrics.nodes : null;
  return Array.isArray(nodes)
    ? nodes.filter(isRecord).map((node) => ({
        id: String(node.id ?? ""),
        label: typeof node.label === "string" ? node.label : undefined,
        wave: typeof node.wave === "number" ? node.wave : undefined,
        files: Array.isArray(node.files) ? node.files.map(String) : [],
        dependencies: Array.isArray(node.dependencies) ? node.dependencies.map(String) : [],
        status: typeof node.status === "string" ? node.status : "pending",
        startedAt: typeof node.startedAt === "string" ? node.startedAt : null,
        finishedAt: typeof node.finishedAt === "string" ? node.finishedAt : null,
        durationSeconds: typeof node.durationSeconds === "number" ? node.durationSeconds : null,
        error: typeof node.error === "string" ? node.error : null
      }))
    : [];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function formatBytes(value: number) {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}
