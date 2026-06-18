# AthleteX Agentic Backend Server

FastAPI backend for the AthleteX DeFi/Sports Prediction Platform.

## Quick Start

```bash
cd ax-server
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload
```

## Endpoints

| Method | Path | Description |`
|--------|------|-------------|
| GET | `/api/v1/health` | Health check + chain status |
| GET | `/api/v1/markets` | List available markets |
| GET | `/api/v1/markets/{market_id}` | Get market details |
| GET | `/api/v1/positions/{address}` | Get positions for address |
| POST | `/api/v1/agent/action` | Trigger agent action |
| GET | `/api/v1/agent/status` | Get agent status |
| WS | `/ws/events` | Real-time event stream |

## Architecture

- **agents/** - Autonomous agent framework (base, market, execution, listener)
- **chain/** - On-chain interaction layer (Synthetix V3, Uniswap V2, UMA)
- **models/** - Pydantic data models
- **services/** - Business logic (pricing, portfolio)

## Contracts (Polygon Mainnet - Chain ID 137)

- CoreProxy: `0x4C2474365eE4d6Ab5c6B5cf3ec860530a9162552`
- axUSD: `0x1Ea27b8fa8D9Fb4370Dd654ffFad4734D0960fA6`
- SpotMarketProxy: `0xc79eC919a0A20E29873143AB9658aF75C0b73A23`
- AX Token: `0x5617604BA0a30E0ff1d2163aB94E50d8b6D0B0Df`
- Multicall3: `0xcA11bde05977b3631167028862bE2a173976CA11`
