import { FormEvent, useEffect, useMemo, useState } from "react";
import { CalendarDays, Clock3, FileText, MapPin, Play, Search } from "lucide-react";
import { api } from "./api";
import type {
  BirthInput,
  BirthTimePrecision,
  CoreJobResponse,
  PlaceOption,
  PlaceSearchLevel,
  SkillRunInput,
  SkillSessionResponse
} from "../shared/domain";

type LoadingState = "idle" | "session" | "skill" | "coreJob" | "feedback" | "synastry";

type RunMetrics = {
  jobId?: string;
  status?: string;
  calculator?: {
    durationSeconds?: number | null;
  } | null;
  durationSeconds?: number | null;
  waves?: Array<{
    wave: number;
    total: number;
    completed: number;
    failed: number;
    durationSeconds?: number | null;
  }>;
  nodes?: Array<{
    id: string;
    label?: string;
    wave: number;
    status: string;
    durationSeconds?: number | null;
  }>;
};

const precisionOptions: Array<{ value: BirthTimePrecision; label: string }> = [
  { value: "exact", label: "精确到分钟" },
  { value: "approximate", label: "约略时间" },
  { value: "part_of_day", label: "仅知道时段" },
  { value: "unknown", label: "未知出生时间" }
];

const skillActions: Array<{ skill: SkillRunInput["skill"]; label: string; requiresSynastry?: boolean }> =
  [
    { skill: "vedic-reader", label: "vedic-reader 验前事" },
    { skill: "vedic-core", label: "生成完整 core 报告" },
    { skill: "vedic-career", label: "vedic-career 事业" },
    { skill: "vedic-love", label: "vedic-love 感情" },
    { skill: "vedic-rectifier", label: "vedic-rectifier 校时" },
    { skill: "vedic-synastry", label: "vedic-synastry 合盘", requiresSynastry: true }
  ];

const emptyBirthInput: BirthInput = {
  birthDate: "",
  birthTime: "",
  birthPlace: "",
  birthTimePrecision: "exact",
  gender: "[待填]",
  relationship: "[待填]",
  timeSource: "未追问"
};

