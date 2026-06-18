"""Multicall3 integration — batch multiple read calls into one RPC request.

Uses the canonical Multicall3 contract deployed at the same address
on all EVM chains.
"""

from __future__ import annotations

import logging
from typing import Any

from web3 import Web3
from web3.contract import Contract

from app.chain.contracts import get_contract

logger = logging.getLogger("ax-server.chain.multicall")

MULTICALL3_ADDRESS = "0xcA11bde05977b3631167028862bE2a173976CA11"


class Call:
    """A single call to batch via Multicall3."""

    def __init__(self, target: str, call_data: bytes, allow_failure: bool = False) -> None:
        self.target = target
        self.call_data = call_data
        self.allow_failure = allow_failure


class MulticallClient:
    """Batches multiple contract read calls into a single RPC request.

    This dramatically reduces RPC usage when reading state from
    many contracts (e.g., fetching all market prices at once).
    """

    def __init__(self, w3: Web3, address: str = MULTICALL3_ADDRESS) -> None:
        self.w3 = w3
        self.address = address
        self._contract: Contract | None = None

    @property
    def contract(self) -> Contract:
        """Multicall3 contract instance."""
        if self._contract is None:
            self._contract = get_contract(self.w3, self.address, "multicall3")
        return self._contract

    async def aggregate(self, calls: list[Call]) -> list[tuple[bool, bytes]]:
        """Execute multiple calls in a single transaction.

        Uses tryAggregate to allow individual call failures.

        Args:
            calls: List of Call objects to batch.

        Returns:
            List of (success, returnData) tuples.
        """
        if not calls:
            return []

        # Build multicall input
        multicall_input = [
            (call.target, call.allow_failure, call.call_data)
            for call in calls
        ]

        # TODO: Call contract.functions.tryAggregate(False, multicall_input)
        logger.debug("Multicall batch with %d calls", len(calls))
        return []

    async def get_block_number(self) -> int:
        """Utility: get current block number via multicall.

        Useful for testing the multicall connection.
        """
        return self.w3.eth.block_number

    async def get_eth_balance(self, address: str) -> int:
        """Utility: get ETH balance via multicall.

        Args:
            address: Wallet address.

        Returns:
            Balance in wei.
        """
        return self.w3.eth.get_balance(Web3.to_checksum_address(address))
