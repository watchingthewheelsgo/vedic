import { SignedIn, SignedOut, SignInButton, SignUpButton } from "@clerk/clerk-react";
import { FormEvent, SetStateAction, useMemo, useState } from "react";
import { UserRound } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { AccountCenter } from "../components/AccountCenter";
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
import { Card, CardContent } from "../components/ui/card";
import { Field } from "../components/ui/field";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from "../components/ui/select";
import { cn } from "../lib/cn";
import { formatBirthDate } from "../lib/birth-details";
import { formatBirthTime, normalizeTimeForPrecision } from "../lib/birth-time";
import { useI18n } from "../i18n/provider";
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
                  <div className="mb-5 rounded-[10px] border border-gold/25 bg-[#fff9ed] px-4 py-3 text-[13px] leading-relaxed text-body">
                    {t("intake.unknownNotice")}
                  </div>
                )}

                <BirthPlaceField
                  value={place}
                  onChange={(value) => {
                    setPlace(value);
                    if (value) clearError(setErrors, "place");
                  }}
                  error={errors.place}
                />

                <BirthNameField value={name} onChange={setName} />

                <div className="grid gap-4 md:grid-cols-2">
                  <BirthGenderField value={gender} onChange={setGender} />

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
        <AccountCenter compact />
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
