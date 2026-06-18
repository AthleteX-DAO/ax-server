"""Spot Market endpoints — Synthetix V3 SpotMarketProxy reads.

L0 (public): market list, prices, quotes.
L2 (auth):   balances, buy/sell tx builders (Phase 3).
"""

from __future__ import annotations

from fastapi import APIRouter, Query
from web3 import Web3

from app.deps import ChainProviderDep
from app.models.trading import SpotMarket, SpotPrice, SpotQuote

router = APIRouter(prefix="/spot", tags=["spot"])


@router.get("/markets", response_model=list[SpotMarket])
async def list_spot_markets(chain: ChainProviderDep):
    """List all synth markets on SpotMarketProxy."""
    from app.chain.synthetix import SynthetixClient

    snx = SynthetixClient(chain.w3, chain._rpc_urls)  # noqa: will fix DI
    # Known market IDs — extend as new synths are registered
    # TODO: read from on-chain registry or config
    known_ids = [1, 2, 3, 4, 5]
    markets = []
    for mid in known_ids:
        try:
            info = await snx.get_synth_market_info(mid)
            markets.append(SpotMarket(
                market_id=mid,
                name=info.get("name", f"Synth {mid}"),
                synth_address=info.get("synth_address", ""),
            ))
        except Exception:
            continue
    return markets


@router.get("/markets/{market_id}/price", response_model=SpotPrice)
async def get_spot_price(market_id: int, chain: ChainProviderDep):
    """Current buy/sell price for a synth market."""
    w3 = chain.w3
    from app.chain.contracts import get_contract

    spot = get_contract(w3, "0xc79eC919a0A20E29873143AB9658aF75C0b73A23", "spot_market_proxy")

    # indexPrice returns (uint256 price) — 18 decimals
    try:
        buy_price = spot.functions.indexPrice(market_id).call()
        sell_price = buy_price  # spot buy/sell spread handled by fees
        price_float = buy_price / 1e18
    except Exception:
        price_float = 0.0

    return SpotPrice(
        market_id=market_id,
        buy_price=price_float,
        sell_price=price_float,
        timestamp=w3.eth.get_block("latest")["timestamp"],
    )


@router.get("/markets/{market_id}/quote", response_model=SpotQuote)
async def get_spot_quote(
    market_id: int,
    side: str = Query(..., pattern="^(buy|sell)$"),
    amount: str = Query(..., description="Amount in wei"),
    chain: ChainProviderDep = None,
):
    """Quote: given amount in, how much out (buy synth or sell synth)."""
    w3 = chain.w3
    from app.chain.contracts import get_contract

    spot = get_contract(w3, "0xc79eC919a0A20E29873143AB9658aF75C0b73A23", "spot_market_proxy")
    amount_wei = int(amount)

    try:
        if side == "buy":
            # quoteBuyExactIn(marketId, usdAmount) -> (synthAmount, fees)
            result = spot.functions.quoteBuyExactIn(market_id, amount_wei).call()
            amount_out, fees = str(result[0]), str(result[1])
        else:
            # quoteSellExactIn(marketId, synthAmount) -> (usdAmount, fees)
            result = spot.functions.quoteSellExactIn(market_id, amount_wei).call()
            amount_out, fees = str(result[0]), str(result[1])
    except Exception:
        amount_out, fees = "0", "0"

    return SpotQuote(
        market_id=market_id,
        side=side,
        amount_in=amount,
        amount_out=amount_out,
        fee=fees,
    )
