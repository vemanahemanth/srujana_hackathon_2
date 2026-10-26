# FragilityShield — Phase 10 Application Security & Integrity Review

**Audit Date:** October 25, 2026  
**Auditor:** Senior Application Security & Systems Integrity Reviewer  
**Scope:** Threat Surfaces, Code Isolation Model, Input Validation, Path Traversal, Credential Management, and Denial of Service  

---

## 1. Executive Summary & Security Verdict

FragilityShield's core domain calculation modules exhibit strong software engineering standards regarding input sanitization, strict typing, immutable frozen dataclasses, and path traversal guards.

However, from an **untrusted multi-tenant security architecture perspective**, the following critical finding is identified:

> [!CAUTION]
> **CRITICAL SECURITY BOUNDARY LIMITATION:**
> The plugin registry (`PluginRegistry` in `plugins.py`) and model execution interfaces execute arbitrary Python callable objects **in-process within the main backend runtime**. Catching `Exception` prevents process crashes from standard errors, but **does NOT provide process isolation, memory sandboxing, syscall filtering (seccomp), filesystem restrictions, or network segmentation**. 
> Any dynamically registered Python plugin has full access to the host Python process, environment variables, filesystem, and network sockets.

For single-user local quantitative research (the current design baseline), this is standard and functional. For any planned multi-tenant SaaS or cloud deployment accepting arbitrary user-uploaded Python packages or code, **an out-of-process isolated worker boundary (e.g. gVisor, Firecracker, or Docker with rootless execution) is mandatory**.

---

## 2. Threat Surface Analysis

