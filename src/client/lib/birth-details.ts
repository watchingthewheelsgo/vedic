import type { BirthTimePrecision } from "../../shared/domain";

export type BirthDetailsErrorKey = "birthDate" | "birthTime" | "timeSource" | "place" | "gender";

export type BirthDetailsErrors = Partial<Record<BirthDetailsErrorKey, string>>;

export type BirthSelectOption<T extends string = string> = {
  value: T;
  labelKey?: string;
  label?: string;
};

export const TIME_PRECISION_OPTIONS: Array<BirthSelectOption<BirthTimePrecision>> = [
  {
    value: "exact",
    labelKey: "intake.precision.exact.label"
  },
  {
    value: "approximate",
    labelKey: "intake.precision.approximate.label"
  },
  {
    value: "part_of_day",
    labelKey: "intake.precision.part_of_day.label"
  },
  {
    value: "unknown",
    labelKey: "intake.precision.unknown.label"
  }
];

export const TIME_SOURCE_OPTIONS: BirthSelectOption[] = [
  { value: "出生证/医院记录", labelKey: "intake.source.certificate" },
  { value: "家人明确记忆", labelKey: "intake.source.familyClear" },
  { value: "家人大概回忆", labelKey: "intake.source.familyApprox" }
];

export const REQUIRED_GENDER_OPTIONS: BirthSelectOption[] = [
  { value: "女", labelKey: "intake.gender.female" },
  { value: "男", labelKey: "intake.gender.male" }
];

export const OPTIONAL_GENDER_OPTIONS: BirthSelectOption[] = [
  ...REQUIRED_GENDER_OPTIONS,
  { value: "未提供", labelKey: "common.notProvided" }
];

const pad = (n: number) => String(n).padStart(2, "0");

export function formatBirthDate(date: Date | null): string {
  if (!date) return "";
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}
