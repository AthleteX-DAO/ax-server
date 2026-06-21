"""Token-bucket rate limiter middleware.

Implements per-IP rate limiting with three tiers (BASIC, ADVANCED, MARKET_MAKER).
Continuous token refill, not fixed windows. Returns proper 429 responses with
X-RateLimit-* headers.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger("ax-server.rate_limit")

# ── Tier Definitions ────────────────────────────────────────────────────


class RateTier(str, Enum):
    """Rate-limit tiers matching exchange conventions."""

    BASIC = "BASIC"
    ADVANCED = "ADVANCED"
    MARKET_MAKER = "MARKET_MAKER"


# (max_tokens, refill_period_seconds)
_TIER_CONFIG: dict[RateTier, tuple[int, float]] = {
    RateTier.BASIC: (100, 10.0),
    RateTier.ADVANCED: (500, 10.0),
    RateTier.MARKET_MAKER: (2000, 10.0),
}


# ── Bucket State ────────────────────────────────────────────────────────


@dataclass
class TokenBucket:
    """Per-IP token bucket with continuous refill."""

    max_tokens: int
    refill_rate: float  # tokens per second
    tokens: float = field(init=False)
    last_refill: float = field(init=False)

    def __post_init__(self) -> None:
        self.tokens = float(self.max_tokens)
        self.last_refill = time.monotonic()

    def consume(self) -> bool:
        """Try to consume one token. Returns True if allowed."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(
            self.max_tokens,
            self.tokens + elapsed * self.refill_rate,
        )
        self.last_refill = now

        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False

    @property
    def remaining(self) -> int:
        """Tokens remaining (floor to int for headers)."""
        return max(0, int(self.tokens))

    @property
    def reset_seconds(self) -> float:
        """Seconds until at least one token is available."""
        if self.tokens >= 1.0:
            return 0.0
        return (1.0 - self.tokens) / self.refill_rate


# ── Middleware ──────────────────────────────────────────────────────────


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP token-bucket rate limiter.

    Usage::

        app.add_middleware(RateLimitMiddleware, default_tier=RateTier.BASIC)
    """

    # Mapping of IP overrides to tier (set via API or config)
    _ip_tiers: dict[str, RateTier] = {}

    def __init__(
        self,
        app: object,
        default_tier: RateTier = RateTier.BASIC,
        cleanup_interval: float = 60.0,
    ) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.default_tier = default_tier
        self.cleanup_interval = cleanup_interval
        self._buckets: dict[str, TokenBucket] = {}
        self._last_cleanup = time.monotonic()

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP, respecting X-Forwarded-For behind a proxy."""
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "0.0.0.0"

    def _get_bucket(self, ip: str) -> TokenBucket:
        """Get or create a token bucket for the given IP."""
        if ip not in self._buckets:
            tier = self._ip_tiers.get(ip, self.default_tier)
            max_tokens, period = _TIER_CONFIG[tier]
            refill_rate = max_tokens / period
            self._buckets[ip] = TokenBucket(
                max_tokens=max_tokens,
                refill_rate=refill_rate,
            )
        return self._buckets[ip]

    def _cleanup_stale(self) -> None:
        """Remove buckets that haven't been used for >60s."""
        now = time.monotonic()
        if now - self._last_cleanup < self.cleanup_interval:
            return
        self._last_cleanup = now
        stale_threshold = now - self.cleanup_interval
        stale_keys = [
            ip
            for ip, bucket in self._buckets.items()
            if bucket.last_refill < stale_threshold
        ]
        for key in stale_keys:
            del self._buckets[key]
        if stale_keys:
            logger.debug("Cleaned up %d stale rate-limit buckets", len(stale_keys))

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Check rate limit, forward request or return 429.

        If the request includes a valid JWT Bearer token, the rate-limit
        tier is upgraded to match the token's tier (ADVANCED or MARKET_MAKER).
        """
        self._cleanup_stale()

        ip = self._get_client_ip(request)

        # Check for JWT-based tier upgrade
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer ") and len(auth_header) > 10:
            token = auth_header[7:]
            try:
                from app.auth.tokens import verify_token

                payload = verify_token(token, expected_type="access")
                tier_name = payload.tier.upper()
                if tier_name in RateTier.__members__:
                    tier = RateTier(tier_name)
                    self._ip_tiers[ip] = tier
                    # Recreate bucket if tier changed
                    if ip in self._buckets:
                        existing = self._buckets[ip]
                        max_tokens, period = _TIER_CONFIG[tier]
                        if existing.max_tokens != max_tokens:
                            self._buckets[ip] = TokenBucket(
                                max_tokens=max_tokens,
                                refill_rate=max_tokens / period,
                            )
            except Exception:
                pass  # Invalid token — fall back to default tier

        bucket = self._get_bucket(ip)
        tier = self._ip_tiers.get(ip, self.default_tier)
        max_tokens = _TIER_CONFIG[tier][0]

        if not bucket.consume():
            reset_ms = int(bucket.reset_seconds * 1000)
            logger.warning("Rate limit exceeded for %s", ip)
            return JSONResponse(
                status_code=429,
                content={
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": "Rate limit exceeded. Please slow down.",
                    "service": "athletex",
                },
                headers={
                    "X-RateLimit-Limit": str(max_tokens),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_ms),
                    "Retry-After": str(max(1, int(bucket.reset_seconds))),
                },
            )

        response = await call_next(request)

        # Attach rate-limit headers to every response
        response.headers["X-RateLimit-Limit"] = str(max_tokens)
        response.headers["X-RateLimit-Remaining"] = str(bucket.remaining)
        response.headers["X-RateLimit-Reset"] = str(
            int(bucket.reset_seconds * 1000)
        )

        return response
