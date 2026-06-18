"""Tests for the health endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_returns_200():
    """Health endpoint should return 200 even if chain is unreachable."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["version"] == "0.1.0"
    assert "chain" in data
    assert data["status"] in ("healthy", "degraded")


@pytest.mark.asyncio
async def test_health_chain_fields():
    """Chain status should include expected fields."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/health")
    chain = resp.json()["chain"]
    assert "chain_id" in chain
    assert "rpc_url" in chain
    assert "connected" in chain


@pytest.mark.asyncio
async def test_markets_returns_list():
    """Markets endpoint should return an empty list (skeleton)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/markets")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_positions_returns_summary():
    """Positions endpoint should return a summary for any address."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/positions/0x1234567890abcdef1234567890abcdef12345678")
    assert resp.status_code == 200
    data = resp.json()
    assert data["address"] == "0x1234567890abcdef1234567890abcdef12345678"
    assert data["total_value_usd"] == 0.0
    assert data["positions"] == []


@pytest.mark.asyncio
async def test_agent_status():
    """Agent status endpoint should return empty agent list."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/agent/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["agents"] == []
    assert data["active_tasks"] == 0
