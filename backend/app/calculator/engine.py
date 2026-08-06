"""VedicDust deterministic chart engine.

Swiss Ephemeris owns sidereal astronomy. Pinned PyJHora adapters own the
declared varga, Ashtakavarga, Shadbala, and Vimshottari provider calculations.
Required providers fail fast; this module contains no alternate chart or Dasha
implementation.
"""

import os, sys

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")  # 受限环境(如Claude Code)免疫OpenBLAS线程探测

try:
    import swisseph as swe
except ImportError as e:  # 用错python时给可执行纠正,不再含糊报错
    sys.stderr.write(
        "\n❌ swisseph 不可用—极可能用了系统 Python。\n"
        "  请使用 backend runtime 启动服务，并先运行 npm run backend:setup。\n"
        f"  原始错误: {e}\n"
    )
    raise
from datetime import datetime, timezone
import pytz
import json

from .constants import SIGNS, SIGN_LORDS
from .dignity import derive_dignities
from .provider_runtime import (
    canonical_planet_flags,
    configure_lahiri_swisseph,
    require_canonical_ephemeris_result,
    serialized_provider_call,
)

# ── PyJHora 固定版本适配模块（必须全部加载，否则 fail-fast）──
_SETUP_HINT = (
    "\n╔══════════════════════════════════════════════════════╗\n"
    "║  Backend runtime 未正确安装 PyJHora/依赖。             ║\n"
    "║  请在项目根目录运行: npm run backend:setup             ║\n"
    "╚══════════════════════════════════════════════════════╝"
)

_load_errors = []
try:
    from .ashtakavarga_pyjhora import calculate_ashtakavarga_fixed as _av_pyjhora
except ImportError as e:
    _av_pyjhora = None
    _load_errors.append(f"ashtakavarga_pyjhora: {e}")
try:
    from .shadbala_pyjhora import calculate_shadbala_fixed as _shadbala_pyjhora
except ImportError as e:
    _shadbala_pyjhora = None
    _load_errors.append(f"shadbala_pyjhora: {e}")
try:
    from .dasha_pyjhora import calculate_dasha_fixed as _dasha_pyjhora
except ImportError as e:
    _dasha_pyjhora = None
    _load_errors.append(f"dasha_pyjhora: {e}")
try:
    from .divisional_pyjhora import calculate_divisional_charts as _div_pyjhora
except ImportError as e:
    _div_pyjhora = None
    _load_errors.append(f"divisional_pyjhora: {e}")
try:
    from .extras_pyjhora import (
        calculate_bhava_bala as _bhava_bala_pyjhora,
        calculate_special_lagnas as _special_lagnas_pyjhora,
        calculate_vargeeya_bala as _vargeeya_bala_pyjhora,
    )
except ImportError as e:
    _bhava_bala_pyjhora = None
    _special_lagnas_pyjhora = None
    _vargeeya_bala_pyjhora = None
    _load_errors.append(f"extras_pyjhora: {e}")
try:
    from .kp_pyjhora import calc_kp_sub_lords as _kp_pyjhora
except ImportError as e:
    _kp_pyjhora = None
    _load_errors.append(f"kp_pyjhora: {e}")

# Fail-fast: 核心模块必须全部加载
_REQUIRED = {
    "Varga": _div_pyjhora,
    "SAV": _av_pyjhora,
    "Shadbala": _shadbala_pyjhora,
    "Dasha": _dasha_pyjhora,
}
_missing = [name for name, mod in _REQUIRED.items() if mod is None]
if _missing:
    print(f"\n❌ FATAL: 以下核心模块加载失败: {', '.join(_missing)}", file=sys.stderr)
    for err in _load_errors:
        print(f"   → {err}", file=sys.stderr)
    print(_SETUP_HINT, file=sys.stderr)
    raise ImportError(
        f"backend calculator 核心模块缺失: {', '.join(_missing)}. 请运行 npm run backend:setup"
    )

# === 配置 ===
# Lahiri是印度官方历书及绝大多数吠陀占星软件的默认Ayanamsa，作为主计算口径
# 保证跨软件Lagna/行星星座结论一致；True Chitrapaksha作为交叉校验口径保留，
# 差异通常<2角分，但边界盘主可能因此跨越星座边界，见 ayanamsa_cross_check()。
configure_lahiri_swisseph()

SIGN_ABBR = ["Ar", "Ta", "Ge", "Cn", "Le", "Vi", "Li", "Sc", "Sg", "Cp", "Aq", "Pi"]

PLANETS_SWE = {
    "Sun": swe.SUN,
    "Moon": swe.MOON,
    "Mars": swe.MARS,
    "Mercury": swe.MERCURY,
    "Jupiter": swe.JUPITER,
    "Venus": swe.VENUS,
    "Saturn": swe.SATURN,
}

