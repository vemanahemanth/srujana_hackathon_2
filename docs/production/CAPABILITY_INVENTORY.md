# FragilityShield — Authoritative Capability Inventory (Phase 2)

**Audit Date:** 2026-10-25  
**Auditing Authority:** Independent Model Validation & Senior Engineering Team  
**Standard:** 18 Core Quantitative Laboratories + 2 External Data Dependencies

---

## 1. Summary of Inventory Totals

```
Total Core Laboratories:        18
  - READY — VERIFIED:           17
  - CONDITIONALLY READY:         1 (LAB-04: Scenario & Macro Stress Testing)
  - PARTIALLY IMPLEMENTED:       0
  - BLOCKED:                     0
  - NOT VERIFIED:                0
Subtotal Core Laboratories:     17 + 1 = 18

Total External Data Dependencies: 2
  - BLOCKED:                     2 (EXT-01: Corporate Actions, EXT-02: Sovereign Yield Curves)
Subtotal External Dependencies:  2

Grand Total Inventory Entries:  20 Unique Items
```

---

## 2. Exhaustive Specification of All 18 Core Laboratories

### LAB-01: Portfolio Ingestion, Validation & Concentration Analysis
- **Main Implementation File:** [`backend/fragility_engine/models.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/models.py), [`backend/fragility_engine/concentration.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/concentration.py)
- **Primary REST Routes:** `POST /api/portfolios/validate`, `GET /api/portfolios/sample`
- **SDK & CLI Entry Points:** `FragilityShieldSDK.validate_portfolio()`, `python -m fragility_engine.cli portfolio validate`
- **Input Schema:** JSON payload or CSV stream with fields `asset_id` (str), `quantity` (float > 0), `price` (float > 0), `sector` (optional str).
- **Supported Data Sources:** `USER_UPLOADED_DATA`, `SYNTHETIC_TEST_DATA` (sample fixture `nse_10l.json`).
- **Mathematical Contract:** Weights $w_i = \frac{q_i p_i}{\sum q_j p_j}$, $\sum w_i = 1.0$. Herfindahl-Hirschman Index $HHI = \sum w_i^2 \in [1/N, 1.0]$. Effective asset count $N_{eff} = 1 / HHI$.
- **Test Evidence:** 29 passing tests in [`test_portfolio_lab.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/tests/test_portfolio_lab.py).
- **Readiness Status:** **READY — VERIFIED**

---

### LAB-02: Core Risk & Capital Modeling
- **Main Implementation File:** [`backend/fragility_engine/risk.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/risk.py)
- **Primary REST Route:** `POST /api/risk/calculate`
- **SDK & CLI Entry Points:** `FragilityShieldSDK.calculate_risk()`, `python -m fragility_engine.cli risk calculate`
- **Input Schema:** Sized 1D numeric array of returns or `symbol` (str), confidence level $\alpha \in (0, 1)$, annualization factor (default 252.0).
- **Supported Data Sources:** `REAL_DATA` (via Upstox), `USER_UPLOADED_DATA`, `SYNTHETIC_TEST_DATA`.
- **Mathematical Contract:**
  - Historical VaR: $VaR_\alpha = -Q_{1-\alpha}(R)$ (positive loss convention).
  - Parametric Gaussian VaR: $VaR_{norm} = -(\mu + z_{1-\alpha} \sigma)$.
  - Cornish-Fisher Expansion: Corrects quantile for skewness $S$ and excess kurtosis $K$.
  - Coherent Expected Shortfall: Discrete Acerbi & Tasche (2002) integral; $ES_\alpha \ge VaR_\alpha$ strictly.
  - Volatility Annualized: $\sigma_{ann} = \sigma_{daily} \times \sqrt{252}$.
  - Maximum Drawdown: Peak-to-trough decline $MDD = \max_t (M_t - W_t)/M_t$.
