# AthleteX Agentic Backend Server

FastAPI backend for the AthleteX DeFi/Sports Prediction Platform. This server provides a comprehensive API for trading, historical data, and autonomous agent orchestration.

## Features

- **SIWE Authentication**: Native Sign-In with Ethereum (EIP-4361) using JWT sessions.
- **Historical Price Data**: High-performance time-series data via QuestDB (OHLCV candles and trade history).
- **Real-time WebSocket**: Streaming data for orderbooks, market updates, and exchange status.
- **DeFi Native**: Directly interacts with Synthetix V3, Uniswap V2 forks, and UMA Optimistic Oracle on Polygon.
- **Exchange-Grade API**: Structured errors, multi-tiered token bucket rate limiting, and cursor pagination.

## Infrastructure

The server relies on the following components:
1. **DEX Subgraph**: Pulls on-chain data and swap events (`api.studio.thegraph.com/query/1743457/athletex-dex/v0.0.1`).
2. **QuestDB**: Time-series database for storing and querying price data.
3. **RPC Node**: Direct connection to the Polygon blockchain.

## Quick Start

### 1. Start QuestDB
QuestDB is required for historical price data (candles, trades). It runs locally via Docker Compose.

```bash
docker compose -f docker-compose.questdb.yml up -d
```

### 2. Configure Environment
Copy the example environment variables and configure your keys:

```bash
cp .env.example .env
```

Ensure your `.env` contains:
```env
POLYGON_RPC_URL="https://polygon-rpc.com"
JWT_SECRET="generate-a-secure-32-byte-secret"
ACTIVE_VENUE="athletex"
```

### 3. Start the Server
Set up the Python environment and run the FastAPI server:

```bash
# Create virtual environment
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# Run the server
uvicorn app.main:app --reload
```

## Documentation

- **[API Reference](API.md)**: Comprehensive documentation of all REST endpoints and WebSocket channels.
- **[Production Checklist](production_checklist.md)**: Security and infrastructure gaps to address before deploying to production.

## Architecture Highlights

- **`app/api/v1/`**: Modular routers for spot, predict, vaults, auth, history, portfolio, and orders.
- **`app/api/ws/`**: Production-grade WebSocket server with a background `MarketPoller` fetching real on-chain data.
- **`app/auth/`**: Complete EIP-4361 SIWE implementation.
- **`app/chain/`**: On-chain interaction layer wrapping smart contracts.
- **`app/services/questdb_client.py`**: Dual-protocol client for QuestDB (ILP for fast writes, PGWire for async reads).
- **`app/services/price_ingest.py`**: Background worker that continuously polls the subgraph and writes to QuestDB.

## Contracts (Polygon Mainnet - Chain ID 137)

- CoreProxy: `0x4C2474365eE4d6Ab5c6B5cf3ec860530a9162552`
- axUSD: `0x1Ea27b8fa8D9Fb4370Dd654ffFad4734D0960fA6`
- SpotMarketProxy: `0xc79eC919a0A20E29873143AB9658aF75C0b73A23`
- AX Token: `0x5617604BA0a30E0ff1d2163aB94E50d8b6D0B0Df`
- Multicall3: `0xcA11bde05977b3631167028862bE2a173976CA11`
