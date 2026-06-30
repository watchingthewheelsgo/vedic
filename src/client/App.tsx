import { FormEvent, useEffect, useMemo, useState } from "react";
import { CalendarDays, FileText, MapPin, Play, Search } from "lucide-react";
import { api } from "./api";
import type {
  BirthInput,
  BirthTimePrecision,
  PlaceOption,
  PlaceSearchLevel,
  SkillRunInput,
  SkillSessionResponse
} from "../shared/domain";

type LoadingState = "idle" | "session" | "skill" | "feedback" | "synastry";

const precisionOptions: Array<{ value: BirthTimePrecision; label: string }> = [
  { value: "exact", label: "精确到分钟" },
  { value: "approximate", label: "约略时间" },
  { value: "part_of_day", label: "仅知道时段" },
  { value: "unknown", label: "未知出生时间" }
];

const skillActions: Array<{ skill: SkillRunInput["skill"]; label: string; requiresSynastry?: boolean }> =
  [
    { skill: "vedic-reader", label: "vedic-reader 验前事" },
    { skill: "vedic-core", label: "vedic-core 完整分析" },
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
  const [session, setSession] = useState<SkillSessionResponse | null>(null);
  const [selectedArtifactPath, setSelectedArtifactPath] = useState("structured_data.md");
  const [feedbackMarkdown, setFeedbackMarkdown] = useState("");
  const [skillMessage, setSkillMessage] = useState("");
  const [loading, setLoading] = useState<LoadingState>("idle");
  const [error, setError] = useState("");

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

  useEffect(() => {
    if (session?.activeArtifact) {
      setSelectedArtifactPath(session.activeArtifact);
    }
  }, [session?.activeArtifact]);

  async function submitBirthData(event: FormEvent) {
    event.preventDefault();
    setError("");
    setLoading("session");
    try {
      const response = await api.createSkillSession(birthInput);
      setSession(response);
      setSelectedArtifactPath(response.activeArtifact ?? "structured_data.md");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "无法生成 structured_data.md");
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
          <button className="primary-button" disabled={loading !== "idle"}>
            <Play size={16} />
            生成 structured_data.md
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
                    loading !== "idle" || Boolean(action.requiresSynastry && !hasSynastryData)
                  }
                >
                  {action.label}
                </button>
              ))}
            </div>
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
            <button type="submit" disabled={loading !== "idle"}>
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
            <button type="button" onClick={submitFeedback} disabled={loading !== "idle"}>
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
