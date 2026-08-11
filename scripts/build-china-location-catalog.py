#!/usr/bin/env python3
"""Build the VedicDust China administrative-location catalog.

The source files are GeoJSON.CN's national province index and one direct-child
file per province-level region. Geometry is intentionally discarded: the
intake flow needs stable administrative IDs, names, hierarchy, and centers.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any


SOURCE_URL = "https://geojson.cn/data/atlas/china"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--national", type=Path, required=True)
    parser.add_argument("--regions-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--retrieved-on", default=date.today().isoformat())
    return parser.parse_args()


def center(properties: dict[str, Any]) -> dict[str, float] | None:
    value = properties.get("center")
    if not isinstance(value, list) or len(value) != 2:
        return None
    try:
        longitude, latitude = float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None
    if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
        return None
    return {"longitude": longitude, "latitude": latitude}


def search_names(properties: dict[str, Any]) -> list[str]:
    values = [
        properties.get("pinyin"),
        properties.get("name"),
        properties.get("fullname"),
    ]
    return list(
        dict.fromkeys(
            str(value).strip() for value in values if value and str(value).strip()
        )
    )


def unit_type(full_name: str, source_level: int) -> str:
    if full_name.endswith(("自治县", "县")):
        return "county"
    if full_name.endswith(("自治州", "州", "地区")):
        return "prefecture"
    if full_name.endswith("盟"):
        return "league"
    if full_name.endswith(("旗", "自治旗")):
        return "banner"
    if full_name.endswith("区"):
        return "district"
    if full_name.endswith("市"):
        return "city"
    return "subregion"


def child_record(properties: dict[str, Any], parent_id: str) -> dict[str, Any] | None:
    code = str(properties.get("code") or "").strip()
    name = str(properties.get("name") or "").strip()
    full_name = str(properties.get("fullname") or name).strip()
    pinyin = str(properties.get("pinyin") or "").strip()
    try:
        source_level = int(properties.get("level"))
    except (TypeError, ValueError):
        return None
    point = center(properties)
    if not code or not name or point is None:
        return None
    return {
        "id": f"CN-{code}",
        "code": code,
        "parentRegionId": parent_id,
        "name": name,
        "fullName": full_name,
        "pinyin": pinyin,
        "sourceLevel": source_level,
        "unitType": unit_type(full_name, source_level),
        "searchNames": search_names(properties),
        "center": point,
    }


def build(args: argparse.Namespace) -> dict[str, Any]:
    national = json.loads(args.national.read_text(encoding="utf-8"))
    regions: list[dict[str, Any]] = []
    for feature in national.get("features", []):
        properties = feature.get("properties") or {}
        code = str(properties.get("code") or "").strip()
        name = str(properties.get("name") or "").strip()
        full_name = str(properties.get("fullname") or name).strip()
        point = center(properties)
        if not code or not name or point is None:
            continue

        region_id = f"CN-{code}"
        source_file = args.regions_dir / f"{code}.json"
        source = json.loads(source_file.read_text(encoding="utf-8"))
        children = [
            child
            for feature in source.get("features", [])
            if (child := child_record(feature.get("properties") or {}, region_id))
        ]
        children.sort(key=lambda item: (item["name"], item["code"]))
        regions.append(
            {
                "id": region_id,
                "code": code,
                "name": name,
                "fullName": full_name,
                "pinyin": str(properties.get("pinyin") or "").strip(),
                "level": "province",
                "searchNames": search_names(properties),
                "center": point,
                "children": children,
            }
        )

    regions.sort(key=lambda item: item["code"])
    return {
        "schemaVersion": "vedicdust.location-catalog.v2",
        "catalogId": "china-administrative",
        "country": {
            "id": "CN",
            "code": "CN",
            "name": "China",
            "displayName": "中国",
            "level": "country",
            "searchNames": ["China", "中国", "CN"],
        },
        "source": {
            "provider": "GeoJSON.CN",
            "dataset": "中国地图数据集",
            "version": args.version,
            "sourceUrl": SOURCE_URL,
            "dataBaseUrl": f"https://file.geojson.cn/china/{args.version}/",
            "retrievedOn": args.retrieved_on,
            "coordinateSystem": "CGCS2000",
            "coordinateReference": "EPSG:4490",
            "note": (
                "Administrative centers are used for the selected level; an optional "
                "verified POI may replace the selected center."
            ),
        },
        "regions": regions,
    }


def main() -> None:
    args = parse_args()
    payload = build(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    child_count = sum(len(region["children"]) for region in payload["regions"])
    print(f"built {len(payload['regions'])} regions and {child_count} direct children")


if __name__ == "__main__":
    main()
