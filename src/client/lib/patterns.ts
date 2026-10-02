import { addDays, dayPillar } from "./sexagenary";
import type { JournalResponse } from "./journal";

// Personal auspicious days are learned only from the user's own recorded moods. A group
// counts once the backend publishes its average (at least 7 recorded days).
export const MIN_GROUP_DAYS = 7;
const SIGNAL = 0.35;

export type Fit = "bright" | "steady" | "gentle" | "unknown";
export type Signal = {
  kind: "stem" | "branch";
  key: string;
  averageMood: number;
  count: number;
  delta: number;
};
export type DayReading = { day: string; pillar: string; fit: Fit; signals: Signal[] };

type Summary = JournalResponse["summary"];

function groupSignal(summary: Summary, kind: "stem" | "branch", key: string): Signal | null {
  const baseline = summary.averageMood;
  const group = (kind === "stem" ? summary.byStem : summary.byBranch).find((g) => g.stem === key);
  if (baseline === null || !group || group.averageMood === null) return null;
  const delta = Math.round((group.averageMood - baseline) * 100) / 100;
  return { kind, key, averageMood: group.averageMood, count: group.count, delta };
}

export function readDay(day: string, summary: Summary): DayReading {
  const { stem, branch, pillar } = dayPillar(day);
  const signals = [
    groupSignal(summary, "stem", stem),
    groupSignal(summary, "branch", branch)
  ].filter((signal): signal is Signal => signal !== null);
  if (!signals.length) return { day, pillar, fit: "unknown", signals };
  const score = signals.reduce((sum, signal) => sum + signal.delta, 0);
  const fit: Fit = score >= SIGNAL ? "bright" : score <= -SIGNAL ? "gentle" : "steady";
  return { day, pillar, fit, signals };
}

export function upcoming(from: string, summary: Summary, days = 30): DayReading[] {
  return Array.from({ length: days }, (_, i) => readDay(addDays(from, i + 1), summary));
}

/** Strongest learned stem/branch associations, most pronounced first. */
export function learnedRules(summary: Summary, limit = 4): Signal[] {
  const all = [
    ...summary.byStem.map((g) => groupSignal(summary, "stem", g.stem)),
    ...summary.byBranch.map((g) => groupSignal(summary, "branch", g.stem))
  ].filter((signal): signal is Signal => signal !== null && Math.abs(signal.delta) >= SIGNAL);
  return all.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta)).slice(0, limit);
}

/** Progress toward the first learnable group: the best-covered branch or stem. */
export function unlockProgress(summary: Summary): number {
  const best = Math.max(
    0,
    ...summary.byStem.map((g) => g.count),
    ...summary.byBranch.map((g) => g.count)
  );
  return Math.min(best, MIN_GROUP_DAYS);
}
