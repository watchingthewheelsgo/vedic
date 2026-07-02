import type {
  CoreJobResponse,
  PlaceSearchLevel,
  PlaceSearchResponse,
  SkillBirthInput,
  SkillFeedbackInput,
  SkillRunInput,
  SkillSessionResponse,
  SynastryBirthInput
} from "../shared/domain";
import { sessionAccessToken } from "./lib/sessionAccess";

async function postJson<TResponse, TBody>(
  path: string,
  body: TBody,
  sessionId?: string
): Promise<TResponse> {
  const response = await fetch(path, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...sessionAccessHeaders(sessionId)
    },
    body: JSON.stringify(body)
  });

  if (!response.ok) {
    const error = (await response.json().catch(() => null)) as
      | { error?: string; detail?: string }
      | null;
    throw new Error(error?.detail ?? error?.error ?? `Request failed: ${response.status}`);
  }

  return (await response.json()) as TResponse;
}

async function getJson<TResponse>(
  path: string,
  signal?: AbortSignal,
  sessionId?: string
): Promise<TResponse> {
  const response = await fetch(path, {
    signal,
    headers: sessionAccessHeaders(sessionId)
  });

  if (!response.ok) {
    const error = (await response.json().catch(() => null)) as
      | { error?: string; detail?: string }
      | null;
    throw new Error(error?.detail ?? error?.error ?? `Request failed: ${response.status}`);
  }

  return (await response.json()) as TResponse;
}

function sessionAccessHeaders(sessionId?: string): Record<string, string> {
  if (!sessionId) return {};
  const token = sessionAccessToken(sessionId);
  return token ? { "x-session-token": token } : {};
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
    return getJson<SkillSessionResponse>(
      `/api/skill-sessions/${encodeURIComponent(sessionId)}`,
      undefined,
      sessionId
    );
  },
  createSynastrySubject(input: SynastryBirthInput) {
    return postJson<SkillSessionResponse, SynastryBirthInput>(
      "/api/skill-synastry-subject",
      input,
      input.sessionId
    );
  },
  runSkill(input: SkillRunInput) {
    return postJson<SkillSessionResponse, SkillRunInput>("/api/skill-runs", input, input.sessionId);
  },
  startCoreJob(input: SkillRunInput) {
    return postJson<CoreJobResponse, SkillRunInput>("/api/core-jobs", input, input.sessionId);
  },
  getCoreJob(jobId: string, sessionId: string) {
    return getJson<CoreJobResponse>(
      `/api/core-jobs/${encodeURIComponent(jobId)}`,
      undefined,
      sessionId
    );
  },
  recordSkillFeedback(input: SkillFeedbackInput) {
    return postJson<SkillSessionResponse, SkillFeedbackInput>(
      "/api/skill-feedback",
      input,
      input.sessionId
    );
  }
};
