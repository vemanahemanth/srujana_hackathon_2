# Phase 14 — Security, Interface & Workflow Verification Audit

**Audit Date:** 2026-10-25  
**Repository:** `/Users/vemanahemanthbabu/srujana_hackathon_2`  
**Auditor:** Application Security Tester & API/SDK Architecture Reviewer

---

## 1. Security Architecture & Threat Analysis

### 1.1 In-Process Execution Model vs OS Isolation (Finding SEC-01)
FragilityShield's plugin architecture (`fragility_engine/plugins.py`) and Experiment Studio (`fragility_engine/studio.py`) operate entirely within the Python process on the host machine.

- **Current Implementation:**
  - The `PluginRegistry` enforces a strict policy gate: `PluginRegistry(enforce_trusted_execution=True)`.
  - Plugins with `trusted=False` cannot be executed via `registry.execute_plugin()` and immediately raise `PermissionError: Execution of untrusted plugin '...' is blocked on unisolated host runtime.`
  - The registry's `get_isolation_status()` method explicitly reports:
    ```json
    {
      "host_execution_model": "in_process",
      "os_isolation_active": false,
      "security_warning": "WARNING: Local runtime executes plugins in-process without OS container isolation. Third-party untrusted code requires an external isolated worker container."
    }
    ```
- **Auditor Assessment:**
  - **The trusted execution policy is verified and enforced in code.** Untrusted plugins cannot execute on the host.
  - **However, rejecting untrusted code is NOT operating-system isolation.**
  - If a trusted plugin contains a vulnerability or if an attacker manages to register code as trusted, the execution has full access to the host Python process, environment variables, filesystem, and network stack.
  - **Remediation Recommendation:** For multi-tenant or enterprise deployment, third-party model plugins must run in isolated worker processes sandboxed via gVisor, Firecracker microVMs, or hardened OCI containers with dropped capabilities (`CAP_DROP_ALL`) and read-only root filesystems.

### 1.2 Path Traversal & Filesystem Security
The Experiment Studio and Project Catalog write artifacts to `data/experiments/` and `data/catalog/`.
- Project and experiment identifiers are validated against strict regex whitelist:
  `^[a-zA-Z0-9_\-\.]+$`
