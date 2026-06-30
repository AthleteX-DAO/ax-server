"""Oracle Manager API endpoints."""

import logging

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from app.deps import SynthetixClientDep

logger = logging.getLogger("ax-server")

router = APIRouter(prefix="/oracle", tags=["oracle"])


class OraclePriceResponse(BaseModel):
    node_id: str = Field(..., description="The bytes32 oracle node ID")
    price_axusd: float = Field(..., description="Current price denominated in axUSD")
    timestamp: int = Field(..., description="Last update timestamp")


@router.get("/{node_id}", response_model=OraclePriceResponse)
def get_oracle_price(node_id: str, snx: SynthetixClientDep):
    """Fetch current axUSD price for a specific oracle node ID."""
    try:
        if not node_id.startswith("0x"):
            raise ValueError("Node ID must start with 0x")
            
        node_bytes = bytes.fromhex(node_id[2:])
        price_wei, timestamp = snx.get_oracle_price(node_bytes)
        
        return OraclePriceResponse(
            node_id=node_id,
            price_axusd=price_wei / 1e18,
            timestamp=timestamp,
        )
    except Exception as e:
        logger.error(f"Failed to fetch oracle price for {node_id}: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid node ID or oracle lookup failed: {e}")
