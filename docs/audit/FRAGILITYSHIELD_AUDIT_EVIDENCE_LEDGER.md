# FRAGILITYSHIELD — SECOND-PASS FORENSIC EVIDENCE LEDGER
**Repository:** `/Users/vemanahemanthbabu/srujana_hackathon_2`  
**Audit Baseline Commit:** `74ef3fe` (`docs(phase-9): record final commit hash in completion report`) on branch `main`  
**Audit Execution Date:** 2026-10-26 | **Auditor Protocol:** Strictly Read-Only (Zero Code/State Modifications)  
**Verification Tooling:** Python 3.14.6, Node v20.19.1, Pytest 8.x, Vite 6.4.5, Starlette TestClient  

---

## 1. BASELINE GIT INTEGRITY & ENVIRONMENT AUDIT

### 1.1 Git Status Verification
- **Initial `git status --short`:** Verified at 03:07:25 UTC+05:30.
- **Final `git status --short`:** Verified at 03:10:45 UTC+05:30.
- **Working Tree Delta:** **ZERO CHANGES.** The repository's tracked source code remains in its exact original state. All pre-existing user modifications and untracked files were strictly preserved.

### 1.2 Execution Commands & Observed Exit Codes
| Step / Check | Exact Shell Command Executed | Working Directory | Observed Exit Code | Key Result |
| :--- | :--- | :--- | :--- | :--- |
| **Git Baseline** | `git log -n 1 --oneline && git status --short` | Repo Root | `0` | Clean working tree; HEAD at `74ef3fe`. |
| **Python Environment**| `python3 --version && .venv/bin/python --version` | Repo Root | `0` | Python 3.14.6 in `.venv`. |
| **Backend Test Suite**| `PYTHONPATH=. .venv/bin/python -m pytest backend/tests -v` | Repo Root | `0` | **848 passed, 0 failed, 28 skipped** (9.41s). |
| **Frontend Typecheck**| `cd frontend && npm run typecheck` (`tsc --noEmit`) | `frontend/` | `0` | Clean typecheck; 0 TypeScript errors. |
| **Frontend Build** | `cd frontend && npm run build` (`vite build`) | `frontend/` | `0` | Output: `index-D25sPq2S.js` (1,662 kB raw / 411 kB gzip). |
| **Endpoint Probe** | TestClient POST probe to `/api/allocation/optimize` | In-process Python | `0` | HTTP 200; weights returned with falsified provenance. |

---

## 2. FORENSIC EVIDENCE LEDGER — AUDIT CLAIMS VALIDATION

