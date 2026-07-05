import { useEffect, useRef, useState } from "react";
import { Check, Globe2 } from "lucide-react";
import { useI18n } from "../i18n/provider";
import { LOCALES, localeNames, type LocaleCode } from "../i18n/messages";
import { cn } from "../lib/cn";

export function LanguageSwitcher({ align = "right" }: { align?: "left" | "right" }) {
  const { locale, setLocale } = useI18n();
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  function choose(nextLocale: LocaleCode) {
    setLocale(nextLocale);
    setOpen(false);
  }

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        aria-label="Change language"
        className="grid size-9 place-items-center rounded-full border border-gold/25 bg-cream-2 text-gold-dim transition hover:border-gold/60 hover:bg-gold/10 hover:text-gold focus:outline-none focus:ring-4 focus:ring-gold/15"
        onClick={() => setOpen((value) => !value)}
      >
        <Globe2 className="size-4" />
      </button>
      {open && (
        <div
          className={cn(
            "absolute top-11 z-[70] w-36 rounded-lg border border-gold/25 bg-cream p-1 shadow-[0_18px_48px_rgba(44,31,15,0.16)]",
            align === "right" ? "right-0" : "left-0"
          )}
        >
          {LOCALES.map((item) => {
            const selected = item === locale;
            return (
              <button
                type="button"
                key={item}
                className={cn(
                  "flex w-full items-center justify-between gap-2 rounded-md px-3 py-2 text-left text-sm transition",
                  selected ? "bg-gold text-white" : "text-body hover:bg-gold/10 hover:text-ink"
                )}
                onClick={() => choose(item)}
              >
                {localeNames[item]}
                {selected && <Check className="size-3.5" />}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
