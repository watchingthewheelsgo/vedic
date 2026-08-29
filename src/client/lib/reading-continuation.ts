export type ReadingContinuationAction =
  "full_report" | "reader" | "collect_events" | "confirm_rectification" | "reset_events" | "stop";

type JsonObject = Record<string, unknown>;

export function canStartFullReadingFromArtifacts(
  state: JsonObject | null,
  prevalidationResult: JsonObject | null
): boolean {
  if (state) {
    const status = String(state.status ?? "").trim();
    const conclusion = objectValue(state, "rectificationConclusion");
    const confirmation = objectValue(conclusion, "confirmation");
    if (status === "rectification_confirmation_required" || confirmation?.status === "pending") {
      return false;
    }
    const gate = objectValue(state, "reportGate");
    if (status === "not_required" && gate?.fullReportAllowed === true) return true;
    if (
      status === "corrected_chart_ready" &&
      state.holdoutResult === "passed" &&
      gate?.fullReportAllowed === true
    ) {
      return true;
    }
    if (
      status === "multiple_equivalent" &&
      state.holdoutResult === "passed" &&
      gate?.fullReportAllowed === true &&
      gate.reportScope === "stable_intersection_only"
    ) {
      return true;
    }
    if (status) return false;
  }
  const decision = objectValue(prevalidationResult, "decision");
  return decision?.reportAllowed === true && decision.reportScope !== "prevalidation_or_d1_only";
}

export function readingContinuationActionFromArtifacts(
  state: JsonObject | null,
  prevalidationResult: JsonObject | null
): ReadingContinuationAction {
  if (state) {
    const status = String(state.status ?? "").trim();
    const conclusion = objectValue(state, "rectificationConclusion");
    const confirmation = objectValue(conclusion, "confirmation");
    if (status === "rectification_confirmation_required" || confirmation?.status === "pending") {
      return "confirm_rectification";
    }
  }

  if (canStartFullReadingFromArtifacts(state, prevalidationResult)) return "full_report";

  const prevalidationDecision = objectValue(prevalidationResult, "decision");
  if (prevalidationDecision?.nextStep === "review_birth_details_or_stop") return "stop";
  if (!state) return "reader";

  const status = String(state.status ?? "").trim();
  const plan = objectValue(state, "rectificationPlan");
  const action = String(plan?.action ?? "").trim();
  if (action === "reset_rectification_evidence") return "reset_events";
  if (
    status === "collecting_evidence" ||
    action === "collect_dated_life_events" ||
    (status === "underdetermined" && plan?.eventCollectionRequired === true)
  ) {
    return "collect_events";
  }
  return "stop";
}

function objectValue(value: unknown, key: string): JsonObject | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const next = (value as JsonObject)[key];
  return next && typeof next === "object" && !Array.isArray(next) ? (next as JsonObject) : null;
}
