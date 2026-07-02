import { useState } from "react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "../components/ui/button";

const FEATURES = [
  { icon: "◎", title: "Identity Overview", body: "Ascendant (Lagna), chart lord, Moon sign. Understand your core temperament, inner needs, and how the world perceives you." },
  { icon: "⬡", title: "Planetary Audit", body: "All 9 planets analyzed with Shadbala scores and SAV/BAV strength metrics - quantified, not generic." },
  { icon: "◈", title: "D9 Navamsha Deep Dive", body: "What D1 promises, D9 reveals. Uncover the deeper quality of each planet - true fulfillment vs. surface expression." },
  { icon: "▦", title: "All 12 House Diagnosis", body: "From House 1 (self) to House 12 (spirituality) - career, wealth, family, relationships, health, each fully diagnosed." },
  { icon: "◷", title: "Dasha Timeline", body: "Vimsottari Mahadasha + Antardasha mapping. Know which planetary period governs your life now, and what each phase brings." },
  { icon: "◉", title: "Live Generation Flow", body: "Watch your report build in real time - every analysis stage, dependency, and its progress on an interactive pipeline." }
];

const FAQS = [
  { q: "How is Vedic Astrology different from Western Astrology?", a: "Vedic Astrology (Jyotish) uses the Sidereal zodiac - aligned with actual star positions - while Western astrology uses the Tropical zodiac. The two differ by ~23°. Vedic emphasizes the Ascendant (Lagna), quantified planetary strength (Shadbala), and the Dasha time-period system for event-level predictions." },
  { q: "Do I need my exact birth time?", a: "Yes - birth time is critical for calculating your Ascendant (Lagna), the foundation of the entire chart. A 2-hour difference can shift your Ascendant to a completely different sign. Check your birth certificate or hospital records." },
  { q: "How long does report generation take?", a: "The full report is a multi-stage analysis of ~48 nodes. It runs in a few minutes; you can watch each stage complete live in the Workshop tab." }
];

