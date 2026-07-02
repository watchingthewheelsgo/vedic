import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

export function Field({
  label,
  hint,
  error,
  icon,
  children,
  className
}: {
  label: string;
  hint?: string;
  error?: string;
  icon?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("mb-5", className)}>
      <label className="mb-2 flex items-center gap-2 text-[11px] uppercase tracking-[1.1px] text-muted">
        {icon ? <span className="text-gold-dim [&_svg]:size-4">{icon}</span> : null}
        <span>{label}</span>
      </label>
      {children}
      {error ? (
        <div className="mt-2 text-xs leading-relaxed text-red">{error}</div>
      ) : hint ? (
        <div className="mt-2 text-xs leading-relaxed text-muted">{hint}</div>
      ) : null}
    </div>
  );
}
