#!/usr/bin/env python3
"""Build localized country names for the GeoNames country vocabulary.

The runtime place dataset uses English country names as stable values. This
builder maps that vocabulary to Unicode CLDR territory codes, then emits the
localized labels used by the intake UI. No CLDR parsing or network access is
performed at application runtime.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from pathlib import Path
from typing import Any


CLDR_REPOSITORY = "https://github.com/unicode-org/cldr-json"

# GeoNames and CLDR occasionally use different official or historical English
# names. These are source-vocabulary crosswalks, not application search aliases.
GEONAMES_TO_CLDR_CODE = {
    "Bonaire, Saint Eustatius and Saba": "BQ",
    "Cabo Verde": "CV",
    "Cocos Islands": "CC",
    "Democratic Republic of the Congo": "CD",
    "Hong Kong": "HK",
    "Ivory Coast": "CI",
    "Macao": "MO",
    "Myanmar": "MM",
    "Palestinian Territory": "PS",
    "Pitcairn": "PN",
    "Republic of the Congo": "CG",
    "Saint Vincent and the Grenadines": "VC",
    "South Georgia and the South Sandwich Islands": "GS",
    "Turkey": "TR",
    "Vatican": "VA",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--geonames", type=Path, required=True)
    parser.add_argument(
        "--cldr-dir",
        type=Path,
        required=True,
        help="Directory containing territories-en.json, territories-zh.json, and territories-ja.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cldr-revision", required=True)
    return parser.parse_args()


def normalized_name(value: str) -> str:
    value = value.replace("&", " and ")
    value = re.sub(r"^The\s+", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\bSt[.]?\s+", "Saint ", value, flags=re.IGNORECASE)
    value = "".join(
        character
        for character in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(character)
    )
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def load_cldr_territories(path: Path, locale: str) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    territories = payload["main"][locale]["localeDisplayNames"]["territories"]
    return {
        code: str(name)
        for code, name in territories.items()
        if "-alt-" not in code and len(code) == 2
    }


def cldr_english_index(path: Path) -> dict[str, set[str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    territories = payload["main"]["en"]["localeDisplayNames"]["territories"]
    index: dict[str, set[str]] = {}
    for raw_code, raw_name in territories.items():
        code = raw_code.split("-alt-", 1)[0]
        if len(code) != 2:
            continue
        index.setdefault(normalized_name(str(raw_name)), set()).add(code)
    return index


def geonames_countries(path: Path) -> list[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return sorted(
            {
                country
                for row in csv.DictReader(handle)
                if (country := str(row.get("country") or "").strip())
            }
        )


def build(args: argparse.Namespace) -> dict[str, Any]:
    localized = {
        locale: load_cldr_territories(
            args.cldr_dir / f"territories-{locale}.json", locale
        )
        for locale in ("en", "zh", "ja")
    }
    english_index = cldr_english_index(args.cldr_dir / "territories-en.json")
    countries: list[dict[str, Any]] = []
    unresolved: list[str] = []

    for source_name in geonames_countries(args.geonames):
        code = GEONAMES_TO_CLDR_CODE.get(source_name)
        if not code:
            matches = english_index.get(normalized_name(source_name), set())
            if len(matches) == 1:
                code = next(iter(matches))
        if not code or any(code not in localized[locale] for locale in localized):
            unresolved.append(source_name)
            continue

        names = {locale: localized[locale][code] for locale in localized}
        search_names = list(dict.fromkeys([source_name, code, *names.values()]))
        countries.append(
            {
                "sourceName": source_name,
                "territoryCode": code,
                "names": names,
                "searchNames": search_names,
            }
        )

    if unresolved:
        raise ValueError(f"Unresolved GeoNames countries: {', '.join(unresolved)}")

    return {
        "schemaVersion": "vedicdust.country-names.v1",
        "source": {
            "provider": "Unicode Consortium",
            "dataset": "Unicode CLDR JSON territory names",
            "repository": CLDR_REPOSITORY,
            "revision": args.cldr_revision,
            "locales": ["en", "zh", "ja"],
            "note": "GeoNames English names remain stable values; CLDR names are display labels.",
        },
        "countries": countries,
    }


def main() -> None:
    args = parse_args()
    payload = build(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"built {len(payload['countries'])} localized country names")


if __name__ == "__main__":
    main()
