import { SignedIn, SignedOut, SignInButton, SignUpButton } from "@clerk/clerk-react";
import { FormEvent, useMemo, useState, type Dispatch, type SetStateAction } from "react";
import { Compass, ScrollText } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
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
import { Card, CardContent } from "../components/ui/card";
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

const CALENDAR_OPTIONS: Array<{ value: BaziCalendarType; label: string }> = [
  { value: "solar", label: "Solar / 阳历" },
  { value: "lunar", label: "Lunar / 农历" }
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
    if (!gender) nextErrors.gender = "Gender is required for major-luck direction.";

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
        submit: caught instanceof Error ? caught.message : "Could not start BaZi workshop."
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
          <BaziAuthControls />
        </div>
      </nav>

      <main className="px-5 py-9 sm:px-10 sm:py-14">
        <div className="mx-auto max-w-[820px]">
          <div className="mb-8 flex items-center justify-between gap-4">
            <button
              className="inline-flex items-center gap-1 border-0 bg-transparent text-sm text-muted transition hover:text-ink"
              onClick={() => navigate("/")}
            >
              ← {t("common.back")}
            </button>
            <div className="rounded-full border border-gold/25 bg-gold/10 px-3 py-1 text-[11px] uppercase tracking-[1.6px] text-gold-dim">
              Hidden BaZi Workshop
            </div>
          </div>

          <section className="mb-7 flex items-start gap-3.5">
            <div className="grid size-[38px] shrink-0 place-items-center rounded-[10px] bg-night text-gold shadow-[0_10px_24px_rgba(15,12,9,0.12)]">
              <ScrollText size={18} />
            </div>
            <div>
              <h1 className="mb-1.5 text-[27px] font-light tracking-normal text-ink">
                BaZi Workshop
              </h1>
              <p className="max-w-[620px] text-sm leading-relaxed text-body">
                Generate the four pillars and luck-cycle workspace first, then run the classical
                report from the workshop page.
              </p>
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

                <div className="grid gap-4 md:grid-cols-2">
                  <Field label="Calendar" icon={<Compass size={16} />} hint="Default is solar.">
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
                            {option.label}
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
                    hint="Required by the BaZi luck-cycle direction algorithm."
                    onChange={(value) => {
                      setGender(value);
                      clearError(setErrors, "gender");
                    }}
                  />
                </div>

                <Field label="Focus" hint="Optional. Kept as report context for the classical run.">
                  <Textarea
                    rows={4}
                    value={topic}
                    onChange={(event) => setTopic(event.target.value)}
                    placeholder="Career, relationship, timing, general life direction..."
                  />
                </Field>

                {errors.submit && (
                  <div className="mt-1 rounded-md border border-red/30 bg-red/10 px-4 py-3 text-[13px] text-red">
                    {errors.submit}
                  </div>
                )}

                <Button className="mt-2 w-full" size="lg" disabled={busy}>
                  {busy ? "Preparing BaZi workshop..." : "Open BaZi Workshop"}
                </Button>
              </form>
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
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
