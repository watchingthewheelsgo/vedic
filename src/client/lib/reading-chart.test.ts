import assert from "node:assert/strict";
import { test } from "node:test";
import { readingChartFrom } from "./reading-chart";

const pos = (signIndex: number, nakshatra?: string) => ({
  position: { signIndex, nakshatra: nakshatra ? { name: nakshatra } : undefined }
});
const record = (changedFields: string[]) => ({
  inputSensitivity: { changedFields },
  charts: [
    {
      vargaId: "D1",
      lagna: pos(3),
      placements: [
        { objectId: "Moon", ...pos(7, "Jyeshtha") },
        { objectId: "Sun", ...pos(1) }
      ]
    }
  ]
});

test("the chart hero shows D1 signs that hold across the birth window", () => {
  const chart = readingChartFrom(record(["lagnaDegree"]));
  assert.equal(chart?.lagna, 3);
  assert.equal(chart?.moon?.nakshatra, "Jyeshtha");
  assert.equal(chart?.sun?.signIndex, 1);
});

test("an unstable rising sign hides the chart; an unstable nakshatra hides only it", () => {
  assert.equal(readingChartFrom(record(["lagnaSign"])), null);
  assert.equal(readingChartFrom(record(["moonNakshatra"]))?.moon?.nakshatra, undefined);
});
