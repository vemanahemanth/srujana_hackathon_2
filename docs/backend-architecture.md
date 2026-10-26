# FragilityShield — Backend Architecture Specification

**Product:** FragilityShield — Quantitative Risk, Model Validation & Assumption-Testing Laboratory  
**Specification Reference:** `FragilityShield_1.docx`  
**Date:** October 25, 2026  
**Status:** Canonical Reference Architecture

---

## 1. Architectural Philosophy & Core Invariants

FragilityShield is designed as an open-source, plug-and-play laboratory for financial risk modeling, quantitative model validation, assumption challenge, and machine-learning evaluation.

### 1.1 The Single Calculation Core Principle
All external interfaces—the **Python SDK**, the **Command-Line Interface (CLI)**, the **Versioned REST API**, the **Automated Test Suites**, and the **Experiment Studio**—call the exact same underlying calculation services located within `backend/fragility_engine/`.

Calculation logic is strictly forbidden from being duplicated in API route handlers, SDK managers, or CLI commands. Each interface serves solely as an ingestion, serialization, and presentation wrapper around the shared domain core.

```
                      ┌────────────────────────────────────────┐
                      │             User Interfaces            │
                      ├─────────────┬─────────────┬────────────┤
                      │ Python SDK  │     CLI     │  REST API  │
                      └──────┬──────┴──────┬──────┴─────┬──────┘
                             │             │            │
                             ▼             ▼            ▼
                      ┌────────────────────────────────────────┐
                      │    Shared Engine Facade & Managers     │
                      └────────────────────┬───────────────────┘
                                           │
         ┌───────────────────┬─────────────┴───────┬───────────────────┐
         ▼                   ▼                     ▼                   ▼
┌─────────────────┐ ┌─────────────────┐  ┌──────────────────┐ ┌────────────────┐
│  Portfolio Lab  │ │    Risk Lab     │  │   Scenario Lab   │ │ Fragility Lab  │
│ models / loader │ │ risk / attrib   │  │    scenarios     │ │   fragility    │
└────────┬────────┘ └────────┬────────┘  └────────┬─────────┘ └────────┬───────┘
         │                   │                    │                    │
         └───────────────────┼────────────────────┼────────────────────┘
                             │
         ┌───────────────────┼─────────────────────┬───────────────────┐
         ▼                   ▼                     ▼                   ▼
┌─────────────────┐ ┌─────────────────┐  ┌──────────────────┐ ┌────────────────┐
│ Allocation Lab  │ │ Validation Lab  │  │   ML Test Lab    │ │ Market Data    │
│   allocation    │ │   validation    │  │        ml        │ │  market_data   │
└────────┬────────┘ └────────┬────────┘  └────────┬─────────┘ └────────┬───────┘
         │                   │                    │                    │
         └───────────────────┴──────────┬─────────┴────────────────────┘
                                        ▼
                      ┌────────────────────────────────────────┐
                      │ Plugin Extensibility & Benchmarks      │
                      │       plugins / benchmarks             │
                      └─────────────────┬──────────────────────┘
                                        ▼
                      ┌────────────────────────────────────────┐
                      │ Experiment Studio & Reproducibility    │
                      │       studio / reproducibility         │
                      └────────────────────────────────────────┘
```

### 1.2 Mathematical & Methodological Invariants
1. **Loss Convention:** Financial risk metrics evaluate loss $L_t = -R_t$. Positive values represent financial loss.
2. **Acerbi-Tasche Coherence:** Expected Shortfall strictly satisfies subadditivity and exceeds Value-at-Risk ($ES_\alpha \ge VaR_\alpha$).
3. **Euler Risk Decomposition:** Portfolio risk decomposes additively across constituent holdings ($\sum CVaR_i = VaR_{\text{port}}$) within numerical tolerance ($< 10^{-7}$).
4. **Zero Look-Ahead Bias:** Chronological data splits and walk-forward evaluations strictly forbid contamination from future timestamps ($\max(\text{Date}_{\text{train}}) < \min(\text{Date}_{\text{test}})$).
5. **Deterministic Cryptographic Provenance:** Every experiment specification, input dataset, execution environment, and output result is hashed via SHA-256 for deterministic reproducibility and drift detection.

---

## 2. Module Layering & Contracts

### 2.1 Domain Models & Portfolio Ingestion (`models.py`, `portfolio_loader.py`)
- **`Holding`**: Immutable representation of a multi-asset position with fields: `asset_id`, `quantity`, `price`, `sector`, `entry_price`, `asset_class`, `metadata`.
  - Computes `invested_capital = quantity * entry_price`.
  - Computes `market_value = quantity * price`.
  - Computes `unrealized_pnl = market_value - invested_capital`.
  - Validates positive, finite quantities and prices. Rejects blank/whitespace IDs.
