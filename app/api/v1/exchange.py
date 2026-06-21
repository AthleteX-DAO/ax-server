"""Exchange status endpoint — real-time health and chain state.

Returns exchange connectivity, block number, RPC latency, and deployed
contract addresses. Modelled after Kalshi /exchange/status.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import get_settings
from app.deps import ChainProviderDep

logger = logging.getLogger("ax-server.exchange")

router = APIRouter(prefix="/exchange", tags=["exchange"])


# ── Response Models ─────────────────────────────────────────────────────


class ContractAddresses(BaseModel):
    """Deployed contract addresses."""

    core_proxy: str
    spot_market_proxy: str
    axusd_proxy: str


class ExchangeStatus(BaseModel):
    """Top-level exchange status response."""

    exchange_active: bool
    trading_active: bool
    chain_id: int
    block_number: int | None = None
    rpc_latency_ms: float | None = None
    contracts: ContractAddresses
    timestamp: str


# ── Endpoint ────────────────────────────────────────────────────────────


@router.get("/status", response_model=ExchangeStatus)
async def get_exchange_status(chain: ChainProviderDep) -> ExchangeStatus:
    """Return exchange health, chain state, and deployed contract addresses.

    Performs a live eth_blockNumber call to verify RPC connectivity and
    measure latency. Returns ``exchange_active: false`` if the RPC is
    unreachable.
    """
    settings = get_settings()

    exchange_active = False
    trading_active = False
    block_number: int | None = None
    rpc_latency_ms: float | None = None

    try:
        w3 = chain.w3
        t0 = time.perf_counter()
        block_number = w3.eth.block_number
        rpc_latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        exchange_active = True
        trading_active = True
    except Exception:
        logger.exception("RPC health check failed")

    return ExchangeStatus(
        exchange_active=exchange_active,
        trading_active=trading_active,
        chain_id=settings.default_chain_id,
        block_number=block_number,
        rpc_latency_ms=rpc_latency_ms,
        contracts=ContractAddresses(
            core_proxy=settings.addresses.core_proxy,
            spot_market_proxy=settings.addresses.spot_market_proxy,
            axusd_proxy=settings.addresses.usd_proxy,
        ),
        timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
