import type { ReactNode } from "react";

/** One compact header row: title, an optional single line of context, optional actions. */
export function PageHeader({
  title,
  note,
  action
}: {
  title: ReactNode;
  note?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
      <div className="min-w-0">
        <h1 className="font-display text-[34px] leading-[1.05] tracking-normal sm:text-[40px]">
          {title}
        </h1>
        {note && <p className="mt-1.5 max-w-2xl text-sm leading-6 text-cream/50">{note}</p>}
      </div>
      {action && <div className="flex shrink-0 items-center gap-2">{action}</div>}
    </header>
  );
}
