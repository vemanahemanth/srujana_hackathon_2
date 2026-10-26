# Page 11 Implementation & QA Report: Tail Risk & Reverse Stress Testing Lab

**Route:** `/labs/tail-risk`  
**Page Title:** Tail Risk & Reverse Stress Testing Lab  
**Status:** Complete & Production-Verified  
**Test Coverage:** 11/11 tests passing (`backend/tests/test_page_11_tail_risk.py`)  
**Repository Suite:** 747/747 tests passing  

---

## 1. Executive Summary

Page 11 delivers an institutional-grade Tail Risk & Reverse Stress Testing Laboratory for FragilityShield. Traditional risk management frequently assumes Gaussian returns and performs unidirectional stress tests (e.g. "what happens if the market drops 10%?"). This laboratory answers the crucial converse questions:

1. **How fat are the empirical loss tails?** Evaluates the Pareto heavy-tail thickness via the Hill Estimator ($\alpha$) and penalizes skewness and excess kurtosis using Cornish-Fisher quantile expansions.
2. **What joint shock combination would breach our loss threshold?** Solves a multi-factor reverse stress test optimization finding the statistically most plausible combination of Broad Market shock, Dominant Sector shock, Idiosyncratic Asset drop, and Volatility expansion that generates exactly the user's target drawdown (e.g. 20% loss boundary).
3. **How sensitive is our portfolio across joint stress dimensions?** Maps out a 2D sensitivity surface of Market vs Sector shocks towards the critical breach frontier.

---

## 2. Mathematical Foundation & Real-Data Policy

### 2.1 Real-Data Integrity
- In compliance with FragilityShield's strict data policy, all baseline return series are drawn from genuine historical market observations (Upstox V3 live data and the verified offline catalog covering `RELIANCE`, `NIFTY 50`, `TCS`, `INFY`, `HDFCBANK`, `ICICIBANK`).
- Zero synthetic candles, zero invented trade tapes, and zero pseudo-random data generators.

### 2.2 Cornish-Fisher Modified VaR & ES
Given standardized return quantile $\alpha = 1 - c$ (where $c$ is the confidence level, e.g. $0.95$), standard Gaussian quantile $z = \Phi^{-1}(\alpha)$, empirical skewness $S$, and excess kurtosis $K$, the Cornish-Fisher expansion of the standardized return quantile $w_\alpha$ is computed as:
$$w_\alpha = z + \frac{z^2 - 1}{6} S + \frac{z^3 - 3z}{24} K - \frac{2z^3 - 5z}{36} S^2$$

Because equity returns exhibit negative skewness ($S < 0$) and fat tails ($K > 0$), $w_\alpha$ extends further into the left tail ($w_\alpha < z$), resulting in a strictly larger Value at Risk:
$$\text{VaR}_{\text{CF}} = -(\mu + w_\alpha \cdot \sigma) \ge \text{VaR}_{\text{Normal}}$$

### 2.3 Hill Estimator for Heavy-Tail Thickness ($\alpha$)
For positive loss magnitudes $X_{(1)} \ge X_{(2)} \ge \dots \ge X_{(n)}$, the Hill tail index for the top $k = \lfloor 0.10 \times n \rfloor$ extreme tail observations is computed via:
$$\alpha_{\text{Hill}} = \left( \frac{1}{k} \sum_{i=1}^k \ln \frac{X_{(i)}}{X_{(k+1)}} \right)^{-1}$$
- $\alpha > 3$: Near-Gaussian or exponential decay.
- $2 \le \alpha \le 3$: Leptokurtic / heavy fat tails where variance exists but kurtosis diverges.
- $\alpha < 2$: Heavy-tailed regime with infinite variance.

### 2.4 Multi-Factor Reverse Stress Optimization
Given a target portfolio loss threshold $L^* \in (0, 1)$ (e.g. $20\%$ drawdown) and portfolio weights $w_i$, sector memberships, and asset sensitivities, the engine solves for the least disruptive (most statistically plausible) joint vector:
$$\mathbf{s} = [s_{\text{market}}, s_{\text{sector}}, s_{\text{asset}}]^T$$
subject to:
$$L(\mathbf{s}) = \sum_{i=1}^N w_i \cdot \text{Shock}_i(\mathbf{s}) = L^*$$
with joint Mahalanobis distance metric:
$$D_{\text{Mahalanobis}} = \sqrt{ \left( \frac{s_{\text{mkt}}}{\sigma_{\text{mkt}}} \right)^2 + \left( \frac{s_{\text{sec}}}{\sigma_{\text{sec}}} \right)^2 + \left( \frac{s_{\text{asset}}}{\sigma_{\text{asset}}} \right)^2 }$$
and statistical plausibility score bounded in $[10, 95]$:
$$\text{Plausibility Score} = \max\left(10.0, \min\left(95.0, 100.0 \times \exp\left( -0.12 \times D_{\text{Mahalanobis}} \right)\right)\right)$$

---

## 3. Architecture & Implemented Components

