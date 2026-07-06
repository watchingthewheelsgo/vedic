from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any
import re
from urllib.parse import quote

import httpx
import jwt
from fastapi import Depends, Header, HTTPException

from app.settings import Settings, get_settings


LOCAL_DEV_USER_ID = "local-dev-user"
ANONYMOUS_ID_PATTERN = re.compile(r"^anonym_[A-Za-z0-9_-]{8,64}$")


class ClerkBackendLookupError(RuntimeError):
    pass


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    auth_mode: str
    anonymous_user_id: str | None = None
    email: str | None = None
    role: str = "user"
    is_admin: bool = False
    auth_error_detail: str | None = None

    @property
    def owner_user_id(self) -> str | None:
        return self.user_id if self.auth_mode in {"anonymous", "clerk"} else None

    @property
    def is_clerk(self) -> bool:
        return self.auth_mode == "clerk"


class ClerkTokenVerifier:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def verify(self, token: str) -> AuthenticatedUser:
        try:
            payload = jwt.decode(
                token,
                options={
                    "verify_signature": False,
                    "verify_exp": True,
                    "verify_aud": False,
                    "verify_iss": False,
                },
            )
        except jwt.ExpiredSignatureError as exc:
            raise HTTPException(status_code=401, detail="Clerk session token has expired") from exc
        except jwt.PyJWTError as exc:
            raise HTTPException(status_code=401, detail="Invalid Clerk session token") from exc

        if "exp" not in payload:
            raise HTTPException(status_code=401, detail="Clerk session token is missing exp")

        try:
            clerk_user = _clerk_user_from_backend(self.settings.clerk_secret_key, payload)
        except ClerkBackendLookupError as exc:
            raise HTTPException(
                status_code=503,
                detail="Unable to verify Clerk user with Clerk Backend API",
            ) from exc

        return self._user_from_payload(payload, clerk_user)

    def _user_from_payload(
        self, payload: dict[str, Any], clerk_user: dict[str, Any]
    ) -> AuthenticatedUser:
        subject = str(payload.get("sub") or "").strip()
        if not subject:
            raise HTTPException(status_code=401, detail="Clerk session token is missing a subject")
        email = _email_from_claims(payload) or _email_from_clerk_user(clerk_user)
        claim_admin = _claims_grant_admin(payload) or self.settings.is_admin_identity(
            subject, email
        )
        return AuthenticatedUser(
            user_id=subject,
            auth_mode="clerk",
            email=email,
            role="admin" if claim_admin else "user",
            is_admin=claim_admin,
        )


@lru_cache(maxsize=1)
def _verifier() -> ClerkTokenVerifier:
    return ClerkTokenVerifier(get_settings())


def _anonymous_user(anonymous_id: str | None) -> AuthenticatedUser | None:
    value = (anonymous_id or "").strip()
    if not value:
        return None
    if not ANONYMOUS_ID_PATTERN.fullmatch(value):
        raise HTTPException(status_code=401, detail="Invalid anonymous session id")
    return AuthenticatedUser(user_id=value, auth_mode="anonymous")


async def resolve_session_user(
    authorization: str | None = Header(default=None),
    anonymous_id: str | None = Header(default=None, alias="x-vedic-anonymous-id"),
) -> AuthenticatedUser:
    settings = get_settings()
    if not settings.auth_enabled():
        return AuthenticatedUser(
            user_id=LOCAL_DEV_USER_ID,
            auth_mode="disabled",
            role="admin",
            is_admin=True,
        )

    anonymous = _anonymous_user(anonymous_id)
    if not authorization:
        if anonymous:
            return anonymous
        raise HTTPException(status_code=401, detail="Missing anonymous session id")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Expected Bearer token")
    try:
        user = _verifier().verify(token.strip())
    except HTTPException as exc:
        # Public reading endpoints accept anonymous sessions. If the browser has a
        # stale/misconfigured Clerk token but still sends a valid anonymous id,
        # keep the trial flow working as anonymous. Protected endpoints call
        # require_user(), which will still reject the anonymous user below.
        if exc.status_code == 401 and anonymous:
            return AuthenticatedUser(
                user_id=anonymous.user_id,
                auth_mode=anonymous.auth_mode,
                auth_error_detail=str(exc.detail),
            )
        raise
    return AuthenticatedUser(
        user_id=user.user_id,
        auth_mode=user.auth_mode,
        anonymous_user_id=anonymous.user_id if anonymous else None,
        email=user.email,
        role=user.role,
        is_admin=user.is_admin,
    )