| Finding ID | Original Audit Claim | Verdict | Severity | Exact File & Line References | Evidence Observed & Tested | Existing Test Coverage | Remaining Uncertainty | Recommended Next Action |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **CRIT-01** | Allocation endpoint synthesizes covariance with fixed seed ($r=0.35$) and falsifies provenance as `user_uploaded`. | **CONFIRMED** | **CRITICAL** | `backend/app.py:2962-2988` | Probing `POST /api/allocation/optimize` without covariance returns weights computed from `seed=42`, $r=0.35$, with `'is_synthetic': False` and `'data_source_mode': 'USER_UPLOADED_DATA'`. | `test_all_11_labs_comprehensive.py:440` passes without covariance and asserts HTTP 200, actively masking this fallback. | None. Fully reproduced via live in-process TestClient call. | Remove lines 2966-2970. Enforce HTTP 422 if covariance is missing and cannot be computed from empirical return series. |
| **CRIT-02** | Default local persistence resides in RAM (`MemoryTenantRepository`), causing all user portfolios to vanish on server restart. | **CONFIRMED** | **CRITICAL** | `backend/fragility_engine/database.py:1222-1245` | `get_current_database_mode()` returns `LOCAL_RESEARCH`, resolving to `MemoryTenantRepository`. Portfolios and transactions exist only in Python dicts (`self._portfolios`). | Covered by memory repo tests; PostgreSQL RLS integration tests (28) skipped in local mode. | None. Restarting the backend process clears all RAM state. (Note: experiments and market caches persist to disk). | Implement `SqliteTenantRepository` for `LOCAL_RESEARCH` mode backed by `data/fragilityshield.db`. |
| **CRIT-03** | Kupiec POF Likelihood Ratio test sets `lr_stat = 0.0` and passes when breaches are 0, falsely certifying small samples ($N=4$). | **CONFIRMED** | **CRITICAL** | `backend/app.py:3642-3651` | `if breaches > 0 and breaches < n_test: ... else: lr_stat = 0.0; kupiec_pass = True`. Analytical check proves $N=100, x=0$ has true $	ext{LR}=10.26 > 3.841$ (REJECT), and $N=100, x=100$ also enters `else:` and passes! | Tested with arbitrary thresholds in `test_all_11_labs_comprehensive.py`. | None. Mathematically verified across 8 analytical boundary cases. | Implement standard Kupiec formula with $0 \ln 0 = 0$ convention. Flag sample sizes with expected breaches $N p < 5$ as `INCONCLUSIVE`. |
| **MATH-01** | Quantile VaR threshold evaluated using RMSE against mean loss produces guaranteed negative skill. | **CONFIRMED** | **HIGH** | `backend/app.py:3660-3666` | `rmse_model = sqrt(mean((losses - var_thresh)^2))`, `rmse_naive = sqrt(mean((losses - mean_loss)^2))`. Because mean minimizes squared error, $	ext{RMSE}_{	ext{model}} \ge 	ext{RMSE}_{	ext{naive}}$ always, forcing skill $\le 0\%$. | Covered by API validation tests asserting presence of `relative_skill_pct`. | None. Proven by Cauchy-Schwarz and quadratic minimization properties. | Replace squared error loss on VaR with tick/pinball check loss: $L_lpha(y, q) = (y - q)(lpha - \mathbb{I}(y < q))$. |
| **FRONT-01** | Frontend hardcodes `+` sign and `PASSED` badge on relative skill, rendering negative skill as green `+-92.5% PASSED`. | **CONFIRMED** | **HIGH** | `frontend/src/components/pages/ModelValidationLab.tsx:325, 412, 456, 498` | Direct inspection of JSX template: `+${validationReport.benchmarks.relative_skill_pct}%` and `'PASSED'` hardcoded in table array. | Frontend typecheck passes because string concatenation is valid TypeScript. | None. Visual verification confirmed in source code. | Render dynamic sign: `{val > 0 ? '+' : ''}{val}%` and style negative values with red font and `FAILED` badge. |
| **FRONT-02** | Frontend router is `wouter` in `App.tsx` (not `routes.tsx`). 1,600+ lines of dead monolithic mock code remain in `App.tsx`. | **CONFIRMED** | **MEDIUM** | `frontend/src/App.tsx:1100-2795` | `routes.tsx` does not exist (`FileNotFoundError`). Functions `function Overview(`, `function Market(`, etc. exist with 0 JSX call sites. | `npm run build` succeeds but emits bundle size warning (>500 kB). | None. Bundle size measured at 1,662 kB raw (411 kB gzip). | Purge legacy uncalled functions from `App.tsx` and implement `React.lazy()` route splitting. |
| **SDK-01** | Python SDK class is named `FragilityShieldClient`. | **CONTRADICTED BY EVIDENCE** | **LOW** | `backend/fragility_engine/sdk.py:1088` | The exported class is `Client` (not `FragilityShieldClient`). It contains 16 sub-managers and operates both in-process and via HTTP. | `backend/tests/test_sdk_and_cli.py` imports `from fragility_engine.sdk import Client`. | Prior audit claim was inaccurate regarding class naming. | Update documentation to refer to `from fragility_engine.sdk import Client`. |
| **COLAB-01**| External Colab connectivity works out-of-the-box. | **CONTRADICTED BY EVIDENCE** | **HIGH** | `backend/app.py:5810` & `examples/external_experiment_client.py` | Server binds to loopback `127.0.0.1:8000`. No automated tunnel (ngrok, cloudflared) or public reverse proxy exists. | Tested only locally via loopback in `test_sprint9_external_connectivity.py`. | None. Loopback cannot be reached from external cloud containers. | Provide documented tunneling configuration or cloud gateway endpoint for Colab. |
| **TEST-01** | Test suite has 1 failure in `test_cli_new_commands`. | **DISPROVEN AS ARTIFACT** | **INFORMATIONAL**| `backend/tests/test_new_api_and_cli.py:159` | When run from repository root (`cd srujana_hackathon_2`), `test_cli_new_commands` passes. The prior failure occurred because Cwd was set to `srujana_hackathon_1`. | Total suite: **848 passed, 0 failed, 28 skipped**. | None. Exactly 100% test pass rate for configured local environment. | Ensure test execution documentation specifies running from repository root. |

---

## 3. CONFIRMED DEFECTS TABLE

