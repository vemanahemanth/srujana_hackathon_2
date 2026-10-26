# FragilityShield — Capability Traceability Matrix (Phase 2)

**Audit Date:** 2026-10-25  
**Auditing Authority:** Independent Quality Assurance & Verification Team  
**Standard:** Complete Traceability from Capability ID to Code, REST Route, Test Suite, and Status

---

| Unique ID | Capability Name | Engine Implementation | REST Endpoint Route | Primary Test Suites | Verified Test Count | Current Status |
|---|---|---|---|---|---|---|
| `LAB-01` | Portfolio Ingestion & Concentration | `models.py`, `concentration.py` | `POST /api/portfolios/validate` | `test_portfolio_lab.py`, `test_validation_edge_cases.py` | 60 | **READY — VERIFIED** |
| `LAB-02` | Core Risk & Capital Modeling | `risk.py` | `POST /api/risk/calculate` | `test_risk_engine.py`, `test_engine_foundation.py` | 90 | **READY — VERIFIED** |
| `LAB-03` | Risk Attribution & Euler Decomposition | `attribution.py` | `POST /api/risk/attribution` | `test_attribution.py`, `test_phase15_remediation.py` | 35 | **READY — VERIFIED** |
| `LAB-04` | Scenario & Macro Stress Testing | `scenarios.py` | `POST /api/scenarios/run` | `test_scenario_engine.py` | 30 | **CONDITIONALLY READY** |
| `LAB-05` | Reverse Stress & Boundary Search | `scenarios.py`, `fragility.py` | `POST /api/scenarios/reverse-stress` | `test_reverse_stress_and_boundary.py` | 7 | **READY — VERIFIED** |
| `LAB-06` | Fragility Analysis & Assumption Sensitivity | `fragility.py` | `POST /api/fragility/run` | `test_fragility_lab.py`, `test_fragility_new_attacks.py` | 38 | **READY — VERIFIED** |
| `LAB-07` | Model Validation & Analytical Check Lab | `validation.py` | `POST /api/validation/run` | `test_validation_edge_cases.py`, `test_validation_lab.py` | 33 | **READY — VERIFIED** |
| `LAB-08` | Out-of-Sample Backtesting Lab | `backtesting.py` | `POST /api/backtest/run` | `test_forecast_backtest.py` | 19 | **READY — VERIFIED** |
| `LAB-09` | Model Tournament & Benchmarking Lab | `benchmarks.py` | `POST /api/benchmarks/tournament` | `test_plugin_benchmarking.py`, `test_statistical_calibration.py` | 59 | **READY — VERIFIED** |
| `LAB-10` | Financial Data Diagnostics Lab | `data_diagnostics.py` | `POST /api/data/validate-ohlcv` | `test_data_diagnostics.py` | 6 | **READY — VERIFIED** |
| `LAB-11` | Monte Carlo Simulation Lab | `simulation.py` | `POST /api/simulation/monte-carlo` | `test_simulation_uncertainty.py` | 5 | **READY — VERIFIED** |
| `LAB-12` | Bootstrap & Uncertainty Lab | `simulation.py` | `POST /api/simulation/bootstrap` | `test_simulation_uncertainty.py` | 5 | **READY — VERIFIED** |
| `LAB-13` | Model Assumptions Registry Lab | `assumptions.py` | `GET /api/assumptions` | `test_phase13_full_platform_campaign.py` | 11 | **READY — VERIFIED** |
| `LAB-14` | Upstox Market Data V3 Provider Lab | `upstox.py`, `market_data.py` | `GET /api/upstox/candles` | `test_upstox_adapter.py`, `test_market_data.py` | 30 | **READY — VERIFIED** |
| `LAB-15` | Quantitative Allocation & Optimization | `allocation.py` | `POST /api/allocation/optimize` | `test_allocation_lab.py`, `test_new_api_and_cli.py` | 7 | **READY — VERIFIED** |
| `LAB-16` | ML Model Testing & Robustness Lab | `ml.py` | `POST /api/ml/evaluate` | `test_ml_evaluation.py`, `test_new_api_and_cli.py` | 7 | **READY — VERIFIED** |
| `LAB-17` | Model & Attack Plugin System | `plugins.py` | `POST /api/plugins/register` | `test_custom_model_builder.py`, `test_plugin_benchmarking.py` | 49 | **READY — VERIFIED** |
| `LAB-18` | Experiment Studio & Reproducibility | `projects.py`, `reproducibility.py` | `POST /api/projects` | `test_reproducibility_lab.py`, `test_experiment_studio.py` | 68 | **READY — VERIFIED** |
| `EXT-01` | Corporate Actions & Dividend Adjustment | Upstox API | N/A | `test_upstox_adapter.py` | Documented Limitation | **BLOCKED** |
| `EXT-02` | Sovereign Macro & Yield Curve Feeds | Central Bank API | N/A | `test_scenario_engine.py` | Documented Limitation | **BLOCKED** |

---

## Traceability Totals
- **Total Unique Core Capabilities:** 18
  - `READY — VERIFIED`: 17
  - `CONDITIONALLY READY`: 1
- **Total External Data Dependencies:** 2
  - `BLOCKED`: 2
- **Grand Total Capabilities Audited:** 20
- **Total Automated Tests Traced:** 585 tests across 33 test files.
- **Pass Rate:** 100% (585 passed, 0 failed).
