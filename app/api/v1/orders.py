"""Unsigned transaction builders — exchange-grade order endpoints.

Returns unsigned transaction calldata for client-side signing.
NO private keys ever touch the server.
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter
from pydantic import BaseModel
from web3 import Web3

from app.config import get_settings
from app.deps import ChainProviderDep
from app.middleware.errors import (
    APIError,
    INVALID_MARKET_ID,
    INVALID_WALLET_ADDRESS,
    INVALID_AMOUNT,
    CHAIN_ERROR,
    CONTRACT_REVERT,
)

logger = logging.getLogger("ax-server.orders")

router = APIRouter(prefix="/orders", tags=["orders"])

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")

# Minimal ERC-20 approve ABI
_ERC20_APPROVE_ABI = [
    {
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    },
]


# ── Request / Response Models ───────────────────────────────────────────


class BuildBuyRequest(BaseModel):
    """Request body for building a buy transaction."""

    market_id: int
    usd_amount: str  # wei string
    min_received: str = "0"  # slippage protection
    wallet: str


class BuildSellRequest(BaseModel):
    """Request body for building a sell transaction."""

    market_id: int
    synth_amount: str  # wei string
    min_received: str = "0"  # slippage protection
    wallet: str


class BuildApproveRequest(BaseModel):
    """Request body for building an ERC-20 approve transaction."""

    token_address: str
    spender: str
    amount: str  # wei string
    wallet: str


class UnsignedTransaction(BaseModel):
    """Unsigned transaction payload for client-side signing."""

    to: str
    data: str
    value: str = "0"
    gas_estimate: int | None = None
    chain_id: int


# ── Validators ──────────────────────────────────────────────────────────


def _validate_address(addr: str, field_name: str = "address") -> str:
    """Validate and checksum an Ethereum address."""
    if not _ADDRESS_RE.match(addr):
        raise APIError(
            code=INVALID_WALLET_ADDRESS,
            message=f"Invalid {field_name}: {addr}",
            status_code=400,
        )
    return Web3.to_checksum_address(addr)


def _validate_amount(amount: str, field_name: str = "amount") -> int:
    """Validate and parse a wei amount string."""
    try:
        value = int(amount)
        if value <= 0:
            raise ValueError("must be positive")
        return value
    except (ValueError, TypeError) as exc:
        raise APIError(
            code=INVALID_AMOUNT,
            message=f"Invalid {field_name}: {amount}. Must be a positive integer (wei).",
            status_code=400,
        ) from exc


# ── Endpoints ───────────────────────────────────────────────────────────


@router.post("/build-buy", response_model=UnsignedTransaction)
async def build_buy_transaction(
    body: BuildBuyRequest,
    chain: ChainProviderDep,
) -> UnsignedTransaction:
    """Build an unsigned buy transaction for a spot synth market.

    Constructs calldata for ``SpotMarketProxy.buy(marketId, usdAmount, minAmountReceived, referrer)``
    and returns it for client-side signing. The server never handles private keys.
    """
    wallet = _validate_address(body.wallet, "wallet")
    usd_amount = _validate_amount(body.usd_amount, "usd_amount")
    min_received = int(body.min_received) if body.min_received != "0" else 0

    settings = get_settings()
    w3 = chain.w3

    try:
        from app.chain.contracts import get_contract

        spot = get_contract(
            w3, settings.addresses.spot_market_proxy, "spot_market_proxy"
        )

        # Build transaction — buy(uint128 marketId, uint256 usdAmount, uint256 minAmountReceived, address referrer)
        tx = spot.functions.buy(
            body.market_id,
            usd_amount,
            min_received,
            wallet,  # referrer = self
        ).build_transaction(
            {
                "from": wallet,
                "value": 0,
                "chainId": settings.default_chain_id,
            }
        )

        # Estimate gas
        gas_estimate: int | None = None
        try:
            gas_estimate = w3.eth.estimate_gas(
                {"from": wallet, "to": tx["to"], "data": tx["data"], "value": 0}
            )
        except Exception:
            logger.debug("Gas estimation failed for buy, using build_tx default")
            gas_estimate = tx.get("gas")

    except APIError:
        raise
    except Exception as exc:
        logger.exception("Failed to build buy tx for market %d", body.market_id)
        raise APIError(
            code=CONTRACT_REVERT,
            message=f"Failed to build buy transaction for market {body.market_id}",
            status_code=400,
            details=str(exc),
        ) from exc

    return UnsignedTransaction(
        to=tx["to"],
        data=tx["data"],
        value=str(tx.get("value", 0)),
        gas_estimate=gas_estimate,
        chain_id=settings.default_chain_id,
    )


@router.post("/build-sell", response_model=UnsignedTransaction)
async def build_sell_transaction(
    body: BuildSellRequest,
    chain: ChainProviderDep,
) -> UnsignedTransaction:
    """Build an unsigned sell transaction for a spot synth market.

    Constructs calldata for ``SpotMarketProxy.sell(marketId, synthAmount, minUsdAmount, referrer)``
    and returns it for client-side signing.
    """
    wallet = _validate_address(body.wallet, "wallet")
    synth_amount = _validate_amount(body.synth_amount, "synth_amount")
    min_received = int(body.min_received) if body.min_received != "0" else 0

    settings = get_settings()
    w3 = chain.w3

    try:
        from app.chain.contracts import get_contract

        spot = get_contract(
            w3, settings.addresses.spot_market_proxy, "spot_market_proxy"
        )

        # Build transaction — sell(uint128 marketId, uint256 synthAmount, uint256 minUsdAmount, address referrer)
        tx = spot.functions.sell(
            body.market_id,
            synth_amount,
            min_received,
            wallet,  # referrer = self
        ).build_transaction(
            {
                "from": wallet,
                "value": 0,
                "chainId": settings.default_chain_id,
            }
        )

        gas_estimate: int | None = None
        try:
            gas_estimate = w3.eth.estimate_gas(
                {"from": wallet, "to": tx["to"], "data": tx["data"], "value": 0}
            )
        except Exception:
            logger.debug("Gas estimation failed for sell, using build_tx default")
            gas_estimate = tx.get("gas")

    except APIError:
        raise
    except Exception as exc:
        logger.exception("Failed to build sell tx for market %d", body.market_id)
        raise APIError(
            code=CONTRACT_REVERT,
            message=f"Failed to build sell transaction for market {body.market_id}",
            status_code=400,
            details=str(exc),
        ) from exc

    return UnsignedTransaction(
        to=tx["to"],
        data=tx["data"],
        value=str(tx.get("value", 0)),
        gas_estimate=gas_estimate,
        chain_id=settings.default_chain_id,
    )


@router.post("/build-approve", response_model=UnsignedTransaction)
async def build_approve_transaction(
    body: BuildApproveRequest,
    chain: ChainProviderDep,
) -> UnsignedTransaction:
    """Build an unsigned ERC-20 approve transaction.

    Required before buy/sell if the SpotMarketProxy doesn't yet have
    sufficient allowance for the token being traded.
    """
    wallet = _validate_address(body.wallet, "wallet")
    token_address = _validate_address(body.token_address, "token_address")
    spender = _validate_address(body.spender, "spender")
    amount = _validate_amount(body.amount, "amount")

    settings = get_settings()
    w3 = chain.w3

    try:
        token = w3.eth.contract(
            address=token_address,
            abi=_ERC20_APPROVE_ABI,
        )

        tx = token.functions.approve(spender, amount).build_transaction(
            {
                "from": wallet,
                "value": 0,
                "chainId": settings.default_chain_id,
            }
        )

        gas_estimate: int | None = None
        try:
            gas_estimate = w3.eth.estimate_gas(
                {"from": wallet, "to": tx["to"], "data": tx["data"], "value": 0}
            )
        except Exception:
            logger.debug("Gas estimation failed for approve")
            gas_estimate = tx.get("gas")

    except APIError:
        raise
    except Exception as exc:
        logger.exception("Failed to build approve tx")
        raise APIError(
            code=CONTRACT_REVERT,
            message="Failed to build approve transaction",
            status_code=400,
            details=str(exc),
        ) from exc

    return UnsignedTransaction(
        to=tx["to"],
        data=tx["data"],
        value=str(tx.get("value", 0)),
        gas_estimate=gas_estimate,
        chain_id=settings.default_chain_id,
    )
