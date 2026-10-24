# FragilityShield — Phase 5: Issue Review Report

**Date:** 2026-10-24  
**Auditor / Reviewer:** Senior Quantitative Researcher & Code Reviewer  
**Scope:** Comprehensive review of Phase 4.1 carried-forward issues, verification of mathematical edge cases, test coverage tooling, and Phase 5 Fragility Lab validation.

---

## 1. Carried-Forward Issue Audit & Status Matrix

| Issue ID | Domain / Area | Previous Hypothesis / Symptom | Audit Finding & Mathematical Evidence | Final Status |
| :--- | :--- | :--- | :--- | :--- |
| **ISSUE-4.1-A** | **Expected Shortfall & VaR Tail Consistency** | Potential finite-sample distortion and tie inconsistency from naive boolean thresholding. | Fixed and verified. Implemented discrete coherent **Acerbi & Tasche (2002)** estimator with fractional tail weighting. Tested with heavy ties and small fractional boundaries ($w = N(1-\alpha)$). | **Resolved & Verified** |
| **ISSUE-4.1-B** | **Maximum Drawdown Recovery & Ties** | Partial rebounds incorrectly classified as recoveries; flat peak and tied trough ambiguity. | Formally documented and regression-tested. Partial rebound retains `is_recovered=False` and `recovery_duration=None`. Peak selection tracks latest peak before descent. | **Resolved & Verified** |
| **ISSUE-4.1-C** | **Test Coverage Measurement** | Coverage tooling previously missing from active virtualenv. | Installed `coverage 7.17.0` and `pytest-cov 7.1.0` into `.venv`. Measured actual total coverage: **92% statement coverage** (935 statements, 54 missed, 350 branches) across 212 tests. | **Resolved & Verified** |
| **ISSUE-4.1-D** | **Independent HHI Recomputation** | Check whether Phase 2 reported values (0.1106 / 1106 pts asset, 0.1950 / 1950 pts sector) were accurate. | Independently recomputed on exact `nse_10l.json` holding weights: Asset HHI = $\sum w_i^2 = 0.11060000$ (1106.0 pts); Sector HHI = $\sum s_j^2 = 0.19500000$ (1950.0 pts). Exactly confirmed. | **Resolved & Verified** |
| **ISSUE-4.1-E** | **Git Baseline & Ignore Rules** | Untracked repository files with no baseline commit; unconfigured author identity. | Configured local author identity (`Vemana Hemanth Babu`), verified `.gitignore`, and established initial clean commit `a954ce3` on `main`. | **Resolved & Verified** |
| **ISSUE-4.1-F** | **Unclassified Sector Scenario Reconciliation** | Holdings lacking explicit sector tags caused `sum(sector_pnl) != portfolio_pnl` during scenario stress tests. | Defaulted unassigned/blank sectors to `"Unclassified"`, ensuring 100% mathematical P&L reconciliation even on incomplete sector metadata. | **Resolved & Verified** |

---

## 2. Phase 5 Fragility Lab Issues & Design Constraints

### 1. Multivariate Return Requirements vs. Static Snapshots
- **Issue:** The portfolio domain (`models.py`) represents a static snapshot of holdings, prices, and quantities. It does not contain time-series price histories for constituent assets.
- **Resolution:**
  - Designed `run_correlation_perturbation` to explicitly require a synchronized 2D multivariate return matrix ($\mathbb{R}^{T \times K}$).
  - Enforced defensive type and dimension validation: if a caller supplies a 1D array or static portfolio without return histories, the engine raises an explicit `ValueError`:
    `"Correlation perturbation requires a 2D synchronized multivariate return matrix (shape T x K). A static portfolio snapshot has no multivariate return history."`
  - Under no circumstances does the engine fabricate synthetic cross-asset return histories.

### 2. Transaction Cost and Trade History Reconstruction
- **Issue:** Static portfolio holdings do not provide trade execution logs, limit orders, or historical rebalancing timestamps.
- **Resolution:**
  - Implemented two mathematically precise, transparent cost models:
    1. **Periodic Return Friction Shock (`run_return_friction_perturbation`)**: Evaluates return series drag by deducting constant basis points $r_t' = r_t - \frac{c}{10000}$ to measure how trading friction expands VaR, ES, and drawdown.
    2. **Instantaneous Liquidation / Rebalancing Shock (`calculate_portfolio_liquidation_shock`)**: Evaluates turnover cost drag on portfolio valuation: $\text{Cost} = \text{MV} \times \tau \times \frac{c}{10000}$.
  - Full dynamic historical turnover reconstruction is explicitly marked as **deferred** until an order/trade history domain model is introduced in future phases.

### 3. Alternative Volatility Estimators (EWMA)
- **Issue:** Comparing standard sample deviation with EWMA requires consistent units and annualization.
- **Resolution:**
  - Implemented RiskMetrics EWMA ($\lambda = 0.94$ default) with initial variance $\sigma_0^2 = \frac{1}{N}\sum r_i^2$.
  - Enforced identical annualization factor ($\sqrt{252}$) across both baseline and perturbed estimates.
  - Validated parameter boundaries ($\lambda \in (0, 1)$ strictly).

### 4. Zero-Baseline Relative Changes
- **Issue:** When a baseline risk metric is zero (e.g. constant returns producing $\sigma_0 = 0.0$ or flat curve yielding $\text{MDD}_0 = 0.0$), relative change $\frac{M_1 - M_0}{|M_0|}$ would produce division by zero, yielding $\pm\infty$ or NaN.
- **Resolution:**
  - Defined `compute_changes` to return `None` (JSON `null`) for `relative_change` whenever $|M_0| \le 10^{-15}$.
  - Guaranteed that no experiment result ever emits NaN or infinity.

---

## 3. Verification & Regression Protection

- Total automated tests: **212 tests passed**.
- Total measured test coverage: **92% across all modules**.
- Backward compatibility: 100% of Phase 1 foundation, Phase 2 portfolio lab, Phase 3 risk calculation, Phase 4 scenario lab, and Phase 4.1 verification tests pass without modification.
