import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import type { LocaleCode } from "../i18n/messages";
import { dailySign, type SignTier } from "../lib/daily-sign";
import { guidanceText, type DailyGuidance } from "../lib/journal";

type TierCopy = { han: string; word: string; line: string };

const copy: Record<
  LocaleCode,
  {
    tap: string;
    chipDraw: string;
    chipToday: string;
    close: string;
    dialog: string;
    again: string;
    good: string;
    avoid: string;
    why: (pillar: string, master: string) => string;
    locked: string;
    tiers: Record<SignTier, TierCopy>;
  }
> = {
  en: {
    tap: "Tap to draw today's card",
    chipDraw: "Draw today's card",
    chipToday: "Today",
    close: "Close",
    dialog: "Today's card",
    again: "Tap to turn it over",
    good: "Good for",
    avoid: "Avoid",
    why: (pillar, master) => `Drawn from today's ${pillar} and your ${master} Day Master`,
    locked: "Your daily card is drawn from your own chart.",
    tiers: {
      radiant: {
        han: "大吉",
        word: "Radiant",
        line: "Doors open easily today. Start the thing you've been waiting on."
      },
      bright: { han: "吉", word: "Bright", line: "A good current runs through today. Lean in." },
      steady: { han: "平", word: "Steady", line: "An even day. Small, steady moves land best." },
      gentle: {
        han: "慎",
        word: "Go gently",
        line: "Friction is likely. Slow down, keep it simple, protect your energy."
      }
    }
  },
  zh: {
    tap: "轻点抽取今日之签",
    chipDraw: "抽取今日之签",
    chipToday: "今日",
    close: "关闭",
    dialog: "今日之签",
    again: "轻点翻回背面",
    good: "宜",
    avoid: "忌",
    why: (pillar, master) => `由今日 ${pillar} 与你的日主 ${master} 推出`,
    locked: "每日之签来自你自己的命盘。",
    tiers: {
      radiant: { han: "大吉", word: "上上签", line: "顺风顺水，适合开始一直想做的事。" },
      bright: { han: "吉", word: "上签", line: "今天气场不错，可以主动一点。" },
      steady: { han: "平", word: "中签", line: "平稳的一天，小步前进最稳妥。" },
      gentle: { han: "慎", word: "宜静", line: "今天易有摩擦，放慢节奏，照顾好自己。" }
    }
  },
  ja: {
    tap: "タップして今日のカードを引く",
    chipDraw: "今日のカードを引く",
    chipToday: "今日",
    close: "閉じる",
    dialog: "今日のカード",
    again: "タップで裏返す",
    good: "宜",
    avoid: "忌",
    why: (pillar, master) => `今日の${pillar}とあなたの日主${master}から`,
    locked: "毎日のカードはあなた自身のチャートから引かれます。",
    tiers: {
      radiant: {
        han: "大吉",
        word: "大吉",
        line: "物事が開けやすい日。温めていたことを始めましょう。"
      },
      bright: { han: "吉", word: "吉", line: "良い流れの日。一歩踏み出して。" },
      steady: { han: "平", word: "平", line: "穏やかな日。小さく着実に。" },
      gentle: {
        han: "慎",
        word: "慎",
        line: "摩擦が起きやすい日。ペースを落として、無理をせずに。"
      }
    }
  }
};

const tierStyle: Record<SignTier, { face: string; glow: string; spark: string; ink: string }> = {
  radiant: {
    face: "bg-[radial-gradient(circle_at_50%_30%,#ffd9a8_0%,#f4a259_45%,#9a5a24_100%)]",
    glow: "rgba(244,162,89,0.55)",
    spark: "#ffd9a8",
    ink: "text-[#2a1606]"
  },
  bright: {
    face: "bg-[radial-gradient(circle_at_50%_30%,#c9f5e4_0%,#6cd4b1_50%,#2c7a62_100%)]",
    glow: "rgba(108,212,177,0.45)",
    spark: "#c9f5e4",
    ink: "text-[#06261c]"
  },
  steady: {
    face: "bg-[radial-gradient(circle_at_50%_30%,#ffffff_0%,#e8e3d8_55%,#a9a397_100%)]",
    glow: "rgba(243,240,233,0.35)",
    spark: "#ffffff",
    ink: "text-[#1a1712]"
  },
  gentle: {
    face: "bg-[radial-gradient(circle_at_50%_30%,#d9d6f2_0%,#8f8bbd_55%,#3f3c62_100%)]",
    glow: "rgba(143,139,189,0.45)",
    spark: "#d9d6f2",
    ink: "text-[#14122a]"
  }
};

