import { SignedIn, SignedOut, SignInButton, SignUpButton, useAuth } from "@clerk/clerk-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ComponentProps, FormEvent, ReactNode } from "react";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  Clock3,
  Download,
  Eye,
  FileText,
  Info,
  ListChecks,
  LoaderCircle,
  RefreshCw,
  Workflow
} from "lucide-react";
import { api } from "../api";
import { AccountCenter } from "../components/AccountCenter";
import { LanguageSwitcher } from "../components/LanguageSwitcher";
import {
  aggregateWorkshopStages,
  PipelineFlow,
  WORKSHOP_STAGES,
  WORKSHOP_STAGE_EDGES,
  type StageDef,
  type StageStatus
} from "../components/PipelineFlow";
import { MarkdownReport } from "../components/MarkdownReport";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "../components/ui/popover";
import { Textarea } from "../components/ui/textarea";
import {
  formatDuration,
  getPipelineData,
  parseRunMetrics,
  type PipelineData,
  type PipelineNode
} from "../lib/pipeline";
import { getReportSections, titleForArtifact } from "../lib/report";
import { cn } from "../lib/cn";
import { useI18n } from "../i18n/provider";
import type {
  BirthInput,
  CoreJobResponse,
  SkillArtifact,
  SkillSessionResponse
} from "../../shared/domain";

type NavState = { name?: string; birth?: BirthInput; concern?: string } | null;

type BirthInfo = {
  date: string;
  time: string;
  place: string;
  latitude: string;
  longitude: string;
  gender: string;
  relationship: string;
  timePrecision: string;
  timeSource: string;
  effectivePrecision: string;
  concern: string;
};

type StageCopy = {
  purpose: string;
  userResult: string;
  userAction: string;
  expected: string;
};

type ValidationAnswer = "accurate" | "partly" | "inaccurate";

type ValidationAnchor = {
  id: string;
  index: number;
  statement: string;
  rationale: string;
};

type ValidationFeedbackSummary = {
  answer: ValidationAnswer | "recorded";
  answerLabel: string;
  note: string;
  anchorText: string;
};

type ResultPreviewSection = {
  id: string;
  title: string;
  body: string;
};

type Translate = (key: string, vars?: Record<string, string | number>) => string;

const STAGE_COPY: Record<string, StageCopy> = {
  src: {
    purpose: "Keeps your birth details fixed for the rest of the reading.",
    userResult: "The reading uses one clear set of date, time, place, and time-confidence details.",
    userAction: "Review the details. If something is wrong, start a fresh reading.",
    expected: "Usually seconds. If the city cannot be found, choose it again from search."
  },
  chart: {
    purpose: "Calculates and saves the chart facts before any LLM interpretation begins.",
    userResult: "You can inspect the exact structured-data sections used by later stages.",
    userAction: "Review the chart facts. First Check uses these facts as its source.",
    expected: "Generated immediately after the birth details are accepted."
  },
  reader: {
    purpose: "Checks a few lived-experience signals before the full reading begins.",
    userResult: "You get 3-5 short checks to mark as accurate, partly accurate, or inaccurate.",
    userAction: "Answer one check at a time. The full reading starts after your replies are saved.",
    expected: "Usually a few minutes while the system prepares your first checks."
  },
  p1: {
    purpose: "Establishes the first portrait of temperament and life orientation.",
    userResult: "The reading starts with your core pattern and the tone of the chart.",
    userAction: "No action required. Wait for this stage to finish.",
    expected: "Starts after your first-check replies are saved."
  },
  yoga: {
    purpose: "Looks for major chart patterns that can color the rest of the reading.",
    userResult: "Strong patterns are carried forward; weak patterns are not overstated.",
    userAction: "No action required.",
    expected: "Runs automatically while other reading sections are prepared."
  },
  p2: {
    purpose: "Reads the nine planetary signals behind most of the guidance.",
    userResult: "Strengths, constraints, and recurring pressures are prepared for synthesis.",
    userAction: "No action required.",
    expected: "Several independent signals can be prepared at the same time."
  },
  d9: {
    purpose: "Uses Navamsha (D9) as a deeper lens on promise and fulfillment.",
    userResult: "The reading can separate visible potential from what tends to mature over time.",
    userAction: "No action required.",
    expected: "Prepared after the main planetary signals are available."
  },
  div: {
    purpose: "Adds supporting context for career, home, authority, and creative direction.",
    userResult: "These supporting lenses add nuance without overwhelming the main reading.",
    userAction: "No action required.",
    expected: "Prepared after the main planetary signals are available."
  },
  house: {
    purpose: "Reviews the major life areas the final reading will synthesize.",
    userResult:
      "Money, work, relationships, health, learning, family, reputation, and inner growth are covered.",
    userAction: "No action required.",
    expected: "Prepared after the deeper and supporting lenses are available."
  },
  dasha: {
    purpose: "Frames current and upcoming life periods for timing guidance.",
    userResult: "The reading can connect present themes to the season you are in.",
    userAction: "No action required.",
    expected: "Prepared once the deeper and supporting lenses are available."
  },
  pari: {
    purpose: "Cross-checks strong links between life areas so the reading stays balanced.",
    userResult: "Confirmed links are included; weaker links are kept in proportion.",
    userAction: "No action required.",
    expected: "Prepared after the life-area review."
  },
  life: {
    purpose: "Turns the chart evidence into readable life-domain guidance.",
    userResult:
      "Identity, wealth, career, relationship, health, education, family, reputation, growth, and strengths are synthesized.",
    userAction: "No action required.",
    expected: "Several life themes can be prepared at the same time."
  },
  appx: {
    purpose: "Finishes the reading and keeps reference notes available at the end.",
    userResult: "The Report tab becomes available with export-ready sections.",
    userAction: "Open the Report tab when this completes.",
    expected: "Final wrap-up."
  },
  bazi_chart: {
    purpose:
      "Calculates the four pillars, ten gods, hidden stems, solar-term boundaries, and luck cycles.",
    userResult: "A structured BaZi chart workspace is saved before any interpretation begins.",
    userAction: "Review the chart facts, then generate the classical report when ready.",
    expected: "Usually seconds."
  },
  bazi_report: {
    purpose: "Turns the chart facts into a classical BaZi report using the repo-local skill.",
    userResult: "The Report tab becomes available with BaZi sections and timing notes.",
    userAction: "Sign in if needed, then generate the report.",
    expected: "Usually several minutes."
  }
};

function localizedStageCopy(stageId: string, t: Translate): StageCopy {
  const fallback = STAGE_COPY[stageId] ?? STAGE_COPY.appx;
  const fieldKeys: Record<keyof StageCopy, string> = {
    purpose: "purpose",
    userResult: "result",
    userAction: "action",
    expected: "expected"
  };
  const fromKey = (field: keyof StageCopy) => {
    const key = `stage.copy.${stageId}.${fieldKeys[field]}`;
    const text = t(key);
    return text === key ? fallback[field] : text;
  };
  return {
    purpose: fromKey("purpose"),
    userResult: fromKey("userResult"),
    userAction: fromKey("userAction"),
    expected: fromKey("expected")
  };
}

const STAGE_ARTIFACT_CANDIDATES: Record<string, string[]> = {
  src: [
    "structured_data.md",
    "structured_data.json",
    "birth_input_context.json",
    "sensitivity_scan.json",
    "run_metrics.json"
  ],
  chart: ["structured_data.md", "birth_input_context.json", "sensitivity_scan.json"],
  reader: ["reader_prevalidation.md", "prevalidation_result.json", "user_context.md"],
  p1: ["p1_overview.md"],
  yoga: [".runtime/p2/yoga.md", "p2a_planets.md"],
  p2: ["p2a_planets.md", "p2b_planets.md", "p2c_planets.md", "p2d_planets.md"],
  d9: ["p3a_d9.md"],
  div: ["p3b_divisional.md"],
  house: ["p4a_houses.md", "p4b_houses.md"],
  dasha: [".runtime/dasha_review.md"],
  pari: [".runtime/houses/parivartana.md", "p4b_houses.md"],
  life: ["p5a_life.md", "p5b_life.md"],
  appx: ["appendix.md", "report_quality_audit.md"],
  bazi_chart: ["bazi_structured_data.md", "bazi_report_context.md", "bazi_structured_data.json"],
  bazi_report: [
    "bazi_life_report.md",
    "bazi_overview.md",
    "bazi_classics_audit.md",
    "bazi_timing_report.md",
    "bazi_data_audit.md",
    "bazi_appendix.md"
  ]
};

const BAZI_WORKSHOP_STAGES: StageDef[] = [
  {
    id: "src",
    label: "Birth Details",
    sub: "intake",
    seed: true,
    match: () => false
  },
  {
    id: "bazi_chart",
    label: "BaZi Chart Facts",
    sub: "four pillars",
    match: (id) => id === "bazi_chart"
  },
  {
    id: "bazi_report",
    label: "Classical Report",
    sub: "three classics",
    match: (id) => id === "bazi_report"
  }
];

const BAZI_WORKSHOP_STAGE_EDGES: Array<[string, string]> = [
  ["src", "bazi_chart"],
  ["bazi_chart", "bazi_report"]
];

const PRECISION_LABELS: Record<string, string> = {
  exact: "Exact minute",
  approximate: "About ±15 minutes",
  part_of_day: "Only known hour",
  unknown: "Unknown",
  精确到分钟: "Exact minute",
  约略时间: "Approximate time",
  仅知道时段: "Only known part of day",
  未知出生时间: "Unknown"
};

const TIME_SOURCE_LABELS: Record<string, string> = {
  "出生证/医院记录": "Birth certificate / hospital record",
  家人明确记忆: "Clear family memory",
  家人大概回忆: "Approximate family memory",
  未追问: "Not asked"
};

const GENDER_LABELS: Record<string, string> = {
  女: "Female",
  男: "Male",
  未提供: "Prefer not to say"
};

const RELATIONSHIP_LABELS: Record<string, string> = {
  单身: "Single",
  恋爱中: "Dating / in a relationship",
  已婚: "Married",
  未提供: "Prefer not to say"
};

