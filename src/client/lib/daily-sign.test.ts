import assert from "node:assert/strict";
import { test } from "node:test";
import { dailySign } from "./daily-sign";
import type { DailyGuidance } from "./journal";

function guidance(facts: Partial<DailyGuidance["facts"]>): DailyGuidance {
  return {
    facts: {
      dayMaster: "甲",
      tenGod: "比肩",
      stemCombination: null,
      clashes: [],
      combinations: [],
      trines: [],
      punishments: [],
      harms: [],
      ...facts
    }
  } as unknown as DailyGuidance;
}

test("harmonies and a favorable ten god make a radiant day", () => {
  const sign = dailySign(
    guidance({
      tenGod: "正财",
      combinations: [{ natalPillar: "day", branches: "辰酉", label: "辰酉合金" }]
    }),
    "bright"
  );
  assert.equal(sign.tier, "radiant");
  assert.ok(sign.reasons.includes("辰酉"));
});

test("a clash on a plain day asks to go gently", () => {
  assert.equal(
    dailySign(guidance({ clashes: [{ natalPillar: "day", branches: "子午" }] })).tier,
    "gentle"
  );
});

test("a plain day is steady", () => {
  assert.equal(dailySign(guidance({})).tier, "steady");
});