NAKSHATRAS = [
    ("Ashwini", "Ketu"),
    ("Bharani", "Venus"),
    ("Krittika", "Sun"),
    ("Rohini", "Moon"),
    ("Mrigashira", "Mars"),
    ("Ardra", "Rahu"),
    ("Punarvasu", "Jupiter"),
    ("Pushya", "Saturn"),
    ("Ashlesha", "Mercury"),
    ("Magha", "Ketu"),
    ("Purva Phalguni", "Venus"),
    ("Uttara Phalguni", "Sun"),
    ("Hasta", "Moon"),
    ("Chitra", "Mars"),
    ("Swati", "Rahu"),
    ("Vishakha", "Jupiter"),
    ("Anuradha", "Saturn"),
    ("Jyeshtha", "Mercury"),
    ("Moola", "Ketu"),
    ("Purva Ashadha", "Venus"),
    ("Uttara Ashadha", "Sun"),
    ("Shravana", "Moon"),
    ("Dhanishta", "Mars"),
    ("Shatabhisha", "Rahu"),
    ("Purva Bhadrapada", "Jupiter"),
    ("Uttara Bhadrapada", "Saturn"),
    ("Revati", "Mercury"),
]

HOUSE_DOMAINS = {
    1: "自我",
    2: "财富",
    3: "兄弟",
    4: "家庭",
    5: "子女",
    6: "疾病",
    7: "婚姻",
    8: "变故",
    9: "运势",
    10: "事业",
    11: "收入",
    12: "损耗",
}

# Explicit VedicDust calculation policy. These thresholds preserve the current
# Parashari-style profile behavior while removing an opaque runtime dependency.
COMBUSTION_ORBS_DEG = {
    "Moon": {False: 12.0, True: 12.0},
    "Mars": {False: 17.0, True: 17.0},
    "Mercury": {False: 14.0, True: 12.0},
    "Jupiter": {False: 11.0, True: 11.0},
    "Venus": {False: 10.0, True: 8.0},
    "Saturn": {False: 15.0, True: 15.0},
}

DIRECTIONAL_STRENGTH_HOUSES = {
    "Sun": 10,
    "Moon": 4,
    "Mars": 10,
    "Mercury": 1,
    "Jupiter": 1,
    "Venus": 4,
    "Saturn": 7,
}


def angular_separation(longitude_a, longitude_b):
    """Return the shortest angular distance between two zodiac longitudes."""

    difference = abs(float(longitude_a) - float(longitude_b)) % 360.0
    return min(difference, 360.0 - difference)


def lunar_phase_hemicycle(moon_longitude, sun_longitude):
    """Return geometric Sun-Moon separation and waxing/waning hemicycle state."""

    separation = (float(moon_longitude) - float(sun_longitude)) % 360.0
    return {"waxing": separation < 180.0, "sun_moon_diff": round(separation, 6)}


def combustion_status(planet_name, planet_longitude, sun_longitude, is_retrograde=False):
    """Evaluate combustion against the declared profile threshold."""

    thresholds = COMBUSTION_ORBS_DEG.get(planet_name)
    if thresholds is None:
        return {
            "is_combust": False,
            "distance": angular_separation(planet_longitude, sun_longitude),
            "threshold": None,
        }
    distance = angular_separation(planet_longitude, sun_longitude)
    threshold = thresholds[bool(is_retrograde)]
    return {
        "is_combust": distance <= threshold,
        "distance": distance,
        "threshold": threshold,
    }


def has_directional_strength(planet_name, house):
    """Return whether a graha occupies its declared full-Digbala house."""

    return DIRECTIONAL_STRENGTH_HOUSES.get(planet_name) == int(house)


# === 核心计算函数 ===


def to_jd(
    year,
    month,
    day,
    hour,
    minute,
    tz_str,
    *,
    second=0,
    utc_offset_seconds=None,
):
    local_dt = _localize_strict(
        pytz.timezone(tz_str),
        datetime(year, month, day, hour, minute, second),
        utc_offset_seconds=utc_offset_seconds,
    )
    utc_dt = local_dt.astimezone(pytz.utc)
    ut_hour = utc_dt.hour + utc_dt.minute / 60.0 + utc_dt.second / 3600.0
    return swe.julday(utc_dt.year, utc_dt.month, utc_dt.day, ut_hour)


def _localize_strict(tz, naive_dt, *, utc_offset_seconds=None):
    """Resolve civil time without silently choosing a side of a DST transition."""
    from app.calculator.civil_time import resolve_civil_time

    return resolve_civil_time(
        naive_dt,
        tz.zone,
        utc_offset_seconds=utc_offset_seconds,
    )


def _format_degree_in_sign(degree):
    """Render a sign-local longitude without rounding into an invalid 60th minute."""

    total_minutes = min(int((float(degree) % 30.0) * 60.0), 29 * 60 + 59)
    return f"{total_minutes // 60}°{total_minutes % 60:02d}'"


def calc_planet(jd, planet_id):
    flags = canonical_planet_flags()
    result = swe.calc_ut(jd, planet_id, flags)
    require_canonical_ephemeris_result(result, object_name=f"planet id {planet_id}")
    lon = result[0][0]
    speed = result[0][3]
    sign_idx = int(lon / 30)
    degree = lon % 30
    return {
        "longitude": lon,
        "sign": SIGNS[sign_idx],
        "sign_idx": sign_idx,
        "degree": degree,
        "deg_str": _format_degree_in_sign(degree),
        "retrograde": speed < 0,
        "speed": speed,
    }


def calc_lagna(jd, lat, lon):
    flags = swe.FLG_SIDEREAL
    cusps, ascmc = swe.houses_ex(jd, lat, lon, b"W", flags)
    asc_lon = ascmc[0]
    sign_idx = int(asc_lon / 30)
    degree = asc_lon % 30
    return {
        "longitude": asc_lon,
        "sign": SIGNS[sign_idx],
        "sign_idx": sign_idx,
        "degree": degree,
        "deg_str": _format_degree_in_sign(degree),
    }


