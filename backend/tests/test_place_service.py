from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.place_service import PlaceService


def test_precise_search_uses_local_city_index_first(tmp_path) -> None:
    geonames = tmp_path / "geonames.csv"
    geonames.write_text(
        "place_name,alternate_names,state,country,latitude,longitude,timezone_hours\n"
        "Shanghai,上海|Shanghai,Shanghai,China,31.2304,121.4737,8\n",
        encoding="utf-8",
    )
    service = PlaceService(
        SimpleNamespace(
            geonames_path=lambda: geonames,
            amap_place_fallback_enabled=True,
            amap_web_service_key="not-used-when-local-matches",
        )
    )

    response = service.search_precise("上海", limit=5)

    assert response.local_count == 1
    assert response.fallback_source is None
    assert response.options[0].source == "geonames-local"
    assert response.options[0].coordinate_system == "WGS84"
    assert (
        response.options[0].birth_place == "Shanghai, Shanghai, China | lat=31.2304, lon=121.4737"
    )


def test_precise_search_stays_empty_without_configured_fallback(tmp_path) -> None:
    geonames = tmp_path / "geonames.csv"
    geonames.write_text(
        "place_name,alternate_names,state,country,latitude,longitude,timezone_hours\n"
        "Shanghai,上海|Shanghai,Shanghai,China,31.2304,121.4737,8\n",
        encoding="utf-8",
    )
    service = PlaceService(
        SimpleNamespace(
            geonames_path=lambda: geonames,
            amap_place_fallback_enabled=False,
            amap_web_service_key="",
        )
    )

    response = service.search_precise("北京协和医院", limit=5)

    assert response.options == []
    assert response.local_count == 0
    assert response.fallback_enabled is False


def test_gcj02_to_wgs84_conversion_keeps_non_china_coordinates() -> None:
    service = PlaceService(SimpleNamespace())

    lat, lon = service._gcj02_to_wgs84(34.0522, -118.2437)

    assert lat == 34.0522
    assert lon == -118.2437


def test_resolve_accepts_valid_inline_coordinates(monkeypatch: pytest.MonkeyPatch) -> None:
    service = PlaceService(SimpleNamespace())
    monkeypatch.setattr(service, "_timezone_for_coordinates", lambda lat, lon: "Asia/Shanghai")

    place = service.resolve("lat=31.2304, lon=121.4737")

    assert place.lat == 31.2304
    assert place.lon == 121.4737
    assert place.timezone == "Asia/Shanghai"
    assert place.source == "inline-coordinates"


@pytest.mark.parametrize(
    "raw_query,error",
    [
        ("lat=91, lon=121.4737", "纬度必须在 -90 到 90 之间"),
        ("lat=31.2304, lon=181", "经度必须在 -180 到 180 之间"),
        ("lat=31.2304", "经纬度格式不完整"),
    ],
)
def test_resolve_rejects_invalid_inline_coordinates(raw_query: str, error: str) -> None:
    service = PlaceService(SimpleNamespace())

    with pytest.raises(ValueError, match=error):
        service.resolve(raw_query)
