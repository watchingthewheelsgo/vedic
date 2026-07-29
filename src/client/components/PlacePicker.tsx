import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { Check, Crosshair, LocateFixed, LoaderCircle, MapPin, Search } from "lucide-react";
import { api } from "../api";
import { useI18n } from "../i18n/provider";
import { cn } from "../lib/cn";
import {
  formatCoordinateNumber,
  parseCoordinateInput,
  validateCoordinateParts
} from "../lib/coordinates";
import type { PlaceOption, PlaceSearchLevel, PrecisePlaceOption } from "../../shared/domain";
import { Field } from "./ui/field";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";

type PlaceMode = "city" | "coordinates";
type PlaceReadoutKind = "city" | "city-fallback" | "precise" | "manual";
type Translator = (key: string, vars?: Record<string, string | number>) => string;
type PlaceReadout = {
  kind: PlaceReadoutKind;
  label?: string | null;
  latitude: number;
  longitude: number;
  timezone?: string | null;
};

export type BirthPlaceVisualState = {
  latitude: number;
  longitude: number;
  label?: string | null;
  exact?: boolean;
};

type PreciseLookupState = {
  fallbackEnabled: boolean;
  agentFallbackEnabled: boolean;
  agentAttempted: boolean;
  agentError: string | null;
  verificationBase: string | null;
  rejectedCount: number;
  attemptedSources: string[];
};

const emptyLookupState: PreciseLookupState = {
  fallbackEnabled: false,
  agentFallbackEnabled: false,
  agentAttempted: false,
  agentError: null,
  verificationBase: null,
  rejectedCount: 0,
  attemptedSources: []
};

