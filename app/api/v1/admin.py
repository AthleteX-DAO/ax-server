"""Admin endpoints — prediction market deployment and registry management.

All endpoints require MARKET_MAKER tier authentication.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from eth_account import Account
from fastapi import APIRouter

from app.auth.deps import RequireMarketMaker
from app.chain.prediction_deployer import PredictionDeployer
from app.deps import ChainProviderDep, SettingsDep
from app.middleware.errors import APIError
from app.models.trading import (
    DeployMarketRequest,
    DeployMarketResponse,
    RegisteredMarket,
    RegisterMarketRequest,
)

logger = logging.getLogger("ax-server.api.admin")

router = APIRouter(prefix="/admin", tags=["admin"])

DEPLOY_ERROR = "DEPLOY_ERROR"
AGENT_KEY_MISSING = "AGENT_KEY_MISSING"


def _get_deployer(settings: SettingsDep, chain: ChainProviderDep) -> PredictionDeployer:
    if not settings.agent_private_key:
        raise APIError(
            code=AGENT_KEY_MISSING,
            message="Agent private key not configured. Set AGENT_PRIVATE_KEY in .env.",
            status_code=500,
        )
    account = Account.from_key(settings.agent_private_key)
    return PredictionDeployer(chain.w3, account, settings)


@router.post("/deploy-market", response_model=DeployMarketResponse)
async def deploy_market(
    body: DeployMarketRequest,
    auth: RequireMarketMaker,
    settings: SettingsDep,
    chain: ChainProviderDep,
):
    """Deploy a new prediction market, mint initial tokens, and seed LP pools.

    Requires MARKET_MAKER tier. Currently raises a descriptive error because
    contract bytecode is not yet bundled — use ``/admin/register-market`` for
    already-deployed contracts.
    """
    deployer = _get_deployer(settings, chain)

    try:
        result = await deployer.deploy_market(
            pair_name=body.pair_name,
            question=body.question,
            resolve_by=body.resolve_by,
            category=body.category,
            details=body.details,
        )
    except NotImplementedError as e:
        raise APIError(
            code=DEPLOY_ERROR,
            message=str(e),
            details="Use POST /admin/register-market to register an already-deployed contract.",
            status_code=501,
        )

    market_info = {
        "market_address": result["contract_address"],
        "yes_token": result["long_token_address"],
        "no_token": result["short_token_address"],
        "question": body.question,
        "category": body.category,
        "details": body.details,
        "resolve_by": body.resolve_by,
        "pair_name": body.pair_name,
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }

    # Mint initial tokens
    liquidity_wei = int(body.initial_liquidity_usd * 1e18)
    await deployer.create_initial_tokens(result["contract_address"], liquidity_wei)

    # Seed LP pools (half the liquidity per pool)
    per_pool = liquidity_wei // 2
    lp_result = await deployer.create_lp_pools(
        result["long_token_address"],
        result["short_token_address"],
        per_pool,
    )
    market_info["yes_pair_address"] = lp_result["yes_pair_address"]
    market_info["no_pair_address"] = lp_result["no_pair_address"]

    await deployer.register_market(market_info)

    return DeployMarketResponse(
        status="deployed",
        market=RegisteredMarket(**market_info),
    )


@router.post("/register-market", response_model=DeployMarketResponse)
async def register_existing_market(
    body: RegisterMarketRequest,
    auth: RequireMarketMaker,
    settings: SettingsDep,
    chain: ChainProviderDep,
):
    """Register an already-deployed prediction market contract.

    Use this for markets that are already live on-chain (e.g. Aiyuk).
    """
    deployer = _get_deployer(settings, chain)

    market_info = {
        "market_address": body.contract_address,
        "yes_token": body.yes_token,
        "no_token": body.no_token,
        "question": body.question,
        "category": body.category,
        "details": body.details,
        "resolve_by": body.resolve_by,
        "pair_name": body.pair_name,
        "registered_at": datetime.now(timezone.utc).isoformat(),
    }

    # Try to read LP pair addresses from on-chain
    try:
        axusd = settings.addresses.usd_proxy
        yes_pair = await deployer.dex.get_pair(body.yes_token, axusd)
        no_pair = await deployer.dex.get_pair(body.no_token, axusd)
        market_info["yes_pair_address"] = yes_pair
        market_info["no_pair_address"] = no_pair
    except Exception:
        logger.warning("Could not resolve LP pairs for %s", body.contract_address)
        market_info["yes_pair_address"] = market_info.get("yes_pair_address", "")
        market_info["no_pair_address"] = market_info.get("no_pair_address", "")

    await deployer.register_market(market_info)

    return DeployMarketResponse(
        status="registered",
        market=RegisteredMarket(**market_info),
    )


@router.get("/markets", response_model=list[RegisteredMarket])
async def list_registered_markets(
    settings: SettingsDep,
    chain: ChainProviderDep,
):
    """Return all markets from the deployment registry.

    Optionally enriches each entry with live on-chain data if readable.
    """
    deployer = _get_deployer(settings, chain)
    raw_markets = await deployer.get_registered_markets()

    results: list[RegisteredMarket] = []
    for m in raw_markets:
        entry = RegisteredMarket(**m)
        # Try to fetch on-chain state
        if entry.market_address and entry.yes_token and entry.no_token:
            try:
                on_chain = await deployer.get_market_data(
                    entry.market_address,
                    entry.yes_token,
                    entry.no_token,
                )
                from app.models.trading import MarketOnChainData
                entry.on_chain = MarketOnChainData(**on_chain)
            except Exception:
                logger.debug("Could not read on-chain data for %s", entry.market_address)
        results.append(entry)

    return results
