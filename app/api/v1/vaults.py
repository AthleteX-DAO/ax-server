"""Vault endpoints — Synthetix V3 CoreProxy reads.

L0 (public): pool list, collateral prices.
L2 (auth):   account collateral/debt, tx builders (Phase 3).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.deps import ChainProviderDep
from app.models.trading import AccountCollateral, AccountDebt, CollateralPrice, Pool

router = APIRouter(prefix="/vaults", tags=["vaults"])


@router.get("/pools", response_model=list[Pool])
async def list_pools(chain: ChainProviderDep):
    """List available pools and their collateral types."""
    # Synthetix V3 on Polygon has a single preferred pool (pool 1)
    # TODO: Read getPreferredPool() and getApprovedPools() from CoreProxy
    return [
        Pool(
            pool_id=1,
            name="AthleteX Main Pool",
            collateral_types=[
                "0x5617604BA0a30E0ff1d2163aB94E50d8b6D0B0Df",  # AX Token
            ],
        ),
    ]


@router.get("/collateral-price/{token}", response_model=CollateralPrice)
async def get_collateral_price(token: str, chain: ChainProviderDep):
    """Get oracle price for a collateral token."""
    w3 = chain.w3
    from app.chain.contracts import get_contract

    core = get_contract(w3, "0x4C2474365eE4d6Ab5c6B5cf3ec860530a9162552", "core_proxy")

    try:
        # getCollateralPrice(address collateralType) -> uint256
        price_raw = core.functions.getCollateralPrice(
            w3.to_checksum_address(token)
        ).call()
        price_usd = price_raw / 1e18
    except Exception:
        price_usd = 0.0

    return CollateralPrice(
        token=token,
        price_usd=price_usd,
        timestamp=w3.eth.get_block("latest")["timestamp"],
    )


@router.get("/account/{account_id}", response_model=AccountCollateral)
async def get_account_collateral(
    account_id: int,
    collateral: str = "0x5617604BA0a30E0ff1d2163aB94E50d8b6D0B0Df",
    chain: ChainProviderDep = None,
):
    """Get collateral deposited/delegated/available for an account."""
    w3 = chain.w3
    from app.chain.contracts import get_contract

    core = get_contract(w3, "0x4C2474365eE4d6Ab5c6B5cf3ec860530a9162552", "core_proxy")

    try:
        # getAccountCollateral(uint128 accountId, address collateralType)
        # returns (uint256 totalDeposited, uint256 totalAssigned, uint256 totalLocked)
        result = core.functions.getAccountCollateral(
            account_id, w3.to_checksum_address(collateral)
        ).call()
        deposited, assigned, locked = str(result[0]), str(result[1]), str(result[2])
        available = str(result[0] - result[1] - result[2])
    except Exception:
        deposited, assigned, available = "0", "0", "0"

    return AccountCollateral(
        account_id=account_id,
        collateral_token=collateral,
        deposited=deposited,
        delegated=assigned,
        available=available,
    )


@router.get("/account/{account_id}/debt", response_model=AccountDebt)
async def get_account_debt(
    account_id: int,
    pool_id: int = 1,
    collateral: str = "0x5617604BA0a30E0ff1d2163aB94E50d8b6D0B0Df",
    chain: ChainProviderDep = None,
):
    """Get current debt (axUSD minted) for an account."""
    w3 = chain.w3
    from app.chain.contracts import get_contract

    core = get_contract(w3, "0x4C2474365eE4d6Ab5c6B5cf3ec860530a9162552", "core_proxy")

    try:
        # callStatic getPositionDebt(uint128 accountId, uint128 poolId, address collateralType)
        debt_raw = core.functions.getPositionDebt(
            account_id, pool_id, w3.to_checksum_address(collateral)
        ).call()
        debt = str(debt_raw)
    except Exception:
        debt = "0"

    # Calculate c-ratio if we have collateral value
    c_ratio = None
    try:
        collateral_data = await get_account_collateral(account_id, collateral, chain)
        price_data = await get_collateral_price(collateral, chain)
        deposited_val = int(collateral_data.delegated) * price_data.price_usd / 1e18
        debt_val = int(debt) / 1e18
        if debt_val > 0:
            c_ratio = deposited_val / debt_val
    except Exception:
        pass

    return AccountDebt(
        account_id=account_id,
        debt=debt,
        c_ratio=c_ratio,
    )
