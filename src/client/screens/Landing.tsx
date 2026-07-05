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
  const { t } = useI18n();
  const [openFaq, setOpenFaq] = useState(0);
  const start = () => navigate("/new");
  const heroStrong = t("landing.hero.strong");

  return (
    <div className="bg-cream text-ink">
      <nav className="sticky top-0 z-50 border-b border-gold/25 bg-cream/95 px-6 backdrop-blur-xl sm:px-10">
        <div className="mx-auto flex h-16 max-w-[1100px] items-center justify-between">
          <button className="brand-logo border-0 bg-transparent" onClick={() => navigate("/")}>
            Veda<span>Light</span>
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
              <Button onClick={start}>{t("landing.nav.reportArrow")}</Button>
              <AccountCenter />
            </SignedIn>
          </div>
        </div>
      </nav>

      <section className="bg-linear-to-b from-cream to-cream-2 px-6 pb-20 pt-24 text-center sm:px-10 sm:pt-28">
        <div className="mb-9 inline-block rounded-full border border-gold/25 px-5 py-1.5 text-[11px] uppercase tracking-[4px] text-gold">
          {t("landing.eyebrow")}
        </div>
        <h1 className="mb-5 text-[42px] font-light leading-[1.18] tracking-normal text-night sm:text-[52px]">
          {t("landing.hero.title")}
          {heroStrong ? <strong className="font-semibold text-gold">{heroStrong}</strong> : null}
        </h1>
        <p className="mx-auto mb-10 max-w-[540px] text-[17px] leading-[1.75] text-body">
          {t("landing.hero.body")}
        </p>
        <div className="flex flex-wrap justify-center gap-3">
          <Button size="lg" onClick={start} className="px-9">
            {t("landing.nav.report")}
          </Button>
          <Button
            size="lg"
            variant="outline"
            className="px-7"
            onClick={() =>
              document.getElementById("sample")?.scrollIntoView({ behavior: "smooth" })
            }
          >
            {t("landing.nav.sample")}
          </Button>
        </div>
        <div className="mt-14 flex flex-wrap justify-center gap-10 sm:gap-12">
          <HeroMeta value="41" label={t("landing.meta.pages")} />
          <HeroMeta value="9" label={t("landing.meta.planets")} />
          <HeroMeta value="12" label={t("landing.meta.lifeAreas")} />
          <HeroMeta value="D9" label={t("landing.meta.d9")} />
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

      <Section
        title={t("landing.plan.title")}
        strong={t("landing.plan.strong")}
        subtitle={t("landing.plan.subtitle")}
      >
        <div className="mx-auto grid max-w-[760px] gap-5 md:grid-cols-2">
          <PriceCard
            name={t("landing.plan.essential.name")}
            price="$39"
            description={t("landing.plan.essential.description")}
            features={[
              t("landing.plan.essential.f1"),
              t("landing.plan.essential.f2"),
              t("landing.plan.essential.f3"),
              t("landing.plan.essential.f4")
            ]}
            onClick={start}
          />
          <PriceCard
            featured
            name={t("landing.plan.pro.name")}
            price="$79"
            description={t("landing.plan.pro.description")}
            features={[
              t("landing.plan.pro.f1"),
              t("landing.plan.pro.f2"),
              t("landing.plan.pro.f3"),
              t("landing.plan.pro.f4"),
              t("landing.plan.pro.f5"),
              t("landing.plan.pro.f6")
            ]}
            onClick={start}
          />
        </div>
      </Section>

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
                onClick={() => setOpenFaq(openFaq === index ? -1 : index)}
              >
                {t(`landing.faq.q${item}`)}
                <span
                  className={`shrink-0 text-lg text-gold transition ${openFaq === index ? "rotate-180" : ""}`}
                >
                  ↓
                </span>
              </button>
              {openFaq === index && (
                <p className="mt-3 text-sm leading-[1.85] text-body">{t(`landing.faq.a${item}`)}</p>
              )}
            </div>
          ))}
        </div>
      </Section>

      <footer className="bg-night px-5 py-8 text-center text-[13px] tracking-[0.3px] text-cream/40">
        <p>
          © 2026 <span className="text-gold/60">VedaLight</span> &nbsp;·&nbsp; {t("landing.footer")}
        </p>
      </footer>
    </div>
  );
}

function HeroMeta({ value, label }: { value: string; label: string }) {
  return (
    <div className="text-center">
      <div className="text-[30px] font-semibold text-gold">{value}</div>
      <div className="mt-0.5 text-xs tracking-[0.5px] text-muted">{label}</div>
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

function PriceCard({
  featured = false,
  name,
  price,
  description,
  features,
  onClick
}: {
  featured?: boolean;
  name: string;
  price: string;
  description: string;
  features: string[];
  onClick: () => void;
}) {
  const { t } = useI18n();
  return (
    <div
      className={`relative rounded-md border bg-cream p-9 ${featured ? "border-gold shadow-[0_0_0_1px_var(--color-gold)]" : "border-gold/25"}`}
    >
      {featured && (
        <div className="absolute left-1/2 top-[-13px] -translate-x-1/2 rounded-full bg-gold px-3.5 py-1 text-[10px] uppercase tracking-[2px] text-white">
          {t("landing.plan.popular")}
        </div>
      )}
      <div className="mb-2 text-xs uppercase tracking-[2px] text-muted">{name}</div>
      <div className="mb-1 text-[44px] font-semibold text-ink">
        {price}
        <span className="text-[15px] font-normal text-muted"> {t("landing.plan.unit")}</span>
      </div>
      <p className="mb-6 border-b border-gold/25 pb-6 text-[13px] text-body">{description}</p>
      <ul className="mb-8 space-y-2">
        {features.map((feature) => (
          <li
            key={feature}
            className="flex items-start gap-2.5 text-sm text-body before:mt-0.5 before:font-bold before:text-gold before:content-['✓']"
          >
            {feature}
          </li>
        ))}
      </ul>
      <Button variant={featured ? "gold" : "outline"} className="w-full" onClick={onClick}>
        {t("landing.plan.choose", { name })}
      </Button>
    </div>
  );
}
