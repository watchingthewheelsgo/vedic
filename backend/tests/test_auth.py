from __future__ import annotations

import asyncio
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from fastapi import HTTPException
import pytest
from sqlalchemy import select

import app.auth as auth_module
import app.main as main_module
from app.main import app
from app.db.engine import close_db, get_session_factory, init_db
from app.db.models import AppUserRecord
from app.schemas import SkillRunInput
from app.services.user_store import UserStore
from app.settings import Settings


class AuthEnabledSettings:
    def auth_enabled(self) -> bool:
        return True


class RejectingClerkVerifier:
    def verify(self, token: str) -> auth_module.AuthenticatedUser:
        raise HTTPException(status_code=401, detail="Invalid Clerk session token")


def install_rejecting_clerk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_module, "get_settings", lambda: AuthEnabledSettings())
    monkeypatch.setattr(auth_module, "_verifier", lambda: RejectingClerkVerifier())


@pytest.mark.parametrize("token", [None, "Bearer stale-token"])
def test_anonymous_headers_never_grant_product_access(monkeypatch, token):
    install_rejecting_clerk(monkeypatch)
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            auth_module.resolve_session_user(authorization=token, anonymous_id="anonym_abc12345")
        )
    assert error.value.status_code == 401


def test_resolve_session_user_rejects_invalid_clerk_token_without_anonymous_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_rejecting_clerk(monkeypatch)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            auth_module.resolve_session_user(
                authorization="Bearer stale-token",
                anonymous_id=None,
            )
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid Clerk session token"


def test_require_user_does_not_allow_invalid_clerk_token_with_anonymous_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_rejecting_clerk(monkeypatch)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            auth_module.require_user(
                authorization="Bearer stale-token",
                anonymous_id="anonym_abc12345",
            )
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid Clerk session token"


def test_require_user_prompts_sign_in_for_anonymous_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth_module, "get_settings", lambda: AuthEnabledSettings())

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            auth_module.require_user(
                authorization=None,
                anonymous_id="anonym_abc12345",
            )
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Sign in to continue"


def test_require_user_prompts_sign_in_when_auth_headers_are_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth_module, "get_settings", lambda: AuthEnabledSettings())

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(auth_module.require_user(authorization=None, anonymous_id=None))

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Sign in to continue"


def test_api_endpoint_auth_dependency_matrix() -> None:
    route_dependencies = {
        cast(Any, route).path: [
            getattr(dependency.call, "__name__", repr(dependency.call))
            for dependency in cast(Any, route).dependant.dependencies
        ]
        for route in app.routes
        if getattr(route, "path", "").startswith("/api/") and hasattr(route, "dependant")
    }

    assert route_dependencies == {
        "/api/health": [],
        "/api/places": ["require_user"],
        "/api/precise-places": ["require_user"],
        "/api/precise-places/stream": ["require_user"],
        "/api/admin/sessions": ["require_user"],
        "/api/admin/sessions/{session_id}": ["require_user"],
        "/api/me": ["require_user"],
        "/api/me/sessions": ["require_user"],
        "/api/billing/account": ["require_user"],
        "/api/billing/checkout": ["require_user"],
        "/api/billing/portal": ["require_user"],
        "/api/webhooks/creem": [],
        "/api/skill-sessions": ["require_user"],
        "/api/bazi-sessions": ["require_user"],
        "/api/skill-sessions/{session_id}": ["require_user"],
        "/api/rectification-life-events": ["require_user"],
        "/api/rectification-life-events/reset": ["require_user"],
        "/api/rectification-interview": ["require_user"],
        "/api/rectification-confirmation": ["require_user"],
        "/api/consultation-questions": ["require_user"],
        "/api/consultation-conversations/{session_id}": ["require_user"],
        "/api/skill-sessions/{session_id}/report.pdf": ["require_user"],
        "/api/skill-synastry-subject": ["require_user"],
        "/api/skill-runs": ["require_user"],
        "/api/core-jobs": ["require_user"],
        "/api/core-jobs/{job_id}": ["require_user"],
        "/api/skill-feedback": ["require_user"],
    }


