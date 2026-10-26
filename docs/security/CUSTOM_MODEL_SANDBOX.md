# FRAGILITYSHIELD — CUSTOM FINANCIAL MODEL SANDBOX & CONTRACT SPECIFICATION (SPRINT 4)

## 1. Overview & Architecture Boundary

FragilityShield separates core quantitative risk calculation engines from user-submitted quantitative models and third-party plugins. Custom models are executed through a decoupled **Model Execution Sandbox** that strictly isolates code execution from host files, environment variables, credentials, and databases.

### Core Architectural Invariants:
1. **Zero Database Access:** Sandboxed model runners are never given database credentials or network access to PostgreSQL. All necessary input data is resolved and authorized under PostgreSQL Row-Level Security (RLS) by the backend before being passed as a strictly bounded JSON payload into the sandbox.
2. **Fail-Closed Isolation:** If a verified container runtime (Docker daemon, Podman, or gVisor) is unavailable or unresponsive, untrusted execution **strictly fails closed** with `SandboxSecurityError` (HTTP 503). In-process or host-level execution of untrusted code is prohibited by system design.
3. **Financial Contract Validation:** Output produced by models is treated as untrusted data and subjected to strict category-specific validation (rejecting NaN, Inf, unnormalized weights, out-of-order intervals, or negative risk values).

---

## 2. Canonical Model Categories & Interfaces

FragilityShield defines typed contracts across five quantitative model categories:

### A. Portfolio Allocation Models (`allocation`)
- **Required Input:** `assets` (list of non-empty asset symbols), optional `constraints`, `benchmark_weights`.
- **Accepted Data Types:** List of strings, JSON mappings.
- **Output Schema:** `weights` mapping asset symbols to finite floats.
- **Validation Rules:**
  - Every asset weight must be a strictly finite float in `[-1.0, 1.0]`.
  - Sum of all weights must equal `1.0` (tolerance `abs_tol = 1e-3`).
  - No NaN or Inf values allowed.

### B. Forecasting Models (`forecasting`)
- **Required Input:** `series` (chronological list of at least 5 price/return points), `horizon` (positive integer).
- **Accepted Data Types:** List of floats, integer horizon.
- **Output Schema:** `forecast` (list of forecasted points), optional `lower_bound` and `upper_bound` interval arrays.
- **Validation Rules:**
  - Length of `forecast` must match `horizon`.
  - Interval ordering: For all points, `lower_bound[i] <= forecast[i] <= upper_bound[i]`.
  - All values must be strictly finite floats.

### C. Risk Estimation Models (`risk_estimation`)
- **Required Input:** `returns` (list of at least 5 return observations), `confidence_level` (float between 0.0 and 1.0).
- **Accepted Data Types:** List of floats, float confidence level.
- **Output Schema:** `metrics` dictionary containing `var`, `expected_shortfall`, and `volatility`.
- **Validation Rules:**
  - `var` (Value-at-Risk) and `expected_shortfall` must be non-negative finite floats (`>= 0.0`).
  - `volatility` must be non-negative finite float.

### D. Trading Strategies (`trading_strategy`)
- **Required Input:** `prices` or `signals` chronological series.
- **Output Schema:** `positions` or `target_weights` mapped across chronological periods.
- **Validation Rules:**
  - Monotonically increasing timestamps.
  - Position sizes bounded by configured leverage ceilings.

### E. Scenario Response Models (`scenario_response`)
- **Required Input:** `shocks` dictionary mapping factor names to percentage or basis point shifts.
- **Output Schema:** `impacts` dictionary or `projected_pnl`.
- **Validation Rules:**
  - All shift impacts must be finite numerical values.

---

## 3. Execution Modes & Trust Boundaries

| Mode | Execution Environment | Use Case | Security Guarantees |
| :--- | :--- | :--- | :--- |
| **`trusted_local_research`** | In-process canonical execution | Local single-user research with verified quantitative algorithms | Zero container overhead; verified code only |
| **`approved_isolated_container`** | Hardened container runner (Docker/Podman/gVisor) | Third-party custom models & multi-tenant user submissions | Non-root, read-only root, no network, drop-all capabilities, cgroups |
| **`disabled`** | None (Fails closed immediately) | Production multi-tenant when container daemon is missing | Absolute protection against host compromise |

---

## 4. Container Isolation Ceilings & Security Flags

When running in `approved_isolated_container` mode, the container runner executes with the following mandatory security configuration:

```bash
docker run --rm \
    --user 10001:10001 \
    --network none \
    --read-only \
    --cap-drop ALL \
    --security-opt no-new-privileges:true \
    --memory 256m \
    --cpus 1.0 \
    --pids-limit 32 \
    -v /tmp/fs_mdl_sandbox_xxx:/workspace:rw \
    -w /workspace \
    fragilityshield-sandbox-worker:latest \
    python -m models.<model_id> --input /workspace/input.json --output /workspace/output.json
```

- **Non-root Execution:** Runs as unprivileged UID `10001:10001`.
- **Network Egress Isolation:** `--network none` prohibits outbound sockets and exfiltration.
- **Read-Only Root Filesystem:** Root OS image cannot be modified by the model code.
- **Dropped Linux Capabilities:** `--cap-drop ALL` strips kernel administrative capabilities.
- **Resource Ceilings:** 256 MB RAM, 1.0 CPU core, 32 PIDs maximum.
- **Hard Execution Timeout:** 5.0 seconds wall-clock limit with forced `SIGKILL`.
- **Output Size Bounding:** Output JSON payload capped at 1 MB.

---

## 5. Auditability & Reproducibility Evidence

Every model execution produces an immutable record stored in the `jobs` and `experiment_runs` tables under PostgreSQL Row-Level Security (RLS):

```json
{
  "job_id": "job_mdl_9a8f12c3e4b56789",
  "request_id": "req_88f01a34b2c1",
  "tenant_id": "ten_alpha_capital",
  "user_id": "usr_quant_1",
  "model_id": "custom_garch_estimator",
  "category": "risk_estimation",
  "status": "succeeded",
  "execution_mode": "trusted_local_research",
  "exit_code": 0,
  "execution_time_ms": 3.42,
  "reproducibility_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "output_payload": {
    "var": 0.0215,
    "expected_shortfall": 0.0289,
    "volatility": 0.0142
  }
}
```

The `reproducibility_hash` is computed as:
$$\text{SHA256}(\text{model\_id} \parallel \text{artifact\_hash} \parallel \text{dataset\_fingerprint} \parallel \text{canonical\_output\_json})$$

---

## 6. Go / No-Go Criteria for Untrusted Execution

Untrusted model execution must remain **STRICTLY BLOCKED** unless all of the following conditions are met:
- [x] Host has a functional, responsive container engine (verified via `/api/security/status`).
- [x] Base sandbox worker image (`fragilityshield-sandbox-worker`) is pre-built, pinned, and scanned for CVEs.
- [x] Hardened execution flags (`--network none`, `--cap-drop ALL`, `--read-only`, non-root) are enforced by the controller.
- [x] Category contracts and output validation reject non-finite and unnormalized floats.
- [x] In environments without a verified container runtime (e.g. serverless environments without nested virtualization), untrusted execution **must remain disabled**.