- **`Portfolio`**: Immutable collection of holdings with currency and metadata.
  - `get_weights(weight_basis)`: Computes normalized weights where $\sum w_i = 1.0$ using `market_value`, `invested_capital`, or `equal_weight`.
  - `top_holdings(k)`: Ranks holdings by valuation and computes cumulative weight.
  - `allocations_by_sector()` and `allocations_by_asset_class()`: Aggregates weights by sector and asset class.
  - `create_snapshot()`: Generates a timestamped, cryptographically hashable `PortfolioSnapshot`.
- **`portfolio_loader`**: High-performance JSON and CSV parser enforcing strict path traversal safeguards and schema validation.

### 2.2 Financial Calculations & Risk Engine (`risk.py`, `concentration.py`, `attribution.py`)
- **Volatility**: Annualized sample standard deviation $\sigma_{\text{ann}} = \sigma \sqrt{252}$ and `calculate_rolling_volatility` series.
- **Value-at-Risk (VaR)**: Non-parametric historical quantile calculation under the loss convention $L = -R$.
- **Expected Shortfall (ES)**: Discrete tail conditional expectation according to Acerbi & Tasche (2002).
- **Maximum Drawdown**: Continuous peak-to-trough equity curve analysis recording peak, trough, drawdown percentage, and recovery duration in trading days.
- **Financial Ratios**:
  - `calculate_sharpe_ratio`: Excess return over risk-free rate divided by annualized volatility.
  - `calculate_sortino_ratio`: Excess return divided by annualized downside deviation below a required target return.
  - `calculate_calmar_ratio`: Annualized return divided by maximum drawdown.
- **Multi-Asset Statistical Dependencies**:
  - `calculate_covariance_matrix` & `calculate_correlation_matrix`: Computes sample covariance/correlation with positive semi-definiteness verification.
  - `calculate_beta`: Covariance with market benchmark divided by benchmark variance.
  - `calculate_capture_ratios`: Upside capture ($\bar{R}_{p, +} / \bar{R}_{m, +}$) and downside capture ($\bar{R}_{p, -} / \bar{R}_{m, -}$).
- **Concentration Analysis**: Herfindahl-Hirschman Index (HHI) bounded strictly in $[10000/N, 10000]$.
- **Risk Attribution**: Euler component risk decomposition calculating marginal contribution to risk ($MCR_i$) and component VaR ($CVaR_i$) with exact sum reconciliation.

### 2.3 Scenario Lab & P&L Accounting (`scenarios.py`)
- **`ScenarioDefinition`**: Defines shock rules comprising `sector_shocks`, `asset_shocks`, and `macro_shocks`.
- **`validate_scenario_against_portfolio`**:
  - Verifies all targeted sectors and assets exist in the portfolio.
  - Strictly rejects conflicting simultaneous shocks to a holding's sector and asset ID to prevent ambiguous precedence.
  - Rejects shocks resulting in non-positive asset prices ($P_i^{\text{new}} \le 0$).
- **`apply_scenario`**: Executes the stressed revaluation, producing a `ScenarioResult` with exact P&L accounting identity:
  $$V_{\text{stressed}} = V_{\text{baseline}} + \Delta V_{\text{total}}$$
  $$\Delta V_{\text{total}} = \sum_{i} \Delta V_i = \sum_{S} \Delta V_S$$
- **Preset Scenarios**: Curated historical and hypothetical stress scenarios:
  - `banking_minus_20_it_minus_10`
  - `mild_market_correction` (-5%)
  - `moderate_market_drop` (-10%)
  - `severe_market_crash` (-20%)
  - `gfc_2008_replay` (Global Financial Crisis)
  - `covid_2020_replay` (March 2020 Liquidity Shock)
- **`apply_correlation_stress`**: Re-correlates empirical covariance matrices by elevating off-diagonal pairwise correlations to $\rho_{\text{stress}}$ while preserving individual asset volatilities and using eigenvalue floor clipping to preserve positive semi-definiteness.

### 2.4 Fragility Lab & Assumption Testing (`fragility.py`, `assumptions.py`)
- **Assumption Attacks Suite**:
  1. `run_lookback_window_attack`: Window truncation stress testing sample stability.
  2. `run_volatility_estimator_attack`: EWMA decay factor perturbations ($\lambda \in (0, 1)$) testing memory sensitivity.
  3. `run_confidence_level_attack`: Tail probability shifting ($95\% \to 99\%$) testing fat-tail vulnerability.
  4. `run_transaction_cost_attack`: Return drag shock ($+5 \text{ to } +50 \text{ bps}$) testing execution friction.
  5. `run_outlier_sensitivity_attack`: Winsorization (clipping) and Trimming (removal) of tail observations testing sensitivity to extreme single-day outliers.
  6. `run_missing_data_attack`: Bernoulli dropout with forward-fill and drop imputation policies testing data quality degradation.
  7. `run_regime_shift_attack`: High-volatility sub-period slicing testing structural instability.
