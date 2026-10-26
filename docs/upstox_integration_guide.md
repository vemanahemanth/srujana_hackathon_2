# Upstox Market Data V3 Integration Guide

**Document Version:** 1.0.0  
**Status:** Implemented & Verified (Deterministic Fixtures & Live API Tested)  
**Security Level:** Read-Only Market Data Access (Zero Order/Trade Execution)  

---

## 1. Executive Summary

FragilityShield now features native, production-minded integration with **Upstox Market Data API V3**. This adapter provides institutional-grade market data ingest, candle normalization, physical data-integrity auditing, and catalog registration for quantitative risk models, stress tests, and fragility analyses.

### Non-Negotiable Operating Principles
1. **100% Read-Only:** Strictly market data endpoints. No broker order placement, order modification, or trade execution capabilities are included or exposed.
2. **Zero Secret Leakage:** Access tokens and API secrets are never committed, logged, or surfaced through API responses, exceptions, or reports.
3. **Physical Data Quality Auditing:** Every candle sequence is audited through FragilityShield's `validate_financial_ohlcv` engine before ingestion.
4. **Timezone Fidelity:** All historical candles are normalized to standard ISO-8601 with Asia/Kolkata (`+05:30`) timezone offsets.
5. **Reproducibility & Provenance:** Imported datasets are saved with SHA-256 content fingerprints and registered in the `ProjectCatalog`.

---

## 2. Configuration & Environment Variables

Copy `.env.example` to `.env` in the repository root. `.env` is excluded from git in `.gitignore`.

### Environment Variable Reference

| Variable | Description | Required | Example / Default |
| :--- | :--- | :--- | :--- |
| `UPSTOX_ACCESS_TOKEN` | Daily JWT access token for Upstox API requests | Yes (for live market data) | `eyJ0eXAi...` (placeholder) |
| `UPSTOX_CLIENT_ID` | Upstox Developer App API Key / Client ID | Yes (for OAuth flow) | `your_client_id_here` |
| `UPSTOX_CLIENT_SECRET` | Upstox Developer App API Secret | Yes (for OAuth flow) | `your_client_secret_here` |
| `UPSTOX_REDIRECT_URI` | Registered OAuth redirect URL | Optional | `http://localhost:8000/api/upstox/oauth/callback` |
| `UPSTOX_API_BASE_URL` | Upstox API Gateway Base URL | Optional | `https://api.upstox.com` |

> [!WARNING]
> Upstox access tokens expire daily at **03:30 AM IST**. If token expiry occurs, refresh your access token or re-authenticate via OAuth.

---

## 3. Supported Endpoints & Operations Matrix

| Capability | Upstox Endpoint | HTTP Method | FragilityShield Adapter Method | REST Route |
| :--- | :--- | :--- | :--- | :--- |
| **Connection Check** | `/v3/market-quote/ltp` & `/v2/user/profile` | `GET` | `adapter.check_connection()` | `GET /api/upstox/status` |
| **OAuth Dialog URL** | `/v2/login/authorization/dialog` | `GET` | `adapter.generate_oauth_dialog_url()` | `GET /api/upstox/auth/url` |
| **Token Exchange** | `/v2/login/authorization/token` | `POST` | `adapter.exchange_code_for_token()` | `POST /api/upstox/auth/token` |
| **Instrument Resolution** | Curated Master / Passthrough | In-Memory | `adapter.resolve_instrument()` | `GET /api/upstox/instruments/resolve` |
| **Instrument Search** | Curated Master Index | In-Memory | `adapter.resolver.search()` | `GET /api/upstox/instruments/search` |
| **Historical Candles** | `/v3/historical-candle/{key}/{unit}/{interval}/{to}/{from}` | `GET` | `adapter.get_historical_candles()` | `GET /api/upstox/candles` |
| **Market Quotes** | `/v3/market-quote/quotes` | `GET` | `adapter.get_quote()` | `GET /api/upstox/quote` |
| **Last Traded Price** | `/v3/market-quote/ltp` | `GET` | `adapter.get_ltp()` | `GET /api/upstox/quote?type=ltp` |
| **Dataset Ingest & Catalog** | `/v3/historical-candle` + Catalog | `POST` | `adapter.import_and_register_dataset()` | `POST /api/upstox/datasets/import` |

