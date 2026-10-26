# SPRINT 9 — DATA PROVIDERS, SDK, API INTEGRATION & OPEN-SOURCE EXTENSIBILITY QA REPORT

**Date:** 2026-10-25  
**Auditor / Engineer:** Antigravity AI Engineering & Quantitative Audit Team  
**System Scope:** Data Provider Architecture, Upstox V3 Market Data Adapter, Extensible Provider Registry, Python SDK, REST API Endpoints, Model & Plugin Sandboxing, Integration UI Remediation  
**Repository Branch / Commit:** `main` (Sprint 9 Implementation)

---

## 1. Initial Repository Findings

Prior to making code modifications, a comprehensive inspection of the repository was conducted:

| Subsystem | File Inspected | Initial Status & Findings |
| :--- | :--- | :--- |
| **Provider Architecture** | `backend/fragility_engine/market_data.py` | Working `DataProvider` abstract interface, `NSETradingCalendar`, `IndianTradeCharges`, and `NSEOfflineSampleDataProvider`. Lacked an explicit capability discovery contract and unified provider registry. |
| **Upstox Adapter** | `backend/fragility_engine/upstox.py` | Extensive 1,093-line implementation with `UpstoxConfig`, `UpstoxAuthStatus`, `UpstoxInstrumentResolver`, and `UpstoxMarketDataAdapter`. Had token masking and physical OHLCV validation, but lacked explicit capability querying and lifecycle state machine. |
| **Plugin Studio & Prober** | `backend/fragility_engine/plugin_studio.py` | Contained simulated connectivity test logic that returned green "CONNECTED" status when `UPSTOX_ACCESS_TOKEN` was present without actually checking the live endpoint, and fell back to synthetic success. |
| **Plugin Laboratory UI** | `frontend/src/components/pages/PluginLaboratory.tsx` | Contained an artificial fallback in `handleTestPlugin()` catch block lines 117–128 that fabricated mock passes with hardcoded zero-variance determinism. |
| **API Endpoints** | `backend/app.py` | Had Upstox endpoints (`/api/upstox/...`) and plugin studio endpoints (`/api/plugins/...`), but lacked dedicated provider registry endpoints (`/api/providers`). |
| **Python SDK** | `backend/fragility_engine/sdk.py` | Rich `Client` implementation with `market_data` and `upstox` sub-clients, but lacked unified provider registry querying and capability verification. |
| **Plugin Sandbox** | `backend/fragility_engine/plugin_sandbox.py` | Robust fail-closed security boundary enforcing resource limits (Memory $\le 256$ MB, Timeout $\le 5$s) and disallowing unauthorized capabilities. |

---

## 2. Architecture Reused and Files Changed

To maintain stability and avoid creating duplicate subsystems, existing classes and interfaces were strictly reused and enhanced:

### Files Modified
1. `backend/fragility_engine/market_data.py`:
   - Reused `DataProvider`, `NSEOfflineSampleDataProvider`, and `NSETradingCalendar`.
   - Added `ProviderCapability`, `UnsupportedCapabilityError`, `ProviderLifecycleStatus`, `DataProviderRecord`, and `DataProviderRegistry`.
   - Added global singleton `get_default_provider_registry()`.
2. `backend/fragility_engine/upstox.py`:
   - Enhanced `UpstoxMarketDataAdapter` to inherit the new capability contract.
   - Added explicit supported capabilities (`historical_ohlcv`, `intraday_candles`, `latest_quotes`, `instrument_lookup`, `data_provenance`).
   - Added explicit unsupported capability methods (`stream_quotes`, `get_corporate_actions`) raising `UnsupportedCapabilityError`.
   - Implemented dynamic `lifecycle_status` property and state updates during `check_connection()`.
3. `backend/fragility_engine/plugin_studio.py`:
   - Replaced simulated Upstox connectivity and health checks with real delegated calls to `UpstoxMarketDataAdapter.check_connection()` and the `DataProviderRegistry`.
4. `backend/app.py`:
   - Added REST routes:
     - `GET /api/providers`: List registered providers with capability matrices and lifecycle status.
     - `POST /api/providers/verify`: Trigger genuine provider connectivity verification.
     - `GET /api/providers/{provider_id}/capabilities`: Retrieve explicit capability details.
   - Enhanced `api_check_model_capabilities` to resolve built-in models (`builtin.parametric_gaussian`, `builtin.historical_simulation`, `builtin.ewma`, etc.) without requiring external disk files.
5. `backend/fragility_engine/sdk.py`:
   - Enhanced `Client.market_data` with `provider_registry()`, `list_providers()`, `get_provider()`, and `verify_provider()`.
