# FragilityShield — Production SDK Architecture & Hardening Report

**Repository:** `/Users/vemanahemanthbabu/srujana_hackathon_2`  
**Package:** `fragility-engine`  
**Audit Standard:** Section 4 — Production-Grade SDK, Capability-Aware Execution & Sandboxing  

---

## 1. SDK Overview & Public Interface

The `fragility-engine` Python package is a production-grade, typed client interface designed for institutional quantitative finance workflows:
- **Canonical Imports:**
  ```python
  from fragility_engine.sdk import FragilityShield, Client
  from fragility_engine.custom_configs import CustomModelConfig, CustomStrategyConfig
  ```
- **Packaging:** Configured via `pyproject.toml` and `setup.py` with entrypoint CLI `fragility-engine`.
- **Installation:**
  ```bash
  pip install -e .
  ```

---

## 2. Hardened Production Capabilities

### 2.1 Remote Endpoint & Environment Configuration
The SDK client never assumes `localhost`. Endpoints and credentials are systematically loaded from the environment or constructor arguments:
```python
client = Client(
    api_url=os.environ.get("FRAGILITYSHIELD_API_URL", "https://api.fragilityshield.internal"),
    api_token=os.environ.get("FRAGILITYSHIELD_API_TOKEN"),
    workspace_id="ten_alpha_capital",
    timeout=float(os.environ.get("FRAGILITYSHIELD_TIMEOUT", 30.0)),
    max_retries=int(os.environ.get("FRAGILITYSHIELD_MAX_RETRIES", 3))
)
```

### 2.2 Connection Timeouts & Bounded Resilient Retries
All HTTP requests route through `_execute_request` in `ExternalConnectivityClient`:
1. **Strict Socket Timeout:** Enforces connection and read timeouts (default: 30.0 seconds).
2. **Bounded Exponential Backoff with Jitter:** For idempotent calls (GET, HEAD, OPTIONS) encountering transient server errors (HTTP 502, 503, 504) or network dropped connections:
   $$t_{\text{sleep}} = 0.2 \times 2^{\text{attempt}} + \text{Uniform}(0.01, 0.1)$$
3. **Strict Fast-Fail on Client Errors:** Errors in the 4xx range (400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found, 422 Unprocessable Entity) are **NEVER retried**. They fail fast with detailed error diagnostics.

---

## 3. Capability-Aware Algorithm Registration

User algorithms are registered with explicit capability metadata and parameter validation schemas:
```python
model_cfg = CustomModelConfig(
    model_id="garch_vol_t",
    display_name="GARCH(1,1) Student-t Volatility Estimator",
    model_type="risk_model",
    description="Fat-tailed volatility forecast model",
    parameters={"omega": 1e-5, "alpha": 0.08, "beta": 0.90},
    capabilities=["var_calculation", "expected_shortfall", "volatility_forecast"]
)
client.model_lab.register_model(model_cfg)
```

### Capability Match Matrix
| Algorithm Type | Advertised Capabilities | Supported Labs | Incompatible Labs (Explicitly Rejected) |
|---|---|---|---|
| **Risk / VaR Model** | `var_calculation`, `cvar_calculation` | Risk Analytics (`/labs/risk`), Model Validation (`/models`) | Strategy Backtest, Allocation |
| **Forecasting Model** | `volatility_forecast`, `return_forecast`| ML Forecasting (`/labs/ml-forecasting`), Monte Carlo (`/labs/monte-carlo`)| Strategy Backtest, Risk Attribution |
| **Trading Strategy** | `generate_signals`, `position_sizing` | Strategy Backtest (`/labs/backtesting`), Tournament (`/labs/tournament`) | Risk Analytics, Scenario Lab |
| **Allocation Model** | `optimize_weights`, `covariance_estimation`| Allocation & Optimization (`/labs/allocation`), Portfolio Workbench (`/portfolio`)| ML Forecasting, Reverse Stress |

If an incompatible model is submitted to a lab (e.g., submitting an allocation model to the strategy backtest engine), the backend returns HTTP 422 with a descriptive error.

---

## 4. Execution Sandboxing & Security Boundaries

FragilityShield protects against malicious or buggy user code via `PluginSandbox` and `ModelSandbox`:
1. **Static AST Analysis:** Disallows dangerous imports (`os`, `sys`, `subprocess`, `socket`, `shutil`, `pickle`).
2. **Resource Limits:** Restricts worker processes to 1024 MB RAM and 60 seconds CPU timeout.
3. **Tenant Isolation:** Enforces multi-tenant data boundaries so external user submissions cannot access or overwrite another workspace's records.

---

## 5. Automated Verification Evidence

The SDK has been verified with comprehensive unit and integration tests:
- `backend/tests/test_sdk_and_cli.py`: **13 passed** (0.68s) — Exercises portfolio lifecycle, risk calculations, scenario execution, fragility audits, allocation optimization, and CLI commands.
- `backend/tests/test_sdk_network_resilience.py`: **3 passed** (0.83s) — Verifies timeout configuration, non-retry of 422 errors, and retry of transient 502 errors on idempotent calls.
- `backend/tests/test_model_sandbox_and_contracts.py`: **Passed** — Verifies AST safety validation and capability matching.