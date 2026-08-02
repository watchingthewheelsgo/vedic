#!/usr/bin/env node

const apiBase = process.env.VEDIC_API_BASE ?? "http://127.0.0.1:8787";
const pollIntervalMs = Number(process.env.VEDIC_WORKFLOW_POLL_MS ?? 5000);
const timeoutMs = Number(process.env.VEDIC_WORKFLOW_TIMEOUT_MS ?? 7_200_000);
const authToken = process.env.VEDIC_WORKFLOW_AUTH_TOKEN?.trim() ?? "";
const prevalidationFeedback = readPrevalidationFeedback();
const rectificationEvents = readRectificationEvents();

const requiredPublicArtifacts = [
  "chart_record.json",
  "consultation_dossier.json",
  "consultation_report_manifest.json",
  "agent_context.json",
  "consultation_report.md"
];

const birthInput = {
  birthDate: process.env.VEDIC_TEST_BIRTH_DATE ?? "2002-12-11",
  birthTime: process.env.VEDIC_TEST_BIRTH_TIME ?? "20:47",
  birthPlace: process.env.VEDIC_TEST_BIRTH_PLACE ?? "lat=25.4333, lon=119.0, tz=Asia/Shanghai",
  birthTimePrecision: process.env.VEDIC_TEST_BIRTH_PRECISION ?? "exact",
  gender: process.env.VEDIC_TEST_GENDER ?? "[not-collected]",
  relationship: process.env.VEDIC_TEST_RELATIONSHIP ?? "[not-collected]",
  timeSource: "workflow-smoke-test"
};

async function main() {
  if (!authToken) {
    throw new Error(
      "VEDIC_WORKFLOW_AUTH_TOKEN is required. Use a Clerk token for a paid or admin test account."
    );
  }
  console.log(`API: ${apiBase}`);

  const workflowStarted = Date.now();
  const sessionStarted = Date.now();
  const session = await postJson("/api/skill-sessions", birthInput);
  const calculatorSeconds = elapsedSeconds(sessionStarted);
  console.log(`session=${session.sessionId} calculator=${formatDuration(calculatorSeconds)}`);

  const validatedSession = await completePrevalidation(session);

  const job = await postJson("/api/core-jobs", {
    sessionId: validatedSession.sessionId,
    skill: "vedic-core",
    userMessage: "开始完整报告生成，并记录每个阶段耗时。"
  });
  console.log(`job=${job.jobId} status=${job.status}`);

  let latest = job;
  let lastProgress = "";
  while (latest.status === "queued" || latest.status === "running") {
    if (Date.now() - workflowStarted > timeoutMs) {
      throw new Error(`workflow timed out after ${formatDuration(timeoutMs / 1000)}`);
    }
    await sleep(pollIntervalMs);
    latest = await getJson(`/api/core-jobs/${encodeURIComponent(job.jobId)}`);
    const progressKey = `${latest.progress.completed}/${latest.progress.total}/${latest.progress.running}/${latest.progress.failed}`;
    if (progressKey !== lastProgress) {
      lastProgress = progressKey;
      console.log(
        `progress=${latest.progress.completed}/${latest.progress.total} running=${latest.progress.running} failed=${latest.progress.failed} elapsed=${formatDuration(latest.durationSeconds)}`
      );
    }
  }

  if (latest.status !== "completed") {
    printTimingSummary(latest, calculatorSeconds, elapsedSeconds(workflowStarted));
    throw new Error(`workflow failed: ${latest.message}`);
  }

  const totalSeconds = elapsedSeconds(workflowStarted);
  verifyPublicArtifacts(latest);
  printTimingSummary(latest, calculatorSeconds, totalSeconds);
}

async function completePrevalidation(initialSession) {
  let session = initialSession;
  let state = rectificationState(session);

  if (state?.status === "collecting_evidence") {
    if (!rectificationEvents.length) {
      throw new Error(
        "This fixture needs birth-time rectification. Set VEDIC_WORKFLOW_EVENTS_JSON to 3-5 " +
          "dated event objects with date, category, and description."
      );
    }
    session = await postJson("/api/rectification-life-events", {
      sessionId: session.sessionId,
      events: rectificationEvents
    });
    state = rectificationState(session);
    console.log(`rectification status=${state?.status ?? "unknown"}`);
  }

  if (canStartFullReading(session)) return session;
  if (state?.status !== "not_required") {
    throw new Error(
      `Deterministic rectification stopped at status=${state?.status ?? "unknown"}; ` +
        `next=${state?.reportGate?.nextStep ?? "inspect chart_rectification_state.json"}.`
    );
  }

  session = await postJson("/api/skill-runs", {
    sessionId: session.sessionId,
    skill: "vedic-reader",
    userMessage: "",
    locale: birthInput.locale ?? "en"
  });
  console.log("reader status=questions_ready");
  if (canStartFullReading(session)) return session;
  if (!prevalidationFeedback) {
    throw new Error(
      "The scan-stable chart still needs one reading-quality response. Set " +
        "VEDIC_WORKFLOW_FEEDBACK to markdown answers for reader_prevalidation.md."
    );
  }
  session = await postJson("/api/skill-feedback", {
    sessionId: session.sessionId,
    feedbackMarkdown: prevalidationFeedback
  });
  if (!canStartFullReading(session)) {
    throw new Error("Reader prevalidation did not permit a full report.");
  }
  return session;
}

async function postJson(path, body) {
  const response = await fetch(`${apiBase}${path}`, {
    method: "POST",
    headers: requestHeaders({ json: true }),
    body: JSON.stringify(body)
  });
  return readResponse(response);
}

