from __future__ import annotations

from datetime import datetime, timedelta, timezone


EVENT_TIMEZONE_BASIS = "unknown_event_location_utc_offset_envelope"
MIN_EVENT_UTC_OFFSET_HOURS = -12
MAX_EVENT_UTC_OFFSET_HOURS = 14


def event_utc_envelope(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    """Return every UTC instant represented by a civil interval of unknown location."""

    if start.tzinfo is not None or end.tzinfo is not None:
        raise ValueError("event civil interval must be timezone-naive")
    if start > end:
        raise ValueError("event civil interval start must not be after its end")
    earliest = start.replace(
        tzinfo=timezone(timedelta(hours=MAX_EVENT_UTC_OFFSET_HOURS))
    ).astimezone(timezone.utc)
    latest = end.replace(tzinfo=timezone(timedelta(hours=MIN_EVENT_UTC_OFFSET_HOURS))).astimezone(
        timezone.utc
    )
    return earliest, latest


def event_utc_sample_envelope(value: datetime) -> tuple[datetime, datetime]:
    """Return the earliest and latest UTC interpretations of one civil sample."""

    return event_utc_envelope(value, value)
