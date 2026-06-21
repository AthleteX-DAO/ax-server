"""Auth package — SIWE + JWT authentication for AthleteX."""

from app.auth.siwe import build_siwe_message, verify_siwe, nonce_store
from app.auth.tokens import create_access_token, create_refresh_token, verify_token
from app.auth.deps import RequireAuth, OptionalAuth, RequireAuthFull, RequireMarketMaker

__all__ = [
    "build_siwe_message",
    "verify_siwe",
    "nonce_store",
    "create_access_token",
    "create_refresh_token",
    "verify_token",
    "RequireAuth",
    "OptionalAuth",
    "RequireAuthFull",
    "RequireMarketMaker",
]
