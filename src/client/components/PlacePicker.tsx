import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import {
  Check,
  Crosshair,
  Database,
  LocateFixed,
  LoaderCircle,
  MapPin,
  Search
} from "lucide-react";
import { api } from "../api";
import { useI18n } from "../i18n/provider";
import { cn } from "../lib/cn";
import {
  formatCoordinateNumber,
  parseCoordinateInput,
  validateCoordinateParts
} from "../lib/coordinates";
import type { PlaceOption, PlaceSearchLevel, PrecisePlaceOption } from "../../shared/domain";
import { Badge } from "./ui/badge";
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
  error
}: {
  value: string;
  onChange: (value: string) => void;
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
    window.dispatchEvent(
      new CustomEvent("birth-place-coordinates", {
        detail: readout
          ? {
              latitude: readout.latitude,
              longitude: readout.longitude,
              label: readout.label,
              exact: readout.kind === "manual" || readout.kind === "precise"
            }
          : null
      })
    );
  }, [readout]);

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
  const showPoiDiagnostics =
    Boolean(preciseSelection) ||
    poiLoading ||
    poiLookupStarted ||
    lookupState.agentAttempted ||
    Boolean(lookupState.verificationBase) ||
    Boolean(lookupState.agentError);

  return (
    <Field
      label={t("place.label")}
      icon={mode === "coordinates" ? <LocateFixed size={16} /> : <MapPin size={16} />}
      error={fieldError}
      hint={mode === "coordinates" ? t("place.coordinates.hint") : undefined}
    >
      <div className="grid gap-3">
        <div className="birth-input-mode-switch inline-grid w-fit grid-cols-2 rounded-full border border-gold/25 bg-white/5 p-1 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]">
          <button
            type="button"
            onClick={() => switchMode("city")}
            data-active={mode === "city"}
            className="inline-flex h-8 items-center justify-center gap-1.5 rounded-full px-3 text-xs font-medium text-cream/50 transition hover:text-cream focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-gold/15 data-[active=true]:bg-gold data-[active=true]:text-white"
          >
            <MapPin className="size-3.5" />
            {t("place.mode.city")}
          </button>
          <button
            type="button"
            onClick={() => switchMode("coordinates")}
            data-active={mode === "coordinates"}
            className="inline-flex h-8 items-center justify-center gap-1.5 rounded-full px-3 text-xs font-medium text-cream/50 transition hover:text-cream focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-gold/15 data-[active=true]:bg-gold data-[active=true]:text-white"
          >
            <LocateFixed className="size-3.5" />
            {t("place.mode.coordinates")}
          </button>
        </div>

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
              ) : (
                <p className="text-xs leading-relaxed text-cream/50">
                  {t("place.citySearch.help")}
                </p>
              )}
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
                      value={poiQuery}
                      onChange={(event) => updatePoiQuery(event.target.value)}
                      onKeyDown={onPoiKeyDown}
                      placeholder={t("place.poi.placeholder")}
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
                ) : null}

                {showPoiDiagnostics ? (
                  <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
                    <Badge variant="done" className="gap-1">
                      <Database className="size-3" />
                      {t("precisePlace.source.local")}
                    </Badge>
                    {lookupState.fallbackEnabled ? (
                      <Badge variant="done" className="gap-1">
                        <MapPin className="size-3" />
                        {t("precisePlace.source.amap.enabled")}
                      </Badge>
                    ) : null}
                    {lookupState.agentFallbackEnabled || lookupState.agentAttempted ? (
                      <Badge
                        variant={lookupState.agentAttempted ? "done" : "neutral"}
                        className="gap-1"
                      >
                        <Crosshair className="size-3" />
                        {lookupState.agentAttempted
                          ? t("precisePlace.source.agent.attempted")
                          : t("precisePlace.source.agent.enabled")}
                      </Badge>
                    ) : null}
                  </div>
                ) : null}

                {lookupState.verificationBase ? (
                  <div className="rounded-[10px] border border-gold/20 bg-white/5 px-3 py-2 text-xs leading-relaxed text-cream/70">
                    {t("precisePlace.verification.base")}: {lookupState.verificationBase}
                    {lookupState.rejectedCount > 0
                      ? ` · ${t("precisePlace.verification.rejected")} ${lookupState.rejectedCount}`
                      : ""}
                  </div>
                ) : null}
                {lookupState.agentError ? (
                  <div className="rounded-[10px] border border-gold/20 bg-white/5 px-3 py-2 text-xs leading-relaxed text-cream/55">
                    {t("precisePlace.source.agent.error")}: {lookupState.agentError}
                  </div>
                ) : null}
                {poiError ? (
                  <div className="rounded-[10px] border border-red/25 bg-red/10 px-4 py-3 text-sm text-red">
                    {poiError}
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
            ) : (
              <div className="flex items-center gap-2 rounded-[10px] border border-gold/15 bg-white/[0.03] px-3 py-2 text-xs leading-relaxed text-cream/45">
                <Crosshair className="size-3.5 shrink-0 text-gold-dim" />
                <span>{t("place.poi.afterCity")}</span>
              </div>
            )}
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

