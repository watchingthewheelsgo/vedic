import { SignedIn, SignedOut, SignInButton, SignUpButton } from "@clerk/clerk-react";
import { FormEvent, SetStateAction, useMemo, useState, type ReactNode } from "react";
import { CheckCircle2, Clock3, MapPin, Sparkles, UserRound } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { AccountCenter } from "../components/AccountCenter";
import { BirthInputLayout } from "../components/BirthInputLayout";
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
import { Field } from "../components/ui/field";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from "../components/ui/select";
import { Textarea } from "../components/ui/textarea";
import { formatBirthDate } from "../lib/birth-details";
import { formatBirthTime, normalizeTimeForPrecision } from "../lib/birth-time";
import { useI18n } from "../i18n/provider";
import { cn } from "../lib/cn";
import type { AppLocale, BirthInput, BirthTimePrecision } from "../../shared/domain";

type SelectOption<T extends string = string> = {
  value: T;
  labelKey: string;
};

type FieldKey = "birthDate" | "birthTime" | "timeSource" | "place" | "submit";
type FormErrors = Partial<Record<FieldKey, string>>;

const RELATIONSHIP_OPTIONS: SelectOption[] = [
  { value: "单身", labelKey: "intake.relationship.single" },
  { value: "恋爱中", labelKey: "intake.relationship.dating" },
  { value: "已婚", labelKey: "intake.relationship.married" },
  { value: "未提供", labelKey: "common.notProvided" }
];

