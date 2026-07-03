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
import {
  aggregateWorkshopStages,
  PipelineFlow,
  WORKSHOP_STAGES,
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
import type { BirthInput, CoreJobResponse, SkillArtifact, SkillSessionResponse } from "../../shared/domain";

type NavState = { name?: string; birth?: BirthInput; concern?: string } | null;

type BirthInfo = {
  date: string;
  time: string;
  place: string;
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
  inputs: string[];
  outputs: string[];
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

const STAGE_COPY: Record<string, StageCopy> = {
  src: {
    purpose: "Locks the personal information that every later reading must use.",
    userResult: "A stable chart data snapshot is created. This avoids later stages reinterpreting the form fields differently.",
    userAction: "Review the date, time, place, and time confidence. If something is wrong, start a fresh workshop.",
    inputs: ["Birth date, time, place", "Time precision and source", "Gender and relationship status"],
    outputs: ["structured_data.md", "structured_data.json", "run_metrics.json"],
    expected: "Usually seconds. If place resolution fails, fix the city input before continuing."
  },
  reader: {
    purpose: "Validates a few concrete chart anchors before spending time on the full report.",
    userResult: "You get 3-5 concrete anchors to mark as accurate, inaccurate, or partly accurate.",
    userAction: "Answer one anchor at a time. The full report starts only after every anchor has feedback.",
    inputs: ["structured_data.md"],
    outputs: ["reader_prevalidation.md", "user_context.md after your feedback"],
    expected: "Usually a few minutes because this is an LLM reading step."
  },
  p1: {
    purpose: "Builds the first identity frame for the report.",
    userResult: "The report starts with temperament, chart lord, and core orientation.",
    userAction: "No action required. Wait for this stage to finish.",
    inputs: ["structured_data.md"],
    outputs: ["p1_overview.md"],
    expected: "First core node; starts after validation feedback is recorded."
  },
  yoga: {
    purpose: "Finds major chart patterns before judging individual planets.",
    userResult: "Confirmed and rejected pattern signals are carried into later interpretation.",
    userAction: "No action required.",
    inputs: ["structured_data.md", "resources/yogas.md"],
    outputs: [".runtime/p2/yoga.md", "p2a_planets.md after composition"],
    expected: "Runs in parallel with P1 where dependencies allow."
  },
  p2: {
    purpose: "Scores the nine planetary actors that drive most report sections.",
    userResult: "Strength, dignity, house role, and constraints are prepared for later synthesis.",
    userAction: "No action required.",
    inputs: ["structured_data.md", ".runtime/p2/yoga.md"],
    outputs: ["p2a_planets.md", "p2b_planets.md", "p2c_planets.md", "p2d_planets.md"],
    expected: "Nine independent planet nodes can run in parallel after Yoga pre-scan."
  },
  d9: {
    purpose: "Checks whether the surface chart promise holds at a deeper Navamsha level.",
    userResult: "The report can separate visible potential from deeper fulfillment quality.",
    userAction: "No action required.",
    inputs: ["structured_data.md", "p2a-p2d planet audits"],
    outputs: ["p3a_d9.md"],
    expected: "Nine D9 planet nodes can run in parallel after P2."
  },
  div: {
    purpose: "Adds context for career, home/property, and authority/creative themes.",
    userResult: "Specialized charts add evidence without overwhelming the main report.",
    userAction: "No action required.",
    inputs: ["structured_data.md", "p2a-p2d planet audits"],
    outputs: ["p3b_divisional.md"],
    expected: "Three divisional summaries can run in parallel after P2."
  },
  house: {
    purpose: "Reviews the 12 life areas that the final report will synthesize.",
    userResult: "Money, work, relationships, health, learning, family, reputation, and spiritual areas get evidence.",
    userAction: "No action required.",
    inputs: ["p2a-p2d", "p3a_d9.md", "p3b_divisional.md"],
    outputs: ["p4a_houses.md", "p4b_houses.md"],
    expected: "Twelve house nodes can run in parallel after D9 and divisional summaries."
  },
  dasha: {
    purpose: "Builds the timing reference used by the life synthesis.",
    userResult: "Current and upcoming periods can be tied back to the chart evidence.",
    userAction: "No action required.",
    inputs: ["p2a-p2d", "p3a_d9.md", "p3b_divisional.md"],
    outputs: [".runtime/dasha_review.md"],
    expected: "Runs once D9 and divisional outputs are ready."
  },
  pari: {
    purpose: "Cross-checks house interactions so the report does not overstate exchange patterns.",
    userResult: "Confirmed and excluded links are recorded before the final synthesis.",
    userAction: "No action required.",
    inputs: ["All 12 house diagnosis nodes"],
    outputs: [".runtime/houses/parivartana.md", "p4b_houses.md"],
    expected: "Runs after every house node completes."
  },
  life: {
    purpose: "Turns the evidence into readable life-domain sections.",
    userResult: "The report assembles identity, wealth, career, relationship, health, education, family, reputation, growth, and strengths.",
    userAction: "No action required.",
    inputs: ["p4 outputs", "Dasha review", "user_context.md"],
    outputs: ["p5a_life.md", "p5b_life.md"],
    expected: "Ten life-block nodes can run in parallel after house and Dasha stages."
  },
  appx: {
    purpose: "Finalizes the report and keeps technical evidence available at the end.",
    userResult: "The Report tab becomes available with export-ready markdown sections.",
    userAction: "Open the Report tab when this completes.",
    inputs: ["All completed core report artifacts"],
    outputs: ["appendix.md"],
    expected: "Final core node."
  }
};

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

const STATUS_LABELS: Record<StageStatus, string> = {
  done: "Done",
  running: "Running",
  waiting: "Waiting for feedback",
  failed: "Failed",
  pending: "Pending"
};

const VALIDATION_CHOICES: Array<{
  value: ValidationAnswer;
  label: string;
  storedLabel: string;
  description: string;
}> = [
  {
    value: "accurate",
    label: "Accurate",
    storedLabel: "准",
    description: "This anchor matches my real experience."
  },
  {
    value: "partly",
    label: "Partly",
    storedLabel: "部分准",
    description: "The direction is right, but the details need correction."
  },
  {
    value: "inaccurate",
    label: "Not accurate",
    storedLabel: "不准",
    description: "This anchor does not fit my experience."
  }
];

function statusBadgeVariant(status: StageStatus): ComponentProps<typeof Badge>["variant"] {
  if (status === "done") return "done";
  if (status === "running" || status === "waiting") return "gold";
  if (status === "failed") return "error";
  return "neutral";
}

export function Session() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const navState = location.state as NavState;
  const [searchParams, setSearchParams] = useSearchParams();
  const tab = searchParams.get("tab") === "report" ? "report" : "workshop";

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
  const [now, setNow] = useState(Date.now());
  const coreStartedRef = useRef(false);
  const readerStartedRef = useRef(false);

  const reportSections = useMemo(() => getReportSections(session), [session]);
  const runMetrics = useMemo(() => parseRunMetrics(session), [session]);
  const pipelineData = useMemo(
    () => getPipelineData(coreJob, runMetrics, { session, readerRunning }),
    [coreJob, runMetrics, session, readerRunning]
  );
  const jobActive = coreJob?.status === "queued" || coreJob?.status === "running";
  const complete = session?.stage === "core_complete" || coreJob?.status === "completed";
  const coreInterrupted = coreJob?.status === "failed" || (!coreJob && runMetrics?.status === "failed");
  const birthInfo = useMemo(() => resolveBirthInfo(navState, session), [navState, session]);
  const readerPrevalidation = findArtifact(session, "reader_prevalidation.md");
  const feedbackArtifact = findArtifact(session, "user_context.md");
  const awaitingValidationFeedback = Boolean(readerPrevalidation && !feedbackArtifact && !complete);

  const startCoreReport = useCallback(async (options: { resume?: boolean } = {}) => {
    if (!id || (coreStartedRef.current && !options.resume)) return;
    coreStartedRef.current = true;
    setError("");
    try {
      const job = await api.startCoreJob({ sessionId: id, skill: "vedic-core", userMessage: "" });
      setCoreJob(job);
      if (job.session) setSession(job.session);
    } catch (caught) {
      coreStartedRef.current = false;
      setError(caught instanceof Error ? caught.message : "Could not start the core report.");
    }
  }, [id]);

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
        userMessage: "开始读盘验前事"
      });
      setSession(response);
    } catch (caught) {
      readerStartedRef.current = false;
      setError(caught instanceof Error ? caught.message : "Could not generate pre-validation.");
    } finally {
      setReaderRunning(false);
    }
  }, [id]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const loaded = await api.getSkillSession(id);
        if (cancelled) return;
        setSession(loaded);
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
        if (!cancelled) setError(caught instanceof Error ? caught.message : "Could not load session.");
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
            setError(response.message);
          }
        })
        .catch((caught) => {
          if (!cancelled) setError(caught instanceof Error ? caught.message : "Could not refresh progress.");
        });
    }, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [coreJob?.jobId, coreJob?.status]);

  function setTab(next: "workshop" | "report") {
    const params = new URLSearchParams(searchParams);
    params.set("tab", next);
    setSearchParams(params, { replace: true });
  }

  function scrollToSection(index: number) {
    setActiveSection(index);
    document.getElementById(`section-${index}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function onExport() {
    if (!id || exportingPdf) return;
    setError("");
    setExportingPdf(true);
    try {
      await api.downloadReportPdf(id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not export PDF.");
    } finally {
      setExportingPdf(false);
    }
  }

  async function onSubmitFeedback(event: FormEvent) {
    event.preventDefault();
    const feedback = validationFeedback.trim();
    if (!feedback) {
      setError("Please reply to the validation anchors before starting the full report.");
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
      setError(caught instanceof Error ? caught.message : "Could not record validation feedback.");
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
        <Button variant="tab" size="sm" data-active={tab === "workshop"} onClick={() => setTab("workshop")}>
          <Workflow size={14} /> Workshop
        </Button>
        <Button variant="tab" size="sm" data-active={tab === "report"} onClick={() => setTab("report")}>
          <BookOpen size={14} /> Report
        </Button>
        <div className="flex-1" />
      </div>

      {error && (
        <div className="screen-error mx-5 mt-3 shrink-0 rounded-md border border-red/30 bg-red/10 px-4 py-3 text-[13px] text-red sm:mx-8">
          {error}
        </div>
      )}

      {tab === "workshop" ? (
        <div className="grid min-h-0 flex-1 grid-cols-1 overflow-y-auto lg:grid-cols-[minmax(480px,0.95fr)_minmax(420px,1fr)] lg:overflow-hidden 2xl:grid-cols-[560px_1fr]">
          <WorkshopDetailPanel
            selectedStageId={selectedStageId}
            session={session}
            pipelineData={pipelineData}
            coreJob={coreJob}
            birthInfo={birthInfo}
            readerRunning={readerRunning}
            readerStartedAt={readerStartedAt}
            now={now}
            validationFeedback={validationFeedback}
            submittingFeedback={submittingFeedback}
            onValidationFeedbackChange={setValidationFeedback}
            onSubmitFeedback={onSubmitFeedback}
            onResumeCoreReport={resumeCoreReport}
            coreInterrupted={coreInterrupted}
          />
          <div className="relative min-w-0 bg-night-2 max-lg:min-h-[70vh] lg:min-h-0 lg:overflow-hidden">
            {pipelineData ? (
              <PipelineFlow
                data={pipelineData}
                selectedStageId={selectedStageId}
                onSelectStage={setSelectedStageId}
              />
            ) : (
              <div className="grid h-full min-h-[420px] place-items-center text-cream/50">
                <div className="text-center">
                  <LoaderCircle className="mx-auto size-7 animate-spin" />
                  <p className="mt-2.5">Preparing pipeline...</p>
                </div>
              </div>
            )}
          </div>
        </div>
      ) : complete && reportSections.length > 0 ? (
        <div className="report-doc grid h-[calc(100vh-57px)] grid-cols-1 lg:grid-cols-[1fr_260px]">
          <main className="report-main overflow-y-auto bg-cream px-6 py-9 pb-20 sm:px-11">
            <div className="report-doc-head mb-7 flex flex-wrap items-center justify-between gap-4">
              <h1 className="text-[28px] font-light tracking-normal">Your Vedic Report</h1>
              <Button onClick={() => void onExport()} disabled={exportingPdf}>
                {exportingPdf ? <LoaderCircle className="size-4 animate-spin" /> : <Download size={15} />}
                {exportingPdf ? "Preparing PDF..." : "Download PDF"}
              </Button>
            </div>
            {reportSections.map((artifact, index) => (
              <section
                className="report-section mb-12 scroll-mt-20 border-b border-gold/25 pb-12 last:border-0"
                id={`section-${index}`}
                key={artifact.path}
              >
                <div className="mb-2 text-[10px] uppercase tracking-[3px] text-gold">
                  Section {String(index + 1).padStart(2, "0")}
                </div>
                <div className="mb-4 text-[22px] font-medium tracking-normal text-ink">{titleForArtifact(artifact)}</div>
                <MarkdownReport content={artifact.content} />
              </section>
            ))}
          </main>
          <nav className="report-toc hidden overflow-y-auto border-l border-gold/25 bg-cream-2 px-4 py-6 lg:block">
            <h4 className="mb-3.5 text-[11px] uppercase tracking-[2px] text-muted">Contents</h4>
            {reportSections.map((artifact, index) => (
              <button
                key={artifact.path}
                className={cn(
                  "flex w-full items-baseline gap-2 rounded-md px-2.5 py-2 text-left text-[13px] text-body transition hover:bg-gold/10 hover:text-ink",
                  activeSection === index && "bg-gold text-white hover:bg-gold hover:text-white"
                )}
                onClick={() => scrollToSection(index)}
              >
                <span className={cn("shrink-0 text-[11px] font-bold text-gold", activeSection === index && "text-white")}>
                  {String(index + 1).padStart(2, "0")}
                </span>
                {titleForArtifact(artifact)}
              </button>
            ))}
          </nav>
        </div>
      ) : (
        <div className="grid min-h-[calc(100vh-57px)] place-items-center px-6 py-10 text-center">
          <div>
            <div className="mx-auto mb-5 size-11 animate-spin rounded-full border-[3px] border-gold/25 border-t-gold" />
            <h2 className="mb-2 text-2xl font-light">
              {coreInterrupted
                ? "Generation failed"
                : awaitingValidationFeedback
                  ? "Pre-validation is ready"
                  : readerRunning
                    ? "Generating pre-validation"
                    : "Your report is being generated"}
            </h2>
            <p className="mx-auto mb-6 max-w-[420px] text-sm text-body">
              {coreInterrupted
                ? coreJob?.message ?? "Generation was interrupted. Completed sections are saved; retry will resume from unfinished steps."
                : awaitingValidationFeedback
                  ? "Reply to the validation anchors in Workshop before the full report starts."
                  : `The full analysis runs stage by stage${
                      pipelineData ? ` - ${pipelineData.completed}/${pipelineData.total} steps done` : ""
                    }. Watch it live in the Workshop tab.`}
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              {coreInterrupted && (
                <Button onClick={() => void resumeCoreReport()}>
                  <RefreshCw size={15} /> Resume generation
                </Button>
              )}
              <Button variant={coreInterrupted ? "outline" : "gold"} onClick={() => setTab("workshop")}>
                <Workflow size={15} /> Go to Workshop
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function WorkshopDetailPanel({
  selectedStageId,
  session,
  pipelineData,
  coreJob,
  birthInfo,
  readerRunning,
  readerStartedAt,
  now,
  validationFeedback,
  submittingFeedback,
  onValidationFeedbackChange,
  onSubmitFeedback,
  onResumeCoreReport,
  coreInterrupted
}: {
  selectedStageId: string;
  session: SkillSessionResponse | null;
  pipelineData: PipelineData | null;
  coreJob: CoreJobResponse | null;
  birthInfo: BirthInfo;
  readerRunning: boolean;
  readerStartedAt: number | null;
  now: number;
  validationFeedback: string;
  submittingFeedback: boolean;
  onValidationFeedbackChange: (value: string) => void;
  onSubmitFeedback: (event: FormEvent) => void;
  onResumeCoreReport: () => Promise<void>;
  coreInterrupted: boolean;
}) {
  const stage = WORKSHOP_STAGES.find((item) => item.id === selectedStageId) ?? WORKSHOP_STAGES[0];
  const nodes = pipelineData?.nodes.filter((node) => stage.match(node.id)) ?? [];
  const stageAgg = pipelineData ? aggregateWorkshopStages(pipelineData.nodes)[stage.id] : null;
  const status = stage.seed ? "done" : stageAgg?.status ?? "pending";

  return (
    <aside className="relative border-r border-gold/25 bg-cream px-6 py-7 max-lg:border-b max-lg:border-r-0 lg:min-h-0 lg:overflow-y-auto">
      <StageInfoPopover
        stageLabel={stage.label}
        copy={STAGE_COPY[stage.id]}
        className="absolute right-6 top-7"
      />
      <div className="mb-2 pr-9 text-[10px] uppercase tracking-[2.4px] text-gold">Workshop detail</div>
      <div className="mb-5 flex items-start justify-between gap-3 pr-9">
        <h3 className="min-w-0 text-lg font-semibold tracking-normal text-ink">{stage.label}</h3>
        <Badge variant={statusBadgeVariant(status)}>{STATUS_LABELS[status]}</Badge>
      </div>

      {stage.id === "src" ? (
        <BirthDetail birthInfo={birthInfo} />
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
        />
      ) : (
        <CoreStageDetail
          stageId={stage.id}
          session={session}
          nodes={nodes}
          status={status}
          coreJob={coreJob}
          now={now}
          onResumeCoreReport={onResumeCoreReport}
          coreInterrupted={coreInterrupted}
        />
      )}
    </aside>
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
          aria-label={`About ${stageLabel}`}
        >
          <Info className="size-3" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-[min(92vw,380px)] p-4" align="end" side="bottom">
        <div className="mb-3">
          <div className="mb-1 text-[10px] uppercase tracking-[1.8px] text-gold">Stage guide</div>
          <h4 className="m-0 text-base font-semibold text-ink">{stageLabel}</h4>
        </div>
        <div className="grid gap-3 text-[13px] leading-[1.65] text-body">
          <StageInfoBlock title="What this stage does">{copy.purpose}</StageInfoBlock>
          <StageInfoBlock title="What you get">{copy.userResult}</StageInfoBlock>
          <StageInfoBlock title="What you do">{copy.userAction}</StageInfoBlock>
          <div className="border-t border-gold/20 pt-3">
            <StageInfoBlock title="Expected timing">{copy.expected}</StageInfoBlock>
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
  return (
    <>
      <div className="my-4">
        <InfoRow label="Date" value={birthInfo.date} />
        <InfoRow label="Time" value={birthInfo.time} />
        <InfoRow label="Place" value={birthInfo.place} />
        <InfoRow label="Time precision" value={birthInfo.timePrecision} />
        <InfoRow label="Time source" value={birthInfo.timeSource} />
        <InfoRow label="Effective precision" value={birthInfo.effectivePrecision} />
        {birthInfo.gender && <InfoRow label="Gender" value={birthInfo.gender} />}
        {birthInfo.relationship && <InfoRow label="Relationship" value={birthInfo.relationship} />}
      </div>
      {birthInfo.concern && (
        <div className="my-4">
          <DetailSubtitle>Initial concern</DetailSubtitle>
          <p className="m-0 text-[13px] leading-[1.7] text-body">{birthInfo.concern}</p>
        </div>
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
  onSubmitFeedback
}: {
  session: SkillSessionResponse | null;
  readerRunning: boolean;
  readerStartedAt: number | null;
  now: number;
  validationFeedback: string;
  submittingFeedback: boolean;
  onValidationFeedbackChange: (value: string) => void;
  onSubmitFeedback: (event: FormEvent) => void;
}) {
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

  function updateAnchorFeedback(anchor: ValidationAnchor, update: Partial<{ answer: ValidationAnswer; note: string }>) {
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
          <DetailSubtitle>{readerRunning ? "Running now" : "Not started"}</DetailSubtitle>
          <p className="m-0 text-[13px] leading-[1.7] text-body">
            {readerRunning
              ? `Elapsed ${formatElapsed(readerStartedAt, now)}. The LLM is generating validation anchors from structured_data.md.`
              : STAGE_COPY.reader.expected}
          </p>
        </div>
      </>
    );
  }

  return (
    <>
      {feedback ? (
        <ReaderCompletedDetail anchors={anchors} feedback={feedback} recordedFeedback={recordedFeedback} />
      ) : (
        <form className="mt-4 grid gap-4" onSubmit={onSubmitFeedback}>
          <div className="rounded-xl border border-gold/35 bg-gold/10 px-4 py-3 shadow-[0_12px_30px_rgba(201,169,110,0.10)]">
            <div className="mb-1 flex items-center gap-2 text-[11px] font-bold uppercase tracking-[1.5px] text-gold-dim">
              <CheckCircle2 className="size-4" />
              Your input is required
            </div>
            <p className="m-0 text-[13px] leading-[1.65] text-body">
              Answer each validation anchor before the full report starts. These answers calibrate how much confidence the reader should place in your birth time.
            </p>
          </div>

          {activeAnchor ? (
            <div className="rounded-xl border border-gold/25 bg-cream-2 p-4">
              <div className="mb-3 flex items-center justify-between gap-3">
                <div>
                  <div className="text-[10px] uppercase tracking-[1.8px] text-muted">Validation anchor</div>
                  <div className="mt-1 flex items-center gap-2 text-sm font-semibold text-ink">
                    Question {activeAnchorIndex + 1} of {anchors.length}
                    {activeAnchor.rationale && (
                      <AnchorRationalePopover
                        label={`Why question ${activeAnchorIndex + 1} was inferred`}
                        rationale={activeAnchor.rationale}
                      />
                    )}
                  </div>
                </div>
                <Badge variant="neutral">
                  {answeredCount}/{anchors.length} answered
                </Badge>
              </div>

              <div className="rounded-lg border border-gold/20 bg-gold/10 px-3.5 py-3 text-[13px] leading-[1.75] text-body">
                {activeAnchor.statement}
              </div>

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
                      onClick={() => updateAnchorFeedback(activeAnchor, { answer: choice.value })}
                    >
                      <span className="block text-sm font-semibold">{choice.label}</span>
                      <span className={cn("mt-0.5 block text-[12.5px]", selected ? "text-white/80" : "text-muted")}>
                        {choice.description}
                      </span>
                    </button>
                  );
                })}
              </div>

              <label className="mt-4 block">
                <span className="mb-1.5 block text-[11px] uppercase tracking-[1.4px] text-muted">Optional note</span>
                <Textarea
                  rows={4}
                  value={anchorFeedback[activeAnchor.index]?.note ?? ""}
                  onChange={(event) => updateAnchorFeedback(activeAnchor, { note: event.target.value })}
                  placeholder="Add a correction or example if useful."
                />
              </label>

              <div className="mt-4 flex items-center justify-between gap-3">
                <Button type="button" variant="ghost" size="sm" disabled={activeAnchorIndex === 0} onClick={movePrev}>
                  <ChevronLeft size={14} /> Previous
                </Button>
                {activeAnchorIndex < anchors.length - 1 ? (
                  <Button
                    type="button"
                    size="sm"
                    disabled={!anchorFeedback[activeAnchor.index]?.answer}
                    onClick={moveNext}
                  >
                    Next <ChevronRight size={14} />
                  </Button>
                ) : (
                  <Button disabled={submittingFeedback || !allAnswered || !validationFeedback.trim()}>
                    {submittingFeedback ? "Recording..." : "Record feedback and start report"}
                  </Button>
                )}
              </div>
            </div>
          ) : (
            <div className="rounded-xl border border-gold/25 bg-cream-2 p-4">
              <DetailSubtitle>Validation response</DetailSubtitle>
              <Textarea
                rows={7}
                value={validationFeedback}
                onChange={(event) => onValidationFeedbackChange(event.target.value)}
                placeholder="Reply with what feels accurate, partly accurate, or inaccurate."
              />
              <Button className="mt-3 w-full" disabled={submittingFeedback || !validationFeedback.trim()}>
                {submittingFeedback ? "Recording..." : "Record feedback and start report"}
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
  const structuredCount = recordedFeedback.size;

  return (
    <div className="mt-4 grid gap-4">
      <div className="rounded-xl border border-gold/35 bg-gold/10 px-4 py-3 shadow-[0_12px_30px_rgba(201,169,110,0.10)]">
        <div className="mb-1 flex items-center gap-2 text-[11px] font-bold uppercase tracking-[1.5px] text-gold-dim">
          <CheckCircle2 className="size-4" />
          Validation complete
        </div>
        <p className="m-0 text-[13px] leading-[1.65] text-body">
          Your feedback has been saved. The full reading can now use these answers as calibration context.
        </p>
      </div>

      {structuredCount === 0 && (
        <div className="rounded-xl border border-gold/25 bg-cream-2 px-4 py-3 text-[13px] leading-[1.65] text-body">
          Your feedback was saved as general context for the report.
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
                    <div className="text-[10px] uppercase tracking-[1.8px] text-muted">Validation anchor</div>
                    <div className="mt-1 flex items-center gap-2 text-sm font-semibold text-ink">
                      Question {anchorIndex + 1} of {anchors.length}
                      {anchor.rationale && (
                        <AnchorRationalePopover
                          label={`Why question ${anchorIndex + 1} was inferred`}
                          rationale={anchor.rationale}
                        />
                      )}
                    </div>
                  </div>
                  <Badge variant={feedbackBadgeVariant(summary?.answer)}>{summary?.answerLabel ?? "Recorded"}</Badge>
                </div>

                <div className="rounded-lg border border-gold/20 bg-gold/10 px-3.5 py-3 text-[13px] leading-[1.75] text-body">
                  {anchor.statement}
                </div>

                {summary?.note && (
                  <div className="mt-3 rounded-lg border border-gold/20 bg-cream/80 px-3.5 py-3">
                    <div className="mb-1 text-[10px] uppercase tracking-[1.4px] text-muted">Your note</div>
                    <p className="m-0 text-[13px] leading-[1.65] text-body">{summary.note}</p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="rounded-xl border border-gold/25 bg-cream-2 p-4">
          <DetailSubtitle>Recorded feedback</DetailSubtitle>
          <p className="m-0 text-[13px] leading-[1.65] text-body">{excerpt(feedback.content, 420)}</p>
        </div>
      )}
    </div>
  );
}

function feedbackBadgeVariant(answer: ValidationFeedbackSummary["answer"] | undefined): ComponentProps<typeof Badge>["variant"] {
  if (answer === "accurate") return "done";
  if (answer === "partly") return "gold";
  if (answer === "inaccurate") return "error";
  return "neutral";
}

function AnchorRationalePopover({ label, rationale }: { label: string; rationale: string }) {
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
        <div className="mb-2 text-[10px] uppercase tracking-[1.6px] text-gold">Why this was inferred</div>
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
  coreJob,
  now,
  onResumeCoreReport,
  coreInterrupted
}: {
  stageId: string;
  session: SkillSessionResponse | null;
  nodes: PipelineNode[];
  status: StageStatus;
  coreJob: CoreJobResponse | null;
  now: number;
  onResumeCoreReport: () => Promise<void>;
  coreInterrupted: boolean;
}) {
  const copy = STAGE_COPY[stageId];
  const runningNodes = nodes.filter((node) => node.status === "running");
  const completedNodes = nodes.filter((node) => node.status === "completed" || node.status === "skipped");
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
              Needs attention
            </div>
            {coreInterrupted && (
              <Button size="sm" onClick={() => void onResumeCoreReport()}>
                <RefreshCw size={13} /> Resume
              </Button>
            )}
          </div>
          {coreInterrupted && (
            <p className="m-0 mb-3 text-[13px] leading-[1.7] text-body">
              Completed sections have been saved. Resume will continue from unfinished steps.
            </p>
          )}
          <div className="grid gap-2 border-t border-red/20 pt-3">
            {failedNodes.map((node) => (
              <div className="text-[12.5px] leading-[1.6]" key={node.id}>
                <div className="font-semibold text-ink">{node.label}</div>
                <div className="mt-0.5 break-words text-red">{node.error || "Failed"}</div>
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
  const Icon = status === "failed" ? AlertTriangle : status === "running" ? Clock3 : status === "done" ? CheckCircle2 : ListChecks;
  const summary = stageStatusSummary(status, copy, coreInterrupted);

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
                {completed}/{total} ready
              </span>
            )}
            {running > 0 && status === "running" && (
              <span className="rounded-full border border-gold/25 bg-gold/10 px-2.5 py-1">
                {running} active
              </span>
            )}
            {durationSeconds > 0 && (
              <span className="rounded-full border border-gold/25 bg-cream-2 px-2.5 py-1">
                {formatDuration(durationSeconds)} saved
              </span>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

function stageStatusSummary(status: StageStatus, copy: StageCopy, coreInterrupted: boolean) {
  if (status === "failed") {
    return {
      title: "Generation paused",
      body: coreInterrupted
        ? "Something interrupted this part of the reading. Resume will keep completed content and only retry unfinished work."
        : "This section needs attention before it can be used in the final report."
    };
  }
  if (status === "done") {
    return {
      title: "Result is ready",
      body: "There is nothing you need to do here. This section is saved and will be included in the final report."
    };
  }
  if (status === "running") {
    return {
      title: "Reading in progress",
      body: "No action is needed. The system is saving each completed part as it becomes available."
    };
  }
  if (status === "waiting") {
    return {
      title: "Waiting for your input",
      body: copy.userAction
    };
  }
  return {
    title: "Waiting for earlier sections",
    body: "No action is needed. This section will start after its source evidence is ready."
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
  if (status === "done") return null;
  return (
    <section className="my-5 border-t border-gold/25 pt-4">
      <DetailSubtitle>{status === "running" ? "Result preview" : "Coming next"}</DetailSubtitle>
      <p className="m-0 text-[13px] leading-[1.7] text-body">
        {status === "running"
          ? `A preview will appear here as soon as this section has saved readable output${progress ? ` (${progress} parts ready)` : ""}.`
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
  const [expanded, setExpanded] = useState(false);
  const displayContent = useMemo(() => sanitizeResultContentForDisplay(artifact.content), [artifact.content]);
  const sections = useMemo(() => parseResultPreviewSections(displayContent), [displayContent]);
  const visibleSections = expanded ? sections : sections.slice(0, 3);
  const canExpand = sections.length > 0;
  const label = status === "done" ? "Result preview" : "Saved result preview";

  return (
    <section className="my-5 border-t border-gold/25 pt-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-2.5">
          <div className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full border border-gold/25 bg-gold/10 text-gold-dim">
            <FileText className="size-3.5" />
          </div>
          <div className="min-w-0">
            <DetailSubtitle className="mb-1">{label}</DetailSubtitle>
            <div className="text-sm font-semibold text-ink">{titleForArtifact(artifact)}</div>
          </div>
        </div>
        {canExpand && (
          <Button type="button" variant="ghost" size="sm" onClick={() => setExpanded((value) => !value)}>
            <Eye size={13} /> {expanded ? "Show less" : "Show full"}
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
              {sections.length - visibleSections.length} more sections are available in the full result.
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function DetailSubtitle({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("mb-2 text-[11px] uppercase tracking-[1.4px] text-muted", className)}>{children}</div>;
}

function findStageArtifact(
  session: SkillSessionResponse | null,
  stageId: string,
  nodes: PipelineNode[]
): SkillArtifact | null {
  const candidates = [
    ...(STAGE_COPY[stageId]?.outputs ?? []),
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
    return [{ id: "result-section-1", title: "Overview", body: cleanResultPreviewBody(normalized) }];
  }
  const readable = sections.filter((section) => stripMarkdownForPreview(section.body).length > 24);
  return (readable.length > 0 ? readable : sections).slice(0, 24);
}

function cleanResultPreviewBody(content: string) {
  return content
    .split("\n")
    .filter((line) => !isPreviewMetaLine(line))
    .join("\n")
    .trim();
}

function isPreviewMetaLine(line: string) {
  const normalized = line
    .trim()
    .replace(/^>\s*/, "")
    .replace(/\*\*/g, "")
    .replace(/`/g, "");
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
          rationaleLines.push(trimmed.replace(/^>\s*/, "").replace(/^推导[:：]\s*/, ""));
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
    lines.push(`- User answer: ${choice?.storedLabel ?? entry?.answer ?? ""} (${choice?.label ?? ""})`);
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
    const anchorText = block.match(/^- Anchor text:\s*([\s\S]*?)(?=\n- User |\n$|$)/m)?.[1]?.trim() ?? "";
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

function normalizeRecordedAnswer(raw: string): { answer: ValidationAnswer | "recorded"; label: string } {
  if (/Not accurate|不准/i.test(raw)) return { answer: "inaccurate", label: "Not accurate" };
  if (/Partly|部分/i.test(raw)) return { answer: "partly", label: "Partly" };
  if (/Accurate|准/i.test(raw)) return { answer: "accurate", label: "Accurate" };
  return { answer: "recorded", label: raw || "Recorded" };
}

function formatElapsed(startedAt: number | null, now: number) {
  if (!startedAt) return "—";
  return formatDuration(Math.max(0, (now - startedAt) / 1000));
}

function formatElapsedIso(startedAt: string | null | undefined, now: number) {
  if (!startedAt) return "—";
  const started = new Date(startedAt).getTime();
  if (Number.isNaN(started)) return "—";
  return formatDuration(Math.max(0, (now - started) / 1000));
}

function formatTimestamp(value: string | null | undefined) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function resolveBirthInfo(navState: NavState, session: SkillSessionResponse | null): BirthInfo {
  if (navState?.birth) {
    return {
      date: navState.birth.birthDate,
      time: navState.birth.birthTime || "Unknown (12:00 placeholder)",
      place: navState.birth.birthPlace,
      gender: displayCollected(GENDER_LABELS[navState.birth.gender] ?? navState.birth.gender),
      relationship: displayCollected(RELATIONSHIP_LABELS[navState.birth.relationship] ?? navState.birth.relationship),
      timePrecision: displayMappedValue(navState.birth.birthTimePrecision, PRECISION_LABELS),
      timeSource: displayMappedValue(navState.birth.timeSource || "未追问", TIME_SOURCE_LABELS),
      effectivePrecision:
        navState.birth.birthTimePrecision === "exact" && navState.birth.timeSource === "出生证/医院记录"
          ? "± minute-level"
          : "Adjusted by reader validation",
      concern: navState.concern?.trim() ?? ""
    };
  }

  const sd = session?.artifacts.find((a) => a.path === "structured_data.md")?.content ?? "";
  const grab = (label: string) => sd.match(new RegExp(`${label}:\\s*(.+)`))?.[1]?.trim() ?? "—";
  const feedback = session?.artifacts.find((a) => a.path === "user_context.md")?.content ?? "";
  return {
    date: grab("出生日期"),
    time: grab("出生时间"),
    place: grab("出生地点"),
    gender: displayCollected(displayMappedValue(grab("性别"), GENDER_LABELS)),
    relationship: displayCollected(displayMappedValue(grab("感情状态"), RELATIONSHIP_LABELS)),
    timePrecision: displayMappedValue(grab("时间精度"), PRECISION_LABELS),
    timeSource: displayMappedValue(grab("时间来源"), TIME_SOURCE_LABELS),
    effectivePrecision: displayMappedValue(grab("有效精度"), EFFECTIVE_PRECISION_LABELS),
    concern: extractConcern(feedback)
  };
}

function displayMappedValue(value: string | undefined, labels: Record<string, string>) {
  if (!value) return "";
  return labels[value] ?? value;
}

function displayCollected(value: string | undefined) {
  if (!value || value === "—" || value.includes("not-collected") || value.includes("待填")) return "";
  return value;
}

function extractConcern(userContext: string) {
  const match = userContext.match(/### 初始关心事项\s+([\s\S]*?)(?:\n### |\n##_|\n## |$)/);
  return match?.[1]?.trim() ?? "";
}
