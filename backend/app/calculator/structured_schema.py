from __future__ import annotations

from typing import Any


SIGNS = [
    "Aries",
    "Taurus",
    "Gemini",
    "Cancer",
    "Leo",
    "Virgo",
    "Libra",
    "Scorpio",
    "Sagittarius",
    "Capricorn",
    "Aquarius",
    "Pisces",
]


def build_structured_schema(
    chart: dict[str, Any],
    transit_data: dict[str, Any] | None,
    meta: dict[str, Any],
    user_info: dict[str, Any],
    input_context: dict[str, Any] | None = None,
    sensitivity_scan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the canonical machine-readable chart facts.

    `structured_data.md` remains the skill-compatible prompt artifact. This
    schema is the stable tool interface for validators and future rule engines.
    """

    lagna = chart["lagna"]
    return {
        "schemaVersion": "vedic-chart-facts/v1",
        "calculation": {
            "engine": "vedic-calculator-pyjhora",
            "ayanamsa": {
                "mode": "LAHIRI",
                "label": "Lahiri",
                "degrees": round(float(chart["ayanamsa"]), 6),
                "crossCheck": chart.get("ayanamsa_cross_check", {}),
            },
            "nodeMode": "mean",
            "houseSystem": "whole-sign",
            "coordinateSystem": "sidereal",
        },
        "subject": {
            "birthDate": meta["dob"],
            "birthTime": meta["time"],
            "birthPlace": meta["place"],
            "coordinates": {
                "lat": float(meta["lat"]),
                "lon": float(meta["lon"]),
            },
            "timezone": meta.get("timezone"),
            "timePrecision": meta.get("time_precision"),
            "timeSource": meta.get("time_source"),
            "effectivePrecision": meta.get("effective_precision"),
            "gender": user_info.get("gender"),
            "relationship": user_info.get("relationship"),
        },
        "inputContext": input_context or {},
        "sensitivityScan": sensitivity_scan or {},
        "rashi": {
            "lagna": _body("Lagna", lagna),
            "planets": {
                name: _body(name, chart["planets"][name])
                for name in [
                    "Sun",
                    "Moon",
                    "Mars",
                    "Mercury",
                    "Jupiter",
                    "Venus",
                    "Saturn",
                    "Rahu",
                    "Ketu",
                ]
            },
        },
        "houses": _houses(chart),
        "strengths": {
            "shadbala": chart.get("shadbala", {}),
            "dignity": chart.get("dignity", {}),
            "combustion": chart.get("combustion", {}),
            "digbala": chart.get("digbala", {}),
            "vargottama": chart.get("vargottama", {}),
            "vargeeyaBala": chart.get("vargeeya_bala") or {},
            "bhavaBala": chart.get("bhava_bala") or {},
            "specialLagnas": chart.get("special_lagnas") or {},
        },
        "ashtakavarga": {
            "savBySign": chart.get("sav", {}),
            "savByHouse": chart.get("sav_by_house", {}),
            "bav": chart.get("bav", {}),
            "savTotal": sum(int(chart.get("sav", {}).get(sign, 0)) for sign in SIGNS),
        },
        "dashas": {
            "system": "Vimsottari",
            "mahadashas": chart.get("dashas", []),
        },
        "divisionalCharts": _divisional_charts(chart),
        "jaimini": {
            "charaKarakas": chart.get("karakas", {}),
            "specialPoints": chart.get("special_points", {}),
        },
        "vedicAspects": {
            "planetContacts": chart.get("aspects", []),
            "houseDrishti": chart.get("house_aspects", []),
        },
        "transits": transit_data or {},
        "validation": _validation(chart),
    }


def _body(name: str, value: dict[str, Any]) -> dict[str, Any]:
    nakshatra = value.get("nakshatra") or {}
    body: dict[str, Any] = {
        "name": name,
        "sign": value.get("sign"),
        "signIndex": value.get("sign_idx"),
        "house": value.get("house"),
        "longitude": _round_or_none(value.get("longitude")),
        "degreeInSign": _round_or_none(value.get("degree")),
        "degreeText": value.get("deg_str"),
        "nakshatra": nakshatra.get("name"),
        "pada": nakshatra.get("pada"),
        "nakshatraLord": nakshatra.get("lord"),
    }
    if name != "Lagna":
        body["retrograde"] = bool(value.get("retrograde"))
        body["speed"] = _round_or_none(value.get("speed"))
    return body


def _houses(chart: dict[str, Any]) -> dict[str, Any]:
    occupants: dict[int, list[str]] = {house: [] for house in range(1, 13)}
    for name, planet in chart.get("planets", {}).items():
        house = planet.get("house")
        if isinstance(house, int):
            occupants.setdefault(house, []).append(name)

    houses: dict[str, Any] = {}
    for house in range(1, 13):
        lord_info = chart["house_lords"][house]
        sav_info = chart["sav_by_house"][house]
        houses[str(house)] = {
            "house": house,
            "sign": lord_info.get("sign"),
            "signIndex": SIGNS.index(lord_info["sign"]) if lord_info.get("sign") in SIGNS else None,
            "domain": lord_info.get("domain"),
            "lord": lord_info.get("lord"),
            "lordHouse": lord_info.get("lord_house"),
            "occupants": occupants.get(house, []),
            "sav": sav_info.get("value"),
            "aspectedBy": [
                item for item in chart.get("house_aspects", []) if item.get("target_house") == house
            ],
        }
    return houses


def _divisional_charts(chart: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, raw_chart in (chart.get("divisional_charts") or {}).items():
        if not isinstance(raw_chart, dict) or "error" in raw_chart:
            result[key] = raw_chart
            continue
        lagna = raw_chart.get("Lagna")
        lagna_idx = lagna.get("sign_idx") if isinstance(lagna, dict) else None
        result[key] = {
            name: _divisional_body(name, value, lagna_idx)
            for name, value in raw_chart.items()
            if isinstance(value, dict)
        }
    return result


def _divisional_body(name: str, value: dict[str, Any], lagna_idx: int | None) -> dict[str, Any]:
    sign_idx = value.get("sign_idx")
    house = (
        ((sign_idx - lagna_idx) % 12) + 1
        if isinstance(sign_idx, int) and isinstance(lagna_idx, int)
        else None
    )
    return {
        "name": name,
        "sign": value.get("sign"),
        "signIndex": sign_idx,
        "house": house,
        "degreeInSign": _round_or_none(value.get("degree")),
    }


def _validation(chart: dict[str, Any]) -> dict[str, Any]:
    sav_total = sum(int(chart.get("sav", {}).get(sign, 0)) for sign in SIGNS)
    rahu = chart["planets"]["Rahu"]["longitude"]
    ketu = chart["planets"]["Ketu"]["longitude"]
    node_gap = abs(rahu - ketu)
    if node_gap > 180:
        node_gap = 360 - node_gap
    return {
        "savTotal337": sav_total == 337,
        "savTotal": sav_total,
        "rahuKetuOpposition": abs(node_gap - 180) < 0.01,
        "rahuKetuGap": round(node_gap, 6),
        "planetCompleteness": len(chart.get("planets", {})) == 9,
    }


def _round_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return round(float(value), 6)
