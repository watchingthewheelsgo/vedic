from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from .models import (
    ConfidenceGrade,
    JyotishFact,
    JudgementConclusion,
    JudgementFinding,
    TimeRange,
    TimingPeriod,
)
from .confidence import effective_fact_confidence, effective_timing_confidence


Polarity = Literal["supportive", "challenging", "context"]

INTERPRETATION_RULE_IDS = {
    "reference_points": "judge.structure.lagna-sun-moon-reference-points",
    "house_lord": "judge.structure.house-lord-placement",
    "occupant": "judge.structure.house-occupancy",
    "aspect": "judge.structure.graha-drishti",
    "varga": "judge.structure.varga-confirmation",
    "association": "judge.structure.same-sign-association",
    "parivartana": "judge.structure.parivartana",
    "gaja_kesari": "judge.structure.gaja-kesari",
    "natural_karaka": "judge.structure.natural-karaka",
    "dispositor": "judge.structure.dispositor-path",
    "sav": "judge.capacity.sav-structural-band",
    "dignity": "judge.capacity.dignity-condition",
    "shadbala": "judge.capacity.shadbala-band",
    "combustion": "judge.capacity.combustion-condition",
}

_SUPPORTIVE_DIGNITIES = {
    "exalted",
    "moolatrikona",
    "own_sign",
    "great_friend",
    "friend",
}
_CHALLENGING_DIGNITIES = {"debilitated", "great_enemy", "enemy"}

_HOUSE_DOMAINS = {
    "zh": {
        1: "自我与行动",
        2: "资源、家庭与表达",
        3: "沟通、技能与主动性",
        4: "家庭、居所与内在安定",
        5: "创造、学习与培育",
        6: "工作、服务与压力管理",
        7: "伴侣、合作与契约",
        8: "转变、风险与共同资源",
        9: "信念、高等学习与远行",
        10: "事业、责任与公众角色",
        11: "收益、社群与长期目标",
        12: "退隐、海外与资源消耗",
    },
    "ja": {
        1: "自己と行動",
        2: "資源、家族、表現",
        3: "伝達、技能、自発性",
        4: "家庭、住居、内的安定",
        5: "創造、学習、養育",
        6: "仕事、奉仕、負荷管理",
        7: "伴侶、協力、契約",
        8: "変化、危機、共有資源",
        9: "信念、高等教育、遠方",
        10: "仕事、責任、公的役割",
        11: "収益、共同体、長期目標",
        12: "退隠、海外、資源消耗",
    },
}

_PLANET_LABELS = {
    "zh": {
        "Sun": "太阳",
        "Moon": "月亮",
        "Mars": "火星",
        "Mercury": "水星",
        "Jupiter": "木星",
        "Venus": "金星",
        "Saturn": "土星",
        "Rahu": "罗睺",
        "Ketu": "计都",
    },
    "ja": {
        "Sun": "太陽",
        "Moon": "月",
        "Mars": "火星",
        "Mercury": "水星",
        "Jupiter": "木星",
        "Venus": "金星",
        "Saturn": "土星",
        "Rahu": "ラーフ",
        "Ketu": "ケートゥ",
    },
}

_DIGNITY_LABELS = {
    "zh": {
        "exalted": "擢升",
        "moolatrikona": "根本三分",
        "own_sign": "入庙",
        "great_friend": "大友",
        "friend": "友好",
        "neutral": "中性",
        "enemy": "敌对",
        "great_enemy": "大敌",
        "debilitated": "落陷",
    },
    "ja": {
        "exalted": "高揚",
        "moolatrikona": "ムーラトリコーナ",
        "own_sign": "自室",
        "great_friend": "大友好",
        "friend": "友好",
        "neutral": "中立",
        "enemy": "敵対",
        "great_enemy": "大敵対",
        "debilitated": "減衰",
    },
}

_SIGN_LABELS = {
    "zh": {
        "Aries": "白羊座",
        "Taurus": "金牛座",
        "Gemini": "双子座",
        "Cancer": "巨蟹座",
        "Leo": "狮子座",
        "Virgo": "处女座",
        "Libra": "天秤座",
        "Scorpio": "天蝎座",
        "Sagittarius": "射手座",
        "Capricorn": "摩羯座",
        "Aquarius": "水瓶座",
        "Pisces": "双鱼座",
    },
    "ja": {
        "Aries": "牡羊座",
        "Taurus": "牡牛座",
        "Gemini": "双子座",
        "Cancer": "蟹座",
        "Leo": "獅子座",
        "Virgo": "乙女座",
        "Libra": "天秤座",
        "Scorpio": "蠍座",
        "Sagittarius": "射手座",
        "Capricorn": "山羊座",
        "Aquarius": "水瓶座",
        "Pisces": "魚座",
    },
}


@dataclass(frozen=True)
class JudgementPolicy:
    """Versioned product thresholds, kept explicit until source-validated alternatives exist."""

    policy_id: str = "vedicdust-structural-bands-1.2.0"
    sav_supportive_min: float = 30.0
    sav_challenging_max: float = 26.0
    shadbala_supportive_min: float = 120.0
    shadbala_challenging_below: float = 90.0
    directional_margin: float = 0.35
    minimum_directional_methods: int = 2


POLICY = JudgementPolicy()


