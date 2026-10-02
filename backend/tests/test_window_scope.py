from __future__ import annotations

import pytest

from app.services.chart_rectification import ChartRectificationService
from app.vedicdust.rectification_policy import window_scope_available


def _state(**overrides):
    state = {
        "status": "collecting_evidence",
        "revision": 3,
        "candidates": [
            {"candidateId": "cand.a", "interval": {"start": "1992-05-18T01:55:00Z"}},
            {"candidateId": "cand.b", "interval": {"start": "1992-05-18T02:05:00Z"}},
        ],
        "scanChangedFields": ["d9Lagna", "d10Lagna", "lagnaDegree"],
        "reportGate": {"fullReportAllowed": False},
    }
    state.update(overrides)
    return state


def test_window_scope_requires_a_stable_d1_ascendant():
    assert window_scope_available(_state())
    assert window_scope_available(_state(status="underdetermined"))
    assert not window_scope_available(_state(scanChangedFields=["lagnaSign"]))
    assert not window_scope_available(_state(scanChangedFields=["d1Structure"]))
    assert not window_scope_available(_state(status="corrected_chart_ready"))
    assert not window_scope_available(_state(candidates=[]))
    assert not window_scope_available(
        _state(evidenceInvalidation={"requiresReset": True}, status="underdetermined")
    )


def test_window_scope_releases_only_the_scan_stable_envelope():
    service = ChartRectificationService()
    scoped = service.apply_window_scope(_state())

    assert scoped["status"] == "window_scoped"
    assert scoped["selectedCandidateId"] is None
    assert scoped["equivalentCandidateIds"] == ["cand.a", "cand.b"]
    assert scoped["revision"] == 4
    assert scoped["reportGate"]["fullReportAllowed"] is True
    assert scoped["reportGate"]["reportScope"] == "stable_intersection_only"
    intersection = scoped["equivalentCandidateIntersection"]
    assert intersection["factPolicy"] == "release_only_scan_stable_facts"
    assert intersection["unstableFields"] == ["d9Lagna", "d10Lagna", "lagnaDegree"]

    decision = service.apply_prevalidation_decision(
        {"reportAllowed": False, "reportScope": "prevalidation_or_d1_only"}, scoped
    )
    assert decision["reportAllowed"] is True
    assert decision["reportScope"] == "stable_intersection_only"

    with pytest.raises(ValueError):
        service.apply_window_scope(_state(scanChangedFields=["lagnaSign"]))


def test_dossier_draft_normalizes_only_narrative_labels():
    import json

    from app.services.skill_runtime import SkillRuntime

    draft = {
        "sections": [
            {
                "sectionKind": "chart_foundation",
                "claimIds": ["c1"],
                "narratives": [
                    {"kind": "foundation", "text": "Kept exactly.", "claimIds": ["c1"]},
                    {"kind": "reflection", "text": "Also kept.", "claimIds": ["c1"]},
                ],
            }
        ]
    }
    normalized = json.loads(SkillRuntime._normalize_dossier_draft(json.dumps(draft)))
    narratives = normalized["sections"][0]["narratives"]
    assert [item["kind"] for item in narratives] == ["synthesis", "reflection"]
    assert narratives[0]["text"] == "Kept exactly."
    assert SkillRuntime._normalize_dossier_draft("not json") == "not json"


def test_dossier_draft_repairs_section_assignment():
    import json

    from app.services.skill_runtime import SkillRuntime

    draft = {
        "executiveClaimIds": ["c.career", "c.career.timing"],
        "sections": [
            {
                "sectionKind": "executive_synthesis",
                "claimIds": ["c.career", "c.career.timing"],
                "narratives": [
                    {"kind": "synthesis", "text": "x", "claimIds": ["c.career", "c.career.timing"]}
                ],
            },
            {
                "sectionKind": "priority_domain",
                "claimIds": ["c.career", "c.love"],
                "narratives": [{"kind": "domain", "text": "y", "claimIds": ["c.career"]}],
            },
            {"sectionKind": "timing_outlook", "claimIds": [], "narratives": []},
        ],
    }
    fixed = json.loads(
        SkillRuntime._normalize_dossier_draft(json.dumps(draft), frozenset({"c.career.timing"}))
    )
    executive, domain, timing = fixed["sections"]
    assert executive["claimIds"] == ["c.career"]
    assert executive["narratives"][0]["claimIds"] == ["c.career"]
    assert domain["claimIds"] == ["c.love"]
    assert domain["narratives"] == []
    assert timing["claimIds"] == ["c.career.timing"]
    assert fixed["executiveClaimIds"] == ["c.career"]


