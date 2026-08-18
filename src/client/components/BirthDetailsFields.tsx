import { CalendarDays, Clock3, ShieldCheck, UserRound } from "lucide-react";
import { enUS, ja, zhCN } from "date-fns/locale";
import type { BirthTimePrecision } from "../../shared/domain";
import { useI18n } from "../i18n/provider";
import {
  OPTIONAL_GENDER_OPTIONS,
  TIME_PRECISION_OPTIONS,
  type BirthDetailsErrors,
  type BirthSelectOption
} from "../lib/birth-details";
import { Input } from "./ui/input";
import { Field } from "./ui/field";
import { DatePicker } from "./ui/date-picker";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { PlacePicker, type BirthPlaceVisualState } from "./PlacePicker";
import { BirthTimePicker } from "./BirthTimePicker";

export function BirthDateTimeFields({
  birthDate,
  birthTime,
  timePrecision,
  errors = {},
  onBirthDateChange,
  onBirthTimeChange,
  onBirthTimePreviewChange
}: {
  birthDate: Date | null;
  birthTime: Date | null;
  timePrecision: BirthTimePrecision;
  errors?: Pick<BirthDetailsErrors, "birthDate" | "birthTime">;
  onBirthDateChange: (date: Date | null) => void;
  onBirthTimeChange: (date: Date | null) => void;
  onBirthTimePreviewChange?: (date: Date | null) => void;
}) {
  const { locale, t } = useI18n();
  const calendarLocale = locale === "zh" ? zhCN : locale === "ja" ? ja : enUS;

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Field
        label={t("intake.date.label")}
        icon={<CalendarDays size={16} />}
        hint={t("intake.date.hint")}
        hintDisplay="tooltip"
        className="mb-0"
        error={errors.birthDate}
      >
        <DatePicker
          value={birthDate}
          locale={calendarLocale}
          placeholder={t("intake.date.placeholder")}
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
        hintDisplay="tooltip"
        className="mb-0"
        error={errors.birthTime}
      >
        <BirthTimePicker
          value={birthTime}
          precision={timePrecision}
          invalid={Boolean(errors.birthTime)}
          onChange={onBirthTimeChange}
          onPreviewChange={onBirthTimePreviewChange}
        />
      </Field>
    </div>
  );
}

export function BirthTimePrecisionField({
  value,
  error,
  onChange
}: {
  value: BirthTimePrecision | "";
  error?: string;
  onChange: (value: BirthTimePrecision) => void;
}) {
  const { t } = useI18n();
  const selectedOption = TIME_PRECISION_OPTIONS.find((option) => option.value === value);

  return (
    <Field
      label={t("intake.precision.label")}
      icon={<ShieldCheck size={16} />}
      hint={
        selectedOption
          ? t(`intake.precision.${selectedOption.value}.description`)
          : t("intake.precision.placeholder")
      }
      hintDisplay="tooltip"
      className="mb-0"
      error={error}
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
      {selectedOption && (
        <p className="mb-0 mt-2.5 text-xs leading-relaxed text-cream/48">
          {t(`intake.precision.${selectedOption.value}.description`)}
        </p>
      )}
    </Field>
  );
}

export function BirthPlaceField({
  value,
  error,
  onVisualStateChange,
  onChange
}: {
  value: string;
  error?: string;
  onVisualStateChange?: (value: BirthPlaceVisualState | null) => void;
  onChange: (value: string) => void;
}) {
  return (
    <PlacePicker
      value={value}
      onChange={onChange}
      onVisualStateChange={onVisualStateChange}
      error={error}
    />
  );
}

export function BirthNameField({
  value,
  error,
  required = false,
  onChange
}: {
  value: string;
  error?: string;
  required?: boolean;
  onChange: (value: string) => void;
}) {
  const { t } = useI18n();

  return (
    <Field
      label={t("intake.name.label")}
      hint={t("intake.name.hint")}
      hintDisplay="tooltip"
      className="mb-0"
      error={error}
      required={required}
    >
      <Input
        value={value}
        required={required}
        aria-invalid={Boolean(error)}
        autoComplete="name"
        maxLength={120}
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
  required = false,
  options = OPTIONAL_GENDER_OPTIONS,
  onChange
}: {
  value: string;
  error?: string;
  hint?: string;
  required?: boolean;
  options?: BirthSelectOption[];
  onChange: (value: string) => void;
}) {
  const { t } = useI18n();

  return (
    <Field
      label={t("intake.gender.label")}
      icon={<UserRound size={16} />}
      hint={hint ?? t("intake.gender.hint")}
      hintDisplay="tooltip"
      className="mb-0"
      error={error}
      required={required}
    >
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger aria-invalid={Boolean(error)} aria-required={required}>
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