def compile_topic_judgement(
    *,
    topic_id: str,
    topic_title: str,
    anchor_houses: tuple[int, ...],
    karakas: tuple[str, ...],
    primary_rule_id: str,
    natal_fact_ids: list[str],
    capacity_fact_ids: list[str],
    varga_fact_ids: list[str],
    facts_by_id: dict[str, JyotishFact],
    locale: str,
    requested: bool,
    certainty_cap: Literal["high", "moderate", "low"],
    limitations: list[str],
    interpretation_rule_ids: dict[str, str],
    directional_judgement_rule_ids: set[str],
    validated_derivation_rule_ids: set[str],
    timing_rule_id: str | None = None,
    timing_gate_rule_id: str | None = None,
    timing_periods: list[TimingPeriod] | None = None,
    reference_time: datetime | None = None,
) -> tuple[list[JudgementFinding], list[JudgementConclusion]]:
    """Compile a topic into deterministic observations and one bounded synthesis.

    The kernel intentionally evaluates only explicit, inspectable factors. It does not infer
    life events or personality from a fact merely being present.
    """

    findings: list[JudgementFinding] = []
    allowed_fact_ids = set(natal_fact_ids + capacity_fact_ids + varga_fact_ids)

    if topic_id == "foundation":
        reference_facts = [
            _find_fact(
                facts_by_id,
                allowed_fact_ids,
                fact_type=fact_type,
                subject_ref=subject_ref,
            )
            for fact_type, subject_ref in (
                ("rashi.lagna.position", "D1.Lagna"),
                ("rashi.graha.position", "D1.Sun"),
                ("rashi.graha.position", "D1.Moon"),
            )
        ]
        if all(fact is not None and isinstance(fact.value, dict) for fact in reference_facts):
            lagna_fact, sun_fact, moon_fact = reference_facts
            assert lagna_fact is not None and sun_fact is not None and moon_fact is not None
            lagna_value = lagna_fact.value
            sun_value = sun_fact.value
            moon_value = moon_fact.value
            findings.append(
                _finding(
                    topic_id,
                    interpretation_rule_ids.get("reference_points", primary_rule_id),
                    code="reference_points.lagna_sun_moon",
                    polarity="context",
                    weight=0.9,
                    fact_ids=[lagna_fact.fact_id, sun_fact.fact_id, moon_fact.fact_id],
                    statement=(
                        "The D1 reference points are "
                        f"Lagna in {lagna_value.get('sign')}, Sun in {sun_value.get('sign')}, "
                        f"and Moon in {moon_value.get('sign')}."
                    ),
                    parameters={
                        "lagnaSign": lagna_value.get("sign"),
                        "sunSign": sun_value.get("sign"),
                        "moonSign": moon_value.get("sign"),
                        "moonNakshatra": (moon_value.get("nakshatra") or {}).get("name"),
                        "moonNakshatraPada": (moon_value.get("nakshatra") or {}).get("pada"),
                        "interpretation": "reference_points_context_only",
                    },
                    facts_by_id=facts_by_id,
                )
            )

    for house in anchor_houses:
        house_ref = f"D1.H{house}"
        occupant_facts = sorted(
            (
                fact
                for fact_id, fact in facts_by_id.items()
                if fact_id in allowed_fact_ids
                and fact.fact_type == "rashi.house.occupant"
                and fact.subject_ref.startswith(f"{house_ref}.occupant.")
            ),
            key=lambda fact: fact.subject_ref,
        )
        for occupant_fact in occupant_facts:
            occupant = occupant_fact.subject_ref.rsplit(".", 1)[-1]
            occupant_rule_id = interpretation_rule_ids.get("occupant", primary_rule_id)
            findings.append(
                _finding(
                    topic_id,
                    occupant_rule_id,
                    code=f"anchor.h{house}.occupant.{occupant.lower()}",
                    polarity="context",
                    weight=0.35,
                    fact_ids=[occupant_fact.fact_id],
                    statement=f"{occupant} occupies H{house} in D1.",
                    parameters={
                        "house": house,
                        "graha": occupant,
                        "interpretation": "placement_context_only",
                    },
                    facts_by_id=facts_by_id,
                )
            )

        house_aspect_facts = sorted(
            (
                fact
                for fact_id, fact in facts_by_id.items()
                if fact_id in allowed_fact_ids
                and fact.fact_type == "aspect.graha_drishti"
                and fact.subject_ref.endswith(f"->H{house}")
            ),
            key=lambda fact: fact.subject_ref,
        )
        for aspect_index, aspect_fact in enumerate(house_aspect_facts, start=1):
            source = aspect_fact.subject_ref.removeprefix("D1.").split("->", 1)[0]
            aspect_rule_id = interpretation_rule_ids.get("aspect", primary_rule_id)
            findings.append(
                _finding(
                    topic_id,
                    aspect_rule_id,
                    code=f"anchor.h{house}.aspect.{source.lower()}.{aspect_index}",
                    polarity="context",
                    weight=0.3,
                    fact_ids=[aspect_fact.fact_id],
                    statement=f"{source} casts a declared Parashari graha drishti to H{house}.",
                    parameters={
                        "house": house,
                        "sourceGraha": source,
                        "interpretation": "aspect_context_only",
                    },
                    facts_by_id=facts_by_id,
                )
            )

        lord_fact = _find_fact(
            facts_by_id, allowed_fact_ids, fact_type="rashi.house.lord", subject_ref=house_ref
        )
        if lord_fact is None or not isinstance(lord_fact.value, dict):
            continue
        lord = str(lord_fact.value.get("lord") or "unknown")
        lord_house = _integer_value(lord_fact.value, "lord_house", "lordHouse")
        house_lord_rule_id = interpretation_rule_ids.get("house_lord", primary_rule_id)
        findings.append(
            _finding(
                topic_id,
                house_lord_rule_id,
                code=f"anchor.h{house}.lord_path",
                polarity="context",
                weight=0.55,
                fact_ids=[lord_fact.fact_id],
                statement=(
                    f"The H{house} lord is {lord} and is placed in H{lord_house}."
                    if lord_house is not None
                    else f"The H{house} lord is {lord}."
                ),
                parameters={"house": house, "lord": lord, "lordHouse": lord_house},
                facts_by_id=facts_by_id,
            )
        )

        if lord != "unknown":
            lord_aspect_facts = sorted(
                (
                    fact
                    for fact_id, fact in facts_by_id.items()
                    if fact_id in allowed_fact_ids
                    and fact.fact_type == "aspect.graha_drishti"
                    and fact.subject_ref.endswith(f"->{lord}")
                ),
                key=lambda fact: fact.subject_ref,
            )
            for aspect_index, aspect_fact in enumerate(lord_aspect_facts, start=1):
                source = aspect_fact.subject_ref.removeprefix("D1.").split("->", 1)[0]
                aspect_rule_id = interpretation_rule_ids.get("aspect", primary_rule_id)
                findings.append(
                    _finding(
                        topic_id,
                        aspect_rule_id,
                        code=(f"anchor.h{house}.lord_aspect.{source.lower()}.{aspect_index}"),
                        polarity="context",
                        weight=0.3,
                        fact_ids=[lord_fact.fact_id, aspect_fact.fact_id],
                        statement=(
                            f"{source} casts a declared Parashari graha drishti to {lord}, "
                            f"lord of H{house}."
                        ),
                        parameters={
                            "house": house,
                            "houseLord": lord,
                            "sourceGraha": source,
                            "interpretation": "aspect_context_only",
                        },
                        facts_by_id=facts_by_id,
                    )
                )

        sav_fact = _find_fact(
            facts_by_id,
            allowed_fact_ids,
            fact_type="ashtakavarga.sav.house",
            subject_ref=house_ref,
        )
        if sav_fact is not None and isinstance(sav_fact.value, (int, float)):
            sav = float(sav_fact.value)
            sav_rule_id = interpretation_rule_ids.get("sav", primary_rule_id)
            candidate_polarity: Polarity = (
                "supportive"
                if sav >= POLICY.sav_supportive_min
                else "challenging"
                if sav <= POLICY.sav_challenging_max
                else "context"
            )
            polarity = _validated_directional_polarity(
                candidate_polarity,
                [sav_fact],
                interpretation_rule_id=sav_rule_id,
                directional_judgement_rule_ids=directional_judgement_rule_ids,
                validated_derivation_rule_ids=validated_derivation_rule_ids,
            )
            findings.append(
                _finding(
                    topic_id,
                    sav_rule_id,
                    code=f"anchor.h{house}.sav",
                    polarity=polarity,
                    weight=0.7,
                    fact_ids=[sav_fact.fact_id],
                    statement=f"H{house} has {sav:g} Sarvashtakavarga bindus.",
                    parameters={
                        "house": house,
                        "sav": sav,
                        "policyId": POLICY.policy_id,
                        "supportiveMin": POLICY.sav_supportive_min,
                        "challengingMax": POLICY.sav_challenging_max,
                        "directionWithheld": candidate_polarity != "context"
                        and polarity == "context",
                    },
                    facts_by_id=facts_by_id,
                )
            )

        if lord == "unknown":
            continue
        lord_ref = f"D1.{lord}"
        dignity_fact = _find_fact(
            facts_by_id,
            allowed_fact_ids,
            fact_type="strength.dignity",
            subject_ref=lord_ref,
        )
        if dignity_fact is not None and isinstance(dignity_fact.value, dict):
            dignity_rule_id = interpretation_rule_ids.get("dignity", primary_rule_id)
            dignity = str(
                dignity_fact.value.get("effective")
                or dignity_fact.value.get("special")
                or dignity_fact.value.get("compound")
                or dignity_fact.value.get("basic")
                or "unknown"
            ).lower()
            candidate_polarity = (
                "supportive"
                if dignity in _SUPPORTIVE_DIGNITIES
                else "challenging"
                if dignity in _CHALLENGING_DIGNITIES
                else "context"
            )
            polarity = _validated_directional_polarity(
                candidate_polarity,
                [dignity_fact],
                interpretation_rule_id=dignity_rule_id,
                directional_judgement_rule_ids=directional_judgement_rule_ids,
                validated_derivation_rule_ids=validated_derivation_rule_ids,
            )
            findings.append(
                _finding(
                    topic_id,
                    dignity_rule_id,
                    code=f"anchor.h{house}.lord_dignity",
                    polarity=polarity,
                    weight=0.8,
                    fact_ids=[lord_fact.fact_id, dignity_fact.fact_id],
                    statement=f"{lord}, lord of H{house}, has {dignity} dignity in D1.",
                    parameters={
                        "house": house,
                        "lord": lord,
                        "dignity": dignity,
                        "directionWithheld": candidate_polarity != "context"
                        and polarity == "context",
                    },
                    facts_by_id=facts_by_id,
                )
            )

        shadbala_fact = _find_fact(
            facts_by_id,
            allowed_fact_ids,
            fact_type="strength.shadbala",
            subject_ref=lord_ref,
        )
        if shadbala_fact is not None and isinstance(shadbala_fact.value, dict):
            shadbala_rule_id = interpretation_rule_ids.get("shadbala", primary_rule_id)
            strength_pct = _float_value(
                shadbala_fact.value, "strength_pct", "strengthPct", "percentage"
            )
            if strength_pct is not None:
                candidate_polarity = (
                    "supportive"
                    if strength_pct >= POLICY.shadbala_supportive_min
                    else "challenging"
                    if strength_pct < POLICY.shadbala_challenging_below
                    else "context"
                )
                polarity = _validated_directional_polarity(
                    candidate_polarity,
                    [shadbala_fact],
                    interpretation_rule_id=shadbala_rule_id,
                    directional_judgement_rule_ids=directional_judgement_rule_ids,
                    validated_derivation_rule_ids=validated_derivation_rule_ids,
                )
                findings.append(
                    _finding(
                        topic_id,
                        shadbala_rule_id,
                        code=f"anchor.h{house}.lord_shadbala",
                        polarity=polarity,
                        weight=0.8,
                        fact_ids=[lord_fact.fact_id, shadbala_fact.fact_id],
                        statement=(
                            f"{lord}, lord of H{house}, has Shadbala at "
                            f"{strength_pct:g}% of its required strength."
                        ),
                        parameters={
                            "house": house,
                            "lord": lord,
                            "strengthPercentage": strength_pct,
                            "policyId": POLICY.policy_id,
                            "supportiveMin": POLICY.shadbala_supportive_min,
                            "challengingBelow": POLICY.shadbala_challenging_below,
                            "directionWithheld": candidate_polarity != "context"
                            and polarity == "context",
                        },
                        facts_by_id=facts_by_id,
                    )
                )

        combustion_fact = _find_fact(
            facts_by_id,
            allowed_fact_ids,
            fact_type="strength.combustion",
            subject_ref=lord_ref,
        )
        if combustion_fact is not None and isinstance(combustion_fact.value, dict):
            combustion_rule_id = interpretation_rule_ids.get("combustion", primary_rule_id)
            is_combust = bool(
                combustion_fact.value.get(
                    "isCombust", combustion_fact.value.get("is_combust", False)
                )
            )
            combustion_polarity: Polarity = "challenging" if is_combust else "context"
            combustion_polarity = _validated_directional_polarity(
                combustion_polarity,
                [combustion_fact],
                interpretation_rule_id=combustion_rule_id,
                directional_judgement_rule_ids=directional_judgement_rule_ids,
                validated_derivation_rule_ids=validated_derivation_rule_ids,
            )
            findings.append(
                _finding(
                    topic_id,
                    combustion_rule_id,
                    code=f"anchor.h{house}.lord_combustion",
                    polarity=combustion_polarity,
                    weight=0.65 if is_combust else 0.25,
                    fact_ids=[lord_fact.fact_id, combustion_fact.fact_id],
                    statement=(
                        f"{lord}, lord of H{house}, is combust."
                        if is_combust
                        else f"{lord}, lord of H{house}, is not combust."
                    ),
                    parameters={
                        "house": house,
                        "lord": lord,
                        "isCombust": is_combust,
                        "directionWithheld": is_combust and combustion_polarity == "context",
                    },
                    facts_by_id=facts_by_id,
                )
            )

        dispositor_fact = _find_fact(
            facts_by_id,
            allowed_fact_ids,
            fact_type="relationship.dispositor_chain",
            subject_ref=lord_ref,
        )
        if dispositor_fact is not None and isinstance(dispositor_fact.value, dict):
            chain = [str(item) for item in dispositor_fact.value.get("chain") or []]
            if chain:
                findings.append(
                    _finding(
                        topic_id,
                        interpretation_rule_ids.get("dispositor", primary_rule_id),
                        code=f"anchor.h{house}.lord_dispositor_chain",
                        polarity="context",
                        weight=0.4,
                        fact_ids=[lord_fact.fact_id, dispositor_fact.fact_id],
                        statement=(
                            f"The dispositor chain for {lord}, lord of H{house}, is "
                            + " -> ".join(chain)
                            + "."
                        ),
                        parameters={"house": house, "lord": lord, "chain": chain},
                        facts_by_id=facts_by_id,
                    )
                )

        varga_house_facts = sorted(
            (
                fact
                for fact_id, fact in facts_by_id.items()
                if fact_id in allowed_fact_ids
                and fact.fact_type == "varga.house.lord"
                and fact.subject_ref.endswith(f".H{house}")
            ),
            key=lambda fact: fact.subject_ref,
        )
        for varga_fact in varga_house_facts:
            if not isinstance(varga_fact.value, dict):
                continue
            varga_id = varga_fact.subject_ref.split(".", 1)[0]
            varga_lord = str(varga_fact.value.get("lord") or "unknown")
            varga_lord_house = _integer_value(varga_fact.value, "lord_house", "lordHouse")
            varga_rule_id = interpretation_rule_ids.get("varga", primary_rule_id)
            findings.append(
                _finding(
                    topic_id,
                    varga_rule_id,
                    code=f"anchor.h{house}.{varga_id.lower()}_lord_path",
                    polarity="context",
                    weight=0.4,
                    fact_ids=[lord_fact.fact_id, varga_fact.fact_id],
                    statement=(
                        f"In {varga_id}, the H{house} lord is {varga_lord} "
                        f"and is placed in H{varga_lord_house}."
                    ),
                    parameters={
                        "house": house,
                        "varga": varga_id,
                        "lord": varga_lord,
                        "lordHouse": varga_lord_house,
                        "interpretation": "corroboration_context_only",
                    },
                    facts_by_id=facts_by_id,
                )
            )

    findings.extend(
        _relationship_context_findings(
            topic_id=topic_id,
            association_rule_id=interpretation_rule_ids.get("association", primary_rule_id),
            parivartana_rule_id=interpretation_rule_ids.get("parivartana", primary_rule_id),
            gaja_kesari_rule_id=interpretation_rule_ids.get("gaja_kesari", primary_rule_id),
            allowed_fact_ids=allowed_fact_ids,
            facts_by_id=facts_by_id,
        )
    )
    findings.extend(
        _natural_karaka_findings(
            topic_id=topic_id,
            rule_id=interpretation_rule_ids.get("natural_karaka", primary_rule_id),
            karakas=karakas,
            allowed_fact_ids=allowed_fact_ids,
            facts_by_id=facts_by_id,
        )
    )

    findings = _require_directional_method_convergence(
        findings,
        directional_judgement_rule_ids=directional_judgement_rule_ids,
    )

    if not findings:
        fallback_ids = list(
            dict.fromkeys(
                [
                    *(sorted(natal_fact_ids)[:1]),
                    *(sorted(capacity_fact_ids)[:1]),
                    *(sorted(varga_fact_ids)[:1]),
                ]
            )
        )
        if not fallback_ids:
            raise ValueError(f"topic {topic_id} has no facts available to compile")
        findings.append(
            _finding(
                topic_id,
                primary_rule_id,
                code="available_evidence",
                polarity="context",
                weight=0.2,
                fact_ids=fallback_ids,
                statement="Topic evidence is available, but no executable anchor rule matched it.",
                parameters={},
                facts_by_id=facts_by_id,
            )
        )

    conclusion = _conclusion(
        topic_id=topic_id,
        topic_title=topic_title,
        findings=findings,
        locale=locale,
        requested=requested,
        primary_rule_id=primary_rule_id,
        certainty_cap=certainty_cap,
        limitations=limitations,
    )
    conclusions = [conclusion]
    if timing_rule_id and timing_gate_rule_id and timing_periods and reference_time:
        timing_result = _timing_conclusion(
            topic_id=topic_id,
            topic_title=topic_title,
            anchor_houses=anchor_houses,
            structural_conclusion=conclusion,
            findings=findings,
            facts_by_id=facts_by_id,
            allowed_fact_ids=allowed_fact_ids,
            timing_rule_id=timing_rule_id,
            timing_gate_rule_id=timing_gate_rule_id,
            timing_periods=timing_periods,
            reference_time=reference_time,
            validated_derivation_rule_ids=validated_derivation_rule_ids,
            locale=locale,
            requested=requested,
            limitations=limitations,
        )
        if timing_result is not None:
            timing_finding, timing_conclusion = timing_result
            findings.append(timing_finding)
            conclusions.append(timing_conclusion)
    return findings, conclusions


