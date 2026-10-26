# QA REPORT — FRAGILITYSHIELD PAGE 17: MODEL TOURNAMENT & BENCHMARKING

**Route:** `/labs/tournament`  
**Status:** **VERIFIED**  
**Date:** 2026-10-25  
**Component:** `frontend/src/components/pages/ModelTournamentBenchmarking.tsx`  
**Backend Engine:** `backend/fragility_engine/tournament_engine.py`  
**Test Suite:** `backend/tests/test_page_17_tournament.py` (6/6 passed)

---

## 1. Executive Summary

Page 17 (Model Tournament & Benchmarking) provides a fair, auditable evaluation framework for quantitative trading strategies and risk models. Unlike standard return-only leaderboards, it enforces identical observation windows across all candidates, applies uniform transaction friction (statutory exchange fees, STT, and slippage), evaluates subperiod stability, and calculates the Bailey & López de Prado (2014) Deflated Sharpe Ratio (DSR) with Bonferroni multiple testing penalties.

---

## 2. Implemented Capabilities & Entry Points

| Capability | Technical Description | Source Entry Point |
|---|---|---|
| **Shared Evaluation Protocol** | Aligns all candidates to synchronous market candles, statutory NSE trading calendars, and common $T+1$ execution conventions. | [`backend/fragility_engine/tournament_engine.py:execute_tournament`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/tournament_engine.py) |
| **Deflated Sharpe Ratio (DSR)** | Bailey & López de Prado (2014) statistical adjustment correcting the maximum observed Sharpe ratio for candidate count $K$, sample length $N$, skewness, and kurtosis. | [`backend/fragility_engine/tournament_engine.py:compute_deflated_sharpe_ratio`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/tournament_engine.py) |
| **Bonferroni Adjustment** | Family-wise error rate control bounding false discovery risk in quantitative candidate selection. | [`backend/fragility_engine/tournament_engine.py:compute_deflated_sharpe_ratio`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/tournament_engine.py) |
| **Rank Stability Scoring** | Evaluates Sharpe ratio consistency across subperiod splits and flags strategies vulnerable to regime decay. | [`backend/fragility_engine/tournament_engine.py:execute_tournament`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/tournament_engine.py) |
| **Interactive Research UI** | Leaderboard with sorting and badges, Risk vs Return scatter plot, primary score ranking chart, and CSV export. | [`frontend/src/components/pages/ModelTournamentBenchmarking.tsx`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/frontend/src/components/pages/ModelTournamentBenchmarking.tsx) |

---

## 3. Endpoints & API Contract

- `GET /api/tournaments/candidates`: Lists verified model and strategy candidates eligible for tournament entry.
- `POST /api/tournaments/run`: Executes tournament evaluation under specified protocol parameters and returns ranked leaderboard with DSR diagnostics.

---

## 4. Test Verification & Actual Outcomes

Command executed:
```bash
PYTHONPATH=backend:. pytest backend/tests/test_page_17_tournament.py -v
```

Output:
```
============================= test session starts ==============================
backend/tests/test_page_17_tournament.py::test_page_17_deflated_sharpe_ratio PASSED [ 16%]
backend/tests/test_page_17_tournament.py::test_page_17_tournament_execution PASSED [ 33%]
backend/tests/test_page_17_tournament.py::test_page_17_api_endpoints PASSED [ 50%]
backend/tests/test_page_17_tournament.py::test_page_17_cost_sensitivity_and_rank_inversion PASSED [ 66%]
backend/tests/test_page_17_tournament.py::test_page_17_minimum_sample_rejection PASSED [ 83%]
backend/tests/test_page_17_tournament.py::test_page_17_stability_scoring PASSED [100%]
========================= 6 passed, 1 warning in 1.19s =========================
```

---

## 5. Traceability Matrix

1. **Fair Comparison**: Every candidate is evaluated on identical historical dates with identical initial capital and cost assumptions.
2. **Multiple Testing Correction**: DSR and Bonferroni adjustments prevent declaring skill from pure random mining.
3. **Reproducibility**: Generates an immutable SHA-256 fingerprint for every completed tournament run.
4. **Data Integrity**: Uses genuine Upstox market observations from the local catalog without synthetic data.