| Threat Surface | Entry Point | Potential Risk | Implemented Defense | Residual Risk / Audit Finding |
| :--- | :--- | :--- | :--- | :--- |
| **REST API Inputs** | Starlette ASGI routes in `app.py` | Malformed JSON payloads, non-numeric values, injection | Explicit JSON parsing, `float()` conversions, try/except envelope returning standardized HTTP 400 | Low. Payloads are strictly parsed into domain models. |
| **Path Traversal** | Portfolio loading (`portfolio_loader.py`), Catalog storage (`projects.py`) | Arbitrary file read/write (`../../etc/passwd`) | `sanitize_filename` enforces `basename` and rejects `..`, `/`, `\`; `_safe_path` enforces regex `^[a-zA-Z0-9_\-\.]+$` and `is_relative_to` | Low in catalog; Medium in `load_portfolio_from_json(source)` which accepts arbitrary existing file paths if passed directly by internal callers. |
| **Arbitrary Code Execution** | `ModelPlugin` registration in `plugins.py`, `ModelManifest` in `model_lab.py` | Host takeover, secret exfiltration, infinite loops | `ModelManifest.code_isolation_required` sets `Arbitrary code isolation: Required before execution` status | **HIGH (Architectural):** If a caller invokes the plugin directly, execution occurs in-process without sandbox enforcement. |
| **Denial of Service (DoS)** | Fragility search, Monte Carlo simulation, grid perturbation | High CPU/memory consumption locking the asyncio event loop | Max iteration bounds (`max_iter=100` in bisection), small sample validation, execution timeouts measured | **MEDIUM:** Synchronous compute-heavy calculations run in the main asyncio thread pool; concurrent large simulations could cause API latency spikes. |
| **Credential Exfiltration** | Broker integration (Upstox API keys / secrets) | Leaking API keys in saved experiment artifacts or logs | Offline sample provider fallback; API keys read from environment variables | Low. Credentials are not persisted in catalog JSON files or experiment reports. |

---

## 3. Detailed Audit Findings

### 3.1 Finding SEC-01: In-Process Execution of Custom Model Code (Severity: HIGH)
- **Component:** `fragility_engine/plugins.py`, `fragility_engine/model_lab.py`
- **Source Inspection:**
  ```python
  # plugins.py line 855-865:
  def get(self, plugin_id: str) -> ModelPlugin:
      return self._plugins[plugin_id]

  # When executed:
  plugin.execute(data, config)
  ```
- **Analysis:**
  The `PluginRegistry` accepts any object conforming to the `ModelPlugin` protocol. While `try ... except Exception as exc` catches runtime exceptions and formats them as `ModelExecutionResult(error_message=...)`, this is purely exception handling, not process isolation.
  A malicious or buggy plugin can:
  1. Call `os.environ` to read API secrets or environment variables.
  2. Open and read arbitrary files accessible to the user running the server.
  3. Execute subprocesses or shell commands.
  4. Allocate unbounded memory or enter infinite loops.
- **Remediation Recommendation:**
  1. For local developer mode: Maintain current in-process execution, but clearly document the security boundary.
  2. For server/cloud deployment: Implement a worker process pool or containerized runner (e.g., using `multiprocessing` with restricted privileges, Docker, or WebAssembly/Wasmtime for compiled models).

---

### 3.2 Finding SEC-02: Path Traversal Defenses in Catalog and Filename Sanitization (Severity: LOW / SECURE)
- **Component:** `fragility_engine/projects.py`, `backend/app.py`
- **Source Inspection:**
  ```python
  # projects.py lines 631-637:
  def _safe_path(self, parent: Path, identifier: str) -> Path:
      if not re.match(r"^[a-zA-Z0-9_\-\.]+$", identifier):
          raise ValueError(f"Invalid identifier for storage: '{identifier}'")
      target = (parent / f"{identifier}.json").resolve()
      if not target.is_relative_to(parent):
          raise ValueError(f"Path traversal detected for identifier '{identifier}'")
      return target

  # app.py lines 143-148:
  def sanitize_filename(filename: str) -> str:
      base = os.path.basename(filename)
      if ".." in filename or "/" in filename or "\\" in filename:
          raise ValueError(f"Unsafe filename detected: '{filename}'")
      return base
  ```
- **Analysis:**
  Both mechanisms were tested against traversal vectors:
  - `../secret` $\implies$ rejected by regex (contains `/`) and `sanitize_filename` (contains `..` and `/`).
  - `..` $\implies$ rejected by `sanitize_filename`; in `_safe_path`, `"..json"` is created, which stays inside `parent` directory and does not escape.
  - `target.is_relative_to(parent)` actively enforces containment.
- **Verification:**
  Tested traversal vectors in unit tests; all traversal attempts are rejected with `ValueError`.
  - **Verdict:** VERIFIED SECURE.

---

### 3.3 Finding SEC-03: Broker Credentials and Secret Management (Severity: LOW / SECURE)
- **Component:** `fragility_engine/market_data.py`
- **Analysis:**
  The Upstox data provider requires `UPSTOX_API_KEY` and `UPSTOX_API_SECRET`.
  - The provider reads credentials from constructor parameters or `os.environ.get("UPSTOX_API_KEY")`.
  - If credentials are not present, it gracefully falls back to the deterministic offline fixture `OfflineSampleDataProvider`.
  - In `studio.py`, `ExperimentReport` records parameters and provenance, but strips sensitive API secrets from serialized dictionaries.
  - **Verdict:** VERIFIED SECURE.

---

### 3.4 Finding SEC-04: Blocking CPU Execution on the Asyncio Event Loop (Severity: MEDIUM)
- **Component:** `backend/app.py`
- **Analysis:**
  Starlette API endpoints are declared as `async def api_calculate_risk(request: Request)`.
  Inside these endpoints, compute-intensive operations (such as high-dimensional correlation matrices, Monte Carlo paths in `simulation.py`, and multi-attack fragility audits) execute synchronously on the main thread.
  If an experiment takes 500ms of pure CPU time, the asyncio event loop is blocked for that duration, delaying concurrent HTTP requests.
- **Remediation Recommendation:**
  Offload compute-heavy quantitative routines to worker threads using `anyio.to_thread.run_sync(...)` or an external background task queue (e.g., Celery, Redis Queue, or a background worker thread).

---

## 4. Security Verification Summary

| Security Control | Claimed by Architecture | Audit Verification Status |
| :--- | :--- | :--- |
| **Input Sanitization & Schema Checks** | Yes | **VERIFIED** — Strictly typed dataclasses and regex validation. |
| **Path Traversal Prevention** | Yes | **VERIFIED** — Filename basename enforcement, regex alphanumeric filtering, and `is_relative_to` checks. |
| **Credential Redaction in Reports** | Yes | **VERIFIED** — No API keys stored in catalog files or exported markdown/CSV. |
| **Safe Error Envelopes** | Yes | **VERIFIED** — Exceptions caught and returned as structured HTTP 400 envelopes without exposing raw server internals. |
| **Isolated Code Execution (Sandboxing)** | Claimed as goal | **PARTIALLY VERIFIED** — Feature-flagged in capability report (`code_isolation_required`), but physically executes in-process. Out-of-process isolation is not yet implemented. |
| **Event Loop Non-Blocking Execution** | Implicit | **PARTIALLY VERIFIED** — Heavy calculations currently run synchronously on the ASGI loop. |