async function getJson(path) {
  const response = await fetch(`${apiBase}${path}`, { headers: requestHeaders() });
  return readResponse(response);
}

function requestHeaders({ json = false } = {}) {
  return {
    ...(json ? { "content-type": "application/json" } : {}),
    authorization: `Bearer ${authToken}`
  };
}

function parseArtifact(session, path) {
  const artifact = session?.artifacts?.find((item) => item.path === path);
  if (!artifact?.content) return null;
  try {
    const parsed = JSON.parse(artifact.content);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function canStartFullReading(session) {
  const state = rectificationState(session);
  if (
    state?.reportGate?.fullReportAllowed === true &&
    String(state.status ?? "") === "corrected_chart_ready"
  ) {
    return true;
  }
  const decision = parseArtifact(session, "prevalidation_result.json")?.decision;
  return decision?.reportAllowed === true && decision.reportScope !== "prevalidation_or_d1_only";
}

function rectificationState(session) {
  return parseArtifact(session, "chart_rectification_state.json");
}

function readPrevalidationFeedback() {
  const single = process.env.VEDIC_WORKFLOW_FEEDBACK?.trim();
  if (single) return single;
  const legacyJson = process.env.VEDIC_WORKFLOW_FEEDBACK_JSON?.trim();
  if (!legacyJson) return "";
  const parsed = parseJsonEnv("VEDIC_WORKFLOW_FEEDBACK_JSON", legacyJson);
  if (!Array.isArray(parsed) || typeof parsed[0] !== "string") {
    throw new Error("VEDIC_WORKFLOW_FEEDBACK_JSON must contain at least one markdown string.");
  }
  return parsed[0].trim();
}

function readRectificationEvents() {
  const json = process.env.VEDIC_WORKFLOW_EVENTS_JSON?.trim();
  if (!json) return [];
  const parsed = parseJsonEnv("VEDIC_WORKFLOW_EVENTS_JSON", json);
  if (!Array.isArray(parsed) || parsed.length < 3 || parsed.length > 5) {
    throw new Error("VEDIC_WORKFLOW_EVENTS_JSON must be a JSON array with 3-5 event objects.");
  }
  for (const event of parsed) {
    if (
      !event ||
      typeof event !== "object" ||
      typeof event.date !== "string" ||
      typeof event.category !== "string" ||
      typeof event.description !== "string"
    ) {
      throw new Error(
        "Each VEDIC_WORKFLOW_EVENTS_JSON item needs string date, category, and description."
      );
    }
  }
  return parsed;
}

function parseJsonEnv(name, value) {
  try {
    return JSON.parse(value);
  } catch (error) {
    throw new Error(
      `${name} must be valid JSON: ${error instanceof Error ? error.message : String(error)}`,
      { cause: error }
    );
  }
}

function verifyPublicArtifacts(job) {
  const paths = job.session?.artifacts?.map((artifact) => artifact.path) ?? [];
  const missing = requiredPublicArtifacts.filter((path) => !paths.includes(path));
  if (missing.length) {
    throw new Error(`Workflow completed without required public artifacts: ${missing.join(", ")}`);
  }
  const leaked = paths.filter((path) => path === ".runtime" || path.startsWith(".runtime/"));
  if (leaked.length) {
    throw new Error(
      `Internal runtime artifacts leaked through the public API: ${leaked.join(", ")}`
    );
  }
}

async function readResponse(response) {
  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;
  if (!response.ok) {
    throw new Error(payload?.detail ?? payload?.error ?? `HTTP ${response.status}`);
  }
  return payload;
}

function printTimingSummary(job, calculatorSeconds, totalSeconds) {
  const publicArtifacts = job.session?.artifacts?.map((artifact) => artifact.path) ?? [];
  const slowest = [...job.nodes]
    .filter((node) => node.durationSeconds != null)
    .sort((a, b) => (b.durationSeconds ?? 0) - (a.durationSeconds ?? 0))
    .slice(0, 8);

  console.log("\nWorkflow timing summary");
  console.log(`session=${job.sessionId}`);
  console.log(`job=${job.jobId}`);
  console.log(`status=${job.status}`);
  console.log(`calculator=${formatDuration(calculatorSeconds)}`);
  console.log(`core=${formatDuration(job.durationSeconds)}`);
  console.log(`total=${formatDuration(totalSeconds)}`);
  console.log("\nWaves");
  for (const wave of job.waves) {
    console.log(
      `wave ${wave.wave}: ${wave.completed}/${wave.total} completed, failed=${wave.failed}, duration=${formatDuration(wave.durationSeconds)}`
    );
  }
  console.log("\nSlowest nodes");
  for (const node of slowest) {
    console.log(
      `${node.id} wave=${node.wave} status=${node.status} duration=${formatDuration(node.durationSeconds)}`
    );
  }
  console.log("\nPublic artifacts");
  for (const path of publicArtifacts) {
    console.log(path);
  }
}

function elapsedSeconds(startedMs) {
  return Math.round((Date.now() - startedMs) / 100) / 10;
}

function formatDuration(seconds) {
  if (seconds == null) return "n/a";
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`;
  const minutes = Math.floor(seconds / 60);
  const remaining = Math.round(seconds % 60);
  if (minutes < 60) return `${minutes}m ${remaining}s`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ${minutes % 60}m`;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

main().catch((error) => {
  if (error instanceof Error) {
    console.error(error.stack ?? error.message);
    if ("cause" in error && error.cause) {
      console.error("cause:", error.cause);
    }
  } else {
    console.error(error);
  }
  process.exit(1);
});
