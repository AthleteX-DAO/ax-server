# AthleteX API Reference

The AthleteX API is organized into logical domains. It uses standard HTTP response codes, structured JSON error responses, and token-bucket rate limiting.

All API endpoints are prefixed with `/api/v1`.

---

## Rate Limiting
The API implements token-bucket rate limiting. Limits are per-IP.

| Tier | Rate | Authenticated? |
|---|---|---|
| **BASIC** | 100 requests / 10s | Unauthenticated clients |
| **ADVANCED** | 500 requests / 10s | Authenticated via SIWE (JWT) |
| **MARKET_MAKER** | 2000 requests / 10s | Whitelisted accounts |

Response headers include:
- `X-RateLimit-Limit`: Bucket capacity.
- `X-RateLimit-Remaining`: Tokens left.
- `X-RateLimit-Reset`: Milliseconds until the next token is generated.

When limits are exceeded, the API returns a `429 Too Many Requests` status with a `Retry-After` header.

---

## Authentication (SIWE)
Authentication is handled via **Sign-In with Ethereum (EIP-4361)**. Authenticated users receive an upgraded rate limit tier and access to private endpoints (e.g., portfolio).

1. **`GET /auth/nonce`**
   - Returns a single-use cryptographic nonce (`{"nonce": "hex..."}`).
2. **`POST /auth/message`**
   - Body: `{"address": "0x...", "chain_id": 137}`
   - Returns a formatted EIP-4361 message ready for wallet signing.
3. **`POST /auth/verify`**
   - Body: `{"message": "...", "signature": "0x..."}`
   - Verifies the signature and returns `{access_token, refresh_token, wallet, tier}`.
4. **`POST /auth/refresh`**
   - Exchanges a valid refresh token for a new access token.
5. **`GET /auth/me`** *(Protected)*
   - Requires `Authorization: Bearer <access_token>`. Returns current session info.

---

## Historical Data (QuestDB)
Historical data is served from a local QuestDB instance.

1. **`GET /history/candles/{market_id}`**
   - Parameters:
     - `timeframe`: 1m, 5m, 15m, 1h, 4h, 1d (default: 1h)
     - `market_type`: spot, predict, perps
     - `start`, `end`: Unix timestamps or ISO-8601 strings.
     - `limit`: Max candles (default 500)
   - Returns an array of OHLCV candles `[{t, o, h, l, c, v}, ...]`.
2. **`GET /history/trades/{market_id}`**
   - Parameters: `limit` (default 100).
   - Returns the most recent trades for a market.
3. **`GET /history/price/{market_id}`**
   - Returns the absolute latest price snapshot available in the DB.

*(Note: Perps endpoints `/history/perps/candles` and `/history/perps/funding` are currently stubbed).*

---

## Spot Markets (Synthetix V3)
Spot market endpoints provide discovery and quotes.

1. **`GET /spot/markets`**
   - Parameters: `cursor` (integer), `limit` (max 100).
   - Returns a paginated list of available synth markets.
2. **`GET /spot/markets/{market_id}/price`**
   - Returns the current on-chain oracle price.
3. **`GET /spot/markets/{market_id}/quote`**
   - Parameters: `side` (buy|sell), `amount` (in wei).
   - Returns exact amount out and fees for a trade.

---

## Prediction Markets
Prediction market endpoints provide discovery and pricing.

1. **`GET /predict/markets`**
   - Parameters: `category` (optional filter).
   - Returns all active prediction markets.
2. **`GET /predict/markets/{market_id}`**
   - Returns details for a specific market.
3. **`GET /predict/markets/{market_id}/price`**
   - Returns current `yes_price` and `no_price`.

---

## Exchange & Portfolio (Protected)
These endpoints interact with the user's specific on-chain data. They require authentication or a wallet address parameter.

1. **`GET /exchange/status`**
   - Returns overall platform status, active networks, and deployed contract addresses.
2. **`GET /portfolio/balance`** *(Protected via `OptionalAuth`)*
   - Parameters: `wallet` (optional if authenticated).
   - Returns aggregated balance info.
3. **`GET /portfolio/positions`** *(Protected via `OptionalAuth`)*
   - Parameters: `wallet` (optional if authenticated).
   - Returns active trading positions.

---

## Orders (Unsigned Transactions)
The server does **not** custody funds or execute trades directly on behalf of users. Instead, these endpoints build **unsigned transactions** for the client to sign and broadcast.

1. **`POST /orders/buy`**
   - Body: `{"market_id": "...", "amount": "...", "wallet": "0x..."}`
   - Returns an `UnsignedTx` object for buying a spot synth or prediction outcome.
2. **`POST /orders/sell`**
   - Returns an `UnsignedTx` object for selling.
3. **`POST /orders/approve`**
   - Body: `{"token": "0x...", "spender": "0x...", "amount": "..."}`
   - Returns an `UnsignedTx` to approve token spending.

---

## Vaults & Liquidity
Provides data on liquidity provider positions.

1. **`GET /vaults/pools`**
   - Returns available liquidity pools.
2. **`GET /vaults/accounts/{account_id}/collateral`**
   - Returns collateral details for a specific LP account.
3. **`GET /vaults/accounts/{account_id}/debt`**
   - Returns the debt and c-ratio for an LP account.

---

## WebSocket API
A production-grade WebSocket API is available at `ws://<host>/ws/v1` (or the legacy `/ws/events` which redirects).

### Commands
Send a JSON payload to interact with the WebSocket:

```json
{
  "cmd": "subscribe",
  "channels": ["market", "orderbook", "trades"],
  "market_ids": [1, 2]
}
```
Available commands: `subscribe`, `unsubscribe`, `ping`.

### Channels
- **`exchange_status`**: Real-time platform health and global stats.
- **`market`**: Market summary updates (price, 24h volume).
- **`orderbook`**: State of the AMM (vault collateral/debt reserves).
- **`trades`**: Stream of live swaps and executions.

The server uses a background `MarketPoller` to continually push on-chain data to active subscribers.
