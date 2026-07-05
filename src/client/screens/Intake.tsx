import { SignedIn, SignedOut, SignInButton, SignUpButton, UserButton } from "@clerk/clerk-react";
import { FormEvent, SetStateAction, useMemo, useState } from "react";
import { CalendarDays, Clock3, ShieldCheck, UserRound } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { LanguageSwitcher } from "../components/LanguageSwitcher";
import { PlacePicker } from "../components/PlacePicker";
import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";
import { DatePicker } from "../components/ui/date-picker";
import { Field } from "../components/ui/field";
import { Input } from "../components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "../components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from "../components/ui/select";
import { cn } from "../lib/cn";
import { useI18n } from "../i18n/provider";
import type { AppLocale, BirthInput, BirthTimePrecision } from "../../shared/domain";

type SelectOption<T extends string = string> = {
  value: T;
  labelKey: string;
};

type FieldKey = "birthDate" | "birthTime" | "timeSource" | "place" | "submit";
type FormErrors = Partial<Record<FieldKey, string>>;

const TIME_PRECISION_OPTIONS: Array<SelectOption<BirthTimePrecision>> = [
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

const TIME_SOURCE_OPTIONS: SelectOption[] = [
  { value: "出生证/医院记录", labelKey: "intake.source.certificate" },
  { value: "家人明确记忆", labelKey: "intake.source.familyClear" },
  { value: "家人大概回忆", labelKey: "intake.source.familyApprox" }
];

const GENDER_OPTIONS: SelectOption[] = [
  { value: "女", labelKey: "intake.gender.female" },
  { value: "男", labelKey: "intake.gender.male" },
  { value: "未提供", labelKey: "common.notProvided" }
];

const RELATIONSHIP_OPTIONS: SelectOption[] = [
  { value: "单身", labelKey: "intake.relationship.single" },
  { value: "恋爱中", labelKey: "intake.relationship.dating" },
  { value: "已婚", labelKey: "intake.relationship.married" },
  { value: "未提供", labelKey: "common.notProvided" }
];

const HOURS = Array.from({ length: 24 }, (_, i) => i);
const ALL_MINUTES = Array.from({ length: 60 }, (_, i) => i);
const QUARTER_MINUTES = [0, 15, 30, 45];

const pad = (n: number) => String(n).padStart(2, "0");

export function Intake() {
  const navigate = useNavigate();
  const { locale, t } = useI18n();
  const [birthDate, setBirthDate] = useState<Date | null>(null);
  const [birthTime, setBirthTime] = useState<Date | null>(null);
  const [place, setPlace] = useState("");
  const [name, setName] = useState("");
  const [gender, setGender] = useState("");
  const [relationship, setRelationship] = useState("");
  const [timePrecision, setTimePrecision] = useState<BirthTimePrecision>("exact");
  const [timeSource, setTimeSource] = useState("");
  const [errors, setErrors] = useState<FormErrors>({});
  const [busy, setBusy] = useState(false);

  const precisionOption = useMemo(
    () =>
      TIME_PRECISION_OPTIONS.find((option) => option.value === timePrecision) ??
      TIME_PRECISION_OPTIONS[0],
    [timePrecision]
  );

  const currentBirth = useMemo(
    () =>
      buildBirthInput({
        birthDate,
        birthTime,
        place,
        timePrecision,
        gender,
        relationship,
        timeSource,
        locale
      }),
    [birthDate, birthTime, gender, locale, place, relationship, timePrecision, timeSource]
  );

  async function onStart(event: FormEvent) {
    event.preventDefault();
    const nextErrors: FormErrors = {};

    if (!birthDate) nextErrors.birthDate = t("intake.error.birthDate");
    if (timePrecision !== "unknown" && !birthTime) {
      nextErrors.birthTime =
        timePrecision === "part_of_day" ? t("intake.error.birthHour") : t("intake.error.birthTime");
    }
    if (timePrecision === "exact" && !timeSource) {
      nextErrors.timeSource = t("intake.error.timeSource");
    }
    if (!place) nextErrors.place = t("intake.error.place");

    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors);
      return;
    }

    const birth = currentBirth;
    if (!birth) return;

    setBusy(true);
    setErrors({});
    try {
      const session = await api.createSkillSession(birth);
      navigate(`/session/${session.sessionId}?tab=reading`, {
        state: { name, birth }
      });
    } catch (caught) {
      setErrors({
        submit: caught instanceof Error ? caught.message : t("intake.error.start")
      });
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-cream-2">
      <nav className="sticky top-0 z-50 border-b border-gold/25 bg-cream/95 px-6 backdrop-blur-xl sm:px-10">
        <div className="mx-auto flex h-16 max-w-[1100px] items-center justify-between">
          <button className="brand-logo border-0 bg-transparent" onClick={() => navigate("/")}>
            Veda<span>Light</span>
          </button>
          <IntakeAuthControls />
        </div>
      </nav>

      <main className="px-5 py-9 sm:px-10 sm:py-14">
        <div className="mx-auto max-w-[760px]">
          <div className="mb-8 flex items-center justify-start">
            <button
              className="inline-flex items-center gap-1 border-0 bg-transparent text-sm text-muted transition hover:text-ink"
              onClick={() => navigate("/")}
            >
              ← {t("common.back")}
            </button>
          </div>

          <div className="mb-12 flex items-start">
            <ProgressStep active label={t("intake.step.personal")} index={1} />
            <ProgressStep label={t("intake.step.reading")} index={2} />
            <ProgressStep label={t("intake.step.report")} index={3} last />
          </div>

          <section className="mb-6 flex items-start gap-3.5">
            <div className="grid size-[38px] shrink-0 place-items-center rounded-[10px] bg-night text-gold shadow-[0_10px_24px_rgba(15,12,9,0.12)]">
              <UserRound size={18} />
            </div>
            <div>
              <h2 className="mb-1.5 text-[26px] font-light tracking-[-0.2px] text-ink">
                {t("intake.title")}
              </h2>
              <p className="mb-9 text-sm text-body">{t("intake.subtitle")}</p>
            </div>
          </section>

          <Card>
            <CardContent className="p-5 sm:p-6">
              <form onSubmit={onStart} noValidate>
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
                      onChange={(date) => {
                        setBirthDate(date);
                        clearError(setErrors, "birthDate");
                      }}
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
                      onChange={(date) => {
                        setBirthTime(date);
                        clearError(setErrors, "birthTime");
                      }}
                    />
                  </Field>
                </div>

                <Field
                  label={t("intake.precision.label")}
                  icon={<ShieldCheck size={16} />}
                  hint={t(`intake.precision.${precisionOption.value}.description`)}
                >
                  <Select
                    value={timePrecision}
                    onValueChange={(value) => {
                      const next = value as BirthTimePrecision;
                      setTimePrecision(next);
                      setBirthTime((current) => normalizeTimeForPrecision(current, next));
                      if (next !== "exact") {
                        setTimeSource("");
                        clearError(setErrors, "timeSource");
                      }
                      if (next === "unknown") {
                        clearError(setErrors, "birthTime");
                      }
                    }}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder={t("intake.precision.placeholder")} />
                    </SelectTrigger>
                    <SelectContent>
                      {TIME_PRECISION_OPTIONS.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {t(option.labelKey)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Field>

                {timePrecision === "exact" && (
                  <Field
                    label={t("intake.source.label")}
                    hint={t("intake.source.hint")}
                    error={errors.timeSource}
                  >
                    <Select
                      value={timeSource || undefined}
                      onValueChange={(value) => {
                        setTimeSource(value);
                        clearError(setErrors, "timeSource");
                      }}
                    >
                      <SelectTrigger aria-invalid={Boolean(errors.timeSource)}>
                        <SelectValue placeholder={t("intake.source.placeholder")} />
                      </SelectTrigger>
                      <SelectContent>
                        {TIME_SOURCE_OPTIONS.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            {t(option.labelKey)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </Field>
                )}

                {timePrecision === "unknown" && (
                  <div className="mb-5 rounded-[10px] border border-gold/25 bg-[#fff9ed] px-4 py-3 text-[13px] leading-relaxed text-body">
                    {t("intake.unknownNotice")}
                  </div>
                )}

                <PlacePicker
                  value={place}
                  onChange={(value) => {
                    setPlace(value);
                    if (value) clearError(setErrors, "place");
                  }}
                  error={errors.place}
                />

                <Field label={t("intake.name.label")} hint={t("intake.name.hint")}>
                  <Input
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    placeholder={t("intake.name.placeholder")}
                  />
                </Field>

                <div className="grid gap-4 md:grid-cols-2">
                  <Field label={t("intake.gender.label")} hint={t("intake.gender.hint")}>
                    <Select value={gender || undefined} onValueChange={setGender}>
                      <SelectTrigger>
                        <SelectValue placeholder={t("intake.select")} />
                      </SelectTrigger>
                      <SelectContent>
                        {GENDER_OPTIONS.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            {t(option.labelKey)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </Field>

                  <Field
                    label={t("intake.relationship.label")}
                    hint={t("intake.relationship.hint")}
                  >
                    <Select value={relationship || undefined} onValueChange={setRelationship}>
                      <SelectTrigger>
                        <SelectValue placeholder={t("intake.select")} />
                      </SelectTrigger>
                      <SelectContent>
                        {RELATIONSHIP_OPTIONS.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            {t(option.labelKey)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </Field>
                </div>

                {errors.submit && (
                  <div className="mt-1 rounded-md border border-red/30 bg-red/10 px-4 py-3 text-[13px] text-red">
                    {errors.submit}
                  </div>
                )}

                <Button className="mt-2 w-full" size="lg" disabled={busy}>
                  {busy ? t("intake.submit.busy") : t("intake.submit")}
                </Button>
              </form>
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  );
}

function IntakeAuthControls() {
  const { t } = useI18n();
  return (
    <div className="flex items-center gap-2">
      <LanguageSwitcher />
      <SignedOut>
        <span className="hidden rounded-full border border-gold/25 bg-gold/10 px-2.5 py-1 text-[11px] font-medium text-gold-dim sm:inline-flex">
          {t("common.trialMode")}
        </span>
        <SignInButton mode="modal">
          <Button variant="ghost" size="sm">
            {t("common.signIn")}
          </Button>
        </SignInButton>
        <SignUpButton mode="modal">
          <Button size="sm">{t("common.createAccount")}</Button>
        </SignUpButton>
      </SignedOut>
      <SignedIn>
        <UserButton afterSignOutUrl="/" />
      </SignedIn>
    </div>
  );
}

function ProgressStep({
  active = false,
  label,
  index,
  last = false
}: {
  active?: boolean;
  label: string;
  index: number;
  last?: boolean;
}) {
  return (
    <div
      className={cn(
        "relative flex-1 text-center text-xs tracking-[0.3px]",
        active ? "text-gold" : "text-muted"
      )}
    >
      {!last && <div className="absolute left-[55%] right-[-55%] top-[15px] h-px bg-gold/25" />}
      <div
        className={cn(
          "relative z-[1] mx-auto mb-2 grid size-[30px] place-items-center rounded-full border text-[13px]",
          active ? "border-gold bg-gold text-white" : "border-gold/25 bg-cream text-muted"
        )}
      >
        {index}
      </div>
      {label}
    </div>
  );
}

function BirthTimePicker({
  value,
  precision,
  invalid,
  onChange
}: {
  value: Date | null;
  precision: BirthTimePrecision;
  invalid: boolean;
  onChange: (date: Date | null) => void;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const disabled = precision === "unknown";
  const selectedHour = value?.getHours() ?? null;
  const selectedMinute = value ? normalizeMinuteForPrecision(value.getMinutes(), precision) : null;
  const minuteOptions =
    precision === "part_of_day" ? [0] : precision === "approximate" ? QUARTER_MINUTES : ALL_MINUTES;

  function commit(hour: number, minute: number) {
    onChange(makeTime(hour, normalizeMinuteForPrecision(minute, precision)));
  }

  function selectHour(hour: number) {
    commit(hour, selectedMinute ?? 0);
    if (precision === "part_of_day") setOpen(false);
  }

  function selectMinute(minute: number) {
    commit(selectedHour ?? 0, minute);
    setOpen(false);
  }

  return (
    <div>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="outline"
            size="lg"
            disabled={disabled}
            aria-invalid={invalid}
            className={cn(
              "w-full justify-start border-gold/30 bg-white px-4 text-left font-normal text-ink hover:border-gold/50 hover:bg-white data-[state=open]:border-gold data-[state=open]:ring-4 data-[state=open]:ring-gold/15",
              invalid && "border-red bg-red/5 hover:border-red"
            )}
          >
            <Clock3 className="size-4 shrink-0 text-gold-dim" />
            <span
              className={cn(
                "min-w-0 flex-1 text-[15px] font-medium tabular-nums",
                value ? "text-ink" : "text-muted"
              )}
            >
              {disabled
                ? t("common.timeUnknown")
                : value
                  ? formatTimeLabel(value, precision)
                  : t("intake.time.select")}
            </span>
          </Button>
        </PopoverTrigger>

        {!disabled && (
          <PopoverContent className="w-[min(92vw,280px)] p-3" align="start">
            <div className="grid grid-cols-[1fr_auto_1fr] items-end gap-2">
              <TimeSelect
                title={t("time.hour")}
                values={HOURS}
                value={selectedHour}
                placeholder="HH"
                onSelect={selectHour}
              />
              <div className="pb-2 text-sm text-muted">:</div>
              <TimeSelect
                title={t("time.minute")}
                values={minuteOptions}
                value={precision === "part_of_day" ? 0 : selectedMinute}
                placeholder="MM"
                onSelect={selectMinute}
                disabled={precision === "part_of_day"}
              />
            </div>

            <div className="mt-3 flex items-center justify-between">
              <button
                type="button"
                className="text-xs text-muted transition hover:text-ink"
                onClick={() => {
                  onChange(null);
                  setOpen(false);
                }}
              >
                {t("common.clear")}
              </button>
              <Button type="button" size="sm" onClick={() => setOpen(false)}>
                {t("common.done")}
              </Button>
            </div>
          </PopoverContent>
        )}
      </Popover>
    </div>
  );
}

function TimeSelect({
  title,
  values,
  value,
  placeholder,
  disabled = false,
  onSelect
}: {
  title: string;
  values: number[];
  value: number | null;
  placeholder: string;
  disabled?: boolean;
  onSelect: (value: number) => void;
}) {
  return (
    <div>
      <div className="mb-1.5 text-[11px] text-muted">{title}</div>
      <Select
        value={value === null ? "" : String(value)}
        onValueChange={(next) => onSelect(Number(next))}
        disabled={disabled}
      >
        <SelectTrigger className="h-10 rounded-md px-3 text-sm tabular-nums">
          <SelectValue placeholder={placeholder} />
        </SelectTrigger>
        <SelectContent className="max-h-64">
          {values.map((value) => {
            return (
              <SelectItem key={value} value={String(value)} className="tabular-nums">
                {pad(value)}
              </SelectItem>
            );
          })}
        </SelectContent>
      </Select>
    </div>
  );
}

function clearError(setErrors: (value: SetStateAction<FormErrors>) => void, key: FieldKey) {
  setErrors((current) => {
    if (!current[key]) return current;
    const next = { ...current };
    delete next[key];
    return next;
  });
}

function formatBirthDate(date: Date | null): string {
  if (!date) return "";
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function buildBirthInput({
  birthDate,
  birthTime,
  place,
  timePrecision,
  gender,
  relationship,
  timeSource,
  locale
}: {
  birthDate: Date | null;
  birthTime: Date | null;
  place: string;
  timePrecision: BirthTimePrecision;
  gender: string;
  relationship: string;
  timeSource: string;
  locale: AppLocale;
}): BirthInput | null {
  if (!birthDate) return null;
  if (!place) return null;
  if (timePrecision !== "unknown" && !birthTime) return null;
  if (timePrecision === "exact" && !timeSource) return null;

  return {
    birthDate: formatBirthDate(birthDate),
    birthTime: timePrecision === "unknown" ? "" : formatBirthTime(birthTime, timePrecision),
    birthPlace: place,
    birthTimePrecision: timePrecision,
    gender: gender || "未提供",
    relationship: relationship || "未提供",
    timeSource: timePrecision === "exact" ? timeSource : "未追问",
    locale
  };
}

function formatBirthTime(date: Date | null, precision: BirthTimePrecision): string {
  if (!date) return "";
  const hour = date.getHours();
  const minute = precision === "part_of_day" ? 0 : date.getMinutes();
  return `${pad(hour)}:${pad(minute)}`;
}

function makeTime(hour: number, minute: number): Date {
  const next = new Date();
  next.setHours(hour, minute, 0, 0);
  return next;
}

function normalizeTimeForPrecision(date: Date | null, precision: BirthTimePrecision): Date | null {
  if (!date || precision === "unknown") return null;
  const next = new Date(date);
  next.setMinutes(normalizeMinuteForPrecision(next.getMinutes(), precision), 0, 0);
  return next;
}

function normalizeMinuteForPrecision(minute: number, precision: BirthTimePrecision): number {
  if (precision === "part_of_day") return 0;
  if (precision === "approximate") return Math.min(45, Math.round(minute / 15) * 15);
  return Math.max(0, Math.min(59, minute));
}

function formatTimeLabel(date: Date, precision: BirthTimePrecision): string {
  const hour = date.getHours();
  const minute = precision === "part_of_day" ? 0 : date.getMinutes();
  return `${pad(hour)}:${pad(minute)}`;
}
