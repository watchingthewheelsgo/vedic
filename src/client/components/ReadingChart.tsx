import type { LocaleCode } from "../i18n/messages";
import type { ReadingChartData } from "../lib/reading-chart";

// South Indian layout: signs stay fixed, Pisces top-left, running clockwise.
const CELLS: { sign: number; row: number; col: number }[] = [
  { sign: 11, row: 1, col: 1 },
  { sign: 0, row: 1, col: 2 },
  { sign: 1, row: 1, col: 3 },
  { sign: 2, row: 1, col: 4 },
  { sign: 3, row: 2, col: 4 },
  { sign: 4, row: 3, col: 4 },
  { sign: 5, row: 4, col: 4 },
  { sign: 6, row: 4, col: 3 },
  { sign: 7, row: 4, col: 2 },
  { sign: 8, row: 4, col: 1 },
  { sign: 9, row: 3, col: 1 },
  { sign: 10, row: 2, col: 1 }
];

// U+FE0E asks for the text glyph, not a colored emoji.
const GLYPHS = ["♈", "♉", "♊", "♋", "♌", "♍", "♎", "♏", "♐", "♑", "♒", "♓"].map(
  (glyph) => `${glyph}\uFE0E`
);
const ORDER = ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"];

const copy: Record<
  LocaleCode,
  {
    title: string;
    note: string;
    signs: string[];
    planets: Record<string, string>;
    rising: [string, string];
    moon: [string, string];
    sun: [string, string];
    asc: string;
  }
> = {
  en: {
    title: "Your chart",
    note: "Vedic astrology uses the sidereal zodiac, so your signs here may differ from your Western ones.",
    signs: [
      "Aries",
      "Taurus",
      "Gemini",
      "Cancer",
      "Leo",
      "Virgo",
      "Libra",
      "Scorpio",
      "Sagittarius",
      "Capricorn",
      "Aquarius",
      "Pisces"
    ],
    planets: {
      Sun: "Su",
      Moon: "Mo",
      Mars: "Ma",
      Mercury: "Me",
      Jupiter: "Ju",
      Venus: "Ve",
      Saturn: "Sa",
      Rahu: "Ra",
      Ketu: "Ke"
    },
    rising: ["Rising sign", "How you meet the world"],
    moon: ["Moon", "Your inner weather"],
    sun: ["Sun", "What drives you"],
    asc: "Asc"
  },
  zh: {
    title: "你的命盘",
    note: "吠陀占星使用恒星黄道，所以这里的星座可能和你熟悉的西方星座不同。",
    signs: [
      "白羊",
      "金牛",
      "双子",
      "巨蟹",
      "狮子",
      "处女",
      "天秤",
      "天蝎",
      "射手",
      "摩羯",
      "水瓶",
      "双鱼"
    ],
    planets: {
      Sun: "日",
      Moon: "月",
      Mars: "火",
      Mercury: "水",
      Jupiter: "木",
      Venus: "金",
      Saturn: "土",
      Rahu: "罗",
      Ketu: "计"
    },
    rising: ["上升", "你面对世界的方式"],
    moon: ["月亮", "你内心的天气"],
    sun: ["太阳", "驱动你的力量"],
    asc: "升"
  },
  ja: {
    title: "あなたのチャート",
    note: "インド占星術はサイデリアル方式のため、西洋占星術の星座と異なることがあります。",
    signs: [
      "牡羊座",
      "牡牛座",
      "双子座",
      "蟹座",
      "獅子座",
      "乙女座",
      "天秤座",
      "蠍座",
      "射手座",
      "山羊座",
      "水瓶座",
      "魚座"
    ],
    planets: {
      Sun: "日",
      Moon: "月",
      Mars: "火",
      Mercury: "水",
      Jupiter: "木",
      Venus: "金",
      Saturn: "土",
      Rahu: "羅",
      Ketu: "計"
    },
    rising: ["アセンダント", "世界との向き合い方"],
    moon: ["月", "心の天気"],
    sun: ["太陽", "あなたを動かすもの"],
    asc: "Asc"
  }
};

