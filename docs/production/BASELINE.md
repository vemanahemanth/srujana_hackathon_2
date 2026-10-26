# FragilityShield — Production Baseline (Phase 0)

**Baseline Date:** 2026-10-25  
**Active Branch:** `main`  
**Base Commit:** `74ef3fe7ad6f9ef681e8eab66cf0c080438637f7`  
**Python Runtime:** Python 3.14.6 (macOS Darwin 25.3.0 arm64)  
**Test Runner:** pytest 9.0.3 with plugins `anyio-4.12.1`, `Faker-40.37.0`, `asyncio-1.4.0`

---

## 1. Baseline Test Execution State

- **Command Executed:** `PYTHONPATH=.:backend pytest -v`
- **Collection Total:** **585 test items** across 33 test files in `backend/tests/`.
- **Pass/Fail Breakdown:**
  - Passed: **585**
  - Failed: **0**
  - Errors: **0**
  - Skipped: **0**
  - Warnings: **1** (`StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead.`)
- **Execution Duration:** 1.94s.
- **Exit Code:** `0` (Success).

---

## 2. Git Working-Tree & Modification Baseline

### Preserved Pre-Existing Working-Tree Files:
The working tree contains existing modifications in:
- `README.md`
- `backend/app.py`
- `backend/fragility_engine/__init__.py`
- `backend/fragility_engine/fragility.py`
- `backend/fragility_engine/models.py`
- `backend/fragility_engine/plugins.py`
- `backend/fragility_engine/risk.py`
- `backend/fragility_engine/scenarios.py`
- `backend/tests/test_application_api.py`
- `frontend/app.js` (Preserved — zero modification authorized)
- `frontend/index.html` (Preserved — zero modification authorized)
- `frontend/style.css` (Preserved — zero modification authorized)

All untracked backend modules, tests, catalog directories, and audit documentation are strictly preserved.

---

## 3. Secret Management & Git Hygiene

- **Git Tracking Check:** `.env` is uncommitted and excluded by line 52 of `.gitignore`.
- **Git History Inspection:** `git log --oneline -- .env` confirmed zero commits containing `.env`.
- **Example Template:** `.env.example` provides non-sensitive template keys without secrets (`UPSTOX_API_KEY=`, `UPSTOX_API_SECRET=`).
- **Token Masking:** `UpstoxConfig.mask_token()` ensures tokens are never emitted raw in API responses or logs (`token_masked: "eyJ0...-nmU"`).

---

## 4. Application Startup, Configuration & Lifespan

- **Entry Point:** `backend/app.py:create_application()` building a Starlette ASGI instance.
- **Startup Events:** Local dataset and project catalog initialization (`data/catalog/`, `data/experiments/`).
- **Shutdown Events:** Clean resource release, memory cache cleanup, threadpool termination.
- **Port Binding:** Defaults to `127.0.0.1:8000`.
- **Static Assets:** Serves `frontend/` at `/` for single-page application interface.

---

## 5. Quantitative Engine Structure

Core package: `backend/fragility_engine/`:
- `models.py`: Holding, Portfolio domain models, JSON/CSV loaders.
- `risk.py`: Volatility, Historical VaR, Parametric VaR, Cornish-Fisher VaR, coherent Expected Shortfall (Acerbi & Tasche), Maximum Drawdown.
- `attribution.py`: Euler risk decomposition, Marginal VaR, Component VaR.
- `scenarios.py`: Static sector/asset shocks, historical crisis replays, reverse-stress Euler loss solver.
- `fragility.py`: 5 assumption attack suites, sensitivity rankings, composite fragility index.
- `validation.py`: Model manifests, reference benchmark oracles, parameter boundary checks.
- `backtesting.py`: Rolling walk-forward evaluation, Kupiec POF test, Christoffersen independence test.
- `benchmarks.py`: Multi-model tournament and tail quantile accuracy ranking.
- `data_diagnostics.py`: OHLCV bar physics, outlier detection (z-score, IQR winsorization), Kolmogorov-Smirnov drift.
- `simulation.py`: Geometric Brownian Motion Monte Carlo and stationary block bootstrap resampling.
- `assumptions.py`: Normality, i.i.d., stationarity, and fat-tail mathematical precondition audits.
- `allocation.py`: Constrained minimum-variance quadratic programming (SciPy SLSQP), turnover calculation.
- `ml.py`: Chronological train/test split (zero forward leakage), regression, classification, forecasting metrics, adversarial noise.
- `plugins.py`: Model and attack plugin registry, interface conformance suite, host execution security gate.
- `projects.py`, `reproducibility.py`: Cryptographic SHA-256 manifests, catalog persistence, multi-format export.
- `upstox.py`, `market_data.py`: Upstox V3 Market Data client (read-only quotes, LTP, daily/minute historical candles).
- `data_provenance.py`: Anti-spoofing provenance tracking (`REAL_DATA`, `USER_UPLOADED_DATA`, `SYNTHETIC_TEST_DATA`, `MIXED_DATA`).
- `cli.py`, `sdk.py`: Command-line interface and Python SDK.
