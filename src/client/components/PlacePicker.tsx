import { useEffect, useState } from "react";
import { LocateFixed, LoaderCircle, MapPin, Search } from "lucide-react";
import { api } from "../api";
import { useI18n } from "../i18n/provider";
import { cn } from "../lib/cn";
import {
  formatCoordinateNumber,
  parseCoordinateInput,
  validateCoordinateParts
} from "../lib/coordinates";
import type { PlaceOption } from "../../shared/domain";
import { Field } from "./ui/field";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";

type PlaceMode = "city" | "coordinates";

// City stays the primary path. Coordinates are an explicit fallback so
// invalid latitude/longitude text never gets committed as a birth place.
export function PlacePicker({
  value,
  onChange,
  error
}: {
  value: string;
  onChange: (value: string) => void;
  error?: string;
}) {
  const { t } = useI18n();
  const initialCoordinates = parseCoordinateInput(value);
  const [mode, setMode] = useState<PlaceMode>(initialCoordinates.ok ? "coordinates" : "city");
  const [query, setQuery] = useState(initialCoordinates.ok ? "" : value);
  const [latitude, setLatitude] = useState(
    initialCoordinates.ok ? formatCoordinateNumber(initialCoordinates.latitude) : ""
  );
  const [longitude, setLongitude] = useState(
    initialCoordinates.ok ? formatCoordinateNumber(initialCoordinates.longitude) : ""
  );
  const [options, setOptions] = useState<PlaceOption[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    if (mode === "city" && value && value !== query && options.length === 0) setQuery(value);
  }, [mode, options.length, query, value]);

  useEffect(() => {
    const q = query.trim();
    if (mode !== "city" || q === value || q.length < 2) {
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
  }, [focused, mode, query, value]);

  function commit(option: PlaceOption) {
    const picked = option.birthPlace ?? option.value;
    onChange(picked);
    setQuery(picked);
    setOptions([]);
    setOpen(false);
  }

  function onInput(text: string) {
    setQuery(text);
    if (value) onChange("");
  }

  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key === "Escape") {
      setOpen(false);
    }
  }

  function switchMode(nextMode: PlaceMode) {
    setMode(nextMode);
    setOpen(false);
    setOptions([]);
    if (nextMode === "city") {
      setLatitude("");
      setLongitude("");
      if (parseCoordinateInput(value).ok) onChange("");
      return;
    }
    setQuery("");
    if (value) onChange("");
  }

  function updateCoordinates(nextLatitude: string, nextLongitude: string) {
    setLatitude(nextLatitude);
    setLongitude(nextLongitude);
    const validation = validateCoordinateParts(nextLatitude, nextLongitude);
    onChange(validation.ok ? validation.value : "");
  }

  const coordinateValidation = validateCoordinateParts(latitude, longitude);
  const coordinateError =
    mode === "coordinates" && !coordinateValidation.ok && coordinateValidation.reason !== "empty"
      ? coordinateValidation.reason === "latitude"
        ? t("place.coordinates.error.latitude")
        : coordinateValidation.reason === "longitude"
          ? t("place.coordinates.error.longitude")
          : t("place.coordinates.error.format")
      : undefined;
  const committed = mode === "city" && Boolean(value) && query.trim() === value;
  const fieldError = coordinateError ?? error;

  return (
    <Field
      label={t("place.label")}
      icon={mode === "coordinates" ? <LocateFixed size={16} /> : <MapPin size={16} />}
      error={fieldError}
      hint={mode === "coordinates" ? t("place.coordinates.hint") : t("place.city.hint")}
    >
      <div className="grid gap-2.5">
        <div className="inline-grid w-fit grid-cols-2 rounded-full border border-gold/25 bg-cream p-1">
          <button
            type="button"
            onClick={() => switchMode("city")}
            data-active={mode === "city"}
            className="inline-flex h-8 items-center justify-center gap-1.5 rounded-full px-3 text-xs font-medium text-muted transition hover:text-ink data-[active=true]:bg-gold data-[active=true]:text-white"
          >
            <MapPin className="size-3.5" />
            {t("place.mode.city")}
          </button>
          <button
            type="button"
            onClick={() => switchMode("coordinates")}
            data-active={mode === "coordinates"}
            className="inline-flex h-8 items-center justify-center gap-1.5 rounded-full px-3 text-xs font-medium text-muted transition hover:text-ink data-[active=true]:bg-gold data-[active=true]:text-white"
          >
            <LocateFixed className="size-3.5" />
            {t("place.mode.coordinates")}
          </button>
        </div>

        {mode === "city" ? (
          <Popover open={open && (loading || options.length > 0)} onOpenChange={setOpen}>
            <PopoverTrigger asChild>
              <div
                className={cn(
                  "flex h-[52px] items-center gap-3 rounded-[10px] border border-gold/30 bg-white px-4 text-muted shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] transition focus-within:border-gold focus-within:ring-4 focus-within:ring-gold/15",
                  committed && "text-ink",
                  fieldError && "border-red bg-red/5"
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
                  placeholder={t("place.placeholder")}
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
                  <div className="px-3 py-6 text-center text-sm text-muted">
                    {t("place.searching")}
                  </div>
                ) : (
                  <div role="listbox" aria-label={t("place.results")} className="grid gap-1">
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
                        <span className="max-w-[55%] truncate text-xs text-muted">
                          {option.meta}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </PopoverContent>
          </Popover>
        ) : (
          <div
            className={cn(
              "grid gap-3 rounded-[10px] border border-gold/30 bg-white p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] transition focus-within:border-gold focus-within:ring-4 focus-within:ring-gold/15 sm:grid-cols-2",
              fieldError && "border-red bg-red/5"
            )}
          >
            <label className="grid gap-1.5">
              <span className="text-[11px] uppercase tracking-[1px] text-muted">
                {t("place.coordinates.longitude")}
              </span>
              <input
                value={longitude}
                onChange={(event) => updateCoordinates(latitude, event.target.value)}
                inputMode="decimal"
                placeholder={t("place.coordinates.longitude.placeholder")}
                className="min-w-0 border-0 bg-transparent p-0 text-[15px] text-ink outline-none placeholder:text-muted"
              />
            </label>
            <label className="grid gap-1.5">
              <span className="text-[11px] uppercase tracking-[1px] text-muted">
                {t("place.coordinates.latitude")}
              </span>
              <input
                value={latitude}
                onChange={(event) => updateCoordinates(event.target.value, longitude)}
                inputMode="decimal"
                placeholder={t("place.coordinates.latitude.placeholder")}
                className="min-w-0 border-0 bg-transparent p-0 text-[15px] text-ink outline-none placeholder:text-muted"
              />
            </label>
          </div>
        )}
      </div>
    </Field>
  );
}
