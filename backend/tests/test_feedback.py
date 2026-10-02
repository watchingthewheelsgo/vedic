import asyncio
from types import SimpleNamespace
from uuid import uuid4

import httpx
from fastapi import FastAPI
from sqlalchemy import select

from app.auth import AuthenticatedUser, require_user
from app.db.engine import init_db, close_db, get_session_factory
from app.db.models import FeedbackRateRecord
import app.services.feedback as feedback


def test_feedback_receipts_auth_rate_limit_and_admin_inbox(tmp_path):
    app = FastAPI()
    app.include_router(feedback.router)
    user = AuthenticatedUser(user_id="alice", auth_mode="clerk")
    app.dependency_overrides[require_user] = lambda: user

    async def run():
        await init_db(
            SimpleNamespace(
                database_url=f"sqlite+aiosqlite:///{tmp_path / 'feedback.db'}", database_echo=False
            )
        )
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                payload = {
                    "request_id": str(uuid4()),
                    "kind": "feedback",
                    "contact": "WeChat: test-reader",
                    "message": "Please improve the daily calendar.",
                }
                a, b = await asyncio.gather(
                    *(client.post("/api/feedback", json=payload) for _ in range(2))
                )
                assert a.status_code == b.status_code == 201 and a.json() == b.json()
                assert (
                    await client.post(
                        "/api/feedback", json=payload | {"message": "Changed content"}
                    )
                ).status_code == 409
                assert (
                    await client.post(
                        "/api/feedback",
                        json=payload | {"request_id": str(uuid4()), "message": "    "},
                    )
                ).status_code == 422
                assert (
                    await client.post("/api/feedback", json=payload | {"kind": "upgrade"})
                ).status_code == 401
                assert (await client.get("/api/admin/feedback")).status_code == 403
                assert (
                    await client.patch(
                        f"/api/admin/feedback/{payload['request_id']}",
                        json={"status": "resolved"},
                    )
                ).status_code == 403
                app.dependency_overrides.pop(require_user)
                assert (await client.get("/api/admin/feedback")).status_code == 401
                assert (
                    await client.patch(
                        f"/api/admin/feedback/{payload['request_id']}",
                        json={"status": "resolved"},
                    )
                ).status_code == 401
                app.dependency_overrides[require_user] = lambda: AuthenticatedUser(
                    user_id="local", auth_mode="disabled", is_admin=True
                )
                assert (await client.get("/api/admin/feedback")).status_code == 403
                app.dependency_overrides[require_user] = lambda: user
                for _ in range(4):
                    assert (
                        await client.post(
                            "/api/feedback", json=payload | {"request_id": str(uuid4())}
                        )
                    ).status_code == 201
                assert (
                    await client.post("/api/feedback", json=payload | {"request_id": str(uuid4())})
                ).status_code == 429
                app.dependency_overrides[feedback.optional_user] = lambda: user
                upgrade = await client.post(
                    "/api/feedback", json=payload | {"request_id": str(uuid4()), "kind": "upgrade"}
                )
                assert upgrade.status_code == 201
                admin = AuthenticatedUser(user_id="admin", auth_mode="clerk", is_admin=True)
                app.dependency_overrides[require_user] = lambda: admin
                inbox = (await client.get("/api/admin/feedback")).json()["items"]
                assert len(inbox) == 6
                assert any(row["ownerUserId"] == "alice" for row in inbox)
                assert (
                    await client.patch(
                        f"/api/admin/feedback/{upgrade.json()['id']}", json={"status": "resolved"}
                    )
                ).status_code == 200
                updated = (await client.get("/api/admin/feedback")).json()["items"]
                assert (
                    next(row for row in updated if row["id"] == upgrade.json()["id"])["status"]
                    == "resolved"
                )
                assert (
                    await client.patch(
                        f"/api/admin/feedback/{upgrade.json()['id']}", json={"status": "open"}
                    )
                ).status_code == 200
                reopened = (await client.get("/api/admin/feedback")).json()["items"]
                assert (
                    next(row for row in reopened if row["id"] == upgrade.json()["id"])["status"]
                    == "open"
                )
                assert (
                    await client.patch(
                        f"/api/admin/feedback/{uuid4()}", json={"status": "resolved"}
                    )
                ).status_code == 404
                async with get_session_factory()() as db:
                    rates = (await db.scalars(select(FeedbackRateRecord))).all()
                    assert sorted(row.count for row in rates) == [1, 5]
        finally:
            await close_db()

    asyncio.run(run())
