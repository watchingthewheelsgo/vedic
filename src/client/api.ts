import type {
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
    const error = (await response.json().catch(() => null)) as
      | { error?: string; detail?: string }
      | null;
    throw new Error(error?.detail ?? error?.error ?? `Request failed: ${response.status}`);
  }

  return (await response.json()) as TResponse;
}

async function getJson<TResponse>(path: string, signal?: AbortSignal): Promise<TResponse> {
  const response = await fetch(path, { signal });

  if (!response.ok) {
    const error = (await response.json().catch(() => null)) as
      | { error?: string; detail?: string }
      | null;
    throw new Error(error?.detail ?? error?.error ?? `Request failed: ${response.status}`);
  }

  return (await response.json()) as TResponse;
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
  createSynastrySubject(input: SynastryBirthInput) {
    return postJson<SkillSessionResponse, SynastryBirthInput>(
      "/api/skill-synastry-subject",
      input
    );
  },
  runSkill(input: SkillRunInput) {
    return postJson<SkillSessionResponse, SkillRunInput>("/api/skill-runs", input);
  },
  recordSkillFeedback(input: SkillFeedbackInput) {
    return postJson<SkillSessionResponse, SkillFeedbackInput>("/api/skill-feedback", input);
  }
};
