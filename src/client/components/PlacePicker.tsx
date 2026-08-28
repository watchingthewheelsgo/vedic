import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import {
  Check,
  ChevronsUpDown,
  ChevronRight,
  Crosshair,
  LocateFixed,
  LoaderCircle,
  MapPin,
  MapPinCheck,
  RotateCcw,
  Search,
  X
} from "lucide-react";
import { api } from "../api";
import { useI18n } from "../i18n/provider";
import { cn } from "../lib/cn";
import {
  formatCoordinateNumber,
  parseCoordinateInput,
  validateCoordinateParts
} from "../lib/coordinates";
import type {
  PlaceOption,
  PlaceSearchLevel,
  PrecisePlaceLookupStage,
  PrecisePlaceOption
} from "../../shared/domain";
import { Field } from "./ui/field";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";

type PlaceMode = "city" | "coordinates";
type PlaceReadoutKind = "administrative" | "city" | "city-fallback" | "precise" | "manual";
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

const administrativeOptionCache = new Map<string, PlaceOption[]>();

async function loadAdministrativeOptions(
  input: { level: PlaceSearchLevel; country?: string; region?: string },
  locale: "zh" | "en" | "ja",
  signal: AbortSignal
) {
  const key = [locale, input.level, input.country ?? "", input.region ?? ""].join(":");
  const cached = administrativeOptionCache.get(key);
  if (cached) return cached;
  const response = await api.searchPlaces({ ...input, locale, q: "", limit: 500 }, signal);
  administrativeOptionCache.set(key, response.options);
  return response.options;
}

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
  const { locale, t } = useI18n();
  const initialCoordinates = parseCoordinateInput(value);
  const [mode, setMode] = useState<PlaceMode>(initialCoordinates.ok ? "coordinates" : "city");
  const [country, setCountry] = useState<PlaceOption | null>(null);
  const [region, setRegion] = useState<PlaceOption | null>(null);
  const [city, setCity] = useState<PlaceOption | null>(null);
  const [cityFallback, setCityFallback] = useState(initialCoordinates.ok ? "" : value);
  const [countryOptions, setCountryOptions] = useState<PlaceOption[]>([]);
  const [regionOptions, setRegionOptions] = useState<PlaceOption[]>([]);
  const [cityOptions, setCityOptions] = useState<PlaceOption[]>([]);
  const [countryLoading, setCountryLoading] = useState(true);
  const [regionLoading, setRegionLoading] = useState(false);
  const [cityLoading, setCityLoading] = useState(false);
  const [poiQuery, setPoiQuery] = useState("");
  const [poiOptions, setPoiOptions] = useState<PrecisePlaceOption[]>([]);
  const [poiLoading, setPoiLoading] = useState(false);
  const [poiElapsedSeconds, setPoiElapsedSeconds] = useState(0);
  const [poiError, setPoiError] = useState("");
  const [poiLookupStarted, setPoiLookupStarted] = useState(false);
  const [lookupState, setLookupState] = useState<PreciseLookupState>(emptyLookupState);
  const [poiProgressStage, setPoiProgressStage] = useState<PrecisePlaceLookupStage | null>(null);
  const [preciseSelection, setPreciseSelection] = useState<PrecisePlaceOption | null>(null);
  const activePoiController = useRef<AbortController | null>(null);
  const [latitude, setLatitude] = useState(
    initialCoordinates.ok ? formatCoordinateNumber(initialCoordinates.latitude) : ""
  );
  const [longitude, setLongitude] = useState(
    initialCoordinates.ok ? formatCoordinateNumber(initialCoordinates.longitude) : ""
  );
  const [cityReadout, setCityReadout] = useState<PlaceReadout | null>(null);
  const [regionReadout, setRegionReadout] = useState<PlaceReadout | null>(null);
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
    const controller = new AbortController();
    setCountryLoading(true);
    loadAdministrativeOptions({ level: "country" }, locale, controller.signal)
      .then((options) => {
        setCountryOptions(options);
        setCountry((selected) =>
          selected ? (options.find((option) => option.value === selected.value) ?? selected) : null
        );
      })
      .catch(() => {
        if (!controller.signal.aborted) setCountryOptions([]);
      })
      .finally(() => {
        if (!controller.signal.aborted) setCountryLoading(false);
      });
    return () => controller.abort();
  }, [locale]);

  useEffect(() => {
    setRegionOptions([]);
    if (!country) return;
    const controller = new AbortController();
    setRegionLoading(true);
    loadAdministrativeOptions(
      { level: "region", country: country.value },
      locale,
      controller.signal
    )
      .then((options) => {
        setRegionOptions(options);
        setRegion((selected) =>
          selected ? (options.find((option) => option.value === selected.value) ?? selected) : null
        );
      })
      .catch(() => {
        if (!controller.signal.aborted) setRegionOptions([]);
      })
      .finally(() => {
        if (!controller.signal.aborted) setRegionLoading(false);
      });
    return () => controller.abort();
  }, [country, locale]);

  useEffect(() => {
    setCityOptions([]);
    if (!country || !region) return;
    const controller = new AbortController();
    setCityLoading(true);
    loadAdministrativeOptions(
      { level: "city", country: country.value, region: region.value },
      locale,
      controller.signal
    )
      .then((options) => {
        setCityOptions(options);
        setCity((selected) =>
          selected ? (options.find((option) => option.value === selected.value) ?? selected) : null
        );
      })
      .catch(() => {
        if (!controller.signal.aborted) setCityOptions([]);
      })
      .finally(() => {
        if (!controller.signal.aborted) setCityLoading(false);
      });
    return () => controller.abort();
  }, [country, locale, region]);

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

  function clearPreciseSelection(nextReadout: PlaceReadout | null = cityReadout ?? regionReadout) {
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
    setCityFallback(picked);
    setCityReadout(nextReadout);
    setReadout(nextReadout);
    setPreciseSelection(null);
    setPoiQuery("");
    setPoiOptions([]);
    setPoiLookupStarted(false);
    setPoiLoading(false);
    setLookupState(emptyLookupState);
    setPoiProgressStage(null);
    onChange(picked);
  }

  function selectCountry(option: PlaceOption) {
    activePoiController.current?.abort();
    activePoiController.current = null;
    setCountry(option);
    setRegion(null);
    setRegionReadout(null);
    setCity(null);
    setCityFallback("");
    setCityReadout(null);
    setReadout(null);
    setPreciseSelection(null);
    setPoiQuery("");
    setPoiOptions([]);
    setPoiLookupStarted(false);
    setPoiLoading(false);
    setLookupState(emptyLookupState);
    setPoiProgressStage(null);
    onChange("");
  }

  function selectRegion(option: PlaceOption) {
    activePoiController.current?.abort();
    activePoiController.current = null;
    const nextReadout = placeReadoutFromAdministrativeOption(option);
    setRegion(option);
    setCity(null);
    setCityFallback("");
    setCityReadout(null);
    setRegionReadout(nextReadout);
    setReadout(null);
    setPreciseSelection(null);
    setPoiQuery("");
    setPoiOptions([]);
    setPoiLookupStarted(false);
    setPoiLoading(false);
    setLookupState(emptyLookupState);
    setPoiProgressStage(null);
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
    setPoiProgressStage(null);
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
    setPoiProgressStage("resolving");

    api
      .searchPrecisePlacesStream(
        { q, city: cityContext, locale, limit: 8 },
        (progress) => setPoiProgressStage(progress.stage),
        controller.signal
      )
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
    const nextReadout = placeReadoutFromPreciseOption(option, cityReadout ?? regionReadout);
    setPreciseSelection(option);
    setPoiQuery(option.label);
    setReadout(nextReadout);
    onChange(option.birthPlace);
  }

  function changePrecisePlace() {
    updatePoiQuery("");
  }

  function useCityFallback() {
    const fallback = cityFallback.trim();
    setMode("city");
    setLatitude("");
    setLongitude("");
    setPreciseSelection(null);
    setPoiQuery("");
    setPoiOptions([]);
    setPoiLookupStarted(false);
    setPoiError("");
    setLookupState(emptyLookupState);
    setPoiProgressStage(null);
    setReadout(cityReadout ?? regionReadout);
    onChange(fallback);
  }

  function switchMode(nextMode: PlaceMode) {
    setMode(nextMode);
    if (nextMode === "city") {
      setLatitude("");
      setLongitude("");
      setReadout(
        preciseSelection
          ? placeReadoutFromPreciseOption(preciseSelection, cityReadout ?? regionReadout)
          : (cityReadout ?? regionReadout)
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
  const locationReady = Boolean(country && region && city && cityFallback.trim());
  const cityReady = locationReady;
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
          <div className="grid gap-4">
            <div className="grid min-w-0 gap-3 sm:grid-cols-2 sm:items-end">
              <PlaceSearchBox
                label={t("place.country.label")}
                placeholder={t("place.country.placeholder")}
                resultsLabel={t("place.country.results")}
                selected={country}
                options={countryOptions}
                loading={countryLoading}
                showMeta={false}
                onSelect={selectCountry}
              />
              <PlaceSearchBox
                label={t("place.region.label")}
                placeholder={t("place.region.placeholder")}
                resultsLabel={t("place.region.results")}
                selected={region}
                options={regionOptions}
                loading={regionLoading}
                disabled={!country}
                disabledText={t("place.region.requiresCountry")}
                onSelect={selectRegion}
              />
              <div className="sm:col-span-2">
                <PlaceSearchBox
                  label={t("place.city.label")}
                  placeholder={t("place.city.placeholder")}
                  resultsLabel={t("place.city.results")}
                  selected={city}
                  options={cityOptions}
                  loading={cityLoading}
                  disabled={!country || !region}
                  disabledText={t("place.city.requiresRegion")}
                  onSelect={selectCity}
                />
              </div>
            </div>

            {locationReady && readout ? <PlaceCoordinateReadout readout={readout} t={t} /> : null}

            {locationReady ? (
              selectedPreciseLabel ? (
                <SelectedPrecisePlace
                  option={preciseSelection}
                  onChange={changePrecisePlace}
                  onUseCityFallback={useCityFallback}
                  t={t}
                />
              ) : (
                <div className="grid gap-3 border-t border-white/[0.08] pt-4">
                  <div className="flex items-start gap-3">
                    <span className="grid size-8 shrink-0 place-items-center text-gold-light/75">
                      <Crosshair className="size-4" />
                    </span>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm font-medium text-cream/78">
                        <span>{t("place.flow.poi.title")}</span>
                        <span className="text-[11px] font-normal text-cream/38">
                          {t("place.poi.optionalTag")}
                        </span>
                      </div>
                      <p className="m-0 mt-1 text-xs leading-relaxed text-cream/45">
                        {t("place.flow.poi.body")}
                      </p>
                    </div>
                  </div>
                  <label className="grid min-w-0 gap-2">
                    <span className="sr-only">{t("place.poi.label")}</span>
                    <div className="flex min-h-[54px] items-center gap-3 rounded-[9px] border border-white/12 bg-white/[0.035] px-4 text-cream/45 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)] transition focus-within:border-gold/70 focus-within:bg-white/[0.055] focus-within:ring-2 focus-within:ring-gold/15">
                      <Crosshair className="size-[18px] shrink-0 text-gold-dim" />
                      <input
                        name="birthPoi"
                        value={poiQuery}
                        onChange={(event) => updatePoiQuery(event.target.value)}
                        onKeyDown={onPoiKeyDown}
                        placeholder={t("place.poi.placeholder")}
                        autoComplete="street-address"
                        className="min-w-0 flex-1 border-0 bg-transparent p-0 text-[15px] text-cream outline-none placeholder:text-cream/35"
                      />
                      {poiQuery ? (
                        <button
                          type="button"
                          onClick={() => updatePoiQuery("")}
                          aria-label={t("common.clear")}
                          className="grid size-8 shrink-0 place-items-center rounded-full text-cream/40 transition hover:bg-white/10 hover:text-cream focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-gold/15"
                        >
                          <X className="size-4" />
                        </button>
                      ) : null}
                      <button
                        type="button"
                        onClick={runPoiLookup}
                        disabled={!canSearchPoi}
                        className="inline-flex min-h-9 shrink-0 items-center justify-center gap-1.5 rounded-[8px] border border-gold bg-gold px-3.5 text-xs font-medium text-[#17120b] transition hover:border-gold-light hover:bg-gold-light disabled:cursor-not-allowed disabled:border-white/[0.06] disabled:bg-white/[0.035] disabled:text-cream/28 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gold/20"
                      >
                        {poiLoading ? (
                          <LoaderCircle className="size-3.5 animate-spin" />
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
                        progressStage={poiProgressStage}
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
                    onRetry={runPoiLookup}
                    onUseCityFallback={useCityFallback}
                    t={t}
                  />
                </div>
              )
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

        {mode === "coordinates" && readout ? (
          <PlaceCoordinateReadout readout={readout} t={t} />
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

function SelectedPrecisePlace({
  option,
  onChange,
  onUseCityFallback,
  t
}: {
  option: PrecisePlaceOption | null;
  onChange: () => void;
  onUseCityFallback: () => void;
  t: Translator;
}) {
  if (!option) return null;
  return (
    <div className="flex min-w-0 flex-wrap items-center justify-between gap-3 rounded-[12px] border border-gold/35 bg-gold/12 px-3.5 py-3">
      <div className="flex min-w-0 items-start gap-2.5">
        <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full bg-gold text-night">
          <MapPinCheck className="size-3.5" />
        </span>
        <div className="min-w-0">
          <div className="truncate text-sm font-medium text-cream">{option.label}</div>
          <div className="mt-1 line-clamp-2 text-xs leading-relaxed text-cream/55">
            {option.address || option.meta || t("place.flow.precisePoint")}
          </div>
        </div>
      </div>
      <div className="flex shrink-0 flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={onChange}
          className="inline-flex min-h-9 items-center gap-1.5 rounded-full border border-gold/25 px-3 text-xs font-medium text-gold-light transition hover:border-gold/45 hover:bg-gold/10 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-gold/15"
        >
          <RotateCcw className="size-3.5" />
          {t("place.flow.changePoint")}
        </button>
        <button
          type="button"
          onClick={onUseCityFallback}
          className="inline-flex min-h-9 items-center gap-1.5 text-xs text-cream/45 underline-offset-4 transition hover:text-gold-light hover:underline focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-gold/15"
        >
          {t("place.flow.useCityPoint")}
        </button>
      </div>
    </div>
  );
}

function PlaceLookupProgress({
  cityReady,
  query,
  lookupStarted,
  loading,
  elapsedSeconds,
  progressStage,
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
  progressStage: PrecisePlaceLookupStage | null;
  lookupState: PreciseLookupState;
  options: PrecisePlaceOption[];
  selected: PrecisePlaceOption | null;
  poiError: string;
  t: Translator;
}) {
  const trimmed = query.trim();
  if (!cityReady || trimmed.length < 2 || !lookupStarted) return null;

  const hasOptions = options.some((option) => option.verificationStatus !== "city-fallback");
  const hasError = Boolean(poiError || (!hasOptions && lookupState.agentError));
  const activeStage = loading
    ? progressStage === "verifying"
      ? 1
      : progressStage === "matching"
        ? 2
        : progressStage === "complete"
          ? 3
          : 0
    : hasOptions || selected
      ? 3
      : hasError
        ? 2
        : 0;
  const caption = loading
    ? t("place.flow.lookup.running", { seconds: elapsedSeconds })
    : selected
      ? t("place.flow.lookup.selected")
      : hasOptions
        ? t("place.flow.lookup.review")
        : hasError
          ? t("place.flow.lookup.retry")
          : t("place.flow.lookup.empty");

  return (
    <div className="grid gap-2.5 px-1 py-1" aria-label={t("place.lookup.progress.title")}>
      <div
        className={cn(
          "flex items-center gap-2 text-xs",
          hasError && !hasOptions ? "text-red" : "text-cream/62"
        )}
      >
        <span className="grid size-5 shrink-0 place-items-center rounded-full bg-gold/12 text-gold-light">
          {loading ? (
            <LoaderCircle className="size-3 animate-spin" />
          ) : hasError && !hasOptions ? (
            <Crosshair className="size-3" />
          ) : (
            <Check className="size-3" />
          )}
        </span>
        <span className="min-w-0 flex-1 leading-relaxed">{caption}</span>
        {loading ? (
          <span className="shrink-0 tabular-nums text-cream/35">{elapsedSeconds}s</span>
        ) : null}
      </div>
      <div className="grid grid-cols-3 gap-2" aria-hidden>
        {[
          t("place.flow.lookup.stage.search"),
          t("place.flow.lookup.stage.verify"),
          t("place.flow.lookup.stage.match")
        ].map((label, step) => {
          const complete = activeStage > step;
          const active = activeStage === step;
          return (
            <div key={label} className="min-w-0">
              <div className="mb-1 flex items-center gap-1.5">
                <span
                  className={cn(
                    "size-1.5 shrink-0 rounded-full transition",
                    complete || active ? "bg-gold" : hasError ? "bg-red/45" : "bg-white/12",
                    active && loading && "animate-pulse"
                  )}
                />
                <span
                  className={cn(
                    "truncate text-[10px]",
                    complete ? "text-gold-light/75" : active ? "text-cream/65" : "text-cream/30"
                  )}
                >
                  {label}
                </span>
              </div>
              <span
                className={cn(
                  "block h-1 rounded-full transition",
                  complete ? "bg-gold/70" : active && loading ? "bg-gold/35" : "bg-white/10"
                )}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}

function PlaceSearchBox({
  label,
  placeholder,
  resultsLabel,
  selected,
  options,
  loading,
  disabled = false,
  disabledText,
  showMeta = true,
  onSelect
}: {
  label: string;
  placeholder: string;
  resultsLabel: string;
  selected: PlaceOption | null;
  options: PlaceOption[];
  loading: boolean;
  disabled?: boolean;
  disabledText?: string;
  showMeta?: boolean;
  onSelect: (option: PlaceOption) => void;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const normalizedQuery = normalizeAdministrativeSearch(query);
  const filteredOptions = useMemo(() => {
    if (!normalizedQuery) return options;
    return options.filter((option) =>
      normalizeAdministrativeSearch(
        [option.label, option.meta, option.searchText].filter(Boolean).join(" ")
      ).includes(normalizedQuery)
    );
  }, [normalizedQuery, options]);

  function choose(option: PlaceOption) {
    onSelect(option);
    setQuery("");
    setOpen(false);
  }

  return (
    <div className="grid min-w-0 gap-1.5">
      <span className="min-w-0 truncate text-[11px] font-medium text-cream/52">{label}</span>
      <Popover open={open && !disabled} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            disabled={disabled}
            aria-label={label}
            role="combobox"
            aria-expanded={open}
            className={cn(
              "birth-input-field-shell flex h-[50px] min-w-0 max-w-full items-center gap-3 overflow-hidden rounded-[10px] border border-gold/30 bg-white/5 px-3 text-left text-cream/40 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] outline-none transition hover:border-gold/45 hover:bg-white/[0.075] focus-visible:border-gold focus-visible:ring-4 focus-visible:ring-gold/15",
              selected && "text-cream",
              disabled && "cursor-not-allowed opacity-45"
            )}
          >
            <span
              className={cn("min-w-0 flex-1 truncate text-[15px]", !selected && "text-cream/35")}
            >
              {selected?.label ?? (disabled ? disabledText : placeholder)}
            </span>
            {loading ? (
              <LoaderCircle className="size-4 shrink-0 animate-spin text-gold" />
            ) : (
              <ChevronsUpDown className="size-4 shrink-0 text-gold-dim" />
            )}
          </button>
        </PopoverTrigger>
        <PopoverContent
          className="w-[min(22rem,calc(100vw-2rem))] p-2"
          onOpenAutoFocus={(event) => {
            event.preventDefault();
            window.requestAnimationFrame(() => inputRef.current?.focus());
          }}
          onCloseAutoFocus={() => setQuery("")}
        >
          <div className="mb-2 flex h-10 items-center gap-2 rounded-lg border border-gold/20 bg-black/20 px-3 focus-within:border-gold/45">
            <Search className="size-4 shrink-0 text-gold-dim" />
            <input
              ref={inputRef}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && filteredOptions[0]) {
                  event.preventDefault();
                  choose(filteredOptions[0]);
                }
              }}
              placeholder={placeholder}
              aria-label={label}
              autoComplete="off"
              className="min-w-0 flex-1 border-0 bg-transparent p-0 text-sm text-cream outline-none placeholder:text-cream/35"
            />
            {query ? (
              <button
                type="button"
                onClick={() => setQuery("")}
                aria-label={t("common.clear")}
                className="grid size-6 place-items-center rounded-full text-cream/35 hover:bg-white/10 hover:text-cream"
              >
                <X className="size-3.5" />
              </button>
            ) : null}
          </div>
          <div className="max-h-[280px] overflow-y-auto">
            {loading ? (
              <div className="px-3 py-6 text-center text-sm text-muted">{t("place.searching")}</div>
            ) : filteredOptions.length === 0 ? (
              <div className="px-3 py-6 text-center text-sm text-muted">{t("place.noMatches")}</div>
            ) : (
              <div role="listbox" aria-label={resultsLabel} className="grid gap-1">
                {filteredOptions.map((option) => (
                  <button
                    type="button"
                    key={option.id}
                    role="option"
                    aria-selected={selected?.id === option.id}
                    onClick={() => choose(option)}
                    className="flex w-full items-baseline justify-between gap-3 rounded-lg px-3 py-2.5 text-left text-sm text-cream/55 outline-none transition hover:bg-gold/15 hover:text-cream focus:bg-gold/15 focus:text-cream focus-visible:ring-4 focus-visible:ring-gold/15 aria-selected:bg-gold/12 aria-selected:text-cream"
                  >
                    <span className="flex min-w-0 items-center gap-2 truncate font-medium text-cream">
                      {selected?.id === option.id ? (
                        <Check className="size-3.5 shrink-0 text-gold" />
                      ) : null}
                      <span className="truncate">{option.label}</span>
                    </span>
                    {showMeta && option.meta ? (
                      <span className="max-w-[55%] truncate text-xs text-cream/45">
                        {option.meta}
                      </span>
                    ) : null}
                  </button>
                ))}
              </div>
            )}
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
}

function normalizeAdministrativeSearch(value: string) {
  return value.normalize("NFKC").toLocaleLowerCase().replace(/\s+/g, "");
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
  onRetry,
  onUseCityFallback,
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
  onRetry: () => void;
  onUseCityFallback: () => void;
  t: Translator;
}) {
  const trimmed = query.trim();
  if (!cityReady) return null;
  if (trimmed.length === 0) return null;
  if (trimmed.length < 2) return <InlineHint text={t("precisePlace.search.minLength")} />;
  if (selected) return null;
  if (!lookupStarted && !selected) return <InlineHint text={t("precisePlace.search.ready")} />;
  if (loading) return null;

  const preciseOptions = options.filter((option) => option.verificationStatus !== "city-fallback");
  if (preciseOptions.length === 0) {
    return (
      <div className="grid gap-3 rounded-[12px] border border-dashed border-gold/25 bg-white/[0.03] px-3.5 py-3.5">
        <div>
          <div className="text-sm font-medium text-cream">{t("place.flow.noExactTitle")}</div>
          <p className="m-0 mt-1 text-xs leading-relaxed text-cream/50">
            {fallbackEnabled || agentFallbackEnabled
              ? t("place.flow.noExactBody")
              : t("precisePlace.search.emptyNoFallback")}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={onRetry}
            className="inline-flex min-h-9 w-fit items-center gap-1.5 rounded-full border border-gold/30 bg-gold/10 px-3 text-xs font-medium text-gold-light transition hover:border-gold/50 hover:bg-gold/15 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-gold/15"
          >
            <RotateCcw className="size-3.5" />
            {t("place.flow.retry")}
          </button>
          <button
            type="button"
            onClick={onUseCityFallback}
            className="inline-flex min-h-9 w-fit items-center gap-1.5 rounded-full border border-gold/20 px-3 text-xs font-medium text-cream/60 transition hover:border-gold/40 hover:bg-gold/10 hover:text-gold-light focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-gold/15"
          >
            <MapPin className="size-3.5" />
            {t("place.flow.useCityPoint")}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="grid gap-2">
      {preciseOptions.map((option) => (
        <button
          key={option.id}
          type="button"
          onClick={() => onSelect(option)}
          className="group flex min-w-0 items-center gap-3 rounded-[12px] border border-gold/18 bg-white/[0.035] px-3.5 py-3 text-left outline-none transition hover:border-gold/45 hover:bg-gold/10 focus-visible:ring-4 focus-visible:ring-gold/20 data-[active=true]:border-gold data-[active=true]:bg-gold/15"
        >
          <span className="grid size-8 shrink-0 place-items-center rounded-full bg-gold/10 text-gold-light">
            <MapPin className="size-4" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate font-medium text-cream">{option.label}</span>
            <span className="mt-1 block line-clamp-2 text-xs leading-relaxed text-cream/55">
              {option.address || option.meta || t("place.flow.precisePoint")}
            </span>
          </span>
          <ChevronRight className="size-4 shrink-0 text-cream/30 transition group-hover:translate-x-0.5 group-hover:text-gold-light" />
        </button>
      ))}
      <button
        type="button"
        onClick={onUseCityFallback}
        className="inline-flex min-h-9 w-fit items-center gap-1.5 text-xs text-cream/45 underline-offset-4 transition hover:text-gold-light hover:underline focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-gold/15"
      >
        <MapPin className="size-3.5" />
        {t("place.flow.useCityPoint")}
      </button>
    </div>
  );
}

function placeReadoutFromAdministrativeOption(option: PlaceOption): PlaceReadout | null {
  if (!isFiniteNumber(option.latitude) || !isFiniteNumber(option.longitude)) return null;
  return {
    kind: "administrative",
    label: option.label,
    latitude: option.latitude,
    longitude: option.longitude,
    timezone: option.timezone
  };
}

function placeReadoutFromCityOption(option: PlaceOption): PlaceReadout | null {
  return placeReadoutFromAdministrativeOption(option);
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
    <div className="birth-input-readout rounded-[9px] border border-white/10 bg-white/[0.03] px-3.5 py-3">
      <div className="mb-2.5 flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2 text-xs font-medium text-cream/70">
          <LocateFixed className="size-3.5 shrink-0 text-gold-dim" />
          <span className="shrink-0">{t("place.flow.calculationPoint")}</span>
          {readout?.label ? (
            <span className="truncate text-cream/45">· {readout.label}</span>
          ) : null}
        </div>
        <span className="shrink-0 text-[11px] text-gold-light/75">{t(statusKey)}</span>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
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
      </div>
    </div>
  );
}

function ReadoutCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <div className="mb-1 text-[10px] font-medium text-cream/40">{label}</div>
      <div className="truncate font-mono text-[12px] text-cream">{value}</div>
    </div>
  );
}

function InlineHint({ text }: { text: string }) {
  return <div className="text-xs leading-relaxed text-cream/50">{text}</div>;
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
