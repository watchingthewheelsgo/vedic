import assert from "node:assert/strict";
import { test } from "node:test";
import { learnedRules, readDay, unlockProgress, upcoming } from "./patterns";

const summary = {
  recordedDays: 40,
  averageMood: 3.4,
  byStem: [
    { stem: "甲", count: 9, averageMood: 4.2 },
    { stem: "己", count: 8, averageMood: 3.5 },
    { stem: "丙", count: 3, averageMood: null }
  ],
  byBranch: [
    { stem: "子", count: 7, averageMood: 2.6 },
    { stem: "酉", count: 7, averageMood: 3.4 }
  ],
  byPillar: []
};

test("a day is bright when its learned groups beat the baseline", () => {
  const reading = readDay("2026-10-07", summary); // 甲寅
  assert.equal(reading.pillar, "甲寅");
  assert.equal(reading.fit, "bright");
  assert.equal(reading.signals[0].delta, 0.8);
});

test("clashing signals and missing groups", () => {
  assert.equal(readDay("2026-10-17", summary).fit, "steady"); // 甲子: +0.8 and -0.8
  assert.equal(readDay("2026-10-05", summary).fit, "gentle"); // 壬子
  assert.equal(readDay("2026-10-09", summary).fit, "unknown"); // 丙辰
  assert.equal(readDay("2026-10-02", summary).fit, "steady"); // 己酉
});

test("rules, progress and lookahead", () => {
  assert.deepEqual(
    learnedRules(summary).map((rule) => rule.key),
    ["甲", "子"]
  );
  assert.equal(
    unlockProgress({
      ...summary,
      byStem: [],
      byBranch: [{ stem: "子", count: 3, averageMood: null }]
    }),
    3
  );
  assert.equal(upcoming("2026-10-02", summary, 5)[4].day, "2026-10-07");
});
