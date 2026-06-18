"""Trade execution agent.

Responsible for:
- Executing trades on Synthetix V3 spot markets (wrap/unwrap, buy/sell)
- Providing liquidity on Uniswap V2 (APTRouter fork)
- Managing collateral delegation on Synthetix V3 core
- Handling transaction lifecycle (build, sign, submit, confirm)
"""

from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent


class ExecutionAgent(BaseAgent):
    """Executes on-chain transactions based on signals or user requests.

    Requires AGENT_PRIVATE_KEY to be set in environment for signing.
    Without a key, the agent runs in read-only / simulation mode.
    """

    def __init__(self, agent_id: str = "executor-0") -> None:
        super().__init__(agent_id=agent_id, agent_type="execution")
        self._pending_orders: list[dict[str, Any]] = []
        self._read_only: bool = True

    async def setup(self) -> None:
        """Initialise execution agent.

        Future implementation:
        - Load wallet from AGENT_PRIVATE_KEY
        - Check nonce and gas balance
        - Set read_only flag based on key availability
        """
        self.logger.info("ExecutionAgent setup (read_only=%s)", self._read_only)

    async def step(self) -> None:
        """Process pending orders queue.

        Future implementation:
        1. Pop next order from queue
        2. Estimate gas cost
        3. Build transaction via appropriate chain module
        4. Sign and submit
        5. Wait for confirmation
        6. Emit result event via WebSocket
        """
        self._current_task = "processing_orders"
        # TODO: Process pending orders
        self._current_task = None

    async def teardown(self) -> None:
        """Cancel any pending orders, cleanup."""
        self.logger.info("ExecutionAgent teardown complete")

    async def execute_swap(
        self,
        market_id: str,
        side: str,
        amount: float,
        slippage_bps: int = 50,
    ) -> dict[str, Any]:
        """Execute a spot market swap on Synthetix V3.

        Args:
            market_id: Target synth market ID.
            side: 'buy' or 'sell'.
            amount: Amount in axUSD (for buy) or synth tokens (for sell).
            slippage_bps: Maximum acceptable slippage in basis points.

        Returns:
            Transaction receipt or simulation result.
        """
        # TODO: Build and submit via chain/synthetix.py
        return {
            "status": "simulated",
            "market_id": market_id,
            "side": side,
            "amount": amount,
        }

    async def add_liquidity(
        self,
        token_a: str,
        token_b: str,
        amount_a: float,
        amount_b: float,
    ) -> dict[str, Any]:
        """Add liquidity to a Uniswap V2 pool.

        Args:
            token_a: Address of token A.
            token_b: Address of token B.
            amount_a: Amount of token A to deposit.
            amount_b: Amount of token B to deposit.

        Returns:
            Transaction receipt with LP token amount received.
        """
        # TODO: Build and submit via chain/uniswap_v2.py
        return {"status": "simulated", "lp_tokens": 0}
