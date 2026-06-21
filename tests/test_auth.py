"""Tests for SIWE authentication flow.

Tests the full auth lifecycle: nonce generation, SIWE message building,
signature verification, JWT issuance, token refresh, and protected endpoints.

Run: cd /home/boltik/code/ax-server && python -m pytest tests/test_auth.py -v
"""

from __future__ import annotations

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from httpx import ASGITransport, AsyncClient

from app.main import app


# Generate a test wallet for signing
_TEST_KEY = "0x" + "ab" * 32
_TEST_ACCOUNT = Account.from_key(_TEST_KEY)
_TEST_WALLET = _TEST_ACCOUNT.address


# ── Nonce ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_nonce():
    """Nonce endpoint should return a hex nonce."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/auth/nonce")
    assert resp.status_code == 200
    data = resp.json()
    assert "nonce" in data
    assert len(data["nonce"]) == 32  # 16 bytes hex


@pytest.mark.asyncio
async def test_nonce_is_unique():
    """Each nonce call should return a different value."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r1 = await client.get("/api/v1/auth/nonce")
        r2 = await client.get("/api/v1/auth/nonce")
    assert r1.json()["nonce"] != r2.json()["nonce"]


# ── Build Message ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_build_message():
    """Message endpoint should return an EIP-4361 message."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/message",
            json={"address": _TEST_WALLET, "chain_id": 137},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "message" in data
    assert "nonce" in data
    assert _TEST_WALLET in data["message"]
    assert "athletex.io" in data["message"]
    assert "Chain ID: 137" in data["message"]


@pytest.mark.asyncio
async def test_build_message_invalid_address():
    """Should reject invalid addresses."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/auth/message",
            json={"address": "not-an-address"},
        )
    assert resp.status_code == 400


# ── Full SIWE Flow ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_full_siwe_flow():
    """End-to-end: get message → sign → verify → receive JWT."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Step 1: Build message
        msg_resp = await client.post(
            "/api/v1/auth/message",
            json={"address": _TEST_WALLET, "chain_id": 137},
        )
        assert msg_resp.status_code == 200
        message = msg_resp.json()["message"]

        # Step 2: Sign with test wallet
        signable = encode_defunct(text=message)
        signed = _TEST_ACCOUNT.sign_message(signable)
        signature = signed.signature.hex()

        # Step 3: Verify
        verify_resp = await client.post(
            "/api/v1/auth/verify",
            json={"message": message, "signature": signature},
        )
        assert verify_resp.status_code == 200
        tokens = verify_resp.json()
        assert "access_token" in tokens
        assert "refresh_token" in tokens
        assert tokens["wallet"] == _TEST_WALLET
        assert tokens["tier"] == "ADVANCED"
        assert tokens["token_type"] == "Bearer"

        # Step 4: Use access token
        me_resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        assert me_resp.status_code == 200
        session = me_resp.json()
        assert session["wallet"] == _TEST_WALLET
        assert session["authenticated"] is True


# ── Token Refresh ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_token_refresh():
    """Refresh token should issue a new access token."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Full sign-in first
        msg_resp = await client.post(
            "/api/v1/auth/message",
            json={"address": _TEST_WALLET},
        )
        message = msg_resp.json()["message"]
        signable = encode_defunct(text=message)
        signed = _TEST_ACCOUNT.sign_message(signable)

        verify_resp = await client.post(
            "/api/v1/auth/verify",
            json={"message": message, "signature": signed.signature.hex()},
        )
        tokens = verify_resp.json()

        # Refresh
        refresh_resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )
        assert refresh_resp.status_code == 200
        new_tokens = refresh_resp.json()
        assert "access_token" in new_tokens
        assert "refresh_token" in new_tokens
        assert new_tokens["wallet"] == _TEST_WALLET
        assert new_tokens["tier"] == "ADVANCED"


# ── Protected Endpoint ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_me_requires_auth():
    """GET /auth/me should return 401 without a token."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    assert resp.json()["code"] == "AUTH_REQUIRED"


@pytest.mark.asyncio
async def test_me_rejects_bad_token():
    """GET /auth/me should return 401 with an invalid token."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid.jwt.token"},
        )
    assert resp.status_code == 401


# ── Verify Failures ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verify_bad_signature():
    """Verify should reject an incorrect signature."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        msg_resp = await client.post(
            "/api/v1/auth/message",
            json={"address": _TEST_WALLET},
        )
        message = msg_resp.json()["message"]

        resp = await client.post(
            "/api/v1/auth/verify",
            json={"message": message, "signature": "0x" + "00" * 65},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_verify_reused_nonce():
    """Nonce should be single-use — second verify with same message should fail."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        msg_resp = await client.post(
            "/api/v1/auth/message",
            json={"address": _TEST_WALLET},
        )
        message = msg_resp.json()["message"]
        signable = encode_defunct(text=message)
        signed = _TEST_ACCOUNT.sign_message(signable)
        sig = signed.signature.hex()

        # First verify — should succeed
        r1 = await client.post("/api/v1/auth/verify", json={"message": message, "signature": sig})
        assert r1.status_code == 200

        # Second verify — nonce consumed, should fail
        r2 = await client.post("/api/v1/auth/verify", json={"message": message, "signature": sig})
        assert r2.status_code == 401
