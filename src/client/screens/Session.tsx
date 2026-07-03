import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ComponentProps, FormEvent, ReactNode } from "react";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { BookOpen, Download, LoaderCircle, Workflow } from "lucide-react";
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

const STAGE_COPY: Record<string, StageCopy> = {
  src: {
    purpose: "Locks the birth details that every later reading must use.",
    userResult: "A stable chart data snapshot is created. This avoids later stages reinterpreting the form fields differently.",
    userAction: "Review the date, time, place, and time confidence. If something is wrong, start a fresh workshop.",
    inputs: ["Birth date, time, place", "Time precision and source", "Gender and relationship status"],
    outputs: ["structured_data.md", "structured_data.json", "run_metrics.json"],
    expected: "Usually seconds. If place resolution fails, fix the city input before continuing."
  },
  reader: {
    purpose: "Checks whether the birth time feels plausible before spending time on the full report.",
    userResult: "You get 3-5 concrete anchors to mark as accurate, inaccurate, or partly accurate.",
    userAction: "Reply to each anchor. The full report starts only after this feedback is recorded.",
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
  unknown: "Unknown"
};

const STATUS_LABELS: Record<StageStatus, string> = {
  done: "Done",
  running: "Running",
  waiting: "Waiting for feedback",
  failed: "Failed",
  pending: "Pending"
};

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
  const birthInfo = useMemo(() => resolveBirthInfo(navState, session), [navState, session]);
  const readerPrevalidation = findArtifact(session, "reader_prevalidation.md");
  const feedbackArtifact = findArtifact(session, "user_context.md");
  const awaitingValidationFeedback = Boolean(readerPrevalidation && !feedbackArtifact && !complete);

  const startCoreReport = useCallback(async () => {
    if (!id || coreStartedRef.current) return;
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
          if (response.status === "failed") setError(response.message);
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

  function onExport() {
    setError("");
    window.requestAnimationFrame(() => window.print());
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
    <div className="app-shell flex min-h-screen flex-col bg-cream-2">
      <div className="app-tabs sticky top-0 z-10 flex items-center gap-2 border-b border-gold/25 bg-cream/95 px-5 py-3 backdrop-blur-lg sm:px-8">
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
        <div className="screen-error mx-5 mt-3 rounded-md border border-red/30 bg-red/10 px-4 py-3 text-[13px] text-red sm:mx-8">
          {error}
        </div>
      )}

      {tab === "workshop" ? (
        <div className="grid flex-1 grid-cols-1 overflow-hidden lg:grid-cols-[340px_1fr]">
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
          />
          <div className="relative min-w-0 bg-night-2 max-lg:min-h-[70vh]">
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
              <Button onClick={onExport}>
                <Download size={15} /> Export PDF
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
              {coreJob?.status === "failed"
                ? "Generation failed"
                : awaitingValidationFeedback
                  ? "Pre-validation is ready"
                  : readerRunning
                    ? "Generating pre-validation"
                    : "Your report is being generated"}
            </h2>
            <p className="mx-auto mb-6 max-w-[420px] text-sm text-body">
              {coreJob?.status === "failed"
                ? coreJob.message
                : awaitingValidationFeedback
                  ? "Reply to the validation anchors in Workshop before the full report starts."
                  : `The full analysis runs stage by stage${
                      pipelineData ? ` - ${pipelineData.completed}/${pipelineData.total} steps done` : ""
                    }. Watch it live in the Workshop tab.`}
            </p>
            <Button onClick={() => setTab("workshop")}>
              <Workflow size={15} /> Go to Workshop
            </Button>
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
  onSubmitFeedback
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
}) {
  const stage = WORKSHOP_STAGES.find((item) => item.id === selectedStageId) ?? WORKSHOP_STAGES[0];
  const nodes = pipelineData?.nodes.filter((node) => stage.match(node.id)) ?? [];
  const stageAgg = pipelineData ? aggregateWorkshopStages(pipelineData.nodes)[stage.id] : null;
  const status = stage.seed ? "done" : stageAgg?.status ?? "pending";

  return (
    <aside className="border-r border-gold/25 bg-cream px-6 py-7 max-lg:border-b max-lg:border-r-0 lg:overflow-y-auto">
      <div className="mb-2 text-[10px] uppercase tracking-[2.4px] text-gold">Workshop detail</div>
      <div className="mb-2.5 flex items-start justify-between gap-3">
        <h3 className="text-lg font-semibold tracking-normal text-ink">{stage.label}</h3>
        <Badge variant={statusBadgeVariant(status)}>{STATUS_LABELS[status]}</Badge>
      </div>
      <p className="mb-4 text-[13px] leading-[1.65] text-body">{STAGE_COPY[stage.id]?.purpose}</p>
      <div className="mb-5 grid gap-2.5">
        <DetailCallout title="What you get">{STAGE_COPY[stage.id]?.userResult}</DetailCallout>
        <DetailCallout title="What to do">{STAGE_COPY[stage.id]?.userAction}</DetailCallout>
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
        />
      )}
    </aside>
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
      <div className="my-4">
        <InfoRow label="Generated" value={formatTimestamp(prevalidation.updatedAt)} />
        <InfoRow label="Feedback" value={feedback ? "Recorded" : "Required before full report"} />
      </div>
      <ArtifactExcerpt artifact={prevalidation} title="Validation anchors" />
      {feedback ? (
        <ArtifactExcerpt artifact={feedback} title="Recorded feedback" />
      ) : (
        <form className="mt-4 grid gap-2.5" onSubmit={onSubmitFeedback}>
          <label className="text-[11px] uppercase tracking-[1.4px] text-muted">Reply to each anchor</label>
          <Textarea
            rows={7}
            value={validationFeedback}
            onChange={(event) => onValidationFeedbackChange(event.target.value)}
            placeholder={"1. 准 / 不准 / 部分准 - ...\n2. 准 / 不准 / 部分准 - ...\n3. 准 / 不准 / 部分准 - ..."}
          />
          <Button disabled={submittingFeedback || !validationFeedback.trim()}>
            {submittingFeedback ? "Recording..." : "Record feedback and start report"}
          </Button>
        </form>
      )}
    </>
  );
}

