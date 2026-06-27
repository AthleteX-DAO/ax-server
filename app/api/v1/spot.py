"""Spot Market endpoints — Synthetix V3 SpotMarketProxy reads.

L0 (public): market list (cursor-paginated), prices, quotes.
L2 (auth):   balances, buy/sell tx builders (Phase 3).
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.deps import SynthetixClientDep
from app.models.trading import SpotMarket, SpotPrice, SpotQuote

router = APIRouter(prefix="/spot", tags=["spot"])

# ── Pagination Models ───────────────────────────────────────────────────

_MAX_MARKET_SCAN = 50  # upper bound for market ID scan


class PaginatedMarkets(BaseModel):
    """Cursor-paginated list of spot markets."""

    markets: list[SpotMarket]
    next_cursor: str | None = None
    has_more: bool = False


# ── Endpoints ───────────────────────────────────────────────────────────


@router.get("/markets", response_model=PaginatedMarkets)
async def list_spot_markets(
    snx: SynthetixClientDep,
    cursor: int | None = Query(None, ge=0, description="Last market_id seen (start after this)"),
    limit: int = Query(20, ge=1, le=100, description="Max markets to return"),
):
    """List synth markets with cursor-based pagination.

    Pass the ``next_cursor`` value from the response as ``cursor`` in
    the next request to get the next page.

    Examples::

        GET /spot/markets              → first 20 markets
        GET /spot/markets?limit=5      → first 5 markets
        GET /spot/markets?cursor=5     → markets after ID 5
    """
    start_id = (cursor + 1) if cursor is not None else 1
    markets: list[SpotMarket] = []
    consecutive_misses = 0
    last_found_id: int | None = None

    for mid in range(start_id, start_id + _MAX_MARKET_SCAN):
        if len(markets) >= limit:
            break

        try:
            name = snx.get_synth_market_name(mid)
            synth_address = snx.get_synth_address(mid)
            markets.append(SpotMarket(
                market_id=mid,
                name=name or f"Synth {mid}",
                synth_address=synth_address or "",
            ))
            last_found_id = mid
            consecutive_misses = 0
        except Exception:
            consecutive_misses += 1
            # Stop scanning after 5 consecutive misses (no more markets)
            if consecutive_misses >= 5:
                break
            continue

    # Determine if there are more markets
    has_more = len(markets) >= limit and consecutive_misses < 5
    next_cursor = str(last_found_id) if has_more and last_found_id is not None else None

    return PaginatedMarkets(
        markets=markets,
        next_cursor=next_cursor,
        has_more=has_more,
    )


class BatchPriceEntry(BaseModel):
    price: str
    timestamp: int

class BatchPricesResponse(BaseModel):
    prices: dict[str, BatchPriceEntry]

@router.get("/markets/prices", response_model=BatchPricesResponse)
async def get_batch_prices(snx: SynthetixClientDep) -> BatchPricesResponse:
    """Get prices for all spot markets in a single call."""
    prices = {}
    # Try market IDs 1-15
    for mid in range(1, 16):
        try:
            price = snx.get_index_price(mid)
            timestamp = snx.w3.eth.get_block('latest')['timestamp']
            prices[str(mid)] = BatchPriceEntry(price=str(price), timestamp=timestamp)
        except Exception:
            continue
    return BatchPricesResponse(prices=prices)


@router.get("/markets/{market_id}/price", response_model=SpotPrice)
async def get_spot_price(market_id: int, snx: SynthetixClientDep):
    """Current buy/sell price for a synth market."""
    try:
        price_raw = snx.get_index_price(market_id)
        price_float = price_raw / 1e18
    except Exception:
        price_float = 0.0

    try:
        timestamp = snx.w3.eth.get_block("latest")["timestamp"]
    except Exception:
        timestamp = 0

    return SpotPrice(
        market_id=market_id,
        buy_price=price_float,
        sell_price=price_float,  # spot buy/sell spread handled by fees
        timestamp=timestamp,
    )


@router.get("/markets/{market_id}/quote", response_model=SpotQuote)
async def get_spot_quote(
    market_id: int,
    snx: SynthetixClientDep,
    side: str = Query(..., pattern="^(buy|sell)$"),
    amount: str = Query(..., description="Amount in wei"),
):
    """Quote: given amount in, how much out (buy synth or sell synth)."""
    amount_wei = int(amount)

    try:
        if side == "buy":
            result_amount, fees_dict = snx.quote_buy(market_id, amount_wei)
        else:
            result_amount, fees_dict = snx.quote_sell(market_id, amount_wei)

        amount_out = str(result_amount)
        total_fee = (
            fees_dict["fixed_fees"]
            + fees_dict["utilization_fees"]
            + abs(fees_dict["skew_fees"])
            + abs(fees_dict["wrapper_fees"])
        )
        fees = str(total_fee)
    except Exception:
        amount_out, fees = "0", "0"

    return SpotQuote(
        market_id=market_id,
        side=side,
        amount_in=amount,
        amount_out=amount_out,
        fee=fees,
    )
