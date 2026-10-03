import { useUser } from "@clerk/clerk-react";
import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams, useNavigate } from "react-router-dom";
import { Check, Download, LoaderCircle, Minus, Sparkles } from "lucide-react";
import { PageHeader } from "../components/PageHeader";
import { chartLabel, uniqueCharts } from "../lib/atlas";
import { AtlasChartFirst, useAtlas } from "../components/Atlas";
import { api, ApiError } from "../api";
import { Button } from "../components/ui/button";
import { Textarea } from "../components/ui/textarea";
import { MoodPicker } from "../components/MoodMoon";
import { useWorkspaceDraft } from "../lib/workspace-draft";
import { workspaceCopy } from "../lib/workspace";
import { useI18n } from "../i18n/provider";
import {
  guidanceText,
  journalCopy,
  type DailyGuidanceResponse,
  type JournalResponse,
  type JournalEntry
} from "../lib/journal";
import { daysCopy } from "../lib/days-copy";
import { readDay, upcoming } from "../lib/patterns";
import { branchElement, parseDay, stemElement } from "../lib/sexagenary";

const topics = ["life", "work", "relationships", "health", "learning"];
const panel = "surface p-5 sm:p-7";
const field =
  "min-h-11 rounded-xl border border-white/15 bg-night-3 px-3 text-sm text-cream [color-scheme:dark]";

