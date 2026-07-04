import { useEffect, useState } from "react";
import { LoaderCircle, MapPin, Search } from "lucide-react";
import { api } from "../api";
import { cn } from "../lib/cn";
import type { PlaceOption } from "../../shared/domain";
import { Field } from "./ui/field";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";

const isCoord = (s: string) => /lat\s*=/.test(s);

// Single-field city autocomplete: type a city, then pick
// "City, Region, Country" from the async place API.
export function PlacePicker({
  value,
  onChange,
  error
}: {
  value: string;
  onChange: (value: string) => void;
  error?: string;
}) {
  const [query, setQuery] = useState(value);
  const [options, setOptions] = useState<PlaceOption[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    if (value && value !== query && options.length === 0) setQuery(value);
  }, [options.length, query, value]);

  useEffect(() => {
    const q = query.trim();
    if (q === value || q.length < 2 || isCoord(q)) {
      setOptions([]);
      setOpen(false);
      setLoading(false);
      return;
    }

    const controller = new AbortController();
    setLoading(true);
    const timer = window.setTimeout(() => {
      api
        .searchPlaces({ level: "city", q, limit: 8 }, controller.signal)
        .then((response) => {
          setOptions(response.options);
          if (focused && response.options.length > 0) setOpen(true);
        })
        .catch(() => setOptions([]))
        .finally(() => setLoading(false));
    }, 350);

    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [focused, query, value]);

  function commit(option: PlaceOption) {
    const picked = option.birthPlace ?? option.value;
    onChange(picked);
    setQuery(picked);
    setOptions([]);
    setOpen(false);
  }

  function onInput(text: string) {
    setQuery(text);
    if (isCoord(text)) {
      onChange(text.trim());
    } else if (value) {
      onChange("");
    }
  }

  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key === "Enter" && isCoord(query)) {
      event.preventDefault();
      onChange(query.trim());
      setOpen(false);
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  }

  const committed = Boolean(value) && query.trim() === value;

  return (
    <Field
      label="City of birth"
      icon={<MapPin size={16} />}
      error={error}
      hint="Search by city name. If your city is missing, exact coordinates are also supported."
    >
      <Popover open={open && (loading || options.length > 0)} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <div
            className={cn(
              "flex h-[52px] items-center gap-3 rounded-[10px] border border-gold/30 bg-white px-4 text-muted shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] transition focus-within:border-gold focus-within:ring-4 focus-within:ring-gold/15",
              committed && "text-ink",
              error && "border-red bg-red/5"
            )}
          >
            <MapPin className="size-4 shrink-0" />
            <input
              value={query}
              onChange={(event) => onInput(event.target.value)}
              onFocus={() => {
                setFocused(true);
                if (options.length) setOpen(true);
              }}
              onBlur={() => setFocused(false)}
              onKeyDown={onKeyDown}
              placeholder="Search city"
              autoComplete="off"
              role="combobox"
              aria-expanded={open && options.length > 0}
              className="min-w-0 flex-1 border-0 bg-transparent p-0 text-[15px] text-ink outline-none placeholder:text-muted"
            />
            {loading ? (
              <LoaderCircle className="size-4 shrink-0 animate-spin text-gold" />
            ) : (
              <Search className="size-4 shrink-0" />
            )}
          </div>
        </PopoverTrigger>
        <PopoverContent
          className="w-[var(--radix-popover-trigger-width)] p-1"
          onOpenAutoFocus={(event) => event.preventDefault()}
          onCloseAutoFocus={(event) => event.preventDefault()}
        >
          <div className="max-h-[300px] overflow-y-auto">
            {loading ? (
              <div className="px-3 py-6 text-center text-sm text-muted">Searching...</div>
            ) : (
              <div role="listbox" aria-label="City search results" className="grid gap-1">
                {options.map((option) => (
                  <button
                    type="button"
                    key={option.id}
                    role="option"
                    onMouseDown={(event) => {
                      event.preventDefault();
                      commit(option);
                    }}
                    className="flex items-baseline justify-between gap-3 rounded-lg px-3 py-2.5 text-left text-sm text-muted outline-none transition hover:bg-gold/15 hover:text-ink focus:bg-gold/15 focus:text-ink"
                  >
                    <span className="font-medium text-ink">{option.label}</span>
                    <span className="max-w-[55%] truncate text-xs text-muted">{option.meta}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </PopoverContent>
      </Popover>
    </Field>
  );
}
