"""FastAPI dependency injection.

Provides shared singletons (settings, web3 provider, services) to route handlers.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.config import Settings, get_settings


@lru_cache
def _settings() -> Settings:
    return get_settings()


SettingsDep = Annotated[Settings, Depends(_settings)]


def get_chain_provider(settings: SettingsDep):
    """Return the ChainProvider singleton.

    Lazily imported to avoid circular deps and allow the provider
    to be initialised only when the app is actually running.
    """
    from app.chain.provider import ChainProvider

    return ChainProvider.from_settings(settings)


ChainProviderDep = Annotated[object, Depends(get_chain_provider)]
