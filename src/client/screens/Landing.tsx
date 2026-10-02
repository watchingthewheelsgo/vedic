import { workspaceCopy } from "../lib/workspace";
import { daysCopy } from "../lib/days-copy";
import { Methodology } from "../components/Methodology";
import { journalCopy } from "../lib/journal";
import { preferredScrollBehavior } from "../lib/motion";
import { SignedIn, SignedOut, SignInButton, SignUpButton } from "@clerk/clerk-react";
import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { AccountCenter } from "../components/AccountCenter";
import { LanguageSwitcher } from "../components/LanguageSwitcher";
import { Button } from "../components/ui/button";
import { useI18n } from "../i18n/provider";

const FEATURES = [
  { id: "core", icon: "◎" },
  { id: "planets", icon: "⬡" },
  { id: "promise", icon: "◈" },
  { id: "areas", icon: "▦" },
  { id: "timing", icon: "◷" },
  { id: "progress", icon: "◉" }
];

const FAQS = ["1", "2", "3"];

export function Landing() {
  const navigate = useNavigate();
  const { t, locale } = useI18n();
  const [openFaq, setOpenFaq] = useState(0);
  const start = () => navigate("/app/charts/new");
  const heroStrong = t("landing.hero.strong");

  return (
    <div className="bg-cream text-ink">
      <nav className="sticky top-0 z-50 border-b border-gold/25 bg-cream/95 px-4 backdrop-blur-xl sm:px-8 lg:px-12">
        <div className="mx-auto flex h-[72px] max-w-[1440px] items-center justify-between gap-3">
          <button
            className="brand-logo shrink-0 border-0 bg-transparent"
            onClick={() => navigate("/welcome")}
          >
            Sign <span>Atlas</span>
          </button>
          <div className="flex items-center gap-2">
            <LanguageSwitcher />
            <SignedOut>
              <SignInButton mode="modal">
                <Button variant="ghost">{t("common.signIn")}</Button>
              </SignInButton>
              <SignUpButton mode="modal">
                <Button>{t("common.createAccount")}</Button>
              </SignUpButton>
            </SignedOut>
            <SignedIn>
              <Button
                variant="ghost"
                className="hidden sm:inline-flex"
                onClick={() => navigate("/app")}
              >
                {workspaceCopy[locale].space}
              </Button>
              <Button className="hidden sm:inline-flex" onClick={start}>
                {t("landing.nav.reportArrow")}
              </Button>
              <AccountCenter />
            </SignedIn>
          </div>
        </div>
      </nav>

      <section className="bg-linear-to-b from-cream to-cream-2 px-6 pb-20 pt-24 text-center sm:px-10 sm:pt-28">
        <div className="mb-9 inline-block rounded-full border border-gold/25 px-5 py-1.5 text-[11px] uppercase tracking-[4px] text-gold">
          {t("landing.eyebrow")}
        </div>
        <h1 className="mb-5 text-[42px] font-light leading-[1.18] tracking-normal text-cream sm:text-[52px]">
          {t("landing.hero.title")}
          {heroStrong ? <strong className="font-semibold text-gold">{heroStrong}</strong> : null}
        </h1>
        <p className="mx-auto mb-10 max-w-[540px] text-[17px] leading-[1.75] text-body">
          {t("landing.hero.body")}
        </p>
        <div className="flex flex-wrap justify-center gap-3">
          <SignedIn>
            <Button size="lg" onClick={() => navigate("/app")} className="px-9">
              {workspaceCopy[locale].homeAction}
            </Button>
            <Button size="lg" variant="outline" onClick={start} className="px-7">
              {t("landing.nav.report")}
            </Button>
          </SignedIn>
          <SignedOut>
            <Button size="lg" onClick={() => navigate("/app")} className="px-9">
              {workspaceCopy[locale].homeAction}
            </Button>
          </SignedOut>
          <Button
            size="lg"
            variant="outline"
            className="px-7"
            onClick={() =>
              document
                .getElementById("traditions")
                ?.scrollIntoView({ behavior: preferredScrollBehavior() })
            }
          >
            {t("landing.paths.explore")}
          </Button>
        </div>
      </section>

      <section className="border-y border-white/8 px-6 py-16 sm:px-10">
        <div className="mx-auto max-w-[1120px]">
          <p className="mb-3 text-xs tracking-widest text-gold">
            SIGN ATLAS · {workspaceCopy[locale].space}
          </p>
          <h2 className="text-3xl font-medium">
            {locale === "zh"
              ? "生活的线索，慢慢连成自己的地图。"
              : locale === "ja"
                ? "日々の出来事から、自分の地図を。"
                : "Turn everyday moments into a map of your own."}
          </h2>
          <div className="mt-10 grid gap-8 sm:grid-cols-3">
            {daysCopy[locale].landingSteps.map((step, i) => (
              <div key={step.title}>
                <p className="mb-4 font-mono text-sm text-gold/70">0{i + 1}</p>
                <h3 className="text-xl">{step.title}</h3>
                <p className="mt-3 text-sm leading-7 text-cream/65">{step.body}</p>
              </div>
            ))}
          </div>
          <Button className="mt-8" onClick={() => navigate("/app")}>
            {workspaceCopy[locale].homeAction} →
          </Button>
          <p className="mt-6 max-w-3xl text-sm leading-7 text-cream/65">
            {locale === "zh"
              ? "这里的 AI 对话帮助你表达和整理感受，不是心理咨询或治疗。轻量文化小游戏与更多娱乐互动正在规划中，尚未开放。"
              : locale === "ja"
                ? "AI との対話は気持ちを言葉にして整理するためのもので、心理相談や治療ではありません。文化を楽しむミニゲームなどの機能は計画中で、まだ利用できません。"
                : "AI conversation helps you express and organize feelings; it is not counseling or therapy. Light cultural mini-games and more playful interactions are planned and not yet available."}
          </p>
        </div>
      </section>
      <section id="traditions" className="bg-cream-2 px-6 py-16 sm:px-10">
        <div className="mx-auto max-w-[1100px]">
          <SectionTitle
            title={t("landing.paths.title")}
            strong=""
            subtitle={t("landing.paths.body")}
          />
          <div className="grid gap-5 md:grid-cols-3">
            {(["vedic", "bazi", "tarot"] as const).map((path, index) => (
              <article
                key={path}
                className="flex flex-col rounded-lg border border-gold/25 bg-cream p-7 sm:p-8"
              >
                <div className="mb-8 flex items-center justify-between text-gold">
                  <span aria-hidden="true" className="font-serif text-5xl">
                    {["☉", "五", "✧"][index]}
                  </span>
                  <span className="text-xs tracking-widest">0{index + 1}</span>
                </div>
                <p className="mb-3 text-xs uppercase tracking-widest text-gold">
                  {t(path === "vedic" ? "landing.paths.live" : "landing.paths.soon")}
                </p>
                <h2 className="mb-4 text-xl font-semibold">{t(`landing.paths.${path}.title`)}</h2>
                <p className="mb-8 flex-1 text-sm leading-7 text-body">
                  {t(`landing.paths.${path}.body`)}
                </p>
                <Button
                  variant={path === "vedic" ? "gold" : "outline"}
                  disabled={path !== "vedic"}
                  onClick={path === "vedic" ? start : undefined}
                >
                  {t(path === "vedic" ? "landing.nav.report" : "landing.paths.soon")}
                </Button>
              </article>
            ))}
          </div>
        </div>
      </section>

      <Section
        className="bg-cream-2"
        title={t("landing.inside.title")}
        strong={t("landing.inside.strong")}
        subtitle={t("landing.inside.subtitle")}
      >
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((feature) => (
            <div key={feature.id} className="rounded-md border border-gold/25 bg-cream px-6 py-8">
              <div className="mb-4 text-[22px] opacity-80">{feature.icon}</div>
              <h3 className="mb-2.5 text-[15px] font-semibold tracking-[0.5px]">
                {t(`landing.feature.${feature.id}.title`)}
              </h3>
              <p className="text-sm leading-[1.75] text-body">
                {t(`landing.feature.${feature.id}.body`)}
              </p>
            </div>
          ))}
        </div>
      </Section>

      <section id="sample" className="bg-night px-6 py-20 text-cream sm:px-10">
        <div className="mx-auto max-w-[1100px]">
          <SectionTitle
            title={t("landing.sample.title")}
            strong={t("landing.sample.strong")}
            subtitle={t("landing.sample.subtitle")}
            dark
          />
          <div className="relative overflow-hidden rounded-lg border border-gold/20 bg-night-2 p-7 sm:p-10 after:absolute after:right-5 after:top-4 after:text-[10px] after:uppercase after:tracking-[3px] after:text-gold after:opacity-40 after:content-['SAMPLE_EXCERPT']">
            <div className="mb-3.5 text-[10px] uppercase tracking-[3px] text-gold">
              {t("landing.sample.badge")}
            </div>
            <div className="mb-4 text-[22px] font-medium text-cream">
              {t("landing.sample.heading")}
            </div>
            <p className="mb-6 text-sm leading-[1.9] text-cream/75">{t("landing.sample.body")}</p>
            <SampleTable />
            <div className="relative mt-1">
              <div className="select-none blur-sm">
                <table className="w-full border-collapse text-[13px]">
                  <tbody>
                    <tr>
                      <td className="border-b border-gold/10 px-3 py-2 text-cream/80">4</td>
                      <td className="border-b border-gold/10 px-3 py-2 text-cream/80">Mercury</td>
                      <td className="border-b border-gold/10 px-3 py-2 text-cream/80">124.6%</td>
                      <td className="border-b border-gold/10 px-3 py-2 text-cream/80">
                        Great Friend · Libra H10 · Atmakaraka
                      </td>
                    </tr>
                    <tr>
                      <td className="border-b border-gold/10 px-3 py-2 text-cream/80">5</td>
                      <td className="border-b border-gold/10 px-3 py-2 text-cream/80">Jupiter</td>
                      <td className="border-b border-gold/10 px-3 py-2 text-cream/80">118.3%</td>
                      <td className="border-b border-gold/10 px-3 py-2 text-cream/80">
                        Neutral · Libra H10 · Current Mahadasha lord
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div className="absolute inset-0 grid place-items-center">
                <Button onClick={start}>{t("landing.sample.unlock")}</Button>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="px-6 py-16 sm:px-10">
        <div className="mx-auto grid max-w-[1000px] gap-5 md:grid-cols-2">
          <div className="rounded-2xl border border-gold/30 bg-gold/10 p-7">
            <h2 className="text-2xl font-medium text-cream">{workspaceCopy[locale].space}</h2>
            <p className="my-4 text-sm leading-7 text-cream/75">{journalCopy[locale].subtitle}</p>
            <p className="mb-6 text-sm leading-7 text-cream/65">
              {workspaceCopy[locale].homeAction} · {journalCopy[locale].history} ·{" "}
              {journalCopy[locale].ask}
            </p>
            <Button onClick={() => navigate("/app")}>{workspaceCopy[locale].homeAction}</Button>
          </div>
          <div className="rounded-2xl border border-white/15 bg-white/[0.035] p-7">
            <h2 className="text-2xl font-medium text-cream">{t("landing.paths.vedic.title")}</h2>
            <p className="my-4 text-sm leading-7 text-cream/75">{t("landing.paths.vedic.body")}</p>
            <p className="mb-6 text-sm text-cream/65">
              {locale === "zh"
                ? "记录与日常使用免费，每月包含 10 个 AI 额度。需要更多额度时，可在反馈窗口申请升级。"
                : locale === "ja"
                  ? "記録と日常利用は無料。毎月10 AIクレジット付き。追加はフィードバックからお問い合わせください。"
                  : "Free daily records and 10 AI credits every month. Request more credits through the feedback window."}
            </p>
            <Button variant="outline" onClick={start}>
              {t("landing.nav.reportArrow")}
            </Button>
          </div>
        </div>
      </section>

      <Methodology />
      <Section
        className="bg-cream-2"
        title={t("landing.faq.title")}
        strong={t("landing.faq.strong")}
      >
        <div className="mx-auto max-w-[700px]">
          {FAQS.map((item, index) => (
            <div key={item} className="border-b border-gold/25 py-5">
              <button
                className="flex w-full items-center justify-between gap-4 bg-transparent text-left text-[15px] font-medium"
                id={`faq-trigger-${item}`}
                aria-expanded={openFaq === index}
                aria-controls={`faq-panel-${item}`}
                onClick={() => setOpenFaq(openFaq === index ? -1 : index)}
              >
                {t(`landing.faq.q${item}`)}
                <span
                  className={`shrink-0 text-lg text-gold transition ${openFaq === index ? "rotate-180" : ""}`}
                >
                  ↓
                </span>
              </button>
              <div
                id={`faq-panel-${item}`}
                role="region"
                aria-labelledby={`faq-trigger-${item}`}
                hidden={openFaq !== index}
              >
                <p className="mt-3 text-sm leading-[1.85] text-body">{t(`landing.faq.a${item}`)}</p>
              </div>
            </div>
          ))}
        </div>
      </Section>

      <footer className="bg-night px-5 py-8 text-center text-[13px] tracking-[0.3px] text-cream/40">
        <div className="mb-4 flex flex-wrap justify-center gap-x-6 gap-y-3 text-cream/75">
          <a href="#sources" className="underline underline-offset-4">
            {locale === "zh"
              ? "方法与来源"
              : locale === "ja"
                ? "方法と参考文献"
                : "Methods & sources"}
          </a>
          <a href="mailto:lizero.why@gmail.com" className="underline underline-offset-4">
            lizero.why@gmail.com
          </a>
        </div>
        <p>
          © 2026 <span className="text-gold/60">Sign Atlas</span> &nbsp;·&nbsp;{" "}
          {t("landing.footer")}
        </p>
      </footer>
    </div>
  );
}

