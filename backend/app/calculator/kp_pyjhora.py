"""
kp_pyjhora.py — PyJHora KP (Krishnamurti Paddhati) 副星主包装器

使用固定版本 PyJHora 计算 12 宫 KP bhava-chalita cusp 的星宿主(star lord)/
副星主(sub lord),以及命盘行星本身的 KP 星宿主/副星主,供 significator 交叉核对。

这是与本仓库现有 whole-sign 宫位体系并行的、仅供生时校验证据使用的新计算通道,
不替换、也不影响 dignity/shadbala/yoga 等依赖 whole-sign 的既有产品逻辑。

Cusp 计算沿用 PyJHora 的 KP/Placidus bhava-chalita 方法(`drik.bhaava_madhya_kp`,
与 KN Rao 常用的 KP 软件口径一致)。Ayanamsa 沿用本项目全局 Lahiri 配置,不使用
PyJHora 另有的独立 "KP" ayanamsa 模式 —— 该差异在返回结果里显式记录
(`ayanamsa` 字段),以便下游证据消费方和审计者知悉这是已知但未实现的变体。
"""

import swisseph as swe
import os

from .pyjhora_compat import ensure_pyjhora_swe_compat
from .provider_runtime import configure_vedicdust_pyjhora, serialized_provider_call


# Planet ID ↔ Name mapping (PyJHora convention: RAHU=7, KETU=8)
_PLANET_NAMES = {
    0: "Sun",
    1: "Moon",
    2: "Mars",
    3: "Mercury",
    4: "Jupiter",
    5: "Venus",
    6: "Saturn",
    7: "Rahu",
    8: "Ketu",
}

_AYANAMSA_USED = "Lahiri"


def _setup_jhora():
    """Install the process-wide PyJHora compatibility layer."""
    ensure_pyjhora_swe_compat()


def _lord_name(planet_id) -> str:
    return _PLANET_NAMES.get(int(planet_id), f"P{planet_id}")


@serialized_provider_call
def calc_kp_sub_lords(
    year,
    month,
    day,
    hour,
    minute,
    lat,
    lon,
    tz_offset,
    *,
    second=0,
    planet_longitudes=None,
):
    """Calculate KP cuspal sub-lords for all 12 houses, and optionally per-planet KP lords.

    Args:
        year, month, day, hour, minute, second: Birth date/time (local)
        lat, lon: Birth coordinates
        tz_offset: Birth-time timezone offset in hours
        planet_longitudes: optional {planet_name: longitude_degrees} to also resolve
            each planet's own KP star/sub lord (used for significator cross-checking).
            Cusp calculation runs regardless of whether this is supplied.

    Returns:
        {
            "ayanamsa": "Lahiri",
            "cuspMethod": "bhava_chalita_kp_placidus",
            "houses": [
                {"house": 1, "cuspLongitude": ..., "signLord": "Mars",
                 "starLord": "Ketu", "subLord": "Venus", "kpIndex": 87},
                ...
            ],
            "planets": {"Sun": {"starLord": ..., "subLord": ..., "kpIndex": ...}, ...},
        }
    """
    _setup_jhora()

    from jhora.panchanga import drik

    ephe_dir = os.path.join(os.path.dirname(os.path.dirname(drik.__file__)), "data", "ephe")
    if os.path.isdir(ephe_dir):
        swe.set_ephe_path(ephe_dir)

    from jhora import const, utils
    from jhora.panchanga.drik import Place, bhaava_madhya_kp

    configure_vedicdust_pyjhora()

    place = Place("birth_place", lat, lon, tz_offset)
    local_hour = hour + minute / 60.0 + second / 3600.0
    jd_local = swe.julday(year, month, day, local_hour)

    # swe.houses_ex returns a 13-element cusps tuple: index 0 is an unused
    # placeholder, indices 1..12 are the 12 house cusps (house 1 = Ascendant).
    cusp_longitudes = bhaava_madhya_kp(jd_local, place)[1:13]

    houses = []
    for house_no, cusp_long in enumerate(cusp_longitudes, start=1):
        normalized = float(cusp_long) % 360.0
        lord_info = utils.kp_lords_for_longitude(house_no, normalized, levels=1)[house_no]
        kp_index, star_lord_id, sub_lord_id = lord_info
        sign_lord_id = const._house_owners_list[int(normalized // 30)]
        houses.append(
            {
                "house": house_no,
                "cuspLongitude": round(normalized, 6),
                "signLord": _lord_name(sign_lord_id),
                "starLord": _lord_name(star_lord_id),
                "subLord": _lord_name(sub_lord_id),
                "kpIndex": int(kp_index),
            }
        )

    planets_out = {}
    for planet_name, longitude in (planet_longitudes or {}).items():
        normalized = float(longitude) % 360.0
        lord_info = utils.kp_lords_for_longitude(planet_name, normalized, levels=1)[planet_name]
        kp_index, star_lord_id, sub_lord_id = lord_info
        planets_out[planet_name] = {
            "starLord": _lord_name(star_lord_id),
            "subLord": _lord_name(sub_lord_id),
            "kpIndex": int(kp_index),
        }

    return {
        "ayanamsa": _AYANAMSA_USED,
        "cuspMethod": "bhava_chalita_kp_placidus",
        "houses": houses,
        "planets": planets_out,
    }
