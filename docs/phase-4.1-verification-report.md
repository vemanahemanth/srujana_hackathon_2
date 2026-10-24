# FragilityShield — Phase 4.1 Verification Report

**Date:** 2026-10-24  
**Auditor / Reviewer:** Senior Quantitative Researcher & Code Reviewer  
**Scope:** Mathematical correctness audit, test coverage measurement, edge-case validation, independent HHI verification, Git baseline resolution, and regression protection.

---

## 1. Executive Summary

Phase 4.1 conducted an exhaustive audit of the existing FragilityShield calculation engine across all modules:
- Installed `coverage` and `pytest-cov` in the development environment and measured **91% total test coverage** (695 statements, 49 missed, 274 branches).
- Independently recomputed the Herfindahl-Hirschman Index (HHI) for the illustrative ₹10 Lakh NSE portfolio: confirmed **Asset HHI = 0.1106 (1106.0 points)** and **Sector HHI = 0.1950 (1950.0 points)** with exact mathematical precision.
- Discovered and fixed a scenario P&L reconciliation edge case when holdings lack explicit sector assignments (defaulting to `"Unclassified"`).
- Resolved the untracked Git baseline by configuring local repository author identity, verifying `.gitignore` exclusions, and creating the clean root commit `a954ce3`.
- Re-verified Expected Shortfall (Acerbi & Tasche 2002 fractional tail weighting) and Maximum Drawdown (recovery durations, tied peaks/troughs, partial rebound rejection).
- Executed the full automated regression suite: **180 tests passing in 0.36 seconds**.

---

## 2. Actual Test Coverage Measurement

### Tooling Status & Setup
- `coverage 7.17.0` and `pytest-cov 7.1.0` were installed into `.venv` as development-only dependencies without modifying production runtime requirements.

### Exact Execution Command
```bash
python -m pytest backend/tests/ --cov=fragility_engine --cov-report=term-missing --cov-branch
```

### Coverage Report Table
| Module | Statements | Missed | Branches | Branch Partials | Statement Coverage |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `backend/fragility_engine/__init__.py` | 8 | 0 | 0 | 0 | **100%** |
| `backend/fragility_engine/returns.py` | 29 | 0 | 12 | 0 | **100%** |
| `backend/fragility_engine/scenarios.py` | 153 | 5 | 60 | 5 | **95%** |
| `backend/fragility_engine/models.py` | 111 | 4 | 38 | 4 | **95%** |
| `backend/fragility_engine/concentration.py` | 60 | 3 | 22 | 3 | **93%** |
| `backend/fragility_engine/risk.py` | 173 | 14 | 56 | 6 | **91%** |
| `backend/fragility_engine/portfolio_loader.py` | 161 | 23 | 86 | 16 | **83%** |
| **TOTAL** | **695** | **49** | **274** | **34** | **91%** |

### Uncovered Branches Analysis
- `portfolio_loader.py`: Uncovered lines represent OS-level file error fallbacks (e.g. invalid file descriptors or permissions errors during string path resolution). All primary parsing paths, validation checks, CSV row errors, and malformed inputs are covered.
- `risk.py`: Uncovered lines represent defensive type assertions for invalid non-sequence inputs in internal helpers.
- `scenarios.py`: Uncovered branches correspond to secondary assertions for lethal non-finite numeric combinations.

---

## 3. Independent HHI Re-Verification

### Portfolio Fixture Audited: `data/sample_portfolios/nse_10l.json`
- **Total Portfolio Market Value:** ₹10,00,000.00 exactly ($1,000,000.00$)
- **Holdings and Weights Table:**

| Asset Identifier | Economic Sector | Quantity | Price (₹) | Market Value (₹) | Market Weight ($w_i$) | Squared Weight ($w_i^2$) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| `NSE:HDFCBANK` | Banking | 100.0 | 1,600.00 | 160,000.00 | 0.1600 | 0.025600 |
| `NSE:ICICIBANK` | Banking | 80.0 | 1,000.00 | 80,000.00 | 0.0800 | 0.006400 |
| `NSE:SBIN` | Banking | 100.0 | 600.00 | 60,000.00 | 0.0600 | 0.003600 |
| `NSE:INFY` | Information Technology | 80.0 | 1,500.00 | 120,000.00 | 0.1200 | 0.014400 |
| `NSE:TCS` | Information Technology | 20.0 | 4,000.00 | 80,000.00 | 0.0800 | 0.006400 |
| `NSE:RELIANCE` | Energy | 50.0 | 3,000.00 | 150,000.00 | 0.1500 | 0.022500 |
| `NSE:ITC` | FMCG | 200.0 | 450.00 | 90,000.00 | 0.0900 | 0.008100 |
| `NSE:HINDUNILVR` | FMCG | 25.0 | 2,400.00 | 60,000.00 | 0.0600 | 0.003600 |
| `NSE:SUNPHARMA` | Healthcare | 80.0 | 1,250.00 | 100,000.00 | 0.1000 | 0.010000 |
| `NSE:LT` | Industrials | 25.0 | 4,000.00 | 100,000.00 | 0.1000 | 0.010000 |
| **TOTAL** | — | — | — | **₹1,000,000.00** | **1.0000** | **0.110600** |

$$\text{Asset HHI}_{\text{decimal}} = \sum_{i=1}^{10} w_i^2 = 0.11060000$$
$$\text{Asset HHI}_{\text{points}} = 0.1106 \times 10,000 = \mathbf{1106.0 \text{ points}}$$