| Issue ID | Module & Line Reference | Nature of Defect | Quantitative / Operational Impact |
| :--- | :--- | :--- | :--- |
| **CRIT-01** | `backend/app.py:2966-2988` | Silently fabricates synthetic covariance ($r=0.35$, seed 42) and marks provenance as `user_uploaded`. | Users receive optimized asset weights based on fake correlations while the system claims data was user-supplied. |
| **CRIT-02** | `backend/fragility_engine/database.py:1222` | In `LOCAL_RESEARCH` mode, `MemoryTenantRepository` stores portfolios in RAM. | All custom portfolios, holdings, and transactions are permanently lost when backend reboots. |
| **CRIT-03** | `backend/app.py:3649-3651` | Kupiec Likelihood Ratio hardcodes `lr_stat = 0.0` and `kupiec_pass = True` when `breaches == 0` or `breaches == n_test`. | Fails to reject over-conservative models ($N=100, x=0$), falsely passes tiny samples ($N=4$), and passes catastrophic models ($N=100, x=100$). |
| **MATH-01** | `backend/app.py:3661-3666` | Evaluates VaR quantile threshold using RMSE against mean return loss. | Mathematical category error. Guarantees negative relative skill because mean always minimizes RMSE. |
| **FRONT-01** | `frontend/src/components/pages/ModelValidationLab.tsx:325` | Hardcodes `+` sign and `PASSED` badge on relative skill. | A model with $-92.5\%$ skill displays in green as `+-92.5% PASSED`, deceiving researchers. |
| **FRONT-02** | `frontend/src/App.tsx:1100-2795` | 1,600+ lines of uncalled monolithic prototype functions generating sine-wave mock charts. | Bloats frontend bundle to 1.66 MB raw; causes confusion about whether pages are real or mock. |

---

## 4. PARTIALLY CONFIRMED & SUSPECTED CLAIMS TABLE

| Claim / Topic | Original Severity | Current Status | Detailed Evidence & Limitations |
| :--- | :--- | :--- | :--- |
| **Copula Positive Semi-Definiteness** | Medium | **Partially Confirmed** | `copula_engine.py` fits Archimedean copulas pairwise. For portfolios with $>5$ assets, reconstructed correlation matrices can have negative eigenvalues unless projected via Higham's algorithm. |
| **Pickle Model Deserialization Security** | Medium | **Partially Confirmed** | `model_sandbox.py:145` inspects pickle opcodes against a whitelist. While effective against basic payloads, opcode whitelists without OS container isolation cannot guarantee 100% exploit prevention. |
| **Indian Market STT Frictions** | Low | **Partially Confirmed** | Backtester friction model supports percentage fees and slippage, but does not distinguish delivery STT (0.1%) from intraday sell STT (0.025%), slightly overstating net intraday returns. |
| **React 19 Dispatcher Null Crash** | Medium | **Suspected (Environment Flaky)** | The error `null is not an object (evaluating 'resolveDispatcher().useRef')` was observed during browser automation in WebKit/Safari when stale `.vite/deps` cache evaluated duplicate React instances. A clean Vite build does not exhibit this crash. |

---

## 5. CLAIMS CONTRADICTED BY EVIDENCE TABLE

| Claim | Source of Claim | Evidence Refuting the Claim |
| :--- | :--- | :--- |
| **"Frontend router is defined in `routes.tsx`"** | Prior Audit Report | File `frontend/src/routes.tsx` does not exist (`FileNotFoundError`). Routing is managed in `frontend/src/App.tsx` via `wouter`. |
| **"Python SDK class is `FragilityShieldClient`"** | Prior Audit Report | `backend/fragility_engine/sdk.py:1088` defines `class Client:`. `FragilityShieldClient` does not exist anywhere in the codebase. |
| **"Backend has 92 registered endpoints"** | Prior Audit Report | Starlette inspection reveals exactly **142 registered routes** (56 GET/HEAD, 78 POST, 7 DELETE, 1 Static). |
| **"Test suite has 1 failed test"** | Prior Audit Report | When pytest is run with Cwd at the repository root, **848 tests pass, 0 fail, and 28 are skipped**. The single failure was an execution Cwd artifact. |
| **"Risk attribution fakes provenance"** | Prior Audit Report | In `backend/app.py:1868`, missing return data is explicitly tagged as `DataProvenance.synthetic_demo(reason=...)`. The provenance falsification is isolated to **allocation optimization** (`app.py:2985`). |

---

## 6. QUANTITATIVE METHODOLOGY AUDIT

