from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import secrets
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthenticatedUser
from app.db.engine import get_session_factory
from app.db.models import BillingCheckoutRecord, BillingEventRecord, UserSubscriptionRecord
from app.schemas import (
    BillingAccountResponse,
    BillingCheckoutInput,
    BillingCheckoutResponse,
    BillingPlanKey,
    BillingPlanResponse,
    BillingPortalResponse,
    BillingSubscriptionResponse,
    CreemWebhookResponse,
)
from app.settings import Settings


ACTIVE_SUBSCRIPTION_STATUSES = {"active", "trialing", "scheduled_cancel", "paid"}
TERMINAL_EVENT_STATUS = {
    "subscription.canceled": "canceled",
    "subscription.expired": "expired",
    "subscription.paused": "paused",
    "subscription.past_due": "past_due",
    "refund.created": "refunded",
    "dispute.created": "disputed",
}


@dataclass(frozen=True)
class BillingPlan:
    key: BillingPlanKey
    name: str
    billing_period: str
    product_id: str


class CreemBillingService:
    """Creem payment integration with local entitlement projection.

    Clerk remains the identity source. Creem remains the payment provider. This
    service stores only the metadata needed to decide access locally.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _session(self):
        return get_session_factory()()

    def plans(self) -> list[BillingPlan]:
        product_ids = self.settings.creem_product_ids_by_plan()
        return [
            BillingPlan(
                key="pro_monthly",
                name="Pro monthly",
                billing_period="monthly",
                product_id=product_ids.get("pro_monthly", "").strip(),
            ),
            BillingPlan(
                key="pro_yearly",
                name="Pro yearly",
                billing_period="yearly",
                product_id=product_ids.get("pro_yearly", "").strip(),
            ),
            BillingPlan(
                key="single_report",
                name="Single report",
                billing_period="one_time",
                product_id=product_ids.get("single_report", "").strip(),
            ),
        ]

    async def account_for_user(self, user: AuthenticatedUser) -> BillingAccountResponse:
        subscription = await self.current_subscription(user.owner_user_id)
        entitlement = "admin" if user.is_admin else "paid" if _is_active(subscription) else "free"
        return BillingAccountResponse(
            configured=self.is_configured(),
            testMode=self.settings.creem_test_mode,
            entitlement=entitlement,
            hasActiveEntitlement=entitlement in {"admin", "paid"},
            canManageBilling=bool(subscription and subscription.creem_customer_id),
            subscription=_subscription_response(subscription),
            plans=[
                BillingPlanResponse(
                    key=plan.key,
                    name=plan.name,
                    billingPeriod=plan.billing_period,
                    productIdConfigured=bool(plan.product_id),
                )
                for plan in self.plans()
            ],
        )

    async def current_subscription(
        self, owner_user_id: str | None
    ) -> UserSubscriptionRecord | None:
        if not owner_user_id:
            return None
        async with self._session() as db:
            result = await db.execute(
                select(UserSubscriptionRecord)
                .where(UserSubscriptionRecord.owner_user_id == owner_user_id)
                .order_by(UserSubscriptionRecord.updated_at.desc())
            )
            return result.scalars().first()

    async def create_checkout(
        self,
        user: AuthenticatedUser,
        input_data: BillingCheckoutInput,
    ) -> BillingCheckoutResponse:
        if not user.is_clerk:
            raise PermissionError("Sign in to manage billing.")
        if not self.is_configured():
            raise ValueError("CREEM_API_KEY is not configured.")

        plan = self._plan_for_key(input_data.plan_key)
        if not plan.product_id:
            raise ValueError(f"Creem product id is not configured for {plan.key}.")

        request_id = f"vedic_{secrets.token_urlsafe(18)}"
        payload: dict[str, Any] = {
            "product_id": plan.product_id,
            "request_id": request_id,
            "success_url": input_data.success_url or self.settings.creem_success_url,
            "metadata": {
                "clerk_user_id": user.user_id,
                "app_user_id": user.user_id,
                "plan_key": plan.key,
                "source": "vedic_account_center",
            },
        }
        if user.email:
            payload["customer"] = {"email": user.email}

        response = await asyncio.to_thread(self._post_json, "/v1/checkouts", payload)
        checkout_url = str(response.get("checkout_url") or response.get("checkoutUrl") or "")
        if not checkout_url:
            raise RuntimeError("Creem checkout response did not include checkout_url.")

        checkout_id = _string_or_none(response.get("id") or response.get("checkout_id"))
        async with self._session() as db:
            record = BillingCheckoutRecord(
                request_id=request_id,
                checkout_id=checkout_id,
                owner_user_id=user.user_id,
                plan_key=plan.key,
                creem_product_id=plan.product_id,
                status=str(response.get("status") or "pending"),
                checkout_url=checkout_url,
                raw_payload=response,
            )
            db.add(record)
            await db.commit()

        return BillingCheckoutResponse(
            checkoutUrl=checkout_url,
            checkoutId=checkout_id,
            requestId=request_id,
        )

    async def assert_paid_access(self, user: AuthenticatedUser) -> None:
        if user.is_admin or not self.paywall_enabled():
            return
        subscription = await self.current_subscription(user.owner_user_id)
        if not _is_active(subscription):
            raise PermissionError("Upgrade to continue.")

    async def create_portal(self, user: AuthenticatedUser) -> BillingPortalResponse:
        if not user.is_clerk:
            raise PermissionError("Sign in to manage billing.")
        if not self.is_configured():
            raise ValueError("CREEM_API_KEY is not configured.")

        subscription = await self.current_subscription(user.owner_user_id)
        if not subscription or not subscription.creem_customer_id:
            raise LookupError("No Creem customer is connected to this account yet.")

        response = await asyncio.to_thread(
            self._post_json,
            "/v1/customers/billing",
            {"customer_id": subscription.creem_customer_id},
        )
        portal_url = str(
            response.get("customer_portal_link")
            or response.get("customerPortalLink")
            or response.get("url")
            or ""
        )
        if not portal_url:
            raise RuntimeError("Creem portal response did not include a portal link.")
        return BillingPortalResponse(portalUrl=portal_url)

    async def handle_webhook(
        self,
        raw_body: bytes,
        signature: str | None,
    ) -> CreemWebhookResponse:
        if not self.settings.creem_webhook_secret.strip():
            raise ValueError("CREEM_WEBHOOK_SECRET is not configured.")
        if not self.verify_webhook_signature(raw_body, signature):
            raise PermissionError("Invalid Creem webhook signature.")

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Invalid Creem webhook payload.") from exc
        if not isinstance(payload, dict):
            raise ValueError("Invalid Creem webhook payload.")

        event_id = str(payload.get("id") or "").strip()
        event_type = str(payload.get("eventType") or payload.get("event_type") or "").strip()
        if not event_id or not event_type:
            raise ValueError("Creem webhook is missing event id or event type.")

        async with self._session() as db:
            existing = await db.execute(
                select(BillingEventRecord).where(BillingEventRecord.event_id == event_id)
            )
            if existing.scalar_one_or_none():
                return CreemWebhookResponse(
                    ok=True,
                    processed=False,
                    duplicate=True,
                    eventId=event_id,
                    eventType=event_type,
                )

            owner_user_id = await self._resolve_owner_user_id(db, payload)
            creem_object_id = _string_or_none(_event_object(payload).get("id"))
            if owner_user_id:
                await self._upsert_subscription_from_event(
                    db,
                    owner_user_id=owner_user_id,
                    event_type=event_type,
                    payload=payload,
                )

            db.add(
                BillingEventRecord(
                    event_id=event_id,
                    event_type=event_type,
                    owner_user_id=owner_user_id,
                    creem_object_id=creem_object_id,
                    raw_payload=payload,
                    processed_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()

        return CreemWebhookResponse(
            ok=True,
            processed=True,
            duplicate=False,
            eventId=event_id,
            eventType=event_type,
            ownerUserId=owner_user_id,
        )

    def verify_webhook_signature(self, raw_body: bytes, signature: str | None) -> bool:
        received = (signature or "").strip()
        if not received:
            return False
        secret = self.settings.creem_webhook_secret.strip().encode("utf-8")
        expected = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(received, expected)

    def is_configured(self) -> bool:
        return bool(self.settings.creem_api_key.strip())

    def paywall_enabled(self) -> bool:
        return self.is_configured() and any(plan.product_id for plan in self.plans())

    def _plan_for_key(self, key: str) -> BillingPlan:
        for plan in self.plans():
            if plan.key == key:
                return plan
        raise ValueError(f"Unknown billing plan: {key}")

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        api_key = self.settings.creem_api_key.strip()
        url = f"{self.settings.creem_effective_api_base_url()}{path}"
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            url,
            data=body,
            method="POST",
            headers={
                "content-type": "application/json",
                "x-api-key": api_key,
            },
        )
        try:
            with urlopen(request, timeout=20) as response:
                response_body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Creem API error {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"Creem API request failed: {exc.reason}") from exc

        try:
            decoded = json.loads(response_body) if response_body else {}
        except json.JSONDecodeError as exc:
            raise RuntimeError("Creem API returned invalid JSON.") from exc
        if not isinstance(decoded, dict):
            raise RuntimeError("Creem API returned an unexpected response.")
        return decoded

    async def _resolve_owner_user_id(
        self,
        db: AsyncSession,
        payload: dict[str, Any],
    ) -> str | None:
        metadata = _collect_metadata(payload)
        owner = _owner_from_metadata(metadata)
        if owner:
            return owner

        request_id = _request_id_from_payload(payload)
        if request_id:
            result = await db.execute(
                select(BillingCheckoutRecord).where(BillingCheckoutRecord.request_id == request_id)
            )
            checkout = result.scalar_one_or_none()
            if checkout:
                return checkout.owner_user_id

        subscription_id = _subscription_id_from_payload(payload)
        if subscription_id:
            result = await db.execute(
                select(UserSubscriptionRecord).where(
                    UserSubscriptionRecord.creem_subscription_id == subscription_id
                )
            )
            subscription = result.scalar_one_or_none()
            if subscription:
                return subscription.owner_user_id

        customer_id = _customer_id_from_payload(payload)
        if customer_id:
            result = await db.execute(
                select(UserSubscriptionRecord)
                .where(UserSubscriptionRecord.creem_customer_id == customer_id)
                .order_by(UserSubscriptionRecord.updated_at.desc())
            )
            subscription = result.scalars().first()
            if subscription:
                return subscription.owner_user_id
        return None

    async def _upsert_subscription_from_event(
        self,
        db: AsyncSession,
        *,
        owner_user_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        subscription = _subscription_object_from_payload(payload)
        order = _order_object_from_payload(payload)
        if not subscription and not order:
            return

        subscription_id = _subscription_id_from_payload(payload)
        if not subscription_id and order:
            order_id = _string_or_none(order.get("id"))
            subscription_id = f"order:{order_id}" if order_id else None
        if not subscription_id:
            return

        result = await db.execute(
            select(UserSubscriptionRecord).where(
                UserSubscriptionRecord.creem_subscription_id == subscription_id
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            record = UserSubscriptionRecord(
                owner_user_id=owner_user_id,
                creem_subscription_id=subscription_id,
            )
            db.add(record)

        product_id = _product_id_from_payload(payload)
        customer_id = _customer_id_from_payload(payload)
        plan_key = _plan_key_from_payload(payload) or self._plan_key_for_product(product_id)
        status = _status_from_event(event_type, subscription, order)

        record.owner_user_id = owner_user_id
        record.creem_customer_id = customer_id or record.creem_customer_id
        record.creem_product_id = product_id or record.creem_product_id
        record.plan_key = plan_key or record.plan_key or "unknown"
        record.status = status
        period_start = _parse_datetime(
            _value_from(subscription, "current_period_start_date", "current_period_start")
        )
        period_end = _parse_datetime(
            _value_from(subscription, "current_period_end_date", "current_period_end")
        )
        if period_start:
            record.current_period_start = period_start
        if period_end:
            record.current_period_end = period_end
        record.cancel_at_period_end = status == "scheduled_cancel"
        record.canceled_at = _parse_datetime(_value_from(subscription, "canceled_at"))
        record.raw_payload = payload
        record.updated_at = datetime.now(timezone.utc)

    def _plan_key_for_product(self, product_id: str | None) -> str:
        if not product_id:
            return "unknown"
        for plan in self.plans():
            if plan.product_id == product_id:
                return plan.key
        return "unknown"


def _subscription_response(
    record: UserSubscriptionRecord | None,
) -> BillingSubscriptionResponse | None:
    if record is None:
        return None
    return BillingSubscriptionResponse(
        planKey=record.plan_key,
        status=record.status,
        isActive=_is_active(record),
        currentPeriodStart=_iso(record.current_period_start),
        currentPeriodEnd=_iso(record.current_period_end),
        cancelAtPeriodEnd=record.cancel_at_period_end,
        creemCustomerId=record.creem_customer_id,
        creemSubscriptionId=record.creem_subscription_id,
    )


def _is_active(record: UserSubscriptionRecord | None) -> bool:
    return bool(record and record.status in ACTIVE_SUBSCRIPTION_STATUSES)


def _event_object(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("object")
    return value if isinstance(value, dict) else {}


def _collect_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    combined: dict[str, Any] = {}
    candidates = [
        payload,
        _event_object(payload),
        _subscription_object_from_payload(payload) or {},
        _checkout_object_from_payload(payload) or {},
    ]
    for candidate in candidates:
        metadata = candidate.get("metadata") if isinstance(candidate, dict) else None
        if isinstance(metadata, dict):
            combined.update(metadata)
    return combined


def _owner_from_metadata(metadata: dict[str, Any]) -> str | None:
    for key in [
        "clerk_user_id",
        "app_user_id",
        "user_id",
        "userId",
        "referenceId",
        "internal_customer_id",
    ]:
        value = _string_or_none(metadata.get(key))
        if value:
            return value
    return None


def _request_id_from_payload(payload: dict[str, Any]) -> str | None:
    obj = _event_object(payload)
    checkout = _checkout_object_from_payload(payload)
    return _string_or_none(
        obj.get("request_id")
        or obj.get("requestId")
        or (checkout or {}).get("request_id")
        or (checkout or {}).get("requestId")
    )


def _subscription_id_from_payload(payload: dict[str, Any]) -> str | None:
    subscription = _subscription_object_from_payload(payload)
    if subscription:
        return _string_or_none(subscription.get("id"))
    obj = _event_object(payload)
    return _string_or_none(obj.get("subscription") or obj.get("subscription_id"))


def _customer_id_from_payload(payload: dict[str, Any]) -> str | None:
    obj = _event_object(payload)
    customer = obj.get("customer")
    if isinstance(customer, dict):
        return _string_or_none(customer.get("id"))
    if isinstance(customer, str):
        return _string_or_none(customer)
    subscription = _subscription_object_from_payload(payload)
    if subscription:
        customer = subscription.get("customer")
        if isinstance(customer, dict):
            return _string_or_none(customer.get("id"))
        return _string_or_none(customer)
    return None


def _product_id_from_payload(payload: dict[str, Any]) -> str | None:
    obj = _event_object(payload)
    for candidate in [
        obj.get("product"),
        (_subscription_object_from_payload(payload) or {}).get("product"),
    ]:
        if isinstance(candidate, dict):
            value = _string_or_none(candidate.get("id"))
        else:
            value = _string_or_none(candidate)
        if value:
            return value
    order = _order_object_from_payload(payload)
    if order:
        return _string_or_none(order.get("product"))
    return None


def _plan_key_from_payload(payload: dict[str, Any]) -> str | None:
    metadata = _collect_metadata(payload)
    return _string_or_none(metadata.get("plan_key") or metadata.get("planKey"))


def _subscription_object_from_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    obj = _event_object(payload)
    if obj.get("object") == "subscription":
        return obj
    subscription = obj.get("subscription")
    return subscription if isinstance(subscription, dict) else None


def _checkout_object_from_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    obj = _event_object(payload)
    if obj.get("object") == "checkout":
        return obj
    checkout = obj.get("checkout")
    return checkout if isinstance(checkout, dict) else None


def _order_object_from_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    obj = _event_object(payload)
    order = obj.get("order")
    return order if isinstance(order, dict) else None


def _status_from_event(
    event_type: str,
    subscription: dict[str, Any] | None,
    order: dict[str, Any] | None,
) -> str:
    if event_type in TERMINAL_EVENT_STATUS:
        return TERMINAL_EVENT_STATUS[event_type]
    status = _string_or_none(_value_from(subscription, "status"))
    if status:
        return status
    if event_type == "checkout.completed":
        order_status = _string_or_none(_value_from(order, "status"))
        if order_status == "paid":
            return "paid"
        return order_status or "completed"
    return event_type.removeprefix("subscription.").replace(".", "_")


def _value_from(source: dict[str, Any] | None, *keys: str) -> Any:
    if not source:
        return None
    for key in keys:
        if key in source:
            return source[key]
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if value in (None, "", "null"):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
