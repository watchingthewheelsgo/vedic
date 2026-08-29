import assert from "node:assert/strict";
import test from "node:test";
import {
  canStartFullReadingFromArtifacts,
  readingContinuationActionFromArtifacts
} from "./reading-continuation";

test("starts a stable chart without forcing a redundant reader round", () => {
  const state = {
    status: "not_required",
    reportGate: { fullReportAllowed: true, reportScope: "full" }
  };

  assert.equal(canStartFullReadingFromArtifacts(state, null), true);
  assert.equal(readingContinuationActionFromArtifacts(state, null), "full_report");
});

test("requires confirmation before a corrected chart can continue", () => {
  const state = {
    status: "rectification_confirmation_required",
    holdoutResult: "passed",
    reportGate: { fullReportAllowed: true },
    rectificationConclusion: { confirmation: { status: "pending" } }
  };

  assert.equal(canStartFullReadingFromArtifacts(state, null), false);
  assert.equal(readingContinuationActionFromArtifacts(state, null), "confirm_rectification");
});

test("requires a passed holdout for selected or equivalent candidates", () => {
  const corrected = {
    status: "corrected_chart_ready",
    holdoutResult: "failed",
    reportGate: { fullReportAllowed: true }
  };
  const equivalent = {
    status: "multiple_equivalent",
    holdoutResult: "passed",
    reportGate: { fullReportAllowed: true, reportScope: "stable_intersection_only" }
  };

  assert.equal(canStartFullReadingFromArtifacts(corrected, null), false);
  assert.equal(canStartFullReadingFromArtifacts(equivalent, null), true);
});

test("does not let a stale prevalidation decision bypass rectification", () => {
  const state = {
    status: "corrected_chart_ready",
    holdoutResult: "failed",
    reportGate: { fullReportAllowed: true }
  };
  const stalePrevalidation = {
    decision: { reportAllowed: true, reportScope: "guarded_full_report" }
  };

  assert.equal(canStartFullReadingFromArtifacts(state, stalePrevalidation), false);
  assert.equal(readingContinuationActionFromArtifacts(state, stalePrevalidation), "stop");
});

test("collects one more event only when the backend plan requests it", () => {
  const state = {
    status: "underdetermined",
    rectificationPlan: { eventCollectionRequired: true }
  };

  assert.equal(readingContinuationActionFromArtifacts(state, null), "collect_events");
  assert.equal(
    readingContinuationActionFromArtifacts(null, {
      decision: { nextStep: "review_birth_details_or_stop" }
    }),
    "stop"
  );
});