type LookupStepStatus = "pending" | "active" | "done" | "error";

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
  const hasAgentEvidence =
    lookupState.agentAttempted ||
    lookupState.attemptedSources.includes("agent") ||
    options.some((option) => option.source === "agent");
  const hasVerifiedResult =
    Boolean(selected) ||
    options.some((option) => option.verificationStatus === "verified") ||
    options.some((option) => option.verificationStatus === "city-fallback");
  const hasError = Boolean(poiError || lookupState.agentError);
  const localStatus: LookupStepStatus = loading ? (elapsedSeconds < 3 ? "active" : "done") : "done";
  const agentStatus: LookupStepStatus = lookupState.agentError
    ? "error"
    : hasAgentEvidence
      ? "done"
      : loading && elapsedSeconds >= 3
        ? "active"
        : "pending";
  const verifyStatus: LookupStepStatus =
    hasError && !hasOptions
      ? "error"
      : hasVerifiedResult
        ? "done"
        : loading && elapsedSeconds >= 8
          ? "active"
          : "pending";
  const caption = loading
    ? t("place.lookup.progress.running", { seconds: elapsedSeconds, timeout: 120 })
    : selected
      ? t("place.lookup.progress.selected")
      : hasOptions
        ? t("place.lookup.progress.review")
        : hasError
          ? t("place.lookup.progress.retry")
          : t("place.lookup.progress.waiting");

  const steps: Array<{ key: string; label: string; status: LookupStepStatus }> = [
    { key: "scope", label: t("place.lookup.progress.scope"), status: "done" },
    { key: "local", label: t("place.lookup.progress.local"), status: localStatus },
    { key: "agent", label: t("place.lookup.progress.agent"), status: agentStatus },
    { key: "verify", label: t("place.lookup.progress.verify"), status: verifyStatus }
  ];

  return (
    <div className="overflow-hidden rounded-[12px] border border-gold/20 bg-black/15">
      <div className="flex items-center justify-between gap-3 border-b border-gold/10 px-3 py-2">
        <div className="min-w-0 text-[11px] uppercase tracking-[1.1px] text-muted">
          {t("place.lookup.progress.title")}
        </div>
        {loading ? (
          <div className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-gold/25 bg-gold/10 px-2 py-0.5 text-[11px] text-gold-light">
            <span className="size-1.5 rounded-full bg-gold shadow-[0_0_10px_rgba(213,178,104,0.85)] animate-pulse" />
            {t("place.lookup.progress.live")}
          </div>
        ) : null}
      </div>
      <div className="grid gap-2 px-3 py-3 sm:grid-cols-4">
        {steps.map((step, index) => (
          <div key={step.key} className="relative flex min-w-0 items-center gap-2 sm:block">
            {index > 0 ? (
              <div className="absolute left-[-50%] top-[13px] hidden h-px w-full bg-gold/15 sm:block" />
            ) : null}
            <div className="relative z-10 flex items-center gap-2 sm:grid sm:justify-items-center sm:gap-1.5">
              <LookupStatusDot status={step.status} />
              <div className="min-w-0 truncate text-xs text-cream/70 sm:text-center">
                {step.label}
              </div>
              <div className="hidden text-[10px] uppercase tracking-[0.8px] text-cream/35 sm:block">
                {t(`place.lookup.progress.status.${step.status}`)}
              </div>
            </div>
          </div>
        ))}
      </div>
      <div className="border-t border-gold/10 px-3 py-2 text-xs leading-relaxed text-cream/55">
        {caption}
      </div>
    </div>
  );
}

function LookupStatusDot({ status }: { status: LookupStepStatus }) {
  if (status === "done") {
    return (
      <span className="inline-flex size-6 shrink-0 items-center justify-center rounded-full border border-gold/40 bg-gold/20 text-gold-light">
        <Check className="size-3.5" />
      </span>
    );
  }
  if (status === "active") {
    return (
      <span className="inline-flex size-6 shrink-0 items-center justify-center rounded-full border border-gold/50 bg-gold/15 text-gold-light shadow-[0_0_18px_rgba(213,178,104,0.18)]">
        <LoaderCircle className="size-3.5 animate-spin" />
      </span>
    );
  }
  if (status === "error") {
    return (
      <span className="inline-flex size-6 shrink-0 items-center justify-center rounded-full border border-red/35 bg-red/10 text-red">
        <Crosshair className="size-3.5" />
      </span>
    );
  }
  return (
    <span className="inline-flex size-6 shrink-0 items-center justify-center rounded-full border border-gold/15 bg-white/[0.03]">
      <span className="size-1.5 rounded-full bg-cream/30" />
    </span>
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
                      onSelect(option);
                      setOpen(false);
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
  if (trimmed.length === 0) return <InlineHint text={t("place.poi.prompt")} />;
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
          <div className="flex items-start justify-between gap-3">
            <span className="min-w-0 font-medium text-cream">{option.label}</span>
            <span className="shrink-0 rounded-full border border-gold/25 bg-white/5 px-2 py-0.5 text-[10px] uppercase tracking-normal text-gold-light">
              {labelForSource(option.source)}
            </span>
          </div>
          <span className="text-xs leading-relaxed text-cream/70">
            {option.address || option.meta}
          </span>
          <span className="font-mono text-[11px] text-cream/50">
            {formatCoordinateNumber(option.longitude)}, {formatCoordinateNumber(option.latitude)} ·{" "}
            {option.coordinateSystem}
          </span>
          {option.verificationReason ? (
            <span className="text-[11px] leading-relaxed text-cream/50">
              {option.verificationReason}
            </span>
          ) : null}
          {option.rawEvidence ? (
            <span className="line-clamp-2 text-[11px] leading-relaxed text-cream/50">
              {option.rawEvidence}
            </span>
          ) : null}
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

function labelForSource(source: PrecisePlaceOption["source"]) {
  if (source === "amap") return "AMap";
  if (source === "agent") return "Agent";
  if (source === "geonames-local") return "GeoNames";
  return "Manual";
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}
