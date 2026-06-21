"""Auth dependencies — FastAPI dependency injection for authentication.

Provides:
- ``OptionalAuth`` — extracts wallet if token present, None otherwise
- ``RequireAuth`` — requires valid JWT, returns wallet address
- ``RequireMarketMaker`` — requires MARKET_MAKER tier

Usage in endpoints::

    @router.get("/protected")
    async def protected(wallet: RequireAuth):
        return {"wallet": wallet}

    @router.get("/optional")
    async def optional(wallet: OptionalAuth):
        if wallet:
            return {"wallet": wallet, "authenticated": True}
        return {"authenticated": False}
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, Header, Request

from app.auth.tokens import TokenPayload, verify_token
from app.middleware.errors import APIError

logger = logging.getLogger("ax-server.auth.deps")

# Error codes
AUTH_REQUIRED = "AUTH_REQUIRED"
AUTH_INVALID = "AUTH_INVALID"
AUTH_EXPIRED = "AUTH_EXPIRED"
AUTH_INSUFFICIENT_TIER = "AUTH_INSUFFICIENT_TIER"


def _extract_token(authorization: str | None = Header(None, alias="Authorization")) -> str | None:
    """Extract Bearer token from Authorization header."""
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1]


async def _get_optional_auth(
    token: str | None = Depends(_extract_token),
) -> TokenPayload | None:
    """Verify token if present, return None if absent."""
    if not token:
        return None
    try:
        return verify_token(token, expected_type="access")
    except ValueError:
        return None


async def _get_required_auth(
    token: str | None = Depends(_extract_token),
) -> TokenPayload:
    """Require a valid JWT access token.

    Raises ``APIError`` with appropriate code if token is missing, invalid,
    or expired.
    """
    if not token:
        raise APIError(
            code=AUTH_REQUIRED,
            message="Authentication required. Sign in with SIWE to get a token.",
            status_code=401,
        )
    try:
        payload = verify_token(token, expected_type="access")
    except ValueError as e:
        error_msg = str(e)
        if "expired" in error_msg.lower():
            raise APIError(
                code=AUTH_EXPIRED,
                message="Token has expired. Please sign in again or use your refresh token.",
                status_code=401,
            )
        raise APIError(
            code=AUTH_INVALID,
            message=f"Invalid authentication token: {error_msg}",
            status_code=401,
        )
    return payload


async def _get_wallet(auth: TokenPayload = Depends(_get_required_auth)) -> str:
    """Extract just the wallet address from a required auth token."""
    return auth.wallet


async def _get_optional_wallet(
    auth: TokenPayload | None = Depends(_get_optional_auth),
) -> str | None:
    """Extract wallet address if authenticated, None otherwise."""
    return auth.wallet if auth else None


async def _require_market_maker(auth: TokenPayload = Depends(_get_required_auth)) -> TokenPayload:
    """Require MARKET_MAKER tier."""
    if auth.tier != "MARKET_MAKER":
        raise APIError(
            code=AUTH_INSUFFICIENT_TIER,
            message="This endpoint requires MARKET_MAKER tier access.",
            status_code=403,
        )
    return auth


# Dependency types for use in endpoint signatures
RequireAuth = Annotated[str, Depends(_get_wallet)]
OptionalAuth = Annotated[str | None, Depends(_get_optional_wallet)]
RequireAuthFull = Annotated[TokenPayload, Depends(_get_required_auth)]
OptionalAuthFull = Annotated[TokenPayload | None, Depends(_get_optional_auth)]
RequireMarketMaker = Annotated[TokenPayload, Depends(_require_market_maker)]
