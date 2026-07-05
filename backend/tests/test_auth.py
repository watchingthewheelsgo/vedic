from __future__ import annotations

import asyncio

from fastapi import HTTPException
import pytest

import app.auth as auth_module


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
    assert exc_info.value.detail == "Sign in to continue"
