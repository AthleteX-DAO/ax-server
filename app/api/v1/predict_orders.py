"""Unsigned transaction builders — prediction market order endpoints.

Returns unsigned transaction calldata for client-side signing.
NO private keys ever touch the server.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from web3 import Web3

from app.config import get_settings
from app.deps import ChainProviderDep
from app.middleware.errors import (
    APIError,
    MARKET_NOT_FOUND,
    INVALID_WALLET_ADDRESS,
    INVALID_AMOUNT,
    CHAIN_ERROR,
    CONTRACT_REVERT,
)

logger = logging.getLogger("ax-server.predict-orders")

router = APIRouter(prefix="/predict", tags=["predict-orders"])

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")

_REGISTRY_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "markets_registry.json"

# Minimal ERC-20 ABI (approve + allowance)
_ERC20_ABI = [
    {
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    },
    {
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"},
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
        "stateMutability": "view",
    },
]

# Minimal prediction market ABI (create + redeem)
_PREDICT_MARKET_ABI = [
    {
        "inputs": [{"name": "amount", "type": "uint256"}],
        "name": "create",
        "outputs": [],
        "type": "function",
    },
    {
        "inputs": [{"name": "amount", "type": "uint256"}],
        "name": "redeem",
        "outputs": [],
        "type": "function",
    },
]


# ── Request / Response Models ───────────────────────────────────────────


class PredictBuyRequest(BaseModel):
    """Build unsigned txs to buy YES or NO tokens."""

    market_id: str  # contract address
    outcome: str  # "yes" or "no"
    axusd_amount: str  # wei string
    wallet: str
    slippage_bps: int = 100


class PredictSellRequest(BaseModel):
    """Build unsigned txs to sell YES or NO tokens back for axUSD."""

    market_id: str
    outcome: str
    token_amount: str  # wei string
    wallet: str
    slippage_bps: int = 100


class PredictMintRequest(BaseModel):
    """Build unsigned tx to mint YES+NO tokens by depositing axUSD."""

    market_id: str
    axusd_amount: str  # wei string
    wallet: str


class PredictRedeemRequest(BaseModel):
    """Build unsigned tx to redeem equal YES+NO tokens for axUSD."""

    market_id: str
    token_amount: str  # wei string
    wallet: str


class UnsignedTxPayload(BaseModel):
    """Single unsigned transaction in a multi-tx response."""

    to: str
    data: str
    value: str = "0"
    gas_estimate: int | None = None
    description: str = ""


class BuildTxResponse(BaseModel):
    """Response containing one or more unsigned transactions."""

    transactions: list[UnsignedTxPayload]
    chain_id: int


class PredictQuote(BaseModel):
    """Expected output for a prediction market swap."""

    amount_in: str
    amount_out: str
    price_impact_bps: int | None = None
    path: list[str]


# ── Helpers ─────────────────────────────────────────────────────────────


_REGISTRY_CACHE: dict[str, Any] | None = None


def _load_registry() -> dict[str, Any]:
    """Load the market registry and index by address for fast lookup."""
    global _REGISTRY_CACHE
    if _REGISTRY_CACHE is None:
        if not _REGISTRY_PATH.exists():
            logger.warning("Market registry not found: %s", _REGISTRY_PATH)
            _REGISTRY_CACHE = {}
        else:
            with open(_REGISTRY_PATH) as f:
                data = json.load(f)
            # Support both formats: {"markets": [...]} or flat dict
            if isinstance(data, dict) and "markets" in data:
                _REGISTRY_CACHE = {
                    m["market_address"].lower(): m
                    for m in data["markets"]
                    if "market_address" in m
                }
            elif isinstance(data, dict):
                # Legacy format: keyed by address
                _REGISTRY_CACHE = {k.lower(): v for k, v in data.items()}
            else:
                _REGISTRY_CACHE = {}
    return _REGISTRY_CACHE


def _lookup_market(market_id: str) -> dict[str, Any]:
    """Look up a market by contract address."""
    addr = _validate_address(market_id, "market_id")
    registry = _load_registry()
    market = registry.get(addr.lower())
    if not market:
        raise APIError(
            code=MARKET_NOT_FOUND,
            message=f"Market not found: {addr}",
            status_code=404,
        )
    return market


def _validate_address(addr: str, field_name: str = "address") -> str:
    if not _ADDRESS_RE.match(addr):
        raise APIError(
            code=INVALID_WALLET_ADDRESS,
            message=f"Invalid {field_name}: {addr}",
            status_code=400,
        )
    return Web3.to_checksum_address(addr)


def _validate_amount(amount: str, field_name: str = "amount") -> int:
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


def _validate_outcome(outcome: str) -> str:
    outcome = outcome.lower().strip()
    if outcome not in ("yes", "no"):
        raise APIError(
            code=INVALID_AMOUNT,
            message=f"Invalid outcome: {outcome}. Must be 'yes' or 'no'.",
            status_code=400,
        )
    return outcome


def _resolve_token(market: dict[str, Any], outcome: str) -> str:
    key = "yes_token" if outcome == "yes" else "no_token"
    return Web3.to_checksum_address(market[key])


def _build_tx_payload(
    tx: dict[str, Any],
    w3: Web3,
    wallet: str,
    description: str,
) -> UnsignedTxPayload:
    gas_estimate: int | None = None
    try:
        gas_estimate = w3.eth.estimate_gas(
            {"from": wallet, "to": tx["to"], "data": tx["data"], "value": 0}
        )
    except Exception:
        logger.debug("Gas estimation failed for %s", description)
        gas_estimate = tx.get("gas")

    return UnsignedTxPayload(
        to=tx["to"],
        data=tx["data"],
        value=str(tx.get("value", 0)),
        gas_estimate=gas_estimate,
        description=description,
    )


def _apply_slippage(amount: int, slippage_bps: int) -> int:
    return amount * (10_000 - slippage_bps) // 10_000


def _swap_deadline() -> int:
    return int(time.time()) + 1200  # 20 minutes


# ── Endpoints ───────────────────────────────────────────────────────────


@router.post("/orders/build-buy", response_model=BuildTxResponse)
async def build_predict_buy(
    body: PredictBuyRequest,
    chain: ChainProviderDep,
) -> BuildTxResponse:
    """Build unsigned txs to buy YES or NO tokens.

    Returns approve tx (if needed) + swap tx.
    Path: axUSD → YES/NO token via APTRouter.
    """
    wallet = _validate_address(body.wallet, "wallet")
    amount = _validate_amount(body.axusd_amount, "axusd_amount")
    outcome = _validate_outcome(body.outcome)
    market = _lookup_market(body.market_id)

    settings = get_settings()
    w3 = chain.w3
    router_addr = _validate_address(settings.addresses.apt_router, "apt_router")
    axusd = _validate_address(settings.addresses.usd_proxy, "usd_proxy")
    target_token = _resolve_token(market, outcome)
    path = [axusd, target_token]

    try:
        from app.chain.contracts import get_contract

        transactions: list[UnsignedTxPayload] = []

        # Check allowance — build approve if needed
        token_contract = w3.eth.contract(address=axusd, abi=_ERC20_ABI)
        allowance = token_contract.functions.allowance(wallet, router_addr).call()
        if allowance < amount:
            approve_tx = token_contract.functions.approve(
                router_addr, amount
            ).build_transaction(
                {"from": wallet, "value": 0, "chainId": settings.default_chain_id}
            )
            transactions.append(
                _build_tx_payload(approve_tx, w3, wallet, "Approve axUSD for router")
            )

        # Build swap tx
        apt_router = get_contract(w3, router_addr, "uniswap_v2_router")

        # Get expected output for slippage calc
        amounts_out = apt_router.functions.getAmountsOut(amount, path).call()
        amount_out_min = _apply_slippage(amounts_out[-1], body.slippage_bps)

        swap_tx = apt_router.functions.swapExactTokensForTokens(
            amount, amount_out_min, path, wallet, _swap_deadline()
        ).build_transaction(
            {"from": wallet, "value": 0, "chainId": settings.default_chain_id}
        )
        transactions.append(
            _build_tx_payload(swap_tx, w3, wallet, f"Buy {outcome.upper()} tokens")
        )

    except APIError:
        raise
    except Exception as exc:
        logger.exception("Failed to build predict buy tx for %s", body.market_id)
        raise APIError(
            code=CONTRACT_REVERT,
            message=f"Failed to build buy transaction for market {body.market_id}",
            status_code=400,
            details=str(exc),
        ) from exc

    return BuildTxResponse(transactions=transactions, chain_id=settings.default_chain_id)


@router.post("/orders/build-sell", response_model=BuildTxResponse)
async def build_predict_sell(
    body: PredictSellRequest,
    chain: ChainProviderDep,
) -> BuildTxResponse:
    """Build unsigned txs to sell YES or NO tokens back for axUSD."""
    wallet = _validate_address(body.wallet, "wallet")
    amount = _validate_amount(body.token_amount, "token_amount")
    outcome = _validate_outcome(body.outcome)
    market = _lookup_market(body.market_id)

    settings = get_settings()
    w3 = chain.w3
    router_addr = _validate_address(settings.addresses.apt_router, "apt_router")
    axusd = _validate_address(settings.addresses.usd_proxy, "usd_proxy")
    source_token = _resolve_token(market, outcome)
    path = [source_token, axusd]

    try:
        from app.chain.contracts import get_contract

        transactions: list[UnsignedTxPayload] = []

        # Check allowance on the outcome token
        token_contract = w3.eth.contract(address=source_token, abi=_ERC20_ABI)
        allowance = token_contract.functions.allowance(wallet, router_addr).call()
        if allowance < amount:
            approve_tx = token_contract.functions.approve(
                router_addr, amount
            ).build_transaction(
                {"from": wallet, "value": 0, "chainId": settings.default_chain_id}
            )
            transactions.append(
                _build_tx_payload(
                    approve_tx, w3, wallet, f"Approve {outcome.upper()} token for router"
                )
            )

        # Build swap tx
        apt_router = get_contract(w3, router_addr, "uniswap_v2_router")
        amounts_out = apt_router.functions.getAmountsOut(amount, path).call()
        amount_out_min = _apply_slippage(amounts_out[-1], body.slippage_bps)

        swap_tx = apt_router.functions.swapExactTokensForTokens(
            amount, amount_out_min, path, wallet, _swap_deadline()
        ).build_transaction(
            {"from": wallet, "value": 0, "chainId": settings.default_chain_id}
        )
        transactions.append(
            _build_tx_payload(swap_tx, w3, wallet, f"Sell {outcome.upper()} tokens")
        )

    except APIError:
        raise
    except Exception as exc:
        logger.exception("Failed to build predict sell tx for %s", body.market_id)
        raise APIError(
            code=CONTRACT_REVERT,
            message=f"Failed to build sell transaction for market {body.market_id}",
            status_code=400,
            details=str(exc),
        ) from exc

    return BuildTxResponse(transactions=transactions, chain_id=settings.default_chain_id)


@router.post("/orders/build-mint", response_model=BuildTxResponse)
async def build_predict_mint(
    body: PredictMintRequest,
    chain: ChainProviderDep,
) -> BuildTxResponse:
    """Build unsigned tx to mint YES+NO tokens by depositing axUSD."""
    wallet = _validate_address(body.wallet, "wallet")
    amount = _validate_amount(body.axusd_amount, "axusd_amount")
    market = _lookup_market(body.market_id)
    market_addr = _validate_address(market["market_address"], "market_address")

    settings = get_settings()
    w3 = chain.w3
    axusd = _validate_address(settings.addresses.usd_proxy, "usd_proxy")

    try:
        transactions: list[UnsignedTxPayload] = []

        # Approve axUSD → market contract
        token_contract = w3.eth.contract(address=axusd, abi=_ERC20_ABI)
        allowance = token_contract.functions.allowance(wallet, market_addr).call()
        if allowance < amount:
            approve_tx = token_contract.functions.approve(
                market_addr, amount
            ).build_transaction(
                {"from": wallet, "value": 0, "chainId": settings.default_chain_id}
            )
            transactions.append(
                _build_tx_payload(approve_tx, w3, wallet, "Approve axUSD for market")
            )

        # Build create tx
        market_contract = w3.eth.contract(address=market_addr, abi=_PREDICT_MARKET_ABI)
        create_tx = market_contract.functions.create(amount).build_transaction(
            {"from": wallet, "value": 0, "chainId": settings.default_chain_id}
        )
        transactions.append(
            _build_tx_payload(create_tx, w3, wallet, "Mint YES + NO tokens")
        )

    except APIError:
        raise
    except Exception as exc:
        logger.exception("Failed to build predict mint tx for %s", body.market_id)
        raise APIError(
            code=CONTRACT_REVERT,
            message=f"Failed to build mint transaction for market {body.market_id}",
            status_code=400,
            details=str(exc),
        ) from exc

    return BuildTxResponse(transactions=transactions, chain_id=settings.default_chain_id)


@router.post("/orders/build-redeem", response_model=BuildTxResponse)
async def build_predict_redeem(
    body: PredictRedeemRequest,
    chain: ChainProviderDep,
) -> BuildTxResponse:
    """Build unsigned tx to redeem equal YES+NO tokens for axUSD."""
    wallet = _validate_address(body.wallet, "wallet")
    amount = _validate_amount(body.token_amount, "token_amount")
    market = _lookup_market(body.market_id)
    market_addr = _validate_address(market["market_address"], "market_address")

    settings = get_settings()
    w3 = chain.w3

    try:
        market_contract = w3.eth.contract(address=market_addr, abi=_PREDICT_MARKET_ABI)
        redeem_tx = market_contract.functions.redeem(amount).build_transaction(
            {"from": wallet, "value": 0, "chainId": settings.default_chain_id}
        )

        payload = _build_tx_payload(redeem_tx, w3, wallet, "Redeem YES + NO for axUSD")

    except APIError:
        raise
    except Exception as exc:
        logger.exception("Failed to build predict redeem tx for %s", body.market_id)
        raise APIError(
            code=CONTRACT_REVERT,
            message=f"Failed to build redeem transaction for market {body.market_id}",
            status_code=400,
            details=str(exc),
        ) from exc

    return BuildTxResponse(transactions=[payload], chain_id=settings.default_chain_id)


@router.get("/orders/quote", response_model=PredictQuote)
async def get_predict_quote(
    market_id: str = Query(..., description="Market contract address"),
    outcome: str = Query(..., description="yes or no"),
    amount: str = Query(..., description="Amount in wei"),
    side: str = Query(..., description="buy or sell"),
    chain: ChainProviderDep = ...,
) -> PredictQuote:
    """Get expected output for a prediction market swap."""
    _validate_address(market_id, "market_id")
    validated_amount = _validate_amount(amount, "amount")
    outcome = _validate_outcome(outcome)
    market = _lookup_market(market_id)

    side = side.lower().strip()
    if side not in ("buy", "sell"):
        raise APIError(
            code=INVALID_AMOUNT,
            message=f"Invalid side: {side}. Must be 'buy' or 'sell'.",
            status_code=400,
        )

    settings = get_settings()
    w3 = chain.w3
    router_addr = _validate_address(settings.addresses.apt_router, "apt_router")
    axusd = _validate_address(settings.addresses.usd_proxy, "usd_proxy")
    token = _resolve_token(market, outcome)

    if side == "buy":
        path = [axusd, token]
    else:
        path = [token, axusd]

    try:
        from app.chain.contracts import get_contract

        apt_router = get_contract(w3, router_addr, "uniswap_v2_router")
        amounts = apt_router.functions.getAmountsOut(validated_amount, path).call()

    except APIError:
        raise
    except Exception as exc:
        logger.exception("Failed to get predict quote for %s", market_id)
        raise APIError(
            code=CHAIN_ERROR,
            message=f"Failed to get quote for market {market_id}",
            status_code=502,
            details=str(exc),
        ) from exc

    # Price impact: deviation from 1:1 in basis points
    price_impact_bps: int | None = None
    if validated_amount > 0 and amounts[-1] > 0:
        ratio = amounts[-1] / validated_amount
        price_impact_bps = abs(int((1 - ratio) * 10_000))

    return PredictQuote(
        amount_in=str(amounts[0]),
        amount_out=str(amounts[-1]),
        price_impact_bps=price_impact_bps,
        path=[addr for addr in path],
    )
