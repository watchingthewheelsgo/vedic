from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import cast

import pytest

from app.schemas import BirthInput
from app.services.rectification_confirmation import build_rectification_conclusion
from app.services.skill_runtime import SkillRuntime
from app.services.skill_workspace import SkillWorkspace


def test_deterministic_fallback_reviews_time_without_reusing_submitted_events() -> None:
    conclusion = build_rectification_conclusion(
        {
            "selectedCandidateId": "candidate-a",
            "selectionConfidence": "medium",
            "candidates": [
                {
                    "candidateId": "candidate-a",
                    "interval": {
                        "start": "1990-01-01 08:20",
                        "end": "1990-01-01 08:25",
                    },
                    "evidenceScores": [
                        {
                            "eventId": "event-calibration",
                            "score": 0.4,
                            "selectionScore": 0.4,
                        },
                        {"eventId": "event-generic", "score": 1.0, "selectionScore": 0.3},
                        {"eventId": "event-holdout", "score": 0.3, "selectionScore": 0.3},
                    ],
                },
                {
                    "candidateId": "candidate-b",
                    "interval": {
                        "start": "1990-01-01 08:25",
                        "end": "1990-01-01 08:30",
                    },
                    "evidenceScores": [
                        {
                            "eventId": "event-calibration",
                            "score": 0.0,
                            "selectionScore": 0.0,
                        },
                        {"eventId": "event-generic", "score": 0.0, "selectionScore": 0.3},
                        {"eventId": "event-holdout", "score": 0.1, "selectionScore": 0.1},
                    ],
                },
            ],
            "lifeEventLedger": {
                "events": [
                    {
                        "eventId": "event-calibration",
                        "date": "2018",
                        "description": "Submitted marriage event",
                        "category": "relationship",
                        "eventSubtype": "marriage",
                        "role": "calibration",
                        "intakeSequence": 1,
                    },
                    {
                        "eventId": "event-generic",
                        "date": "2020",
                        "description": "Submitted career event",
                        "category": "career",
                        "eventSubtype": "job_change",
                        "role": "calibration",
                        "intakeSequence": 2,
                    },
                    {
                        "eventId": "event-holdout",
                        "date": "2022-06",
                        "description": "Submitted relocation event",
                        "category": "relocation",
                        "eventSubtype": "moved_city",
                        "role": "holdout",
                        "intakeSequence": 3,
                    },
                ]
            },
            "selectionEvidence": {},
            "holdoutResult": "passed",
            "methodMaturity": "product_hypothesis",
            "validationStatus": "internal_regression_only",
        },
        rectified_input=BirthInput(
            birthDate="1990-01-01",
            birthTime="08:22",
            birthPlace="Shanghai, China",
            birthTimePrecision="exact",
            locale="en",
        ),
        chart_revision=2,
    )

    assert conclusion["examples"][0]["source"] == "deterministic_input_review"
    assert conclusion["examples"][0]["usedForSelection"] is False
    assert "Submitted marriage event" not in conclusion["examples"][0]["prompt"]
    assert conclusion["generation"]["source"] == "deterministic_evidence_review"
    assert conclusion["generation"]["usedForSelection"] is False
    assert conclusion["examples"][1]["source"] == "submitted_evidence"
    assert "Submitted marriage event" in conclusion["examples"][1]["prompt"]
    assert conclusion["selectedInterval"]["boundarySemantics"] == ("start_inclusive_end_exclusive")
    assert "to before 1990-01-01 08:25" in conclusion["examples"][0]["prompt"]
    assert conclusion["methodAssurance"] == {
        "methodMaturity": "product_hypothesis",
        "validationStatus": "internal_regression_only",
        "independentProfessionalReviewCompleted": False,
    }
    assert conclusion["evidenceHighlights"] == [
        {
            "date": "2018",
            "datePrecision": None,
            "category": "relationship",
            "eventSubtype": "marriage",
            "description": "Submitted marriage event",
            "role": "calibration",
            "result": "used_for_candidate_comparison",
            "usedForSelection": True,
        },
        {
            "date": "2022-06",
            "datePrecision": None,
            "category": "relocation",
            "eventSubtype": "moved_city",
            "description": "Submitted relocation event",
            "role": "holdout",
            "result": "passed_reserved_cross_check",
            "usedForSelection": False,
        },
    ]


def test_confirmation_checkpoint_does_not_generate_agent_life_events() -> None:
    class FailingAgentRuntime:
        async def run_skill_prompt_task(self, *_args: object, **_kwargs: object) -> object:
            raise AssertionError("confirmation Agent must not run")

    runtime = SkillRuntime.__new__(SkillRuntime)
    runtime.agent_runtime = FailingAgentRuntime()  # type: ignore[assignment]
    state = {
        "status": "rectification_confirmation_required",
        "rectificationConclusion": {
            "generation": {"source": "deterministic_input_review"},
            "examples": [
                {"exampleId": "corrected-time-review", "source": "deterministic_input_review"}
            ],
        },
    }

    prepared = asyncio.run(runtime._prepare_rectification_confirmation_examples("session", state))

    assert prepared is state
    assert prepared["rectificationConclusion"]["examples"] == [
        {"exampleId": "corrected-time-review", "source": "deterministic_input_review"}
    ]


def test_core_readiness_rejects_pending_rectification_checkpoint(tmp_path) -> None:
    workspace = SkillWorkspace(SimpleNamespace(project_root=tmp_path))  # type: ignore[arg-type]
    session_id = "pending-rectification-checkpoint"
    workspace.create_session(session_id)
    workspace.write_artifact(
        session_id,
        "chart_rectification_state.json",
        '{"status":"rectification_confirmation_required",'
        '"rectificationConclusion":{"confirmation":{"status":"pending"}}}\n',
    )
    runtime = SkillRuntime(
        calculator=cast(object, object()),  # type: ignore[arg-type]
        workspace=workspace,
        agent_runtime=cast(object, None),  # type: ignore[arg-type]
    )

    with pytest.raises(ValueError, match="确认阶段性的生时校正结论"):
        runtime.assert_core_readiness(session_id)