def test_skill_run_value_error_records_failed_session(monkeypatch: pytest.MonkeyPatch) -> None:
    class UserStore:
        async def upsert_from_auth_user(self, user: auth_module.AuthenticatedUser):
            return user

    class MetadataStore:
        def __init__(self) -> None:
            self.synced: dict[str, object] | None = None

        async def assert_session_access(self, session_id: str, owner_user_id: str | None) -> None:
            assert session_id == "session_123"
            assert owner_user_id == "user_123"

        async def sync_session_from_files(self, session_id: str, **kwargs: object) -> None:
            self.synced = {"session_id": session_id, **kwargs}

    class SkillRuntime:
        async def run_skill(self, input_data: SkillRunInput, *, owner_user_id: str | None = None):
            assert input_data.session_id == "session_123"
            assert owner_user_id == "user_123"
            raise ValueError("Agent did not return artifact JSON")

    metadata_store = MetadataStore()
    container = SimpleNamespace(
        user_store=UserStore(),
        metadata_store=metadata_store,
        skill_runtime=SkillRuntime(),
        ai_allowance=SimpleNamespace(charge=lambda *args, **kwargs: nullcontext()),
    )
    monkeypatch.setattr(main_module, "get_container", lambda: container)

    async def run() -> None:
        with pytest.raises(HTTPException) as exc_info:
            await main_module.run_skill(
                SkillRunInput(
                    sessionId="session_123",
                    skill="vedic-reader",
                    userMessage="",
                    locale="zh",
                ),
                current_user=auth_module.AuthenticatedUser(
                    user_id="user_123",
                    auth_mode="clerk",
                ),
            )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Agent did not return artifact JSON"
        assert metadata_store.synced == {
            "session_id": "session_123",
            "stage": "error",
            "status": "failed",
            "owner_user_id": "user_123",
            "error": "Agent did not return artifact JSON",
        }

    asyncio.run(run())


def test_clerk_verifier_uses_backend_email_when_token_has_no_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Settings:
        clerk_secret_key = "sk_test_value"

        def allowed_origin_list(self) -> list[str]:
            return ["http://127.0.0.1:5173"]

        def is_admin_identity(self, user_id: str, email: str | None = None) -> bool:
            return email == "admin@example.com"

    verifier = auth_module.ClerkTokenVerifier(
        Settings(),
        authenticate_request=lambda request, options: SimpleNamespace(
            is_signed_in=True,
            payload={"sub": "user_123", "exp": 9999999999},
        ),
    )
    monkeypatch.setattr(
        auth_module,
        "_cached_clerk_user_from_backend",
        lambda secret_key, user_id: {
            "primary_email_address_id": "email_1",
            "email_addresses": [
                {"id": "email_1", "email_address": "Admin@Example.com"},
            ],
        },
    )

    user = verifier.verify("valid-token")

    assert user.user_id == "user_123"
    assert user.email == "admin@example.com"
    assert user.is_admin is False
    assert user.role == "user"


