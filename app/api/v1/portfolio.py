"""Portfolio endpoints — authentication-free wallet reads.

Reads on-chain balances (AX, axUSD, MATIC) and synth positions for a
given wallet address. No private keys required — all data is public.
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Query
from pydantic import BaseModel
from web3 import Web3

from app.config import get_settings
from app.deps import ChainProviderDep
from app.middleware.errors import (
    APIError,
    INVALID_WALLET_ADDRESS,
    MARKET_NOT_FOUND,
    CHAIN_ERROR,
)

logger = logging.getLogger("ax-server.portfolio")

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

# Minimal ERC-20 ABI for balanceOf
_ERC20_BALANCE_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    },
]

_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


# ── Response Models ─────────────────────────────────────────────────────


class VaultState(BaseModel):
    """Collateral and debt state for the wallet's vault position."""

    collateral_ax: str
    collateral_usd: str
    debt_axusd: str
    c_ratio: str | None = None


class BalanceResponse(BaseModel):
    """Wallet balances for core tokens."""

    wallet: str
    ax: str  # string for full 18-decimal precision
    axusd: str
    matic: str
    vault: VaultState | None = None


class Position(BaseModel):
    """Individual synth position."""

    market_id: int
    symbol: str
    synth_address: str
    balance: str
    value_usd: str | None = None


class PositionsResponse(BaseModel):
    """All synth positions for a wallet."""

    wallet: str
    positions: list[Position]


# ── Helpers ─────────────────────────────────────────────────────────────


def _validate_wallet(wallet: str) -> str:
    """Validate and checksum a wallet address."""
    if not _ADDRESS_RE.match(wallet):
        raise APIError(
            code=INVALID_WALLET_ADDRESS,
            message=f"Invalid Ethereum address: {wallet}",
            status_code=400,
        )
    return Web3.to_checksum_address(wallet)


def _read_erc20_balance(w3: Web3, token_address: str, wallet: str) -> int:
    """Read balanceOf for an ERC-20 token. Returns raw wei value."""
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(token_address),
        abi=_ERC20_BALANCE_ABI,
    )
    return contract.functions.balanceOf(wallet).call()


# ── Endpoints ───────────────────────────────────────────────────────────


@router.get("/balance", response_model=BalanceResponse)
async def get_wallet_balance(
    chain: ChainProviderDep,
    wallet: str = Query(..., description="Wallet address (0x...)"),
) -> BalanceResponse:
    """Return AX, axUSD, and MATIC balances for a wallet.

    Also returns vault state (collateral + debt) if the wallet has an
    active Synthetix V3 vault position.
    """
    wallet = _validate_wallet(wallet)
    settings = get_settings()
    w3 = chain.w3

    try:
        # Native MATIC balance
        matic_raw = w3.eth.get_balance(wallet)

        # ERC-20 balances
        ax_raw = _read_erc20_balance(w3, settings.addresses.ax_token, wallet)
        axusd_raw = _read_erc20_balance(w3, settings.addresses.usd_proxy, wallet)
    except Exception as exc:
        logger.exception("Failed to read balances for %s", wallet)
        raise APIError(
            code=CHAIN_ERROR,
            message="Failed to read on-chain balances",
            status_code=502,
            details=str(exc),
        ) from exc

    # Attempt to read vault state from CoreProxy
    vault: VaultState | None = None
    try:
        from app.chain.contracts import get_contract

        core = get_contract(w3, settings.addresses.core_proxy, "core_proxy")
        # Try to read account collateral for account 1 (simplified)
        # Full implementation would enumerate accounts owned by wallet
        collateral_result = core.functions.getAccountCollateral(
            1, Web3.to_checksum_address(settings.addresses.ax_token)
        ).call()
        deposited = collateral_result[0]

        # Get collateral price
        collateral_price = core.functions.getCollateralPrice(
            Web3.to_checksum_address(settings.addresses.ax_token)
        ).call()
        collateral_usd = deposited * collateral_price // (10**18)

        # Get debt
        debt_raw = core.functions.getPositionDebt(
            1, 1, Web3.to_checksum_address(settings.addresses.ax_token)
        ).call()

        c_ratio: str | None = None
        if debt_raw > 0:
            c_ratio = str(round(collateral_usd / debt_raw, 4))

        vault = VaultState(
            collateral_ax=str(deposited),
            collateral_usd=str(collateral_usd),
            debt_axusd=str(debt_raw),
            c_ratio=c_ratio,
        )
    except Exception:
        # Wallet may not have a vault position — this is fine
        logger.debug("No vault position for %s (or read failed)", wallet)

    return BalanceResponse(
        wallet=wallet,
        ax=str(ax_raw),
        axusd=str(axusd_raw),
        matic=str(matic_raw),
        vault=vault,
    )


@router.get("/positions", response_model=PositionsResponse)
async def get_wallet_positions(
    chain: ChainProviderDep,
    wallet: str = Query(..., description="Wallet address (0x...)"),
) -> PositionsResponse:
    """Return synth token balances for each spot market.

    Enumerates known spot markets and reads the wallet's balance of each
    synth token.
    """
    wallet = _validate_wallet(wallet)
    settings = get_settings()
    w3 = chain.w3

    positions: list[Position] = []

    try:
        from app.chain.contracts import get_contract

        spot = get_contract(
            w3, settings.addresses.spot_market_proxy, "spot_market_proxy"
        )

        # Known market IDs — mirrors spot.py
        # TODO: read dynamically from on-chain registry
        known_ids = [1, 2, 3, 4, 5]

        for mid in known_ids:
            try:
                # getSynth(uint128 marketId) → address
                synth_address = spot.functions.getSynth(mid).call()
                synth_address = Web3.to_checksum_address(synth_address)

                balance = _read_erc20_balance(w3, synth_address, wallet)
                if balance == 0:
                    continue

                # Try to get a human-readable name
                symbol = f"sAX-{mid}"
                try:
                    name_result = spot.functions.name(mid).call()
                    if name_result:
                        symbol = name_result
                except Exception:
                    pass

                # Try to price the position
                value_usd: str | None = None
                try:
                    price = spot.functions.indexPrice(mid).call()
                    value_usd = str(balance * price // (10**18))
                except Exception:
                    pass

                positions.append(
                    Position(
                        market_id=mid,
                        symbol=symbol,
                        synth_address=synth_address,
                        balance=str(balance),
                        value_usd=value_usd,
                    )
                )
            except Exception:
                logger.debug("Skipping market %d for %s", mid, wallet)
                continue

    except Exception as exc:
        logger.exception("Failed to read positions for %s", wallet)
        raise APIError(
            code=CHAIN_ERROR,
            message="Failed to read on-chain positions",
            status_code=502,
            details=str(exc),
        ) from exc

    return PositionsResponse(wallet=wallet, positions=positions)
