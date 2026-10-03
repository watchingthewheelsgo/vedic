import type { DailyGuidance } from "./journal";

export type SignTier = "radiant" | "bright" | "steady" | "gentle";

// Ten gods read as easy, supportive days in everyday almanac use.
const FAVORABLE_GODS = new Set(["正财", "正官", "正印", "食神"]);

/**
 * Today's card, scored from the BaZi day relations already shown as Good for / Avoid:
 * harmonies lift the day, clashes, punishments and harms lower it, and the user's own
 * mood pattern for this stem-branch nudges it. Deterministic, so the card never
 * contradicts the guidance beside it.
 */
export function dailySign(
  guidance: DailyGuidance,
  fit: "bright" | "steady" | "gentle" | "unknown" = "unknown"
): { tier: SignTier; score: number; reasons: string[] } {
  const { facts } = guidance;
  let score = FAVORABLE_GODS.has(facts.tenGod) ? 1 : 0;
  const reasons: string[] = [facts.tenGod];
  if (facts.stemCombination) {
    score += 1;
    reasons.push(facts.stemCombination);
  }
  const harmonies = [...facts.combinations, ...facts.trines];
  score += Math.min(2, harmonies.length);
  reasons.push(...harmonies.map((item) => item.branches));
  score -= 2 * facts.clashes.length + facts.punishments.length + facts.harms.length;
  reasons.push(
    ...[...facts.clashes, ...facts.punishments, ...facts.harms].map((item) => item.branches)
  );
  if (fit === "bright") score += 1;
  if (fit === "gentle") score -= 1;
  const tier: SignTier =
    score >= 3 ? "radiant" : score >= 2 ? "bright" : score >= 0 ? "steady" : "gentle";
  return { tier, score, reasons: [...new Set(reasons)] };
}
