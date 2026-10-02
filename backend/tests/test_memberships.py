import asyncio
from types import SimpleNamespace
from uuid import uuid4
import httpx
from fastapi import FastAPI
from app.auth import AuthenticatedUser, require_user
from app.db.engine import init_db, close_db, get_session_factory
from app.db.models import AppUserRecord
from app.services.memberships import router
from app.services.ai_allowance import AiAllowanceService


def test_admin_membership_lifecycle_and_idempotency(tmp_path):
    api = FastAPI()
    api.include_router(router)
    user = AuthenticatedUser(user_id="alice", auth_mode="clerk")
    admin = AuthenticatedUser(user_id="admin", auth_mode="clerk", is_admin=True)
    api.dependency_overrides[require_user] = lambda: user

    async def run():
        await init_db(
            SimpleNamespace(
                database_url=f"sqlite+aiosqlite:///{tmp_path / 'members.db'}", database_echo=False
            )
        )
        try:
            async with get_session_factory()() as db:
                db.add(AppUserRecord(clerk_user_id="alice", role="user"))
                await db.commit()
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=api), base_url="http://test"
            ) as client:
                url = "/api/admin/memberships/alice"
                data = {
                    "request_id": str(uuid4()),
                    "action": "grant",
                    "days": 30,
                    "monthly_limit": 100,
                    "note": "Verified request",
                }
                assert (await client.get(url)).status_code == 403
                assert (await client.post(url, json=data)).status_code == 403
                api.dependency_overrides[require_user] = lambda: admin
                assert (
                    await client.post("/api/admin/memberships/unknown", json=data)
                ).status_code == 404
                quota = AiAllowanceService()
                reservation = await quota.reserve(user, 1, "test")
                await quota.settle(reservation, success=True)
                assert (await client.post(url, json=data)).status_code == 200
                assert (await quota.summary(user))["remaining"] == 99
                first = (await client.get(url)).json()
                assert first["active"] and len(first["history"]) == 1
                assert (await client.post(url, json=data)).status_code == 200
                assert (await client.post(url, json=data | {"days": 31})).status_code == 409
                assert (
                    await client.post(url, json=data | {"request_id": str(uuid4())})
                ).status_code == 409
                renewal = data | {"request_id": str(uuid4()), "action": "renew"}
                responses = await asyncio.gather(
                    *(client.post(url, json=renewal) for _ in range(2))
                )
                assert all(r.status_code == 200 for r in responses)
                second = (await client.get(url)).json()
                from datetime import datetime, timedelta

                assert datetime.fromisoformat(second["expiresAt"]) - datetime.fromisoformat(
                    first["expiresAt"]
                ) == timedelta(days=30)
                assert len(second["history"]) == 2
                assert second["history"][0]["actor"] == "admin"
                assert (
                    await client.post(
                        url, json=data | {"request_id": str(uuid4()), "action": "revoke"}
                    )
                ).status_code == 200
                assert not (await client.get(url)).json()["active"]
                assert (await quota.summary(user))["remaining"] == 9
                assert (
                    await client.post(url, json=data | {"request_id": str(uuid4()), "days": 0})
                ).status_code == 422
                assert (
                    await client.post(url, json=data | {"request_id": str(uuid4()), "note": " "})
                ).status_code == 422
        finally:
            await close_db()

    asyncio.run(run())