### 6.1 Kupiec POF Likelihood Ratio Verification
Standard Kupiec (1995) unconditional coverage test statistic:
$$	ext{LR}_{	ext{POF}} = 2 \left[ x \ln\left(rac{x}{N p}ight) + (N - x) \ln\left(rac{N - x}{N (1 - p)}ight) ight] \sim \chi^2(1)$$
Using the standard continuous limit $\lim_{u 	o 0} u \ln u = 0$:

#### Analytical Test Cases vs Backend Behavior
| Test Case Parameters | Standard Kupiec $	ext{LR}$ | Standard Critical Value ($lpha=0.05$) | True Decision | `backend/app.py` Output | `backend/app.py` Decision | Mathematical Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **$N=100, x=0, p=0.05$** | **$10.2587$** | $3.841$ | **REJECT (Fail)** | `lr_stat = 0.0` | **PASS (True)** | **DEFECT (Fails to catch over-conservatism)** |
| **$N=100, x=5, p=0.05$** | **$0.0000$** | $3.841$ | **PASS** | `lr_stat = 0.0` | **PASS (True)** | Correct |
| **$N=100, x=10, p=0.05$**| **$4.1308$** | $3.841$ | **REJECT (Fail)** | `lr_stat = 4.1308` | **FAIL (False)**| Correct |
| **$N=100, x=100, p=0.05$**| **$599.1465$** | $3.841$ | **REJECT (Fail)** | `lr_stat = 0.0` | **PASS (True)** | **CRITICAL DEFECT (Passes 100% breach catastrophe)** |
| **$N=4, x=0, p=0.05$** | **$0.4103$** | $3.841$ | **INCONCLUSIVE** | `lr_stat = 0.0` | **PASS (True)** | **DEFECT (Zero statistical power)** |
| **$N=252, x=0, p=0.05$** | **$25.8518$** | $3.841$ | **REJECT (Fail)** | `lr_stat = 0.0` | **PASS (True)** | **DEFECT (Fails to reject zero breaches in 1 yr)** |
| **$N=252, x=12, p=0.05$**| **$0.0305$** | $3.841$ | **PASS** | `lr_stat = 0.0305` | **PASS (True)** | Correct |
| **$N=252, x=25, p=0.05$**| **$10.1126$** | $3.841$ | **REJECT (Fail)** | `lr_stat = 10.1126`| **FAIL (False)**| Correct |

### 6.2 Sample Size Justification & Power Analysis
- **Why $N \ge 252$ in Basel Banking Supervision:** Under $p=0.05$, expected breaches $\mathbb{E}[x] = 252 	imes 0.05 = 12.6$.
- **Why $N < 40$ is Statistically Inadequate:** For $N=4$, $P(X=0) = (0.95)^4 = 81.5\%$. Even if $x=1$ breach occurs, $	ext{LR} = 1.800 < 3.841$. The test **cannot reject the null under any outcome ($x=0$ or $x=1$) at the 5% significance level**.
- **Regulatory Reconciliation:** Rather than hardcoding $N \ge 252$ across all asset horizons, the system must:
  1. Emit `INCONCLUSIVE_SAMPLE_SIZE` whenever $\mathbb{E}[x] = N p < 5.0$.
  2. Implement the exact two-sided binomial test (Clopper-Pearson interval) for small samples where asymptotic $\chi^2(1)$ distribution fails.

### 6.3 VaR Quantile Scoring vs RMSE
Evaluating a quantile forecast $\hat{q}_lpha$ against sample returns $y_t$ using RMSE:
$$	ext{RMSE}(\hat{q}_lpha) = \sqrt{rac{1}{N} \sum_{t=1}^N (y_t - \hat{q}_lpha)^2}$$
is mathematically improper because squared error is strictly minimized by the conditional mean $\mathbb{E}[y]$, not the quantile.
The strictly consistent scoring function for quantile forecasts is the **Tick Loss (Pinball Loss)**:
$$S(q; y, lpha) = (lpha - \mathbb{I}(y < q)) (y - q)$$
Relative skill must be computed as:
$$	ext{Skill}_{	ext{pinball}} = 1 - rac{\sum S(\hat{q}_{	ext{model}}; y_t, lpha)}{\sum S(\hat{q}_{	ext{baseline}}; y_t, lpha)}$$

---

## 7. CONNECTIVITY AUDIT: SDK VS DASHBOARD VS COLAB

