"""Prediction Market endpoints — serves market data to the Flutter frontend.

L0 (public): market list, single market, prices.
L2 (auth):   positions, tx builders (Phase 3).
"""

from __future__ import annotations

import math
import random
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.models.trading import (
    Comment,
    CreateCommentRequest,
    PredictMarket,
    PredictPosition,
    PredictPrice,
    PriceHistory,
    PricePoint,
    TxResponse,
    UnsignedTx,
    PredictApproveRequest,
    PredictCreateRequest,
)

router = APIRouter(prefix="/predict", tags=["predict"])


def get_chain_provider_optional():
    """Return ChainProvider or None if unavailable."""
    try:
        from app.deps import get_settings
        from app.chain.provider import ChainProvider
        settings = get_settings()
        return ChainProvider.from_settings(settings)
    except Exception:
        return None

# ── Seed data ────────────────────────────────────────────────────────────
# Migrated from ax_dapp GetPredictionMarketDataUseCase._buildMockPredictionMarkets
# so the frontend can fetch from a single source of truth.

_MARKETS: list[dict] = [
    {"id": 1, "prompt": "who will win superbowl 2026",
     "details": "Projected championship odds for the 2026 Super Bowl field.",
     "category": "football", "end_date": "2026-02-08"},
    {"id": 2, "prompt": "who will win the fifa world cup",
     "details": "Outright winner market for the 2026 FIFA World Cup.",
     "category": "soccer", "end_date": "2026-07-19"},
    {"id": 3, "prompt": "who will win the Winter Olympics",
     "details": "Overall medal table leader for the 2026 Winter Games.",
     "category": "exotic", "end_date": "2026-02-22"},
    {"id": 4, "prompt": "NFL Playoffs Bracket Set",
     "details": "Market on the final AFC/NFC playoff bracket seeding.",
     "category": "football", "end_date": "2026-01-05"},
    {"id": 5, "prompt": "2026 NBA Finals MVP",
     "details": "MVP honors for the 2026 NBA Finals series.",
     "category": "basketball", "end_date": "2026-06-25"},
    {"id": 6, "prompt": "2026 NBA Finals Champion",
     "details": "Outright winner for the 2026 NBA title.",
     "category": "basketball", "end_date": "2026-06-20"},
    {"id": 7, "prompt": "2026 World Series Winner",
     "details": "Which club lifts the Commissioner's Trophy in 2026.",
     "category": "baseball", "end_date": "2026-11-05"},
    {"id": 8, "prompt": "2026 Stanley Cup Champion",
     "details": "NHL postseason futures for the 2026 Stanley Cup.",
     "category": "hockey", "end_date": "2026-06-15"},
    {"id": 9, "prompt": "2026 March Madness Champion",
     "details": "Who cuts down the nets at the 2026 NCAA tournament.",
     "category": "college", "end_date": "2026-04-06"},
    {"id": 10, "prompt": "2026 College Football Champion",
     "details": "CFP title odds for the 2026 season.",
     "category": "college", "end_date": "2026-01-12"},
    {"id": 11, "prompt": "2026 UEFA Champions League Winner",
     "details": "Outright UCL winner for the 2025/26 campaign.",
     "category": "soccer", "end_date": "2026-05-31"},
    {"id": 12, "prompt": "2026 Copa America Winner",
     "details": "Champion of the expanded 2026 Copa America field.",
     "category": "soccer", "end_date": "2026-07-12"},
    {"id": 13, "prompt": "2026 Formula 1 Constructors Champion",
     "details": "Team standings futures for the 2026 F1 season.",
     "category": "exotic", "end_date": "2026-12-01"},
    {"id": 14, "prompt": "2026 Wimbledon Women's Champion",
     "details": "Ladies' singles outright at Wimbledon 2026.",
     "category": "exotic", "end_date": "2026-07-11"},
    {"id": 15, "prompt": "2026 US Open Men's Champion",
     "details": "Mens singles outright at Flushing Meadows 2026.",
     "category": "exotic", "end_date": "2026-09-13"},
    {"id": 16, "prompt": "Community pick: shorten shot clock to 22s?",
     "details": "Community governance vote on pro basketball shot clocks.",
     "category": "voted", "end_date": "2026-03-15"},
    {"id": 17, "prompt": "2026 NBA Draft #1 Pick",
     "details": "Who goes first overall in the 2026 NBA Draft.",
     "category": "basketball", "end_date": "2026-06-10"},
    {"id": 18, "prompt": "2026 AL MVP Winner",
     "details": "American League MVP honors for the 2026 season.",
     "category": "baseball", "end_date": "2026-11-20"},
    {"id": 19, "prompt": "2026 NHL Hart Trophy Winner",
     "details": "League MVP futures for the 2025/26 NHL season.",
     "category": "hockey", "end_date": "2026-06-22"},
    {"id": 20, "prompt": "2026 NFL Offensive Rookie of the Year",
     "details": "OROY race for the incoming 2026 rookie class.",
     "category": "football", "end_date": "2027-02-10"},
    {"id": 21, "prompt": "Will the Lakers win 50+ games?",
     "details": "Regular season win total market for Los Angeles.",
     "category": "basketball", "end_date": "2026-04-15"},
    {"id": 22, "prompt": "Will the Yankees make the postseason?",
     "details": "New York Yankees playoff berth odds for 2026.",
     "category": "baseball", "end_date": "2026-10-02"},
    {"id": 23, "prompt": "Will Messi score 20+ MLS goals in 2026?",
     "details": "Goal-scoring prop for Lionel Messi's 2026 MLS season.",
     "category": "soccer", "end_date": "2026-10-20"},
    {"id": 24, "prompt": "Will Colorado reach 8+ wins?",
     "details": "Regular season win total for Colorado football.",
     "category": "college", "end_date": "2026-12-05"},
    # ── Real deployed market ─────────────────────────────────────
    {"id": 25,
     "prompt": "Will Jelly Roll and Bunnie Xo finalize their divorce by August 1, 2026?",
     "details": "Resolves YES if Jelly Roll (Jason DeFord) and Bunnie Xo have their divorce finalized by a court on or before August 1, 2026. Resolves NO otherwise.",
     "category": "exotic", "end_date": "2026-08-01",
     "market_address": "0x164c1b6e1C9F3c088D3930eDE9fCA4ea8C11Ad9F",
     "yes_token": "0xAfa41dAd6Eeb7155c2A327c4a33E4503BF172D01",
     "no_token": "0xcf3558796C2e38B3277AbEAd647B341390d3e07d",
     "live": True},
]


