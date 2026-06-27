"""Vault endpoints — Synthetix V3 CoreProxy reads.

L0 (public): pool list, collateral prices.
L2 (auth):   account collateral/debt, tx builders (Phase 3).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.deps import SynthetixClientDep
from app.models.trading import AccountCollateral, AccountDebt, CollateralPrice, Pool

router = APIRouter(prefix="/vaults", tags=["vaults"])


@router.get("/pools", response_model=list[Pool])
async def list_pools(snx: SynthetixClientDep):
    """List available pools and their collateral types."""
    try:
        preferred = snx.get_preferred_pool()
        pool_name = snx.get_pool_name(preferred)
        return [Pool(
            pool_id=preferred,
            name=pool_name,
            collateral_types=[snx.addresses.ax_token],
        )]
    except Exception:
        return [Pool(
            pool_id=1,
            name="AthleteX Main Pool",
            collateral_types=[snx.addresses.ax_token],
        )]


@router.get("/collateral-price/{token}", response_model=CollateralPrice)
async def get_collateral_price(token: str, snx: SynthetixClientDep):
    """Get oracle price for a collateral token."""
    try:
        price_raw = snx.get_collateral_price(token)
        price_usd = price_raw / 1e18
    except Exception:
        price_usd = 0.0

    try:
        timestamp = snx.w3.eth.get_block("latest")["timestamp"]
    except Exception:
        timestamp = 0

    return CollateralPrice(
        token=token,
        price_usd=price_usd,
        timestamp=timestamp,
    )


@router.get("/account/{account_id}", response_model=AccountCollateral)
async def get_account_collateral(
    account_id: int,
    snx: SynthetixClientDep,
    collateral: str = "0x5617604BA0a30E0ff1d2163aB94E50d8b6D0B0Df",
):
    """Get collateral deposited/delegated/available for an account."""
    try:
        deposited, assigned, locked = snx.get_account_collateral(
            account_id, collateral
        )
        available = deposited - assigned - locked
    except Exception:
        deposited, assigned, available = 0, 0, 0

    return AccountCollateral(
        account_id=account_id,
        collateral_token=collateral,
        deposited=str(deposited),
        delegated=str(assigned),
        available=str(available),
    )


@router.get("/account/{account_id}/debt", response_model=AccountDebt)
async def get_account_debt(
    account_id: int,
    snx: SynthetixClientDep,
    pool_id: int = 1,
    collateral: str = "0x5617604BA0a30E0ff1d2163aB94E50d8b6D0B0Df",
):
    """Get current debt (axUSD minted) for an account."""
    try:
        debt_raw = snx.get_position_debt(account_id, pool_id, collateral)
        debt = str(debt_raw)
    except Exception:
        debt = "0"

    c_ratio = None
    try:
        cr = snx.get_position_c_ratio(account_id, pool_id, collateral)
        if cr > 0:
            c_ratio = cr / 1e18
    except Exception:
        pass

    return AccountDebt(
        account_id=account_id,
        debt=debt,
        c_ratio=c_ratio,
    )
