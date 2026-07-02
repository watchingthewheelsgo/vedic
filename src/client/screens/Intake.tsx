import { FormEvent, ReactNode, SetStateAction, useEffect, useMemo, useRef, useState } from "react";
import DatePicker from "react-datepicker";
import Select from "react-select";
import { CalendarDays, Clock3, ShieldCheck, UserRound } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { PlacePicker } from "../components/PlacePicker";
import type { BirthInput, BirthTimePrecision } from "../../shared/domain";
import "react-datepicker/dist/react-datepicker.css";

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
const COMMON_MINUTES = Array.from({ length: 12 }, (_, i) => i * 5);
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
    <div className="form-screen-wrap">
      <div className="form-inner intake-modern">
        <button className="back-btn" onClick={() => navigate("/")}>← Back</button>

        <div className="progress-steps">
          <div className="p-step active"><div className="p-dot">1</div>Personal Info</div>
          <div className="p-step"><div className="p-dot">2</div>Workshop</div>
          <div className="p-step"><div className="p-dot">3</div>Report</div>
        </div>

        <section className="intake-hero">
          <div className="intake-hero-icon"><UserRound size={18} /></div>
          <div>
            <h2 className="form-h2">Personal Information</h2>
            <p className="form-sub">
              These details calculate your chart and determine how strict the pre-validation should be.
            </p>
          </div>
        </section>

        <form className="intake-card" onSubmit={onStart} noValidate>
          <div className="field-grid">
            <FieldShell
              label="Date of birth"
              icon={<CalendarDays size={16} />}
              hint="Calendar input replaces manual year/month/day selection."
              error={errors.birthDate}
            >
              <DatePicker
                selected={birthDate}
                onChange={(date: Date | null) => {
                  setBirthDate(date);
                  clearError(setErrors, "birthDate");
                }}
                placeholderText="Select date"
                dateFormat="MMMM d, yyyy"
                maxDate={new Date()}
                showMonthDropdown
                showYearDropdown
                dropdownMode="select"
                scrollableYearDropdown
                yearDropdownItemNumber={90}
                className={`date-input ${errors.birthDate ? "field-invalid" : ""}`}
                wrapperClassName="date-picker-wrap"
              />
            </FieldShell>

            <FieldShell
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
            </FieldShell>
          </div>

          <FieldShell
            label="Birth time confidence"
            icon={<ShieldCheck size={16} />}
            hint={precisionOption.description}
          >
            <Select
              value={precisionOption}
              onChange={(option) => {
                const next = option?.value ?? "exact";
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
              options={TIME_PRECISION_OPTIONS}
              classNamePrefix="modern-select"
              className="modern-select"
              isSearchable={false}
            />
          </FieldShell>

          {timePrecision === "exact" && (
            <FieldShell
              label="Birth time source"
              hint="The reader skill converts source quality into effective precision."
              error={errors.timeSource}
            >
              <Select
                value={TIME_SOURCE_OPTIONS.find((option) => option.value === timeSource) ?? null}
                onChange={(option) => {
                  setTimeSource(option?.value ?? "");
                  clearError(setErrors, "timeSource");
                }}
                options={TIME_SOURCE_OPTIONS}
                placeholder="Select source"
                classNamePrefix="modern-select"
                className={`modern-select ${errors.timeSource ? "field-invalid-select" : ""}`}
              />
            </FieldShell>
          )}

          {timePrecision === "unknown" && (
            <div className="form-note compact modern-note">
              Unknown birth time is allowed, but the next validation step becomes more important.
            </div>
          )}

          <PlacePicker value={place} onChange={(value) => {
            setPlace(value);
            if (value) clearError(setErrors, "place");
          }} error={errors.place} />

          <FieldShell label="Name" hint="Optional. Used only to address you in the experience.">
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="How should the report address you?"
              className="text-input"
            />
          </FieldShell>

          <div className="field-grid">
            <FieldShell label="Gender" hint="Used for wording and role interpretation in the report.">
              <Select
                value={GENDER_OPTIONS.find((option) => option.value === gender) ?? null}
                onChange={(option) => setGender(option?.value ?? "")}
                options={GENDER_OPTIONS}
                placeholder="Select"
                classNamePrefix="modern-select"
                className="modern-select"
                isSearchable={false}
              />
            </FieldShell>

            <FieldShell label="Relationship status" hint="Shapes the validation and relationship wording.">
              <Select
                value={RELATIONSHIP_OPTIONS.find((option) => option.value === relationship) ?? null}
                onChange={(option) => setRelationship(option?.value ?? "")}
                options={RELATIONSHIP_OPTIONS}
                placeholder="Select"
                classNamePrefix="modern-select"
                className="modern-select"
                isSearchable={false}
              />
            </FieldShell>
          </div>

          {errors.submit && <div className="form-error submit-error">{errors.submit}</div>}

          <button className="btn btn-gold intake-submit" disabled={busy}>
            {busy ? "Preparing…" : "Continue to Workshop →"}
          </button>
        </form>
      </div>
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
  const rootRef = useRef<HTMLDivElement>(null);
  const disabled = precision === "unknown";
  const selectedHour = value?.getHours() ?? null;
  const selectedMinute = value?.getMinutes() ?? 0;
  const minuteOptions =
    precision === "part_of_day"
      ? [0]
      : precision === "approximate"
        ? QUARTER_MINUTES
        : COMMON_MINUTES;

  useEffect(() => {
    if (disabled) setOpen(false);
  }, [disabled]);

  useEffect(() => {
    function onDocClick(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  function commit(hour: number, minute: number) {
    onChange(makeTime(hour, normalizeMinuteForPrecision(minute, precision)));
  }

  function pickHour(hour: number) {
    commit(hour, selectedMinute);
  }

  function pickMinute(minute: number) {
    commit(selectedHour ?? 8, minute);
  }

  function pickExactMinute(rawValue: string) {
    const digits = rawValue.replace(/\D/g, "");
    if (!digits) {
      pickMinute(0);
      return;
    }
    pickMinute(Math.max(0, Math.min(59, Number(digits))));
  }

  return (
    <div className="time-picker" ref={rootRef}>
      <button
        type="button"
        className={`time-trigger ${invalid ? "field-invalid" : ""} ${value ? "filled" : ""}`}
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
        onKeyDown={(event) => {
          if (event.key === "Escape") setOpen(false);
        }}
        aria-haspopup="dialog"
        aria-expanded={open}
      >
        <span className="time-trigger-main">{disabled ? "Time unknown" : value ? formatTimeLabel(value, precision) : "Select time"}</span>
        <span className="time-trigger-meta">
          {disabled ? "No input needed" : precision === "part_of_day" ? "Hour only" : "HH:MM"}
        </span>
      </button>

      {open && !disabled && (
        <div className="time-popover" role="dialog" aria-label="Choose birth time">
          <div className="time-readout">
            <span>Selected time</span>
            <strong>{value ? formatTimeLabel(value, precision) : "--:--"}</strong>
            <em>{precision === "exact" ? "Exact minute" : precision === "approximate" ? "15 minute step" : "Hour only"}</em>
          </div>

          <div className="time-quick-row">
            {QUICK_TIMES.map((item) => (
              <button
                type="button"
                key={item.label}
                onClick={() => {
                  commit(item.hour, item.minute);
                  setOpen(false);
                }}
              >
                <b>{item.label}</b>
                <span>{pad(item.hour)}:{pad(item.minute)}</span>
              </button>
            ))}
          </div>

          <div className="time-columns">
            <div className="time-panel-section">
              <div className="time-panel-title">Hour</div>
              <div className="time-grid hours">
                {HOURS.map((hour) => (
                  <button
                    type="button"
                    key={hour}
                    className={selectedHour === hour ? "selected" : ""}
                    onClick={() => pickHour(hour)}
                  >
                    {pad(hour)}
                  </button>
                ))}
              </div>
            </div>

            <div className="time-panel-section">
              <div className="time-panel-title">Minute</div>
              {precision === "part_of_day" ? (
                <div className="minute-locked">Fixed to :00 for hour-level precision.</div>
              ) : precision === "exact" ? (
                <>
                  <label className="minute-exact-input">
                    <span>Exact minute</span>
                    <input
                      type="number"
                      min={0}
                      max={59}
                      value={selectedMinute}
                      onChange={(event) => pickExactMinute(event.target.value)}
                    />
                  </label>
                  <div className="minute-presets" aria-label="Common minute presets">
                    {minuteOptions.map((minute) => (
                      <button
                        type="button"
                        key={minute}
                        className={selectedMinute === minute ? "selected" : ""}
                        onClick={() => pickMinute(minute)}
                      >
                        {pad(minute)}
                      </button>
                    ))}
                  </div>
                </>
              ) : (
                <div className="time-grid minutes">
                  {minuteOptions.map((minute) => (
                    <button
                      type="button"
                      key={minute}
                      className={selectedMinute === minute ? "selected" : ""}
                      onClick={() => pickMinute(minute)}
                    >
                      {pad(minute)}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="time-popover-footer">
            <span>{value ? `Selected ${formatTimeLabel(value, precision)}` : "Pick an hour and minute"}</span>
            <button type="button" onClick={() => setOpen(false)}>Done</button>
          </div>
        </div>
      )}
    </div>
  );
}

function FieldShell({
  label,
  hint,
  error,
  icon,
  children
}: {
  label: string;
  hint?: string;
  error?: string;
  icon?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className={`form-group modern-field ${error ? "has-error" : ""}`}>
      <label>{icon}<span>{label}</span></label>
      {children}
      {error ? <div className="field-error">{error}</div> : hint ? <div className="hint">{hint}</div> : null}
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
