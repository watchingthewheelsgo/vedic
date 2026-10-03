import assert from "node:assert/strict";
import { test } from "node:test";
import { atlasContextFor, chartLabel, uniqueCharts } from "./atlas";

test("chart labels read as a date and a place, never coordinates", () => {
  assert.equal(
    chartLabel({ birthDate: "1992-05-18", birthPlace: "Shanghai | lat=31.2" }, "en-US"),
    "May 18, 1992 · Shanghai"
  );
  assert.equal(
    chartLabel({ birthDate: "1992-05-18", birthPlace: "lat=31.2, lon=121.4" }, "en-US"),
    "May 18, 1992"
  );
});

test("one chart per person and tradition, preferring a finished one", () => {
  const charts = [
    { sessionId: "a", kind: "vedic", label: "x", completed: false },
    { sessionId: "b", kind: "vedic", label: "x", completed: true },
    { sessionId: "c", kind: "vedic", label: "x", completed: true },
    { sessionId: "d", kind: "bazi", label: "x", completed: false }
  ];
  assert.deepEqual(
    uniqueCharts(charts).map((chart) => chart.sessionId),
    ["b", "d"]
  );
});

test("reading routes get the reading context", () => {
  assert.equal(atlasContextFor("/app/charts/session_1"), "reading");
  assert.equal(atlasContextFor("/app/charts/new"), "charts");
});
