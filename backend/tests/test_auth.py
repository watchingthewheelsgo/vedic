from __future__ import annotations

import asyncio
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


def test_resolve_session_user_uses_anonymous_when_clerk_token_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_rejecting_clerk(monkeypatch)

    user = asyncio.run(
        auth_module.resolve_session_user(
            authorization="Bearer stale-token",
            anonymous_id="anonym_abc12345",
        )
    )

    assert user.user_id == "anonym_abc12345"
    assert user.auth_mode == "anonymous"
    assert user.anonymous_user_id is None


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
        "/api/places": [],
        "/api/precise-places": [],
        "/api/admin/sessions": ["require_user"],
        "/api/admin/sessions/{session_id}": ["require_user"],
        "/api/me": ["require_user"],
        "/api/me/sessions": ["require_user"],
        "/api/billing/account": ["require_user"],
        "/api/billing/checkout": ["require_user"],
        "/api/billing/portal": ["require_user"],
        "/api/webhooks/creem": [],
        "/api/skill-sessions": ["resolve_session_user"],
        "/api/bazi-sessions": ["resolve_session_user"],
        "/api/skill-sessions/{session_id}": ["resolve_session_user"],
        "/api/skill-sessions/{session_id}/report.pdf": ["require_user"],
        "/api/skill-synastry-subject": ["require_user"],
        "/api/skill-runs": ["resolve_session_user"],
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

        def is_admin_identity(self, user_id: str, email: str | None = None) -> bool:
            return email == "admin@example.com"

    verifier = auth_module.ClerkTokenVerifier(Settings())
    monkeypatch.setattr(
        auth_module,
        "jwt",
        SimpleNamespace(
            ExpiredSignatureError=auth_module.jwt.ExpiredSignatureError,
            PyJWTError=auth_module.jwt.PyJWTError,
            decode=lambda token, **kwargs: {"sub": "user_123", "exp": 9999999999},
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
    assert user.is_admin is True
    assert user.role == "admin"


def test_clerk_verifier_rejects_expired_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Settings:
        clerk_secret_key = "sk_test_value"

        def is_admin_identity(self, user_id: str, email: str | None = None) -> bool:
            return False

    verifier = auth_module.ClerkTokenVerifier(Settings())
    monkeypatch.setattr(
        auth_module.jwt,
        "decode",
        lambda token, **kwargs: (_ for _ in ()).throw(
            auth_module.jwt.ExpiredSignatureError("expired")
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        verifier.verify("expired-token")

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Clerk session token has expired"


def test_clerk_settings_use_backend_user_lookup_when_secret_key_is_configured() -> None:
    settings = Settings(
        _env_file=None,
        VEDIC_AUTH_MODE="clerk",
        VITE_CLERK_PUBLISHABLE_KEY="pk_test_value",
        CLERK_SECRET_KEY="sk_test_value",
    )

    assert settings.clerk_verifier_source() == "unsigned_jwt_claims_plus_clerk_user_lookup"
    assert settings.auth_config_summary()["secretKeyConfigured"] is True


def test_clerk_verifier_rejects_unknown_backend_user(monkeypatch: pytest.MonkeyPatch) -> None:
    class Settings:
        clerk_secret_key = "sk_test_value"

        def is_admin_identity(self, user_id: str, email: str | None = None) -> bool:
            return False

    verifier = auth_module.ClerkTokenVerifier(Settings())
    monkeypatch.setattr(
        auth_module.jwt,
        "decode",
        lambda token, **kwargs: {"sub": "missing_user", "exp": 9999999999},
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
            assert created.role == "admin"
            assert created.is_admin is True

            async with get_session_factory()() as db:
                result = await db.execute(
                    select(AppUserRecord).where(AppUserRecord.clerk_user_id == "user_admin123")
                )
                record = result.scalar_one()
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
