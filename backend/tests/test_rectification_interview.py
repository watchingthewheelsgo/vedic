from __future__ import annotations

import asyncio
import json
from datetime import date
from types import SimpleNamespace
from typing import Any

import pytest

from app.schemas import (
    ConsultationAnswerResponse,
    RectificationInterviewInput,
    RectificationLifeEventInput,
)
from app.services.rectification_interview import (
    build_rectification_interview,
    validate_agent_event_evidence,
    validate_agent_question_wording,
    validate_rectification_event_bindings,
    validate_rectification_event_dates,
)
from app.services.skill_runtime import SkillRuntime
from app.services.life_event_rectification import parse_life_event_ledger
from app.services.chart_rectification import ChartRectificationService
from app.services.skill_workspace import SkillWorkspace


def _state(
    *,
    status: str = "collecting_evidence",
    fields: list[str] | None = None,
    categories: list[str] | None = None,
) -> dict[str, Any]:
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

    assert [question["category"] for question in interview["questions"]] == ["career"]
    assert len(interview["questions"]) == 1
    assert interview["progress"]["target"] == 3
    assert interview["source"] == "deterministic_brief"
    assert interview["questions"][0]["questionValue"]["tier"] == "discriminating"
    assert interview["questions"][0]["questionValue"]["matchedFields"] == ["d10Lagna"]
    assert len(interview["questionPool"]) >= 2
    assert interview["questions"][0]["questionId"] == interview["questionPool"][0]["questionId"]
    assert "候选" not in " ".join(question["prompt"] for question in interview["questions"])


def test_question_ranking_prefers_the_field_with_better_candidate_partition() -> None:
    state = _state(fields=["d10Lagna", "d4Structure"])
    state["rectificationPlan"]["questionDiscrimination"] = {
        "d10Lagna": {
            "candidateCount": 3,
            "partitionCount": 2,
            "largestPartitionSize": 2,
        },
        "d4Structure": {
            "candidateCount": 3,
            "partitionCount": 3,
            "largestPartitionSize": 1,
        },
    }
    interview = build_rectification_interview(
        state,
        session_id="session-test",
        locale="en",
    )

    assert interview["questions"][0]["category"] == "relocation"
    assert interview["questions"][0]["questionValue"]["partitionCount"] == 3


def test_user_available_categories_bound_the_candidate_driven_question_pool() -> None:
    interview = build_rectification_interview(
        _state(fields=["d10Lagna", "d4Structure"]),
        session_id="session-test",
        locale="zh",
        available_categories={"relocation", "health"},
    )

    assert [question["category"] for question in interview["questions"]] == ["relocation"]
    assert {question["category"] for question in interview["questionPool"]} <= {
        "relocation",
        "health",
    }
    assert interview["availableCategories"] == ["health", "relocation"]


def test_agent_event_evidence_prompt_renders_nested_json_contract() -> None:
    class FakeAgentRuntime:
        def is_configured(self) -> bool:
            return True

        async def run_skill_prompt_task(self, _task: str, prompt: str, **_kwargs: object):
            assert '"eventFacts": {' in prompt
            assert '"dateConfidence": "year|month|day|unknown"' in prompt
            return SimpleNamespace(
                raw_text=json.dumps(
                    {
                        "results": [
                            {
                                "questionId": "q-education",
                                "category": "education",
                                "eventSubtype": "graduation",
                                "accepted": True,
                                "reason": "Concrete dated event.",
                                "eventFacts": {
                                    "occurrence": "occurred",
                                    "agency": "active",
                                    "impact": "major",
                                    "dateConfidence": "month",
                                },
                            }
                        ]
                    }
                )
            )

    runtime = SkillRuntime.__new__(SkillRuntime)
    runtime.agent_runtime = FakeAgentRuntime()  # type: ignore[assignment]

    result = asyncio.run(
        runtime._validate_rectification_event_evidence(
            [
                {
                    "questionId": "q-education",
                    "category": "education",
                    "eventSubtype": "graduation",
                    "date": "2012-09",
                    "description": "Started university",
                }
            ]
        )
    )

    assert result["source"] == "agent_semantic_validation"
    assert result["results"][0]["eventSubtype"] == "graduation"
    assert result["results"][0]["eventFacts"]["dateConfidence"] == "month"


