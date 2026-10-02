from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.auth import AuthenticatedUser
from app.db.engine import close_db, init_db
from app.services.creem_billing import CreemBillingService
from app.settings import Settings


@pytest.mark.parametrize("period_end_days", [30, -1])
def test_creem_webhook_syncs_subscription_and_deduplicates_events(
    tmp_path: Path, period_end_days: int
) -> None:
    async def run() -> None:
        await init_db(
            SimpleNamespace(
                database_url=f"sqlite+aiosqlite:///{tmp_path / 'vedic.db'}",
                database_echo=False,
            )
        )
        try:
            settings = Settings(
                _env_file=None,
                CREEM_WEBHOOK_SECRET="whsec_test",
                CREEM_PRODUCT_PRO_MONTHLY="prod_monthly",
            )
            service = CreemBillingService(settings)
            now = datetime.now(timezone.utc)
            payload = {
                "id": "evt_paid_123",
                "eventType": "subscription.paid",
                "created_at": int(now.timestamp() * 1000),
                "object": {
                    "id": "sub_123",
                    "object": "subscription",
                    "product": {"id": "prod_monthly"},
                    "customer": {"id": "cust_123", "email": "reader@example.com"},
                    "status": "active",
                    "current_period_start_date": (now - timedelta(days=31)).isoformat(),
                    "current_period_end_date": (now + timedelta(days=period_end_days)).isoformat(),
                    "metadata": {
                        "clerk_user_id": "user_123",
                        "plan_key": "pro_monthly",
                    },
                },
            }
            raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            signature = hmac.new(b"whsec_test", raw_body, hashlib.sha256).hexdigest()

            result = await service.handle_webhook(raw_body, signature)
            duplicate = await service.handle_webhook(raw_body, signature)
            account = await service.account_for_user(
                AuthenticatedUser(user_id="user_123", auth_mode="clerk")
            )

            assert result.processed is True
            assert result.duplicate is False
            assert result.owner_user_id == "user_123"
            assert duplicate.processed is False
            assert duplicate.duplicate is True
            assert account.entitlement == ("paid" if period_end_days > 0 else "free")
            assert account.has_active_entitlement is (period_end_days > 0)
            assert account.subscription
            assert account.subscription.plan_key == "pro_monthly"
            assert account.subscription.creem_customer_id == "cust_123"
        finally:
            await close_db()

    asyncio.run(run())
