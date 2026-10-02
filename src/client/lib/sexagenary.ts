// Civil-date stem-branch helpers for calendar display. The backend remains the source of
// truth for saved entries; these only label days that have no saved record yet.
export const STEMS = "甲乙丙丁戊己庚辛壬癸";
export const BRANCHES = "子丑寅卯辰巳午未申酉戌亥";

export type Element = "wood" | "fire" | "earth" | "metal" | "water";

const STEM_ELEMENTS: Element[] = [
  "wood",
  "wood",
  "fire",
  "fire",
  "earth",
  "earth",
  "metal",
  "metal",
  "water",
  "water"
];
const BRANCH_ELEMENTS: Element[] = [
  "water",
  "earth",
  "wood",
  "wood",
  "earth",
  "fire",
  "fire",
  "earth",
  "metal",
  "metal",
  "earth",
  "water"
];

// 1949-10-01 is a 甲子 day.
const ANCHOR = Date.UTC(1949, 9, 1);
const DAY_MS = 86_400_000;

export type DayPillar = { stem: string; branch: string; pillar: string };

export function parseDay(day: string): number {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(day);
  if (!match) throw new Error(`Invalid day: ${day}`);
  return Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
}

export function formatDay(utc: number): string {
  return new Date(utc).toISOString().slice(0, 10);
}

export function addDays(day: string, amount: number): string {
  return formatDay(parseDay(day) + amount * DAY_MS);
}

export function dayPillar(day: string): DayPillar {
  const offset = Math.round((parseDay(day) - ANCHOR) / DAY_MS);
  const index = ((offset % 60) + 60) % 60;
  const stem = STEMS[index % 10];
  const branch = BRANCHES[index % 12];
  return { stem, branch, pillar: stem + branch };
}

export function stemElement(stem: string): Element {
  return STEM_ELEMENTS[STEMS.indexOf(stem)];
}

export function branchElement(branch: string): Element {
  return BRANCH_ELEMENTS[BRANCHES.indexOf(branch)];
}

/** Monday-first weekday index, 0..6. */
export function weekdayIndex(day: string): number {
  return (new Date(parseDay(day)).getUTCDay() + 6) % 7;
}

export function monthDays(year: number, month: number): string[] {
  const count = new Date(Date.UTC(year, month, 0)).getUTCDate();
  return Array.from({ length: count }, (_, i) => formatDay(Date.UTC(year, month - 1, i + 1)));
}
