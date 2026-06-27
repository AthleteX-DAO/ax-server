"""Web3 provider management — multi-chain support.

Manages Web3 instances for each supported chain and provides
a clean interface for the rest of the application.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import TYPE_CHECKING

from web3 import Web3

if TYPE_CHECKING:
    from app.config import Settings

logger = logging.getLogger("ax-server.chain")

# Supported chains
CHAIN_NAMES: dict[int, str] = {
    137: "polygon",
    8453: "base",
    42161: "arbitrum",
}


class ChainProvider:
    """Multi-chain Web3 provider manager.

    Lazily creates Web3 instances per chain and caches them.
    The default chain is Polygon (137).
    """

    def __init__(self, rpc_urls: dict[int, str], default_chain_id: int = 137) -> None:
        self._rpc_urls = rpc_urls
        self._instances: dict[int, Web3] = {}
        self.default_chain_id = default_chain_id
        self._addresses = None

    @classmethod
    def from_settings(cls, settings: Settings) -> ChainProvider:
        """Create a ChainProvider from application settings."""
        rpc_urls = {
            137: settings.polygon_rpc_url,
            8453: settings.base_rpc_url,
            42161: settings.arbitrum_rpc_url,
        }
        provider = cls(rpc_urls=rpc_urls, default_chain_id=settings.default_chain_id)
        provider._addresses = settings.addresses
        return provider

    @property
    def addresses(self):
        """Contract addresses for the active chain."""
        if self._addresses is None:
            from app.config import ChainAddresses
            self._addresses = ChainAddresses()
        return self._addresses

    def get_web3(self, chain_id: int | None = None) -> Web3:
        """Get or create a Web3 instance for the given chain.

        Args:
            chain_id: EVM chain ID. Defaults to the configured default.

        Returns:
            Connected Web3 instance.

        Raises:
            ValueError: If chain_id is not supported.
        """
        cid = chain_id or self.default_chain_id
        if cid not in self._instances:
            rpc_url = self._rpc_urls.get(cid)
            if not rpc_url:
                raise ValueError(f"No RPC URL configured for chain_id={cid}")
            self._instances[cid] = Web3(Web3.HTTPProvider(rpc_url))
            logger.info("Created Web3 instance for %s (chain_id=%d)", CHAIN_NAMES.get(cid, "unknown"), cid)
        return self._instances[cid]

    @property
    def w3(self) -> Web3:
        """Shortcut for the default chain Web3 instance."""
        return self.get_web3()

    async def check_connection(self, chain_id: int | None = None) -> bool:
        """Check if the Web3 connection is alive."""
        try:
            w3 = self.get_web3(chain_id)
            _ = w3.eth.block_number
            return True
        except Exception:
            return False