const EFFECTIVE_PRECISION_LABELS: Record<string, string> = {
  "±分钟级": "± minute-level",
  按出生时间精度降级解释: "Downgraded by birth-time confidence"
};

const VALIDATION_CHOICES: Array<{
  value: ValidationAnswer;
  labelKey: string;
  storedLabel: string;
  descriptionKey: string;
}> = [
  {
    value: "accurate",
    labelKey: "validation.accurate.label",
    storedLabel: "准",
    descriptionKey: "validation.accurate.description"
  },
  {
    value: "partly",
    labelKey: "validation.partly.label",
    storedLabel: "部分准",
    descriptionKey: "validation.partly.description"
  },
  {
    value: "inaccurate",
    labelKey: "validation.inaccurate.label",
    storedLabel: "不准",
    descriptionKey: "validation.inaccurate.description"
  }
];

function statusBadgeVariant(status: StageStatus): ComponentProps<typeof Badge>["variant"] {
  if (status === "done") return "done";
  if (status === "running" || status === "waiting") return "gold";
  if (status === "failed") return "error";
  return "neutral";
}

const READING_INTERRUPTED_MESSAGE =
  "The reading was interrupted. Completed parts are saved, and resume will continue from the unfinished part.";

const TECHNICAL_ERROR_PATTERN =
  /(structured_data|reader_prevalidation|user_context|run_metrics|\.md|artifact|agent output|traceback|vedic-core|batch|node|pipeline|skill|expected artifact|AGENT_TIMEOUT_MS|JSON)/i;

function userFacingError(caught: unknown, fallback: string) {
  return sanitizeUserMessage(caught instanceof Error ? caught.message : "", fallback);
}

function sanitizeUserMessage(message: string | null | undefined, fallback: string) {
  const trimmed = (message ?? "").trim();
  if (!trimmed || TECHNICAL_ERROR_PATTERN.test(trimmed)) return fallback;
  return trimmed;
}

