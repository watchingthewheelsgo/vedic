from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pytz


@dataclass(frozen=True)
class CivilTimeChoice:
    utc_offset_seconds: int
    local_datetime: datetime
    utc_datetime: datetime

    def as_payload(self) -> dict[str, object]:
        return {
            "utcOffsetSeconds": self.utc_offset_seconds,
            "localDatetime": self.local_datetime.isoformat(),
            "utcDatetime": self.utc_datetime.isoformat(),
        }


class AmbiguousCivilTimeError(ValueError):
    def __init__(self, naive_datetime: datetime, timezone_id: str, choices: list[CivilTimeChoice]):
        self.naive_datetime = naive_datetime
        self.timezone_id = timezone_id
        self.choices = choices
        super().__init__(
            f"Birth time {naive_datetime.isoformat()} is ambiguous in {timezone_id}; "
            "choose which occurrence matches the birth record."
        )

    def api_detail(self) -> dict[str, object]:
        return {
            "code": "ambiguous_birth_time",
            "message": str(self),
            "timezoneId": self.timezone_id,
            "localDatetime": self.naive_datetime.isoformat(),
            "choices": [choice.as_payload() for choice in self.choices],
        }


def resolve_civil_time(
    naive_datetime: datetime,
    timezone_id: str,
    *,
    utc_offset_seconds: int | None = None,
) -> datetime:
    """Resolve a wall-clock time without silently choosing a DST fold.

    The optional offset is used only to distinguish duplicated civil times. For
    ordinary moments, an inconsistent supplied offset is rejected so the input
    cannot claim one instant while the IANA timezone resolves another.
    """

    if naive_datetime.tzinfo is not None:
        raise ValueError("civil time resolver requires a naive local datetime")
    timezone = pytz.timezone(timezone_id)
    try:
        resolved = timezone.localize(naive_datetime, is_dst=None)
    except pytz.AmbiguousTimeError as exc:
        choices = _ambiguous_choices(timezone, naive_datetime)
        if utc_offset_seconds is None:
            raise AmbiguousCivilTimeError(naive_datetime, timezone_id, choices) from exc
        matching = [
            choice.local_datetime
            for choice in choices
            if choice.utc_offset_seconds == utc_offset_seconds
        ]
        if len(matching) != 1:
            valid = ", ".join(_format_offset(choice.utc_offset_seconds) for choice in choices)
            raise ValueError(
                f"UTC offset {_format_offset(utc_offset_seconds)} does not identify an occurrence "
                f"of {naive_datetime.isoformat()} in {timezone_id}; expected one of {valid}."
            ) from exc
        return matching[0]
    except pytz.NonExistentTimeError as exc:
        raise ValueError(
            f"Birth time {naive_datetime.isoformat()} does not exist in {timezone_id} "
            "because of a civil-time transition."
        ) from exc

    resolved_offset = int(resolved.utcoffset().total_seconds())
    if utc_offset_seconds is not None and utc_offset_seconds != resolved_offset:
        raise ValueError(
            f"UTC offset {_format_offset(utc_offset_seconds)} conflicts with {timezone_id} at "
            f"{naive_datetime.isoformat()}; expected {_format_offset(resolved_offset)}."
        )
    return resolved


def _ambiguous_choices(timezone, naive_datetime: datetime) -> list[CivilTimeChoice]:
    choices: dict[int, CivilTimeChoice] = {}
    for is_dst in (True, False):
        localized = timezone.localize(naive_datetime, is_dst=is_dst)
        offset = int(localized.utcoffset().total_seconds())
        choices[offset] = CivilTimeChoice(
            utc_offset_seconds=offset,
            local_datetime=localized,
            utc_datetime=localized.astimezone(pytz.utc),
        )
    return sorted(choices.values(), key=lambda choice: choice.utc_datetime)


def _format_offset(seconds: int) -> str:
    sign = "+" if seconds >= 0 else "-"
    total = abs(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, seconds_part = divmod(remainder, 60)
    suffix = f":{seconds_part:02d}" if seconds_part else ""
    return f"UTC{sign}{hours:02d}:{minutes:02d}{suffix}"
