import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.auth import AuthenticatedUser
from app.schemas import BillingCheckoutInput, SkillRunInput, ConsultationQuestionInput
from app.services.ai_allowance import AiAllowanceService
from app.db.engine import init_db, close_db
import app.main as routes


def test_access_and_quota_are_independent_of_payment_configuration(monkeypatch, tmp_path):
    async def run():
        await init_db(
            SimpleNamespace(
                database_url=f"sqlite+aiosqlite:///{tmp_path / 'api.db'}", database_echo=False
            )
        )
        user = AuthenticatedUser(user_id="alice", auth_mode="clerk")
        access = AsyncMock()
        runtime = SimpleNamespace(
            run_skill=AsyncMock(return_value="generated"),
            answer_consultation_question=AsyncMock(return_value="answer"),
            get_consultation_conversation=lambda _: "saved conversation",
        )
        allowance = AiAllowanceService()
        container = SimpleNamespace(
            ai_allowance=allowance,
            metadata_store=SimpleNamespace(assert_session_access=access),
            skill_runtime=runtime,
        )
        monkeypatch.setattr(routes, "get_container", lambda: container)
        monkeypatch.setattr(routes, "_sync_account_user", AsyncMock(return_value=user))
        try:
            request = SkillRunInput(sessionId="owned", skill="vedic-reader", userMessage="read")
            assert await routes.run_skill(request, user) == "generated"
            assert (await allowance.summary(user))["used"] == 1
            access.side_effect = PermissionError("Not your session")
            with pytest.raises(HTTPException) as error:
                await routes.run_skill(request, user)
            assert error.value.status_code == 403
            assert runtime.run_skill.await_count == 1
            assert (await allowance.summary(user))["used"] == 1
            access.side_effect = None
            ticket = await allowance.reserve(user, 9, "exhaust")
            await allowance.settle(ticket, success=True)
            with pytest.raises(HTTPException) as error:
                await routes.answer_consultation_question(
                    ConsultationQuestionInput(sessionId="owned", question="What next?"), user
                )
            assert error.value.status_code == 402
            runtime.answer_consultation_question.assert_not_awaited()
            assert await routes.get_consultation_conversation("owned", user) == "saved conversation"
            account = await routes.get_billing_account(user)
            assert account.provider == "manual" and account.ai_allowance["remaining"] == 0
            with pytest.raises(HTTPException) as error:
                await routes.create_billing_checkout(
                    BillingCheckoutInput(planKey="pro_monthly"), user
                )
            assert error.value.status_code == 409
        finally:
            await close_db()

    asyncio.run(run())