@serialized_provider_call
def ayanamsa_cross_check(jd, lagna_longitude):
    """Compare the primary Lahiri Lagna against the True Chitrapaksha alternative.

    Both are legitimate, widely-used sidereal ayanamsas; they typically differ
    by well under 2 arcminutes. That is usually negligible, but for a Lagna
    sitting near a sign boundary it can be the difference between two
    adjacent signs. This does not change any calculation output — it only
    flags when the two mainstream ayanamsas would disagree on the Lagna sign,
    so the report can surface that as an explicit caveat instead of silently
    picking one.
    """
    lahiri_ayanamsa = swe.get_ayanamsa_ut(jd)
    try:
        swe.set_sid_mode(swe.SIDM_TRUE_CITRA)
        true_citra_ayanamsa = swe.get_ayanamsa_ut(jd)
    finally:
        swe.set_sid_mode(swe.SIDM_LAHIRI)  # restore primary mode for the rest of the engine

    diff = lahiri_ayanamsa - true_citra_ayanamsa
    alt_longitude = (lagna_longitude + diff) % 360
    lahiri_sign_idx = int(lagna_longitude / 30)
    alt_sign_idx = int(alt_longitude / 30)

    return {
        "primary": "Lahiri",
        "alternate": "True Chitrapaksha",
        "primaryAyanamsa": round(lahiri_ayanamsa, 6),
        "alternateAyanamsa": round(true_citra_ayanamsa, 6),
        "diffArcminutes": round(diff * 60, 3),
        "alternateLagnaSign": SIGNS[alt_sign_idx],
        "lagnaSignAgrees": alt_sign_idx == lahiri_sign_idx,
    }


def get_nakshatra(longitude):
    nak_idx = int(longitude / (360 / 27))
    pada = int((longitude % (360 / 27)) / (360 / 108)) + 1
    name, lord = NAKSHATRAS[nak_idx]
    return {"name": name, "pada": pada, "lord": lord}


def get_house(planet_sign_idx, lagna_sign_idx):
    return ((planet_sign_idx - lagna_sign_idx) % 12) + 1


def calc_chara_karakas_7k8k(planets):
    """Calculate the declared 7K profile baseline and an unpromoted 8K comparison."""
    # Effective degree = degree in sign (for Rahu: 30 - degree)
    karaka_data = []
    for name in ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]:
        karaka_data.append((name, planets[name]["degree"]))

    # 7K is the current product profile choice; source promotion remains pending.
    sorted_7k = sorted(karaka_data, key=lambda x: x[1], reverse=True)
    karaka_names_7k = ["AK", "AmK", "BK", "MK", "PK", "GK", "DK"]
    karakas_7k = [(karaka_names_7k[i], sorted_7k[i][0], sorted_7k[i][1]) for i in range(7)]
    ambiguous_7k = []
    for index in range(len(karakas_7k) - 1):
        current = karakas_7k[index]
        following = karakas_7k[index + 1]
        if round(float(current[2]), 6) == round(float(following[2]), 6):
            ambiguous_7k.append(
                {
                    "roles": [current[0], following[0]],
                    "grahas": [current[1], following[1]],
                    "degreeInSign": round(float(current[2]), 6),
                }
            )

    # 8K (reference/Sanjay Rath): add Rahu (30 - degree)
    rahu_eff_deg = 30 - planets["Rahu"]["degree"]
    karaka_data_8k = karaka_data + [("Rahu", rahu_eff_deg)]
    sorted_8k = sorted(karaka_data_8k, key=lambda x: x[1], reverse=True)
    karaka_names_8k = ["AK", "AmK", "BK", "MK", "PiK", "PK", "GK", "DK"]
    karakas_8k = [(karaka_names_8k[i], sorted_8k[i][0], sorted_8k[i][1]) for i in range(8)]

    # DK: 7K为主，8K为参考
    dk_7k = karakas_7k[6][1]  # 7K DK（主）
    dk_8k = karakas_8k[7][1]  # 8K DK = 第8位（最低度数）

    return {
        "7k": karakas_7k,
        "7k_ambiguities": ambiguous_7k,
        "8k": karakas_8k,
        "dk_7k": dk_7k,
        "dk_8k": dk_8k,
        "dk_note": f"7K(profile)={dk_7k}, 8K(supplemental)={dk_8k}",
    }


SPECIAL_DRISHTI = {
    "Mars": [4, 8],
    "Jupiter": [5, 9],
    "Saturn": [3, 10],
    # Rahu/Ketu drishti is lineage-dependent and excluded by this profile.
}


def _degree_gap_in_sign(p1, p2):
    return abs(p1["degree"] - p2["degree"])


