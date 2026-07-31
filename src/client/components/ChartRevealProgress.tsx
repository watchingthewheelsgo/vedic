import { useEffect, useState } from "react";
import {
  User,
  Coins,
  Users,
  Home,
  Sparkles,
  ShieldAlert,
  Heart,
  Flame,
  Compass,
  Landmark,
  TrendingUp,
  Wind,
  type LucideIcon
} from "lucide-react";
import type {
  ChartRevealCoordinates,
  ChartRevealState,
  PlanetKey
} from "../lib/chartRevealMapping";

/**
 * Pure presentational component. Takes a single ChartRevealState — produced
 * either by lib/chartRevealMapping's deriveChartRevealState(realPipelineData)
 * or, for this prototype/demo route, by cycling DEMO_STATES below. Both
 * paths converge on the same shape so swapping demo -> real data later is a
 * prop change, not a rewrite.
 */

const PLANET_GLYPH: Record<PlanetKey, string> = {
  Sun: "☉",
  Moon: "☽",
  Mars: "♂",
  Mercury: "☿",
  Jupiter: "♃",
  Venus: "♀",
  Saturn: "♄",
  Rahu: "☊",
  Ketu: "☋"
};

// Fixed demo layout — 9 grahas placed around the wheel. Real angles come
// from the actual chart once this is wired to Chart Record facts.
const DEMO_PLANET_ANGLES: Record<PlanetKey, number> = {
  Sun: 15,
  Moon: 55,
  Mars: 95,
  Mercury: 130,
  Jupiter: 175,
  Venus: 230,
  Saturn: 275,
  Rahu: 320,
  Ketu: 140
};

const HOUSE_ICON: LucideIcon[] = [
  User, // 1 self
  Coins, // 2 wealth
  Users, // 3 siblings
  Home, // 4 home
  Sparkles, // 5 creativity
  ShieldAlert, // 6 health/competition
  Heart, // 7 partnership
  Flame, // 8 transformation
  Compass, // 9 fortune
  Landmark, // 10 career
  TrendingUp, // 11 income
  Wind // 12 release
];

const DASHA_YEARS: Record<PlanetKey, number> = {
  Ketu: 7,
  Venus: 20,
  Sun: 6,
  Moon: 10,
  Mars: 7,
  Rahu: 18,
  Jupiter: 16,
  Saturn: 19,
  Mercury: 17
};
const DASHA_ORDER: PlanetKey[] = [
  "Ketu",
  "Venus",
  "Sun",
  "Moon",
  "Mars",
  "Rahu",
  "Jupiter",
  "Saturn",
  "Mercury"
];

// Fixed fake progression for the /dev/chart-reveal preview route. Mirrors
// the shape deriveChartRevealState() produces from real pipeline data.
const DEMO_STATES: ChartRevealState[] = [
  {
    title: "确定上升点与行星落位",
    caption: "正在计算你的上升点和9颗行星的位置——这是你星盘的基础骨架。",
    focus: { kind: "lagna" },
    lagnaRevealed: true,
    planetsRevealed: false,
    housesCompleted: [],
    progressLabel: "1/48"
  },
  {
    title: "评估Moon的信号",
    caption: "正在评估月亮的力量——这关系到你的情绪稳定度和直觉。",
    focus: { kind: "planet", planet: "Moon" },
    lagnaRevealed: true,
    planetsRevealed: true,
    housesCompleted: [],
    progressLabel: "12/48"
  },
  {
    title: "评估Jupiter的信号",
    caption: "正在评估木星的力量——这决定了你智慧和好运信号有多「响」。",
    focus: { kind: "planet", planet: "Jupiter" },
    lagnaRevealed: true,
    planetsRevealed: true,
    housesCompleted: [],
    progressLabel: "15/48"
  },
  {
    title: "九分盘深度审计",
    caption: "正在核对你的九分盘——这是检验命盘承诺能不能兑现的关键一层。",
    focus: { kind: "d9" },
    lagnaRevealed: true,
    planetsRevealed: true,
    housesCompleted: [],
    progressLabel: "22/48"
  },
  {
    title: "诊断第10宫",
    caption: "正在诊断第10宫（事业）：你的事业主星落在哪，决定了你的职场生态位。",
    focus: { kind: "house", house: 10 },
    lagnaRevealed: true,
    planetsRevealed: true,
    housesCompleted: [1, 2, 3, 4, 5, 6, 7, 8, 9],
    progressLabel: "34/48"
  },
  {
    title: "诊断第7宫",
    caption: "正在诊断第7宫（婚姻/合作）：这个宫位的状态决定了关系中的模式。",
    focus: { kind: "house", house: 7 },
    lagnaRevealed: true,
    planetsRevealed: true,
    housesCompleted: [1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12],
    progressLabel: "38/48"
  },
  {
    title: "合成大运时间线",
    caption: "正在合成你的大运时间线——9颗行星依次「当家」，决定了什么时候轮到谁的能量登场。",
    focus: { kind: "dasha" },
    lagnaRevealed: true,
    planetsRevealed: true,
    housesCompleted: Array.from({ length: 12 }, (_, i) => i + 1),
    progressLabel: "40/48"
  },
  {
    title: "十大人生板块合成",
    caption: "正在把前面所有层次的证据，合成到事业、感情、财富等十个具体人生板块。",
    focus: { kind: "synthesis" },
    lagnaRevealed: true,
    planetsRevealed: true,
    housesCompleted: Array.from({ length: 12 }, (_, i) => i + 1),
    progressLabel: "46/48"
  }
];

