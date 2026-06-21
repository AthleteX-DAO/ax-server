"""Uniswap V2 integration — APTRouter / APTFactory fork.

Provides wrappers for swap, addLiquidity, removeLiquidity on
the AthleteX Uniswap V2 fork deployed on Polygon.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from eth_account.signers.local import LocalAccount
from web3 import Web3
from web3.contract import Contract

from app.chain.contracts import get_contract

logger = logging.getLogger("ax-server.chain.uniswap_v2")

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
GAS_BUFFER = 1.2  # 20% gas estimate buffer


class UniswapV2Client:
    """Client for interacting with the AthleteX Uniswap V2 fork.

    The APTRouter and APTFactory are forked Uniswap V2 contracts
    that handle athlete token liquidity pools.
    """

    def __init__(
        self,
        w3: Web3,
        router_address: str | None = None,
        factory_address: str | None = None,
        account: LocalAccount | None = None,
    ) -> None:
        self.w3 = w3
        self.router_address = router_address
        self.factory_address = factory_address
        self.account = account
        self._router: Contract | None = None
        self._factory: Contract | None = None

    @property
    def router(self) -> Contract | None:
        """APTRouter contract (Uniswap V2 Router fork)."""
        if self._router is None and self.router_address:
            self._router = get_contract(self.w3, self.router_address, "uniswap_v2_router")
        return self._router

    @property
    def factory(self) -> Contract | None:
        """APTFactory contract (Uniswap V2 Factory fork)."""
        if self._factory is None and self.factory_address:
            self._factory = get_contract(self.w3, self.factory_address, "uniswap_v2_factory")
        return self._factory

    def _build_tx_params(self) -> dict[str, Any]:
        """Common transaction parameters for signed sends."""
        return {
            "from": self.account.address,
            "chainId": 137,
            "nonce": self.w3.eth.get_transaction_count(self.account.address),
        }

    def _sign_and_send(self, tx: dict[str, Any]) -> dict[str, Any]:
        """Estimate gas, sign, send, and wait for receipt."""
        gas = self.w3.eth.estimate_gas(tx)
        tx["gas"] = int(gas * GAS_BUFFER)
        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return dict(receipt)

    async def get_pair(self, token_a: str, token_b: str) -> str | None:
        """Get the pair address for two tokens.

        Args:
            token_a: Address of token A.
            token_b: Address of token B.

        Returns:
            Pair contract address, or None if no pair exists.
        """
        if not self.factory:
            return None
        addr_a = Web3.to_checksum_address(token_a)
        addr_b = Web3.to_checksum_address(token_b)
        pair = self.factory.functions.getPair(addr_a, addr_b).call()
        if pair == ZERO_ADDRESS:
            return None
        return pair

    async def get_reserves(self, pair_address: str) -> tuple[int, int]:
        """Get reserves for a liquidity pair.

        Args:
            pair_address: Address of the pair contract.

        Returns:
            Tuple of (reserve0, reserve1) in wei.
        """
        pair = get_contract(self.w3, pair_address, "uniswap_v2_pair")
        result = pair.functions.getReserves().call()
        return (result[0], result[1])

    async def get_token0(self, pair_address: str) -> str:
        """Get token0 address for a pair."""
        pair = get_contract(self.w3, pair_address, "uniswap_v2_pair")
        return pair.functions.token0().call()

    async def get_amount_out(
        self,
        amount_in: int,
        reserve_in: int,
        reserve_out: int,
    ) -> int:
        """Calculate output amount for a swap (constant product formula).

        Args:
            amount_in: Input amount in wei.
            reserve_in: Reserve of input token.
            reserve_out: Reserve of output token.

        Returns:
            Output amount in wei.
        """
        if reserve_in == 0 or reserve_out == 0:
            return 0
        amount_in_with_fee = amount_in * 997
        numerator = amount_in_with_fee * reserve_out
        denominator = reserve_in * 1000 + amount_in_with_fee
        return numerator // denominator

    async def swap_exact_tokens(
        self,
        amount_in: int,
        amount_out_min: int,
        path: list[str],
        to: str,
        deadline: int,
    ) -> dict[str, Any]:
        """Execute a token swap via the router.

        Args:
            amount_in: Amount of input token (wei).
            amount_out_min: Minimum output (slippage protection).
            path: Token swap path [tokenIn, ..., tokenOut].
            to: Recipient address.
            deadline: Unix timestamp deadline.

        Returns:
            Transaction receipt.
        """
        if not self.router or not self.account:
            raise RuntimeError("Router and account required for swap")
        checksummed_path = [Web3.to_checksum_address(t) for t in path]
        tx = self.router.functions.swapExactTokensForTokens(
            amount_in,
            amount_out_min,
            checksummed_path,
            Web3.to_checksum_address(to),
            deadline,
        ).build_transaction(self._build_tx_params())
        return self._sign_and_send(tx)

    async def add_liquidity(
        self,
        token_a: str,
        token_b: str,
        amount_a_desired: int,
        amount_b_desired: int,
        amount_a_min: int,
        amount_b_min: int,
        to: str,
        deadline: int,
    ) -> dict[str, Any]:
        """Add liquidity to a pool.

        Args:
            token_a: Token A address.
            token_b: Token B address.
            amount_a_desired: Desired amount of A (wei).
            amount_b_desired: Desired amount of B (wei).
            amount_a_min: Minimum A to deposit (wei).
            amount_b_min: Minimum B to deposit (wei).
            to: LP token recipient.
            deadline: Unix timestamp deadline.

        Returns:
            Transaction receipt with amounts deposited and LP tokens minted.
        """
        if not self.router or not self.account:
            raise RuntimeError("Router and account required for addLiquidity")
        tx = self.router.functions.addLiquidity(
            Web3.to_checksum_address(token_a),
            Web3.to_checksum_address(token_b),
            amount_a_desired,
            amount_b_desired,
            amount_a_min,
            amount_b_min,
            Web3.to_checksum_address(to),
            deadline,
        ).build_transaction(self._build_tx_params())
        return self._sign_and_send(tx)
