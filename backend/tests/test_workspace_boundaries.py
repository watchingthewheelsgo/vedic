from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.agents.claude_runtime import AgentRunResult
from app.services.report_exporter import ReportExporter
from app.services.skill_runtime import SkillRuntime
from app.services.skill_workspace import SkillWorkspace
from app.vedicdust.models import (
    BirthAssertion,
    ChartRecord,
    EvidenceItem,
    SubjectContext,
)
from app.vedicdust.profiles import parashari_lahiri_profile


def test_workspace_rejects_project_root_runtime_artifacts(tmp_path: Path) -> None:
    runtime_file = tmp_path / ".runtime" / "p2" / "yoga.md"
    runtime_file.parent.mkdir(parents=True)
    runtime_file.write_text("# stale root runtime\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="Root \\.runtime contains generated artifacts"):
        SkillWorkspace(SimpleNamespace(project_root=tmp_path))  # type: ignore[arg-type]


def test_active_vedic_skill_bundles_have_matching_metadata() -> None:
    project_root = Path(__file__).resolve().parents[2]
    skills_root = project_root / ".claude" / "skills" / "vedic"
    expected = {
        "vedic-calculator",
        "vedic-core",
        "vedic-reader",
        "vedic-rectifier",
        "vedic-synastry",
        "vedicdust-chart-audit",
        "vedicdust-consultation",
        "vedicdust-rectification-confirmation",
        "vedicdust-rectification-interview",
    }

    assert {
        path.name for path in skills_root.iterdir() if (path / "SKILL.md").is_file()
    } == expected
    for skill_name in sorted(expected):
        skill_dir = skills_root / skill_name
        skill_text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        metadata_text = (skill_dir / "agents" / "openai.yaml").read_text(encoding="utf-8")

        assert skill_text.startswith("---\n")
        assert f"\nname: {skill_name}\n" in skill_text
        assert "\ndescription:" in skill_text
        assert "display_name:" in metadata_text
        assert "short_description:" in metadata_text
        assert f"${skill_name}" in metadata_text


def test_report_export_defaults_to_session_exports_directory(tmp_path: Path) -> None:
    workspace = SkillWorkspace(SimpleNamespace(project_root=tmp_path))  # type: ignore[arg-type]
    session_id = workspace.create_session()
    workspace.write_artifact(session_id, "chart_record.json", '{"chartRecordId":"chart-1"}\n')
    workspace.write_session_manifest(session_id)
    workspace.write_artifact(
        session_id, "consultation_report.md", "# Consultation\n\nApproved report"
    )

    exporter = ReportExporter(workspace)

    def fake_render_pdf(**kwargs) -> None:
        kwargs["pdf_path"].write_text("pdf", encoding="utf-8")

    exporter._render_pdf_with_playwright = fake_render_pdf  # type: ignore[method-assign]
    result = exporter.export_session(session_id)

    session_dir = workspace.session_dir(session_id)
    assert result.html_path == session_dir / "exports" / "report.html"
    assert result.pdf_path == session_dir / "exports" / "report.pdf"
    assert result.html_path.exists()
    assert result.pdf_path.exists()


def test_chart_record_is_the_public_calculation_contract(tmp_path: Path) -> None:
    workspace = SkillWorkspace(SimpleNamespace(project_root=tmp_path))  # type: ignore[arg-type]
    session_id = workspace.create_session()
    workspace.write_artifact(
        session_id,
        "chart_record.json",
        '{"schemaVersion":"vedicdust-chart-record/1.6.0","chartRecordId":"chart-1"}\n',
    )
    workspace.write_artifact(session_id, "obsolete_artifact.md", "# ignored\n")

    public_artifacts = workspace.read_artifacts(session_id)
    runtime_artifacts = workspace.read_artifacts(session_id, include_internal=True)

    assert [artifact.path for artifact in public_artifacts] == ["chart_record.json"]
    assert runtime_artifacts[0].path == "chart_record.json"
    assert runtime_artifacts[0].kind == "json"


def test_rectification_runtime_artifacts_have_strict_client_projections(tmp_path: Path) -> None:
    workspace = SkillWorkspace(SimpleNamespace(project_root=tmp_path))  # type: ignore[arg-type]
    session_id = workspace.create_session()
    private_marker = "PRIVATE_CANDIDATE_EVIDENCE"
    source_payloads = {
        "birth_input_context.json": {
            "schemaVersion": "birth-input-context/v1",
            "time": {"reported": "09:30", "window": {"minutesBefore": 30}},
            "place": {"reported": "Shanghai", "coordinates": {"lat": 31.2, "lon": 121.5}},
            "lifeEvents": {
                "independentEpisodeCount": 1,
                "events": [
                    {
                        "date": "2020",
                        "category": "career",
                        "description": "Started a new job",
                        "role": "holdout",
                    }
                ],
            },
            "lifeEventSemantics": [{"private": private_marker}],
        },
        "sensitivity_scan.json": {
            "schemaVersion": "vedic-sensitivity-scan/v1",
            "summary": {"riskLevel": "high", "candidateScoringErrors": []},
            "reportReadiness": {
                "mode": "rectification_required",
                "candidateCount": 2,
            },
            "base": {"private": private_marker},
            "candidateGroups": [{"candidateId": "A", "private": private_marker}],
            "timeVariants": [{"private": private_marker}],
        },
        "chart_record.json": {
            "schemaVersion": "vedicdust-chart-record/1.6.0",
            "chartRecordId": "chart-1",
            "astronomy": {"public": "chart facts remain visible"},
            "sensitivityBoundaries": [
                {"beforeFingerprint": private_marker, "afterFingerprint": private_marker}
            ],
            "rectification": {
                "candidates": [
                    {
                        "candidateId": "A",
                        "evidenceScores": [{"explanation": private_marker}],
                    }
                ]
            },
        },
        "chart_rectification_state.json": {
            "schemaVersion": "vedicdust-chart-rectification-state/1.0.0",
            "status": "collecting_evidence",
            "riskLevel": "high",
            "equivalentCandidateIds": ["A", "B"],
            "holdoutResult": "not_run",
            "reportGate": {"fullReportAllowed": False, "nextStep": "collect_dated_events"},
            "rectificationPlan": {
                "action": "collect_dated_life_events",
                "eventCollectionRequired": True,
            },
            "selectionEvidence": {
                "calibrationEventCount": 2,
                "holdoutEventCount": 1,
                "blockers": [private_marker],
            },
            "lifeEventLedger": {
                "independentEpisodeCount": 1,
                "events": [
                    {
                        "eventId": "event-private",
                        "date": "2020",
                        "datePrecision": "year",
                        "category": "career",
                        "eventSubtype": "first_job",
                        "description": "Started a new job",
                        "role": "holdout",
                    }
                ],
            },
            "candidates": [
                {
                    "candidateId": "A",
                    "signature": {"private": private_marker},
                    "evidenceScores": [{"explanation": private_marker}],
                }
            ],
            "rectificationRounds": [
                {
                    "round": 1,
                    "evidenceImpact": {"private": private_marker},
                    "decision": {
                        "outcome": "candidate_scores_separated",
                        "selectedCandidateId": "A",
                    },
                }
            ],
            "rectificationConclusion": {
                "schemaVersion": "vedicdust-rectification-conclusion/1.2.0",
                "status": "ready_for_confirmation",
                "chartRevision": 2,
                "candidateId": "A",
                "confidence": "high",
                "correctedBirthTime": {
                    "localDate": "1990-01-01",
                    "localTime": "08:22",
                    "timezoneId": "Asia/Shanghai",
                },
                "evidenceSummary": {
                    "calibrationEventCount": 2,
                    "holdoutEventCount": 1,
                    "selectionPolicyId": private_marker,
                },
                "futurePrivateField": private_marker,
                "confirmation": {
                    "status": "pending",
                    "responses": [{"note": private_marker}],
                },
            },
        },
    }
    for path, payload in source_payloads.items():
        workspace.write_artifact(session_id, path, json.dumps(payload))

    public = {
        artifact.path: json.loads(artifact.content)
        for artifact in workspace.read_artifacts(session_id)
    }
    internal = {
        artifact.path: artifact.content
        for artifact in workspace.read_artifacts(session_id, include_internal=True)
    }

    assert set(source_payloads) <= set(public)
    assert private_marker not in json.dumps(public)
    assert private_marker in internal["chart_rectification_state.json"]
    assert "lifeEvents" not in public["birth_input_context.json"]
    assert "lifeEventSemantics" not in public["birth_input_context.json"]
    assert "candidateGroups" not in public["sensitivity_scan.json"]
    assert "timeVariants" not in public["sensitivity_scan.json"]
    assert "rectification" not in public["chart_record.json"]
    assert "sensitivityBoundaries" not in public["chart_record.json"]
    public_state = public["chart_rectification_state.json"]
    assert "candidates" not in public_state
    assert "holdoutResult" not in public_state
    assert "equivalentCandidateIds" not in public_state
    assert public_state["equivalentCandidateCount"] == 2
    assert public_state["lifeEventLedger"]["events"] == [
        {
            "date": "2020",
            "datePrecision": "year",
            "category": "career",
            "eventSubtype": "first_job",
            "description": "Started a new job",
        }
    ]
    assert public_state["rectificationRounds"] == [
        {"round": 1, "decision": {"outcome": "candidate_scores_separated"}}
    ]
    public_conclusion = public_state["rectificationConclusion"]
    assert public_conclusion["correctedBirthTime"]["localTime"] == "08:22"
    assert public_conclusion["confirmation"] == {"status": "pending"}
    assert "candidateId" not in public_conclusion
    assert "selectionPolicyId" not in public_conclusion["evidenceSummary"]
    assert "futurePrivateField" not in public_conclusion


def test_malformed_private_projection_is_not_returned_to_client(tmp_path: Path) -> None:
    workspace = SkillWorkspace(SimpleNamespace(project_root=tmp_path))  # type: ignore[arg-type]
    session_id = workspace.create_session()
    workspace.write_artifact(session_id, "chart_rectification_state.json", "not-json")

    public_paths = {artifact.path for artifact in workspace.read_artifacts(session_id)}
    internal = {
        artifact.path: artifact.content
        for artifact in workspace.read_artifacts(session_id, include_internal=True)
    }

    assert "chart_rectification_state.json" not in public_paths
    assert internal["chart_rectification_state.json"] == "not-json"


def test_core_completion_requires_all_released_consultation_artifacts(tmp_path: Path) -> None:
    workspace = SkillWorkspace(SimpleNamespace(project_root=tmp_path))  # type: ignore[arg-type]
    session_id = workspace.create_session()
    runtime = cast(Any, SkillRuntime.__new__(SkillRuntime))
    runtime.workspace = workspace
    dependencies = [
        "judgement_context.json",
        "claim_graph.json",
        "consultation_dossier.json",
    ]
    for path in dependencies:
        workspace.write_artifact(session_id, path, f'{{"path":"{path}"}}\n')

    released = [
        "consultation_report_manifest.json",
        "agent_context.json",
        "consultation_report.md",
    ]
    for path in released[:-1]:
        workspace.write_artifact(session_id, path, f"released:{path}\n")
        workspace.mark_artifact_checkpoint(
            session_id,
            path,
            producer="vedicdust-consultation-renderer",
            dependency_paths=dependencies,
        )

    assert runtime._consultation_artifacts_complete(session_id) is False

    workspace.write_artifact(session_id, released[-1], "# Consultation\n")
    workspace.mark_artifact_checkpoint(
        session_id,
        released[-1],
        producer="vedicdust-consultation-renderer",
        dependency_paths=dependencies,
    )
    assert runtime._consultation_artifacts_complete(session_id) is True

    workspace.write_artifact(session_id, dependencies[0], '{"changed":true}\n')
    assert runtime._consultation_artifacts_complete(session_id) is False


def test_reader_agent_view_is_minimal_and_blind_to_holdout_evidence() -> None:
    secret = "SECRET_HOLDOUT_EVENT_2023"
    artifacts = {
        "birth_input_context.json": json.dumps(
            {
                "lifeEvents": {
                    "schemaVersion": "life-event-ledger/v1",
                    "raw": f"2018 calibration\n2023 {secret}",
                    "categoryCounts": {"career": 1, "health": 1},
                    "eligibleEventCount": 2,
                    "events": [
                        {
                            "eventId": "evt-calibration",
                            "role": "calibration",
                            "description": "VISIBLE_CALIBRATION_EVENT",
                        },
                        {
                            "eventId": "evt-private",
                            "role": "holdout",
                            "description": secret,
                        },
                        {
                            "eventId": "evt-private-context",
                            "role": "holdout_context",
                            "description": f"{secret}_CORROBORATING",
                        },
                    ],
                }
            }
        ),
        "sensitivity_scan.json": json.dumps(
            {
                "candidateGroups": [
                    {
                        "candidateId": "A",
                        "holdoutScore": 0.9,
                        "evidenceScores": [
                            {"eventId": "evt-calibration", "role": "calibration", "score": 0.4},
                            {
                                "eventId": "evt-private",
                                "role": "holdout",
                                "score": 0.9,
                                "explanation": secret,
                            },
                        ],
                    }
                ]
            }
        ),
        "chart_rectification_state.json": json.dumps(
            {
                "holdoutResult": "passed",
                "reason": f"holdout passed because {secret}",
            }
        ),
        "consultation_report.md": secret,
    }

    visible = SkillRuntime._reader_agent_artifacts(artifacts)
    combined = "\n".join(visible.values())

    assert "VISIBLE_CALIBRATION_EVENT" in combined
    assert secret not in combined
    assert '"role": "holdout"' not in combined
    assert "holdoutScore" not in combined
    assert "holdoutResult" not in combined
    assert "consultation_report.md" not in visible


def test_reader_agent_view_projects_report_scale_chart_to_bounded_evidence() -> None:
    artifacts = {
        "chart_record.json": json.dumps(
            {
                "schemaVersion": "vedicdust-chart-record/1.6.0",
                "chartRecordId": "chart-1",
                "subject": {"currentAge": 30, "lifeStage": "adult"},
                "birthAssertion": {"localDate": "1996-01-01"},
                "charts": [
                    {
                        "vargaId": "D1",
                        "inputStability": "verified",
                        "eligibleAsPrimaryEvidence": True,
                    },
                    {
                        "vargaId": "D60",
                        "inputStability": "provisional",
                        "eligibleAsPrimaryEvidence": False,
                        "payload": "x" * 100_000,
                    },
                    {
                        "vargaId": "D10",
                        "inputStability": "provisional",
                        "eligibleAsPrimaryEvidence": True,
                    },
                ],
                "facts": [
                    {
                        "factId": "fact.D1.Lagna.position",
                        "factType": "rashi.lagna.position",
                        "subjectRef": "D1.Lagna",
                        "value": {"sign": "Aries"},
                        "inputStability": "verified",
                        "provenance": {"large": "x" * 100_000},
                    },
                    {
                        "factId": "fact.D60.Lagna.position",
                        "factType": "varga.lagna.position",
                        "subjectRef": "D60.Lagna",
                        "value": {"sign": "Virgo"},
                        "inputStability": "provisional",
                    },
                ],
                "timingPeriods": [
                    {
                        "periodId": "md-1",
                        "system": "Vimshottari",
                        "level": "mahadasha",
                        "lords": ["Saturn"],
                        "interval": {"start": "2010-01-01", "end": "2029-01-01"},
                        "inputStability": "verified",
                        "provenance": {"large": "x" * 100_000},
                    },
                    {
                        "periodId": "pd-1",
                        "system": "Vimshottari",
                        "level": "pratyantardasha",
                        "lords": ["Saturn", "Venus", "Moon"],
                        "interval": {"start": "2024-01-01", "end": "2024-02-01"},
                        "inputStability": "verified",
                        "payload": "x" * 100_000,
                    },
                    {
                        "periodId": "md-unstable",
                        "system": "Vimshottari",
                        "level": "mahadasha",
                        "lords": ["Mercury"],
                        "interval": {"start": "2012-01-01", "end": "2030-01-01"},
                        "inputStability": "provisional",
                    },
                ],
            }
        )
    }

    visible = SkillRuntime._reader_agent_artifacts(artifacts)
    projected = json.loads(visible["chart_record.json"])

    assert projected["readerProjectionVersion"] == "vedicdust-reader-evidence/1.0.0"
    assert [chart["vargaId"] for chart in projected["charts"]] == ["D1"]
    assert [fact["factId"] for fact in projected["facts"]] == ["fact.D1.Lagna.position"]
    assert [period["periodId"] for period in projected["timingPeriods"]] == ["md-1"]
    assert "provenance" not in visible["chart_record.json"]
    assert len(visible["chart_record.json"]) < 10_000


def test_agent_prompts_and_result_metadata_are_persisted_but_not_public(
    tmp_path: Path,
) -> None:
    workspace = SkillWorkspace(SimpleNamespace(project_root=tmp_path))  # type: ignore[arg-type]
    session_id = workspace.create_session()
    runtime = cast(Any, SkillRuntime.__new__(SkillRuntime))
    runtime.workspace = workspace

    prompt = "Use chart_record.json and return only the contracted dossier."
    prompt_path, prompt_hash = runtime._write_agent_prompt_trace(
        session_id,
        "agent_run_fixed",
        1,
        prompt,
    )
    execution = {
        "runId": "agent_run_fixed",
        "taskName": "vedicdust-consultation",
        "attempts": [
            {
                "attempt": 1,
                "promptPath": prompt_path,
                "promptSha256": prompt_hash,
                "status": "accepted",
                **runtime._agent_result_trace(
                    AgentRunResult(
                        mode="claude",
                        raw_text="done",
                        session_id="sdk-session-1",
                        duration_ms=1234,
                        total_cost_usd=0.031,
                        stop_reason="end_turn",
                        model="claude-test",
                    )
                ),
            }
        ],
    }
    runtime._persist_agent_run_trace(
        session_id,
        "core",
        "vedicdust_consultation",
        execution,
    )

    prompt_file = workspace.session_dir(session_id) / prompt_path
    trace_file = (
        workspace.session_dir(session_id) / ".runtime/agent-runs/core/vedicdust_consultation.json"
    )
    trace = json.loads(trace_file.read_text(encoding="utf-8"))
    attempt = trace["executions"][0]["attempts"][0]
    execution_trace = trace["executions"][0]

    assert prompt_file.read_text(encoding="utf-8") == prompt
    assert prompt_hash == hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    assert attempt["sdkSessionId"] == "sdk-session-1"
    assert attempt["durationMs"] == 1234
    assert attempt["totalCostUsd"] == 0.031
    assert attempt["stopReason"] == "end_turn"
    assert attempt["model"] == "claude-test"
    assert execution_trace["attemptCount"] == 1
    assert execution_trace["retryCount"] == 0
    assert execution_trace["finalStatus"] == "accepted"
    assert workspace.read_artifacts(session_id, include_internal=True) == []


def test_failed_agent_attempt_restores_allowed_and_protected_files(tmp_path: Path) -> None:
    workspace = SkillWorkspace(SimpleNamespace(project_root=tmp_path))  # type: ignore[arg-type]
    session_id = workspace.create_session()
    session_dir = workspace.session_dir(session_id)
    workspace.write_artifact(session_id, "consultation_dossier.json", '{"before":true}\n')
    workspace.write_artifact(session_id, "chart_record.json", '{"stable":true}\n')

    runtime = cast(Any, SkillRuntime.__new__(SkillRuntime))
    snapshot = runtime._snapshot_agent_workspace(
        session_dir,
        {"consultation_dossier.json", "new-output.json"},
    )
    workspace.write_artifact(session_id, "consultation_dossier.json", '{"partial":')
    workspace.write_artifact(session_id, "new-output.json", '{"partial":')
    workspace.write_artifact(session_id, "chart_record.json", '{"corrupted":true}\n')
    workspace.write_artifact(session_id, "undeclared.txt", "created by failed attempt")

    runtime._restore_failed_agent_attempt(
        session_dir,
        {"consultation_dossier.json", "new-output.json"},
        snapshot,
    )

    assert (session_dir / "consultation_dossier.json").read_text(encoding="utf-8") == (
        '{"before":true}\n'
    )
    assert not (session_dir / "new-output.json").exists()
    assert (session_dir / "chart_record.json").read_text(encoding="utf-8") == ('{"stable":true}\n')
    assert not (session_dir / "undeclared.txt").exists()


@pytest.mark.parametrize(
    ("error", "retryable"),
    [
        (TimeoutError("timed out"), True),
        (RuntimeError("API Error: Connection closed mid-response."), True),
        (RuntimeError("HTTP 503 service unavailable"), True),
        (RuntimeError("Invalid API key"), False),
        (RuntimeError("Claude Agent SDK runtime is not configured"), False),
        (ValueError("deterministic contract failed"), False),
    ],
)
def test_agent_transient_retry_classification(error: Exception, retryable: bool) -> None:
    assert SkillRuntime._is_transient_agent_error(error) is retryable


def test_checkpoint_invalidates_when_native_dependency_changes(tmp_path: Path) -> None:
    workspace = SkillWorkspace(SimpleNamespace(project_root=tmp_path))  # type: ignore[arg-type]
    session_id = workspace.create_session()
    workspace.write_artifact(session_id, "chart_record.json", '{"chartRevision":1}\n')
    workspace.write_artifact(session_id, "judgement_context.json", '{"revision":1}\n')
    workspace.write_artifact(session_id, "claim_graph.json", '{"claims":[]}\n')
    workspace.mark_artifact_checkpoint(
        session_id,
        "claim_graph.json",
        producer="vedicdust-claim-graph",
        dependency_paths=["judgement_context.json"],
    )

    assert workspace.artifact_checkpoint_valid(
        session_id,
        "claim_graph.json",
        producer="vedicdust-claim-graph",
        dependency_paths=["judgement_context.json"],
    )

    workspace.write_artifact(session_id, "judgement_context.json", '{"revision":2}\n')

    assert not workspace.artifact_checkpoint_valid(
        session_id,
        "claim_graph.json",
        producer="vedicdust-claim-graph",
        dependency_paths=["judgement_context.json"],
    )


def test_reading_session_keeps_chart_identity_across_revisions(tmp_path: Path) -> None:
    workspace = SkillWorkspace(SimpleNamespace(project_root=tmp_path))  # type: ignore[arg-type]
    session_id = workspace.create_session()
    record = ChartRecord(
        chart_record_id="chart-stable",
        reading_session_id=session_id,
        revision=1,
        created_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
        subject=SubjectContext(subject_id="subject-stable"),
        birth_assertion=BirthAssertion(
            local_date="1990-01-01",
            reported_local_time="08:00",
            reported_place="Shanghai, China",
            time_certainty="reported_exact",
            evidence=[
                EvidenceItem(
                    evidence_id="birth-input",
                    evidence_class="user_testimony",
                    source_label="user",
                    observed_value="1990-01-01 08:00",
                    confidence="corroborated",
                )
            ],
        ),
        calculation_profile=parashari_lahiri_profile(),
        status="intake",
    )
    workspace.write_artifact(
        session_id,
        "chart_record.json",
        record.model_dump_json(by_alias=True),
    )
    runtime = cast(Any, SkillRuntime.__new__(SkillRuntime))
    runtime.workspace = workspace

    revision = runtime._chart_record_identity(session_id, revision=2)

    assert revision.reading_session_id == session_id
    assert revision.chart_record_id == "chart-stable"
    assert revision.subject_id == "subject-stable"
    assert revision.revision == 2
    reading = workspace.read_artifact_text(session_id, "reading_session.json")
    assert reading is not None


def test_legacy_rectification_vote_artifacts_are_not_active_runtime_files(
    tmp_path: Path,
) -> None:
    workspace = SkillWorkspace(SimpleNamespace(project_root=tmp_path))  # type: ignore[arg-type]
    session_id = workspace.create_session()
    workspace.write_artifact(session_id, "rectification_question_set.json", "{}")
    workspace.write_artifact(session_id, "rectification_answer_batch.json", "{}")

    visible = {artifact.path for artifact in workspace.read_artifacts(session_id)}
    internal = {
        artifact.path for artifact in workspace.read_artifacts(session_id, include_internal=True)
    }
    assert "rectification_question_set.json" not in visible
    assert "rectification_answer_batch.json" not in visible
    assert "rectification_question_set.json" not in internal
    assert "rectification_answer_batch.json" not in internal


def test_life_event_evidence_audit_is_internal_only(tmp_path: Path) -> None:
    workspace = SkillWorkspace(SimpleNamespace(project_root=tmp_path))  # type: ignore[arg-type]
    session_id = workspace.create_session()
    workspace.write_artifact(
        session_id,
        "life_event_evidence_validation.json",
        '{"source":"agent_semantic_enrichment"}\n',
    )

    public_paths = {artifact.path for artifact in workspace.read_artifacts(session_id)}
    internal_paths = {
        artifact.path for artifact in workspace.read_artifacts(session_id, include_internal=True)
    }
    assert "life_event_evidence_validation.json" not in public_paths
    assert "life_event_evidence_validation.json" in internal_paths


def test_rectification_transaction_recovers_archived_revision_after_interruption(
    tmp_path: Path,
) -> None:
    settings = SimpleNamespace(project_root=tmp_path)
    workspace = SkillWorkspace(settings)  # type: ignore[arg-type]
    session_id = workspace.create_session()
    workspace.write_artifact(session_id, "chart_record.json", '{"revision":1}\n')
    workspace.write_artifact(
        session_id,
        "chart_rectification_state.json",
        '{"status":"collecting_evidence","revision":1}\n',
    )
    workspace.write_session_manifest(session_id)
    workspace.mark_artifact_checkpoint(
        session_id,
        "chart_record.json",
        producer="test-fixture",
    )

    workspace.begin_rectification_transaction(session_id)
    workspace.write_artifact(
        session_id,
        ".runtime/chart_revisions/rev_1/chart_record.json",
        '{"revision":1}\n',
    )
    workspace.write_artifact(
        session_id,
        ".runtime/chart_revisions/rev_1/chart_rectification_state.json",
        '{"status":"collecting_evidence","revision":1}\n',
    )
    session_dir = workspace.require_session_dir(session_id)
    workspace.write_artifact(
        session_id,
        ".runtime/chart_revisions/rev_1/.meta/session.json",
        (session_dir / ".meta/session.json").read_text(encoding="utf-8"),
    )
    checkpoint_relative_path = workspace.artifact_checkpoint_relative_path("chart_record.json")
    workspace.write_artifact(
        session_id,
        f".runtime/chart_revisions/rev_1/{checkpoint_relative_path}",
        (session_dir / checkpoint_relative_path).read_text(encoding="utf-8"),
    )
    workspace.mark_rectification_transaction_archive_ready(session_id)
    workspace.write_artifact(session_id, "chart_record.json", '{"revision":2}\n')
    workspace.write_artifact(
        session_id,
        "chart_rectification_state.json",
        '{"status":"corrected_chart_ready","revision":2}\n',
    )
    workspace.write_session_manifest(session_id)
    workspace.mark_artifact_checkpoint(
        session_id,
        "chart_record.json",
        producer="new-fixture",
    )

    recovered_workspace = SkillWorkspace(settings)  # type: ignore[arg-type]
    assert recovered_workspace.read_artifact_text(session_id, "chart_record.json") == (
        '{"revision":1}\n'
    )
    assert (
        recovered_workspace.read_artifact_text(session_id, "chart_rectification_state.json")
        == '{"status":"collecting_evidence","revision":1}\n'
    )
    assert recovered_workspace.read_session_locale(session_id) == "en"
    assert recovered_workspace.artifact_checkpoint_valid(
        session_id,
        "chart_record.json",
        producer="test-fixture",
    )


def test_judgement_prefers_active_rectified_sensitivity(tmp_path: Path) -> None:
    workspace = SkillWorkspace(SimpleNamespace(project_root=tmp_path))  # type: ignore[arg-type]
    session_id = workspace.create_session()
    workspace.write_artifact(session_id, "sensitivity_scan.json", '{"source":"reported-window"}')
    runtime = cast(Any, SkillRuntime.__new__(SkillRuntime))
    runtime.workspace = workspace

    assert runtime._judgement_sensitivity(session_id) == {"source": "reported-window"}

    workspace.write_artifact(
        session_id,
        "active_chart_sensitivity.json",
        '{"source":"rectified-canonical-chart"}',
    )
    workspace.write_artifact(session_id, "chart_record.json", '{"revision":2}')
    workspace.write_artifact(
        session_id,
        "chart_rectification_state.json",
        '{"status":"corrected_chart_ready"}',
    )
    workspace.mark_artifact_checkpoint(
        session_id,
        "active_chart_sensitivity.json",
        producer="calculator:rectification-active-sensitivity",
        dependency_paths=["chart_record.json"],
    )

    assert runtime._judgement_sensitivity(session_id) == {"source": "rectified-canonical-chart"}

    workspace.write_artifact(
        session_id,
        "active_chart_sensitivity.json",
        '{"source":"tampered"}',
    )
    with pytest.raises(ValueError, match="stale or was modified"):
        runtime._judgement_sensitivity(session_id)


def test_judgement_rejects_corrected_chart_without_active_sensitivity(tmp_path: Path) -> None:
    workspace = SkillWorkspace(SimpleNamespace(project_root=tmp_path))  # type: ignore[arg-type]
    session_id = workspace.create_session()
    workspace.write_artifact(session_id, "chart_record.json", '{"revision":2}')
    workspace.write_artifact(session_id, "sensitivity_scan.json", '{"source":"reported-window"}')
    workspace.write_artifact(
        session_id,
        "chart_rectification_state.json",
        '{"status":"corrected_chart_ready"}',
    )
    runtime = cast(Any, SkillRuntime.__new__(SkillRuntime))
    runtime.workspace = workspace

    with pytest.raises(ValueError, match="missing its bounded sensitivity scan"):
        runtime._judgement_sensitivity(session_id)
