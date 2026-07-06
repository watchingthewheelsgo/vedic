export type CoordinateValidation =
  | {
      ok: true;
      latitude: number;
      longitude: number;
      value: string;
    }
  | {
      ok: false;
      reason: "empty" | "latitude" | "longitude" | "format";
    };

const COORDINATE_NUMBER_PATTERN = "[+-]?(?:\\d+(?:\\.\\d*)?|\\.\\d+)";
const LABELED_LATITUDE = new RegExp(
  `(?:lat|latitude|纬度|緯度)\\s*[:=]\\s*(${COORDINATE_NUMBER_PATTERN})`,
  "i"
);
const LABELED_LONGITUDE = new RegExp(
  `(?:lon|lng|longitude|经度|經度|経度)\\s*[:=]\\s*(${COORDINATE_NUMBER_PATTERN})`,
  "i"
);

export function validateCoordinateParts(
  latitudeText: string,
  longitudeText: string
): CoordinateValidation {
  const latitudeTrimmed = latitudeText.trim();
  const longitudeTrimmed = longitudeText.trim();
  if (!latitudeTrimmed && !longitudeTrimmed) {
    return { ok: false, reason: "empty" };
  }
  if (!latitudeTrimmed) {
    return { ok: false, reason: "latitude" };
  }
  if (!longitudeTrimmed) {
    return { ok: false, reason: "longitude" };
  }

  const latitude = Number(latitudeTrimmed);
  if (!Number.isFinite(latitude) || latitude < -90 || latitude > 90) {
    return { ok: false, reason: "latitude" };
  }

  const longitude = Number(longitudeTrimmed);
  if (!Number.isFinite(longitude) || longitude < -180 || longitude > 180) {
    return { ok: false, reason: "longitude" };
  }

  return {
    ok: true,
    latitude,
    longitude,
    value: formatCoordinateValue(latitude, longitude)
  };
}

export function parseCoordinateInput(value: string): CoordinateValidation {
  const trimmed = value.trim();
  if (!trimmed) return { ok: false, reason: "empty" };

  const latitudeMatch = LABELED_LATITUDE.exec(trimmed);
  const longitudeMatch = LABELED_LONGITUDE.exec(trimmed);
  if (!latitudeMatch && !longitudeMatch) {
    return { ok: false, reason: "format" };
  }
  if (!latitudeMatch) {
    return { ok: false, reason: "latitude" };
  }
  if (!longitudeMatch) {
    return { ok: false, reason: "longitude" };
  }

  return validateCoordinateParts(latitudeMatch[1], longitudeMatch[1]);
}

export function formatCoordinateValue(latitude: number, longitude: number): string {
  return `lat=${formatCoordinateNumber(latitude)}, lon=${formatCoordinateNumber(longitude)}`;
}

export function formatCoordinateNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(6)));
}
