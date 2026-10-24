# FragilityShield — Phase 8: Issue Review Report
## Plugin System & Quantitative Model Benchmarking Laboratory

**Date:** 2026-10-24  
**Auditor / Reviewer:** Principal Software Architect, Quantitative Risk Engineer & Application Security Specialist  
**Baseline Git Commit:** `ec1997e`  
**Referenced Deliverables:** `backend/fragility_engine/plugins.py`, `backend/fragility_engine/benchmarks.py`, `backend/tests/test_plugin_benchmarking.py`

---

## 1. Objectives & Executive Scope

FragilityShield Phase 8 introduces a typed, verifiable model plugin architecture and an assumption-aware quantitative benchmarking laboratory.

The laboratory allows quantitative risk managers, researchers, and model validation teams to:
1. Register and inspect diverse financial and machine learning risk models under a unified interface.
2. Ensure strict input and output validation before and after execution.
3. Subject competing models to identical historical datasets and market conditions (Fair Comparison Guarantee).
4. Evaluate sensitivity to assumption perturbations (e.g., return friction, lookback window truncation, EWMA decay adjustments).
5. Generate transparent metric rankings with explicit directional preference (`lower_is_better` for loss/tail risk, `higher_is_better` for diversification/returns).
6. Export tamper-evident, reproducible benchmark artifacts across JSON, Markdown, and CSV formats.

---

## 2. Engineering & Design Challenges Addressed

| Challenge ID | Domain / Area | Technical Challenge | Engineering Resolution & Evidence | Status |
| :--- | :--- | :--- | :--- | :--- |
| **ISSUE-8-A** | **Plugin Contract & Decoupling** | External models vary widely in input structures, capabilities, and configuration options. Creating a brittle inheritance tree forces models to implement irrelevant methods. | Designed an abstract base class `ModelPlugin` with clean separation between metadata declaration (`PluginMetadata`), pre-flight validation (`validate_input`), and computation (`execute`). No internal engine details or private state are leaked. | **Resolved & Tested** |
| **ISSUE-8-B** | **Calculation Duplication Risk** | Adding built-in model plugins could duplicate VaR, ES, Volatility, or HHI calculations, introducing divergence. | Built-in adapters (`HistoricalSimulationPlugin`, `ParametricGaussianPlugin`, `EWMAVolatilityPlugin`, `PortfolioConcentrationPlugin`) directly reuse FragilityShield's core modules (`risk.py`, `fragility.py`, `concentration.py`). Zero algorithm duplication. | **Resolved & Tested** |
| **ISSUE-8-C** | **Fair Comparison Guarantee** | Comparing models computed over differing sample windows, missing dates, or conflicting loss conventions creates spurious rankings. | `BenchmarkSpecification` enforces identical dataset input, observation windows, and baseline configurations across all plugins in the benchmark. Incompatible models (e.g. Portfolio models run on Return Series) are flagged as `incompatible` and excluded from rankings rather than corrupted. | **Resolved & Tested** |
| **ISSUE-8-D** | **Directional Ranking & Tie Handling** | Naive rankers sort ascending without acknowledging whether higher or lower values indicate increased risk, or collapse all metrics into an opaque "score". | Implemented explicit `ranking_direction` parameter (`lower_is_better` vs `higher_is_better`). Tail loss metrics (VaR, ES, MDD) default to `lower_is_better`. Fractional and dense ranking detect ties within floating-point tolerance $\epsilon$. Incomparable or failed models are clearly separated into `unranked_models`. | **Resolved & Tested** |
| **ISSUE-8-E** | **Execution Safety & Honest Failure** | Buggy or adversarial third-party plugins can crash the runner, emit NaNs/Infinities, or silently fabricate zeros. | Exceptions in plugins are caught, isolated to that model entry, and marked `failed_execution`. All outputs are screened for `math.isfinite()`. Post-execution invariant checks run via `verify_experiment_invariants`. Zero-risk results are never fabricated. | **Resolved & Tested** |
| **ISSUE-8-F** | **Untrusted Plugin Containment** | Plugins running in Python processes have full access to process memory, files, and environment. | Documented explicit in-process trust boundaries. Plug-in identifiers and benchmark identifiers are validated against strict regex (`^[a-zA-Z0-9_\-\.]+$`) to prevent path traversal. External module auto-execution and dynamic package downloads are prohibited. | **Documented & Enforced** |

---

## 3. Mathematical & Financial Conventions

1. **Loss vs Return Convention:**
   FragilityShield adopts the standard loss convention $L_t = -R_t$.
   Consequently:
   - Positive VaR ($\text{VaR}_\alpha > 0$) indicates an estimated loss threshold at confidence $\alpha$.
   - A higher estimated VaR denotes a larger potential loss (higher risk).
   - Therefore, risk ranking uses `lower_is_better` to prioritize lower loss estimates.

2. **Parametric Gaussian Benchmark Model:**
   For a normal distribution $\mathcal{N}(\mu, \sigma^2)$:
   $$\text{VaR}_\alpha = -\mu + z_\alpha \sigma$$
   $$\text{ES}_\alpha = -\mu + \sigma \frac{\phi(z_\alpha)}{1 - \alpha}$$
   where $\phi$ is the standard normal probability density function, and $z_{0.95} \approx 1.64485$, $z_{0.99} \approx 2.32635$.
   This model serves as an ideal benchmark to contrast empirical fat-tailed distributions against Gaussian assumptions.

3. **RiskMetrics EWMA Volatility:**
   Calculated iteratively:
   $$\sigma_t^2 = (1 - \lambda) r_t^2 + \lambda \sigma_{t-1}^2$$
   with decay factor $\lambda \in (0, 1)$ (default $0.94$).

---

## 4. Reproducibility & Audit Provenance

Each `BenchmarkReport` contains:
- SHA-256 canonical hash of the dataset.
- SHA-256 canonical hash of mathematical configuration parameters (excluding non-functional metadata).
- SHA-256 canonical hash of model benchmark outputs and ranking positions.
- Runtime platform, Python interpreter version, and dependency versions.
- Machine-readable JSON, publication Markdown, and standard RFC 4180 CSV export methods.
