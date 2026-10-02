"""Database-backed feedback inbox with authenticated administrator access."""

import hashlib
from datetime import datetime, timezone
from typing import Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field, ValidationInfo, field_validator
from sqlalchemy import select, update, delete
from sqlalchemy.engine import CursorResult
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.auth import AuthenticatedUser, require_user
from app.db.engine import get_session_factory
from app.db.models import FeedbackRecord, FeedbackRateRecord

router = APIRouter(tags=["feedback"])


class FeedbackInput(BaseModel):
    request_id: UUID
    kind: Literal["feedback", "upgrade"] = "feedback"
    contact: str = Field(min_length=3, max_length=320)
    message: str = Field(min_length=5, max_length=4000)

    @field_validator("contact", "message")
    @classmethod
    def trim(cls, value: str, info: ValidationInfo):
        value = value.strip()
        if len(value) < (5 if info.field_name == "message" else 3):
            raise ValueError("Please provide a contact and message")
        return value


async def optional_user(authorization: str | None = Header(default=None)):
    if authorization:
        return await require_user(authorization=authorization, anonymous_id=None)
    return None


@router.post("/api/feedback", status_code=201)
async def submit_feedback(payload: FeedbackInput, request: Request, user=Depends(optional_user)):
    if payload.kind == "upgrade" and not user:
        raise HTTPException(401, "Sign in to request a membership upgrade.")
    owner = user.user_id if user else None
    # Use the trusted ASGI client address, never a caller-supplied forwarded header.
    sender = owner or (request.client.host if request.client else "unknown")
    key = hashlib.sha256(sender.encode()).hexdigest()
    hour = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
    request_id = str(payload.request_id)
    async with get_session_factory()() as db:
        insert = sqlite_insert if db.bind.dialect.name == "sqlite" else pg_insert
        # One atomic insert doubles as the retry/idempotency gate.
        created = await db.execute(
            insert(FeedbackRecord)
            .values(
                id=request_id,
                owner_user_id=owner,
                sender_key=key,
                kind=payload.kind,
                contact=payload.contact,
                message=payload.message,
                status="open",
            )
            .on_conflict_do_nothing()
        )
        if cast(CursorResult, created).rowcount == 0:
            previous = await db.get(FeedbackRecord, request_id)
            if (
                previous.sender_key != key
                or previous.contact != payload.contact
                or previous.message != payload.message
                or previous.kind != payload.kind
            ):
                raise HTTPException(409, "Please start a new feedback request.")
            return {"id": request_id, "status": "received"}
        limit_key = f"{hour}:{key}"
        await db.execute(
            insert(FeedbackRateRecord).values(key=limit_key, count=0).on_conflict_do_nothing()
        )
        changed = await db.execute(
            update(FeedbackRateRecord)
            .where(FeedbackRateRecord.key == limit_key, FeedbackRateRecord.count < 5)
            .values(count=FeedbackRateRecord.count + 1)
        )
        if cast(CursorResult, changed).rowcount != 1:
            raise HTTPException(429, "Too many requests. Please try again in an hour.")
        await db.execute(delete(FeedbackRateRecord).where(FeedbackRateRecord.key < hour))
        await db.commit()
    return {"id": request_id, "status": "received"}


@router.get("/api/admin/feedback")
async def feedback_inbox(user: AuthenticatedUser = Depends(require_user)):
    if not user.is_clerk or not user.is_admin:
        raise HTTPException(403, "Admin access required")
    async with get_session_factory()() as db:
        records = (
            await db.scalars(
                select(FeedbackRecord).order_by(FeedbackRecord.created_at.desc()).limit(100)
            )
        ).all()
        return {
            "items": [
                {
                    "id": row.id,
                    "kind": row.kind,
                    "contact": row.contact,
                    "message": row.message,
                    "ownerUserId": row.owner_user_id,
                    "status": row.status,
                    "createdAt": row.created_at.isoformat(),
                }
                for row in records
            ]
        }


class FeedbackStatusInput(BaseModel):
    status: Literal["open", "resolved"]


@router.patch("/api/admin/feedback/{feedback_id}")
async def update_feedback(
    feedback_id: UUID, payload: FeedbackStatusInput, user: AuthenticatedUser = Depends(require_user)
):
    if not user.is_clerk or not user.is_admin:
        raise HTTPException(403, "Admin access required")
    async with get_session_factory()() as db:
        row = await db.get(FeedbackRecord, str(feedback_id))
        if row is None:
            raise HTTPException(404, "Feedback not found")
        row.status = payload.status
        await db.commit()
    return {"ok": True}