export function ReadingChart({ chart, locale }: { chart: ReadingChartData; locale: LocaleCode }) {
  const c = copy[locale];
  const bySign = new Map<number, string[]>();
  for (const id of ORDER) {
    const pos = chart.placements.get(id);
    if (pos) bySign.set(pos.signIndex, [...(bySign.get(pos.signIndex) ?? []), c.planets[id]]);
  }
  const anchors = [
    { key: "rising", label: c.rising, sign: chart.lagna, extra: undefined },
    chart.moon && {
      key: "moon",
      label: c.moon,
      sign: chart.moon.signIndex,
      extra: chart.moon.nakshatra
    },
    chart.sun && { key: "sun", label: c.sun, sign: chart.sun.signIndex, extra: undefined }
  ].filter(Boolean) as {
    key: string;
    label: [string, string];
    sign: number;
    extra?: string;
  }[];

  return (
    <section
      aria-label={c.title}
      className="@container mb-12 overflow-hidden rounded-3xl border border-white/[0.08] bg-night-2"
    >
      <div className="grid gap-6 p-5 sm:p-7 @xl:grid-cols-[minmax(0,300px)_minmax(0,1fr)] @xl:items-center">
        <div
          className="mx-auto grid aspect-square w-full max-w-[300px] grid-cols-4 grid-rows-4 gap-px overflow-hidden rounded-2xl bg-white/[0.08]"
          role="img"
          aria-label={c.title}
        >
          {CELLS.map((cell, index) => {
            const isLagna = cell.sign === chart.lagna;
            const grahas = bySign.get(cell.sign) ?? [];
            return (
              <div
                key={cell.sign}
                className={`chart-cell relative flex flex-col items-center justify-center gap-0.5 p-1 ${isLagna ? "bg-gold/[0.16]" : "bg-night-2"}`}
                style={{
                  gridRow: cell.row,
                  gridColumn: cell.col,
                  animationDelay: `${index * 45}ms`
                }}
              >
                <span
                  className={`absolute left-1.5 top-1 text-[10px] ${isLagna ? "text-gold" : "text-cream/30"}`}
                >
                  {GLYPHS[cell.sign]}
                </span>
                {isLagna && (
                  <span className="text-[10px] font-semibold uppercase tracking-wide text-gold">
                    {c.asc}
                  </span>
                )}
                <span className="flex flex-wrap justify-center gap-x-1 text-[12px] font-medium leading-4 text-cream/90">
                  {grahas.map((graha) => (
                    <span key={graha}>{graha}</span>
                  ))}
                </span>
              </div>
            );
          })}
          <div
            className="flex flex-col items-center justify-center bg-night text-center"
            style={{ gridRow: "2 / span 2", gridColumn: "2 / span 2" }}
          >
            <span className="font-display text-3xl leading-none text-cream">D1</span>
            <span className="mt-1 text-[11px] text-cream/45">Rāśi</span>
          </div>
        </div>

        <div>
          <p className="eyebrow mb-4">{c.title}</p>
          <ul className="space-y-3">
            {anchors.map((anchor) => (
              <li key={anchor.key} className="flex items-baseline gap-3">
                <span className="w-7 shrink-0 text-center text-xl text-gold">
                  {GLYPHS[anchor.sign]}
                </span>
                <span className="min-w-0">
                  <span className="block font-display text-2xl leading-tight text-cream">
                    {c.signs[anchor.sign]}
                    {anchor.extra && <span className="text-cream/50"> · {anchor.extra}</span>}
                  </span>
                  <span className="text-[13px] text-cream/55">
                    {anchor.label[0]} · {anchor.label[1]}
                  </span>
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-5 text-xs leading-5 text-cream/40">{c.note}</p>
        </div>
      </div>
    </section>
  );
}
