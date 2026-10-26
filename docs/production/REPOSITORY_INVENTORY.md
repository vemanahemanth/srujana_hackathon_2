# FragilityShield — Repository Inventory (Phase 0)

**Date:** 2026-10-25  
**Repository:** `FragilityShield` (`/Users/vemanahemanthbabu/srujana_hackathon_2`)  
**Scope:** Exhaustive inventory of all REST endpoints, engine modules, SDK methods, CLI commands, data feeds, and persistence catalogs.

---

## 1. REST API Endpoints Inventory

All routes defined in [`backend/app.py:create_application()`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/app.py#L1550):

| Method | Endpoint Route | Handler Function | Capability / Lab ID | Data Provenance Assigned |
|---|---|---|---|---|
| `GET` | `/api/health` | `api_health` | Platform Health | System Status |
| `GET` | `/api/portfolios/sample` | `api_load_sample_portfolio` | `LAB-01` | `SYNTHETIC_TEST_DATA` |
| `POST` | `/api/portfolios/validate` | `api_validate_portfolio` | `LAB-01` | `USER_UPLOADED_DATA` |
| `POST` | `/api/risk/calculate` | `api_calculate_risk` | `LAB-02` | `REAL_DATA` / `USER_UPLOADED` / `SYNTHETIC` |
| `POST` | `/api/risk/attribution` | `api_calculate_risk_attribution` | `LAB-03` | `REAL_DATA` / `USER_UPLOADED` / `SYNTHETIC` |
| `POST` | `/api/scenarios/run` | `api_run_scenario` | `LAB-04` | `USER_UPLOADED_DATA` |
| `POST` | `/api/scenarios/reverse-stress` | `api_reverse_stress_test` | `LAB-05` | `USER_UPLOADED_DATA` |
| `POST` | `/api/fragility/search-boundary` | `api_search_stress_boundary` | `LAB-05` | `USER_UPLOADED_DATA` |
| `POST` | `/api/fragility/run` | `api_run_fragility` | `LAB-06` | `REAL_DATA` / `USER_UPLOADED` |
| `POST` | `/api/validation/run` | `api_run_validation` | `LAB-07` | `USER_UPLOADED_DATA` |
| `POST` | `/api/backtest/run` | `api_run_backtest` | `LAB-08` | `REAL_DATA` / `USER_UPLOADED` |
| `POST` | `/api/benchmarks/tournament` | `api_run_model_tournament` | `LAB-09` | `REAL_DATA` / `USER_UPLOADED` |
| `POST` | `/api/data/validate-ohlcv` | `api_validate_ohlcv` | `LAB-10` | `REAL_DATA` / `USER_UPLOADED` |
| `POST` | `/api/data/validate-tabular` | `api_validate_tabular` | `LAB-10` | `USER_UPLOADED_DATA` |
| `POST` | `/api/data/audit-outliers` | `api_audit_outliers` | `LAB-10` | `USER_UPLOADED_DATA` |
| `POST` | `/api/data/detect-drift` | `api_detect_drift` | `LAB-10` | `USER_UPLOADED_DATA` |
| `POST` | `/api/simulation/monte-carlo` | `api_run_monte_carlo` | `LAB-11` | `MIXED_DATA` (`SIMULATED`) |
| `POST` | `/api/simulation/bootstrap` | `api_run_bootstrap` | `LAB-12` | `MIXED_DATA` (`SIMULATED`) |
| `GET` | `/api/assumptions` | `api_list_assumptions` | `LAB-13` | System Rules |
| `POST` | `/api/assumptions/audit` | `api_audit_assumptions` | `LAB-13` | `USER_UPLOADED_DATA` |
| `GET` | `/api/upstox/status` | `api_upstox_status` | `LAB-14` | Gateway Status |
| `GET` | `/api/upstox/instruments/resolve` | `api_upstox_resolve_instrument` | `LAB-14` | `REAL_DATA` |
| `GET` | `/api/upstox/instruments/search` | `api_upstox_search_instruments` | `LAB-14` | `REAL_DATA` |
| `GET` | `/api/upstox/candles` | `api_upstox_historical_candles` | `LAB-14` | `REAL_DATA` |
| `GET` | `/api/upstox/quote` | `api_upstox_quotes` | `LAB-14` | `REAL_DATA` |
| `GET` | `/api/upstox/auth/url` | `api_upstox_auth_url` | `LAB-14` | OAuth Flow |
| `POST` | `/api/upstox/auth/exchange` | `api_upstox_exchange_token` | `LAB-14` | OAuth Exchange |
| `POST` | `/api/allocation/optimize` | `api_optimize_allocation` | `LAB-15` | `USER_UPLOADED_DATA` |
| `POST` | `/api/allocation/compare` | `api_compare_allocations` | `LAB-15` | `USER_UPLOADED_DATA` |
| `POST` | `/api/ml/evaluate` | `api_evaluate_ml` | `LAB-16` | `USER_UPLOADED_DATA` |
| `POST` | `/api/ml/split` | `api_split_chronological` | `LAB-16` | `USER_UPLOADED_DATA` |
| `GET` | `/api/plugins` | `api_list_plugins` | `LAB-17` | Plugin Registry |
| `POST` | `/api/plugins/register` | `api_register_plugin` | `LAB-17` | `USER_UPLOADED_DATA` |
| `POST` | `/api/plugins/execute` | `api_execute_plugin` | `LAB-17` | `USER_UPLOADED_DATA` |
| `GET` | `/api/projects` | `api_list_projects` | `LAB-18` | Catalog Index |
| `POST` | `/api/projects` | `api_create_project` | `LAB-18` | Catalog Metadata |
| `GET` | `/api/datasets` | `api_list_datasets` | `LAB-18` | Catalog Index |
| `POST` | `/api/datasets` | `api_register_dataset` | `LAB-18` | Catalog Dataset |
| `POST` | `/api/datasets/import-upstox` | `api_import_upstox_dataset` | `LAB-18` | `REAL_DATA` |
| `POST` | `/api/experiments/runs` | `api_record_experiment_run` | `LAB-18` | `USER_UPLOADED_DATA` |
| `POST` | `/api/models/manifests` | `api_register_model_manifest` | `LAB-18` | Model Registry |
| `POST` | `/api/models/check-capabilities` | `api_check_model_capabilities` | `LAB-18` | Model Registry |

---

## 2. Python SDK Inventory (`backend/fragility_engine/sdk.py`)

Primary class: `FragilityShieldSDK(base_url="http://localhost:8000")`
- `validate_portfolio(portfolio_data: Dict) -> Dict`
- `calculate_risk(returns: Sequence[float], confidence_level: float = 0.95, symbol: Optional[str] = None) -> Dict`
- `attribute_risk(portfolio: Dict, asset_returns: Optional[List[List[float]]] = None, use_upstox: bool = False) -> Dict`
- `run_scenario(portfolio: Dict, preset_id: Optional[str] = None, sector_shocks: Optional[Dict] = None) -> Dict`
- `run_fragility_analysis(returns: Sequence[float], lookback_short: int = 20, lookback_long: int = 60) -> Dict`
- `run_backtest(returns: Sequence[float], window_size: int = 40, confidence_level: float = 0.95) -> Dict`
- `run_monte_carlo(returns: Sequence[float], num_paths: int = 250, horizon_days: int = 30) -> Dict`
- `run_bootstrap_uncertainty(returns: Sequence[float], num_bootstraps: int = 300) -> Dict`
- `optimize_allocation(covariance_matrix: List[List[float]], asset_ids: List[str]) -> Dict`
- `evaluate_ml(task_type: str, y_true: List[float], y_pred: List[float], y_prob: Optional[List[float]] = None) -> Dict`
- `get_upstox_candles(symbol: str, from_date: str, to_date: str) -> Dict`
- `create_project(project_id: str, name: str, objective: str) -> Dict`

---

## 3. CLI Command Inventory (`backend/fragility_engine/cli.py`)

Commands invoked via `python -m fragility_engine.cli <command> <subcommand>`:
- `portfolio validate --portfolio <path>`
- `risk calculate --returns <path> --symbol <ticker>`
- `risk attribute --portfolio <path> --returns <path>`
- `scenario run --portfolio <path> --preset <preset_id>`
- `scenario reverse-stress --portfolio <path> --target-loss <float>`
- `fragility run --returns <path>`
- `backtest run --returns <path> --window <int>`
- `upstox candles --symbol <ticker> --from-date <date> --to-date <date>`
- `project create --id <id> --name <name> --objective <text>`
- `project list`
- `dataset list`

---

## 4. Local Catalog & Persistence Storage

Directory structure:
- `data/catalog/`: Dataset registration metadata and JSON schema indices.
- `data/experiments/projects/`: Project metadata records (UUID keys).
- `data/experiments/datasets/`: Ingested market-data series and uploaded CSVs.
- `data/experiments/models/`: Model manifests and execution specifications.
- `data/sample_portfolios/`: Deterministic testing portfolios (`nse_10l.json`).