const SPARKS = Array.from({ length: 36 }, (_, i) => {
  const angle = (i / 36) * Math.PI * 2 + (i % 2 ? 0.14 : -0.09);
  const distance = 120 + ((i * 41) % 110);
  return {
    dx: Math.cos(angle) * distance,
    dy: Math.sin(angle) * distance * 1.15,
    size: 4 + (i % 5) * 1.4,
    delay: (i % 6) * 35
  };
});

function storageKey(day: string) {
  return `signatlas.card.${day}`;
}

function readDrawn(day: string) {
  try {
    return localStorage.getItem(storageKey(day)) === "1";
  } catch {
    return false;
  }
}

/** Today's card: one draw a day, flipped with a burst; the sign follows the day guidance. */
export function FortuneCard({
  day,
  guidance,
  fit,
  locale,
  locked,
  onDrawn,
  size = "regular"
}: {
  day: string;
  guidance: DailyGuidance | null;
  fit: "bright" | "steady" | "gentle" | "unknown";
  locale: LocaleCode;
  locked: boolean;
  onDrawn?: () => void;
  size?: "regular" | "large";
}) {
  const c = copy[locale];
  const large = size === "large";
  const width = large ? "max-w-[300px]" : "max-w-[240px]";
  const [flipped, setFlipped] = useState(() => readDrawn(day));
  const [burst, setBurst] = useState(0);
  const [anticipate, setAnticipate] = useState(false);
  const timers = useRef<number[]>([]);
  const sign = useMemo(() => (guidance ? dailySign(guidance, fit) : null), [guidance, fit]);

  useEffect(() => () => timers.current.forEach((timer) => window.clearTimeout(timer)), []);

  if (locked || !guidance || !sign) {
    return (
      <div className="mx-auto flex aspect-[11/16] w-full max-w-[240px] flex-col items-center justify-center gap-3 rounded-[22px] border border-dashed border-white/20 p-5 text-center">
        <CardEmblem dim />
        <p className="text-xs leading-5 text-cream/55">{c.locked}</p>
      </div>
    );
  }

  const tier = c.tiers[sign.tier];
  const style = tierStyle[sign.tier];
  const top = guidance.goodFor[0];
  const caution = guidance.avoid[0];

  function draw() {
    if (flipped) {
      setFlipped(false);
      return;
    }
    setAnticipate(true);
    timers.current.push(
      window.setTimeout(() => {
        setAnticipate(false);
        setFlipped(true);
        try {
          localStorage.setItem(storageKey(day), "1");
        } catch {
          // The card simply asks to be drawn again next visit.
        }
        onDrawn?.();
      }, 260),
      // Sparks fire as the face turns toward the viewer.
      window.setTimeout(() => setBurst((value) => value + 1), 560)
    );
  }

  return (
    <div className={`relative mx-auto w-full ${width}`}>
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10 rounded-[30px] blur-2xl transition-opacity duration-700"
        style={{ background: style.glow, opacity: flipped ? 0.9 : 0.25 }}
      />
      <button
        type="button"
        onClick={draw}
        aria-label={flipped ? `${tier.han} ${tier.word}. ${tier.line} ${c.again}` : c.tap}
        aria-pressed={flipped}
        className={`fortune-card group relative block aspect-[11/16] w-full [perspective:1200px] ${anticipate ? "fortune-anticipate" : flipped ? "" : "fortune-float"}`}
      >
        <span
          className="relative block size-full transition-transform duration-[900ms] ease-[cubic-bezier(0.2,0.8,0.2,1)] [transform-style:preserve-3d]"
          style={{ transform: flipped ? "rotateY(180deg)" : "rotateY(0deg)" }}
        >
          {/* Back */}
          <span className="absolute inset-0 flex flex-col items-center justify-between overflow-hidden rounded-[22px] border border-gold/45 bg-[linear-gradient(160deg,#1f2230_0%,#0d0e14_100%)] p-4 shadow-[0_24px_60px_rgba(0,0,0,0.55)] [backface-visibility:hidden]">
            <span className="absolute inset-[7px] rounded-[16px] border border-gold/20" />
            <span className="fortune-sheen absolute inset-0" />
            <span className="relative text-[10px] uppercase tracking-[0.3em] text-gold/70">
              Sign Atlas
            </span>
            <CardEmblem />
            <span className="relative text-[11px] leading-4 text-cream/60">{c.tap}</span>
          </span>
          {/* Face */}
          <span
            className={`absolute inset-0 flex flex-col items-center overflow-hidden rounded-[22px] p-4 text-center shadow-[0_24px_60px_rgba(0,0,0,0.55)] [backface-visibility:hidden] [transform:rotateY(180deg)] ${style.face} ${style.ink}`}
          >
            <span className="absolute inset-[7px] rounded-[16px] border border-black/15" />
            <span className="relative mt-1 text-[10px] uppercase tracking-[0.3em] opacity-60">
              {guidance.dayPillar}
            </span>
            <span
              className={`han relative font-bold leading-none ${large ? "mt-6 text-[92px]" : "mt-2 text-[58px]"}`}
            >
              {tier.han}
            </span>
            <span
              className={`relative mt-1 font-display italic ${large ? "text-[30px]" : "text-xl"}`}
            >
              {tier.word}
            </span>
            <span
              className={`relative opacity-80 ${large ? "mt-4 px-2 text-[15px] leading-[1.5]" : "mt-2 text-[11.5px] leading-[1.45]"}`}
            >
              {tier.line}
            </span>
            <span className="relative mt-auto w-full space-y-1 border-t border-black/15 pt-2 text-left text-[11px] leading-4">
              {top && (
                <span className="block truncate">
                  <b className="font-semibold">{c.good}</b> · {guidanceText(top, locale)}
                </span>
              )}
              {caution && (
                <span className="block truncate opacity-75">
                  <b className="font-semibold">{c.avoid}</b> · {guidanceText(caution, locale)}
                </span>
              )}
            </span>
          </span>
        </span>
      </button>

      {burst > 0 && (
        <span
          key={burst}
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 aspect-[11/16]"
        >
          <span
            className="fortune-bloom absolute left-1/2 top-1/2 size-[260px] rounded-full"
            style={{ background: `radial-gradient(circle, ${style.glow} 0%, transparent 65%)` }}
          />
          <span
            className="fortune-flash absolute inset-0 rounded-[22px]"
            style={{ background: style.spark }}
          />
          {sign.tier !== "gentle" && (
            <span
              className="fortune-ring absolute left-1/2 top-1/2 size-24 rounded-full border-2"
              style={{ borderColor: style.spark }}
            />
          )}
          {sign.tier === "radiant" && (
            <span
              className="fortune-ring fortune-ring-late absolute left-1/2 top-1/2 size-24 rounded-full border"
              style={{ borderColor: style.spark }}
            />
          )}
          {SPARKS.slice(0, sign.tier === "gentle" ? 14 : 36).map((spark, i) => (
            <span
              key={i}
              className="fortune-spark absolute left-1/2 top-1/2 rounded-full"
              style={
                {
                  width: spark.size,
                  height: spark.size,
                  background: style.spark,
                  boxShadow: `0 0 10px ${style.spark}`,
                  animationDelay: `${spark.delay}ms`,
                  "--dx": `${spark.dx}px`,
                  "--dy": `${spark.dy}px`
                } as CSSProperties
              }
            />
          ))}
        </span>
      )}

      <p className="mt-3 text-center text-[11px] leading-4 text-cream/40">
        {flipped ? c.why(guidance.dayPillar, guidance.facts.dayMaster) : "\u00a0"}
      </p>
    </div>
  );
}

