"""Position endpoints — query user positions across protocols."""

from __future__ import annotations

from fastapi import APIRouter

from app.models.position import Position, PositionSummary

router = APIRouter(prefix="/positions", tags=["positions"])


@router.get("/{address}", response_model=PositionSummary)
async def get_positions(address: str):
    """Return all positions for a given wallet address.

    Aggregates across:
    - Synthetix V3 collateral / delegation positions
    - Spot synth balances
    - Uniswap V2 LP positions
    - UMA prediction market positions

    Future: Uses Multicall3 to batch-read positions in a single RPC call.
    """
    # TODO: Wire to chain layer with multicall batching
    return PositionSummary(
        address=address,
        total_value_usd=0.0,
        positions=[],
    )
