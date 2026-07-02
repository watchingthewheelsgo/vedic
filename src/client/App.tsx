import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";
import {
  BookOpen,
  CalendarDays,
  CheckCircle2,
  Clock3,
  LoaderCircle,
  MapPin,
  Play,
  Search,
  Sparkles
} from "lucide-react";
import { api } from "./api";
import type {
  BirthInput,
  BirthTimePrecision,
  CoreJobResponse,
  PlaceOption,
  PlaceSearchLevel,
  SkillArtifact,
  SkillSessionResponse
} from "../shared/domain";

type LoadingState = "idle" | "session" | "coreJob" | "feedback";
type StepState = "done" | "active" | "waiting";

type RunMetrics = {
  status?: string;
  calculator?: {
    durationSeconds?: number | null;
  } | null;
  durationSeconds?: number | null;
};

const precisionOptions: Array<{ value: BirthTimePrecision; label: string }> = [
  { value: "exact", label: "精确到分钟" },
  { value: "approximate", label: "约略时间" },
  { value: "part_of_day", label: "仅知道时段" },
  { value: "unknown", label: "未知出生时间" }
];

const emptyBirthInput: BirthInput = {
  birthDate: "",
  birthTime: "",
  birthPlace: "",
  birthTimePrecision: "exact",
  gender: "",
  relationship: "",
  timeSource: ""
};

const reportOrder = [
  "p1_overview.md",
  "p2a_planets.md",
  "p2b_planets.md",
  "p2c_planets.md",
  "p2d_planets.md",
  "p3a_d9.md",
  "p3b_divisional.md",
  "p4a_houses.md",
  "p4b_houses.md",
  "p5a_life.md",
  "p5b_life.md",
  "appendix.md",
  "career_phase4a.md",
  "love_report.md",
  "rectification_report.md"
];

const reportTitles: Record<string, string> = {
  "p1_overview.md": "总览",
  "p2a_planets.md": "行星结构一",
  "p2b_planets.md": "行星结构二",
  "p2c_planets.md": "行星结构三",
  "p2d_planets.md": "行星结构四",
  "p3a_d9.md": "D9 与分盘",
  "p3b_divisional.md": "分盘补充",
  "p4a_houses.md": "宫位主题一",
  "p4b_houses.md": "宫位主题二",
  "p5a_life.md": "人生板块一",
  "p5b_life.md": "人生板块二",
  "appendix.md": "附录",
  "career_phase4a.md": "事业",
  "love_report.md": "关系",
  "rectification_report.md": "校时"
};