```
+-----------------------------------------------------------------------------------------------+
|                                  CONNECTIVITY REALITY MATRIX                                  |
+-----------------------------------------------------------------------------------------------+
| Environment Mode         | Transport Layer     | Ingestion Endpoint       | Actual Verification |
+--------------------------+---------------------+--------------------------+---------------------+
| 1. Local Python SDK      | Direct in-process   | Local ProjectCatalog     | VERIFIED WORKING    |
|    (No server running)   | engine calls        | (data/catalog/, data/)   | (848 tests pass)    |
+--------------------------+---------------------+--------------------------+---------------------+
| 2. Local Python Script   | HTTP JSON           | POST http://127.0.0.1    | VERIFIED WORKING    |
|    (Local server active) | (urllib / requests) | :8000/api/ingest/runs    | (test_sprint9 pass) |
+--------------------------+---------------------+--------------------------+---------------------+
| 3. Local Dashboard UI    | REST Fetch          | GET /api/experiments/runs| VERIFIED WORKING    |
|    (Browser on host)     | (frontend/api.ts)   | (aggregates disk & RAM)  | (Displays all runs) |
+--------------------------+---------------------+--------------------------+---------------------+
| 4. Deployed Endpoint     | HTTPS REST          | Configurable Base URL    | PARTIAL             |
|    (Public server/cloud) | (Reverse proxy)     | (Requires env setup)     | (No prod config)    |
+--------------------------+---------------------+--------------------------+---------------------+
| 5. Independent Colab     | Public Internet     | Unreachable on loopback  | NOT WORKING         |
|    (Google Cloud runtime)| Egress              | (127.0.0.1:8000 fails)   | (No tunnel bridge)  |
+--------------------------+---------------------+--------------------------+---------------------+
```

### Key Connectivity Findings
1. **Local SDK is Standalone:** A Python user can `from fragility_engine.sdk import Client` and run all calculations, risk decompositions, and backtests without starting the web server.
2. **Dashboard Ingestion is Real:** Submitting an experiment via `client.external.submit_run` writes to `data/experiments/external_{run_id}.json` and appears immediately in the Unified Experiment Registry.
3. **Colab Notebooks Cannot Reach Loopback:** Google Colab executes in Google Cloud VMs; sending requests to `http://127.0.0.1:8000` attempts to connect to the Colab container itself, failing immediately with `ConnectionRefusedError`. A public tunnel (ngrok, Cloudflare Tunnel) or deployed host is required.
4. **Metric Verification is Conditional:**
   - With raw prediction pairs ($N \ge 2$): Backend independently recomputes RMSE, MAE, and directional accuracy, writing `verification_status: "INDEPENDENTLY_VERIFIED"`.
   - Without raw predictions: Backend records client-supplied metrics directly without recalculation.

---

## 8. PRIORITIZED REMEDIATION ROADMAP

Based solely on confirmed findings, the recommended remediation order is:

1. **PHASE 1 (Immediate Quantitative Fix): Eliminate Synthetic Covariance Fabrication (`CRIT-01`)**
   - In `backend/app.py:2966-2970`, remove synthetic matrix generation.
   - Enforce HTTP 422 if covariance is missing and cannot be computed from empirical return data.
   - Accurately label data provenance on all endpoints.

2. **PHASE 2 (Immediate Quantitative Fix): Correct Kupiec Likelihood Ratio Boundary Handling (`CRIT-03`)**
   - In `backend/app.py:3642-3651`, compute true likelihood ratio using standard limiting convention $0 \ln 0 = 0$.
   - Flag $x=0$ and $x=n$ with true test statistics.
   - Introduce `INCONCLUSIVE` verdict when expected breaches $N p < 5.0$.

3. **PHASE 3 (Immediate UI Fix): Correct Model Skill Calculation and Display (`MATH-01`, `FRONT-01`)**
   - In `backend/app.py:3666`, evaluate quantile thresholds using tick/pinball loss instead of squared error.
   - In `ModelValidationLab.tsx`, remove hardcoded `+` sign and hardcoded `PASSED` table cell.
   - Render negative skill with prominent red styling and an underperformance badge.

4. **PHASE 4 (Data Durability Fix): Implement Local SQLite Persistence (`CRIT-02`)**
   - Implement `SqliteTenantRepository` in `backend/fragility_engine/database.py` for `LOCAL_RESEARCH` mode.
   - Ensure user-created portfolios, holdings, and transactions persist to `data/fragilityshield.db` across server reboots.

5. **PHASE 5 (Frontend Architecture & Performance): Clean Up `App.tsx` and Enable Code Splitting (`FRONT-02`)**
   - Purge the 1,600 lines of dead monolithic mock functions from `App.tsx`.
   - Implement `React.lazy()` for all 27 lab pages to reduce the 1.66 MB bundle into $<300	ext{ kB}$ chunks.

---
**END OF EVIDENCE LEDGER**
