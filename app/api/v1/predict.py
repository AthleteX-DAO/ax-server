"""Prediction Market endpoints — serves market data to the Flutter frontend.

L0 (public): market list, single market, prices.
L2 (auth):   positions, tx builders (Phase 3).
"""

from __future__ import annotations

import math
import random
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.models.trading import PredictMarket, PredictPrice, PriceHistory, PricePoint

router = APIRouter(prefix="/predict", tags=["predict"])

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
]


def _seed_price(prompt: str) -> float:
    """Deterministic YES price derived from the prompt string hash."""
    rng = random.Random(hash(prompt))
    return round(0.25 + rng.random() * 0.5, 4)


def _build_markets() -> list[PredictMarket]:
    """Build the full list of PredictMarket objects with seeded prices."""
    results: list[PredictMarket] = []
    for m in _MARKETS:
        yes_price = _seed_price(m["prompt"])
        no_price = round(1 - yes_price, 4)
        rng = random.Random(hash(m["prompt"]))
        volume = round(500_000 + rng.random() * 4_500_000, 2)

        mid = m["id"]
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


@router.get("/markets", response_model=list[PredictMarket])
async def list_prediction_markets(
    category: Optional[str] = Query(None, description="Filter by category"),
):
    """List all prediction markets, optionally filtered by category."""
    markets = _get_markets()
    if category:
        markets = [m for m in markets if m.category == category.lower()]
    return markets


@router.get("/markets/{market_id}", response_model=PredictMarket)
async def get_prediction_market(market_id: int):
    """Get single prediction market by numeric ID."""
    for m in _get_markets():
        if m.id == market_id:
            return m
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
    days: int = Query(30, ge=1, le=365, description="Number of days of history"),
):
    """Return YES/NO price history for a prediction market."""
    for m in _get_markets():
        if m.id == market_id:
            yes_history = _generate_price_series(
                m.prompt, days, m.yes_price,
            )
            no_history = _generate_price_series(
                m.prompt, days, m.yes_price, invert=True,
            )
            return PriceHistory(
                market_id=market_id,
                yes_history=yes_history,
                no_history=no_history,
            )
    raise HTTPException(status_code=404, detail="Market not found")


# ── Stats endpoints (Vote/Dashboard page) ────────────────────────────────


@router.get("/stats/volume")
async def get_prediction_volume():
    """24h trading volume across all prediction market pairs."""
    try:
        registry = _load_registry()
        if not registry:
            # Fall back to sum from seed data
            markets = _get_markets()
            total = sum(m.trading_volume for m in markets)
            return {"volume_24h": total, "source": "seed"}

        # TODO: Query subgraph for actual 24h volume on prediction pairs
        # For now, sum trading_volume from seed markets
        markets = _get_markets()
        total = sum(m.trading_volume for m in markets)
        return {"volume_24h": total, "source": "seed"}
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
