"""Historical price data endpoints — OHLCV candles, trades, latest prices.

Serves data from QuestDB for spot, prediction, and perps markets.
Falls back gracefully when QuestDB is unavailable.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone, timedelta
from enum import Enum

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from app.middleware.errors import APIError

logger = logging.getLogger("ax-server.history")

router = APIRouter(prefix="/history", tags=["history"])

# ── Models ──────────────────────────────────────────────────────────────

ALLOWED_TIMEFRAMES = {"1m", "5m", "15m", "1h", "4h", "1d"}


class MarketType(str, Enum):
    SPOT = "spot"
    PREDICT = "predict"
    PERPS = "perps"


class Candle(BaseModel):
    """Single OHLCV candle."""

    t: int  # unix timestamp
    o: float  # open
    h: float  # high
    l: float  # low
    c: float  # close
    v: float  # volume


class CandleResponse(BaseModel):
    market_id: str
    market_type: str
    timeframe: str
    candles: list[Candle] = Field(default_factory=list)


class TradeRecord(BaseModel):
    timestamp: int
    price: float
    amount: float
    amount_usd: float
    side: str
    tx_hash: str


class TradeHistoryResponse(BaseModel):
    market_id: str
    trades: list[TradeRecord] = Field(default_factory=list)


class LatestPriceResponse(BaseModel):
    market_id: str
    price: float
    timestamp: int
    market_type: str


# ── Helpers ─────────────────────────────────────────────────────────────


def _get_questdb(request: Request):
    """Extract QuestDB client from app state, or None if unavailable."""
    return getattr(request.app.state, "questdb", None)


# ── Endpoints ───────────────────────────────────────────────────────────


@router.get("/candles/{market_id}", response_model=CandleResponse)
async def get_candles(
    request: Request,
    market_id: str,
    timeframe: str = Query("1h", description="Candle interval: 1m, 5m, 15m, 1h, 4h, 1d"),
    market_type: MarketType = Query(MarketType.SPOT, description="Market type"),
    start: str | None = Query(None, description="Start time ISO-8601 or unix seconds"),
    end: str | None = Query(None, description="End time ISO-8601 or unix seconds"),
    limit: int = Query(500, ge=1, le=5000, description="Max candles to return"),
):
    """OHLCV candle data for any market.

    Examples::

        GET /history/candles/1?timeframe=1h&market_type=spot
        GET /history/candles/axBTC?timeframe=1d&start=2025-01-01
        GET /history/candles/42?market_type=predict&timeframe=4h&limit=100
    """
    if timeframe not in ALLOWED_TIMEFRAMES:
        raise APIError(
            code="INVALID_TIMEFRAME",
            message=f"Invalid timeframe '{timeframe}'. Allowed: {', '.join(sorted(ALLOWED_TIMEFRAMES))}",
            status_code=400,
        )

    # Parse time range
    start_ts = _parse_timestamp(start) if start else None
    end_ts = _parse_timestamp(end) if end else None

    # Default to last 7 days
    if not start_ts:
        start_ts = int((datetime.now(timezone.utc) - timedelta(days=7)).timestamp())
    if not end_ts:
        end_ts = int(datetime.now(timezone.utc).timestamp())

    qdb = _get_questdb(request)
    if qdb is None:
        logger.warning("QuestDB unavailable — returning empty candles")
        return CandleResponse(
            market_id=market_id,
            market_type=market_type.value,
            timeframe=timeframe,
            candles=[],
        )

    try:
        rows = await qdb.get_candles(
            market_id=market_id,
            timeframe=timeframe,
            start_ts=start_ts,
            end_ts=end_ts,
            limit=limit,
        )
        candles = [
            Candle(
                t=int(r.ts.timestamp()) if hasattr(r.ts, "timestamp") else int(r.ts),
                o=r.open,
                h=r.high,
                l=r.low,
                c=r.close,
                v=r.volume,
            )
            for r in rows
        ]
    except Exception:
        logger.exception("Failed to query candles from QuestDB")
        candles = []

    return CandleResponse(
        market_id=market_id,
        market_type=market_type.value,
        timeframe=timeframe,
        candles=candles,
    )


@router.get("/trades/{market_id}", response_model=TradeHistoryResponse)
async def get_trades(
    request: Request,
    market_id: str,
    limit: int = Query(100, ge=1, le=1000),
):
    """Recent trade history for a market.

    Returns the most recent trades, ordered by timestamp descending.
    """
    qdb = _get_questdb(request)
    if qdb is None:
        return TradeHistoryResponse(market_id=market_id, trades=[])

    try:
        rows = await qdb.get_trade_history(market_id=market_id, limit=limit)
        trades = [
            TradeRecord(
                timestamp=int(r["ts"].timestamp()) if hasattr(r["ts"], "timestamp") else int(r["ts"]),
                price=float(r["price"]),
                amount=float(r["amount"]),
                amount_usd=float(r.get("amount_usd", 0)),
                side=str(r.get("side", "unknown")),
                tx_hash=str(r.get("tx_hash", "")),
            )
            for r in rows
        ]
    except Exception:
        logger.exception("Failed to query trades from QuestDB")
        trades = []

    return TradeHistoryResponse(market_id=market_id, trades=trades)


@router.get("/price/{market_id}", response_model=LatestPriceResponse)
async def get_latest_price(
    request: Request,
    market_id: str,
    market_type: MarketType = Query(MarketType.SPOT),
):
    """Latest price for a market from QuestDB.

    This returns the most recent trade price — for real-time oracle
    prices, use the ``/spot/markets/{id}/price`` endpoint instead.
    """
    qdb = _get_questdb(request)
    if qdb is None:
        raise APIError(
            code="SERVICE_UNAVAILABLE",
            message="Price history service is not available",
            status_code=503,
        )

    try:
        row = await qdb.get_latest_price(market_id=market_id)
        if row is None:
            raise APIError(
                code="NOT_FOUND",
                message=f"No price data found for market '{market_id}'",
                status_code=404,
            )
        return LatestPriceResponse(
            market_id=market_id,
            price=float(row["price"]),
            timestamp=int(row["ts"].timestamp()) if hasattr(row["ts"], "timestamp") else int(row["ts"]),
            market_type=market_type.value,
        )
    except APIError:
        raise
    except Exception:
        logger.exception("Failed to query latest price")
        raise APIError(
            code="QUERY_FAILED",
            message="Failed to fetch latest price",
            status_code=502,
        )


# ── Perps Stub ──────────────────────────────────────────────────────────


@router.get("/perps/candles/{market_id}", response_model=CandleResponse)
async def get_perps_candles(
    market_id: str,
    timeframe: str = Query("1h"),
    limit: int = Query(500, ge=1, le=5000),
):
    """OHLCV candles for perpetual futures markets.

    .. note::
        PerpsMarketProxy is not yet deployed. This endpoint returns
        empty data and will be wired up when perps go live.
    """
    return CandleResponse(
        market_id=market_id,
        market_type="perps",
        timeframe=timeframe,
        candles=[],
    )


@router.get("/perps/funding/{market_id}")
async def get_perps_funding(market_id: str):
    """Funding rate history for a perpetual market.

    .. note::
        PerpsMarketProxy is not yet deployed.
    """
    return {
        "market_id": market_id,
        "funding_rates": [],
        "message": "Perps not yet deployed — endpoint stubbed for future use.",
    }


# ── Utils ───────────────────────────────────────────────────────────────


def _parse_timestamp(value: str) -> int:
    """Parse a timestamp string — accepts ISO-8601 or unix seconds."""
    try:
        return int(value)
    except ValueError:
        pass
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return int(dt.timestamp())
    except Exception:
        raise APIError(
            code="INVALID_TIMESTAMP",
            message=f"Cannot parse timestamp: '{value}'. Use ISO-8601 or unix seconds.",
            status_code=400,
        )
