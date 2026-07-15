import { SignedIn, SignedOut, SignInButton, SignUpButton } from "@clerk/clerk-react";
import { FormEvent, useMemo, useState, type Dispatch, type SetStateAction } from "react";
import { Compass, ScrollText } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { BirthInputLayout } from "../components/BirthInputLayout";
import {
  BirthDateTimeFields,
  BirthGenderField,
  BirthNameField,
  BirthPlaceField,
  BirthTimePrecisionField
} from "../components/BirthDetailsFields";
import { AccountCenter } from "../components/AccountCenter";
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
import { useI18n } from "../i18n/provider";
import { REQUIRED_GENDER_OPTIONS, formatBirthDate } from "../lib/birth-details";
import { formatBirthTime, normalizeTimeForPrecision } from "../lib/birth-time";
import type { BaziCalendarType, BirthTimePrecision } from "../../shared/domain";

type FormErrors = Partial<
  Record<"birthDate" | "birthTime" | "place" | "gender" | "submit", string>
>;

const CALENDAR_OPTIONS: Array<{ value: BaziCalendarType; labelKey: string }> = [
  { value: "solar", labelKey: "bazi.calendar.solar" },
  { value: "lunar", labelKey: "bazi.calendar.lunar" }
];

export function BaziWorkshop() {
  const navigate = useNavigate();
  const { locale, t } = useI18n();
  const [birthDate, setBirthDate] = useState<Date | null>(null);
  const [birthTime, setBirthTime] = useState<Date | null>(null);
  const [place, setPlace] = useState("");
  const [name, setName] = useState("");
  const [gender, setGender] = useState("");
  const [calendarType, setCalendarType] = useState<BaziCalendarType>("solar");
  const [timePrecision, setTimePrecision] = useState<BirthTimePrecision>("exact");
  const [topic, setTopic] = useState("");
  const [errors, setErrors] = useState<FormErrors>({});
  const [busy, setBusy] = useState(false);

  const today = useMemo(() => new Date(), []);

  async function onStart(event: FormEvent) {
    event.preventDefault();
    const nextErrors: FormErrors = {};
    if (!birthDate) nextErrors.birthDate = t("intake.error.birthDate");
    if (timePrecision !== "unknown" && !birthTime) {
      nextErrors.birthTime =
        timePrecision === "part_of_day" ? t("intake.error.birthHour") : t("intake.error.birthTime");
    }
    if (!place) nextErrors.place = t("intake.error.place");
    if (!gender) nextErrors.gender = t("bazi.error.gender");

    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors);
      return;
    }

    setBusy(true);
    setErrors({});
    try {
      const birthDateText = formatBirthDate(birthDate);
      const birthTimeText =
        timePrecision === "unknown" ? "" : formatBirthTime(birthTime, timePrecision);
      const session = await api.createBaziSession({
        birthDate: birthDateText,
        birthTime: birthTimeText,
        birthPlace: place,
        birthTimePrecision: timePrecision,
        gender,
        relationship: "self",
        timeSource: timePrecision === "exact" ? "user-provided" : "not-exact",
        locale,
        calendarType,
        currentDate: formatBirthDate(today),
        audience: "self",
        topic: topic.trim() || "[not provided]"
      });
      navigate(`/session/${session.sessionId}?tab=reading`, {
        state: {
          name,
          concern: topic,
          birth: {
            birthDate: birthDateText,
            birthTime: birthTimeText,
            birthPlace: place,
            birthTimePrecision: timePrecision,
            gender,
            relationship: "self",
            timeSource: timePrecision === "exact" ? "user-provided" : "not-exact",
            locale
          }
        }
      });
    } catch (caught) {
      setErrors({
        submit: caught instanceof Error ? caught.message : t("bazi.error.start")
      });
      setBusy(false);
    }
  }

  return (
    <BirthInputLayout
      navControls={<BaziAuthControls />}
      backLabel={t("common.back")}
      title={t("bazi.title")}
      subtitle={t("bazi.subtitle")}
      icon={<ScrollText size={18} />}
      badge={
        <div className="rounded-full border border-gold/25 bg-gold/10 px-3 py-1 text-[11px] uppercase tracking-[1.6px] text-gold-dim">
          {t("bazi.hiddenBadge")}
        </div>
      }
      steps={[
        { active: true, label: t("intake.step.personal"), index: 1 },
        { label: t("bazi.step.chart"), index: 2 },
        { label: t("intake.step.report"), index: 3 }
      ]}
      maxWidthClass="max-w-[620px]"
      onBack={() => navigate("/")}
    >
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

        <div className="grid gap-4 md:grid-cols-2">
          <Field
            label={t("bazi.calendar.label")}
            icon={<Compass size={16} />}
            hint={t("bazi.calendar.hint")}
          >
            <Select
              value={calendarType}
              onValueChange={(value) => setCalendarType(value as BaziCalendarType)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CALENDAR_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {t(option.labelKey)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>

          <BirthTimePrecisionField
            value={timePrecision}
            onChange={(next) => {
              setTimePrecision(next);
              setBirthTime((current) => normalizeTimeForPrecision(current, next));
              if (next === "unknown") {
                clearError(setErrors, "birthTime");
              }
            }}
          />
        </div>

        <BirthPlaceField
          value={place}
          onChange={(value) => {
            setPlace(value);
            if (value) clearError(setErrors, "place");
          }}
          error={errors.place}
        />

        <div className="grid gap-4 md:grid-cols-2">
          <BirthNameField value={name} onChange={setName} />

          <BirthGenderField
            value={gender}
            error={errors.gender}
            options={REQUIRED_GENDER_OPTIONS}
            hint={t("bazi.gender.hint")}
            onChange={(value) => {
              setGender(value);
              clearError(setErrors, "gender");
            }}
          />
        </div>

        <Field label={t("bazi.focus.label")} hint={t("bazi.focus.hint")}>
          <Textarea
            rows={4}
            value={topic}
            onChange={(event) => setTopic(event.target.value)}
            placeholder={t("bazi.focus.placeholder")}
          />
        </Field>

        {errors.submit && (
          <div className="mt-1 rounded-md border border-red/30 bg-red/10 px-4 py-3 text-[13px] text-red">
            {errors.submit}
          </div>
        )}

        <Button className="mt-2 w-full" size="lg" disabled={busy}>
          {busy ? t("bazi.submit.busy") : t("bazi.submit")}
        </Button>
      </form>
    </BirthInputLayout>
  );
}

function BaziAuthControls() {
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

function clearError(setErrors: Dispatch<SetStateAction<FormErrors>>, key: keyof FormErrors) {
  setErrors((current) => {
    if (!current[key]) return current;
    const next = { ...current };
    delete next[key];
    return next;
  });
}