def _build_markets() -> list[PredictMarket]:
    """Build the full list of PredictMarket objects with default values."""
    results: list[PredictMarket] = []
    for m in _MARKETS:
        yes_price = 0.50
        no_price = 0.50
        volume = 0.0
        lifetime_volume = 0.0

        mid = m["id"]

        # Use real addresses for deployed markets, synthetic for seed data
        if "market_address" in m:
            market_address = m["market_address"]
            yes_token = m["yes_token"]
            no_token = m["no_token"]
        else:
            market_address = f"0x{mid:040X}"
            yes_token = f"0x{(mid * 2 + 1):040X}"
            no_token = f"0x{(mid * 2 + 2):040X}"

        results.append(
            PredictMarket(
                id=mid,
                prompt=m["prompt"],
                details=m["details"],
                market_address=market_address,
                yes_token_address=yes_token,
                no_token_address=no_token,
                yes_price=yes_price,
                no_price=no_price,
                trading_volume=volume,
                lifetime_volume=lifetime_volume,
                end_date=m["end_date"],
                category=m["category"],
            )
        )
    return results


# Cache so we build once per process
_CACHED_MARKETS: list[PredictMarket] | None = None


def _get_markets() -> list[PredictMarket]:
    global _CACHED_MARKETS
    if _CACHED_MARKETS is None:
        _CACHED_MARKETS = _build_markets()
    return _CACHED_MARKETS


# ── Endpoints ────────────────────────────────────────────────────────────


import json
from pathlib import Path

def _load_registry() -> list[dict]:
    registry_path = Path(__file__).resolve().parents[3] / "data" / "markets_registry.json"
    if not registry_path.exists():
        return []
    import json
    try:
        return json.loads(registry_path.read_text()).get("markets", [])
    except Exception:
        return []

