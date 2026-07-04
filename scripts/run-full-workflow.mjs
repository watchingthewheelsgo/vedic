#!/usr/bin/env node

const apiBase = process.env.VEDIC_API_BASE ?? "http://127.0.0.1:8787";
const pollIntervalMs = Number(process.env.VEDIC_WORKFLOW_POLL_MS ?? 5000);
const timeoutMs = Number(process.env.VEDIC_WORKFLOW_TIMEOUT_MS ?? 7_200_000);

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
  console.log(`API: ${apiBase}`);

  const workflowStarted = Date.now();
  const sessionStarted = Date.now();
  const session = await postJson("/api/skill-sessions", birthInput);
  const calculatorSeconds = elapsedSeconds(sessionStarted);
  console.log(`session=${session.sessionId} calculator=${formatDuration(calculatorSeconds)}`);

  const job = await postJson("/api/core-jobs", {
    sessionId: session.sessionId,
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
  printTimingSummary(latest, calculatorSeconds, totalSeconds);
}

async function postJson(path, body) {
  const response = await fetch(`${apiBase}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body)
  });
  return readResponse(response);
}

async function getJson(path) {
  const response = await fetch(`${apiBase}${path}`);
  return readResponse(response);
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