6. `backend/fragility_engine/__init__.py`:
   - Exported all new provider and capability symbols.
7. `frontend/src/components/pages/PluginLaboratory.tsx`:
   - Eliminated the fake catch-block mock report. Replaced with genuine error state handling, red-badged failure indicators, and transparent error messaging.
8. `docs/upstox_integration_guide.md`:
   - Added Section 8 detailing the Provider Capability contract, lifecycle state machine, and REST endpoints.

### New Test Suite
- `backend/tests/test_sprint9_extensibility.py`: 19 comprehensive unit and integration tests covering providers, Upstox mock scenarios, registry, SDK, plugin sandbox, and regression continuity.

---

## 3. Provider Capabilities Verified Against Official Documentation

Upstox API V3 official market data documentation was audited against implemented capabilities:

| Capability | Upstox Official API V3 Endpoint | FragilityShield Status | Audit Notes |
| :--- | :--- | :--- | :--- |
| **Historical OHLCV** | `GET /v3/historical-candle/{instrument_key}/{interval_unit}/{interval}/{to_date}/{from_date}` | **Verified through automated tests** | Verified with daily, weekly, and monthly intervals. Handles date partitioning across years. |
| **Intraday Candles** | `GET /v3/historical-candle/{instrument_key}/minutes/{interval}/{to_date}/{from_date}` | **Verified through automated tests** | Verified with 1-minute and 30-minute bar intervals. |
| **Market Quotes / LTP** | `GET /v3/market-quote/ltp`, `GET /v3/market-quote/quotes` | **Verified through automated tests** | Single and multi-instrument quote querying. Batch requests comma-separated. |
| **Instrument Lookup** | Curated Master Index + Upstox Key Format (`NSE_EQ\|INE...`) | **Verified through automated tests** | Resolver maps human tickers (`RELIANCE`, `TCS`, `NIFTY 50`) to canonical keys. |
| **Data Provenance** | Custom metadata contract | **Verified through automated tests** | Ingested datasets record `source: upstox_v3`, retrieved timestamp, and SHA-256 fingerprint. |
| **Streaming Quotes (WebSocket)** | Upstox WebSocket Feed via Protobuf | **Not implemented (Explicitly unsupported)** | Batch mode only. Adapter raises `UnsupportedCapabilityError`. |
| **Corporate Actions (Dividends/Splits)** | Upstox V3 Market Data does not expose adjustments | **Not implemented (Explicitly unsupported)** | Adapter raises `UnsupportedCapabilityError`. Users directed to statutory NSE calendar. |

---

## 4. Upstox Operations Implemented and Verification Status

| Operation | Implementation Method | Status | Evidence / Test |
| :--- | :--- | :--- | :--- |
| **Connection Check** | `UpstoxMarketDataAdapter.check_connection()` | **Verified through automated tests** | Tested against mock 200, 401, 429, and 504 responses in `test_sprint9_extensibility.py`. |
| **Secret Masking** | `UpstoxConfig.mask_token()`, `safe_dict()` | **Verified through automated tests** | Verified that raw tokens and client secrets are never exposed in dicts, strings, or reprs. |
| **Historical Candles** | `UpstoxMarketDataAdapter.get_historical_candles()` | **Verified through automated tests** | Tested normalization, reverse-chronological reversal, and IST offset preservation. |
| **Market Quotes** | `UpstoxMarketDataAdapter.get_quote()` | **Verified through automated tests** | Returns typed `CanonicalQuote` objects with valid LTP and spreads. |
| **Dataset Ingest & Registration** | `UpstoxMarketDataAdapter.import_and_register_dataset()` | **Verified through automated tests** | Audits OHLCV physical bounds ($H \ge L, H \ge O, C \ge L$), saves JSON, and registers in catalog. |
| **Live Upstox API Connectivity** | Network request with production credentials | **Implemented but not live-verified** | Live credentials (`UPSTOX_ACCESS_TOKEN`) not configured in this development environment. Adapter reports `NOT_CONFIGURED` truthfully. |

---

## 5. Credential and Security Handling

FragilityShield strictly enforces credential boundary protection:
1. **Source of Truth:** Credentials originate solely from OS environment variables (`UPSTOX_ACCESS_TOKEN`, `UPSTOX_CLIENT_ID`, `UPSTOX_CLIENT_SECRET`) or local `.env` (git-ignored).
2. **Zero Plaintext Token Transmission:** API endpoints (`/api/upstox/status`, `/api/providers`) return only masked tokens (e.g. `eyJh...data`) or boolean flags (`has_access_token: true`).
3. **Log & Exception Redaction:** `UpstoxConfig.__repr__` masks tokens. String representations omit `client_secret` entirely.
4. **Least Privilege & Read-Only:** All Upstox interactions target read-only market data endpoints. The adapter contains zero order placement, modification, or cancellation code.

