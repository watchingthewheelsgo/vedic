import { useCallback, useEffect, useState } from "react";
import { PageHeader } from "../components/PageHeader";
import { chartLabel } from "../lib/atlas";
import { ReadingsShowcase } from "../components/ReadingsShowcase";
import { Link, useSearchParams } from "react-router-dom";
import { Download, LoaderCircle, Plus, Sparkles } from "lucide-react";
import { api } from "../api";
import { useI18n } from "../i18n/provider";
import type { LocaleCode } from "../i18n/messages";
import type { AdminSessionStatus, AdminSessionSummary } from "../../shared/domain";

type Tab = "vedic" | "bazi" | "tarot";

const copy: Record<
  LocaleCode,
  {
    title: string;
    body: string;
    tabs: Record<Tab, string>;
    soon: string;
    newVedic: string;
    newBazi: string;
    preview: string;
    open: string;
    pdf: string;
    untitled: string;
    status: Record<AdminSessionStatus, string>;
    emptyVedic: string;
    emptyBazi: string;
    tarotBody: string;
    vedicPitch: string;
    baziPitch: string;
    error: string;
  }
> = {
  en: {
    title: "Readings",
    body: "Vedic, BaZi and soon Tarot. Each one is calculated first, then explained.",
    tabs: { vedic: "Vedic", bazi: "BaZi", tarot: "Tarot" },
    soon: "Soon",
    newVedic: "New Vedic reading",
    newBazi: "New BaZi chart",
    preview: "Preview",
    open: "Open",
    pdf: "PDF",
    untitled: "Untitled chart",
    status: {
      draft: "Started",
      validation: "Birth-time check",
      queued: "Queued",
      running: "Writing your reading",
      completed: "Ready",
      failed: "Paused",
      stalled: "Paused"
    },
    emptyVedic: "Your first Vedic reading starts with your birth date, time and place.",
    emptyBazi: "Calculate your Four Pillars, Day Master and luck pillars.",
    tarotBody: "Tarot readings for reflection, connected to your journal, are coming soon.",
    vedicPitch:
      "Birth chart, life chapters and a reading by life area, every claim tied to its source.",
    baziPitch: "Four Pillars read with Di Tian Sui, Zi Ping Zhen Quan and Qiong Tong Bao Jian.",
    error: "Couldn't load your charts."
  },
  zh: {
    title: "解读",
    body: "吠陀占星、八字，塔罗即将推出。每一份都先精确计算，再解读。",
    tabs: { vedic: "Vedic", bazi: "八字", tarot: "塔罗" },
    soon: "即将推出",
    newVedic: "新建 Vedic 读盘",
    newBazi: "新建八字命盘",
    preview: "预览",
    open: "打开",
    pdf: "PDF",
    untitled: "未命名命盘",
    status: {
      draft: "已开始",
      validation: "出生时间校验",
      queued: "排队中",
      running: "正在撰写报告",
      completed: "已完成",
      failed: "已暂停",
      stalled: "已暂停"
    },
    emptyVedic: "第一份 Vedic 报告，从出生日期、时间和地点开始。",
    emptyBazi: "计算你的四柱、日主与大运。",
    tarotBody: "与日记相连的塔罗反思，即将推出。",
    vedicPitch: "本命盘、人生阶段与分领域解读，每条结论都标明依据。",
    baziPitch: "依据《滴天髓》《子平真诠》《穷通宝鉴》解读四柱。",
    error: "暂时无法加载命盘。"
  },
  ja: {
    title: "リーディング",
    body: "インド占星術、八字、そして近日タロット。どれもまず計算し、それから解説します。",
    tabs: { vedic: "Vedic", bazi: "八字", tarot: "タロット" },
    soon: "近日",
    newVedic: "Vedic リーディングを作成",
    newBazi: "八字チャートを作成",
    preview: "プレビュー",
    open: "開く",
    pdf: "PDF",
    untitled: "無題のチャート",
    status: {
      draft: "開始",
      validation: "出生時刻の確認",
      queued: "待機中",
      running: "レポート作成中",
      completed: "完了",
      failed: "一時停止",
      stalled: "一時停止"
    },
    emptyVedic: "最初の Vedic リーディングは、生年月日・時刻・場所から始まります。",
    emptyBazi: "四柱、日主、大運を計算します。",
    tarotBody: "日記とつながるタロットの振り返りは近日公開です。",
    vedicPitch: "出生図、人生の章、分野別のリーディング。すべての結論に根拠を示します。",
    baziPitch: "『滴天髄』『子平真詮』『窮通宝鑑』で四柱を読み解きます。",
    error: "チャートを読み込めませんでした。"
  }
};