export function ChartRevealProgress({
  state,
  coordinates,
  demo = false,
  demoIntervalMs = 2600
}: {
  /** Real usage: pass deriveChartRevealState(pipelineData) here. */
  state?: ChartRevealState;
  /** Real chart coordinates from chart_record.json. */
  coordinates?: ChartRevealCoordinates | null;
  /** Preview usage: cycle through DEMO_STATES instead of using `state`. */
  demo?: boolean;
  demoIntervalMs?: number;
}) {
  const [demoIndex, setDemoIndex] = useState(0);

  useEffect(() => {
    if (!demo) return;
    const id = window.setInterval(() => {
      setDemoIndex((prev) => (prev + 1) % DEMO_STATES.length);
    }, demoIntervalMs);
    return () => window.clearInterval(id);
  }, [demo, demoIntervalMs]);

  const current = demo ? DEMO_STATES[demoIndex] : state;
  if (!current) return null;

  const focusHouse = current.focus.kind === "house" ? current.focus.house : null;
  const focusPlanet = current.focus.kind === "planet" ? current.focus.planet : null;
  const dashaActive = current.focus.kind === "dasha";
  const d9Active = current.focus.kind === "d9";
  const synthesisActive = current.focus.kind === "synthesis";
  const housesCompleted = new Set(current.housesCompleted);
  const lagnaLongitude = coordinates?.lagnaLongitude ?? 0;
  const planetAngles = demo
    ? DEMO_PLANET_ANGLES
    : relativePlanetAngles(coordinates?.planetLongitudes, lagnaLongitude);

  return (
    <div className="flex flex-col items-center gap-6">
      <div className="relative h-[380px] w-[380px] shrink-0 sm:h-[420px] sm:w-[420px]">
        <svg viewBox="0 0 400 400" className="h-full w-full">
          <defs>
            <radialGradient id="crp-glow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="rgba(201,169,110,0.35)" />
              <stop offset="100%" stopColor="rgba(201,169,110,0)" />
            </radialGradient>
          </defs>

          {/* Outer Dasha ring — 9 arcs proportional to Vimshottari years */}
          <g
            className={dashaActive ? "opacity-100" : "opacity-35"}
            style={{ transition: "opacity 700ms ease" }}
          >
            {dashaArcs().map((arc) => (
              <path
                key={arc.planet}
                d={arc.path}
                fill="none"
                stroke={
                  dashaActive ? "var(--color-gold, #c9a96e)" : "var(--color-gold-dim, #9a7a4a)"
                }
                strokeWidth={dashaActive && arc.planet === "Jupiter" ? 8 : 5}
                strokeLinecap="round"
                style={{ transition: "stroke 700ms ease, stroke-width 700ms ease" }}
              />
            ))}
          </g>

          {/* 12 house slices — bright glow while actively diagnosed, dim gold
              fill once done (stays lit), transparent if not yet reached. */}
          {houseSlices().map((slice) => {
            const active = focusHouse === slice.house;
            const done = housesCompleted.has(slice.house);
            const fill = active
              ? "url(#crp-glow)"
              : done
                ? "rgba(201,169,110,0.1)"
                : "rgba(240,232,216,0.03)";
            const stroke = active
              ? "rgba(201,169,110,0.85)"
              : done
                ? "rgba(201,169,110,0.4)"
                : "rgba(201,169,110,0.18)";
            return (
              <path
                key={slice.house}
                d={slice.path}
                fill={fill}
                stroke={stroke}
                strokeWidth={active ? 1.6 : 1}
                style={{ transition: "fill 600ms ease, stroke 600ms ease" }}
              />
            );
          })}

          {/* House icons */}
          {houseSlices().map((slice) => {
            const Icon = HOUSE_ICON[slice.house - 1];
            const active = focusHouse === slice.house;
            const done = housesCompleted.has(slice.house);
            return (
              <foreignObject
                key={`icon-${slice.house}`}
                x={slice.iconPoint.x - 11}
                y={slice.iconPoint.y - 11}
                width={22}
                height={22}
              >
                <div
                  className={active ? "text-gold" : done ? "text-gold-dim" : "text-cream/30"}
                  style={{ transition: "color 600ms ease" }}
                >
                  <Icon size={18} strokeWidth={active ? 2.25 : 1.5} />
                </div>
              </foreignObject>
            );
          })}
          {houseSlices().map((slice) => {
            const active = focusHouse === slice.house;
            const done = housesCompleted.has(slice.house);
            return (
              <text
                key={`num-${slice.house}`}
                x={slice.numberPoint.x}
                y={slice.numberPoint.y}
                textAnchor="middle"
                className={active ? "fill-gold" : done ? "fill-gold-dim" : "fill-cream/25"}
                style={{ fontSize: 9, transition: "fill 600ms ease" }}
              >
                {slice.house}
              </text>
            );
          })}

          {/* Planets — outer band, closer to the rim than the house icons, with a
              chip backdrop so an active planet reads as its own marker, not
              a highlighted house icon. Revealed once chart_facts completes. */}
          {current.planetsRevealed &&
            (Object.keys(planetAngles) as PlanetKey[]).map((planet) => {
              const angle = planetAngles[planet];
              if (angle == null) return null;
              const point = polarToCartesian(200, 200, 146, angle);
              const active = focusPlanet === planet;
              return (
                <g key={planet}>
                  {active && (
                    <circle
                      cx={point.x}
                      cy={point.y}
                      r={14}
                      fill="rgba(16,12,22,0.9)"
                      stroke="rgba(237,217,163,0.9)"
                      strokeWidth={1.4}
                    />
                  )}
                  <text
                    x={point.x}
                    y={point.y}
                    textAnchor="middle"
                    dominantBaseline="central"
                    className={active ? "fill-gold-light" : "fill-cream/50"}
                    style={{
                      fontSize: active ? 17 : 13,
                      transition: "font-size 500ms ease, fill 500ms ease",
                      filter: active ? "drop-shadow(0 0 5px rgba(237,217,163,0.75))" : "none"
                    }}
                  >
                    {PLANET_GLYPH[planet]}
                  </text>
                </g>
              );
            })}

          {/* Lagna marker */}
          <g
            style={{ transition: "opacity 700ms ease" }}
            className={current.lagnaRevealed ? "opacity-100" : "opacity-0"}
          >
            <circle cx={200} cy={38} r={5} fill="var(--color-gold-light,#edd9a3)" />
            <text
              x={200}
              y={22}
              textAnchor="middle"
              className="fill-gold-light"
              style={{ fontSize: 10, letterSpacing: 1 }}
            >
              LAGNA
            </text>
          </g>

          {/* D9 overlay ring — a second, smaller wheel appearing during the
              Navamsha audit stage, representing the "soul layer" check. */}
          <circle
            cx={200}
            cy={200}
            r={40}
            fill="none"
            stroke="rgba(237,217,163,0.85)"
            strokeDasharray="4 3"
            strokeWidth={1.3}
            style={{ transition: "opacity 700ms ease" }}
            className={d9Active ? "opacity-100" : "opacity-0"}
          />
          {d9Active && (
            <text
              x={200}
              y={204}
              textAnchor="middle"
              className="fill-gold-light"
              style={{ fontSize: 9 }}
            >
              D9
            </text>
          )}

          {/* Center synthesis glow */}
          <circle
            cx={200}
            cy={200}
            r={54}
            fill={synthesisActive ? "url(#crp-glow)" : "rgba(240,232,216,0.02)"}
            stroke={synthesisActive ? "rgba(237,217,163,0.9)" : "rgba(201,169,110,0.2)"}
            strokeWidth={synthesisActive ? 1.8 : 1}
            style={{ transition: "fill 700ms ease, stroke 700ms ease, stroke-width 700ms ease" }}
          />
        </svg>
      </div>

      <div className="w-full max-w-[420px] rounded-lg border border-gold/25 bg-[rgba(16,12,22,0.72)] px-5 py-4 text-center backdrop-blur-xl">
        <div className="mb-1 text-[10px] uppercase tracking-[2px] text-gold">
          {current.progressLabel}
        </div>
        <div className="mb-1.5 text-sm font-semibold text-cream">{current.title}</div>
        <p className="text-[13px] leading-[1.7] text-cream/70">{current.caption}</p>
      </div>
    </div>
  );
}

