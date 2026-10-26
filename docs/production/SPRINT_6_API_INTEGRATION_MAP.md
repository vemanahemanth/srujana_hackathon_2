# FragilityShield — Sprint 6 API Integration Map

## 1. Authentication & Security Policy

All API endpoints enforcing multi-tenancy require a valid JWT Bearer token:
- **Header:** `Authorization: Bearer <JWT>`
- **Token Claims:** `tenant_id`, `sub` (user_id), `role`, `exp`
- **Roles:** `VIEWER`, `RESEARCHER`, `RISK_MANAGER`, `ADMIN`
- **Fallback / Local Mode:** When running in `local_research` mode without a JWT header, endpoints fall back to the default local tenant context (`ten_alpha_capital` with role `ADMIN`).

---

## 2. API Endpoint Matrix & Frontend Component Mapping

| Category | HTTP Method & Path | Auth Required | Request / Response Schema | Connected Frontend View |
| :--- | :--- | :---: | :--- | :--- |
| **System** | `GET /api/health` | No | `{ status: "ok", timestamp: ... }` | Statusbar & Offline Indicator |
| **Security** | `GET /api/security/status` | Yes | `{ deployment_mode, rls_active, database_mode, container_sandbox }` | Settings & Statusbar |
| **Auth** | `POST /api/auth/token` | No | `{ tenant_id, user_id, role }` -> `{ access_token, token_type }` | Topbar Auth & Settings |
| **Portfolio** | `GET /api/portfolios/sample` | Yes | `?name=nse_10l.json` -> `Portfolio` | Portfolio Workbench & Overview |
| **Portfolio** | `GET /api/portfolios` | Yes | `-> Portfolio[]` | Saved Portfolios (`/saved-portfolios`) |
| **Portfolio** | `POST /api/portfolios` | Yes | `Portfolio` -> `{ success, portfolio_id }` | Portfolio Workbench Save |
| **Portfolio** | `POST /api/portfolios/validate` | Yes | `Portfolio` -> `{ is_valid, holdings_count, total_value }` | Portfolio Workbench Validator |
| **Portfolio** | `POST /api/portfolios/concentration` | Yes | `Portfolio` -> `{ hhi, top_holdings, sector_weights }` | Portfolio Workbench & Risk Lab |
| **Risk** | `POST /api/risk/calculate` | Yes | `{ portfolio, confidence_level, lookback_window }` -> `RiskReport` | Risk Analytics Lab (`/labs/risk`) |
| **Attribution** | `POST /api/risk/attribution` | Yes | `{ portfolio, benchmark }` -> `RiskAttributionReport` | Attribution Lab (`/labs/attribution`) |
| **Scenarios** | `POST /api/scenarios/execute` | Yes | `{ portfolio, scenario }` -> `ScenarioResult` | Scenario Analysis (`/labs/scenarios`) |
| **Reverse Stress** | `POST /api/scenarios/reverse-stress` | Yes | `{ portfolio, loss_threshold }` -> `ReverseStressResult` | Reverse Stress Lab (`/labs/reverse-stress`) |
| **Fragility** | `POST /api/fragility/run` | Yes | `{ portfolio, attack_type, step_size }` -> `FragilityResult` | Fragility Studio (`/labs/fragility`) |
| **Monte Carlo** | `POST /api/simulation/monte-carlo` | Yes | `{ portfolio, simulations, horizon }` -> `SimulationResult` | Monte Carlo Lab (`/labs/monte-carlo`) |
| **Bootstrap** | `POST /api/simulation/bootstrap` | Yes | `{ returns, replications }` -> `UncertaintyIntervals` | Uncertainty Lab (`/labs/uncertainty`) |
| **Allocation** | `POST /api/allocation/optimize` | Yes | `{ portfolio, objective, constraints }` -> `AllocationResult` | Allocation Lab (`/labs/allocation`) |
| **Models** | `POST /api/models/execute` | Yes | `{ model_id, category, async }` -> `202 Accepted` / Result | Model Runner & Lab |
| **Jobs** | `GET /api/models/jobs/{id}` | Yes | `-> JobRecord { status, result, worker_id }` | Notifications & Execution History |
| **Jobs** | `POST /api/models/jobs/{id}/cancel`| Yes | `-> { success, status }` | Notifications & Job Actions |
| **Workers** | `GET /api/workers/status` | Yes | `-> { worker: { worker_id, queue_depth, storage } }` | Integrations & Diagnostics |
| **Artifacts** | `GET /api/artifacts` | Yes | `?job_id=...` -> `ArtifactMetadata[]` | Reproducibility & Provenance |
| **Artifacts** | `GET /api/artifacts/{id}/download`| Yes | `-> Binary StreamingResponse` | Artifact Download buttons |
| **Market** | `GET /api/upstox/status` | No | `{ configured, authenticated }` | Market Terminal & Topbar Pill |
| **Market** | `GET /api/upstox/instruments/search`| Yes | `?q=...` -> `Instrument[]` | Market Terminal Search |
| **Market** | `GET /api/upstox/candles` | Yes | `?instrument_key=...&interval=day` -> `Candle[]` | Market Terminal Charts |

---

## 3. Disclosed Limitations & Unavailable Backend Capabilities

1. **Third-Party Upstox Credentials:** When `UPSTOX_ACCESS_TOKEN` is unconfigured, market data endpoints report `configured: false`. The frontend must display an honest "Provider unconfigured" badge and fall back to local portfolio datasets.
2. **Untrusted Custom Model Sandbox:** When running without rootless Docker/gVisor isolation, third-party model execution fails closed with HTTP 503 (`SandboxSecurityError`). The frontend must display a prominent security notice: "Untrusted container sandbox unavailable. Trusted local research mode active."
3. **Real-time WebSockets:** WebSocket streaming for ticks is not yet implemented in backend; polling is used for asynchronous jobs.