def _require_directional_method_convergence(
    findings: list[JudgementFinding],
    *,
    directional_judgement_rule_ids: set[str],
) -> list[JudgementFinding]:
    """Release direction only from permitted methods that converge on the same polarity."""

    eligible_by_polarity: dict[Polarity, set[str]] = {
        "supportive": set(),
        "challenging": set(),
        "context": set(),
    }
    for finding in findings:
        if finding.polarity != "context" and finding.rule_id in directional_judgement_rule_ids:
            eligible_by_polarity[finding.polarity].add(finding.rule_id)

    released: list[JudgementFinding] = []
    for finding in findings:
        if finding.polarity == "context":
            released.append(finding)
            continue

        eligible_rule_ids = eligible_by_polarity[finding.polarity]
        if (
            finding.rule_id in directional_judgement_rule_ids
            and len(eligible_rule_ids) >= POLICY.minimum_directional_methods
        ):
            released.append(finding)
            continue

        reason = (
            "insufficient_directional_method_convergence"
            if finding.rule_id in directional_judgement_rule_ids
            else "interpretation_rule_not_directional"
        )
        released.append(
            finding.model_copy(
                update={
                    "polarity": "context",
                    "parameters": {
                        **finding.parameters,
                        "directionWithheld": True,
                        "directionWithheldReason": reason,
                        "directionalJudgementRuleIds": sorted(eligible_rule_ids),
                        "minimumDirectionalMethods": POLICY.minimum_directional_methods,
                    },
                }
            )
        )
    return released


