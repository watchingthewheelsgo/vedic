"""
chara_dasha_pyjhora.py — PyJHora Jaimini Chara Dasha 包装器

使用固定版本 PyJHora 计算 Jaimini Chara Dasha(rasi 级大运)在指定事件时刻正在
运行的 MD/AD/PD 星座(rasi),供生时校验的独立第二套大运证据使用。

方法选择:采用 PVN Rao 方法(`const.CHARA_TYPE.PVN_RAO`),因为(a)该方法性别
中立(不像 Iranganti/MindSutra 方法那样有男女命分支),(b)其作者与本仓库
rectification 规则已引用的 P.V.R. Narasimha Rao 是同一人,复用引用链一致性最好。
PyJHora 默认方法是 KN Rao,必须显式传参覆盖。

大运年长度显式锁定为 MEAN_SIDEREAL_YEAR(而非 PyJHora 默认的
TRUE_SIDEREAL_YEAR),以便与本仓库 Vimshottari 大运(`dasha_pyjhora.py`)使用
的固定恒星年长度口径保持一致、结果确定且与出生地无关。

与 Vimshottari 不同,Chara Dasha 的运期主体是星座(rasi)而非行星 —— 返回值
是 0-11 的 rasi 序号(Aries=0),由调用方按需转换为星座名。
"""

import swisseph as swe
import os
from datetime import timedelta, timezone

from .constants import SIGNS
from .pyjhora_compat import ensure_pyjhora_swe_compat
from .provider_runtime import configure_vedicdust_pyjhora, serialized_provider_call


def _setup_jhora():
    """Install the process-wide PyJHora compatibility layer."""
    ensure_pyjhora_swe_compat()


def _event_provider_coordinate(moment, fixed_offset: timezone):
    """Map an absolute event instant into the JD coordinate used by PyJHora."""

    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("Chara Dasha event moments must be timezone-aware")
    return moment.astimezone(fixed_offset).replace(tzinfo=None)


@serialized_provider_call
def calculate_chara_dasha_lords_at(
    year,
    month,
    day,
    hour,
    minute,
    lat,
    lon,
    tz_offset,
    event_moments,
    *,
    birth_second=0,
):
    """Resolve the running Jaimini Chara Dasha MD/AD/PD rasi for dated events.

    Args:
        year, month, day, hour, minute, second: Birth date/time (local)
        lat, lon, tz_offset: Birth coordinates and timezone offset in hours
        event_moments: timezone-aware datetimes to resolve running rasi periods at

    Returns:
        List (one entry per event moment) of
        {'mahaRasi': str | None, 'antarRasi': str | None, 'pratyantarRasi': str | None}
    """
    _setup_jhora()

    from jhora.panchanga import drik

    ephe_dir = os.path.join(os.path.dirname(os.path.dirname(drik.__file__)), "data", "ephe")
    if os.path.isdir(ephe_dir):
        swe.set_ephe_path(ephe_dir)

    from jhora import const
    from jhora.panchanga.drik import Place
    from jhora.horoscope.dhasa.raasi import chara

    configure_vedicdust_pyjhora()

    place = Place("birth_place", lat, lon, tz_offset)
    fixed_offset = timezone(timedelta(hours=float(tz_offset)))
    birth_jd = swe.julday(
        year,
        month,
        day,
        hour + minute / 60.0 + birth_second / 3600.0,
    )

    results = []
    for moment in event_moments:
        provider_moment = _event_provider_coordinate(moment, fixed_offset)
        event_jd = swe.julday(
            provider_moment.year,
            provider_moment.month,
            provider_moment.day,
            provider_moment.hour + provider_moment.minute / 60.0 + provider_moment.second / 3600.0,
        )
        running_ladder = chara.get_running_dhasa_for_given_date(
            event_jd,
            birth_jd,
            place,
            dhasa_level_index=const.MAHA_DHASA_DEPTH.PRATYANTARA,
            chara_method=const.CHARA_TYPE.PVN_RAO,
            dhasa_duration_type=const.DHASA_YEAR_DURATION.MEAN_SIDEREAL_YEAR,
        )
        if len(running_ladder) < 3:
            results.append({"mahaRasi": None, "antarRasi": None, "pratyantarRasi": None})
            continue
        md_rasi, ad_rasi, pd_rasi = running_ladder[2][0]
        results.append(
            {
                "mahaRasi": SIGNS[int(md_rasi) % 12],
                "antarRasi": SIGNS[int(ad_rasi) % 12],
                "pratyantarRasi": SIGNS[int(pd_rasi) % 12],
            }
        )
    return results


def rasi_drishti(rasi_index: int) -> list[int]:
    """Return the 0-indexed rasis (Aries=0) that ``rasi_index`` aspects under Jaimini rasi drishti.

    Delegates to PyJHora's own `house.raasi_drishti_of_the_raasi` table (movable signs
    aspect all fixed signs except their immediate neighbors; fixed signs aspect all
    movable signs except their immediate neighbors; dual signs mutually aspect all
    other dual signs) rather than re-deriving the rule, since this classical
    sign-to-sign aspect table is a distinct methodology from Parashari graha drishti
    and easy to get subtly wrong from memory.
    """
    _setup_jhora()

    from jhora.horoscope.chart import house

    return list(house.raasi_drishti_of_the_raasi(None, int(rasi_index) % 12))