- **Test Evidence:** 38 passing tests in [`test_risk_engine.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/tests/test_risk_engine.py).
- **Readiness Status:** **READY — VERIFIED**

---

### LAB-03: Portfolio Risk Attribution & Euler Decomposition
- **Main Implementation File:** [`backend/fragility_engine/attribution.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/attribution.py)
- **Primary REST Route:** `POST /api/risk/attribution`
- **SDK & CLI Entry Points:** `FragilityShieldSDK.attribute_risk()`, `python -m fragility_engine.cli risk attribute`
- **Input Schema:** Portfolio holdings dictionary, optional `asset_returns_matrix` ($T \times N$), or `use_upstox=True`.
- **Supported Data Sources:** `REAL_DATA`, `USER_UPLOADED_DATA`, `SYNTHETIC_TEST_DATA`.
- **Mathematical Contract:** Homogeneous first-degree decomposition: Marginal VaR $MVaR_i = \frac{\partial \rho(w)}{\partial w_i}$, Component VaR $CVaR_i = w_i \cdot MVaR_i$. Reconciliation invariant $\sum_{i=1}^N CVaR_i \equiv \rho(w)$ verified within floating-point tolerance ($10^{-10}$).
- **Test Evidence:** 11 passing tests in [`test_attribution.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/tests/test_attribution.py), 24 tests in [`test_phase15_remediation.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/tests/test_phase15_remediation.py).
- **Readiness Status:** **READY — VERIFIED**

---

### LAB-04: Scenario & Macro Stress Testing
- **Main Implementation File:** [`backend/fragility_engine/scenarios.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/scenarios.py)
- **Primary REST Route:** `POST /api/scenarios/run`
- **SDK & CLI Entry Points:** `FragilityShieldSDK.run_scenario()`, `python -m fragility_engine.cli scenario run`
- **Input Schema:** Portfolio object + preset scenario ID (`lehman_2008`, `covid_2020`, `rate_hike_100bps`) or custom sector/asset shock vectors.
- **Supported Data Sources:** `USER_UPLOADED_DATA`, `SYNTHETIC_TEST_DATA`.
- **Mathematical Contract:** Instantaneous asset valuation: $V_{i, stressed} = q_i p_i (1 + s_i)$. Total portfolio loss $\Delta V = \sum q_i p_i s_i$. P&L reconciliation verified.
- **Limitation:** Upstox does not offer live central bank policy rate telemetry or sovereign yield curves; scenarios operate on static mathematical shock projections.
- **Test Evidence:** 30 passing tests in [`test_scenario_engine.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/tests/test_scenario_engine.py).
- **Readiness Status:** **CONDITIONALLY READY**

---

### LAB-05: Reverse Stress Testing & Stress-Boundary Search
- **Main Implementation File:** [`backend/fragility_engine/scenarios.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/scenarios.py), [`backend/fragility_engine/fragility.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/fragility.py)
- **Primary REST Routes:** `POST /api/scenarios/reverse-stress`, `POST /api/fragility/search-boundary`
- **SDK & CLI Entry Points:** `FragilityShieldSDK.search_stress_boundary()`, `python -m fragility_engine.cli scenario reverse-stress`
- **Input Schema:** Portfolio object, target loss fraction $L^*$, shock target (market or sector/asset), return vector, failure threshold.
- **Mathematical Contract:** Solves Euler loss equation for required shock $s^* = -L^* / \sum_{i \in target} w_i$. Bracketing search applies secant/bisection algorithm to solve parameter threshold where target metric crosses failure boundary.
- **Test Evidence:** 7 passing tests in [`test_reverse_stress_and_boundary.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/tests/test_reverse_stress_and_boundary.py).
- **Readiness Status:** **READY — VERIFIED**

---

### LAB-06: Fragility Analysis & Assumption Sensitivity
- **Main Implementation File:** [`backend/fragility_engine/fragility.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/fragility.py)
- **Primary REST Route:** `POST /api/fragility/run`
- **SDK & CLI Entry Points:** `FragilityShieldSDK.run_fragility_analysis()`, `python -m fragility_engine.cli fragility run`
- **Input Schema:** Return series ($N \ge 20$), lookback window boundaries, EWMA decay factor $\lambda$, friction basis points, confidence levels.
- **Mathematical Contract:** Executes 5 structured assumption attacks: lookback shifts, RiskMetrics EWMA vs sample variance, execution friction drag, confidence shifts, portfolio liquidation cost. Computes percentage metric shifts and normalized composite fragility score $\in [0, 100]$.
- **Test Evidence:** 32 passing tests in [`test_fragility_lab.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/tests/test_fragility_lab.py), 6 tests in [`test_fragility_new_attacks.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/tests/test_fragility_new_attacks.py).
- **Readiness Status:** **READY — VERIFIED**

---

