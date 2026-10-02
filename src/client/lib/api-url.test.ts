import assert from "node:assert/strict";
import test from "node:test";
import { resolveApiUrl } from "./api-url";
test("routes every production API family without duplicating /api", () => {
  for (const path of [
    "/api/me",
    "/api/billing/account",
    "/api/precise-places/stream?q=Paris",
    "/api/skill-sessions/s1/report.pdf"
  ]) {
    assert.equal(
      resolveApiUrl(path, "https://api.signatlas.app/v1/"),
      "https://api.signatlas.app/v1/" + path.slice(5)
    );
    assert.equal(resolveApiUrl(path, ""), path);
  }
  assert.throws(() => resolveApiUrl("https://other.example", "https://api.signatlas.app/v1"));
});
