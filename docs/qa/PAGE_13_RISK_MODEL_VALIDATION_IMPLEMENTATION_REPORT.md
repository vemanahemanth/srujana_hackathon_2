# Quality Assurance & Implementation Report: Page 13 — Risk Model Validation & Backtesting Observatory

**Page Route:** `/models/risk-validation`  
**Page Title:** Risk Model Validation & Backtesting Observatory  
**Component:** `frontend/src/components/pages/RiskModelValidationLab.tsx`  
**Backend Engine:** `backend/fragility_engine/risk_model_validation.py`  
**Test Suite:** `backend/tests/test_page_13_risk_validation.py`  
**Status:** Complete, Verified, 11/11 Passing Tests  

---

## 1. Executive Summary & Core Objective

The **Risk Model Validation & Backtesting Observatory** provides an institutional-grade laboratory for statistically evaluating whether quantitative risk model forecasts ($\text{VaR}_\alpha$, $\text{ES}_\alpha$) align with subsequently realized market outcomes. 

Rather than relying on naive backtesting or synthetic toy distributions, this engine executes a **strictly time-aware rolling backtest** enforcing zero lookahead bias ($T_{\text{train\_end}} < T_{\text{eval}}$) across genuine market observations (Upstox V3 API and verified catalog snapshots).

Every model evaluated undergoes three canonical regulatory and statistical testing batteries:
1. **Kupiec Proportion of Failures (POF) Unconditional Coverage Test** ($\chi^2(1)$).
2. **Christoffersen Markov Chain Independence & Conditional Coverage Test** ($\chi^2(1)$ and $\chi^2(2)$).
3. **McNeil-Frey Expected Shortfall Tail Residual Validation** ($t$-test on standardized exceedances).

---

## 2. Architecture & File Inventory