export function App() {
  const [birthInput, setBirthInput] = useState<BirthInput>(emptyBirthInput);
  const [synastryBirth, setSynastryBirth] = useState<BirthInput>(emptyBirthInput);
  const [synastryLabel, setSynastryLabel] = useState("B");
  const [relationshipType, setRelationshipType] = useState("");
  const [currentStage, setCurrentStage] = useState("");
  const [synastryQuestion, setSynastryQuestion] = useState("");
  const [sessionLookup, setSessionLookup] = useState(
    () => new URLSearchParams(window.location.search).get("sessionId") ?? ""
  );
  const [session, setSession] = useState<SkillSessionResponse | null>(null);
  const [selectedArtifactPath, setSelectedArtifactPath] = useState("structured_data.md");
  const [feedbackMarkdown, setFeedbackMarkdown] = useState("");
  const [skillMessage, setSkillMessage] = useState("");
  const [coreJob, setCoreJob] = useState<CoreJobResponse | null>(null);
  const [loading, setLoading] = useState<LoadingState>("idle");
  const [error, setError] = useState("");
  const coreJobId = coreJob?.jobId;
  const coreJobStatus = coreJob?.status;
  const isCoreJobActive = coreJobStatus === "queued" || coreJobStatus === "running";

  const selectedArtifact = useMemo(() => {
    if (!session) return null;
    return (
      session.artifacts.find((artifact) => artifact.path === selectedArtifactPath) ??
      session.artifacts[0] ??
      null
    );
  }, [selectedArtifactPath, session]);

  const hasSynastryData = useMemo(
    () => Boolean(session?.artifacts.some((artifact) => artifact.path.endsWith("synastry_data.md"))),
    [session?.artifacts]
  );
  const runMetrics = useMemo(() => parseRunMetrics(session), [session]);

  useEffect(() => {
    if (session?.activeArtifact) {
      setSelectedArtifactPath(session.activeArtifact);
    }
  }, [session?.activeArtifact]);

  useEffect(() => {
    const initialSessionId = new URLSearchParams(window.location.search).get("sessionId");
    if (initialSessionId) {
      void loadSessionById(initialSessionId);
    }
  }, []);

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
            setError(caught instanceof Error ? caught.message : "无法刷新 core 报告进度");
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
    setLoading("session");
    try {
      const response = await api.createSkillSession(birthInput);
      setSession(response);
      setCoreJob(null);
      setSelectedArtifactPath(response.activeArtifact ?? "structured_data.md");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "无法生成 structured_data.md");
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
      setSelectedArtifactPath(response.activeArtifact ?? "run_metrics.json");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "无法载入 session");
    } finally {
      setLoading("idle");
    }
  }

  async function submitSynastryBirth(event: FormEvent) {
    event.preventDefault();
    if (!session) return;
    setError("");
    setLoading("synastry");
    try {
      const response = await api.createSynastrySubject({
        sessionId: session.sessionId,
        label: synastryLabel,
        relationshipType,
        currentStage,
        question: synastryQuestion,
        birth: synastryBirth
      });
      setSession(response);
      setSelectedArtifactPath(response.activeArtifact ?? selectedArtifactPath);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "无法生成合盘前置数据");
    } finally {
      setLoading("idle");
    }
  }

  async function runSkill(skill: SkillRunInput["skill"]) {
    if (!session) return;
    setError("");
    if (skill === "vedic-core") {
      setLoading("coreJob");
      try {
        const response = await api.startCoreJob({
          sessionId: session.sessionId,
          skill,
          userMessage: skillMessage
        });
        setCoreJob(response);
        if (response.session) {
          setSession(response.session);
        }
        setSkillMessage("");
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "完整 core 报告启动失败");
      } finally {
        setLoading("idle");
      }
      return;
    }

    setLoading("skill");
    try {
      const response = await api.runSkill({
        sessionId: session.sessionId,
        skill,
        userMessage: skillMessage
      });
      setSession(response);
      setSkillMessage("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : `${skill} 执行失败`);
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
      setError(caught instanceof Error ? caught.message : "反馈写入失败");
    } finally {
      setLoading("idle");
    }
  }

  return (
    <main className="skill-app">
      <section className="control-pane">
        <div className="brand-row">
          <div className="brand-mark">
            <CalendarDays size={20} />
          </div>
          <div>
            <h1>吠陀占星 Skills 工作台</h1>
            <p>calculator → reader → core / career / love / rectifier / synastry</p>
          </div>
        </div>

        <form className="panel" onSubmit={submitBirthData}>
          <h2>A 盘出生信息</h2>
          <BirthFields input={birthInput} onChange={setBirthInput} />
          <button className="primary-button" disabled={loading !== "idle" || isCoreJobActive}>
            <Play size={16} />
            生成 structured_data.md
          </button>
        </form>

        <form className="panel" onSubmit={loadExistingSession}>
          <h2>载入已有结果</h2>
          <label>
            Session ID
            <input
              value={sessionLookup}
              onChange={(event) => setSessionLookup(event.target.value)}
              placeholder="skill_..."
            />
          </label>
          <button type="submit" disabled={loading !== "idle" || isCoreJobActive}>
            载入报告与耗时
          </button>
        </form>

        {session && (
          <section className="panel">
            <h2>原始 skills</h2>
            <textarea
              value={skillMessage}
              onChange={(event) => setSkillMessage(event.target.value)}
              rows={3}
              placeholder="可选：传给当前 skill 的用户消息"
            />
            <div className="action-grid">
              {skillActions.map((action) => (
                <button
                  key={action.skill}
                  type="button"
                  onClick={() => runSkill(action.skill)}
                  disabled={
                    loading !== "idle" ||
                    isCoreJobActive ||
                    Boolean(action.requiresSynastry && !hasSynastryData)
                  }
                >
                  {action.label}
                </button>
              ))}
            </div>
            {coreJob && <CoreJobProgressPanel job={coreJob} />}
            {!coreJob && runMetrics && <RunMetricsPanel metrics={runMetrics} />}
          </section>
        )}

        {session && (
          <form className="panel" onSubmit={submitSynastryBirth}>
            <h2>合盘 B 盘</h2>
            <label>
              B 名称
              <input
                value={synastryLabel}
                onChange={(event) => setSynastryLabel(event.target.value)}
              />
            </label>
            <BirthFields input={synastryBirth} onChange={setSynastryBirth} />
            <div className="field-grid">
              <label>
                关系类型
                <input
                  value={relationshipType}
                  onChange={(event) => setRelationshipType(event.target.value)}
                  placeholder="可留空"
                />
              </label>
              <label>
                当前阶段
                <input
                  value={currentStage}
                  onChange={(event) => setCurrentStage(event.target.value)}
                  placeholder="可留空"
                />
              </label>
            </div>
            <label>
              合盘问题
              <textarea
                value={synastryQuestion}
                onChange={(event) => setSynastryQuestion(event.target.value)}
                rows={3}
                placeholder="可留空"
              />
            </label>
            <button type="submit" disabled={loading !== "idle" || isCoreJobActive}>
              生成 B 盘与 synastry_data.md
            </button>
          </form>
        )}

        {session && (
          <section className="panel">
            <h2>验前事反馈 / 用户补充</h2>
            <textarea
              value={feedbackMarkdown}
              onChange={(event) => setFeedbackMarkdown(event.target.value)}
              rows={5}
              placeholder="逐条写：1 准 / 2 不准 / 3 部分准..."
            />
            <button
              type="button"
              onClick={submitFeedback}
              disabled={loading !== "idle" || isCoreJobActive}
            >
              写入 user_context.md
            </button>
          </section>
        )}

        {error && <div className="error-banner">{error}</div>}
      </section>

      <section className="artifact-pane">
        <div className="status-bar">
          <div>
            <span>Session</span>
            <strong>{session?.sessionId ?? "未创建"}</strong>
          </div>
          <div>
            <span>Stage</span>
            <strong>{session?.stage ?? "idle"}</strong>
          </div>
        </div>

        {session?.chatMessage && (
          <section className="chat-output">
            <h2>聊天框输出</h2>
            <pre>{session.chatMessage}</pre>
          </section>
        )}

        <section className="artifact-workspace">
          <aside className="artifact-list">
            {(session?.artifacts ?? []).map((artifact) => (
              <button
                key={artifact.path}
                className={artifact.path === selectedArtifact?.path ? "selected" : ""}
                onClick={() => setSelectedArtifactPath(artifact.path)}
              >
                <FileText size={15} />
                {artifact.path}
              </button>
            ))}
          </aside>
          <article className="artifact-view">
            {selectedArtifact ? (
              <>
                <header>
                  <h2>{selectedArtifact.path}</h2>
                  <span>{new Date(selectedArtifact.updatedAt).toLocaleString()}</span>
                </header>
                <pre>{selectedArtifact.content}</pre>
              </>
            ) : (
              <div className="empty-state">等待生成 structured_data.md</div>
            )}
          </article>
        </section>
      </section>
    </main>
  );
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

