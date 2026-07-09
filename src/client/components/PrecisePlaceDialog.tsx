import { useEffect, useMemo, useState } from "react";
import {
  Check,
  Crosshair,
  Database,
  LocateFixed,
  LoaderCircle,
  MapPin,
  Search,
  X
} from "lucide-react";
import { api } from "../api";
import { useI18n } from "../i18n/provider";
import {
  formatCoordinateNumber,
  formatCoordinateValue,
  validateCoordinateParts
} from "../lib/coordinates";
import type { PrecisePlaceOption } from "../../shared/domain";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";

type PrecisePlaceDialogProps = {
  open: boolean;
  initialValue?: string;
  cityContext?: string;
  onClose: () => void;
  onConfirm: (option: PrecisePlaceOption) => void;
};

export function PrecisePlaceDialog({
  open,
  initialValue = "",
  cityContext = "",
  onClose,
  onConfirm
}: PrecisePlaceDialogProps) {
  const { t } = useI18n();
  const [query, setQuery] = useState("");
  const [options, setOptions] = useState<PrecisePlaceOption[]>([]);
  const [selected, setSelected] = useState<PrecisePlaceOption | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [fallbackEnabled, setFallbackEnabled] = useState(false);
  const [agentFallbackEnabled, setAgentFallbackEnabled] = useState(false);
  const [agentAttempted, setAgentAttempted] = useState(false);
  const [agentError, setAgentError] = useState<string | null>(null);
  const [webFallbackEnabled, setWebFallbackEnabled] = useState(false);
  const [verificationBase, setVerificationBase] = useState<string | null>(null);
  const [rejectedCount, setRejectedCount] = useState(0);
  const [manualLatitude, setManualLatitude] = useState("");
  const [manualLongitude, setManualLongitude] = useState("");

  useEffect(() => {
    if (!open) return;
    const seed = initialValue.split("|")[0]?.trim() ?? "";
    setQuery(seed);
    setOptions([]);
    setSelected(null);
    setError("");
    setFallbackEnabled(false);
    setAgentFallbackEnabled(false);
    setAgentAttempted(false);
    setAgentError(null);
    setWebFallbackEnabled(false);
    setVerificationBase(null);
    setRejectedCount(0);
  }, [initialValue, open]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [onClose, open]);

  useEffect(() => {
    if (!open) return;
    const trimmed = query.trim();
    if (trimmed.length < 2) {
      setOptions([]);
      setLoading(false);
      setError("");
      setFallbackEnabled(false);
      setAgentFallbackEnabled(false);
      setAgentAttempted(false);
      setAgentError(null);
      setWebFallbackEnabled(false);
      setVerificationBase(null);
      setRejectedCount(0);
      return;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setLoading(true);
      setError("");
      api
        .searchPrecisePlaces(
          { q: trimmed, city: cityContext.trim() || undefined, limit: 8 },
          controller.signal
        )
        .then((response) => {
          setOptions(response.options);
          setFallbackEnabled(response.fallbackEnabled);
          setAgentFallbackEnabled(response.agentFallbackEnabled);
          setAgentAttempted(response.agentAttempted);
          setAgentError(response.agentError ?? null);
          setWebFallbackEnabled(response.webFallbackEnabled);
          setVerificationBase(response.verificationBase ?? null);
          setRejectedCount(response.rejectedCount);
          setSelected((current) =>
            current && response.options.some((option) => option.id === current.id) ? current : null
          );
        })
        .catch((caught) => {
          if (controller.signal.aborted) return;
          setOptions([]);
          setError(caught instanceof Error ? caught.message : t("precisePlace.search.error"));
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 350);

    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [cityContext, open, query, t]);

  const manualValidation = useMemo(
    () => validateCoordinateParts(manualLatitude, manualLongitude),
    [manualLatitude, manualLongitude]
  );

  const activeOption = selected;
  const manualError =
    !manualValidation.ok && manualValidation.reason !== "empty"
      ? manualValidation.reason === "latitude"
        ? t("place.coordinates.error.latitude")
        : manualValidation.reason === "longitude"
          ? t("place.coordinates.error.longitude")
          : t("place.coordinates.error.format")
      : "";

  function selectOption(option: PrecisePlaceOption) {
    setSelected(option);
    setManualLatitude(formatCoordinateNumber(option.latitude));
    setManualLongitude(formatCoordinateNumber(option.longitude));
  }

  function confirmSelected() {
    if (activeOption) {
      onConfirm({
        ...activeOption,
        latitude: Number(formatCoordinateNumber(activeOption.latitude)),
        longitude: Number(formatCoordinateNumber(activeOption.longitude))
      });
      onClose();
      return;
    }
    if (manualValidation.ok) {
      const label = query.trim() || t("precisePlace.manual.label");
      onConfirm({
        id: `manual:${manualValidation.latitude}:${manualValidation.longitude}`,
        label,
        address: label,
        meta: t("precisePlace.manual.source"),
        source: "manual",
        accuracy: "coordinate",
        coordinateSystem: "WGS84",
        latitude: manualValidation.latitude,
        longitude: manualValidation.longitude,
        verificationStatus: "manual",
        birthPlace: `${label} | ${formatCoordinateValue(
          manualValidation.latitude,
          manualValidation.longitude
        )}, source=manual, accuracy=coordinate`
      });
      onClose();
    }
  }

  function nudge(deltaLat: number, deltaLon: number) {
    const current =
      activeOption ?? (manualValidation.ok ? optionFromManual(query, manualValidation) : null);
    if (!current) return;
    const latitude = Number((current.latitude + deltaLat).toFixed(6));
    const longitude = Number((current.longitude + deltaLon).toFixed(6));
    const label = current.label || query.trim() || t("precisePlace.manual.label");
    const next: PrecisePlaceOption = {
      ...current,
      id: `${current.id}:nudged:${latitude}:${longitude}`,
      label,
      latitude,
      longitude,
      accuracy: current.accuracy === "city" ? "coordinate" : current.accuracy,
      birthPlace: `${label} | ${formatCoordinateValue(latitude, longitude)}, source=${
        current.source
      }, accuracy=${current.accuracy === "city" ? "coordinate" : current.accuracy}`
    };
    setSelected(next);
    setManualLatitude(formatCoordinateNumber(latitude));
    setManualLongitude(formatCoordinateNumber(longitude));
  }

  if (!open) return null;

  const canConfirm = Boolean(activeOption) || manualValidation.ok;

  return (
    <div
      className="fixed inset-0 z-[90] grid place-items-center bg-night/45 px-3 py-6 backdrop-blur-[2px]"
      role="dialog"
      aria-modal="true"
      aria-labelledby="precise-place-title"
      onMouseDown={onClose}
    >
      <div
        className="grid max-h-[min(760px,calc(100vh-32px))] w-full max-w-[920px] overflow-hidden rounded-[14px] border border-gold/30 bg-cream shadow-[0_28px_90px_rgba(15,12,9,0.32)]"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="flex items-start justify-between gap-4 border-b border-gold/20 bg-cream-2 px-5 py-4">
          <div>
            <div className="mb-1 flex items-center gap-2 text-[11px] uppercase tracking-[1.6px] text-gold-dim">
              <LocateFixed className="size-4" />
              {t("precisePlace.eyebrow")}
            </div>
            <h2 id="precise-place-title" className="text-xl font-medium tracking-normal text-ink">
              {t("precisePlace.title")}
            </h2>
            <p className="mt-1 max-w-[620px] text-sm leading-relaxed text-body">
              {t("precisePlace.subtitle")}
            </p>
            {cityContext.trim() ? (
              <p className="mt-1 text-xs leading-relaxed text-muted">
                {t("precisePlace.cityContext")}: {cityContext.trim()}
              </p>
            ) : null}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="grid size-9 shrink-0 place-items-center rounded-full border border-gold/25 bg-cream text-muted transition hover:border-gold hover:bg-gold/10 hover:text-ink"
            aria-label={t("common.cancel")}
          >
            <X className="size-4" />
          </button>
        </header>

        <div className="grid min-h-0 gap-0 overflow-y-auto md:grid-cols-[minmax(0,1fr)_360px]">
          <section className="grid gap-4 border-b border-gold/20 p-5 md:border-b-0 md:border-r">
            <label className="grid gap-2">
              <span className="flex items-center gap-2 text-[11px] uppercase tracking-[1.1px] text-muted">
                <Search className="size-4 text-gold-dim" />
                {t("precisePlace.search.label")}
              </span>
              <div className="flex h-[50px] items-center gap-3 rounded-[10px] border border-gold/30 bg-white px-4 text-muted shadow-[inset_0_1px_0_rgba(255,255,255,0.7)] transition focus-within:border-gold focus-within:ring-4 focus-within:ring-gold/15">
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder={t("precisePlace.search.placeholder")}
                  className="min-w-0 flex-1 border-0 bg-transparent p-0 text-[15px] text-ink outline-none placeholder:text-muted"
                />
                {loading ? (
                  <LoaderCircle className="size-4 animate-spin text-gold" />
                ) : (
                  <Search className="size-4" />
                )}
              </div>
            </label>

            <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
              <Badge variant="done" className="gap-1">
                <Database className="size-3" />
                {t("precisePlace.source.local")}
              </Badge>
              <Badge variant={fallbackEnabled ? "done" : "neutral"} className="gap-1">
                <MapPin className="size-3" />
                {fallbackEnabled
                  ? t("precisePlace.source.amap.enabled")
                  : t("precisePlace.source.amap.disabled")}
              </Badge>
              <Badge
                variant={agentAttempted ? "done" : agentFallbackEnabled ? "neutral" : "neutral"}
                className="gap-1"
              >
                <Crosshair className="size-3" />
                {agentAttempted
                  ? t("precisePlace.source.agent.attempted")
                  : agentFallbackEnabled
                    ? t("precisePlace.source.agent.enabled")
                    : t("precisePlace.source.agent.disabled")}
              </Badge>
              <Badge variant={webFallbackEnabled ? "done" : "neutral"} className="gap-1">
                <Search className="size-3" />
                {webFallbackEnabled
                  ? t("precisePlace.source.web.enabled")
                  : t("precisePlace.source.web.disabled")}
              </Badge>
            </div>
            {verificationBase ? (
              <div className="rounded-[10px] border border-gold/20 bg-cream-2 px-3 py-2 text-xs leading-relaxed text-body">
                {t("precisePlace.verification.base")}: {verificationBase}
                {rejectedCount > 0
                  ? ` · ${t("precisePlace.verification.rejected")} ${rejectedCount}`
                  : ""}
              </div>
            ) : null}
            {agentError ? (
              <div className="rounded-[10px] border border-gold/20 bg-cream-2 px-3 py-2 text-xs leading-relaxed text-muted">
                {t("precisePlace.source.agent.error")}: {agentError}
              </div>
            ) : null}

            <div className="grid gap-2">
              {error ? (
                <div className="rounded-[10px] border border-red/25 bg-red/10 px-4 py-3 text-sm text-red">
                  {error}
                </div>
              ) : null}
              {query.trim().length < 2 ? (
                <EmptyState text={t("precisePlace.search.minLength")} />
              ) : loading ? (
                <EmptyState text={t("precisePlace.search.loading")} />
              ) : options.length === 0 ? (
                <EmptyState
                  text={
                    fallbackEnabled || webFallbackEnabled
                      ? t("precisePlace.search.empty")
                      : t("precisePlace.search.emptyNoFallback")
                  }
                />
              ) : (
                options.map((option) => (
                  <button
                    key={option.id}
                    type="button"
                    onClick={() => selectOption(option)}
                    data-active={selected?.id === option.id}
                    className="grid gap-1 rounded-[10px] border border-gold/20 bg-white px-4 py-3 text-left shadow-sm transition hover:border-gold/50 hover:bg-gold/10 data-[active=true]:border-gold data-[active=true]:bg-gold/15"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <span className="font-medium text-ink">{option.label}</span>
                      <span className="shrink-0 rounded-full border border-gold/25 bg-cream px-2 py-0.5 text-[10px] uppercase tracking-normal text-gold-dim">
                        {labelForSource(option.source)}
                      </span>
                    </div>
                    <span className="text-xs leading-relaxed text-body">
                      {option.address || option.meta}
                    </span>
                    <span className="font-mono text-[11px] text-muted">
                      {formatCoordinateNumber(option.longitude)},{" "}
                      {formatCoordinateNumber(option.latitude)} · {option.coordinateSystem}
                    </span>
                    {option.verificationReason ? (
                      <span className="text-[11px] leading-relaxed text-muted">
                        {option.verificationReason}
                      </span>
                    ) : null}
                    {option.rawEvidence ? (
                      <span className="line-clamp-2 text-[11px] leading-relaxed text-muted">
                        {option.rawEvidence}
                      </span>
                    ) : null}
                  </button>
                ))
              )}
            </div>
          </section>

          <aside className="grid gap-4 bg-[#fff9ed] p-5">
            <div className="rounded-[12px] border border-gold/25 bg-cream p-3">
              <div className="mb-3 flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 text-[11px] uppercase tracking-[1.1px] text-muted">
                  <Crosshair className="size-4 text-gold-dim" />
                  {t("precisePlace.confirmMap")}
                </div>
                {activeOption ? <Badge variant="gold">{activeOption.accuracy}</Badge> : null}
              </div>
              <div className="relative aspect-[4/3] overflow-hidden rounded-[10px] border border-gold/25 bg-[linear-gradient(90deg,rgba(201,169,110,0.12)_1px,transparent_1px),linear-gradient(0deg,rgba(201,169,110,0.12)_1px,transparent_1px)] bg-[size:28px_28px]">
                <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(201,169,110,0.24),transparent_44%)]" />
                <div className="absolute left-1/2 top-1/2 grid size-10 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border border-gold bg-cream text-gold shadow-[0_8px_24px_rgba(44,31,15,0.18)]">
                  <MapPin className="size-5 fill-gold/20" />
                </div>
                <button
                  type="button"
                  onClick={() => nudge(0.001, 0)}
                  className="absolute left-1/2 top-3 grid size-8 -translate-x-1/2 place-items-center rounded-full border border-gold/30 bg-cream/90 text-xs text-gold-dim hover:bg-gold/10"
                >
                  ↑
                </button>
                <button
                  type="button"
                  onClick={() => nudge(-0.001, 0)}
                  className="absolute bottom-3 left-1/2 grid size-8 -translate-x-1/2 place-items-center rounded-full border border-gold/30 bg-cream/90 text-xs text-gold-dim hover:bg-gold/10"
                >
                  ↓
                </button>
                <button
                  type="button"
                  onClick={() => nudge(0, -0.001)}
                  className="absolute left-3 top-1/2 grid size-8 -translate-y-1/2 place-items-center rounded-full border border-gold/30 bg-cream/90 text-xs text-gold-dim hover:bg-gold/10"
                >
                  ←
                </button>
                <button
                  type="button"
                  onClick={() => nudge(0, 0.001)}
                  className="absolute right-3 top-1/2 grid size-8 -translate-y-1/2 place-items-center rounded-full border border-gold/30 bg-cream/90 text-xs text-gold-dim hover:bg-gold/10"
                >
                  →
                </button>
              </div>
            </div>

            <div className="grid gap-3">
              <div className="text-[11px] uppercase tracking-[1.1px] text-muted">
                {t("precisePlace.manual.heading")}
              </div>
              <div className="grid grid-cols-2 gap-3">
                <label className="grid gap-1.5">
                  <span className="text-[11px] uppercase tracking-[1px] text-muted">
                    {t("place.coordinates.longitude")}
                  </span>
                  <input
                    value={manualLongitude}
                    onChange={(event) => {
                      setManualLongitude(event.target.value);
                      setSelected(null);
                    }}
                    inputMode="decimal"
                    placeholder={t("place.coordinates.longitude.placeholder")}
                    className="h-11 rounded-[10px] border border-gold/30 bg-white px-3 text-[14px] text-ink outline-none transition placeholder:text-muted focus:border-gold focus:ring-4 focus:ring-gold/15"
                  />
                </label>
                <label className="grid gap-1.5">
                  <span className="text-[11px] uppercase tracking-[1px] text-muted">
                    {t("place.coordinates.latitude")}
                  </span>
                  <input
                    value={manualLatitude}
                    onChange={(event) => {
                      setManualLatitude(event.target.value);
                      setSelected(null);
                    }}
                    inputMode="decimal"
                    placeholder={t("place.coordinates.latitude.placeholder")}
                    className="h-11 rounded-[10px] border border-gold/30 bg-white px-3 text-[14px] text-ink outline-none transition placeholder:text-muted focus:border-gold focus:ring-4 focus:ring-gold/15"
                  />
                </label>
              </div>
              {manualError ? (
                <div className="text-xs leading-relaxed text-red">{manualError}</div>
              ) : null}
            </div>

            <div className="rounded-[10px] border border-gold/25 bg-cream px-4 py-3 text-xs leading-relaxed text-body">
              {activeOption ? (
                <>
                  <div className="mb-1 font-medium text-ink">{activeOption.label}</div>
                  <div>
                    {formatCoordinateNumber(activeOption.longitude)},{" "}
                    {formatCoordinateNumber(activeOption.latitude)} ·{" "}
                    {activeOption.coordinateSystem}
                  </div>
                  {activeOption.verificationReason ? (
                    <div className="mt-1 text-muted">{activeOption.verificationReason}</div>
                  ) : null}
                </>
              ) : (
                t("precisePlace.confirm.empty")
              )}
            </div>
          </aside>
        </div>

        <footer className="flex flex-col-reverse gap-3 border-t border-gold/20 bg-cream-2 px-5 py-4 sm:flex-row sm:items-center sm:justify-end">
          <Button type="button" variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="button" onClick={confirmSelected} disabled={!canConfirm}>
            <Check className="size-4" />
            {t("precisePlace.confirm")}
          </Button>
        </footer>
      </div>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="rounded-[10px] border border-dashed border-gold/30 bg-cream-2 px-4 py-8 text-center text-sm text-muted">
      {text}
    </div>
  );
}

function labelForSource(source: PrecisePlaceOption["source"]) {
  if (source === "amap") return "AMap";
  if (source === "agent") return "Agent";
  if (source === "web") return "Web";
  if (source === "geonames-local") return "GeoNames";
  return "Manual";
}

function optionFromManual(
  query: string,
  validation: Extract<ReturnType<typeof validateCoordinateParts>, { ok: true }>
): PrecisePlaceOption {
  const label = query.trim() || "Manual coordinates";
  return {
    id: `manual:${validation.latitude}:${validation.longitude}`,
    label,
    address: label,
    meta: "Manual",
    source: "manual",
    accuracy: "coordinate",
    coordinateSystem: "WGS84",
    latitude: validation.latitude,
    longitude: validation.longitude,
    verificationStatus: "manual",
    birthPlace: `${label} | ${validation.value}, source=manual, accuracy=coordinate`
  };
}