---

## 6. Data Normalization and Provenance Behavior

The normalization pipeline guarantees physical data integrity without fabricating synthetic candles:
- **Timestamp Formatting:** Timestamps are normalized to ISO-8601 with Asia/Kolkata timezone (`+05:30`).
- **Ordering:** Upstox returns newest candles first; the normalizer sorts chronological order (oldest first).
- **Physical Bounds Validation:** Every candle is validated via `validate_financial_ohlcv()`:
  - $High \ge Low$
  - $High \ge Open$ and $High \ge Close$
  - $Low \le Open$ and $Low \le Close$
  - $Volume \ge 0$
  - Positive non-zero prices.
- **Zero Forward-Filling:** Gaps or missing observations are preserved as gaps rather than silently forward-filled or interpolated without audit record.
- **Provenance Registration:** Every ingested dataset stores source provider, query parameters, retrieval timestamp, and SHA-256 hash in its `DatasetRecord`.

---

## 7. SDK and API Changes

### REST API Endpoints Added
- `GET /api/providers`: Returns list of all registered market data providers, supported capabilities, unsupported capabilities, and lifecycle states.
- `POST /api/providers/verify`: Accepts `{"provider_id": "...", "timeout": 10.0}` and executes a live or offline verification check.
- `GET /api/providers/{provider_id}/capabilities`: Returns the capability specification for a specific provider.

### Python SDK Enhancements (`fragility_engine.sdk.Client`)
- `client.market_data.provider_registry()`: Access the `DataProviderRegistry`.
- `client.market_data.list_providers()`: List all provider records.
- `client.market_data.get_provider(provider_id)`: Retrieve provider instance.
- `client.market_data.verify_provider(provider_id)`: Trigger verification check.

---

## 8. Model and Plugin Registration Changes

1. **Common Model Contract Validation:**
   - Manifests require alphanumeric IDs, valid semver versions, valid entry points, and bounded resource limits (Memory $\le 512$ MB, Timeout $\le 30$s, CPU $\le 2.0$).
2. **Fail-Closed Security Boundary:**
   - Permitted capabilities are strictly restricted to `ALLOWED_PLUGIN_CAPABILITIES` (`dataset:read`, `workspace:write`, `result:return`). Requests for unauthorized capabilities (e.g. `network:egress`) are rejected with `PluginValidationError`.
   - Untrusted third-party code is prohibited from executing in-process on the host. In the absence of an isolated gVisor/container runtime, execution fails closed with `SandboxUnavailableError`.
3. **Truthful Built-In Model Capability Evaluation:**
   - `api_check_model_capabilities` resolves built-in models (`builtin.parametric_gaussian`, `builtin.historical_simulation`, etc.) and evaluates their real capability matrices dynamically.

---

## 9. UI Actions Tested

### Plugin Laboratory (`frontend/src/components/pages/PluginLaboratory.tsx`)
- **Action:** Clicking "Validate Contract" on any registered plugin.
- **Result:** Executes `POST /api/models/check-capabilities`. Real report is rendered showing verified capabilities, numerical stability, and security boundary.
- **Error Handling:** If backend fails or model is invalid, the modal displays an explicit red-badged `FAILED` status and displays the exact backend error message. The artificial zero-variance mock fallback has been completely removed.

### Integration & Plugin Studio (`frontend/src/components/pages/IntegrationPluginStudio.tsx`)
- **Action:** Clicking "Test Provider" or "Test Connectivity".
- **Result:** Probes `UpstoxMarketDataAdapter.check_connection()` and displays honest status:
  - If unconfigured: Reports `NOT_CONFIGURED` with guidance to supply `UPSTOX_ACCESS_TOKEN`.
  - Offline fallback provider remains operational and labeled as `LOCAL VERIFIED CATALOG`.

---

## 10. Automated Tests and Exact Outcomes

