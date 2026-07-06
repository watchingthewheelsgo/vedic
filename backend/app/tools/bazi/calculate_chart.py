from __future__ import annotations

import argparse
import importlib.metadata
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from lunar_python import Lunar, Solar
from lunar_python.util import LunarUtil


YANG_STEMS = {"甲", "丙", "戊", "庚", "壬"}
STEM_ELEMENTS = LunarUtil.WU_XING_GAN
BRANCH_ELEMENTS = LunarUtil.WU_XING_ZHI
HIDDEN_STEMS = LunarUtil.ZHI_HIDE_GAN
LUNAR_PYTHON_VERSION = importlib.metadata.version("lunar_python")

BRANCH_PAIRS = {
    "combinations": {
        "子丑": "六合化土",
        "寅亥": "六合化木",
        "卯戌": "六合化火",
        "辰酉": "六合化金",
        "巳申": "六合化水",
        "午未": "六合化土",
    },
    "clashes": {
        "子午": "冲",
        "丑未": "冲",
        "寅申": "冲",
        "卯酉": "冲",
        "辰戌": "冲",
        "巳亥": "冲",
    },
    "harms": {
        "子未": "害",
        "丑午": "害",
        "寅巳": "害",
        "卯辰": "害",
        "申亥": "害",
        "酉戌": "害",
    },
}

THREE_GROUPS = {
    "threeCombinations": {
        frozenset({"申", "子", "辰"}): "三合水局",
        frozenset({"亥", "卯", "未"}): "三合木局",
        frozenset({"寅", "午", "戌"}): "三合火局",
        frozenset({"巳", "酉", "丑"}): "三合金局",
    },
    "threeMeetings": {
        frozenset({"寅", "卯", "辰"}): "三会木方",
        frozenset({"巳", "午", "未"}): "三会火方",
        frozenset({"申", "酉", "戌"}): "三会金方",
        frozenset({"亥", "子", "丑"}): "三会水方",
    },
    "punishments": {
        frozenset({"寅", "巳", "申"}): "无恩之刑",
        frozenset({"丑", "戌", "未"}): "恃势之刑",
        frozenset({"子", "卯"}): "无礼之刑",
    },
}


@dataclass(frozen=True)
class BaziInput:
    birth_date: date
    birth_time: str
    birth_place: str
    gender: str
    calendar_type: str
    time_precision: str
    timezone_name: str
    latitude: float | None
    longitude: float | None
    current_date: date
    audience: str
    relationship: str
    topic: str
    day_boundary_sect: int
    luck_sect: int
    solar_time_policy: str


