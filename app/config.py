"""Application configuration using pydantic-settings.

Loads from environment variables / .env file.
All chain addresses are checksummed Polygon Mainnet addresses.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ChainAddresses(BaseSettings):
    """Contract addresses for the active chain."""

    model_config = SettingsConfigDict(env_prefix="")

    core_proxy: str = "0x4C2474365eE4d6Ab5c6B5cf3ec860530a9162552"
    usd_proxy: str = "0x1Ea27b8fa8D9Fb4370Dd654ffFad4734D0960fA6"
    spot_market_proxy: str = "0xc79eC919a0A20E29873143AB9658aF75C0b73A23"
    oracle_manager: str = "0x37bCfB2AA84DE620b3ff4eb946a9CbcF1589DCe2"
    rewards_distributor: str = "0x12055514cf8CEf890a012FecCEd580a01c98828a"
    ax_token: str = "0x5617604BA0a30E0ff1d2163aB94E50d8b6D0B0Df"
    multicall3: str = "0xcA11bde05977b3631167028862bE2a173976CA11"
    perps_market_proxy: str = ""  # Not yet deployed
    uma_finder: str = "0x09aea4b2242abC8bb4BB78D537A67a245A7bEC64"
    uma_optimistic_oracle: str = "0x0A2F9bd90e88149F7d60699a8A340F46fE8BA95f"
    apt_factory: str = "0x8720DccfCd5687AfAE5F0BFb56ff664e6D8b385B"
    apt_router: str = "0x15e4eb77713CD274472D95bDfcc7797F6a8C2D95"


class Settings(BaseSettings):
    """Root application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Server ────────────────────────────────────────────────────
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True
    log_level: str = "info"

    # ── CORS ──────────────────────────────────────────────────────
    cors_origins: str = "http://localhost:3000,http://localhost:8080"

    # ── Chain RPC ─────────────────────────────────────────────────
    polygon_rpc_url: str = "https://polygon-rpc.com"
    base_rpc_url: str = "https://mainnet.base.org"
    arbitrum_rpc_url: str = "https://arb1.arbitrum.io/rpc"
    default_chain_id: int = 137

    # ── Agent wallet (optional) ───────────────────────────────────
    agent_private_key: str = ""
    agent_address: str = ""

    # ── External APIs ─────────────────────────────────────────────
    coingecko_api_key: str = ""

    # ── QuestDB (time-series) ─────────────────────────────────────
    questdb_host: str = "localhost"
    questdb_http_port: int = 9000    # ILP ingestion + REST API
    questdb_pg_port: int = 8812      # PostgreSQL wire protocol (asyncpg)
    questdb_pg_user: str = "admin"
    questdb_pg_password: str = "quest"

    # ── Subgraph ──────────────────────────────────────────────────
    dex_subgraph_url: str = "https://api.studio.thegraph.com/query/1743457/athletex-dex/v0.0.1"

    # ── Ingest Worker ─────────────────────────────────────────────
    ingest_poll_interval: int = 30   # seconds between poll cycles
    ingest_backfill_days: int = 30   # days to backfill on first run
    ingest_enabled: bool = True      # set False to disable background ingestion

    # ── Derived ───────────────────────────────────────────────────
    addresses: ChainAddresses = Field(default_factory=ChainAddresses)

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def rpc_url_for_chain(self, chain_id: int) -> str:
        """Return the RPC URL for a given chain ID."""
        mapping = {
            137: self.polygon_rpc_url,
            8453: self.base_rpc_url,
            42161: self.arbitrum_rpc_url,
        }
        url = mapping.get(chain_id)
        if url is None:
            raise ValueError(f"Unsupported chain_id={chain_id}")
        return url


def get_settings() -> Settings:
    """Factory that can be overridden in tests."""
    return Settings()
