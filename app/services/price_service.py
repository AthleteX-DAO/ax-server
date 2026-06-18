"""Price service — aggregates prices from multiple sources.

Sources:
- Synthetix V3 Oracle Manager (on-chain)
- Uniswap V2 pool reserves (on-chain)
- External APIs (CoinGecko, etc.) for reference prices
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("ax-server.services.price")


class PriceService:
    """Aggregates and caches price data from multiple sources.

    Provides a unified interface for getting athlete token prices
    regardless of the underlying source.
    """

    def __init__(self) -> None:
        self._cache: dict[str, float] = {}

    async def get_price(self, token_or_market: str) -> float | None:
        """Get the current USD price for a token or market.

        Checks cache first, then fetches from on-chain sources.

        Args:
            token_or_market: Token address or market ID.

        Returns:
            Price in USD, or None if unavailable.
        """
        if token_or_market in self._cache:
            return self._cache[token_or_market]

        # TODO: Fetch from Synthetix Oracle or Uniswap V2 reserves
        return None

    async def get_prices_batch(self, identifiers: list[str]) -> dict[str, float | None]:
        """Get prices for multiple tokens/markets in one call.

        Uses Multicall3 to batch oracle reads for efficiency.

        Args:
            identifiers: List of token addresses or market IDs.

        Returns:
            Dict mapping identifier -> price (or None).
        """
        # TODO: Use Multicall3 to batch oracle reads
        return {ident: None for ident in identifiers}

    async def get_lp_price(self, pair_address: str) -> float | None:
        """Calculate the price of an LP token.

        Uses the pair reserves and underlying token prices
        to compute fair value of one LP token.

        Args:
            pair_address: Uniswap V2 pair address.

        Returns:
            LP token price in USD, or None.
        """
        # TODO: Fetch reserves, compute LP token price
        return None

    def invalidate_cache(self, identifier: str | None = None) -> None:
        """Clear cached prices.

        Args:
            identifier: Specific token/market to invalidate.
                       If None, clears entire cache.
        """
        if identifier:
            self._cache.pop(identifier, None)
        else:
            self._cache.clear()