export function App() {
  const [birthInput, setBirthInput] = useState<BirthInput>(emptyBirthInput);
  const [sessionLookup, setSessionLookup] = useState(
    () => new URLSearchParams(window.location.search).get("sessionId") ?? ""
  );
  const [session, setSession] = useState<SkillSessionResponse | null>(null);
  const [selectedReportPath, setSelectedReportPath] = useState("");
  const [feedbackMarkdown, setFeedbackMarkdown] = useState("");
  const [coreJob, setCoreJob] = useState<CoreJobResponse | null>(null);
  const [loading, setLoading] = useState<LoadingState>("idle");
  const [error, setError] = useState("");

  const coreJobId = coreJob?.jobId;
  const coreJobStatus = coreJob?.status;
  const isCoreJobActive = coreJobStatus === "queued" || coreJobStatus === "running";
  const reportSections = useMemo(() => getReportSections(session), [session]);
  const selectedReport =
    reportSections.find((artifact) => artifact.path === selectedReportPath) ??
    reportSections[0] ??
    null;
  const runMetrics = useMemo(() => parseRunMetrics(session), [session]);
  const progress = getProgress({
    session,
    coreJob,
    loading,
    reportSections,
    hasError: Boolean(error)
  });

  useEffect(() => {
    const initialSessionId = new URLSearchParams(window.location.search).get("sessionId");
    if (initialSessionId) {
      void loadSessionById(initialSessionId);
    }
  }, []);

  useEffect(() => {
    if (!reportSections.length) return;
    if (!reportSections.some((artifact) => artifact.path === selectedReportPath)) {
      setSelectedReportPath(reportSections[0].path);
    }
  }, [reportSections, selectedReportPath]);

  useEffect(() => {
    if (!coreJobId || (coreJobStatus !== "queued" && coreJobStatus !== "running")) return;

    let cancelled = false;
    const timer = window.setInterval(() => {
      api
        .getCoreJob(coreJobId)
        .then((response) => {
          if (cancelled) return;
          setCoreJob(response);
          if (response.session) {
            setSession(response.session);
          }
          if (response.status === "failed") {
            setError(response.message);
          }
        })
        .catch((caught) => {
          if (!cancelled) {
            setError(caught instanceof Error ? caught.message : "无法刷新报告进度");
          }
        });
    }, 5000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [coreJobId, coreJobStatus]);

  async function submitBirthData(event: FormEvent) {
    event.preventDefault();
    setError("");
    setCoreJob(null);
    setLoading("session");
    try {
      const response = await api.createSkillSession(normalizeBirthInput(birthInput));
      setSession(response);
      setSessionLookup(response.sessionId);
      await startCoreReport(response.sessionId);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "无法生成报告");
    } finally {
      setLoading("idle");
    }
  }

  async function loadExistingSession(event: FormEvent) {
    event.preventDefault();
    if (!sessionLookup.trim()) return;
    await loadSessionById(sessionLookup.trim());
  }

  async function loadSessionById(sessionId: string) {
    setError("");
    setLoading("session");
    try {
      const response = await api.getSkillSession(sessionId);
      setSession(response);
      setCoreJob(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "无法载入报告");
    } finally {
      setLoading("idle");
    }
  }

  async function startCoreReport(sessionId = session?.sessionId) {
    if (!sessionId) return;
    setError("");
    setLoading("coreJob");
    try {
      const response = await api.startCoreJob({
        sessionId,
        skill: "vedic-core",
        userMessage: ""
      });
      setCoreJob(response);
      if (response.session) {
        setSession(response.session);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "完整报告启动失败");
    } finally {
      setLoading("idle");
    }
  }

  async function submitFeedback() {
    if (!session || !feedbackMarkdown.trim()) return;
    setError("");
    setLoading("feedback");
    try {
      const response = await api.recordSkillFeedback({
        sessionId: session.sessionId,
        feedbackMarkdown
      });
      setSession(response);
      setFeedbackMarkdown("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "补充信息写入失败");
    } finally {
      setLoading("idle");
    }
  }

  return (
    <main className="advisor-app">
      <section className="intake-shell">
        <header className="app-title">
          <div className="title-mark">
            <Sparkles size={19} />
          </div>
          <div>
            <h1>命盘顾问</h1>
            <p>私人报告</p>
          </div>
        </header>

        {progress.reportReady && (
          <ProgressPanel
            progress={progress}
            job={coreJob}
            metrics={runMetrics}
            canResume={Boolean(session && !isCoreJobActive && reportSections.length === 0)}
            onResume={() => void startCoreReport()}
          />
        )}

        {!progress.reportReady ? (
          <form className="intake-card" onSubmit={submitBirthData}>
            <div className="card-heading">
              <span>出生信息</span>
              <small>用于生成完整报告</small>
            </div>
            <BirthFields input={birthInput} onChange={setBirthInput} />
            <button className="primary-button" disabled={loading !== "idle" || isCoreJobActive}>
              <Play size={16} />
              生成完整报告
            </button>
          </form>
        ) : (
          <details className="quiet-panel">
            <summary>新建一份报告</summary>
            <form className="collapsed-form" onSubmit={submitBirthData}>
              <BirthFields input={birthInput} onChange={setBirthInput} />
              <button className="primary-button" disabled={loading !== "idle" || isCoreJobActive}>
                <Play size={16} />
                生成完整报告
              </button>
            </form>
          </details>
        )}

        {!progress.reportReady && (
          <ProgressPanel
            progress={progress}
            job={coreJob}
            metrics={runMetrics}
            canResume={Boolean(session && !isCoreJobActive && reportSections.length === 0)}
            onResume={() => void startCoreReport()}
          />
        )}

        <details className="quiet-panel">
          <summary>打开已有报告</summary>
          <form onSubmit={loadExistingSession}>
            <label>
              报告编号
              <input
                value={sessionLookup}
                onChange={(event) => setSessionLookup(event.target.value)}
                placeholder="skill_..."
              />
            </label>
            <button type="submit" disabled={loading !== "idle" || isCoreJobActive}>
              打开
            </button>
          </form>
        </details>

        {session && (
          <details className="quiet-panel">
            <summary>补充已验证信息</summary>
            <textarea
              value={feedbackMarkdown}
              onChange={(event) => setFeedbackMarkdown(event.target.value)}
              rows={4}
              placeholder="例如：哪些地方准确、哪些地方不准确、想补充的经历"
            />
            <button
              type="button"
              onClick={submitFeedback}
              disabled={loading !== "idle" || isCoreJobActive}
            >
              保存补充
            </button>
          </details>
        )}

        {error && <div className="error-banner">{error}</div>}
      </section>

      <section className="report-shell">
        <header className="report-top">
          <div>
            <span>你的报告</span>
            <h2>{selectedReport ? titleForArtifact(selectedReport) : "报告将在这里呈现"}</h2>
          </div>
          {session && <small>编号 {session.sessionId}</small>}
        </header>

        {reportSections.length > 0 ? (
          <div className="report-layout">
            <nav className="chapter-tabs" aria-label="报告章节">
              {reportSections.map((artifact, index) => (
                <button
                  key={artifact.path}
                  type="button"
                  className={artifact.path === selectedReport?.path ? "selected" : ""}
                  onClick={() => setSelectedReportPath(artifact.path)}
                >
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  {titleForArtifact(artifact)}
                </button>
              ))}
            </nav>
            <article className="report-paper">
              {selectedReport && (
                <>
                  <div className="report-section-kicker">
                    <BookOpen size={16} />
                    <span>{titleForArtifact(selectedReport)}</span>
                  </div>
                  <MarkdownReport content={selectedReport.content} />
                </>
              )}
            </article>
          </div>
        ) : (
          <EmptyReport progress={progress} />
        )}
      </section>
    </main>
  );
}

function normalizeBirthInput(input: BirthInput): BirthInput {
  return {
    ...input,
    gender: input.gender.trim() || "[待填]",
    relationship: input.relationship.trim() || "[待填]",
    timeSource: input.timeSource.trim() || "未追问"
  };
}

function parseRunMetrics(session: SkillSessionResponse | null): RunMetrics | null {
  const artifact = session?.artifacts.find((item) => item.path === "run_metrics.json");
  if (!artifact) return null;
  try {
    return JSON.parse(artifact.content) as RunMetrics;
  } catch {
    return null;
  }
}

function getReportSections(session: SkillSessionResponse | null) {
  const artifacts = session?.artifacts ?? [];
  return artifacts
    .filter(isReportArtifact)
    .sort((a, b) => reportRank(a.path) - reportRank(b.path) || a.path.localeCompare(b.path));
}

function isReportArtifact(artifact: SkillArtifact) {
  const path = artifact.path;
  if (!path.endsWith(".md")) return false;
  if (
    path === "structured_data.md" ||
    path === "reader_prevalidation.md" ||
    path === "user_context.md" ||
    path === "intake.md" ||
    path.endsWith("structured_data_B.md") ||
    path.endsWith("synastry_data.md")
  ) {
    return false;
  }
  return (
    path.startsWith("p") ||
    path === "appendix.md" ||
    path.startsWith("career_") ||
    path.startsWith("love_") ||
    path === "rectification_report.md" ||
    path.includes("/reports/")
  );
}

function reportRank(path: string) {
  const normalized = path.split("/").pop() ?? path;
  const index = reportOrder.indexOf(normalized);
  if (index >= 0) return index;
  if (path.includes("/reports/")) return 200 + path.localeCompare("");
  return 100 + path.localeCompare("");
}

function titleForArtifact(artifact: SkillArtifact) {
  const basename = artifact.path.split("/").pop() ?? artifact.path;
  if (reportTitles[basename]) return reportTitles[basename];
  if (artifact.title && artifact.title !== artifact.path) return artifact.title;
  return basename.replace(/\.md$/, "").replace(/[_-]+/g, " ");
}

function getProgress({
  session,
  coreJob,
  loading,
  reportSections,
  hasError
}: {
  session: SkillSessionResponse | null;
  coreJob: CoreJobResponse | null;
  loading: LoadingState;
  reportSections: SkillArtifact[];
  hasError: boolean;
}) {
  const reportReady =
    reportSections.length > 0 &&
    (session?.stage === "core_complete" || coreJob?.status === "completed" || !coreJob);
  const activeAnalysis = coreJob?.status === "queued" || coreJob?.status === "running";
  const percent = hasError
    ? coreJob?.progress.percent ?? 0
    : activeAnalysis
      ? coreJob.progress.percent
      : reportReady
        ? 100
        : session
          ? 28
          : loading === "session"
            ? 12
            : 0;

  const steps: Array<{ label: string; state: StepState }> = [
    {
      label: "信息",
      state: session ? "done" : loading === "session" ? "active" : "waiting"
    },
    {
      label: "排盘",
      state: session ? "done" : loading === "session" ? "active" : "waiting"
    },
    {
      label: "分析",
      state: reportReady ? "done" : activeAnalysis || loading === "coreJob" ? "active" : "waiting"
    },
    {
      label: "报告",
      state: reportReady ? "done" : "waiting"
    }
  ];

  const title = hasError
    ? "需要处理"
    : reportReady
      ? "报告已完成"
      : activeAnalysis
        ? "正在生成报告"
        : session
          ? "星盘已建立"
          : "等待出生信息";

  const detail = activeAnalysis
    ? `${coreJob.progress.completed}/${coreJob.progress.total} 步完成`
    : reportReady
      ? `${reportSections.length} 个章节`
      : session
        ? "可以继续生成完整报告"
        : "填写后开始";

  return { percent, steps, title, detail, reportReady };
}

function ProgressPanel({
  progress,
  job,
  metrics,
  canResume,
  onResume
}: {
  progress: ReturnType<typeof getProgress>;
  job: CoreJobResponse | null;
  metrics: RunMetrics | null;
  canResume: boolean;
  onResume: () => void;
}) {
  return (
    <section className="progress-card">
      <div className="progress-title">
        <div>
          <span>进度</span>
          <strong>{progress.title}</strong>
        </div>
        <b>{progress.percent}%</b>
      </div>
      <div
        className="progress-track"
        role="progressbar"
        aria-valuenow={progress.percent}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <span style={{ width: `${progress.percent}%` }} />
      </div>
      <div className="step-row">
        {progress.steps.map((step) => (
          <div key={step.label} className={`step-pill ${step.state}`}>
            {step.state === "done" ? (
              <CheckCircle2 size={15} />
            ) : step.state === "active" ? (
              <LoaderCircle size={15} />
            ) : (
              <span className="step-dot" />
            )}
            {step.label}
          </div>
        ))}
      </div>
      <div className="progress-meta">
        <span>{progress.detail}</span>
        <span>{job ? formatDuration(job.durationSeconds) : formatDuration(metrics?.durationSeconds)}</span>
      </div>
      {canResume && (
        <button type="button" className="secondary-button" onClick={onResume}>
          <Sparkles size={15} />
          继续生成
        </button>
      )}
    </section>
  );
}

function EmptyReport({ progress }: { progress: ReturnType<typeof getProgress> }) {
  return (
    <div className="empty-report">
      <div className="empty-symbol">
        <CalendarDays size={28} />
      </div>
      <h2>{progress.title}</h2>
      <p>{progress.detail}</p>
    </div>
  );
}

function formatDuration(seconds?: number | null) {
  if (seconds == null) return "—";
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`;
  const minutes = Math.floor(seconds / 60);
  const remaining = Math.round(seconds % 60);
  if (minutes < 60) return `${minutes}m ${remaining}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

function BirthFields({ input, onChange }: { input: BirthInput; onChange: (value: BirthInput) => void }) {
  return (
    <>
      <div className="field-grid">
        <label>
          出生日期
          <input
            type="date"
            value={input.birthDate}
            onChange={(event) => onChange({ ...input, birthDate: event.target.value })}
            required
          />
        </label>
        <label>
          出生时间
          <input
            type="time"
            value={input.birthTime}
            onChange={(event) => onChange({ ...input, birthTime: event.target.value })}
            disabled={input.birthTimePrecision === "unknown"}
            required={input.birthTimePrecision !== "unknown"}
          />
        </label>
      </div>
      <label>
        时间精度
        <select
          value={input.birthTimePrecision}
          onChange={(event) =>
            onChange({
              ...input,
              birthTimePrecision: event.target.value as BirthTimePrecision
            })
          }
        >
          {precisionOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <BirthPlacePicker
        value={input.birthPlace}
        onChange={(birthPlace) => onChange({ ...input, birthPlace })}
      />
      <div className="field-grid">
        <label>
          性别
          <input
            value={input.gender}
            onChange={(event) => onChange({ ...input, gender: event.target.value })}
            placeholder="可留空"
          />
        </label>
        <label>
          感情状态
          <input
            value={input.relationship}
            onChange={(event) => onChange({ ...input, relationship: event.target.value })}
            placeholder="可留空"
          />
        </label>
      </div>
      <label>
        时间来源
        <input
          value={input.timeSource}
          onChange={(event) => onChange({ ...input, timeSource: event.target.value })}
          placeholder="出生证 / 家人记忆 / 大概回忆"
        />
      </label>
    </>
  );
}

function BirthPlacePicker({
  value,
  onChange
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const [level, setLevel] = useState<PlaceSearchLevel>("country");
  const [query, setQuery] = useState("");
  const [country, setCountry] = useState("");
  const [region, setRegion] = useState("");
  const [options, setOptions] = useState<PlaceOption[]>([]);

  useEffect(() => {
    const controller = new AbortController();
    api
      .searchPlaces(
        {
          level,
          q: query,
          country: country || undefined,
          region: region || undefined,
          limit: 30
        },
        controller.signal
      )
      .then((response) => setOptions(response.options))
      .catch(() => setOptions([]));
    return () => controller.abort();
  }, [country, level, query, region]);

  function pick(option: PlaceOption) {
    if (level === "country") {
      setCountry(option.value);
      setRegion("");
      setLevel("region");
      setQuery("");
      return;
    }
    if (level === "region") {
      setRegion(option.value);
      setLevel("city");
      setQuery("");
      return;
    }
    onChange(option.birthPlace ?? option.value);
  }

  return (
    <div className="place-picker">
      <label>
        出生地点
        <div className="place-input">
          <MapPin size={16} />
          <input
            value={value}
            readOnly
            placeholder="请从下方选择城市"
            required
          />
        </div>
      </label>
      <div className="place-controls">
        <select value={level} onChange={(event) => setLevel(event.target.value as PlaceSearchLevel)}>
          <option value="country">国家</option>
          <option value="region">省/州</option>
          <option value="city">城市</option>
        </select>
        <div className="place-search">
          <Search size={15} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索"
          />
        </div>
      </div>
      <div className="place-options">
        {options.slice(0, 6).map((option) => (
          <button key={option.id} type="button" onClick={() => pick(option)}>
            <span>{option.label}</span>
            <small>{option.meta}</small>
          </button>
        ))}
      </div>
    </div>
  );
}

type MarkdownBlock =
  | { type: "heading"; level: number; text: string }
  | { type: "paragraph"; text: string }
  | { type: "quote"; text: string }
  | { type: "list"; items: string[] }
  | { type: "table"; lines: string[] }
  | { type: "code"; text: string };

function MarkdownReport({ content }: { content: string }) {
  const blocks = useMemo(() => parseMarkdown(content), [content]);
  return (
    <div className="markdown-report">
      {blocks.map((block, index) => (
        <MarkdownBlockView key={index} block={block} />
      ))}
    </div>
  );
}

function MarkdownBlockView({ block }: { block: MarkdownBlock }) {
  if (block.type === "heading") {
    const level = Math.min(Math.max(block.level, 2), 4);
    const Tag = `h${level}` as "h2" | "h3" | "h4";
    return <Tag>{renderInline(block.text)}</Tag>;
  }
  if (block.type === "quote") return <blockquote>{renderInline(block.text)}</blockquote>;
  if (block.type === "list") {
    return (
      <ul>
        {block.items.map((item, index) => (
          <li key={index}>{renderInline(item)}</li>
        ))}
      </ul>
    );
  }
  if (block.type === "table") return <pre className="md-table">{block.lines.join("\n")}</pre>;
  if (block.type === "code") return <pre className="md-code">{block.text}</pre>;
  return <p>{renderInline(block.text)}</p>;
}

function parseMarkdown(content: string): MarkdownBlock[] {
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  const blocks: MarkdownBlock[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    const trimmed = line.trim();
    if (!trimmed) {
      index += 1;
      continue;
    }

    if (trimmed.startsWith("```")) {
      index += 1;
      const code: string[] = [];
      while (index < lines.length && !lines[index].trim().startsWith("```")) {
        code.push(lines[index]);
        index += 1;
      }
      index += 1;
      blocks.push({ type: "code", text: code.join("\n") });
      continue;
    }

    const heading = trimmed.match(/^(#{1,4})\s+(.+)$/);
    if (heading) {
      blocks.push({ type: "heading", level: heading[1].length + 1, text: heading[2] });
      index += 1;
      continue;
    }

    if (trimmed.startsWith(">")) {
      const quote: string[] = [];
      while (index < lines.length && lines[index].trim().startsWith(">")) {
        quote.push(lines[index].trim().replace(/^>\s?/, ""));
        index += 1;
      }
      blocks.push({ type: "quote", text: quote.join(" ") });
      continue;
    }

    if (isTableLine(trimmed)) {
      const table: string[] = [];
      while (index < lines.length && isTableLine(lines[index].trim())) {
        table.push(lines[index]);
        index += 1;
      }
      blocks.push({ type: "table", lines: table });
      continue;
    }

    if (/^[-*]\s+/.test(trimmed)) {
      const items: string[] = [];
      while (index < lines.length && /^[-*]\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^[-*]\s+/, ""));
        index += 1;
      }
      blocks.push({ type: "list", items });
      continue;
    }

    const paragraph: string[] = [];
    while (
      index < lines.length &&
      lines[index].trim() &&
      !lines[index].trim().startsWith("```") &&
      !lines[index].trim().startsWith(">") &&
      !lines[index].trim().match(/^(#{1,4})\s+/) &&
      !/^[-*]\s+/.test(lines[index].trim()) &&
      !isTableLine(lines[index].trim())
    ) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    blocks.push({ type: "paragraph", text: paragraph.join(" ") });
  }

  return blocks;
}

function isTableLine(line: string) {
  return line.includes("|") && line.split("|").length >= 3;
}

function renderInline(text: string): ReactNode[] {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).filter(Boolean);
  return parts.map((part, index) => {
    if (part.startsWith("`") && part.endsWith("`")) return <code key={index}>{part.slice(1, -1)}</code>;
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={index}>{part.slice(2, -2)}</strong>;
    return <span key={index}>{part}</span>;
  });
}