const isBazi = (session: AdminSessionSummary) => session.stage.startsWith("bazi_");

export function Charts() {
  const { locale, localeTag } = useI18n();
  const c = copy[locale];
  const [params] = useSearchParams();
  const requested = params.get("tab");
  const [tab, setTab] = useState<Tab>(
    requested === "bazi" || requested === "tarot" ? requested : "vedic"
  );
  useEffect(() => {
    if (requested === "vedic" || requested === "bazi" || requested === "tarot") setTab(requested);
  }, [requested]);
  const [sessions, setSessions] = useState<AdminSessionSummary[] | null>(null);
  const [error, setError] = useState("");
  const [downloading, setDownloading] = useState("");

  const load = useCallback(async () => {
    try {
      setSessions((await api.listMySessions()).sessions);
    } catch {
      setError(c.error);
    }
  }, [c.error]);

  useEffect(() => {
    void load();
  }, [load]);

  async function download(sessionId: string) {
    setDownloading(sessionId);
    try {
      await api.downloadReportPdf(sessionId);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : c.error);
    } finally {
      setDownloading("");
    }
  }

  const visible = (sessions ?? []).filter((session) =>
    tab === "bazi" ? isBazi(session) : !isBazi(session)
  );
  const accent = tab === "bazi" ? "bg-jade" : "bg-gold";

  return (
    <div className="mx-auto max-w-[1080px] px-5 py-8 sm:px-8 sm:py-10">
      <PageHeader title={c.title} note={c.body} />
      <div className="mb-8">
        <ReadingsShowcase showTitle={false} />
      </div>

      <div className="mb-6 flex flex-wrap items-center gap-2" role="tablist">
        {(["vedic", "bazi", "tarot"] as const).map((key) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={`flex h-10 items-center gap-2 rounded-full px-4 text-sm font-medium transition-colors ${
              tab === key
                ? key === "vedic"
                  ? "bg-gold text-[#16130e]"
                  : key === "bazi"
                    ? "bg-jade text-[#0a0b10]"
                    : "bg-night-3 text-cream"
                : key === "tarot"
                  ? "border border-dashed border-white/20 text-cream/55"
                  : "border border-white/14 text-cream/70 hover:bg-white/[0.05]"
            }`}
          >
            {c.tabs[key]}
            {key === "tarot" && (
              <span className="rounded-full bg-night-3 px-1.5 py-0.5 text-[10px] text-cream/55">
                {c.soon}
              </span>
            )}
            {key === "bazi" && tab !== "bazi" && (
              <span className="text-[10px] text-cream/40">{c.preview}</span>
            )}
          </button>
        ))}
      </div>

      {error && (
        <p role="alert" className="mb-4 text-sm text-[#f0a493]">
          {error}
        </p>
      )}

      {tab === "tarot" ? (
        <section className="rounded-3xl border border-dashed border-white/20 p-8 text-center">
          <p className="font-display text-3xl text-cream/80">XXII</p>
          <p className="mx-auto mt-3 max-w-md text-sm leading-6 text-cream/55">{c.tarotBody}</p>
        </section>
      ) : (
        <div className="grid gap-4 @3xl:grid-cols-2">
          <Link
            to={tab === "bazi" ? "/app/charts/bazi" : "/app/charts/new"}
            className="press-feedback group flex min-h-40 flex-col justify-between rounded-3xl border border-white/10 bg-night-2 p-6 hover:border-white/25"
          >
            <span className="flex items-center gap-3">
              <span
                className={`grid size-10 place-items-center rounded-full ${accent} text-[#0a0b10]`}
              >
                <Plus size={18} />
              </span>
              <span className="font-display text-2xl">
                {tab === "bazi" ? c.newBazi : c.newVedic}
              </span>
            </span>
            <span className="mt-4 text-sm leading-6 text-cream/55">
              {tab === "bazi" ? c.baziPitch : c.vedicPitch}
            </span>
          </Link>

          {sessions === null && !error && (
            <div className="grid min-h-40 place-items-center rounded-3xl bg-night-2">
              <LoaderCircle className="size-5 animate-spin text-cream/50" />
            </div>
          )}

          {sessions !== null && visible.length === 0 && (
            <div className="flex min-h-40 items-center rounded-3xl border border-white/[0.06] p-6 text-sm leading-6 text-cream/50">
              {tab === "bazi" ? c.emptyBazi : c.emptyVedic}
            </div>
          )}

          {visible.map((session) => {
            const place = session.subject?.birthPlace?.split("|")[0].trim();
            const running = ["queued", "running", "validation"].includes(session.status);
            return (
              <article
                key={session.sessionId}
                className="flex min-h-40 flex-col rounded-3xl border border-white/[0.08] bg-night-2 p-6"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate font-display text-2xl leading-tight">
                      {chartLabel(session.subject, localeTag).split(" · ")[0] || c.untitled}
                    </p>
                    <p className="mt-1 truncate text-sm text-cream/50">
                      {[
                        session.subject?.birthTime,
                        place && !place.startsWith("lat=") ? place : null
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                  </div>
                  <span
                    className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] ${
                      session.status === "completed"
                        ? "bg-paper text-[#16130e]"
                        : session.status === "failed" || session.status === "stalled"
                          ? "border border-dashed border-white/30 text-cream/65"
                          : "bg-night-3 text-cream/75"
                    }`}
                  >
                    {c.status[session.status]}
                  </span>
                </div>
                {running && (
                  <div className="mt-4 h-1 overflow-hidden rounded-full bg-night-3">
                    <div
                      className={`h-full rounded-full ${accent}`}
                      style={{ width: `${Math.max(6, Math.min(100, session.progress.percent))}%` }}
                    />
                  </div>
                )}
                <div className="mt-auto flex items-center gap-2 pt-5">
                  <Link
                    to={`/app/charts/${encodeURIComponent(session.sessionId)}`}
                    className="inline-flex h-10 items-center gap-2 rounded-full bg-paper px-4 text-sm font-medium text-[#16130e]"
                  >
                    {c.open}
                  </Link>
                  {session.status === "completed" && !isBazi(session) && (
                    <>
                      <Link
                        to="/app/ask"
                        aria-label="Atlas"
                        className="grid size-10 place-items-center rounded-full border border-white/14 text-cream/70 hover:bg-white/[0.05]"
                      >
                        <Sparkles size={16} />
                      </Link>
                      <button
                        type="button"
                        onClick={() => void download(session.sessionId)}
                        disabled={downloading === session.sessionId}
                        className="inline-flex h-10 items-center gap-2 rounded-full border border-white/14 px-3.5 text-sm text-cream/70 hover:bg-white/[0.05] disabled:opacity-50"
                      >
                        {downloading === session.sessionId ? (
                          <LoaderCircle size={15} className="animate-spin" />
                        ) : (
                          <Download size={15} />
                        )}
                        {c.pdf}
                      </button>
                    </>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