@router.post("/build-approve", response_model=TxResponse)
async def build_predict_approve(
    req: PredictApproveRequest,
    chain: object = Depends(get_chain_provider_optional),
):
    """Build unsigned approve transaction for axUSD spend in a predict market."""
    if not chain:
        raise HTTPException(500, "Chain provider unavailable")
    
    # Typical axUSD address for predict
    axUsdAddress = "0x1Ea27b8fa8D9Fb4370Dd654ffFad4734D0960fA6"
    
    from web3 import Web3
    
    # simple ERC20 ABI for approve
    erc20_abi = [
        {
            "constant": False,
            "inputs": [
                {"name": "_spender", "type": "address"},
                {"name": "_value", "type": "uint256"}
            ],
            "name": "approve",
            "outputs": [{"name": "", "type": "bool"}],
            "type": "function"
        }
    ]
    
    contract = chain.w3.eth.contract(address=Web3.to_checksum_address(axUsdAddress), abi=erc20_abi)
    amount_wei = int(req.amount)
    
    # estimate gas?
    tx_data = contract.encodeABI(fn_name="approve", args=[Web3.to_checksum_address(req.market_address), amount_wei])
    
    return TxResponse(
        transaction=UnsignedTx(
            to=axUsdAddress,
            data=tx_data,
            value="0",
            chain_id=chain.w3.eth.chain_id,
        )
    )


@router.post("/build-create", response_model=TxResponse)
async def build_predict_create(
    req: PredictCreateRequest,
    chain: object = Depends(get_chain_provider_optional),
):
    """Build unsigned create transaction for a predict market."""
    if not chain:
        raise HTTPException(500, "Chain provider unavailable")
    
    from web3 import Web3
    
    market_abi = [
        {
            "inputs": [{"internalType": "uint256", "name": "tokensToCreate", "type": "uint256"}],
            "name": "create",
            "outputs": [],
            "stateMutability": "nonpayable",
            "type": "function"
        }
    ]
    
    contract = chain.w3.eth.contract(address=Web3.to_checksum_address(req.market_address), abi=market_abi)
    amount_wei = int(req.amount)
    
    tx_data = contract.encodeABI(fn_name="create", args=[amount_wei])
    
    return TxResponse(
        transaction=UnsignedTx(
            to=req.market_address,
            data=tx_data,
            value="0",
            chain_id=chain.w3.eth.chain_id,
        )
    )

async def _enrich_markets(markets: list[PredictMarket], request: Request) -> list[PredictMarket]:
    volumes = {}
    if request and hasattr(request.app.state, "questdb") and request.app.state.questdb is not None:
        try:
            volumes = await request.app.state.questdb.get_volume_stats_by_pair("predict")
        except Exception:
            pass

    registry = _load_registry()

    enriched = []
    
    # Try to get chain from request
    chain = None
    if request:
        try:
            from app.api.v1.predict import get_chain_provider_optional
            chain = get_chain_provider_optional(request)
        except Exception:
            pass

    w3 = chain.w3 if chain else None
    if w3:
        from app.chain.contracts import get_contract

    for m in markets:
        updates = {}
        rm = next((x for x in registry if x.get("market_address", "").lower() == m.market_address.lower()), None)
        
        if rm and rm.get("yes_pair_address") and rm.get("no_pair_address"):
            yes_pair_addr = rm["yes_pair_address"].lower()
            no_pair_addr = rm["no_pair_address"].lower()
            
            # 1. Volume Enrichment
            yes_stats = volumes.get(yes_pair_addr, {"24h": 0.0, "lifetime": 0.0})
            no_stats = volumes.get(no_pair_addr, {"24h": 0.0, "lifetime": 0.0})
            
            vol_24h = yes_stats["24h"] + no_stats["24h"]
            vol_lifetime = yes_stats["lifetime"] + no_stats["lifetime"]
            
            updates["trading_volume"] = round(vol_24h, 2)
            updates["lifetime_volume"] = round(vol_lifetime, 2)
            
            # 2. Price Enrichment (On-chain)
            if w3:
                try:
                    yes_pair = get_contract(w3, rm["yes_pair_address"], "uniswap_v2_pair")
                    yes_reserves = yes_pair.functions.getReserves().call()
                    yes_token0 = yes_pair.functions.token0().call()

                    if yes_token0.lower() == rm["yes_token"].lower():
                        yes_token_reserve, yes_usd_reserve = yes_reserves[0], yes_reserves[1]
                    else:
                        yes_usd_reserve, yes_token_reserve = yes_reserves[0], yes_reserves[1]

                    if yes_token_reserve > 0:
                        yes_price = round(yes_usd_reserve / yes_token_reserve, 4)
                        updates["yes_price"] = yes_price
                        updates["no_price"] = round(1 - yes_price, 4) if yes_price < 1.0 else 0.0

                    try:
                        no_pair = get_contract(w3, rm["no_pair_address"], "uniswap_v2_pair")
                        no_reserves = no_pair.functions.getReserves().call()
                        no_token0 = no_pair.functions.token0().call()

                        if no_token0.lower() == rm["no_token"].lower():
                            no_token_reserve, no_usd_reserve = no_reserves[0], no_reserves[1]
                        else:
                            no_usd_reserve, no_token_reserve = no_reserves[0], no_reserves[1]

                        if no_token_reserve > 0:
                            no_price = round(no_usd_reserve / no_token_reserve, 4)
                            updates["no_price"] = no_price
                            
                            if "yes_price" in updates:
                                total = updates["yes_price"] + updates["no_price"]
                                if total > 0:
                                    updates["yes_price"] = round(updates["yes_price"] / total, 4)
                                    updates["no_price"] = round(updates["no_price"] / total, 4)
                    except Exception:
                        pass
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).debug(f"LP price fetch failed for {m.market_address}: {e}")

        if updates:
            enriched.append(m.model_copy(update=updates))
        else:
            enriched.append(m)
            
    return enriched

