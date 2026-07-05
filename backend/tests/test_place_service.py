from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.place_service import PlaceService


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