def _natural_karaka_findings(
    *,
    topic_id: str,
    rule_id: str,
    karakas: tuple[str, ...],
    allowed_fact_ids: set[str],
    facts_by_id: dict[str, JyotishFact],
) -> list[JudgementFinding]:
    """Expose natural-karaka condition without assigning an unpinned benefic/malefic verdict."""

    findings: list[JudgementFinding] = []
    for karaka in karakas:
        subject_ref = f"D1.{karaka}"
        evidence = [
            fact
            for fact_type in (
                "rashi.graha.position",
                "strength.dignity",
                "strength.shadbala",
                "strength.combustion",
            )
            if (
                fact := _find_fact(
                    facts_by_id,
                    allowed_fact_ids,
                    fact_type=fact_type,
                    subject_ref=subject_ref,
                )
            )
            is not None
        ]
        if not evidence:
            continue

        details: dict[str, Any] = {}
        statements: list[str] = []
        for fact in evidence:
            value = fact.value if isinstance(fact.value, dict) else {}
            if fact.fact_type == "rashi.graha.position":
                sign = value.get("sign") or value.get("signName")
                details["sign"] = sign
                if sign:
                    statements.append(f"is in {sign}")
            elif fact.fact_type == "strength.dignity":
                dignity = (
                    value.get("effective")
                    or value.get("special")
                    or value.get("compound")
                    or value.get("basic")
                )
                details["dignity"] = dignity
                if dignity:
                    statements.append(f"has {dignity} dignity")
            elif fact.fact_type == "strength.shadbala":
                strength_pct = _float_value(value, "strength_pct", "strengthPct", "percentage")
                details["shadbalaPercentage"] = strength_pct
                if strength_pct is not None:
                    statements.append(f"has Shadbala at {strength_pct:g}% of requirement")
            elif fact.fact_type == "strength.combustion":
                is_combust = bool(value.get("isCombust", value.get("is_combust", False)))
                details["isCombust"] = is_combust
                statements.append("is combust" if is_combust else "is not combust")

        summary = ", ".join(statements) if statements else "has recorded D1 condition evidence"
        findings.append(
            _finding(
                topic_id,
                rule_id,
                code=f"karaka.{karaka.lower()}.condition",
                polarity="context",
                weight=0.35,
                fact_ids=[fact.fact_id for fact in evidence],
                statement=f"Natural karaka {karaka} {summary}.",
                parameters={
                    "karaka": karaka,
                    **details,
                    "interpretation": "natural_karaka_context_only",
                },
                facts_by_id=facts_by_id,
            )
        )
    return findings


def _relationship_context_findings(
    *,
    topic_id: str,
    association_rule_id: str,
    parivartana_rule_id: str,
    gaja_kesari_rule_id: str,
    allowed_fact_ids: set[str],
    facts_by_id: dict[str, JyotishFact],
) -> list[JudgementFinding]:
    """Expose declared D1 associations without assigning automatic direction."""

    findings: list[JudgementFinding] = []
    relation_facts = sorted(
        (
            fact
            for fact_id, fact in facts_by_id.items()
            if fact_id in allowed_fact_ids
            and fact.fact_type
            in {
                "relationship.same_sign",
                "relationship.parivartana",
                "yoga.raja.kendra_trikona",
                "yoga.gaja_kesari.structure",
            }
        ),
        key=lambda fact: fact.fact_id,
    )
    for index, fact in enumerate(relation_facts, start=1):
        if fact.fact_type == "yoga.gaja_kesari.structure":
            value = fact.value if isinstance(fact.value, dict) else {}
            supporters = [
                str(item.get("graha"))
                for item in value.get("supporters", [])
                if isinstance(item, dict) and item.get("graha")
            ]
            relative_house = value.get("jupiterRelativeHouse")
            statement = (
                "D1 contains the complete source-pinned Gaja-Kesari structure: "
                f"Jupiter is H{relative_house} from Moon, receives qualified benefic contact "
                f"from {', '.join(supporters)}, and passes the declared Jupiter condition gates."
            )
            interpretation = "gaja_kesari_structure_context_only"
            weight = 0.45
            rule_id = gaja_kesari_rule_id
        elif fact.fact_type == "yoga.raja.kendra_trikona":
            statement = (
                f"{fact.subject_ref.removeprefix('D1.')} forms a same-sign association "
                "between declared kendra and trikona lords in D1."
            )
            interpretation = "raja_yoga_structure_context_only"
            weight = 0.45
            rule_id = association_rule_id
        elif fact.fact_type == "relationship.parivartana":
            value = fact.value if isinstance(fact.value, dict) else {}
            houses = value.get("houses") or []
            statement = (
                f"{fact.subject_ref.removeprefix('D1.')} forms a D1 Parivartana "
                f"between houses {houses}."
            )
            interpretation = "parivartana_structure_context_only"
            weight = 0.45
            rule_id = parivartana_rule_id
        else:
            statement = f"{fact.subject_ref.removeprefix('D1.')} shares one D1 sign."
            interpretation = "same_sign_context_only"
            weight = 0.3
            rule_id = association_rule_id
        findings.append(
            _finding(
                topic_id,
                rule_id,
                code=f"relationship.{interpretation}.{index}",
                polarity="context",
                weight=weight,
                fact_ids=[fact.fact_id],
                statement=statement,
                parameters={
                    "interpretation": interpretation,
                    **(
                        {
                            "jupiterRelativeHouse": relative_house,
                            "supporters": supporters,
                            "interpretationPermission": "structure_only",
                        }
                        if fact.fact_type == "yoga.gaja_kesari.structure"
                        else {}
                    ),
                },
                facts_by_id=facts_by_id,
            )
        )
    return findings


def _finding(
    topic_id: str,
    rule_id: str,
    *,
    code: str,
    polarity: Polarity,
    weight: float,
    fact_ids: list[str],
    statement: str,
    parameters: dict[str, Any],
    timing_period_ids: list[str] | None = None,
    facts_by_id: dict[str, JyotishFact] | None = None,
) -> JudgementFinding:
    safe_code = code.replace("_", "-")
    unique_fact_ids = list(dict.fromkeys(fact_ids))
    confidence_multiplier = _evidence_confidence_multiplier(
        [
            facts_by_id[fact_id]
            for fact_id in unique_fact_ids
            if facts_by_id and fact_id in facts_by_id
        ]
    )
    effective_weight = round(weight * confidence_multiplier, 3)
    weighted_parameters = {
        **parameters,
        "baseWeight": weight,
        "evidenceConfidenceMultiplier": confidence_multiplier,
    }
    return JudgementFinding(
        finding_id=f"finding.{topic_id}.{safe_code}",
        finding_code=f"{topic_id}.{code}",
        rule_id=rule_id,
        polarity=polarity,
        weight=effective_weight,
        fact_ids=unique_fact_ids,
        timing_period_ids=list(dict.fromkeys(timing_period_ids or [])),
        technical_statement=statement,
        parameters=weighted_parameters,
    )