- **`run_fragility_audit`**: Automated execution of 5 standardized perturbations across lookback, volatility estimation, tail confidence, friction drag, and outlier winsorization.
- **Sensitivity Ranking**: Strictly orders perturbations by descending absolute impact ($|\Delta \text{metric}|$), with explicit documentation that non-linear fragility effects do not add linearly.

### 2.5 Allocation & Optimization Lab (`allocation.py`)
- **Equal-Weighting**: `create_equal_weighted_portfolio` establishes the classical $1/N$ benchmark.
- **Weight Adjustment & Turnover**:
  - `adjust_portfolio_weights`: Normalizes user-specified target allocations.
  - `calculate_turnover`: Computes half the L1 norm of weight differences: $\frac{1}{2}\sum |w_{\text{new}, i} - w_{\text{old}, i}|$.
  - `calculate_transaction_cost`: Translates turnover and portfolio valuation into monetary friction costs.
- **Constrained Minimum-Variance Optimization**:
  - Solves the quadratic program:
    $$\min_{\mathbf{w}} \mathbf{w}^T \Sigma \mathbf{w} \quad \text{s.t.} \quad \sum w_i = 1, \quad l_i \le w_i \le u_i$$
  - Employs SciPy Sequential Least Squares Programming (`SLSQP`) with fallback diagnostics.
- **Side-by-Side Comparison**: `compare_allocations` generates a comprehensive comparison report itemizing volatility, VaR, HHI concentration, turnover, and transaction friction.

### 2.6 Validation Lab & Invariant Taxonomy (`validation.py`)
- **`ValidationStatus` Taxonomy**:
  - `PASS`: Calculation matched analytical closed-form expectation within numerical tolerance.
  - `FAIL`: Mathematical or property invariant violated.
  - `WARNING`: Tolerable divergence or parameter near critical boundary.
  - `SKIPPED`: Preconditions not met (e.g. required package unavailable).
  - `INCONCLUSIVE`: Sample size or statistical power insufficient to confirm invariant.
- **Reference-Value Invariant Tests**:
  - Test 1: Uniform distribution variance matches theoretical $\sigma = \frac{b - a}{\sqrt{12}}$.
  - Test 2: Standard Gaussian 95% VaR matches $z_{0.95} \approx 1.6448536$.
  - Test 3: Standard Gaussian 95% Expected Shortfall matches $\frac{\phi(z)}{0.05} \approx 2.0627128$.
  - Test 4: HHI for equal-weight portfolio of $N$ assets equals $\frac{10000}{N}$.
  - Test 5: Single-asset portfolio HHI equals exactly $10000.0$.
- **Portfolio Consistency Invariant Tests**: Validates weight unity ($\sum w_i = 1.0$), valuation positivity, and holding-level mathematical consistency.

### 2.7 Machine Learning Model Testing (`ml.py`)
- **`BaseMLModel`**: Contract declaring `model_id`, `task_type` (`REGRESSION`, `CLASSIFICATION`, `FORECASTING`), and `predict(X)`.
- **Chronological Data Splitting**:
  - `split_chronological`: Implements sequential splitting guaranteeing $\max(\text{Time}_{\text{train}}) < \min(\text{Time}_{\text{test}})$, preventing future information leakage into historical evaluation.
- **Evaluation Metric Suites**:
  - Regression: MAE, RMSE, $R^2$, MAPE.
  - Classification: Confusion Matrix, Accuracy, Precision, Recall, $F_1$-score, ROC-AUC (trapezoidal rule), Brier Score.
  - Forecasting: sMAE, RMSE, MASE (Mean Absolute Scaled Error relative to naive random walk).
- **Robustness Attacks**: Evaluates model prediction stability and metric degradation under Gaussian input noise injection and feature zero-dropout masking.

### 2.8 Plugin Extensibility & Benchmarking (`plugins.py`, `benchmarks.py`)
- **`ModelPlugin` & `AttackPlugin` Contracts**:
  - Strict metadata specification (`plugin_id`, `name`, `capabilities`, `version`, `supported_data_types`).
  - Pre-flight `validate_input(data, config)`.
  - Sandboxed `execute(data, config)` returning typed `ModelExecutionResult`.
- **Built-in Plugins**:
  - `builtin.historical_simulation` (Empirical sample distribution)
  - `builtin.parametric_gaussian` (Analytical normal distribution)
  - `builtin.ewma` (RiskMetrics exponential weighting)
  - `builtin.portfolio_concentration` (HHI analysis)
