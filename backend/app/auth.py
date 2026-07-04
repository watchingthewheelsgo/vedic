from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import re

import jwt
from fastapi import Depends, Header, HTTPException
from jwt import PyJWKClient

from app.settings import Settings, get_settings


LOCAL_DEV_USER_ID = "local-dev-user"
ANONYMOUS_ID_PATTERN = re.compile(r"^anonym_[A-Za-z0-9_-]{8,64}$")


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: str
    auth_mode: str
    anonymous_user_id: str | None = None

    @property
    def owner_user_id(self) -> str | None:
        return self.user_id if self.auth_mode in {"anonymous", "clerk"} else None

    @property
    def is_clerk(self) -> bool:
        return self.auth_mode == "clerk"


class ClerkTokenVerifier:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        jwks_url = settings.clerk_effective_jwks_url()
        self.jwks_client = PyJWKClient(jwks_url) if jwks_url else None

    def verify(self, token: str) -> AuthenticatedUser:
        if self.jwks_client is None:
            raise HTTPException(
                status_code=500, detail="CLERK_JWT_ISSUER or CLERK_JWKS_URL is not configured"
            )

        try:
            signing_key = self.jwks_client.get_signing_key_from_jwt(token)
            decode_options: dict[str, object] = {
                "key": signing_key.key,
                "algorithms": ["RS256"],
                "options": {"verify_aud": False},
            }
            issuer = self.settings.clerk_jwt_issuer.strip()
            if issuer:
                decode_options["issuer"] = issuer
            payload = jwt.decode(token, **decode_options)
        except jwt.PyJWTError as exc:
            raise HTTPException(status_code=401, detail="Invalid Clerk session token") from exc

        subject = str(payload.get("sub") or "").strip()
        if not subject:
            raise HTTPException(status_code=401, detail="Clerk session token is missing a subject")
        return AuthenticatedUser(user_id=subject, auth_mode="clerk")


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
        return AuthenticatedUser(user_id=LOCAL_DEV_USER_ID, auth_mode="disabled")

    if not authorization:
        anonymous = _anonymous_user(anonymous_id)
        if anonymous:
            return anonymous
        raise HTTPException(status_code=401, detail="Missing anonymous session id")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Expected Bearer token")
    user = _verifier().verify(token.strip())
    anonymous = _anonymous_user(anonymous_id)
    return AuthenticatedUser(
        user_id=user.user_id,
        auth_mode=user.auth_mode,
        anonymous_user_id=anonymous.user_id if anonymous else None,
    )


async def require_user(
    authorization: str | None = Header(default=None),
    anonymous_id: str | None = Header(default=None, alias="x-vedic-anonymous-id"),
) -> AuthenticatedUser:
    settings = get_settings()
    if not settings.auth_enabled():
        return AuthenticatedUser(user_id=LOCAL_DEV_USER_ID, auth_mode="disabled")

    user = await resolve_session_user(authorization=authorization, anonymous_id=anonymous_id)
    if not user.is_clerk:
        raise HTTPException(status_code=401, detail="Sign in to continue")
    return user


CurrentUser = Depends(require_user)
