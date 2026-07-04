import { UserButton } from "@clerk/clerk-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Download,
  Eye,
  FileText,
  LoaderCircle,
  RefreshCw,
  Search,
  ServerCog
} from "lucide-react";
import { api } from "../api";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { cn } from "../lib/cn";
import { formatDuration } from "../lib/pipeline";
import type {
  AdminSessionListResponse,
  AdminSessionStatus,
  AdminSessionSummary
} from "../../shared/domain";

const STATUS_LABELS: Record<AdminSessionStatus, string> = {
  draft: "Draft",
  validation: "Validation",
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  stalled: "Stalled"
};

export function AdminSessions() {
  const navigate = useNavigate();
  const [data, setData] = useState<AdminSessionListResponse | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  async function load(options: { quiet?: boolean } = {}) {
    setError("");
    if (options.quiet) setRefreshing(true);
    else setLoading(true);
    try {
      setData(await api.listAdminSessions());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load admin sessions.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load({ quiet: true }), 5000);
    return () => window.clearInterval(timer);
  }, []);

  const filtered = useMemo(() => {
    const sessions = data?.sessions ?? [];
    const needle = query.trim().toLowerCase();
    if (!needle) return sessions;
    return sessions.filter((session) =>
      [
        session.sessionId,
        session.status,
        session.stage,
        session.subject?.birthPlace,
        session.subject?.birthDate,
        session.activeNode,
        session.error
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(needle)
    );
  }, [data?.sessions, query]);

  return (
    <div className="min-h-screen bg-cream-2 text-ink">
      <AdminHeader
        title="Sessions"
        subtitle="Historical and running report sessions"
        refreshing={refreshing}
        onRefresh={() => void load({ quiet: true })}
      />

      <main className="mx-auto flex w-full max-w-[1440px] flex-col gap-5 px-5 py-6 sm:px-8">
        {error && (
          <div className="rounded-md border border-red/30 bg-red/10 px-4 py-3 text-sm text-red">
            {error}
          </div>
        )}

        <section className="grid gap-3 md:grid-cols-4">
          <AdminStat
            label="Total sessions"
            value={data?.total ?? 0}
            icon={<ServerCog size={16} />}
          />
          <AdminStat
            label="Running or stalled"
            value={data?.running ?? 0}
            icon={<Activity size={16} />}
            tone="gold"
          />
          <AdminStat
            label="Completed"
            value={data?.completed ?? 0}
            icon={<CheckCircle2 size={16} />}
            tone="green"
          />
          <AdminStat
            label="Failed"
            value={data?.failed ?? 0}
            icon={<AlertTriangle size={16} />}
            tone="red"
          />
        </section>

        <section className="rounded-lg border border-gold/25 bg-cream shadow-[0_18px_48px_rgba(44,31,15,0.07)]">
          <div className="flex flex-col gap-3 border-b border-gold/20 px-4 py-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div className="text-[10px] uppercase tracking-[2.2px] text-gold">Admin index</div>
              <h2 className="mt-1 text-lg font-semibold tracking-normal">All Sessions</h2>
            </div>
            <label className="relative block w-full max-w-[420px]">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" />
              <Input
                className="h-10 bg-cream-2 pl-9"
                value={query}
                placeholder="Search session, place, status, error..."
                onChange={(event) => setQuery(event.target.value)}
              />
            </label>
          </div>

          {loading ? (
            <div className="grid min-h-[360px] place-items-center text-muted">
              <div className="text-center">
                <LoaderCircle className="mx-auto size-7 animate-spin text-gold" />
                <p className="mt-2 text-sm">Loading sessions...</p>
              </div>
            </div>
          ) : filtered.length === 0 ? (
            <div className="grid min-h-[260px] place-items-center px-6 text-center text-muted">
              <p>No sessions match the current filter.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[980px] border-collapse text-left text-sm">
                <thead>
                  <tr className="border-b border-gold/20 bg-cream-2/70 text-[10px] uppercase tracking-[1.8px] text-muted">
                    <th className="px-4 py-3 font-semibold">Status</th>
                    <th className="px-4 py-3 font-semibold">Session</th>
                    <th className="px-4 py-3 font-semibold">Subject</th>
                    <th className="px-4 py-3 font-semibold">Progress</th>
                    <th className="px-4 py-3 font-semibold">Updated</th>
                    <th className="px-4 py-3 font-semibold">Files</th>
                    <th className="px-4 py-3 font-semibold">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((session) => (
                    <SessionRow
                      key={session.sessionId}
                      session={session}
                      onOpen={() =>
                        navigate(`/admin/sessions/${encodeURIComponent(session.sessionId)}`)
                      }
                      onOpenWorkshop={() =>
                        navigate(`/session/${encodeURIComponent(session.sessionId)}`)
                      }
                      onDownload={() => void api.downloadReportPdf(session.sessionId)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

function AdminHeader({
  title,
  subtitle,
  refreshing,
  onRefresh
}: {
  title: string;
  subtitle: string;
  refreshing: boolean;
  onRefresh: () => void;
}) {
  const navigate = useNavigate();
  return (
    <header className="border-b border-gold/25 bg-cream/95 px-5 py-4 backdrop-blur-lg sm:px-8">
      <div className="mx-auto flex max-w-[1440px] flex-wrap items-center gap-4">
        <button className="brand-logo border-0 bg-transparent" onClick={() => navigate("/")}>
          Veda<span>Light</span>
        </button>
        <div className="h-8 w-px bg-gold/25" />
        <div>
          <h1 className="text-xl font-semibold leading-tight tracking-normal">{title}</h1>
          <p className="m-0 text-xs text-muted">{subtitle}</p>
        </div>
        <div className="flex-1" />
        <Button variant="outline" size="sm" onClick={onRefresh} disabled={refreshing}>
          {refreshing ? <LoaderCircle className="size-4 animate-spin" /> : <RefreshCw size={14} />}
          Refresh
        </Button>
        <UserButton afterSignOutUrl="/" />
      </div>
    </header>
  );
}

function AdminStat({
  label,
  value,
  icon,
  tone = "neutral"
}: {
  label: string;
  value: number;
  icon: ReactNode;
  tone?: "neutral" | "gold" | "green" | "red";
}) {
  return (
    <div className="rounded-lg border border-gold/25 bg-cream px-4 py-4 shadow-[0_14px_36px_rgba(44,31,15,0.06)]">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-[1.8px] text-muted">{label}</span>
        <span
          className={cn(
            "grid size-7 place-items-center rounded-full border",
            tone === "gold" && "border-gold/35 bg-gold/10 text-gold-dim",
            tone === "green" && "border-green/30 bg-green/10 text-green",
            tone === "red" && "border-red/30 bg-red/10 text-red",
            tone === "neutral" && "border-gold/25 bg-cream-2 text-muted"
          )}
        >
          {icon}
        </span>
      </div>
      <div className="text-3xl font-light leading-none tracking-normal">{value}</div>
    </div>
  );
}

function SessionRow({
  session,
  onOpen,
  onOpenWorkshop,
  onDownload
}: {
  session: AdminSessionSummary;
  onOpen: () => void;
  onOpenWorkshop: () => void;
  onDownload: () => void;
}) {
  return (
    <tr className="border-b border-gold/15 transition hover:bg-gold/5">
      <td className="px-4 py-4 align-top">
        <StatusBadge status={session.status} />
        {session.activeNode && (
          <div
            className="mt-2 max-w-[170px] truncate text-xs text-muted"
            title={session.activeNode}
          >
            {session.activeNode}
          </div>
        )}
      </td>
      <td className="px-4 py-4 align-top">
        <button
          className="font-mono text-xs font-semibold text-ink hover:text-gold-dim"
          onClick={onOpen}
        >
          {session.sessionId}
        </button>
        {session.jobId && (
          <div className="mt-1 font-mono text-[10px] text-muted">job {session.jobId}</div>
        )}
      </td>
      <td className="px-4 py-4 align-top">
        <div className="font-medium text-ink">{session.subject?.birthPlace ?? "No place"}</div>
        <div className="mt-1 text-xs text-muted">
          {compact([
            session.subject?.birthDate,
            session.subject?.birthTime,
            session.subject?.timezone
          ])}
        </div>
      </td>
      <td className="px-4 py-4 align-top">
        <ProgressMeter session={session} />
        <div className="mt-1 text-xs text-muted">
          {session.progress.completed}/{session.progress.total || 0} nodes
          {session.durationSeconds ? ` · ${formatDuration(session.durationSeconds)}` : ""}
        </div>
      </td>
      <td className="px-4 py-4 align-top text-xs text-body">
        <div>{formatDateTime(session.updatedAt)}</div>
        <div className="mt-1 text-muted">created {formatDateTime(session.createdAt)}</div>
      </td>
      <td className="px-4 py-4 align-top text-xs text-body">
        <div className="flex items-center gap-1">
          <FileText size={13} className="text-gold-dim" />
          {session.artifactCount} artifacts
        </div>
        <div className="mt-1 text-muted">{session.exportCount} exports</div>
      </td>
      <td className="px-4 py-4 align-top">
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="icon" title="Open admin detail" onClick={onOpen}>
            <Eye size={15} />
          </Button>
          <Button variant="ghost" size="icon" title="Open user session" onClick={onOpenWorkshop}>
            <Activity size={15} />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            title="Download PDF"
            onClick={onDownload}
            disabled={!session.hasPdf}
          >
            <Download size={15} />
          </Button>
        </div>
      </td>
    </tr>
  );
}

function ProgressMeter({ session }: { session: AdminSessionSummary }) {
  return (
    <div className="w-[180px]">
      <div className="mb-1 flex items-center justify-between text-[11px] text-muted">
        <span>{session.progress.percent}%</span>
        {session.progress.failed > 0 && (
          <span className="text-red">{session.progress.failed} failed</span>
        )}
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-cream-3">
        <div
          className={cn(
            "h-full rounded-full",
            session.status === "failed"
              ? "bg-red"
              : session.status === "completed"
                ? "bg-green"
                : "bg-gold"
          )}
          style={{ width: `${Math.min(100, Math.max(0, session.progress.percent))}%` }}
        />
      </div>
    </div>
  );
}

export function StatusBadge({ status }: { status: AdminSessionStatus }) {
  const variant =
    status === "completed"
      ? "done"
      : status === "failed"
        ? "error"
        : status === "running" || status === "queued" || status === "validation"
          ? "gold"
          : "neutral";
  return <Badge variant={variant}>{STATUS_LABELS[status]}</Badge>;
}

function compact(values: Array<string | null | undefined>) {
  return values.filter(Boolean).join(" · ") || "No subject data";
}

export function formatDateTime(value?: string | null) {
  if (!value) return "-";
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) return value;
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(timestamp);
}