def _conclusion(
    *,
    topic_id: str,
    topic_title: str,
    findings: list[JudgementFinding],
    locale: str,
    requested: bool,
    primary_rule_id: str,
    certainty_cap: Literal["high", "moderate", "low"],
    limitations: list[str],
) -> JudgementConclusion:
    support_score = sum(finding.weight for finding in findings if finding.polarity == "supportive")
    challenge_score = sum(
        finding.weight for finding in findings if finding.polarity == "challenging"
    )
    if support_score >= challenge_score + POLICY.directional_margin:
        direction: Literal["supportive", "mixed", "challenging", "descriptive"] = "supportive"
    elif challenge_score >= support_score + POLICY.directional_margin:
        direction = "challenging"
    elif support_score or challenge_score:
        direction = "mixed"
    else:
        direction = "descriptive"

    context_findings = [finding for finding in findings if finding.polarity == "context"]
    context_fact_ids = _unique_fact_ids(context_findings)
    context_fact_set = set(context_fact_ids)
    if direction == "supportive":
        primary = [finding for finding in findings if finding.polarity == "supportive"]
        counter = [finding for finding in findings if finding.polarity == "challenging"]
    elif direction == "challenging":
        primary = [finding for finding in findings if finding.polarity == "challenging"]
        counter = [finding for finding in findings if finding.polarity == "supportive"]
    elif direction == "mixed":
        primary = [finding for finding in findings if finding.polarity == "supportive"]
        counter = [finding for finding in findings if finding.polarity == "challenging"]
    else:
        primary = context_findings
        counter = []
    counter_fact_ids = _unique_fact_ids(counter)
    counter_fact_set = set(counter_fact_ids)
    supporting_fact_ids = [
        fact_id
        for fact_id in _unique_fact_ids(primary)
        if fact_id not in counter_fact_set and fact_id not in context_fact_set
    ]

    localized_title = _localized_topic_title(locale, topic_title)
    plain, expressions, implications = _localized_synthesis(
        locale=locale,
        topic_title=localized_title,
        direction=direction,
        findings=findings,
    )
    counter_statements = _localized_counter_statements(counter, locale)
    return JudgementConclusion(
        conclusion_id=f"conclusion.{topic_id}.integrated",
        conclusion_code=f"{topic_id}.{direction}_structure",
        direction=direction,
        scope="natal_promise",
        title=localized_title,
        plain_statement=plain,
        technical_statement=_technical_synthesis(findings, direction),
        finding_ids=[finding.finding_id for finding in findings],
        supporting_fact_ids=supporting_fact_ids,
        context_fact_ids=context_fact_ids,
        counter_fact_ids=counter_fact_ids,
        counter_statements=counter_statements,
        rule_ids=list(dict.fromkeys([primary_rule_id, *(finding.rule_id for finding in findings)])),
        user_relevance=_localized_user_relevance(locale, localized_title) if requested else None,
        real_world_expressions=expressions,
        conditions=[_localized_structural_condition(locale)],
        practical_implications=implications,
        limitations=list(dict.fromkeys(limitations)),
        certainty_cap=certainty_cap,
    )


def _timing_conclusion(
    *,
    topic_id: str,
    topic_title: str,
    anchor_houses: tuple[int, ...],
    structural_conclusion: JudgementConclusion,
    findings: list[JudgementFinding],
    facts_by_id: dict[str, JyotishFact],
    allowed_fact_ids: set[str],
    timing_rule_id: str,
    timing_gate_rule_id: str,
    timing_periods: list[TimingPeriod],
    reference_time: datetime,
    validated_derivation_rule_ids: set[str],
    locale: str,
    requested: bool,
    limitations: list[str],
) -> tuple[JudgementFinding, JudgementConclusion] | None:
    """Select one bounded Vimshottari window linked to inspectable topic anchors.

    This is deliberately narrower than a forecast. A period is eligible only when its
    Antardasha lord owns, occupies, or aspects a topic anchor house. Birth-time-sensitive
    Pratyantardasha is withheld.
    """

    anchor_lords: dict[str, list[str]] = {}
    anchor_fact_ids: dict[str, list[str]] = {}
    for house in anchor_houses:
        fact = _find_fact(
            facts_by_id,
            allowed_fact_ids,
            fact_type="rashi.house.lord",
            subject_ref=f"D1.H{house}",
        )
        if (
            fact is None
            or fact.provenance.rule_id not in validated_derivation_rule_ids
            or not isinstance(fact.value, dict)
        ):
            continue
        lord = fact.value.get("lord")
        if isinstance(lord, str) and lord:
            anchor_lords.setdefault(lord, []).append(f"H{house}")
            anchor_fact_ids.setdefault(lord, []).append(fact.fact_id)
    if not anchor_lords:
        return None

    def activation_for(lord: str) -> dict[str, Any]:
        houses: list[str] = []
        fact_ids: list[str] = []
        dimensions: list[str] = []
        for house in anchor_houses:
            house_ref = f"H{house}"
            if lord in anchor_lords and house_ref in anchor_lords[lord]:
                houses.append(house_ref)
                fact_ids.extend(anchor_fact_ids[lord])
                dimensions.append("house_lord")
            occupant = _find_fact(
                facts_by_id,
                allowed_fact_ids,
                fact_type="rashi.house.occupant",
                subject_ref=f"D1.H{house}.occupant.{lord}",
            )
            if (
                occupant is not None
                and occupant.provenance.rule_id in validated_derivation_rule_ids
            ):
                houses.append(house_ref)
                fact_ids.append(occupant.fact_id)
                dimensions.append("occupant")
            aspect = _find_fact(
                facts_by_id,
                allowed_fact_ids,
                fact_type="aspect.graha_drishti",
                subject_ref=f"D1.{lord}->H{house}",
            )
            if aspect is not None and aspect.provenance.rule_id in validated_derivation_rule_ids:
                houses.append(house_ref)
                fact_ids.append(aspect.fact_id)
                dimensions.append("graha_drishti")
        return {
            "houses": list(dict.fromkeys(houses)),
            "factIds": list(dict.fromkeys(fact_ids)),
            "dimensions": list(dict.fromkeys(dimensions)),
        }

    eligible: list[tuple[TimingPeriod, dict[str, Any]]] = []
    for period in timing_periods:
        if (
            period.level != "antardasha"
            or period.end_boundary.latest <= reference_time
            or not period.lords
            or effective_timing_confidence(period).rank < ConfidenceGrade.PROVISIONAL.rank
        ):
            continue
        activation = activation_for(period.lords[-1])
        if activation["factIds"]:
            eligible.append((period, activation))
    if not eligible:
        return None
    eligible.sort(
        key=lambda item: (
            0
            if item[0].start_boundary.earliest <= reference_time < item[0].end_boundary.latest
            else 1,
            item[0].start_boundary.earliest,
            item[0].end_boundary.latest,
        )
    )
    selected, activation = eligible[0]
    antardasha_lord = selected.lords[-1]
    activating_lords = [antardasha_lord]
    linked_houses = list(activation["houses"])
    linked_fact_ids = list(activation["factIds"])
    activation_dimensions = list(activation["dimensions"])
    if not linked_fact_ids:
        return None

    finding = _finding(
        topic_id,
        timing_rule_id,
        code="timing.vimshottari_anchor_activation",
        polarity="context",
        weight=0.5,
        fact_ids=linked_fact_ids,
        timing_period_ids=[selected.period_id],
        statement=(
            f"Vimshottari period {selected.period_id} is ruled by "
            f"{'/'.join(selected.lords)}; {'/'.join(activating_lords)} connects with "
            f"{'/'.join(linked_houses)} through {'/'.join(activation_dimensions)}."
        ),
        parameters={
            "periodId": selected.period_id,
            "periodLevel": selected.level,
            "periodLords": selected.lords,
            "antardashaLord": antardasha_lord,
            "activatingLords": activating_lords,
            "linkedHouses": linked_houses,
            "activationDimensions": activation_dimensions,
            "activationRule": "antardasha-lord-owns-occupies-or-aspects-topic-anchor-house",
            "startBoundary": selected.start_boundary.model_dump(
                by_alias=True,
                mode="json",
            ),
            "endBoundary": selected.end_boundary.model_dump(
                by_alias=True,
                mode="json",
            ),
        },
        facts_by_id=facts_by_id,
    )
    localized_title = _localized_topic_title(locale, topic_title)
    outer_time_scope = TimeRange(
        start=selected.start_boundary.earliest,
        end=selected.end_boundary.latest,
    )
    plain, expressions, implications = _localized_timing_synthesis(
        locale=locale,
        topic_title=localized_title,
        start=outer_time_scope.start,
        end=outer_time_scope.end,
    )
    timing_limits = list(
        dict.fromkeys(
            [
                *limitations,
                "This window is a Vimshottari lordship activation, not an event prediction.",
                "Transit corroboration must be recalculated for the date being assessed.",
                (
                    "The displayed range is the outer Vimshottari boundary envelope from "
                    f"{selected.start_boundary.sampled_hypotheses} sampled birth-time "
                    f"hypotheses ({selected.start_boundary.coverage}); the canonical provider "
                    f"interval is {selected.interval.start.isoformat()} to "
                    f"{selected.interval.end.isoformat()}."
                ),
            ]
        )
    )
    linked_fact_set = set(linked_fact_ids)
    counter_fact_ids = [
        fact_id
        for fact_id in structural_conclusion.counter_fact_ids
        if fact_id not in linked_fact_set
    ]
    counter_fact_set = set(counter_fact_ids)
    supporting_fact_ids = [
        fact_id
        for fact_id in structural_conclusion.supporting_fact_ids
        if fact_id not in counter_fact_set
    ]
    context_fact_ids = list(
        dict.fromkeys([*structural_conclusion.context_fact_ids, *linked_fact_ids])
    )
    return finding, JudgementConclusion(
        conclusion_id=f"conclusion.{topic_id}.timing.vimshottari",
        conclusion_code=f"{topic_id}.bounded_vimshottari_activation",
        direction="descriptive",
        scope="timing",
        title=localized_title,
        plain_statement=plain,
        technical_statement=(
            structural_conclusion.technical_statement + " " + finding.technical_statement
        ),
        user_relevance=_localized_user_relevance(locale, localized_title) if requested else None,
        finding_ids=[*structural_conclusion.finding_ids, finding.finding_id],
        supporting_fact_ids=supporting_fact_ids,
        context_fact_ids=context_fact_ids,
        counter_fact_ids=counter_fact_ids,
        counter_statements=(structural_conclusion.counter_statements if counter_fact_ids else []),
        timing_fact_ids=[],
        timing_period_ids=[selected.period_id],
        rule_ids=list(
            dict.fromkeys([*structural_conclusion.rule_ids, timing_rule_id, timing_gate_rule_id])
        ),
        time_scope=outer_time_scope,
        real_world_expressions=expressions,
        conditions=[_localized_timing_condition(locale)],
        practical_implications=implications,
        limitations=timing_limits,
        certainty_cap="low",
    )


