import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronLeft, ChevronRight, LoaderCircle } from "lucide-react";
import { api } from "../api";
import { useI18n } from "../i18n/provider";
import { daysCopy } from "../lib/days-copy";
import { journalCopy, type JournalEntry, type JournalResponse } from "../lib/journal";
import { learnedRules, MIN_GROUP_DAYS, readDay, unlockProgress, type Fit } from "../lib/patterns";
import { monthDays, weekdayIndex } from "../lib/sexagenary";

const fitCell: Record<Fit, string> = {
  bright: "border-transparent bg-paper text-[#16120c]",
  steady: "border-transparent bg-white/[0.06] text-cream/80",
  gentle: "border-dashed border-white/25 bg-transparent text-cream/55",
  unknown: "border-transparent bg-white/[0.025] text-cream/45"
};

export function Patterns() {
  const { locale } = useI18n();
  const d = daysCopy[locale];
  const c = journalCopy[locale];
  const [zone] = useState(
    () => Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Shanghai"
  );
  const [data, setData] = useState<JournalResponse | null>(null);
  const [error, setError] = useState("");
  const [month, setMonth] = useState<{ year: number; month: number } | null>(null);
  const [selected, setSelected] = useState("");

  useEffect(() => {
    let alive = true;
    api
      .getJournal(zone)
      .then((result) => {
        if (!alive) return;
        setData(result);
        const [year, mon] = result.today.day.split("-").map(Number);
        setMonth({ year, month: mon });
        setSelected(result.today.day);
      })
      .catch(() => alive && setError(c.error));
    return () => {
      alive = false;
    };
  }, [zone, c.error]);

  const entries = useMemo(
    () =>
      new Map((data?.entries ?? []).map((entry) => [entry.day, entry] as [string, JournalEntry])),
    [data]
  );

  if (error) {
    return (
      <p role="alert" className="mx-auto max-w-[1180px] px-5 py-10 text-sm text-[#ffb5a4] sm:px-8">
        {error}
      </p>
    );
  }
  if (!data || !month) {
    return (
      <div role="status" className="grid min-h-[50vh] place-items-center text-cream/60">
        <LoaderCircle className="size-6 animate-spin text-gold" />
      </div>
    );
  }

  const summary = data.summary;
  const days = monthDays(month.year, month.month);
  const lead = weekdayIndex(days[0]);
  const rules = learnedRules(summary);
  const progress = unlockProgress(summary);
  const reading = readDay(selected, summary);
  const entry = entries.get(selected);
  const canLog = selected <= data.today.day;
  const shift = (delta: number) => {
    const index = month.year * 12 + (month.month - 1) + delta;
    setMonth({ year: Math.floor(index / 12), month: (index % 12) + 1 });
  };

  return (
    <div className="mx-auto max-w-[1180px] px-5 py-8 sm:px-8 sm:py-10">
      <header className="mb-8 max-w-2xl">
        <p className="eyebrow mb-3">{d.learned(summary.recordedDays)}</p>
        <h1 className="font-display text-4xl leading-tight sm:text-5xl">{d.daysTitle}</h1>
        <p className="mt-3 text-sm leading-7 text-cream/60">{d.daysBody}</p>
      </header>

      <div className="grid gap-5 @4xl:grid-cols-[minmax(0,1fr)_340px]">
        <section className="surface self-start p-4 sm:p-6" aria-label={d.daysTitle}>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-display text-2xl">
              {d.months[month.month - 1]} {month.year}
            </h2>
            <div className="flex gap-1">
              <button
                type="button"
                aria-label={d.prev}
                onClick={() => shift(-1)}
                className="grid size-11 place-items-center rounded-full text-cream/70 hover:bg-white/5"
              >
                <ChevronLeft size={18} />
              </button>
              <button
                type="button"
                aria-label={d.next}
                onClick={() => shift(1)}
                className="grid size-11 place-items-center rounded-full text-cream/70 hover:bg-white/5"
              >
                <ChevronRight size={18} />
              </button>
            </div>
          </div>
          <div className="mb-2 grid grid-cols-7 gap-1.5 text-center text-[11px] text-cream/45">
            {d.weekdays.map((day, i) => (
              <span key={i}>{day}</span>
            ))}
          </div>
          <div className="grid grid-cols-7 gap-1.5">
            {Array.from({ length: lead }, (_, i) => (
              <span key={`lead-${i}`} />
            ))}
            {days.map((day) => {
              const cell = readDay(day, summary);
              const logged = entries.get(day);
              const isToday = day === data.today.day;
              const isSelected = day === selected;
              return (
                <button
                  key={day}
                  type="button"
                  onClick={() => setSelected(day)}
                  aria-pressed={isSelected}
                  aria-label={`${day} ${cell.pillar} ${d.fit[cell.fit]}`}
                  className={`relative flex h-14 flex-col items-center justify-center rounded-xl border text-xs transition sm:h-16 ${fitCell[cell.fit]} ${isSelected ? "ring-2 ring-gold" : isToday ? "ring-1 ring-cream/50" : ""}`}
                >
                  <span className="text-[10px] opacity-70">{Number(day.slice(8))}</span>
                  <span className="text-[13px] font-semibold sm:text-sm">{cell.pillar}</span>
                  {logged && (
                    <span
                      className="absolute bottom-1 h-1 rounded-full bg-gold"
                      style={{ width: `${logged.mood * 3 + 2}px` }}
                    />
                  )}
                </button>
              );
            })}
          </div>
          <div className="mt-4 flex flex-wrap gap-4 text-xs text-cream/60">
            {(["bright", "steady", "gentle"] as const).map((fit) => (
              <span key={fit} className="flex items-center gap-2">
                <span className={`size-3 rounded border ${fitCell[fit]}`} />
                {d.fit[fit]}
              </span>
            ))}
            <span className="flex items-center gap-2">
              <span className="h-1 w-3 rounded-full bg-gold" />
              {d.logged}
            </span>
          </div>
        </section>

        <div className="space-y-5">
          <section className="surface p-5 sm:p-6" aria-live="polite">
            <div className="flex items-baseline justify-between gap-3">
              <p className="text-sm text-cream/60">{selected}</p>
              <p className="text-3xl font-semibold tracking-wide">{reading.pillar}</p>
            </div>
            <p className="mt-2 font-display text-2xl">{d.fit[reading.fit]}</p>
            <p className="mt-2 text-sm leading-6 text-cream/75">{d.fitLong[reading.fit]}</p>
            {reading.signals.length > 0 && (
              <ul className="mt-4 space-y-2 text-sm leading-6 text-cream/65">
                {reading.signals.map((signal) => (
                  <li key={signal.kind} className="flex gap-2">
                    <span className={signal.delta >= 0 ? "text-jade" : "text-cream/40"}>●</span>
                    {d.signal(signal.kind, signal.key, signal.averageMood, signal.count)}
                  </li>
                ))}
              </ul>
            )}
            <div className="mt-5 border-t border-white/[0.07] pt-4">
              {entry ? (
                <>
                  <p className="eyebrow">{d.logged}</p>
                  <p className="mt-2 text-sm text-gold">{c.moods[entry.mood - 1]}</p>
                  <p className="mt-1 line-clamp-3 text-sm leading-6 text-cream/80">{entry.note}</p>
                  <Link
                    to={`/app/records?day=${selected}`}
                    className="mt-3 inline-block text-sm text-gold"
                  >
                    {d.viewEntry} →
                  </Link>
                </>
              ) : (
                <>
                  <p className="text-sm text-cream/55">{d.notLogged}</p>
                  {canLog && (
                    <Link
                      to={`/app/records?day=${selected}`}
                      className="mt-3 inline-block text-sm text-gold"
                    >
                      {d.writeThis} →
                    </Link>
                  )}
                </>
              )}
            </div>
          </section>

          <section className="surface p-5 sm:p-6">
            <h2 className="font-display text-2xl">{d.rulesTitle}</h2>
            {rules.length ? (
              <ul className="mt-4 space-y-3">
                {rules.map((rule) => (
                  <li key={rule.kind + rule.key} className="rounded-2xl bg-white/[0.04] p-4">
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-2xl font-semibold">{rule.key}</span>
                      <span
                        className={`rounded-full px-2.5 py-1 text-xs ${rule.delta > 0 ? "bg-jade/15 text-jade" : "border border-dashed border-white/25 text-cream/60"}`}
                      >
                        {rule.delta > 0 ? d.ruleLift : d.ruleDip}
                      </span>
                    </div>
                    <p className="mt-2 text-sm leading-6 text-cream/65">
                      {d.rule(rule.key, rule.averageMood, rule.count, summary.averageMood ?? 0)}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="mt-4">
                <p className="text-sm leading-6 text-cream/65">{d.noRules}</p>
                <div className="mt-4 h-1.5 rounded-full bg-white/[0.07]">
                  <div
                    className="h-1.5 rounded-full bg-gold"
                    style={{ width: `${(progress / MIN_GROUP_DAYS) * 100}%` }}
                  />
                </div>
                <p className="mt-2 text-xs text-cream/50">{d.unlock(progress, MIN_GROUP_DAYS)}</p>
              </div>
            )}
            <p className="mt-5 text-xs leading-6 text-cream/50">{d.caution}</p>
          </section>
        </div>
      </div>
    </div>
  );
}