@router.get("/markets", response_model=list[PredictMarket])
async def list_prediction_markets(
    request: Request,
    category: Optional[str] = Query(None, description="Filter by category"),
):
    """List all prediction markets, optionally filtered by category."""
    markets = _get_markets()
    if category:
        markets = [m for m in markets if m.category == category.lower()]
    return await _enrich_markets(markets, request)


@router.get("/markets/{market_id}", response_model=PredictMarket)
async def get_prediction_market(
    market_id: int,
    request: Request = None,
    chain: object = Depends(get_chain_provider_optional),
):
    """Get single prediction market by numeric ID."""
    for m in _get_markets():
        if m.id == market_id:
            updates = {}

            # Get enriched volume and prices
            enriched_m = (await _enrich_markets([m], request))[0]
            
            return enriched_m
    raise HTTPException(status_code=404, detail="Market not found")


@router.get("/markets/{market_id}/price", response_model=PredictPrice)
async def get_prediction_price(market_id: int):
    """YES/NO implied probability for a market."""
    for m in _get_markets():
        if m.id == market_id:
            import time
            return PredictPrice(
                market_id=str(market_id),
                yes_price=m.yes_price,
                no_price=m.no_price,
                timestamp=int(time.time()),
            )
    raise HTTPException(status_code=404, detail="Market not found")


def _generate_price_series(
    prompt: str,
    days: int,
    start_price: float,
    invert: bool = False,
) -> list[PricePoint]:
    """Generate a deterministic price series from the prompt hash."""
    from datetime import datetime, timedelta

    rng = random.Random(hash(prompt) + (1 if invert else 0))
    points: list[PricePoint] = []
    price = start_price
    now = datetime.utcnow()
    start = now - timedelta(days=days)

    for i in range(days):
        drift = (rng.random() - 0.5) * 0.08
        price = max(0.05, min(0.95, price + drift))
        adjusted = (1 - price) if invert else price
        ts = (start + timedelta(days=i)).strftime("%Y-%m-%dT%H:%M:%S")
        points.append(PricePoint(timestamp=ts, price=round(adjusted, 4)))

    return points


