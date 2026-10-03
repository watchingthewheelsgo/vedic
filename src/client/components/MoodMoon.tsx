import { useId } from "react";

/** Mood 1-5 drawn as a moon phase: new moon (heavy) to full moon (glowing). */
export function MoodMoon({ level, size = 28 }: { level: number; size?: number }) {
  const clip = useId();
  const lit = (Math.min(5, Math.max(1, level)) - 1) / 4;
  const r = 10;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      <defs>
        <clipPath id={clip}>
          <circle cx="12" cy="12" r={r} />
        </clipPath>
      </defs>
      <circle cx="12" cy="12" r={r} fill="currentColor" opacity={0.92} />
      <g clipPath={`url(#${clip})`}>
        <circle cx={12 + lit * 2 * r + (lit === 1 ? 4 : 0)} cy="12" r={r} fill="#0a0b10" />
      </g>
      <circle cx="12" cy="12" r={r} fill="none" stroke="currentColor" strokeOpacity={0.45} />
    </svg>
  );
}

export function MoodPicker({
  labels,
  value,
  onPick,
  disabled,
  legend
}: {
  labels: string[];
  value: number | null;
  onPick: (mood: number) => void;
  disabled?: boolean;
  legend: string;
}) {
  return (
    <fieldset disabled={disabled}>
      <legend className="sr-only">{legend}</legend>
      <div className="grid grid-cols-5 gap-1.5">
        {labels.map((label, i) => {
          const selected = value === i + 1;
          return (
            <button
              key={label}
              type="button"
              aria-pressed={selected}
              onClick={() => onPick(i + 1)}
              className={`press-feedback group flex min-h-[76px] flex-col items-center justify-center gap-1.5 rounded-2xl border transition-[background-color,border-color,color] duration-200 ${
                selected
                  ? "border-gold/60 bg-gold/[0.12] text-gold-light"
                  : "border-white/[0.08] bg-white/[0.02] text-cream/55 hover:border-white/20 hover:text-cream/85"
              }`}
            >
              <span
                className={`transition-transform duration-300 ${selected ? "scale-110" : "group-hover:scale-105"}`}
              >
                <MoodMoon level={i + 1} />
              </span>
              <span className="text-[11px] leading-none">{label}</span>
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
