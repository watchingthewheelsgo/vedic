from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from app.utils.ids import make_id

from .models import (
    ChartPlacement,
    ChartRecord,
    QualityCheck,
    SynastryContact,
    SynastryContext,
    SynastryOverlay,
    SynastryScope,
    SynastrySubject,
    VargaChart,
)


_GRAHA_DRISHTI: dict[str, tuple[tuple[int, str], ...]] = {
    "Sun": ((7, "seventh_drishti"),),
    "Moon": ((7, "seventh_drishti"),),
    "Mars": (
        (4, "mars_fourth_drishti"),
        (7, "seventh_drishti"),
        (8, "mars_eighth_drishti"),
    ),
    "Mercury": ((7, "seventh_drishti"),),
    "Jupiter": (
        (5, "jupiter_fifth_drishti"),
        (7, "seventh_drishti"),
        (9, "jupiter_ninth_drishti"),
    ),
    "Venus": ((7, "seventh_drishti"),),
    "Saturn": (
        (3, "saturn_third_drishti"),
        (7, "seventh_drishti"),
        (10, "saturn_tenth_drishti"),
    ),
}


def build_synastry_context(
    a: ChartRecord,
    b: ChartRecord,
    *,
    b_label: str,
    relationship_type: str,
    current_stage: str,
    question: str,
) -> SynastryContext:
    """Build deterministic cross-chart evidence without producing interpretation."""

    a_d1 = _require_d1(a)
    b_d1 = _require_d1(b)
    checks = _quality_checks(a, b)
    blocked = any(check.status == "failed" for check in checks)

    overlays = [
        *_overlays("A", a_d1, "B", b_d1),
        *_overlays("B", b_d1, "A", a_d1),
    ]
    contacts = [
        *_contacts("A", a_d1, "B", b_d1),
        *_contacts("B", b_d1, "A", a_d1),
    ]
    return SynastryContext(
        synastry_context_id=make_id("synastry"),
        reading_session_id=a.reading_session_id,
        generated_at=datetime.now(timezone.utc),
        method_profile_id=a.calculation_profile.profile_id,
        subjects=[
            SynastrySubject(
                role="A",
                label=a.subject.display_name or "A",
                chart_record_id=a.chart_record_id,
                chart_revision=a.revision,
                subject_id=a.subject.subject_id,
            ),
            SynastrySubject(
                role="B",
                label=b_label or b.subject.display_name or "B",
                chart_record_id=b.chart_record_id,
                chart_revision=b.revision,
                subject_id=b.subject.subject_id,
            ),
        ],
        scope=SynastryScope(
            relationship_type=relationship_type or None,
            current_stage=current_stage or None,
            question=question or None,
        ),
        overlays=overlays,
        contacts=contacts,
        quality_checks=checks,
        limitations=[
            "This context contains deterministic D1 whole-sign overlays and Parashari graha "
            "drishti only; it does not itself make a relationship judgement.",
            "Ashtakoota, Jaimini relationship techniques, composite charts, and Western "
            "degree-based aspects are outside this method profile.",
            "Timing claims require both natal promise and separately validated timing evidence.",
        ],
        status="blocked" if blocked else "ready_for_judgement",
    )


def _require_d1(record: ChartRecord) -> VargaChart:
    chart = next((chart for chart in record.charts if chart.varga_id == "D1"), None)
    if chart is None:
        raise ValueError(f"chart record {record.chart_record_id} has no D1 chart")
    return chart


def _quality_checks(a: ChartRecord, b: ChartRecord) -> list[QualityCheck]:
    same_profile = a.calculation_profile.profile_id == b.calculation_profile.profile_id
    eligible_states = {"ready_for_judgement", "rectified"}
    records_usable = a.status in eligible_states and b.status in eligible_states
    same_session = a.reading_session_id == b.reading_session_id
    return [
        QualityCheck(
            check_id="synastry.method-profile-match",
            status="passed" if same_profile else "failed",
            expected=a.calculation_profile.profile_id,
            observed=b.calculation_profile.profile_id,
            message="Both charts must use the same declared calculation profile.",
        ),
        QualityCheck(
            check_id="synastry.chart-record-status",
            status="passed" if records_usable else "failed",
            expected="A and B are ready_for_judgement or rectified",
            observed=f"A={a.status}; B={b.status}",
            message="Blocked chart records cannot enter relationship judgement.",
        ),
        QualityCheck(
            check_id="synastry.reading-session-link",
            status="passed" if same_session else "failed",
            expected=a.reading_session_id,
            observed=b.reading_session_id,
            message="Both chart records must belong to the active reading session.",
        ),
    ]


def _overlays(
    source_role: Literal["A", "B"],
    source: VargaChart,
    target_role: Literal["A", "B"],
    target: VargaChart,
) -> list[SynastryOverlay]:
    target_lagna = target.lagna.position.sign_index
    placements = [source.lagna, *source.placements]
    return [
        SynastryOverlay(
            overlay_id=f"overlay.{source_role}.{placement.object_id}.to.{target_role}",
            source_role=source_role,
            source_object_id=placement.object_id,
            target_role=target_role,
            target_house=((placement.position.sign_index - target_lagna) % 12) + 1,
            source_sign_index=placement.position.sign_index,
            target_lagna_sign_index=target_lagna,
        )
        for placement in placements
    ]


def _contacts(
    source_role: Literal["A", "B"],
    source: VargaChart,
    target_role: Literal["A", "B"],
    target: VargaChart,
) -> list[SynastryContact]:
    targets = [target.lagna, *target.placements]
    contacts: list[SynastryContact] = []
    for source_placement in source.placements:
        source_sign = source_placement.position.sign_index
        contact_specs = ((1, "conjunction"), *_GRAHA_DRISHTI.get(source_placement.object_id, ()))
        for offset, contact_type in contact_specs:
            expected_sign = (source_sign + offset - 1) % 12
            for target_placement in targets:
                if target_placement.position.sign_index != expected_sign:
                    continue
                contacts.append(
                    SynastryContact(
                        contact_id=(
                            f"contact.{source_role}.{source_placement.object_id}."
                            f"{contact_type}.{target_role}.{target_placement.object_id}"
                        ),
                        source_role=source_role,
                        source_object_id=source_placement.object_id,
                        target_role=target_role,
                        target_object_id=target_placement.object_id,
                        contact_type=contact_type,
                        source_sign_index=source_sign,
                        target_sign_index=target_placement.position.sign_index,
                    )
                )
    return contacts