def test_dossier_draft_keeps_required_section_claims():
    import json

    from app.services.skill_runtime import SkillRuntime

    draft = {
        "executiveClaimIds": ["c.foundation", "c.career"],
        "sections": [
            {
                "sectionKind": "executive_synthesis",
                "claimIds": ["c.foundation", "c.career"],
                "narratives": [],
            },
            {"sectionKind": "chart_foundation", "claimIds": ["c.foundation"], "narratives": []},
            {"sectionKind": "decision_support", "claimIds": ["c.career"], "narratives": []},
        ],
    }
    fixed = json.loads(SkillRuntime._normalize_dossier_draft(json.dumps(draft)))
    executive, foundation, decision = fixed["sections"]
    assert foundation["claimIds"] == ["c.foundation"]
    assert decision["claimIds"] == ["c.career"]
    assert executive["claimIds"] == []
    assert fixed["executiveClaimIds"] == []


def test_consultation_placement_is_valid_by_construction():
    from types import SimpleNamespace

    from app.services.skill_runtime import SkillRuntime

    def claim(topic, scope="natal_promise"):
        return SimpleNamespace(claim_id=f"claim.{topic}.{scope}", topic=topic, scope=scope)

    claims = [
        claim("foundation"),
        claim("career"),
        claim("relationship"),
        claim("identity"),
        claim("learning"),
        claim("home"),
        claim("career", "timing"),
    ]
    layout = SkillRuntime._consultation_placement(
        claims, ["career", "relationship", "foundation", "identity", "learning", "home"]
    )
    by_kind = {}
    for section in layout["sections"]:
        by_kind.setdefault(section["sectionKind"], []).extend(section["claimIds"])
    assert by_kind["chart_foundation"] == ["claim.foundation.natal_promise"]
    assert by_kind["executive_synthesis"] == [
        "claim.career.natal_promise",
        "claim.relationship.natal_promise",
        "claim.identity.natal_promise",
    ]
    assert by_kind["decision_support"] == ["claim.learning.natal_promise"]
    assert by_kind["timing_outlook"] == ["claim.career.timing"]
    assigned = [claim_id for ids in by_kind.values() for claim_id in ids]
    assert sorted(assigned) == sorted(c.claim_id for c in claims)
    assert layout["executiveClaimIds"] == by_kind["executive_synthesis"]


def test_dossier_draft_restores_backend_placement_and_keeps_prose():
    import json

    from app.services.skill_runtime import SkillRuntime

    template = {
        "executiveClaimIds": ["c.a"],
        "omittedClaimIds": {},
        "sections": [
            {
                "sectionId": "section.executive_synthesis",
                "sectionKind": "executive_synthesis",
                "claimIds": ["c.a"],
                "narratives": [],
            },
            {
                "sectionId": "section.decision_support",
                "sectionKind": "decision_support",
                "claimIds": ["c.b"],
                "narratives": [],
            },
        ],
    }
    draft = {
        "executiveClaimIds": ["c.a", "c.b"],
        "sections": [
            {
                "sectionId": "section.executive_synthesis",
                "sectionKind": "executive_synthesis",
                "claimIds": ["c.a", "c.b"],
                "narratives": [
                    {
                        "narrativeId": "n1",
                        "kind": "synthesis",
                        "text": "Prose kept.",
                        "claimIds": ["c.a", "c.b"],
                    }
                ],
            }
        ],
    }
    fixed = json.loads(SkillRuntime._normalize_dossier_draft(json.dumps(draft), template=template))
    executive, decision = fixed["sections"]
    assert executive["claimIds"] == ["c.a"]
    assert executive["narratives"][0]["claimIds"] == ["c.a"]
    assert executive["narratives"][0]["text"] == "Prose kept."
    assert decision["claimIds"] == ["c.b"]
    assert fixed["executiveClaimIds"] == ["c.a"]
