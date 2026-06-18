"""Prediction Market endpoints — UMA OOv3 reads.

L0 (public): market list, prices.
L2 (auth):   positions, tx builders (Phase 3).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.deps import ChainProviderDep
from app.models.trading import PredictMarket, PredictPrice

router = APIRouter(prefix="/predict", tags=["predict"])

# ABI fragments for the OOv3 PredictionMarket factory (read-only)
_MARKET_ABI = [
    {"inputs": [{"name": "marketId", "type": "bytes32"}], "name": "getMarket",
     "outputs": [{"components": [
         {"name": "resolved", "type": "bool"},
         {"name": "assertedOutcomeId", "type": "bytes32"},
         {"name": "outcome1Token", "type": "address"},
         {"name": "outcome2Token", "type": "address"},
         {"name": "reward", "type": "uint256"},
         {"name": "requiredBond", "type": "uint256"},
         {"name": "outcome1", "type": "bytes"},
         {"name": "outcome2", "type": "bytes"},
         {"name": "description", "type": "bytes"},
     ], "name": "", "type": "tuple"}],
     "stateMutability": "view", "type": "function"},
]

_ERC20_TOTAL_SUPPLY = [
    {"inputs": [], "name": "totalSupply",
     "outputs": [{"name": "", "type": "uint256"}],
     "stateMutability": "view", "type": "function"},
]


@router.get("/markets", response_model=list[PredictMarket])
async def list_prediction_markets(chain: ChainProviderDep):
    """List all prediction markets.

    NOTE: Until OOv3 factory is deployed, this reads from a config list.
    Once deployed, we'll index MarketInitialized events.
    """
    # TODO: Replace with on-chain event indexing after OOv3 deployment
    # For now, return the known markets from config
    return [
        PredictMarket(
            market_id="aiyuk_trade_2026",
            question="Will Brandon Aiyuk be traded before the 2026 League Year?",
            outcome1="YES",
            outcome2="NO",
            outcome1_price=0.50,
            outcome2_price=0.50,
            resolved=False,
            category="football",
        ),
    ]


@router.get("/markets/{market_id}", response_model=PredictMarket)
async def get_prediction_market(market_id: str, chain: ChainProviderDep):
    """Get single prediction market detail."""
    # TODO: Read from indexed markets DB
    markets = await list_prediction_markets(chain)
    for m in markets:
        if m.market_id == market_id:
            return m
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="Market not found")


@router.get("/markets/{market_id}/price", response_model=PredictPrice)
async def get_prediction_price(market_id: str, chain: ChainProviderDep):
    """YES/NO implied probability from token supply ratio."""
    w3 = chain.w3

    # TODO: Once OOv3 deployed, read outcome token supplies on-chain
    # yes_supply / (yes_supply + no_supply) = yes_price
    return PredictPrice(
        market_id=market_id,
        yes_price=0.50,
        no_price=0.50,
        timestamp=w3.eth.get_block("latest")["timestamp"],
    )
