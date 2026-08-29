import assert from "node:assert/strict";
import test from "node:test";
import { formatCoordinateValue, validateCoordinateParts } from "./coordinates";

test("manual coordinates carry an explicit WGS84 datum", () => {
  assert.equal(
    formatCoordinateValue(31.2304, 121.4737),
    "lat=31.2304, lon=121.4737, source=manual, accuracy=coordinate, coord=WGS84"
  );
});

test("manual coordinate validation still rejects out-of-range values", () => {
  assert.deepEqual(validateCoordinateParts("91", "121.4737"), {
    ok: false,
    reason: "latitude"
  });
});
