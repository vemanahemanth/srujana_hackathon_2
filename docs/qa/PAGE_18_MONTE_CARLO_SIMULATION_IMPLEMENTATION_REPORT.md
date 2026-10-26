# QA REPORT — FRAGILITYSHIELD PAGE 18: MONTE CARLO SIMULATION LAB

**Route:** `/labs/monte-carlo`  
**Status:** **VERIFIED**  
**Date:** 2026-10-25  
**Component:** `frontend/src/components/pages/MonteCarloSimulationLab.tsx`  
**Backend Engine:** `backend/fragility_engine/monte_carlo_engine.py`  
**Test Suite:** `backend/tests/test_page_18_monte_carlo.py` (5/5 passed)

---

## 1. Executive Summary

Page 18 (Monte Carlo Simulation Lab) introduces path-dependent stochastic projection capabilities to FragilityShield. It models portfolio values and returns across four stochastic generation processes: Parametric Gaussian (Geometric Brownian Motion), Fat-Tailed Student-t ($\nu$ degrees of freedom), Non-parametric empirical return resampling (bootstrap), and 2-State Markov Regime-Switching. All simulations strictly enforce bit-for-bit seed reproducibility and compute Monte Carlo standard errors.

---

## 2. Implemented Capabilities & Entry Points

| Capability | Technical Description | Source Entry Point |
|---|---|---|
| **Stochastic Model Families** | Parametric Gaussian, Student-t (with user-configurable degrees of freedom), Non-parametric historical bootstrap, and 2-State Markov regime switching. | [`backend/fragility_engine/monte_carlo_engine.py:run_monte_carlo_simulation`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/monte_carlo_engine.py) |
| **Path-Dependent Risk Metrics** | Computes Value at Risk (VaR 95/99%), Expected Shortfall (CVaR 95%), Probability of Loss, and Path Drawdown Breach Probability. | [`backend/fragility_engine/monte_carlo_engine.py:run_monte_carlo_simulation`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/monte_carlo_engine.py) |
| **Convergence Diagnostics** | Tracks running mean and running 95% VaR across increasing path evaluations to guarantee asymptotic Monte Carlo convergence ($\sigma / \sqrt{M}$). | [`backend/fragility_engine/monte_carlo_engine.py:run_monte_carlo_simulation`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/monte_carlo_engine.py) |
| **Reproducibility & Provenance** | Strict deterministic seed locking, SHA-256 simulation digest, and calibration parameter audit. | [`backend/fragility_engine/monte_carlo_engine.py:run_monte_carlo_simulation`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/monte_carlo_engine.py) |
| **Interactive Research UI** | Shaded percentile fan chart (5th–95th band, median), terminal value histogram, convergence trace, parameter editor, and CSV trajectory export. | [`frontend/src/components/pages/MonteCarloSimulationLab.tsx`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/frontend/src/components/pages/MonteCarloSimulationLab.tsx) |

---

## 3. Endpoints & API Contract

- `POST /api/monte-carlo/run`: Accepts asset symbol, path count, horizon days, stochastic model method, random seed, and initial capital, returning full percentile bands, sample trajectories, terminal metrics, histogram bins, and convergence trace.

---

## 4. Test Verification & Actual Outcomes

Command executed:
```bash
PYTHONPATH=backend:. pytest backend/tests/test_page_18_monte_carlo.py -v
```

Output:
```
============================= test session starts ==============================
backend/tests/test_page_18_monte_carlo.py::test_page_18_monte_carlo_models PASSED [ 20%]
backend/tests/test_page_18_monte_carlo.py::test_page_18_api_endpoint PASSED [ 40%]
backend/tests/test_page_18_monte_carlo.py::test_page_18_seed_reproducibility PASSED [ 60%]
backend/tests/test_page_18_monte_carlo.py::test_page_18_percentile_monotonicity PASSED [ 80%]
backend/tests/test_page_18_monte_carlo.py::test_page_18_student_t_fat_tails PASSED [100%]
========================= 5 passed, 1 warning in 0.82s =========================
```

---

## 5. Traceability Matrix

1. **Path-Dependent Analysis**: Full equity trajectories modeled across daily time steps without lookahead.
2. **Seed Reproducibility**: Exact same random seed produces identical terminal metrics and percentile bands.
3. **Monotonicity**: Strict ordering $p5 \le p25 \le p50 \le p75 \le p95$ enforced at all time steps.
4. **Data Realism**: Calibrates drift and volatility from genuine Upstox historical candles.
