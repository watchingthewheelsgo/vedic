import { FormEvent, SetStateAction, useEffect, useMemo, useRef, useState } from "react";
import { format } from "date-fns";
import { CalendarDays, Clock3, ShieldCheck, UserRound } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { PlacePicker } from "../components/PlacePicker";
import { Button } from "../components/ui/button";
import { Calendar, CalendarButton } from "../components/ui/calendar";
import { Card, CardContent } from "../components/ui/card";
import { Field } from "../components/ui/field";
import { Input } from "../components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "../components/ui/popover";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { cn } from "../lib/cn";
import type { BirthInput, BirthTimePrecision } from "../../shared/domain";

type SelectOption<T extends string = string> = {
  value: T;
  label: string;
  description?: string;
};

type FieldKey = "birthDate" | "birthTime" | "timeSource" | "place" | "submit";
type FormErrors = Partial<Record<FieldKey, string>>;

const TIME_PRECISION_OPTIONS: Array<SelectOption<BirthTimePrecision>> = [
  {
    value: "exact",
    label: "Exact minute",
    description: "Best for D9 and time-sensitive divisional analysis"
  },
  {
    value: "approximate",
    label: "About +/- 15 minutes",
    description: "Usable, but validation decides which divisions remain reliable"
  },
  {
    value: "part_of_day",
    label: "Only know the hour",
    description: "Minute-level claims will be downgraded"
  },
  {
    value: "unknown",
    label: "Unknown",
    description: "The engine uses noon as a calculation placeholder"
  }
];

const TIME_SOURCE_OPTIONS: SelectOption[] = [
  { value: "出生证/医院记录", label: "Birth certificate / hospital record" },
  { value: "家人明确记忆", label: "Clear family memory" },
  { value: "家人大概回忆", label: "Approximate family memory" }
];

const GENDER_OPTIONS: SelectOption[] = [
  { value: "女", label: "Female" },
  { value: "男", label: "Male" },
  { value: "未提供", label: "Prefer not to say" }
];

const RELATIONSHIP_OPTIONS: SelectOption[] = [
  { value: "单身", label: "Single" },
  { value: "恋爱中", label: "Dating / in a relationship" },
  { value: "已婚", label: "Married" },
  { value: "未提供", label: "Prefer not to say" }
];

const HOURS = Array.from({ length: 24 }, (_, i) => i);
const ALL_MINUTES = Array.from({ length: 60 }, (_, i) => i);
const QUARTER_MINUTES = [0, 15, 30, 45];
const QUICK_TIMES = [
  { label: "Midnight", hour: 0, minute: 0 },
  { label: "Morning", hour: 8, minute: 0 },
  { label: "Noon", hour: 12, minute: 0 },
  { label: "Evening", hour: 18, minute: 0 }
];

const pad = (n: number) => String(n).padStart(2, "0");