def _technical_synthesis(findings: list[JudgementFinding], direction: str) -> str:
    support_score = sum(finding.weight for finding in findings if finding.polarity == "supportive")
    challenge_score = sum(
        finding.weight for finding in findings if finding.polarity == "challenging"
    )
    anchor = next(
        (
            finding
            for finding in findings
            if finding.finding_code.endswith(".lord_path") and "varga" not in finding.parameters
        ),
        None,
    )
    ranked = sorted(
        (finding for finding in findings if finding.polarity in {"supportive", "challenging"}),
        key=lambda finding: (-finding.weight, finding.finding_id),
    )
    selected: list[JudgementFinding] = []
    if anchor is not None:
        selected.append(anchor)
    selected.extend(ranked[:4])
    statements = list(dict.fromkeys(finding.technical_statement for finding in selected))
    score_summary = (
        f"Integrated direction={direction}; effective support weight={support_score:.3f}; "
        f"effective challenge weight={challenge_score:.3f}."
    )
    return " ".join([score_summary, *statements])


def _localized_counter_statements(findings: list[JudgementFinding], locale: str) -> list[str]:
    ranked = sorted(findings, key=lambda finding: (-finding.weight, finding.finding_id))
    return list(
        dict.fromkeys(_localized_finding_statement(finding, locale) for finding in ranked[:3])
    )


def _planet_label(planet: object, locale: str) -> str:
    value = str(planet or "unknown")
    return _PLANET_LABELS.get(locale, {}).get(value, value)


def _sign_label(sign: object, locale: str) -> str:
    value = str(sign or "unknown")
    return _SIGN_LABELS.get(locale, {}).get(value, value)


def _house_domain(house: object, locale: str) -> str:
    if not isinstance(house, int):
        return "unknown domain" if locale == "en" else "未知领域"
    localized = _HOUSE_DOMAINS.get(locale, {}).get(house)
    if localized:
        return localized
    return f"house {house}" if locale == "en" else f"第{house}宫主题"


def _localized_anchor_statement(finding: JudgementFinding, locale: str) -> str:
    house = finding.parameters.get("house")
    lord_house = finding.parameters.get("lordHouse")
    lord = _planet_label(finding.parameters.get("lord"), locale)
    if locale == "zh":
        if isinstance(lord_house, int):
            return (
                f"第{house}宫（{_house_domain(house, locale)}）由{lord}掌管，"
                f"宫主落入第{lord_house}宫（{_house_domain(lord_house, locale)}）"
            )
        return f"第{house}宫（{_house_domain(house, locale)}）由{lord}掌管"
    if locale == "ja":
        if isinstance(lord_house, int):
            return (
                f"第{house}室（{_house_domain(house, locale)}）の支配星は{lord}で、"
                f"第{lord_house}室（{_house_domain(lord_house, locale)}）にあります"
            )
        return f"第{house}室（{_house_domain(house, locale)}）の支配星は{lord}です"
    if isinstance(lord_house, int):
        return (
            f"the H{house} lord {lord} connects {_house_domain(house, locale)} with "
            f"H{lord_house} ({_house_domain(lord_house, locale)})"
        )
    return f"the H{house} lord is {lord}"


def _localized_anchor_expression(finding: JudgementFinding, locale: str) -> str:
    house = finding.parameters.get("house")
    lord_house = finding.parameters.get("lordHouse")
    if not isinstance(lord_house, int):
        if locale == "zh":
            return f"现实中重点观察第{house}宫主题如何在具体选择中反复出现。"
        if locale == "ja":
            return f"現実では第{house}室のテーマが具体的な選択にどう反復するかを確認します。"
        return f"Observe how H{house} themes recur through concrete choices."
    source = _house_domain(house, locale)
    target = _house_domain(lord_house, locale)
    if locale == "zh":
        return f"现实观察重点：处理“{target}”时，“{source}”议题是否同步被带动。"
    if locale == "ja":
        return f"現実の観察点: 「{target}」を扱う時に「{source}」も連動するか。"
    return f"Observe whether {source} becomes active when dealing with {target}."