def test_underdetermined_state_requests_round_four_until_maximum_evidence() -> None:
    service = ChartRectificationService()
    ledger = parse_life_event_ledger(
        "2012 education: Graduated\n2018 career: Changed jobs\n2020 relationship: Married"
    )
    state = {
        "lifeEventLedger": ledger,
        "candidates": [
            {
                "candidateId": "A",
                "score": 0.1,
                "evidenceScores": [],
                "changedFromBase": [],
                "signature": {"d10Lagna": "Aries"},
            },
            {
                "candidateId": "B",
                "score": 0.1,
                "evidenceScores": [],
                "changedFromBase": ["d10Lagna"],
                "signature": {"d10Lagna": "Taurus"},
            },
        ],
        "status": "comparing_candidates",
        "reportGate": {"fullReportAllowed": False},
    }

    updated = service._apply_initial_deterministic_event_decision(state)

    assert updated["status"] == "underdetermined"
    assert updated["lifeEventLedger"]["eventCollectionRequired"] is True
    assert updated["rectificationPlan"]["action"] == "collect_dated_life_events"

    updated["lifeEventLedger"]["eligibleEventCount"] = 5
    service._set_additional_event_request(updated)
    updated["rectificationPlan"] = service._build_rectification_plan(updated)
    assert updated["lifeEventLedger"]["eventCollectionRequired"] is False
    assert updated["rectificationPlan"]["action"] == "rectification_inconclusive"


def test_underdetermined_round_can_reuse_best_domain_after_breadth_requirement() -> None:
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
    assert interview["questions"][0]["category"] == "career"
    assert interview["progress"]["answered"] == 3
    assert interview["progress"]["target"] == 4
    assert interview["progress"]["maximumAccepted"] == 5


def test_third_reserved_event_prefers_a_new_domain_when_available() -> None:
    interview = build_rectification_interview(
        _state(
            status="collecting_evidence",
            fields=["d10Lagna", "d4Structure", "d24Lagna"],
            categories=["career", "relocation"],
        ),
        session_id="session-test",
        locale="en",
        available_categories={"career", "relocation", "education"},
    )

    assert interview["questions"][0]["category"] == "education"


def test_third_reserved_event_may_repeat_when_only_two_domains_are_available() -> None:
    interview = build_rectification_interview(
        _state(
            status="collecting_evidence",
            fields=["d10Lagna", "d4Structure"],
            categories=["career", "relocation"],
        ),
        session_id="session-test",
        locale="en",
        available_categories={"career", "relocation"},
    )

    assert interview["questions"][0]["category"] in {"career", "relocation"}


def test_runtime_allows_round_four_when_recalculation_requests_more_evidence(tmp_path) -> None:
    async def run() -> None:
        workspace = SkillWorkspace(SimpleNamespace(project_root=tmp_path))  # type: ignore[arg-type]
        session_id = workspace.create_session("round-four")
        state = _state(
            status="underdetermined",
            fields=["d30Lagna"],
            categories=["career", "relocation", "education"],
        )
        state["rectificationPlan"]["eventCollectionRequired"] = True
        workspace.write_artifact(
            session_id,
            "chart_rectification_state.json",
            json.dumps(state),
        )
        runtime = SkillRuntime(
            calculator=object(),  # type: ignore[arg-type]
            workspace=workspace,
            agent_runtime=None,  # type: ignore[arg-type]
        )

        response = await runtime.prepare_rectification_interview(
            RectificationInterviewInput(
                sessionId=session_id,
                locale="en",
                availableCategories=["career", "relocation", "education", "health"],
            ),
            use_agent=False,
        )
        interview = json.loads(
            workspace.read_artifact_text(session_id, "rectification_interview.json") or "{}"
        )

        assert response.stage == "reader_ready"
        assert interview["round"] == 4
        assert interview["questions"][0]["category"] == "health"

    asyncio.run(run())