export function PlacePicker({
  value,
  onChange,
  onVisualStateChange,
  error
}: {
  value: string;
  onChange: (value: string) => void;
  onVisualStateChange?: (value: BirthPlaceVisualState | null) => void;
  error?: string;
}) {
  const { t } = useI18n();
  const initialCoordinates = parseCoordinateInput(value);
  const [mode, setMode] = useState<PlaceMode>(initialCoordinates.ok ? "coordinates" : "city");
  const [city, setCity] = useState<PlaceOption | null>(null);
  const [cityQuery, setCityQuery] = useState(initialCoordinates.ok ? "" : value);
  const [cityFallback, setCityFallback] = useState(initialCoordinates.ok ? "" : value);
  const [poiQuery, setPoiQuery] = useState("");
  const [poiOptions, setPoiOptions] = useState<PrecisePlaceOption[]>([]);
  const [poiLoading, setPoiLoading] = useState(false);
  const [poiElapsedSeconds, setPoiElapsedSeconds] = useState(0);
  const [poiError, setPoiError] = useState("");
  const [poiLookupStarted, setPoiLookupStarted] = useState(false);
  const [lookupState, setLookupState] = useState<PreciseLookupState>(emptyLookupState);
  const [preciseSelection, setPreciseSelection] = useState<PrecisePlaceOption | null>(null);
  const activePoiController = useRef<AbortController | null>(null);
  const [latitude, setLatitude] = useState(
    initialCoordinates.ok ? formatCoordinateNumber(initialCoordinates.latitude) : ""
  );
  const [longitude, setLongitude] = useState(
    initialCoordinates.ok ? formatCoordinateNumber(initialCoordinates.longitude) : ""
  );
  const [cityReadout, setCityReadout] = useState<PlaceReadout | null>(null);
  const [readout, setReadout] = useState<PlaceReadout | null>(
    initialCoordinates.ok
      ? {
          kind: "manual",
          latitude: initialCoordinates.latitude,
          longitude: initialCoordinates.longitude
        }
      : null
  );

  useEffect(() => {
    if (!value) {
      setReadout(null);
      setPreciseSelection(null);
    }
  }, [value]);

  useEffect(() => {
    return () => {
      activePoiController.current?.abort();
    };
  }, []);

  useEffect(() => {
    const visualState = readout
      ? {
          latitude: readout.latitude,
          longitude: readout.longitude,
          label: readout.label,
          exact: readout.kind === "manual" || readout.kind === "precise"
        }
      : null;
    onVisualStateChange?.(visualState);
    window.dispatchEvent(
      new CustomEvent("birth-place-coordinates", {
        detail: visualState
      })
    );
  }, [onVisualStateChange, readout]);

  useEffect(() => {
    if (!poiLoading) {
      setPoiElapsedSeconds(0);
      return;
    }

    const startedAt = Date.now();
    setPoiElapsedSeconds(0);
    const interval = window.setInterval(() => {
      setPoiElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => window.clearInterval(interval);
  }, [poiLoading]);

  function clearCity() {
    activePoiController.current?.abort();
    activePoiController.current = null;
    setCity(null);
    setCityQuery("");
    setCityFallback("");
    setCityReadout(null);
    setReadout(null);
    setPreciseSelection(null);
    setPoiQuery("");
    setPoiOptions([]);
    setPoiLookupStarted(false);
    setPoiLoading(false);
    setLookupState(emptyLookupState);
    onChange("");
  }

  function clearPreciseSelection(nextReadout: PlaceReadout | null = cityReadout) {
    setPreciseSelection(null);
    setReadout(nextReadout);
    if (cityFallback.trim()) onChange(cityFallback);
  }

  function selectCity(option: PlaceOption) {
    activePoiController.current?.abort();
    activePoiController.current = null;
    const picked = option.birthPlace ?? option.value;
    const nextReadout = placeReadoutFromCityOption(option);
    setCity(option);
    setCityQuery(option.label);
    setCityFallback(picked);
    setCityReadout(nextReadout);
    setReadout(nextReadout);
    setPreciseSelection(null);
    setPoiQuery("");
    setPoiOptions([]);
    setPoiLookupStarted(false);
    setPoiLoading(false);
    setLookupState(emptyLookupState);
    onChange(picked);
  }

  function updateCityQuery(text: string) {
    setCityQuery(text);
    if (!city) return;
    setCity(null);
    setCityFallback("");
    setCityReadout(null);
    clearPreciseSelection(null);
    onChange("");
  }

  function updatePoiQuery(text: string) {
    activePoiController.current?.abort();
    activePoiController.current = null;
    setPoiQuery(text);
    setPoiOptions([]);
    setPoiError("");
    setPoiLookupStarted(false);
    setPoiLoading(false);
    setLookupState(emptyLookupState);
    if (preciseSelection) clearPreciseSelection();
  }

  function runPoiLookup() {
    const q = poiQuery.trim();
    const cityContext = cityFallback.trim();
    if (mode !== "city" || !cityContext || q.length < 2 || poiLoading) return;
    if (preciseSelection && q === preciseSelection.label.trim()) return;

    activePoiController.current?.abort();
    const controller = new AbortController();
    activePoiController.current = controller;
    setPoiLookupStarted(true);
    setPoiLoading(true);
    setPoiElapsedSeconds(0);
    setPoiError("");
    setPoiOptions([]);
    setLookupState(emptyLookupState);

    api
      .searchPrecisePlaces({ q, city: cityContext, limit: 8 }, controller.signal)
      .then((response) => {
        setPoiOptions(response.options);
        setLookupState({
          fallbackEnabled: response.fallbackEnabled,
          agentFallbackEnabled: response.agentFallbackEnabled,
          agentAttempted: response.agentAttempted,
          agentError: response.agentError ?? null,
          verificationBase: response.verificationBase ?? null,
          rejectedCount: response.rejectedCount,
          attemptedSources: response.attemptedSources
        });
      })
      .catch((caught) => {
        if (controller.signal.aborted) return;
        setPoiOptions([]);
        setPoiError(caught instanceof Error ? caught.message : t("precisePlace.search.error"));
      })
      .finally(() => {
        if (activePoiController.current === controller) {
          activePoiController.current = null;
          setPoiLoading(false);
        }
      });
  }

  function onPoiKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key !== "Enter") return;
    event.preventDefault();
    runPoiLookup();
  }

  function commitPrecise(option: PrecisePlaceOption) {
    const nextReadout = placeReadoutFromPreciseOption(option, cityReadout);
    setPreciseSelection(option);
    setPoiQuery(option.label);
    setReadout(nextReadout);
    onChange(option.birthPlace);
  }

  function useCityFallback() {
    const fallback = cityFallback.trim();
    setMode("city");
    setLatitude("");
    setLongitude("");
    setPreciseSelection(null);
    setReadout(cityReadout);
    onChange(fallback);
  }

  function switchMode(nextMode: PlaceMode) {
    setMode(nextMode);
    if (nextMode === "city") {
      setLatitude("");
      setLongitude("");
      setReadout(
        preciseSelection
          ? placeReadoutFromPreciseOption(preciseSelection, cityReadout)
          : cityReadout
      );
      onChange(preciseSelection?.birthPlace ?? cityFallback);
      return;
    }
    setReadout(null);
    if (value) onChange("");
  }

  function updateCoordinates(nextLatitude: string, nextLongitude: string) {
    setLatitude(nextLatitude);
    setLongitude(nextLongitude);
    const validation = validateCoordinateParts(nextLatitude, nextLongitude);
    setReadout(
      validation.ok
        ? {
            kind: "manual",
            latitude: validation.latitude,
            longitude: validation.longitude
          }
        : null
    );
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
  const fieldError = coordinateError ?? error;
  const selectedPreciseLabel =
    preciseSelection && preciseSelection.verificationStatus !== "city-fallback"
      ? preciseSelection.label
      : "";
  const cityReady = Boolean(cityFallback.trim());
  const canSearchPoi =
    mode === "city" &&
    cityReady &&
    poiQuery.trim().length >= 2 &&
    !poiLoading &&
    !(preciseSelection && poiQuery.trim() === preciseSelection.label.trim());
  return (
    <Field label="" error={fieldError} className="mb-0">
      <div className="grid gap-3">
        {mode === "city" ? (
          <div className="grid gap-3">
            <div className="grid gap-2">
              <PlaceSearchBox
                level="city"
                label={t("place.citySearch.label")}
                placeholder={t("place.citySearch.placeholder")}
                resultsLabel={t("place.citySearch.results")}
                query={cityQuery}
                selected={city}
                onQueryChange={updateCityQuery}
                onSelect={selectCity}
              />
              {cityReady ? (
                <ResolvedPlaceSummary
                  label={cityFallback}
                  readout={cityReadout}
                  onClear={clearCity}
                  t={t}
                />
              ) : null}
            </div>

            {cityReady ? (
              <div className="grid gap-3 rounded-[12px] border border-gold/20 bg-white/[0.035] p-3">
                <label className="grid min-w-0 gap-1.5">
                  <span className="flex items-center gap-2 text-[11px] uppercase tracking-[1.1px] text-muted">
                    <Crosshair className="size-4 text-gold-dim" />
                    {t("place.poi.label")}
                    <span className="normal-case tracking-normal text-cream/35">
                      {t("place.poi.optionalTag")}
                    </span>
                  </span>
                  <div className="flex h-[50px] items-center gap-3 rounded-[10px] border border-gold/25 bg-white/5 px-4 text-cream/45 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] transition focus-within:border-gold focus-within:bg-white/10 focus-within:ring-4 focus-within:ring-gold/15">
                    <input
                      name="birthPoi"
                      value={poiQuery}
                      onChange={(event) => updatePoiQuery(event.target.value)}
                      onKeyDown={onPoiKeyDown}
                      placeholder={t("place.poi.placeholder")}
                      autoComplete="street-address"
                      className="min-w-0 flex-1 border-0 bg-transparent p-0 text-[15px] text-cream outline-none placeholder:text-cream/35"
                    />
                    <button
                      type="button"
                      onClick={runPoiLookup}
                      disabled={!canSearchPoi}
                      className="inline-flex h-8 shrink-0 items-center justify-center gap-1.5 rounded-full border border-gold/25 bg-gold/10 px-3 text-xs font-medium text-gold-light transition hover:border-gold/45 hover:bg-gold/15 disabled:cursor-not-allowed disabled:border-gold/10 disabled:bg-white/[0.03] disabled:text-cream/30 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-gold/15"
                    >
                      {poiLoading ? (
                        <LoaderCircle className="size-3.5 animate-spin" />
                      ) : preciseSelection ? (
                        <Check className="size-3.5" />
                      ) : (
                        <Search className="size-3.5" />
                      )}
                      {t("place.poi.search")}
                    </button>
                  </div>
                </label>

                {poiLookupStarted || poiLoading || preciseSelection ? (
                  <div aria-live="polite">
                    <PlaceLookupProgress
                      cityReady={cityReady}
                      query={poiQuery}
                      lookupStarted={poiLookupStarted}
                      loading={poiLoading}
                      elapsedSeconds={poiElapsedSeconds}
                      lookupState={lookupState}
                      options={poiOptions}
                      selected={preciseSelection}
                      poiError={poiError}
                      t={t}
                    />
                  </div>
                ) : null}

                <PreciseOptionsList
                  options={poiOptions}
                  loading={poiLoading}
                  query={poiQuery}
                  lookupStarted={poiLookupStarted}
                  cityReady={cityReady}
                  selected={preciseSelection}
                  fallbackEnabled={lookupState.fallbackEnabled}
                  agentFallbackEnabled={lookupState.agentFallbackEnabled}
                  onSelect={commitPrecise}
                  t={t}
                />
              </div>
            ) : null}
          </div>
        ) : (
          <div
            className={cn(
              "birth-input-field-shell grid gap-3 rounded-[10px] border border-gold/30 bg-white/5 p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] transition focus-within:border-gold focus-within:bg-white/10 focus-within:ring-4 focus-within:ring-gold/15 sm:grid-cols-2",
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
                className="min-w-0 border-0 bg-transparent p-0 text-[15px] text-cream outline-none placeholder:text-cream/35"
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
                className="min-w-0 border-0 bg-transparent p-0 text-[15px] text-cream outline-none placeholder:text-cream/35"
              />
            </label>
          </div>
        )}

        {readout ? <PlaceCoordinateReadout readout={readout} t={t} /> : null}
        {selectedPreciseLabel ? (
          <div className="flex w-fit flex-wrap items-center gap-2 rounded-full border border-gold/25 bg-white/5 px-3 py-1 text-xs text-cream/70">
            <span className="inline-flex items-center gap-2">
              <MapPin className="size-3.5 text-gold-dim" />
              {selectedPreciseLabel}
            </span>
            <button
              type="button"
              onClick={useCityFallback}
              className="font-medium text-gold-light underline-offset-2 hover:text-gold-light hover:underline focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-gold/15"
            >
              {t("place.precise.incorrect")}
            </button>
          </div>
        ) : null}
        <button
          type="button"
          onClick={() => switchMode(mode === "city" ? "coordinates" : "city")}
          className="inline-flex w-fit items-center gap-1.5 text-xs text-cream/45 underline-offset-4 transition-colors hover:text-gold-light hover:underline focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-gold/15"
        >
          {mode === "city" ? <LocateFixed className="size-3.5" /> : <MapPin className="size-3.5" />}
          {mode === "city" ? t("place.coordinates.manualLink") : t("place.mode.city")}
        </button>
      </div>
    </Field>
  );
}

function ResolvedPlaceSummary({
  label,
  readout,
  onClear,
  t
}: {
  label: string;
  readout: PlaceReadout | null;
  onClear: () => void;
  t: Translator;
}) {
  return (
    <div className="flex min-w-0 flex-wrap items-center justify-between gap-2 rounded-[10px] border border-gold/20 bg-gold/10 px-3 py-2">
      <div className="min-w-0">
        <div className="flex min-w-0 items-center gap-2 text-sm text-cream">
          <MapPin className="size-4 shrink-0 text-gold-dim" />
          <span className="truncate">{label}</span>
        </div>
        <div className="mt-1 text-xs text-cream/50">
          {readout
            ? `${formatLatitude(readout.latitude)} · ${formatLongitude(readout.longitude)} · ${
                readout.timezone ?? t("place.readout.backendTimezone")
              }`
            : t("place.city.selected")}
        </div>
      </div>
      <button
        type="button"
        onClick={onClear}
        className="shrink-0 text-xs font-medium text-gold-light underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-gold/15"
      >
        {t("place.city.change")}
      </button>
    </div>
  );
}

function PlaceLookupProgress({
  cityReady,
  query,
  lookupStarted,
  loading,
  elapsedSeconds,
  lookupState,
  options,
  selected,
  poiError,
  t
}: {
  cityReady: boolean;
  query: string;
  lookupStarted: boolean;
  loading: boolean;
  elapsedSeconds: number;
  lookupState: PreciseLookupState;
  options: PrecisePlaceOption[];
  selected: PrecisePlaceOption | null;
  poiError: string;
  t: Translator;
}) {
  const trimmed = query.trim();
  if (!cityReady || trimmed.length < 2 || !lookupStarted) return null;

  const hasOptions = options.length > 0;
  const hasError = Boolean(poiError || lookupState.agentError);
  const caption = loading
    ? t("place.lookup.progress.running", { seconds: elapsedSeconds, timeout: 120 })
    : selected
      ? t("place.lookup.progress.selected")
      : hasOptions
        ? t("place.lookup.progress.review")
        : hasError
          ? t("place.lookup.progress.retry")
          : t("place.lookup.progress.waiting");

  return (
    <div
      className={cn(
        "flex items-start gap-3 rounded-[11px] border px-3 py-2.5 text-xs leading-relaxed",
        hasError && !hasOptions
          ? "border-red/25 bg-red/8 text-red"
          : "border-gold/18 bg-black/12 text-cream/58"
      )}
    >
      <span className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-full border border-gold/25 bg-gold/10 text-gold-light">
        {loading ? (
          <LoaderCircle className="size-3.5 animate-spin" />
        ) : hasError && !hasOptions ? (
          <Crosshair className="size-3.5" />
        ) : (
          <Check className="size-3.5" />
        )}
      </span>
      <div className="min-w-0">
        <div className="font-medium text-cream/82">{t("place.lookup.progress.title")}</div>
        <div className="mt-0.5">{caption}</div>
      </div>
    </div>
  );
}

function PlaceSearchBox({
  level,
  label,
  placeholder,
  resultsLabel,
  query,
  selected,
  country,
  region,
  disabled = false,
  disabledText,
  onQueryChange,
  onSelect
}: {
  level: PlaceSearchLevel;
  label: string;
  placeholder: string;
  resultsLabel: string;
  query: string;
  selected: PlaceOption | null;
  country?: string;
  region?: string;
  disabled?: boolean;
  disabledText?: string;
  onQueryChange: (value: string) => void;
  onSelect: (option: PlaceOption) => void;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [focused, setFocused] = useState(false);
  const [loading, setLoading] = useState(false);
  const [options, setOptions] = useState<PlaceOption[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (disabled || !focused) {
      setOpen(false);
      setLoading(false);
      return;
    }

    const controller = new AbortController();
    setLoading(true);
    const timer = window.setTimeout(() => {
      api
        .searchPlaces({ level, q: query.trim(), country, region, limit: 10 }, controller.signal)
        .then((response) => {
          setOptions(response.options);
          setOpen(response.options.length > 0);
        })
        .catch(() => {
          if (!controller.signal.aborted) setOptions([]);
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 250);

    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [country, disabled, focused, level, query, region]);

  function onKeyDown(event: KeyboardEvent) {
    if (event.key === "Escape") setOpen(false);
  }

  return (
    <label className="grid min-w-0 gap-1.5">
      <span className="text-[11px] uppercase tracking-[1.1px] text-muted">{label}</span>
      <Popover open={open && !disabled && (loading || options.length > 0)} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <div
            className={cn(
              "birth-input-field-shell flex h-[50px] items-center gap-3 rounded-[10px] border border-gold/30 bg-white/5 px-3 text-cream/40 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] transition focus-within:border-gold focus-within:bg-white/10 focus-within:ring-4 focus-within:ring-gold/15",
              selected && "text-cream",
              disabled && "opacity-55"
            )}
          >
            <input
              ref={inputRef}
              value={query}
              onChange={(event) => onQueryChange(event.target.value)}
              onFocus={() => setFocused(true)}
              onBlur={() => setFocused(false)}
              onKeyDown={onKeyDown}
              disabled={disabled}
              placeholder={disabled ? disabledText : placeholder}
              autoComplete="off"
              role="combobox"
              aria-expanded={open && options.length > 0}
              className="min-w-0 flex-1 border-0 bg-transparent p-0 text-[15px] text-cream outline-none placeholder:text-cream/35 disabled:cursor-not-allowed"
            />
            {selected ? (
              <Check className="size-4 shrink-0 text-gold" />
            ) : loading ? (
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
              <div className="px-3 py-6 text-center text-sm text-muted">{t("place.searching")}</div>
            ) : (
              <div role="listbox" aria-label={resultsLabel} className="grid gap-1">
                {options.map((option) => (
                  <button
                    type="button"
                    key={option.id}
                    role="option"
                    onMouseDown={(event) => {
                      event.preventDefault();
                      setFocused(false);
                      setOpen(false);
                      inputRef.current?.blur();
                      onSelect(option);
                    }}
                    className="flex items-baseline justify-between gap-3 rounded-lg px-3 py-2.5 text-left text-sm text-cream/55 outline-none transition hover:bg-gold/15 hover:text-cream focus:bg-gold/15 focus:text-cream focus-visible:ring-4 focus-visible:ring-gold/15"
                  >
                    <span className="min-w-0 truncate font-medium text-cream">{option.label}</span>
                    <span className="max-w-[55%] truncate text-xs text-cream/45">
                      {option.meta}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </PopoverContent>
      </Popover>
    </label>
  );
}

function PreciseOptionsList({
  options,
  loading,
  query,
  lookupStarted,
  cityReady,
  selected,
  fallbackEnabled,
  agentFallbackEnabled,
  onSelect,
  t
}: {
  options: PrecisePlaceOption[];
  loading: boolean;
  query: string;
  lookupStarted: boolean;
  cityReady: boolean;
  selected: PrecisePlaceOption | null;
  fallbackEnabled: boolean;
  agentFallbackEnabled: boolean;
  onSelect: (option: PrecisePlaceOption) => void;
  t: Translator;
}) {
  const trimmed = query.trim();
  if (!cityReady) return null;
  if (trimmed.length === 0) return null;
  if (trimmed.length < 2) return <InlineHint text={t("precisePlace.search.minLength")} />;
  if (!lookupStarted && !selected) return <InlineHint text={t("precisePlace.search.ready")} />;
  if (loading) return <InlineHint text={t("precisePlace.search.loading")} />;
  if (options.length === 0) {
    return (
      <EmptyState
        text={
          fallbackEnabled || agentFallbackEnabled
            ? t("precisePlace.search.empty")
            : t("precisePlace.search.emptyNoFallback")
        }
      />
    );
  }

  return (
    <div className="grid gap-2">
      {options.map((option) => (
        <button
          key={option.id}
          type="button"
          onClick={() => onSelect(option)}
          data-active={selected?.id === option.id}
          className="grid gap-1 rounded-[10px] border border-gold/20 bg-white/5 px-4 py-3 text-left shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] outline-none transition hover:border-gold/50 hover:bg-gold/10 focus-visible:ring-4 focus-visible:ring-gold/20 data-[active=true]:border-gold data-[active=true]:bg-gold/15"
        >
          <span className="min-w-0 font-medium text-cream">{option.label}</span>
          <span className="text-xs leading-relaxed text-cream/70">
            {option.address || option.meta}
          </span>
          <span className="text-[11px] tabular-nums text-cream/48">
            {formatCoordinateNumber(option.longitude)}, {formatCoordinateNumber(option.latitude)} ·{" "}
            {t("place.readout.verifiedCoordinates")}
          </span>
        </button>
      ))}
    </div>
  );
}

function placeReadoutFromCityOption(option: PlaceOption): PlaceReadout | null {
  if (!isFiniteNumber(option.latitude) || !isFiniteNumber(option.longitude)) return null;
  return {
    kind: "city",
    label: option.value,
    latitude: option.latitude,
    longitude: option.longitude,
    timezone: option.timezone
  };
}

function placeReadoutFromPreciseOption(
  option: PrecisePlaceOption,
  cityReadout: PlaceReadout | null
): PlaceReadout {
  return {
    kind: option.verificationStatus === "city-fallback" ? "city-fallback" : "precise",
    label: option.label,
    latitude: option.latitude,
    longitude: option.longitude,
    timezone: cityReadout?.timezone
  };
}

function PlaceCoordinateReadout({ readout, t }: { readout: PlaceReadout | null; t: Translator }) {
  const statusKey = readout ? `place.readout.status.${readout.kind}` : "place.readout.status.empty";

  return (
    <div className="birth-input-readout grid grid-cols-2 gap-2 rounded-[10px] border border-gold/20 bg-gold/10 px-3 py-3 sm:grid-cols-4">
      <ReadoutCell
        label={t("place.readout.latitude")}
        value={readout ? formatLatitude(readout.latitude) : "--"}
      />
      <ReadoutCell
        label={t("place.readout.longitude")}
        value={readout ? formatLongitude(readout.longitude) : "--"}
      />
      <ReadoutCell
        label={t("place.readout.timezone")}
        value={readout?.timezone ?? (readout ? t("place.readout.backendTimezone") : "--")}
      />
      <ReadoutCell label={t("place.readout.status")} value={t(statusKey)} />
    </div>
  );
}

function ReadoutCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <div className="mb-1 text-[10px] uppercase tracking-[1px] text-cream/40">{label}</div>
      <div className="truncate font-mono text-[12px] text-cream">{value}</div>
    </div>
  );
}

function InlineHint({ text }: { text: string }) {
  return <div className="text-xs leading-relaxed text-cream/50">{text}</div>;
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="rounded-[10px] border border-dashed border-gold/30 bg-white/5 px-4 py-5 text-center text-sm text-cream/55">
      {text}
    </div>
  );
}

function formatLatitude(value: number) {
  return `${formatCoordinateNumber(value)} ${value >= 0 ? "N" : "S"}`;
}

function formatLongitude(value: number) {
  return `${formatCoordinateNumber(value)} ${value >= 0 ? "E" : "W"}`;
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}