### Supported Candle Intervals
- **Daily:** `unit="days"`, `interval="1"`
- **Weekly:** `unit="weeks"`, `interval="1"`
- **Monthly:** `unit="months"`, `interval="1"`
- **Intraday:** `unit="minutes"`, `interval="1"`, `"30"`

---

## 4. Instrument Resolution Architecture

Upstox requires exact instrument keys in the format `<SEGMENT>|<IDENTIFIER>` (e.g. `NSE_EQ|INE002A01018` for Reliance Industries, or `NSE_INDEX|Nifty 50` for Nifty 50).

FragilityShield's `UpstoxInstrumentResolver` eliminates guesswork:
1. **Curated High-Speed Index:** Instant resolution for benchmark indices (`NIFTY`, `NIFTY50`, `BANKNIFTY`, `FINNIFTY`, `MIDCPNIFTY`, `NIFTY100`, `NIFTY500`) and bluechips (`RELIANCE`, `TCS`, `INFY`, `HDFCBANK`, `ICICIBANK`, `SBIN`, `ITC`, `LT`, etc.).
2. **Direct Passthrough:** Accepts raw instrument keys (e.g. `NSE_EQ|INE...` or `BSE_EQ|...`) without restriction.
3. **Prefix Normalization:** Automatically strips exchange prefixes (`NSE:RELIANCE` → `RELIANCE`).

---

## 5. Usage Guide

### A. Python SDK
```python
from fragility_engine.sdk import Client

client = Client()

# 1. Check connection status (zero secret leakage)
status = client.upstox.check_connection()
print("Connected:", status.authenticated, status.message)

# 2. Resolve symbol
inst = client.market_data.resolve_upstox_instrument("RELIANCE")
print("Instrument Key:", inst.instrument_key)

# 3. Retrieve historical candles (Asia/Kolkata timezone aware)
candles = client.market_data.get_upstox_candles(
    symbol="RELIANCE",
    from_date="2026-03-01",
    to_date="2026-04-01",
)
print(f"Retrieved {len(candles)} candles. Latest close: {candles[-1].close}")

# 4. Import & Register in Project Catalog
record, report = client.market_data.import_upstox_dataset(
    symbol="RELIANCE",
    catalog=client.catalog,
    from_date="2026-03-01",
    to_date="2026-04-01",
)
print("Registered Dataset:", record.dataset_id, "OHLCV Valid:", report.is_valid)

# 5. Run Fragility Risk Audit on the imported market data
prices = client.upstox.get_historical_prices("RELIANCE")
returns = [float((prices[i] - prices[i-1]) / prices[i-1]) for i in range(1, len(prices))]
audit = client.fragility.run_audit(returns)
print("Fragility Score:", audit.fragility_score)
```

### B. Command-Line Interface (CLI)
```bash
# Check connectivity
fragilityshield upstox status

# Resolve an instrument
fragilityshield upstox resolve RELIANCE

# Fetch live market quote
fragilityshield upstox quote RELIANCE

# Import historical candles into ProjectCatalog
fragilityshield upstox import RELIANCE --from-date 2026-03-01 --to-date 2026-04-01
```

### C. REST API
```bash
# 1. Status
curl -s http://localhost:8000/api/upstox/status

# 2. Resolve
curl -s "http://localhost:8000/api/upstox/instruments/resolve?query=RELIANCE"

# 3. Historical Candles
curl -s "http://localhost:8000/api/upstox/candles?symbol=RELIANCE&from_date=2026-03-01&to_date=2026-04-01"

# 4. Market Quote
curl -s "http://localhost:8000/api/upstox/quote?symbols=RELIANCE,NIFTY50"

# 5. Import Dataset
curl -s -X POST http://localhost:8000/api/upstox/datasets/import \
  -H "Content-Type: application/json" \
  -d '{"symbol": "RELIANCE", "from_date": "2026-03-01", "to_date": "2026-04-01"}'
```

---

## 6. Levels of Verification & Honesty Framework

FragilityShield distinguishes between four distinct levels of verification:

1. **Fixture-Tested Integration (PASS):**
   - Deterministic HTTP mock fixtures verify edge cases: 401 Unauthorized, 429 Rate Limits, 500 Server Errors, 504 Timeouts, corrupted candles ($H < L$, non-positive prices), and JSON parsing.