def calculate_bazi(input_data: BaziInput) -> dict[str, Any]:
    hour, minute, time_uncertain = _parse_birth_time(
        input_data.birth_time,
        input_data.time_precision,
    )
    solar, lunar = _build_lunar(input_data, hour, minute)
    eight_char = lunar.getEightChar()
    eight_char.setSect(input_data.day_boundary_sect)

    pillars = _pillars(eight_char, lunar)
    branches = [pillars[key]["branch"] for key in ["year", "month", "day", "hour"]]
    day_stem = pillars["day"]["stem"]
    luck = _luck(eight_char, input_data, pillars["month"]["ganZhi"])
    age = _completed_age(input_data.birth_date, input_data.current_date)

    warnings = _warnings(input_data, time_uncertain, solar, lunar)
    payload: dict[str, Any] = {
        "schemaVersion": "bazi-chart-facts/v1",
        "engine": "lunar-python",
        "calculationVersion": f"lunar-python-{LUNAR_PYTHON_VERSION}",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "subject": {
            "gender": input_data.gender or "未提供",
            "birthDate": input_data.birth_date.isoformat(),
            "birthTime": input_data.birth_time or "unknown",
            "birthPlace": input_data.birth_place,
            "calendarType": input_data.calendar_type,
            "timePrecision": input_data.time_precision,
            "timezone": input_data.timezone_name,
            "latitude": input_data.latitude,
            "longitude": input_data.longitude,
            "solarTimePolicy": input_data.solar_time_policy,
            "solarTimeApplied": False,
            "effectiveSolarDateTime": solar.toYmdHms(),
        },
        "settings": {
            "dayBoundarySect": input_data.day_boundary_sect,
            "luckSect": input_data.luck_sect,
            "monthBoundary": "节",
            "yearBoundary": "立春",
            "trueSolarTime": "not-applied",
        },
        "reportContext": {
            "currentDate": input_data.current_date.isoformat(),
            "currentAge": age,
            "lifeStage": _life_stage(age),
            "audience": input_data.audience,
            "relationship": input_data.relationship,
            "topic": input_data.topic,
        },
        "pillars": pillars,
        "dayMaster": {
            "stem": day_stem,
            "element": STEM_ELEMENTS.get(day_stem),
            "yinYang": "阳" if day_stem in YANG_STEMS else "阴",
        },
        "hiddenStems": {branch: HIDDEN_STEMS.get(branch, []) for branch in set(branches)},
        "tenGods": _ten_gods(pillars),
        "fiveElements": _five_elements(pillars),
        "relations": _relations(branches),
        "solarTerms": {
            "previousJie": {
                "name": lunar.getPrevJie().getName(),
                "solarDateTime": lunar.getPrevJie().getSolar().toYmdHms(),
            },
            "nextJie": {
                "name": lunar.getNextJie().getName(),
                "solarDateTime": lunar.getNextJie().getSolar().toYmdHms(),
            },
        },
        "luck": luck,
        "warnings": warnings,
    }
    return payload


def render_structured_markdown(payload: dict[str, Any]) -> str:
    pillars = payload["pillars"]
    subject = payload["subject"]
    context = payload["reportContext"]
    luck = payload["luck"]
    lines = [
        "# BaZi Structured Data",
        "",
        "## Subject",
        "",
        f"- Birth: {subject['birthDate']} {subject['birthTime']} ({subject['calendarType']})",
        f"- Place: {subject['birthPlace']}",
        f"- Gender: {subject['gender']}",
        f"- Time precision: {subject['timePrecision']}",
        f"- Timezone: {subject['timezone']}",
        f"- Solar time applied: {subject['solarTimeApplied']} ({subject['solarTimePolicy']})",
        "",
        "## Report Context",
        "",
        f"- Current date: {context['currentDate']}",
        f"- Current age: {context['currentAge']}",
        f"- Life stage: {context['lifeStage']}",
        f"- Audience: {context['audience']}",
        f"- Relationship: {context['relationship']}",
        f"- Topic: {context['topic']}",
        "",
        "## Calculator Settings",
        "",
        f"- Engine: {payload['engine']} {payload['calculationVersion']}",
        f"- Day boundary sect: {payload['settings']['dayBoundarySect']}",
        f"- Luck sect: {payload['settings']['luckSect']}",
        f"- Year boundary: {payload['settings']['yearBoundary']}",
        f"- Month boundary: {payload['settings']['monthBoundary']}",
        "",
        "## Four Pillars",
        "",
        "| Pillar | GanZhi | Stem | Branch | Hidden stems | Stem ten god | Branch ten gods | DiShi |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for key, label in [("year", "Year"), ("month", "Month"), ("day", "Day"), ("hour", "Hour")]:
        item = pillars[key]
        lines.append(
            "| "
            + " | ".join(
                [
                    label,
                    item["ganZhi"],
                    item["stem"],
                    item["branch"],
                    ", ".join(item["hiddenStems"]),
                    item["stemTenGod"],
                    ", ".join(item["branchTenGods"]),
                    item["diShi"],
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Day Master",
            "",
            f"- Stem: {payload['dayMaster']['stem']}",
            f"- Element: {payload['dayMaster']['element']}",
            f"- Yin/Yang: {payload['dayMaster']['yinYang']}",
            "",
            "## Solar Terms",
            "",
            f"- Previous Jie: {payload['solarTerms']['previousJie']['name']} "
            f"{payload['solarTerms']['previousJie']['solarDateTime']}",
            f"- Next Jie: {payload['solarTerms']['nextJie']['name']} "
            f"{payload['solarTerms']['nextJie']['solarDateTime']}",
            "",
            "## Luck",
            "",
            f"- Available: {luck['available']}",
            f"- Direction: {luck.get('direction')}",
            f"- Start: {luck.get('startSolarDateTime')}",
            f"- Start offset: {luck.get('startOffset')}",
            f"- Current luck: {_format_current_luck(luck.get('currentLuck'))}",
            "",
            "| Index | GanZhi | Start year | End year | Start age | End age | True start age |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in luck.get("majorLuck", []):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(item["index"]),
                    item["pillar"],
                    str(item["startYear"]),
                    str(item["endYear"]),
                    str(item["startAge"]),
                    str(item["endAge"]),
                    str(item.get("trueStartAge", "")),
                ]
            )
            + " |"
        )
    if payload["warnings"]:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in payload["warnings"])
    return "\n".join(lines).rstrip() + "\n"


