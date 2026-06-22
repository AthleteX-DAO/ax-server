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

    On startup:
    - Initialize QuestDB connection pool + ensure tables
    - Start the background price ingest worker

    On shutdown:
    - Stop the ingest worker
    - Close QuestDB connections
    """
    settings = get_settings()
    logger.info("Starting AthleteX server on chain_id=%s", settings.default_chain_id)

    # --- startup -------------------------------------------------

    # QuestDB + Ingest Worker
    questdb_client = None
    ingest_worker = None

    try:
        from app.services.questdb_client import QuestDBClient

        questdb_client = QuestDBClient(
            pg_host=settings.questdb_host,
            pg_port=settings.questdb_pg_port,
            ilp_host=settings.questdb_host,
            ilp_port=settings.questdb_http_port,
            pg_user=settings.questdb_pg_user,
            pg_password=settings.questdb_pg_password,
        )
        await questdb_client.init()
        app.state.questdb = questdb_client
        logger.info("QuestDB client initialized")

        if settings.ingest_enabled:
            from app.chain.subgraph import SubgraphClient
            from app.services.price_ingest import PriceIngestWorker

            subgraph = SubgraphClient(url=settings.dex_subgraph_url)
            ingest_worker = PriceIngestWorker(
                settings=settings,
                questdb=questdb_client,
                subgraph=subgraph,
            )
            await ingest_worker.start()
            logger.info("Price ingest worker started")

    except Exception:
        logger.warning("QuestDB not available — historical data disabled", exc_info=True)
        app.state.questdb = None

    yield

    # --- shutdown ------------------------------------------------
    logger.info("Shutting down AthleteX server")

    if ingest_worker:
        await ingest_worker.stop()

    if questdb_client:
        await questdb_client.close()


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="AthleteX Agentic Backend",
        description="DeFi / Sports Prediction Platform API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # ── Error handlers (exchange-grade structured errors) ─────────
    from app.middleware.errors import register_error_handlers

    register_error_handlers(app)

    # ── Rate limiter (token-bucket, per-IP) ───────────────────────
    from app.middleware.rate_limit import RateLimitMiddleware

    app.add_middleware(RateLimitMiddleware)

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
