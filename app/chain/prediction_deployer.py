"""Prediction market deployment engine — deploys and manages markets on-chain.

Handles contract interaction for EventBasedPredictionMarket contracts,
initial token minting, LP pool creation, and a JSON-file registry of
deployed markets.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from eth_account.signers.local import LocalAccount
from web3 import Web3

from app.chain.contracts import get_contract
from app.chain.uniswap_v2 import UniswapV2Client
from app.config import Settings

logger = logging.getLogger("ax-server.chain.prediction_deployer")

REGISTRY_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "markets_registry.json"
GAS_BUFFER = 1.2


class PredictionDeployer:
    """Deploys and manages prediction markets on-chain."""

    def __init__(self, w3: Web3, account: LocalAccount, settings: Settings) -> None:
        self.w3 = w3
        self.account = account
        self.settings = settings
        self.dex = UniswapV2Client(
            w3,
            router_address=settings.addresses.apt_router,
            factory_address=settings.addresses.apt_factory,
            account=account,
        )

    def _build_tx_params(self) -> dict[str, Any]:
        return {
            "from": self.account.address,
            "chainId": 137,
            "nonce": self.w3.eth.get_transaction_count(self.account.address),
        }

    def _sign_and_send(self, tx: dict[str, Any]) -> str:
        gas = self.w3.eth.estimate_gas(tx)
        tx["gas"] = int(gas * GAS_BUFFER)
        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return tx_hash.hex()

    def _approve_token(self, token_address: str, spender: str, amount: int) -> str:
        """Approve spender for amount on an ERC-20 token."""
        token = get_contract(self.w3, token_address, "erc20")
        tx = token.functions.approve(
            Web3.to_checksum_address(spender),
            amount,
        ).build_transaction(self._build_tx_params())
        return self._sign_and_send(tx)

    async def deploy_market(
        self,
        pair_name: str,
        question: str,
        resolve_by: str,
        category: str,
        details: str,
    ) -> dict[str, str]:
        """Deploy a new EventBasedPredictionMarket contract.

        Returns dict with contract_address, long_token_address, short_token_address.
        """
        # Contract bytecode deployment requires compiled Solidity artifacts.
        # Use register_market() + register-market API for already-deployed contracts.
        raise NotImplementedError("Contract bytecode not available — use /admin/register-market for existing contracts")

    async def create_initial_tokens(self, market_address: str, axusd_amount_wei: int) -> str:
        """Approve axUSD and call market.create() to mint YES+NO tokens.

        Returns:
            Transaction hash of the create() call.
        """
        axusd = self.settings.addresses.usd_proxy
        self._approve_token(axusd, market_address, axusd_amount_wei)

        market = get_contract(self.w3, market_address, "event_based_prediction_market")
        tx = market.functions.create(axusd_amount_wei).build_transaction(self._build_tx_params())
        return self._sign_and_send(tx)

    async def create_lp_pools(
        self,
        yes_token: str,
        no_token: str,
        axusd_per_pool_wei: int,
    ) -> dict[str, Any]:
        """Create YES/axUSD and NO/axUSD LP pools via APTRouter.

        Seeds each pool with equal amounts of token and axUSD (50/50 price).
        """
        axusd = self.settings.addresses.usd_proxy
        router_addr = self.settings.addresses.apt_router
        agent = self.account.address
        deadline = int(time.time()) + 600  # 10 min

        # YES pool
        self._approve_token(yes_token, router_addr, axusd_per_pool_wei)
        self._approve_token(axusd, router_addr, axusd_per_pool_wei)
        yes_receipt = await self.dex.add_liquidity(
            token_a=yes_token,
            token_b=axusd,
            amount_a_desired=axusd_per_pool_wei,
            amount_b_desired=axusd_per_pool_wei,
            amount_a_min=1,
            amount_b_min=1,
            to=agent,
            deadline=deadline,
        )

        # NO pool
        self._approve_token(no_token, router_addr, axusd_per_pool_wei)
        self._approve_token(axusd, router_addr, axusd_per_pool_wei)
        no_receipt = await self.dex.add_liquidity(
            token_a=no_token,
            token_b=axusd,
            amount_a_desired=axusd_per_pool_wei,
            amount_b_desired=axusd_per_pool_wei,
            amount_a_min=1,
            amount_b_min=1,
            to=agent,
            deadline=deadline,
        )

        yes_pair = await self.dex.get_pair(yes_token, axusd)
        no_pair = await self.dex.get_pair(no_token, axusd)

        return {
            "yes_pair_address": yes_pair,
            "no_pair_address": no_pair,
            "yes_tx": yes_receipt.get("transactionHash", "").hex() if isinstance(yes_receipt.get("transactionHash"), bytes) else str(yes_receipt.get("transactionHash", "")),
            "no_tx": no_receipt.get("transactionHash", "").hex() if isinstance(no_receipt.get("transactionHash"), bytes) else str(no_receipt.get("transactionHash", "")),
        }

    async def get_market_data(
        self,
        market_address: str,
        yes_token: str,
        no_token: str,
    ) -> dict[str, Any]:
        """Read on-chain state for a deployed market."""
        market = get_contract(self.w3, market_address, "event_based_prediction_market")
        yes_erc = get_contract(self.w3, yes_token, "erc20")
        no_erc = get_contract(self.w3, no_token, "erc20")

        price_requested = market.functions.priceRequested().call()
        market_resolved = market.functions.marketResolved().call()
        settlement_price = market.functions.settlementPrice().call()

        yes_supply = yes_erc.functions.totalSupply().call()
        no_supply = no_erc.functions.totalSupply().call()

        # Compute prices from LP reserves if pools exist
        axusd = self.settings.addresses.usd_proxy
        yes_price = 0.5
        no_price = 0.5

        yes_pair = await self.dex.get_pair(yes_token, axusd)
        if yes_pair:
            r0, r1 = await self.dex.get_reserves(yes_pair)
            token0 = await self.dex.get_token0(yes_pair)
            if r0 > 0 and r1 > 0:
                if Web3.to_checksum_address(token0) == Web3.to_checksum_address(axusd):
                    yes_price = r0 / (r0 + r1)
                else:
                    yes_price = r1 / (r0 + r1)

        no_pair = await self.dex.get_pair(no_token, axusd)
        if no_pair:
            r0, r1 = await self.dex.get_reserves(no_pair)
            token0 = await self.dex.get_token0(no_pair)
            if r0 > 0 and r1 > 0:
                if Web3.to_checksum_address(token0) == Web3.to_checksum_address(axusd):
                    no_price = r0 / (r0 + r1)
                else:
                    no_price = r1 / (r0 + r1)

        return {
            "price_requested": price_requested,
            "market_resolved": market_resolved,
            "settlement_price": str(settlement_price),
            "yes_total_supply": str(yes_supply),
            "no_total_supply": str(no_supply),
            "yes_price": round(yes_price, 6),
            "no_price": round(no_price, 6),
        }

    async def register_market(self, market_info: dict[str, Any]) -> None:
        """Store deployed market info in the market registry."""
        REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        markets = await self.get_registered_markets()

        # Deduplicate by market_address
        addr = market_info.get("market_address", "")
        markets = [m for m in markets if m.get("market_address") != addr]
        markets.append(market_info)

        with open(REGISTRY_PATH, "w") as f:
            json.dump({"markets": markets}, f, indent=2)
        logger.info("Registered market %s", addr)

    async def get_registered_markets(self) -> list[dict[str, Any]]:
        """Load all registered markets from the registry."""
        if not REGISTRY_PATH.exists():
            return []
        with open(REGISTRY_PATH) as f:
            data = json.load(f)
        if isinstance(data, dict) and "markets" in data:
            return data["markets"]
        if isinstance(data, list):
            return data
        return []
