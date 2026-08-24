import type { ReactNode } from "react";
import { CircleHelp } from "lucide-react";
import { cn } from "../../lib/cn";

export function Field({
  label,
  hint,
  error,
  icon,
  required = false,
  children,
  className,
  hintDisplay = "below"
}: {
  label: string;
  hint?: string;
  error?: string;
  icon?: ReactNode;
  required?: boolean;
  children: ReactNode;
  className?: string;
  hintDisplay?: "below" | "tooltip";
}) {
  return (
    <div className={cn("mb-5", className)}>
      {label ? (
        <div className="mb-2 flex items-center gap-2 text-[13px] font-medium text-muted">
          {icon ? <span className="text-cream/42 [&_svg]:size-4">{icon}</span> : null}
          <span className="leading-5">{label}</span>
          {required ? (
            <span aria-hidden="true" className="text-[13px] leading-none text-gold-light">
              *
            </span>
          ) : null}
          {hint && hintDisplay === "tooltip" ? <FieldHint text={hint} /> : null}
        </div>
      ) : null}
      {children}
      {error ? (
        <div className="mt-2 text-xs leading-relaxed text-red">{error}</div>
      ) : hint && hintDisplay === "below" ? (
        <div className="mt-2 text-xs leading-relaxed text-muted">{hint}</div>
      ) : null}
    </div>
  );
}

export function FieldHint({ text }: { text: string }) {
  return (
    <span className="group relative inline-flex normal-case tracking-normal">
      <span
        role="button"
        tabIndex={0}
        aria-label={text}
        className="grid size-5 place-items-center text-cream/30 outline-none transition hover:text-gold-light focus-visible:text-gold-light focus-visible:ring-2 focus-visible:ring-gold/30"
      >
        <CircleHelp className="size-3.5" />
      </span>
      <span
        role="tooltip"
        className="pointer-events-none invisible absolute left-1/2 top-full z-[70] mt-2 w-60 -translate-x-1/2 rounded-[8px] border border-white/10 bg-[#151312]/98 px-3 py-2 text-left text-xs font-normal leading-relaxed text-cream/72 opacity-0 shadow-[0_16px_40px_rgba(0,0,0,0.45)] backdrop-blur-xl transition group-hover:visible group-hover:opacity-100 group-focus-within:visible group-focus-within:opacity-100"
      >
        {text}
      </span>
    </span>
  );
}
