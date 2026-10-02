"""Admin-only membership actions. Never charge a payment provider."""

from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from app.auth import AuthenticatedUser, require_user
from app.db.engine import get_session_factory
from app.db.models import AppUserRecord, ManualMembershipRecord, MembershipAuditRecord
from app.services.ai_allowance import utc

router = APIRouter(prefix="/api/admin/memberships", tags=["memberships"])


def check_admin(user):
    if not user.is_clerk or not user.is_admin:
        raise HTTPException(403, "Admin access required")


def snapshot(row):
    return {
        "expiresAt": utc(row.expires_at).isoformat() if row else None,
        "monthlyLimit": row.monthly_limit if row else 10,
    }


class MembershipAction(BaseModel):
    request_id: UUID
    action: Literal["grant", "renew", "revoke"]
    days: int = Field(default=30, ge=1, le=366)
    monthly_limit: int = Field(default=100, ge=10, le=10000)
    note: str = Field(min_length=1, max_length=500)


@router.get("/{user_id}")
async def read_membership(user_id: str, admin: AuthenticatedUser = Depends(require_user)):
    check_admin(admin)
    async with get_session_factory()() as db:
        user = await db.scalar(select(AppUserRecord).where(AppUserRecord.clerk_user_id == user_id))
        if not user:
            raise HTTPException(404, "用户不存在，请先让该账号登录网站。")
        row = await db.get(ManualMembershipRecord, user_id)
        audits = (
            await db.scalars(
                select(MembershipAuditRecord)
                .where(MembershipAuditRecord.owner_user_id == user_id)
                .order_by(MembershipAuditRecord.created_at.desc())
                .limit(20)
            )
        ).all()
        return {
            "userId": user_id,
            "email": user.email,
            "role": user.role,
            "active": bool(row and utc(row.expires_at) > datetime.now(timezone.utc)),
            **snapshot(row),
            "history": [
                {
                    "id": a.id,
                    "actor": a.actor_user_id,
                    "action": a.action,
                    "note": a.request["note"],
                    "createdAt": utc(a.created_at).isoformat(),
                    "before": a.before,
                    "after": a.after,
                }
                for a in audits
            ],
        }


@router.post("/{user_id}")
async def change_membership(
    user_id: str, payload: MembershipAction, admin: AuthenticatedUser = Depends(require_user)
):
    check_admin(admin)
    if not payload.note.strip():
        raise HTTPException(422, "请填写操作备注。")
    data = payload.model_dump(mode="json")
    now = datetime.now(timezone.utc)
    async with get_session_factory()() as db:
        # Serialize changes to the same account on PostgreSQL and SQLite.
        result = await db.execute(
            update(AppUserRecord)
            .where(AppUserRecord.clerk_user_id == user_id)
            .values(updated_at=AppUserRecord.updated_at)
            .returning(AppUserRecord.id)
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(404, "用户不存在，请先让该账号登录网站。")
        previous = await db.get(MembershipAuditRecord, str(payload.request_id))
        if previous:
            if (
                previous.owner_user_id != user_id
                or previous.actor_user_id != admin.user_id
                or previous.request != data
            ):
                raise HTTPException(409, "操作编号冲突，请刷新重试。")
            return {"ok": True}
        row = await db.get(ManualMembershipRecord, user_id)
        before = snapshot(row)
        active = bool(row and utc(row.expires_at) > now)
        if payload.action == "grant" and active:
            raise HTTPException(409, "该用户已经是会员，请选择续期。")
        if payload.action == "revoke":
            if not active:
                raise HTTPException(409, "该用户当前不是有效会员。")
            row.expires_at = now
        else:
            base = utc(row.expires_at) if active and payload.action == "renew" else now
            if row is None:
                row = ManualMembershipRecord(owner_user_id=user_id)
                db.add(row)
            row.expires_at = base + timedelta(days=payload.days)
            row.monthly_limit = payload.monthly_limit
        row.note = payload.note.strip()
        db.add(
            MembershipAuditRecord(
                id=str(payload.request_id),
                owner_user_id=user_id,
                actor_user_id=admin.user_id,
                action=payload.action,
                request=data,
                before=before,
                after=snapshot(row),
                created_at=now,
            )
        )
        await db.commit()
    return {"ok": True}
