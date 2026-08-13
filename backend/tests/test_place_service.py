from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.schemas import PrecisePlaceOption
from app.services.place_service import PlaceService
from app.settings import Settings


def test_city_search_options_include_coordinates_and_timezone(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    geonames = tmp_path / "geonames.csv"
    geonames.write_text(
        "place_name,alternate_names,state,country,latitude,longitude,timezone_hours\n"
        "Shanghai,上海|Shanghai,Shanghai,China,31.2304,121.4737,8\n",
        encoding="utf-8",
    )
    service = PlaceService(SimpleNamespace(geonames_path=lambda: geonames))
    monkeypatch.setattr(service, "_timezone_for", lambda lat, lon, hours: "Asia/Shanghai")

    response = service.search("city", query="上海", limit=5)

    assert len(response.options) == 1
    option = response.options[0]
    assert option.birth_place == "Shanghai, Shanghai, China"
    assert option.latitude == 31.2304
    assert option.longitude == 121.4737
    assert option.timezone == "Asia/Shanghai"


def test_city_search_supports_dataset_alternate_name(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    geonames = tmp_path / "geonames.csv"
    geonames.write_text(
        "place_name,alternate_names,state,country,latitude,longitude,timezone_hours\n"
        "Suzhou,宿州|宿州市|Suzhou,Anhui,China,33.63611,116.97889,8\n"
        "Suzhou,苏州|苏州市|Suzhou,Jiangsu,China,31.30408,120.59538,8\n",
        encoding="utf-8",
    )
    service = PlaceService(SimpleNamespace(geonames_path=lambda: geonames))
    monkeypatch.setattr(service, "_timezone_for", lambda lat, lon, hours: "Asia/Shanghai")

    response = service.search("city", query="宿州", limit=5)

    assert len(response.options) == 1
    assert response.options[0].birth_place == "Suzhou, Anhui, China"
    assert response.options[0].latitude == 33.63611
    assert response.options[0].longitude == 116.97889


def test_china_catalog_filters_cities_by_region(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    geonames = tmp_path / "geonames.csv"
    geonames.write_text(
        "place_name,alternate_names,state,country,latitude,longitude,timezone_hours\n"
        "Suzhou,Suzhou,Anhui,China,33.63611,116.97889,8\n",
        encoding="utf-8",
    )
    service = PlaceService(SimpleNamespace(geonames_path=lambda: geonames))
    monkeypatch.setattr(service, "_timezone_for_coordinates", lambda lat, lon: "Asia/Shanghai")

    regions = service.search("region", country="China", query="安徽", limit=5)

    assert len(regions.options) == 1
    region = regions.options[0]
    assert region.value == "CN-340000"
    assert region.label == "安徽省"
    assert region.birth_place == "CN-340000"
    assert region.latitude == 31.734559
    assert region.longitude == 117.330139
    assert region.timezone == "Asia/Shanghai"

    cities = service.search("city", country="China", region=region.value, query="宿州", limit=5)

    assert len(cities.options) == 1
    city = cities.options[0]
    assert city.value == "CN-341300"
    assert city.label == "宿州市"
    assert city.birth_place == "CN-341300"
    assert city.latitude == 33.647726
    assert city.longitude == 116.96419
    assert city.timezone == "Asia/Shanghai"


def test_china_catalog_localizes_labels_without_changing_stable_ids(tmp_path) -> None:
    geonames = tmp_path / "geonames.csv"
    geonames.write_text(
        "place_name,alternate_names,state,country,latitude,longitude,timezone_hours\n"
        "Shanghai,上海|Shanghai,Shanghai,China,31.22222,121.45806,8\n"
        "Paris,Paris,Ile-de-France,France,48.8566,2.3522,1\n"
        "Tokyo,Tokyo,Tokyo,Japan,35.6762,139.6503,9\n"
        "Berlin,Berlin,Berlin,Germany,52.52,13.405,1\n"
        "New York,New York,New York,United States,40.7128,-74.006,-5\n",
        encoding="utf-8",
    )
    service = PlaceService(SimpleNamespace(geonames_path=lambda: geonames))

    zh_country = service.search("country", query="", locale="zh", limit=500).options
    en_country = service.search("country", query="", locale="en", limit=500).options
    ja_country = service.search("country", query="", locale="ja", limit=500).options
    assert next(option for option in zh_country if option.value == "China").label == "中国"
    assert next(option for option in en_country if option.value == "China").label == "China"
    assert next(option for option in ja_country if option.value == "China").label == "中国"
    assert next(option for option in zh_country if option.value == "France").label == "法国"
    assert next(option for option in zh_country if option.value == "Japan").label == "日本"
    assert next(option for option in zh_country if option.value == "United States").label == "美国"
    assert next(option for option in ja_country if option.value == "France").label == "フランス"

    zh_germany = service.search("country", query="德国", locale="zh", limit=500).options
    assert [option.value for option in zh_germany] == ["Germany"]

    zh_region = service.search("region", country="China", query="", locale="zh", limit=80).options[
        0
    ]
    en_regions = service.search("region", country="China", query="", locale="en", limit=80).options
    en_region = next(option for option in en_regions if option.value == zh_region.value)
    assert zh_region.value == en_region.value
    assert zh_region.label != en_region.label
    assert "(" in en_region.label

    zh_units = service.search(
        "city", country="China", region="CN-310000", query="", locale="zh", limit=500
    ).options
    en_units = service.search(
        "city", country="China", region="CN-310000", query="", locale="en", limit=500
    ).options
    zh_pudong = next(option for option in zh_units if option.value == "CN-310115")
    en_pudong = next(option for option in en_units if option.value == "CN-310115")
    assert zh_pudong.label == "浦东新区"
    assert en_pudong.label == "Pudong (浦东新区)"


def test_country_name_catalog_covers_the_runtime_geonames_dataset() -> None:
    service = PlaceService(Settings())

    assert set(service.country_counts) == set(service.country_names)


def test_china_catalog_city_id_resolves_for_chart_calculation(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    geonames = tmp_path / "geonames.csv"
    geonames.write_text(
        "place_name,alternate_names,state,country,latitude,longitude,timezone_hours\n",
        encoding="utf-8",
    )
    service = PlaceService(SimpleNamespace(geonames_path=lambda: geonames))
    monkeypatch.setattr(service, "_timezone_for_coordinates", lambda lat, lon: "Asia/Shanghai")

    place = service.resolve("CN-341300")

    assert place.source == "china-administrative-catalog"
    assert place.label == "宿州市, 安徽省, China"
    assert place.lat == 33.647726
    assert place.lon == 116.96419
    assert place.timezone == "Asia/Shanghai"
    assert place.matched == {
        "placeName": "宿州市",
        "alternateNames": "宿州|宿州市|suzhou",
        "state": "安徽省",
        "country": "China",
        "administrativeCode": "341300",
        "regionCode": "340000",
        "administrativeLevel": "2",
        "administrativeType": "city",
    }


def test_china_catalog_supports_region_and_direct_district_selection() -> None:
    service = PlaceService(SimpleNamespace())

    shanghai = service.resolve("CN-310000")
    pudong = service.resolve("CN-310115")

    assert shanghai.label == "上海市, China"
    assert shanghai.matched["administrativeType"] == "province"
    assert shanghai.matched["administrativeLevel"] == "1"
    assert pudong.label == "浦东新区, 上海市, China"
    assert pudong.matched["administrativeType"] == "district"
    assert pudong.matched["administrativeLevel"] == "3"


def test_china_catalog_has_stable_hierarchy_and_coordinates() -> None:
    service = PlaceService(SimpleNamespace())

    regions = service.china_regions
    region_ids = [region.id for region in regions]
    city_ids = [city.id for region in regions for city in region.children]

    assert len(regions) == 34
    assert len(set(region_ids)) == len(region_ids)
    assert len(set(city_ids)) == len(city_ids)
    assert all(region.children for region in regions)
    assert all(
        city.region_id == region.id and -90 <= city.latitude <= 90 and -180 <= city.longitude <= 180
        for region in regions
        for city in region.children
    )

    response = service.search("region", country="China", query="", limit=80)
    assert len(response.options) == 34

    shanghai_units = service.search(
        "city", country="China", region="CN-310000", query="", limit=500
    )
    assert len(shanghai_units.options) == 16
    assert any(
        option.value == "CN-310115" and option.label == "浦东新区"
        for option in shanghai_units.options
    )


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


def test_precise_search_falls_back_when_candidate_conflicts_with_selected_district(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    geonames = tmp_path / "geonames.csv"
    geonames.write_text(
        "place_name,alternate_names,state,country,latitude,longitude,timezone_hours\n"
        "Shanghai,上海|Shanghai,Shanghai,China,31.22222,121.45806,8\n"
        "Pudong,浦东|Pudong,Shanghai,China,31.23995,121.50094,8\n",
        encoding="utf-8",
    )
    service = PlaceService(
        SimpleNamespace(
            geonames_path=lambda: geonames,
            amap_place_fallback_enabled=False,
            amap_web_service_key="",
        )
    )
    monkeypatch.setattr(service, "_timezone_for", lambda lat, lon, hours: "Asia/Shanghai")

    response = service.search_precise(
        "上海市第一妇婴保健院",
        city_context="Pudong, Shanghai, China",
        agent_options=[
            PrecisePlaceOption(
                id="agent:west",
                label="上海市第一妇婴保健院西院",
                address="静安区长乐路536号, Shanghai, China",
                meta="Agent web evidence",
                source="agent",
                accuracy="poi",
                coordinateSystem="WGS84",
                latitude=31.22217,
                longitude=121.45168,
                birthPlace=(
                    "上海市第一妇婴保健院西院, Shanghai, Shanghai, China | "
                    "lat=31.22217, lon=121.45168, source=agent, accuracy=poi"
                ),
                scopeMatchStatus="conflict",
                scopeMatchReason="静安区不属于用户选择的浦东新区。",
            )
        ],
        agent_enabled=True,
        agent_attempted=True,
    )

    assert response.verification_base == "Pudong, Shanghai, China"
    assert response.rejected_count == 1
    assert response.options[0].verification_status == "city-fallback"
    assert response.options[0].city_label == "Pudong, Shanghai, China"
    assert "No precise candidate stayed within the selected city scope" in (
        response.options[0].verification_reason or ""
    )


def test_precise_search_rejects_explicit_conflicting_campus_in_selected_district(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    geonames = tmp_path / "geonames.csv"
    geonames.write_text(
        "place_name,alternate_names,state,country,latitude,longitude,timezone_hours\n"
        "Shanghai,上海|Shanghai,Shanghai,China,31.22222,121.45806,8\n"
        "Pudong,浦东|Pudong,Shanghai,China,31.23995,121.50094,8\n",
        encoding="utf-8",
    )
    service = PlaceService(
        SimpleNamespace(
            geonames_path=lambda: geonames,
            amap_place_fallback_enabled=False,
            amap_web_service_key="",
        )
    )
    monkeypatch.setattr(service, "_timezone_for", lambda lat, lon, hours: "Asia/Shanghai")

    response = service.search_precise(
        "上海市第一妇婴保健院西院",
        city_context="Pudong, Shanghai, China",
        agent_options=[
            PrecisePlaceOption(
                id="agent:west",
                label="上海市第一妇婴保健院西院",
                address="上海市静安区长乐路536号",
                meta="Agent web evidence",
                source="agent",
                accuracy="poi",
                coordinateSystem="WGS84",
                latitude=31.22217,
                longitude=121.45168,
                birthPlace=(
                    "上海市第一妇婴保健院西院, Shanghai, Shanghai, China | "
                    "lat=31.22217, lon=121.45168, source=agent, accuracy=poi"
                ),
                rawEvidence="上海市第一妇婴保健院西院，静安区长乐路536号。",
                scopeMatchStatus="conflict",
                scopeMatchReason="静安区不属于用户选择的浦东新区。",
            )
        ],
        agent_enabled=True,
        agent_attempted=True,
    )

    assert len(response.options) == 1
    assert response.options[0].verification_status == "city-fallback"
    assert response.options[0].label == "Pudong, Shanghai, China"


def test_precise_search_city_fallback_keeps_selected_chinese_municipality_district(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    geonames = tmp_path / "geonames.csv"
    geonames.write_text(
        "place_name,alternate_names,state,country,latitude,longitude,timezone_hours\n"
        "Shanghai,上海|Shanghai,Shanghai,China,31.22222,121.45806,8\n"
        "Pudong,浦东|Pudong,Shanghai,China,31.23995,121.50094,8\n",
        encoding="utf-8",
    )
    service = PlaceService(
        SimpleNamespace(
            geonames_path=lambda: geonames,
            amap_place_fallback_enabled=False,
            amap_web_service_key="",
        )
    )
    monkeypatch.setattr(service, "_timezone_for", lambda lat, lon, hours: "Asia/Shanghai")

    response = service.search_precise(
        "上海市第一妇婴保健院",
        city_context="Pudong, Shanghai, China",
        agent_enabled=True,
        agent_attempted=True,
        agent_error="agent place lookup timed out",
    )

    assert response.verification_base == "Pudong, Shanghai, China"
    assert response.agent_error == "agent place lookup timed out"
    assert response.options[0].verification_status == "city-fallback"
    assert response.options[0].label == "Pudong, Shanghai, China"


def test_precise_search_prefers_selected_district_for_broad_municipality_poi(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    geonames = tmp_path / "geonames.csv"
    geonames.write_text(
        "place_name,alternate_names,state,country,latitude,longitude,timezone_hours\n"
        "Shanghai,上海|Shanghai,Shanghai,China,31.22222,121.45806,8\n"
        "Pudong,浦东|浦东新区|P'u-tung|Pudong|pu dong xin qu|shang hai pu dong,Shanghai,China,31.23995,121.50094,8\n",
        encoding="utf-8",
    )
    service = PlaceService(
        SimpleNamespace(
            geonames_path=lambda: geonames,
            amap_place_fallback_enabled=False,
            amap_web_service_key="",
        )
    )
    monkeypatch.setattr(service, "_timezone_for", lambda lat, lon, hours: "Asia/Shanghai")

    response = service.search_precise(
        "第一妇婴保健院",
        city_context="Pudong, Shanghai, China",
        agent_options=[
            PrecisePlaceOption(
                id="agent:west",
                label="上海市第一妇婴保健院西院",
                address="上海市静安区长乐路536号",
                meta="Agent web evidence",
                source="agent",
                accuracy="poi",
                coordinateSystem="WGS84",
                latitude=31.22217,
                longitude=121.45168,
                birthPlace=(
                    "上海市第一妇婴保健院西院, Shanghai, Shanghai, China | "
                    "lat=31.22217, lon=121.45168, source=agent, accuracy=poi"
                ),
                rawEvidence="上海市第一妇婴保健院西院，静安区长乐路536号。",
                scopeMatchStatus="conflict",
                scopeMatchReason="静安区不属于用户选择的浦东新区。",
            ),
            PrecisePlaceOption(
                id="agent:east",
                label="上海市第一妇婴保健院东院",
                address="上海市浦东新区高科西路2699号",
                meta="Agent web evidence",
                source="agent",
                accuracy="poi",
                coordinateSystem="WGS84",
                latitude=31.19174,
                longitude=121.54581,
                birthPlace=(
                    "上海市第一妇婴保健院东院, Shanghai, Shanghai, China | "
                    "lat=31.19174, lon=121.54581, source=agent, accuracy=poi"
                ),
                rawEvidence="上海市第一妇婴保健院东院，浦东新区高科西路2699号。",
                scopeMatchStatus="match",
                scopeMatchReason="地址明确位于用户选择的浦东新区。",
            ),
        ],
        agent_enabled=True,
        agent_attempted=True,
    )

    assert response.verification_base == "Pudong, Shanghai, China"
    assert response.rejected_count == 1
    assert len(response.options) == 1
    assert response.options[0].label == "上海市第一妇婴保健院东院"
    assert response.options[0].verification_status == "verified"


def test_resolve_accepts_dataset_alternate_name(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    geonames = tmp_path / "geonames.csv"
    geonames.write_text(
        "place_name,alternate_names,state,country,latitude,longitude,timezone_hours\n"
        "Shanghai,上海|Shanghai,Shanghai,China,31.22222,121.45806,8\n"
        "Pudong,浦东|浦东新区|P'u-tung|Pudong|pu dong xin qu|shang hai pu dong,Shanghai,China,31.23995,121.50094,8\n",
        encoding="utf-8",
    )
    service = PlaceService(
        SimpleNamespace(
            geonames_path=lambda: geonames,
            amap_place_fallback_enabled=False,
            amap_web_service_key="",
        )
    )
    monkeypatch.setattr(service, "_timezone_for", lambda lat, lon, hours: "Asia/Shanghai")

    place = service.resolve("浦东, Shanghai, China")

    assert place.label == "Pudong, Shanghai, China"


def test_precise_search_accepts_chinese_prefecture_county_poi_with_scope_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    geonames = tmp_path / "geonames.csv"
    geonames.write_text(
        "place_name,alternate_names,state,country,latitude,longitude,timezone_hours\n"
        "Suzhou,宿州|宿州市|Suzhou,Anhui,China,33.63611,116.97889,8\n",
        encoding="utf-8",
    )
    service = PlaceService(
        SimpleNamespace(
            geonames_path=lambda: geonames,
            amap_place_fallback_enabled=False,
            amap_web_service_key="",
        )
    )
    monkeypatch.setattr(service, "_timezone_for", lambda lat, lon, hours: "Asia/Shanghai")

    response = service.search_precise(
        "泗县人民医院",
        city_context="Suzhou, Anhui, China",
        agent_options=[
            PrecisePlaceOption(
                id="agent:sixian-hospital",
                label="泗县人民医院",
                address="安徽省宿州市泗县泗城镇花园路120号",
                meta="Agent web evidence",
                source="agent",
                accuracy="poi",
                coordinateSystem="WGS84",
                latitude=33.50117,
                longitude=117.88762,
                birthPlace=(
                    "泗县人民医院, Suzhou, Anhui, China | "
                    "lat=33.50117, lon=117.88762, source=agent, accuracy=poi"
                ),
                rawEvidence="泗县人民医院位于安徽省宿州市泗县，坐标 33.50117, 117.88762。",
                scopeMatchStatus="match",
                scopeMatchReason="泗县属于用户选择的宿州市行政范围。",
            )
        ],
        agent_enabled=True,
        agent_attempted=True,
    )

    assert response.rejected_count == 0
    assert response.fallback_source == "agent"
    assert response.options[0].source == "agent"
    assert response.options[0].verification_status == "verified"
    assert response.options[0].distance_from_city_km is not None
    assert response.options[0].distance_from_city_km > 80
    assert "泗县属于用户选择的宿州市行政范围" in (response.options[0].verification_reason or "")


def test_precise_search_rejects_distant_chinese_poi_without_scope_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    geonames = tmp_path / "geonames.csv"
    geonames.write_text(
        "place_name,alternate_names,state,country,latitude,longitude,timezone_hours\n"
        "Suzhou,宿州|宿州市|Suzhou,Anhui,China,33.63611,116.97889,8\n",
        encoding="utf-8",
    )
    service = PlaceService(
        SimpleNamespace(
            geonames_path=lambda: geonames,
            amap_place_fallback_enabled=False,
            amap_web_service_key="",
        )
    )
    monkeypatch.setattr(service, "_timezone_for", lambda lat, lon, hours: "Asia/Shanghai")

    response = service.search_precise(
        "人民医院",
        city_context="Suzhou, Anhui, China",
        agent_options=[
            PrecisePlaceOption(
                id="agent:far",
                label="人民医院",
                address="花园路120号",
                meta="Agent web evidence",
                source="agent",
                accuracy="poi",
                coordinateSystem="WGS84",
                latitude=33.50117,
                longitude=117.88762,
                birthPlace="人民医院 | lat=33.50117, lon=117.88762, source=agent, accuracy=poi",
            )
        ],
        agent_enabled=True,
        agent_attempted=True,
    )

    assert response.rejected_count == 1
    assert response.options[0].verification_status == "city-fallback"


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