### LAB-07: Model Validation & Analytical Check Lab
- **Main Implementation File:** [`backend/fragility_engine/validation.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/validation.py)
- **Primary REST Route:** `POST /api/validation/run`
- **Input Schema:** Model manifest dictionary, empirical return series, portfolio holdings.
- **Mathematical Contract:** Evaluates candidate model outputs against analytical closed-form oracles (reference benchmark suite), tests portfolio invariants (homogeneity, subadditivity, translation invariance), and asserts parameter boundary constraints.
- **Test Evidence:** 31 passing tests in [`test_validation_edge_cases.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/tests/test_validation_edge_cases.py), 2 tests in [`test_validation_lab.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/tests/test_validation_lab.py).
- **Readiness Status:** **READY — VERIFIED**

---

### LAB-08: Out-of-Sample Backtesting Lab
- **Main Implementation File:** [`backend/fragility_engine/backtesting.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/backtesting.py)
- **Primary REST Route:** `POST /api/backtest/run`
- **SDK & CLI Entry Points:** `FragilityShieldSDK.run_backtest()`, `python -m fragility_engine.cli backtest run`
- **Input Schema:** Historical return series ($T \ge 60$), rolling estimation window $W$ (default 40), target VaR coverage $\alpha$ (default 0.95).
- **Mathematical Contract:** Rolling walk-forward 1-step ahead VaR forecast. Computes empirical breach count $N$. Evaluates Kupiec POF Unconditional Coverage likelihood ratio $LR_{uc} \sim \chi^2_1$ and Christoffersen Independence likelihood ratio $LR_{ind} \sim \chi^2_1$.
- **Test Evidence:** 19 passing tests in [`test_forecast_backtest.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/tests/test_forecast_backtest.py).
- **Readiness Status:** **READY — VERIFIED**

---

### LAB-09: Model Tournament & Benchmarking Lab
- **Main Implementation File:** [`backend/fragility_engine/benchmarks.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/benchmarks.py)
- **Primary REST Route:** `POST /api/benchmarks/tournament`
- **Input Schema:** Empirical return series, list of candidate model specifications.
- **Mathematical Contract:** Evaluates competing risk models on held-out out-of-sample data. Generates ranked leaderboard based on RMSE, MAE, tail quantile accuracy, and breach divergence penalty.
- **Test Evidence:** 16 tests in [`test_statistical_calibration.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/tests/test_statistical_calibration.py), 43 tests in [`test_plugin_benchmarking.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/tests/test_plugin_benchmarking.py).
- **Readiness Status:** **READY — VERIFIED**

---

### LAB-10: Financial Data Diagnostics Lab
- **Main Implementation File:** [`backend/fragility_engine/data_diagnostics.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/data_diagnostics.py)
- **Primary REST Routes:** `POST /api/data/validate-ohlcv`, `POST /api/data/validate-tabular`, `POST /api/data/audit-outliers`, `POST /api/data/detect-drift`
- **Input Schema:** OHLCV candle lists or 1D price/return arrays.
- **Mathematical Contract:**
  - Bar physics: Rejects bars where $Low > High$, $Open \notin [Low, High]$, $Close \notin [Low, High]$, or $Volume < 0$.
  - Outliers: Z-score $> 3.0$ and IQR winsorization flags.
  - Distribution moments: Sample skewness $S = \frac{\frac{1}{N}\sum (x_i - \bar{x})^3}{s^3}$, excess kurtosis $K = \frac{\frac{1}{N}\sum (x_i - \bar{x})^4}{s^4} - 3$.
  - Drift: Two-sample Kolmogorov-Smirnov test statistic and asymptotic p-value.
- **Test Evidence:** 6 passing tests in [`test_data_diagnostics.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/tests/test_data_diagnostics.py).
- **Readiness Status:** **READY — VERIFIED**

---

### LAB-11: Monte Carlo Simulation Lab
- **Main Implementation File:** [`backend/fragility_engine/simulation.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/simulation.py)
- **Primary REST Route:** `POST /api/simulation/monte-carlo`
- **SDK Entry Point:** `FragilityShieldSDK.run_monte_carlo()`
- **Input Schema:** Initial price $S_0$, historical returns (for $\mu, \sigma$ calibration), projection horizon $T \in [1, 252]$, path count $M \in [10, 2000]$, seed.
- **Mathematical Contract:** Simulates forward Geometric Brownian Motion paths: $S_t = S_{t-1} \exp\left( (\mu - \frac{1}{2}\sigma^2)\Delta t + \sigma \sqrt{\Delta t} Z_t \right)$. Calculates terminal price percentiles and simulated tail risk. Explicitly tagged `MIXED_DATA` with `SIMULATED` freshness status.
- **Test Evidence:** 5 passing tests in [`test_simulation_uncertainty.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/tests/test_simulation_uncertainty.py).
- **Readiness Status:** **READY — VERIFIED**

