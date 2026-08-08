import { SignedIn, SignedOut, SignInButton, SignUpButton } from "@clerk/clerk-react";
import {
  FormEvent,
  SetStateAction,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode
} from "react";
import {
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  Clock3,
  MapPin,
  Sparkles,
  UserRound
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api";
import { AccountCenter } from "../components/AccountCenter";
import { BirthInputLayout } from "../components/BirthInputLayout";
import { BirthInputAstroVisual } from "../components/BirthInputAstroVisual";
import type { BirthPlaceVisualState } from "../components/PlacePicker";
import {
  BirthDateTimeFields,
  BirthGenderField,
  BirthNameField,
  BirthPlaceField,
  BirthTimePrecisionField,
  BirthTimeSourceField
} from "../components/BirthDetailsFields";
import { LanguageSwitcher } from "../components/LanguageSwitcher";
import { Button } from "../components/ui/button";
import { Field, FieldHint } from "../components/ui/field";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from "../components/ui/select";
import { Textarea } from "../components/ui/textarea";
import { formatBirthDate, TIME_SOURCE_OPTIONS } from "../lib/birth-details";
import { formatBirthTime, normalizeTimeForPrecision } from "../lib/birth-time";
import { useI18n } from "../i18n/provider";
import { cn } from "../lib/cn";
import type { AppLocale, BirthInput, BirthTimePrecision } from "../../shared/domain";

type SelectOption<T extends string = string> = {
  value: T;
  labelKey: string;
};

type FieldKey = "birthDate" | "birthTime" | "place" | "submit";
type FormErrors = Partial<Record<FieldKey, string>>;
type AmbiguousTimeChoice = {
  utcOffsetSeconds: number;
  localDatetime: string;
  utcDatetime: string;
};
type AmbiguousTimeDetail = {
  code: "ambiguous_birth_time";
  timezoneId: string;
  localDatetime: string;
  choices: AmbiguousTimeChoice[];
};

const RELATIONSHIP_OPTIONS: SelectOption[] = [
  { value: "单身", labelKey: "intake.relationship.single" },
  { value: "恋爱中", labelKey: "intake.relationship.dating" },
  { value: "已婚", labelKey: "intake.relationship.married" },
  { value: "未提供", labelKey: "common.notProvided" }
];

export function Intake() {
  const navigate = useNavigate();
  const { formatDate, locale, t } = useI18n();
  const [birthDate, setBirthDate] = useState<Date | null>(null);
  const [birthTime, setBirthTime] = useState<Date | null>(null);
  const [place, setPlace] = useState("");
  const [locationConfirmed, setLocationConfirmed] = useState(false);
  const [name, setName] = useState("");
  const [gender, setGender] = useState("");
  const [relationship, setRelationship] = useState("");
  const [readingFocus, setReadingFocus] = useState("");
  const [timePrecision, setTimePrecision] = useState<BirthTimePrecision>("exact");
  const [timeSource, setTimeSource] = useState("");
  const [utcOffsetSeconds, setUtcOffsetSeconds] = useState<number | null>(null);
  const [ambiguousTime, setAmbiguousTime] = useState<AmbiguousTimeDetail | null>(null);
  const [errors, setErrors] = useState<FormErrors>({});
  const [busy, setBusy] = useState(false);
  const [visualLocation, setVisualLocation] = useState<BirthPlaceVisualState | null>(null);
  const handleVisualLocationChange = useCallback((next: BirthPlaceVisualState | null) => {
    setVisualLocation(next);
  }, []);

  const currentBirth = useMemo(
    () =>
      buildBirthInput({
        birthDate,
        birthTime,
        place,
        timePrecision,
        gender,
        relationship,
        readingFocus,
        timeSource,
        utcOffsetSeconds,
        locale
      }),
    [
      birthDate,
      birthTime,
      gender,
      readingFocus,
      locale,
      place,
      relationship,
      timePrecision,
      timeSource,
      utcOffsetSeconds
    ]
  );
  const birthTimeReady = timePrecision === "unknown" || Boolean(birthTime);
  const birthMomentReady = Boolean(birthDate) && birthTimeReady;
  const locationReady = Boolean(place) && locationConfirmed;
  const optionalProfileTouched = Boolean(name || gender || relationship || readingFocus.trim());
  const currentStep = !birthMomentReady ? 1 : !locationReady ? 2 : 3;
  const birthMomentSummary = birthDate
    ? `${formatDate(birthDate, { year: "numeric", month: "short", day: "numeric" })} · ${
        timePrecision === "unknown"
          ? t("intake.precision.unknown.label")
          : formatBirthTime(birthTime, timePrecision)
      }`
    : "";
  const timeSourceOption = TIME_SOURCE_OPTIONS.find((option) => option.value === timeSource);
  const birthMomentDetail = [
    t(`intake.precision.${timePrecision}.label`),
    timeSourceOption?.labelKey ? t(timeSourceOption.labelKey) : ""
  ]
    .filter(Boolean)
    .join(" · ");
  const locationSummary = place.split("|", 1)[0]?.trim() ?? "";
  const locationDetail = visualLocation
    ? t(visualLocation.exact ? "place.readout.status.precise" : "place.readout.status.city")
    : "";
  const visualTimeReady = Boolean(birthDate) && birthTimeReady;

  async function onStart(event: FormEvent) {
    event.preventDefault();
    const nextErrors: FormErrors = {};

    if (!birthDate) nextErrors.birthDate = t("intake.error.birthDate");
    if (timePrecision !== "unknown" && !birthTime) {
      nextErrors.birthTime =
        timePrecision === "part_of_day" ? t("intake.error.birthHour") : t("intake.error.birthTime");
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
      const detail = caught instanceof ApiError ? caught.detail : null;
      if (isAmbiguousTimeDetail(detail)) {
        setAmbiguousTime(detail);
        setErrors({});
        setBusy(false);
        return;
      }
      setErrors({
        submit: caught instanceof Error ? caught.message : t("intake.error.start")
      });
      setBusy(false);
    }
  }

  return (
    <BirthInputLayout
      navControls={<IntakeAuthControls />}
      backLabel={t("common.back")}
      title={t("intake.title")}
      subtitle={t("intake.subtitle")}
      icon={<UserRound size={18} />}
      steps={[
        {
          active: currentStep === 1,
          complete: currentStep > 1,
          label: t("intake.step.birth"),
          index: 1
        },
        {
          active: currentStep === 2,
          complete: currentStep > 2,
          label: t("intake.step.location"),
          index: 2
        },
        { active: currentStep === 3, label: t("intake.step.review"), index: 3 }
      ]}
      visual={
        <BirthInputAstroVisual
          theme="cosmic"
          embedded
          birthDate={visualTimeReady ? birthDate : null}
          birthTime={birthTime}
          timePrecision={timePrecision}
          location={visualLocation}
          timeTitle={t("intake.step.birth")}
          locationTitle={t("intake.step.location")}
          timeLabel={visualTimeReady ? birthMomentSummary : undefined}
          locationLabel={visualLocation?.label || locationSummary || undefined}
        />
      }
      onBack={() => navigate("/")}
    >
      <form className="grid gap-4" onSubmit={onStart} noValidate>
        <IntakeFlowSection
          index={1}
          title={t("intake.flow.birth.title")}
          body={t("intake.flow.birth.body")}
          icon={<Clock3 size={17} />}
          active={!birthMomentReady}
          complete={birthMomentReady}
          summary={birthMomentSummary}
          summaryDetail={birthMomentDetail}
        >
          <BirthDateTimeFields
            birthDate={birthDate}
            birthTime={birthTime}
            timePrecision={timePrecision}
            errors={errors}
            onBirthDateChange={(date) => {
              setBirthDate(date);
              setUtcOffsetSeconds(null);
              setAmbiguousTime(null);
              clearError(setErrors, "birthDate");
            }}
            onBirthTimeChange={(date) => {
              setBirthTime(date);
              setUtcOffsetSeconds(null);
              setAmbiguousTime(null);
              clearError(setErrors, "birthTime");
            }}
          />

          <BirthTimePrecisionField
            value={timePrecision}
            onChange={(next) => {
              setTimePrecision(next);
              setUtcOffsetSeconds(null);
              setAmbiguousTime(null);
              setBirthTime((current) => normalizeTimeForPrecision(current, next));
              if (next === "unknown") {
                setTimeSource("");
                clearError(setErrors, "birthTime");
              }
            }}
          />

          {timePrecision === "unknown" && (
            <div className="rounded-[12px] border border-gold/25 bg-gold/10 px-4 py-3 text-[13px] leading-relaxed text-body">
              {t("intake.unknownNotice")}
            </div>
          )}
        </IntakeFlowSection>

        {birthMomentReady && (
          <IntakeFlowSection
            index={2}
            title={t("intake.flow.place.title")}
            body={t("intake.flow.place.body")}
            icon={<MapPin size={17} />}
            active={!locationReady}
            complete={locationReady}
            summary={locationSummary}
            summaryDetail={locationDetail}
          >
            <BirthPlaceField
              value={place}
              onVisualStateChange={handleVisualLocationChange}
              onChange={(value) => {
                setPlace(value);
                setUtcOffsetSeconds(null);
                setAmbiguousTime(null);
                setLocationConfirmed(false);
                if (value) clearError(setErrors, "place");
              }}
              error={errors.place}
            />
            <Button
              type="button"
              variant="gold"
              disabled={!place}
              onClick={() => setLocationConfirmed(true)}
            >
              {t("intake.flow.place.confirm")}
            </Button>
          </IntakeFlowSection>
        )}

        {locationReady && (
          <IntakeFlowSection
            index={3}
            title={t("intake.flow.profile.title")}
            body={t("intake.flow.profile.body")}
            icon={<Sparkles size={17} />}
            active
            complete={optionalProfileTouched}
          >
            <BirthNameField value={name} onChange={setName} />

            <div className="grid gap-4 md:grid-cols-2">
              <BirthGenderField value={gender} onChange={setGender} />

              <Field
                label={t("intake.relationship.label")}
                hint={t("intake.relationship.hint")}
                hintDisplay="tooltip"
                className="mb-0"
              >
                <Select value={relationship} onValueChange={setRelationship}>
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

            <details className="rounded-[12px] border border-gold/18 bg-white/[0.025] p-3.5">
              <summary className="cursor-pointer select-none text-[12px] font-semibold uppercase tracking-[1.4px] text-gold-light outline-none">
                {t("intake.flow.profile.optional")}
              </summary>
              <div className="mt-4 grid gap-4">
                {timePrecision !== "unknown" && (
                  <BirthTimeSourceField value={timeSource} onChange={setTimeSource} />
                )}
                <Field
                  label={t("intake.lifeEvents.label")}
                  hint={t("intake.lifeEvents.hint")}
                  hintDisplay="tooltip"
                  className="mb-0"
                >
                  <Textarea
                    value={readingFocus}
                    onChange={(event) => setReadingFocus(event.target.value)}
                    placeholder={t("intake.lifeEvents.placeholder")}
                    rows={4}
                  />
                </Field>
              </div>
            </details>
          </IntakeFlowSection>
        )}

        {errors.submit && (
          <div className="rounded-md border border-red/30 bg-red/10 px-4 py-3 text-[13px] text-red">
            {errors.submit}
          </div>
        )}

        {ambiguousTime && (
          <div className="rounded-[12px] border border-gold/28 bg-gold/10 p-4">
            <div className="flex items-start gap-3">
              <Clock3 className="mt-0.5 size-4 shrink-0 text-gold-light" />
              <div className="min-w-0">
                <p className="text-sm font-semibold text-heading">
                  {t("intake.ambiguousTime.title")}
                </p>
                <p className="mt-1 text-[13px] leading-relaxed text-body">
                  {t("intake.ambiguousTime.body")}
                </p>
              </div>
            </div>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {ambiguousTime.choices.map((choice, index) => (
                <button
                  key={`${choice.utcDatetime}-${choice.utcOffsetSeconds}`}
                  type="button"
                  className="rounded-[10px] border border-gold/22 bg-black/15 px-3 py-3 text-left transition-colors hover:border-gold/50 hover:bg-gold/10"
                  onClick={() => {
                    setUtcOffsetSeconds(choice.utcOffsetSeconds);
                    setAmbiguousTime(null);
                    setErrors({});
                  }}
                >
                  <span className="block text-[13px] font-semibold text-heading">
                    {t(index === 0 ? "intake.ambiguousTime.first" : "intake.ambiguousTime.second")}
                  </span>
                  <span className="mt-1 block text-xs text-muted">
                    {formatUtcOffset(choice.utcOffsetSeconds)}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}

        {locationReady && (
          <Button className="w-full" size="lg" disabled={busy}>
            {busy ? (
              t("intake.submit.busy")
            ) : (
              <>
                {t("intake.submit")} <ArrowRight className="size-4" />
              </>
            )}
          </Button>
        )}
      </form>
    </BirthInputLayout>
  );
}

function IntakeFlowSection({
  index,
  title,
  body,
  icon,
  active = false,
  complete = false,
  summary = "",
  summaryDetail = "",
  children
}: {
  index: number;
  title: string;
  body: string;
  icon: ReactNode;
  active?: boolean;
  complete?: boolean;
  summary?: string;
  summaryDetail?: string;
  children: ReactNode;
}) {
  const { t } = useI18n();
  const [editing, setEditing] = useState(false);
  const collapsible = complete && !active;
  const collapsed = collapsible && !editing;

  useEffect(() => {
    if (collapsible) setEditing(false);
  }, [collapsible]);

  const header = (
    <>
      <div
        className={cn(
          "grid size-9 shrink-0 place-items-center rounded-full border text-[13px] font-semibold tabular-nums",
          complete
            ? "border-gold/35 bg-gold text-night"
            : active
              ? "border-gold/45 bg-gold/15 text-gold-light"
              : "border-gold/18 bg-white/[0.035] text-cream/42"
        )}
      >
        {complete ? <CheckCircle2 className="size-4" /> : index}
      </div>
      <div className="min-w-0 flex-1 text-left">
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <span className="text-gold-light">{icon}</span>
          <h2 className="m-0 text-base font-semibold tracking-normal text-cream">{title}</h2>
          <FieldHint text={body} />
        </div>
        {collapsed && summary ? (
          <div className="space-y-0.5">
            <p className="m-0 truncate text-[13px] text-cream/68">{summary}</p>
            {summaryDetail ? (
              <p className="m-0 truncate text-[11.5px] text-cream/40">{summaryDetail}</p>
            ) : null}
          </div>
        ) : null}
      </div>
      {collapsible && (
        <span className="flex shrink-0 items-center gap-1 text-xs text-gold-light/72">
          {collapsed ? t("intake.flow.edit") : t("intake.flow.done")}
          <ChevronDown
            className={cn("size-3.5 transition-transform", !collapsed && "rotate-180")}
          />
        </span>
      )}
    </>
  );

  return (
    <section
      className={cn(
        "border-t border-gold/18 pt-5 transition duration-300",
        active && "border-gold/30",
        complete && "border-gold/24"
      )}
    >
      {collapsible ? (
        <button
          type="button"
          className={cn(
            "flex w-full items-start gap-3 rounded-md text-left outline-none focus-visible:ring-4 focus-visible:ring-gold/15",
            !collapsed && "mb-4"
          )}
          aria-expanded={!collapsed}
          onClick={() => setEditing((current) => !current)}
        >
          {header}
        </button>
      ) : (
        <div className="mb-4 flex items-start gap-3">{header}</div>
      )}
      {!collapsed && <div className="grid gap-4">{children}</div>}
    </section>
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
        <AccountCenter compact />
      </SignedIn>
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

function buildBirthInput({
  birthDate,
  birthTime,
  place,
  timePrecision,
  gender,
  relationship,
  readingFocus,
  timeSource,
  utcOffsetSeconds,
  locale
}: {
  birthDate: Date | null;
  birthTime: Date | null;
  place: string;
  timePrecision: BirthTimePrecision;
  gender: string;
  relationship: string;
  readingFocus: string;
  timeSource: string;
  utcOffsetSeconds: number | null;
  locale: AppLocale;
}): BirthInput | null {
  if (!birthDate) return null;
  if (!place) return null;
  if (timePrecision !== "unknown" && !birthTime) return null;
  return {
    birthDate: formatBirthDate(birthDate),
    birthTime: timePrecision === "unknown" ? "" : formatBirthTime(birthTime, timePrecision),
    birthPlace: place,
    birthTimePrecision: timePrecision,
    gender: gender || "未提供",
    relationship: relationship || "未提供",
    readingFocus: readingFocus.trim(),
    lifeEvents: "",
    readerRelationship: "self",
    timeSource: timePrecision === "unknown" ? "时间未知" : timeSource || "未提供",
    ...(utcOffsetSeconds !== null ? { utcOffsetSeconds } : {}),
    locale
  };
}

function isAmbiguousTimeDetail(value: unknown): value is AmbiguousTimeDetail {
  if (!value || typeof value !== "object") return false;
  const candidate = value as Partial<AmbiguousTimeDetail>;
  return (
    candidate.code === "ambiguous_birth_time" &&
    typeof candidate.timezoneId === "string" &&
    Array.isArray(candidate.choices) &&
    candidate.choices.length === 2 &&
    candidate.choices.every(
      (choice) =>
        choice &&
        typeof choice.utcOffsetSeconds === "number" &&
        typeof choice.utcDatetime === "string"
    )
  );
}

function formatUtcOffset(seconds: number): string {
  const sign = seconds >= 0 ? "+" : "-";
  const totalMinutes = Math.floor(Math.abs(seconds) / 60);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return `UTC${sign}${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}