@router.get("/markets/{market_id}/history", response_model=PriceHistory)
async def get_prediction_history(
    market_id: int,
    request: Request,
    days: int = Query(30, ge=1, le=365, description="Number of days of history"),
):
    """Return YES/NO price history for a prediction market.

    Tries QuestDB first (real trade data), falls back to mock series.
    """

    # Resolve the market
    market = None
    for m in _get_markets():
        if m.id == market_id:
            market = m
            break
    if market is None:
        raise HTTPException(status_code=404, detail="Market not found")

    # Attempt QuestDB read
    questdb = getattr(request.app.state, "questdb", None) if request else None
    if questdb is not None:
        try:
            from datetime import datetime, timedelta

            end_ts = datetime.utcnow()
            start_ts = end_ts - timedelta(days=days)

            # Find the QuestDB market_id for this prediction market's tokens.
            # The ingest worker stores market_id as "YESSYM-axUSD" etc.
            # We query by pair_address (the LP pool address) which is more
            # reliable.  For prediction markets we look up via the registry.
            registry = _load_registry()
            yes_pair = None
            no_pair = None
            for rm in registry:
                if rm.get("contract_address", "").lower() == market.market_address.lower():
                    yes_pair = rm.get("yes_pair_address", "").lower()
                    no_pair = rm.get("no_pair_address", "").lower()
                    break

            # Also try matching on token addresses from the seed data
            if not yes_pair:
                for rm in registry:
                    if rm.get("yes_token", "").lower() == market.yes_token_address.lower():
                        yes_pair = rm.get("yes_pair_address", "").lower()
                        no_pair = rm.get("no_pair_address", "").lower()
                        break

            yes_points: list[PricePoint] = []
            no_points: list[PricePoint] = []

            if yes_pair:
                # Query trades for the YES/axUSD pair by LP pool address
                yes_candles = await questdb.get_candles_by_pair(
                    pair_address=yes_pair,
                    timeframe="1d" if days > 7 else "1h",
                    start_ts=start_ts,
                    end_ts=end_ts,
                )
                for c in yes_candles:
                    yes_points.append(PricePoint(
                        timestamp=c["ts"].strftime("%Y-%m-%dT%H:%M:%S"),
                        price=round(c["close"], 4),
                    ))

            if no_pair:
                no_candles = await questdb.get_candles_by_pair(
                    pair_address=no_pair,
                    timeframe="1d" if days > 7 else "1h",
                    start_ts=start_ts,
                    end_ts=end_ts,
                )
                for c in no_candles:
                    no_points.append(PricePoint(
                        timestamp=c["ts"].strftime("%Y-%m-%dT%H:%M:%S"),
                        price=round(c["close"], 4),
                    ))

            # Fallback: query by symbol-based market_id (e.g. "axUSD-YES")
            # This covers backfilled data where pair_address may be empty.
            if not yes_points:
                for yes_id_candidate in ["axUSD-YES", "YES-axUSD"]:
                    yes_candles = await questdb.get_candles(
                        market_id=yes_id_candidate,
                        timeframe="1d" if days > 7 else "1h",
                        start_ts=start_ts,
                        end_ts=end_ts,
                    )
                    if yes_candles:
                        for c in yes_candles:
                            yes_points.append(PricePoint(
                                timestamp=c["ts"].strftime("%Y-%m-%dT%H:%M:%S"),
                                price=round(c["close"], 4),
                            ))
                        break

            if not no_points:
                for no_id_candidate in ["axUSD-NO", "NO-axUSD"]:
                    no_candles = await questdb.get_candles(
                        market_id=no_id_candidate,
                        timeframe="1d" if days > 7 else "1h",
                        start_ts=start_ts,
                        end_ts=end_ts,
                    )
                    if no_candles:
                        for c in no_candles:
                            no_points.append(PricePoint(
                                timestamp=c["ts"].strftime("%Y-%m-%dT%H:%M:%S"),
                                price=round(c["close"], 4),
                            ))
                        break

            if yes_points or no_points:
                return PriceHistory(
                    market_id=market_id,
                    yes_history=yes_points,
                    no_history=no_points,
                )

        except Exception as _exc:
            import logging
            logging.getLogger("ax-server").warning(
                "QuestDB history query failed for market %d: %s", market_id, _exc,
            )

    # No data fallback: return empty history
    return PriceHistory(
        market_id=market_id,
        yes_history=[],
        no_history=[],
    )


# ── Stats endpoints (Vote/Dashboard page) ────────────────────────────────


@router.get("/stats/volume")
async def get_prediction_volume(request: Request):
    """24h trading volume across all prediction market pairs."""
    try:
        markets = _get_markets()
        enriched = await _enrich_markets_with_volume(markets, request)
        total_24h = sum(m.trading_volume for m in enriched)
        total_lifetime = sum(m.lifetime_volume for m in enriched)
        return {"volume_24h": total_24h, "volume_lifetime": total_lifetime, "source": "questdb"}
    except Exception:
        return {"volume_24h": 0, "source": "error"}


