import { FormEvent, useMemo, useState } from "react";
import { useClerk } from "@clerk/clerk-react";
import { LoaderCircle } from "lucide-react";
import { api } from "../api";
import { useI18n } from "../i18n/provider";
import type { LocaleCode } from "../i18n/messages";
import { formatBirthDate } from "../lib/birth-details";
import { PlaceSelect, type SelectedPlace } from "./PlaceSelect";

type Errors = Partial<Record<"birthDate" | "gender" | "place" | "submit", string>>;

const copy: Record<
  LocaleCode,
  {
    eyebrow: string;
    title: string;
    body: string;
    date: string;
    time: string;
    timeHint: string;
    gender: string;
    female: string;
    male: string;
    place: string;
    placeError: string;
    submit: string;
    busy: string;
    signOut: string;
    note: string;
  }
> = {
  en: {
    eyebrow: "Welcome to Sign Atlas",
    title: "Let's start with you",
    body: "Your birthday, birthplace and gender are all Sign Atlas needs to draw your daily card, find your auspicious days and let Atlas answer as you.",
    date: "Date of birth",
    time: "Birth time",
    timeHint: "Optional. Leave it empty if you don't know.",
    gender: "Gender",
    female: "Female",
    male: "Male",
    place: "Place of birth",
    placeError: "Choose where you were born.",
    submit: "Save and continue",
    busy: "Saving…",
    signOut: "Sign out",
    note: "Private to your account. You can change it any time in Account."
  },
  zh: {
    eyebrow: "欢迎来到 Sign Atlas",
    title: "先认识一下你",
    body: "只需要生日、出生地和性别，就能为你抽今日之签、找出属于你的顺日，并让 Atlas 以你为中心回答问题。",
    date: "出生日期",
    time: "出生时间",
    timeHint: "选填，不记得可以留空。",
    gender: "性别",
    female: "女",
    male: "男",
    place: "出生地",
    placeError: "请选择你的出生地。",
    submit: "保存并继续",
    busy: "正在保存……",
    signOut: "退出登录",
    note: "信息只保存在你的账户中，之后可在账户页随时修改。"
  },
  ja: {
    eyebrow: "Sign Atlas へようこそ",
    title: "まずはあなたのことを",
    body: "誕生日・出生地・性別だけで、今日のカード、あなたの吉日、あなたに向けた Atlas の回答が使えます。",
    date: "生年月日",
    time: "出生時刻",
    timeHint: "任意。わからなければ空欄で大丈夫です。",
    gender: "性別",
    female: "女性",
    male: "男性",
    place: "出生地",
    placeError: "出生地を選んでください。",
    submit: "保存して続ける",
    busy: "保存中…",
    signOut: "ログアウト",
    note: "情報はあなたのアカウントにのみ保存され、アカウントページでいつでも変更できます。"
  }
};

const field =
  "h-12 w-full rounded-2xl border border-white/12 bg-white/[0.035] px-4 text-base text-cream outline-none transition-colors [color-scheme:dark] focus:border-gold/70";

/**
 * Shown over the workspace until the owner's birth details are known: date, place and
 * gender, with an optional time. It only saves a profile (no chart or reading is
 * created); exact time certainty and address belong to the reading flows.
 */
export function OnboardingGate() {
  const { locale, t } = useI18n();
  const c = copy[locale];
  const { signOut } = useClerk();
  const [birthDate, setBirthDate] = useState("");
  const [birthTime, setBirthTime] = useState("");
  const [gender, setGender] = useState("");
  const [place, setPlace] = useState<SelectedPlace | null>(null);
  const [errors, setErrors] = useState<Errors>({});
  const [busy, setBusy] = useState(false);
  const today = useMemo(() => new Date(), []);
  const maxDate = formatBirthDate(today);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const next: Errors = {};
    if (!/^\d{4}-\d{2}-\d{2}$/.test(birthDate) || birthDate > maxDate) {
      next.birthDate = t("intake.error.birthDate");
    }
    if (!gender) next.gender = t("bazi.error.gender");
    if (!place) next.place = c.placeError;
    if (Object.keys(next).length || !place) {
      setErrors(next);
      return;
    }
    setBusy(true);
    setErrors({});
    try {
      await api.saveProfile({
        birthDate,
        birthTime,
        birthPlace: place.place,
        placeLabel: place.label,
        timezone: place.timezone,
        gender: gender as "女" | "男"
      });
      // Guidance, the daily card and Atlas all read the new profile on a fresh load of Today.
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
        <form
          onSubmit={submit}
          noValidate
          className="fortune-dialog w-full max-w-[560px] rounded-[28px] border border-white/10 bg-night-2 p-6 shadow-[0_40px_120px_rgba(0,0,0,0.6)] sm:p-9"
        >
          <p className="text-xs uppercase tracking-[0.2em] text-gold/80">{c.eyebrow}</p>
          <h1 id="onboarding-title" className="mt-2 font-display text-[38px] leading-tight">
            {c.title}
          </h1>
          <p className="mt-2 text-sm leading-6 text-cream/60">{c.body}</p>

          <div className="mt-7 flex flex-col gap-5">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="onboarding-date" className="mb-2 block text-sm text-cream/75">
                  {c.date}
                </label>
                <input
                  id="onboarding-date"
                  type="date"
                  value={birthDate}
                  max={maxDate}
                  min="1901-01-01"
                  aria-invalid={Boolean(errors.birthDate)}
                  onChange={(event) => setBirthDate(event.target.value)}
                  className={`${field} ${errors.birthDate ? "border-red/70" : ""}`}
                />
                {errors.birthDate && (
                  <p className="mt-1.5 text-xs text-[#ffb5a4]">{errors.birthDate}</p>
                )}
              </div>
              <div>
                <label htmlFor="onboarding-time" className="mb-2 block text-sm text-cream/75">
                  {c.time}
                </label>
                <input
                  id="onboarding-time"
                  type="time"
                  value={birthTime}
                  onChange={(event) => setBirthTime(event.target.value)}
                  className={field}
                />
                <p className="mt-1.5 text-xs text-cream/40">{c.timeHint}</p>
              </div>
            </div>

            <fieldset>
              <legend className="mb-2 text-sm text-cream/75">{c.gender}</legend>
              <div className="grid grid-cols-2 gap-2">
                {[
                  { value: "女", label: c.female },
                  { value: "男", label: c.male }
                ].map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    aria-pressed={gender === option.value}
                    onClick={() => setGender(option.value)}
                    className={`h-12 rounded-2xl border text-[15px] transition-colors ${
                      gender === option.value
                        ? "border-gold/60 bg-gold/[0.12] text-gold-light"
                        : "border-white/12 bg-white/[0.02] text-cream/70 hover:border-white/25"
                    }`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
              {errors.gender && <p className="mt-1.5 text-xs text-[#ffb5a4]">{errors.gender}</p>}
            </fieldset>

            <div>
              <p className="mb-2 text-sm text-cream/75">{c.place}</p>
              <PlaceSelect locale={locale} error={errors.place} onChange={setPlace} />
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
            className="press-feedback mt-7 flex h-12 w-full items-center justify-center gap-2 rounded-full bg-paper text-[15px] font-medium text-[#16130e] disabled:opacity-60"
          >
            {busy && <LoaderCircle className="size-4 animate-spin" />}
            {busy ? c.busy : c.submit}
          </button>
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-xs text-cream/45">
            <span className="max-w-[300px]">{c.note}</span>
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
  );
}
