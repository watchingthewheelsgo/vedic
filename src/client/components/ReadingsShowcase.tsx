import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { useI18n } from "../i18n/provider";
import type { LocaleCode } from "../i18n/messages";
import { useAtlas } from "./Atlas";

type Tradition = "vedic" | "bazi" | "tarot";

const copy: Record<
  LocaleCode,
  {
    title: string;
    note: string;
    names: Record<Tradition, string>;
    native: Record<Tradition, string>;
    engine: Record<Tradition, string[]>;
    open: string;
    start: Record<Tradition, string>;
    ready: string;
    soon: string;
  }
> = {
  en: {
    title: "Your readings",
    note: "Calculated first, then interpreted. Every finding traces back to its chart facts.",
    names: { vedic: "Vedic astrology", bazi: "BaZi", tarot: "Tarot" },
    native: { vedic: "Jyotiṣa", bazi: "八字", tarot: "XXII" },
    engine: {
      vedic: ["Swiss Ephemeris", "D1–D60 divisional charts", "Vimshottari dashas", "Shadbala"],
      bazi: ["Four Pillars", "Ten Gods", "Luck pillars", "滴天髓 · 子平真诠 · 穷通宝鉴"],
      tarot: ["Daily draw", "Linked to your journal"]
    },
    open: "Open",
    start: { vedic: "Get my reading", bazi: "Calculate my chart", tarot: "" },
    ready: "Ready",
    soon: "Coming soon"
  },
  zh: {
    title: "你的解读",
    note: "先精确计算，再解读。每条结论都能追溯到盘面事实。",
    names: { vedic: "吠陀占星", bazi: "八字命理", tarot: "塔罗" },
    native: { vedic: "Jyotiṣa", bazi: "四柱", tarot: "XXII" },
    engine: {
      vedic: ["Swiss Ephemeris 星历", "D1–D60 分盘", "Vimshottari 大运", "六力 Shadbala"],
      bazi: ["四柱排盘", "十神", "大运", "滴天髓 · 子平真诠 · 穷通宝鉴"],
      tarot: ["每日一抽", "与日记相连"]
    },
    open: "打开",
    start: { vedic: "获取我的解读", bazi: "排出我的八字", tarot: "" },
    ready: "已完成",
    soon: "即将推出"
  },
  ja: {
    title: "あなたのリーディング",
    note: "まず正確に計算し、それから解釈。すべての結論がチャートの事実にたどれます。",
    names: { vedic: "インド占星術", bazi: "八字", tarot: "タロット" },
    native: { vedic: "Jyotiṣa", bazi: "四柱", tarot: "XXII" },
    engine: {
      vedic: ["Swiss Ephemeris", "D1–D60 分割図", "ヴィムショッタリ・ダシャー", "シャドバラ"],
      bazi: ["四柱", "十神", "大運", "滴天髄 · 子平真詮 · 窮通宝鑑"],
      tarot: ["毎日の一枚", "日記と連動"]
    },
    open: "開く",
    start: { vedic: "リーディングを受ける", bazi: "八字を出す", tarot: "" },
    ready: "完了",
    soon: "近日公開"
  }
};

const accent: Record<Tradition, { dot: string; ring: string; glow: string }> = {
  vedic: {
    dot: "bg-gold",
    ring: "hover:border-gold/45",
    glow: "bg-[radial-gradient(circle_at_85%_0%,rgba(244,162,89,0.16),transparent_55%)]"
  },
  bazi: {
    dot: "bg-jade",
    ring: "hover:border-jade/45",
    glow: "bg-[radial-gradient(circle_at_85%_0%,rgba(108,212,177,0.14),transparent_55%)]"
  },
  tarot: {
    dot: "bg-white/30",
    ring: "",
    glow: "bg-[radial-gradient(circle_at_85%_0%,rgba(143,139,189,0.14),transparent_55%)]"
  }
};

/** The three traditions and the engines behind them, with each one's next step. */
export function ReadingsShowcase() {
  const { locale } = useI18n();
  const c = copy[locale];
  const { charts } = useAtlas();
  const latest = (kind: "vedic" | "bazi") =>
    charts.find((chart) => chart.kind === kind && chart.completed) ??
    charts.find((chart) => chart.kind === kind);

  const target = (kind: Tradition) => {
    if (kind === "tarot") return null;
    const chart = latest(kind);
    if (chart && (kind === "bazi" || chart.completed)) {
      return {
        to: `/app/charts/${encodeURIComponent(chart.sessionId)}`,
        label: c.open,
        ready: true
      };
    }
    return {
      to:
        kind === "bazi"
          ? "/app/charts/bazi"
          : chart
            ? `/app/charts/${encodeURIComponent(chart.sessionId)}`
            : "/app/charts/new",
      label: c.start[kind],
      ready: false
    };
  };

  return (
    <section aria-labelledby="readings-title">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 id="readings-title" className="font-display text-2xl">
          {c.title}
        </h2>
        <p className="text-xs text-cream/45">{c.note}</p>
      </div>
      <div className="grid gap-3 @3xl:grid-cols-3">
        {(["vedic", "bazi", "tarot"] as const).map((kind) => {
          const next = target(kind);
          const body = (
            <>
              <span
                aria-hidden
                className={`pointer-events-none absolute inset-0 ${accent[kind].glow}`}
              />
              <span className="relative flex items-start justify-between gap-3">
                <span>
                  <span className="flex items-center gap-2 text-[15px] text-cream">
                    <span className={`size-2 rounded-full ${accent[kind].dot}`} />
                    {c.names[kind]}
                  </span>
                  <span className="han mt-1 block font-display text-3xl leading-none text-cream/85">
                    {c.native[kind]}
                  </span>
                </span>
                {next?.ready && (
                  <span className="rounded-full bg-paper px-2.5 py-1 text-[11px] text-[#16130e]">
                    {c.ready}
                  </span>
                )}
                {!next && (
                  <span className="rounded-full border border-dashed border-white/25 px-2.5 py-1 text-[11px] text-cream/55">
                    {c.soon}
                  </span>
                )}
              </span>
              <span className="relative mt-4 flex flex-wrap gap-1.5">
                {c.engine[kind].map((item) => (
                  <span
                    key={item}
                    className="rounded-full bg-white/[0.05] px-2.5 py-1 text-[11px] text-cream/60"
                  >
                    {item}
                  </span>
                ))}
              </span>
              {next && (
                <span className="relative mt-5 inline-flex items-center gap-1.5 text-sm text-cream">
                  {next.label}
                  <ArrowRight
                    size={14}
                    className="transition-transform group-hover:translate-x-0.5"
                  />
                </span>
              )}
            </>
          );
          const className = `group relative flex min-h-[188px] flex-col overflow-hidden rounded-3xl border border-white/[0.08] bg-night-2 p-5 transition-colors ${accent[kind].ring}`;
          return next ? (
            <Link key={kind} to={next.to} className={`press-feedback ${className}`}>
              {body}
            </Link>
          ) : (
            <div key={kind} className={`${className} opacity-80`}>
              {body}
            </div>
          );
        })}
      </div>
    </section>
  );
}
