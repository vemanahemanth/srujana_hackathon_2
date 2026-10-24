# FragilityShield — Phase 5 Verification Report

**Date:** 2026-10-24  
**Auditor / Reviewer:** Principal Software Architect & Quantitative Risk Engineer  
**Scope:** Independent audit of Phase 5 Fragility Lab implementation, mathematical verification of all perturbation models, coverage re-measurement, and Git baseline verification.

---

## 1. Executive Summary

Phase 5 verification independently audited the starting repository state, executed the full regression test suite, verified test coverage tooling and numbers, and evaluated every mathematical formula in `backend/fragility_engine/fragility.py`.

Key findings:
1. **Starting State Verified:** Git branch `main` at commit `cd78d7e366ad4691e8e2b8ea3559196b0266cb67`. Working tree is 100% clean with zero uncommitted changes or untracked sensitive files.
2. **Automated Test Results:** All **212 unit tests pass in 0.29s**.
3. **Coverage Tooling Verified:** `pytest-cov 7.1.0` and `coverage 7.17.0` installed in `.venv`. Measured statement coverage is **94.2%** (881 / 935 statements), branch coverage is **88.3%** (309 / 350 branches), and overall reported pytest-cov coverage is **92%**.
4. **Mathematical Verification:** All six Fragility Lab perturbation models and ranking routines were verified against analytical formulas and hand-calculated test fixtures.
5. **HHI & Risk Estimators:** Expected Shortfall (Acerbi & Tasche 2002), Maximum Drawdown dynamics, Asset HHI (0.1106 / 1106.0 pts), and Sector HHI (0.1950 / 1950.0 pts) confirmed exact.

---

## 2. Actual Commands and Outputs

### A. Git Repository State
```bash
git status --short --branch
# Output: ## main (clean working tree)

git log --oneline -2
# Output:
# cd78d7e feat: FragilityShield Phase 5 Fragility Lab implementation and Phase 4.1 verification
# a954ce3 feat: FragilityShield Phase 1-4 baseline with Scenario Lab and issue fixes

git rev-parse HEAD
# Output: cd78d7e366ad4691e8e2b8ea3559196b0266cb67
```

### B. Automated Test Suite
```bash
.venv/bin/python -m pytest backend/tests/ -v
# Output: 212 passed in 0.29s
```

### C. Statement and Branch Coverage Measurement
```bash
.venv/bin/python -m pytest backend/tests/ --cov=fragility_engine --cov-report=term-missing --cov-branch
```

```text
Name                                           Stmts   Miss Branch BrPart  Cover   Missing
------------------------------------------------------------------------------------------
backend/fragility_engine/__init__.py               9      0      0      0   100%
backend/fragility_engine/returns.py               29      0     12      0   100%
backend/fragility_engine/fragility.py            239      5     76      7    96%   184->183, 210->212, 327, 425, 545, 757-758, 765->769
backend/fragility_engine/scenarios.py            153      5     60      5    95%   74, 244, 291, 395, 402
backend/fragility_engine/models.py               111      4     38      4    95%   107, 110, 123, 139
backend/fragility_engine/concentration.py         60      3     22      3    93%   135, 159, 163
backend/fragility_engine/risk.py                 173     14     56      6    91%   121, 125-126, 137-138, 156, 160-161, 169, 172-173, 465, 474-475, 476->479
backend/fragility_engine/portfolio_loader.py     161     23     86     16    83%   45, 48-51, 67, 85, 89, 94-95, 98, 102-103, 106, 113->123, 121, 124->129, 127, 142, 185, 188-191, 213, 319-320
------------------------------------------------------------------------------------------
TOTAL                                            935     54    350     41    92%
```

- **Statement Coverage:** 881 / 935 = 94.2%
- **Branch Coverage:** 309 / 350 = 88.3%
- **Combined Reporting Coverage:** 92%
- **Reproducibility:** Re-run yields identical percentage.

---

## 3. Mathematical Verification of Fragility Lab

### 1. Lookback Window Perturbation
- **Implementation:** `run_lookback_perturbation(returns, perturbed_window, baseline_window)`.
- **Chronological Integrity:** Uses trailing slice `arr[-perturbed_window:]`. Because observations are chronologically ordered, taking the last $W$ entries strictly uses historical data up to the cutoff without any look-ahead leakage.
- **Validation:** Rejects $W < 2$ and $W > N$ with clear `ValueError`. Raises warning when $W < 20$.
- **Baseline Equivalence:** When $W_{\text{perturbed}} = W_{\text{baseline}}$, $\Delta = 0.0$ and $\text{rel\_delta} = 0.0$ across all metrics.

