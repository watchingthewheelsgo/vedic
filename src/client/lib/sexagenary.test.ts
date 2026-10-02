import assert from "node:assert/strict";
import { test } from "node:test";
import { addDays, dayPillar, monthDays, stemElement, weekdayIndex } from "./sexagenary";

test("day pillars match published charts", () => {
  assert.equal(dayPillar("1949-10-01").pillar, "甲子");
  assert.equal(dayPillar("2026-10-02").pillar, "己酉");
  assert.equal(dayPillar("1955-02-24").pillar, "丙辰");
  assert.equal(dayPillar("1879-03-14").pillar, "丙申");
  assert.equal(dayPillar("1940-11-27").pillar, "甲戌");
  assert.equal(dayPillar("1900-01-31").pillar, "甲辰");
});

test("calendar helpers", () => {
  assert.equal(addDays("2026-10-31", 1), "2026-11-01");
  assert.equal(weekdayIndex("2026-10-01"), 3);
  assert.equal(monthDays(2028, 2).length, 29);
  assert.equal(stemElement("己"), "earth");
});

test("famous chart day pillars agree with the calculator", async () => {
  const { famousCharts } = await import("./famous-charts");
  for (const chart of famousCharts) {
    assert.equal(dayPillar(chart.born.slice(0, 10)).pillar, chart.pillars[2], chart.id);
  }
});
