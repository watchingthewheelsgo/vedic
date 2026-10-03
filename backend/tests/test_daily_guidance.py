from __future__ import annotations

import asyncio
import json
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from lunar_python.util import LunarUtil

from app.auth import AuthenticatedUser
from app.services.daily_guidance import read_daily_guidance
from app.services.daily_journal import calendar_day
from app.tools.bazi.calculate_chart import BaziInput, calculate_bazi
from app.tools.bazi.daily_guidance import (
    CATALOG,
    RULES,
    STEMS,
    evaluate_day,
    punishment,
    ten_god,
    trines,
)


def natal(day_master: str = "甲", **branches: str) -> dict:
    return {"dayMaster": day_master, "branches": {"day": "午", **branches}}


def test_ten_god_known_pairs_and_matches_lunar_python_table():
    assert ten_god("甲", "己") == "正财"
    assert ten_god("甲", "甲") == "比肩"
    assert ten_god("甲", "乙") == "劫财"
    assert ten_god("甲", "丙") == "食神"
    assert ten_god("甲", "丁") == "伤官"
    assert ten_god("甲", "戊") == "偏财"
    assert ten_god("甲", "庚") == "七杀"
    assert ten_god("甲", "辛") == "正官"
    assert ten_god("甲", "壬") == "偏印"
    assert ten_god("甲", "癸") == "正印"
    for day_master in STEMS:
        for stem in STEMS:
            assert ten_god(day_master, stem) == LunarUtil.SHI_SHEN[day_master + stem]
    with pytest.raises(ValueError):
        ten_god("甲", "子")


def test_direct_wealth_day_and_day_branch_clash():
    result = evaluate_day(natal("甲"), "己酉")
    assert result["facts"]["tenGod"] == "正财"
    assert "BZD.TENGOD.ZHENGCAI" in result["ruleIds"]
    assert "money_talks" in [item["id"] for item in result["goodFor"]]

    clash = evaluate_day(natal("甲"), "丙子")
    assert clash["facts"]["clashes"] == [{"natalPillar": "day", "branches": "子午"}]
    assert "BZD.BRANCH.CLASH_DAY" in clash["ruleIds"]
    avoid = [item["id"] for item in clash["avoid"]]
    assert avoid[:2] == ["confrontation", "major_relationship_decisions"]


def test_clashes_with_year_and_month_and_hour_only_when_given():
    result = evaluate_day(natal("甲", year="卯", month="申"), "丙寅")
    pillars = {item["natalPillar"] for item in result["facts"]["clashes"]}
    assert pillars == {"month"}
    assert "BZD.BRANCH.CLASH_MONTH" in result["ruleIds"]
    result = evaluate_day(natal("甲", year="酉"), "丁卯")
    assert "BZD.BRANCH.CLASH_YEAR" in result["ruleIds"]
    assert "BZD.BRANCH.CLASH_HOUR" not in result["ruleIds"]
    result = evaluate_day(natal("甲", hour="酉"), "丁卯")
    assert "BZD.BRANCH.CLASH_HOUR" in result["ruleIds"]


def test_combinations_trines_punishments_and_harms():
    combine = evaluate_day(natal("甲"), "己未")
    assert combine["facts"]["combinations"][0]["label"] == "六合化土"
    assert "BZD.BRANCH.COMBINE_DAY" in combine["ruleIds"]
    assert "relationship_time" in [item["id"] for item in combine["goodFor"]]
    # 甲 + 己 also forms a stem combination with the Day Master.
    assert combine["facts"]["stemCombination"] == "甲己合土"

    assert trines("午", ["寅", "戌"]) == [
        {"branches": "寅午戌", "label": "三合火局", "kind": "三合"}
    ]
    assert trines("寅", ["午"])[0]["kind"] == "半合"
    assert trines("寅", ["戌"]) == []  # no cardinal branch: not a half combination

    assert punishment("子", "卯") == "无礼之刑"
    assert punishment("寅", "巳") == "无恩之刑"
    assert punishment("午", "午") == "自刑"
    assert punishment("子", "子") is None
    harm = evaluate_day(natal("甲"), "癸丑")
    assert harm["facts"]["harms"] == [{"natalPillar": "day", "branches": "丑午"}]
    assert "relying_on_promises" in [item["id"] for item in harm["avoid"]]


def test_every_day_has_bounded_traceable_catalog_items():
    natal_chart = natal("庚", year="辰", month="卯", hour="亥")
    for index in range(60):
        pillar = LunarUtil.JIA_ZI[index]
        result = evaluate_day(natal_chart, pillar)
        assert 2 <= len(result["goodFor"]) <= 4
        assert 1 <= len(result["avoid"]) <= 3
        good = {item["id"] for item in result["goodFor"]}
        avoid = {item["id"] for item in result["avoid"]}
        assert not good & avoid
        for item in avoid:
            assert not good & set(CATALOG[item].get("blocks", []))
        for item in [*result["goodFor"], *result["avoid"]]:
            assert item["zh"] and item["en"] and item["ja"]
            assert set(item["ruleIds"]) <= set(result["ruleIds"])
            assert set(item["ruleIds"]) <= set(RULES)


def test_catalog_and_rules_are_closed():
    for rule in RULES.values():
        assert rule.source
        for item in [*rule.good, *rule.avoid]:
            assert item in CATALOG
        for item in rule.avoid:  # a rule never suppresses its own supportive items
            assert not set(rule.good) & set(CATALOG[item].get("blocks", []))
    for entry in CATALOG.values():
        for blocked in entry.get("blocks", []):
            assert blocked in CATALOG


