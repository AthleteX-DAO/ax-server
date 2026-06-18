"""Portfolio service — aggregates user positions and computes metrics.

Reads positions across Synthetix V3, Uniswap V2, and UMA prediction
markets to give a unified portfolio view.
"""

from __future__ import annotations

import logging
from typing import Any

from app.models.position import Position, PositionSummary, PositionType

logger = logging.getLogger("ax-server.services.portfolio")


class PortfolioService:
    """Aggregates positions across all protocols for a given address.

    Uses Multicall3 for efficient batched reads.
    """

    def __init__(self) -> None:
        pass

    async def get_portfolio(self, address: str) -> PositionSummary:
        """Build a complete portfolio summary for a wallet address.

        Steps:
        1. Fetch Synthetix V3 account IDs owned by address
        2. For each account: get collateral, delegations
        3. Fetch synth token balances (ERC-20 balanceOf)
        4. Fetch Uniswap V2 LP token balances
        5. Fetch UMA prediction market positions
        6. Price everything and compute totals

        All reads are batched via Multicall3.

        Args:
            address: Wallet address (checksummed).

        Returns:
            Aggregated portfolio summary with all positions.
        """
        positions: list[Position] = []

        # TODO: Implement batched position fetching

        total_value = sum(p.value_usd for p in positions)

        return PositionSummary(
            address=address,
            total_value_usd=total_value,
            positions=positions,
        )

    async def get_synthetix_positions(self, address: str) -> list[Position]:
        """Fetch Synthetix V3 positions (collateral + delegation).

        Args:
            address: Wallet address.

        Returns:
            List of Synthetix positions.
        """
        # TODO: Query CoreProxy for account IDs and collateral
        return []

    async def get_lp_positions(self, address: str) -> list[Position]:
        """Fetch Uniswap V2 LP positions.

        Args:
            address: Wallet address.

        Returns:
            List of LP positions with underlying token breakdown.
        """
        # TODO: Query known LP pairs for balanceOf(address)
        return []

    async def get_prediction_positions(self, address: str) -> list[Position]:
        """Fetch UMA prediction market positions.

        Args:
            address: Wallet address.

        Returns:
            List of prediction market positions.
        """
        # TODO: Query prediction market contracts
        return []
