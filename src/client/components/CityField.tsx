import { useEffect, useId, useRef, useState } from "react";
import { LoaderCircle, MapPin } from "lucide-react";
import { api } from "../api";
import type { LocaleCode } from "../i18n/messages";
import type { PlaceOption } from "../../shared/domain";

const CJK = /[㐀-鿿]/;

/**
 * One search box for a birth city (no country / province steps, no coordinates). Chinese
 * names search the China catalog, other text the world catalog; the picked option's
 * birthPlace is what the backend resolves.
 */
export function CityField({
  id,
  label,
  placeholder,
  emptyText,
  locale,
  value,
  error,
  onChange
}: {
  id: string;
  label: string;
  placeholder: string;
  emptyText: string;
  locale: LocaleCode;
  value: { place: string; label: string } | null;
  error?: string;
  onChange: (value: { place: string; label: string } | null) => void;
}) {
  const listId = useId();
  const [query, setQuery] = useState(value?.label ?? "");
  const [options, setOptions] = useState<PlaceOption[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [active, setActive] = useState(0);
  const blurTimer = useRef<number | null>(null);

  useEffect(() => {
    const text = query.trim();
    if (!open || text.length < (CJK.test(text) ? 1 : 2) || text === value?.label) {
      setOptions([]);
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setLoading(true);
      try {
        const searches = [
          CJK.test(text)
            ? api.searchPlaces(
                { level: "city", q: text, country: "China", locale, limit: 6 },
                controller.signal
              )
            : null,
          api.searchPlaces({ level: "city", q: text, locale, limit: 6 }, controller.signal)
        ];
        const results = await Promise.all(
          searches.map((search) => (search ? search.catch(() => null) : null))
        );
        const seen = new Set<string>();
        const merged = results
          .flatMap((result) => result?.options ?? [])
          .filter((option) => {
            const key = option.birthPlace ?? option.value;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
          })
          .slice(0, 8);
        setOptions(merged);
        setActive(0);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, 220);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [query, open, locale, value?.label]);

  function pick(option: PlaceOption) {
    const display = option.meta ? `${option.label} · ${option.meta}` : option.label;
    // A readable name plus resolved coordinates, the same shape the Vedic flow stores, so
    // every screen can show the city and the place picker can reopen it.
    const name = option.meta ? `${option.label}, ${option.meta}` : option.label;
    const place =
      typeof option.latitude === "number" && typeof option.longitude === "number"
        ? `${name} | lat=${option.latitude}, lon=${option.longitude}${option.timezone ? `, tz=${option.timezone}` : ""}, coord=WGS84`
        : (option.birthPlace ?? option.value);
    onChange({ place, label: display });
    setQuery(display);
    setOpen(false);
  }

  const expanded = open && (options.length > 0 || (!loading && query.trim().length > 1));
  return (
    <div className="relative">
      <label htmlFor={id} className="mb-2 block text-sm text-cream/75">
        {label}
      </label>
      <div
        className={`flex h-12 items-center gap-2 rounded-2xl border bg-white/[0.035] px-4 transition-colors focus-within:border-gold/70 ${error ? "border-red/70" : "border-white/12"}`}
      >
        <MapPin size={16} className="shrink-0 text-cream/40" />
        <input
          id={id}
          role="combobox"
          aria-expanded={expanded}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-invalid={Boolean(error)}
          autoComplete="off"
          value={query}
          placeholder={placeholder}
          onFocus={() => setOpen(true)}
          onBlur={() => {
            blurTimer.current = window.setTimeout(() => setOpen(false), 150);
          }}
          onChange={(event) => {
            setQuery(event.target.value);
            setOpen(true);
            if (value) onChange(null);
          }}
          onKeyDown={(event) => {
            if (!options.length) return;
            if (event.key === "ArrowDown") {
              event.preventDefault();
              setActive((index) => (index + 1) % options.length);
            } else if (event.key === "ArrowUp") {
              event.preventDefault();
              setActive((index) => (index - 1 + options.length) % options.length);
            } else if (event.key === "Enter") {
              event.preventDefault();
              pick(options[active]);
            } else if (event.key === "Escape") {
              setOpen(false);
            }
          }}
          className="min-w-0 flex-1 bg-transparent text-base text-cream outline-none placeholder:text-cream/30"
        />
        {loading && <LoaderCircle size={15} className="shrink-0 animate-spin text-cream/40" />}
      </div>
      {error && <p className="mt-1.5 text-xs text-[#ffb5a4]">{error}</p>}
      {expanded && (
        <ul
          id={listId}
          role="listbox"
          className="absolute inset-x-0 top-full z-10 mt-2 max-h-72 overflow-y-auto rounded-2xl border border-white/10 bg-night-3 p-1.5 shadow-[0_20px_60px_rgba(0,0,0,0.5)]"
        >
          {options.length === 0 && (
            <li className="px-3 py-2.5 text-sm text-cream/50">{emptyText}</li>
          )}
          {options.map((option, index) => (
            <li key={option.id} role="option" aria-selected={index === active}>
              <button
                type="button"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => pick(option)}
                onMouseEnter={() => setActive(index)}
                className={`flex w-full items-baseline justify-between gap-3 rounded-xl px-3 py-2.5 text-left text-sm ${index === active ? "bg-white/[0.07] text-cream" : "text-cream/75"}`}
              >
                <span className="truncate">{option.label}</span>
                {option.meta && (
                  <span className="shrink-0 text-xs text-cream/45">{option.meta}</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
