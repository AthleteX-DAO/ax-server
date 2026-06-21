"""Tests for the new ax-server endpoints: exchange, portfolio, orders, errors.

Uses httpx AsyncClient + ASGITransport for in-process FastAPI testing.
Run: cd /home/boltik/code/ax-server && python -m pytest tests/test_exchange_api.py -v
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


# ── Exchange Status ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_exchange_status_returns_200():
    """Exchange status should return 200 with chain info."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/exchange/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "exchange_active" in data
    assert "chain_id" in data
    assert "contracts" in data
    assert "timestamp" in data
    assert data["chain_id"] == 137  # Polygon mainnet


@pytest.mark.asyncio
async def test_exchange_status_has_contracts():
    """Exchange status should list deployed contract addresses."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/exchange/status")
    contracts = resp.json()["contracts"]
    assert "core_proxy" in contracts
    assert "spot_market_proxy" in contracts
    assert "axusd_proxy" in contracts
    # Addresses should be checksummed 0x...
    assert contracts["core_proxy"].startswith("0x")


# ── Portfolio Balance ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_portfolio_balance_valid_wallet():
    """Balance endpoint should return structured balance for a valid wallet."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/portfolio/balance",
            params={"wallet": "0x1234567890abcdef1234567890abcdef12345678"},
        )
    # May return 200 (if RPC works) or 502 (if chain call fails)
    assert resp.status_code in (200, 502)
    if resp.status_code == 200:
        data = resp.json()
        assert "wallet" in data
        assert "ax" in data
        assert "axusd" in data
        assert "matic" in data


@pytest.mark.asyncio
async def test_portfolio_balance_invalid_wallet():
    """Balance endpoint should return 400 for invalid wallet address."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/portfolio/balance",
            params={"wallet": "not-a-real-address"},
        )
    assert resp.status_code == 400
    data = resp.json()
    assert data["code"] == "INVALID_WALLET_ADDRESS"
    assert data["service"] == "athletex"


@pytest.mark.asyncio
async def test_portfolio_balance_missing_wallet():
    """Balance endpoint should return 422 when wallet param is missing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/portfolio/balance")
    assert resp.status_code == 422  # FastAPI validation error


# ── Portfolio Positions ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_portfolio_positions_valid_wallet():
    """Positions endpoint should return a list of positions."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/portfolio/positions",
            params={"wallet": "0x1234567890abcdef1234567890abcdef12345678"},
        )
    assert resp.status_code in (200, 502)
    if resp.status_code == 200:
        data = resp.json()
        assert "wallet" in data
        assert "positions" in data
        assert isinstance(data["positions"], list)


@pytest.mark.asyncio
async def test_portfolio_positions_invalid_wallet():
    """Positions endpoint should return structured error for invalid address."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/portfolio/positions",
            params={"wallet": "xyz"},
        )
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_WALLET_ADDRESS"


# ── Orders — Build Buy ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_build_buy_invalid_wallet():
    """Build buy should reject invalid wallet address."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/orders/build-buy",
            json={
                "market_id": 1,
                "usd_amount": "1000000000000000000",
                "wallet": "bad-address",
            },
        )
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_WALLET_ADDRESS"


@pytest.mark.asyncio
async def test_build_buy_invalid_amount():
    """Build buy should reject non-positive amount."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/orders/build-buy",
            json={
                "market_id": 1,
                "usd_amount": "0",
                "wallet": "0x1234567890abcdef1234567890abcdef12345678",
            },
        )
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_AMOUNT"


@pytest.mark.asyncio
async def test_build_buy_negative_amount():
    """Build buy should reject negative amount string."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/orders/build-buy",
            json={
                "market_id": 1,
                "usd_amount": "-100",
                "wallet": "0x1234567890abcdef1234567890abcdef12345678",
            },
        )
    assert resp.status_code == 400


# ── Orders — Build Sell ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_build_sell_invalid_wallet():
    """Build sell should reject invalid wallet."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/orders/build-sell",
            json={
                "market_id": 1,
                "synth_amount": "1000000000000000000",
                "wallet": "not-valid",
            },
        )
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_WALLET_ADDRESS"


# ── Orders — Build Approve ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_build_approve_invalid_addresses():
    """Build approve should validate all address fields."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/orders/build-approve",
            json={
                "token_address": "bad",
                "spender": "0x1234567890abcdef1234567890abcdef12345678",
                "amount": "1000000000000000000",
                "wallet": "0x1234567890abcdef1234567890abcdef12345678",
            },
        )
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_WALLET_ADDRESS"


# ── Error Format ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_404_returns_error():
    """Non-existent routes should return 404 with error body."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/nonexistent")
    # FastAPI returns 404 with {detail: "Not Found"} for unregistered routes
    assert resp.status_code in (404, 405)
    data = resp.json()
    # Either our structured format or FastAPI's default
    assert "code" in data or "detail" in data


@pytest.mark.asyncio
async def test_error_response_shape():
    """All error responses should match {code, message, service} format."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/portfolio/balance",
            params={"wallet": "invalid"},
        )
    data = resp.json()
    assert "code" in data
    assert "message" in data
    assert "service" in data
    assert data["service"] == "athletex"


# ── Rate Limit Headers ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rate_limit_headers_present():
    """All responses should include rate-limit headers."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/exchange/status")
    # Rate limit middleware should add these headers
    assert "x-ratelimit-limit" in resp.headers or resp.status_code == 429
