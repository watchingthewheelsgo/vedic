type Json = Record<string, unknown>;

function obj(value: unknown): Json | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Json) : null;
}

type Position = { signIndex: number; nakshatra?: string };

function position(value: unknown): Position | null {
  const pos = obj(obj(value)?.position);
  const signIndex = Number(pos?.signIndex);
  if (!pos || !Number.isInteger(signIndex)) return null;
  const nakshatra = obj(pos.nakshatra)?.name;
  return { signIndex, nakshatra: typeof nakshatra === "string" ? nakshatra : undefined };
}

/** D1 signs, only when they hold across the whole reported birth window. */
export function readingChartFrom(record: Json | null) {
  if (!record) return null;
  const changed = new Set(
    (obj(record.inputSensitivity)?.changedFields as string[] | undefined) ?? []
  );
  if (changed.has("lagnaSign") || changed.has("d1Structure")) return null;
  if ([...changed].some((field) => field.startsWith("planetSign"))) return null;
  const charts = Array.isArray(record.charts) ? record.charts.map(obj) : [];
  const d1 = charts.find((chart) => chart?.vargaId === "D1");
  const lagna = position(d1?.lagna);
  if (!d1 || !lagna) return null;
  const placements = new Map<string, Position>();
  for (const item of Array.isArray(d1.placements) ? d1.placements : []) {
    const id = obj(item)?.objectId;
    const pos = position(item);
    if (typeof id === "string" && pos) placements.set(id, pos);
  }
  const moon = placements.get("Moon");
  return {
    lagna: lagna.signIndex,
    moon: moon && {
      ...moon,
      nakshatra: changed.has("moonNakshatra") ? undefined : moon.nakshatra
    },
    sun: placements.get("Sun"),
    placements
  };
}

export type ReadingChartData = NonNullable<ReturnType<typeof readingChartFrom>>;