function CoreStageDetail({
  stageId,
  session,
  nodes,
  status,
  coreJob,
  now
}: {
  stageId: string;
  session: SkillSessionResponse | null;
  nodes: PipelineNode[];
  status: StageStatus;
  coreJob: CoreJobResponse | null;
  now: number;
}) {
  const copy = STAGE_COPY[stageId];
  const runningNodes = nodes.filter((node) => node.status === "running");
  const completedNodes = nodes.filter((node) => node.status === "completed" || node.status === "skipped");
  const failedNodes = nodes.filter((node) => node.status === "failed");
  const stageDuration = completedNodes.reduce((sum, node) => sum + (node.durationSeconds ?? 0), 0);
  const artifact = findStageArtifact(session, stageId, nodes);

  return (
    <>
      <div className="my-4">
        <InfoRow label="Stage status" value={STATUS_LABELS[status]} />
        {nodes.length > 0 && <InfoRow label="Nodes" value={`${completedNodes.length}/${nodes.length} complete`} />}
        {stageDuration > 0 && <InfoRow label="Completed node time" value={formatDuration(stageDuration)} />}
        {coreJob?.status && <InfoRow label="Core job" value={coreJob.status} />}
      </div>

      {status === "pending" && (
        <div className="my-4">
          <DetailSubtitle>What will run here</DetailSubtitle>
          <p className="m-0 text-[13px] leading-[1.7] text-body">{copy.expected}</p>
        </div>
      )}

      {runningNodes.length > 0 && (
        <div className="my-4">
          <DetailSubtitle>Running nodes</DetailSubtitle>
          <div className="grid gap-2">
            {runningNodes.map((node) => (
              <div className="flex justify-between gap-2.5 rounded-md border border-gold/25 bg-cream-2 px-2.5 py-2 text-[12.5px]" key={node.id}>
                <b className="font-semibold text-ink">{node.label}</b>
                <span className="text-right text-muted">{formatElapsedIso(node.startedAt, now)} elapsed</span>
              </div>
            ))}
          </div>
          <p className="m-0 mt-2.5 text-[13px] leading-[1.7] text-muted">
            Expected time depends mostly on LLM latency; parallel waves reduce wall-clock time when
            independent nodes are ready together.
          </p>
        </div>
      )}

      {failedNodes.length > 0 && (
        <div className="my-4">
          <DetailSubtitle>Errors</DetailSubtitle>
          <div className="grid gap-2">
            {failedNodes.map((node) => (
              <div className="flex justify-between gap-2.5 rounded-md border border-red/30 bg-red/10 px-2.5 py-2 text-[12.5px]" key={node.id}>
                <b className="font-semibold text-ink">{node.label}</b>
                <span className="text-right text-red">{node.error || "Failed"}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {artifact && <ArtifactExcerpt artifact={artifact} title="Latest generated draft" />}
    </>
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

function DetailCallout({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-lg border border-gold/20 bg-cream-2 px-3 py-2.5">
      <div className="mb-1 text-[10px] uppercase tracking-[1.4px] text-muted">{title}</div>
      <p className="m-0 text-[12.5px] leading-[1.65] text-body">{children}</p>
    </div>
  );
}

function ArtifactExcerpt({ artifact, title }: { artifact: SkillArtifact; title: string }) {
  return (
    <div className="my-4">
      <DetailSubtitle>{title}</DetailSubtitle>
      <pre className="m-0 max-h-[280px] overflow-auto whitespace-pre-wrap rounded-md border border-gold/25 bg-cream-2 p-3 font-mono text-[12.5px] leading-[1.65] text-body">
        {excerpt(artifact.content)}
      </pre>
    </div>
  );
}

function DetailSubtitle({ children }: { children: ReactNode }) {
  return <div className="mb-2 text-[11px] uppercase tracking-[1.4px] text-muted">{children}</div>;
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

function excerpt(content: string, max = 1600) {
  const normalized = content.trim();
  if (normalized.length <= max) return normalized;
  return `${normalized.slice(0, max).trimEnd()}\n\n...`;
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
      gender: displayCollected(navState.birth.gender),
      relationship: displayCollected(navState.birth.relationship),
      timePrecision: PRECISION_LABELS[navState.birth.birthTimePrecision] ?? navState.birth.birthTimePrecision,
      timeSource: navState.birth.timeSource || "未追问",
      effectivePrecision:
        navState.birth.birthTimePrecision === "exact" && navState.birth.timeSource === "出生证/医院记录"
          ? "±minute"
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
    gender: displayCollected(grab("性别")),
    relationship: displayCollected(grab("感情状态")),
    timePrecision: grab("时间精度"),
    timeSource: grab("时间来源"),
    effectivePrecision: grab("有效精度"),
    concern: extractConcern(feedback)
  };
}

function displayCollected(value: string | undefined) {
  if (!value || value === "—" || value.includes("not-collected") || value.includes("待填")) return "";
  return value;
}

function extractConcern(userContext: string) {
  const match = userContext.match(/### 初始关心事项\s+([\s\S]*?)(?:\n### |\n##_|\n## |$)/);
  return match?.[1]?.trim() ?? "";
}
