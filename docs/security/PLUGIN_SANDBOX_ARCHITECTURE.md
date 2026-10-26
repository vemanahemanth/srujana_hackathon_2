# FragilityShield — Isolated Worker & Plugin Sandbox Architecture

**Document Version:** 1.0.0  
**Implementation Module:** `backend/fragility_engine/plugin_sandbox.py`, `backend/fragility_engine/plugins.py`  
**Security Standard:** Container Hardening & Principle of Least Privilege  

---

## 1. Classification of Quantitative Model Code

To prevent conflating trusted internal algorithms with untrusted user-submitted code, FragilityShield enforces four explicit execution tiers:

| Tier | Classification | Examples | Host Execution Policy | Sandbox Boundary |
| :--- | :--- | :--- | :--- | :--- |
| **Tier 1** | **Built-in First-Party Plugins** | `HistoricalSimulationPlugin`, `ParametricGaussianPlugin`, `EWMAVolatilityPlugin`, `PortfolioConcentrationPlugin` | In-process execution permitted under `PluginRegistry`. Code is vetted, static, and part of the core repository. | None required (trusted core). |
| **Tier 2** | **Configurable Custom Models** | `ConfigurableCustomModelPlugin` (Student-t $\nu$, RiskMetrics $\lambda$, Cornish-Fisher, quantile interpolation) | In-process execution permitted using safe analytical formulas (SciPy/NumPy). User only configures validated numerical floats. | None required (no arbitrary code execution). |
| **Tier 3** | **Metadata-Only Registrations** | Third-party model capability manifests registered for lab compatibility checks | Registration allowed. Execution is NOT permitted until verified. | N/A (no execution). |
| **Tier 4** | **Untrusted Third-Party Plugins** | Arbitrary user-uploaded Python modules, custom simulation algorithms | **NEVER permitted in-process or on host.** Requires dedicated container/gVisor disposable sandbox. | Hardened Container / gVisor sandbox mandatory. |

---

## 2. Sandbox Worker Architecture & Pipeline

```
[ FastAPI API Layer ]
       │
       ▼  (1. Validate user permissions & plugin manifest)
[ Tenant Execution Record Created ]
       │
       ▼  (2. Pass bounded input JSON & resource limits)
[ IsolatedWorkerController ]
       │
       ├─── Check if Container Runtime (Docker/Podman/gVisor) is Available?
       │        │
       │        ├── NO  ──► [ FAIL-CLOSED: Raise SandboxUnavailableError ]
       │        │            (Host execution is STRICTLY BLOCKED)
       │        │
       │        └── YES ──► [ Provision Disposable Hardened Container ]
                                     │
                                     ├── Non-root execution (--user 10001:10001)
                                     ├── Read-only root filesystem (--read-only)
                                     ├── Zero network access (--network none)
                                     ├── Dropped capabilities (--cap-drop ALL)
                                     ├── No new privileges (--security-opt no-new-privileges:true)
                                     ├── Memory limit (--memory 256m)
                                     ├── CPU limit (--cpus 1.0)
                                     ├── PID limit (--pids-limit 32)
                                     ├── Disposable scratch workspace (/workspace:rw)
                                     └── Hard execution timeout (5.0s kill deadline)
                                     │
                                     ▼
                        [ Execute Python Plugin Entrypoint ]
                                     │
                                     ├── Success ──► Validate output JSON schema & bounds (<= 1MB)
                                     ├── Timeout ──► Force SIGKILL, mark TIMEOUT
                                     └── Failure ──► Return sanitized error trace
                                     │
                                     ▼
                        [ Destroy Container & Wipe Workspace ]
                                     │
                                     ▼
                        [ Store Execution Audit Event & Metrics ]
```

---

## 3. Minimum Sandbox Controls & Enforcement

1. **Non-Root Execution:** The sandbox runs as an unprivileged service user (`UID 10001:10001`).
2. **Read-Only Root Filesystem:** Root filesystem is mounted read-only (`--read-only`), preventing modification of system binaries or installation of persistent malware.
3. **No Host Mounts or Sockets:** Docker socket (`/var/run/docker.sock`), host filesystem roots (`/`, `/etc`, `/home`), and environment variables are strictly inaccessible.
4. **Complete Network Isolation:** Containers run with `--network none`. Outbound connections to external servers, internal databases, or cloud instance metadata (`169.254.169.254`) are physically dropped by the network namespace.
5. **Dropped Linux Capabilities:** All kernel capabilities are stripped (`--cap-drop ALL`), preventing privilege escalation, raw socket manipulation, or namespace breakout.
6. **Hard Wall-Clock Timeout:** If an execution exceeds `5.0` seconds (preventing infinite loops or cryptominers), the worker controller sends `SIGKILL` and marks the status as `TIMEOUT`.
7. **Ephemeral Lifecycle:** Containers are created with `--rm`, and the host temporary workspace directory is wiped immediately following execution.

---

## 4. Fail-Closed Behavior

**An in-process software permission check is NOT an operating-system sandbox.**

If the hosting environment lacks a verified container engine (e.g., standard developer laptops without Docker running, or serverless functions lacking nested virtualization):

- Untrusted third-party code **WILL NEVER** fall back to in-process execution.
- `execute_untrusted()` raises `SandboxUnavailableError`.
- The API responds with HTTP 403 Forbidden:
  ```json
  {
    "success": false,
    "error": "Untrusted plugin execution is blocked on host. No isolated container runtime is available.",
    "type": "sandbox_unavailable"
  }
  ```
- Built-in risk algorithms and custom parametric models remain fully functional.

---

## 5. Verification Evidence

Validated by 7 automated tests in `backend/tests/test_plugin_sandbox_boundary.py`:
- `test_valid_manifest_creation`: Verified compliant manifest parsing.
- `test_reject_unauthorized_capabilities`: Proved unauthorized capabilities (`network:egress`, `host:shell`) are rejected at manifest registration.
- `test_reject_invalid_plugin_identifiers`: Proved path traversal (`../../etc/passwd`) is rejected.
- `test_untrusted_plugin_fails_closed_when_runtime_missing`: Proved untrusted execution raises `SandboxUnavailableError` when runtime is absent.
- `test_registry_untrusted_block_integration`: Proved in-process execution of untrusted plugins raises `PermissionError`.
- `test_builtin_plugins_execute_safely`: Proved built-in plugins continue running without regression.
- `test_default_resource_limits`: Verified 256MB memory, 1.0 CPU, 5.0s timeout limits.