def test_skipped_category_is_not_reissued() -> None:
    interview = build_rectification_interview(
        _state(fields=["d10Lagna", "d4Structure"]),
        session_id="session-test",
        locale="en",
        skipped_categories={"career"},
    )

    assert interview["questions"][0]["category"] != "career"


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
    assert {question["category"] for question in interview["questionPool"]}.isdisjoint(
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
    assert "questionPool" not in accepted
    assert "questionValue" not in accepted["questions"][0]

    proposed["questions"][0]["category"] = "health"
    with pytest.raises(ValueError, match="changed a question category"):
        validate_agent_question_wording(brief, proposed)


def test_agent_cannot_switch_to_a_lower_ranked_pool_question() -> None:
    brief = build_rectification_interview(
        _state(fields=["d10Lagna", "d4Structure"]),
        session_id="session-test",
        locale="en",
    )
    selected = brief["questionPool"][1]
    proposed = {
        "questions": [
            {
                "questionId": selected["questionId"],
                "category": selected["category"],
                "title": selected["title"],
                "prompt": selected["prompt"],
                "whyWeAsk": selected["whyWeAsk"],
                "detailsPlaceholder": selected["detailsPlaceholder"],
            }
        ]
    }

    with pytest.raises(ValueError, match="backend question set"):
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


def test_rectification_event_dates_accept_year_precision_and_reject_impossible_ranges() -> None:
    validate_rectification_event_dates(
        [{"date": "2018"}, {"date": "2020-02"}, {"date": "2024-02-29"}],
        birth_date="1990-01-01",
        today=date(2026, 8, 3),
    )

    with pytest.raises(ValueError, match="invalid calendar date"):
        validate_rectification_event_dates(
            [{"date": "2023-02-31"}],
            birth_date="1990-01-01",
            today=date(2026, 8, 3),
        )
    with pytest.raises(ValueError, match="before the birth date"):
        validate_rectification_event_dates(
            [{"date": "1989"}],
            birth_date="1990-01-01",
            today=date(2026, 8, 3),
        )
    with pytest.raises(ValueError, match="in the future"):
        validate_rectification_event_dates(
            [{"date": "2099"}],
            birth_date="1990-01-01",
            today=date(2026, 8, 3),
        )


def test_rectification_event_must_match_backend_question_category() -> None:
    state = _state(fields=["d10Lagna"])
    interview = build_rectification_interview(
        state,
        session_id="session-test",
        locale="en",
    )
    question = interview["questions"][0]
    event = {
        "questionId": question["questionId"],
        "date": "2018",
        "category": question["category"],
        "eventSubtype": question["allowedSubtypes"][0],
        "description": "Changed employer",
    }
    assert validate_rectification_event_bindings([event], state=state, interview=interview) == [
        event
    ]

    with pytest.raises(ValueError, match="does not match"):
        validate_rectification_event_bindings(
            [{**event, "category": "health"}],
            state=state,
            interview=interview,
        )

    with pytest.raises(ValueError, match="subtype does not match"):
        validate_rectification_event_bindings(
            [{**event, "eventSubtype": "not_an_option"}],
            state=state,
            interview=interview,
        )

    with pytest.raises(ValueError, match="exactly one"):
        validate_rectification_event_bindings(
            [event, event],
            state=state,
            interview=interview,
        )

    with pytest.raises(ValueError, match="current verification question"):
        validate_rectification_event_bindings(
            [{**event, "questionId": None}],
            state=state,
            interview=interview,
        )


def test_rectification_event_schema_rejects_cross_category_subtype() -> None:
    with pytest.raises(ValueError, match="not valid for category"):
        RectificationLifeEventInput.model_validate(
            {
                "questionId": "rectify.r1.q1.career",
                "date": "2018",
                "category": "career",
                "eventSubtype": "marriage",
                "description": "Changed employer",
            }
        )


def test_rectification_event_schema_requires_backend_bound_subtype() -> None:
    with pytest.raises(ValueError, match="eventSubtype"):
        RectificationLifeEventInput.model_validate(
            {
                "questionId": "rectify.r1.q1.career",
                "date": "2018",
                "category": "career",
                "description": "Started a new job",
            }
        )


def test_agent_cannot_duplicate_the_single_backend_question() -> None:
    brief = build_rectification_interview(
        _state(fields=["d10Lagna"]),
        session_id="session-duplicate-question",
        locale="en",
    )
    original = brief["questions"][0]
    wording = {
        **original,
        "title": "A career turning point",
        "prompt": "Which dated career change do you remember most clearly?",
        "whyWeAsk": "A dated event helps compare the remaining time ranges.",
        "detailsPlaceholder": "Choose the event and add a short factual note.",
    }

    with pytest.raises(ValueError, match="exactly once"):
        validate_agent_question_wording(brief, {"questions": [wording, wording]})


def test_agent_event_audit_must_account_for_and_accept_every_event() -> None:
    events = [
        {
            "questionId": "rectify.r1.q1.career",
            "category": "career",
            "date": "2018",
            "description": "Changed employer",
        }
    ]
    validated = validate_agent_event_evidence(
        events,
        {
            "results": [
                {
                    "questionId": "rectify.r1.q1.career",
                    "category": "career",
                    "accepted": True,
                    "reason": "Concrete career event",
                }
            ]
        },
    )
    assert validated[0]["accepted"] is True
    assert validated[0]["eventFacts"] == {
        "occurrence": "occurred",
        "agency": "unknown",
        "impact": "unknown",
        "dateConfidence": "unknown",
    }

    with pytest.raises(ValueError, match="Please revise"):
        validate_agent_event_evidence(
            events,
            {
                "results": [
                    {
                        "questionId": "rectify.r1.q1.career",
                        "category": "career",
                        "accepted": False,
                        "reason": "This describes an unrelated purchase.",
                    }
                ]
            },
        )


def test_semantic_event_facts_are_attached_to_the_deterministic_ledger() -> None:
    ledger = parse_life_event_ledger(
        "2018 career: Changed employer",
        semantic_evidence=[
            {
                "questionId": "rectify.r1.q1.career",
                "date": "2018",
                "category": "career",
                "description": "Changed employer",
                "eventFacts": {
                    "occurrence": "occurred",
                    "agency": "active",
                    "impact": "major",
                    "dateConfidence": "year",
                },
            }
        ],
    )

    event = ledger["events"][0]
    assert event["eventId"] == f"evt_{event['eventFingerprint'][:16]}"
    assert event["semanticFacts"]["impact"] == "major"


def test_event_ids_do_not_change_when_an_older_event_is_inserted() -> None:
    before = parse_life_event_ledger(
        "2018 career: Changed employer\n2020 relationship: Registered marriage"
    )
    after = parse_life_event_ledger(
        "2012 education: Graduated\n2018 career: Changed employer\n"
        "2020 relationship: Registered marriage"
    )

    before_ids = {event["date"]: event["eventId"] for event in before["events"]}
    after_ids = {event["date"]: event["eventId"] for event in after["events"]}
    assert after_ids["2018"] == before_ids["2018"]
    assert after_ids["2020"] == before_ids["2020"]


def test_consultation_answer_rejects_unsupported_certainty_language() -> None:
    with pytest.raises(ValueError, match="deterministic outcome"):
        SkillRuntime._validate_consultation_answer_payload(
            {
                "answerability": "answered",
                "answer": "You will certainly win the lottery tomorrow according to this chart.",
                "supportingClaimIds": ["claim.career"],
                "limitations": [],
                "followUpQuestions": [],
            },
            {"approvedClaims": [{"claimId": "claim.career"}]},
        )


def test_consultation_grounding_audit_rejects_content_beyond_cited_claims() -> None:
    class FakeAgentRuntime:
        async def run_skill_prompt_task(self, *_args: object, **_kwargs: object):
            return SimpleNamespace(
                raw_text=json.dumps(
                    {
                        "supported": False,
                        "unsafeCertainty": False,
                        "unsupportedStatements": ["The answer invents a financial outcome."],
                    }
                )
            )

    runtime = SkillRuntime.__new__(SkillRuntime)
    runtime.agent_runtime = FakeAgentRuntime()  # type: ignore[assignment]
    response = ConsultationAnswerResponse(
        answerability="answered",
        answer="The report says this career pattern guarantees a specific financial result.",
        supportingClaimIds=["claim.career"],
        limitations=[],
        followUpQuestions=[],
    )
    with pytest.raises(ValueError, match="failed grounding audit"):
        asyncio.run(
            runtime._audit_consultation_answer(
                question="Will this make me rich?",
                response=response,
                context={
                    "approvedClaims": [
                        {
                            "claimId": "claim.career",
                            "plainStatement": "Career decisions benefit from staged review.",
                        }
                    ]
                },
                locale="en",
            )
        )


def test_consultation_grounding_audit_retries_malformed_contract_once() -> None:
    class FakeAgentRuntime:
        def __init__(self) -> None:
            self.calls = 0

        async def run_skill_prompt_task(self, *_args: object, **_kwargs: object):
            self.calls += 1
            if self.calls == 1:
                return SimpleNamespace(raw_text="not json")
            return SimpleNamespace(
                raw_text=json.dumps(
                    {
                        "supported": True,
                        "unsafeCertainty": False,
                        "unsupportedStatements": [],
                    }
                )
            )

    runtime = SkillRuntime.__new__(SkillRuntime)
    fake = FakeAgentRuntime()
    runtime.agent_runtime = fake  # type: ignore[assignment]
    response = ConsultationAnswerResponse(
        answerability="answered",
        answer="The approved career pattern supports reviewing this decision in stages.",
        supportingClaimIds=["claim.career"],
        limitations=[],
        followUpQuestions=[],
    )

    asyncio.run(
        runtime._audit_consultation_answer(
            question="How should I approach this career decision?",
            response=response,
            context={
                "approvedClaims": [
                    {
                        "claimId": "claim.career",
                        "plainStatement": "Career decisions benefit from staged review.",
                    }
                ]
            },
            locale="en",
        )
    )

    assert fake.calls == 2