def calc_aspects(planets):
    """Calculate Vedic whole-sign contacts and Graha Drishti.

    This intentionally does not use Western aspect angles such as 60/90/120.
    Degree gaps only grade strength inside an already-valid whole-sign contact.
    """
    contacts = []
    planet_names = list(planets.keys())

    # Same-sign contact is mutual. Keep a single row per pair so the markdown
    # fact source stays compact while preserving both participants.
    for i in range(len(planet_names)):
        for j in range(i + 1, len(planet_names)):
            p1_name, p2_name = planet_names[i], planet_names[j]
            p1, p2 = planets[p1_name], planets[p2_name]
            if p1["sign_idx"] != p2["sign_idx"]:
                continue
            gap = _degree_gap_in_sign(p1, p2)
            contacts.append(
                {
                    "source": p1_name,
                    "target": p2_name,
                    "direction": "mutual",
                    "kind": "same_sign",
                    "type": "同座接触",
                    "aspect": 1,
                    "source_house": p1["house"],
                    "target_house": p2["house"],
                    "target_sign": p2["sign"],
                    "degree_gap": round(gap, 2),
                }
            )

    # Graha Drishti is directional. The seven classical grahas cast the 7th;
    # Mars, Jupiter, and Saturn add their declared special drishti. Rahu/Ketu
    # remain valid targets but are not aspect sources in this profile.
    for source_name in [name for name in planet_names if name not in {"Rahu", "Ketu"}]:
        source = planets[source_name]
        aspect_numbers = [7] + SPECIAL_DRISHTI.get(source_name, [])
        for aspect_number in aspect_numbers:
            target_sign_idx = (source["sign_idx"] + aspect_number - 1) % 12
            for target_name in planet_names:
                if source_name == target_name:
                    continue
                target = planets[target_name]
                if target["sign_idx"] != target_sign_idx:
                    continue
                gap = _degree_gap_in_sign(source, target)
                contacts.append(
                    {
                        "source": source_name,
                        "target": target_name,
                        "direction": "source_to_target",
                        "kind": "graha_drishti",
                        "type": f"{aspect_number}th Graha Drishti",
                        "aspect": aspect_number,
                        "source_house": source["house"],
                        "target_house": target["house"],
                        "target_sign": target["sign"],
                        "degree_gap": round(gap, 2),
                    }
                )

    contacts.sort(
        key=lambda item: (
            0 if item["kind"] == "same_sign" else 1,
            item["aspect"],
            item["degree_gap"],
            item["source"],
            item["target"],
        )
    )
    return contacts


def calc_house_aspects(planets, lagna_sign_idx):
    """Return source graha -> target house drishti facts for house diagnosis."""
    rows = []
    for source_name, source in planets.items():
        if source_name in {"Rahu", "Ketu"}:
            continue
        aspect_numbers = [7] + SPECIAL_DRISHTI.get(source_name, [])
        for aspect_number in aspect_numbers:
            target_sign_idx = (source["sign_idx"] + aspect_number - 1) % 12
            target_house = get_house(target_sign_idx, lagna_sign_idx)
            rows.append(
                {
                    "source": source_name,
                    "aspect": aspect_number,
                    "source_house": source["house"],
                    "target_house": target_house,
                    "target_sign": SIGNS[target_sign_idx],
                    "type": f"{aspect_number}th Graha Drishti",
                }
            )
    rows.sort(key=lambda item: (item["target_house"], item["source"], item["aspect"]))
    return rows


def calc_house_lords(lagna_sign_idx):
    """Calculate house lord table"""
    lords = {}
    for house in range(1, 13):
        sign_idx = (lagna_sign_idx + house - 1) % 12
        lord = SIGN_LORDS[sign_idx]
        lords[house] = {"sign": SIGNS[sign_idx], "lord": lord, "domain": HOUSE_DOMAINS[house]}
    return lords


def calc_special_points(lagna, planets):
    """Calculate provisional AL and UL using the seven-lord baseline.

    This intentionally does not resolve Scorpio/Aquarius co-lords. The emitted points
    stay provisional and must not be presented as lineage-complete Arudha calculations.
    """
    lagna_idx = lagna["sign_idx"]

    def calc_arudha(house_num, lagna_idx):
        """Calculate one Arudha Pada under the declared simplified baseline."""
        sign_idx = (lagna_idx + house_num - 1) % 12
        lord = SIGN_LORDS[sign_idx]
        lord_sign_idx = planets[lord]["sign_idx"]
        # Count from house sign to lord (1-based: lord in same sign = 1st)
        dist = (lord_sign_idx - sign_idx) % 12
        # Arudha = same distance from lord's position
        arudha_idx = (lord_sign_idx + dist) % 12
        # BPHS Exception: arudha cannot be in 1st or 7th from house sign
        # If 1st → use 10th from house sign
        # If 7th → use 4th from house sign
        if arudha_idx == sign_idx:
            arudha_idx = (sign_idx + 9) % 12  # 10th from house sign
        elif arudha_idx == (sign_idx + 6) % 12:
            arudha_idx = (sign_idx + 3) % 12  # 4th from house sign
        return SIGNS[arudha_idx], arudha_idx

    al_sign, al_idx = calc_arudha(1, lagna_idx)
    al_house = get_house(al_idx, lagna_idx)

    ul_sign, ul_idx = calc_arudha(12, lagna_idx)
    ul_house = get_house(ul_idx, lagna_idx)

    return {
        "AL": {"sign": al_sign, "sign_idx": al_idx, "house": al_house},
        "UL": {"sign": ul_sign, "sign_idx": ul_idx, "house": ul_house},
    }


