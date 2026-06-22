"""Background price ingest worker — polls subgraph and writes to QuestDB.

Runs as an asyncio task in the FastAPI lifespan. On each cycle:
1. Queries the DEX subgraph for recent swaps
2. Derives trade records with price, amount, side
3. Ingests into QuestDB via ILP

Supports initial backfill from pairDayDatas.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta

from app.config import Settings
from app.services.questdb_client import TradeRow

logger = logging.getLogger("ax-server.ingest")


class PriceIngestWorker:
    """Background task that polls the subgraph and ingests trades into QuestDB.

    Parameters
    ----------
    settings:
        Application settings with subgraph URL, poll interval, etc.
    questdb:
        QuestDB client for writing trades.
    subgraph:
        Subgraph client for reading swap data.
    """

    def __init__(self, settings: Settings, questdb, subgraph) -> None:
        self._settings = settings
        self._qdb = questdb
        self._sg = subgraph
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_swap_ts: int = 0  # high-water mark
        self._backfilled = False

    async def start(self) -> None:
        """Start the background ingest loop."""
        self._running = True
        self._task = asyncio.create_task(self._run(), name="price-ingest")
        logger.info(
            "Price ingest worker started (poll=%ds, backfill=%dd)",
            self._settings.ingest_poll_interval,
            self._settings.ingest_backfill_days,
        )

    async def stop(self) -> None:
        """Stop the ingest loop gracefully."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Price ingest worker stopped")

    async def _run(self) -> None:
        """Main loop: backfill once, then poll for new swaps."""
        # Wait a few seconds for QuestDB to be ready
        await asyncio.sleep(3)

        while self._running:
            try:
                # One-time backfill on first run
                if not self._backfilled:
                    await self._backfill()
                    self._backfilled = True

                # Poll for new swaps
                await self._poll_swaps()

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Ingest cycle error")

            await asyncio.sleep(self._settings.ingest_poll_interval)

    async def _backfill(self) -> None:
        """Backfill historical data from pairDayDatas."""
        logger.info("Starting backfill (%d days)...", self._settings.ingest_backfill_days)

        since = int(
            (datetime.now(timezone.utc) - timedelta(days=self._settings.ingest_backfill_days))
            .timestamp()
        )

        try:
            pairs = await self._sg.get_all_pairs()
            logger.info("Found %d pairs to backfill", len(pairs))

            for pair in pairs:
                pair_id = pair.get("id", "")
                t0_sym = pair.get("token0", {}).get("symbol", "?")
                t1_sym = pair.get("token1", {}).get("symbol", "?")
                market_id = f"{t0_sym}-{t1_sym}"

                try:
                    day_datas = await self._sg.get_pair_day_data(pair_id, since)
                    if not day_datas:
                        continue

                    trades = []
                    for dd in day_datas:
                        r0 = float(dd.get("reserve0", 0) or 0)
                        r1 = float(dd.get("reserve1", 0) or 0)
                        vol = float(dd.get("dailyVolumeUSD", 0) or 0)
                        ts = int(dd.get("date", 0))

                        if r0 > 0:
                            price = r1 / r0
                        else:
                            price = 0.0

                        trades.append(TradeRow(
                            ts=datetime.fromtimestamp(ts, tz=timezone.utc),
                            market_id=market_id,
                            market_type=_classify_market(t0_sym, t1_sym),
                            price=price,
                            amount=vol / max(price, 0.001) if price > 0 else 0,
                            amount_usd=vol,
                            side="buy",
                            tx_hash=f"backfill-{pair_id}-{ts}",
                            pair_address=pair_id,
                        ))

                    if trades:
                        await self._qdb.ingest_trades(trades)
                        logger.debug("Backfilled %d days for %s", len(trades), market_id)

                except Exception:
                    logger.warning("Failed to backfill pair %s", pair_id)
                    continue

            logger.info("Backfill complete")

        except Exception:
            logger.exception("Backfill failed")

    async def _poll_swaps(self) -> None:
        """Poll recent swaps from the subgraph and ingest into QuestDB."""
        try:
            swaps = await self._sg.get_recent_swaps(limit=200)
            if not swaps:
                return

            new_swaps = [
                s for s in swaps
                if int(s.get("timestamp", 0)) > self._last_swap_ts
            ]

            if not new_swaps:
                return

            trades = []
            for s in new_swaps:
                ts = int(s.get("timestamp", 0))
                pair = s.get("pair", {})
                t0_sym = pair.get("token0", {}).get("symbol", "?")
                t1_sym = pair.get("token1", {}).get("symbol", "?")
                market_id = f"{t0_sym}-{t1_sym}"

                # Derive price and side from amounts
                a0_in = float(s.get("amount0In", 0) or 0)
                a1_in = float(s.get("amount1In", 0) or 0)
                a0_out = float(s.get("amount0Out", 0) or 0)
                a1_out = float(s.get("amount1Out", 0) or 0)
                amount_usd = float(s.get("amountUSD", 0) or 0)

                # If token0 goes in → buying token1 (sell token0)
                if a0_in > 0 and a1_out > 0:
                    price = a0_in / a1_out if a1_out > 0 else 0
                    side = "sell"
                    amount = a1_out
                elif a1_in > 0 and a0_out > 0:
                    price = a1_in / a0_out if a0_out > 0 else 0
                    side = "buy"
                    amount = a0_out
                else:
                    continue

                trades.append(TradeRow(
                    ts=datetime.fromtimestamp(ts, tz=timezone.utc),
                    market_id=market_id,
                    market_type=_classify_market(t0_sym, t1_sym),
                    price=price,
                    amount=amount,
                    amount_usd=amount_usd,
                    side=side,
                    tx_hash=s.get("id", ""),
                    pair_address=pair.get("id", ""),
                ))

            if trades:
                await self._qdb.ingest_trades(trades)
                self._last_swap_ts = max(int(s.get("timestamp", 0)) for s in new_swaps)
                logger.info("Ingested %d new swaps (hwm=%d)", len(trades), self._last_swap_ts)

        except Exception:
            logger.exception("Swap poll failed")


def _classify_market(token0_symbol: str, token1_symbol: str) -> str:
    """Classify a pair as spot, predict, or perps based on token symbols.

    - Prediction market tokens typically have YES/NO in their name
    - Spot markets are axXXX pairs
    - Everything else defaults to spot
    """
    symbols = (token0_symbol.upper(), token1_symbol.upper())
    for s in symbols:
        if "YES" in s or "NO" in s or "PREDICT" in s:
            return "predict"
        if "PERP" in s or "LONG" in s or "SHORT" in s:
            return "perps"
    return "spot"
