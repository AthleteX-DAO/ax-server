"""Synthetix V3 integration — Core, Spot Market, Oracle Manager.

Provides typed wrappers around Synthetix V3 contracts on Polygon.
"""

from __future__ import annotations

import logging
from typing import Any

from web3 import Web3
from web3.contract import Contract

from app.chain.contracts import get_contract
from app.config import ChainAddresses

logger = logging.getLogger("ax-server.chain.synthetix")


class SynthetixClient:
    """Client for interacting with Synthetix V3 contracts.

    Wraps CoreProxy, SpotMarketProxy, and OracleManager.
    """

    def __init__(self, w3: Web3, addresses: ChainAddresses) -> None:
        self.w3 = w3
        self.addresses = addresses
        self._core: Contract | None = None
        self._spot: Contract | None = None
        self._oracle: Contract | None = None

    @property
    def core(self) -> Contract:
        """Synthetix V3 CoreProxy — manages accounts, collateral, delegation."""
        if self._core is None:
            self._core = get_contract(self.w3, self.addresses.core_proxy, "core_proxy")
        return self._core

    @property
    def spot_market(self) -> Contract:
        """SpotMarketProxy — manages synth markets (athlete tokens)."""
        if self._spot is None:
            self._spot = get_contract(self.w3, self.addresses.spot_market_proxy, "spot_market_proxy")
        return self._spot

    @property
    def oracle_manager(self) -> Contract:
        """OracleManager — manages price oracle nodes."""
        if self._oracle is None:
            self._oracle = get_contract(self.w3, self.addresses.oracle_manager, "oracle_manager")
        return self._oracle

    # ── Core Protocol ─────────────────────────────────────────────

    async def get_account_permissions(self, account_id: int) -> dict[str, Any]:
        """Get permissions for a Synthetix V3 account.

        Args:
            account_id: The NFT token ID of the account.

        Returns:
            Dict with owner and permission grants.
        """
        # TODO: Call core.functions.getAccountOwner(account_id)
        return {"account_id": account_id, "permissions": []}

    async def get_collateral(self, account_id: int, collateral_type: str) -> float:
        """Get collateral amount for an account.

        Args:
            account_id: Synthetix V3 account ID.
            collateral_type: Collateral token address.

        Returns:
            Collateral amount as float.
        """
        # TODO: Call core.functions.getAccountCollateral(account_id, collateral_type)
        return 0.0

    # ── Spot Market ───────────────────────────────────────────────

    async def get_synth_market_info(self, market_id: int) -> dict[str, Any]:
        """Get information about a synth market.

        Args:
            market_id: On-chain synth market ID.

        Returns:
            Market metadata including name, synth address, fees.
        """
        # TODO: Call spot_market.functions.getMarketName(market_id)
        return {"market_id": market_id, "name": "", "synth_address": ""}

    async def get_synth_price(self, market_id: int) -> float:
        """Get current synth price from the oracle.

        Args:
            market_id: On-chain synth market ID.

        Returns:
            Price in USD (18-decimal adjusted).
        """
        # TODO: Call oracle for market price
        return 0.0

    async def buy_synth(
        self,
        market_id: int,
        usd_amount: int,
        min_amount_received: int,
        referrer: str = "0x0000000000000000000000000000000000000000",
    ) -> dict[str, Any]:
        """Buy synth tokens with axUSD.

        Args:
            market_id: Target synth market.
            usd_amount: Amount of axUSD to spend (wei).
            min_amount_received: Minimum synth tokens to receive (wei).
            referrer: Referrer address for fee sharing.

        Returns:
            Transaction result with amount received.
        """
        # TODO: Build and sign buy transaction
        return {"status": "not_implemented"}

    async def sell_synth(
        self,
        market_id: int,
        synth_amount: int,
        min_usd_received: int,
        referrer: str = "0x0000000000000000000000000000000000000000",
    ) -> dict[str, Any]:
        """Sell synth tokens for axUSD.

        Args:
            market_id: Target synth market.
            synth_amount: Amount of synth tokens to sell (wei).
            min_usd_received: Minimum axUSD to receive (wei).
            referrer: Referrer address for fee sharing.

        Returns:
            Transaction result with USD received.
        """
        # TODO: Build and sign sell transaction
        return {"status": "not_implemented"}