| Artifact / Module | File Path | Description |
|---|---|---|
| **Backend Engine** | [`backend/fragility_engine/risk_model_validation.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/risk_model_validation.py) | Statistical engines for Kupiec, Christoffersen, McNeil-Frey ES, Clopper-Pearson CI, and rolling time-aware backtesting. |
| **Starlette API Handlers** | [`backend/app.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/app.py) | REST API endpoints `/api/models/risk-validation/run` and `/api/models/risk-validation/compare`. |
| **Automated Test Suite** | [`backend/tests/test_page_13_risk_validation.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/tests/test_page_13_risk_validation.py) | 11 comprehensive unit and integration tests covering statistical fixtures, edge cases ($x=0, x=N$), and REST APIs. |
| **Frontend API Client** | [`frontend/src/lib/api.ts`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/frontend/src/lib/api.ts) | Typed API client methods `runRiskModelValidation` and `compareRiskModels`. |
| **React Component** | [`frontend/src/components/pages/RiskModelValidationLab.tsx`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/frontend/src/components/pages/RiskModelValidationLab.tsx) | Interactive UI featuring timeline charting (Recharts), statistical scorecard, multi-model comparison, and breach log. |
| **Navigation & Routing** | [`frontend/src/App.tsx`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/frontend/src/App.tsx) | Navigation menu entry under *Models & strategies* and URL routing to `/models/risk-validation`. |

---

## 3. Mathematical & Statistical Methodology

### A. Kupiec Proportion of Failures (POF) Unconditional Coverage Test
Under null hypothesis $H_0: \mathbb{E}[I_t] = p = 1 - \alpha$, the number of exceptions $x = \sum_{t=1}^N I_t$ follows a binomial distribution $B(N, p)$.
The Likelihood Ratio statistic is formulated as:
$$LR_{\text{uc}} = -2 \ln \left[ \frac{p^x (1 - p)^{N - x}}{\left(\frac{x}{N}\right)^x \left(1 - \frac{x}{N}\right)^{N - x}} \right] \sim \chi^2(1)$$

- **Boundary Edge Cases:** Handled cleanly when $x = 0$ ($LR = -2 N \ln(1 - p)$) and $x = N$ ($LR = -2 N \ln(p)$) without numerical singularity.
- **Clopper-Pearson Exact Confidence Interval:** Exact $95\%$ binomial confidence interval $[L, U]$ is computed using the Beta distribution quantiles.

### B. Christoffersen Independence & Conditional Coverage Test
Evaluates whether risk breaches cluster in time using a 1st-order Markov chain with transition probability matrix:
$$\Pi = \begin{pmatrix} 1 - \pi_{01} & \pi_{01} \\ 1 - \pi_{11} & \pi_{11} \end{pmatrix}$$
Where:
- $n_{00}$: No breach followed by no breach
- $n_{01}$: No breach followed by breach
- $n_{10}$: Breach followed by no breach
- $n_{11}$: Consecutive breach clusters (breach followed by breach)

The test statistic $LR_{\text{ind}} = -2 \ln \left[ \frac{L(\Pi_0)}{L(\Pi)} \right] \sim \chi^2(1)$ directly checks $H_0: \pi_{01} = \pi_{11}$.
The Joint Conditional Coverage statistic is:
$$LR_{\text{cc}} = LR_{\text{uc}} + LR_{\text{ind}} \sim \chi^2(2)$$

### C. McNeil-Frey Expected Shortfall Tail Residual Validation
For dates where a breach occurs ($L_t > \text{VaR}_t$), standardized excess residuals are evaluated:
$$e_t = \frac{L_t - \text{ES}_t}{\text{VaR}_t}$$
Under correct calibration, $\mathbb{E}[e_t] \le 0$. A one-sided Student's $t$-test validates whether the model systematically underestimates tail severity. If $k < 5$ breaches exist, the status is strictly flagged as `INSUFFICIENT_EVIDENCE` rather than reporting false calibration.

---

## 4. Supported Risk Model Families

| Model ID | Formulation | Characteristic |
|---|---|---|
| `historical_simulation` | $\text{VaR}_\alpha = \text{Percentile}(L, \alpha)$ | Non-parametric, fat tails captured natively from historical distribution. |
| `parametric_gaussian` | $\text{VaR}_\alpha = \mu + z_\alpha \cdot \sigma$ | Benchmark normal distribution model ($z_{0.95} = 1.64485$). |
| `cornish_fisher` | $\text{VaR}_\alpha = \mu + z_{\text{cf}} \cdot \sigma$ | Semi-parametric skewness and excess kurtosis polynomial adjustment. |
| `ewma` | $\sigma_t^2 = \lambda \sigma_{t-1}^2 + (1-\lambda) r_{t-1}^2$ | RiskMetrics exponential weighting ($\lambda = 0.94$) adapting to volatility clustering. |

---

## 5. Strict Zero-Lookahead Audit Guarantee

Every forecast point $t$ enforces the invariant:
$$T_{\text{train\_end}} < T_{\text{eval}}$$
No return, quote, or price occurring at or after date $t$ is included in the parameter estimation for the forecast of date $t$. The automated audit verifies this condition for $100\%$ of evaluation points and flags any timeline anomaly.

---

## 6. Automated Test Results

The test suite [`backend/tests/test_page_13_risk_validation.py`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/tests/test_page_13_risk_validation.py) passes 11/11 tests:

```text
backend/tests/test_page_13_risk_validation.py::test_kupiec_test_independent_fixture PASSED [  9%]
backend/tests/test_page_13_risk_validation.py::test_kupiec_boundary_edge_cases PASSED [ 18%]
backend/tests/test_page_13_risk_validation.py::test_clopper_pearson_confidence_interval PASSED [ 27%]
backend/tests/test_page_13_risk_validation.py::test_christoffersen_independence_and_conditional_coverage PASSED [ 36%]
backend/tests/test_page_13_risk_validation.py::test_expected_shortfall_validation PASSED [ 45%]
backend/tests/test_page_13_risk_validation.py::test_expected_shortfall_insufficient_sample PASSED [ 54%]
backend/tests/test_page_13_risk_validation.py::test_time_aware_risk_model_predictors PASSED [ 63%]
backend/tests/test_page_13_risk_validation.py::test_reconstructed_rolling_backtest_no_lookahead PASSED [ 72%]
backend/tests/test_page_13_risk_validation.py::test_compare_risk_models PASSED [ 81%]
backend/tests/test_page_13_risk_validation.py::test_api_models_risk_validation_run PASSED [ 90%]
backend/tests/test_page_13_risk_validation.py::test_api_models_risk_validation_compare PASSED [100%]
======================== 11 passed in 1.58s =========================
```

---

## 7. Real Data Policy Compliance

- All backtest runs utilize genuine daily OHLCV observations from the Upstox V3 Market API or the verified local catalog snapshot.
- Zero synthetic returns, artificial price paths, or fake candles are permitted or rendered.
- Deterministic SHA-256 dataset digests are generated and cryptographically tracked with every backtest run.
