# FragilityShield — Product Gap Implementation & Lab Expansion Report

**Repository:** `/Users/vemanahemanthbabu/srujana_hackathon_2`  
**Date:** October 25, 2026  
**Auditor / Engineer:** Quantitative Risk & Software Engineering Team  
**Scope:** Full Product Completeness Audit & Priority Laboratory Expansion  
**Status:** Complete — All Priority Laboratories Implemented, Tested, and Verified

---

## 1. Executive Summary

Following the comprehensive audit documented in [`docs/product-completeness-audit.md`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/docs/product-completeness-audit.md), FragilityShield has been expanded from an 8-workspace application into a 12-workspace quantitative stress-testing laboratory. 

Every expanded capability is grounded in rigorous quantitative finance mathematics and software engineering:
1. **Data Diagnostics Lab:** Pre-model empirical return diagnostics (skewness, excess kurtosis, Jarque-Bera normality testing with exact Chi-Square $p$-values, lag-1 autocorrelation, and suitability verdicts).
2. **Euler Marginal Risk Allocation & Component VaR:** Exact Euler Homogeneity risk decomposition ($\sum CVaR_i = VaR_p$) reconciling asset marginal contributions with zero residual discrepancy ($< 10^{-7}$).
3. **Simulation & Uncertainty Lab:** Multi-path forward Monte Carlo simulations with Gaussian and Student-$t$ fat-tailed innovations, paired with non-parametric bootstrap resampling yielding 90% and 95% confidence intervals on VaR and Expected Shortfall.
4. **Model Assumption Registry:** Centralized, inspectable catalog of mathematical formulations, distributional assumptions, temporal assumptions, preconditions, known failure regimes, and fragility vulnerabilities across quantitative model families.
5. **Interactive Custom Model Builder:** Extensible plugin interface allowing users to dynamically configure, instantiate, and register custom models (Student-$t$, EWMA, Cornish-Fisher, historical quantiles) into the global runtime registry for cross-model benchmarking and walk-forward backtesting.

All 402 automated unit, property, and API tests pass with 94% branch/statement coverage. End-to-end browser verification has been executed and visually recorded.

---

## 2. Quantitative Architecture & Implementations

### 2.1 Empirical Data Diagnostics (`backend/fragility_engine/data_diagnostics.py`)
Financial return distributions rarely follow a Gaussian bell curve. Calculating Parametric Gaussian VaR on fat-tailed or skewed returns creates significant underestimation of tail risk.

The new Data Diagnostics engine evaluates:
- **Sample Mean ($\mu$) and Sample Volatility ($\sigma$):** Annualized with continuous compounding.
- **Fisher-Pearson Sample Skewness ($S$):**
  $$S = \frac{\frac{1}{N} \sum_{t=1}^N (R_t - \bar{R})^3}{\left(\frac{1}{N} \sum_{t=1}^N (R_t - \bar{R})^2\right)^{3/2}}$$
- **Sample Excess Kurtosis ($\kappa$):**
  $$\kappa = \frac{\frac{1}{N} \sum_{t=1}^N (R_t - \bar{R})^4}{\left(\frac{1}{N} \sum_{t=1}^N (R_t - \bar{R})^2\right)^2} - 3$$
- **Jarque-Bera Normality Test ($JB$):**
  $$JB = \frac{N}{6} \left(S^2 + \frac{\kappa^2}{4}\right) \sim \chi^2(2)$$
  Evaluates exact survival function $p = 1 - F_{\chi^2(2)}(JB) = \exp(-JB / 2)$.
- **First-Order Autocorrelation ($\rho_1$):** Identifies volatility clustering or momentum/reversal tendencies.
- **Zero-Return Frequency:** Detects illiquid or stale pricing regimes.
- **Automated Model Suitability Guidance:** Produces actionable recommendations (e.g. rejecting Gaussian models when $\kappa > 1.0$ or $p_{JB} < 0.05$ in favor of Student-$t$ or Historical Simulation).

### 2.2 Euler Marginal Risk Allocation & Component VaR (`backend/fragility_engine/attribution.py`)
Value-at-Risk under standard linear portfolio models is a homogeneous function of degree 1 in portfolio holdings ($VaR(\lambda \mathbf{w}) = \lambda VaR(\mathbf{w})$). By Euler's homogeneous function theorem:
$$VaR_p = \sum_{i=1}^n w_i \frac{\partial VaR_p}{\partial w_i}$$

