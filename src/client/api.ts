import type {
  AdminSessionDetailResponse,
  AdminSessionListResponse,
  CoreJobResponse,
  PlaceSearchLevel,
  PlaceSearchResponse,
  SkillBirthInput,
  SkillFeedbackInput,
  SkillRunInput,
  SkillSessionResponse,
  SynastryBirthInput
} from "../shared/domain";

async function postJson<TResponse, TBody>(path: string, body: TBody): Promise<TResponse> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body)
  });

  if (!response.ok) {
    const error = (await response.json().catch(() => null)) as {
      error?: string;
      detail?: string;
    } | null;
    throw new Error(error?.detail ?? error?.error ?? `Request failed: ${response.status}`);
  }

  return (await response.json()) as TResponse;
}

async function getJson<TResponse>(path: string, signal?: AbortSignal): Promise<TResponse> {
  const response = await fetch(path, { signal });

  if (!response.ok) {
    const error = (await response.json().catch(() => null)) as {
      error?: string;
      detail?: string;
    } | null;
    throw new Error(error?.detail ?? error?.error ?? `Request failed: ${response.status}`);
  }

  return (await response.json()) as TResponse;
}

async function downloadFile(path: string, filename: string): Promise<void> {
  const response = await fetch(path);
  if (!response.ok) {
    const error = (await response.json().catch(() => null)) as {
      error?: string;
      detail?: string;
    } | null;
    throw new Error(error?.detail ?? error?.error ?? `Request failed: ${response.status}`);
  }

  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(url);
}

export const api = {
  searchPlaces(
    input: {
      level: PlaceSearchLevel;
      q?: string;
      country?: string;
      region?: string;
      limit?: number;
    },
    signal?: AbortSignal
  ) {
    const params = new URLSearchParams();
    params.set("level", input.level);
    if (input.q) params.set("q", input.q);
    if (input.country) params.set("country", input.country);
    if (input.region) params.set("region", input.region);
    if (input.limit) params.set("limit", String(input.limit));
    return getJson<PlaceSearchResponse>(`/api/places?${params.toString()}`, signal);
  },
  createSkillSession(input: SkillBirthInput) {
    return postJson<SkillSessionResponse, SkillBirthInput>("/api/skill-sessions", input);
  },
  getSkillSession(sessionId: string) {
    return getJson<SkillSessionResponse>(`/api/skill-sessions/${encodeURIComponent(sessionId)}`);
  },
  listAdminSessions() {
    return getJson<AdminSessionListResponse>("/api/admin/sessions");
  },
  getAdminSession(sessionId: string) {
    return getJson<AdminSessionDetailResponse>(
      `/api/admin/sessions/${encodeURIComponent(sessionId)}`
    );
  },
  createSynastrySubject(input: SynastryBirthInput) {
    return postJson<SkillSessionResponse, SynastryBirthInput>("/api/skill-synastry-subject", input);
  },
  runSkill(input: SkillRunInput) {
    return postJson<SkillSessionResponse, SkillRunInput>("/api/skill-runs", input);
  },
  startCoreJob(input: SkillRunInput) {
    return postJson<CoreJobResponse, SkillRunInput>("/api/core-jobs", input);
  },
  getCoreJob(jobId: string) {
    return getJson<CoreJobResponse>(`/api/core-jobs/${encodeURIComponent(jobId)}`);
  },
  recordSkillFeedback(input: SkillFeedbackInput) {
    return postJson<SkillSessionResponse, SkillFeedbackInput>("/api/skill-feedback", input);
  },
  downloadReportPdf(sessionId: string) {
    return downloadFile(
      `/api/skill-sessions/${encodeURIComponent(sessionId)}/report.pdf`,
      `vedic-report-${sessionId}.pdf`
    );
  }
};