function relativePlanetAngles(
  longitudes: Partial<Record<PlanetKey, number>> | undefined,
  lagnaLongitude: number
) {
  const result: Partial<Record<PlanetKey, number>> = {};
  if (!longitudes) return result;
  for (const planet of Object.keys(longitudes) as PlanetKey[]) {
    const longitude = longitudes[planet];
    if (longitude == null) continue;
    result[planet] = (longitude - lagnaLongitude + 360) % 360;
  }
  return result;
}

function polarToCartesian(cx: number, cy: number, r: number, angleDeg: number) {
  const rad = ((angleDeg - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function houseSlices() {
  const slices: {
    house: number;
    path: string;
    iconPoint: { x: number; y: number };
    numberPoint: { x: number; y: number };
  }[] = [];
  const cx = 200;
  const cy = 200;
  const outerR = 165;
  const innerR = 68;
  for (let house = 1; house <= 12; house++) {
    const startAngle = (house - 1) * 30;
    const endAngle = house * 30;
    const p1 = polarToCartesian(cx, cy, outerR, startAngle);
    const p2 = polarToCartesian(cx, cy, outerR, endAngle);
    const p3 = polarToCartesian(cx, cy, innerR, endAngle);
    const p4 = polarToCartesian(cx, cy, innerR, startAngle);
    const path = [
      `M ${p1.x} ${p1.y}`,
      `A ${outerR} ${outerR} 0 0 1 ${p2.x} ${p2.y}`,
      `L ${p3.x} ${p3.y}`,
      `A ${innerR} ${innerR} 0 0 0 ${p4.x} ${p4.y}`,
      "Z"
    ].join(" ");
    const midAngle = startAngle + 15;
    slices.push({
      house,
      path,
      iconPoint: polarToCartesian(cx, cy, innerR + 22, midAngle),
      numberPoint: polarToCartesian(cx, cy, innerR - 10, midAngle)
    });
  }
  return slices;
}

function dashaArcs() {
  const cx = 200;
  const cy = 200;
  const r = 182;
  let angle = 0;
  const arcs: { planet: PlanetKey; path: string }[] = [];
  for (const planet of DASHA_ORDER) {
    const span = (DASHA_YEARS[planet] / 120) * 360 - 3;
    const start = angle + 1.5;
    const end = start + span;
    const p1 = polarToCartesian(cx, cy, r, start);
    const p2 = polarToCartesian(cx, cy, r, end);
    const largeArc = span > 180 ? 1 : 0;
    arcs.push({
      planet,
      path: `M ${p1.x} ${p1.y} A ${r} ${r} 0 ${largeArc} 1 ${p2.x} ${p2.y}`
    });
    angle += (DASHA_YEARS[planet] / 120) * 360;
  }
  return arcs;
}
