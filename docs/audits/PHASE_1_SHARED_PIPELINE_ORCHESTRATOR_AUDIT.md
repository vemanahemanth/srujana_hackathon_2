# PHASE 1 AUDIT REPORT: SHARED DATA PIPELINE, TEST ALL ORCHESTRATOR & RESEARCH LAB
**FragilityShield Quantitative Architecture & Extensibility Audit**
**Date:** October 2026
**Auditor:** Senior Full-Stack Architect & Quantitative Research Lead

---

## 1. Executive Summary

FragilityShield contains deep quantitative models, risk calculators, backtesting engines, scenario perturbation algorithms, and external connectivity adapters. However, historically, these laboratories evolved as semi-independent modules:
1. **Isolated Execution**: When a backtest or model validation was run, only that specific calculation was performed. Other relevant risk assessments (such as Monte Carlo, Tail Risk, Scenario Shocks, or Fragility Sensitivity) required manual navigation to other tabs and separate clicks with duplicated inputs.
2. **Fragmented Persistence**: Several labs (`StrategyBacktestLab`, `ModelValidationLab`, `FragilityAssumptionMatrix`, and `ExternalIngestionEngine`) stored records into local in-memory arrays or catalog directories, while others (`PortfolioWorkbench`, `MonteCarloLab`, `UncertaintyLab`) returned direct HTTP responses without persisting experiment runs into the central ledger.
3. **Missing Test Orchestrator**: There was no unified "Test All" or "Custom Test Profile" orchestrator that could take an experiment submission (internal or external via SDK/Colab) and automatically run all applicable test suites with incremental status tracking.

This audit maps existing capabilities, partial implementations, demo/mock patterns, APIs, and the exact integration blueprint for Phases 2–8.

---

## 2. Inventory of Existing Functionality

| Module / Engine | File Path | Existing Working Capabilities | Current Gaps / Limitations |
| :--- | :--- | :--- | :--- |
| **Risk Analytics Engine** | `backend/fragility_engine/risk.py` | Historical VaR, Parametric VaR, Cornish-Fisher VaR, Expected Shortfall (CVaR), Volatility, Sharpe Ratio, Max Drawdown. | Does not automatically persist an experiment run into the unified ledger when called via `/api/risk/calculate`. |
| **Scenario & Stress Engine** | `backend/fragility_engine/scenarios.py` | Historical shock library (2008 GFC, 2020 COVID, Taper Tantrum), factor shocks (equity crash, interest rate surge, vol spike), custom shock vectors. | Calculates shock impact on portfolio weights, but does not record results into the experiment history. |
| **Tail Risk & EVT Engine** | `backend/fragility_engine/tail_risk_engine.py` | Extreme Value Theory (EVT/POT), Hill estimator, Reverse Stress Testing (breach boundary search), Liquidity-Adjusted VaR. | Independent endpoint (`/api/tail-risk/calculate`); not orchestrated as part of model screening. |
| **Fragility Assumption Matrix** | `backend/fragility_engine/fragility.py` | 2D assumption sensitivity grid (lookbacks × distributions), conclusion change percentage, relative sensitivity range. | Manages its own `FRAGILITY_EXPERIMENT_RUNS` list; partial schema overlap with central runs. |
| **Model Validation Engine** | `backend/fragility_engine/risk_model_validation.py` | Kupiec POF test, Christoffersen independence test, Basel traffic light zones (Green/Yellow/Red), ES backtesting. | Can evaluate predictions or VaR breaches, but lacked a unified trigger for external models. |
| **Strategy & Backtesting Lab** | `backend/fragility_engine/backtesting_lab.py`, `strategy_engine.py` | Walk-forward simulation with strict 1-bar lag (no lookahead bias), slippage, fee modeling, equity curve, trade log, indicator ablation. | Highly capable; saves to `STRATEGY_BACKTEST_RUNS` and `repo.save_experiment_run`. |
| **Monte Carlo Simulation** | `backend/fragility_engine/monte_carlo_engine.py` | Geometric Brownian Motion, Student-t jumps, GARCH vol paths, ruin probabilities, terminal distributions. | Runs on-demand; results are ephemeral and not linked to experiment run IDs. |
| **Bootstrap & Uncertainty** | `backend/fragility_engine/uncertainty_engine.py` | Stationary block bootstrap, circular block bootstrap, IID bootstrap, metric confidence intervals. | Runs on-demand; not connected to unified experiment reproducibility ledger. |
| **Data Diagnostics & Observatory** | `backend/fragility_engine/data_diagnostics.py`, `data_observatory.py` | Augmented Dickey-Fuller (ADF) test, KPSS test, Ljung-Box autocorrelation, Jarque-Bera normality, outlier detection. | Used in Data Observatory; not automatically run as an input validation prerequisite for models. |
| **External Connectivity Engine** | `backend/fragility_engine/external_connectivity.py` | Canonical REST ingestion, SHA-256 provenance hashing, dual-layer metric recomputation (RMSE, MAE, Directional Accuracy), artifact storage. | Working; accepts external submissions from Colab/Python, but does not yet trigger automated full-suite testing. |
| **Unified Experiment Registry** | `backend/app.py` (`/api/experiments/runs`), `UnifiedExperimentRegistry.tsx` | Aggregates strategy backtests, model validations, fragility matrices, catalog reports, and ingested external runs. | Lacks an orchestrator trigger to "Test All" or execute custom test suites directly from the registry. |

---

