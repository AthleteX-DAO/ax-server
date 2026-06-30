"""Production WebSocket server — real-time market data, trades, and exchange events.

Implements a channel-based subscription model inspired by Kalshi/Polymarket:

Channels
--------
- ``exchange_status`` — periodic exchange health heartbeats
- ``market``          — per-market price and metadata updates
- ``orderbook``       — per-market orderbook snapshots (AMM state)
- ``trades``          — public trade feed (from on-chain events)

Protocol
--------
Client sends JSON commands::

    {"cmd": "subscribe",   "channels": ["market", "orderbook"], "market_ids": [1, 2]}
    {"cmd": "unsubscribe", "channels": ["orderbook"]}
    {"cmd": "ping"}

Server sends JSON events::

    {"channel": "market",   "type": "snapshot", "data": {...}}
    {"channel": "exchange_status", "type": "heartbeat", "data": {...}}
    {"channel": "system",   "type": "pong"}
    {"channel": "system",   "type": "error",  "message": "..."}
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware

from app.config import get_settings

logger = logging.getLogger("ax-server.ws")

ws_router = APIRouter()

# ── Channel constants ───────────────────────────────────────────────────

CH_EXCHANGE_STATUS = "exchange_status"
CH_MARKET = "market"
CH_ORDERBOOK = "orderbook"
CH_TRADES = "trades"
CH_SYSTEM = "system"
CH_PORTFOLIO = "portfolio"

ALL_CHANNELS = {CH_EXCHANGE_STATUS, CH_MARKET, CH_ORDERBOOK, CH_TRADES, CH_PORTFOLIO}

# Minimal ABIs for on-chain reads
_SPOT_QUERY_ABI = [
    {
        "type": "function",
        "name": "getName",
        "inputs": [{"name": "marketId", "type": "uint128"}],
        "outputs": [{"type": "string"}],
        "stateMutability": "view",
    },
    {
        "type": "function",
        "name": "getSynth",
        "inputs": [{"name": "marketId", "type": "uint128"}],
        "outputs": [{"type": "address"}],
        "stateMutability": "view",
    },
]

_ERC20_ABI = [
    {
        "type": "function",
        "name": "symbol",
        "inputs": [],
        "outputs": [{"type": "string"}],
        "stateMutability": "view",
    },
    {
        "type": "function",
        "name": "totalSupply",
        "inputs": [],
        "outputs": [{"type": "uint256"}],
        "stateMutability": "view",
    },
]

_CORE_COLLATERAL_ABI = [
    {
        "type": "function",
        "name": "getVaultCollateral",
        "inputs": [
            {"name": "poolId", "type": "uint128"},
            {"name": "collateralType", "type": "address"},
        ],
        "outputs": [
            {"type": "uint256"},
            {"type": "uint256"},
        ],
        "stateMutability": "view",
    },
    {
        "type": "function",
        "name": "getVaultDebt",
        "inputs": [
            {"name": "poolId", "type": "uint128"},
            {"name": "collateralType", "type": "address"},
        ],
        "outputs": [{"type": "int256"}],
        "stateMutability": "view",
    },
]

_ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
_MAX_MARKET_SCAN = 20


# ── Client subscription state ──────────────────────────────────────────


@dataclass
class ClientState:
    """Per-client subscription state."""

    ws: WebSocket
    channels: set[str] = field(default_factory=set)
    market_ids: set[int] = field(default_factory=set)  # empty = all markets
    wallet: str | None = None
    connected_at: float = field(default_factory=time.time)
    last_ping: float = field(default_factory=time.time)


# ── Connection Manager ──────────────────────────────────────────────────


class ChannelManager:
    """Manages WebSocket clients with channel-based subscriptions.

    Supports per-market filtering: clients subscribing to ``market`` or
    ``orderbook`` can optionally specify ``market_ids`` to limit which
    markets they receive data for.
    """

    def __init__(self) -> None:
        self._clients: dict[WebSocket, ClientState] = {}
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> ClientState:
        """Accept and register a new client."""
        await ws.accept()
        state = ClientState(ws=ws)
        async with self._lock:
            self._clients[ws] = state
        logger.info("WS client connected (%d total)", len(self._clients))
        return state

    async def disconnect(self, ws: WebSocket) -> None:
        """Remove a client."""
        async with self._lock:
            self._clients.pop(ws, None)
        logger.info("WS client disconnected (%d remaining)", len(self._clients))

    async def subscribe(self, ws: WebSocket, channels: list[str], market_ids: list[int] | None = None) -> None:
        """Add channel subscriptions for a client."""
        async with self._lock:
            state = self._clients.get(ws)
            if not state:
                return
            valid = set(channels) & ALL_CHANNELS
            state.channels |= valid
            if market_ids:
                state.market_ids |= set(market_ids)
            logger.debug("Client subscribed to %s (markets: %s)", valid, state.market_ids or "all")

    async def unsubscribe(self, ws: WebSocket, channels: list[str]) -> None:
        """Remove channel subscriptions."""
        async with self._lock:
            state = self._clients.get(ws)
            if state:
                state.channels -= set(channels)

    async def broadcast(self, channel: str, data: dict[str, Any], market_id: int | None = None) -> None:
        """Send an event to all clients subscribed to a channel.

        If ``market_id`` is provided, only send to clients that either
        have no market filter or include this market in their filter.
        """
        dead: list[WebSocket] = []
        event = {"channel": channel, **data}

        async with self._lock:
            targets = list(self._clients.items())

        for ws, state in targets:
            if channel not in state.channels:
                continue
            # Market filtering
            if market_id is not None and state.market_ids and market_id not in state.market_ids:
                continue
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.pop(ws, None)

    async def send_to(self, ws: WebSocket, data: dict[str, Any]) -> None:
        """Send a message to a specific client."""
        try:
            await ws.send_json(data)
        except Exception:
            pass

    @property
    def client_count(self) -> int:
        return len(self._clients)

    def get_client_info(self) -> list[dict[str, Any]]:
        """Summary of connected clients (for debugging)."""
        return [
            {
                "channels": list(s.channels),
                "market_ids": list(s.market_ids),
                "connected_at": s.connected_at,
            }
            for s in self._clients.values()
        ]


# Singleton manager
manager = ChannelManager()


# ── Chain data poller ───────────────────────────────────────────────────


class MarketPoller:
    """Background task that reads on-chain state and pushes to subscribers.

    Runs in a loop, polling:
    - Exchange health (block number, latency) every 10s
    - Market data (synth supply, vault state) every 15s
    """

    def __init__(self) -> None:
        self._running = False
        self._task: asyncio.Task | None = None
        self._w3: Web3 | None = None

    def _get_web3(self) -> Web3:
        """Lazy-init web3 provider."""
        if self._w3 is None:
            settings = get_settings()
            self._w3 = Web3(Web3.HTTPProvider(settings.polygon_rpc_url))
            self._w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        return self._w3

    async def start(self) -> None:
        """Start background polling tasks."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info("MarketPoller started (status 10s, orderbook 15s, portfolio 15s)")

    async def stop(self) -> None:
        """Stop background polling tasks."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("MarketPoller stopped")

    async def _run(self) -> None:
        """Main polling loop."""
        cycle = 0
        while self._running:
            try:
                # Exchange status every cycle (10s)
                await self._poll_exchange_status()

                # Market data every 2nd cycle (20s)
                if cycle % 2 == 0:
                    await self._poll_markets()
                    
                # Portfolio data every 1.5 cycles (~15s interval via separate task logic or inline)
                await self._tick_portfolio()

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Poller error")

            cycle += 1
            await asyncio.sleep(10)

    async def _poll_exchange_status(self) -> None:
        """Read block number and broadcast exchange heartbeat."""
        if manager.client_count == 0:
            return

        settings = get_settings()
        w3 = self._get_web3()

        try:
            t0 = time.perf_counter()
            block = w3.eth.block_number
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)

            await manager.broadcast(CH_EXCHANGE_STATUS, {
                "type": "heartbeat",
                "data": {
                    "exchange_active": True,
                    "trading_active": True,
                    "chain_id": settings.default_chain_id,
                    "block_number": block,
                    "rpc_latency_ms": latency_ms,
                    "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "connected_clients": manager.client_count,
                },
            })
        except Exception:
            await manager.broadcast(CH_EXCHANGE_STATUS, {
                "type": "heartbeat",
                "data": {
                    "exchange_active": False,
                    "trading_active": False,
                    "chain_id": settings.default_chain_id,
                    "block_number": None,
                    "rpc_latency_ms": None,
                    "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "connected_clients": manager.client_count,
                },
            })

    async def _poll_markets(self) -> None:
        """Read synth market data and broadcast updates."""
        if manager.client_count == 0:
            return

        settings = get_settings()
        w3 = self._get_web3()

        spot = w3.eth.contract(
            address=w3.to_checksum_address(settings.addresses.spot_market_proxy),
            abi=_SPOT_QUERY_ABI,
        )

        for mid in range(1, _MAX_MARKET_SCAN + 1):
            try:
                synth_addr = spot.functions.getSynth(mid).call()
                if synth_addr == _ZERO_ADDRESS:
                    continue

                market_name = "unknown"
                try:
                    market_name = spot.functions.getName(mid).call()
                except Exception:
                    pass

                symbol = market_name
                total_supply = 0.0
                try:
                    token = w3.eth.contract(
                        address=w3.to_checksum_address(synth_addr),
                        abi=_ERC20_ABI,
                    )
                    symbol = token.functions.symbol().call()
                    raw_supply = token.functions.totalSupply().call()
                    total_supply = raw_supply / 1e18
                except Exception:
                    pass

                await manager.broadcast(
                    CH_MARKET,
                    {
                        "type": "snapshot",
                        "data": {
                            "market_id": mid,
                            "name": market_name,
                            "symbol": symbol,
                            "synth_address": synth_addr,
                            "total_supply": str(total_supply),
                            "status": "active",
                            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        },
                    },
                    market_id=mid,
                )

            except Exception:
                continue

        # Vault/pool state as orderbook proxy
        try:
            core = w3.eth.contract(
                address=w3.to_checksum_address(settings.addresses.core_proxy),
                abi=_CORE_COLLATERAL_ABI,
            )
            ax_addr = w3.to_checksum_address(settings.addresses.ax_token)

            coll = core.functions.getVaultCollateral(1, ax_addr).call()
            debt = core.functions.getVaultDebt(1, ax_addr).call()

            await manager.broadcast(CH_ORDERBOOK, {
                "type": "amm_state",
                "data": {
                    "pool_id": 1,
                    "collateral_type": "AX",
                    "collateral_amount": str(coll[0]),
                    "collateral_value_usd": str(coll[1]),
                    "vault_debt": str(debt),
                    "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                },
            })
        except Exception:
            logger.debug("Failed to read vault state for orderbook channel")

    async def _tick_portfolio(self) -> None:
        """Tick portfolio value for clients subscribed to portfolio."""
        from app.api.v1.portfolio import get_wallet_balance
        from app.deps import get_chain_provider, get_synthetix_client, get_subgraph_client
        
        # Get unique wallets from subscribed clients
        subscribed_clients = []
        async with manager._lock:
            for ws, state in manager._clients.items():
                if CH_PORTFOLIO in state.channels and state.wallet:
                    subscribed_clients.append((ws, state.wallet))
        
        if not subscribed_clients:
            return

        settings = get_settings()
        chain = get_chain_provider(settings)
        snx = get_synthetix_client(chain, settings)
        sg = get_subgraph_client(settings)

        # Fetch and send balance per client
        for ws, wallet in subscribed_clients:
            try:
                balance_resp = await get_wallet_balance(wallet, snx, sg)
                await manager.send_to(ws, {
                    "channel": CH_PORTFOLIO,
                    "type": "portfolio_update",
                    "data": balance_resp.model_dump(),
                })
            except Exception as e:
                logger.warning(f"Failed to fetch portfolio for {wallet}: {e}")


# Singleton poller
poller = MarketPoller()


# ── WebSocket endpoint ──────────────────────────────────────────────────


@ws_router.websocket("/ws/v1")
async def websocket_endpoint(ws: WebSocket):
    """Production WebSocket endpoint with channel subscriptions.

    Connect and send subscription commands to receive real-time data::

        ws://host/ws/v1

    Commands::

        {"cmd": "subscribe", "channels": ["market", "exchange_status"], "market_ids": [1,2]}
        {"cmd": "unsubscribe", "channels": ["market"]}
        {"cmd": "ping"}
        {"cmd": "info"}
    """
    state = await manager.connect(ws)

    # Start poller if this is the first client
    if manager.client_count == 1:
        await poller.start()

    # Send welcome
    await manager.send_to(ws, {
        "channel": CH_SYSTEM,
        "type": "welcome",
        "data": {
            "message": "Connected to AthleteX WebSocket v1",
            "available_channels": sorted(ALL_CHANNELS),
            "protocol": "Subscribe to channels to receive data. Send {cmd: 'ping'} for keepalive.",
        },
    })

    try:
        while True:
            raw = await ws.receive_text()

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await manager.send_to(ws, {
                    "channel": CH_SYSTEM,
                    "type": "error",
                    "message": "Invalid JSON",
                })
                continue

            cmd = msg.get("cmd", "").lower()

            if cmd == "subscribe":
                channels = msg.get("channels", [])
                market_ids = msg.get("market_ids")
                wallet = msg.get("wallet")
                if wallet:
                    state.wallet = wallet
                    
                if not channels:
                    await manager.send_to(ws, {
                        "channel": CH_SYSTEM,
                        "type": "error",
                        "message": "Missing 'channels' array",
                    })
                    continue

                valid = [c for c in channels if c in ALL_CHANNELS]
                invalid = [c for c in channels if c not in ALL_CHANNELS]

                await manager.subscribe(ws, valid, market_ids)
                resp: dict[str, Any] = {
                    "channel": CH_SYSTEM,
                    "type": "subscribed",
                    "data": {
                        "channels": valid,
                        "market_ids": market_ids or "all",
                    },
                }
                if invalid:
                    resp["data"]["invalid_channels"] = invalid
                await manager.send_to(ws, resp)

            elif cmd == "unsubscribe":
                channels = msg.get("channels", [])
                await manager.unsubscribe(ws, channels)
                await manager.send_to(ws, {
                    "channel": CH_SYSTEM,
                    "type": "unsubscribed",
                    "data": {"channels": channels},
                })

            elif cmd == "ping":
                state.last_ping = time.time()
                await manager.send_to(ws, {
                    "channel": CH_SYSTEM,
                    "type": "pong",
                    "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                })

            elif cmd == "info":
                await manager.send_to(ws, {
                    "channel": CH_SYSTEM,
                    "type": "info",
                    "data": {
                        "your_channels": sorted(state.channels),
                        "your_market_ids": sorted(state.market_ids) if state.market_ids else "all",
                        "connected_clients": manager.client_count,
                        "uptime_seconds": round(time.time() - state.connected_at, 1),
                    },
                })

            else:
                await manager.send_to(ws, {
                    "channel": CH_SYSTEM,
                    "type": "error",
                    "message": f"Unknown command: '{cmd}'. Use: subscribe, unsubscribe, ping, info",
                })

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket handler error")
    finally:
        await manager.disconnect(ws)
        # Stop poller if no more clients
        if manager.client_count == 0:
            await poller.stop()


# ── Legacy compat — keep the old /ws/events route working ───────────────


@ws_router.websocket("/ws/events")
async def event_stream_legacy(ws: WebSocket):
    """Legacy event stream — redirects to /ws/v1 protocol."""
    # Use the same handler
    await websocket_endpoint(ws)
