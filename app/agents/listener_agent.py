"""Event listener agent.

Responsible for:
- Monitoring on-chain events (Transfer, Swap, MarketCreated, etc.)
- Relaying events to WebSocket clients in real-time
- Tracking prediction market state changes (assertions, disputes, settlements)
- Maintaining a local event log for recovery
"""

from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent


class ListenerAgent(BaseAgent):
    """Listens to on-chain events and broadcasts them via WebSocket.

    Uses web3 event filters / polling to detect new events and
    forwards them to the ConnectionManager for real-time delivery.
    """

    def __init__(self, agent_id: str = "listener-0") -> None:
        super().__init__(agent_id=agent_id, agent_type="listener")
        self._last_block: int = 0
        self._event_filters: list[Any] = []

    async def setup(self) -> None:
        """Set up event filters.

        Future implementation:
        - Get current block number
        - Create filters for key contract events:
          - SpotMarketProxy: SynthBought, SynthSold, MarketCreated
          - CoreProxy: DelegationUpdated, RewardsClaimed
          - UMA: AssertionMade, AssertionResolved
        """
        self.logger.info("ListenerAgent setup complete")

    async def step(self) -> None:
        """Poll for new events since last check.

        Future implementation:
        1. Get new entries from each event filter
        2. Parse and enrich event data
        3. Broadcast via ConnectionManager
        4. Update last_block checkpoint
        """
        self._current_task = "polling_events"
        # TODO: Poll event filters
        self._current_task = None

    async def teardown(self) -> None:
        """Uninstall event filters, save checkpoint."""
        self.logger.info("ListenerAgent teardown complete")

    async def subscribe(self, event_type: str, contract_address: str | None = None) -> str:
        """Add a new event subscription.

        Args:
            event_type: Type of event to subscribe to.
            contract_address: Optional filter for a specific contract.

        Returns:
            Subscription ID for later unsubscription.
        """
        # TODO: Create web3 event filter
        sub_id = f"sub_{event_type}_{len(self._event_filters)}"
        self.logger.info("New subscription: %s", sub_id)
        return sub_id
