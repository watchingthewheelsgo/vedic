import assert from "node:assert/strict";
import { test } from "node:test";
import { ownerBirthFrom, ownerBirthFromProfile } from "./owner-birth";
import type { AdminSessionSummary } from "../../shared/domain";

const session = (subject: AdminSessionSummary["subject"]) =>
  ({ sessionId: "s", status: "completed", stage: "x", subject }) as AdminSessionSummary;

test("the owner's own chart wins and its details become form values", () => {
  const owner = ownerBirthFrom([
    session({ birthDate: "1990-01-01", gender: "male", relationship: "单身" }),
    session({
      birthDate: "1992-05-18",
      birthTime: "10:05",
      birthPlace: "Shanghai | lat=31.2",
      timePrecision: "exact",
      gender: "female",
      relationship: "self"
    })
  ]);
  assert.equal(owner?.birthDate.getFullYear(), 1992);
  assert.equal(owner?.birthTime?.getHours(), 10);
  assert.equal(owner?.birthTime?.getMinutes(), 5);
  assert.equal(owner?.place, "Shanghai | lat=31.2");
  assert.equal(owner?.gender, "女");
  assert.equal(owner?.timePrecision, "exact");
});

test("no birth time means an unknown-time prefill; no charts means none", () => {
  assert.equal(ownerBirthFrom([session({ birthDate: "1992-05-18" })])?.timePrecision, "unknown");
  assert.equal(ownerBirthFrom([]), null);
});

test("the onboarding profile prefills date, place and gender", () => {
  const owner = ownerBirthFromProfile({
    birthDate: "1992-05-18",
    birthTime: null,
    birthPlace: "福州市, 福建省, 中国 | lat=26.07, lon=119.3, tz=Asia/Shanghai, coord=WGS84",
    placeLabel: "福州市, 福建省, 中国",
    timezone: "Asia/Shanghai",
    gender: "女"
  });
  assert.equal(owner?.birthDate.getDate(), 18);
  assert.equal(owner?.birthTime, null);
  assert.equal(owner?.timePrecision, "unknown");
  assert.equal(owner?.gender, "女");
  assert.ok(owner?.place.startsWith("福州市"));
});