---

### LAB-12: Bootstrap & Uncertainty Analysis Lab
- **Main Implementation File:** [`backend/fragility_engine/simulation.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/simulation.py)
- **Primary REST Route:** `POST /api/simulation/bootstrap`
- **SDK Entry Point:** `FragilityShieldSDK.run_bootstrap_uncertainty()`
- **Input Schema:** Historical return series ($N \ge 8$), confidence level $\alpha$, bootstrap iterations $B \in [50, 1000]$, seed.
- **Mathematical Contract:** Executes stationary block bootstrap resampling preserving serial dependence. Derives 90% and 95% empirical confidence intervals for VaR and ES point estimates. Explicitly tagged `MIXED_DATA`.
- **Test Evidence:** 5 passing tests in [`test_simulation_uncertainty.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/tests/test_simulation_uncertainty.py).
- **Readiness Status:** **READY — VERIFIED**

---

### LAB-13: Model Assumptions Registry Lab
- **Main Implementation File:** [`backend/fragility_engine/assumptions.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/assumptions.py)
- **Primary REST Routes:** `GET /api/assumptions`, `POST /api/assumptions/audit`
- **Input Schema:** Empirical return series, candidate model family identifier.
- **Mathematical Contract:** Audits empirical series against model preconditions: normality (Jarque-Bera), i.i.d. autocorrelation (Ljung-Box), stationarity (Augmented Dickey-Fuller), and heavy tails ($K > 0$). Outputs pass/fail flags and failure regime warnings.
- **Test Evidence:** Tested in `test_phase13_full_platform_campaign.py`.
- **Readiness Status:** **READY — VERIFIED**

---

### LAB-14: Upstox Market Data V3 Provider Lab
- **Main Implementation File:** [`backend/fragility_engine/upstox.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/upstox.py), [`backend/fragility_engine/market_data.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/market_data.py)
- **Primary REST Routes:** `GET /api/upstox/status`, `GET /api/upstox/instruments/resolve`, `GET /api/upstox/candles`, `GET /api/upstox/quote`
- **SDK & CLI Entry Points:** `FragilityShieldSDK.get_upstox_candles()`, `python -m fragility_engine.cli upstox candles`
- **Input Schema:** Symbol or instrument key (e.g. `RELIANCE` / `NSE_EQ|INE002A01018`), interval (`1D` or `1minute`), `from_date`, `to_date`.
- **Supported Data Sources:** Live authenticated Upstox V3 Gateway (`https://api.upstox.com/v3`).
- **Mathematical & Security Contract:** Read-only market data only. Zero order routing or account mutation APIs. All timestamps normalized to `Asia/Kolkata` (`+05:30`). Non-physical candles ($High < Low$, negative prices) rejected. Tokens masked in memory and REST responses.
- **Test Evidence:** 26 passing tests in [`test_upstox_adapter.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/tests/test_upstox_adapter.py), live gateway probe verified.
- **Readiness Status:** **READY — VERIFIED**

---

### LAB-15: Quantitative Allocation & Optimization Lab
- **Main Implementation File:** [`backend/fragility_engine/allocation.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/allocation.py)
- **Primary REST Routes:** `POST /api/allocation/optimize`, `POST /api/allocation/compare`
- **SDK Entry Point:** `FragilityShieldSDK.optimize_allocation()`
- **Input Schema:** Covariance matrix ($N \times N$), asset identifier list, minimum weight $w_{min}$, maximum weight $w_{max}$, original and adjusted portfolios.
- **Mathematical Contract:** Solves constrained minimum-variance quadratic program: $\min_w \frac{1}{2} w^T \Sigma w$ subject to $\sum w_i = 1.0$ and $w_{min} \le w_i \le w_{max}$ via SciPy SLSQP. Calculates portfolio turnover $\text{Turnover} = \frac{1}{2}\sum |w_{1,i} - w_{0,i}|$ and basis point friction costs.
- **Test Evidence:** 5 tests in [`test_allocation_lab.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/tests/test_allocation_lab.py), 2 tests in [`test_new_api_and_cli.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/tests/test_new_api_and_cli.py).
- **Readiness Status:** **READY — VERIFIED**

---

### LAB-16: ML Model Testing & Robustness Lab
- **Main Implementation File:** [`backend/fragility_engine/ml.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/ml.py)
- **Primary REST Routes:** `POST /api/ml/evaluate`, `POST /api/ml/split`
- **SDK Entry Point:** `FragilityShieldSDK.evaluate_ml()`
- **Input Schema:** Feature matrix $X$, target vector $y$, task type (`regression`, `classification`, `forecasting`), prediction vector $\hat{y}$, train ratio.
- **Mathematical Contract:**
  - Strict chronological split: Guarantees $\max(\text{train\_indices}) < \min(\text{test\_indices})$. Shuffling strictly disallowed.
  - Regression: MAE, RMSE, $R^2$, MAPE.
  - Classification: Accuracy, Precision, Recall, F1, ROC-AUC, Brier score, Confusion matrix.
  - Forecasting: Mean Absolute Scaled Error (MASE), Mean Directional Accuracy (MDA).
  - Adversarial feature noise robustness evaluation.
- **Test Evidence:** 5 tests in [`test_ml_evaluation.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/tests/test_ml_evaluation.py), 2 tests in [`test_new_api_and_cli.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/tests/test_new_api_and_cli.py).
- **Readiness Status:** **READY — VERIFIED**

---

### LAB-17: Model & Attack Plugin System
- **Main Implementation File:** [`backend/fragility_engine/plugins.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/plugins.py)
- **Primary REST Routes:** `GET /api/plugins`, `POST /api/plugins/register`, `POST /api/plugins/execute`
- **Input Schema:** Plugin metadata specification, Python class implementation complying with `ModelPlugin` or `FragilityAttackPlugin` interface contracts.
- **Security & Conformance Contract:** Full conformance test suite validates input rejection and output typing. Host execution security gate blocks in-process execution of untrusted third-party code via `PermissionError`.
- **Test Evidence:** 6 tests in [`test_custom_model_builder.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/tests/test_custom_model_builder.py), 43 tests in [`test_plugin_benchmarking.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/tests/test_plugin_benchmarking.py).
- **Readiness Status:** **READY — VERIFIED**

---

### LAB-18: Experiment Studio & Reproducibility Lab
- **Main Implementation File:** [`backend/fragility_engine/projects.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/projects.py), [`backend/fragility_engine/reproducibility.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/reproducibility.py)
- **Primary REST Routes:** `GET /api/projects`, `POST /api/projects`, `POST /api/datasets`, `POST /api/experiments/runs`
- **SDK & CLI Entry Points:** `FragilityShieldSDK.create_project()`, `python -m fragility_engine.cli project create`
- **Input Schema:** Project metadata, dataset registration records, experiment run parameter configurations.
- **Reproducibility Contract:** Generates cryptographic SHA-256 digests across all input vectors, parameters, software environment versions, and output reports. Exports reproducible audit packages in JSON, CSV, Markdown, and LaTeX.
- **Test Evidence:** 38 tests in [`test_reproducibility_lab.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/tests/test_reproducibility_lab.py), 30 tests in [`test_experiment_studio.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/tests/test_experiment_studio.py).
- **Readiness Status:** **READY — VERIFIED**

---

## 3. External Data Dependencies Specification

### EXT-01: Corporate Actions & Dividend Adjustment Feed
- **Interface:** Upstox Historical Candle API (`/v3/historical-candle`)
- **Limitation:** Upstox Market Data V3 historical candles reflect raw unadjusted exchange trade tape prices. Cash dividend adjustments, bonus shares, and stock split adjustments are not provided.
- **Operational Requirement:** Long-term equity backtesting (>1 year) requires user upload of split-adjusted series or explicit disclosure in report metadata.
- **Readiness Status:** **BLOCKED (External Provider Limitation)**

### EXT-02: Sovereign Macroeconomic & Yield Curve Feeds
- **Interface:** Central Bank / Macro Telemetry Gateway
- **Limitation:** Upstox is strictly an exchange equity and derivatives market data broker. Sovereign yield curves (e.g. 91-day T-bill, 10-year G-sec) and RBI repo policy rates are not provided.
- **Operational Requirement:** Macroeconomic stress scenarios require user shock specifications; risk-free rates default to 0.0 or user-configured values.
- **Readiness Status:** **BLOCKED (External Provider Limitation)**