### Dedicated Sprint 9 Test Suite (`backend/tests/test_sprint9_extensibility.py`)
```
======================== 19 passed, 1 warning in 0.84s =========================
```
1. `test_provider_capability_declaration_and_enforcement`: **PASSED**
2. `test_provider_lifecycle_state_machine`: **PASSED**
3. `test_upstox_unconfigured_status_and_honest_reporting`: **PASSED**
4. `test_upstox_secret_masking_and_no_token_leakage`: **PASSED**
5. `test_upstox_mock_connection_verification_success`: **PASSED**
6. `test_upstox_mock_authentication_failure_401`: **PASSED**
7. `test_upstox_mock_rate_limit_429`: **PASSED**
8. `test_upstox_mock_timeout_handling`: **PASSED**
9. `test_ohlcv_normalization_and_provenance`: **PASSED**
10. `test_data_provider_registry_lifecycle_and_isolation`: **PASSED**
11. `test_api_list_data_providers`: **PASSED**
12. `test_api_verify_data_provider`: **PASSED**
13. `test_api_get_provider_capabilities`: **PASSED**
14. `test_api_check_model_capabilities_builtin`: **PASSED**
15. `test_sdk_market_data_and_provider_registry`: **PASSED**
16. `test_manifest_validation_valid`: **PASSED**
17. `test_manifest_validation_unauthorized_capability`: **PASSED**
18. `test_manifest_validation_invalid_id`: **PASSED**
19. `test_regression_offline_risk_calculation_without_external_provider`: **PASSED**

### Full Repository Regression Test Suite
```
PYTHONPATH=backend:. python3 -m pytest backend/tests/ -q
856 passed, 1 warning in 12.16s
```
**Total Passing Tests:** **856 passed** (Zero failures, Zero regressions).

---

## 11. Lint, Type-Check, and Production-Build Outcomes

### TypeScript Static Typecheck
```bash
npm run typecheck
> fragilityshield-frontend@1.0.0 typecheck
> tsc --noEmit
# Exit code: 0 (Zero type errors)
```

### Frontend Production Build
```bash
npm run build
> fragilityshield-frontend@1.0.0 build
> vite build
✓ 2325 modules transformed.
dist/index.html                  1.40 kB │ gzip:   0.55 kB
dist/assets/index-Dqt1CnKI.css 204.10 kB │ gzip:  33.54 kB
dist/assets/index-CCOs91SB.js 1,648.92 kB │ gzip: 408.01 kB
✓ built in 2.38s
# Exit code: 0 (Clean production build)
```

---

## 12. Known Limitations and Unresolved Blockers

1. **Daily Token Expiration (Upstox Policy):** Upstox V3 JWT access tokens expire daily at 03:30 AM IST. Production environments require a recurring daily OAuth token refresh routine or developer portal renewal.
2. **Streaming WebSocket Market Data:** WebSocket streaming via Protobuf is deliberately declared unsupported in this release (`UnsupportedCapabilityError`), as FragilityShield is engineered for quantitative risk, scenario analysis, and model validation rather than active high-frequency order routing.
3. **OS-Level Container Sandboxing:** In local development environments without Docker/Podman or gVisor installed, execution of arbitrary untrusted third-party code fails closed by design. Untrusted plugins cannot execute on the un-isolated host.

---

## 13. Live Provider Verification Status

| Provider / Integration | Declared Lifecycle Status | Exact Verification Status |
| :--- | :--- | :--- |
| **NSE Offline Sample Provider** | `VERIFIED` | **Verified through automated tests** |
| **Upstox V3 Market Data Adapter (Mock)** | `VERIFIED` | **Verified through automated tests** |
| **Upstox V3 Market Data Feed (Live Gateway)** | `NOT_CONFIGURED` / `CONFIGURED` | **Implemented but not live-verified** (Requires active live `UPSTOX_ACCESS_TOKEN` in `.env`) |
| **PostgreSQL Timeseries Engine** | `CONNECTED` / `STANDBY` | **Verified through automated tests** (Runs with in-memory ledger fallback when `DATABASE_URL` is omitted) |

> [!NOTE]
> Tests against mocks are strictly recorded as verified through automated tests; they are never conflated with live provider verification. When credentials are not provided, FragilityShield truthfully reports `NOT_CONFIGURED`.

---

## 14. Final Evidence-Based Sprint Assessment

Sprint 9 has successfully established an institutional extensibility layer for FragilityShield:
- **Capability-Driven Provider Architecture:** Replaced ad-hoc provider checks with a formal capability specification. Unsupported capabilities raise explicit errors and never fabricate data.
- **Upstox V3 Production Hardening:** All endpoints, token masking, rate limits, timeouts, and OHLCV physical data-integrity checks are implemented, safe, and covered by automated tests.
- **Truthful UI State:** Removed synthetic green indicators and artificial mock validation reports. Status transitions honestly reflect real backend checks.
- **Full Test & Build Verification:** 856 backend tests passed, frontend TypeScript checks cleanly with zero errors, and the production bundle builds in 2.38 seconds.

**Sprint Status:** **COMPLETED & VERIFIED**
