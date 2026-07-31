from __future__ import annotations

from datetime import datetime, timezone

from app.vedicdust.models import (
    ChartPlacement,
    ChartRecord,
    SubjectContext,
    VargaChart,
    VargaHouseLord,
    ZodiacPosition,
)
from app.vedicdust.profiles import parashari_lahiri_profile
from app.vedicdust.synastry import build_synastry_context


def test_synastry_context_uses_typed_chart_records_and_directed_graha_drishti() -> None:
    a = _record("chart-a", "subject-a", lagna_sign=0, graha="Sun", graha_sign=0)
    b = _record("chart-b", "subject-b", lagna_sign=6, graha="Moon", graha_sign=6)

    context = build_synastry_context(
        a,
        b,
        b_label="B",
        relationship_type="partner",
        current_stage="dating",
        question="What needs attention?",
    )

    assert context.status == "ready_for_judgement"
    assert [subject.chart_record_id for subject in context.subjects] == ["chart-a", "chart-b"]
    assert any(
        overlay.source_role == "A"
        and overlay.source_object_id == "Sun"
        and overlay.target_role == "B"
        and overlay.target_house == 7
        for overlay in context.overlays
    )
    assert any(
        contact.source_role == "A"
        and contact.source_object_id == "Sun"
        and contact.target_role == "B"
        and contact.target_object_id == "Moon"
        and contact.contact_type == "seventh_drishti"
        for contact in context.contacts
    )
    assert "compatibilityScore" not in context.model_dump(by_alias=True)


def test_synastry_context_blocks_unrectified_chart_records() -> None:
    a = _record("chart-a", "subject-a", lagna_sign=0, graha="Sun", graha_sign=0)
    b = _record("chart-b", "subject-b", lagna_sign=6, graha="Moon", graha_sign=6)
    b.status = "rectification_required"

    context = build_synastry_context(
        a,
        b,
        b_label="B",
        relationship_type="",
        current_stage="",
        question="",
    )

    assert context.status == "blocked"
    assert any(
        check.check_id == "synastry.chart-record-status" and check.status == "failed"
        for check in context.quality_checks
    )


def _record(
    chart_record_id: str,
    subject_id: str,
    *,
    lagna_sign: int,
    graha: str,
    graha_sign: int,
) -> ChartRecord:
    d1 = VargaChart(
        varga_id="D1",
        factor=1,
        method="canonical-swiss-ephemeris",
        lagna=ChartPlacement(
            object_id="Lagna",
            position=_position(lagna_sign),
            house=1,
        ),
        placements=[
            ChartPlacement(
                object_id=graha,
                position=_position(graha_sign),
                house=((graha_sign - lagna_sign) % 12) + 1,
            )
        ],
        house_lords=[
            VargaHouseLord(
                house=house,
                sign=_position((lagna_sign + house - 1) % 12).sign,
                sign_index=(lagna_sign + house - 1) % 12,
                lord="Mars",
            )
            for house in range(1, 13)
        ],
        confidence="verified",
        eligible_as_primary_evidence=True,
    )
    return ChartRecord.model_construct(
        chart_record_id=chart_record_id,
        reading_session_id="session-1",
        revision=1,
        created_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
        subject=SubjectContext(subject_id=subject_id),
        calculation_profile=parashari_lahiri_profile(),
        charts=[d1],
        quality_checks=[],
        status="ready_for_judgement",
    )


def _position(sign_index: int) -> ZodiacPosition:
    return ZodiacPosition(
        longitude_deg=float(sign_index * 30 + 1),
        sign=f"sign-{sign_index}",
        sign_index=sign_index,
        degree_in_sign=1.0,
    )
