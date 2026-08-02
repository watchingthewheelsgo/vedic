"""
dasha_pyjhora.py — PyJHora Vimsottari Dasha 包装器
使用固定版本 PyJHora 计算 Vimshottari 大运、小运和三级运日期。
跨桌面软件误差必须由独立、可复现的 golden fixture 验证。

输出 VedicDust engine 消费的分层时间轴结构。
"""

import swisseph as swe
import os
import sys
from datetime import datetime, timedelta, timezone

import pytz

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

# Standard Vimsottari Dasha durations
_DASHA_YEARS = {
    "Ketu": 7,
    "Venus": 20,
    "Sun": 6,
    "Moon": 10,
    "Mars": 7,
    "Rahu": 18,
    "Jupiter": 16,
    "Saturn": 19,
    "Mercury": 17,
}

# Standard Vimsottari Antardasha order: from dasha lord, cycle through 9 planets
_DASHA_ORDER = ["Ketu", "Venus", "Sun", "Moon", "Mars", "Rahu", "Jupiter", "Saturn", "Mercury"]
_DASHA_YEAR_DURATION_DAYS = 365.256364


def _lock_profile_dasha_year(const, vimsottari) -> object:
    """Apply the Calculation Profile's mean-sidereal year to PyJHora globals/calls."""

    if abs(float(const.sidereal_year) - _DASHA_YEAR_DURATION_DAYS) > 1e-9:
        raise RuntimeError("PyJHora sidereal-year constant differs from the Calculation Profile")
    vimsottari.year_duration = _DASHA_YEAR_DURATION_DAYS
    return const.DHASA_YEAR_DURATION.MEAN_SIDEREAL_YEAR


def _period_is_current(start: datetime, end: datetime, moment: datetime) -> bool:
    """Use half-open periods so a boundary instant belongs to exactly one period."""

    return start <= moment < end


def _datetime_from_julian_parts(year, month, day, fractional_hour) -> datetime:
    """Preserve the local civil-time precision returned by PyJHora/Swiss Ephemeris."""

    midnight = datetime(int(year), int(month), int(day))
    return midnight + timedelta(hours=float(fractional_hour))


def _provider_instant(moment: datetime, fixed_offset: timezone) -> datetime:
    """Interpret a PyJHora period JD in its birth-offset coordinate system."""

    return moment.replace(tzinfo=fixed_offset).astimezone(timezone.utc)


def _display_period_moment(
    moment: datetime,
    fixed_offset: timezone,
    timezone_id: str | None,
) -> datetime:
    instant = _provider_instant(moment, fixed_offset)
    if timezone_id:
        return instant.astimezone(pytz.timezone(timezone_id))
    return instant.astimezone(fixed_offset)


def _event_provider_coordinate(moment: datetime, fixed_offset: timezone) -> datetime:
    """Map an absolute event instant into the JD coordinate used by PyJHora."""

    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("Vimshottari event moments must be timezone-aware")
    return moment.astimezone(fixed_offset).replace(tzinfo=None)


def _period_lord_at(jd: float, starts) -> object | None:
    """Resolve a half-open period without relying on PyJHora's private helper."""

    for lord, start_jd in reversed(list(starts.items())):
        if float(start_jd) <= jd:
            return lord
    return None


def _setup_jhora():
    """Install the process-wide PyJHora compatibility layer."""
    ensure_pyjhora_swe_compat()


