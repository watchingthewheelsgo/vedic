from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from pathlib import Path
from types import SimpleNamespace

from app.auth import AuthenticatedUser
from app.db.engine import close_db, init_db
from app.services.creem_billing import CreemBillingService
from app.settings import Settings


def test_creem_webhook_syncs_subscription_and_deduplicates_events(tmp_path: Path) -> None:
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
            payload = {
                "id": "evt_paid_123",
                "eventType": "subscription.paid",
                "created_at": 1728734327355,
                "object": {
                    "id": "sub_123",
                    "object": "subscription",
                    "product": {"id": "prod_monthly"},
                    "customer": {"id": "cust_123", "email": "reader@example.com"},
                    "status": "active",
                    "current_period_start_date": "2026-07-01T00:00:00.000Z",
                    "current_period_end_date": "2026-08-01T00:00:00.000Z",
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
            assert account.entitlement == "paid"
            assert account.has_active_entitlement is True
            assert account.subscription
            assert account.subscription.plan_key == "pro_monthly"
            assert account.subscription.creem_customer_id == "cust_123"
        finally:
            await close_db()

    asyncio.run(run())
