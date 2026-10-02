import { useState } from "react";
import { Link } from "react-router-dom";
import { Sparkles } from "lucide-react";
import { useI18n } from "../i18n/provider";
import { daysCopy } from "../lib/days-copy";
import { dayMasterOf, famousCharts } from "../lib/famous-charts";
import { dayPillar, stemElement } from "../lib/sexagenary";

export function Discover() {
  const { locale } = useI18n();
  const d = daysCopy[locale];
  const [birthDate, setBirthDate] = useState("");
  const [master, setMaster] = useState<string | null>(null);
  const valid = /^\d{4}-\d{2}-\d{2}$/.test(birthDate) && birthDate >= "1900-01-01";
  const twins = famousCharts.filter((chart) => master && dayMasterOf(chart) === master);
  const others = famousCharts.filter((chart) => !master || dayMasterOf(chart) !== master);

  return (
    <div className="mx-auto max-w-[1180px] px-5 py-8 sm:px-8 sm:py-10">
      <header className="mb-8 max-w-2xl">
        <h1 className="font-display text-4xl leading-tight sm:text-5xl">{d.discoverTitle}</h1>
        <p className="mt-3 text-sm leading-7 text-cream/60">{d.discoverBody}</p>
      </header>

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <section className="surface p-5 sm:p-7">
          <form
            className="flex flex-wrap items-end gap-3"
            onSubmit={(event) => {
              event.preventDefault();
              if (valid) setMaster(dayPillar(birthDate).stem);
            }}
          >
            <label className="flex flex-col gap-2 text-sm text-cream/70">
              {d.birthDate}
              <input
                type="date"
                value={birthDate}
                min="1900-01-01"
                onChange={(event) => setBirthDate(event.target.value)}
                className="h-12 rounded-xl border border-white/15 bg-[#1c1823] px-4 text-base text-cream [color-scheme:dark]"
              />
            </label>
            <button
              type="submit"
              disabled={!valid}
              className="press-feedback h-12 rounded-full bg-[#f3ece0] px-6 text-sm font-medium text-[#16120c] disabled:opacity-40"
            >
              {d.findTwin}
            </button>
          </form>

          {master ? (
            <div className="mt-6 flex items-center gap-4">
              <span className="grid size-16 shrink-0 place-items-center rounded-2xl bg-jade text-3xl font-semibold text-[#0e0c13]">
                {master}
              </span>
              <div>
                <p className="eyebrow">
                  {d.dayMaster} · {d.elements[stemElement(master)]}
                </p>
                <p className="mt-1 font-display text-xl leading-snug">{d.stems[master]}</p>
              </div>
            </div>
          ) : null}
          <p className="mt-4 text-xs leading-5 text-cream/45">{d.lateBirth}</p>

          {twins.length > 0 && (
            <div className="mt-6 space-y-3">
              <p className="eyebrow text-jade">{d.sameMaster}</p>
              {twins.map((chart) => (
                <FamousRow key={chart.id} chart={chart} highlight locale={locale} />
              ))}
              <Link
                to="/app/explore"
                className="press-feedback mt-2 inline-flex h-11 items-center gap-2 rounded-full bg-[#f3ece0] px-5 text-sm font-medium text-[#16120c]"
              >
                <Sparkles size={15} />
                {d.compareAsk}
              </Link>
            </div>
          )}
        </section>

        <section className="surface p-5 sm:p-7">
          <div className="flex items-baseline justify-between gap-3">
            <h2 className="font-display text-2xl">{d.famousTitle}</h2>
            <span className="text-xs text-cream/45">{d.pillarsOrder}</span>
          </div>
          <div className="mt-4 divide-y divide-white/[0.07]">
            {others.map((chart) => (
              <FamousRow key={chart.id} chart={chart} locale={locale} />
            ))}
          </div>
          <p className="mt-4 text-xs leading-5 text-cream/45">{d.famousNote}</p>
        </section>
      </div>

      <h2 className="mb-4 mt-10 font-display text-2xl">{d.learnTitle}</h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {d.lessons.map((lesson) => (
          <article key={lesson.title} className="surface p-5">
            <h3 className="text-base font-medium">{lesson.title}</h3>
            <p className="mt-2 text-sm leading-6 text-cream/60">{lesson.body}</p>
          </article>
        ))}
        <article className="rounded-3xl border border-dashed border-white/20 p-5">
          <div className="flex items-center justify-between">
            <h3 className="text-base font-medium text-cream/75">{d.tarotTitle}</h3>
            <span className="rounded-full bg-white/[0.06] px-2.5 py-1 text-[11px] text-cream/60">
              {d.soon}
            </span>
          </div>
          <p className="mt-2 text-sm leading-6 text-cream/50">{d.tarotBody}</p>
        </article>
      </div>
    </div>
  );
}

function FamousRow({
  chart,
  highlight = false,
  locale
}: {
  chart: (typeof famousCharts)[number];
  highlight?: boolean;
  locale: "zh" | "en" | "ja";
}) {
  return (
    <div
      className={`flex flex-wrap items-center justify-between gap-3 py-3 ${highlight ? "rounded-2xl bg-jade/[0.08] px-4" : ""}`}
    >
      <div className="min-w-0">
        <p className="text-[15px]">{chart.name[locale]}</p>
        <p className="text-xs text-cream/45">
          {chart.born.slice(0, 10)} · {chart.place}
        </p>
      </div>
      <p className="flex gap-2 text-[15px] tracking-wide text-cream/70">
        {chart.pillars.map((pillar, i) => (
          <span key={i} className={i === 2 ? "font-semibold text-jade" : undefined}>
            {pillar}
          </span>
        ))}
      </p>
    </div>
  );
}
