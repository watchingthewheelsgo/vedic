import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode
} from "react";
import { Link, useLocation } from "react-router-dom";
import { useUser } from "@clerk/clerk-react";
import { ArrowUp, LoaderCircle, Plus, Sparkles, X } from "lucide-react";
import { api } from "../api";
import { useI18n } from "../i18n/provider";
import {
  atlasContextFor,
  atlasCopy,
  chartLabel,
  readStoredTurns,
  storeTurns,
  turnText,
  type AtlasLens,
  type AtlasTurn
} from "../lib/atlas";
import type { AdminSessionSummary } from "../../shared/domain";

export type WorkspaceChart = {
  sessionId: string;
  kind: "vedic" | "bazi";
  label: string;
  completed: boolean;
};

type AtlasState = {
  turns: AtlasTurn[];
  busy: boolean;
  error: string;
  useNotes: boolean;
  setUseNotes: (value: boolean) => void;
  ask: (message: string) => Promise<void>;
  /** Open Atlas (drawer or rail) and ask right away. */
  askAbout: (message: string) => void;
  reset: () => void;
  charts: WorkspaceChart[];
  /** null while loading; Atlas needs a chart (Vedic or BaZi) to speak about a person. */
  hasChart: boolean | null;
  reading: WorkspaceChart | null;
  drawerOpen: boolean;
  setDrawerOpen: (value: boolean) => void;
};

const AtlasContext = createContext<AtlasState | null>(null);

function chartFrom(session: AdminSessionSummary, localeTag: string): WorkspaceChart {
  return {
    sessionId: session.sessionId,
    kind: session.stage.startsWith("bazi_") ? "bazi" : "vedic",
    label: chartLabel(session.subject, localeTag),
    completed: session.status === "completed"
  };
}

