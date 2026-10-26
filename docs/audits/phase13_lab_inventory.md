# FragilityShield — Implemented Laboratory Inventory

**Audit Date:** October 25, 2026  
**Auditor:** Senior Software Auditor & Quantitative Validation Lead  
**Scope:** Exhaustive inventory of every implemented laboratory, entry point, dependency, test suite, and operational boundary in the FragilityShield repository.  
**Repository:** `/Users/vemanahemanthbabu/srujana_hackathon_2`  

---

## 1. Laboratory Inventory & Architecture Map

| Lab # | Laboratory Name | Core Engine Modules | Primary REST API Routes | Python SDK & CLI Commands | Test Suites | Implementation Status |
| :---: | :--- | :--- | :--- | :--- | :--- | :---: |
| **1** | **Portfolio & Allocation Lab** | [`models.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/models.py), [`portfolio_loader.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/portfolio_loader.py), [`concentration.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/concentration.py), [`allocation.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/allocation.py) | `/api/portfolios/sample`, `/api/portfolios/validate`, `/api/portfolios/concentration` | `sdk.validate_portfolio()`, `sdk.calculate_concentration()`, `cli portfolio validate` | `test_portfolio_lab.py`, `test_allocation_lab.py` | **FULL (Long-only)** |
| **2** | **Risk Engine & Attribution Lab** | [`risk.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/risk.py), [`attribution.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/attribution.py) | `/api/risk/calculate`, `/api/risk/attribution` | `sdk.calculate_risk()`, `sdk.calculate_risk_attribution()`, `cli risk` | `test_risk_engine.py`, `test_attribution.py`, `test_phase12_corrective_suite.py` | **FULL (Linear Covariance Beta)** |
| **3** | **Scenario & Stress Testing Lab** | [`scenarios.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/scenarios.py) | `/api/scenarios/execute`, `/api/scenarios/reverse-stress` | `sdk.execute_scenario()`, `sdk.run_reverse_stress()`, `cli scenario run` | `test_scenario_engine.py`, `test_reverse_stress_and_boundary.py` | **FULL** |
| **4** | **Fragility & Assumption Attack Lab** | [`fragility.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/fragility.py), [`assumptions.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/assumptions.py) | `/api/fragility/run`, `/api/fragility/search-boundary`, `/api/assumptions/catalog` | `sdk.run_fragility()`, `sdk.search_stress_boundary()`, `sdk.get_assumptions_catalog()`, `cli fragility` | `test_fragility_lab.py`, `test_fragility_new_attacks.py`, `test_reverse_stress_and_boundary.py` | **FULL** |
| **5** | **Model Integration & Capability Lab** | [`model_lab.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/model_lab.py), [`projects.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/projects.py) | `/api/models/manifests`, `/api/models/check-capabilities` | `sdk.register_model_manifest()`, `sdk.check_model_capabilities()` | `test_model_integration_lab.py`, `test_project_and_model_registry.py` | **FULL** |
| **6** | **Model Benchmarking & Ranking Lab** | [`benchmarks.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/benchmarks.py) | `/api/benchmarks/models`, `/api/benchmarks/execute` | `sdk.list_benchmark_models()`, `sdk.execute_benchmark()`, `cli benchmarks` | `test_plugin_benchmarking.py`, `test_statistical_calibration.py` | **FULL** |
| **7** | **Backtesting & Statistical Validation Lab** | [`backtest.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/backtest.py) | `/api/backtest/run` | `sdk.run_backtest()`, `cli backtest` | `test_forecast_backtest.py`, `test_validation_lab.py` | **FULL** |
| **8** | **Simulation & Uncertainty Lab** | [`simulation.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/simulation.py) | `/api/simulation/monte-carlo`, `/api/simulation/bootstrap` | `sdk.run_monte_carlo()`, `sdk.run_bootstrap()` | `test_simulation_uncertainty.py` | **FULL** |
| **9** | **Data Diagnostics & Market Data Lab** | [`data_diagnostics.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/data_diagnostics.py), [`market_data.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/market_data.py) | `/api/data/diagnostics`, `/api/data/validate-ohlcv`, `/api/data/validate-tabular`, `/api/data/audit-outliers`, `/api/data/detect-drift` | `sdk.run_data_diagnostics()`, `sdk.calculate_regulatory_charges()`, `cli charges` | `test_data_diagnostics.py`, `test_market_data.py` | **FULL** |
| **10** | **ML Model Evaluation Lab** | [`ml.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/ml.py) | Programmatic SDK integration | `sdk.evaluate_ml_model()` | `test_ml_evaluation.py` | **FULL** |
| **11** | **Plugin Registry & Security Policy Lab** | [`plugins.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/plugins.py) | `/api/models/register` | `sdk.list_plugins()`, `cli plugins` | `test_custom_model_builder.py`, `test_phase12_corrective_suite.py` | **FULL (Trusted-Mode Only)** |
| **12** | **Reproducibility & Provenance Lab** | [`reproducibility.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/reproducibility.py) | SHA-256 manifest hash calculation, run snapshotting | `sdk.reproduce_run()` | `test_reproducibility_lab.py` | **FULL** |
| **13** | **Experiment Studio & Catalog** | [`studio.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/studio.py), [`projects.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/projects.py) | `/api/projects`, `/api/datasets`, `/api/studio/catalog`, `/api/studio/experiment`, `/api/export` | `sdk.create_project()`, `sdk.register_dataset()`, `sdk.execute_studio_experiment()` | `test_experiment_studio.py`, `test_backend_acceptance_workflows.py` | **FULL** |

---

## 2. Detailed Laboratory Breakdown

### Lab 1: Portfolio & Allocation Lab
- **User Scenarios:** Import holdings from JSON/CSV, validate non-negative quantities and positive valuations, calculate sector weights and Herfindahl-Hirschman Index (HHI) concentration. Compute Markowitz Mean-Variance optimal weights, Equal Risk Contribution (Risk Parity), and Black-Litterman subjective view incorporation.
- **Entry Points:** `load_portfolio_from_json`, `load_portfolio_from_csv`, `calculate_portfolio_concentration`, `optimize_mean_variance`, `optimize_risk_parity`, `optimize_black_litterman`.
- **Known Boundaries:** Strictly long-only positions ($quantity > 0.0$ enforced in `Holding.__post_init__`). Short-selling is rejected with `ValueError`.

### Lab 2: Risk Calculation & Risk Attribution Lab
- **User Scenarios:** Calculate annualized volatility (ddof=1, default 252 factor), Historical VaR at 95% and 99% (positive loss convention), Acerbi & Tasche (2002) Expected Shortfall with IEEE 754 integer boundary precision, Maximum Drawdown with recovery duration. Perform Euler linear covariance-beta risk attribution.
- **Entry Points:** `calculate_annualized_volatility`, `calculate_historical_var`, `calculate_expected_shortfall`, `calculate_maximum_drawdown`, `calculate_risk_report`, `calculate_portfolio_risk_attribution`, `verify_attribution_finite_difference`.
- **Known Boundaries:** Component VaR is an Euler linear approximation ($\text{CVaR}_i = w_i \beta_i \text{VaR}_p$). Heavy-tailed returns diverge from linear beta.

### Lab 3: Scenario & Stress Testing Lab
- **User Scenarios:** Apply preset historical crisis scenarios (2008 Lehman default, 2020 COVID liquidity shock, 2000 Dot-com crash). Define parametric macro factor shocks (interest rates, crude oil, tech selloff). Execute reverse stress testing to solve for the exact market or sector shock magnitude that breaches a user-defined loss ceiling.
- **Entry Points:** `create_preset_scenario`, `apply_scenario`, `run_reverse_stress_test`.
- **Known Boundaries:** Reverse stress solver checks loss budget feasibility; if target loss exceeds 100% of the shockable portfolio subset, reports `feasible=False`.

### Lab 4: Fragility & Assumption Attack Lab
- **User Scenarios:** Perturb model assumptions across 6 attack dimensions (transaction friction, lookback window shift, EWMA volatility estimator, confidence level shift, liquidation shock, correlation breakdown). Rank vulnerability. Search break-even parameter limits using validated bisection.
- **Entry Points:** `run_return_friction_perturbation`, `run_lookback_perturbation`, `run_volatility_estimator_perturbation`, `run_confidence_level_perturbation`, `calculate_portfolio_liquidation_shock`, `run_correlation_perturbation`, `rank_perturbation_sensitivities`, `run_stress_boundary_search`.
- **Known Boundaries:** Bisection requires monotonic bracketed intervals ($min < max$). Invariant pairs (e.g. volatility under transaction friction) return `converged=False`.

### Lab 5: Model Integration & Capability Lab
- **User Scenarios:** Register a quantitative model contract manifest (`ModelManifest`). Inspect model capabilities against 7 canonical checks. Verify determinism, error handling under malformed input, and execution runtime timeouts.
- **Entry Points:** `run_model_integration_suite`, `check_model_capabilities`.
- **Known Boundaries:** `code_isolation_required: True` is a deployment requirement; local runtime runs in-process with trusted-code restrictions.

### Lab 6: Model Benchmarking & Ranking Lab
- **User Scenarios:** Benchmark multiple quantitative models across identical empirical return datasets. Compute standardized financial metrics (Sharpe, Calmar, Sortino, VaR, MaxDD). Generate benchmark rankings with tied-rank handling, unranked exclusions, and explicit non-superiority disclaimers.
- **Entry Points:** `execute_model_benchmark`, `BenchmarkSpecification`, `BenchmarkReport`.
- **Known Boundaries:** Models declaring incompatible capabilities are excluded from ranking with human-readable rationale.

### Lab 7: Backtesting & Statistical Validation Lab
- **User Scenarios:** Run walk-forward rolling backtests without forward look-ahead bias. Track daily VaR breaches. Evaluate Kupiec POF Likelihood-Ratio test and Christoffersen Markov Independence / Conditional Coverage test with exact closed-form $\chi^2$ p-values.
- **Entry Points:** `backtest_model_rolling`, `evaluate_var_breaches`, `calculate_kupiec_pof_test`, `calculate_christoffersen_test`.
- **Known Boundaries:** Small sample warnings issued for $N < 30$. Zero-breach transition frequencies handled safely without division by zero.

### Lab 8: Simulation & Uncertainty Lab
- **User Scenarios:** Generate parametric Monte Carlo equity projections under Gaussian and Student-$t$ distribution assumptions. Compute 5th, 50th, and 95th percentile confidence envelopes. Perform block bootstrap resampling to evaluate risk metric uncertainty bounds.
- **Entry Points:** `simulate_monte_carlo`, `calculate_bootstrap_uncertainty`.
- **Known Boundaries:** Requires random seed parameter for reproducible simulation.

### Lab 9: Data Diagnostics & Market Data Lab
- **User Scenarios:** Validate tabular datasets for missing values, duplicate timestamps, and monotonic chronological ordering. Validate financial OHLCV records (High >= Low, High >= Open/Close, non-negative volume). Detect outliers using Z-score and IQR. Detect dataset distribution drift using Kolmogorov-Smirnov and Wasserstein distance. Simulate realistic Indian market statutory transaction charges (STT, SEBI, stamp duty, exchange turnover, GST).
- **Entry Points:** `validate_tabular_dataset`, `validate_financial_ohlcv`, `audit_outliers`, `detect_dataset_drift`, `calculate_data_diagnostics`, `calculate_regulatory_charges`.

### Lab 10: Machine Learning Evaluation Lab
- **User Scenarios:** Generate zero look-ahead chronological train/validation/test splits. Evaluate regression models (MSE, RMSE, MAE, R², Directional Accuracy). Evaluate binary classification models (Precision, Recall, F1, Balanced Accuracy, Brier Score). Compute feature importances and temporal drift.
- **Entry Points:** `create_chronological_split`, `evaluate_financial_regression`, `evaluate_financial_classification`, `detect_feature_drift`.

### Lab 11: Plugin Registry & Security Policy Lab
- **User Scenarios:** Register custom quantitative model adapters. Validate metadata and configuration schemas. Enforce trusted-code-only execution policy; untrusted models attempting in-process execution raise `PermissionError`.
- **Entry Points:** `PluginRegistry.register`, `PluginRegistry.execute_plugin`, `PluginRegistry.get_isolation_status`.
- **Known Boundaries:** Arbitrary in-process untrusted code execution is blocked. External MicroVM / container worker required for true untrusted multi-tenancy.

### Lab 12: Reproducibility & Provenance Lab
- **User Scenarios:** Generate deterministic cryptographic SHA-256 provenance hashes for experiments, datasets, model weights, and hyperparameters. Re-execute historical experiments and verify identical numerical outputs to machine precision.
- **Entry Points:** `ProvenanceTracker`, `create_reproducible_record`, `verify_experiment_provenance`.

### Lab 13: Experiment Studio & Project Catalog
- **User Scenarios:** Organize research in hierarchical projects (`ProjectCatalog`). Register and version datasets and model manifests. Define multi-lab experiment specifications (`StudioExperimentDefinition`). Execute experiments across multiple labs, persist state and telemetry on disk (`data/experiments/`), and export comprehensive executive reports.
- **Entry Points:** `ProjectCatalog`, `LocalExperimentCatalog`, `execute_studio_experiment`, `/api/studio/experiment`, `/api/export`.