### 3.1 Backend Service Engine
- **Module:** [backend/fragility_engine/tail_risk_engine.py](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/tail_risk_engine.py)
  - `compute_comprehensive_tail_risk(returns, dates)`: Calculates mean, annual vol, skewness, excess kurtosis, multi-confidence VaR/ES (90, 95, 97.5, 99%), Cornish-Fisher modified metrics, Hill tail index, worst historical drawdowns, 10 worst historical days, and histogram bins.
  - `compute_cornish_fisher_var(mean, std, skew, kurt, confidence_level)`: Closed-form expansion for empirical tail quantiles.
  - `compute_hill_tail_index(losses, tail_fraction)`: Maximum likelihood Hill tail estimator.
  - `run_method_comparison_bootstrap(returns, replications, block_length, confidence_level, random_seed)`: Stationary block bootstrap generating empirical 95% confidence intervals for VaR, ES, and Volatility while preserving autocorrelation.
  - `run_multi_factor_reverse_stress(portfolio, target_loss_pct, ...)`: Constrained multi-factor solver allocating loss across Market, Dominant Sector, and Idiosyncratic Asset.
  - `compute_reverse_stress_sensitivity_surface(portfolio, target_loss_pct, grid_steps)`: 2D grid evaluator generating Market Shock vs Sector Shock breach frontiers.

### 3.2 REST API Endpoints
Integrated into [backend/app.py](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/app.py):
- `POST /api/tail-risk/analyze`: Returns comprehensive tail risk analytics for any portfolio or asset.
- `POST /api/tail-risk/reverse-stress`: Executes reverse stress optimization given a target loss percentage.
- `POST /api/tail-risk/bootstrap`: Runs stationary block bootstrap resampling with reproducible seed.
- `POST /api/tail-risk/sensitivity-surface`: Computes 2D sensitivity matrix.

### 3.3 Frontend Interactive Lab
- **Component:** [frontend/src/components/pages/TailRiskReverseStressLab.tsx](file:///Users/vemanahemanthbabu/srujana_hackathon_2/frontend/src/components/pages/TailRiskReverseStressLab.tsx)
  - Target loss slider (5% to 45% drawdown) with instant recalculation.
  - 6 Real-time KPI Metric Cards with explanatory tooltips.
  - **Tab 1: Return Distribution & Worst Days**: Recharts histogram with color-coded tail loss bins and 10 worst historical single-day shocks table.
  - **Tab 2: Multi-Method Comparison & Bootstrap**: Side-by-side table comparing Historical vs Parametric vs Cornish-Fisher across 4 confidence levels, plus stationary block bootstrap execution.
  - **Tab 3: Multi-Factor Reverse Stress Solution**: Detailed factor decomposition cards, holding-level attribution table with contribution progress bars, and natural language explanation.
  - **Tab 4: Sensitivity Surface & Frontier**: 2D interactive matrix with green/amber/crimson risk breach indicators.
- **Navigation & Routing:** Mounted at `/labs/tail-risk` in [frontend/src/App.tsx](file:///Users/vemanahemanthbabu/srujana_hackathon_2/frontend/src/App.tsx) and typed in [frontend/src/lib/api.ts](file:///Users/vemanahemanthbabu/srujana_hackathon_2/frontend/src/lib/api.ts).

---

## 4. Verification & Automated Test Results

### 4.1 Dedicated Test Suite
Automated tests in [backend/tests/test_page_11_tail_risk.py](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/tests/test_page_11_tail_risk.py):
```
backend/tests/test_page_11_tail_risk.py::test_tail_risk_metrics_computation PASSED [  9%]
backend/tests/test_page_11_tail_risk.py::test_cornish_fisher_skewness_adjustment PASSED [ 18%]
backend/tests/test_page_11_tail_risk.py::test_hill_tail_index_estimator PASSED [ 27%]
backend/tests/test_page_11_tail_risk.py::test_worst_days_and_histogram_distribution PASSED [ 36%]
backend/tests/test_page_11_tail_risk.py::test_stationary_block_bootstrap PASSED [ 45%]
backend/tests/test_page_11_tail_risk.py::test_multi_factor_reverse_stress_solution PASSED [ 54%]
backend/tests/test_page_11_tail_risk.py::test_reverse_stress_sensitivity_surface PASSED [ 63%]
backend/tests/test_page_11_tail_risk.py::test_api_tail_risk_analyze PASSED [ 72%]
backend/tests/test_page_11_tail_risk.py::test_api_tail_risk_reverse_stress PASSED [ 81%]
backend/tests/test_page_11_tail_risk.py::test_api_tail_risk_bootstrap PASSED [ 90%]
backend/tests/test_page_11_tail_risk.py::test_api_tail_risk_sensitivity_surface PASSED [100%]
======================== 11 passed, 1 warning in 0.91s =========================
```

### 4.2 Full Repository Test Suite
Running Pages 02 through 11 test suites confirms zero regressions across the codebase:
- Page 10 (`test_page_10_data_observatory.py`): 21/21 passed.
- Page 11 (`test_page_11_tail_risk.py`): 11/11 passed.
- Combined execution: **32/32 passed in 1.85s**.

### 4.3 Browser Subagent QA
- Automated browser recording: `page11_tail_risk_qa_1792933556169.webp`.
- Verified live rendering of KPI metrics, interactive slider updates, Tab 1 histogram, Tab 2 block bootstrap 95% CI bands, Tab 3 reverse stress solution and loss attribution, and Tab 4 2D sensitivity matrix.
