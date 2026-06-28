"""Pydantic response models for the Trading API.

Organized by domain. Each model is the JSON shape returned to API consumers.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ── Shared ──────────────────────────────────────────────────────────────

class UnsignedTx(BaseModel):
    """Unsigned transaction payload — client signs and submits."""

    to: str
    data: str
    value: str = "0"
    chain_id: int = 137
    gas_estimate: int | None = None


class TxResponse(BaseModel):
    """Standard response for all tx-builder endpoints."""

    transaction: UnsignedTx
    metadata: dict = Field(default_factory=dict)


# ── Spot ────────────────────────────────────────────────────────────────

class SpotMarket(BaseModel):
    market_id: int
    name: str
    synth_address: str = ""
    price_usd: float | None = None
    volume_24h: float | None = None


class SpotPrice(BaseModel):
    market_id: int
    buy_price: float
    sell_price: float
    timestamp: int


class SpotQuote(BaseModel):
    market_id: int
    side: str  # "buy" or "sell"
    amount_in: str
    amount_out: str
    fee: str
    price_impact_bps: int | None = None


# ── Vaults ──────────────────────────────────────────────────────────────

class Pool(BaseModel):
    pool_id: int
    name: str
    collateral_types: list[str] = Field(default_factory=list)


class AccountCollateral(BaseModel):
    account_id: int
    collateral_token: str
    deposited: str  # wei string
    delegated: str
    available: str


class AccountDebt(BaseModel):
    account_id: int
    debt: str  # wei string
    c_ratio: float | None = None


class CollateralPrice(BaseModel):
    token: str
    price_usd: float
    timestamp: int


# ── Prediction ──────────────────────────────────────────────────────────

class PredictMarket(BaseModel):
    """Full prediction market payload consumed by the Flutter frontend."""

    id: int
    prompt: str
    details: str = ""
    market_address: str = ""
    yes_token_address: str = ""
    no_token_address: str = ""
    yes_name: str = "YES"
    no_name: str = "NO"
    yes_price: float = 0.50
    no_price: float = 0.50
    trading_volume: float = 0.0
    end_date: str = ""
    category: str = ""
    resolved: bool | None = None


class PredictPrice(BaseModel):
    market_id: str
    yes_price: float
    no_price: float
    timestamp: int


class PredictPosition(BaseModel):
    market_id: str
    wallet: str
    outcome1_balance: str  # wei
    outcome2_balance: str  # wei


class PricePoint(BaseModel):
    """Single price data point."""

    timestamp: str
    price: float


class PriceHistory(BaseModel):
    """YES/NO price history for a prediction market."""

    market_id: int
    yes_history: list[PricePoint] = Field(default_factory=list)
    no_history: list[PricePoint] = Field(default_factory=list)


# ── Versus ──────────────────────────────────────────────────────────────

class VersusAthlete(BaseModel):
    athlete_id: str
    name: str
    team: str = ""
    category: str = ""
    elo: float = 1500.0
    wins: int = 0
    losses: int = 0
    record: str = "0-0"
    win_pct: float = 0.0
    rank: int | None = None


class VersusMatchup(BaseModel):
    athlete_a: VersusAthlete
    athlete_b: VersusAthlete


# ── Admin / Deployment ──────────────────────────────────────────────────

class DeployMarketRequest(BaseModel):
    """Request to deploy a new prediction market."""

    pair_name: str
    question: str
    category: str = ""
    details: str = ""
    resolve_by: str = ""
    initial_liquidity_usd: float = 1000.0


class InitializeMarketRequest(BaseModel):
    """Request to initialize a prediction market (admin bypass)."""

    market_address: str


class ResolveMarketRequest(BaseModel):
    """Request to resolve a prediction market via ownerResolve."""

    market_address: str
    outcome: str  # "YES", "NO", or "SPLIT"


class UpdateMarketStatusRequest(BaseModel):
    """Request to update a market's registry status."""

    status: str  # "active" | "paused" | "resolved" | "settled"


class RegisterMarketRequest(BaseModel):
    """Request to register an already-deployed market."""

    contract_address: str
    yes_token: str
    no_token: str
    question: str
    category: str = ""
    details: str = ""
    resolve_by: str = ""
    pair_name: str = ""


class MarketOnChainData(BaseModel):
    """On-chain state snapshot for a prediction market."""

    price_requested: bool = False
    market_resolved: bool = False
    settlement_price: str = "0"
    yes_total_supply: str = "0"
    no_total_supply: str = "0"
    yes_price: float = 0.5
    no_price: float = 0.5


class RegisteredMarket(BaseModel):
    """A market stored in the deployment registry."""

    market_address: str = Field(default="", alias="market_address")
    yes_token: str = ""
    no_token: str = ""
    question: str = ""
    category: str = ""
    details: str = ""
    resolve_by: str = ""
    pair_name: str = ""
    yes_pair_address: str | None = None
    no_pair_address: str | None = None
    registered_at: str = ""
    status: str = "active"
    outcome: str | None = None
    resolved_at: str | None = None
    on_chain: MarketOnChainData | None = None

    model_config = {"populate_by_name": True}


class DeployMarketResponse(BaseModel):
    """Response from market deployment or registration."""

    status: str
    market: RegisteredMarket


# ── Comments ────────────────────────────────────────────────────────────

class Comment(BaseModel):
    id: str
    market_id: int
    wallet: str
    text: str
    timestamp: str
    display_name: str | None = None

class CreateCommentRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
