"""Server-owned monthly credits, independent of unlaunched payment providers."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import cast
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.auth import AuthenticatedUser
from app.db.engine import get_session_factory
from app.db.models import (
    AiAllowanceRecord,
    AiUsageRecord,
    ManualMembershipRecord,
    VedicCoreJobRecord,
)

SUPPORT_EMAIL = "lizero.why@gmail.com"
FREE_LIMIT = 10
MEMBER_LIMIT = 100
REPORT_COST = 10


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class AiAllowanceService:
    def now(self):
        return datetime.now(timezone.utc)

    async def summary(self, user: AuthenticatedUser) -> dict:
        await self.reconcile(user.owner_user_id)
        now = self.now()
        period = now.strftime("%Y-%m")
        async with get_session_factory()() as db:
            membership = await db.get(ManualMembershipRecord, user.owner_user_id)
            active = bool(membership and utc(membership.expires_at) > now)
            limit = membership.monthly_limit if active else FREE_LIMIT
            row = await db.get(AiAllowanceRecord, (user.owner_user_id, period))
            used = row.used if row else 0
        resets = (now.replace(day=1) + timedelta(days=32)).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        return {
            "period": period,
            "plan": "admin" if user.is_admin else "member" if active else "free",
            "limit": limit,
            "used": used,
            "remaining": max(0, limit - used),
            "unlimited": user.is_admin,
            "resetsAt": resets.isoformat(),
            "expiresAt": utc(membership.expires_at).isoformat() if active else None,
            "supportEmail": SUPPORT_EMAIL,
            "standardCost": 1,
            "reportCost": REPORT_COST,
        }

    async def reserve(self, user: AuthenticatedUser, units: int, operation: str, *, job_id=None):
        if not user.owner_user_id:
            raise HTTPException(401, "Sign in to use AI.")
        if user.is_admin:
            return None
        if units <= 0:
            raise ValueError("AI credit cost must be positive")
        account = await self.summary(user)
        period = account["period"]
        async with get_session_factory()() as db:
            insert = sqlite_insert if db.bind.dialect.name == "sqlite" else pg_insert
            await db.execute(
                insert(AiAllowanceRecord)
                .values(owner_user_id=user.owner_user_id, period=period, used=0)
                .on_conflict_do_nothing()
            )
            changed = await db.execute(
                update(AiAllowanceRecord)
                .where(
                    AiAllowanceRecord.owner_user_id == user.owner_user_id,
                    AiAllowanceRecord.period == period,
                    AiAllowanceRecord.used + units <= account["limit"],
                )
                .values(used=AiAllowanceRecord.used + units)
            )
            if cast(CursorResult, changed).rowcount != 1:
                raise HTTPException(
                    402,
                    {
                        "code": "ai_allowance_exhausted",
                        "message": "Not enough AI credits. Your records and existing content remain available.",
                        "required": units,
                        "supportEmail": SUPPORT_EMAIL,
                    },
                )
            reservation = uuid4().hex
            db.add(
                AiUsageRecord(
                    id=reservation,
                    owner_user_id=user.owner_user_id,
                    period=period,
                    operation=operation,
                    units=units,
                    status="reserved",
                    job_id=job_id,
                )
            )
            await db.commit()
            return reservation

    async def settle(self, reservation: str | None, *, success: bool):
        if not reservation:
            return
        async with get_session_factory()() as db:
            row = await db.get(AiUsageRecord, reservation)
            if not row:
                return
            changed = await db.execute(
                update(AiUsageRecord)
                .where(AiUsageRecord.id == reservation, AiUsageRecord.status == "reserved")
                .values(status="completed" if success else "refunded")
            )
            if cast(CursorResult, changed).rowcount == 1 and not success:
                await db.execute(
                    update(AiAllowanceRecord)
                    .where(
                        AiAllowanceRecord.owner_user_id == row.owner_user_id,
                        AiAllowanceRecord.period == row.period,
                    )
                    .values(used=AiAllowanceRecord.used - row.units)
                )
            await db.commit()

    async def reconcile(self, owner_user_id):
        # Terminal durable jobs settle even after an interrupted API process.
        async with get_session_factory()() as db:
            rows = (
                await db.scalars(
                    select(AiUsageRecord).where(
                        AiUsageRecord.owner_user_id == owner_user_id,
                        AiUsageRecord.status == "reserved",
                    )
                )
            ).all()
            outcomes = []
            for row in rows:
                job = (
                    await db.scalar(
                        select(VedicCoreJobRecord).where(VedicCoreJobRecord.job_id == row.job_id)
                    )
                    if row.job_id
                    else None
                )
                if job and job.status in {"completed", "failed", "interrupted"}:
                    outcomes.append((row.id, job.status == "completed"))
                elif not job and utc(row.created_at) < self.now() - timedelta(hours=24):
                    outcomes.append((row.id, False))
        for reservation, success in outcomes:
            await self.settle(reservation, success=success)

    @asynccontextmanager
    async def charge(self, user, units=1, operation="reflection"):
        reservation = await self.reserve(user, units, operation)
        try:
            yield
        except BaseException:
            await self.settle(reservation, success=False)
            raise
        else:
            await self.settle(reservation, success=True)
