import test from "node:test";
import assert from "node:assert/strict";
import { safeWorkspaceReturn } from "./workspace";

test("login preserves local workspace intent without open redirects", () => {
  assert.equal(safeWorkspaceReturn("/app/explore?day=2026-10-02"), "/app/explore?day=2026-10-02");
  assert.equal(safeWorkspaceReturn("/app/charts/new"), "/app/charts/new");
  for (const value of [
    null,
    "https://evil.example",
    "//evil.example",
    "/app\\evil",
    "/application",
    "/welcome",
    "/app\n"
  ]) {
    assert.equal(safeWorkspaceReturn(value), "/app");
  }
});