@serialized_provider_call
def calc_transits(lagna_sign_idx, moon_sign_idx, *, as_of=None):
    """Calculate current transit positions for slow planets.
    Used by core-pro for Sade Sati, BAV transit calibration, double transit.
    """
    moment = as_of or datetime.now(timezone.utc)
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("transit as_of must be timezone-aware")
    now = moment.astimezone(timezone.utc)
    jd_now = swe.julday(
        now.year,
        now.month,
        now.day,
        now.hour + now.minute / 60 + now.second / 3600,
    )
    configure_lahiri_swisseph()
    flags = canonical_planet_flags()

    transits = {}
    # Slow planets: Saturn, Jupiter, Rahu, Ketu
    slow_planets = {"Saturn": swe.SATURN, "Jupiter": swe.JUPITER}
    for name, pid in slow_planets.items():
        result = swe.calc_ut(jd_now, pid, flags)
        require_canonical_ephemeris_result(result, object_name=f"transit {name}")
        lon = result[0][0]
        speed = result[0][3]
        sign_idx = int(lon / 30)
        house = get_house(sign_idx, lagna_sign_idx)
        transits[name] = {
            "longitude": lon,
            "sign": SIGNS[sign_idx],
            "sign_idx": sign_idx,
            "degree": lon % 30,
            "house": house,
            "speed": speed,
            "retrograde": speed < 0,
        }

    # Rahu (Mean Node)
    result = swe.calc_ut(jd_now, swe.MEAN_NODE, flags)
    require_canonical_ephemeris_result(result, object_name="transit mean lunar node")
    rahu_lon = result[0][0]
    rahu_speed = result[0][3]
    rahu_idx = int(rahu_lon / 30)
    transits["Rahu"] = {
        "longitude": rahu_lon,
        "sign": SIGNS[rahu_idx],
        "sign_idx": rahu_idx,
        "degree": rahu_lon % 30,
        "house": get_house(rahu_idx, lagna_sign_idx),
        "speed": rahu_speed,
        "retrograde": rahu_speed < 0,
    }
    ketu_lon = (rahu_lon + 180.0) % 360.0
    ketu_idx = int(ketu_lon / 30)
    transits["Ketu"] = {
        "longitude": ketu_lon,
        "sign": SIGNS[ketu_idx],
        "sign_idx": ketu_idx,
        "degree": ketu_lon % 30,
        "house": get_house(ketu_idx, lagna_sign_idx),
        "speed": rahu_speed,
        "retrograde": rahu_speed < 0,
    }

    # Sade Sati check
    saturn_idx = transits["Saturn"]["sign_idx"]
    sade_sati = "inactive"
    if saturn_idx == (moon_sign_idx - 1) % 12:
        sade_sati = "phase1_rising"
    elif saturn_idx == moon_sign_idx:
        sade_sati = "phase2_peak"
    elif saturn_idx == (moon_sign_idx + 1) % 12:
        sade_sati = "phase3_fading"
    transits["sade_sati"] = sade_sati

    # Double transit (Saturn-Jupiter intersection)
    sat_houses = {transits["Saturn"]["house"]}
    # Saturn aspects: 3rd, 7th, 10th
    sat_h = transits["Saturn"]["house"]
    for asp in [3, 7, 10]:
        sat_houses.add(((sat_h - 1 + asp - 1) % 12) + 1)

    jup_houses = {transits["Jupiter"]["house"]}
    # Jupiter aspects: 5th, 7th, 9th
    jup_h = transits["Jupiter"]["house"]
    for asp in [5, 7, 9]:
        jup_houses.add(((jup_h - 1 + asp - 1) % 12) + 1)

    double_transit = sorted(sat_houses & jup_houses)
    transits["double_transit_houses"] = double_transit
    transits["as_of_utc"] = now.isoformat()

    return transits


# === 主计算函数 ===


