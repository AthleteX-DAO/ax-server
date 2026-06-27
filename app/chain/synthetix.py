"""Synthetix V3 integration — Core, Spot Market, Oracle Manager.

Provides typed wrappers around Synthetix V3 contracts on Polygon.
All read methods are synchronous (Web3.py calls are blocking).
All write methods return UnsignedTx dicts for client-side signing.
"""

from __future__ import annotations

import logging
from typing import Any

from web3 import Web3
from web3.contract import Contract

from app.chain.contracts import get_contract
from app.config import ChainAddresses

logger = logging.getLogger("ax-server.chain.synthetix")

# Default staleness tolerance for spot market quotes
# 0 = DEFAULT (most common), 1 = STRICT, 2 = STALE_ALLOWED
_DEFAULT_STALENESS_TOLERANCE = 0


class SynthetixClient:
    """Client for interacting with Synthetix V3 contracts.

    Wraps CoreProxy, SpotMarketProxy, and OracleManager.
    All read methods are synchronous (blocking web3 calls).
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

    # ── Core Protocol — Reads (synchronous) ───────────────────────

    def get_account_owner(self, account_id: int) -> str:
        """Get the owner address of a Synthetix V3 account NFT."""
        return self.core.functions.getAccountOwner(account_id).call()

    def get_account_token_address(self) -> str:
        """Get the Account NFT (ERC-721) contract address."""
        return self.core.functions.getAccountTokenAddress().call()

    def get_account_collateral(
        self, account_id: int, collateral_type: str
    ) -> tuple[int, int, int]:
        """Get collateral state for an account.

        Returns:
            Tuple of (totalDeposited, totalAssigned, totalLocked) in wei.
        """
        ct = Web3.to_checksum_address(collateral_type)
        result = self.core.functions.getAccountCollateral(account_id, ct).call()
        return result[0], result[1], result[2]

    def get_available_collateral(
        self, account_id: int, collateral_type: str
    ) -> int:
        """Get withdrawable collateral for an account (in wei)."""
        ct = Web3.to_checksum_address(collateral_type)
        return self.core.functions.getAccountAvailableCollateral(account_id, ct).call()

    def get_position(
        self, account_id: int, pool_id: int, collateral_type: str
    ) -> tuple[int, int, int, int]:
        """Get full position data.

        Returns:
            Tuple of (collateralAmount, collateralValue, debt, collateralizationRatio) in wei.
        """
        ct = Web3.to_checksum_address(collateral_type)
        result = self.core.functions.getPosition(account_id, pool_id, ct).call()
        return result[0], result[1], result[2], result[3]

    def get_position_debt(
        self, account_id: int, pool_id: int, collateral_type: str
    ) -> int:
        """Get current debt (axUSD minted) for a position (in wei)."""
        ct = Web3.to_checksum_address(collateral_type)
        return self.core.functions.getPositionDebt(account_id, pool_id, ct).call()

    def get_position_c_ratio(
        self, account_id: int, pool_id: int, collateral_type: str
    ) -> int:
        """Get collateralization ratio for a position (18-decimal fixed point)."""
        ct = Web3.to_checksum_address(collateral_type)
        return self.core.functions.getPositionCollateralRatio(
            account_id, pool_id, ct
        ).call()

    def get_collateral_price(self, collateral_type: str) -> int:
        """Get oracle price for a collateral token (18-decimal wei)."""
        ct = Web3.to_checksum_address(collateral_type)
        return self.core.functions.getCollateralPrice(ct).call()

    def get_preferred_pool(self) -> int:
        """Get the preferred pool ID."""
        return self.core.functions.getPreferredPool().call()

    def get_approved_pools(self) -> list[int]:
        """Get list of approved pool IDs."""
        return self.core.functions.getApprovedPools().call()

    def get_pool_name(self, pool_id: int) -> str:
        """Get human-readable name of a pool."""
        return self.core.functions.getPoolName(pool_id).call()

    # ── Core Protocol — Writes (return unsigned tx dicts) ─────────

    def build_deposit_tx(
        self, account_id: int, collateral_type: str, amount: int
    ) -> dict[str, Any]:
        """Build unsigned deposit transaction."""
        ct = Web3.to_checksum_address(collateral_type)
        return {
            "to": self.addresses.core_proxy,
            "data": self.core.functions.deposit(
                account_id, ct, amount
            )._encode_transaction_data(),
            "value": "0",
            "chain_id": self.w3.eth.chain_id,
        }

    def build_withdraw_tx(
        self, account_id: int, collateral_type: str, amount: int
    ) -> dict[str, Any]:
        """Build unsigned withdraw transaction."""
        ct = Web3.to_checksum_address(collateral_type)
        return {
            "to": self.addresses.core_proxy,
            "data": self.core.functions.withdraw(
                account_id, ct, amount
            )._encode_transaction_data(),
            "value": "0",
            "chain_id": self.w3.eth.chain_id,
        }

    def build_delegate_tx(
        self,
        account_id: int,
        pool_id: int,
        collateral_type: str,
        amount: int,
        leverage: int = 1 * 10**18,
    ) -> dict[str, Any]:
        """Build unsigned delegateCollateral transaction."""
        ct = Web3.to_checksum_address(collateral_type)
        return {
            "to": self.addresses.core_proxy,
            "data": self.core.functions.delegateCollateral(
                account_id, pool_id, ct, amount, leverage
            )._encode_transaction_data(),
            "value": "0",
            "chain_id": self.w3.eth.chain_id,
        }

    def build_mint_usd_tx(
        self,
        account_id: int,
        pool_id: int,
        collateral_type: str,
        amount: int,
    ) -> dict[str, Any]:
        """Build unsigned mintUsd transaction."""
        ct = Web3.to_checksum_address(collateral_type)
        return {
            "to": self.addresses.core_proxy,
            "data": self.core.functions.mintUsd(
                account_id, pool_id, ct, amount
            )._encode_transaction_data(),
            "value": "0",
            "chain_id": self.w3.eth.chain_id,
        }

    def build_burn_usd_tx(
        self,
        account_id: int,
        pool_id: int,
        collateral_type: str,
        amount: int,
    ) -> dict[str, Any]:
        """Build unsigned burnUsd transaction."""
        ct = Web3.to_checksum_address(collateral_type)
        return {
            "to": self.addresses.core_proxy,
            "data": self.core.functions.burnUsd(
                account_id, pool_id, ct, amount
            )._encode_transaction_data(),
            "value": "0",
            "chain_id": self.w3.eth.chain_id,
        }

    # ── Spot Market — Reads ───────────────────────────────────────

    def get_synth_market_name(self, market_id: int) -> str:
        """Get human-readable name of a synth market."""
        return self.spot_market.functions.getName(market_id).call()

    def get_synth_address(self, market_id: int) -> str:
        """Get the synth token contract address for a market."""
        return self.spot_market.functions.getSynth(market_id).call()

    def get_index_price(self, market_id: int) -> int:
        """Get current index price for a synth market (18-decimal wei)."""
        return self.spot_market.functions.indexPrice(market_id).call()

    def quote_buy(
        self, market_id: int, usd_amount: int
    ) -> tuple[int, dict[str, Any]]:
        """Quote buying synth with exact USD amount.

        Returns:
            Tuple of (synthAmount, fees_dict).
        """
        result = self.spot_market.functions.quoteBuyExactIn(
            market_id, usd_amount, _DEFAULT_STALENESS_TOLERANCE
        ).call()
        synth_amount = result[0]
        fees = {
            "fixed_fees": result[1][0],
            "utilization_fees": result[1][1],
            "skew_fees": result[1][2],
            "wrapper_fees": result[1][3],
        }
        return synth_amount, fees

    def quote_sell(
        self, market_id: int, synth_amount: int
    ) -> tuple[int, dict[str, Any]]:
        """Quote selling synth for USD.

        Returns:
            Tuple of (usdAmount, fees_dict).
        """
        result = self.spot_market.functions.quoteSellExactIn(
            market_id, synth_amount, _DEFAULT_STALENESS_TOLERANCE
        ).call()
        usd_amount = result[0]
        fees = {
            "fixed_fees": result[1][0],
            "utilization_fees": result[1][1],
            "skew_fees": result[1][2],
            "wrapper_fees": result[1][3],
        }
        return usd_amount, fees

    def get_market_skew(self, market_id: int) -> int:
        """Get market skew (positive = more longs)."""
        return self.spot_market.functions.getMarketSkew(market_id).call()

    def get_market_fees(self, market_id: int) -> dict[str, Any]:
        """Get fee configuration for a synth market."""
        result = self.spot_market.functions.getMarketFees(market_id).call()
        return {
            "atomic_fixed_fee": result[0],
            "async_fixed_fee": result[1],
            "wrap_fee": result[2],
            "unwrap_fee": result[3],
        }

    # ── Spot Market — Writes ──────────────────────────────────────

    def build_buy_tx(
        self,
        market_id: int,
        usd_amount: int,
        min_received: int = 0,
        referrer: str = "0x0000000000000000000000000000000000000000",
    ) -> dict[str, Any]:
        """Build unsigned buy synth transaction."""
        return {
            "to": self.addresses.spot_market_proxy,
            "data": self.spot_market.functions.buy(
                market_id, usd_amount, min_received,
                Web3.to_checksum_address(referrer)
            )._encode_transaction_data(),
            "value": "0",
            "chain_id": self.w3.eth.chain_id,
        }

    def build_sell_tx(
        self,
        market_id: int,
        synth_amount: int,
        min_received: int = 0,
        referrer: str = "0x0000000000000000000000000000000000000000",
    ) -> dict[str, Any]:
        """Build unsigned sell synth transaction."""
        return {
            "to": self.addresses.spot_market_proxy,
            "data": self.spot_market.functions.sell(
                market_id, synth_amount, min_received,
                Web3.to_checksum_address(referrer)
            )._encode_transaction_data(),
            "value": "0",
            "chain_id": self.w3.eth.chain_id,
        }

    def build_wrap_tx(
        self,
        market_id: int,
        wrap_amount: int,
        min_received: int = 0,
    ) -> dict[str, Any]:
        """Build unsigned wrap transaction (collateral → synth)."""
        return {
            "to": self.addresses.spot_market_proxy,
            "data": self.spot_market.functions.wrap(
                market_id, wrap_amount, min_received
            )._encode_transaction_data(),
            "value": "0",
            "chain_id": self.w3.eth.chain_id,
        }

    def build_unwrap_tx(
        self,
        market_id: int,
        unwrap_amount: int,
        min_received: int = 0,
    ) -> dict[str, Any]:
        """Build unsigned unwrap transaction (synth → collateral)."""
        return {
            "to": self.addresses.spot_market_proxy,
            "data": self.spot_market.functions.unwrap(
                market_id, unwrap_amount, min_received
            )._encode_transaction_data(),
            "value": "0",
            "chain_id": self.w3.eth.chain_id,
        }

    # ── Oracle ────────────────────────────────────────────────────

    def get_oracle_price(self, node_id: bytes) -> tuple[int, int]:
        """Get price from oracle node.

        Args:
            node_id: The bytes32 oracle node ID.

        Returns:
            Tuple of (price, timestamp). Price is 18-decimal.
        """
        result = self.oracle_manager.functions.process(node_id).call()
        return result[0], result[1]
