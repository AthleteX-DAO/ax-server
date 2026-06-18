"""UMA Optimistic Oracle + AthleteX Prediction Market integration.

Provides wrappers for:
- Querying active prediction markets
- Reading assertion / dispute status
- Settling resolved markets
"""

from __future__ import annotations

import logging
from typing import Any

from web3 import Web3
from web3.contract import Contract

from app.chain.contracts import get_contract
from app.config import ChainAddresses

logger = logging.getLogger("ax-server.chain.uma")


class UMAClient:
    """Client for interacting with UMA Optimistic Oracle contracts.

    Used for the AthleteX prediction market system where outcomes
    are asserted and resolved via UMA's dispute resolution mechanism.
    """

    def __init__(self, w3: Web3, addresses: ChainAddresses) -> None:
        self.w3 = w3
        self.addresses = addresses
        self._finder: Contract | None = None
        self._oracle: Contract | None = None

    @property
    def finder(self) -> Contract:
        """UMA Finder — registry for UMA system contract addresses."""
        if self._finder is None:
            self._finder = get_contract(self.w3, self.addresses.uma_finder, "uma_finder")
        return self._finder

    @property
    def optimistic_oracle(self) -> Contract:
        """UMA Optimistic Oracle V3 (OO) — handles assertions and disputes."""
        if self._oracle is None:
            self._oracle = get_contract(
                self.w3, self.addresses.uma_optimistic_oracle, "uma_optimistic_oracle"
            )
        return self._oracle

    async def get_assertion(self, assertion_id: bytes) -> dict[str, Any]:
        """Get details of an assertion.

        Args:
            assertion_id: The bytes32 assertion identifier.

        Returns:
            Assertion details (asserter, bond, expiry, resolved, etc.)
        """
        # TODO: Call optimistic_oracle.functions.getAssertion(assertion_id)
        return {"assertion_id": assertion_id.hex(), "status": "unknown"}

    async def get_prediction_market(self, market_address: str) -> dict[str, Any]:
        """Get state of an AthleteX prediction market.

        Args:
            market_address: Address of the AthleteXPredictionMarket contract.

        Returns:
            Market state including question, outcomes, resolution status.
        """
        # TODO: Instantiate prediction market contract and read state
        return {"address": market_address, "status": "not_implemented"}

    async def assert_truth(
        self,
        claim: bytes,
        asserter: str,
        bond: int,
        currency: str,
        liveness: int = 7200,
    ) -> dict[str, Any]:
        """Submit a truth assertion to the Optimistic Oracle.

        Args:
            claim: The ABI-encoded claim being asserted.
            asserter: Address of the asserter.
            bond: Bond amount in currency tokens (wei).
            currency: Bond currency token address.
            liveness: Challenge window in seconds (default 2h).

        Returns:
            Transaction receipt with assertion ID.
        """
        # TODO: Build and sign assertTruth transaction
        return {"status": "not_implemented"}

    async def settle_assertion(self, assertion_id: bytes) -> dict[str, Any]:
        """Settle a resolved assertion.

        Can only be called after the liveness period has passed
        without a dispute, or after a dispute has been resolved.

        Args:
            assertion_id: The bytes32 assertion identifier.

        Returns:
            Transaction receipt with settlement result.
        """
        # TODO: Build and sign settleAssertion transaction
        return {"status": "not_implemented"}