function CardEmblem({ dim = false }: { dim?: boolean }) {
  return (
    <span className={`relative grid size-24 place-items-center ${dim ? "opacity-40" : ""}`}>
      <span className="fortune-orbit absolute inset-0 rounded-full border border-gold/50" />
      <span className="fortune-orbit-reverse absolute inset-3 rounded-full border border-jade/45" />
      <span className="absolute inset-[26px] rounded-full bg-gold/15" />
      <span className="size-2.5 rounded-full bg-cream shadow-[0_0_14px_#f3f0e9]" />
    </span>
  );
}

/**
 * Today's card lives behind a small glowing chip: tapping it opens the card as a floating
 * dialog where it is drawn with the burst; closing tucks it back into the chip, which then
 * shows the result and reopens the drawn card.
 */
export function DailyCardLauncher({
  day,
  guidance,
  fit,
  locale
}: {
  day: string;
  guidance: DailyGuidance;
  fit: "bright" | "steady" | "gentle" | "unknown";
  locale: LocaleCode;
}) {
  const c = copy[locale];
  const [open, setOpen] = useState(false);
  const [drawn, setDrawn] = useState(() => readDrawn(day));
  const closeButton = useRef<HTMLButtonElement>(null);
  const opener = useRef<HTMLButtonElement>(null);
  const sign = useMemo(() => dailySign(guidance, fit), [guidance, fit]);
  const tier = c.tiers[sign.tier];
  const style = tierStyle[sign.tier];

  // The first visit of the day offers the card once; closing it leaves the chip as the reminder.
  useEffect(() => {
    if (drawn) return;
    const key = `signatlas.card.offered.${day}`;
    try {
      if (localStorage.getItem(key)) return;
      localStorage.setItem(key, "1");
    } catch {
      return;
    }
    const timer = window.setTimeout(() => setOpen(true), 700);
    return () => window.clearTimeout(timer);
  }, [day, drawn]);

  useEffect(() => {
    if (!open) return;
    const openerNode = opener.current;
    closeButton.current?.focus({ preventScroll: true });
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      openerNode?.focus({ preventScroll: true });
    };
  }, [open]);

  return (
    <>
      <button
        ref={opener}
        type="button"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        className={`press-feedback group relative inline-flex h-11 items-center gap-2.5 rounded-full border pl-1.5 pr-4 text-sm transition-colors ${
          drawn
            ? "border-white/12 bg-white/[0.03] text-cream/80 hover:border-white/25"
            : "fortune-chip-glow border-gold/45 bg-gold/[0.08] text-gold-light hover:bg-gold/[0.14]"
        }`}
      >
        <span
          aria-hidden
          className={`relative grid h-8 w-6 place-items-center rounded-[6px] text-[13px] font-bold ${drawn ? `${style.face} ${style.ink}` : "border border-gold/50 bg-[linear-gradient(160deg,#1f2230_0%,#0d0e14_100%)]"}`}
        >
          {drawn ? (
            <span className="han">{tier.han.slice(-1)}</span>
          ) : (
            <span className="size-1.5 rounded-full bg-cream shadow-[0_0_8px_#f3f0e9]" />
          )}
        </span>
        {drawn ? (
          <span>
            {c.chipToday} · <span className="han">{tier.han}</span>{" "}
            <span className="font-display italic">{tier.word}</span>
          </span>
        ) : (
          <span>{c.chipDraw}</span>
        )}
        {!drawn && (
          <span
            aria-hidden
            className="fortune-twinkle absolute -right-0.5 -top-0.5 size-2 rounded-full bg-gold-light"
          />
        )}
      </button>

      {open &&
        createPortal(
          <div
            role="dialog"
            aria-modal="true"
            aria-label={c.dialog}
            className="fixed inset-0 z-[80] grid place-items-center p-6"
          >
            <button
              type="button"
              tabIndex={-1}
              aria-label={c.close}
              onClick={() => setOpen(false)}
              className="fortune-backdrop absolute inset-0 cursor-default bg-[#05060a]/80 backdrop-blur-md"
            />
            <div className="fortune-dialog relative w-full max-w-[300px]">
              <button
                ref={closeButton}
                type="button"
                onClick={() => setOpen(false)}
                aria-label={c.close}
                className="absolute -right-2 -top-14 grid size-11 place-items-center rounded-full border border-white/15 bg-white/[0.06] text-cream/80 transition-colors hover:bg-white/[0.12] hover:text-cream"
              >
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  aria-hidden="true"
                >
                  <path d="M6 6l12 12M18 6L6 18" />
                </svg>
              </button>
              <FortuneCard
                day={day}
                guidance={guidance}
                fit={fit}
                locale={locale}
                locked={false}
                onDrawn={() => setDrawn(true)}
                size="large"
              />
            </div>
          </div>,
          document.body
        )}
    </>
  );
}
