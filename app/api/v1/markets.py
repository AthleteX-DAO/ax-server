"""Market endpoints — list and inspect athlete / prediction markets."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.market import MarketSummary, MarketDetail

router = APIRouter(prefix="/markets", tags=["markets"])


@router.get("", response_model=list[MarketSummary])
async def list_markets(
    market_type: str | None = None,
    sport: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """Return a paginated list of available markets.

    Filters:
        market_type: spot | perp | prediction
        sport: nfl | nba | mlb | ...
    Future: queries SpotMarketProxy for synth markets and UMA for prediction markets.
    """
    # TODO: Wire to chain/synthetix.py and chain/uma.py
    return []


@router.get("/{market_id}", response_model=MarketDetail)
async def get_market(market_id: str):
    """Return detailed information for a single market.

    Includes current price, liquidity, open interest, oracle info.
    Future: fetches on-chain state via SpotMarketProxy + OracleManager.
    """
    # TODO: Fetch from chain
    raise HTTPException(status_code=404, detail=f"Market {market_id} not found")