2. **Live API Connectivity (PASS):**
   - Verified against `https://api.upstox.com/v3/historical-candle` and `/v3/market-quote/ltp` using live credentials. Active requests return HTTP 200 with authenticated market data.
3. **Verified Data Correctness (PASS):**
   - Candlestick OHLC relationships ($L \le O, C \le H$, $L \le H$, $V \ge 0$), timestamp monotonicity, and duplicate prevention audited via `validate_financial_ohlcv`.
4. **Production Deployment Readiness (PARTIAL PASS / CONDITIONAL):**
   - Backend adapter, API routes, SDK bindings, and CLI are fully production-grade.
   - Requires daily token renewal protocol in production (tokens expire at 03:30 AM IST).
   - WebSocket streaming Protobuf feed is documented and reserved for a dedicated real-time milestone.

---

## 7. Troubleshooting Guide

| Issue / Error | Root Cause | Actionable Solution |
| :--- | :--- | :--- |
| `UpstoxConfigurationError: UPSTOX_ACCESS_TOKEN is missing` | `.env` file absent or token unconfigured | Copy `.env.example` to `.env` and set `UPSTOX_ACCESS_TOKEN`. |
| `UpstoxAuthenticationError: Token invalid or expired (401)` | Upstox tokens expire daily at 03:30 AM IST | Generate a fresh token in Upstox Developer Portal or complete OAuth. |
| `UDAPI1221: Static IP configured in account` | Upstox account has static IP binding on user profile | Market data endpoints (`/v3/historical-candle`, `/v3/market-quote`) operate normally. For user profile, add your public IP in Upstox Developer Portal. |
| `UpstoxRateLimitError: Rate limit exceeded (429)` | Too many requests in short period | FragilityShield raises `UpstoxRateLimitError`. Apply backoff retry. |
| `UpstoxInstrumentNotFoundError` | Unknown ticker symbol | Pass exact Upstox key (e.g. `NSE_EQ|INE002A01018`) or check `curated_symbols`. |

---

## 8. Provider Architecture & Capability Registry (Sprint 9)

In Sprint 9, FragilityShield introduces a formal capability contract and registry for market-data providers:

### Supported vs. Explicitly Unsupported Capabilities
| Capability Identifier | Upstox Market Data V3 Status | Behavior When Invoked |
| :--- | :--- | :--- |
| `historical_ohlcv` | **SUPPORTED** | Returns normalized `CanonicalCandle` sequence in IST. |
| `intraday_candles` | **SUPPORTED** | Returns normalized 1m/30m intraday bars. |
| `latest_quotes` | **SUPPORTED** | Returns `CanonicalQuote` with LTP, OHLC, volume, and spread. |
| `instrument_lookup` | **SUPPORTED** | Maps symbols to canonical Upstox instrument keys. |
| `data_provenance` | **SUPPORTED** | Records provider, timestamp, and SHA-256 integrity checksum. |
| `streaming_quotes` | **UNSUPPORTED** | Raises `UnsupportedCapabilityError`. Batch mode only; WebSocket streaming reserved. |
| `corporate_actions` | **UNSUPPORTED** | Raises `UnsupportedCapabilityError`. Use NSE statutory reference catalog. |

### Lifecycle State Machine
`NOT_CONFIGURED` $\to$ `CONFIGURED` $\to$ `VERIFICATION_REQUESTED` $\to$ `VERIFIED` or `FAILED`

- Providers with missing credentials remain `NOT_CONFIGURED`.
- Merely having credentials in `.env` sets state to `CONFIGURED` (never marked `VERIFIED` without an explicit probe).
- When a verification check succeeds with HTTP 200, state transitions to `VERIFIED`.
- If credentials are rejected (HTTP 401/403/timeout), state transitions to `FAILED`.

### Provider Registry REST Endpoints
- `GET /api/providers`: Lists all registered providers, their capability matrices, and current lifecycle states.
- `POST /api/providers/verify`: Executes a genuine connectivity and authorization verification check.
- `GET /api/providers/{provider_id}/capabilities`: Retrieves the detailed capability and unsupported-feature specification.