async def require_user(
    authorization: str | None = Header(default=None),
    anonymous_id: str | None = Header(default=None, alias="x-vedic-anonymous-id"),
) -> AuthenticatedUser:
    settings = get_settings()
    if not settings.auth_enabled():
        return AuthenticatedUser(
            user_id=LOCAL_DEV_USER_ID,
            auth_mode="disabled",
            role="admin",
            is_admin=True,
        )

    if not authorization:
        raise HTTPException(status_code=401, detail="Sign in to continue")

    user = await resolve_session_user(authorization=authorization, anonymous_id=anonymous_id)
    if not user.is_clerk:
        if user.auth_error_detail:
            raise HTTPException(status_code=401, detail=user.auth_error_detail)
        raise HTTPException(status_code=401, detail="Sign in to continue")
    return user


CurrentUser = Depends(require_user)


def _email_from_claims(payload: dict[str, Any]) -> str | None:
    for key in ["email", "email_address", "primary_email_address"]:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return None


def _clerk_user_from_backend(secret_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    user_id = str(payload.get("sub") or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="Clerk session token is missing a subject")
    clerk_user = _cached_clerk_user_from_backend(secret_key, user_id)
    if clerk_user is None:
        raise HTTPException(status_code=401, detail="Clerk user not found")
    return clerk_user


@lru_cache(maxsize=512)
def _cached_clerk_user_from_backend(secret_key: str, user_id: str) -> dict[str, Any] | None:
    secret = (secret_key or "").strip()
    subject = (user_id or "").strip()
    if not secret:
        raise HTTPException(status_code=500, detail="CLERK_SECRET_KEY is not configured")
    if not subject:
        raise HTTPException(status_code=401, detail="Clerk session token is missing a subject")

    try:
        response = httpx.get(
            f"https://api.clerk.com/v1/users/{quote(subject, safe='')}",
            headers={"Authorization": f"Bearer {secret}"},
            timeout=4.0,
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return None
        raise ClerkBackendLookupError(str(exc)) from exc
    except (httpx.HTTPError, ValueError):
        raise ClerkBackendLookupError("Clerk Backend API request failed")

    if not isinstance(payload, dict):
        raise ClerkBackendLookupError("Clerk Backend API returned an invalid user payload")
    return payload


def _email_from_clerk_user(payload: dict[str, Any]) -> str | None:
    addresses = payload.get("email_addresses")
    if not isinstance(addresses, list):
        return None

    primary_id = payload.get("primary_email_address_id")
    ordered = []
    if isinstance(primary_id, str) and primary_id:
        ordered.extend(
            address
            for address in addresses
            if isinstance(address, dict) and address.get("id") == primary_id
        )
    ordered.extend(address for address in addresses if isinstance(address, dict))

    for address in ordered:
        email = address.get("email_address")
        if isinstance(email, str) and email.strip():
            return email.strip().lower()
    return None


def _claims_grant_admin(payload: dict[str, Any]) -> bool:
    if _role_is_admin(payload.get("role")) or _role_is_admin(payload.get("org_role")):
        return True
    if _roles_include_admin(payload.get("roles")):
        return True
    for key in ["public_metadata", "private_metadata", "unsafe_metadata", "metadata"]:
        metadata = payload.get(key)
        if not isinstance(metadata, dict):
            continue
        if metadata.get("admin") is True or metadata.get("isAdmin") is True:
            return True
        if _role_is_admin(metadata.get("role")) or _role_is_admin(metadata.get("userRole")):
            return True
        if _roles_include_admin(metadata.get("roles")):
            return True
    return False


def _role_is_admin(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return value.strip().lower() in {"admin", "owner", "super_admin", "super-admin"}


def _roles_include_admin(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    return any(_role_is_admin(item) for item in value)