@serialized_provider_call
def calculate_dasha_fixed(
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
    include_pratyantara=True,
    as_of=None,
    timezone_id=None,
):
    """Calculate Vimsottari Dasha using PyJHora's precise algorithm.

    Args:
        year, month, day: Birth date
        hour, minute, second: Birth time (local)
        lat, lon: Birth coordinates
        tz_offset: Birth-time timezone offset in hours (e.g., 8.0 for Asia/Shanghai)
        timezone_id: IANA timezone used to render each boundary in its actual civil offset

    Returns:
        List of dasha dicts consumed by the engine:
        [{'planet': str, 'start': 'YYYY-MM', 'end': 'YYYY-MM', 'years': float,
          'is_current': bool, 'antardashas': [...]}, ...]
    """
    _setup_jhora()

    # Set ephemeris path
    from jhora.panchanga import drik

    ephe_dir = os.path.join(os.path.dirname(os.path.dirname(drik.__file__)), "data", "ephe")
    if os.path.isdir(ephe_dir):
        swe.set_ephe_path(ephe_dir)

    # Configure ayanamsa (same as ashtakavarga_pyjhora)
    from jhora import const
    from jhora.panchanga.drik import Place
    from jhora.horoscope.dhasa.graha import vimsottari

    configure_vedicdust_pyjhora()
    dasha_duration_type = _lock_profile_dasha_year(const, vimsottari)

    # Create Place and JD (local time, same as ashtakavarga)
    place = Place("birth_place", lat, lon, tz_offset)
    local_hour = hour + minute / 60.0 + second / 3600.0
    jd_local = swe.julday(year, month, day, local_hour)

    # ── 1. Get Mahadasha start dates ──
    md_dict = vimsottari.vimsottari_mahadasa(jd_local, place)
    # md_dict: OrderedDict {planet_id: start_jd}

    # ── 2. Get Antardasha entries ──
    try:
        result = vimsottari.get_vimsottari_dhasa_bhukthi(
            jd_local,
            place,
            dhasa_level_index=2,  # ANTARA level
            dhasa_duration_type=dasha_duration_type,
        )
        _, ad_entries = result[0], result[1]
    except Exception as exc:
        raise RuntimeError("PyJHora failed to calculate Vimshottari Antardasha") from exc

    if include_pratyantara:
        try:
            _, pd_entries = vimsottari.get_vimsottari_dhasa_bhukthi(
                jd_local,
                place,
                dhasa_level_index=3,
                dhasa_duration_type=dasha_duration_type,
            )
        except Exception as exc:
            raise RuntimeError("PyJHora failed to calculate Vimshottari Pratyantardasha") from exc
    else:
        pd_entries = []

    # Build local civil-time lookups while retaining legacy date summaries.
    ad_lookup = {}
    for entry in ad_entries:
        md_id, ad_id = entry[0]
        y, m, d, h = entry[1]
        ad_start = _datetime_from_julian_parts(y, m, d, h)
        ad_planet = _PLANET_NAMES.get(ad_id, f"P{ad_id}")

        if md_id not in ad_lookup:
            ad_lookup[md_id] = []
        ad_lookup[md_id].append((ad_planet, ad_start))

    pd_lookup = {}
    for entry in pd_entries:
        md_id, ad_id, pd_id = entry[0]
        y, m, d, h = entry[1]
        pd_start = _datetime_from_julian_parts(y, m, d, h)
        pd_lookup.setdefault((md_id, ad_id), []).append(
            (_PLANET_NAMES.get(pd_id, f"P{pd_id}"), pd_start)
        )

    # ── 3. Build output ──
    calculation_moment = as_of or datetime.now(timezone.utc)
    if calculation_moment.tzinfo is None:
        raise ValueError("Vimshottari as_of must be timezone-aware")
    local_offset = timezone(timedelta(hours=float(tz_offset)))
    now_utc = calculation_moment.astimezone(timezone.utc)
    md_items = list(md_dict.items())
    dashas = []

    for i, (pid, start_jd) in enumerate(md_items):
        planet = _PLANET_NAMES.get(pid, f"P{pid}")
        years = _DASHA_YEARS.get(planet, 0)

        # Start date
        sy, sm, sd, sh = swe.revjul(start_jd)
        start_dt = _datetime_from_julian_parts(sy, sm, sd, sh)
        # End date = next dasha's start, or start + years
        if i + 1 < len(md_items):
            next_jd = list(md_dict.values())[i + 1]
            ey, em, ed, eh = swe.revjul(next_jd)
            end_dt = _datetime_from_julian_parts(ey, em, ed, eh)
        else:
            end_dt = start_dt + timedelta(days=years * _DASHA_YEAR_DURATION_DAYS)
        start_display = _display_period_moment(start_dt, local_offset, timezone_id)
        end_display = _display_period_moment(end_dt, local_offset, timezone_id)
        start_str = start_display.strftime("%Y-%m")
        end_str = end_display.strftime("%Y-%m")
        is_current = _period_is_current(
            _provider_instant(start_dt, local_offset),
            _provider_instant(end_dt, local_offset),
            now_utc,
        )

        # Build antardashas
        antardashas = []
        ad_list = ad_lookup.get(pid, [])
        for j, (ad_planet, ad_start_dt) in enumerate(ad_list):
            # End = next antardasha's start
            if j + 1 < len(ad_list):
                ad_end_dt = ad_list[j + 1][1]
            else:
                ad_end_dt = end_dt
            ad_start_display = _display_period_moment(ad_start_dt, local_offset, timezone_id)
            ad_end_display = _display_period_moment(ad_end_dt, local_offset, timezone_id)
            ad_start_str = ad_start_display.strftime("%Y-%m-%d")
            ad_end_str = ad_end_display.strftime("%Y-%m-%d")
            ad_is_current = _period_is_current(
                _provider_instant(ad_start_dt, local_offset),
                _provider_instant(ad_end_dt, local_offset),
                now_utc,
            )

            ad_id = next(
                (planet_id for planet_id, name in _PLANET_NAMES.items() if name == ad_planet),
                None,
            )
            pratyantardashas = []
            pd_list = pd_lookup.get((pid, ad_id), []) if ad_id is not None else []
            for k, (pd_planet, pd_start_dt) in enumerate(pd_list):
                pd_end_dt = pd_list[k + 1][1] if k + 1 < len(pd_list) else ad_end_dt
                pd_start_display = _display_period_moment(pd_start_dt, local_offset, timezone_id)
                pd_end_display = _display_period_moment(pd_end_dt, local_offset, timezone_id)
                pratyantardashas.append(
                    {
                        "planet": pd_planet,
                        "start": pd_start_display.strftime("%Y-%m-%d"),
                        "end": pd_end_display.strftime("%Y-%m-%d"),
                        "start_exact": pd_start_display.isoformat(timespec="seconds"),
                        "end_exact": pd_end_display.isoformat(timespec="seconds"),
                        "is_current": _period_is_current(
                            _provider_instant(pd_start_dt, local_offset),
                            _provider_instant(pd_end_dt, local_offset),
                            now_utc,
                        ),
                    }
                )

            antardashas.append(
                {
                    "planet": ad_planet,
                    "start": ad_start_str,
                    "end": ad_end_str,
                    "start_exact": ad_start_display.isoformat(timespec="seconds"),
                    "end_exact": ad_end_display.isoformat(timespec="seconds"),
                    "is_current": ad_is_current,
                    "pratyantardashas": pratyantardashas,
                }
            )

        dashas.append(
            {
                "planet": planet,
                "start": start_str,
                "end": end_str,
                "start_exact": start_display.isoformat(timespec="seconds"),
                "end_exact": end_display.isoformat(timespec="seconds"),
                "years": round(years, 1),
                "is_current": is_current,
                "antardashas": antardashas,
            }
        )

    return dashas


