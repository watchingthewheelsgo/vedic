"""The account owner's birth profile: collected once, used for the daily card, Good for /
Avoid, auspicious days and Atlas, and to prefill new readings. No chart session is
created; readings stay something the user starts on purpose."""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from app.auth import AuthenticatedUser, require_user
from app.db.engine import get_session_factory
from app.db.models import UserProfileRecord
from app.services.daily_journal import timezone_for

router = APIRouter(prefix="/api/me/profile", tags=["profile"])


class ProfileInput(BaseModel):
    birth_date: date = Field(alias="birthDate")
    birth_time: str = Field(default="", alias="birthTime", max_length=5)
    birth_place: str = Field(alias="birthPlace", min_length=2, max_length=300)
    place_label: str = Field(alias="placeLabel", min_length=1, max_length=200)
    timezone: str = Field(max_length=80)
    gender: Literal["女", "男"]

    model_config = {"populate_by_name": True}

    @field_validator("birth_date")
    @classmethod
    def plausible_date(cls, value: date) -> date:
        if not date(1901, 1, 1) <= value <= date.today():
            raise ValueError("Birth date must be between 1901 and today")
        return value

    @field_validator("birth_time")
    @classmethod
    def clock_time(cls, value: str) -> str:
        value = value.strip()
        if value and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("Birth time must be HH:MM")
        return value

    @field_validator("timezone")
    @classmethod
    def known_zone(cls, value: str) -> str:
        timezone_for(value)
        return value


def project(record: UserProfileRecord) -> dict[str, Any]:
    return {
        "birthDate": record.birth_date,
        "birthTime": record.birth_time,
        "birthPlace": record.birth_place,
        "placeLabel": record.place_label,
        "timezone": record.timezone,
        "gender": record.gender,
    }


async def load_profile(owner_user_id: str | None) -> dict[str, Any] | None:
    if not owner_user_id:
        return None
    async with get_session_factory()() as db:
        record = await db.get(UserProfileRecord, owner_user_id)
        return project(record) if record else None


@router.get("")
async def read_profile(user: AuthenticatedUser = Depends(require_user)) -> dict:
    from app.container import get_container
    from app.services.daily_guidance import resolve_natal

    profile = await load_profile(user.owner_user_id)
    natal = await resolve_natal(get_container(), user.owner_user_id)
    return {"profile": profile, "natalAvailable": natal is not None}


@router.put("")
async def save_profile(
    payload: ProfileInput, user: AuthenticatedUser = Depends(require_user)
) -> dict:
    if not user.owner_user_id:
        raise HTTPException(401, "Sign in to continue")
    async with get_session_factory()() as db:
        record = await db.scalar(
            select(UserProfileRecord).where(UserProfileRecord.owner_user_id == user.owner_user_id)
        )
        if record is None:
            record = UserProfileRecord(owner_user_id=user.owner_user_id)
            db.add(record)
        record.birth_date = payload.birth_date.isoformat()
        record.birth_time = payload.birth_time or None
        record.birth_place = payload.birth_place.strip()
        record.place_label = payload.place_label.strip()
        record.timezone = payload.timezone
        record.gender = payload.gender
        await db.commit()
        await db.refresh(record)
        return {"profile": project(record), "natalAvailable": True}