def _localized_finding_statement(finding: JudgementFinding, locale: str) -> str:
    parameters = finding.parameters
    house = parameters.get("house")
    lord = _planet_label(parameters.get("lord"), locale)
    code = finding.finding_code
    if code.endswith(".reference_points.lagna_sun_moon"):
        lagna = _sign_label(parameters.get("lagnaSign"), locale)
        sun = _sign_label(parameters.get("sunSign"), locale)
        moon = _sign_label(parameters.get("moonSign"), locale)
        nakshatra = parameters.get("moonNakshatra")
        pada = parameters.get("moonNakshatraPada")
        moon_detail = f"{moon}"
        if nakshatra:
            moon_detail += f"、{nakshatra}宿"
            if isinstance(pada, int):
                moon_detail += f"第{pada}足"
        if locale == "zh":
            return f"D1基础坐标为上升{lagna}、太阳{sun}、月亮{moon_detail}"
        if locale == "ja":
            return f"D1の基準点はラグナ{lagna}、太陽{sun}、月{moon_detail}です"
        moon_detail = moon
        if nakshatra:
            moon_detail += f" in {nakshatra}"
            if isinstance(pada, int):
                moon_detail += f" pada {pada}"
        return f"D1 reference points are Lagna in {lagna}, Sun in {sun}, and Moon in {moon_detail}"
    if ".occupant." in code:
        graha = _planet_label(parameters.get("graha"), locale)
        if locale == "zh":
            return f"{graha}落在第{house}宫（{_house_domain(house, locale)}）"
        if locale == "ja":
            return f"{graha}は第{house}室（{_house_domain(house, locale)}）にあります"
        return f"{graha} occupies H{house} ({_house_domain(house, locale)})"
    if ".lord_aspect." in code:
        source = _planet_label(parameters.get("sourceGraha"), locale)
        house_lord = _planet_label(parameters.get("houseLord"), locale)
        if locale == "zh":
            return f"{source}对第{house}宫宫主{house_lord}形成传统Graha Drishti"
        if locale == "ja":
            return f"{source}は第{house}室の支配星{house_lord}にグラハ・ドリシュティを形成します"
        return f"{source} casts graha drishti to H{house} lord {house_lord}"
    if ".aspect." in code:
        source = _planet_label(parameters.get("sourceGraha"), locale)
        if locale == "zh":
            return f"{source}对第{house}宫（{_house_domain(house, locale)}）形成传统Graha Drishti"
        if locale == "ja":
            return f"{source}は第{house}室（{_house_domain(house, locale)}）にグラハ・ドリシュティを形成します"
        return f"{source} casts graha drishti to H{house} ({_house_domain(house, locale)})"
    if code.endswith(".sav"):
        sav = parameters.get("sav")
        if locale == "zh":
            return f"第{house}宫的Sarvashtakavarga为{sav:g}点"
        if locale == "ja":
            return f"第{house}室のSarvashtakavargaは{sav:g}点です"
        return f"H{house} has {sav:g} Sarvashtakavarga bindus"
    if code.endswith(".lord_dignity"):
        dignity = str(parameters.get("dignity") or "unknown")
        dignity_label = _DIGNITY_LABELS.get(locale, {}).get(dignity, dignity)
        if locale == "zh":
            return f"第{house}宫宫主{lord}在D1处于{dignity_label}状态"
        if locale == "ja":
            return f"第{house}室の支配星{lord}はD1で{dignity_label}です"
        return f"H{house} lord {lord} has {dignity} dignity in D1"
    if code.endswith(".lord_shadbala"):
        percentage = parameters.get("strengthPercentage")
        if locale == "zh":
            return f"第{house}宫宫主{lord}的Shadbala为所需强度的{percentage:g}%"
        if locale == "ja":
            return f"第{house}室の支配星{lord}のShadbalaは必要強度の{percentage:g}%です"
        return f"H{house} lord {lord} has {percentage:g}% of required Shadbala"
    if code.endswith(".lord_combustion"):
        combust = bool(parameters.get("isCombust"))
        if locale == "zh":
            return f"第{house}宫宫主{lord}{'处于燃烧状态' if combust else '未处于燃烧状态'}"
        if locale == "ja":
            return f"第{house}室の支配星{lord}は{'コンバストです' if combust else 'コンバストではありません'}"
        return f"H{house} lord {lord} is {'combust' if combust else 'not combust'}"
    if code.endswith(".lord_dispositor_chain"):
        chain = " -> ".join(_planet_label(item, locale) for item in parameters.get("chain") or [])
        if locale == "zh":
            return f"第{house}宫宫主{lord}的定位星链为{chain}"
        if locale == "ja":
            return f"第{house}室の支配星{lord}のディスポジター連鎖は{chain}です"
        return f"H{house} lord {lord} follows the dispositor chain {chain}"
    if "varga" in parameters and code.endswith("_lord_path"):
        varga = str(parameters.get("varga") or "varga")
        lord_house = parameters.get("lordHouse")
        if locale == "zh":
            return f"在{varga}中，第{house}宫宫主为{lord}，落入第{lord_house}宫"
        if locale == "ja":
            return f"{varga}では第{house}室の支配星は{lord}で、第{lord_house}室にあります"
        return f"in {varga}, H{house} lord {lord} is placed in H{lord_house}"
    if ".karaka." in code:
        karaka = _planet_label(parameters.get("karaka"), locale)
        details: list[str] = []
        sign = parameters.get("sign")
        if sign:
            details.append(_sign_label(sign, locale))
        dignity = parameters.get("dignity")
        if dignity:
            details.append(_DIGNITY_LABELS.get(locale, {}).get(str(dignity), str(dignity)))
        percentage = parameters.get("shadbalaPercentage")
        if isinstance(percentage, (int, float)):
            details.append(f"Shadbala {percentage:g}%")
        if parameters.get("isCombust") is True:
            details.append("燃烧" if locale == "zh" else "combust")
        detail_text = "、".join(details) if locale in {"zh", "ja"} else ", ".join(details)
        if locale == "zh":
            return f"该主题的自然象征星{karaka}已有可核查状态" + (
                f"（{detail_text}）" if detail_text else ""
            )
        if locale == "ja":
            return f"このテーマのナチュラル・カラカ{karaka}には確認可能な状態があります" + (
                f"（{detail_text}）" if detail_text else ""
            )
        return f"natural karaka {karaka} has recorded condition evidence" + (
            f" ({detail_text})" if detail_text else ""
        )
    return finding.technical_statement


def _localized_context_details(
    findings: list[JudgementFinding],
    anchor: JudgementFinding | None,
    locale: str,
    *,
    limit: int = 2,
) -> list[str]:
    """Select a compact, method-diverse set of inspectable structural observations."""

    ranked = sorted(
        (
            finding
            for finding in findings
            if finding.polarity == "context" and finding is not anchor
        ),
        key=lambda finding: (-finding.weight, finding.finding_id),
    )
    selected: list[str] = []
    used_rules: set[str] = set()
    for finding in ranked:
        if finding.rule_id in used_rules:
            continue
        statement = _localized_finding_statement(finding, locale)
        if statement == finding.technical_statement and locale != "en":
            continue
        selected.append(statement)
        used_rules.add(finding.rule_id)
        if len(selected) >= limit:
            break
    return selected


def _localized_evidence_clause(
    *,
    locale: str,
    direction: str,
    support_text: str | None,
    challenge_text: str | None,
) -> str:
    if locale == "zh":
        if direction == "supportive" and support_text:
            return f"主要支持证据是{support_text}" + (
                f"，同时存在制约：{challenge_text}" if challenge_text else ""
            )
        if direction == "challenging" and challenge_text:
            return f"主要压力证据是{challenge_text}" + (
                f"，仍有支持：{support_text}" if support_text else ""
            )
        if direction == "mixed":
            parts = [
                f"支持面为{support_text}" if support_text else "",
                f"制约面为{challenge_text}" if challenge_text else "",
            ]
            return "，".join(part for part in parts if part)
        return ""
    if locale == "ja":
        if direction == "supportive" and support_text:
            return f"主な支援根拠は{support_text}" + (
                f"ですが、制約として{challenge_text}もあります" if challenge_text else ""
            )
        if direction == "challenging" and challenge_text:
            return f"主な負荷根拠は{challenge_text}" + (
                f"ですが、支援として{support_text}もあります" if support_text else ""
            )
        if direction == "mixed":
            return "、".join(
                part
                for part in (
                    f"支援面は{support_text}" if support_text else "",
                    f"制約面は{challenge_text}" if challenge_text else "",
                )
                if part
            )
        return ""
    if direction == "supportive" and support_text:
        return f"the main support is {support_text}" + (
            f", while {challenge_text} remains a constraint" if challenge_text else ""
        )
    if direction == "challenging" and challenge_text:
        return f"the main pressure is {challenge_text}" + (
            f", while {support_text} remains supportive" if support_text else ""
        )
    if direction == "mixed":
        return "; ".join(
            part
            for part in (
                f"support comes from {support_text}" if support_text else "",
                f"constraint comes from {challenge_text}" if challenge_text else "",
            )
            if part
        )
    return ""


