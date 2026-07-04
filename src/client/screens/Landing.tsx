import { SignedIn, SignedOut, SignInButton, SignUpButton, UserButton } from "@clerk/clerk-react";
import { useState } from "react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "../components/ui/button";

const FEATURES = [
  {
    icon: "◎",
    title: "Your Core Pattern",
    body: "Understand the temperament, inner needs, and recurring pressures that shape how you move through life."
  },
  {
    icon: "⬡",
    title: "Nine Planetary Signals",
    body: "Each planetary signal is weighed and translated into plain-language strengths, constraints, and reminders."
  },
  {
    icon: "◈",
    title: "Deeper Promise",
    body: "Navamsha (D9) adds a second lens: what comes naturally, what matures later, and where patience matters."
  },
  {
    icon: "▦",
    title: "Life Areas",
    body: "Career, wealth, family, relationships, health, learning, reputation, and inner growth are read as connected themes."
  },
  {
    icon: "◷",
    title: "Timing Guidance",
    body: "Dasha periods frame the season you are in: what to lean into, what to watch, and where to move carefully."
  },
  {
    icon: "◉",
    title: "Saved Reading Progress",
    body: "Follow the reading as it is prepared, with simple checkpoints and progress saved along the way."
  }
];

const FAQS = [
  {
    q: "How is Vedic Astrology different from Western Astrology?",
    a: "Vedic Astrology (Jyotish) uses the sidereal zodiac and puts strong weight on the Ascendant (Lagna), planetary strength, and Dasha timing. In VedaLight, those methods are used for reflective guidance, timing awareness, and practical reminders - not fixed answers."
  },
  {
    q: "Do I need my exact birth time?",
    a: "The more precise, the better. Exact birth time makes the reading sharper, especially for timing and deeper chart layers. If you only know an approximate time, you can still continue; the reading will treat uncertain areas more carefully."
  },
  {
    q: "How long does the reading take?",
    a: "A full reading usually takes several minutes. You can watch the reading progress live, and completed sections are saved as they become ready."
  }
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
          <div className="flex items-center gap-2">
            <SignedOut>
              <SignInButton mode="modal">
                <Button variant="ghost">Sign in</Button>
              </SignInButton>
              <SignUpButton mode="modal">
                <Button>Create account</Button>
              </SignUpButton>
            </SignedOut>
            <SignedIn>
              <Button onClick={start}>Start My Reading →</Button>
              <UserButton afterSignOutUrl="/" />
            </SignedIn>
          </div>
        </div>
      </nav>

      <section className="bg-linear-to-b from-cream to-cream-2 px-6 pb-20 pt-24 text-center sm:px-10 sm:pt-28">
        <div className="mb-9 inline-block rounded-full border border-gold/25 px-5 py-1.5 text-[11px] uppercase tracking-[4px] text-gold">
          Parashari Jyotish · KN Rao School
        </div>
        <h1 className="mb-5 text-[42px] font-light leading-[1.18] tracking-normal text-night sm:text-[52px]">
          A Private Vedic Reading,
          <br />
          <strong className="font-semibold text-gold">For the Season You Are In</strong>
        </h1>
        <p className="mx-auto mb-10 max-w-[540px] text-[17px] leading-[1.75] text-body">
          Share your birth details. VedaLight prepares a structured Jyotish reading, checks a few
          lived-experience signals with you, then turns the chart into guidance, cautions, and
          themes to reflect on.
        </p>
        <div className="flex flex-wrap justify-center gap-3">
          <Button size="lg" onClick={start} className="px-9">
            Start My Reading
          </Button>
          <Button
            size="lg"
            variant="outline"
            className="px-7"
            onClick={() =>
              document.getElementById("sample")?.scrollIntoView({ behavior: "smooth" })
            }
          >
            View Sample
          </Button>
        </div>
        <div className="mt-14 flex flex-wrap justify-center gap-10 sm:gap-12">
          <HeroMeta value="41" label="Page Reading" />
          <HeroMeta value="9" label="Planetary Signals" />
          <HeroMeta value="12" label="Life Areas" />
          <HeroMeta value="D9" label="Deeper Lens" />
        </div>
      </section>

      <Section
        className="bg-cream-2"
        title="What's Inside"
        strong="Your Reading"
        subtitle="Chart-based guidance without generic horoscope lines or fixed answers"
      >
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((feature) => (
            <div
              key={feature.title}
              className="rounded-md border border-gold/25 bg-cream px-6 py-8"
            >
              <div className="mb-4 text-[22px] opacity-80">{feature.icon}</div>
              <h3 className="mb-2.5 text-[15px] font-semibold tracking-[0.5px]">{feature.title}</h3>
              <p className="text-sm leading-[1.75] text-body">{feature.body}</p>
            </div>
          ))}
        </div>
      </Section>

      <section id="sample" className="bg-night px-6 py-20 text-cream sm:px-10">
        <div className="mx-auto max-w-[1100px]">
          <SectionTitle
            title="Reading"
            strong="Preview"
            subtitle="Excerpt from Section 01 of a real reading"
            dark
          />
          <div className="relative overflow-hidden rounded-lg border border-gold/20 bg-night-2 p-7 sm:p-10 after:absolute after:right-5 after:top-4 after:text-[10px] after:uppercase after:tracking-[3px] after:text-gold after:opacity-40 after:content-['SAMPLE_EXCERPT']">
            <div className="mb-3.5 text-[10px] uppercase tracking-[3px] text-gold">
              Section 01 · Identity Overview
            </div>
            <div className="mb-4 text-[22px] font-medium text-cream">
              Ascendant &amp; Chart Lord
            </div>
            <p className="mb-6 text-sm leading-[1.9] text-cream/75">
              Your Ascendant is <strong className="text-gold">Capricorn</strong> at 29°45' - a
              late-degree signal that often seeks structure before trust. Your chart lord is{" "}
              <strong className="text-gold">Saturn</strong>, strongly placed in the second house:
              discipline, speech, savings, and long-term family responsibility become recurring
              themes.
            </p>
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
                <Button onClick={start}>Unlock Full Reading →</Button>
              </div>
            </div>
          </div>
        </div>
      </section>

      <Section title="Choose Your" strong="Plan" subtitle="One-time · Lifetime access">
        <div className="mx-auto grid max-w-[760px] gap-5 md:grid-cols-2">
          <PriceCard
            name="Essential"
            price="$39"
            description="A focused private reading for first-time users"
            features={[
              "Complete reading (~30 pages)",
              "Identity pattern + planetary signals",
              "All 12 life areas",
              "Timing guidance"
            ]}
            onClick={start}
          />
          <PriceCard
            featured
            name="Pro"
            price="$79"
            description="Deeper context for serious reflection"
            features={[
              "Complete reading (41 pages)",
              "Everything in Essential",
              "D9 deeper-promise reading",
              "Career, home, and authority context",
              "Life synthesis across 10 domains",
              "PDF export"
            ]}
            onClick={start}
          />
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
                <span
                  className={`shrink-0 text-lg text-gold transition ${openFaq === index ? "rotate-180" : ""}`}
                >
                  ↓
                </span>
              </button>
              {openFaq === index && (
                <p className="mt-3 text-sm leading-[1.85] text-body">{item.a}</p>
              )}
            </div>
          ))}
        </div>
      </Section>

      <footer className="bg-night px-5 py-8 text-center text-[13px] tracking-[0.3px] text-cream/40">
        <p>
          © 2026 <span className="text-gold/60">VedaLight</span> &nbsp;·&nbsp; Based on Parashari
          Jyotish | KN Rao School &nbsp;·&nbsp; For self-reflection purposes
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
  const rows = [
    ["1", "Moon", "High", "Emotional steadiness and creative devotion"],
    ["2", "Saturn", "High", "Discipline around speech, family, and savings"],
    ["3", "Sun", "Strong", "Visibility through networks and long-range goals"]
  ];
  return (
    <table className="w-full border-collapse text-[13px]">
      <tbody>
        <tr>
          {["Rank", "Signal", "Weight", "Reading note"].map((header) => (
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
  return (
    <div
      className={`relative rounded-md border bg-cream p-9 ${featured ? "border-gold shadow-[0_0_0_1px_var(--color-gold)]" : "border-gold/25"}`}
    >
      {featured && (
        <div className="absolute left-1/2 top-[-13px] -translate-x-1/2 rounded-full bg-gold px-3.5 py-1 text-[10px] uppercase tracking-[2px] text-white">
          Most Popular
        </div>
      )}
      <div className="mb-2 text-xs uppercase tracking-[2px] text-muted">{name}</div>
      <div className="mb-1 text-[44px] font-semibold text-ink">
        {price}
        <span className="text-[15px] font-normal text-muted"> /reading</span>
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
        Choose {name}
      </Button>
    </div>
  );
}