function Section({
  title,
  strong,
  subtitle,
  className = "",
  children
}: {
  title: string;
  strong: string;
  subtitle?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section className={`px-6 py-20 sm:px-10 ${className}`}>
      <div className="mx-auto max-w-[1100px]">
        <SectionTitle title={title} strong={strong} subtitle={subtitle} />
        {children}
      </div>
    </section>
  );
}

function SectionTitle({
  title,
  strong,
  subtitle,
  dark = false
}: {
  title: string;
  strong: string;
  subtitle?: string;
  dark?: boolean;
}) {
  return (
    <div className="mb-14 text-center">
      <h2
        className={`mb-3 text-[34px] font-light tracking-normal ${dark ? "text-cream" : "text-ink"}`}
      >
        {title} <strong className="font-semibold text-gold">{strong}</strong>
      </h2>
      <div className="mx-auto mt-4 h-px w-9 bg-gold" />
      {subtitle && (
        <p className={`mt-2.5 text-[15px] ${dark ? "text-cream/55" : "text-body"}`}>{subtitle}</p>
      )}
    </div>
  );
}

function SampleTable() {
  const { t } = useI18n();
  const rows = [
    ["1", "Moon", "High", t("landing.sample.row1")],
    ["2", "Saturn", "High", t("landing.sample.row2")],
    ["3", "Sun", "Strong", t("landing.sample.row3")]
  ];
  return (
    <table className="w-full border-collapse text-[13px]">
      <tbody>
        <tr>
          {[
            t("landing.sample.rank"),
            t("landing.sample.signal"),
            t("landing.sample.weight"),
            t("landing.sample.note")
          ].map((header) => (
            <th
              key={header}
              className="bg-gold/10 px-3 py-2 text-left text-[11px] font-medium uppercase tracking-[1px] text-gold"
            >
              {header}
            </th>
          ))}
        </tr>
        {rows.map((row) => (
          <tr key={row[0]}>
            {row.map((cell, index) => (
              <td
                key={`${row[0]}-${index}`}
                className="border-b border-gold/10 px-3 py-2 text-cream/80"
              >
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
