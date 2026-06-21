"""Standardized error responses — exchange-grade error format.

Provides APIError exception, error codes, and FastAPI exception handlers
matching the Kalshi/Polymarket error response pattern.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger("ax-server.errors")


# ── Error Codes ─────────────────────────────────────────────────────────

MARKET_NOT_FOUND = "MARKET_NOT_FOUND"
INVALID_MARKET_ID = "INVALID_MARKET_ID"
INVALID_WALLET_ADDRESS = "INVALID_WALLET_ADDRESS"
INVALID_AMOUNT = "INVALID_AMOUNT"
INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"
RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
CHAIN_ERROR = "CHAIN_ERROR"
CONTRACT_REVERT = "CONTRACT_REVERT"


# ── Exception & Response Model ──────────────────────────────────────────


class APIError(Exception):
    """Structured API error with machine-readable code and HTTP status."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: str | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)


class ErrorResponse(BaseModel):
    """Standard error envelope returned to clients."""

    code: str
    message: str
    details: str | None = None
    service: str = "athletex"


# ── Handler Registration ────────────────────────────────────────────────


def register_error_handlers(app: FastAPI) -> None:
    """Attach global exception handlers to the FastAPI app.

    Catches:
      - APIError  → structured 4xx/5xx with code
      - HTTPException → mapped to ErrorResponse
      - Exception → generic 500 (no leak of internals)
    """

    @app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
        logger.warning(
            "APIError code=%s status=%d path=%s: %s",
            exc.code,
            exc.status_code,
            request.url.path,
            exc.message,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                code=exc.code,
                message=exc.message,
                details=exc.details,
            ).model_dump(),
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                code=f"HTTP_{exc.status_code}",
                message=str(exc.detail),
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception on %s", request.url.path)
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                code="INTERNAL_ERROR",
                message="An internal error occurred",
            ).model_dump(),
        )