export function Session() {
  const { id = "" } = useParams();
  const { isLoaded: authLoaded, isSignedIn } = useAuth();
  const navigate = useNavigate();
  const { locale, t } = useI18n();
  const location = useLocation();
  const navState = location.state as NavState;
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get("tab") === "report" ? "report" : "reading";

  const [session, setSession] = useState<SkillSessionResponse | null>(null);
  const [coreJob, setCoreJob] = useState<CoreJobResponse | null>(null);
  const [error, setError] = useState("");
  const [activeSection, setActiveSection] = useState(0);
  const [selectedStageId, setSelectedStageId] = useState("src");
  const [readerRunning, setReaderRunning] = useState(false);
  const [readerStartedAt, setReaderStartedAt] = useState<number | null>(null);
  const [validationFeedback, setValidationFeedback] = useState("");
  const [submittingFeedback, setSubmittingFeedback] = useState(false);
  const [exportingPdf, setExportingPdf] = useState(false);
  const [baziRunning, setBaziRunning] = useState(false);
  const [now, setNow] = useState(Date.now());
  const coreStartedRef = useRef(false);
  const readerStartedRef = useRef(false);
  const baziStartedRef = useRef(false);

  const baziMode = useMemo(() => isBaziSession(session), [session]);
  const reportSections = useMemo(() => getReportSections(session), [session]);
  const runMetrics = useMemo(() => parseRunMetrics(session), [session]);
  const baziPipelineData = useMemo(
    () => getBaziPipelineData(session, baziRunning),
    [baziRunning, session]
  );
  const pipelineData = useMemo(
    () =>
      baziMode
        ? baziPipelineData
        : getPipelineData(coreJob, runMetrics, { session, readerRunning }),
    [baziMode, baziPipelineData, coreJob, runMetrics, session, readerRunning]
  );
  const pipelineStages = baziMode ? BAZI_WORKSHOP_STAGES : WORKSHOP_STAGES;
  const pipelineEdges = baziMode ? BAZI_WORKSHOP_STAGE_EDGES : WORKSHOP_STAGE_EDGES;
  const jobActive = !baziMode && (coreJob?.status === "queued" || coreJob?.status === "running");
  const complete = baziMode
    ? session?.stage === "bazi_complete"
    : session?.stage === "core_complete" || coreJob?.status === "completed";
  const coreInterrupted =
    !baziMode && (coreJob?.status === "failed" || (!coreJob && runMetrics?.status === "failed"));
  const birthInfo = useMemo(() => resolveBirthInfo(navState, session), [navState, session]);
  const readerPrevalidation = findArtifact(session, "reader_prevalidation.md");
  const feedbackArtifact = findArtifact(session, "user_context.md");
  const awaitingValidationFeedback = Boolean(readerPrevalidation && !feedbackArtifact && !complete);

  const setTab = useCallback(
    (next: "reading" | "report") => {
      const params = new URLSearchParams(searchParams);
      params.set("tab", next);
      setSearchParams(params, { replace: true });
    },
    [searchParams, setSearchParams]
  );

  const startCoreReport = useCallback(
    async (options: { resume?: boolean } = {}) => {
      if (!id || (coreStartedRef.current && !options.resume)) return;
      if (!authLoaded) {
        setError("Account status is still loading. Please try again in a moment.");
        return;
      }
      if (!isSignedIn) {
        setError("Sign in or create an account to start the full reading.");
        return;
      }
      coreStartedRef.current = true;
      setError("");
      try {
        const job = await api.startCoreJob({
          sessionId: id,
          skill: "vedic-core",
          userMessage: "",
          locale
        });
        setCoreJob(job);
        if (job.session) setSession(job.session);
      } catch (caught) {
        coreStartedRef.current = false;
        setError(userFacingError(caught, t("session.error.startReading")));
      }
    },
    [authLoaded, id, isSignedIn, locale, t]
  );

  const resumeCoreReport = useCallback(async () => {
    coreStartedRef.current = false;
    setCoreJob(null);
    await startCoreReport({ resume: true });
  }, [startCoreReport]);

  const startReaderValidation = useCallback(async () => {
    if (!id || readerStartedRef.current) return;
    readerStartedRef.current = true;
    setError("");
    setReaderRunning(true);
    setReaderStartedAt(Date.now());
    setSelectedStageId("reader");
    try {
      const response = await api.runSkill({
        sessionId: id,
        skill: "vedic-reader",
        userMessage: "",
        locale
      });
      setSession(response);
    } catch (caught) {
      readerStartedRef.current = false;
      setError(userFacingError(caught, t("session.error.firstCheck")));
    } finally {
      setReaderRunning(false);
    }
  }, [id, locale, t]);

  const startBaziReport = useCallback(async () => {
    if (!id || baziStartedRef.current) return;
    if (!authLoaded) {
      setError("Account status is still loading. Please try again in a moment.");
      return;
    }
    if (!isSignedIn) {
      setError("Sign in or create an account to generate the BaZi classical report.");
      return;
    }
    baziStartedRef.current = true;
    setError("");
    setBaziRunning(true);
    setSelectedStageId("bazi_report");
    try {
      const response = await api.runSkill({
        sessionId: id,
        skill: "bazi-classics-core",
        userMessage: "生成八字经典报告",
        locale
      });
      setSession(response);
      setTab("report");
    } catch (caught) {
      baziStartedRef.current = false;
      setError(userFacingError(caught, "Could not generate the BaZi report. Please try again."));
    } finally {
      setBaziRunning(false);
    }
  }, [authLoaded, id, isSignedIn, locale, setTab]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const loaded = await api.getSkillSession(id);
        if (cancelled) return;
        setSession(loaded);
        if (isBaziSession(loaded)) {
          setSelectedStageId(loaded.stage === "bazi_complete" ? "bazi_report" : "bazi_chart");
          return;
        }
        if (loaded.stage === "core_complete") return;

        const hasFeedback = Boolean(findArtifact(loaded, "user_context.md"));
        const hasReader = Boolean(findArtifact(loaded, "reader_prevalidation.md"));
        if (hasFeedback) {
          void startCoreReport();
        } else if (hasReader) {
          setSelectedStageId("reader");
        } else {
          void startReaderValidation();
        }
      } catch (caught) {
        if (!cancelled) setError(userFacingError(caught, "Could not load this reading."));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id, startCoreReport, startReaderValidation]);

  useEffect(() => {
    if (readerPrevalidation && !feedbackArtifact) setSelectedStageId("reader");
  }, [readerPrevalidation, feedbackArtifact]);

  useEffect(() => {
    if (!readerRunning && !jobActive) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [readerRunning, jobActive]);

  useEffect(() => {
    const jobId = coreJob?.jobId;
    if (!jobId || (coreJob?.status !== "queued" && coreJob?.status !== "running")) return;
    let cancelled = false;
    const timer = window.setInterval(() => {
      api
        .getCoreJob(jobId)
        .then((response) => {
          if (cancelled) return;
          setCoreJob(response);
          if (response.session) setSession(response.session);
          if (response.status === "failed") {
            coreStartedRef.current = false;
            setError(sanitizeUserMessage(response.message, READING_INTERRUPTED_MESSAGE));
          }
        })
        .catch((caught) => {
          if (!cancelled) setError(userFacingError(caught, "Could not refresh reading progress."));
        });
    }, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [coreJob?.jobId, coreJob?.status]);

  function scrollToSection(index: number) {
    setActiveSection(index);
    document
      .getElementById(`section-${index}`)
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function onExport() {
    if (!id || exportingPdf) return;
    setError("");
    setExportingPdf(true);
    try {
      await api.downloadReportPdf(id);
    } catch (caught) {
      setError(userFacingError(caught, "Could not prepare the PDF. Please try again."));
    } finally {
      setExportingPdf(false);
    }
  }

  async function onSubmitFeedback(event: FormEvent) {
    event.preventDefault();
    if (!authLoaded) {
      setError("Account status is still loading. Please try again in a moment.");
      return;
    }
    if (!isSignedIn) {
      setError("Sign in or create an account to save your replies and continue.");
      return;
    }
    const feedback = validationFeedback.trim();
    if (!feedback) {
      setError("Please answer the current check before starting the full reading.");
      return;
    }

    const concern = birthInfo.concern.trim();
    const feedbackMarkdown = concern
      ? `### 初始关心事项\n\n${concern}\n\n### 验前事逐条反馈\n\n${feedback}`
      : feedback;

    setError("");
    setSubmittingFeedback(true);
    try {
      const updated = await api.recordSkillFeedback({
        sessionId: id,
        feedbackMarkdown
      });
      setSession(updated);
      await startCoreReport();
    } catch (caught) {
      setError(userFacingError(caught, "Could not save your replies. Please try again."));
    } finally {
      setSubmittingFeedback(false);
    }
  }

  return (
    <div className="app-shell flex h-screen flex-col overflow-hidden bg-cream-2">
      <div className="app-tabs z-10 flex shrink-0 items-center gap-2 border-b border-gold/25 bg-cream/95 px-5 py-3 backdrop-blur-lg sm:px-8">
        <button className="brand-logo mr-3 border-0 bg-transparent" onClick={() => navigate("/")}>
          Veda<span>Light</span>
        </button>
        <Button
          variant="tab"
          size="sm"
          data-active={tab === "reading"}
          onClick={() => setTab("reading")}
        >
          <Workflow size={14} /> {t("session.tab.reading")}
        </Button>
        <Button
          variant="tab"
          size="sm"
          data-active={tab === "report"}
          onClick={() => setTab("report")}
        >
          <BookOpen size={14} /> {t("session.tab.report")}
        </Button>
        <div className="flex-1" />
        <SessionAuthControls />
      </div>

      {error && (
        <div className="screen-error mx-5 mt-3 shrink-0 rounded-md border border-red/30 bg-red/10 px-4 py-3 text-[13px] text-red sm:mx-8">
          {error}
        </div>
      )}

      {tab === "reading" ? (
        <div className="grid min-h-0 flex-1 grid-cols-1 overflow-y-auto lg:grid-cols-[minmax(480px,0.95fr)_minmax(420px,1fr)] lg:overflow-hidden 2xl:grid-cols-[560px_1fr]">
          <WorkshopDetailPanel
            selectedStageId={selectedStageId}
            stages={pipelineStages}
            baziMode={baziMode}
            session={session}
            pipelineData={pipelineData}
            birthInfo={birthInfo}
            readerRunning={readerRunning}
            readerStartedAt={readerStartedAt}
            now={now}
            validationFeedback={validationFeedback}
            submittingFeedback={submittingFeedback}
            onValidationFeedbackChange={setValidationFeedback}
            onSubmitFeedback={onSubmitFeedback}
            onResumeCoreReport={resumeCoreReport}
            onStartBaziReport={startBaziReport}
            coreInterrupted={coreInterrupted}
            baziRunning={baziRunning}
            authLoaded={authLoaded}
            isSignedIn={Boolean(isSignedIn)}
          />
          <div className="relative min-w-0 bg-night-2 max-lg:min-h-[70vh] lg:min-h-0 lg:overflow-hidden">
            {pipelineData ? (
              <PipelineFlow
                data={pipelineData}
                selectedStageId={selectedStageId}
                onSelectStage={setSelectedStageId}
                stages={pipelineStages}
                edges={pipelineEdges}
              />
            ) : (
              <div className="grid h-full min-h-[420px] place-items-center text-cream/50">
                <div className="text-center">
                  <LoaderCircle className="mx-auto size-7 animate-spin" />
                  <p className="mt-2.5">{t("session.map.loading")}</p>
                </div>
              </div>
            )}
          </div>
        </div>
      ) : complete && reportSections.length > 0 ? (
        <div className="report-doc grid h-[calc(100vh-57px)] grid-cols-1 lg:grid-cols-[1fr_260px]">
          <main className="report-main overflow-y-auto bg-cream px-6 py-9 pb-20 sm:px-11">
            <div className="report-doc-head mb-7 flex flex-wrap items-center justify-between gap-4">
              <h1 className="text-[28px] font-light tracking-normal">
                {baziMode ? "Your BaZi Report" : t("session.report.heading")}
              </h1>
              <Button onClick={() => void onExport()} disabled={exportingPdf}>
                {exportingPdf ? (
                  <LoaderCircle className="size-4 animate-spin" />
                ) : (
                  <Download size={15} />
                )}
                {exportingPdf ? t("session.report.pdfPreparing") : t("session.report.downloadPdf")}
              </Button>
            </div>
            {reportSections.map((artifact, index) => (
              <section
                className="report-section mb-12 scroll-mt-20 border-b border-gold/25 pb-12 last:border-0"
                id={`section-${index}`}
                key={artifact.path}
              >
                <div className="mb-2 text-[10px] uppercase tracking-[3px] text-gold">
                  {t("session.report.section", { number: String(index + 1).padStart(2, "0") })}
                </div>
                <div className="mb-4 text-[22px] font-medium tracking-normal text-ink">
                  {titleForArtifact(artifact, locale)}
                </div>
                <MarkdownReport content={artifact.content} />
              </section>
            ))}
          </main>
          <nav className="report-toc hidden overflow-y-auto border-l border-gold/25 bg-cream-2 px-4 py-6 lg:block">
            <h4 className="mb-3.5 text-[11px] uppercase tracking-[2px] text-muted">
              {t("session.report.contents")}
            </h4>
            {reportSections.map((artifact, index) => (
              <button
                key={artifact.path}
                className={cn(
                  "flex w-full items-baseline gap-2 rounded-md px-2.5 py-2 text-left text-[13px] text-body transition hover:bg-gold/10 hover:text-ink",
                  activeSection === index && "bg-gold text-white hover:bg-gold hover:text-white"
                )}
                onClick={() => scrollToSection(index)}
              >
                <span
                  className={cn(
                    "shrink-0 text-[11px] font-bold text-gold",
                    activeSection === index && "text-white"
                  )}
                >
                  {String(index + 1).padStart(2, "0")}
                </span>
                {titleForArtifact(artifact, locale)}
              </button>
            ))}
          </nav>
        </div>
      ) : (
        <div className="grid min-h-[calc(100vh-57px)] place-items-center px-6 py-10 text-center">
          <div>
            <div className="mx-auto mb-5 size-11 animate-spin rounded-full border-[3px] border-gold/25 border-t-gold" />
            <h2 className="mb-2 text-2xl font-light">
              {baziMode
                ? baziRunning
                  ? "Generating BaZi report"
                  : "BaZi chart facts are ready"
                : coreInterrupted
                  ? t("session.empty.paused")
                  : awaitingValidationFeedback
                    ? t("session.empty.firstCheckReady")
                    : readerRunning
                      ? t("session.empty.preparingCheck")
                      : t("session.empty.preparing")}
            </h2>
            <p className="mx-auto mb-6 max-w-[420px] text-sm text-body">
              {baziMode
                ? "Review the chart workspace in the Reading tab, then generate the classical report when ready."
                : coreInterrupted
                  ? sanitizeUserMessage(coreJob?.message, t("session.interrupted"))
                  : awaitingValidationFeedback
                    ? t("session.empty.answerChecks")
                    : t("session.empty.progress", {
                        progress: pipelineData
                          ? t("session.empty.partsReady", {
                              completed: pipelineData.completed,
                              total: pipelineData.total
                            })
                          : ""
                      })}
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              {baziMode && !complete && (
                <Button
                  disabled={baziRunning || !authLoaded || !isSignedIn}
                  onClick={() => void startBaziReport()}
                >
                  {baziRunning ? (
                    <LoaderCircle className="size-4 animate-spin" />
                  ) : (
                    <BookOpen size={15} />
                  )}
                  {baziRunning ? "Generating..." : "Generate Classical Report"}
                </Button>
              )}
              {coreInterrupted && (
                <Button onClick={() => void resumeCoreReport()}>
                  <RefreshCw size={15} /> {t("session.empty.resume")}
                </Button>
              )}
              <Button
                variant={coreInterrupted ? "outline" : "gold"}
                onClick={() => setTab("reading")}
              >
                <Workflow size={15} /> {t("session.empty.viewProgress")}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function SessionAuthControls() {
  const { t } = useI18n();
  return (
    <div className="flex items-center gap-2">
      <LanguageSwitcher />
      <SignedOut>
        <span className="hidden rounded-full border border-gold/25 bg-gold/10 px-2.5 py-1 text-[11px] font-medium text-gold-dim sm:inline-flex">
          {t("common.trialMode")}
        </span>
        <SignInButton mode="modal">
          <Button variant="ghost" size="sm">
            {t("common.signIn")}
          </Button>
        </SignInButton>
        <SignUpButton mode="modal">
          <Button size="sm">{t("common.createAccount")}</Button>
        </SignUpButton>
      </SignedOut>
      <SignedIn>
        <AccountCenter compact />
      </SignedIn>
    </div>
  );
}

function WorkshopDetailPanel({
  selectedStageId,
  stages,
  baziMode,
  session,
  pipelineData,
  birthInfo,
  readerRunning,
  readerStartedAt,
  now,
  validationFeedback,
  submittingFeedback,
  onValidationFeedbackChange,
  onSubmitFeedback,
  onResumeCoreReport,
  onStartBaziReport,
  coreInterrupted,
  baziRunning,
  authLoaded,
  isSignedIn
}: {
  selectedStageId: string;
  stages: StageDef[];
  baziMode: boolean;
  session: SkillSessionResponse | null;
  pipelineData: PipelineData | null;
  birthInfo: BirthInfo;
  readerRunning: boolean;
  readerStartedAt: number | null;
  now: number;
  validationFeedback: string;
  submittingFeedback: boolean;
  onValidationFeedbackChange: (value: string) => void;
  onSubmitFeedback: (event: FormEvent) => void;
  onResumeCoreReport: () => Promise<void>;
  onStartBaziReport: () => Promise<void>;
  coreInterrupted: boolean;
  baziRunning: boolean;
  authLoaded: boolean;
  isSignedIn: boolean;
}) {
  const { t } = useI18n();
  const stage = stages.find((item) => item.id === selectedStageId) ?? stages[0];
  const stageLabel = stageLabelFor(stage, t);
  const copy = localizedStageCopy(stage.id, t);
  const nodes = pipelineData?.nodes.filter((node) => stage.match(node.id)) ?? [];
  const stageAgg = pipelineData
    ? aggregateWorkshopStages(pipelineData.nodes, stages)[stage.id]
    : null;
  const status = stage.seed ? "done" : (stageAgg?.status ?? "pending");

  return (
    <aside className="relative border-r border-gold/25 bg-cream px-6 py-7 max-lg:border-b max-lg:border-r-0 lg:min-h-0 lg:overflow-y-auto">
      <StageInfoPopover stageLabel={stageLabel} copy={copy} className="absolute right-6 top-7" />
      <div className="mb-2 pr-9 text-[10px] uppercase tracking-[2.4px] text-gold">
        {t("session.detail.eyebrow")}
      </div>
      <div className="mb-5 flex items-start justify-between gap-3 pr-9">
        <h3 className="min-w-0 text-lg font-semibold tracking-normal text-ink">{stageLabel}</h3>
        <Badge variant={statusBadgeVariant(status)}>{t(`status.${status}`)}</Badge>
      </div>

      {stage.id === "src" ? (
        <BirthDetail birthInfo={birthInfo} />
      ) : stage.id === "chart" ? (
        <ChartFactsDetail session={session} status={status} />
      ) : baziMode ? (
        <BaziStageDetail
          stageId={stage.id}
          session={session}
          nodes={nodes}
          status={status}
          baziRunning={baziRunning}
          onStartBaziReport={onStartBaziReport}
          authLoaded={authLoaded}
          isSignedIn={isSignedIn}
        />
      ) : stage.id === "reader" ? (
        <ReaderDetail
          session={session}
          readerRunning={readerRunning}
          readerStartedAt={readerStartedAt}
          now={now}
          validationFeedback={validationFeedback}
          submittingFeedback={submittingFeedback}
          onValidationFeedbackChange={onValidationFeedbackChange}
          onSubmitFeedback={onSubmitFeedback}
          authLoaded={authLoaded}
          isSignedIn={isSignedIn}
        />
      ) : (
        <CoreStageDetail
          stageId={stage.id}
          session={session}
          nodes={nodes}
          status={status}
          onResumeCoreReport={onResumeCoreReport}
          coreInterrupted={coreInterrupted}
        />
      )}
    </aside>
  );
}

function BaziStageDetail({
  stageId,
  session,
  nodes,
  status,
  baziRunning,
  onStartBaziReport,
  authLoaded,
  isSignedIn
}: {
  stageId: string;
  session: SkillSessionResponse | null;
  nodes: PipelineNode[];
  status: StageStatus;
  baziRunning: boolean;
  onStartBaziReport: () => Promise<void>;
  authLoaded: boolean;
  isSignedIn: boolean;
}) {
  const { t } = useI18n();
  const copy = localizedStageCopy(stageId, t);
  const completedNodes = nodes.filter((node) => node.status === "completed");
  const runningNodes = nodes.filter((node) => node.status === "running");
  const artifact = findStageArtifact(session, stageId, nodes);
  const canGenerate = stageId === "bazi_report" && status !== "done";

  return (
    <>
      <StageStatusSummary
        status={status}
        copy={copy}
        completed={completedNodes.length}
        total={nodes.length}
        running={runningNodes.length}
        durationSeconds={completedNodes.reduce((sum, node) => sum + (node.durationSeconds ?? 0), 0)}
        coreInterrupted={false}
      />

      {canGenerate && (
        <div className="my-5 rounded-xl border border-gold/30 bg-gold/10 px-4 py-3">
          <DetailSubtitle>Classical report</DetailSubtitle>
          <p className="m-0 mb-3 text-[13px] leading-[1.7] text-body">
            Generate the BaZi report from the chart facts using the repo-local three-classics skill.
          </p>
          <Button
            className="w-full"
            disabled={baziRunning || !authLoaded || !isSignedIn}
            onClick={() => void onStartBaziReport()}
          >
            {baziRunning ? (
              <>
                <LoaderCircle className="size-4 animate-spin" /> Generating...
              </>
            ) : (
              <>
                <BookOpen size={15} /> Generate Classical Report
              </>
            )}
          </Button>
          {authLoaded && !isSignedIn && (
            <p className="m-0 mt-2 text-[12.5px] leading-relaxed text-muted">
              Sign in from the top-right account controls to run the report generator.
            </p>
          )}
        </div>
      )}

      {artifact ? (
        <ResultPreview artifact={artifact} status={status} />
      ) : (
        <EmptyResultState status={status} copy={copy} progress="" />
      )}
    </>
  );
}

function StageInfoPopover({
  stageLabel,
  copy,
  className
}: {
  stageLabel: string;
  copy?: StageCopy;
  className?: string;
}) {
  const { t } = useI18n();
  if (!copy) return null;

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            "grid size-5 shrink-0 place-items-center rounded-full border border-gold/25 bg-cream-2 text-gold-dim transition hover:border-gold hover:bg-gold/10 hover:text-gold focus:outline-none focus:ring-4 focus:ring-gold/15",
            className
          )}
          aria-label={t("session.guide.aria", { stage: stageLabel })}
        >
          <Info className="size-3" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-[min(92vw,380px)] p-4" align="end" side="bottom">
        <div className="mb-3">
          <div className="mb-1 text-[10px] uppercase tracking-[1.8px] text-gold">
            {t("session.guide.title")}
          </div>
          <h4 className="m-0 text-base font-semibold text-ink">{stageLabel}</h4>
        </div>
        <div className="grid gap-3 text-[13px] leading-[1.65] text-body">
          <StageInfoBlock title={t("session.guide.purpose")}>{copy.purpose}</StageInfoBlock>
          <StageInfoBlock title={t("session.guide.result")}>{copy.userResult}</StageInfoBlock>
          <StageInfoBlock title={t("session.guide.action")}>{copy.userAction}</StageInfoBlock>
          <div className="border-t border-gold/20 pt-3">
            <StageInfoBlock title={t("session.guide.timing")}>{copy.expected}</StageInfoBlock>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}

function StageInfoBlock({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <div className="mb-0.5 text-[10px] uppercase tracking-[1.4px] text-muted">{title}</div>
      <p className="m-0">{children}</p>
    </div>
  );
}

function BirthDetail({ birthInfo }: { birthInfo: BirthInfo }) {
  const { t } = useI18n();
  return (
    <>
      <div className="my-4">
        <InfoRow label={t("session.birth.date")} value={birthInfo.date} />
        <InfoRow label={t("session.birth.time")} value={birthInfo.time} />
        <InfoRow label={t("session.birth.place")} value={birthInfo.place} />
        <InfoRow label={t("session.birth.latitude")} value={birthInfo.latitude} />
        <InfoRow label={t("session.birth.longitude")} value={birthInfo.longitude} />
        <InfoRow label={t("session.birth.precision")} value={birthInfo.timePrecision} />
        <InfoRow label={t("session.birth.source")} value={birthInfo.timeSource} />
        <InfoRow label={t("session.birth.effective")} value={birthInfo.effectivePrecision} />
        {birthInfo.gender && <InfoRow label={t("session.birth.gender")} value={birthInfo.gender} />}
        {birthInfo.relationship && (
          <InfoRow label={t("session.birth.relationship")} value={birthInfo.relationship} />
        )}
      </div>
      {birthInfo.concern && (
        <div className="my-4">
          <DetailSubtitle>{t("session.birth.concern")}</DetailSubtitle>
          <p className="m-0 text-[13px] leading-[1.7] text-body">{birthInfo.concern}</p>
        </div>
      )}
    </>
  );
}

function ChartFactsDetail({
  session,
  status
}: {
  session: SkillSessionResponse | null;
  status: StageStatus;
}) {
  const { t } = useI18n();
  const copy = localizedStageCopy("chart", t);
  const structuredData = findArtifact(session, "structured_data.md");
  const inputContext = findArtifact(session, "birth_input_context.json");
  const sensitivityScan = findArtifact(session, "sensitivity_scan.json");
  const sections = useMemo(
    () => parseChartFactSections(structuredData?.content ?? ""),
    [structuredData?.content]
  );

  return (
    <>
      <StageStatusSummary
        status={status}
        copy={copy}
        completed={structuredData ? 1 : 0}
        total={1}
        running={0}
        durationSeconds={0}
        coreInterrupted={false}
      />

      <section className="my-5 border-t border-gold/25 pt-4">
        <DetailSubtitle>{t("session.chart.sourceFiles")}</DetailSubtitle>
        <div className="flex flex-wrap gap-2">
          {[structuredData?.path, inputContext?.path, sensitivityScan?.path]
            .filter((path): path is string => Boolean(path))
            .map((path) => (
              <span
                className="rounded-full border border-gold/25 bg-cream-2 px-2.5 py-1 text-[11px] font-medium text-muted"
                key={path}
              >
                {path}
              </span>
            ))}
        </div>
      </section>

      {sections.length > 0 ? (
        <section className="my-5 border-t border-gold/25 pt-4">
          <DetailSubtitle>{t("session.chart.sections")}</DetailSubtitle>
          <div className="grid gap-3">
            {sections.map((section, index) => (
              <article
                className="rounded-xl border border-gold/25 bg-cream-2 px-4 py-3"
                key={section.id}
              >
                <div className="mb-1.5 flex items-baseline gap-2">
                  <span className="text-[10px] font-bold uppercase tracking-[1.4px] text-gold">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <h4 className="m-0 text-sm font-semibold leading-snug text-ink">
                    {section.title}
                  </h4>
                </div>
                <p className="m-0 whitespace-pre-wrap text-[12.5px] leading-[1.7] text-body">
                  {excerpt(stripMarkdownForPreview(section.body), 520)}
                </p>
              </article>
            ))}
          </div>
        </section>
      ) : (
        <EmptyResultState status={status} copy={copy} progress="" />
      )}
    </>
  );
}

function ReaderDetail({
  session,
  readerRunning,
  readerStartedAt,
  now,
  validationFeedback,
  submittingFeedback,
  onValidationFeedbackChange,
  onSubmitFeedback,
  authLoaded,
  isSignedIn
}: {
  session: SkillSessionResponse | null;
  readerRunning: boolean;
  readerStartedAt: number | null;
  now: number;
  validationFeedback: string;
  submittingFeedback: boolean;
  onValidationFeedbackChange: (value: string) => void;
  onSubmitFeedback: (event: FormEvent) => void;
  authLoaded: boolean;
  isSignedIn: boolean;
}) {
  const { t } = useI18n();
  const prevalidation = findArtifact(session, "reader_prevalidation.md");
  const feedback = findArtifact(session, "user_context.md");
  const anchors = useMemo(
    () => parseValidationAnchors(prevalidation?.content ?? ""),
    [prevalidation?.content]
  );
  const [activeAnchorIndex, setActiveAnchorIndex] = useState(0);
  const [anchorFeedback, setAnchorFeedback] = useState<
    Record<number, { answer?: ValidationAnswer; note: string }>
  >({});
  const activeAnchor = anchors[activeAnchorIndex];
  const answeredCount = anchors.filter((anchor) => anchorFeedback[anchor.index]?.answer).length;
  const allAnswered = anchors.length > 0 && answeredCount === anchors.length;
  const anonymousLocked = authLoaded && !isSignedIn && anchors.length > 1 && activeAnchorIndex > 0;
  const recordedFeedback = useMemo(
    () => parseRecordedValidationFeedback(feedback?.content ?? ""),
    [feedback?.content]
  );

  useEffect(() => {
    setActiveAnchorIndex(0);
    setAnchorFeedback({});
    onValidationFeedbackChange("");
  }, [prevalidation?.content, onValidationFeedbackChange]);

  useEffect(() => {
    if (activeAnchorIndex >= anchors.length) setActiveAnchorIndex(Math.max(0, anchors.length - 1));
  }, [activeAnchorIndex, anchors.length]);

  function updateAnchorFeedback(
    anchor: ValidationAnchor,
    update: Partial<{ answer: ValidationAnswer; note: string }>
  ) {
    const nextFeedback = {
      ...anchorFeedback,
      [anchor.index]: {
        answer: anchorFeedback[anchor.index]?.answer,
        note: anchorFeedback[anchor.index]?.note ?? "",
        ...update
      }
    };
    setAnchorFeedback(nextFeedback);
    onValidationFeedbackChange(buildValidationFeedbackMarkdown(anchors, nextFeedback));
  }

  function moveNext() {
    if (!activeAnchor) return;
    setActiveAnchorIndex((current) => Math.min(current + 1, anchors.length - 1));
  }

  function movePrev() {
    setActiveAnchorIndex((current) => Math.max(0, current - 1));
  }

  if (!prevalidation) {
    return (
      <>
        <div className="my-4">
          <DetailSubtitle>
            {readerRunning ? t("session.reader.preparingNow") : t("session.reader.notStarted")}
          </DetailSubtitle>
          <p className="m-0 text-[13px] leading-[1.7] text-body">
            {readerRunning
              ? t("session.reader.elapsed", {
                  duration: formatElapsed(readerStartedAt, now)
                })
              : t("stage.copy.reader.expected")}
          </p>
        </div>
      </>
    );
  }

  return (
    <>
      {feedback ? (
        <ReaderCompletedDetail
          anchors={anchors}
          feedback={feedback}
          recordedFeedback={recordedFeedback}
        />
      ) : (
        <form className="mt-4 grid gap-4" onSubmit={onSubmitFeedback}>
          <div className="rounded-xl border border-gold/35 bg-gold/10 px-4 py-3 shadow-[0_12px_30px_rgba(201,169,110,0.10)]">
            <div className="mb-1 flex items-center gap-2 text-[11px] font-bold uppercase tracking-[1.5px] text-gold-dim">
              <CheckCircle2 className="size-4" />
              {t("session.reader.required")}
            </div>
            <p className="m-0 text-[13px] leading-[1.65] text-body">
              {t("session.reader.requiredBody")}
            </p>
          </div>

          {activeAnchor ? (
            <div className="rounded-xl border border-gold/25 bg-cream-2 p-4">
              <div className="mb-3 flex items-center justify-between gap-3">
                <div>
                  <div className="text-[10px] uppercase tracking-[1.8px] text-muted">
                    {t("session.reader.check")}
                  </div>
                  <div className="mt-1 flex items-center gap-2 text-sm font-semibold text-ink">
                    {t("session.reader.questionOf", {
                      current: activeAnchorIndex + 1,
                      total: anchors.length
                    })}
                    {activeAnchor.rationale && (
                      <AnchorRationalePopover
                        label={t("session.reader.why", { number: activeAnchorIndex + 1 })}
                        rationale={activeAnchor.rationale}
                      />
                    )}
                  </div>
                </div>
                <Badge variant="neutral">
                  {t("session.reader.answered", { answered: answeredCount, total: anchors.length })}
                </Badge>
              </div>

              <div className="rounded-lg border border-gold/20 bg-gold/10 px-3.5 py-3 text-[13px] leading-[1.75] text-body">
                {activeAnchor.statement}
              </div>

              {anonymousLocked ? (
                <AnonymousCheckpointGate questionNumber={activeAnchorIndex + 1} />
              ) : (
                <>
                  <div className="mt-4 grid gap-2">
                    {VALIDATION_CHOICES.map((choice) => {
                      const selected = anchorFeedback[activeAnchor.index]?.answer === choice.value;
                      return (
                        <button
                          type="button"
                          key={choice.value}
                          className={cn(
                            "rounded-lg border px-3.5 py-3 text-left transition",
                            selected
                              ? "border-gold bg-gold text-white shadow-sm"
                              : "border-gold/25 bg-cream text-body hover:border-gold/60 hover:bg-gold/10"
                          )}
                          onClick={() =>
                            updateAnchorFeedback(activeAnchor, { answer: choice.value })
                          }
                        >
                          <span className="block text-sm font-semibold">{t(choice.labelKey)}</span>
                          <span
                            className={cn(
                              "mt-0.5 block text-[12.5px]",
                              selected ? "text-white/80" : "text-muted"
                            )}
                          >
                            {t(choice.descriptionKey)}
                          </span>
                        </button>
                      );
                    })}
                  </div>

                  <label className="mt-4 block">
                    <span className="mb-1.5 block text-[11px] uppercase tracking-[1.4px] text-muted">
                      {t("session.reader.optionalNote")}
                    </span>
                    <Textarea
                      rows={4}
                      value={anchorFeedback[activeAnchor.index]?.note ?? ""}
                      onChange={(event) =>
                        updateAnchorFeedback(activeAnchor, { note: event.target.value })
                      }
                      placeholder={t("session.reader.notePlaceholder")}
                    />
                  </label>
                </>
              )}

              <div className="mt-4 flex items-center justify-between gap-3">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={activeAnchorIndex === 0}
                  onClick={movePrev}
                >
                  <ChevronLeft size={14} /> {t("session.reader.previous")}
                </Button>
                {anonymousLocked ? null : activeAnchorIndex < anchors.length - 1 ? (
                  <Button
                    type="button"
                    size="sm"
                    disabled={!anchorFeedback[activeAnchor.index]?.answer}
                    onClick={moveNext}
                  >
                    {t("session.reader.next")} <ChevronRight size={14} />
                  </Button>
                ) : (
                  <Button
                    disabled={
                      submittingFeedback ||
                      !authLoaded ||
                      !isSignedIn ||
                      !allAnswered ||
                      !validationFeedback.trim()
                    }
                  >
                    {submittingFeedback ? t("session.reader.saving") : t("session.reader.save")}
                  </Button>
                )}
              </div>
            </div>
          ) : (
            <div className="rounded-xl border border-gold/25 bg-cream-2 p-4">
              <DetailSubtitle>{t("session.reader.response")}</DetailSubtitle>
              <Textarea
                rows={7}
                value={validationFeedback}
                onChange={(event) => onValidationFeedbackChange(event.target.value)}
                placeholder={t("session.reader.responsePlaceholder")}
              />
              <Button
                className="mt-3 w-full"
                disabled={
                  submittingFeedback || !authLoaded || !isSignedIn || !validationFeedback.trim()
                }
              >
                {submittingFeedback ? t("session.reader.saving") : t("session.reader.save")}
              </Button>
            </div>
          )}
        </form>
      )}
    </>
  );
}

function ReaderCompletedDetail({
  anchors,
  feedback,
  recordedFeedback
}: {
  anchors: ValidationAnchor[];
  feedback: SkillArtifact;
  recordedFeedback: Map<number, ValidationFeedbackSummary>;
}) {
  const { t } = useI18n();
  const structuredCount = recordedFeedback.size;

  return (
    <div className="mt-4 grid gap-4">
      <div className="rounded-xl border border-gold/35 bg-gold/10 px-4 py-3 shadow-[0_12px_30px_rgba(201,169,110,0.10)]">
        <div className="mb-1 flex items-center gap-2 text-[11px] font-bold uppercase tracking-[1.5px] text-gold-dim">
          <CheckCircle2 className="size-4" />
          {t("session.reader.complete")}
        </div>
        <p className="m-0 text-[13px] leading-[1.65] text-body">
          {t("session.reader.completeBody")}
        </p>
      </div>

      {structuredCount === 0 && (
        <div className="rounded-xl border border-gold/25 bg-cream-2 px-4 py-3 text-[13px] leading-[1.65] text-body">
          {t("session.reader.generalSaved")}
        </div>
      )}

      {anchors.length > 0 ? (
        <div className="grid gap-3">
          {anchors.map((anchor, anchorIndex) => {
            const summary = recordedFeedback.get(anchor.index);
            return (
              <div className="rounded-xl border border-gold/25 bg-cream-2 p-4" key={anchor.id}>
                <div className="mb-3 flex items-start justify-between gap-3">
                  <div>
                    <div className="text-[10px] uppercase tracking-[1.8px] text-muted">
                      {t("session.reader.check")}
                    </div>
                    <div className="mt-1 flex items-center gap-2 text-sm font-semibold text-ink">
                      {t("session.reader.questionOf", {
                        current: anchorIndex + 1,
                        total: anchors.length
                      })}
                      {anchor.rationale && (
                        <AnchorRationalePopover
                          label={t("session.reader.why", { number: anchorIndex + 1 })}
                          rationale={anchor.rationale}
                        />
                      )}
                    </div>
                  </div>
                  <Badge variant={feedbackBadgeVariant(summary?.answer)}>
                    {summary?.answerLabel ?? "Recorded"}
                  </Badge>
                </div>

                <div className="rounded-lg border border-gold/20 bg-gold/10 px-3.5 py-3 text-[13px] leading-[1.75] text-body">
                  {anchor.statement}
                </div>

                {summary?.note && (
                  <div className="mt-3 rounded-lg border border-gold/20 bg-cream/80 px-3.5 py-3">
                    <div className="mb-1 text-[10px] uppercase tracking-[1.4px] text-muted">
                      {t("session.reader.yourNote")}
                    </div>
                    <p className="m-0 text-[13px] leading-[1.65] text-body">{summary.note}</p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="rounded-xl border border-gold/25 bg-cream-2 p-4">
          <DetailSubtitle>{t("session.reader.savedReplies")}</DetailSubtitle>
          <p className="m-0 text-[13px] leading-[1.65] text-body">
            {excerpt(feedback.content, 420)}
          </p>
        </div>
      )}
    </div>
  );
}

function AnonymousCheckpointGate({ questionNumber }: { questionNumber: number }) {
  const { t } = useI18n();
  return (
    <div className="mt-4 rounded-xl border border-gold/35 bg-cream px-4 py-4 shadow-[0_18px_42px_rgba(44,31,15,0.08)]">
      <div className="mb-1 text-[10px] font-bold uppercase tracking-[1.8px] text-gold">
        {t("session.reader.accountCheckpoint")}
      </div>
      <h4 className="m-0 text-base font-semibold tracking-normal text-ink">
        {t("session.reader.signInQuestion", { number: questionNumber })}
      </h4>
      <p className="mb-4 mt-2 text-[13px] leading-[1.7] text-body">
        {t("session.reader.signInBody")}
      </p>
      <div className="flex flex-wrap gap-2">
        <SignUpButton mode="modal">
          <Button>{t("common.createAccount")}</Button>
        </SignUpButton>
        <SignInButton mode="modal">
          <Button variant="outline">{t("common.signIn")}</Button>
        </SignInButton>
      </div>
    </div>
  );
}

function feedbackBadgeVariant(
  answer: ValidationFeedbackSummary["answer"] | undefined
): ComponentProps<typeof Badge>["variant"] {
  if (answer === "accurate") return "done";
  if (answer === "partly") return "gold";
  if (answer === "inaccurate") return "error";
  return "neutral";
}

function AnchorRationalePopover({ label, rationale }: { label: string; rationale: string }) {
  const { t } = useI18n();
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="grid size-5 shrink-0 place-items-center rounded-full border border-gold/25 bg-cream-2 text-gold-dim transition hover:border-gold hover:bg-gold/10 hover:text-gold focus:outline-none focus:ring-4 focus:ring-gold/15"
          aria-label={label}
        >
          <CircleHelp className="size-3" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-[min(92vw,360px)] p-4" align="start" side="bottom">
        <div className="mb-2 text-[10px] uppercase tracking-[1.6px] text-gold">
          {t("session.reader.rationaleTitle")}
        </div>
        <p className="m-0 whitespace-pre-wrap text-[13px] leading-[1.7] text-body">{rationale}</p>
      </PopoverContent>
    </Popover>
  );
}

function CoreStageDetail({
  stageId,
  session,
  nodes,
  status,
  onResumeCoreReport,
  coreInterrupted
}: {
  stageId: string;
  session: SkillSessionResponse | null;
  nodes: PipelineNode[];
  status: StageStatus;
  onResumeCoreReport: () => Promise<void>;
  coreInterrupted: boolean;
}) {
  const { t } = useI18n();
  const copy = localizedStageCopy(stageId, t);
  const runningNodes = nodes.filter((node) => node.status === "running");
  const completedNodes = nodes.filter(
    (node) => node.status === "completed" || node.status === "skipped"
  );
  const failedNodes = nodes.filter((node) => node.status === "failed");
  const stageDuration = completedNodes.reduce((sum, node) => sum + (node.durationSeconds ?? 0), 0);
  const artifact = findStageArtifact(session, stageId, nodes);
  const progress = nodes.length > 0 ? `${completedNodes.length}/${nodes.length}` : "";

  return (
    <>
      <StageStatusSummary
        status={status}
        copy={copy}
        completed={completedNodes.length}
        total={nodes.length}
        running={runningNodes.length}
        durationSeconds={stageDuration}
        coreInterrupted={coreInterrupted}
      />

      {failedNodes.length > 0 && (
        <div className="my-5 rounded-xl border border-red/30 bg-red/10 px-4 py-3">
          <div className="mb-2.5 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-[12px] font-semibold text-red">
              <AlertTriangle className="size-4" />
              {t("stage.summary.paused.title")}
            </div>
            {coreInterrupted && (
              <Button size="sm" onClick={() => void onResumeCoreReport()}>
                <RefreshCw size={13} /> {t("session.empty.resume")}
              </Button>
            )}
          </div>
          {coreInterrupted && (
            <p className="m-0 mb-3 text-[13px] leading-[1.7] text-body">
              {t("stage.failed.saved")}
            </p>
          )}
          <div className="grid gap-2 border-t border-red/20 pt-3">
            {failedNodes.map((node, index) => (
              <div className="text-[12.5px] leading-[1.6]" key={node.id}>
                <div className="font-semibold text-ink">
                  {t("stage.failed.part", { number: index + 1 })}
                </div>
                <div className="mt-0.5 break-words text-red">
                  {sanitizeUserMessage(node.error, t("stage.failed.fallback"))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {artifact ? (
        <ResultPreview artifact={artifact} status={status} />
      ) : (
        <EmptyResultState status={status} copy={copy} progress={progress} />
      )}
    </>
  );
}

function StageStatusSummary({
  status,
  copy,
  completed,
  total,
  running,
  durationSeconds,
  coreInterrupted
}: {
  status: StageStatus;
  copy: StageCopy;
  completed: number;
  total: number;
  running: number;
  durationSeconds: number;
  coreInterrupted: boolean;
}) {
  const { t } = useI18n();
  const Icon =
    status === "failed"
      ? AlertTriangle
      : status === "running"
        ? Clock3
        : status === "done"
          ? CheckCircle2
          : ListChecks;
  const summary = stageStatusSummary(status, copy, coreInterrupted, t);

  return (
    <section className="my-4 border-y border-gold/25 py-4">
      <div className="flex items-start gap-3">
        <div
          className={cn(
            "grid size-9 shrink-0 place-items-center rounded-full border",
            status === "failed"
              ? "border-red/30 bg-red/10 text-red"
              : status === "done"
                ? "border-gold/35 bg-gold/15 text-gold-dim"
                : "border-gold/25 bg-cream-2 text-gold-dim"
          )}
        >
          <Icon className="size-4" />
        </div>
        <div className="min-w-0">
          <div className="text-sm font-semibold text-ink">{summary.title}</div>
          <p className="m-0 mt-1 text-[13px] leading-[1.7] text-body">{summary.body}</p>
          <div className="mt-3 flex flex-wrap gap-2 text-[11px] uppercase tracking-[1.1px] text-muted">
            {total > 0 && (
              <span className="rounded-full border border-gold/25 bg-cream-2 px-2.5 py-1">
                {t("stage.partsReady", { completed, total })}
              </span>
            )}
            {running > 0 && status === "running" && (
              <span className="rounded-full border border-gold/25 bg-gold/10 px-2.5 py-1">
                {t("stage.active", { count: running })}
              </span>
            )}
            {durationSeconds > 0 && (
              <span className="rounded-full border border-gold/25 bg-cream-2 px-2.5 py-1">
                {t("stage.savedDuration", { duration: formatDuration(durationSeconds) })}
              </span>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

function stageStatusSummary(
  status: StageStatus,
  copy: StageCopy,
  coreInterrupted: boolean,
  t: Translate
) {
  if (status === "failed") {
    return {
      title: t("stage.summary.paused.title"),
      body: coreInterrupted
        ? t("stage.summary.paused.body")
        : t("stage.summary.paused.bodyAttention")
    };
  }
  if (status === "done") {
    return {
      title: t("stage.summary.done.title"),
      body: t("stage.summary.done.body")
    };
  }
  if (status === "running") {
    return {
      title: t("stage.summary.running.title"),
      body: t("stage.summary.running.body")
    };
  }
  if (status === "waiting") {
    return {
      title: t("stage.summary.waiting.title"),
      body: copy.userAction
    };
  }
  return {
    title: t("stage.summary.pending.title"),
    body: t("stage.summary.pending.body")
  };
}

function EmptyResultState({
  status,
  copy,
  progress
}: {
  status: StageStatus;
  copy: StageCopy;
  progress: string;
}) {
  const { t } = useI18n();
  if (status === "done") return null;
  return (
    <section className="my-5 border-t border-gold/25 pt-4">
      <DetailSubtitle>
        {status === "running" ? t("stage.preview") : t("stage.comingNext")}
      </DetailSubtitle>
      <p className="m-0 text-[13px] leading-[1.7] text-body">
        {status === "running"
          ? t("stage.previewWaiting", {
              progress: progress
                ? ` (${t("stage.partsReady", { completed: progress.split("/")[0], total: progress.split("/")[1] })})`
                : ""
            })
          : copy.userResult}
      </p>
    </section>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3 border-b border-gold/25 py-2.5 text-sm">
      <span className="text-muted">{label}</span>
      <span className="text-right font-medium text-ink">{value || "—"}</span>
    </div>
  );
}

function ResultPreview({ artifact, status }: { artifact: SkillArtifact; status: StageStatus }) {
  const { locale, t } = useI18n();
  const [expanded, setExpanded] = useState(false);
  const displayContent = useMemo(
    () => sanitizeResultContentForDisplay(artifact.content),
    [artifact.content]
  );
  const sections = useMemo(() => parseResultPreviewSections(displayContent), [displayContent]);
  const visibleSections = expanded ? sections : sections.slice(0, 3);
  const canExpand = sections.length > 0;
  const label = status === "done" ? t("stage.result.previewReady") : t("stage.result.previewSaved");

  return (
    <section className="my-5 border-t border-gold/25 pt-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-2.5">
          <div className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full border border-gold/25 bg-gold/10 text-gold-dim">
            <FileText className="size-3.5" />
          </div>
          <div className="min-w-0">
            <DetailSubtitle className="mb-1">{label}</DetailSubtitle>
            <div className="text-sm font-semibold text-ink">
              {titleForArtifact(artifact, locale)}
            </div>
          </div>
        </div>
        {canExpand && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setExpanded((value) => !value)}
          >
            <Eye size={13} /> {expanded ? t("stage.result.showLess") : t("stage.result.showFull")}
          </Button>
        )}
      </div>

      {expanded ? (
        <div className="mt-4 max-h-[72vh] overflow-auto rounded-lg border border-gold/25 bg-cream-2 px-3.5 py-3">
          <MarkdownReport content={displayContent} />
        </div>
      ) : (
        <div className="mt-4 divide-y divide-gold/20 border-y border-gold/20">
          {visibleSections.map((section, index) => (
            <article className="py-3 first:pt-0 last:pb-0" key={section.id}>
              <div className="mb-1 flex items-baseline gap-2">
                <span className="text-[10px] font-bold uppercase tracking-[1.4px] text-gold">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <h4 className="m-0 text-sm font-semibold leading-snug text-ink">{section.title}</h4>
              </div>
              <p className="m-0 text-[13px] leading-[1.75] text-body">
                {excerpt(stripMarkdownForPreview(section.body), 360)}
              </p>
            </article>
          ))}
          {sections.length > visibleSections.length && (
            <div className="py-3 text-[12.5px] text-muted">
              {t("stage.result.more", { count: sections.length - visibleSections.length })}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function DetailSubtitle({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("mb-2 text-[11px] uppercase tracking-[1.4px] text-muted", className)}>
      {children}
    </div>
  );
}

function findStageArtifact(
  session: SkillSessionResponse | null,
  stageId: string,
  nodes: PipelineNode[]
): SkillArtifact | null {
  const candidates = [
    ...(STAGE_ARTIFACT_CANDIDATES[stageId] ?? []),
    ...nodes.flatMap((node) => node.files)
  ];
  for (const path of candidates) {
    const artifact = findArtifact(session, path);
    if (artifact) return artifact;
  }
  return null;
}

function findArtifact(session: SkillSessionResponse | null, path: string): SkillArtifact | null {
  return session?.artifacts.find((artifact) => artifact.path === path) ?? null;
}

function isBaziSession(session: SkillSessionResponse | null) {
  return Boolean(
    session?.stage.startsWith("bazi_") ||
    session?.artifacts.some((artifact) => artifact.path.startsWith("bazi_"))
  );
}

function getBaziPipelineData(
  session: SkillSessionResponse | null,
  running: boolean
): PipelineData | null {
  if (!session || !isBaziSession(session)) return null;
  const hasChart = Boolean(findArtifact(session, "bazi_structured_data.md"));
  const hasReport = Boolean(findArtifact(session, "bazi_life_report.md"));
  const chartStatus = hasChart ? "completed" : "pending";
  const reportStatus = hasReport
    ? "completed"
    : running
      ? "running"
      : hasChart
        ? "waiting"
        : "pending";
  const nodes: PipelineNode[] = [
    {
      id: "bazi_chart",
      label: "BaZi Chart Facts",
      wave: 0,
      status: chartStatus,
      files: ["bazi_structured_data.md", "bazi_structured_data.json", "bazi_report_context.md"],
      dependencies: [],
      finishedAt: findArtifact(session, "bazi_structured_data.md")?.updatedAt ?? null,
      durationSeconds: null,
      error: null
    },
    {
      id: "bazi_report",
      label: "Classical BaZi Report",
      wave: 1,
      status: reportStatus,
      files: [
        "bazi_data_audit.md",
        "bazi_overview.md",
        "bazi_classics_audit.md",
        "bazi_timing_report.md",
        "bazi_life_report.md",
        "bazi_appendix.md"
      ],
      dependencies: ["bazi_chart"],
      finishedAt: findArtifact(session, "bazi_life_report.md")?.updatedAt ?? null,
      durationSeconds: null,
      error: null
    }
  ];
  const completed = nodes.filter((node) => node.status === "completed").length;
  return {
    nodes,
    status: hasReport ? "completed" : running ? "running" : "waiting",
    percent: Math.round((completed / nodes.length) * 100),
    completed,
    total: nodes.length,
    failed: 0,
    durationSeconds: null
  };
}

function stageLabelFor(stage: StageDef, t: Translate) {
  const key = `stage.${stage.id}.label`;
  const text = t(key);
  return text === key ? stage.label : text;
}

function sanitizeResultContentForDisplay(content: string) {
  return content
    .replace(/\r\n/g, "\n")
    .split("\n")
    .filter((line) => !isPreviewMetaLine(line))
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function parseResultPreviewSections(content: string): ResultPreviewSection[] {
  const normalized = content.replace(/\r\n/g, "\n").trim();
  if (!normalized) return [];

  const lines = normalized.split("\n");
  const sections: ResultPreviewSection[] = [];
  let currentTitle = "";
  let currentBody: string[] = [];

  function flush() {
    const body = cleanResultPreviewBody(currentBody.join("\n"));
    if (!currentTitle && !body) return;
    sections.push({
      id: `result-section-${sections.length + 1}`,
      title: cleanMarkdownInline(currentTitle || "Overview"),
      body: body || currentTitle
    });
  }

  for (const line of lines) {
    const heading = line.trim().match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      flush();
      currentTitle = heading[2].trim();
      currentBody = [];
      continue;
    }
    currentBody.push(line);
  }
  flush();

  if (sections.length === 0) {
    return [
      { id: "result-section-1", title: "Overview", body: cleanResultPreviewBody(normalized) }
    ];
  }
  const readable = sections.filter((section) => stripMarkdownForPreview(section.body).length > 24);
  return (readable.length > 0 ? readable : sections).slice(0, 24);
}

function parseChartFactSections(content: string): ResultPreviewSection[] {
  const normalized = content.replace(/\r\n/g, "\n").trim();
  if (!normalized) return [];

  const lines = normalized.split("\n");
  const sections: ResultPreviewSection[] = [];
  let currentTitle = "";
  let currentBody: string[] = [];

  function flush() {
    const body = cleanResultPreviewBody(currentBody.join("\n"));
    if (!currentTitle && !body) return;
    sections.push({
      id: `chart-section-${sections.length + 1}`,
      title: cleanMarkdownInline(currentTitle || "Overview"),
      body: body || currentTitle
    });
  }

  for (const line of lines) {
    const heading = line.trim().match(/^##\s+(.+)$/);
    if (heading) {
      flush();
      currentTitle = heading[1].trim();
      currentBody = [];
      continue;
    }
    currentBody.push(line);
  }
  flush();

  return sections.filter((section) => stripMarkdownForPreview(section.body).length > 8);
}

function cleanResultPreviewBody(content: string) {
  return content
    .split("\n")
    .filter((line) => !isPreviewMetaLine(line))
    .join("\n")
    .trim();
}

function isPreviewMetaLine(line: string) {
  const normalized = line.trim().replace(/^>\s*/, "").replace(/\*\*/g, "").replace(/`/g, "");
  if (!normalized || /^---+$/.test(normalized)) return true;
  if (normalized.includes(".runtime/") || normalized.includes("内部shard")) return true;
  if (/^\*.*(数据源|本文件为|交付批次).*\*$/.test(normalized)) return true;
  return /^(交付批次|执行日期|数据锚点|合成框架|规则|分析范围|出生时间精度|扫描范围|数据来源|扫描时点|参与星状态)/.test(
    normalized
  );
}

function stripMarkdownForPreview(content: string) {
  return content
    .replace(/^---+$/gm, "")
    .replace(/^>\s?/gm, "")
    .replace(/^\s*[-*]\s+/gm, "")
    .replace(/\|[-:\s|]+\|/g, "")
    .replace(/\*\*/g, "")
    .replace(/`/g, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function excerpt(content: string, max = 1600) {
  const normalized = content.trim();
  if (normalized.length <= max) return normalized;
  return `${normalized.slice(0, max).trimEnd()}\n\n...`;
}

function parseValidationAnchors(content: string): ValidationAnchor[] {
  const normalized = content.trim();
  if (!normalized) return [];

  const markerPattern = /(?:^|\n)\s*(?:\*\*)?(\d+)[.、]\s*(?:\*\*)?\s*/g;
  const markers = Array.from(normalized.matchAll(markerPattern));
  if (markers.length === 0) {
    return [
      {
        id: "anchor-1",
        index: 1,
        statement: stripValidationInstruction(normalized),
        rationale: ""
      }
    ];
  }

  return markers
    .map((marker, markerIndex) => {
      const index = Number(marker[1]);
      const start = (marker.index ?? 0) + marker[0].length;
      const next = markers[markerIndex + 1];
      const end = next?.index ?? normalized.length;
      const block = stripValidationInstruction(normalized.slice(start, end)).trim();
      const lines = block.split("\n");
      const statementLines: string[] = [];
      const rationaleLines: string[] = [];
      let inRationale = false;

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) {
          if (inRationale) rationaleLines.push("");
          continue;
        }
        if (trimmed.startsWith(">")) {
          inRationale = true;
          rationaleLines.push(
            trimmed.replace(/^>\s*/, "").replace(/^(推导|Derivation|根拠)[:：]\s*/i, "")
          );
          continue;
        }
        if (inRationale) rationaleLines.push(trimmed);
        else statementLines.push(trimmed);
      }

      return {
        id: `anchor-${index || markerIndex + 1}`,
        index: index || markerIndex + 1,
        statement: cleanMarkdownInline(statementLines.join("\n")),
        rationale: cleanMarkdownInline(rationaleLines.join("\n").trim())
      };
    })
    .filter((anchor) => anchor.statement);
}

function stripValidationInstruction(content: string) {
  return content
    .replace(/请逐条回复[:：]?[\s\S]*$/m, "")
    .replace(/Reply to each anchor[:：]?[\s\S]*$/im, "")
    .replace(/各項目に返信してください[:：]?[\s\S]*$/m, "")
    .trim();
}

function cleanMarkdownInline(content: string) {
  return content
    .replace(/\*\*/g, "")
    .replace(/`/g, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function buildValidationFeedbackMarkdown(
  anchors: ValidationAnchor[],
  feedback: Record<number, { answer?: ValidationAnswer; note: string }>
) {
  const answered = anchors.filter((anchor) => feedback[anchor.index]?.answer);
  if (answered.length === 0) return "";

  const lines = ["### Pre-reading validation feedback", ""];
  for (const anchor of answered) {
    const entry = feedback[anchor.index];
    const choice = VALIDATION_CHOICES.find((item) => item.value === entry?.answer);
    lines.push(`#### Anchor ${anchor.index}`);
    lines.push(
      `- User answer: ${choice?.storedLabel ?? entry?.answer ?? ""} (${choice?.value ?? ""})`
    );
    if (entry?.note.trim()) lines.push(`- User note: ${entry.note.trim()}`);
    lines.push(`- Anchor text: ${anchor.statement}`);
    lines.push("");
  }
  return lines.join("\n").trim();
}

function parseRecordedValidationFeedback(content: string): Map<number, ValidationFeedbackSummary> {
  const result = new Map<number, ValidationFeedbackSummary>();
  if (!content.trim()) return result;

  const anchorPattern = /####\s+Anchor\s+(\d+)\s*\n([\s\S]*?)(?=\n####\s+Anchor\s+\d+\s*\n|$)/g;
  for (const match of content.matchAll(anchorPattern)) {
    const index = Number(match[1]);
    const block = match[2] ?? "";
    const answerRaw = block.match(/^- User answer:\s*(.+)$/m)?.[1]?.trim() ?? "";
    const note = block.match(/^- User note:\s*([\s\S]*?)(?=\n- User |\n$|$)/m)?.[1]?.trim() ?? "";
    const anchorText =
      block.match(/^- Anchor text:\s*([\s\S]*?)(?=\n- User |\n$|$)/m)?.[1]?.trim() ?? "";
    const normalized = normalizeRecordedAnswer(answerRaw);
    if (index > 0) {
      result.set(index, {
        answer: normalized.answer,
        answerLabel: normalized.label,
        note,
        anchorText
      });
    }
  }

  return result;
}

function normalizeRecordedAnswer(raw: string): {
  answer: ValidationAnswer | "recorded";
  label: string;
} {
  if (/Not accurate|不准/i.test(raw)) return { answer: "inaccurate", label: "Not accurate" };
  if (/Partly|部分/i.test(raw)) return { answer: "partly", label: "Partly" };
  if (/Accurate|准/i.test(raw)) return { answer: "accurate", label: "Accurate" };
  return { answer: "recorded", label: raw || "Recorded" };
}

function formatElapsed(startedAt: number | null, now: number) {
  if (!startedAt) return "—";
  return formatDuration(Math.max(0, (now - startedAt) / 1000));
}

function resolveBirthInfo(navState: NavState, session: SkillSessionResponse | null): BirthInfo {
  const coordinates = resolveBirthCoordinates(session, navState?.birth?.birthPlace);
  if (navState?.birth) {
    return {
      date: navState.birth.birthDate,
      time: navState.birth.birthTime || "Unknown birth time",
      place: navState.birth.birthPlace,
      latitude: coordinates.latitude,
      longitude: coordinates.longitude,
      gender: displayCollected(GENDER_LABELS[navState.birth.gender] ?? navState.birth.gender),
      relationship: displayCollected(
        RELATIONSHIP_LABELS[navState.birth.relationship] ?? navState.birth.relationship
      ),
      timePrecision: displayMappedValue(navState.birth.birthTimePrecision, PRECISION_LABELS),
      timeSource: displayMappedValue(navState.birth.timeSource || "未追问", TIME_SOURCE_LABELS),
      effectivePrecision:
        navState.birth.birthTimePrecision === "exact" &&
        navState.birth.timeSource === "出生证/医院记录"
          ? "± minute-level"
          : "Adjusted by time confidence",
      concern: navState.concern?.trim() ?? ""
    };
  }

  const bazi = session?.artifacts.find((a) => a.path === "bazi_structured_data.md")?.content ?? "";
  if (bazi) {
    const grabBazi = (label: string) =>
      bazi.match(new RegExp(`- ${label}:\\s*(.+)`))?.[1]?.trim() ?? "—";
    const birth = grabBazi("Birth");
    const birthMatch = birth.match(/^(\d{4}-\d{2}-\d{2})\s+([^ ]+)/);
    const context =
      session?.artifacts.find((a) => a.path === "bazi_report_context.md")?.content ?? "";
    const topic = context.match(/- Topic priority:\s*(.+)/)?.[1]?.trim() ?? "";
    return {
      date: birthMatch?.[1] ?? birth,
      time: birthMatch?.[2] ?? "—",
      place: grabBazi("Place"),
      latitude: coordinates.latitude,
      longitude: coordinates.longitude,
      gender: displayCollected(grabBazi("Gender")),
      relationship: displayCollected(context.match(/- Relationship:\s*(.+)/)?.[1]?.trim()),
      timePrecision: displayMappedValue(grabBazi("Time precision"), PRECISION_LABELS),
      timeSource: "BaZi workshop",
      effectivePrecision: grabBazi("Solar time applied"),
      concern: topic === "[not provided]" ? "" : topic
    };
  }

  const sd = session?.artifacts.find((a) => a.path === "structured_data.md")?.content ?? "";
  const grab = (label: string) => sd.match(new RegExp(`${label}:\\s*(.+)`))?.[1]?.trim() ?? "—";
  const feedback = session?.artifacts.find((a) => a.path === "user_context.md")?.content ?? "";
  return {
    date: grab("出生日期"),
    time: grab("出生时间"),
    place: grab("出生地点"),
    latitude: coordinates.latitude,
    longitude: coordinates.longitude,
    gender: displayCollected(displayMappedValue(grab("性别"), GENDER_LABELS)),
    relationship: displayCollected(displayMappedValue(grab("感情状态"), RELATIONSHIP_LABELS)),
    timePrecision: displayMappedValue(grab("时间精度"), PRECISION_LABELS),
    timeSource: displayMappedValue(grab("时间来源"), TIME_SOURCE_LABELS),
    effectivePrecision: displayMappedValue(grab("有效精度"), EFFECTIVE_PRECISION_LABELS),
    concern: extractConcern(feedback)
  };
}

function resolveBirthCoordinates(
  session: SkillSessionResponse | null,
  fallbackPlace?: string
): { latitude: string; longitude: string } {
  const inputContext = parseJsonArtifact(session, "birth_input_context.json");
  const inputCoordinates = objectValue(objectValue(inputContext, "place"), "coordinates");
  const fromInput = coordinatesFromObject(inputCoordinates);
  if (fromInput) return fromInput;

  const structuredData = parseJsonArtifact(session, "structured_data.json");
  const structuredCoordinates = objectValue(objectValue(structuredData, "subject"), "coordinates");
  const fromStructured = coordinatesFromObject(structuredCoordinates);
  if (fromStructured) return fromStructured;

  const structuredMarkdown =
    session?.artifacts.find((artifact) => artifact.path === "structured_data.md")?.content ?? "";
  const markdownPlace =
    structuredMarkdown.match(/出生地点:\s*(.+)/)?.[1]?.trim() ??
    structuredMarkdown.match(/- Place:\s*(.+)/)?.[1]?.trim();
  const fromText = coordinatesFromText(fallbackPlace ?? markdownPlace ?? "");
  if (fromText) return fromText;

  return { latitude: "", longitude: "" };
}

function parseJsonArtifact(
  session: SkillSessionResponse | null,
  path: string
): Record<string, unknown> | null {
  const artifact = session?.artifacts.find((item) => item.path === path);
  if (!artifact) return null;
  try {
    const parsed = JSON.parse(artifact.content) as unknown;
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

function objectValue(value: unknown, key: string): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const next = (value as Record<string, unknown>)[key];
  return next && typeof next === "object" && !Array.isArray(next)
    ? (next as Record<string, unknown>)
    : null;
}

function coordinatesFromObject(
  value: Record<string, unknown> | null
): { latitude: string; longitude: string } | null {
  const lat = numberLike(value?.lat ?? value?.latitude);
  const lon = numberLike(value?.lon ?? value?.lng ?? value?.longitude);
  if (lat == null || lon == null) return null;
  return { latitude: formatCoordinateDisplay(lat), longitude: formatCoordinateDisplay(lon) };
}

function coordinatesFromText(text: string): { latitude: string; longitude: string } | null {
  const latMatch = text.match(/(?:lat|latitude|纬度|緯度)\s*[:=]\s*(-?\d+(?:\.\d+)?)/i);
  const lonMatch = text.match(/(?:lon|lng|longitude|经度|經度|経度)\s*[:=]\s*(-?\d+(?:\.\d+)?)/i);
  const lat = numberLike(latMatch?.[1]);
  const lon = numberLike(lonMatch?.[1]);
  if (lat == null || lon == null) return null;
  return { latitude: formatCoordinateDisplay(lat), longitude: formatCoordinateDisplay(lon) };
}

function numberLike(value: unknown): number | null {
  const number =
    typeof value === "number" ? value : typeof value === "string" ? Number(value) : NaN;
  return Number.isFinite(number) ? number : null;
}

function formatCoordinateDisplay(value: number) {
  return value.toFixed(6).replace(/\.?0+$/, "");
}

function displayMappedValue(value: string | undefined, labels: Record<string, string>) {
  if (!value) return "";
  return labels[value] ?? value;
}

function displayCollected(value: string | undefined) {
  if (!value || value === "—" || value.includes("not-collected") || value.includes("待填"))
    return "";
  return value;
}

function extractConcern(userContext: string) {
  const match = userContext.match(/### 初始关心事项\s+([\s\S]*?)(?:\n### |\n##_|\n## |$)/);
  return match?.[1]?.trim() ?? "";
}
