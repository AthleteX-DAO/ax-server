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
    market_id: str
    question: str
    outcome1: str
    outcome2: str
    outcome1_price: float
    outcome2_price: float
    resolved: bool = False
    volume: float = 0.0
    category: str = ""


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