@router.get("/stats/trades")
async def get_prediction_trades(
    limit: int = Query(50, ge=1, le=200, description="Max trades to return"),
):
    """Recent trades across all prediction market LP pools."""
    try:
        from app.config import Settings

        settings = Settings()
        registry = _load_registry()
        if not registry:
            return {"trades": [], "source": "empty"}

        # Collect all prediction pair addresses
        pair_addresses = []
        for market in registry:
            if market.get("yes_pair_address"):
                pair_addresses.append(market["yes_pair_address"])
            if market.get("no_pair_address"):
                pair_addresses.append(market["no_pair_address"])

        if not pair_addresses:
            return {"trades": [], "source": "no_pairs"}

        # Query subgraph for recent swaps on these pairs
        import httpx

        query = """
        query RecentPredictionSwaps($pairs: [String!]!, $limit: Int!) {
          swaps(
            where: { pair_in: $pairs }
            orderBy: timestamp
            orderDirection: desc
            first: $limit
          ) {
            id
            timestamp
            sender
            amount0In
            amount1In
            amount0Out
            amount1Out
            amountUSD
            pair {
              token0 { symbol }
              token1 { symbol }
            }
          }
        }
        """
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                settings.dex_subgraph_url,
                json={
                    "query": query,
                    "variables": {"pairs": pair_addresses, "limit": limit},
                },
            )
            if resp.status_code != 200:
                return {"trades": [], "source": "subgraph_error"}

            data = resp.json().get("data", {})
            swaps = data.get("swaps", [])

        trades = []
        for s in swaps:
            pair = s.get("pair", {})
            t0 = pair.get("token0", {}).get("symbol", "")
            t1 = pair.get("token1", {}).get("symbol", "")

            # Determine side and token
            if float(s.get("amount0In", 0)) > 0:
                side = "buy" if "YES" in t1 or "NO" in t1 else "sell"
                token_symbol = t1
            else:
                side = "buy" if "YES" in t0 or "NO" in t0 else "sell"
                token_symbol = t0

            from datetime import datetime, timezone

            trades.append({
                "wallet": s.get("sender", ""),
                "side": side,
                "amount_usd": float(s.get("amountUSD", 0)),
                "price": 0,
                "timestamp": datetime.fromtimestamp(
                    int(s.get("timestamp", 0)), tz=timezone.utc,
                ).isoformat(),
                "tx_hash": s.get("id", "").split("-")[0],
                "token_symbol": token_symbol,
                "market_name": f"{t0}/{t1}",
            })

        return {"trades": trades, "source": "subgraph"}
    except Exception as e:
        import logging

        logging.getLogger("ax-server").warning("stats/trades error: %s", e)
        return {"trades": [], "source": "error"}


@router.get("/stats/leaderboard")
async def get_prediction_leaderboard(
    limit: int = Query(10, ge=1, le=50, description="Top N traders"),
):
    """Top prediction traders by volume."""
    try:
        from app.config import Settings

        settings = Settings()
        registry = _load_registry()
        if not registry:
            return {"traders": [], "source": "empty"}

        pair_addresses = []
        for market in registry:
            if market.get("yes_pair_address"):
                pair_addresses.append(market["yes_pair_address"])
            if market.get("no_pair_address"):
                pair_addresses.append(market["no_pair_address"])

        if not pair_addresses:
            return {"traders": [], "source": "no_pairs"}

        # Fetch last 500 swaps and aggregate by sender
        import httpx

        query = """
        query PredictionTraders($pairs: [String!]!) {
          swaps(
            where: { pair_in: $pairs }
            orderBy: timestamp
            orderDirection: desc
            first: 500
          ) {
            sender
            amountUSD
            timestamp
          }
        }
        """
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                settings.dex_subgraph_url,
                json={"query": query, "variables": {"pairs": pair_addresses}},
            )
            if resp.status_code != 200:
                return {"traders": [], "source": "subgraph_error"}

            data = resp.json().get("data", {})
            swaps = data.get("swaps", [])

        # Aggregate by sender
        trader_map: dict[str, dict] = {}
        for s in swaps:
            sender = s.get("sender", "").lower()
            if sender not in trader_map:
                trader_map[sender] = {
                    "wallet": sender,
                    "total_volume": 0,
                    "trade_count": 0,
                    "last_trade": s.get("timestamp", "0"),
                }
            trader_map[sender]["total_volume"] += float(
                s.get("amountUSD", 0),
            )
            trader_map[sender]["trade_count"] += 1

        # Sort by volume, take top N
        from datetime import datetime, timezone

        sorted_traders = sorted(
            trader_map.values(),
            key=lambda t: t["total_volume"],
            reverse=True,
        )[:limit]

        for t in sorted_traders:
            ts = int(t["last_trade"])
            t["last_trade"] = datetime.fromtimestamp(
                ts, tz=timezone.utc,
            ).isoformat()

        return {"traders": sorted_traders, "source": "subgraph"}
    except Exception as e:
        import logging

        logging.getLogger("ax-server").warning("stats/leaderboard error: %s", e)
        return {"traders": [], "source": "error"}


def _load_registry() -> list[dict]:
    """Load the market registry file."""
    import json
    from pathlib import Path

    registry_path = Path(__file__).resolve().parent.parent.parent.parent / "data" / "markets_registry.json"
    if not registry_path.exists():
        return []
    with open(registry_path) as f:
        data = json.load(f)
    return data.get("markets", [])
