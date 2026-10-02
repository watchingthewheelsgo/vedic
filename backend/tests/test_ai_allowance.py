import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.auth import AuthenticatedUser
from app.db.engine import init_db, close_db, get_session_factory
from app.db.models import AiUsageRecord, ManualMembershipRecord, VedicCoreJobRecord
from app.services.ai_allowance import AiAllowanceService


def run_test(tmp_path, action):
    async def run():
        await init_db(
            SimpleNamespace(
                database_url=f"sqlite+aiosqlite:///{tmp_path / 'quota.db'}", database_echo=False
            )
        )
        try:
            await action(
                AiAllowanceService(), AuthenticatedUser(user_id="alice", auth_mode="clerk")
            )
        finally:
            await close_db()

    asyncio.run(run())


def test_atomic_limit_isolation_and_idempotent_refund(tmp_path):
    async def action(service, user):
        async def reserve():
            try:
                return await service.reserve(user, 1, "question")
            except HTTPException as exc:
                assert exc.status_code == 402
                return None

        results = await asyncio.gather(*(reserve() for _ in range(15)))
        accepted = [item for item in results if item]
        assert len(accepted) == 10
        assert (await service.summary(user))["remaining"] == 0
        bob = AuthenticatedUser(user_id="bob", auth_mode="clerk")
        assert (await service.summary(bob))["remaining"] == 10
        await asyncio.gather(*(service.settle(accepted[0], success=False) for _ in range(3)))
        assert (await service.summary(user))["remaining"] == 1
        await service.settle(accepted[1], success=True)
        await service.settle(accepted[1], success=False)
        assert (await service.summary(user))["used"] == 9

    run_test(tmp_path, action)


def test_failures_and_cancellation_refund_and_month_rolls_over(tmp_path):
    async def action(service, user):
        for exception in (ValueError, asyncio.CancelledError):
            with pytest.raises(exception):
                async with service.charge(user):
                    raise exception()
        assert (await service.summary(user))["used"] == 0
        old = datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc)
        service.now = lambda: old
        ticket = await service.reserve(user, 10, "report")
        service.now = lambda: old + timedelta(minutes=2)
        assert (await service.summary(user))["remaining"] == 10
        await service.settle(ticket, success=False)
        assert (await service.summary(user))["used"] == 0

    run_test(tmp_path, action)


def test_manual_membership_expiry_and_existing_free_usage(tmp_path):
    async def action(service, user):
        ticket = await service.reserve(user, 4, "reading")
        await service.settle(ticket, success=True)
        async with get_session_factory()() as db:
            db.add(
                ManualMembershipRecord(
                    owner_user_id=user.user_id,
                    expires_at=service.now() + timedelta(days=2),
                    monthly_limit=100,
                    note="Test approval",
                )
            )
            await db.commit()
        assert (await service.summary(user))["remaining"] == 96
        async with get_session_factory()() as db:
            record = await db.get(ManualMembershipRecord, user.user_id)
            record.expires_at = service.now() - timedelta(days=1)
            await db.commit()
        assert (await service.summary(user))["remaining"] == 6
        admin = AuthenticatedUser(user_id="admin", auth_mode="clerk", role="admin", is_admin=True)
        assert await service.reserve(admin, 1000, "test") is None

    run_test(tmp_path, action)


def test_durable_core_job_reconciliation(tmp_path):
    async def action(service, user):
        await service.reserve(user, 10, "report", job_id="job-failed")
        async with get_session_factory()() as db:
            db.add(
                VedicCoreJobRecord(
                    job_id="job-failed",
                    session_id="session",
                    owner_user_id=user.user_id,
                    status="failed",
                    message="interrupted",
                )
            )
            await db.commit()
        assert (await service.summary(user))["remaining"] == 10
        await service.reserve(user, 10, "report", job_id="job-ok")
        async with get_session_factory()() as db:
            db.add(
                VedicCoreJobRecord(
                    job_id="job-ok",
                    session_id="session",
                    owner_user_id=user.user_id,
                    status="completed",
                    message="done",
                )
            )
            await db.commit()
        assert (await service.summary(user))["remaining"] == 0
        async with get_session_factory()() as db:
            rows = (await db.scalars(select(AiUsageRecord))).all()
            assert {row.status for row in rows} == {"refunded", "completed"}

    run_test(tmp_path, action)


def test_background_report_charges_once_and_refunds_failure(tmp_path):
    from test_core_job_runtime import FakeSkillRuntime, FakeWorkspace, batch
    from app.services.core_job_runtime import CoreJobRuntime
    from app.schemas import SkillRunInput

    async def action(service, user):
        fake = FakeSkillRuntime(FakeWorkspace(tmp_path / "sessions"), [batch("one", "one.md")])
        runtime = CoreJobRuntime(fake, ai_allowance=service)
        gate = asyncio.Event()
        original = fake.run_core_batch

        async def blocked(*args, **kwargs):
            await gate.wait()
            return await original(*args, **kwargs)

        fake.run_core_batch = blocked
        payload = SkillRunInput(sessionId="owned", skill="vedic-core", userMessage="Report")
        first = await runtime.start(payload, owner_user_id=user.user_id, user=user)
        repeated = await runtime.start(payload, owner_user_id=user.user_id, user=user)
        assert repeated.job_id == first.job_id
        assert (await service.summary(user))["used"] == 10
        gate.set()
        await runtime._jobs[first.job_id].task
        assert (await service.summary(user))["used"] == 10
        with pytest.raises(HTTPException) as error:
            await runtime.start(
                payload.model_copy(update={"session_id": "another"}),
                owner_user_id=user.user_id,
                user=user,
            )
        assert error.value.status_code == 402

        bob = AuthenticatedUser(user_id="bob", auth_mode="clerk")

        async def fail(*args, **kwargs):
            raise RuntimeError("model unavailable")

        fake.run_core_batch = fail
        failed = await runtime.start(
            payload.model_copy(update={"session_id": "bob-chart"}),
            owner_user_id=bob.user_id,
            user=bob,
        )
        await runtime._jobs[failed.job_id].task
        assert (await runtime.get(failed.job_id, owner_user_id=bob.user_id)).status == "failed"
        assert (await service.summary(bob))["remaining"] == 10

    run_test(tmp_path, action)
