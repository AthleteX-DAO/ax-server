"""Tests for history API endpoints and cursor-paginated spot markets.

Tests cover the history endpoints (candles, trades, price) and the
new cursor pagination on GET /spot/markets. QuestDB is not available
in test mode, so history endpoints should gracefully return empty data.

Run: cd /home/boltik/code/ax-server && python -m pytest tests/test_history.py -v
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


# ── History Candles ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_candles_endpoint_returns_200():
    """Candles endpoint should return 200 even without QuestDB."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/history/candles/1",
            params={"timeframe": "1h", "market_type": "spot"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["market_id"] == "1"
    assert data["timeframe"] == "1h"
    assert "candles" in data
    assert isinstance(data["candles"], list)


@pytest.mark.asyncio
async def test_candles_invalid_timeframe():
    """Should reject invalid timeframes."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/history/candles/1",
            params={"timeframe": "2h"},
        )
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_TIMEFRAME"


@pytest.mark.asyncio
async def test_candles_all_valid_timeframes():
    """All supported timeframes should be accepted."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for tf in ["1m", "5m", "15m", "1h", "4h", "1d"]:
            resp = await client.get(
                "/api/v1/history/candles/1",
                params={"timeframe": tf},
            )
            assert resp.status_code == 200, f"Failed for timeframe={tf}"


@pytest.mark.asyncio
async def test_candles_with_time_range():
    """Should accept ISO-8601 and unix timestamp formats."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/history/candles/axBTC",
            params={
                "timeframe": "1d",
                "start": "2025-01-01",
                "end": "2025-01-31",
            },
        )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_candles_with_unix_timestamps():
    """Should accept plain unix timestamps."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/history/candles/1",
            params={"start": "1704067200", "end": "1706745600"},
        )
    assert resp.status_code == 200


# ── History Trades ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_trades_endpoint_returns_200():
    """Trades endpoint should return 200 with empty list when no QuestDB."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/history/trades/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["market_id"] == "1"
    assert isinstance(data["trades"], list)


@pytest.mark.asyncio
async def test_trades_with_limit():
    """Limit parameter should be accepted."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/history/trades/1",
            params={"limit": 50},
        )
    assert resp.status_code == 200


# ── History Latest Price ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_latest_price_returns_503_without_questdb():
    """Latest price should return 503 when QuestDB is unavailable."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/history/price/1")
    assert resp.status_code == 503
    assert resp.json()["code"] == "SERVICE_UNAVAILABLE"


# ── Perps Stubs ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_perps_candles_stub():
    """Perps candle stub should return 200 with empty candles."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/history/perps/candles/BTC-PERP")
    assert resp.status_code == 200
    data = resp.json()
    assert data["market_type"] == "perps"
    assert data["candles"] == []


@pytest.mark.asyncio
async def test_perps_funding_stub():
    """Perps funding stub should return 200 with a message."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/history/perps/funding/BTC-PERP")
    assert resp.status_code == 200
    data = resp.json()
    assert "funding_rates" in data
    assert data["funding_rates"] == []


# ── Spot Cursor Pagination ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_spot_markets_returns_paginated():
    """GET /spot/markets should return paginated response shape."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/spot/markets")
    assert resp.status_code == 200
    data = resp.json()
    assert "markets" in data
    assert isinstance(data["markets"], list)
    assert "has_more" in data
    # next_cursor can be None or a string


@pytest.mark.asyncio
async def test_spot_markets_with_cursor():
    """Passing a cursor should be accepted."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/spot/markets",
            params={"cursor": 5, "limit": 3},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "markets" in data


@pytest.mark.asyncio
async def test_spot_markets_limit_respected():
    """Limit parameter should cap the number of results."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/spot/markets",
            params={"limit": 1},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["markets"]) <= 1
