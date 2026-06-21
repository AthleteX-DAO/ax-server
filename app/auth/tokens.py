"""JWT token management — issue and verify session tokens after SIWE.

Tokens are short-lived (default 24h) and contain the authenticated wallet
address plus metadata. Refresh tokens extend the session without re-signing.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any

import jwt

logger = logging.getLogger("ax-server.auth.jwt")

# Default secret — MUST be overridden via JWT_SECRET env var in production
_DEFAULT_SECRET = "ax-server-dev-secret-change-me"
_ALGORITHM = "HS256"


@dataclass
class TokenPayload:
    """Decoded JWT payload."""

    wallet: str        # checksummed Ethereum address
    chain_id: int
    tier: str          # rate-limit tier: BASIC, ADVANCED, MARKET_MAKER
    issued_at: float
    expires_at: float
    token_type: str    # "access" or "refresh"


def _get_secret() -> str:
    """Load JWT secret from environment."""
    secret = os.getenv("JWT_SECRET", _DEFAULT_SECRET)
    if secret == _DEFAULT_SECRET:
        logger.warning("Using default JWT secret — set JWT_SECRET in production!")
    return secret


def create_access_token(
    wallet: str,
    chain_id: int = 137,
    tier: str = "ADVANCED",
    expires_hours: int = 24,
) -> str:
    """Create a signed JWT access token for an authenticated wallet.

    Parameters
    ----------
    wallet:
        Checksummed Ethereum address.
    chain_id:
        Chain ID the user authenticated on.
    tier:
        Rate-limit tier to grant (authenticated users get ADVANCED).
    expires_hours:
        Token lifetime in hours.

    Returns
    -------
    str
        Encoded JWT string.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": wallet.lower(),  # subject = wallet address
        "wallet": wallet,
        "chain_id": chain_id,
        "tier": tier,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=expires_hours)).timestamp()),
    }
    token = jwt.encode(payload, _get_secret(), algorithm=_ALGORITHM)
    logger.info("Issued access token for %s (expires in %dh)", wallet, expires_hours)
    return token


def create_refresh_token(
    wallet: str,
    chain_id: int = 137,
    expires_days: int = 30,
) -> str:
    """Create a long-lived refresh token.

    Refresh tokens can be exchanged for new access tokens without
    re-signing a SIWE message.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": wallet.lower(),
        "wallet": wallet,
        "chain_id": chain_id,
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=expires_days)).timestamp()),
    }
    return jwt.encode(payload, _get_secret(), algorithm=_ALGORITHM)


def verify_token(token: str, expected_type: str = "access") -> TokenPayload:
    """Verify and decode a JWT token.

    Parameters
    ----------
    token:
        The raw JWT string.
    expected_type:
        Either ``"access"`` or ``"refresh"``.

    Returns
    -------
    TokenPayload
        Decoded payload with wallet, chain_id, tier, etc.

    Raises
    ------
    ValueError
        If the token is invalid, expired, or has the wrong type.
    """
    try:
        payload = jwt.decode(token, _get_secret(), algorithms=[_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired")
    except jwt.InvalidTokenError as e:
        raise ValueError(f"Invalid token: {e}")

    token_type = payload.get("type", "access")
    if token_type != expected_type:
        raise ValueError(f"Expected {expected_type} token, got {token_type}")

    return TokenPayload(
        wallet=payload.get("wallet", ""),
        chain_id=payload.get("chain_id", 137),
        tier=payload.get("tier", "BASIC"),
        issued_at=payload.get("iat", 0),
        expires_at=payload.get("exp", 0),
        token_type=token_type,
    )
