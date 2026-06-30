"""Async GraphQL client for the AthleteX DEX subgraph.

Queries pair data, historical metrics, and swap events from the
Uniswap V2 fork subgraph indexed by The Graph.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger("ax-server.chain.subgraph")

DEFAULT_SUBGRAPH_URL = (
    "https://api.studio.thegraph.com/query/1743457/athletex-dex/v0.0.1"
)

# Retry configuration
_MAX_RETRIES = 3
_BASE_BACKOFF_S = 1.0


class SubgraphError(Exception):
    """Raised when a subgraph query fails after all retries."""


class SubgraphClient:
    """GraphQL client for the AthleteX DEX subgraph.

    All queries are executed via ``httpx.AsyncClient`` with automatic
    retry logic and exponential backoff on transient failures.

    Args:
        url: Subgraph GraphQL endpoint.  Defaults to the hosted
            AthleteX DEX subgraph on The Graph Studio.
        timeout: HTTP request timeout in seconds.
        max_retries: Number of retries on transient errors.
    """

    def __init__(
        self,
        url: str = DEFAULT_SUBGRAPH_URL,
        *,
        timeout: float = 30.0,
        max_retries: int = _MAX_RETRIES,
    ) -> None:
        self.url = url
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: httpx.AsyncClient | None = None

    # ── lifecycle ────────────────────────────────────────────────

    async def _get_client(self) -> httpx.AsyncClient:
        """Return a lazily-initialised ``httpx.AsyncClient``."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                headers={"Content-Type": "application/json"},
            )
        return self._client

    async def close(self) -> None:
        """Shut down the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # ── internal transport ──────────────────────────────────────

    async def _execute(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a GraphQL query with retry + exponential backoff.

        Args:
            query: GraphQL query string.
            variables: Optional query variables.

        Returns:
            The ``"data"`` portion of the GraphQL response.

        Raises:
            SubgraphError: After all retries are exhausted.
        """
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                client = await self._get_client()
                resp = await client.post(self.url, json=payload)
                resp.raise_for_status()
                body = resp.json()

                if "errors" in body:
                    err_msgs = [e.get("message", str(e)) for e in body["errors"]]
                    raise SubgraphError(
                        f"GraphQL errors: {'; '.join(err_msgs)}"
                    )

                return body.get("data", {})

            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                last_exc = exc
                backoff = _BASE_BACKOFF_S * (2 ** (attempt - 1))
                logger.warning(
                    "Subgraph request failed (attempt %d/%d): %s — "
                    "retrying in %.1fs",
                    attempt,
                    self.max_retries,
                    exc,
                    backoff,
                )
                await asyncio.sleep(backoff)

            except SubgraphError:
                raise

            except Exception as exc:
                last_exc = exc
                logger.error("Unexpected error querying subgraph: %s", exc)
                break

        raise SubgraphError(
            f"Subgraph query failed after {self.max_retries} retries: {last_exc}"
        )

    # ── public queries ──────────────────────────────────────────

    async def get_pairs(self, token_addresses: list[str]) -> list[dict[str, Any]]:
        """Fetch pair data for tokens appearing on either side of the pool.

        Matches pairs where ``token0`` **or** ``token1`` is one of the
        supplied addresses.

        Args:
            token_addresses: Lowercase hex-encoded token addresses.

        Returns:
            List of pair objects with reserves and pricing info.
        """
        addrs = [a.lower() for a in token_addresses]
        query = """
        query GetPairs($addrs: [String!]!) {
            pairs(where: {token0_in: $addrs, token1_in: $addrs}) {
                id
                token0 { id symbol }
                token1 { id symbol }
                reserve0
                reserve1
                reserveUSD
                token0Price
                token1Price
                totalSupply
            }
        }
        """
        data = await self._execute(query, {"addrs": addrs})
        pairs: list[dict[str, Any]] = data.get("pairs", [])
        logger.debug("get_pairs returned %d pairs for %d tokens", len(pairs), len(addrs))
        return pairs

    async def get_pairs_by_sport(self, sport: str) -> list[dict[str, Any]]:
        """Return all pairs matching a given sport tag."""
        query = """
        query GetPairsBySport($sport: String!) {
          pairs(where: { sport: $sport }) {
            id
            token0 { id symbol name decimals }
            token1 { id symbol name decimals }
            reserve0
            reserve1
            reserveUSD
            volumeUSD
          }
        }
        """
        data = await self._execute(query, {"sport": sport})
        return data.get("pairs", [])

    async def get_user_net_inflow(self, wallet: str) -> float:
        """Get total net inflow USD for a user across all verticals."""
        query = """
        query GetUserNetInflow($id: ID!) {
          user(id: $id) {
            id
            netInflowUSD
            vaultInflowUSD
            spotInflowUSD
            perpsInflowUSD
            predictionInflowUSD
          }
        }
        """
        data = await self._execute(query, {"id": wallet.lower()})
        user = data.get("user")
        if not user:
            return 0.0
        
        return float(user.get("netInflowUSD", 0.0))

    async def get_net_inflows_since(self, wallet: str, since_timestamp: int) -> float:
        """Get total net inflow USD for a user since a specific timestamp."""
        query = """
        query GetUserInflowsSince($id: String!, $since: Int!) {
          netInflowEvents(
            where: { user: $id, timestamp_gte: $since }
          ) {
            amountUSD
          }
        }
        """
        data = await self._execute(
            query,
            {"id": wallet.lower(), "since": since_timestamp}
        )
        events = data.get("netInflowEvents", [])
        total = 0.0
        for ev in events:
            total += float(ev.get("amountUSD", 0.0))
        return total

    async def get_pair_hour_data(
        self,
        pair_address: str,
        since_timestamp: int,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Fetch hourly OHLCV-style data for a single pair.

        Args:
            pair_address: Lowercase pair contract address.
            since_timestamp: Unix timestamp (seconds) lower bound.
            limit: Maximum number of records to return.

        Returns:
            List of hourly data records ordered ascending by time.
        """
        query = """
        query GetPairHourData($pair: String!, $since: Int!, $limit: Int!) {
            pairHourDatas(
                where: {pair: $pair, hourStartUnix_gte: $since}
                orderBy: hourStartUnix
                orderDirection: asc
                first: $limit
            ) {
                hourStartUnix
                reserve0
                reserve1
                hourlyVolumeUSD
                hourlyVolumeToken0
                hourlyVolumeToken1
            }
        }
        """
        data = await self._execute(
            query,
            {
                "pair": pair_address.lower(),
                "since": since_timestamp,
                "limit": limit,
            },
        )
        records: list[dict[str, Any]] = data.get("pairHourDatas", [])
        logger.debug(
            "get_pair_hour_data returned %d records for pair=%s",
            len(records),
            pair_address,
        )
        return records

    async def get_pair_day_data(
        self,
        pair_address: str,
        since_timestamp: int,
    ) -> list[dict[str, Any]]:
        """Fetch daily data for a single pair.

        Args:
            pair_address: Lowercase pair contract address.
            since_timestamp: Unix timestamp (seconds) lower bound.

        Returns:
            List of daily data records ordered ascending by date.
        """
        query = """
        query GetPairDayData($pair: String!, $since: Int!) {
            pairDayDatas(
                where: {pairAddress: $pair, date_gte: $since}
                orderBy: date
                orderDirection: asc
            ) {
                date
                reserve0
                reserve1
                dailyVolumeUSD
                dailyVolumeToken0
                dailyVolumeToken1
            }
        }
        """
        data = await self._execute(
            query,
            {"pair": pair_address.lower(), "since": since_timestamp},
        )
        records: list[dict[str, Any]] = data.get("pairDayDatas", [])
        logger.debug(
            "get_pair_day_data returned %d records for pair=%s",
            len(records),
            pair_address,
        )
        return records

    async def get_recent_swaps(
        self,
        pair_address: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetch the most recent swap events.

        Args:
            pair_address: Optional filter to a single pair.
            limit: Maximum number of swaps to return.

        Returns:
            List of swap objects, newest first.
        """
        if pair_address is not None:
            query = """
            query GetRecentSwaps($pair: String!, $limit: Int!) {
                swaps(
                    first: $limit
                    orderBy: timestamp
                    orderDirection: desc
                    where: {pair: $pair}
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
            variables: dict[str, Any] = {
                "pair": pair_address.lower(),
                "limit": limit,
            }
        else:
            query = """
            query GetRecentSwapsAll($limit: Int!) {
                swaps(
                    first: $limit
                    orderBy: timestamp
                    orderDirection: desc
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
            variables = {"limit": limit}

        data = await self._execute(query, variables)
        swaps: list[dict[str, Any]] = data.get("swaps", [])
        logger.debug("get_recent_swaps returned %d swaps", len(swaps))
        return swaps

    async def get_all_pairs(self) -> list[dict[str, Any]]:
        """Fetch every pair with its reserves.

        Paginates through the subgraph in batches of 1 000 using
        ``id_gt`` cursor-based pagination until all pairs are retrieved.

        Returns:
            Complete list of pair objects.
        """
        all_pairs: list[dict[str, Any]] = []
        last_id = ""
        batch_size = 1000

        while True:
            query = """
            query GetAllPairs($lastId: String!, $first: Int!) {
                pairs(
                    first: $first
                    where: {id_gt: $lastId}
                    orderBy: id
                    orderDirection: asc
                ) {
                    id
                    token0 { id symbol }
                    token1 { id symbol }
                    reserve0
                    reserve1
                    reserveUSD
                    token0Price
                    token1Price
                    totalSupply
                }
            }
            """
            data = await self._execute(
                query, {"lastId": last_id, "first": batch_size}
            )
            batch: list[dict[str, Any]] = data.get("pairs", [])
            if not batch:
                break

            all_pairs.extend(batch)
            last_id = batch[-1]["id"]
            logger.debug(
                "get_all_pairs fetched batch of %d (total %d so far)",
                len(batch),
                len(all_pairs),
            )

            if len(batch) < batch_size:
                break

        logger.info("get_all_pairs completed — %d pairs total", len(all_pairs))
        return all_pairs