### 2. Alternative Volatility Estimator (EWMA)
- **Implementation:** `calculate_ewma_volatility(returns, decay_factor, annualization_factor)` and `run_volatility_estimator_perturbation`.
- **Formulas:**
  $$\sigma_0^2 = \frac{1}{N}\sum_{i=1}^N r_i^2, \quad \sigma_t^2 = \lambda \sigma_{t-1}^2 + (1 - \lambda) r_t^2, \quad \sigma_{\text{ann}} = \sqrt{\sigma_T^2} \times \sqrt{252}$$
- **Verification:** Hand calculation with $r = [0.01, -0.02], \lambda = 0.90 \implies \sigma_{\text{daily}} = \sqrt{0.0002515} \approx 0.01585875$, $\sigma_{\text{ann}} \approx 25.176\%$. Implementation produces bitwise agreement.
- **Consistency:** Both sample standard deviation and EWMA are annualized by $\sqrt{252.0}$.

### 3. Return Friction Shock
- **Implementation:** `run_return_friction_perturbation(returns, friction_bps)`.
- **Formula:** $r_t' = r_t - \frac{\text{friction\_bps}}{10,000}$.
- **Unit Clarity:** Explicitly documented as basis points (bps). 10 bps $= 0.0010$ return drag.
- **Tail Impact:** Correctly shifts empirical loss distribution upward ($L = -R \implies L' = L + \text{drag}$), expanding both VaR and Expected Shortfall.
- **Limitation:** Documented as an analytical return drag sensitivity model, not a transaction-level order backtest.

### 4. Portfolio Liquidation Friction
- **Implementation:** `calculate_portfolio_liquidation_shock(portfolio, cost_bps, turnover_fraction)`.
- **Formula:** $\text{Cost} = \text{Total Market Value} \times \text{turnover} \times \frac{\text{cost\_bps}}{10,000}$.
- **Verification:** On ₹5,00,000 portfolio at 10 bps cost and 100% turnover, cost is exactly ₹500.00, stressed value is ₹4,99,500.00. Zero turnover yields zero cost.
- **Static Portfolio Boundary:** Explicitly disclaims historical trade logs.

### 5. Multivariate Correlation Stress
- **Implementation:** `perturb_correlation_matrix(C_0, stress_factor, target_correlation)` and `run_correlation_perturbation`.
- **Formulas:**
  $$C_{\alpha} = (1 - \alpha) C_0 + \alpha \left( (1 - \rho_{\text{target}}) I_K + \rho_{\text{target}} J_K \right)$$
  $$\Sigma_{\alpha} = D C_{\alpha} D, \quad \sigma_{\text{portfolio}} = \sqrt{w^T \Sigma_{\alpha} w} \times \sqrt{252}$$
- **Properties Preserved:**
  - Symmetry: $C_\alpha = C_\alpha^T$.
  - Unit diagonal: $C_{\alpha, ii} = 1.0$.
  - Positive semidefiniteness for $\alpha \in [0, 1]$ and $\rho_{\text{target}} \in [0, 1]$.
- **Defensive Safeguards:** Rejects 1D arrays or missing weights with clear `ValueError`.

### 6. Tail Confidence Level Shift
- **Implementation:** `run_confidence_level_perturbation(returns, 0.99, 0.95)`.
- **Conventions:** Both baseline and perturbed evaluations use positive loss convention ($L = -R$) and Acerbi & Tasche (2002) fractional tail expectation. $\text{ES} \ge \text{VaR}$ holds across both confidence levels.

### 7. Sensitivity Ranking
- **Implementation:** `rank_perturbation_sensitivities(experiments, target_metric)`.
- **Ordering:** Sorts descending by absolute impact $|\Delta|$.
- **Zero-Baseline Handling:** When $M_0 = 0.0$, relative change returns `None` (JSON `null`), preventing division by zero or NaN/Inf emission.

---

## 4. Re-Verification of Earlier Phase Calculations

1. **Expected Shortfall:** Verified against Acerbi & Tasche (2002) discrete coherent tail integration with fractional weights. Heavy boundary ties preserve exact upper tail expectation.
2. **Maximum Drawdown:** Verified that partial rebounds are not classified as recoveries (`is_recovered=False`). Peak selection during flat tops deterministically picks the latest peak before descent.
3. **Concentration Indices (HHI):**
   - $\text{Asset HHI} = 0.11060000$ (1106.0 points).
   - $\text{Sector HHI} = 0.19500000$ (1950.0 points).
   - Re-verified against `data/sample_portfolios/nse_10l.json`.

---

## 5. Stage A Readiness Decision

All Stage A verification criteria are met. The test suite passes 100%, coverage is verified at 92%, mathematical properties are proven, and the repository baseline is clean.

**Authorization Granted to Proceed with Stage B (Phase 6: Validation & Reproducibility Lab).**
