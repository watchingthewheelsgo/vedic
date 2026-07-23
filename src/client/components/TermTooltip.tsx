import { useState } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";
import type { TermEntry } from "../lib/terminology";

export function TermTooltip({ term, children }: { term: TermEntry; children: string }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <Popover onOpenChange={() => setExpanded(false)}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className="cursor-help border-b border-dotted border-gold/60 text-inherit decoration-transparent hover:border-gold hover:text-gold-dim focus-visible:outline-none focus-visible:border-gold"
        >
          {children}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-72 text-left" align="start">
        <div className="px-1 py-0.5">
          <div className="flex items-baseline justify-between gap-2">
            <span className="text-sm font-semibold text-gold">{term.term}</span>
            {term.sanskrit && <span className="text-[11px] text-cream/50">{term.sanskrit}</span>}
          </div>
          <p className="mt-1.5 text-[13px] leading-[1.7] text-cream/90">{term.short}</p>
          {term.detail && (
            <>
              {expanded ? (
                <p className="mt-1.5 border-t border-gold/15 pt-1.5 text-[12px] leading-[1.65] text-cream/70">
                  {term.detail}
                </p>
              ) : (
                <button
                  type="button"
                  onClick={() => setExpanded(true)}
                  className="mt-1.5 text-[11px] font-medium text-gold-dim hover:text-gold"
                >
                  查看技术细节 ▾
                </button>
              )}
            </>
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
}
