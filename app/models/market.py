"""Market data models."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class MarketType(str, Enum):
    SPOT = "spot"
    PERP = "perp"
    PREDICTION = "prediction"


class Sport(str, Enum):
    NFL = "nfl"
    NBA = "nba"
    MLB = "mlb"
    NHL = "nhl"
    SOCCER = "soccer"
    OTHER = "other"


class MarketSummary(BaseModel):
    """Lightweight market listing item."""

    market_id: str = Field(..., description="Unique market identifier (on-chain synth ID or UMA market address)")
    name: str = Field(..., description="Human-readable market name, e.g. 'Patrick Mahomes pNFT'")
    market_type: MarketType
    sport: Sport | None = None
    price_usd: float | None = Field(None, description="Current mid-price in USD")
    volume_24h_usd: float | None = None


class OracleInfo(BaseModel):
    """Oracle configuration for a market."""

    oracle_node_id: str | None = None
    oracle_manager: str | None = None
    last_update_timestamp: int | None = None


class MarketDetail(BaseModel):
    """Full market detail view."""

    market_id: str
    name: str
    market_type: MarketType
    sport: Sport | None = None
    price_usd: float | None = None
    volume_24h_usd: float | None = None
    total_liquidity_usd: float | None = None
    open_interest_usd: float | None = None
    contract_address: str | None = None
    synth_token_address: str | None = None
    oracle: OracleInfo | None = None
    metadata: dict | None = None
