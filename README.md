# FragilityShield

> **Open-Source Financial & ML Model Testing Laboratory**  
> *"How much should we trust a model's outputs when its assumptions, inputs, data quality, parameters, and operating conditions are challenged?"*

FragilityShield is an empirical stress-testing, validation, and fragility laboratory for financial portfolios and quantitative models. It provides a standardized environment to measure how sensitive outputs are to parameter shifts, data anomalies, and market shocks.

---

## Important Disclaimers

FragilityShield is **not** an investment advice platform, automated trading bot, or profitability guarantee system. All metrics, scenario analyses, and fragility audits are for research, educational, and model-validation purposes only.

---

## Architecture Overview

- **`backend/fragility_engine/`**: Pure, framework-agnostic Python quantitative calculation engine (`models.py`, `returns.py`).
- **`backend/tests/`**: Automated unit test suite with 100% test coverage for domain contracts and numerical calculations.
- **`frontend/`**: Planned React + TypeScript research dashboard (Phase 9).
- **`data/sample_portfolios/`**: Illustrative test fixtures, including the ₹10 Lakh NSE sample portfolio.
- **`docs/`**: Architecture plans and discovery reports (`phase-0-discovery-report.md`).

---

## Local Setup & Testing

### 1. Requirements
- Python 3.10+ (tested on Python 3.14.6)
- Git

### 2. Environment Setup
```bash
# Clone and enter the repository
cd srujana_hackathon_2

# Create a local virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install the engine in editable mode
pip install -e backend
```

### 3. Run Automated Tests
```bash
# Execute full unit test suite with branch coverage (250 tests, 92% coverage)
.venv/bin/python -m pytest backend/tests/ -v --cov=fragility_engine --cov-report=term-missing --cov-branch
```

---

## Validation & Reproducibility Lab (Phase 6)

Located in `backend/fragility_engine/reproducibility.py`:
- **Cryptographic Fingerprinting (`compute_canonical_hash`, `compute_dataset_hash`)**:
  - Deterministic SHA-256 fingerprinting for datasets, calculation configurations, and execution results.
  - Implements canonical JSON serialization (`canonical_json_dumps`): alphabetically sorted dictionary keys, IEEE 754 float precision, strict rejection of non-finite numbers (`NaN`, `Inf`), and compact representation.
  - Separates mathematical calculation parameters from informational metadata (`created_at`, `description`, `metadata`, `dataset_provenance`) so timestamps and user notes never corrupt calculation fingerprints.
- **Experiment Specification (`ExperimentSpecification`)**:
  - Fully typed, immutable domain model specifying `experiment_id`, `name`, `dataset_id`, `baseline_config`, `perturbation_specs`, `schema_version`, `algorithm_version`, `random_seed`, and `date_range`.
  - Validates baseline parameters (e.g. `confidence_level` $\in (0, 1)$) and rejects unsupported perturbation types.
- **Reproducible Experiment Runner (`run_reproducible_experiment`)**:
  - Orchestrates: (1) Dataset and configuration fingerprinting; (2) Baseline risk and concentration calculations; (3) Execution of configured perturbations; (4) Independent mathematical invariant validation; (5) Manifest generation with execution environment capture.
  - Supports 1D return series, 2D multivariate return matrices, and `Portfolio` instances.
- **Reproducibility Manifest (`ReproducibilityManifest`)**:
  - Immutable audit artifact capturing `input_fingerprint`, `configuration_fingerprint`, `output_fingerprint`, environment metadata (Python version, NumPy version, OS platform, machine architecture), validation status, check counts, warnings, and limitations.
- **Independent Invariant Verification (`verify_experiment_invariants`)**:
  - Validates non-circular mathematical constraints:
    - Portfolio weights sum to $1.0 \pm 10^{-5}$.
    - Asset HHI scale consistency ($H_{\text{points}} = 10000 \times H_{\text{decimal}}$).
    - Tail coherence: $\text{ES}_\alpha \ge \text{VaR}_\alpha - 10^{-9}$.
    - Maximum drawdown bounded within $[0.0, 1.0]$.
    - Strict finiteness of all baseline and perturbed metrics.
- **Output Comparison & Drift Detection (`compare_experiment_runs`)**:
  - Compares two experiment runs and produces a structured `DriftReport`.
  - Accurately classifies drift source:
    - **Input Data Drift**: Input dataset SHA-256 changed.
    - **Configuration Drift**: Model parameters or perturbation specs changed.
    - **Environment Drift**: Operating system, Python release, or NumPy version changed.
    - **Tolerance Divergence**: Numerical metrics diverged beyond configurable threshold $\epsilon$ (default $10^{-6}$).