@serialized_provider_call
def calculate_dasha_lords_at(
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
    """Resolve MD/AD/PD lords for dated events without expanding full timelines."""

    _setup_jhora()
    from jhora import const
    from jhora.panchanga import drik
    from jhora.panchanga.drik import Place
    from jhora.horoscope.dhasa.graha import vimsottari

    configure_vedicdust_pyjhora()
    _lock_profile_dasha_year(const, vimsottari)
    place = Place("birth_place", lat, lon, tz_offset)
    fixed_offset = timezone(timedelta(hours=float(tz_offset)))
    birth_jd = swe.julday(
        year,
        month,
        day,
        hour + minute / 60.0 + birth_second / 3600.0,
    )
    mahadashas = vimsottari.vimsottari_mahadasa(birth_jd, place)
    results = []
    for moment in event_moments:
        provider_moment = _event_provider_coordinate(moment, fixed_offset)
        event_jd = swe.julday(
            provider_moment.year,
            provider_moment.month,
            provider_moment.day,
            provider_moment.hour + provider_moment.minute / 60.0 + provider_moment.second / 3600.0,
        )
        md_id = _period_lord_at(event_jd, mahadashas)
        if md_id is None:
            results.append({"mahadasha": None, "antardasha": None, "pratyantardasha": None})
            continue
        antardashas = vimsottari._vimsottari_bhukti(md_id, mahadashas[md_id])
        ad_id = _period_lord_at(event_jd, antardashas)
        if ad_id is None:
            results.append(
                {
                    "mahadasha": _PLANET_NAMES.get(md_id),
                    "antardasha": None,
                    "pratyantardasha": None,
                }
            )
            continue
        pratyantardashas = vimsottari._vimsottari_antara(
            md_id,
            ad_id,
            antardashas[ad_id],
        )
        pd_id = _period_lord_at(event_jd, pratyantardashas)
        results.append(
            {
                "mahadasha": _PLANET_NAMES.get(md_id),
                "antardasha": _PLANET_NAMES.get(ad_id),
                "pratyantardasha": _PLANET_NAMES.get(pd_id),
            }
        )
    return results
