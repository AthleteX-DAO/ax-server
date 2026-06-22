"""QuestDB client — dual-protocol access for AthleteX market data.

Reads use the PostgreSQL wire protocol (``asyncpg``, port 8812).
Writes use the InfluxDB Line Protocol (``questdb.ingress.Sender``,
port 9000) executed in a thread pool to keep the event loop free.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import asyncpg

logger = logging.getLogger("ax-server.services.questdb")

# ── Constants ────────────────────────────────────────────────────

ALLOWED_TIMEFRAMES: set[str] = {"1m", "5m", "15m", "1h", "4h", "1d"}

_TIMEFRAME_TO_SAMPLE_BY: dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}

_CREATE_TRADES_SQL = """
CREATE TABLE IF NOT EXISTS trades (
    ts TIMESTAMP,
    market_id SYMBOL CAPACITY 1024 CACHE,
    market_type SYMBOL CAPACITY 8 CACHE,
    price DOUBLE,
    amount DOUBLE,
    amount_usd DOUBLE,
    side SYMBOL CAPACITY 4 CACHE,
    tx_hash SYMBOL CAPACITY 4096,
    pair_address SYMBOL CAPACITY 1024 CACHE
) TIMESTAMP(ts) PARTITION BY DAY WAL
DEDUP UPSERT KEYS(ts, market_id, tx_hash);
"""

_CREATE_CANDLES_SQL = """
CREATE TABLE IF NOT EXISTS candles (
    ts TIMESTAMP,
    market_id SYMBOL CAPACITY 1024 CACHE,
    market_type SYMBOL CAPACITY 8 CACHE,
    timeframe SYMBOL CAPACITY 16 CACHE,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    volume DOUBLE,
    trade_count LONG
) TIMESTAMP(ts) PARTITION BY MONTH WAL
DEDUP UPSERT KEYS(ts, market_id, timeframe);
"""


# ── Data classes ─────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class TradeRow:
    """A single trade record."""

    ts: datetime
    market_id: str
    market_type: str  # 'spot', 'predict', 'perps'
    price: float
    amount: float
    amount_usd: float
    side: str
    tx_hash: str
    pair_address: str


@dataclass(frozen=True, slots=True)
class CandleRow:
    """A single OHLCV candle record."""

    ts: datetime
    market_id: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    trade_count: int


# ── Client ───────────────────────────────────────────────────────


class QuestDBClient:
    """Dual-protocol QuestDB client.

    Args:
        pg_host: Host for the PostgreSQL wire protocol.
        pg_port: Port for the PostgreSQL wire protocol (default 8812).
        ilp_host: Host for the ILP HTTP endpoint.
        ilp_port: Port for the ILP HTTP endpoint (default 9000).
        pg_user: PostgreSQL user.
        pg_password: PostgreSQL password.
        pg_database: PostgreSQL database name.
    """

    def __init__(
        self,
        *,
        pg_host: str = "localhost",
        pg_port: int = 8812,
        ilp_host: str = "localhost",
        ilp_port: int = 9000,
        pg_user: str = "admin",
        pg_password: str = "quest",
        pg_database: str = "qdb",
    ) -> None:
        self._pg_host = pg_host
        self._pg_port = pg_port
        self._ilp_host = ilp_host
        self._ilp_port = ilp_port
        self._pg_user = pg_user
        self._pg_password = pg_password
        self._pg_database = pg_database

        self._pool: asyncpg.Pool | None = None

    # ── lifecycle ────────────────────────────────────────────────

    async def init(self) -> None:
        """Create the ``asyncpg`` connection pool and ensure tables exist.

        If QuestDB is not reachable the error is logged but not raised
        so the rest of the application can still start up.
        """
        try:
            self._pool = await asyncpg.create_pool(
                host=self._pg_host,
                port=self._pg_port,
                user=self._pg_user,
                password=self._pg_password,
                database=self._pg_database,
                min_size=2,
                max_size=10,
            )
            logger.info(
                "QuestDB asyncpg pool created (%s:%d)", self._pg_host, self._pg_port
            )
            await self._ensure_tables()
        except (OSError, asyncpg.PostgresError) as exc:
            logger.error(
                "Failed to connect to QuestDB at %s:%d — %s",
                self._pg_host,
                self._pg_port,
                exc,
            )

    async def close(self) -> None:
        """Gracefully close the connection pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            logger.info("QuestDB asyncpg pool closed")

    async def _ensure_tables(self) -> None:
        """Run CREATE TABLE IF NOT EXISTS statements."""
        assert self._pool is not None
        async with self._pool.acquire() as conn:
            await conn.execute(_CREATE_TRADES_SQL)
            await conn.execute(_CREATE_CANDLES_SQL)
        logger.info("QuestDB tables verified (trades, candles)")

    def _require_pool(self) -> asyncpg.Pool:
        """Return the pool or raise if not initialised."""
        if self._pool is None:
            raise RuntimeError(
                "QuestDB client not initialised — call init() first"
            )
        return self._pool

    # ── writes (ILP via thread pool) ─────────────────────────────

    async def ingest_trades(self, trades: list[TradeRow]) -> None:
        """Bulk-insert trades via the ILP protocol.

        The ``questdb.ingress.Sender`` is synchronous, so this method
        delegates to :func:`asyncio.to_thread` to avoid blocking the
        event loop.

        Args:
            trades: Trade records to write.
        """
        if not trades:
            return
        await asyncio.to_thread(self._ingest_trades_sync, trades)
        logger.info("Ingested %d trades via ILP", len(trades))

    def _ingest_trades_sync(self, trades: list[TradeRow]) -> None:
        """Synchronous ILP write — runs in a worker thread."""
        from questdb.ingress import Sender, TimestampNanos

        conf = f"http::addr={self._ilp_host}:{self._ilp_port};"
        try:
            with Sender.from_conf(conf) as sender:
                for t in trades:
                    sender.row(
                        "trades",
                        symbols={
                            "market_id": t.market_id,
                            "market_type": t.market_type,
                            "side": t.side,
                            "tx_hash": t.tx_hash,
                            "pair_address": t.pair_address,
                        },
                        columns={
                            "price": t.price,
                            "amount": t.amount,
                            "amount_usd": t.amount_usd,
                        },
                        at=TimestampNanos(int(t.ts.timestamp() * 1_000_000_000)),
                    )
                sender.flush()
        except Exception as exc:
            logger.error("ILP ingest failed: %s", exc)
            raise

    # ── reads (asyncpg) ──────────────────────────────────────────

    async def get_candles(
        self,
        market_id: str,
        timeframe: str,
        start_ts: datetime,
        end_ts: datetime,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Query candles using QuestDB's ``SAMPLE BY``.

        Generates candles on the fly from the ``trades`` table
        if pre-aggregated candles are not available.

        Args:
            market_id: Market identifier.
            timeframe: One of ``ALLOWED_TIMEFRAMES``.
            start_ts: Inclusive start timestamp.
            end_ts: Inclusive end timestamp.
            limit: Maximum rows to return.

        Returns:
            List of candle dicts.

        Raises:
            ValueError: If *timeframe* is not in ``ALLOWED_TIMEFRAMES``.
        """
        if timeframe not in ALLOWED_TIMEFRAMES:
            raise ValueError(
                f"Invalid timeframe {timeframe!r}. "
                f"Allowed: {sorted(ALLOWED_TIMEFRAMES)}"
            )

        pool = self._require_pool()
        sample_by = _TIMEFRAME_TO_SAMPLE_BY[timeframe]

        # Use SAMPLE BY on the trades table to compute OHLCV on the fly.
        # The timeframe literal is validated above, so it is safe to
        # interpolate into the SQL string.
        query = f"""
            SELECT
                ts,
                first(price) AS open,
                max(price)   AS high,
                min(price)   AS low,
                last(price)  AS close,
                sum(amount)  AS volume,
                count()      AS trade_count
            FROM trades
            WHERE market_id = $1
              AND ts >= $2
              AND ts <= $3
            SAMPLE BY {sample_by}
            LIMIT {int(limit)};
        """

        async with pool.acquire() as conn:
            rows = await conn.fetch(query, market_id, start_ts, end_ts)

        return [dict(r) for r in rows]

    async def get_24h_volume(self, market_type: str = "predict") -> dict[str, float]:
        """Get 24-hour trading volume grouped by market_id.

        Returns a dict mapping market_id → total_volume_usd.
        """
        pool = await self._get_pool()

        query = """
            SELECT
                market_id,
                sum(amount_usd) AS volume_usd,
                count()         AS trade_count
            FROM trades
            WHERE market_type = $1
              AND ts >= dateadd('d', -1, now())
            GROUP BY market_id;
        """

        async with pool.acquire() as conn:
            rows = await conn.fetch(query, market_type)

        result: dict[str, float] = {}
        for r in rows:
            mid = r["market_id"]
            vol = r["volume_usd"] or 0.0
            result[mid] = vol
        return result

    async def get_latest_price(self, market_id: str) -> dict[str, Any] | None:
        """Get the most recent price for a market via ``LATEST ON``.

        Args:
            market_id: Market identifier.

        Returns:
            Dict with ``ts``, ``price``, ``amount``, ``side``
            or ``None`` if no data exists.
        """
        pool = self._require_pool()
        query = """
            SELECT ts, price, amount, side
            FROM trades
            LATEST ON ts PARTITION BY market_id
            WHERE market_id = $1;
        """

        async with pool.acquire() as conn:
            row = await conn.fetchrow(query, market_id)

        if row is None:
            return None
        return dict(row)

    async def get_trade_history(
        self,
        market_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetch recent trades for a market, newest first.

        Args:
            market_id: Market identifier.
            limit: Maximum number of trades.

        Returns:
            List of trade dicts.
        """
        pool = self._require_pool()
        query = """
            SELECT ts, price, amount, amount_usd, side, tx_hash
            FROM trades
            WHERE market_id = $1
            ORDER BY ts DESC
            LIMIT $2;
        """

        async with pool.acquire() as conn:
            rows = await conn.fetch(query, market_id, limit)

        return [dict(r) for r in rows]

    async def get_market_types(self) -> list[str]:
        """Return the distinct market types present in the trades table.

        Returns:
            Sorted list of unique ``market_type`` values
            (e.g. ``['perps', 'predict', 'spot']``).
        """
        pool = self._require_pool()
        query = "SELECT DISTINCT market_type FROM trades ORDER BY market_type;"

        async with pool.acquire() as conn:
            rows = await conn.fetch(query)

        return [r["market_type"] for r in rows]

    async def get_candles_by_pair(
        self,
        pair_address: str,
        timeframe: str,
        start_ts: datetime,
        end_ts: datetime,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Query candles filtered by ``pair_address`` instead of ``market_id``.

        Useful for prediction markets where the registry stores LP pool
        addresses rather than symbol-based market IDs.

        Args:
            pair_address: Lowercase LP pool contract address.
            timeframe: One of ``ALLOWED_TIMEFRAMES``.
            start_ts: Inclusive start timestamp.
            end_ts: Inclusive end timestamp.
            limit: Maximum rows to return.

        Returns:
            List of candle dicts.
        """
        if timeframe not in ALLOWED_TIMEFRAMES:
            raise ValueError(
                f"Invalid timeframe {timeframe!r}. "
                f"Allowed: {sorted(ALLOWED_TIMEFRAMES)}"
            )

        pool = self._require_pool()
        sample_by = _TIMEFRAME_TO_SAMPLE_BY[timeframe]

        query = f"""
            SELECT
                ts,
                first(price) AS open,
                max(price)   AS high,
                min(price)   AS low,
                last(price)  AS close,
                sum(amount)  AS volume,
                count()      AS trade_count
            FROM trades
            WHERE pair_address = $1
              AND ts >= $2
              AND ts <= $3
            SAMPLE BY {sample_by}
            LIMIT {int(limit)};
        """

        async with pool.acquire() as conn:
            rows = await conn.fetch(query, pair_address, start_ts, end_ts)

        return [dict(r) for r in rows]
