# FragilityShield — Phase 9: Issue Review Report
## Build the Interactive Risk, Scenario, Fragility & Model Benchmarking Application

**Date:** 2026-10-24  
**Auditor / Reviewer:** Combined Principal Software Architect, Senior Quantitative Risk Researcher, and Application Integration Engineer  
**Baseline Starting Commit:** `b066cf3cb004be59c1e194fece63737cb2cfbebe`  
**Referenced Deliverables:** `backend/app.py`, `frontend/index.html`, `frontend/style.css`, `frontend/app.js`, `backend/tests/test_application_api.py`

---

## 1. Executive Summary & Application Mandate

Phase 9 transforms FragilityShield from a headless Python quantitative engine into an interactive, assumption-aware portfolio risk, scenario analysis, and model benchmarking laboratory.

The core mandate is:
> **It does not merely calculate risk. It helps users investigate how risk estimates change when the assumptions behind them change.**

The application connects the browser interface directly to the genuine `fragility_engine` backend across 8 core laboratory areas:
1. **Overview:** Portfolio valuation, sector breakdown, baseline risk KPIs, latest scenario impact, and model ranking highlights.
2. **Portfolio Lab:** Portfolio creation, JSON/CSV loaders, HHI concentration analysis (decimal and points), sector allocations, and asset allocation visualization.
3. **Risk Analysis:** Historical Volatility, Value-at-Risk (95% & 99%), Expected Shortfall (CVaR), and Maximum Drawdown with educational methodology explanation panels and synthetic equity curve SVG chart.
4. **Scenario Lab:** Instantaneous factor and sector shocks (e.g. Banking -20%, IT -10%), with exact P&L reconciliation and waterfall decomposition.
5. **Fragility Lab (Central Differentiator):** Assumption sensitivity attacks on lookback windows, volatility estimators (Sample vs EWMA), transaction friction drag, confidence levels, and liquidation shocks, accompanied by sensitivity tornado rankings.
6. **Model Benchmarking:** Comparative multi-model evaluations (`parametric_gaussian`, `historical_simulation`, `ewma`) with directional ranking interpretations and prominent disclaimers ("A lower estimated VaR is not automatically a better risk model").
7. **VaR Backtesting:** Walk-forward rolling evaluation with realized loss vs VaR breach timelines, observed breach rates, Kupiec POF unconditional coverage test, and Christoffersen independence and conditional coverage tests.
8. **Experiments & Reports:** Experiment catalog, cryptographic SHA-256 reproducibility manifests, and formatted Markdown/JSON/CSV report exports.

---

## 2. Architecture Decision Record (ADR)

| Decision Item | Chosen Approach | Rejected Alternative | Rationale |
| :--- | :--- | :--- | :--- |
| **Backend Framework** | **Starlette (1.3.1) + Uvicorn (0.40.0)** | Flask / Django / FastAPI full stack | Starlette and Uvicorn were already installed in `.venv`. Starlette provides high-performance, asynchronous REST endpoints, native static file serving, and clean request validation without introducing extraneous third-party dependencies or competing ORMs. |
| **Frontend Architecture** | **Vanilla HTML5 + Modern CSS3 + Vanilla ES6 JavaScript (Single-Page App)** | React / Next.js / Vue / Vite | The repository is a quantitative research project. A self-contained, dependency-free frontend with pure SVG chart generators eliminates Node.js/npm toolchain bloat, guarantees instant local startup, and ensures long-term reproducibility without build-step fragility. |
| **Quantitative Engine Boundary** | **Strict Separation via REST API** | Client-side math recalculation | All financial calculations (VaR, ES, HHI, EWMA, Kupiec, Christoffersen, P&L) run strictly inside `fragility_engine`. The UI never calculates risk formulas independently, preserving mathematical integrity and auditability. |
| **Persistence Boundary** | **Local File Catalog (`data/experiments/`)** | SQLite / PostgreSQL / Cloud Storage | Local JSON catalog matches Phase 6 & Phase 7 design, avoiding external daemon requirements and credential exposure. |

---

## 3. Issues Identified and Resolved During Phase 9

