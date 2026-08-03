from __future__ import annotations

import pytest

from app.services.rectification_interview import (
    build_rectification_interview,
    validate_agent_question_wording,
)
from app.services.skill_runtime import SkillRuntime


def _state(
    *,
    status: str = "collecting_evidence",
    fields: list[str] | None = None,
    categories: list[str] | None = None,
) -> dict[str, object]:
    events = [
        {
            "eventId": f"evt-{index}",
            "date": f"20{10 + index}-01",
            "category": category,
            "description": f"event {index}",
            "role": "calibration" if index < 2 else "holdout",
        }
        for index, category in enumerate(categories or [])
    ]
    return {
        "status": status,
        "rectificationPlan": {
            "discriminatingFields": fields or [],
            "eventCollectionRequired": status == "collecting_evidence",
        },
        "lifeEventLedger": {"events": events},
    }


def test_question_categories_follow_candidate_discriminators() -> None:
    interview = build_rectification_interview(
        _state(fields=["d10Lagna", "d4Structure"]),
        session_id="session-test",
        locale="zh",
    )

    assert [question["category"] for question in interview["questions"]] == [
        "career",
        "relocation",
        "property",
    ]
    assert interview["source"] == "deterministic_brief"
    assert "候选" not in " ".join(question["prompt"] for question in interview["questions"])


def test_undertermined_round_requests_one_new_domain_at_a_time() -> None:
    interview = build_rectification_interview(
        _state(
            status="underdetermined",
            fields=["d10Lagna", "d4Structure"],
            categories=["career", "relocation", "education"],
        ),
        session_id="session-test",
        locale="en",
    )

    assert len(interview["questions"]) == 1
    assert interview["questions"][0]["category"] not in {
        "career",
        "relocation",
        "education",
    }
    assert interview["progress"]["answered"] == 3
    assert interview["progress"]["maximumAccepted"] == 5


def test_interview_stops_after_five_events() -> None:
    interview = build_rectification_interview(
        _state(
            status="underdetermined",
            categories=["career", "relocation", "education", "family", "finance"],
        ),
        session_id="session-test",
        locale="en",
    )

    assert interview["status"] == "exhausted"
    assert interview["questions"] == []
    assert "underdetermined" in interview["stopReason"]


def test_child_interview_excludes_adult_life_domains() -> None:
    interview = build_rectification_interview(
        _state(fields=["d10Lagna", "d9Lagna", "d7Lagna"]),
        session_id="session-child",
        locale="en",
        life_stage="child",
    )

    assert {question["category"] for question in interview["questions"]}.isdisjoint(
        {"career", "relationship", "child", "finance", "property", "legal"}
    )


def test_agent_may_rephrase_but_not_change_question_identity() -> None:
    brief = build_rectification_interview(
        _state(fields=["d10Lagna"]),
        session_id="session-test",
        locale="en",
    )
    proposed = {
        "questions": [
            {
                "questionId": question["questionId"],
                "category": question["category"],
                "title": f"Tell us about {question['title'].lower()}",
                "prompt": question["prompt"],
                "whyWeAsk": "A dated event lets us compare changes inside the time range.",
                "detailsPlaceholder": "Describe the factual change.",
            }
            for question in brief["questions"]
        ]
    }

    accepted = validate_agent_question_wording(brief, proposed)
    assert accepted["source"] == "agent_wording"

    proposed["questions"][0]["category"] = "health"
    with pytest.raises(ValueError, match="changed a question category"):
        validate_agent_question_wording(brief, proposed)


def test_agent_wording_cannot_lead_with_chart_details() -> None:
    brief = build_rectification_interview(
        _state(fields=["d10Lagna"]),
        session_id="session-test",
        locale="en",
    )
    proposed = {
        "questions": [
            {
                "questionId": question["questionId"],
                "category": question["category"],
                "title": question["title"],
                "prompt": "The D10 candidate expects a promotion. When did it happen?",
                "whyWeAsk": question["whyWeAsk"],
                "detailsPlaceholder": question["detailsPlaceholder"],
            }
            for question in brief["questions"]
        ]
    }

    with pytest.raises(ValueError, match="leading language"):
        validate_agent_question_wording(brief, proposed)


def test_consultation_answer_must_cite_an_approved_claim() -> None:
    context = {"approvedClaims": [{"claimId": "claim.career"}]}
    response = SkillRuntime._validate_consultation_answer_payload(
        {
            "answerability": "answered",
            "answer": "The approved career pattern supports reviewing the decision in stages.",
            "supportingClaimIds": ["claim.career"],
            "limitations": ["The chart does not determine one guaranteed outcome."],
            "followUpQuestions": [],
        },
        context,
    )
    assert response.supporting_claim_ids == ["claim.career"]

    with pytest.raises(ValueError, match="unknown claims"):
        SkillRuntime._validate_consultation_answer_payload(
            {
                "answerability": "answered",
                "answer": "This answer attempts to cite evidence that was never approved.",
                "supportingClaimIds": ["claim.invented"],
                "limitations": [],
                "followUpQuestions": [],
            },
            context,
        )


def test_consultation_can_decline_when_evidence_is_missing() -> None:
    response = SkillRuntime._validate_consultation_answer_payload(
        {
            "answerability": "insufficient_evidence",
            "answer": "The approved report does not contain evidence for that question.",
            "supportingClaimIds": [],
            "limitations": ["A relevant approved claim or timing window is missing."],
            "followUpQuestions": ["Would you like to ask about a topic included in the report?"],
        },
        {"approvedClaims": [{"claimId": "claim.career"}]},
    )
    assert response.answerability == "insufficient_evidence"
    assert response.supporting_claim_ids == []