### Sector Allocation & Concentration Table:
| Economic Sector | Constituent Assets | Aggregate Market Value (₹) | Sector Weight ($s_j$) | Squared Sector Weight ($s_j^2$) |
| :--- | :--- | :---: | :---: | :---: |
| **Banking** | HDFCBANK, ICICIBANK, SBIN | 300,000.00 | 0.3000 | 0.090000 |
| **Information Technology** | INFY, TCS | 200,000.00 | 0.2000 | 0.040000 |
| **Energy** | RELIANCE | 150,000.00 | 0.1500 | 0.022500 |
| **FMCG** | ITC, HINDUNILVR | 150,000.00 | 0.1500 | 0.022500 |
| **Healthcare** | SUNPHARMA | 100,000.00 | 0.1000 | 0.010000 |
| **Industrials** | LT | 100,000.00 | 0.1000 | 0.010000 |
| **TOTAL** | **10 Assets** | **₹1,000,000.00** | **1.0000** | **0.195000** |

$$\text{Sector HHI}_{\text{decimal}} = \sum_{j=1}^6 s_j^2 = 0.0900 + 0.0400 + 0.0225 + 0.0225 + 0.0100 + 0.0100 = 0.19500000$$
$$\text{Sector HHI}_{\text{points}} = 0.1950 \times 10,000 = \mathbf{1950.0 \text{ points}}$$

**Conclusion:** The reported values in the Phase 2 report (Asset HHI: 0.1106 / 1106 pts; Sector HHI: 0.1950 / 1950 pts) are **100% mathematically exact and verified against the actual portfolio fixtures**.

---

## 4. Edge-Case Validation & Defect Fixes

1. **Defect Identified:** In `backend/fragility_engine/scenarios.py`, when a holding has `sector=None` or blank, it was omitted from `unique_sectors`. This caused the portfolio P&L reconciliation check `portfolio_pnl == sum(sector_pnls)` to fail.
   - **Fix:** Handled missing or blank sectors consistently by grouping them into an `"Unclassified"` sector bucket, matching the behavior of `concentration.py`.
2. **Added 31 Dedicated Edge-Case Tests in `backend/tests/test_validation_edge_cases.py`:**
   - Unsized and non-numeric inputs for returns and equity curves.
   - Flat prices yielding zero returns.
   - Unnormalized weights automatic normalization ($[2.0, 2.0] \rightarrow [0.5, 0.5]$).
   - Single-asset HHI ($1.0 = 10,000\text{ pts}$) and equal-weight spectrum ($N=2, 4, 5, 10, 20, 50, 100$).
   - JSON and CSV loading from `io.TextIOBase` streams.
   - Rejection of malformed JSON structures, invalid holding dictionary types, and missing holding fields.
   - CSV export to string and `TextIOBase` streams.
   - Serialization verification (`to_dict()`) across `MetricResult`, `ConcentrationAnalysis`, `RiskMetricsReport`, `DrawdownResult`, `ScenarioDefinition`, and `ScenarioResult`.
   - Extreme floating-point values ($10^{16}$ and $10^{-8}$).

---

## 5. Git Baseline Resolution

- **Status:** **Resolved Cleanly.**
- **Local Identity Configured:**
  ```text
  user.name = Vemana Hemanth Babu
  user.email = vemanahemanthbabu@users.noreply.github.com
  ```
- **Ignore Rules Verified:** Checked `.gitignore` to ensure `.venv/`, `__pycache__/`, `.pytest_cache/`, `.coverage`, `.env`, and private files are excluded. Small, synthetic sample fixtures (`nse_10l.json`, `nse_10l.csv`) are safely tracked.
- **Root Commit Created:**
  ```text
  commit a954ce37b98859f86e8f5f4bb08ea0f933e0fa7a (HEAD -> main)
  Author: Vemana Hemanth Babu <vemanahemanthbabu@users.noreply.github.com>
  Date:   Sat Oct 24 21:36:10 2026 +0530

      feat: FragilityShield Phase 1-4 baseline with Scenario Lab and issue fixes
  ```

---

## 6. Expected Shortfall & Maximum Drawdown Verification

### Expected Shortfall (Acerbi & Tasche 2002)
- Re-tested with discrete ordered losses $L_{(1)} \le \dots \le L_{(N)}$.
- For tail weight $w = N(1 - \alpha)$ and $k = \lfloor w \rfloor$:
  $$\text{ES}_\alpha = \frac{1}{w} \left( \sum_{j=0}^{k-1} L_{(N-j)} + (w - k) L_{(N-k)} \right)$$
- Verified that for fractional boundaries (e.g. $N=10, \alpha=0.90 \implies w=1.0$; $\alpha=0.95 \implies w=0.5$), the fractional tail weighting guarantees exact integration of the upper tail probability mass.
- Coherence $\text{ES}_\alpha \ge \text{VaR}_\alpha$ strictly holds.

### Maximum Drawdown
- Verified that partial rebounds are not classified as full recoveries (`recovery_index = None`, `recovery_duration = None`, `is_recovered = False`).
- Verified that flat peaks select the latest peak before fall, and equal troughs deterministically select the first trough.

---

## 7. Regression Suite Summary Before Phase 5

```text
============================= test session starts ==============================
backend/tests/test_engine_foundation.py:     52 passed
backend/tests/test_portfolio_lab.py:         29 passed
backend/tests/test_risk_engine.py:           38 passed
backend/tests/test_scenario_engine.py:       30 passed
backend/tests/test_validation_edge_cases.py: 31 passed

============================= 180 passed in 0.36s ==============================
Statement Coverage: 91% (695 statements, 49 missed, 274 branches)
```

All Phase 4.1 verification criteria are satisfied. The repository is mathematically sound, cleanly committed, and fully prepared for Phase 5 (Fragility Lab).
