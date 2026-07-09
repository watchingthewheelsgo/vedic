import type {
  AccountProfileResponse,
  AdminSessionDetailResponse,
  AdminSessionListResponse,
  BillingAccountResponse,
  BillingCheckoutInput,
  BillingCheckoutResponse,
  BillingPortalResponse,
  BaziSessionInput,
  CoreJobResponse,
  PlaceSearchLevel,
  PlaceSearchResponse,
  PrecisePlaceSearchResponse,
  SkillBirthInput,
  SkillFeedbackInput,
  SkillRunInput,
  SkillSessionResponse,
  SynastryBirthInput
} from "../shared/domain";

type AuthTokenProvider = () => Promise<string | null>;
type AnonymousIdProvider = () => string | null;
type AuthFailureHandler = (failure: { status: number; detail: string }) => void | Promise<void>;
const AUTH_EXPIRED_MESSAGE = "Your session expired. Please sign in again.";
const AUTH_REQUIRED_MESSAGE = "Sign in to continue";

let authTokenProvider: AuthTokenProvider | null = null;
let anonymousIdProvider: AnonymousIdProvider | null = null;
let authFailureHandler: AuthFailureHandler | null = null;

export function setAuthTokenProvider(provider: AuthTokenProvider | null) {
  authTokenProvider = provider;
}

export function setAnonymousIdProvider(provider: AnonymousIdProvider | null) {
  anonymousIdProvider = provider;
}

export function setAuthFailureHandler(handler: AuthFailureHandler | null) {
  authFailureHandler = handler;
}

async function authHeaders({
  requireToken = false
}: {
  requireToken?: boolean;
} = {}): Promise<Record<string, string>> {
  let token: string | null | undefined = null;
  let tokenError: unknown = null;
  try {
    token = await authTokenProvider?.();
  } catch (caught) {
    tokenError = caught;
  }
  if (requireToken && !token) {
    throw new Error(tokenError instanceof Error ? tokenError.message : AUTH_REQUIRED_MESSAGE);
  }
  const anonymousId = anonymousIdProvider?.();
  return {
    ...(token ? { authorization: `Bearer ${token}` } : {}),
    ...(anonymousId ? { "x-vedic-anonymous-id": anonymousId } : {})
  };
}

function isAuthFailure(status: number, detail: string) {
  if (status !== 401) return false;
  return [
    "Invalid Clerk session token",
    "Clerk session token is missing a subject",
    "Expected Bearer token",
    AUTH_EXPIRED_MESSAGE
  ].includes(detail);
}

async function notifyAuthFailure(status: number, detail: string) {
  try {
    await authFailureHandler?.({ status, detail });
  } catch {
    // Do not mask the original API failure if sign-out cleanup itself fails.
  }
}

async function throwApiError(response: Response): Promise<never> {
  const error = (await response.json().catch(() => null)) as {
    error?: string;
    detail?: string;
  } | null;
  const detail = error?.detail ?? error?.error ?? `Request failed: ${response.status}`;
  if (isAuthFailure(response.status, detail)) {
    await notifyAuthFailure(response.status, detail);
    throw new Error(AUTH_EXPIRED_MESSAGE);
  }
  throw new Error(detail);
}

async function postJson<TResponse, TBody>(
  path: string,
  body: TBody,
  options: { requireAuth?: boolean } = {}
): Promise<TResponse> {
  const response = await fetch(path, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(await authHeaders({ requireToken: options.requireAuth }))
    },
    body: JSON.stringify(body)
  });

  if (!response.ok) {
    await throwApiError(response);
  }

  return (await response.json()) as TResponse;
}

async function getJson<TResponse>(
  path: string,
  signal?: AbortSignal,
  options: { requireAuth?: boolean } = {}
): Promise<TResponse> {
  const response = await fetch(path, {
    headers: await authHeaders({ requireToken: options.requireAuth }),
    signal
  });

  if (!response.ok) {
    await throwApiError(response);
  }

  return (await response.json()) as TResponse;
}

async function downloadFile(path: string, filename: string): Promise<void> {
  const response = await fetch(path, { headers: await authHeaders({ requireToken: true }) });
  if (!response.ok) {
    await throwApiError(response);
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
  searchPrecisePlaces(input: { q: string; city?: string; limit?: number }, signal?: AbortSignal) {
    const params = new URLSearchParams();
    params.set("q", input.q);
    if (input.city) params.set("city", input.city);
    if (input.limit) params.set("limit", String(input.limit));
    return getJson<PrecisePlaceSearchResponse>(`/api/precise-places?${params.toString()}`, signal);
  },
  createSkillSession(input: SkillBirthInput) {
    return postJson<SkillSessionResponse, SkillBirthInput>("/api/skill-sessions", input);
  },
  createBaziSession(input: BaziSessionInput) {
    return postJson<SkillSessionResponse, BaziSessionInput>("/api/bazi-sessions", input);
  },
  getMe() {
    return getJson<AccountProfileResponse>("/api/me", undefined, { requireAuth: true });
  },
  getBillingAccount() {
    return getJson<BillingAccountResponse>("/api/billing/account", undefined, {
      requireAuth: true
    });
  },
  createBillingCheckout(input: BillingCheckoutInput) {
    return postJson<BillingCheckoutResponse, BillingCheckoutInput>("/api/billing/checkout", input, {
      requireAuth: true
    });
  },
  createBillingPortal() {
    return postJson<BillingPortalResponse, Record<string, never>>(
      "/api/billing/portal",
      {},
      {
        requireAuth: true
      }
    );
  },
  listMySessions() {
    return getJson<AdminSessionListResponse>("/api/me/sessions", undefined, { requireAuth: true });
  },
  getSkillSession(sessionId: string) {
    return getJson<SkillSessionResponse>(`/api/skill-sessions/${encodeURIComponent(sessionId)}`);
  },
  listAdminSessions() {
    return getJson<AdminSessionListResponse>("/api/admin/sessions", undefined, {
      requireAuth: true
    });
  },
  getAdminSession(sessionId: string) {
    return getJson<AdminSessionDetailResponse>(
      `/api/admin/sessions/${encodeURIComponent(sessionId)}`,
      undefined,
      { requireAuth: true }
    );
  },
  createSynastrySubject(input: SynastryBirthInput) {
    return postJson<SkillSessionResponse, SynastryBirthInput>(
      "/api/skill-synastry-subject",
      input,
      {
        requireAuth: true
      }
    );
  },
  runSkill(input: SkillRunInput) {
    return postJson<SkillSessionResponse, SkillRunInput>("/api/skill-runs", input, {
      requireAuth: input.skill !== "vedic-reader"
    });
  },
  startCoreJob(input: SkillRunInput) {
    return postJson<CoreJobResponse, SkillRunInput>("/api/core-jobs", input, {
      requireAuth: true
    });
  },
  getCoreJob(jobId: string) {
    return getJson<CoreJobResponse>(`/api/core-jobs/${encodeURIComponent(jobId)}`, undefined, {
      requireAuth: true
    });
  },
  recordSkillFeedback(input: SkillFeedbackInput) {
    return postJson<SkillSessionResponse, SkillFeedbackInput>("/api/skill-feedback", input, {
      requireAuth: true
    });
  },
  downloadReportPdf(sessionId: string) {
    return downloadFile(
      `/api/skill-sessions/${encodeURIComponent(sessionId)}/report.pdf`,
      `vedic-report-${sessionId}.pdf`
    );
  }
};