The engine calculates:
- **Marginal VaR ($MVaR_i$):**
  $$MVaR_i = \frac{\partial VaR_p}{\partial w_i} = \beta_i \cdot \frac{VaR_p}{W_p}$$
  where $\beta_i = \frac{\text{Cov}(R_i, R_p)}{\sigma_p^2}$.
- **Component VaR ($CVaR_i$):**
  $$CVaR_i = w_i \cdot MVaR_i = w_i \cdot \beta_i \cdot VaR_p$$
- **Percentage Risk Contribution:**
  $$\%CVaR_i = \frac{CVaR_i}{VaR_p} = w_i \cdot \beta_i$$
- **Euler Reconciliation Guarantee:**
  $$\left| VaR_p - \sum_{i=1}^n CVaR_i \right| < 10^{-7}$$

### 2.3 Forward Monte Carlo & Bootstrap Uncertainty (`backend/fragility_engine/simulation.py`)
Risk measures are point estimates subject to sample uncertainty and path dependency.
- **Forward Multi-Path Monte Carlo:** Simulates geometric random walks over horizon $H$:
  $$S_t = S_0 \exp\left(\sum_{k=1}^t \left(\mu - \frac{1}{2}\sigma^2\right)\Delta t + \sigma \sqrt{\Delta t} \, \epsilon_k\right)$$
  Supports both standard normal innovations $\epsilon_k \sim \mathcal{N}(0, 1)$ and standardized Student-$t$ fat-tailed innovations $\epsilon_k \sim t(\nu) \cdot \sqrt{\frac{\nu-2}{\nu}}$.
  Calculates the 5th percentile, median (50th), and 95th percentile trajectory envelope across all simulated paths.
- **Non-Parametric Bootstrap Resampling:** Resamples the empirical return series with replacement over $B$ iterations (default 300 to 1,000):
  Generates empirical sampling distributions for VaR and ES, extracting two-sided 90% and 95% percentile confidence intervals:
  $$CI_{95}(VaR) = [q_{0.025}(VaR^*), q_{0.975}(VaR^*)]$$

### 2.4 Centralized Model Assumption Registry (`backend/fragility_engine/assumptions.py`)
To prevent models from being treated as black boxes, the assumption catalog explicitly documents:
- **Parametric Gaussian:** Assumes i.i.d. normal returns; fails during market crashes, liquidity crises, and fat-tailed shocks.
- **Historical Simulation:** Assumes stationarity and that past returns represent future distribution; fails on regime shifts, structural breaks, and out-of-sample extremes.
- **RiskMetrics EWMA:** Assumes time-varying volatility with geometric memory decay ($\lambda = 0.94$); fails when decay factor is miscalibrated or during mean-reverting spikes.
- **Student-$t$ Fat-Tailed:** Assumes polynomial tail decay controlled by degrees of freedom $\nu$; fails under extreme asymmetric skewness.
- **Cornish-Fisher Expansion:** Assumes distribution can be approximated via Taylor expansion of quantiles using skewness and kurtosis; fails when kurtosis is excessively high ($\kappa > 4$), causing quantile non-monotonicity.

### 2.5 Dynamic Model Builder (`backend/fragility_engine/plugins.py`)
Added `ConfigurableCustomModelPlugin(ModelPlugin)`:
- Allows programmatic or UI-driven configuration of custom models with user-defined parameters (`df` for Student-$t$, `decay_factor` for EWMA, quantile expansion methods).
- Implemented global shared plugin registry (`_GLOBAL_DEFAULT_REGISTRY` in `get_default_registry()`).
- Registered models are immediately queryable via `/api/benchmarks/models`, executable in `/api/benchmarks/execute`, and backtestable in `/api/backtest/run`.

---

## 3. Web Application Interface & User Experience

The web interface (`frontend/index.html`, `frontend/style.css`, `frontend/app.js`) was extended with 5 responsive research panes:

