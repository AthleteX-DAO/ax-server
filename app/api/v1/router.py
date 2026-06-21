"""V1 API router — aggregates all v1 sub-routers."""

from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.api.v1.markets import router as markets_router
from app.api.v1.positions import router as positions_router
from app.api.v1.agent import router as agent_router
from app.api.v1.share import router as share_router
from app.api.v1.spot import router as spot_router
from app.api.v1.predict import router as predict_router
from app.api.v1.vaults import router as vaults_router
from app.api.v1.versus import router as versus_router
from app.api.v1.exchange import router as exchange_router
from app.api.v1.portfolio import router as portfolio_router
from app.api.v1.orders import router as orders_router
from app.api.v1.auth import router as auth_router
from app.api.v1.history import router as history_router
from app.api.v1.admin import router as admin_router
from app.api.v1.predict_orders import router as predict_orders_router

v1_router = APIRouter(prefix="/api/v1", tags=["v1"])

v1_router.include_router(health_router)
v1_router.include_router(markets_router)
v1_router.include_router(positions_router)
v1_router.include_router(agent_router)
v1_router.include_router(share_router)

# Trading API (Phase 1)
v1_router.include_router(spot_router)
v1_router.include_router(predict_router)
v1_router.include_router(vaults_router)
v1_router.include_router(versus_router)

# Exchange-grade endpoints (Phase 2)
v1_router.include_router(exchange_router)
v1_router.include_router(portfolio_router)
v1_router.include_router(orders_router)

# Authentication (Phase 2)
v1_router.include_router(auth_router)

# Historical data (Phase 2)
v1_router.include_router(history_router)

# Admin (Prediction market deployment)
v1_router.include_router(admin_router)

# Prediction order builders (Phase 3)
v1_router.include_router(predict_orders_router)
