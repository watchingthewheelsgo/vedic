import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { BookOpen, Download, LoaderCircle, Workflow } from "lucide-react";
import { api } from "../api";
import { PipelineFlow } from "../components/PipelineFlow";
import { MarkdownReport } from "../components/MarkdownReport";
import { getPipelineData, parseRunMetrics } from "../lib/pipeline";
import { getReportSections, titleForArtifact } from "../lib/report";
import type { BirthInput, CoreJobResponse, SkillSessionResponse } from "../../shared/domain";

type NavState = { name?: string; birth?: BirthInput } | null;

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
  const startedRef = useRef(false);

  const reportSections = useMemo(() => getReportSections(session), [session]);
  const runMetrics = useMemo(() => parseRunMetrics(session), [session]);
  const pipelineData = useMemo(() => getPipelineData(coreJob, runMetrics), [coreJob, runMetrics]);
  const jobActive = coreJob?.status === "queued" || coreJob?.status === "running";
  // Completion must NOT be inferred from "some report files exist": the backend
  // writes composed public files (p2a_planets.md, …) progressively during the
  // run, so reportSections>0 is true mid-generation. core_complete stage (set
  // only after all batches) or a completed job is the reliable signal.
  const complete = session?.stage === "core_complete" || coreJob?.status === "completed";
  const birthInfo = useMemo(() => resolveBirthInfo(navState, session), [navState, session]);

  // On mount: load session; if not complete, (re)attach a core job. startCoreJob
  // dedups per session server-side, so this recovers the running job on refresh.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const loaded = await api.getSkillSession(id);
        if (cancelled) return;
        setSession(loaded);
        // Only a core_complete session is "done". A session with partial
        // composed files (interrupted run) should resume, not display as ready.
        const done = loaded.stage === "core_complete";
        if (!done && !startedRef.current) {
          startedRef.current = true;
          const job = await api.startCoreJob({ sessionId: id, skill: "vedic-core", userMessage: "" });
          if (cancelled) return;
          setCoreJob(job);
          if (job.session) setSession(job.session);
        }
      } catch (caught) {
        if (!cancelled) setError(caught instanceof Error ? caught.message : "Could not load session.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  // Poll the active job.
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

  return (
    <div className="app-shell">
      <div className="app-tabs">
        <div className="logo" style={{ marginRight: 12 }} onClick={() => navigate("/")}>
          Veda<span>Light</span>
        </div>
        <button className={`rnav-item ${tab === "workshop" ? "active" : ""}`} onClick={() => setTab("workshop")}>
          <Workflow size={14} /> Workshop
        </button>
        <button className={`rnav-item ${tab === "report" ? "active" : ""}`} onClick={() => setTab("report")}>
          <BookOpen size={14} /> Report
        </button>
        <div className="spacer" />
        <span className="sid">{id}</span>
      </div>

      {error && <div className="form-error" style={{ margin: "12px 32px 0" }}>{error}</div>}

      {tab === "workshop" ? (
        <div className="workshop">
          <aside className="info-panel">
            <h3>Birth Details</h3>
            {navState?.name && <div className="info-row"><span className="k">Name</span><span className="v">{navState.name}</span></div>}
            <div className="info-row"><span className="k">Date</span><span className="v">{birthInfo.date}</span></div>
            <div className="info-row"><span className="k">Time</span><span className="v">{birthInfo.time}</span></div>
            <div className="info-row"><span className="k">Place</span><span className="v">{birthInfo.place}</span></div>
            {birthInfo.gender && <div className="info-row"><span className="k">Gender</span><span className="v">{birthInfo.gender}</span></div>}
            <div className="info-note">
              The pipeline on the right runs your chart through ~48 analysis nodes. Nodes turn gold as
              each stage completes; you can pan, zoom, and fit the view.
            </div>
          </aside>
          <div className="flow-wrap">
            {pipelineData ? (
              <PipelineFlow data={pipelineData} />
            ) : (
              <div style={{ height: "100%", display: "grid", placeItems: "center", color: "rgba(245,239,230,.5)" }}>
                <div style={{ textAlign: "center" }}>
                  <LoaderCircle size={26} style={{ animation: "spin 1s linear infinite" }} />
                  <p style={{ marginTop: 10 }}>Preparing pipeline…</p>
                </div>
              </div>
            )}
          </div>
        </div>
      ) : complete && reportSections.length > 0 ? (
        <div className="report-doc">
          <main className="report-main">
            <div className="report-doc-head">
              <h1>Your Vedic Report</h1>
              <button className="btn btn-gold" onClick={onExport}>
                <Download size={15} /> Export PDF
              </button>
            </div>
            {reportSections.map((artifact, index) => (
              <section className="r-section" id={`section-${index}`} key={artifact.path}>
                <div className="r-tag">Section {String(index + 1).padStart(2, "0")}</div>
                <div className="r-title">{titleForArtifact(artifact)}</div>
                <MarkdownReport content={artifact.content} />
              </section>
            ))}
          </main>
          <nav className="report-toc">
            <h4>Contents</h4>
            {reportSections.map((artifact, index) => (
              <a
                key={artifact.path}
                className={activeSection === index ? "active" : ""}
                onClick={() => scrollToSection(index)}
              >
                <span className="n">{String(index + 1).padStart(2, "0")}</span>
                {titleForArtifact(artifact)}
              </a>
            ))}
          </nav>
        </div>
      ) : (
        <div className="report-generating">
          <div>
            <div className="spin" />
            <h2>{coreJob?.status === "failed" ? "Generation failed" : "Your report is being generated"}</h2>
            <p>
              {coreJob?.status === "failed"
                ? coreJob.message
                : `The full analysis runs stage by stage${
                    pipelineData ? ` — ${pipelineData.completed}/${pipelineData.total} steps done` : ""
                  }. Watch it live in the Workshop tab.`}
            </p>
            <button className="btn btn-gold" onClick={() => setTab("workshop")}>
              <Workflow size={15} /> Go to Workshop
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function resolveBirthInfo(navState: NavState, session: SkillSessionResponse | null) {
  if (navState?.birth) {
    return {
      date: navState.birth.birthDate,
      time: navState.birth.birthTime || "—",
      place: navState.birth.birthPlace,
      gender: navState.birth.gender && navState.birth.gender !== "[not-collected]" ? navState.birth.gender : ""
    };
  }
  // Fallback: parse the meta block of structured_data.md on refresh.
  const sd = session?.artifacts.find((a) => a.path === "structured_data.md")?.content ?? "";
  const grab = (label: string) => sd.match(new RegExp(`${label}:\\s*(.+)`))?.[1]?.trim() ?? "—";
  return {
    date: grab("出生日期"),
    time: grab("出生时间"),
    place: grab("出生地点"),
    gender: (() => {
      const g = grab("性别");
      return g && g !== "—" && g !== "[not-collected]" ? g : "";
    })()
  };
}
