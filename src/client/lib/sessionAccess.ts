import type { BirthInput } from "../../shared/domain";

export type RememberedSession = {
  fingerprint: string;
  sessionId: string;
  accessToken?: string | null;
  birthLabel: string;
  updatedAt: string;
};

const SESSION_CACHE_KEY = "vedic.session-cache.v1";
const SESSION_TOKEN_KEY = "vedic.session-token.v1";
const MAX_REMEMBERED_SESSIONS = 20;

export function birthFingerprint(birth: BirthInput): string {
  return `birth_${fnv1a(stableBirthPayload(birth)).toString(36)}`;
}

export function findRememberedSession(birth: BirthInput): RememberedSession | null {
  const cache = readSessionCache();
  const remembered = cache[birthFingerprint(birth)] ?? null;
  if (remembered?.accessToken) rememberSessionAccess(remembered.sessionId, remembered.accessToken);
  return remembered;
}

export function rememberSessionForBirth(
  birth: BirthInput,
  sessionId: string,
  accessToken?: string | null
) {
  const fingerprint = birthFingerprint(birth);
  const cache = readSessionCache();
  cache[fingerprint] = {
    fingerprint,
    sessionId,
    accessToken: accessToken ?? sessionAccessToken(sessionId),
    birthLabel: `${birth.birthDate} · ${birth.birthPlace}`,
    updatedAt: new Date().toISOString()
  };

  const entries = Object.values(cache).sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
  const trimmed = Object.fromEntries(entries.slice(0, MAX_REMEMBERED_SESSIONS).map((entry) => [entry.fingerprint, entry]));
  writeJson(SESSION_CACHE_KEY, trimmed);

  if (accessToken) rememberSessionAccess(sessionId, accessToken);
}

export function forgetRememberedSession(birth: BirthInput) {
  const cache = readSessionCache();
  delete cache[birthFingerprint(birth)];
  writeJson(SESSION_CACHE_KEY, cache);
}

export function rememberSessionAccess(sessionId: string, accessToken: string) {
  const tokens = readTokenCache();
  tokens[sessionId] = accessToken;
  writeJson(SESSION_TOKEN_KEY, tokens);
}

export function sessionAccessToken(sessionId: string): string | null {
  return readTokenCache()[sessionId] ?? null;
}

function stableBirthPayload(birth: BirthInput): string {
  return JSON.stringify({
    birthDate: birth.birthDate,
    birthTime: birth.birthTime,
    birthPlace: birth.birthPlace.trim().toLowerCase(),
    birthTimePrecision: birth.birthTimePrecision,
    gender: birth.gender,
    relationship: birth.relationship,
    timeSource: birth.timeSource
  });
}

function readSessionCache(): Record<string, RememberedSession> {
  return readJson<Record<string, RememberedSession>>(SESSION_CACHE_KEY, {});
}

function readTokenCache(): Record<string, string> {
  return readJson<Record<string, string>>(SESSION_TOKEN_KEY, {});
}

function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function writeJson(key: string, value: unknown) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Resume is an optimization; a full new session still works without localStorage.
  }
}

function fnv1a(value: string): number {
  let hash = 2166136261;
  for (let i = 0; i < value.length; i += 1) {
    hash ^= value.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}
