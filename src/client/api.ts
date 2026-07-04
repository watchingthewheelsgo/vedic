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

type AuthTokenProvider = () => Promise<string | null>;
type AnonymousIdProvider = () => string | null;

let authTokenProvider: AuthTokenProvider | null = null;
let anonymousIdProvider: AnonymousIdProvider | null = null;

export function setAuthTokenProvider(provider: AuthTokenProvider | null) {
  authTokenProvider = provider;
}

export function setAnonymousIdProvider(provider: AnonymousIdProvider | null) {
  anonymousIdProvider = provider;
}

async function authHeaders(): Promise<Record<string, string>> {
  const token = await authTokenProvider?.();
  const anonymousId = anonymousIdProvider?.();
  return {
    ...(token ? { authorization: `Bearer ${token}` } : {}),
    ...(anonymousId ? { "x-vedic-anonymous-id": anonymousId } : {})
  };
}

async function postJson<TResponse, TBody>(path: string, body: TBody): Promise<TResponse> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json", ...(await authHeaders()) },
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
  const response = await fetch(path, { headers: await authHeaders(), signal });

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
  const response = await fetch(path, { headers: await authHeaders() });
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