def _bazi_record(audience: str = "self") -> str:
    payload = calculate_bazi(
        BaziInput(
            birth_date=date(1990, 6, 15),
            birth_time="10:30",
            birth_place="Shanghai",
            gender="female",
            calendar_type="solar",
            time_precision="exact",
            timezone_name="Asia/Shanghai",
            latitude=None,
            longitude=None,
            current_date=date(2026, 10, 2),
            audience=audience,
            relationship="[not provided]",
            topic="[not provided]",
            day_boundary_sect=2,
            luck_sect=2,
            solar_time_policy="civil",
        )
    )
    return json.dumps(payload, ensure_ascii=False)


def _vedic_record(relationship: str = "self") -> str:
    return json.dumps(
        {
            "subject": {"readerRelationship": relationship, "genderContext": "male"},
            "birthAssertion": {
                "localDate": "1988-03-02",
                "reportedLocalTime": "08:15",
                "reportedPlace": "Tokyo",
                "timeCertainty": "approximate",
            },
            "canonicalMoment": {
                "localDatetime": "1988-03-02T08:15:00+09:00",
                "timezoneId": "Asia/Tokyo",
            },
        }
    )


def _container(sessions: dict[str, list[tuple[str, str, str | None]]]):
    """sessions: owner -> [(session_id, stage, file contents)] newest first."""
    files: dict[tuple[str, str], str] = {}
    by_owner: dict[str, list] = {}
    for owner, items in sessions.items():
        for session_id, stage, content in items:
            name = "bazi_chart_record.json" if stage.startswith("bazi") else "chart_record.json"
            if content is not None:
                files[(session_id, name)] = content
            by_owner.setdefault(owner, []).append(
                SimpleNamespace(
                    session_id=session_id,
                    stage=stage,
                    subject=None if stage.startswith("bazi") else SimpleNamespace(),
                )
            )

    async def list_session_summaries(owner_user_id=None):
        return by_owner.get(owner_user_id, [])

    return SimpleNamespace(
        metadata_store=SimpleNamespace(list_session_summaries=list_session_summaries),
        skill_workspace=SimpleNamespace(
            read_artifact_text=lambda session_id, path: files.get((session_id, path))
        ),
    )


def test_api_owner_scoped_prefers_bazi_record_and_falls_back(monkeypatch):
    import app.container

    container = _container(
        {
            "alice": [
                ("vedic-new", "chart_ready", _vedic_record()),
                ("bazi-other", "bazi_ready", _bazi_record(audience="friend")),
                ("bazi-self", "bazi_ready", _bazi_record()),
            ],
            "bob": [
                ("vedic-partner", "chart_ready", _vedic_record("partner")),
                ("vedic-self", "chart_ready", _vedic_record()),
            ],
        }
    )
    monkeypatch.setattr(app.container, "get_container", lambda: container)
    alice = AuthenticatedUser(user_id="alice", auth_mode="clerk")
    bob = AuthenticatedUser(user_id="bob", auth_mode="clerk")
    carol = AuthenticatedUser(user_id="carol", auth_mode="clerk")
    day = date(2026, 10, 2)

    result = asyncio.run(read_daily_guidance(day, "Asia/Shanghai", alice))
    assert result["calendar"] == calendar_day(day, "Asia/Shanghai")
    guidance = result["guidance"]
    assert guidance["natal"]["source"] == "bazi_chart_record"
    assert guidance["natal"]["sessionId"] == "bazi-self"
    assert guidance["dayPillar"] == result["calendar"]["pillar"]
    assert guidance["facts"]["tenGod"] == ten_god(
        guidance["natal"]["dayMaster"], result["calendar"]["stem"]
    )

    result = asyncio.run(read_daily_guidance(day, "Asia/Shanghai", bob))
    natal_info = result["guidance"]["natal"]
    assert natal_info["source"] == "vedic_chart_record"
    assert natal_info["sessionId"] == "vedic-self"
    assert natal_info["pillars"]["hour"] is None  # approximate time: hour pillar omitted
    assert "BZD.BRANCH.CLASH_HOUR" not in result["guidance"]["ruleIds"]

    result = asyncio.run(read_daily_guidance(day, "Asia/Shanghai", carol))
    assert result == {
        "calendar": calendar_day(day, "Asia/Shanghai"),
        "guidance": None,
        "reason": "no_birth_details",
    }

    with pytest.raises(HTTPException) as exc:
        asyncio.run(read_daily_guidance(day, "Not/AZone", alice))
    assert exc.value.status_code == 422


def test_bazi_sessions_summarize_their_birth_subject(tmp_path):
    import json

    from app.services.metadata_store import MetadataStore

    (tmp_path / "bazi_chart_record.json").write_text(
        json.dumps(
            {
                "subject": {
                    "birthDate": "1992-05-18",
                    "birthTime": "",
                    "birthPlace": "CN-350100",
                    "timePrecision": "unknown",
                    "gender": "女",
                    "timezone": "Asia/Shanghai",
                },
                "reportContext": {"audience": "self"},
            }
        ),
        encoding="utf-8",
    )
    store = object.__new__(MetadataStore)
    subject = store._subject_json(tmp_path)
    assert subject is not None
    assert subject["birthPlace"] == "CN-350100"
    assert subject["birthTime"] is None
    assert subject["relationship"] == "self"
    assert subject["gender"] == "女"


def test_reindexed_bazi_sessions_stay_bazi(tmp_path):
    from app.services.metadata_store import MetadataStore

    store = object.__new__(MetadataStore)
    files = [tmp_path / "bazi_chart_record.json", tmp_path / "bazi_chart_foundation.md"]
    assert (
        store._derive_stage(files, {"status": "bazi_calculator_complete"}, "draft") == "bazi_ready"
    )
    files.append(tmp_path / "bazi_life_report.md")
    assert store._derive_stage(files, None, "completed") == "bazi_complete"