function CoreJobProgressPanel({ job }: { job: CoreJobResponse }) {
  const statusText: Record<CoreJobResponse["status"], string> = {
    queued: "排队中",
    running: "生成中",
    completed: "已完成",
    failed: "失败"
  };
  const nodeStatusText = {
    pending: "等待",
    running: "运行",
    completed: "完成",
    skipped: "已存在",
    failed: "失败"
  } satisfies Record<CoreJobResponse["nodes"][number]["status"], string>;
  const nodesByWave = job.waves.map((wave) => ({
    ...wave,
    nodes: job.nodes.filter((node) => node.wave === wave.wave)
  }));

  return (
    <div className="core-job">
      <div className="core-job-header">
        <div>
          <span>{statusText[job.status]}</span>
          <strong>{job.message}</strong>
        </div>
        <b>{job.progress.percent}%</b>
      </div>
      <div
        className="core-progress-track"
        role="progressbar"
        aria-valuenow={job.progress.percent}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <span style={{ width: `${job.progress.percent}%` }} />
      </div>
      <div className="core-progress-meta">
        <span>
          {job.progress.completed}/{job.progress.total} 步完成
        </span>
        <span>{job.progress.running} 步运行中</span>
      </div>

      <div className="timing-strip">
        <div>
          <Clock3 size={14} />
          <span>总耗时</span>
          <strong>{formatDuration(job.durationSeconds)}</strong>
        </div>
        <div>
          <span>开始</span>
          <strong>{formatTimestamp(job.startedAt)}</strong>
        </div>
        <div>
          <span>结束</span>
          <strong>{formatTimestamp(job.finishedAt)}</strong>
        </div>
      </div>

      <div className="core-wave-list">
        {nodesByWave.map((wave) => (
          <section key={wave.wave} className="core-wave">
            <header>
              <span>Wave {wave.wave}</span>
              <small>
                {wave.completed}/{wave.total} · {formatDuration(wave.durationSeconds)}
              </small>
            </header>
            <div className="core-node-list">
              {wave.nodes.map((node) => (
                <div key={node.id} className={`core-node ${node.status}`}>
                  <span>{node.label}</span>
                  <em>{formatDuration(node.durationSeconds)}</em>
                  <small>{nodeStatusText[node.status]}</small>
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}

function RunMetricsPanel({ metrics }: { metrics: RunMetrics }) {
  const waves = metrics.waves ?? [];
  const slowest = [...(metrics.nodes ?? [])]
    .filter((node) => node.durationSeconds != null)
    .sort((a, b) => (b.durationSeconds ?? 0) - (a.durationSeconds ?? 0))
    .slice(0, 5);

  return (
    <div className="metrics-panel">
      <div className="metrics-title">
        <span>运行耗时</span>
        <strong>{metrics.status ?? "recorded"}</strong>
      </div>
      <div className="timing-strip">
        <div>
          <Clock3 size={14} />
          <span>Calculator</span>
          <strong>{formatDuration(metrics.calculator?.durationSeconds)}</strong>
        </div>
        <div>
          <span>Core</span>
          <strong>{formatDuration(metrics.durationSeconds)}</strong>
        </div>
        <div>
          <span>Job</span>
          <strong>{metrics.jobId ? metrics.jobId.slice(0, 8) : "—"}</strong>
        </div>
      </div>
      <div className="metrics-wave-grid">
        {waves.map((wave) => (
          <div key={wave.wave}>
            <span>Wave {wave.wave}</span>
            <strong>{formatDuration(wave.durationSeconds)}</strong>
            <small>
              {wave.completed}/{wave.total} · failed {wave.failed}
            </small>
          </div>
        ))}
      </div>
      {slowest.length > 0 && (
        <div className="slow-node-list">
          <span>最慢节点</span>
          {slowest.map((node) => (
            <div key={node.id}>
              <strong>{node.id}</strong>
              <small>{formatDuration(node.durationSeconds)}</small>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function formatDuration(seconds?: number | null) {
  if (seconds == null) return "运行中";
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`;
  const minutes = Math.floor(seconds / 60);
  const remaining = Math.round(seconds % 60);
  if (minutes < 60) return `${minutes}m ${remaining}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

function formatTimestamp(value?: string | null) {
  if (!value) return "—";
  return new Date(value).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  });
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
      <label>
        时间来源
        <input
          value={input.timeSource}
          onChange={(event) => onChange({ ...input, timeSource: event.target.value })}
          placeholder="出生证 / 家人记忆 / 大概回忆 / 未追问"
        />
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
          />
        </label>
        <label>
          感情状态
          <input
            value={input.relationship}
            onChange={(event) => onChange({ ...input, relationship: event.target.value })}
          />
        </label>
      </div>
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
          <input value={value} onChange={(event) => onChange(event.target.value)} required />
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
            placeholder="Search"
          />
        </div>
      </div>
      <div className="place-options">
        {options.slice(0, 8).map((option) => (
          <button key={option.id} type="button" onClick={() => pick(option)}>
            <span>{option.label}</span>
            <small>{option.meta}</small>
          </button>
        ))}
      </div>
    </div>
  );
}
