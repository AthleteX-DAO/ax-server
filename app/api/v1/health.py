"""Health-check endpoint.

Returns server status and chain connectivity information.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import get_settings

router = APIRouter(tags=["health"])


class ChainStatus(BaseModel):
    chain_id: int
    rpc_url: str
    connected: bool
    block_number: int | None = None
    latency_ms: float | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    uptime_seconds: float
    chain: ChainStatus


_start_time = time.time()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> dict[str, Any]:
    """Return server health and chain connection status.

    Attempts to call eth_blockNumber on the configured RPC to verify
    the chain connection is alive.
    """
    settings = get_settings()
    chain_id = settings.default_chain_id
    rpc_url = settings.rpc_url_for_chain(chain_id)

    connected = False
    block_number = None
    latency_ms = None

    try:
        from web3 import Web3

        t0 = time.time()
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        block_number = w3.eth.block_number
        latency_ms = round((time.time() - t0) * 1000, 2)
        connected = True
    except Exception:
        connected = False

    return {
        "status": "healthy" if connected else "degraded",
        "version": "0.1.0",
        "uptime_seconds": round(time.time() - _start_time, 2),
        "chain": ChainStatus(
            chain_id=chain_id,
            rpc_url=rpc_url,
            connected=connected,
            block_number=block_number,
            latency_ms=latency_ms,
        ),
    }