export function AtlasProvider({ children }: { children: ReactNode }) {
  const { locale, localeTag } = useI18n();
  const { user } = useUser();
  const { pathname } = useLocation();
  const copy = atlasCopy[locale];
  const storageKey = `signatlas.atlas.${user?.id ?? "me"}`;
  const [turns, setTurns] = useState<AtlasTurn[]>(() => readStoredTurns(storageKey));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [useNotes, setUseNotes] = useState(true);
  const [charts, setCharts] = useState<WorkspaceChart[]>([]);
  const [chartsLoaded, setChartsLoaded] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const turnsRef = useRef(turns);
  useEffect(() => {
    turnsRef.current = turns;
    storeTurns(storageKey, turns);
  }, [turns, storageKey]);

  useEffect(() => {
    let alive = true;
    api
      .listMySessions()
      .then((result) => {
        if (!alive) return;
        setCharts(result.sessions.map((session) => chartFrom(session, localeTag)));
        setChartsLoaded(true);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [localeTag]);

  // The reading on screen wins; otherwise the newest finished Vedic reading.
  const viewing = pathname.match(/^\/app\/charts\/([^/]+)/)?.[1];
  const finished = charts.filter((chart) => chart.kind === "vedic" && chart.completed);
  const reading = finished.find((chart) => chart.sessionId === viewing) ?? finished[0] ?? null;
  const readingId = reading?.sessionId ?? null;

  const ask = useCallback(
    async (message: string) => {
      const text = message.trim();
      if (text.length < 2 || busy) return;
      const history = turnsRef.current.slice(-8).map((turn) => ({
        role: turn.role,
        text: turnText(turn).slice(0, 2000)
      }));
      setTurns((current) => [...current, { id: crypto.randomUUID(), role: "user", text }]);
      setBusy(true);
      setError("");
      try {
        const answer = await api.askAtlas({
          message: text,
          history,
          locale,
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
          sessionId: readingId,
          useNotes
        });
        setTurns((current) => [...current, { id: crypto.randomUUID(), role: "atlas", answer }]);
      } catch (caught) {
        setError(caught instanceof Error && caught.message ? caught.message : copy.error);
      } finally {
        setBusy(false);
      }
    },
    [busy, copy.error, locale, readingId, useNotes]
  );

  const askAbout = useCallback(
    (message: string) => {
      setDrawerOpen(true);
      void ask(message);
    },
    [ask]
  );

  const value = useMemo(
    () => ({
      turns,
      busy,
      error,
      useNotes,
      setUseNotes,
      ask,
      askAbout,
      reset: () => {
        setTurns([]);
        setError("");
      },
      charts,
      hasChart: chartsLoaded ? charts.length > 0 : null,
      reading,
      drawerOpen,
      setDrawerOpen
    }),
    [turns, busy, error, useNotes, ask, askAbout, charts, chartsLoaded, reading, drawerOpen]
  );
  return <AtlasContext.Provider value={value}>{children}</AtlasContext.Provider>;
}

export function useAtlas(): AtlasState {
  const value = useContext(AtlasContext);
  if (!value) throw new Error("useAtlas must be used inside AtlasProvider");
  return value;
}

export function AtlasMark({ size = 36 }: { size?: number }) {
  return (
    <span
      className="grid shrink-0 place-items-center rounded-full bg-paper text-[#16130e]"
      style={{ width: size, height: size }}
    >
      <Sparkles size={Math.round(size * 0.44)} strokeWidth={1.8} />
    </span>
  );
}

const lensDot: Record<AtlasLens["source"], string> = {
  vedic: "bg-gold",
  bazi: "bg-jade",
  notes: "bg-cream"
};

function AtlasAnswerView({
  turn,
  onFollowUp
}: {
  turn: Extract<AtlasTurn, { role: "atlas" }>;
  onFollowUp: (q: string) => void;
}) {
  const { locale } = useI18n();
  const copy = atlasCopy[locale];
  const { answer } = turn;
  return (
    <div className="space-y-3">
      <p className="font-display text-[21px] leading-snug text-cream">{answer.headline}</p>
      {answer.answer.split(/\n{2,}/).map((paragraph, i) => (
        <p key={i} className="text-sm leading-6 text-cream/70">
          {paragraph}
        </p>
      ))}
      {answer.lenses.map((lens, i) => (
        <div key={i} className="rounded-2xl border border-white/[0.07] bg-night-2 p-3.5">
          <p className="mb-1.5 flex items-center gap-2 text-[11px] uppercase tracking-[0.12em] text-cream/55">
            <span className={`size-1.5 rounded-full ${lensDot[lens.source]}`} />
            {copy.lens[lens.source]}
          </p>
          <p className="text-sm leading-6 text-cream/80">{lens.text}</p>
          {lens.refs.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {lens.refs.map((ref) => (
                <span
                  key={ref}
                  className="rounded-md bg-night px-2 py-0.5 font-mono text-[10.5px] text-cream/45"
                >
                  {ref}
                </span>
              ))}
            </div>
          )}
        </div>
      ))}
      {answer.followUps.length > 0 && (
        <div className="flex flex-wrap gap-2 pt-1">
          {answer.followUps.map((question) => (
            <button
              key={question}
              type="button"
              onClick={() => onFollowUp(question)}
              className="min-h-9 rounded-full border border-white/12 px-3.5 py-1.5 text-left text-xs text-cream/75 hover:bg-white/[0.06]"
            >
              {question}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function AtlasConversation({ compact = false }: { compact?: boolean }) {
  const { locale } = useI18n();
  const copy = atlasCopy[locale];
  const location = useLocation();
  const { turns, busy, error, ask } = useAtlas();
  const end = useRef<HTMLDivElement>(null);
  const suggestions = copy.suggestions[atlasContextFor(location.pathname)];

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns.length, busy]);

  return (
    <div className={`flex flex-col ${compact ? "gap-5" : "gap-7"}`} aria-live="polite">
      {turns.length === 0 && (
        <div className={compact ? "pt-2" : "pt-6"}>
          <p className={`font-display ${compact ? "text-2xl" : "text-4xl"} text-cream`}>
            {copy.emptyTitle}
          </p>
          <p className="mt-2 text-sm leading-6 text-cream/55">{copy.emptyBody}</p>
          <div className="mt-4 flex flex-col gap-2">
            {suggestions.map((question) => (
              <button
                key={question}
                type="button"
                onClick={() => void ask(question)}
                className="min-h-11 rounded-2xl border border-white/10 bg-night-2 px-4 py-2.5 text-left text-sm text-cream/80 hover:border-white/20 hover:bg-night-3"
              >
                {question}
              </button>
            ))}
          </div>
        </div>
      )}
      {turns.map((turn) =>
        turn.role === "user" ? (
          <div key={turn.id} className="flex justify-end">
            <p className="max-w-[85%] whitespace-pre-wrap rounded-[20px] rounded-br-md bg-night-3 px-4 py-2.5 text-sm leading-6 text-cream">
              {turn.text}
            </p>
          </div>
        ) : (
          <AtlasAnswerView key={turn.id} turn={turn} onFollowUp={(q) => void ask(q)} />
        )
      )}
      {busy && (
        <p className="flex items-center gap-2 text-sm text-cream/55">
          <LoaderCircle className="size-4 animate-spin" />
          {copy.thinking}
        </p>
      )}
      {error && (
        <p role="alert" className="text-sm text-[#f0a493]">
          {error}
        </p>
      )}
      <div ref={end} />
    </div>
  );
}

export function AtlasComposer() {
  const { locale } = useI18n();
  const copy = atlasCopy[locale];
  const { ask, busy } = useAtlas();
  const [draft, setDraft] = useState("");
  const submit = () => {
    if (!draft.trim() || busy) return;
    const text = draft;
    setDraft("");
    void ask(text);
  };
  return (
    <form
      className="flex items-end gap-2 rounded-[26px] border border-white/14 bg-night-2 py-1.5 pl-4 pr-1.5 focus-within:border-white/30"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <label htmlFor="atlas-input" className="sr-only">
        {copy.placeholder}
      </label>
      <textarea
        id="atlas-input"
        rows={1}
        value={draft}
        maxLength={1200}
        placeholder={copy.placeholder}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault();
            submit();
          }
        }}
        className="max-h-32 min-h-10 flex-1 resize-none bg-transparent py-2 text-sm leading-6 text-cream outline-none placeholder:text-cream/35"
      />
      <button
        type="submit"
        aria-label={copy.send}
        disabled={busy || !draft.trim()}
        className="grid size-10 shrink-0 place-items-center rounded-full bg-paper text-[#16130e] disabled:opacity-35"
      >
        <ArrowUp size={17} strokeWidth={2} />
      </button>
    </form>
  );
}

function AtlasSources() {
  const { locale } = useI18n();
  const copy = atlasCopy[locale];
  const { reading, useNotes, setUseNotes } = useAtlas();
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <span className="inline-flex h-7 items-center gap-1.5 rounded-full border border-white/12 px-2.5 text-cream/65">
        <span className={`size-1.5 rounded-full ${reading ? "bg-gold" : "bg-white/25"}`} />
        {reading ? copy.chart : copy.noChart}
      </span>
      <label
        className="inline-flex h-7 cursor-pointer items-center gap-2 rounded-full border border-white/12 px-2.5 text-cream/65"
        title={copy.notesHint}
      >
        <input
          type="checkbox"
          checked={useNotes}
          onChange={(event) => setUseNotes(event.target.checked)}
          className="size-3.5 accent-[#f3f0e9]"
        />
        {copy.useNotes}
      </label>
    </div>
  );
}

function AtlasHeader({ onClose }: { onClose?: () => void }) {
  const { locale } = useI18n();
  const copy = atlasCopy[locale];
  const { reset, turns } = useAtlas();
  return (
    <div className="flex items-center gap-3">
      <AtlasMark />
      <div className="min-w-0 flex-1">
        <p className="font-display text-[22px] leading-none text-cream">{copy.name}</p>
        <p className="mt-1 truncate text-xs text-cream/50">{copy.tagline}</p>
      </div>
      {turns.length > 0 && (
        <button
          type="button"
          onClick={reset}
          aria-label={copy.newChat}
          title={copy.newChat}
          className="grid size-9 place-items-center rounded-full text-cream/60 hover:bg-white/[0.06]"
        >
          <Plus size={17} />
        </button>
      )}
      {onClose && (
        <button
          type="button"
          onClick={onClose}
          aria-label={copy.close}
          className="grid size-9 place-items-center rounded-full text-cream/60 hover:bg-white/[0.06]"
        >
          <X size={17} />
        </button>
      )}
    </div>
  );
}

/** Shown instead of the composer until the user has a chart. */
export function AtlasChartFirst({ compact = false }: { compact?: boolean }) {
  const { locale } = useI18n();
  const copy = atlasCopy[locale];
  const { setDrawerOpen } = useAtlas();
  return (
    <div className={compact ? "pt-2" : "pt-6"}>
      <p className={`font-display ${compact ? "text-2xl" : "text-4xl"} text-cream`}>
        {copy.chartFirstTitle}
      </p>
      <p className="mt-2 text-sm leading-6 text-cream/60">{copy.chartFirstBody}</p>
      <div className="mt-5 flex flex-wrap gap-2">
        <Link
          to="/app/charts/new"
          onClick={() => setDrawerOpen(false)}
          className="inline-flex h-10 items-center rounded-full bg-paper px-4 text-sm font-medium text-[#16130e]"
        >
          {copy.chartFirstVedic}
        </Link>
        <Link
          to="/app/charts/bazi"
          onClick={() => setDrawerOpen(false)}
          className="inline-flex h-10 items-center rounded-full border border-white/15 px-4 text-sm text-cream/80 hover:bg-white/[0.05]"
        >
          {copy.chartFirstBazi}
        </Link>
      </div>
    </div>
  );
}

/** Atlas as a pop-out window (full screen on phones), opened from the launcher. */
export function AtlasPanel() {
  const { locale } = useI18n();
  const copy = atlasCopy[locale];
  const { drawerOpen, setDrawerOpen, hasChart } = useAtlas();
  useEffect(() => {
    if (!drawerOpen) return;
    const close = (event: KeyboardEvent) => event.key === "Escape" && setDrawerOpen(false);
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [drawerOpen, setDrawerOpen]);
  if (!drawerOpen) return null;
  return (
    <div
      role="dialog"
      aria-label={copy.name}
      className="rise-in fixed inset-0 z-[60] flex flex-col bg-[#0d0e14] sm:inset-auto sm:bottom-24 sm:right-6 sm:h-[min(660px,calc(100dvh-128px))] sm:w-[400px] sm:overflow-hidden sm:rounded-3xl sm:border sm:border-white/10 sm:shadow-[0_30px_90px_rgba(0,0,0,0.6)]"
    >
      <div className="flex h-full flex-col gap-4 px-5 pb-5 pt-5">
        <AtlasHeader onClose={() => setDrawerOpen(false)} />
        {hasChart === false ? (
          <AtlasChartFirst compact />
        ) : (
          <>
            <AtlasSources />
            <div className="-mx-1 min-h-0 flex-1 overflow-y-auto px-1">
              <AtlasConversation compact />
            </div>
            <div className="space-y-2">
              <AtlasComposer />
              <p className="text-center text-[11px] text-cream/35">{copy.disclaimer}</p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

/** Round launcher in the bottom-right corner, next to the feedback button. */
export function AtlasLauncher() {
  const { locale } = useI18n();
  const copy = atlasCopy[locale];
  const { drawerOpen, setDrawerOpen, busy } = useAtlas();
  return (
    <button
      type="button"
      onClick={() => setDrawerOpen(!drawerOpen)}
      aria-label={drawerOpen ? copy.close : copy.open}
      aria-expanded={drawerOpen}
      title={copy.open}
      className="press-feedback fixed bottom-[calc(5.25rem+env(safe-area-inset-bottom))] right-4 z-[61] grid size-[52px] place-items-center rounded-full bg-paper text-[#16130e] shadow-[0_14px_40px_rgba(0,0,0,0.55)] transition-transform hover:scale-105 max-sm:aria-expanded:hidden lg:bottom-6 lg:right-6"
    >
      {busy ? (
        <LoaderCircle size={20} className="animate-spin" />
      ) : drawerOpen ? (
        <X size={20} />
      ) : (
        <Sparkles size={20} strokeWidth={1.8} />
      )}
    </button>
  );
}
