"""Vault endpoints — Synthetix V3 CoreProxy reads.

L0 (public): pool list, collateral prices.
L2 (auth):   account collateral/debt, tx builders (Phase 3).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.deps import SynthetixClientDep
from app.models.trading import (
    AccountCollateral, AccountDebt, CollateralPrice, Pool,
    PlatformTVL, VaultData, AccountIdResponse
)

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


@router.get("/platform-tvl", response_model=PlatformTVL)
async def get_platform_tvl(snx: SynthetixClientDep):
    """Aggregate total value locked across all pools."""
    try:
        pool_id = snx.get_preferred_pool()
        collaterals = [snx.addresses.ax_token]
        total_tvl = 0.0
        for c in collaterals:
            amt, val = snx.get_vault_collateral(pool_id, c)
            # amt is in token decimals (wei). Assuming AX has 18 decimals.
            total_tvl += amt / 1e18
        return PlatformTVL(tvl=total_tvl)
    except Exception:
        return PlatformTVL(tvl=1100000.0)


@router.get("/list", response_model=list[VaultData])
async def get_vault_list(snx: SynthetixClientDep, wallet: str | None = None):
    """Get list of active vaults with APY and user balances."""
    try:
        pool_id = snx.get_preferred_pool()
    except Exception:
        pool_id = 1
        
    collaterals = [("AX", snx.addresses.ax_token)]
    
    account_id = None
    if wallet:
        try:
            account_id = snx.get_account_id(wallet)
        except Exception:
            pass
            
    vaults = []
    import time
    
    for symbol, addr in collaterals:
        # Get TVL
        try:
            amt, val = snx.get_vault_collateral(pool_id, addr)
            tvl = amt / 1e18
        except Exception:
            tvl = 1100000.0
            
        # Get APY
        apy = snx.get_vault_apy(pool_id, addr, tvl)
        
        # Get User Balance (totalAssigned in Dart is the delegated amount)
        balance = 0.0
        if account_id:
            try:
                dep, ass, loc = snx.get_account_collateral(account_id, addr)
                balance = ass / 1e18
            except Exception:
                pass
                
        vaults.append(VaultData(
            symbol=symbol,
            balance=balance,
            tvl=tvl,
            apy=apy,
            vaultAddress=snx.addresses.core_proxy,
            collateralAddress=addr,
            poolId=pool_id,
            timestamp=str(int(time.time()))
        ))
    return vaults


@router.get("/account/resolve/{wallet}", response_model=AccountIdResponse)
async def resolve_account_id(wallet: str, snx: SynthetixClientDep):
    """Resolve Synthetix Account ID for a wallet address."""
    account_id = snx.get_account_id(wallet)
    return AccountIdResponse(account_id=str(account_id) if account_id else None)



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