| Issue ID | Affected Component | Severity | Root Cause | Fix / Resolution | Regression Test |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **ISSUE-9-01** | `app.py` (`api_health`, `api_list_benchmark_models`) | **High** | `PluginRegistry.list_plugins()` returns a list of `PluginMetadata` instances directly, rather than wrapped objects. Accessing `p.metadata.plugin_id` raised `AttributeError: 'PluginMetadata' object has no attribute 'metadata'`. | Updated endpoints to access `p.plugin_id`, `p.name`, `p.plugin_version`, `p.capabilities`, and `p.description` directly on `p`. Removed reference to non-existent `p.author` attribute. | `test_api_health`, `test_api_list_benchmark_models` |
| **ISSUE-9-02** | `app.py` (`api_studio_catalog`) | **High** | `LocalExperimentCatalog` requires `catalog_dir` as a mandatory constructor parameter. Calling `LocalExperimentCatalog()` raised `TypeError`. Additionally, `catalog.list_reports()` returns a list of dictionaries, so calling `r.to_dict()` failed. | Instantiated `catalog = LocalExperimentCatalog(CATALOG_DIR)` and serialized `reports` directly as `JSONResponse({"reports": reports})`. | `test_api_studio_catalog_and_experiment` |
| **ISSUE-9-03** | `app.py` (`api_calculate_risk`) | **High** | `calculate_risk_report()` calculates standard 95% and 99% metrics and does not accept `confidence_level` as a keyword argument. Passing `confidence_level` raised `TypeError`. Furthermore, the report drawdown attribute is `report.drawdown` (not `report.max_drawdown`). | Called `calculate_risk_report(arr, annualization_factor=..., ddof=...)` and computed custom confidence levels via `calculate_historical_var()` and `calculate_expected_shortfall()`. Updated drawdown access to `report.drawdown`. | `test_api_calculate_risk_defaults`, `test_api_calculate_risk_custom_confidence` |
| **ISSUE-9-04** | `app.py` (`api_load_sample_portfolio`) | **Medium** | Path traversal vulnerability if arbitrary filenames with `../` were passed to sample portfolio loader. | Implemented `sanitize_filename()` which enforces `os.path.basename` and rejects any filename containing `..`, `/`, or `\`. | `test_api_load_sample_portfolio_path_traversal_rejection` |
| **ISSUE-9-05** | `app.py` (`api_calculate_concentration`) | **Medium** | `PortfolioConcentrationReport` does not have a `warnings` attribute. Calling `conc.warnings` raised `AttributeError`. | Derived concentration warnings dynamically based on regulatory HHI thresholds (`conc.asset_hhi_points > 2500` or `conc.sector_hhi_points > 2500`). | `test_api_calculate_concentration` |
| **ISSUE-9-06** | `frontend/app.js` | **Medium** | Property name discrepancies (`hhi_asset_points` vs `asset_hhi_points`, `annualized_volatility` vs `volatility_annualized`) caused `.toFixed()` on undefined when switching portfolios. | Standardized attribute destructuring in `renderOverview`, `renderPortfolioLab`, and `renderRiskLab` with nullish coalescing operators (`asset_hhi_points ?? hhi_asset_points ?? 0`). | Manual UI verification + browser subagent inspection |

---

## 4. Financial & Quantitative Integrity Safeguards

1. **Loss Convention Consistency:**
   All VaR and Expected Shortfall calculations presented in the UI adhere strictly to the canonical positive loss convention ($L = -R$). A VaR of 0.024 is presented as a 2.4% maximum expected loss, not a positive return.
2. **In-Sample vs Out-of-Sample Separation:**
   The UI explicitly distinguishes descriptive, in-sample risk metrics (shown in Risk Analysis and Model Benchmarking) from genuine out-of-sample walk-forward forecasts (shown in VaR Backtesting).
3. **Statistical Humility and Disclaimer Banners:**
   The UI clearly states:
   - "A lower estimated VaR is not automatically a better risk model."
   - "Stressed valuations represent static sensitivity models and are NOT predictive forecasts of future market movements."
   - "Failure to reject the statistical null hypothesis does not prove that a model is calibrated or investment-safe."
4. **Assumption Sensitivity Exposing:**
   The Fragility Lab provides a sensitivity tornado ranking that quantitatively demonstrates to the user how a simple change in estimation window (e.g., 20 days vs 60 days) or volatility estimator (sample vs EWMA) can shift VaR by over 30%, exposing the dangerous illusion of false precision in static risk numbers.
