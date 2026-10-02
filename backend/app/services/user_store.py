from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.auth import AuthenticatedUser
from app.db.engine import get_session_factory
from app.db.models import AppUserRecord
from app.schemas import AccountProfileResponse


class UserStore:
    """Local user profile and authorization projection for Clerk identities."""

    def _session(self):
        return get_session_factory()()

    async def upsert_from_auth_user(self, user: AuthenticatedUser) -> AuthenticatedUser:
        if not user.is_clerk:
            return user

        now = datetime.now(timezone.utc)
        async with self._session() as db:
            insert = sqlite_insert if db.bind.dialect.name == "sqlite" else pg_insert
            await db.execute(
                insert(AppUserRecord)
                .values(clerk_user_id=user.user_id, email=user.email, role="user", created_at=now)
                .on_conflict_do_nothing(index_elements=["clerk_user_id"])
            )
            result = await db.execute(
                select(AppUserRecord).where(AppUserRecord.clerk_user_id == user.user_id)
            )
            record = result.scalar_one()
            record.email = user.email or record.email
            record.last_seen_at = now
            record.updated_at = now
            await db.commit()
            await db.refresh(record)

        role = normalize_role(record.role)
        return AuthenticatedUser(
            user_id=user.user_id,
            auth_mode=user.auth_mode,
            anonymous_user_id=user.anonymous_user_id,
            email=record.email or user.email,
            role=role,
            is_admin=is_admin_role(role),
        )

    async def profile_for(self, user: AuthenticatedUser) -> AccountProfileResponse:
        synced = await self.upsert_from_auth_user(user)
        return AccountProfileResponse(
            userId=synced.user_id,
            authMode=synced.auth_mode,
            email=synced.email,
            role=synced.role,
            isAdmin=synced.is_admin,
            anonymousUserId=synced.anonymous_user_id,
        )


def normalize_role(value: str | None) -> str:
    role = (value or "user").strip().lower()
    return role or "user"


def is_admin_role(role: str | None) -> bool:
    return role == "admin"
