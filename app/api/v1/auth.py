"""Auth endpoints — SIWE sign-in flow.

Implements the full EIP-4361 authentication flow:

1. ``GET  /auth/nonce``   → client gets a fresh nonce
2. ``POST /auth/verify``  → client submits signed SIWE message, gets JWT
3. ``POST /auth/refresh`` → exchange refresh token for new access token
4. ``GET  /auth/me``      → return current session info (requires auth)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel
from web3 import Web3

from app.auth.siwe import build_siwe_message, verify_siwe, nonce_store
from app.auth.tokens import create_access_token, create_refresh_token, verify_token
from app.auth.deps import RequireAuth, RequireAuthFull
from app.middleware.errors import APIError
from app.middleware.rate_limit import RateLimitMiddleware, RateTier

logger = logging.getLogger("ax-server.auth")

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Request / Response Models ───────────────────────────────────────────


class NonceResponse(BaseModel):
    """Fresh nonce for SIWE message signing."""

    nonce: str


class SIWEMessageRequest(BaseModel):
    """Request to build a SIWE message for signing."""

    address: str
    chain_id: int = 137


class SIWEMessageResponse(BaseModel):
    """SIWE message ready for wallet signing."""

    message: str
    nonce: str


class VerifyRequest(BaseModel):
    """Signed SIWE message for verification."""

    message: str
    signature: str


class AuthTokenResponse(BaseModel):
    """JWT tokens returned after successful SIWE verification."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int  # seconds
    wallet: str
    tier: str


class RefreshRequest(BaseModel):
    """Refresh token exchange."""

    refresh_token: str


class SessionInfo(BaseModel):
    """Current session information."""

    wallet: str
    chain_id: int
    tier: str
    authenticated: bool = True


# ── Endpoints ───────────────────────────────────────────────────────────


@router.get("/nonce", response_model=NonceResponse)
async def get_nonce() -> NonceResponse:
    """Generate a fresh nonce for SIWE message signing.

    The nonce is single-use and expires after 5 minutes.
    The client must include this nonce in their EIP-4361 message.
    """
    nonce = nonce_store.generate()
    return NonceResponse(nonce=nonce)


@router.post("/message", response_model=SIWEMessageResponse)
async def build_message(body: SIWEMessageRequest) -> SIWEMessageResponse:
    """Build a ready-to-sign EIP-4361 SIWE message.

    Convenience endpoint — the client can also construct the message
    themselves following the EIP-4361 spec. This endpoint ensures the
    message is correctly formatted.

    Returns the message string and the embedded nonce.
    """
    # Validate address
    if not Web3.is_address(body.address):
        raise APIError(
            code="INVALID_WALLET_ADDRESS",
            message=f"Invalid Ethereum address: {body.address}",
            status_code=400,
        )

    address = Web3.to_checksum_address(body.address)
    nonce = nonce_store.generate()

    message = build_siwe_message(
        address=address,
        nonce=nonce,
        chain_id=body.chain_id,
    )

    return SIWEMessageResponse(message=message, nonce=nonce)


@router.post("/verify", response_model=AuthTokenResponse)
async def verify_signature(body: VerifyRequest) -> AuthTokenResponse:
    """Verify a signed SIWE message and issue JWT tokens.

    The client signs the EIP-4361 message with their wallet and submits
    the message + signature here. On success, receives:

    - **access_token**: Short-lived (24h) JWT for API access
    - **refresh_token**: Long-lived (30d) JWT for token renewal

    The access token upgrades the user's rate-limit tier from BASIC
    to ADVANCED (5x more requests).
    """
    try:
        wallet = verify_siwe(
            message=body.message,
            signature=body.signature,
        )
    except ValueError as e:
        raise APIError(
            code="AUTH_INVALID",
            message=f"SIWE verification failed: {e}",
            status_code=401,
        )

    # Issue tokens
    tier = "ADVANCED"  # authenticated users get ADVANCED tier
    access_token = create_access_token(wallet=wallet, tier=tier)
    refresh_token = create_refresh_token(wallet=wallet)

    # Upgrade rate-limit tier for this wallet
    # (The middleware will check JWT on subsequent requests)
    logger.info("Authenticated wallet %s — tier upgraded to %s", wallet, tier)

    return AuthTokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=24 * 3600,  # 24 hours in seconds
        wallet=wallet,
        tier=tier,
    )


@router.post("/refresh", response_model=AuthTokenResponse)
async def refresh_access_token(body: RefreshRequest) -> AuthTokenResponse:
    """Exchange a refresh token for a new access token.

    The refresh token must be valid and not expired (30-day lifetime).
    A new access token is issued with the same tier.
    """
    try:
        payload = verify_token(body.refresh_token, expected_type="refresh")
    except ValueError as e:
        raise APIError(
            code="AUTH_INVALID",
            message=f"Invalid refresh token: {e}",
            status_code=401,
        )

    tier = "ADVANCED"
    access_token = create_access_token(
        wallet=payload.wallet,
        chain_id=payload.chain_id,
        tier=tier,
    )
    # Issue a new refresh token too (token rotation)
    new_refresh = create_refresh_token(
        wallet=payload.wallet,
        chain_id=payload.chain_id,
    )

    return AuthTokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        expires_in=24 * 3600,
        wallet=payload.wallet,
        tier=tier,
    )


@router.get("/me", response_model=SessionInfo)
async def get_session(auth: RequireAuthFull) -> SessionInfo:
    """Return current session info for the authenticated user.

    Requires a valid access token in the ``Authorization: Bearer <token>`` header.
    """
    return SessionInfo(
        wallet=auth.wallet,
        chain_id=auth.chain_id,
        tier=auth.tier,
    )
