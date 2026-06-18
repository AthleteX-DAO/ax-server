"""FastAPI application factory with lifespan management.

Start with:
    uvicorn app.main:app --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings

logger = logging.getLogger("ax-server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle hook.

    - On startup: initialise chain providers, start listener agents.
    - On shutdown: gracefully stop agents, close connections.
    """
    settings = get_settings()
    logger.info("Starting AthleteX server on chain_id=%s", settings.default_chain_id)

    # --- startup -------------------------------------------------
    # Future: start listener agents, warm caches, open WS subscriptions
    yield
    # --- shutdown ------------------------------------------------
    logger.info("Shutting down AthleteX server")
    # Future: stop agents, close web3 connections


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="AthleteX Agentic Backend",
        description="DeFi / Sports Prediction Platform API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # ── CORS for Flutter web frontend ─────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routers ───────────────────────────────────────────────────
    from app.api.v1.router import v1_router
    from app.api.ws.events import ws_router
    from app.api.v1.share import router as share_public_router

    app.include_router(v1_router)
    app.include_router(ws_router)
    # Mount share page/image at root for clean social URLs: /share/{id}
    app.include_router(share_public_router)

    return app


app = create_app()