- **Multi-Model Benchmarking**: `execute_model_benchmark` runs competing plugins over identical data, computing side-by-side metric tables, execution durations, and ranked comparisons with explicit disclaimers regarding model assumptions.

### 2.9 Indian Market Layer (`market_data.py`)
- **`NSETradingCalendar`**: Full official NSE holiday calendar filtering weekend sessions and statutory holidays, converting timestamps to Indian Standard Time (IST, UTC+5:30).
- **Statutory Taxes & Charges**: `calculate_indian_transaction_charges` models:
  - Securities Transaction Tax (STT): 0.1% on equity delivery turnover.
  - NSE Exchange Turnover Charges: 0.00345%.
  - SEBI Regulatory Turnover Fee: 0.0001%.
  - Stamp Duty: 0.015% on buy turnover.
  - Goods & Services Tax (GST): 18% on brokerage and exchange fees.
- **Data Providers**:
  - `DataProvider`: Abstract contract for historical market series.
  - `NSEOfflineSampleDataProvider`: Deterministic, offline provider serving bundled NSE 10 Lakh sample data without requiring external internet access.
  - `UpstoxDataProvider`: Provider adapter for Upstox API v2 with transparent error handling and offline fallback when credentials are unconfigured.

### 2.10 Experiment Studio & Reproducibility (`studio.py`, `reproducibility.py`)
- **`StudioExperimentDefinition`**: High-level specification capturing dataset, baseline parameters, perturbation specs, and evaluation metrics.
- **`execute_studio_experiment`**: End-to-end experiment orchestrator running baseline risk, fragility attacks, invariant checks, and sensitivity rankings.
- **`ReproducibilityManifest`**: Cryptographic record containing:
  - SHA-256 fingerprint of input data.
  - SHA-256 fingerprint of experiment configuration.
  - SHA-256 fingerprint of output metrics.
  - System metadata (Python version, OS, timestamp, package versions).
- **Catalog & Comparison**: `LocalExperimentCatalog` provides atomic local persistence, retrieval, and comparative drift analysis (`compare_experiment_reports`).
- **Multi-Format Exporters**: Canonical JSON (`to_json`), publication Markdown (`to_markdown`), and analysis CSV (`to_csv`).

### 2.11 Python SDK & CLI (`sdk.py`, `cli.py`)
- **`fragility_engine.sdk.Client`**: Fluent Python client exposing dedicated domain managers:
  - `client.portfolios`: Create, load, export, and inspect portfolios.
  - `client.risk`: Compute volatility, VaR, ES, drawdowns, Sharpe, Sortino, Calmar, beta, capture ratios.
  - `client.scenarios`: Execute custom scenarios, presets, and correlation stress tests.
  - `client.fragility`: Run individual assumption attacks and consolidated audits.
  - `client.allocation`: Optimize portfolios, adjust weights, and compute turnover.
  - `client.validation`: Run analytical reference-value and consistency suites.
  - `client.ml`: Chronological splitting, metric evaluation, and robustness attacks.
  - `client.market_data`: Calculate Indian taxes/charges and access offline market data.
  - `client.experiments`: Run, retrieve, list, and compare reproducible studio experiments.
  - `client.reports`: Export reports to JSON, Markdown, and CSV.
  - `client.plugins`: Discover, register, and benchmark model plugins.
- **`fragility-shield` CLI**: Command-line interface providing argument-driven access to core workflows:
  - `portfolio`: Summary and allocation breakdown.
  - `risk`: Portfolio risk metric calculations.
  - `scenario`: Stress scenario execution with P&L reconciliation.
  - `fragility`: 5-perturbation assumption audit and sensitivity ranking.
  - `validation`: Analytical reference-value suite verification.
  - `plugins`: Registered plugin discovery.
  - `charges`: Indian trade cost and statutory tax calculations.

---

## 3. Security, Sandboxing & Invariant Safeguards

1. **Path Traversal Prevention**: All file operations in `portfolio_loader` and `studio` validate that user-provided identifiers and file paths do not escape designated directory trees (rejecting `..`, `/`, `\`, and null bytes).
2. **Process & Exception Isolation**: Untrusted plugin execution is isolated via structured try-except boundaries that capture traceback diagnostics and return `failed_execution` status records rather than crashing the primary application thread.
3. **No Arbitrary Code Execution**: Custom plugins must be explicitly registered via in-memory Python classes. Silent, unverified execution of uploaded `.py` files is strictly prohibited.
4. **Input Sanitization**: All arrays are coerced to 64-bit floating point and validated for non-emptiness, finiteness, and sample size sufficiency. Any `NaN`, `Inf`, or non-numeric tokens trigger explicit `ValueError` exceptions.