def test_clerk_verifier_rejects_expired_tokens() -> None:
    class Settings:
        clerk_secret_key = "sk_test_value"

        def allowed_origin_list(self) -> list[str]:
            return ["http://127.0.0.1:5173"]

        def is_admin_identity(self, user_id: str, email: str | None = None) -> bool:
            return False

    verifier = auth_module.ClerkTokenVerifier(
        Settings(),
        authenticate_request=lambda request, options: SimpleNamespace(
            is_signed_in=False,
            payload=None,
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        verifier.verify("expired-token")

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid or expired Clerk session token"


def test_clerk_settings_use_backend_user_lookup_when_secret_key_is_configured() -> None:
    settings = Settings(
        _env_file=None,
        VEDIC_AUTH_MODE="clerk",
        VITE_CLERK_PUBLISHABLE_KEY="pk_test_value",
        CLERK_SECRET_KEY="sk_test_value",
    )

    assert settings.clerk_verifier_source() == "clerk_signed_session_token"
    assert settings.auth_config_summary()["secretKeyConfigured"] is True


def test_clerk_verifier_rejects_unknown_backend_user(monkeypatch: pytest.MonkeyPatch) -> None:
    class Settings:
        clerk_secret_key = "sk_test_value"

        def allowed_origin_list(self) -> list[str]:
            return ["http://127.0.0.1:5173"]

        def is_admin_identity(self, user_id: str, email: str | None = None) -> bool:
            return False

    verifier = auth_module.ClerkTokenVerifier(
        Settings(),
        authenticate_request=lambda request, options: SimpleNamespace(
            is_signed_in=True,
            payload={"sub": "missing_user", "exp": 9999999999},
        ),
    )
    monkeypatch.setattr(
        auth_module,
        "_cached_clerk_user_from_backend",
        lambda secret_key, user_id: None,
    )

    with pytest.raises(HTTPException) as exc_info:
        verifier.verify("valid-looking-token")

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Clerk user not found"


def test_clerk_verifier_does_not_trust_admin_claims(monkeypatch: pytest.MonkeyPatch) -> None:
    class Settings:
        clerk_secret_key = "sk_test_value"

        def allowed_origin_list(self) -> list[str]:
            return ["http://127.0.0.1:5173"]

        def is_admin_identity(self, user_id: str, email: str | None = None) -> bool:
            return False

    verifier = auth_module.ClerkTokenVerifier(
        Settings(),
        authenticate_request=lambda request, options: SimpleNamespace(
            is_signed_in=True,
            payload={
                "sub": "user_123",
                "exp": 9999999999,
                "role": "admin",
                "public_metadata": {"admin": True},
            },
        ),
    )
    monkeypatch.setattr(
        auth_module,
        "_cached_clerk_user_from_backend",
        lambda secret_key, user_id: {
            "primary_email_address_id": "email_1",
            "email_addresses": [{"id": "email_1", "email_address": "user@example.com"}],
        },
    )

    user = verifier.verify("signed-token")

    assert user.is_admin is False
    assert user.role == "user"


def test_user_store_keeps_database_role_as_authority(tmp_path: Path) -> None:
    async def run() -> None:
        await init_db(
            SimpleNamespace(
                database_url=f"sqlite+aiosqlite:///{tmp_path / 'vedic.db'}",
                database_echo=False,
            )
        )
        try:
            store = UserStore()
            token_admin = auth_module.AuthenticatedUser(
                user_id="user_admin123",
                auth_mode="clerk",
                email="admin@example.com",
                role="admin",
                is_admin=True,
            )

            created = await store.upsert_from_auth_user(token_admin)
            assert created.role == "user"
            assert created.is_admin is False

            async with get_session_factory()() as db:
                result = await db.execute(
                    select(AppUserRecord).where(AppUserRecord.clerk_user_id == "user_admin123")
                )
                record = result.scalar_one()
                record.role = "admin"
                await db.commit()

            promoted = await store.upsert_from_auth_user(token_admin)
            assert promoted.is_admin is True
            async with get_session_factory()() as db:
                record = (
                    await db.execute(
                        select(AppUserRecord).where(AppUserRecord.clerk_user_id == "user_admin123")
                    )
                ).scalar_one()
                record.role = "user"
                await db.commit()

            synced = await store.upsert_from_auth_user(token_admin)
            assert synced.role == "user"
            assert synced.is_admin is False

            profile = await store.profile_for(token_admin)
            assert profile.role == "user"
            assert profile.is_admin is False
        finally:
            await close_db()

    asyncio.run(run())


def test_journal_routes_require_verified_users():
    from app.services.daily_journal import router

    for route in router.routes:
        assert any(
            dep.call is auth_module.require_user for dep in cast(Any, route).dependant.dependencies
        )


def test_verified_login_does_not_claim_legacy_anonymous_identity(monkeypatch):
    monkeypatch.setattr(auth_module, "get_settings", lambda: AuthEnabledSettings())
    verified = auth_module.AuthenticatedUser(user_id="user_verified", auth_mode="clerk")
    monkeypatch.setattr(
        auth_module, "_verifier", lambda: SimpleNamespace(verify=lambda _: verified)
    )
    user = asyncio.run(
        auth_module.resolve_session_user(
            authorization="Bearer valid", anonymous_id="anonym_abc12345"
        )
    )
    assert user.user_id == "user_verified"
    assert user.anonymous_user_id is None


def test_legacy_owner_header_cannot_claim_a_private_report():
    class Store:
        async def claim_session_owner(self, *args, **kwargs):
            pytest.fail("legacy ownership must never be claimed automatically")

        async def assert_session_access(self, session_id, owner):
            assert owner == "user_verified"
            raise PermissionError("not owned")

    user = auth_module.AuthenticatedUser(
        user_id="user_verified", auth_mode="clerk", anonymous_user_id="anonym_abc12345"
    )
    with pytest.raises(PermissionError):
        asyncio.run(
            main_module._claim_or_assert_session_access(
                SimpleNamespace(metadata_store=Store()), "old-session", user
            )
        )


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/me/journal"),
        ("POST", "/api/me/journal/reflect"),
        ("POST", "/api/me/journal/actions"),
        ("POST", "/api/skill-sessions"),
        ("POST", "/api/bazi-sessions"),
        ("POST", "/api/skill-runs"),
        ("GET", "/api/skill-sessions/private-id"),
        ("GET", "/api/places"),
        ("GET", "/api/precise-places"),
    ],
)
def test_product_http_endpoints_reject_anonymous_headers(monkeypatch, method, path):
    import httpx

    install_rejecting_clerk(monkeypatch)

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            for headers in (
                {"x-vedic-anonymous-id": "anonym_abc12345"},
                {"authorization": "Bearer stale", "x-vedic-anonymous-id": "anonym_abc12345"},
            ):
                response = await client.request(method, path, headers=headers)
                assert response.status_code == 401, response.text

    asyncio.run(run())


