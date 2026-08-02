"""
divisional_pyjhora.py - PyJHora 分盘计算封装
支持所有标准分盘 (D1-D60)
每张分盘使用 VedicDust Calculation Profile 明确声明的 provider method；
这是 provider 适配声明，不是独立桌面软件验证。
"""

from .pyjhora_compat import ensure_pyjhora_swe_compat
from .provider_runtime import configure_vedicdust_pyjhora, serialized_provider_call
from app.vedicdust.profiles import varga_method_setting


@serialized_provider_call
def calculate_divisional_charts(
    year,
    month,
    day,
    hour,
    minute,
    lat,
    lon,
    tz_offset,
    chart_factors=None,
    *,
    second=0,
):
    """
    使用固定版本 PyJHora 和逐分盘声明的 provider method 计算分盘。

    Returns:
        dict: {'D9': {planet: {'sign':..., 'sign_idx':..., 'degree':...}, ...}, ...}
    """
    import sys
    import os
    import swisseph as swe

    pyjhora_path = None
    try:
        import jhora as _jh

        pyjhora_path = os.path.dirname(os.path.dirname(_jh.__file__))
    except ImportError:
        import site

        for sp in site.getsitepackages():
            if os.path.exists(os.path.join(sp, "jhora")):
                pyjhora_path = sp
                break
    if pyjhora_path is None:
        raise ImportError("jhora package not found")
    if pyjhora_path not in sys.path:
        sys.path.insert(0, pyjhora_path)
    swe.set_ephe_path(os.path.join(pyjhora_path, "jhora", "data", "ephe"))

    ensure_pyjhora_swe_compat()

    from jhora import const
    from jhora.panchanga import drik
    from jhora.panchanga.drik import Place
    from jhora.horoscope.chart import charts

    configure_vedicdust_pyjhora()

    # PyJHora's dhasavarga() defaults to true nodes even when the global constant
    # requests mean nodes. The Calculation Profile is explicit, so ignore the
    # provider default and force mean Rahu/Ketu for every varga call.
    if not hasattr(drik.dhasavarga, "_mean_node_patched"):
        _orig_dhasavarga = drik.dhasavarga

        def _dhasavarga_mean_node(
            jd, place, divisional_chart_factor=1, set_rahu_ketu_as_true_nodes=None, **kw
        ):
            return _orig_dhasavarga(
                jd,
                place,
                divisional_chart_factor=divisional_chart_factor,
                set_rahu_ketu_as_true_nodes=False,
                **kw,
            )

        _dhasavarga_mean_node._mean_node_patched = True
        drik.dhasavarga = _dhasavarga_mean_node

    local_hour = hour + minute / 60.0 + second / 3600.0
    jd_local = swe.julday(year, month, day, local_hour)
    place = Place("birth_place", lat, lon, tz_offset)

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
    PLANET_MAP = {
        "L": "Lagna",
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

    if chart_factors is None:
        chart_factors = [1, 2, 3, 4, 5, 7, 9, 10, 12, 16, 20, 24, 27, 30, 60]

    result = {}
    for dcf in chart_factors:
        key = f"D{dcf}"
        method = varga_method_setting(dcf)
        provider_method = method.provider_method or 1
        try:
            # Ensure Mean Node consistency
            const._use_true_nodes_for_rahu_ketu = False

            pp = charts.divisional_chart(
                jd_local,
                place,
                divisional_chart_factor=dcf,
                chart_method=provider_method,
            )

            chart_data = {}
            for entry in pp:
                p_id = entry[0]
                sign_idx = int(entry[1][0])
                degree = entry[1][1] if len(entry[1]) > 1 else 0
                p_name = PLANET_MAP.get(p_id, str(p_id))
                chart_data[p_name] = {
                    "sign": SIGNS[sign_idx],
                    "sign_idx": sign_idx,
                    "degree": round(degree, 4) if isinstance(degree, float) else degree,
                }
            result[key] = chart_data
        except Exception as exc:
            raise RuntimeError(
                f"required divisional chart {key} failed under "
                f"{method.algorithm_id} (provider method {provider_method})"
            ) from exc

    return result