def _localized_synthesis(
    *,
    locale: str,
    topic_title: str,
    direction: str,
    findings: list[JudgementFinding],
) -> tuple[str, list[str], list[str]]:
    anchor = next(
        (
            finding
            for finding in findings
            if finding.finding_code.endswith(".lord_path") and "varga" not in finding.parameters
        ),
        None,
    )
    supportive = sorted(
        (finding for finding in findings if finding.polarity == "supportive"),
        key=lambda finding: (-finding.weight, finding.finding_id),
    )
    challenging = sorted(
        (finding for finding in findings if finding.polarity == "challenging"),
        key=lambda finding: (-finding.weight, finding.finding_id),
    )
    support_text = _localized_finding_statement(supportive[0], locale) if supportive else None
    challenge_text = _localized_finding_statement(challenging[0], locale) if challenging else None
    anchor_text = _localized_anchor_statement(anchor, locale) if anchor else None
    context_details = _localized_context_details(findings, anchor, locale)

    if locale == "zh":
        labels = {
            "supportive": "支持因素占优",
            "challenging": "压力因素占优",
            "mixed": "支持与制约接近",
            "descriptive": "可确认结构，但方向证据不足",
        }
        evidence = _localized_evidence_clause(
            locale="zh",
            direction=direction,
            support_text=support_text,
            challenge_text=challenge_text,
        )
        plain = f"{topic_title}：{anchor_text or labels[direction]}。{labels[direction]}"
        if evidence:
            plain += f"；{evidence}"
        if context_details:
            plain += "；另有可核查结构：" + "；".join(context_details)
        plain += "。这表示可观察的盘面条件，不代表事件必然发生。"
        expression = (
            _localized_anchor_expression(anchor, "zh")
            if anchor
            else "现实中应观察这个主题如何在具体选择与环境中反复出现。"
        )
        implication = (
            f"决策时同时核对这项制约：{challenge_text}。"
            if challenge_text
            else "把该结构作为决策条件，并另行核对大运、分运与行运。"
        )
        return (
            plain,
            [expression],
            [implication],
        )
    if locale == "ja":
        labels = {
            "supportive": "支援要因が優勢です",
            "challenging": "負荷要因が優勢です",
            "mixed": "支援と制約が拮抗しています",
            "descriptive": "構造は確認できますが方向性の証拠は不足しています",
        }
        evidence = _localized_evidence_clause(
            locale="ja",
            direction=direction,
            support_text=support_text,
            challenge_text=challenge_text,
        )
        plain = f"{topic_title}: {anchor_text or labels[direction]}。{labels[direction]}"
        if evidence:
            plain += f"。{evidence}"
        if context_details:
            plain += "。追加で確認できる構造: " + "、".join(context_details)
        plain += "。これは観察可能な条件であり、出来事の確約ではありません。"
        return (
            plain,
            [
                _localized_anchor_expression(anchor, "ja")
                if anchor
                else "現実では、このテーマが選択と環境の中でどう反復するかを確認します。"
            ],
            [
                f"判断時にはこの制約も確認してください: {challenge_text}。"
                if challenge_text
                else "時期判断はダシャーとトランジットを別に検証してください。"
            ],
        )
    labels = {
        "supportive": "supportive conditions are concentrated",
        "challenging": "pressure conditions are concentrated",
        "mixed": "support and constraint coexist",
        "descriptive": "the structure is visible but directional evidence is insufficient",
    }
    evidence = _localized_evidence_clause(
        locale="en",
        direction=direction,
        support_text=support_text,
        challenge_text=challenge_text,
    )
    plain = f"{topic_title}: {anchor_text or labels[direction]}. {labels[direction]}"
    if evidence:
        plain += f"; {evidence}"
    if context_details:
        plain += "; additional inspectable structure: " + "; ".join(context_details)
    plain += ". These are observable chart conditions, not an event guarantee."
    return (
        plain,
        [
            _localized_anchor_expression(anchor, "en")
            if anchor
            else "Observe how this topic recurs through concrete choices and environments."
        ],
        [
            f"Include this constraint in decisions: {challenge_text}."
            if challenge_text
            else "Use this as a decision condition and evaluate timing separately."
        ],
    )


_TOPIC_TITLES = {
    "zh": {
        "Chart foundation": "盘面基础",
        "Identity and agency": "自我与行动力",
        "Career and contribution": "事业与社会贡献",
        "Resources and finance": "资源与财务",
        "Relationships and partnership": "关系与伴侣",
        "Home and rootedness": "家庭与安定感",
        "Learning and vocation": "学习与志业",
        "Children and stewardship": "子女与培育责任",
        "Vitality and health patterns": "活力与健康模式",
        "Meaning and inner practice": "意义与内在实践",
        "Family and lineage": "家族与传承",
    },
    "ja": {
        "Chart foundation": "チャートの基礎",
        "Identity and agency": "自己と行動力",
        "Career and contribution": "仕事と社会的貢献",
        "Resources and finance": "資源と財務",
        "Relationships and partnership": "関係性とパートナーシップ",
        "Home and rootedness": "家庭と基盤",
        "Learning and vocation": "学習と天職",
        "Children and stewardship": "子どもと養育責任",
        "Vitality and health patterns": "活力と健康傾向",
        "Meaning and inner practice": "意味と内的実践",
        "Family and lineage": "家族と系譜",
    },
}


def _localized_topic_title(locale: str, topic_title: str) -> str:
    return _TOPIC_TITLES.get(locale, {}).get(topic_title, topic_title)


def _localized_user_relevance(locale: str, topic_title: str) -> str:
    if locale == "zh":
        return f"你在本次咨询中明确关注了{topic_title}。"
    if locale == "ja":
        return f"今回の相談で{topic_title}が明確なテーマとして指定されています。"
    return f"You explicitly requested {topic_title.lower()} in this consultation."


def _localized_structural_condition(locale: str) -> str:
    if locale == "zh":
        return "这是结构判断；只有通过独立验证的激活层后，才可讨论时间。"
    if locale == "ja":
        return "これは構造判断です。時期は独立に検証された活性化層が必要です。"
    return (
        "This is a structural judgement; timing requires a separately validated activation layer."
    )


def _localized_timing_condition(locale: str) -> str:
    if locale == "zh":
        return "该时间范围只表示对应宫主被大运系统激活；不保证具体事件发生。"
    if locale == "ja":
        return "この期間は該当ハウス支配星の活性化を示すだけで、出来事を保証しません。"
    return "This interval indicates relevant house-lord activation; it does not guarantee an event."


def _localized_timing_synthesis(
    *, locale: str, topic_title: str, start: datetime, end: datetime
) -> tuple[str, list[str], list[str]]:
    start_label = start.date().isoformat()
    end_label = end.date().isoformat()
    if locale == "zh":
        return (
            f"{topic_title}：{start_label} 至 {end_label} 存在一段可核查的运限激活窗口。",
            ["这一时期相关主题可能更容易进入现实议程，但具体表现取决于选择与环境。"],
            ["把该窗口用于安排复盘与决策观察，不把它当作事件承诺。"],
        )
    if locale == "ja":
        return (
            f"{topic_title}: {start_label}から{end_label}に検証可能なダシャー活性化期間があります。",
            ["関連テーマが現実の課題になりやすい時期ですが、現れ方は選択と環境に依存します。"],
            ["出来事の確約ではなく、見直しと意思決定の観察期間として使います。"],
        )
    return (
        f"{topic_title}: a reviewable dasha activation window runs from {start_label} to {end_label}.",
        [
            "The topic may become more active, while expression still depends on choices and context."
        ],
        ["Use the window for review and decision observation, not as an event promise."],
    )


def _find_fact(
    facts_by_id: dict[str, JyotishFact],
    allowed_fact_ids: set[str],
    *,
    fact_type: str,
    subject_ref: str,
) -> JyotishFact | None:
    return next(
        (
            fact
            for fact_id, fact in facts_by_id.items()
            if fact_id in allowed_fact_ids
            and fact.fact_type == fact_type
            and fact.subject_ref == subject_ref
        ),
        None,
    )


def _integer_value(value: dict[str, Any], *keys: str) -> int | None:
    raw = next((value[key] for key in keys if key in value), None)
    return int(raw) if isinstance(raw, (int, float)) else None


def _float_value(value: dict[str, Any], *keys: str) -> float | None:
    raw = next((value[key] for key in keys if key in value), None)
    return float(raw) if isinstance(raw, (int, float)) else None


def _unique_fact_ids(findings: Iterable[JudgementFinding]) -> list[str]:
    return list(dict.fromkeys(fact_id for finding in findings for fact_id in finding.fact_ids))


def _evidence_confidence_multiplier(facts: list[JyotishFact]) -> float:
    """Prevent a low-confidence derived fact from carrying validated-fact weight."""

    if not facts:
        return 1.0
    multipliers = {
        ConfidenceGrade.VERIFIED: 1.0,
        ConfidenceGrade.CORROBORATED: 0.8,
        ConfidenceGrade.PROVISIONAL: 0.5,
        ConfidenceGrade.DISPUTED: 0.25,
        ConfidenceGrade.UNAVAILABLE: 0.1,
    }
    return min(multipliers[effective_fact_confidence(fact)] for fact in facts)


def _validated_directional_polarity(
    polarity: Polarity,
    facts: list[JyotishFact],
    *,
    interpretation_rule_id: str,
    directional_judgement_rule_ids: set[str],
    validated_derivation_rule_ids: set[str],
) -> Polarity:
    """Require independently eligible derivation and interpretation rules for direction."""

    if polarity == "context":
        return polarity
    if interpretation_rule_id not in directional_judgement_rule_ids:
        return "context"
    if any(fact.provenance.rule_id not in validated_derivation_rule_ids for fact in facts):
        return "context"
    return polarity