export function Intake() {
  const navigate = useNavigate();
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
    () => TIME_PRECISION_OPTIONS.find((option) => option.value === timePrecision) ?? TIME_PRECISION_OPTIONS[0],
    [timePrecision]
  );

  async function onStart(event: FormEvent) {
    event.preventDefault();
    const nextErrors: FormErrors = {};

    if (!birthDate) nextErrors.birthDate = "Select your date of birth.";
    if (timePrecision !== "unknown" && !birthTime) {
      nextErrors.birthTime =
        timePrecision === "part_of_day" ? "Select the closest known birth hour." : "Select your birth time.";
    }
    if (timePrecision === "exact" && !timeSource) {
      nextErrors.timeSource = "Select where this exact time came from.";
    }
    if (!place) nextErrors.place = "Choose a city from search results, or enter coordinates.";

    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors);
      return;
    }

    const birth: BirthInput = {
      birthDate: formatBirthDate(birthDate),
      birthTime: timePrecision === "unknown" ? "" : formatBirthTime(birthTime, timePrecision),
      birthPlace: place,
      birthTimePrecision: timePrecision,
      gender: gender || "未提供",
      relationship: relationship || "未提供",
      timeSource: timePrecision === "exact" ? timeSource : "未追问"
    };

    setBusy(true);
    setErrors({});
    try {
      const session = await api.createSkillSession(birth);
      navigate(`/session/${session.sessionId}?tab=workshop`, {
        state: { name, birth }
      });
    } catch (caught) {
      setErrors({
        submit: caught instanceof Error ? caught.message : "Could not start the report."
      });
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-cream-2 px-5 py-9 sm:px-10 sm:py-14">
      <div className="mx-auto max-w-[760px]">
        <button
          className="mb-8 inline-flex items-center gap-1 border-0 bg-transparent text-sm text-muted transition hover:text-ink"
          onClick={() => navigate("/")}
        >
          ← Back
        </button>

        <div className="mb-12 flex items-start">
          <ProgressStep active label="Personal Info" index={1} />
          <ProgressStep label="Workshop" index={2} />
          <ProgressStep label="Report" index={3} last />
        </div>

        <section className="mb-6 flex items-start gap-3.5">
          <div className="grid size-[38px] shrink-0 place-items-center rounded-[10px] bg-night text-gold shadow-[0_10px_24px_rgba(15,12,9,0.12)]">
            <UserRound size={18} />
          </div>
          <div>
            <h2 className="mb-1.5 text-[26px] font-light tracking-[-0.2px] text-ink">Personal Information</h2>
            <p className="mb-9 text-sm text-body">
              These details calculate your chart and determine how strict the pre-validation should be.
            </p>
          </div>
        </section>

        <Card>
          <CardContent className="p-5 sm:p-6">
            <form onSubmit={onStart} noValidate>
              <div className="grid gap-4 md:grid-cols-2">
                <Field
                  label="Date of birth"
                  icon={<CalendarDays size={16} />}
                  hint="Calendar input replaces manual year/month/day selection."
                  error={errors.birthDate}
                >
                  <Popover>
                    <PopoverTrigger asChild>
                      <CalendarButton aria-invalid={Boolean(errors.birthDate)}>
                        <CalendarDays className="size-4 text-gold-dim" />
                        {birthDate ? format(birthDate, "MMMM d, yyyy") : <span className="text-muted">Select date</span>}
                      </CalendarButton>
                    </PopoverTrigger>
                    <PopoverContent className="p-2">
                      <Calendar
                        mode="single"
                        selected={birthDate ?? undefined}
                        onSelect={(date) => {
                          setBirthDate(date ?? null);
                          clearError(setErrors, "birthDate");
                        }}
                        disabled={{ after: new Date() }}
                        captionLayout="dropdown"
                        startMonth={new Date(1900, 0)}
                        endMonth={new Date()}
                      />
                    </PopoverContent>
                  </Popover>
                </Field>

                <Field
                  label="Birth time"
                  icon={<Clock3 size={16} />}
                  hint={
                    timePrecision === "unknown"
                      ? "No time required. The engine uses 12:00 as a placeholder."
                      : timePrecision === "part_of_day"
                        ? "Select the closest known hour."
                        : "Minute-level time picker. Use the best source you have."
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
                label="Birth time confidence"
                icon={<ShieldCheck size={16} />}
                hint={precisionOption.description}
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
                    <SelectValue placeholder="Select confidence" />
                  </SelectTrigger>
                  <SelectContent>
                    {TIME_PRECISION_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>

              {timePrecision === "exact" && (
                <Field
                  label="Birth time source"
                  hint="The reader skill converts source quality into effective precision."
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
                      <SelectValue placeholder="Select source" />
                    </SelectTrigger>
                    <SelectContent>
                      {TIME_SOURCE_OPTIONS.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Field>
              )}

              {timePrecision === "unknown" && (
                <div className="mb-5 rounded-[10px] border border-gold/25 bg-[#fff9ed] px-4 py-3 text-[13px] leading-relaxed text-body">
                  Unknown birth time is allowed, but the next validation step becomes more important.
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

              <Field label="Name" hint="Optional. Used only to address you in the experience.">
                <Input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="How should the report address you?"
                />
              </Field>

              <div className="grid gap-4 md:grid-cols-2">
                <Field label="Gender" hint="Used for wording and role interpretation in the report.">
                  <Select value={gender || undefined} onValueChange={setGender}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select" />
                    </SelectTrigger>
                    <SelectContent>
                      {GENDER_OPTIONS.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Field>

                <Field label="Relationship status" hint="Shapes the validation and relationship wording.">
                  <Select value={relationship || undefined} onValueChange={setRelationship}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select" />
                    </SelectTrigger>
                    <SelectContent>
                      {RELATIONSHIP_OPTIONS.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
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
                {busy ? "Preparing..." : "Continue to Workshop →"}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>
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
    <div className={cn("relative flex-1 text-center text-xs tracking-[0.3px]", active ? "text-gold" : "text-muted")}>
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
  const [open, setOpen] = useState(false);
  const disabled = precision === "unknown";
  const selectedHour = value?.getHours() ?? null;
  const selectedMinute = value ? normalizeMinuteForPrecision(value.getMinutes(), precision) : null;
  const minuteOptions = precision === "part_of_day" ? [0] : precision === "approximate" ? QUARTER_MINUTES : ALL_MINUTES;
  const precisionLabel =
    precision === "part_of_day" ? "Hour only" : precision === "approximate" ? "15 minute step" : "Exact minute";

  function commit(hour: number, minute: number) {
    onChange(makeTime(hour, normalizeMinuteForPrecision(minute, precision)));
  }

  function selectHour(hour: number) {
    commit(hour, selectedMinute ?? 0);
  }

  function selectMinute(minute: number) {
    commit(selectedHour ?? 8, minute);
  }

  return (
    <div className="space-y-2.5">
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            disabled={disabled}
            aria-invalid={invalid}
            className={cn(
              "flex h-[52px] w-full items-center gap-3 rounded-[10px] border border-gold/30 bg-white px-4 text-left shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] outline-none transition focus:border-gold focus:ring-4 focus:ring-gold/15 disabled:cursor-not-allowed disabled:opacity-60",
              invalid && "border-red bg-red/5"
            )}
          >
            <Clock3 className="size-4 shrink-0 text-gold-dim" />
            <span className={cn("min-w-0 flex-1 text-[15px] font-medium tabular-nums", value ? "text-ink" : "text-muted")}>
              {disabled ? "Time unknown" : value ? formatTimeLabel(value, precision) : "Select time"}
            </span>
            <span className="shrink-0 text-xs text-muted">{disabled ? "No input" : precisionLabel}</span>
          </button>
        </PopoverTrigger>

        {!disabled && (
          <PopoverContent className="w-[min(92vw,360px)] p-3" align="start">
            <div className="mb-3 rounded-lg border border-gold/20 bg-cream px-3 py-2">
              <span className="block text-[10px] uppercase tracking-[1.6px] text-muted">Selected birth time</span>
              <div className="mt-0.5 flex items-end justify-between gap-3">
                <strong className="text-2xl font-semibold leading-none text-gold-dim tabular-nums">
                  {value ? formatTimeLabel(value, precision) : "--:--"}
                </strong>
                <span className="text-xs text-muted">{precisionLabel}</span>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <TimeOptionList
                title="Hour"
                values={HOURS}
                selected={selectedHour}
                onSelect={selectHour}
              />
              <TimeOptionList
                title="Minute"
                values={minuteOptions}
                selected={selectedMinute}
                onSelect={selectMinute}
                disabled={precision === "part_of_day"}
              />
            </div>

            <div className="mt-3 grid grid-cols-4 gap-1.5">
              {QUICK_TIMES.map((item) => {
                const selected =
                  value?.getHours() === item.hour &&
                  normalizeMinuteForPrecision(value.getMinutes(), precision) === normalizeMinuteForPrecision(item.minute, precision);
                return (
                  <button
                    type="button"
                    key={item.label}
                    onClick={() => {
                      commit(item.hour, item.minute);
                      setOpen(false);
                    }}
                    className={cn(
                      "rounded-md border px-2 py-1.5 text-left transition",
                      selected
                        ? "border-gold bg-gold text-white"
                        : "border-gold/20 bg-cream text-body hover:border-gold/50 hover:bg-gold/10"
                    )}
                  >
                    <span className="block text-[11px] font-semibold leading-tight">{item.label}</span>
                    <span className={cn("block text-[11px] tabular-nums", selected ? "text-white/80" : "text-muted")}>
                      {pad(item.hour)}:{pad(normalizeMinuteForPrecision(item.minute, precision))}
                    </span>
                  </button>
                );
              })}
            </div>

            <div className="mt-3 flex items-center justify-between border-t border-gold/15 pt-3">
              <button type="button" className="text-xs text-muted hover:text-ink" onClick={() => onChange(null)}>
                Clear
              </button>
              <Button type="button" size="sm" onClick={() => setOpen(false)}>
                Done
              </Button>
            </div>
          </PopoverContent>
        )}
      </Popover>

      {disabled ? (
        <div className="rounded-lg border border-gold/20 bg-cream px-3 py-2 text-xs leading-relaxed text-muted">
          Birth time is intentionally left blank. The engine will use 12:00 only as a calculation placeholder.
        </div>
      ) : null}
    </div>
  );
}

function TimeOptionList({
  title,
  values,
  selected,
  disabled = false,
  onSelect
}: {
  title: string;
  values: number[];
  selected: number | null;
  disabled?: boolean;
  onSelect: (value: number) => void;
}) {
  const selectedRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    selectedRef.current?.scrollIntoView({ block: "center" });
  }, [selected, values]);

  return (
    <div>
      <div className="mb-1.5 text-[10px] uppercase tracking-[1.4px] text-muted">{title}</div>
      <div className="max-h-36 overflow-y-auto rounded-lg border border-gold/20 bg-white p-1">
        {values.map((value) => {
          const active = selected === value;
          return (
            <button
              type="button"
              key={value}
              ref={active ? selectedRef : undefined}
              disabled={disabled}
              onClick={() => onSelect(value)}
              className={cn(
                "flex h-8 w-full items-center justify-center rounded-md text-sm font-medium tabular-nums transition",
                active ? "bg-gold text-white" : "text-body hover:bg-gold/10 hover:text-ink",
                disabled && "cursor-not-allowed opacity-60"
              )}
            >
              {pad(value)}
            </button>
          );
        })}
      </div>
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