export function Landing() {
  const navigate = useNavigate();
  const [openFaq, setOpenFaq] = useState(0);
  const start = () => navigate("/new");

  return (
    <div className="bg-cream text-ink">
      <nav className="sticky top-0 z-50 border-b border-gold/25 bg-cream/95 px-6 backdrop-blur-xl sm:px-10">
        <div className="mx-auto flex h-16 max-w-[1100px] items-center justify-between">
          <button className="brand-logo border-0 bg-transparent" onClick={() => navigate("/")}>
            Veda<span>Light</span>
          </button>
          <Button onClick={start}>Get My Report →</Button>
        </div>
      </nav>

      <section className="bg-linear-to-b from-cream to-cream-2 px-6 pb-20 pt-24 text-center sm:px-10 sm:pt-28">
        <div className="mb-9 inline-block rounded-full border border-gold/25 px-5 py-1.5 text-[11px] uppercase tracking-[4px] text-gold">
          Parashari Jyotish · KN Rao School
        </div>
        <h1 className="mb-5 text-[42px] font-light leading-[1.18] tracking-normal text-night sm:text-[52px]">
          Your Birth Chart,
          <br />
          <strong className="font-semibold text-gold">Decoded with Data</strong>
        </h1>
        <p className="mx-auto mb-10 max-w-[540px] text-[17px] leading-[1.75] text-body">
          Enter your exact birth time and location. Receive a personalized Vedic Astrology report - quantified,
          structured, and generated stage by stage before your eyes.
        </p>
        <div className="flex flex-wrap justify-center gap-3">
          <Button size="lg" onClick={start} className="px-9">
            Get My Report
          </Button>
          <Button
            size="lg"
            variant="outline"
            className="px-7"
            onClick={() => document.getElementById("sample")?.scrollIntoView({ behavior: "smooth" })}
          >
            View Sample
          </Button>
        </div>
        <div className="mt-14 flex flex-wrap justify-center gap-10 sm:gap-12">
          <HeroMeta value="41" label="Page Report" />
          <HeroMeta value="9" label="Planets Analyzed" />
          <HeroMeta value="12" label="Houses Covered" />
          <HeroMeta value="D9" label="Navamsha Depth" />
        </div>
      </section>

      <Section className="bg-cream-2" title="What's Inside" strong="Your Report" subtitle="Every section is data-backed - no generic predictions, only your chart">
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((feature) => (
            <div key={feature.title} className="rounded-md border border-gold/25 bg-cream px-6 py-8">
              <div className="mb-4 text-[22px] opacity-80">{feature.icon}</div>
              <h3 className="mb-2.5 text-[15px] font-semibold tracking-[0.5px]">{feature.title}</h3>
              <p className="text-sm leading-[1.75] text-body">{feature.body}</p>
            </div>
          ))}
        </div>
      </Section>

      <section id="sample" className="bg-night px-6 py-20 text-cream sm:px-10">
        <div className="mx-auto max-w-[1100px]">
          <SectionTitle title="Report" strong="Preview" subtitle="Excerpt from Section 01 of a real report" dark />
          <div className="relative overflow-hidden rounded-lg border border-gold/20 bg-night-2 p-7 sm:p-10 after:absolute after:right-5 after:top-4 after:text-[10px] after:uppercase after:tracking-[3px] after:text-gold after:opacity-40 after:content-['SAMPLE_EXCERPT']">
            <div className="mb-3.5 text-[10px] uppercase tracking-[3px] text-gold">Section 01 · Identity Overview</div>
            <div className="mb-4 text-[22px] font-medium text-cream">Ascendant &amp; Chart Lord</div>
            <p className="mb-6 text-sm leading-[1.9] text-cream/75">
              Your Ascendant is <strong className="text-gold">Capricorn</strong> at 29°45' - the final degree of
              Capricorn. Pragmatic, goal-driven, focused on long-term accumulation. Your chart lord is{" "}
              <strong className="text-gold">Saturn</strong>, in its own second home - House 2 Aquarius, in Own Sign
              dignity, operating at peak efficiency.
            </p>
            <SampleTable />
            <div className="relative mt-1">
              <div className="select-none blur-sm">
                <table className="w-full border-collapse text-[13px]">
                  <tbody>
                    <tr><td className="border-b border-gold/10 px-3 py-2 text-cream/80">4</td><td className="border-b border-gold/10 px-3 py-2 text-cream/80">Mercury</td><td className="border-b border-gold/10 px-3 py-2 text-cream/80">124.6%</td><td className="border-b border-gold/10 px-3 py-2 text-cream/80">Great Friend · Libra H10 · Atmakaraka</td></tr>
                    <tr><td className="border-b border-gold/10 px-3 py-2 text-cream/80">5</td><td className="border-b border-gold/10 px-3 py-2 text-cream/80">Jupiter</td><td className="border-b border-gold/10 px-3 py-2 text-cream/80">118.3%</td><td className="border-b border-gold/10 px-3 py-2 text-cream/80">Neutral · Libra H10 · Current Mahadasha lord</td></tr>
                  </tbody>
                </table>
              </div>
              <div className="absolute inset-0 grid place-items-center">
                <Button onClick={start}>Unlock Full Report →</Button>
              </div>
            </div>
          </div>
        </div>
      </section>

      <Section title="Choose Your" strong="Plan" subtitle="One-time · Lifetime access">
        <div className="mx-auto grid max-w-[760px] gap-5 md:grid-cols-2">
          <PriceCard name="Essential" price="$39" description="Core report for those new to Vedic Astrology" features={["Complete report (~30 pages)", "Identity overview + planetary audit", "All 12 house diagnoses", "Dasha timeline"]} onClick={start} />
          <PriceCard featured name="Pro" price="$79" description="Full depth for serious seekers" features={["Complete report (41 pages)", "Everything in Essential", "D9 Navamsha deep audit", "Divisional cross-analysis (D10/D4/D5)", "Life architecture summary (10 domains)", "PDF export"]} onClick={start} />
        </div>
      </Section>

      <Section className="bg-cream-2" title="Frequently Asked" strong="Questions">
        <div className="mx-auto max-w-[700px]">
          {FAQS.map((item, index) => (
            <div key={item.q} className="border-b border-gold/25 py-5">
              <button
                className="flex w-full items-center justify-between gap-4 bg-transparent text-left text-[15px] font-medium"
                onClick={() => setOpenFaq(openFaq === index ? -1 : index)}
              >
                {item.q}
                <span className={`shrink-0 text-lg text-gold transition ${openFaq === index ? "rotate-180" : ""}`}>↓</span>
              </button>
              {openFaq === index && <p className="mt-3 text-sm leading-[1.85] text-body">{item.a}</p>}
            </div>
          ))}
        </div>
      </Section>

      <footer className="bg-night px-5 py-8 text-center text-[13px] tracking-[0.3px] text-cream/40">
        <p>© 2026 <span className="text-gold/60">VedaLight</span> &nbsp;·&nbsp; Based on Parashari Jyotish | KN Rao School &nbsp;·&nbsp; For self-reflection purposes</p>
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

function SectionTitle({ title, strong, subtitle, dark = false }: { title: string; strong: string; subtitle?: string; dark?: boolean }) {
  return (
    <div className="mb-14 text-center">
      <h2 className={`mb-3 text-[34px] font-light tracking-normal ${dark ? "text-cream" : "text-ink"}`}>
        {title} <strong className="font-semibold text-gold">{strong}</strong>
      </h2>
      <div className="mx-auto mt-4 h-px w-9 bg-gold" />
      {subtitle && <p className={`mt-2.5 text-[15px] ${dark ? "text-cream/55" : "text-body"}`}>{subtitle}</p>}
    </div>
  );
}

function SampleTable() {
  const rows = [
    ["1", "Moon", "137.8%", "Exalted · Taurus H5 · Emotional anchor"],
    ["2", "Saturn", "136.6%", "Own Sign · Aquarius H2 · Chart lord at home"],
    ["3", "Sun", "128.6%", "Neutral · Scorpio H11 · Vargottama"]
  ];
  return (
    <table className="w-full border-collapse text-[13px]">
      <tbody>
        <tr>
          {["Rank", "Planet", "Shadbala", "Status"].map((header) => (
            <th key={header} className="bg-gold/10 px-3 py-2 text-left text-[11px] font-medium uppercase tracking-[1px] text-gold">
              {header}
            </th>
          ))}
        </tr>
        {rows.map((row) => (
          <tr key={row[0]}>
            {row.map((cell, index) => (
              <td key={`${row[0]}-${index}`} className="border-b border-gold/10 px-3 py-2 text-cream/80">
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
  return (
    <div className={`relative rounded-md border bg-cream p-9 ${featured ? "border-gold shadow-[0_0_0_1px_var(--color-gold)]" : "border-gold/25"}`}>
      {featured && (
        <div className="absolute left-1/2 top-[-13px] -translate-x-1/2 rounded-full bg-gold px-3.5 py-1 text-[10px] uppercase tracking-[2px] text-white">
          Most Popular
        </div>
      )}
      <div className="mb-2 text-xs uppercase tracking-[2px] text-muted">{name}</div>
      <div className="mb-1 text-[44px] font-semibold text-ink">
        {price}
        <span className="text-[15px] font-normal text-muted"> /report</span>
      </div>
      <p className="mb-6 border-b border-gold/25 pb-6 text-[13px] text-body">{description}</p>
      <ul className="mb-8 space-y-2">
        {features.map((feature) => (
          <li key={feature} className="flex items-start gap-2.5 text-sm text-body before:mt-0.5 before:font-bold before:text-gold before:content-['✓']">
            {feature}
          </li>
        ))}
      </ul>
      <Button variant={featured ? "gold" : "outline"} className="w-full" onClick={onClick}>
        Choose {name}
      </Button>
    </div>
  );
}
