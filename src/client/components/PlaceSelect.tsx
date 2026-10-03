import { useEffect, useState } from "react";
import { api } from "../api";
import type { LocaleCode } from "../i18n/messages";
import type { PlaceOption } from "../../shared/domain";

export type SelectedPlace = { place: string; label: string; timezone: string };

const copy: Record<
  LocaleCode,
  { country: string; region: string; city: string; choose: string; wholeRegion: string }
> = {
  en: {
    country: "Country",
    region: "Province / state",
    city: "City",
    choose: "Choose",
    wholeRegion: "Not sure / anywhere here"
  },
  zh: {
    country: "国家",
    region: "省 / 州",
    city: "城市",
    choose: "请选择",
    wholeRegion: "不确定 / 全省"
  },
  ja: {
    country: "国",
    region: "都道府県 / 州",
    city: "市区町村",
    choose: "選択",
    wholeRegion: "わからない / 全域"
  }
};

const selectClass =
  "h-12 w-full appearance-none rounded-2xl border border-white/12 bg-white/[0.035] px-4 text-base text-cream outline-none transition-colors [color-scheme:dark] focus:border-gold/70 disabled:opacity-40";

/** Readable name plus resolved coordinates: what every screen shows and the backend resolves. */
function placeValue(option: PlaceOption, parts: string[]): SelectedPlace | null {
  if (typeof option.latitude !== "number" || typeof option.longitude !== "number") return null;
  if (!option.timezone) return null;
  const label = parts.filter(Boolean).join(", ");
  return {
    place: `${label} | lat=${option.latitude}, lon=${option.longitude}, tz=${option.timezone}, coord=WGS84`,
    label,
    timezone: option.timezone
  };
}

/**
 * Birth place by choosing, not searching: country, then province or state, then city.
 * Where a province already resolves to a place (China), the city is optional.
 */
export function PlaceSelect({
  locale,
  error,
  onChange
}: {
  locale: LocaleCode;
  error?: string;
  onChange: (value: SelectedPlace | null) => void;
}) {
  const c = copy[locale];
  const [countries, setCountries] = useState<PlaceOption[]>([]);
  const [regions, setRegions] = useState<PlaceOption[]>([]);
  const [cities, setCities] = useState<PlaceOption[]>([]);
  const [country, setCountry] = useState("");
  const [region, setRegion] = useState("");
  const [city, setCity] = useState("");

  useEffect(() => {
    api
      .searchPlaces({ level: "country", locale, limit: 300 })
      .then((result) => {
        setCountries(result.options);
        // Most people choose their own country first: start Chinese users on China.
        if (locale === "zh" && result.options.some((option) => option.value === "China")) {
          setCountry((current) => current || "China");
        }
      })
      .catch(() => {});
  }, [locale]);

  useEffect(() => {
    setRegion("");
    setRegions([]);
    if (!country) return;
    api
      .searchPlaces({ level: "region", country, locale, limit: 500 })
      .then((result) => setRegions(result.options))
      .catch(() => {});
  }, [country, locale]);

  useEffect(() => {
    setCity("");
    setCities([]);
    if (!country || !region) return;
    api
      .searchPlaces({ level: "city", country, region, locale, limit: 500 })
      .then((result) => setCities(result.options))
      .catch(() => {});
  }, [country, region, locale]);

  const countryOption = countries.find((option) => option.value === country);
  const regionOption = regions.find((option) => option.value === region);
  const cityOption = cities.find((option) => option.value === city);
  const regionResolves = Boolean(regionOption && placeValue(regionOption, ["x"]));

  useEffect(() => {
    const countryLabel = countryOption?.label ?? "";
    if (cityOption) {
      onChange(placeValue(cityOption, [cityOption.label, regionOption?.label ?? "", countryLabel]));
    } else if (regionOption && regionResolves) {
      onChange(placeValue(regionOption, [regionOption.label, countryLabel]));
    } else {
      onChange(null);
    }
    // onChange is the parent's state setter; selection changes drive this effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cityOption, regionOption, countryOption, regionResolves]);

  return (
    <fieldset>
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="block text-sm text-cream/75">
          <span className="mb-2 block">{c.country}</span>
          <select
            value={country}
            onChange={(event) => setCountry(event.target.value)}
            className={selectClass}
          >
            <option value="">{c.choose}</option>
            {countries.map((option) => (
              <option key={option.id} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm text-cream/75">
          <span className="mb-2 block">{c.region}</span>
          <select
            value={region}
            disabled={!regions.length}
            onChange={(event) => setRegion(event.target.value)}
            className={selectClass}
          >
            <option value="">{c.choose}</option>
            {regions.map((option) => (
              <option key={option.id} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm text-cream/75">
          <span className="mb-2 block">{c.city}</span>
          <select
            value={city}
            disabled={!cities.length}
            onChange={(event) => setCity(event.target.value)}
            className={selectClass}
          >
            <option value="">{regionResolves ? c.wholeRegion : c.choose}</option>
            {cities.map((option) => (
              <option key={option.id} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      {error && <p className="mt-1.5 text-xs text-[#ffb5a4]">{error}</p>}
    </fieldset>
  );
}