## 3. Frontend Dashboard Audit: Data Flows & Mock Analysis

| Dashboard Page | Frontend Component | API Endpoint Used | Status & Real Data Flow |
| :--- | :--- | :--- | :--- |
| **Overview / Command Center** | `OverviewCommandCenter.tsx` | `GET /api/experiments/runs`, `GET /api/upstox/quote`, `GET /api/audit/events` | **Real**. Pulls live verified runs and benchmark quotes. |
| **Unified Experiment Registry (Page 09)** | `UnifiedExperimentRegistry.tsx` | `GET /api/experiments/runs`, `GET /api/experiments/{id}`, `POST /api/experiments/compare` | **Real**. Displays all canonical runs, dual-layer verification, provenance hashes, and artifact links. |
| **Model Validation Lab (Page 07)** | `ModelValidationLab.tsx` | `POST /api/models/risk-validation/run`, `POST /api/models/risk-validation/compare` | **Real**. Calculates Kupiec and Christoffersen backtests, but needed bridge to external model runs. |
| **Portfolio Workbench (Page 04)** | `PortfolioWorkbench.tsx` | `GET /api/portfolios`, `POST /api/risk/calculate`, `POST /api/portfolios/concentration` | **Real**. Uses portfolio holdings and historical prices. Needs one-click "Test All" to stress test the portfolio. |
| **Risk & Scenario Lab (Page 05)** | `RiskScenariosLab.tsx` | `POST /api/scenarios/run`, `POST /api/scenarios/reverse-stress` | **Real**. Applies actual shocks to holdings. Needs persistence of scenario runs into the registry. |
| **Fragility Assumption Matrix (Page 06)** | `FragilityAssumptionMatrix.tsx` | `POST /api/fragility/run`, `POST /api/fragility/surface` | **Real**. Computes 2D assumption perturbations. Already connected to experiment ledger. |
| **Strategy Backtest Lab (Page 08 & 16)** | `StrategyBacktestLab.tsx` | `POST /api/backtesting/run`, `GET /api/backtesting/configs` | **Real**. Executes real walk-forward logic. Fully connected to registry. |
| **Model Tournament & Benchmarking (Page 17)**| `ModelTournamentBenchmarking.tsx`| `POST /api/tournaments/run`, `GET /api/tournaments/candidates` | **Real**. Ranks candidates across Sharpe, information ratio, and drawdown. |
| **Monte Carlo Simulation Lab (Page 18)**| `MonteCarloSimulationLab.tsx` | `POST /api/monte-carlo/run` | **Real**. Computes simulated paths. Needs persistence into the experiment ledger. |
| **Bootstrap & Uncertainty Lab (Page 19)**| `BootstrapUncertaintyLab.tsx` | `POST /api/uncertainty/bootstrap` | **Real**. Computes block bootstrap confidence intervals. Needs persistence into the ledger. |
| **Data Quality Observatory (Page 10)** | `DataObservatory.tsx` | `POST /api/data/diagnostics`, `GET /api/upstox/candles` | **Real**. Computes stationarity and normality tests on actual market datasets. |

---

## 4. Key Architectural Gaps Identified

1. **Absence of a Canonical Test Orchestrator**:
   Users currently have to run each lab independently. If a user has a strategy, model, or portfolio, they cannot click "Test All" to automatically execute all applicable tests (Risk Analytics, Stress Scenarios, Tail Risk, Fragility Matrix, Monte Carlo, Bootstrap Uncertainty, and Data Diagnostics) in a single unified workflow.
2. **Missing Test Profile Schema**:
   Users cannot define, save, or select custom test suites (e.g., "Full Regulatory Stress Pack", "Quick Model Screen", "Conservative Tail Risk Audit") specifying which tests to execute and with what parameters.
3. **Ephemeral Results in Certain Labs**:
   Direct executions in `RiskAnalytics`, `MonteCarlo`, `Uncertainty`, and `Scenarios` were returned directly to the browser but not permanently recorded into `database.py` / `save_experiment_run`.
4. **External Submissions Not Auto-Testing**:
   When Google Colab or external SDK scripts submit a model or experiment, FragilityShield ingests and cryptographically verifies the metrics, but did not have an automated trigger to run server-side stress tests or full-suite evaluations.

---

## 5. Blueprint for Implementation (Phases 2–8)

1. **Phase 2**: Define `CanonicalExperimentRun`, `CanonicalTestResult`, and `CanonicalMetric` in `backend/fragility_engine/orchestrator.py`.
2. **Phase 3**: Implement `SharedTestOrchestrator` registering all 10 core test modules, supporting `test_all=True` and custom `test_profile`.
3. **Phase 4**: Connect API routes (`/api/orchestrator/run`, `/api/orchestrator/modules`, `/api/orchestrator/runs/{id}`, etc.) and ensure all labs persist runs to the shared ledger.
4. **Phase 5**: Build configuration-driven customizable strategies, scenarios, and test profiles with strict validation (no arbitrary code execution).
5. **Phase 6**: Extend Python SDK (`client.orchestrator`) and Colab integration to support one-line full-suite testing.
6. **Phase 7**: Add interactive "Test All" & "Custom Profile" modal and execution UI in `UnifiedExperimentRegistry` and `OverviewCommandCenter`.
7. **Phase 8**: Write comprehensive automated tests in `backend/tests/test_shared_orchestrator.py` verifying all 12 orchestrator requirements, and produce final verification deliverables.
