"""Position data models."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class PositionType(str, Enum):
    COLLATERAL = "collateral"
    DELEGATION = "delegation"
    SPOT_SYNTH = "spot_synth"
    LP = "lp"
    PREDICTION = "prediction"
    PERP = "perp"


class Position(BaseModel):
    """A single position held by a user."""

    position_type: PositionType
    protocol: str = Field(..., description="Protocol name: synthetix | uniswap_v2 | uma")
    market_id: str | None = None
    market_name: str | None = None
    token_address: str | None = None
    amount: float = 0.0
    value_usd: float = 0.0
    entry_price: float | None = None
    current_price: float | None = None
    pnl_usd: float | None = None
    metadata: dict | None = None


class PositionSummary(BaseModel):
    """Aggregated positions for a wallet address."""

    address: str
    total_value_usd: float = 0.0
    positions: list[Position] = Field(default_factory=list)
