import type { BirthTimePrecision } from "../../shared/domain";

const pad = (n: number) => String(n).padStart(2, "0");

export function formatBirthTime(date: Date | null, precision: BirthTimePrecision): string {
  if (!date) return "";
  const hour = date.getHours();
  const minute = precision === "part_of_day" ? 0 : date.getMinutes();
  return `${pad(hour)}:${pad(minute)}`;
}

export function makeBirthTime(hour: number, minute: number): Date {
  const next = new Date();
  next.setHours(hour, minute, 0, 0);
  return next;
}

export function normalizeTimeForPrecision(
  date: Date | null,
  precision: BirthTimePrecision
): Date | null {
  if (!date || precision === "unknown") return null;
  const next = new Date(date);
  next.setMinutes(normalizeMinuteForPrecision(next.getMinutes(), precision), 0, 0);
  return next;
}

export function normalizeMinuteForPrecision(minute: number, precision: BirthTimePrecision): number {
  if (precision === "part_of_day") return 0;
  if (precision === "approximate") return Math.min(45, Math.round(minute / 15) * 15);
  return Math.max(0, Math.min(59, minute));
}

export function formatTimeLabel(date: Date, precision: BirthTimePrecision): string {
  return formatBirthTime(date, precision);
}

export function padTimeUnit(value: number): string {
  return pad(value);
}