- **Reports & Audits**:
  - Phase 5 Verification Report: [`docs/phase-5-verification-report.md`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/docs/phase-5-verification-report.md).
  - Phase 6 Issue Review: [`docs/phase-6-issue-review.md`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/docs/phase-6-issue-review.md).
  - Phase 6 Implementation Report: [`docs/phase-6-report.md`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/docs/phase-6-report.md).

---


## Fragility Lab (Phase 5)

Located in `backend/fragility_engine/fragility.py`:
- **Risk & Model Robustness Laboratory**:
  - Measures how sensitive risk conclusions and portfolio metrics are to shifts in underlying assumptions.
  - Generates structured, immutable `FragilityExperimentResult` artifacts containing baseline metrics, perturbed metrics, absolute changes ($\Delta = M_1 - M_0$), and relative changes ($\Delta / |M_0|$).
  - Handles zero-baseline relative change safely by emitting `None` (JSON `null`) rather than NaN or infinity.
- **Supported Perturbation Models**:
  - **Lookback Window Perturbation (`run_lookback_perturbation`)**: Evaluates risk sensitivity when the historical sample window is truncated.
  - **Alternative Volatility Estimator (`run_volatility_estimator_perturbation`)**: Compares standard sample volatility against RiskMetrics Exponentially Weighted Moving Average (EWMA) volatility (`calculate_ewma_volatility`, $\lambda \in (0, 1)$).
  - **Return Friction Shock (`run_return_friction_perturbation`)**: Evaluates return series drag by deducting constant basis points ($r_t' = r_t - \frac{c}{10000}$) to measure tail risk expansion.
  - **Portfolio Liquidation Cost Shock (`calculate_portfolio_liquidation_shock`)**: Models turnover execution friction on total portfolio valuation ($\text{Cost} = \text{MV} \times \tau \times \frac{c}{10000}$).
  - **Multivariate Correlation Stress (`run_correlation_perturbation`)**: Perturbs empirical correlation matrix toward a uniform crisis target ($C_\alpha = (1-\alpha) C_0 + \alpha C_{\text{target}}$) for synchronized 2D return matrices, evaluating diversified portfolio risk expansion.
  - **Tail Confidence Level Shift (`run_confidence_level_perturbation`)**: Evaluates tail risk expansion between 95% and 99% confidence.
- **Sensitivity Ranking Engine (`rank_perturbation_sensitivities`)**:
  - Ranks experiments by absolute impact $|\Delta|$ on any target metric, identifying the most vulnerable modeling assumption without arbitrary composite scores.
- **Reports & Audits**:
  - Phase 4.1 Verification: [`docs/phase-4.1-verification-report.md`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/docs/phase-4.1-verification-report.md).
  - Phase 5 Issue Review: [`docs/phase-5-issue-review.md`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/docs/phase-5-issue-review.md).
  - Phase 5 Implementation Report: [`docs/phase-5-report.md`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/docs/phase-5-report.md).

---

## Scenario Lab (Phase 4)

Located in `backend/fragility_engine/scenarios.py`:
- **Pure Deterministic Scenario Engine (`apply_scenario`)**:
  - Applies instantaneous price shocks to an existing portfolio snapshot without modifying caller inputs.
  - Calculates holding-level stressed prices, market values, and monetary P&L contributions.
  - Aggregates portfolio-level stressed valuation, net monetary P&L, percentage return, and positive loss magnitude.
  - Produces sector-level P&L attribution and identifies explicitly unshocked holdings.
  - Mathematical integrity: Guarantees exact reconciliation $\sum \text{holding\_pnl} = \text{portfolio\_pnl}$ and $\sum \text{sector\_pnl} = \text{portfolio\_pnl}$.
- **Scenario Specification (`ScenarioDefinition`)**:
  - Supports stable `scenario_id`, human-readable name, narrative description, `sector_shocks`, `asset_shocks`, and `version`.
  - Shocks are expressed as decimal returns (e.g. `-0.20` for -20%, `+0.10` for +10%).
- **Strict Conflict Policy**:
  - Rejects overlapping rules by default: If a holding is targeted simultaneously by a sector shock and an asset-specific shock, execution is aborted with a `ValueError`. Silent precedence or combining of shocks is prohibited.
- **Robust Validation**:
  - Rejects non-finite (NaN, $\pm\infty$) shocks and shocks producing non-positive prices ($\text{shock} \le -1.0$).
  - Rejects unknown sector and asset identifiers not present in the portfolio snapshot.
- **Standard Benchmark Preset (`create_preset_scenario`)**:
  - `"banking_minus_20_it_minus_10"`: -20% instantaneous shock on Banking and -10% on Information Technology assets.
  - Illustrative ₹10 Lakh portfolio impact: Stressed value = ₹9,20,000.00, P&L = -₹80,000.00 (-8.00%), Loss magnitude = ₹80,000.00.
- **Audit & Issue Review**:
  - Documented in `docs/phase-4-issue-review.md`.

---

## Risk Calculation Engine (Phase 3)

Located in `backend/fragility_engine/risk.py`:
- **Annualized Volatility (`calculate_annualized_volatility`)**:
  - Sample standard deviation with Bessel's correction (`ddof=1` default).
  - Formula: $\sigma_{\text{ann}} = \sigma_{\text{daily}} \times \sqrt{252}$.
- **Historical Value at Risk (`calculate_historical_var`)**:
  - Positive-loss convention: Positive VaR indicates loss magnitude ($L = -R$).
  - Evaluated at 95% and 99% confidence using explicit empirical quantile interpolation (`method="linear"`).
- **Historical Expected Shortfall (`calculate_expected_shortfall`)**:
  - Implements coherent discrete tail expectation via **Acerbi & Tasche (2002)** with fractional tail weighting.
  - Solves finite-sample tie and boundary distortions; mathematically guarantees $\text{ES} \ge \text{VaR}$ without artificial clamping.
- **Maximum Drawdown & Duration Dynamics (`calculate_maximum_drawdown`)**:
  - Peak-to-trough decline as a positive loss fraction on $[0.0, 1.0]$.
  - Tracks `peak_to_trough_duration`, `recovery_duration`, and `total_drawdown_duration` in observation intervals.
  - Distinguishes fully recovered drawdowns from ongoing/unrecovered drawdowns and partial rebounds.
- **Consolidated Risk Report (`calculate_risk_report`)**:
  - Bundles daily/annualized volatility, VaR (95%/99%), ES (95%/99%), drawdown diagnostics, and sample size caveats into `RiskMetricsReport`.

## Portfolio Lab & Analytics (Phase 2)

### 1. Illustrative ₹10 Lakh NSE Portfolio Fixtures
Located in `data/sample_portfolios/`:
- `nse_10l.json`: JSON portfolio fixture with metadata and illustrative holdings summing to exactly ₹10,00,000.
- `nse_10l.csv`: Deterministic CSV fixture matching the JSON representation.
- **Sectors covered:** Banking (30%), Information Technology (20%), Energy (15%), FMCG (15%), Healthcare (10%), Industrials (10%).
- *Disclaimer:* All prices, quantities, and allocations are deterministic test assumptions for empirical model testing and do not represent live market data or investment advice.

### 2. Portfolio Loader (`portfolio_loader.py`)
- `load_portfolio_from_json(source)`: Safe JSON parser with strict field checks and contradictory valuation rejection.
- `load_portfolio_from_csv(source)`: Strict all-or-nothing CSV parser requiring `asset_id,quantity,price,sector` columns.
- `export_portfolio_to_csv(portfolio, target)`: Deterministic CSV export with stable column ordering.

### 3. Allocation & Concentration Analytics (`concentration.py`)
- `calculate_portfolio_concentration(portfolio)`: Computes aggregate valuation, asset weights, sector market values, and sector proportions.
- `calculate_hhi(weights)`: Calculates both decimal Herfindahl-Hirschman Index ($[0.0, 1.0]$) and conventional HHI points ($[0, 10000]$).
  - *Reference:* Under Antitrust guidelines, HHI points $<1500$ indicates diversification, $1500-2500$ moderate concentration, and $>2500$ high concentration.
  - *Disclaimer:* HHI measures bucket concentration across weights, not correlation or tail risk.

---

## Core Domain Models (Phase 1)

1. **`Holding`**: Represents an individual asset holding with strict validation for positive, finite quantity, price, and non-empty asset identifier. Calculates `market_value` dynamically.
2. **`Portfolio`**: Represents a multi-asset portfolio with currency validation, unique asset verification, total valuation, and portfolio weights calculation.
3. **`MetricResult`**: Standardized container for quantitative outputs with formal methodology citations, parameter tracking, and diagnostic warnings.
4. **`compute_simple_returns`**: Pure function calculating arithmetic returns from consecutive positive prices without modifying caller-owned sequences.
