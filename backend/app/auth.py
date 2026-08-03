from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable
import re
from urllib.parse import quote

from clerk_backend_api import Clerk
from clerk_backend_api.security.types import AuthenticateRequestOptions, RequestState
import httpx
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
    def __init__(
        self,
        settings: Settings,
        *,
        authenticate_request: Callable[[httpx.Request, AuthenticateRequestOptions], RequestState]
        | None = None,
    ) -> None:
        self.settings = settings
        self._authenticate_request = (
            authenticate_request
            or Clerk(bearer_auth=settings.clerk_secret_key).authenticate_request
        )

    def verify(self, token: str) -> AuthenticatedUser:
        try:
            state = self._authenticate_request(
                httpx.Request(
                    "GET",
                    "https://vedicdust.local/api/auth/session",
                    headers={"Authorization": f"Bearer {token}"},
                ),
                AuthenticateRequestOptions(
                    secret_key=self.settings.clerk_secret_key,
                    authorized_parties=self.settings.allowed_origin_list(),
                    accepts_token=["session_token"],
                ),
            )
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail="Unable to verify Clerk session token",
            ) from exc
        if not state.is_signed_in or not isinstance(state.payload, dict):
            raise HTTPException(status_code=401, detail="Invalid or expired Clerk session token")
        payload = state.payload

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
        email = _email_from_clerk_user(clerk_user)
        claim_admin = self.settings.is_admin_identity(subject, email)
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