@serialized_provider_call
def calculate_full_chart(
    year,
    month,
    day,
    hour,
    minute,
    lat,
    lon,
    tz_str="Asia/Kolkata",
    *,
    second=0,
    transit_as_of=None,
    calculation_as_of=None,
    utc_offset_seconds=None,
):
    """计算完整星盘数据"""
    # 显式重置sid_mode，不依赖进程内上一次调用留下的全局状态
    # （PyJHora子模块/calc_transits会临时切换sid_mode，必须在每次入口处自愈）
    configure_lahiri_swisseph()
    jd = to_jd(
        year,
        month,
        day,
        hour,
        minute,
        tz_str,
        second=second,
        utc_offset_seconds=utc_offset_seconds,
    )
    ayanamsa = swe.get_ayanamsa_ut(jd)

    # 1. Lagna
    lagna = calc_lagna(jd, lat, lon)
    lagna["nakshatra"] = get_nakshatra(lagna["longitude"])
    lagna["house"] = 1
    ayanamsa_check = ayanamsa_cross_check(jd, lagna["longitude"])

    # 2. Planets (7 main)
    planets = {}
    for name, pid in PLANETS_SWE.items():
        p = calc_planet(jd, pid)
        p["house"] = get_house(p["sign_idx"], lagna["sign_idx"])
        p["nakshatra"] = get_nakshatra(p["longitude"])
        planets[name] = p

    # 3. Rahu & Ketu
    flags = canonical_planet_flags()
    result = swe.calc_ut(jd, swe.MEAN_NODE, flags)
    require_canonical_ephemeris_result(result, object_name="mean lunar node")
    rahu_lon = result[0][0]
    rahu_sign_idx = int(rahu_lon / 30)
    rahu_deg = rahu_lon % 30
    planets["Rahu"] = {
        "longitude": rahu_lon,
        "sign": SIGNS[rahu_sign_idx],
        "sign_idx": rahu_sign_idx,
        "degree": rahu_deg,
        "deg_str": _format_degree_in_sign(rahu_deg),
        "retrograde": True,
        "speed": result[0][3],
        "house": get_house(rahu_sign_idx, lagna["sign_idx"]),
        "nakshatra": get_nakshatra(rahu_lon),
    }
    ketu_lon = (rahu_lon + 180) % 360
    ketu_sign_idx = int(ketu_lon / 30)
    ketu_deg = ketu_lon % 30
    planets["Ketu"] = {
        "longitude": ketu_lon,
        "sign": SIGNS[ketu_sign_idx],
        "sign_idx": ketu_sign_idx,
        "degree": ketu_deg,
        "deg_str": _format_degree_in_sign(ketu_deg),
        "retrograde": True,
        "speed": result[0][3],
        "house": get_house(ketu_sign_idx, lagna["sign_idx"]),
        "nakshatra": get_nakshatra(ketu_lon),
    }

    # 4. SAV/BAV (PyJHora — no fallback)
    tz = pytz.timezone(tz_str)
    _tz_dt = _localize_strict(
        tz,
        datetime(year, month, day, hour, minute, second),
        utc_offset_seconds=utc_offset_seconds,
    )
    _tz_offset = _tz_dt.utcoffset().total_seconds() / 3600.0
    ashtak = _av_pyjhora(year, month, day, hour, minute, lat, lon, _tz_offset, second=second)

    # Map SAV to houses
    sav_by_house = {}
    for h in range(1, 13):
        sign_idx = (lagna["sign_idx"] + h - 1) % 12
        sign_name = SIGNS[sign_idx]
        sav_by_house[h] = {"sign": sign_name, "value": ashtak["sarvashtakavarga"].get(sign_name, 0)}

    # 5. Divisional charts (PyJHora: 15 charts)
    divisional_charts = _div_pyjhora(
        year, month, day, hour, minute, lat, lon, _tz_offset, second=second
    )

    # Vargottama check
    d9_chart = divisional_charts.get("D9", {})
    d9_lagna = d9_chart.get("Lagna", {}) if isinstance(d9_chart, dict) else {}
    vargottama = {
        "Lagna": lagna["sign"] == (d9_lagna.get("sign") if isinstance(d9_lagna, dict) else None)
    }
    for name in planets:
        d9_placement = d9_chart.get(name, {}) if isinstance(d9_chart, dict) else {}
        d9_sign_name = d9_placement.get("sign") if isinstance(d9_placement, dict) else None
        vargottama[name] = planets[name]["sign"] == d9_sign_name

    # 6. Sign dignity and Panchadha Maitri. Nodes are excluded by the baseline profile.
    dignity_data = derive_dignities(planets)

    # 7. Combustion check
    sun_lon = planets["Sun"]["longitude"]
    combustion = {}
    combustion_statuses = {}
    for name in ["Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]:
        is_retro = planets[name]["retrograde"]
        comb_result = combustion_status(name, planets[name]["longitude"], sun_lon, is_retro)
        status = {
            "is_combust": bool(comb_result["is_combust"]),
            "distance": round(comb_result["distance"], 2),
            "threshold": comb_result["threshold"],
            "retrogradeThresholdApplied": bool(is_retro),
        }
        combustion_statuses[name] = status
        if comb_result["is_combust"]:
            combustion[name] = dict(status)

    # 8. Chara Karakas (7K primary)
    karakas = calc_chara_karakas_7k8k(planets)

    # 9. Vedic aspects / Graha Drishti
    aspects = calc_aspects(planets)
    house_aspects = calc_house_aspects(planets, lagna["sign_idx"])

    # 10. House lords
    house_lords = calc_house_lords(lagna["sign_idx"])
    # Add planet positions to house lords
    for h, info in house_lords.items():
        planet = info["lord"]
        if planet in planets:
            info["lord_house"] = planets[planet]["house"]

    snapshot_moment = calculation_as_of or transit_as_of or datetime.now(timezone.utc)
    if snapshot_moment.tzinfo is None:
        raise ValueError("calculation_as_of must be timezone-aware")

    # 11. Vimsottari Dasha (PyJHora — no fallback)
    dashas = _dasha_pyjhora(
        year,
        month,
        day,
        hour,
        minute,
        lat,
        lon,
        _tz_offset,
        second=second,
        as_of=snapshot_moment,
        timezone_id=tz_str,
    )

    # 12. Shadbala (PyJHora + 9 bug fixes — no fallback)
    shadbala_data = _shadbala_pyjhora(
        year, month, day, hour, minute, lat, lon, _tz_offset, second=second
    )

    # 13. Moon phase
    moon_phase = lunar_phase_hemicycle(planets["Moon"]["longitude"], planets["Sun"]["longitude"])

    # 14. Digbala
    digbala = {}
    for name in ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn"]:
        digbala[name] = has_directional_strength(name, planets[name]["house"])

    # 15. Special Points (AL, UL)
    special_points = calc_special_points(lagna, planets)

    # 16. Transit positions (current slow planet positions)
    transits = calc_transits(
        lagna["sign_idx"],
        planets["Moon"]["sign_idx"],
        as_of=snapshot_moment,
    )

    # 17. Bhava Bala, Special Lagnas, Vargeeya Bala (via PyJHora)
    # Keep failures independent and visible. ChartRecord must expose missing strength data.
    bhava_bala = None
    special_lagnas = None
    vargeeya_bala = None
    if any([_bhava_bala_pyjhora, _special_lagnas_pyjhora, _vargeeya_bala_pyjhora]):
        tz = pytz.timezone(tz_str)
        _tz_dt = _localize_strict(
            tz,
            datetime(year, month, day, hour, minute, second),
            utc_offset_seconds=utc_offset_seconds,
        )
        _tz_offset = _tz_dt.utcoffset().total_seconds() / 3600.0
        if _bhava_bala_pyjhora:
            try:
                bhava_bala = _bhava_bala_pyjhora(
                    year, month, day, hour, minute, lat, lon, _tz_offset, second=second
                )
            except Exception as exc:
                print(f"⚠️ Bhava Bala计算失败，跳过: {exc}", file=sys.stderr)
        if _special_lagnas_pyjhora:
            try:
                special_lagnas = _special_lagnas_pyjhora(
                    year, month, day, hour, minute, lat, lon, _tz_offset, second=second
                )
            except Exception as exc:
                print(f"⚠️ Special Lagnas计算失败，跳过: {exc}", file=sys.stderr)
        if _vargeeya_bala_pyjhora:
            try:
                vargeeya_bala = _vargeeya_bala_pyjhora(
                    year, month, day, hour, minute, lat, lon, _tz_offset, second=second
                )
            except Exception as exc:
                print(f"⚠️ Vargeeya Bala计算失败，跳过: {exc}", file=sys.stderr)

    return {
        "julian_day_ut": jd,
        "ayanamsa": ayanamsa,
        "ayanamsa_cross_check": ayanamsa_check,
        "lagna": lagna,
        "planets": planets,
        "sav": ashtak["sarvashtakavarga"],
        "sav_by_house": sav_by_house,
        "bav": ashtak["bhinnashtakavarga"],
        "divisional_charts": divisional_charts,
        "vargottama": vargottama,
        "dignity": dignity_data,
        "combustion": combustion,
        "combustion_statuses": combustion_statuses,
        "karakas": karakas,
        "aspects": aspects,
        "house_aspects": house_aspects,
        "house_lords": house_lords,
        "dashas": dashas,
        "shadbala": shadbala_data,
        "moon_phase": moon_phase,
        "digbala": digbala,
        "special_points": special_points,
        "transits": transits,
        "bhava_bala": bhava_bala,
        "special_lagnas": special_lagnas,
        "vargeeya_bala": vargeeya_bala,
    }


@serialized_provider_call
def calculate_rectification_signature(
    year,
    month,
    day,
    hour,
    minute,
    lat,
    lon,
    tz_str="Asia/Kolkata",
    *,
    chart_factors=None,
    second=0,
    utc_offset_seconds=None,
):
    """Calculate only chart fields that can split a birth-time candidate interval."""

    factors = chart_factors or [1, 2, 3, 4, 5, 7, 9, 10, 12, 16, 20, 24, 27, 30, 60]
    configure_lahiri_swisseph()
    jd = to_jd(
        year,
        month,
        day,
        hour,
        minute,
        tz_str,
        second=second,
        utc_offset_seconds=utc_offset_seconds,
    )
    lagna = calc_lagna(jd, lat, lon)
    ayanamsa_check = ayanamsa_cross_check(jd, lagna["longitude"])
    planets = {name: calc_planet(jd, planet_id) for name, planet_id in PLANETS_SWE.items()}
    rahu = calc_planet(jd, swe.MEAN_NODE)
    ketu_longitude = (float(rahu["longitude"]) + 180.0) % 360.0
    planets["Rahu"] = rahu
    planets["Ketu"] = {
        "sign_idx": int(ketu_longitude / 30),
        "sign": SIGNS[int(ketu_longitude / 30)],
        "longitude": ketu_longitude,
        "degree": ketu_longitude % 30,
    }
    moon = planets["Moon"]
    moon_nakshatra = get_nakshatra(moon["longitude"])
    chara_karakas = calc_chara_karakas_7k8k(planets)
    timezone_info = pytz.timezone(tz_str)
    localized = _localize_strict(
        timezone_info,
        datetime(year, month, day, hour, minute, second),
        utc_offset_seconds=utc_offset_seconds,
    )
    timezone_offset = localized.utcoffset().total_seconds() / 3600.0
    divisional_charts = _div_pyjhora(
        year,
        month,
        day,
        hour,
        minute,
        lat,
        lon,
        timezone_offset,
        chart_factors=factors,
        second=second,
    )
    kp_cuspal_sub_lords = None
    if _kp_pyjhora is not None:
        try:
            kp_cuspal_sub_lords = _kp_pyjhora(
                year,
                month,
                day,
                hour,
                minute,
                lat,
                lon,
                timezone_offset,
                second=second,
            )
        except Exception as exc:
            print(f"⚠️ KP副星主计算失败，跳过: {exc}", file=sys.stderr)
    signature = {
        "lagnaSign": lagna.get("sign"),
        "lagnaDegree": round(float(lagna.get("degree", 0)), 4),
        "ayanamsaCrossCheck": ayanamsa_check,
        "kpCuspalSubLords": kp_cuspal_sub_lords,
        "moonSign": moon.get("sign"),
        "moonNakshatra": moon_nakshatra.get("name"),
        "moonPada": moon_nakshatra.get("pada"),
        # Dasha is deliberately omitted from the minute grid. It is expensive and
        # belongs in dated-event scoring, where each surviving interval is assessed.
        "currentDasha": None,
        "charaKaraka7k": {str(role): str(name) for role, name, _degree in chara_karakas["7k"]},
        "planetSignIndices": {
            name: int(position["sign_idx"]) for name, position in planets.items()
        },
        "vargaPlanetSignIndices": {},
    }
    for factor in factors:
        if factor == 1:
            continue
        raw_chart = divisional_charts.get(f"D{factor}")
        raw_lagna = raw_chart.get("Lagna") if isinstance(raw_chart, dict) else None
        signature[f"d{factor}Lagna"] = (
            raw_lagna.get("sign") if isinstance(raw_lagna, dict) else None
        )
        if isinstance(raw_chart, dict) and "error" not in raw_chart:
            signature["vargaPlanetSignIndices"][f"D{factor}"] = {
                name: int(position["sign_idx"])
                for name, position in raw_chart.items()
                if name != "Lagna"
                and isinstance(position, dict)
                and position.get("sign_idx") is not None
            }
    return signature


# === TEST ===
if __name__ == "__main__":
    print("=== vedic-calculator v0.2 Full Test ===\n")

    # Gandhi: 1869-10-02, 07:12, Porbandar
    chart = calculate_full_chart(1869, 10, 2, 7, 12, 21.6417, 69.6293, "Asia/Kolkata")

    print(f"Ayanamsa (Lahiri): {chart['ayanamsa']:.4f}°")
    print(f"Lagna: {chart['lagna']['sign']} {chart['lagna']['deg_str']}")

    print(f"\n--- Planets ---")
    print(
        f"  {'Planet':<10} {'Sign':<12} {'Deg':>8} {'H':>3} {'R':>2} {'Dignity':<16} {'Compound'}"
    )
    for name in ["Sun", "Moon", "Mars", "Mercury", "Jupiter", "Venus", "Saturn", "Rahu", "Ketu"]:
        p = chart["planets"][name]
        r = "R" if p["retrograde"] else ""
        dig = chart["dignity"].get(name, {})
        basic = dig.get("basic", "-")
        compound = dig.get("compound", "-")
        print(
            f"  {name:<10} {p['sign']:<12} {p['deg_str']:>8} {p['house']:>3} {r:>2} {str(basic):<16} {compound}"
        )

    print(f"\n--- SAV by House ---")
    total = 0
    for h in range(1, 13):
        s = chart["sav_by_house"][h]
        total += s["value"]
        print(f"  {h}宫({s['sign'][:2]}): {s['value']}", end="  ")
        if h % 6 == 0:
            print()
    print(f"  Total: {total}")

    print(f"\n--- Chara Karakas (7K) ---")
    for k, planet, deg in chart["karakas"]["7k"]:
        print(f"  {k}: {planet} ({deg:.1f}°)")
    print(
        f"  DK: 7K(profile)={chart['karakas']['dk_7k']}, "
        f"8K(supplemental)={chart['karakas']['dk_8k']}"
    )

    print(f"\n--- Vedic Contacts (top 5) ---")
    for a in chart["aspects"][:5]:
        print(
            f"  {a['source']}->{a['target']}: {a['type']} "
            f"(H{a['source_house']}→H{a['target_house']}, gap={a['degree_gap']}°)"
        )

    print(f"\n--- Dasha ---")
    for d in chart["dashas"]:
        marker = "→" if d["is_current"] else " "
        print(f"  {marker} {d['planet']:<10} {d['start']} ~ {d['end']}  ({d['years']}yr)")

    print(f"\n--- D9 Navamsha ---")
    for name in [
        "Lagna",
        "Sun",
        "Moon",
        "Mars",
        "Mercury",
        "Jupiter",
        "Venus",
        "Saturn",
        "Rahu",
        "Ketu",
    ]:
        sign = chart["divisional_charts"]["D9"][name]["sign"]
        varg = " ★V" if chart["vargottama"].get(name, False) else ""
        print(f"  {name:<10} → {sign}{varg}")

    print(f"\n--- Shadbala ---")
    if "error" in chart["shadbala"]:
        print(f"  Error: {chart['shadbala']['error']}")
    else:
        for name, data in chart["shadbala"].items():
            if isinstance(data, dict):
                total = data.get("total_rupas", data.get("total", "?"))
                print(f"  {name:<10} {total}")

    print(f"\n--- Moon Phase ---")
    phase = chart["moon_phase"]
    print(
        f"  {'盈月(Shukla)' if phase['waxing'] else '亏月(Krishna)'}, 距Sun {phase['sun_moon_diff']}°"
    )

    print(f"\n--- Combustion ---")
    if chart["combustion"]:
        for name, data in chart["combustion"].items():
            print(f"  {name}: {data}")
    else:
        print("  无燃烧行星")

    print(f"\n--- House Lords ---")
    for h in range(1, 13):
        info = chart["house_lords"][h]
        print(f"  {h}宫({info['domain']}): {info['lord']} → {info.get('lord_house', '?')}宫")

    print(f"\n✅ 全部14个数据板块计算完成!")