- Any identifier containing path traversal characters (`..`, `/`, `\`) is rejected before any filesystem `open()` or `mkdir()` call.
- Verified in [test_project_and_model_registry.py](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/tests/test_project_and_model_registry.py).

### 1.3 Safe Model Specification (No Arbitrary `eval`/`exec`)
In the Custom Model Builder Lab (`fragility_engine/model_lab.py`), user models are constructed declaratively:
- Models are defined using a structured JSON specification with enumerated mathematical primitives (`rolling_mean`, `ewma`, `linear_regression`, `empirical_quantile`).
- At no point does the backend pass user strings into Python's `eval()`, `exec()`, or `pickle.loads()`.
- Verified in [test_custom_model_builder.py](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/tests/test_custom_model_builder.py).

---

## 2. Interface Parity: REST API, SDK, and CLI

FragilityShield exposes three consumer interfaces:
1. **REST API:** FastAPI application in [backend/app.py](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/app.py).
2. **Python SDK:** Typed client `FragilityShieldSDK` in [backend/fragility_engine/sdk.py](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/sdk.py).
3. **CLI:** Command-line executable `fragility` in [backend/fragility_engine/cli.py](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/cli.py).

### 2.1 Interface Parity Matrix Across Core Workflows

| Capability / Workflow | REST API Route | SDK Method | CLI Subcommand | Parity Status |
| :--- | :--- | :--- | :--- | :--- |
| **Health & Readiness** | `GET /api/health` | `sdk.health()` | `fragility status` | **FULL PARITY** |
| **Data Diagnostics** | `POST /api/diagnostics/ohlcv` | `sdk.validate_ohlcv()` | `fragility data-check` | **FULL PARITY** |
| **Market Data Generation** | `POST /api/market/generate` | `sdk.generate_market_data()` | `fragility market-gen` | **FULL PARITY** |
| **Portfolio Analysis & HHI** | `POST /api/portfolio/analyze` | `sdk.analyze_portfolio()` | `fragility portfolio-analyze` | **FULL PARITY** |
| **Risk Metrics (VaR/ES/MDD)** | `POST /api/risk/evaluate` | `sdk.evaluate_risk()` | `fragility risk` | **FULL PARITY** |
| **Risk Attribution (Euler Beta)** | `POST /api/attribution/evaluate` | `sdk.evaluate_attribution()` | `fragility attribution` | **FULL PARITY** |
| **Scenario Testing** | `POST /api/scenarios/run` | `sdk.run_scenario()` | `fragility scenario` | **FULL PARITY** |
| **Fragility Perturbations** | `POST /api/fragility/run` | `sdk.run_fragility_experiment()` | `fragility stress` | **FULL PARITY** |
| **Boundary Bisection Search** | `POST /api/fragility/boundary` | `sdk.search_boundary()` | `fragility boundary-search` | **FULL PARITY** |
| **Model Benchmarking** | `POST /api/models/benchmark` | `sdk.run_benchmark()` | `fragility benchmark` | **FULL PARITY** |
| **Statistical Calibration** | `POST /api/validation/calibrate` | `sdk.calibrate_distribution()` | `fragility calibrate` | **FULL PARITY** |
| **Portfolio Optimization** | `POST /api/allocation/optimize` | `sdk.optimize_allocation()` | `fragility optimize` | **FULL PARITY** |
| **Experiment Studio Run** | `POST /api/studio/experiment` | `sdk.run_studio_experiment()` | `fragility studio-run` | **FULL PARITY** |
| **Audit Provenance Verification** | `GET /api/reproducibility/audit` | `sdk.audit_reproducibility()` | `fragility audit` | **FULL PARITY** |

### 2.2 Error Schemas and HTTP Status Consistency
- **Validation Errors:** When input shapes are malformed or required parameters missing, FastAPI returns HTTP `422 Unprocessable Entity` with a standard RFC 7807 compliant `{"detail": [...]}` error array.
- **Invalid Domain Inputs:** When mathematically illegal parameters are supplied (e.g. confidence $\ge 1.0$, negative friction), endpoints catch `ValueError` and return HTTP `400 Bad Request` with `{"detail": "..."}`.
- **Not Found Entities:** Requesting non-existent experiment or model IDs returns HTTP `404 Not Found`.
- **Security Rejection:** Untrusted plugin execution attempts return HTTP `403 Forbidden` with a diagnostic explanation.

### 2.3 Non-Finite Numerical Handling in Serialization
- Python's default `json.dumps()` generates unquoted `NaN` and `Infinity`, which are illegal under strict JSON specification (RFC 8259).
- FastAPI and FragilityShield's serialization pipeline explicitly sanitizes floats:
  - Core calculation outputs reject non-finite inputs before processing.
  - Any intermediate non-finite calculations are converted to `null` or rejected with descriptive errors.
  - Verified in [test_application_api.py](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/tests/test_application_api.py).

---

## 3. Real Provider & Broker Integrations Disclosure

### 3.1 Upstox Integration Scope
- The repository includes `UpstoxSandboxAdapter` in [fragility_engine/market_data.py](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/market_data.py).
- **Audit Findings:**
  1. The adapter is an **in-memory synthetic simulation sandbox** for development and backtesting.
  2. No live broker accounts, real API secrets, or active WebSocket subscriptions are connected or configured in the repository.
  3. Live broker order placement and live money execution are **intentionally NOT implemented**.
  4. This design choice is appropriate and compliant with production financial safety principles: automated risk auditing software must never execute unconfirmed trades on real exchanges.