export function Intake() {
  const navigate = useNavigate();
  const { locale, t } = useI18n();
  const [birthDate, setBirthDate] = useState<Date | null>(null);
  const [birthTime, setBirthTime] = useState<Date | null>(null);
  const [place, setPlace] = useState("");
  const [name, setName] = useState("");
  const [gender, setGender] = useState("");
  const [relationship, setRelationship] = useState("");
  const [lifeEvents, setLifeEvents] = useState("");
  const [timePrecision, setTimePrecision] = useState<BirthTimePrecision>("exact");
  const [timeSource, setTimeSource] = useState("");
  const [errors, setErrors] = useState<FormErrors>({});
  const [busy, setBusy] = useState(false);

  const currentBirth = useMemo(
    () =>
      buildBirthInput({
        birthDate,
        birthTime,
        place,
        timePrecision,
        gender,
        relationship,
        lifeEvents,
        timeSource,
        locale
      }),
    [
      birthDate,
      birthTime,
      gender,
      lifeEvents,
      locale,
      place,
      relationship,
      timePrecision,
      timeSource
    ]
  );
  const birthTimeReady = timePrecision === "unknown" || Boolean(birthTime);
  const timeSourceReady = timePrecision !== "exact" || Boolean(timeSource);
  const birthMomentReady = Boolean(birthDate) && birthTimeReady && timeSourceReady;
  const locationReady = Boolean(place);
  const optionalProfileTouched = Boolean(name || gender || relationship || lifeEvents.trim());

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
    <BirthInputLayout
      navControls={<IntakeAuthControls />}
      backLabel={t("common.back")}
      title={t("intake.title")}
      subtitle={t("intake.subtitle")}
      icon={<UserRound size={18} />}
      steps={[
        { active: !birthMomentReady, label: t("intake.step.birth"), index: 1 },
        { active: birthMomentReady && !locationReady, label: t("intake.step.location"), index: 2 },
        {
          active: birthMomentReady && locationReady,
          label: t("intake.step.calibration"),
          index: 3
        },
        { label: t("intake.step.report"), index: 4 }
      ]}
      onBack={() => navigate("/")}
    >
      <form className="grid gap-5" onSubmit={onStart} noValidate>
        <IntakeFlowSection
          index={1}
          title={t("intake.flow.birth.title")}
          body={t("intake.flow.birth.body")}
          icon={<Clock3 size={17} />}
          active={!birthMomentReady}
          complete={birthMomentReady}
        >
          <BirthDateTimeFields
            birthDate={birthDate}
            birthTime={birthTime}
            timePrecision={timePrecision}
            errors={errors}
            onBirthDateChange={(date) => {
              setBirthDate(date);
              clearError(setErrors, "birthDate");
            }}
            onBirthTimeChange={(date) => {
              setBirthTime(date);
              clearError(setErrors, "birthTime");
            }}
          />

          <BirthTimePrecisionField
            value={timePrecision}
            onChange={(next) => {
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
          />

          {timePrecision === "exact" && (
            <BirthTimeSourceField
              value={timeSource}
              error={errors.timeSource}
              onChange={(value) => {
                setTimeSource(value);
                clearError(setErrors, "timeSource");
              }}
            />
          )}

          {timePrecision === "unknown" && (
            <div className="rounded-[12px] border border-gold/25 bg-gold/10 px-4 py-3 text-[13px] leading-relaxed text-body">
              {t("intake.unknownNotice")}
            </div>
          )}

          {!birthMomentReady && <NextStepHint text={t("intake.flow.birth.next")} />}
        </IntakeFlowSection>

        {birthMomentReady ? (
          <IntakeFlowSection
            index={2}
            title={t("intake.flow.place.title")}
            body={t("intake.flow.place.body")}
            icon={<MapPin size={17} />}
            active={!locationReady}
            complete={locationReady}
          >
            <BirthPlaceField
              value={place}
              onChange={(value) => {
                setPlace(value);
                if (value) clearError(setErrors, "place");
              }}
              error={errors.place}
            />
            {!locationReady && <NextStepHint text={t("intake.flow.place.next")} />}
          </IntakeFlowSection>
        ) : (
          <LockedIntakeStep
            index={2}
            title={t("intake.flow.place.title")}
            body={t("intake.flow.place.locked")}
          />
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

              <Field label={t("intake.relationship.label")} hint={t("intake.relationship.hint")}>
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

            <details className="rounded-[14px] border border-gold/20 bg-white/[0.035] p-4">
              <summary className="cursor-pointer select-none text-[12px] font-semibold uppercase tracking-[1.4px] text-gold-light outline-none">
                {t("intake.flow.profile.optional")}
              </summary>
              <div className="mt-4">
                <Field label={t("intake.lifeEvents.label")} hint={t("intake.lifeEvents.hint")}>
                  <Textarea
                    value={lifeEvents}
                    onChange={(event) => setLifeEvents(event.target.value)}
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

        {locationReady && (
          <Button className="w-full" size="lg" disabled={busy}>
            {busy ? t("intake.submit.busy") : t("intake.submit")}
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
  children
}: {
  index: number;
  title: string;
  body: string;
  icon: ReactNode;
  active?: boolean;
  complete?: boolean;
  children: ReactNode;
}) {
  return (
    <section
      className={cn(
        "rounded-[18px] border p-4 transition duration-300 sm:p-5",
        active
          ? "border-gold/35 bg-white/[0.055] shadow-[0_22px_70px_rgba(0,0,0,0.28),0_0_36px_rgba(201,169,110,0.08)]"
          : "border-gold/18 bg-white/[0.028]",
        complete && "border-gold/28 bg-gold/8"
      )}
    >
      <div className="mb-4 flex items-start gap-3">
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
        <div className="min-w-0 flex-1">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <span className="text-gold-light">{icon}</span>
            <h2 className="m-0 text-base font-semibold tracking-normal text-cream">{title}</h2>
          </div>
          <p className="m-0 max-w-[520px] text-[13px] leading-[1.65] text-cream/58">{body}</p>
        </div>
      </div>
      <div className="grid gap-4">{children}</div>
    </section>
  );
}

function LockedIntakeStep({ index, title, body }: { index: number; title: string; body: string }) {
  return (
    <section className="rounded-[18px] border border-gold/12 bg-white/[0.018] px-4 py-4 text-cream/42 sm:px-5">
      <div className="flex items-center gap-3">
        <div className="grid size-8 shrink-0 place-items-center rounded-full border border-gold/15 bg-white/[0.025] text-[12px] tabular-nums">
          {index}
        </div>
        <div className="min-w-0">
          <div className="text-sm font-semibold text-cream/54">{title}</div>
          <p className="m-0 mt-0.5 text-[12.5px] leading-[1.6] text-cream/38">{body}</p>
        </div>
      </div>
    </section>
  );
}

function NextStepHint({ text }: { text: string }) {
  return (
    <div className="rounded-[12px] border border-gold/16 bg-night/24 px-3 py-2 text-[12.5px] leading-relaxed text-cream/48">
      {text}
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
  lifeEvents,
  timeSource,
  locale
}: {
  birthDate: Date | null;
  birthTime: Date | null;
  place: string;
  timePrecision: BirthTimePrecision;
  gender: string;
  relationship: string;
  lifeEvents: string;
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
    lifeEvents: lifeEvents.trim(),
    timeSource: timePrecision === "exact" ? timeSource : "未追问",
    locale
  };
}
