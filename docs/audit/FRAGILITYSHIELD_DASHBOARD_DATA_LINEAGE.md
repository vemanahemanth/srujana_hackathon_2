# FragilityShield — Dashboard Data Lineage & Provenance Specification

**Repository:** `/Users/vemanahemanthbabu/srujana_hackathon_2`  
**Audit Standard:** Section 7 — Point-by-Point Verification of Dashboard Values  
**Evaluation Standard:** Every displayed metric must have an authoritative calculation source, scope, and test.  

---

## 1. Dashboard Integrity Policy

FragilityShield enforces the following operational rules:
1. **No Hardcoded Counts:** Dashboard badges and counts are queried live or derived from persisted records.
2. **Truthful State Transitions:** If a background calculation fails or worker crashes, the status reports `FAILED`, never `SUCCEEDED`.
3. **Strict Zero Policy:** A metric displays `0` only if zero is the mathematically calculated value. Missing, pending, or failed observations are rendered with appropriate diagnostics (`Unavailable`, `Pending`, or `N/A`).
4. **Tenant Isolation:** Operational metrics are scoped to the active tenant/workspace; records from other tenants are excluded by default.

---

## 2. Lineage Audit of Operational & Quantitative Metrics

| # | Metric / Value | Display Location | Authoritative Source | Mathematical / Operational Definition | Temporal Mode | Tenant Scope | Refresh Mechanism | Empty / Stale / Error State | Automated Test Evidence | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| 01 | **Worker Status** | Global App Footer | `GET /api/workers/status` | Active worker count and queue backlog from `BackgroundWorker` | Real-time | System / Admin | Auto-refresh on mount & button | `Offline (Unavailable)` | `test_master_functionality_repair.py` | **PASS** |
| 02 | **Jobs Processed** | Global App Footer | `GET /api/workers/status` | Monotonically increasing counter of completed worker tasks | Cumulative | System / Admin | Polled / manual refresh | `(Processed count unavailable)` | `test_master_functionality_repair.py` | **PASS** |
| 03 | **Active Portfolios Count** | Portfolio Workbench & Overview | `GET /api/portfolios` | Count of persisted user portfolios: `len(portfolios)` | Current | Active Tenant | Auto-fetch on view load | `0 Portfolios` | `test_sdk_portfolio_lifecycle` | **PASS** |
| 04 | **Registered Models Count** | Model Registry & Overview | `GET /api/models/manifests` | Number of verified registered models in catalog | Current | Active Tenant | Queried from model catalog | `0 Models Registered` | `test_project_and_model_registry.py` | **PASS** |
| 05 | **Registered Strategies Count**| Strategy Library & Overview | `GET /api/configurations/strategies` | Total custom strategies in DB: `SELECT count(*) FROM custom_strategies` | Current | Active Tenant | Queried on mount | `0 Strategies` | `test_custom_strategy_persistence_lifecycle` | **PASS** |
| 06 | **Completed Experiments** | Experiment History & Overview | `GET /api/experiments` | Number of runs with `status == "completed"` | Current | Active Tenant | Dynamic query with filter | `0 Experiments Run` | `test_backend_acceptance_workflows.py`| **PASS** |
| 07 | **Parametric VaR (95%)** | Risk Analytics Lab | `POST /api/calculate-risk` | $z_{0.95} \cdot \sigma_p \cdot \sqrt{h} \cdot \text{PortfolioValue}$ | Current Run | Active Portfolio | Computed on "Run Risk Analysis" | Amber `[ILLUSTRATIVE]` banner if sample | `test_master_functionality_repair.py` | **PASS** |
| 08 | **Historical VaR (95%)** | Risk Analytics Lab | `POST /api/calculate-risk` | Empirical 5th percentile of historical return distribution | Current Run | Active Portfolio | Computed on "Run Risk Analysis" | Amber `[ILLUSTRATIVE]` banner if sample | `test_risk_engine.py` | **PASS** |
| 09 | **Expected Shortfall (CVaR)**| Tail Risk & Risk Labs | `POST /api/tail-risk/cvar` | $\mathbb{E}[L \mid L > \text{VaR}_\alpha]$, conditional tail expectation | Current Run | Active Portfolio | Computed on run action | Formatted error if returns insufficient | `test_tail_risk.py` | **PASS** |
| 10 | **Euler Component Volatility**| Risk Attribution Lab | `POST /api/calculate-attribution`| $w_i \frac{(\Sigma w)_i}{\sigma_p}$, strictly summing to $\sigma_p$ | Current Run | Active Portfolio | Computed on "Calculate Attribution" | Red warning if $\sum \text{CompVol} \ne \sigma_p$ | `test_euler_attribution_reconciliation`| **PASS** |
| 11 | **Kupiec POF Likelihood Ratio**| Model Validation Lab | `POST /api/models/validate-var` | $LR_{\text{pof}} = -2 \ln\left[ \frac{(1-p)^{N-x} p^x}{(1 - x/N)^{N-x} (x/N)^x} \right]$ | Evaluation Window| Selected Model | Computed on validation execution | `Insufficient Observations (<250D)` | `test_master_functionality_repair.py` | **PASS** |
| 12 | **Basel Traffic Light Status**| Model Validation Lab | `POST /api/models/validate-var` | Green ($x < 5$), Amber ($5 \le x \le 9$), Red ($x \ge 10$) for 250D 99% | Evaluation Window| Selected Model | Computed on validation execution | Amber warning if sample data | `test_master_functionality_repair.py` | **PASS** |
| 13 | **Sharpe Ratio** | Strategy Backtest Lab | `POST /api/backtesting/run` | $\frac{\bar{R}_p - R_f}{\sigma_p} \cdot \sqrt{252}$ | Backtest Window | Selected Strategy| Computed on "Run Backtest" | `N/A (Zero Volatility)` | `test_custom_strategy_backtest_execution`| **PASS** |
| 14 | **Maximum Drawdown (MDD)**| Strategy Backtest Lab | `POST /api/backtesting/run` | $\max_{t} \left( \frac{\text{Peak}_t - \text{Trough}_t}{\text{Peak}_t} \right)$ | Backtest Window | Selected Strategy| Computed on "Run Backtest" | `0.0%` if monotonic positive equity | `test_custom_strategy_backtest_execution`| **PASS** |
| 15 | **Tournament Champion Badge**| Model Tournament | `POST /api/tournament/run` | Candidate maximizing Deflated Sharpe / Information Ratio | Tournament Run | Active Tenant | Computed on "Run Tournament" | `NO CANDIDATE QUALIFIED` | `test_tournament_inactive_candidate_handling`| **PASS** |
| 16 | **Monte Carlo Fan Quantiles**| Monte Carlo Simulation Lab | `POST /api/simulation/monte-carlo`| 5th, 25th, 50th, 75th, 95th percentiles of simulated trajectories | Current Run | Active Portfolio | Computed on "Run Simulation" | Stale result banner if parameters edit | `test_monte_carlo_and_bootstrap_contract`| **PASS** |
| 17 | **Dataset SHA-256 Fingerprint**| Data Observatory | `POST /api/data/diagnostics` | Cryptographic hash of normalized OHLCV CSV payload | Ingestion Time | Selected Dataset | Computed upon upload & stored | Checksum mismatch error | `test_data_diagnostics.py` | **PASS** |
| 18 | **Security / RLS Mode** | Settings & Security | `GET /api/security/status` | Active row-level security policy and JWT signing algorithm | Current | Active Tenant | Auto-fetched on view load | Red `Insecure` badge if disabled | `test_multi_tenancy_and_auth.py` | **PASS** |

---

## 3. Data Lineage Summary
- **Total Dashboard Metrics Audited:** 18
- **Authoritative & Verified [PASS]:** 18
- **Hardcoded / Simulated Numbers:** 0
- **Stale State Alerts Enforced:** Yes (Monte Carlo, Risk Analytics, Backtest Lab)