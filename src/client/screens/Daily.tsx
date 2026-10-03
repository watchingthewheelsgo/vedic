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
import { MoodMoon, MoodPicker } from "../components/MoodMoon";
import { DailyCardLauncher } from "../components/FortuneCard";
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
  const [noteOpen, setNoteOpen] = useState(false);
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
    const nextBright = upcoming(data.today.day, data.summary, 30).find(
      (item) => item.fit === "bright" && item.day !== data.today.day
    );
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
    const dayGuidance = guidance?.guidance;
    return (
      <div className="mx-auto max-w-[640px] px-5 py-8 sm:py-12">
        <header className="rise-in text-center">
          <p className="text-sm text-cream/45">{dateLabel}</p>
          <h1 className="mt-1 font-display text-[38px] leading-tight sm:text-[44px]">
            {d.greeting(new Date().getHours(), user?.firstName)}
          </h1>
        </header>

        {error && (
          <div
            role="alert"
            className="mt-5 rounded-2xl border border-red/50 bg-red/10 p-4 text-sm text-[#ffb5a4]"
          >
            {error}
          </div>
        )}

        {hasChart === false ? (
          <section className="rise-in mt-8 rounded-3xl border border-gold/25 bg-gold/[0.05] p-6 text-center">
            <p className="text-[15px] font-medium">{d.startTitle}</p>
            <p className="mx-auto mt-1 max-w-sm text-sm leading-6 text-cream/60">{d.startBody}</p>
            <div className="mt-4 flex justify-center gap-2">
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
        ) : (
          dayGuidance && (
            <div className="rise-in mt-5 flex justify-center" style={{ animationDelay: "80ms" }}>
              <DailyCardLauncher
                day={data.today.day}
                guidance={dayGuidance}
                fit={todayReading.fit}
                locale={locale}
              />
            </div>
          )
        )}

        <section className="rise-in mt-10 text-center" style={{ animationDelay: "160ms" }}>
          <p className="han text-5xl font-bold leading-none">{data.today.pillar}</p>
          <p className="mt-3 text-sm text-cream/50">
            {d.elements[stemElement(data.today.stem)]} ·{" "}
            {d.elements[branchElement(data.today.branch)]}
            {dayGuidance && (
              <>
                {" · "}
                <span className="font-display text-base italic text-cream/75">
                  {d.tenGodDay(dayGuidance.facts.tenGod, dayGuidance.facts.dayMaster)}
                </span>
              </>
            )}
          </p>
          {dayGuidance && (
            <div className="mt-6 grid grid-cols-2 gap-px overflow-hidden rounded-3xl border border-white/[0.07] bg-white/[0.07] text-left">
              <div className="bg-night p-5">
                <p className="mb-2 flex items-center gap-1.5 text-xs text-cream/50">
                  <Check size={13} strokeWidth={2.4} className="text-jade" />
                  {d.goodFor}
                </p>
                <ul className="space-y-1 text-[15px] leading-6">
                  {dayGuidance.goodFor.map((item) => (
                    <li key={item.id}>{guidanceText(item, locale)}</li>
                  ))}
                </ul>
              </div>
              <div className="bg-night p-5">
                <p className="mb-2 flex items-center gap-1.5 text-xs text-cream/50">
                  <Minus size={13} strokeWidth={2.4} className="text-cream/50" />
                  {d.avoid}
                </p>
                <ul className="space-y-1 text-[15px] leading-6 text-cream/75">
                  {dayGuidance.avoid.map((item) => (
                    <li key={item.id}>{guidanceText(item, locale)}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}
          {hasChart && (
            <button
              type="button"
              onClick={() => askAbout(d.askToday)}
              className="mt-4 inline-flex h-9 items-center gap-2 rounded-full px-3 text-sm text-cream/60 transition-colors hover:text-gold-light"
            >
              <Sparkles size={14} />
              {d.askCta}
            </button>
          )}
        </section>

        <section
          className="rise-in mt-10 border-t border-white/[0.07] pt-8"
          style={{ animationDelay: "240ms" }}
        >
          <div className="mb-4 flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between sm:gap-3">
            <h2 className="font-display text-2xl">{d.quick}</h2>
            <span role="status" className="text-xs text-cream/45">
              {entry ? d.checkedIn : d.oneTap}
            </span>
          </div>
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
          {noteOpen || note ? (
            <div className="mt-4">
              <div className="mb-3 flex flex-wrap gap-2">
                {topics.map((value, i) => (
                  <button
                    key={value}
                    type="button"
                    disabled={!!busy}
                    aria-pressed={topic === value}
                    onClick={() => setTopic(value)}
                    className={`h-8 rounded-full border px-3 text-xs transition-colors ${topic === value ? "border-paper bg-paper text-[#16130e]" : "border-white/12 text-cream/60 hover:bg-white/5"}`}
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
                autoFocus={noteOpen && !note}
                onChange={(e) => {
                  setNote(e.target.value);
                  setNotice("");
                }}
                placeholder={c.placeholder}
                className="min-h-24 text-base"
              />
              <div className="mt-3 flex items-center justify-between gap-3">
                <span className="text-xs text-cream/45">{notice ? d.quickSaved : ""}</span>
                <Button size="sm" disabled={!!busy || !dirty} onClick={() => void save()}>
                  {busy === "save" ? (
                    <LoaderCircle className="size-4 animate-spin" />
                  ) : (
                    <Check size={15} />
                  )}
                  {c.save}
                </Button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setNoteOpen(true)}
              className="mt-4 text-sm text-cream/50 transition-colors hover:text-cream"
            >
              + {d.addNote}
            </button>
          )}
        </section>

        <Link
          to="/app/days"
          className="rise-in mt-10 flex items-center justify-between gap-4 rounded-full border border-white/[0.07] px-5 py-3.5 text-sm text-cream/60 transition-colors hover:border-white/20 hover:text-cream"
          style={{ animationDelay: "320ms" }}
        >
          <span className="min-w-0 truncate">
            {nextBright ? (
              <>
                {d.nextBright} ·{" "}
                <span className="text-cream">
                  {shortDate(nextBright.day)} <span className="han">{nextBright.pillar}</span>
                </span>
              </>
            ) : (
              d.fitLong[todayReading.fit]
            )}
          </span>
          <span aria-hidden>→</span>
        </Link>
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
                          <span className="flex items-center gap-3">
                            <span className="text-gold-light">
                              <MoodMoon level={item.mood} size={22} />
                            </span>
                            <span className="min-w-0 flex-1">
                              <span className="flex items-baseline justify-between gap-2">
                                <span className="text-sm text-cream/85">{item.day}</span>
                                <span className="han text-lg leading-none">
                                  {item.calendar.pillar}
                                </span>
                              </span>
                              <span className="block text-xs text-cream/45">
                                {c.moods[item.mood - 1]} · {c.topics[topics.indexOf(item.topic)]}
                              </span>
                            </span>
                          </span>
                          {item.note && (
                            <span className="mt-2 block truncate text-sm text-cream/70">
                              {item.note}
                            </span>
                          )}
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
