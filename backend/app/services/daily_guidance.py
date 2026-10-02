"""Personal BaZi day guidance for the signed-in user. Facts are deterministic; no LLM."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import AuthenticatedUser, require_user
from app.services.daily_journal import calendar_day, timezone_for
from app.tools.bazi.calculate_chart import BaziInput, calculate_bazi
from app.tools.bazi.daily_guidance import evaluate_day, natal_from_bazi_record

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/me/daily-guidance", tags=["journal"])

# Bound file reads per request: only the most recently updated owned sessions are inspected.
MAX_SESSIONS_SCANNED = 12
EXACT_TIME_CERTAINTY = {"documented", "reported_exact", "rectified"}
VEDIC_PRECISION = {"approximate": "approximate", "broad_window": "part_of_day"}
REASON_NO_BIRTH_DETAILS = "no_birth_details"


def _read_json(container: Any, session_id: str, path: str) -> dict[str, Any] | None:
    try:
        raw = container.skill_workspace.read_artifact_text(session_id, path)
    except (LookupError, FileNotFoundError, PermissionError, ValueError):
        return None
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def natal_from_vedic_record(record: dict[str, Any], session_id: str) -> dict[str, Any] | None:
    """Compute natal pillars from a self-reader Vedic Chart Record via ``bazi-calculator``.

    Uses the canonical civil local birth time (active revision, so a confirmed rectification
    applies) and the same civil-time policy as BaZi sessions: no true solar time.
    """
    subject = record.get("subject") or {}
    assertion = record.get("birthAssertion") or {}
    moment = record.get("canonicalMoment") or {}
    if subject.get("readerRelationship") != "self":
        return None
    local = str(moment.get("localDatetime") or "")
    birth_date = local[:10] or str(assertion.get("localDate") or "")
    birth_time = (
        local[11:16] if len(local) >= 16 else str(assertion.get("reportedLocalTime") or "")[:5]
    )
    if not birth_date:
        return None
    certainty = str(assertion.get("timeCertainty") or "unknown")
    if certainty in EXACT_TIME_CERTAINTY:
        precision = "exact"
    else:
        precision = VEDIC_PRECISION.get(certainty, "unknown")
    if not birth_time:
        precision = "unknown"
    payload = calculate_bazi(
        BaziInput(
            birth_date=date.fromisoformat(birth_date),
            birth_time=birth_time,
            birth_place=str(assertion.get("reportedPlace") or "[not provided]"),
            gender=str(subject.get("genderContext") or "未提供"),
            calendar_type="solar",
            time_precision=precision,
            timezone_name=str(moment.get("timezoneId") or "UTC"),
            latitude=None,
            longitude=None,
            current_date=date.today(),
            audience="self",
            relationship="[not provided]",
            topic="[not provided]",
            day_boundary_sect=2,
            luck_sect=2,
            solar_time_policy="civil",
        )
    )
    return {
        **natal_from_bazi_record(payload),
        "source": "vedic_chart_record",
        "sessionId": session_id,
    }


async def resolve_natal(container: Any, owner_user_id: str | None) -> dict[str, Any] | None:
    """Prefer the newest self BaZi Chart Record; else derive from the newest self Vedic chart."""
    summaries = await container.metadata_store.list_session_summaries(owner_user_id)
    bazi = [item for item in summaries if str(item.stage).startswith("bazi")]
    vedic = [item for item in summaries if not str(item.stage).startswith("bazi")]
    for summary in bazi[:MAX_SESSIONS_SCANNED]:
        record = _read_json(container, summary.session_id, "bazi_chart_record.json")
        if not record or (record.get("reportContext") or {}).get("audience") != "self":
            continue
        try:
            natal = natal_from_bazi_record(record)
        except (KeyError, TypeError):
            continue
        return {**natal, "source": "bazi_chart_record", "sessionId": summary.session_id}
    for summary in vedic[:MAX_SESSIONS_SCANNED]:
        if summary.subject is None:
            continue
        record = _read_json(container, summary.session_id, "chart_record.json")
        if not record:
            continue
        try:
            natal = natal_from_vedic_record(record, summary.session_id)
        except (ValueError, KeyError, TypeError):
            logger.warning("daily guidance natal calc failed session_id=%s", summary.session_id)
            continue
        if natal:
            return natal
    return None


def build_guidance(natal: dict[str, Any] | None, calendar: dict[str, Any]) -> dict[str, Any]:
    if natal is None:
        return {"calendar": calendar, "guidance": None, "reason": REASON_NO_BIRTH_DETAILS}
    result = evaluate_day(natal, calendar["pillar"])
    result["natal"] = {
        "source": natal["source"],
        "sessionId": natal["sessionId"],
        "dayMaster": natal["dayMaster"],
        "dayMasterElement": natal.get("dayMasterElement"),
        "pillars": natal["pillars"],
        "warnings": natal.get("warnings", []),
    }
    return {"calendar": calendar, "guidance": result, "reason": None}


@router.get("")
async def read_daily_guidance(
    day: date | None = Query(default=None),
    timezone: str = Query(default="Asia/Shanghai", max_length=80),
    user: AuthenticatedUser = Depends(require_user),
) -> dict:
    from app.container import get_container

    try:
        zone = timezone_for(timezone)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    target = day or datetime.now(zone).date()
    if not 1901 <= target.year <= 2099:
        raise HTTPException(422, "Day must be between 1901 and 2099")
    natal = await resolve_natal(get_container(), user.owner_user_id)
    return build_guidance(natal, calendar_day(target, timezone))