def render_report_context_markdown(payload: dict[str, Any]) -> str:
    context = payload["reportContext"]
    subject = payload["subject"]
    luck = payload["luck"]
    lines = [
        "# BaZi Report Context",
        "",
        f"- Birth date: {subject['birthDate']}",
        f"- Birth time: {subject['birthTime']}",
        f"- Birth place: {subject['birthPlace']}",
        f"- Gender: {subject['gender']}",
        f"- Current date: {context['currentDate']}",
        f"- Current age: {context['currentAge']}",
        f"- Life stage: {context['lifeStage']}",
        f"- Report audience: {context['audience']}",
        f"- Relationship: {context['relationship']}",
        f"- Topic priority: {context['topic']}",
        f"- Time precision: {subject['timePrecision']}",
        f"- Solar time applied: {subject['solarTimeApplied']}",
        f"- Near Jie boundary warning: {_has_boundary_warning(payload)}",
        f"- Near Zi hour warning: {_has_zi_warning(payload)}",
        "",
        "## Major Luck True Ages",
        "",
        "| Index | GanZhi | Years | Nominal ages | True start age |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in luck.get("majorLuck", []):
        lines.append(
            f"| {item['index']} | {item['pillar']} | {item['startYear']}-{item['endYear']} | "
            f"{item['startAge']}-{item['endAge']} | {item.get('trueStartAge', '')} |"
        )
    return "\n".join(lines).rstrip() + "\n"


def build_artifact_contents(payload: dict[str, Any]) -> dict[str, str]:
    return {
        "bazi_structured_data.json": json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        "bazi_structured_data.md": render_structured_markdown(payload),
        "bazi_report_context.md": render_report_context_markdown(payload),
    }


def write_artifacts(payload: dict[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = build_artifact_contents(payload)
    written: dict[str, str] = {}
    for name, content in files.items():
        path = out_dir / name
        path.write_text(content, encoding="utf-8")
        written[name] = str(path)
    return written


def _build_lunar(input_data: BaziInput, hour: int, minute: int) -> tuple[Solar, Lunar]:
    if input_data.calendar_type == "solar":
        solar = Solar.fromYmdHms(
            input_data.birth_date.year,
            input_data.birth_date.month,
            input_data.birth_date.day,
            hour,
            minute,
            0,
        )
        return solar, solar.getLunar()
    if input_data.calendar_type == "lunar":
        lunar = Lunar.fromYmdHms(
            input_data.birth_date.year,
            input_data.birth_date.month,
            input_data.birth_date.day,
            hour,
            minute,
            0,
        )
        return lunar.getSolar(), lunar
    raise ValueError("calendar_type must be solar or lunar")


def _pillars(eight_char: Any, lunar: Lunar) -> dict[str, dict[str, Any]]:
    return {
        "year": _pillar(
            eight_char.getYear(),
            eight_char.getYearGan(),
            eight_char.getYearZhi(),
            eight_char.getYearHideGan(),
            eight_char.getYearShiShenGan(),
            eight_char.getYearShiShenZhi(),
            eight_char.getYearWuXing(),
            eight_char.getYearNaYin(),
            eight_char.getYearDiShi(),
        ),
        "month": {
            **_pillar(
                eight_char.getMonth(),
                eight_char.getMonthGan(),
                eight_char.getMonthZhi(),
                eight_char.getMonthHideGan(),
                eight_char.getMonthShiShenGan(),
                eight_char.getMonthShiShenZhi(),
                eight_char.getMonthWuXing(),
                eight_char.getMonthNaYin(),
                eight_char.getMonthDiShi(),
            ),
            "solarTermBoundary": lunar.getPrevJie().getName(),
        },
        "day": _pillar(
            eight_char.getDay(),
            eight_char.getDayGan(),
            eight_char.getDayZhi(),
            eight_char.getDayHideGan(),
            eight_char.getDayShiShenGan(),
            eight_char.getDayShiShenZhi(),
            eight_char.getDayWuXing(),
            eight_char.getDayNaYin(),
            eight_char.getDayDiShi(),
        ),
        "hour": _pillar(
            eight_char.getTime(),
            eight_char.getTimeGan(),
            eight_char.getTimeZhi(),
            eight_char.getTimeHideGan(),
            eight_char.getTimeShiShenGan(),
            eight_char.getTimeShiShenZhi(),
            eight_char.getTimeWuXing(),
            eight_char.getTimeNaYin(),
            eight_char.getTimeDiShi(),
        ),
    }


def _pillar(
    gan_zhi: str,
    stem: str,
    branch: str,
    hidden_stems: list[str],
    stem_ten_god: str,
    branch_ten_gods: list[str],
    wuxing: str,
    nayin: str,
    dishi: str,
) -> dict[str, Any]:
    return {
        "ganZhi": gan_zhi,
        "stem": stem,
        "branch": branch,
        "hiddenStems": hidden_stems,
        "stemTenGod": stem_ten_god,
        "branchTenGods": branch_ten_gods,
        "wuxing": wuxing,
        "nayin": nayin,
        "diShi": dishi,
    }


def _ten_gods(pillars: dict[str, dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, item in pillars.items():
        result[f"{key}Stem"] = item["stemTenGod"]
        result[f"{key}Branch"] = item["branchTenGods"]
    return result


def _five_elements(pillars: dict[str, dict[str, Any]]) -> dict[str, Any]:
    visible = {"木": 0, "火": 0, "土": 0, "金": 0, "水": 0}
    hidden = {"木": 0, "火": 0, "土": 0, "金": 0, "水": 0}
    for item in pillars.values():
        stem_element = STEM_ELEMENTS.get(item["stem"])
        branch_element = BRANCH_ELEMENTS.get(item["branch"])
        if stem_element:
            visible[stem_element] += 1
        if branch_element:
            visible[branch_element] += 1
        for stem in item["hiddenStems"]:
            element = STEM_ELEMENTS.get(stem)
            if element:
                hidden[element] += 1
    return {"visible": visible, "hiddenStems": hidden}


def _relations(branches: list[str]) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = {
        "combinations": [],
        "clashes": [],
        "harms": [],
        "punishments": [],
        "threeMeetings": [],
        "threeCombinations": [],
    }
    for i, left in enumerate(branches):
        for right in branches[i + 1 :]:
            pair = "".join(sorted([left, right], key=lambda branch: LunarUtil.ZHI.index(branch)))
            for key, table in BRANCH_PAIRS.items():
                if pair in table:
                    result[key].append({"branches": pair, "label": table[pair]})

    branch_set = set(branches)
    for key, groups in THREE_GROUPS.items():
        for group, label in groups.items():
            if group.issubset(branch_set):
                group_branches = "".join(
                    sorted(group, key=lambda branch: LunarUtil.ZHI.index(branch))
                )
                result[key].append({"branches": group_branches, "label": label})
    return result


def _luck(eight_char: Any, input_data: BaziInput, month_pillar: str) -> dict[str, Any]:
    gender_code = _gender_code(input_data.gender)
    if gender_code is None:
        return {
            "available": False,
            "reason": "gender is required for forward/reverse major luck calculation",
            "monthPillar": month_pillar,
            "majorLuck": [],
        }
    yun = eight_char.getYun(gender_code, input_data.luck_sect)
    start_solar = yun.getStartSolar()
    major_luck = []
    for item in yun.getDaYun(11):
        index = item.getIndex()
        if index < 1:
            continue
        cycle_start = start_solar.nextYear((index - 1) * 10)
        next_cycle_start = start_solar.nextYear(index * 10)
        cycle_start_date = _date_from_solar(cycle_start)
        cycle_end_date = _date_from_solar(next_cycle_start) - timedelta(days=1)
        major_luck.append(
            {
                "index": index,
                "pillar": item.getGanZhi(),
                "startYear": item.getStartYear(),
                "endYear": item.getEndYear(),
                "startAge": item.getStartAge(),
                "endAge": item.getEndAge(),
                "startSolarDateTime": cycle_start.toYmdHms(),
                "endSolarDate": cycle_end_date.isoformat(),
                "trueStartAge": _completed_age(input_data.birth_date, cycle_start_date),
            }
        )
    current = _current_luck(major_luck, input_data.current_date)
    return {
        "available": True,
        "direction": "forward" if yun.isForward() else "reverse",
        "genderCode": gender_code,
        "sect": input_data.luck_sect,
        "monthPillar": month_pillar,
        "startSolarDateTime": start_solar.toYmdHms(),
        "startOffset": {
            "years": yun.getStartYear(),
            "months": yun.getStartMonth(),
            "days": yun.getStartDay(),
            "hours": yun.getStartHour(),
        },
        "currentLuck": current,
        "majorLuck": major_luck,
    }


def _current_luck(major_luck: list[dict[str, Any]], current_date: date) -> dict[str, Any] | None:
    for item in major_luck:
        start = date.fromisoformat(str(item["startSolarDateTime"])[:10])
        end = date.fromisoformat(str(item["endSolarDate"]))
        if start <= current_date <= end:
            return item
    return None


def _warnings(
    input_data: BaziInput,
    time_uncertain: bool,
    solar: Solar,
    lunar: Lunar,
) -> list[str]:
    warnings: list[str] = []
    if time_uncertain:
        warnings.append("birth time is not exact; hour pillar and luck timing are degraded")
    if input_data.solar_time_policy != "civil":
        warnings.append("true solar time was requested or noted but is not applied by this tool")
    prev_minutes = abs(solar.subtractMinute(lunar.getPrevJie().getSolar()))
    next_minutes = abs(lunar.getNextJie().getSolar().subtractMinute(solar))
    if min(prev_minutes, next_minutes) <= 1440:
        warnings.append("birth time is within 24 hours of a Jie boundary")
    hour = solar.getHour()
    minute = solar.getMinute()
    if hour == 23 or (hour == 22 and minute >= 30) or (hour == 0 and minute <= 30):
        warnings.append("birth time is near Zi hour/day-boundary sensitivity")
    return warnings


def _parse_birth_time(value: str, precision: str) -> tuple[int, int, bool]:
    if precision == "unknown" or not value:
        return 12, 0, True
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError("birth_time must be HH:MM")
    hour = int(parts[0])
    minute = int(parts[1])
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("birth_time must be a valid HH:MM value")
    return hour, minute, precision != "exact"


def _gender_code(value: str) -> int | None:
    normalized = value.strip().lower()
    if normalized in {"男", "male", "man", "m", "1"}:
        return 1
    if normalized in {"女", "female", "woman", "f", "0"}:
        return 0
    return None


def _completed_age(birth: date, current: date) -> int:
    years = current.year - birth.year
    if (current.month, current.day) < (birth.month, birth.day):
        years -= 1
    return years


def _life_stage(age: int) -> str:
    if age < 13:
        return "child"
    if age < 20:
        return "teen"
    if age < 65:
        return "adult"
    return "elder"


def _date_from_solar(solar: Solar) -> date:
    return date(solar.getYear(), solar.getMonth(), solar.getDay())


def _format_current_luck(value: dict[str, Any] | None) -> str:
    if value is None:
        return "none"
    return f"{value['pillar']} ({value['startYear']}-{value['endYear']})"


def _has_boundary_warning(payload: dict[str, Any]) -> bool:
    return any("Jie boundary" in warning for warning in payload["warnings"])


def _has_zi_warning(payload: dict[str, Any]) -> bool:
    return any("Zi hour" in warning for warning in payload["warnings"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Calculate BaZi chart artifacts.")
    parser.add_argument("--birth-date", required=True, help="Birth date as YYYY-MM-DD")
    parser.add_argument("--birth-time", default="", help="Birth time as HH:MM")
    parser.add_argument("--birth-place", default="[not provided]")
    parser.add_argument("--gender", default="未提供")
    parser.add_argument("--calendar-type", choices=["solar", "lunar"], default="solar")
    parser.add_argument(
        "--time-precision",
        choices=["exact", "approximate", "part_of_day", "unknown"],
        default="exact",
    )
    parser.add_argument("--timezone", default="Asia/Shanghai")
    parser.add_argument("--latitude", type=float)
    parser.add_argument("--longitude", type=float)
    parser.add_argument("--current-date", default=date.today().isoformat())
    parser.add_argument("--audience", default="self")
    parser.add_argument("--relationship", default="[not provided]")
    parser.add_argument("--topic", default="[not provided]")
    parser.add_argument("--day-boundary-sect", type=int, choices=[1, 2], default=2)
    parser.add_argument("--luck-sect", type=int, choices=[1, 2], default=2)
    parser.add_argument(
        "--solar-time-policy",
        choices=["civil", "record_only"],
        default="civil",
    )
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument(
        "--emit-artifact-content",
        action="store_true",
        help="Return artifact contents in JSON instead of only chart facts.",
    )
    return parser.parse_args()


def input_from_args(args: argparse.Namespace) -> BaziInput:
    return BaziInput(
        birth_date=date.fromisoformat(args.birth_date),
        birth_time=args.birth_time,
        birth_place=args.birth_place,
        gender=args.gender,
        calendar_type=args.calendar_type,
        time_precision=args.time_precision,
        timezone_name=args.timezone,
        latitude=args.latitude,
        longitude=args.longitude,
        current_date=date.fromisoformat(args.current_date),
        audience=args.audience,
        relationship=args.relationship,
        topic=args.topic,
        day_boundary_sect=args.day_boundary_sect,
        luck_sect=args.luck_sect,
        solar_time_policy=args.solar_time_policy,
    )


def main() -> None:
    args = parse_args()
    payload = calculate_bazi(input_from_args(args))
    if args.out_dir:
        written = write_artifacts(payload, args.out_dir)
        print(json.dumps({"ok": True, "files": written}, ensure_ascii=False, indent=2))
        return
    if args.emit_artifact_content:
        print(
            json.dumps(
                {
                    "ok": True,
                    "payload": payload,
                    "artifacts": build_artifact_contents(payload),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
