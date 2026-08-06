from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import pytest

from app.services.rectification_confirmation import replace_with_agent_examples
from app.services.skill_runtime import SkillRuntime
from app.services.skill_workspace import SkillWorkspace


def test_post_selection_examples_are_marked_as_non_scoring_checks() -> None:
    conclusion = {
        "status": "ready_for_confirmation",
        "examples": [],
        "generation": {"source": "deterministic_submitted_evidence"},
    }
    timing_periods = [
        {
            "periodId": "vimshottari.md.01",
            "level": "mahadasha",
            "start": "2018-01-01T00:00:00+00:00",
            "end": "2020-12-31T00:00:00+00:00",
        }
    ]

    updated = replace_with_agent_examples(
        conclusion,
        {
            "examples": [
                {
                    "category": "career",
                    "startDate": "2019",
                    "endDate": "2020",
                    "prompt": "Did your role or work direction change during this period?",
                    "rationale": "A broad timing period indicates a possible public-life transition.",
                    "supportingPeriodIds": ["vimshottari.md.01"],
                }
            ]
        },
        birth_date="1990-01-01",
        excluded_dates={"2018-06"},
        timing_periods=timing_periods,
    )

    assert updated["examples"][0]["source"] == "post_selection_agent"
    assert updated["examples"][0]["usedForSelection"] is False
    assert updated["generation"]["postSelectionOnly"] is True
    assert updated["generation"]["usedForSelection"] is False


def test_post_selection_examples_cannot_reuse_submitted_event_window() -> None:
    timing_periods = [
        {
            "periodId": "vimshottari.md.01",
            "level": "mahadasha",
            "start": "2017-01-01T00:00:00+00:00",
            "end": "2020-12-31T00:00:00+00:00",
        }
    ]
    with pytest.raises(ValueError, match="reused a submitted event"):
        replace_with_agent_examples(
            {"examples": []},
            {
                "examples": [
                    {
                        "category": "education",
                        "startDate": "2018",
                        "prompt": "Did your study direction change during this period?",
                        "supportingPeriodIds": ["vimshottari.md.01"],
                    }
                ]
            },
            birth_date="1990-01-01",
            excluded_dates={"2018-06"},
            timing_periods=timing_periods,
        )


def test_post_selection_examples_must_cite_a_period_covering_the_date() -> None:
    with pytest.raises(ValueError, match="outside its cited timing period"):
        replace_with_agent_examples(
            {"examples": []},
            {
                "examples": [
                    {
                        "category": "career",
                        "startDate": "2021",
                        "prompt": "Did your work direction change during this period?",
                        "supportingPeriodIds": ["vimshottari.md.01"],
                    }
                ]
            },
            birth_date="1990-01-01",
            timing_periods=[
                {
                    "periodId": "vimshottari.md.01",
                    "level": "mahadasha",
                    "start": "2018-01-01T00:00:00+00:00",
                    "end": "2020-12-31T00:00:00+00:00",
                }
            ],
        )


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
