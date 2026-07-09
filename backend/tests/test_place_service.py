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
    assert response.options[0].birth_place == (
        "Shanghai, Shanghai, China | lat=31.2304, lon=121.4737, "
        "source=geonames-local, accuracy=city"
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


def test_precise_search_verifies_web_candidate_against_city(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    geonames = tmp_path / "geonames.csv"
    geonames.write_text(
        "place_name,alternate_names,state,country,latitude,longitude,timezone_hours\n"
        "Beijing,北京|Beijing,Beijing,China,39.9042,116.4074,8\n",
        encoding="utf-8",
    )
    service = PlaceService(
        SimpleNamespace(
            geonames_path=lambda: geonames,
            amap_place_fallback_enabled=False,
            amap_web_service_key="",
            web_place_search_enabled=True,
        )
    )
    monkeypatch.setattr(
        service,
        "_web_search_get",
        lambda query: (
            "<html>Beijing Union Medical College Hospital latitude 39.9149, "
            "longitude 116.4136</html>",
            "https://example.test/search?q=beijing",
        ),
    )

    response = service.search_precise(
        "北京协和医院",
        city_context="Beijing, Beijing, China",
        limit=5,
    )

    assert response.verification_base == "Beijing, Beijing, China"
    assert response.rejected_count == 0
    assert response.fallback_source == "web"
    assert response.web_fallback_enabled is True
    assert response.options[0].source == "web"
    assert response.options[0].verification_status == "verified"
    assert response.options[0].distance_from_city_km is not None
    assert response.options[0].distance_from_city_km < 2
    assert response.options[0].birth_place.startswith("北京协和医院, Beijing, Beijing, China")


def test_precise_search_rejects_web_candidate_outside_city_scope(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    geonames = tmp_path / "geonames.csv"
    geonames.write_text(
        "place_name,alternate_names,state,country,latitude,longitude,timezone_hours\n"
        "Beijing,北京|Beijing,Beijing,China,39.9042,116.4074,8\n",
        encoding="utf-8",
    )
    service = PlaceService(
        SimpleNamespace(
            geonames_path=lambda: geonames,
            amap_place_fallback_enabled=False,
            amap_web_service_key="",
            web_place_search_enabled=True,
        )
    )
    monkeypatch.setattr(
        service,
        "_web_search_get",
        lambda query: (
            "<html>Wrong candidate latitude 22.5431, longitude 114.0579</html>",
            "https://example.test/search?q=wrong",
        ),
    )

    response = service.search_precise(
        "北京协和医院",
        city_context="Beijing, Beijing, China",
        limit=5,
    )

    assert response.rejected_count == 1
    assert response.options[0].verification_status == "city-fallback"
    assert response.options[0].source == "geonames-local"
    assert response.options[0].accuracy == "city"
    assert response.options[0].latitude == 39.9042
    assert response.options[0].longitude == 116.4074


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
    assert place.accuracy == "coordinate"
    assert place.radius_km == 0.25


def test_resolve_parses_inline_coordinate_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    service = PlaceService(SimpleNamespace())
    monkeypatch.setattr(service, "_timezone_for_coordinates", lambda lat, lon: "Asia/Shanghai")

    place = service.resolve("Shanghai | lat=31.2304, lon=121.4737, source=amap, accuracy=poi")

    assert place.source == "amap"
    assert place.accuracy == "poi"
    assert place.confidence == "high"
    assert place.radius_km == 0.3


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