| Workspace Pane | Primary Visualizations & Controls | Interaction Flow |
| :--- | :--- | :--- |
| **Data Lab** | SVG Return Distribution Histogram, Skewness/Kurtosis KPI cards, Jarque-Bera Normality Badge, Model Suitability Advice cards | Loads return history, displays moments, visually overlays distribution, and renders warnings regarding Gaussian assumption invalidity. |
| **Risk & Attribution** | Dual-axis Equity Curve / Drawdown chart, Euler Marginal Risk Allocation & Component VaR decomposition table | Recalculates risk metrics, computes individual holding betas $\beta_i$, component VaR, percentage risk contribution, and verifies Euler sum reconciliation badge. |
| **Simulation & Uncertainty** | Forward Monte Carlo fan envelope chart (5th/50th/95th percentiles), Bootstrap VaR & ES Confidence Interval cards | Executes 300+ simulation paths, renders terminal loss distribution, and displays sample-size uncertainty bounds. |
| **Assumption Registry** | Filterable catalog cards detailing mathematical formulations, preconditions, failure regimes, and fragility vulnerabilities | Allows risk officers to inspect why a specific model will fail before deploying it. |
| **Model Builder** | Dynamic custom model configuration form, live registration status, and registered models table | Allows users to configure a Student-$t$ or EWMA model with custom parameters, register it into the backend, and verify its immediate availability. |

---

## 4. Verification and Validation Results

### 4.1 Automated Test Execution Summary
Executed comprehensive regression and unit test suite across all 12 test modules:

```bash
.venv/bin/python -m pytest backend/tests/ -v --cov=fragility_engine --cov-report=term-missing
```

**Results:**
- Total tests: **402 passed**
- Failures / Errors: **0**
- Test execution time: **1.26 seconds**
- Overall engine code coverage: **94%**

| Test Module | Tests | Status | Coverage |
| :--- | :---: | :---: | :---: |
| `test_application_api.py` | 24 | PASSED | 96% |
| `test_attribution.py` | 3 | PASSED | 95% |
| `test_custom_model_builder.py` | 6 | PASSED | 97% |
| `test_data_diagnostics.py` | 6 | PASSED | 90% |
| `test_simulation_uncertainty.py` | 5 | PASSED | 95% |
| `test_forecast_timing_and_backtesting.py` | 28 | PASSED | 98% |
| `test_statistical_calibration.py` | 32 | PASSED | 95% |
| `test_validation_edge_cases.py` | 23 | PASSED | 97% |
| `test_plugins.py` | 25 | PASSED | 95% |
| `test_benchmarks.py` | 30 | PASSED | 95% |
| `test_studio.py` | 28 | PASSED | 91% |
| `test_core_engine.py` | 192 | PASSED | 96% |

### 4.2 Browser End-to-End Verification
The browser subagent performed direct interaction verification of all new and existing laboratories on `http://127.0.0.1:8000/`:
- **Data Lab:** Successfully computed return moments (Skewness: -0.1979, Excess Kurtosis: -0.6353, Jarque-Bera: 0.8172, $p$-value: 0.6646) and rendered the return histogram.
- **Risk Attribution:** Recalculated portfolio risk and rendered the 10-asset Euler Marginal Risk Allocation table, confirming component risk percentages sum to 100.0% with zero Euler discrepancy.
- **Simulation & Uncertainty:** Executed forward Monte Carlo fan envelope simulation and computed non-parametric bootstrap uncertainty (95% CI: ₹13,448 to ₹24,809).
- **Assumption Registry:** Rendered complete catalog cards for Gaussian, Historical, EWMA, Student-$t$, and Cornish-Fisher models.
- **Model Builder:** Confirmed default registered plugins and successfully validated dynamic custom model registration.
- **Walk-Forward Backtesting:** Executed rolling backtest showing calibrated Kupiec POF and Christoffersen independence test acceptance.

Browser session recording artifact: `fragilityshield_expanded_labs_1792867631269.webp`.

---

## 5. Scope Boundaries & Compliance

1. **No External Infrastructure Creep:** Maintained strict in-process, self-contained architecture. No live broker integrations (Upstox), cloud databases, or background web workers were introduced.
2. **Quantitative Conventions Preserved:** Maintained $L = -R$ loss convention, Acerbi & Tasche ES coherence, and Kupiec/Christoffersen backtesting standards.
3. **Stopping Rule Respected:** Lab expansion is complete. Phase 10 has not been initiated.