def test_feedback_permissions_follow_database_role_each_request(monkeypatch, tmp_path):
    import httpx
    from fastapi import FastAPI
    from app.services.feedback import router

    monkeypatch.setattr(auth_module, "get_settings", lambda: AuthEnabledSettings())
    monkeypatch.setattr(
        auth_module,
        "_verifier",
        lambda: SimpleNamespace(
            verify=lambda token: auth_module.AuthenticatedUser(
                user_id="role_test", auth_mode="clerk", role="admin", is_admin=True
            )
        ),
    )
    api = FastAPI()
    api.include_router(router)

    async def run():
        await init_db(
            SimpleNamespace(
                database_url=f"sqlite+aiosqlite:///{tmp_path / 'roles.db'}", database_echo=False
            )
        )
        try:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=api),
                base_url="http://test",
                headers={"Authorization": "Bearer same-token"},
            ) as client:
                # Even a forged upstream admin flag cannot provision an administrator.
                assert (await client.get("/api/admin/feedback")).status_code == 403
                for role, expected in [("admin", 200), ("user", 403), ("owner", 403)]:
                    async with get_session_factory()() as db:
                        record = (
                            await db.execute(
                                select(AppUserRecord).where(
                                    AppUserRecord.clerk_user_id == "role_test"
                                )
                            )
                        ).scalar_one()
                        record.role = role
                        await db.commit()
                    assert (await client.get("/api/admin/feedback")).status_code == expected
                    response = await client.patch(
                        "/api/admin/feedback/00000000-0000-0000-0000-000000000001",
                        json={"status": "resolved"},
                    )
                    assert response.status_code == (404 if role == "admin" else 403)
        finally:
            await close_db()

    asyncio.run(run())
