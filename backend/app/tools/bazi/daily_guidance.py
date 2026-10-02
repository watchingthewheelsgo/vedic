"""Deterministic personal BaZi day guidance (宜 / 忌).

Pure functions only: a day's stem-branch pillar is compared with natal pillars produced by
``bazi-calculator``. Every relation is a registered rule with a stable ID, and every output
item comes from a closed, versioned activity catalog. No LLM produces or edits these facts.

Day Master strength and useful elements are not modelled: ``bazi-calculator`` does not
expose a strength judgement, so no rule depends on one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

GUIDANCE_VERSION = "bazi-daily-guidance/v1"
CATALOG_VERSION = "bazi-daily-activities/v1"
LIMITATIONS = ["day-master-strength-not-modelled", "civil-day-pillar-midnight-boundary"]

STEMS = "甲乙丙丁戊己庚辛壬癸"
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
STEM_ELEMENT = {
    "甲": "木",
    "乙": "木",
    "丙": "火",
    "丁": "火",
    "戊": "土",
    "己": "土",
    "庚": "金",
    "辛": "金",
    "壬": "水",
    "癸": "水",
}
# 生: each element produces the next one in this cycle.
PRODUCES = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
# 克: each element controls the mapped element.
CONTROLS = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}

STEM_COMBINATIONS = {
    frozenset("甲己"): "甲己合土",
    frozenset("乙庚"): "乙庚合金",
    frozenset("丙辛"): "丙辛合水",
    frozenset("丁壬"): "丁壬合木",
    frozenset("戊癸"): "戊癸合火",
}
SIX_COMBINATIONS = {
    frozenset("子丑"): "六合化土",
    frozenset("寅亥"): "六合化木",
    frozenset("卯戌"): "六合化火",
    frozenset("辰酉"): "六合化金",
    frozenset("巳申"): "六合化水",
    frozenset("午未"): "六合化土",
}
SIX_CLASHES = {frozenset(pair) for pair in ["子午", "丑未", "寅申", "卯酉", "辰戌", "巳亥"]}
SIX_HARMS = {frozenset(pair) for pair in ["子未", "丑午", "寅巳", "卯辰", "申亥", "酉戌"]}
THREE_COMBINATIONS = {
    "申子辰": "三合水局",
    "亥卯未": "三合木局",
    "寅午戌": "三合火局",
    "巳酉丑": "三合金局",
}
# A half combination (半合) must contain the cardinal middle branch of the frame.
CARDINAL_BRANCHES = {"子", "卯", "午", "酉"}
PUNISHMENT_GROUPS = [("寅巳申", "无恩之刑"), ("丑戌未", "恃势之刑")]
MUTUAL_PUNISHMENT = frozenset("子卯")
SELF_PUNISHMENT = {"辰", "午", "酉", "亥"}

NATAL_PILLARS = ("year", "month", "day", "hour")


@dataclass(frozen=True)
class Rule:
    rule_id: str
    source: str
    good: tuple[str, ...]
    avoid: tuple[str, ...]


# Each rule: stable ID, short source note, and catalog items it proposes (priority order).
RULES: dict[str, Rule] = {
    rule.rule_id: rule
    for rule in [
        Rule(
            "BZD.TENGOD.BIJIAN",
            "Ten gods: day stem same element and polarity as Day Master (比肩).",
            ("peer_collaboration", "exercise"),
            ("lending_money",),
        ),
        Rule(
            "BZD.TENGOD.JIECAI",
            "Ten gods: day stem same element, opposite polarity (劫财).",
            ("exercise", "peer_collaboration"),
            ("lending_money", "impulse_spending"),
        ),
        Rule(
            "BZD.TENGOD.SHISHEN",
            "Ten gods: Day Master produces day stem, same polarity (食神).",
            ("creative_work", "shared_meals", "rest"),
            ("overindulgence",),
        ),
        Rule(
            "BZD.TENGOD.SHANGGUAN",
            "Ten gods: Day Master produces day stem, opposite polarity (伤官).",
            ("creative_work", "presenting_ideas"),
            ("challenging_authority",),
        ),
        Rule(
            "BZD.TENGOD.PIANCAI",
            "Ten gods: Day Master controls day stem, same polarity (偏财).",
            ("networking", "side_projects"),
            ("speculative_risk",),
        ),
        Rule(
            "BZD.TENGOD.ZHENGCAI",
            "Ten gods: Day Master controls day stem, opposite polarity (正财).",
            ("money_talks", "signing_agreements", "budgeting"),
            ("impulse_spending",),
        ),
        Rule(
            "BZD.TENGOD.QISHA",
            "Ten gods: day stem controls Day Master, same polarity (七杀).",
            ("hard_tasks", "exercise"),
            ("confrontation", "risky_activities"),
        ),
        Rule(
            "BZD.TENGOD.ZHENGGUAN",
            "Ten gods: day stem controls Day Master, opposite polarity (正官).",
            ("formal_applications", "meeting_superiors", "signing_agreements"),
            ("bending_rules",),
        ),
        Rule(
            "BZD.TENGOD.PIANYIN",
            "Ten gods: day stem produces Day Master, same polarity (偏印).",
            ("research", "quiet_reflection"),
            ("rushed_decisions",),
        ),
        Rule(
            "BZD.TENGOD.ZHENGYIN",
            "Ten gods: day stem produces Day Master, opposite polarity (正印).",
            ("learning", "seeking_advice", "rest"),
            ("overcommitting",),
        ),
        Rule(
            "BZD.STEM.COMBINE_DM",
            "天干五合: day stem combines with the Day Master.",
            ("partnership_talks",),
            (),
        ),
        Rule(
            "BZD.BRANCH.CLASH_DAY",
            "地支六冲: day branch clashes the natal day branch (spouse palace).",
            (),
            ("confrontation", "major_relationship_decisions"),
        ),
        Rule(
            "BZD.BRANCH.CLASH_MONTH",
            "地支六冲: day branch clashes the natal month branch (career/parents palace).",
            (),
            ("major_career_moves",),
        ),
        Rule(
            "BZD.BRANCH.CLASH_YEAR",
            "地支六冲: day branch clashes the natal year branch (family/roots palace).",
            (),
            ("family_disputes",),
        ),
        Rule(
            "BZD.BRANCH.CLASH_HOUR",
            "地支六冲: day branch clashes the natal hour branch (exact birth time only).",
            (),
            ("rushed_decisions",),
        ),
        Rule(
            "BZD.BRANCH.COMBINE_DAY",
            "地支六合: day branch combines with the natal day branch.",
            ("relationship_time", "reconciliation"),
            (),
        ),
        Rule(
            "BZD.BRANCH.COMBINE_OTHER",
            "地支六合: day branch combines with a natal year, month or hour branch.",
            ("networking",),
            (),
        ),
        Rule(
            "BZD.BRANCH.TRINE",
            "三合/半合: day branch completes a three-harmony frame with natal branches.",
            ("team_projects",),
            (),
        ),
        Rule(
            "BZD.BRANCH.PUNISHMENT",
            "三刑/相刑/自刑: day branch forms a punishment with natal branches.",
            (),
            ("legal_paperwork_disputes",),
        ),
        Rule(
            "BZD.BRANCH.HARM_DAY",
            "六害: day branch harms the natal day branch.",
            (),
            ("relying_on_promises",),
        ),
        Rule(
            "BZD.FALLBACK.STEADY",
            "Fallback when relations yield fewer than two supportive items.",
            ("steady_routine", "journaling"),
            (),
        ),
    ]
}

TEN_GOD_RULES = {
    "比肩": "BZD.TENGOD.BIJIAN",
    "劫财": "BZD.TENGOD.JIECAI",
    "食神": "BZD.TENGOD.SHISHEN",
    "伤官": "BZD.TENGOD.SHANGGUAN",
    "偏财": "BZD.TENGOD.PIANCAI",
    "正财": "BZD.TENGOD.ZHENGCAI",
    "七杀": "BZD.TENGOD.QISHA",
    "正官": "BZD.TENGOD.ZHENGGUAN",
    "偏印": "BZD.TENGOD.PIANYIN",
    "正印": "BZD.TENGOD.ZHENGYIN",
}

# Closed activity catalog. ``blocks`` lists good items an avoid item suppresses.
CATALOG: dict[str, dict[str, Any]] = {
    # Good for
    "peer_collaboration": {
        "zh": "与同伴合作",
        "en": "Working with peers",
        "ja": "仲間との協力",
    },
    "exercise": {"zh": "运动锻炼", "en": "Exercise", "ja": "運動"},
    "creative_work": {"zh": "创作与表达", "en": "Creative work", "ja": "創作・表現"},
    "shared_meals": {"zh": "聚餐交流", "en": "Sharing a meal", "ja": "会食"},
    "rest": {"zh": "休息充电", "en": "Rest and recharge", "ja": "休養"},
    "presenting_ideas": {
        "zh": "展示想法、演讲",
        "en": "Presenting your ideas",
        "ja": "アイデアの発表",
    },
    "networking": {"zh": "拓展人脉", "en": "Meeting new contacts", "ja": "人脈づくり"},
    "side_projects": {"zh": "副业与新机会", "en": "Side projects", "ja": "副業・新しい機会"},
    "money_talks": {"zh": "谈钱、谈薪资", "en": "Money talks", "ja": "お金の話し合い"},
    "signing_agreements": {"zh": "签约", "en": "Signing agreements", "ja": "契約"},
    "budgeting": {"zh": "理财记账", "en": "Budgeting", "ja": "家計の見直し"},
    "hard_tasks": {
        "zh": "攻克难题",
        "en": "Tackling a hard task",
        "ja": "難しい課題に取り組む",
    },
    "formal_applications": {
        "zh": "正式申请、办手续",
        "en": "Formal applications",
        "ja": "正式な申請・手続き",
    },
    "meeting_superiors": {
        "zh": "拜见上级",
        "en": "Meeting your manager",
        "ja": "上司との面談",
    },
    "research": {"zh": "研究钻研", "en": "Research", "ja": "研究・調べもの"},
    "quiet_reflection": {"zh": "独处思考", "en": "Quiet reflection", "ja": "一人で考える"},
    "learning": {"zh": "学习进修", "en": "Learning", "ja": "学び"},
    "seeking_advice": {"zh": "请教长辈或导师", "en": "Asking a mentor", "ja": "師に相談"},
    "partnership_talks": {
        "zh": "商谈合作",
        "en": "Partnership talks",
        "ja": "協業の話し合い",
    },
    "relationship_time": {
        "zh": "陪伴伴侣",
        "en": "Time with your partner",
        "ja": "パートナーと過ごす",
    },
    "reconciliation": {"zh": "化解误会", "en": "Making up after a quarrel", "ja": "仲直り"},
    "team_projects": {"zh": "团队项目", "en": "Team projects", "ja": "チームの仕事"},
    "steady_routine": {"zh": "按部就班", "en": "Your usual routine", "ja": "いつもの日課"},
    "journaling": {"zh": "记录与复盘", "en": "Journaling", "ja": "記録と振り返り"},
    # Avoid
    "lending_money": {"zh": "借钱给人", "en": "Lending money", "ja": "お金を貸す"},
    "impulse_spending": {
        "zh": "冲动消费",
        "en": "Impulse spending",
        "ja": "衝動買い",
    },
    "overindulgence": {"zh": "暴饮暴食", "en": "Overindulging", "ja": "食べ過ぎ・飲み過ぎ"},
    "challenging_authority": {
        "zh": "顶撞上级",
        "en": "Arguing with your boss",
        "ja": "上司に反論する",
        "blocks": ["meeting_superiors"],
    },
    "speculative_risk": {
        "zh": "投机冒险",
        "en": "Risky bets",
        "ja": "投機",
    },
    "confrontation": {
        "zh": "正面冲突",
        "en": "Confrontations",
        "ja": "正面衝突",
        "blocks": ["reconciliation"],
    },
    "risky_activities": {"zh": "冒险活动", "en": "Risky activities", "ja": "危険な行動"},
    "bending_rules": {"zh": "违规走捷径", "en": "Bending the rules", "ja": "規則を破る"},
    "rushed_decisions": {
        "zh": "仓促决定",
        "en": "Rushed decisions",
        "ja": "急な決断",
        "blocks": ["signing_agreements"],
    },
    "overcommitting": {"zh": "揽事过多", "en": "Taking on too much", "ja": "抱え込み過ぎ"},
    "major_relationship_decisions": {
        "zh": "感情重大决定",
        "en": "Big relationship decisions",
        "ja": "恋愛の大きな決断",
        "blocks": ["relationship_time", "partnership_talks"],
    },
    "major_career_moves": {
        "zh": "跳槽或重大工作变动",
        "en": "Big career moves",
        "ja": "転職・大きな仕事の変化",
        "blocks": ["formal_applications"],
    },
    "family_disputes": {"zh": "家庭争执", "en": "Family arguments", "ja": "家族との口論"},
    "legal_paperwork_disputes": {
        "zh": "官司与文书纠纷",
        "en": "Legal or paperwork disputes",
        "ja": "訴訟・書類のトラブル",
        "blocks": ["signing_agreements"],
    },
    "relying_on_promises": {
        "zh": "轻信口头承诺",
        "en": "Relying on casual promises",
        "ja": "口約束を信じる",
    },
}

MAX_GOOD = 4
MAX_AVOID = 3
MIN_GOOD = 2


def ten_god(day_master: str, stem: str) -> str:
    """Ten-god name of ``stem`` relative to ``day_master`` (both heavenly stems)."""
    if day_master not in STEM_ELEMENT or stem not in STEM_ELEMENT:
        raise ValueError("ten_god requires two heavenly stems")
    me, other = STEM_ELEMENT[day_master], STEM_ELEMENT[stem]
    same_polarity = STEMS.index(day_master) % 2 == STEMS.index(stem) % 2
    if me == other:
        return "比肩" if same_polarity else "劫财"
    if PRODUCES[me] == other:
        return "食神" if same_polarity else "伤官"
    if CONTROLS[me] == other:
        return "偏财" if same_polarity else "正财"
    if CONTROLS[other] == me:
        return "七杀" if same_polarity else "正官"
    return "偏印" if same_polarity else "正印"


def stem_combination(day_master: str, stem: str) -> str | None:
    return STEM_COMBINATIONS.get(frozenset((day_master, stem)))


def _pair(left: str, right: str) -> str:
    return "".join(sorted((left, right), key=BRANCHES.index))


def is_clash(left: str, right: str) -> bool:
    return frozenset((left, right)) in SIX_CLASHES


def six_combination(left: str, right: str) -> str | None:
    if left == right:
        return None
    return SIX_COMBINATIONS.get(frozenset((left, right)))


def is_harm(left: str, right: str) -> bool:
    return frozenset((left, right)) in SIX_HARMS


def punishment(left: str, right: str) -> str | None:
    if left == right:
        return "自刑" if left in SELF_PUNISHMENT else None
    if frozenset((left, right)) == MUTUAL_PUNISHMENT:
        return "无礼之刑"
    for group, label in PUNISHMENT_GROUPS:
        if left in group and right in group:
            return label
    return None


def trines(day_branch: str, natal_branches: list[str]) -> list[dict[str, str]]:
    """三合 (full frame with two natal branches) or 半合 (with one, containing the cardinal)."""
    found: list[dict[str, str]] = []
    natal = set(natal_branches)
    for frame, label in THREE_COMBINATIONS.items():
        if day_branch not in frame:
            continue
        others = [branch for branch in frame if branch != day_branch]
        present = [branch for branch in others if branch in natal]
        if len(present) == 2:
            found.append({"branches": frame, "label": label, "kind": "三合"})
        elif len(present) == 1 and CARDINAL_BRANCHES & {day_branch, present[0]}:
            found.append(
                {"branches": _pair(day_branch, present[0]), "label": label, "kind": "半合"}
            )
    return found


def evaluate_day(natal: dict[str, Any], day_pillar: str) -> dict[str, Any]:
    """Compare a day pillar with natal pillars and return guidance with traceable rules.

    ``natal`` needs ``dayMaster`` (a stem) and ``branches`` mapping pillar names
    (year/month/day/hour) to branches. Omit ``hour`` when the birth time is not exact.
    """
    day_master = natal["dayMaster"]
    branches: dict[str, str] = {
        key: value for key, value in natal["branches"].items() if key in NATAL_PILLARS and value
    }
    if len(day_pillar) != 2 or day_pillar[0] not in STEMS or day_pillar[1] not in BRANCHES:
        raise ValueError("day_pillar must be a stem-branch pair")
    if any(value not in BRANCHES for value in branches.values()) or "day" not in branches:
        raise ValueError("natal branches must include a valid day branch")
    day_stem, day_branch = day_pillar[0], day_pillar[1]

    fired: list[str] = []
    god = ten_god(day_master, day_stem)
    fired.append(TEN_GOD_RULES[god])
    stem_combo = stem_combination(day_master, day_stem)
    if stem_combo:
        fired.append("BZD.STEM.COMBINE_DM")

    clashes, combinations, punishments, harms = [], [], [], []
    for pillar in NATAL_PILLARS:
        natal_branch = branches.get(pillar)
        if not natal_branch:
            continue
        pair = _pair(day_branch, natal_branch)
        if is_clash(day_branch, natal_branch):
            clashes.append({"natalPillar": pillar, "branches": pair})
            fired.append(f"BZD.BRANCH.CLASH_{pillar.upper()}")
        label = six_combination(day_branch, natal_branch)
        if label:
            combinations.append({"natalPillar": pillar, "branches": pair, "label": label})
        label = punishment(day_branch, natal_branch)
        if label:
            punishments.append({"natalPillar": pillar, "branches": pair, "label": label})
        if pillar == "day" and is_harm(day_branch, natal_branch):
            harms.append({"natalPillar": pillar, "branches": pair})
    if any(item["natalPillar"] == "day" for item in combinations):
        fired.append("BZD.BRANCH.COMBINE_DAY")
    if any(item["natalPillar"] != "day" for item in combinations):
        fired.append("BZD.BRANCH.COMBINE_OTHER")
    trine_items = trines(day_branch, list(branches.values()))
    if trine_items:
        fired.append("BZD.BRANCH.TRINE")
    if punishments:
        fired.append("BZD.BRANCH.PUNISHMENT")
    if harms:
        fired.append("BZD.BRANCH.HARM_DAY")

    good, avoid = _select(fired)
    return {
        "version": GUIDANCE_VERSION,
        "catalogVersion": CATALOG_VERSION,
        "dayPillar": day_pillar,
        "goodFor": good,
        "avoid": avoid,
        "ruleIds": list(dict.fromkeys(fired + [rid for item in good for rid in item["ruleIds"]])),
        "facts": {
            "dayMaster": day_master,
            "tenGod": god,
            "stemCombination": stem_combo,
            "clashes": clashes,
            "combinations": combinations,
            "trines": trine_items,
            "punishments": punishments,
            "harms": harms,
        },
        "limitations": list(LIMITATIONS),
    }


def _select(fired: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    # Caution first: branch relations (clash, punishment, harm) outrank ten-god avoid items.
    avoid_order = [rid for rid in fired if not rid.startswith("BZD.TENGOD.")] + [
        rid for rid in fired if rid.startswith("BZD.TENGOD.")
    ]
    avoid_sources = _collect(avoid_order, "avoid")
    avoid_ids = list(avoid_sources)[:MAX_AVOID]
    blocked = {blocked for item in avoid_ids for blocked in CATALOG[item].get("blocks", [])}
    blocked.update(avoid_ids)

    good_sources = _collect(fired, "good")
    candidates = [item for item in good_sources if item not in blocked]
    # The ten-god leads with at most two items so personal branch relations still surface.
    ten_god_items = [i for i in candidates if good_sources[i][0].startswith("BZD.TENGOD.")]
    relation_items = [i for i in candidates if i not in ten_god_items]
    ordered = ten_god_items[:2] + relation_items + ten_god_items[2:]
    good_ids = ordered[:MAX_GOOD]
    if len(good_ids) < MIN_GOOD:
        fallback = _collect(["BZD.FALLBACK.STEADY"], "good")
        for item, rule_ids in fallback.items():
            if len(good_ids) >= MIN_GOOD:
                break
            if item not in good_ids and item not in blocked:
                good_ids.append(item)
                good_sources[item] = rule_ids
    return (
        [_item(item, good_sources[item]) for item in good_ids],
        [_item(item, avoid_sources[item]) for item in avoid_ids],
    )


def _collect(rule_ids: list[str], field: str) -> dict[str, list[str]]:
    collected: dict[str, list[str]] = {}
    for rule_id in rule_ids:
        for item in getattr(RULES[rule_id], field):
            collected.setdefault(item, []).append(rule_id)
    return collected


def _item(item_id: str, rule_ids: list[str]) -> dict[str, Any]:
    entry = CATALOG[item_id]
    return {
        "id": item_id,
        "zh": entry["zh"],
        "en": entry["en"],
        "ja": entry["ja"],
        "ruleIds": rule_ids,
    }


def natal_from_bazi_record(record: dict[str, Any]) -> dict[str, Any]:
    """Extract the natal inputs for :func:`evaluate_day` from a ``bazi_chart_record.json``."""
    pillars = record["pillars"]
    subject = record.get("subject") or {}
    hour_reliable = subject.get("timePrecision") == "exact"
    return {
        "dayMaster": record["dayMaster"]["stem"],
        "dayMasterElement": record["dayMaster"].get("element"),
        "pillars": {
            key: (pillars[key]["ganZhi"] if key != "hour" or hour_reliable else None)
            for key in NATAL_PILLARS
        },
        "branches": {
            key: pillars[key]["branch"] for key in NATAL_PILLARS if key != "hour" or hour_reliable
        },
        "warnings": list(record.get("warnings") or []),
    }
