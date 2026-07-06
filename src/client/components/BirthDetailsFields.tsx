import { CalendarDays, Clock3, ShieldCheck, UserRound } from "lucide-react";
import type { BirthTimePrecision } from "../../shared/domain";
import { useI18n } from "../i18n/provider";
import {
  OPTIONAL_GENDER_OPTIONS,
  TIME_PRECISION_OPTIONS,
  TIME_SOURCE_OPTIONS,
  type BirthDetailsErrors,
  type BirthSelectOption
} from "../lib/birth-details";
import { Input } from "./ui/input";
import { Field } from "./ui/field";
import { DatePicker } from "./ui/date-picker";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { PlacePicker } from "./PlacePicker";
import { BirthTimePicker } from "./BirthTimePicker";

export function BirthDateTimeFields({
  birthDate,
  birthTime,
  timePrecision,
  errors = {},
  onBirthDateChange,
  onBirthTimeChange
}: {
  birthDate: Date | null;
  birthTime: Date | null;
  timePrecision: BirthTimePrecision;
  errors?: Pick<BirthDetailsErrors, "birthDate" | "birthTime">;
  onBirthDateChange: (date: Date | null) => void;
  onBirthTimeChange: (date: Date | null) => void;
}) {
  const { t } = useI18n();

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Field
        label={t("intake.date.label")}
        icon={<CalendarDays size={16} />}
        hint={t("intake.date.hint")}
        error={errors.birthDate}
      >
        <DatePicker
          value={birthDate}
          invalid={Boolean(errors.birthDate)}
          disabled={{ after: new Date() }}
          startMonth={new Date(1900, 0)}
          endMonth={new Date()}
          onChange={onBirthDateChange}
        />
      </Field>

      <Field
        label={t("intake.time.label")}
        icon={<Clock3 size={16} />}
        hint={
          timePrecision === "unknown"
            ? t("intake.time.hint.unknown")
            : timePrecision === "part_of_day"
              ? t("intake.time.hint.partOfDay")
              : t("intake.time.hint.default")
        }
        error={errors.birthTime}
      >
        <BirthTimePicker
          value={birthTime}
          precision={timePrecision}
          invalid={Boolean(errors.birthTime)}
          onChange={onBirthTimeChange}
        />
      </Field>
    </div>
  );
}

export function BirthTimePrecisionField({
  value,
  onChange
}: {
  value: BirthTimePrecision;
  onChange: (value: BirthTimePrecision) => void;
}) {
  const { t } = useI18n();
  const selectedOption =
    TIME_PRECISION_OPTIONS.find((option) => option.value === value) ?? TIME_PRECISION_OPTIONS[0];

  return (
    <Field
      label={t("intake.precision.label")}
      icon={<ShieldCheck size={16} />}
      hint={t(`intake.precision.${selectedOption.value}.description`)}
    >
      <Select value={value} onValueChange={(next) => onChange(next as BirthTimePrecision)}>
        <SelectTrigger>
          <SelectValue placeholder={t("intake.precision.placeholder")} />
        </SelectTrigger>
        <SelectContent>
          {TIME_PRECISION_OPTIONS.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {labelForOption(option, t)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </Field>
  );
}

export function BirthTimeSourceField({
  value,
  error,
  onChange
}: {
  value: string;
  error?: string;
  onChange: (value: string) => void;
}) {
  const { t } = useI18n();

  return (
    <Field label={t("intake.source.label")} hint={t("intake.source.hint")} error={error}>
      <Select value={value || undefined} onValueChange={onChange}>
        <SelectTrigger aria-invalid={Boolean(error)}>
          <SelectValue placeholder={t("intake.source.placeholder")} />
        </SelectTrigger>
        <SelectContent>
          {TIME_SOURCE_OPTIONS.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {labelForOption(option, t)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </Field>
  );
}

export function BirthPlaceField({
  value,
  error,
  onChange
}: {
  value: string;
  error?: string;
  onChange: (value: string) => void;
}) {
  return <PlacePicker value={value} onChange={onChange} error={error} />;
}

export function BirthNameField({
  value,
  onChange
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const { t } = useI18n();

  return (
    <Field label={t("intake.name.label")} hint={t("intake.name.hint")}>
      <Input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={t("intake.name.placeholder")}
      />
    </Field>
  );
}

export function BirthGenderField({
  value,
  error,
  hint,
  options = OPTIONAL_GENDER_OPTIONS,
  onChange
}: {
  value: string;
  error?: string;
  hint?: string;
  options?: BirthSelectOption[];
  onChange: (value: string) => void;
}) {
  const { t } = useI18n();

  return (
    <Field
      label={t("intake.gender.label")}
      icon={<UserRound size={16} />}
      hint={hint ?? t("intake.gender.hint")}
      error={error}
    >
      <Select value={value || undefined} onValueChange={onChange}>
        <SelectTrigger aria-invalid={Boolean(error)}>
          <SelectValue placeholder={t("intake.select")} />
        </SelectTrigger>
        <SelectContent>
          {options.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {labelForOption(option, t)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </Field>
  );
}

function labelForOption(option: BirthSelectOption, t: (key: string) => string): string {
  return option.labelKey ? t(option.labelKey) : (option.label ?? option.value);
}
