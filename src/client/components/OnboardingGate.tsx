import { FormEvent, useMemo, useState } from "react";
import { useClerk } from "@clerk/clerk-react";
import { LoaderCircle } from "lucide-react";
import { api } from "../api";
import { useI18n } from "../i18n/provider";
import type { LocaleCode } from "../i18n/messages";
import { REQUIRED_GENDER_OPTIONS, formatBirthDate } from "../lib/birth-details";
import { formatBirthTime, normalizeTimeForPrecision } from "../lib/birth-time";
import type { BirthTimePrecision } from "../../shared/domain";
import {
  BirthDateTimeFields,
  BirthGenderField,
  BirthNameField,
  BirthPlaceField,
  BirthTimePrecisionField
} from "./BirthDetailsFields";

type Errors = Partial<Record<"birthDate" | "birthTime" | "place" | "gender" | "submit", string>>;

const copy: Record<
  LocaleCode,
  {
    eyebrow: string;
    title: string;
    body: string;
    submit: string;
    busy: string;
    signOut: string;
    note: string;
  }
> = {
  en: {
    eyebrow: "Welcome to Sign Atlas",
    title: "Let's start with you",
    body: "Your birth details let Sign Atlas draw your daily card, find your auspicious days and answer as you, not people in general. It takes half a minute.",
    submit: "Create my chart",
    busy: "Calculating your chart…",
    signOut: "Sign out",
    note: "Private to your account. A full Vedic reading can be added any time."
  },
  zh: {
    eyebrow: "欢迎来到 Sign Atlas",
    title: "先认识一下你",
    body: "有了出生信息，Sign Atlas 才能为你抽今日之签、找出属于你的顺日，并以你为中心回答问题。只需要半分钟。",
    submit: "生成我的命盘",
    busy: "正在排盘……",
    signOut: "退出登录",
    note: "信息只保存在你的账户中。之后随时可以生成完整的 Vedic 解读。"
  },
  ja: {
    eyebrow: "Sign Atlas へようこそ",
    title: "まずはあなたのことを",
    body: "出生情報があると、今日のカード、あなたの吉日、あなた自身に向けた回答が使えるようになります。30秒ほどで終わります。",
    submit: "チャートを作成",
    busy: "チャートを計算中…",
    signOut: "ログアウト",
    note: "情報はあなたのアカウントにのみ保存されます。Vedic リーディングはいつでも追加できます。"
  }
};

/**
 * Shown over the workspace while the account has no chart: the daily card, Good for /
 * Avoid, auspicious days and Atlas all need a Day Master. Submitting calculates a BaZi
 * chart (deterministic, no AI credits), then reloads the workspace with it.
 */
export function OnboardingGate() {
  const { locale, t } = useI18n();
  const c = copy[locale];
  const { signOut } = useClerk();
  const [birthDate, setBirthDate] = useState<Date | null>(null);
  const [birthTime, setBirthTime] = useState<Date | null>(null);
  const [precision, setPrecision] = useState<BirthTimePrecision>("exact");
  const [place, setPlace] = useState("");
  const [name, setName] = useState("");
  const [gender, setGender] = useState("");
  const [errors, setErrors] = useState<Errors>({});
  const [busy, setBusy] = useState(false);
  const today = useMemo(() => new Date(), []);

  const clear = (key: keyof Errors) =>
    setErrors((current) => {
      const next = { ...current };
      delete next[key];
      return next;
    });

  async function submit(event: FormEvent) {
    event.preventDefault();
    const next: Errors = {};
    if (!birthDate) next.birthDate = t("intake.error.birthDate");
    if (precision !== "unknown" && !birthTime) {
      next.birthTime =
        precision === "part_of_day" ? t("intake.error.birthHour") : t("intake.error.birthTime");
    }
    if (!place) next.place = t("intake.error.place");
    if (!gender) next.gender = t("bazi.error.gender");
    if (Object.keys(next).length) {
      setErrors(next);
      return;
    }
    setBusy(true);
    setErrors({});
    try {
      await api.createBaziSession({
        birthDate: formatBirthDate(birthDate),
        birthTime: precision === "unknown" ? "" : formatBirthTime(birthTime, precision),
        birthPlace: place,
        birthTimePrecision: precision,
        gender,
        relationship: "self",
        timeSource: precision === "exact" ? "user-provided" : "not-exact",
        locale,
        calendarType: "solar",
        currentDate: formatBirthDate(today),
        audience: "self",
        topic: name.trim() ? `Name: ${name.trim()}` : "[not provided]"
      });
      // Charts, guidance and Atlas all read the new chart on a fresh load of Today.
      window.location.replace("/app");
    } catch (caught) {
      setErrors({ submit: caught instanceof Error ? caught.message : t("bazi.error.start") });
      setBusy(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="onboarding-title"
      className="fixed inset-0 z-[90] overflow-y-auto bg-[#05060a]/90 backdrop-blur-md"
    >
      <div className="flex min-h-full items-center justify-center p-4 sm:p-8">
        <div
          data-theme="cosmic"
          className="birth-input-screen fortune-dialog w-full max-w-[560px] rounded-[28px] border border-white/10 bg-night-2 shadow-[0_40px_120px_rgba(0,0,0,0.6)]"
        >
          <form onSubmit={submit} noValidate className="birth-input-form-panel p-6 sm:p-9">
            <p className="text-xs uppercase tracking-[0.2em] text-gold/80">{c.eyebrow}</p>
            <h1 id="onboarding-title" className="mt-2 font-display text-[38px] leading-tight">
              {c.title}
            </h1>
            <p className="mb-7 mt-2 text-sm leading-6 text-cream/60">{c.body}</p>

            <div className="flex flex-col gap-5">
              <BirthDateTimeFields
                birthDate={birthDate}
                birthTime={birthTime}
                timePrecision={precision}
                errors={errors}
                onBirthDateChange={(date) => {
                  setBirthDate(date);
                  clear("birthDate");
                }}
                onBirthTimeChange={(date) => {
                  setBirthTime(date);
                  clear("birthTime");
                }}
              />
              <BirthTimePrecisionField
                value={precision}
                onChange={(next) => {
                  setPrecision(next);
                  setBirthTime((current) => normalizeTimeForPrecision(current, next));
                  if (next === "unknown") clear("birthTime");
                }}
              />
              <BirthPlaceField
                value={place}
                onChange={(value) => {
                  setPlace(value);
                  if (value) clear("place");
                }}
                error={errors.place}
              />
              <div className="grid gap-4 sm:grid-cols-2">
                <BirthNameField value={name} onChange={setName} />
                <BirthGenderField
                  value={gender}
                  error={errors.gender}
                  options={REQUIRED_GENDER_OPTIONS}
                  onChange={(value) => {
                    setGender(value);
                    clear("gender");
                  }}
                />
              </div>
            </div>

            {errors.submit && (
              <p role="alert" className="mt-4 text-sm text-[#ffb5a4]">
                {errors.submit}
              </p>
            )}

            <button
              type="submit"
              disabled={busy}
              className="press-feedback mt-6 flex h-12 w-full items-center justify-center gap-2 rounded-full bg-paper text-[15px] font-medium text-[#16130e] disabled:opacity-60"
            >
              {busy && <LoaderCircle className="size-4 animate-spin" />}
              {busy ? c.busy : c.submit}
            </button>
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-xs text-cream/45">
              <span>{c.note}</span>
              <button
                type="button"
                onClick={() => void signOut({ redirectUrl: "/" })}
                className="underline-offset-4 hover:text-cream hover:underline"
              >
                {c.signOut}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