export function Daily({ view }: { view: "today" | "records" | "explore" }) {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const selectedDay = params.get("day");
  const { locale, localeTag } = useI18n();
  const { user } = useUser();
  const { hasChart, askAbout } = useAtlas();
  const c = journalCopy[locale];
  const w = workspaceCopy[locale];
  const d = daysCopy[locale];
  const [zone] = useState(
    () => Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Shanghai"
  );
  const [data, setData] = useState<JournalResponse | null>(null);
  const [day, setDay] = useState("");
  const [note, setNote] = useState("");
  const [mood, setMood] = useState(3);
  const [topic, setTopic] = useState("life");
  const [question, setQuestion] = useState("");
  const [sessionId, setSessionId] = useState(params.get("chart") ?? "");
  const [charts, setCharts] = useState<{ sessionId: string; label: string }[]>([]);
  const [guidance, setGuidance] = useState<DailyGuidanceResponse | null>(null);
  const pendingQuestion = useRef<{ key: string; id: string } | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const entry = data?.entries.find((item) => item.day === day);
  const dirty =
    note !== (entry?.note ?? "") ||
    mood !== (entry?.mood ?? 3) ||
    topic !== (entry?.topic ?? "life");

  useWorkspaceDraft(dirty);

  function choose(nextDay: string, entries = data?.entries ?? []) {
    const selected = entries.find((item) => item.day === nextDay);
    setDay(nextDay);
    setNote(selected?.note ?? "");
    setMood(selected?.mood ?? 3);
    setTopic(selected?.topic ?? "life");
    setQuestion("");
    setNotice("");
    setError("");
  }
  function selectDate(nextDay: string) {
    if (!nextDay || nextDay === day) return;
    setBusy("load");
    setParams({ day: nextDay }, { replace: true });
  }
  async function load() {
    setError("");
    try {
      const result = await api.getJournal(zone);
      setData(result);
      choose(result.today.day, result.entries);
    } catch {
      setError(c.error);
    }
  }
  useEffect(() => {
    let alive = true;
    api
      .getJournal(zone)
      .then((result) => {
        if (alive) {
          setData(result);
          const target =
            selectedDay && /^\d{4}-\d{2}-\d{2}$/.test(selectedDay)
              ? selectedDay
              : view === "explore"
                ? (result.entries[0]?.day ?? result.today.day)
                : result.today.day;
          choose(target, result.entries);
          if (target !== result.today.day && !result.entries.some((item) => item.day === target)) {
            return api
              .getJournalDay(target)
              .then((found) => {
                if (alive) {
                  const entries = [...result.entries, found];
                  setData({ ...result, entries });
                  choose(target, entries);
                }
              })
              .catch((caught) => {
                if (alive && (!(caught instanceof ApiError) || caught.status !== 404))
                  setError(c.error);
              });
          }
        }
      })
      .catch(() => {
        if (alive) setError(c.error);
      })
      .finally(() => {
        if (alive) setBusy("");
      });
    if (view === "today") {
      api
        .getDailyGuidance({ timezone: zone })
        .then((result) => alive && setGuidance(result))
        .catch(() => {});
    }
    api
      .listMySessions()
      .then((result) => {
        if (alive)
          setCharts(
            uniqueCharts(
              result.sessions.map((s) => ({
                sessionId: s.sessionId,
                kind: s.stage.startsWith("bazi_") ? "bazi" : "vedic",
                completed: s.status === "completed",
                label: chartLabel(s.subject, localeTag) || s.createdAt?.slice(0, 10) || ""
              }))
            )
          );
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
    // Locale does not change saved data; requests are bound to the current timezone.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zone, view, selectedDay]);

  async function refreshSelected() {
    const next = await api.getJournal(zone);
    if (!next.entries.some((item) => item.day === day)) {
      next.entries.push(await api.getJournalDay(day));
    }
    setData(next);
  }
  async function save(nextMood = mood) {
    setBusy("save");
    setError("");
    setNotice("");
    try {
      await api.saveJournal({
        day,
        timezone: entry?.timezone ?? zone,
        mood: nextMood,
        note,
        topic
      });
      await refreshSelected();
      setNote(note.trim());
      setNotice(c.saved);
    } catch {
      setError(c.error);
    } finally {
      setBusy("");
    }
  }
  async function ask() {
    if (!entry || dirty) {
      setError(c.noSave);
      return;
    }
    setBusy("ask");
    setError("");
    const key = JSON.stringify([day, question, sessionId, locale, note]);
    if (pendingQuestion.current?.key !== key) {
      pendingQuestion.current = { key, id: crypto.randomUUID() };
    }
    try {
      await api.reflectJournal({
        day,
        question,
        locale,
        session_id: sessionId || null,
        request_id: pendingQuestion.current.id
      });
      await refreshSelected();
      pendingQuestion.current = null;
      setQuestion("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : c.error);
    } finally {
      setBusy("");
    }
  }
  async function setAction(
    reflectionId: string,
    lens: "bazi" | "vedic" | "tarot",
    status: "planned" | "done" | "none"
  ) {
    setBusy("action");
    setError("");
    try {
      await api.updateReflectionAction({ day, reflection_id: reflectionId, lens, status });
      await refreshSelected();
    } catch {
      setError(c.error);
    } finally {
      setBusy("");
    }
  }
  async function remove() {
    if (!window.confirm(c.removeConfirm)) return;
    setBusy("delete");
    setError("");
    try {
      await api.deleteJournal(day);
      const next = await api.getJournal(zone);
      setData(next);
      choose(next.today.day, next.entries);
    } catch {
      setError(c.error);
    } finally {
      setBusy("");
    }
  }
  function exportEntries() {
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(data?.entries ?? [], null, 2)], { type: "application/json" })
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = "sign-atlas-journal.json";
    a.click();
    URL.revokeObjectURL(url);
  }
  if (view === "today" && data) {
    const todayReading = readDay(data.today.day, data.summary);
    const ahead = upcoming(data.today.day, data.summary, 30);
    const bright = ahead.filter((item) => item.fit === "bright").slice(0, 3);
    const gentle = ahead.find((item) => item.fit === "gentle");
    const dateLabel = new Intl.DateTimeFormat(localeTag, {
      weekday: "long",
      month: "long",
      day: "numeric",
      timeZone: "UTC"
    }).format(parseDay(data.today.day));
    const shortDate = (value: string) =>
      new Intl.DateTimeFormat(localeTag, {
        weekday: "short",
        month: "short",
        day: "numeric",
        timeZone: "UTC"
      }).format(parseDay(value));
    return (
      <div className="mx-auto max-w-[1180px] px-5 py-8 sm:px-8 sm:py-10">
        <PageHeader title={d.greeting(new Date().getHours(), user?.firstName)} note={dateLabel} />
        {hasChart === false && (
          <section className="rise-in mb-5 flex flex-wrap items-center gap-4 rounded-3xl border border-gold/30 bg-gold/[0.07] p-5">
            <span className="grid size-11 shrink-0 place-items-center rounded-full bg-gold text-night">
              <Sparkles size={18} />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-[15px] font-medium">{d.startTitle}</p>
              <p className="mt-0.5 text-sm leading-6 text-cream/60">{d.startBody}</p>
            </div>
            <div className="flex gap-2">
              <Link
                to="/app/charts/new"
                className="inline-flex h-10 items-center rounded-full bg-paper px-4 text-sm font-medium text-[#16130e]"
              >
                {d.startVedic}
              </Link>
              <Link
                to="/app/charts/bazi"
                className="inline-flex h-10 items-center rounded-full border border-white/15 px-4 text-sm text-cream/80 hover:bg-white/[0.05]"
              >
                {d.startBazi}
              </Link>
            </div>
          </section>
        )}
        {error && (
          <div
            role="alert"
            className="mb-5 rounded-xl border border-red/50 bg-red/10 p-4 text-sm text-[#ffb5a4]"
          >
            {error}
          </div>
        )}
        <div className="grid gap-5 @4xl:grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)]">
          <section className="surface @container relative overflow-hidden p-6 sm:p-8">
            <div
              aria-hidden="true"
              className="pointer-events-none absolute -right-24 -top-24 size-72 rounded-full border border-gold/20"
            />
            <div
              aria-hidden="true"
              className="pointer-events-none absolute -right-8 -top-8 size-40 rounded-full border border-jade/20"
            />
            <div className="relative flex items-center justify-between gap-3">
              <p className="eyebrow">{d.yourDay}</p>
              <span
                className={`rounded-full px-3 py-1 text-xs ${todayReading.fit === "bright" ? "bg-paper text-[#16130e]" : todayReading.fit === "gentle" ? "border border-dashed border-white/30 text-cream/70" : "bg-white/[0.07] text-cream/75"}`}
              >
                {d.fit[todayReading.fit]}
              </span>
            </div>
            <div className="relative mt-4 flex flex-wrap items-end gap-x-5 gap-y-2">
              <p className="han text-7xl font-bold leading-none sm:text-8xl">{data.today.pillar}</p>
              <div className="pb-1.5">
                <p className="text-sm text-cream/55">
                  {d.elements[stemElement(data.today.stem)]} ·{" "}
                  {d.elements[branchElement(data.today.branch)]}
                </p>
                {guidance?.guidance && (
                  <p className="mt-1 font-display text-lg italic text-cream/85">
                    {d.tenGodDay(guidance.guidance.facts.tenGod, guidance.guidance.facts.dayMaster)}
                  </p>
                )}
              </div>
            </div>

            {guidance?.guidance ? (
              <div className="relative mt-6 grid gap-3 @lg:grid-cols-2">
                <div className="rounded-2xl bg-night-3 p-4">
                  <p className="mb-2 flex items-center gap-2 text-xs text-cream/55">
                    <span className="grid size-6 place-items-center rounded-lg bg-paper text-[#16130e]">
                      <Check size={13} strokeWidth={2.6} />
                    </span>
                    {d.goodFor}
                  </p>
                  <ul className="space-y-1 text-[15px] leading-6">
                    {guidance.guidance.goodFor.map((item) => (
                      <li key={item.id}>{guidanceText(item, locale)}</li>
                    ))}
                  </ul>
                </div>
                <div className="rounded-2xl bg-night-3 p-4">
                  <p className="mb-2 flex items-center gap-2 text-xs text-cream/55">
                    <span className="grid size-6 place-items-center rounded-lg border border-cream/40 text-cream/70">
                      <Minus size={13} strokeWidth={2.6} />
                    </span>
                    {d.avoid}
                  </p>
                  <ul className="space-y-1 text-[15px] leading-6 text-cream/80">
                    {guidance.guidance.avoid.map((item) => (
                      <li key={item.id}>{guidanceText(item, locale)}</li>
                    ))}
                  </ul>
                </div>
              </div>
            ) : guidance ? (
              <div className="relative mt-6 rounded-2xl border border-dashed border-white/20 p-4">
                <p className="text-[15px] font-medium">{d.addBirthTitle}</p>
                <p className="mt-1 text-sm leading-6 text-cream/60">{d.addBirthBody}</p>
                <Link
                  to="/app/charts/new"
                  className="mt-3 inline-flex h-9 items-center rounded-full bg-paper px-4 text-xs font-medium text-[#16130e]"
                >
                  {d.addBirthAction}
                </Link>
              </div>
            ) : null}

            {hasChart && (
              <button
                type="button"
                onClick={() => askAbout(d.askToday)}
                className="press-feedback relative mt-4 inline-flex h-10 items-center gap-2 rounded-full border border-white/12 bg-white/[0.03] px-4 text-sm text-cream/80 transition-colors hover:border-gold/50 hover:text-gold-light"
              >
                <Sparkles size={15} />
                {d.askCta}
              </button>
            )}
            <div className="relative mt-5 border-t border-white/[0.07] pt-4">
              <p className="eyebrow mb-1.5">{d.fromNotes}</p>
              <p className="text-sm leading-6 text-cream/75">{d.fitLong[todayReading.fit]}</p>
              {todayReading.signals.length > 0 && (
                <ul className="mt-2 space-y-1 text-[13px] text-cream/55">
                  {todayReading.signals.map((signal) => (
                    <li key={signal.kind}>
                      <span className={signal.delta >= 0 ? "text-jade" : "text-cream/40"}>● </span>
                      {d.signal(signal.kind, signal.key, signal.averageMood, signal.count)}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>

          <section className="surface p-6 sm:p-7">
            <div className="flex items-baseline justify-between gap-3">
              <h2 className="font-display text-2xl">{d.quick}</h2>
              <Link
                to={`/app/records?day=${data.today.day}`}
                className="text-sm text-cream/55 hover:text-gold"
              >
                {d.writeMore}
              </Link>
            </div>
            <p className="mt-1 text-sm text-cream/50">{entry ? d.checkedIn : d.oneTap}</p>
            <div className="mt-4">
              <MoodPicker
                labels={c.moods}
                legend={c.mood}
                value={entry || busy === "save" ? mood : null}
                disabled={!!busy}
                onPick={(next) => {
                  setMood(next);
                  void save(next);
                }}
              />
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              {topics.map((value, i) => (
                <button
                  key={value}
                  type="button"
                  disabled={!!busy}
                  aria-pressed={topic === value}
                  onClick={() => setTopic(value)}
                  className={`h-9 rounded-full border px-3.5 text-xs transition-colors ${topic === value ? "border-paper bg-paper text-[#16130e]" : "border-white/12 text-cream/60 hover:bg-white/5"}`}
                >
                  {c.topics[i]}
                </button>
              ))}
            </div>
            <label htmlFor="today-note" className="sr-only">
              {c.note}
            </label>
            <Textarea
              id="today-note"
              value={note}
              maxLength={4000}
              disabled={!!busy}
              onChange={(e) => {
                setNote(e.target.value);
                setNotice("");
              }}
              placeholder={c.placeholder}
              className="mt-4 min-h-24 text-base"
            />
            <div className="mt-3 flex items-center justify-between gap-3">
              <span role="status" className="text-xs text-cream/55">
                {notice ? d.quickSaved : ""}
              </span>
              <Button disabled={!!busy || !dirty} onClick={() => void save()}>
                {busy === "save" ? (
                  <LoaderCircle className="size-4 animate-spin" />
                ) : (
                  <Check size={16} />
                )}
                {c.save}
              </Button>
            </div>
          </section>
        </div>

        <div className="mt-5 grid gap-5 @3xl:grid-cols-2">
          <section className="surface p-6">
            <div className="flex items-baseline justify-between gap-3">
              <h2 className="font-display text-2xl">{d.nextBright}</h2>
              <Link to="/app/days" className="text-sm text-cream/55 hover:text-gold">
                {d.nav.calendar} →
              </Link>
            </div>
            {bright.length ? (
              <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
                {bright.map((item) => (
                  <div key={item.day} className="rounded-2xl bg-white/[0.045] p-4">
                    <p className="text-xs text-cream/50">{shortDate(item.day)}</p>
                    <p className="mt-1 text-2xl font-semibold">{item.pillar}</p>
                  </div>
                ))}
                {gentle && (
                  <div className="rounded-2xl border border-dashed border-white/20 p-4">
                    <p className="text-xs text-cream/50">
                      {d.nextGentle} · {shortDate(gentle.day)}
                    </p>
                    <p className="mt-1 text-2xl font-semibold text-cream/60">{gentle.pillar}</p>
                  </div>
                )}
              </div>
            ) : (
              <p className="mt-4 text-sm leading-6 text-cream/55">{d.noForecast}</p>
            )}
          </section>

          <section className="surface p-6">
            <div className="flex items-baseline justify-between gap-3">
              <h2 className="font-display text-2xl">{w.recent}</h2>
              <Link to="/app/records" className="text-sm text-cream/55 hover:text-gold">
                {w.all} →
              </Link>
            </div>
            {data.entries.length ? (
              <ul className="mt-3 divide-y divide-white/[0.06]">
                {data.entries.slice(0, 4).map((item) => (
                  <li key={item.day}>
                    <Link
                      to={`/app/records?day=${item.day}`}
                      className="grid grid-cols-[64px_minmax(0,1fr)] items-center gap-4 py-3"
                    >
                      <span>
                        <span className="block text-lg font-semibold">{item.calendar.pillar}</span>
                        <span className="block text-[11px] text-cream/45">{item.day.slice(5)}</span>
                      </span>
                      <span className="min-w-0">
                        <span className="block truncate text-sm text-cream/85">{item.note}</span>
                        <span className="block text-xs text-cream/45">
                          {c.moods[item.mood - 1]} · {c.topics[topics.indexOf(item.topic)]}
                        </span>
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-4 text-sm leading-6 text-cream/55">{c.empty}</p>
            )}
            {charts.length > 0 && (
              <div className="mt-4 border-t border-white/[0.07] pt-4">
                <p className="eyebrow mb-2">{w.resume}</p>
                {charts.slice(0, 2).map((chart) => (
                  <Link
                    key={chart.sessionId}
                    to={`/app/charts/${encodeURIComponent(chart.sessionId)}`}
                    className="block truncate py-1 text-sm text-gold"
                  >
                    {chart.label} →
                  </Link>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen text-cream">
      <main className="mx-auto max-w-[1240px] px-5 py-8 sm:px-8 sm:py-10">
        <PageHeader
          title={w[view === "today" ? "records" : view]}
          note={view === "explore" ? w.exploreBody : w.recordsBody}
          action={
            view === "records" && data?.entries.length ? (
              <Button variant="ghost" size="sm" onClick={exportEntries}>
                <Download size={15} />
                {c.export}
              </Button>
            ) : undefined
          }
        />
        {error && (
          <div
            role="alert"
            className="mb-5 rounded-xl border border-red/50 bg-red/10 p-4 text-sm text-[#ffb5a4]"
          >
            {error}{" "}
            {!data && (
              <Button onClick={() => void load()} variant="ghost">
                {c.retry}
              </Button>
            )}
          </div>
        )}
        {!data ? (
          <p role="status">{!error && c.loading}</p>
        ) : (
          <div className="grid gap-6 @4xl:grid-cols-[minmax(0,1fr)_320px]">
            <div className="min-w-0 space-y-6">
              {view !== "explore" && (
                <section className={panel}>
                  <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
                    <h2 className="flex items-baseline gap-3 font-display text-2xl">
                      {entry?.calendar.pillar && (
                        <span className="han text-3xl">{entry.calendar.pillar}</span>
                      )}
                      {c.record}
                    </h2>
                    <input
                      aria-label={c.record}
                      className={field}
                      type="date"
                      value={day}
                      max={data.today.day}
                      disabled={!!busy}
                      onChange={(e) => {
                        if (
                          dirty &&
                          !window.confirm(
                            locale === "zh"
                              ? "切换日期会放弃未保存内容，继续吗？"
                              : "Discard unsaved changes?"
                          )
                        )
                          return;
                        if (e.target.value) void selectDate(e.target.value);
                      }}
                    />
                  </div>
                  {day !== data.today.day && (
                    <p className="mb-4 text-xs text-gold">
                      {c.edit} · {entry?.calendar.pillar ?? day}
                    </p>
                  )}
                  <fieldset disabled={!!busy}>
                    <legend className="mb-3 text-sm text-cream/75">{c.mood}</legend>
                    <MoodPicker labels={c.moods} legend={c.mood} value={mood} onPick={setMood} />
                  </fieldset>
                  <div className="mt-5 flex flex-wrap gap-2" role="group" aria-label={c.topic}>
                    {topics.map((value, i) => (
                      <button
                        key={value}
                        type="button"
                        disabled={!!busy}
                        aria-pressed={topic === value}
                        onClick={() => setTopic(value)}
                        className={`h-9 rounded-full border px-3.5 text-xs transition-colors ${topic === value ? "border-paper bg-paper text-[#16130e]" : "border-white/12 text-cream/60 hover:bg-white/5"}`}
                      >
                        {c.topics[i]}
                      </button>
                    ))}
                  </div>
                  <label htmlFor="daily-note" className="mb-2 mt-5 block text-sm text-cream/75">
                    {c.note}
                  </label>
                  <Textarea
                    id="daily-note"
                    value={note}
                    maxLength={4000}
                    disabled={!!busy}
                    onChange={(e) => {
                      setNote(e.target.value);
                      setNotice("");
                    }}
                    placeholder={c.placeholder}
                    className="min-h-40 text-base"
                  />
                  <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
                    <span role="status" className="text-xs text-cream/65">
                      {notice || `${note.length}/4000`}
                    </span>
                    <div className="flex gap-2">
                      {entry && (
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={!!busy}
                          onClick={() => void remove()}
                        >
                          {c.remove}
                        </Button>
                      )}
                      <Button disabled={!!busy} onClick={() => void save()}>
                        {busy === "save" ? (
                          <LoaderCircle className="size-4 animate-spin" />
                        ) : (
                          <Check size={16} />
                        )}{" "}
                        {c.save}
                      </Button>
                    </div>
                  </div>
                  {entry && !dirty && entry.note && (
                    <Link
                      to={`/app/explore?day=${day}`}
                      className="press-feedback mt-6 flex items-center gap-3 rounded-2xl border border-white/[0.08] bg-white/[0.03] p-4 transition-colors hover:border-gold/40"
                    >
                      <span className="grid size-9 place-items-center rounded-full bg-paper text-[#16130e]">
                        <Sparkles size={15} />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm text-cream">{w.continue}</span>
                        <span className="block truncate text-xs text-cream/45">
                          {w.exploreBody}
                        </span>
                      </span>
                      <span className="text-cream/40">→</span>
                    </Link>
                  )}
                </section>
              )}
              {view === "explore" && (
                <section className={panel}>
                  <h2 className="text-xl font-medium">{w.context}</h2>
                  {entry ? (
                    <div className="surface-2 mt-4 p-4">
                      <p className="text-xs text-cream/55">
                        {entry.day} · {entry.calendar.pillar} · {c.moods[entry.mood - 1]}
                      </p>
                      <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-cream/80">
                        {entry.note}
                      </p>
                      <Link
                        to={`/app/records?day=${entry.day}`}
                        className="mt-3 inline-block text-xs text-gold"
                      >
                        {c.edit} →
                      </Link>
                    </div>
                  ) : (
                    <div className="py-5">
                      <p className="text-sm leading-7 text-cream/65">{w.noEntry}</p>
                      <Link to="/app" className="mt-4 inline-block text-gold">
                        {w.write} →
                      </Link>
                    </div>
                  )}
                  <h2 className="mt-8 text-xl font-medium">{c.ask}</h2>
                  {hasChart === false && (
                    <div className="mt-4">
                      <AtlasChartFirst compact />
                    </div>
                  )}
                  <label
                    htmlFor="reflection-question"
                    className="mb-2 mt-5 block text-sm text-cream/75"
                  >
                    {c.question}
                  </label>
                  <Textarea
                    id="reflection-question"
                    value={question}
                    maxLength={1000}
                    onChange={(e) => setQuestion(e.target.value)}
                    disabled={!!busy}
                    className="min-h-24 text-base"
                  />
                  <label className="mt-4 block text-sm text-cream/75">
                    {c.chart}
                    <select
                      value={sessionId}
                      disabled={!!busy}
                      onChange={(e) => setSessionId(e.target.value)}
                      className={`${field} mt-2 w-full`}
                    >
                      <option value="">{c.noChart}</option>
                      {charts.map((item) => (
                        <option key={item.sessionId} value={item.sessionId}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <p className="my-4 text-xs leading-relaxed text-cream/65">{c.consent}</p>
                  <Button
                    disabled={
                      !!busy || question.trim().length < 3 || !entry || dirty || hasChart === false
                    }
                    onClick={() => void ask()}
                  >
                    {busy === "ask" ? (
                      <LoaderCircle className="size-4 animate-spin" />
                    ) : (
                      <Sparkles size={16} />
                    )}{" "}
                    {busy === "ask" ? c.thinking : c.send}
                  </Button>
                  {(!entry || dirty) && <p className="mt-2 text-xs text-gold">{c.noSave}</p>}
                  {entry?.reflections.map((item) => (
                    <article className="mt-6 border-t border-white/10 pt-6" key={item.requestId}>
                      <h3 className="font-medium">{item.question}</h3>
                      <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-cream/80">
                        {item.answer.summary}
                      </p>
                      {item.actionStates && (
                        <p className="mt-3 text-xs text-gold">
                          {Object.entries(item.actionStates)
                            .map(
                              ([lens, state]) =>
                                `${c[lens as "bazi" | "vedic" | "tarot"]} · ${state === "done" ? (locale === "zh" ? "已完成" : "Done") : locale === "zh" ? "准备尝试" : "Planned"}`
                            )
                            .join(" / ")}
                        </p>
                      )}
                      <details className="mt-4">
                        <summary className="cursor-pointer text-sm text-gold">{w.sources}</summary>
                        <div className="mt-4 space-y-4">
                          {(["bazi", "vedic", "tarot"] as const).map((lens) => (
                            <section key={lens} className="rounded-xl bg-white/[0.035] p-4">
                              <h4 className="text-sm font-medium text-gold">
                                {c[lens]}
                                {lens === "tarot" ? ` · ${item.tarotCard}` : ""}
                              </h4>
                              <p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-cream/80">
                                {item.answer[lens].interpretation}
                              </p>
                              <p className="mt-3 text-sm leading-7">
                                <span className="text-gold">{c.action}：</span>
                                {item.answer[lens].action}
                              </p>
                              <div className="mt-3 flex flex-wrap gap-2">
                                <Button
                                  size="sm"
                                  variant="outline"
                                  disabled={!!busy}
                                  onClick={() =>
                                    void setAction(
                                      item.requestId,
                                      lens,
                                      item.actionStates?.[lens] === "planned"
                                        ? "done"
                                        : item.actionStates?.[lens] === "done"
                                          ? "planned"
                                          : "planned"
                                    )
                                  }
                                >
                                  {item.actionStates?.[lens] === "done"
                                    ? locale === "zh"
                                      ? "✓ 已完成 · 再次尝试"
                                      : "✓ Done · Try again"
                                    : item.actionStates?.[lens] === "planned"
                                      ? locale === "zh"
                                        ? "准备尝试 · 标记完成"
                                        : "Planned · Mark done"
                                      : locale === "zh"
                                        ? "我想试一试"
                                        : "I want to try this"}
                                </Button>
                                {item.actionStates?.[lens] && (
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    disabled={!!busy}
                                    onClick={() => void setAction(item.requestId, lens, "none")}
                                  >
                                    {locale === "zh" ? "取消记录" : "Clear status"}
                                  </Button>
                                )}
                              </div>
                            </section>
                          ))}
                        </div>
                      </details>
                      <p className="mt-4 text-sm leading-7">
                        {c.reflection}：{item.answer.questionToReflectOn}
                      </p>
                      <details className="mt-3 text-xs text-cream/60">
                        <summary>{c.snapshot}</summary>
                        <p className="mt-2 whitespace-pre-wrap">{item.noteSnapshot}</p>
                      </details>
                    </article>
                  ))}
                </section>
              )}
            </div>
            <aside className="min-w-0 space-y-6">
              {view === "today" && (
                <section
                  className={`${panel} flex flex-wrap items-center justify-between gap-6 bg-gradient-to-br from-gold/10 to-transparent`}
                >
                  <div>
                    <p className="text-xs text-gold">
                      {c.today} · {data.today.day}
                    </p>
                    <div className="mt-3 flex items-baseline gap-4">
                      <h2 className="text-4xl font-light tracking-widest">{data.today.pillar}</h2>
                      <p className="text-sm text-cream/75">
                        {data.today.stemElement} · {data.today.branchElement}
                      </p>
                    </div>
                    <p className="mt-4 text-xs leading-relaxed text-cream/65">
                      {c.facts}
                      <br />
                      {zone}
                    </p>
                  </div>
                  <Sparkles size={24} className="text-gold/70" />
                </section>
              )}
              {view === "today" && charts.length > 0 && (
                <section className={panel}>
                  <h2 className="text-lg font-medium">{w.resume}</h2>
                  {charts.slice(0, 3).map((chart) => (
                    <Link
                      key={chart.sessionId}
                      to={`/app/charts/${encodeURIComponent(chart.sessionId)}`}
                      className="mt-4 block truncate text-sm text-gold"
                    >
                      {chart.label} →
                    </Link>
                  ))}
                </section>
              )}
              <section className={panel}>
                <h2 className="text-lg font-medium">
                  {view === "today" ? w.recent : view === "explore" ? w.choose : c.history}
                </h2>
                <p className="mt-2 text-xs text-cream/60">{c.recent}</p>
                <div className="mt-4 max-h-[440px] space-y-2 overflow-y-auto">
                  {data.entries.length ? (
                    (view === "today" ? data.entries.slice(0, 5) : data.entries).map(
                      (item: JournalEntry) => (
                        <button
                          key={item.day}
                          disabled={!!busy}
                          onClick={() => {
                            if (
                              !dirty ||
                              window.confirm(
                                locale === "zh" ? "放弃未保存的内容？" : "Discard unsaved changes?"
                              )
                            ) {
                              if (view === "today") navigate(`/app/records?day=${item.day}`);
                              else void selectDate(item.day);
                            }
                          }}
                          className={`w-full rounded-2xl border p-3 text-left ${day === item.day ? "border-white/30 bg-night-3" : "border-white/[0.07] hover:bg-white/[0.04]"}`}
                        >
                          <span className="flex justify-between text-sm">
                            <span>{item.day}</span>
                            <span className="text-gold">{item.calendar.pillar}</span>
                          </span>
                          <span className="mt-1 block text-xs text-cream/65">
                            {c.moods[item.mood - 1]} · {c.topics[topics.indexOf(item.topic)]}
                          </span>
                          <span className="mt-2 block truncate text-sm text-cream/80">
                            {item.note}
                          </span>
                        </button>
                      )
                    )
                  ) : (
                    <p className="text-sm leading-7 text-cream/65">{c.empty}</p>
                  )}
                </div>
                {view === "today" && (
                  <Link to="/app/records" className="mt-4 block text-sm text-gold">
                    {w.all} →
                  </Link>
                )}
              </section>
              {view === "records" && (
                <Link
                  to="/app/days"
                  className="surface block p-5 transition-colors hover:border-white/20"
                >
                  <p className="eyebrow">{c.trends}</p>
                  <p className="mt-3 flex items-baseline gap-2">
                    <span className="font-display text-4xl">{data.summary.recordedDays}</span>
                    <span className="text-sm text-cream/50">{c.samples}</span>
                  </p>
                  <p className="mt-1 text-sm text-cream/50">
                    {c.baseline}: {data.summary.averageMood ?? "—"}/5
                  </p>
                  <p className="mt-4 text-sm text-gold">{d.nav.days} →</p>
                </Link>
              )}
            </aside>
          </div>
        )}
      </main>
    </div>
  );
}
