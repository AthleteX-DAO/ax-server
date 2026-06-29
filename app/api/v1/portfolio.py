"""Portfolio endpoints — authentication-free wallet reads.

Reads on-chain balances (AX, axUSD, USDC, MATIC/POL) and Synthetix V3
account positions for a given wallet address.  No private keys required —
all data is public.
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Query
from pydantic import BaseModel
from web3 import Web3

from app.config import get_settings
from app.deps import SynthetixClientDep
from app.middleware.errors import (
    APIError,
    INVALID_WALLET_ADDRESS,
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

# Known USDC addresses on Polygon
_USDC_NATIVE = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"
_USDC_BRIDGED = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"

# Synthetix V3 pool ID for AX
_POOL_ID = 1


# ── Response Models ─────────────────────────────────────────────────────


class AccountState(BaseModel):
    """Collateral and debt state for a single Synthetix V3 account."""

    account_id: str
    collateral_deposited: str
    collateral_assigned: str
    collateral_available: str
    debt: str
    c_ratio: str | None = None


class BalanceResponse(BaseModel):
    """Wallet balances for core tokens plus Synthetix V3 accounts."""

    wallet: str
    ax: str
    axusd: str
    usdc: str
    matic: str  # POL native balance in wei
    gas_price_gwei: float
    accounts: list[AccountState]


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


class UnsignedTxResponse(BaseModel):
    """Returned unsigned transaction ready for MetaMask / wallet signing."""

    to: str
    data: str
    value: str
    chain_id: int


class BuildApproveRequest(BaseModel):
    token_address: str
    spender: str
    amount: str
    wallet: str


class BuildDepositRequest(BaseModel):
    account_id: int
    collateral_type: str
    amount: str
    wallet: str


class BuildWithdrawRequest(BaseModel):
    account_id: int
    collateral_type: str
    amount: str
    wallet: str


class BuildDelegateRequest(BaseModel):
    account_id: int
    pool_id: int
    collateral_type: str
    amount: str
    wallet: str


class BuildCreateAccountRequest(BaseModel):
    wallet: str


class BuildMintUsdRequest(BaseModel):
    account_id: int
    pool_id: int
    collateral_type: str
    amount: str
    wallet: str


class BuildWrapRequest(BaseModel):
    market_id: int
    wrap_amount: str
    wallet: str

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


def _safe_usdc_balance(w3: Web3, wallet: str) -> int:
    """Sum of native USDC + bridged USDC.e balances (both 6 decimals)."""
    total = 0
    for addr in (_USDC_NATIVE, _USDC_BRIDGED):
        try:
            total += _read_erc20_balance(w3, addr, wallet)
        except Exception:
            logger.debug("Could not read USDC at %s for %s", addr, wallet)
    return total


def _enumerate_accounts(snx, wallet: str) -> list[int]:
    """Discover all Synthetix V3 account IDs owned by *wallet*.

    1. Read the Account NFT address from the SynthetixClient.
    2. Call balanceOf / tokenOfOwnerByIndex on the ERC-721 NFT.
    """
    from app.chain.contracts import get_contract

    nft_address = snx.get_account_token_address()
    nft = get_contract(snx.w3, nft_address, "account_nft")

    count = nft.functions.balanceOf(wallet).call()
    account_ids: list[int] = []
    for i in range(count):
        token_id = nft.functions.tokenOfOwnerByIndex(wallet, i).call()
        account_ids.append(token_id)
    return account_ids


def _read_account_state(
    snx,
    account_id: int,
    collateral_type: str,
    pool_id: int,
) -> AccountState:
    """Read collateral / debt / c-ratio for a single account."""
    # getAccountCollateral → (totalDeposited, totalAssigned, totalLocked)
    deposited, assigned, _locked = snx.get_account_collateral(
        account_id, collateral_type
    )

    # Available collateral (withdrawable)
    available = snx.get_available_collateral(account_id, collateral_type)

    # Debt
    debt = snx.get_position_debt(account_id, pool_id, collateral_type)

    # C-ratio (on-chain returns 0 when no debt)
    c_ratio_raw: str | None = None
    try:
        cr = snx.get_position_c_ratio(
            account_id, pool_id, collateral_type
        )
        if cr > 0:
            c_ratio_raw = str(cr)
    except Exception:
        pass

    return AccountState(
        account_id=str(account_id),
        collateral_deposited=str(deposited),
        collateral_assigned=str(assigned),
        collateral_available=str(available),
        debt=str(debt),
        c_ratio=c_ratio_raw,
    )


# ── Endpoints ───────────────────────────────────────────────────────────


@router.get("/balance", response_model=BalanceResponse)
async def get_wallet_balance(
    snx: SynthetixClientDep,
    wallet: str = Query(..., description="Wallet address (0x...)"),
) -> BalanceResponse:
    """Return AX, axUSD, USDC, MATIC balances and Synthetix V3 accounts."""
    wallet = _validate_wallet(wallet)
    settings = get_settings()
    w3 = snx.w3

    try:
        # Native POL / MATIC balance
        matic_raw = w3.eth.get_balance(wallet)

        # ERC-20 balances
        ax_raw = _read_erc20_balance(w3, settings.addresses.ax_token, wallet)
        axusd_raw = _read_erc20_balance(w3, settings.addresses.usd_proxy, wallet)
        usdc_raw = _safe_usdc_balance(w3, wallet)

        # Gas price
        gas_price_wei = w3.eth.gas_price
        gas_price_gwei = round(gas_price_wei / 1e9, 4)
    except Exception as exc:
        logger.exception("Failed to read balances for %s", wallet)
        raise APIError(
            code=CHAIN_ERROR,
            message="Failed to read on-chain balances",
            status_code=502,
            details=str(exc),
        ) from exc

    # Enumerate Synthetix V3 accounts and read state for each
    accounts: list[AccountState] = []
    try:
        account_ids = _enumerate_accounts(snx, wallet)

        for aid in account_ids:
            try:
                state = _read_account_state(
                    snx, aid, settings.addresses.ax_token, _POOL_ID
                )
                accounts.append(state)
            except Exception:
                logger.debug(
                    "Could not read state for account %d of %s", aid, wallet
                )
    except Exception:
        logger.debug("No Synthetix V3 accounts for %s (or read failed)", wallet)

    return BalanceResponse(
        wallet=wallet,
        ax=str(ax_raw),
        axusd=str(axusd_raw),
        usdc=str(usdc_raw),
        matic=str(matic_raw),
        gas_price_gwei=gas_price_gwei,
        accounts=accounts,
    )


@router.get("/positions", response_model=PositionsResponse)
async def get_wallet_positions(
    snx: SynthetixClientDep,
    wallet: str = Query(..., description="Wallet address (0x...)"),
) -> PositionsResponse:
    """Return synth token balances for each spot market.

    Enumerates known spot markets and reads the wallet's balance of each
    synth token.
    """
    wallet = _validate_wallet(wallet)
    w3 = snx.w3

    positions: list[Position] = []

    try:
        # Known market IDs — mirrors spot.py
        # TODO: read dynamically from on-chain registry
        known_ids = [1, 2, 3, 4, 5]

        for mid in known_ids:
            try:
                synth_address = snx.get_synth_address(mid)
                synth_address = Web3.to_checksum_address(synth_address)

                balance = _read_erc20_balance(w3, synth_address, wallet)
                if balance == 0:
                    continue

                # Try to get a human-readable name
                symbol = f"sAX-{mid}"
                try:
                    name_result = snx.get_synth_market_name(mid)
                    if name_result:
                        symbol = name_result
                except Exception:
                    pass

                # Try to price the position
                value_usd: str | None = None
                try:
                    price = snx.get_index_price(mid)
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


# ── Transaction Builders ────────────────────────────────────────────────

@router.post("/build-approve", response_model=UnsignedTxResponse)
async def build_approve(
    req: BuildApproveRequest, snx: SynthetixClientDep
) -> UnsignedTxResponse:
    w3 = snx.w3
    spender_addr = Web3.to_checksum_address(req.spender)
    token_addr = Web3.to_checksum_address(req.token_address)
    
    # Generic ERC20 ABI for approve
    abi = [
        {
            "constant": False,
            "inputs": [
                {"name": "_spender", "type": "address"},
                {"name": "_value", "type": "uint256"}
            ],
            "name": "approve",
            "outputs": [{"name": "", "type": "bool"}],
            "type": "function"
        }
    ]
    contract = w3.eth.contract(address=token_addr, abi=abi)
    amount_wei = int(req.amount)
    
    data = contract.functions.approve(spender_addr, amount_wei)._encode_transaction_data()
    return UnsignedTxResponse(
        to=token_addr,
        data=data,
        value="0",
        chain_id=w3.eth.chain_id,
    )


@router.post("/build-deposit", response_model=UnsignedTxResponse)
async def build_deposit(
    req: BuildDepositRequest, snx: SynthetixClientDep
) -> UnsignedTxResponse:
    tx = snx.build_deposit_tx(
        account_id=req.account_id,
        collateral_type=req.collateral_type,
        amount=int(req.amount),
    )
    return UnsignedTxResponse(**tx)


@router.post("/build-withdraw", response_model=UnsignedTxResponse)
async def build_withdraw(
    req: BuildWithdrawRequest, snx: SynthetixClientDep
) -> UnsignedTxResponse:
    tx = snx.build_withdraw_tx(
        account_id=req.account_id,
        collateral_type=req.collateral_type,
        amount=int(req.amount),
    )
    return UnsignedTxResponse(**tx)


@router.post("/build-delegate", response_model=UnsignedTxResponse)
async def build_delegate(
    req: BuildDelegateRequest, snx: SynthetixClientDep
) -> UnsignedTxResponse:
    tx = snx.build_delegate_tx(
        account_id=req.account_id,
        pool_id=req.pool_id,
        collateral_type=req.collateral_type,
        amount=int(req.amount),
    )
    return UnsignedTxResponse(**tx)


@router.post("/build-undelegate", response_model=UnsignedTxResponse)
async def build_undelegate(
    req: BuildDelegateRequest, snx: SynthetixClientDep
) -> UnsignedTxResponse:
    tx = snx.build_undelegate_tx(
        account_id=req.account_id,
        pool_id=req.pool_id,
        collateral_type=req.collateral_type,
        amount=int(req.amount),
    )
    return UnsignedTxResponse(**tx)


@router.post("/build-create-account", response_model=UnsignedTxResponse)
async def build_create_account(
    req: BuildCreateAccountRequest, snx: SynthetixClientDep
) -> UnsignedTxResponse:
    tx = snx.build_create_account_tx()
    return UnsignedTxResponse(**tx)


@router.post("/build-mint", response_model=UnsignedTxResponse)
async def build_mint(
    req: BuildMintUsdRequest, snx: SynthetixClientDep
) -> UnsignedTxResponse:
    tx = snx.build_mint_usd_tx(
        account_id=req.account_id,
        pool_id=req.pool_id,
        collateral_type=req.collateral_type,
        amount=int(req.amount),
    )
    return UnsignedTxResponse(**tx)


@router.post("/build-wrap", response_model=UnsignedTxResponse)
async def build_wrap(
    req: BuildWrapRequest, snx: SynthetixClientDep
) -> UnsignedTxResponse:
    tx = snx.build_wrap_tx(
        market_id=req.market_id,
        wrap_amount=int(req.wrap_amount),
    )
    return UnsignedTxResponse(**tx)

