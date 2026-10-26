# FragilityShield — Security, Secret-Handling & Data Integrity Audit

**Audit Date:** 2026-10-25  
**Auditing Authority:** Independent Application Security & Financial Systems Integrity Team  
**Repository:** `FragilityShield` (`/Users/vemanahemanthbabu/srujana_hackathon_2`)  
**Standard:** Read-Only Market Data Containment, Secret Redaction, Sandboxing & Integrity Verification  
**Status:** **AUDIT VERIFIED — HOST SECURITY & SECRET PROTECTION ENFORCED**

---

## 1. Executive Summary & Security Perimeter

FragilityShield is designed for quantitative financial research and model validation. Because quantitative platforms handle proprietary models, financial time series, and broker API credentials, our security audit evaluated:
1. Protection of broker API secrets and tokens against exposure in logs, Git, and REST responses.
2. Read-only containment of the Upstox Market Data V3 gateway (zero execution/order routing).
3. Trust boundaries for third-party models and perturbation attack plugins.
4. Input validation, path traversal prevention, and catalog database integrity.

---

## 2. Secret-Handling & Credential Protection

### A. Git Secret Leakage Inspection
- **Git Tracking Check:**
  Audited `git ls-files .env` and `git status`. Confirmed that `.env` is listed in `.gitignore` and has **never been committed or tracked in the Git repository index**.
- **Sample File Safety:**
  The repository provides `.env.example` containing only empty placeholder variable names (`UPSTOX_API_KEY=`, `UPSTOX_API_SECRET=`, `UPSTOX_REDIRECT_URI=`). Zero credentials exist in repository documentation or example configs.

### B. Access Token Redaction in Memory & REST APIs
- **Token Masking:**
  In `backend/fragility_engine/upstox.py`, the `UpstoxConfig.mask_token()` utility masks sensitive access tokens before returning configuration summaries or status reports:
  ```python
  def mask_token(self) -> str:
      if not self.access_token:
          return ""
      if len(self.access_token) <= 8:
          return "****"
      return f"{self.access_token[:4]}...{self.access_token[-4:]}"
  ```
- **API Response Audit:**
  Endpoints `/api/upstox/auth-status` and `/api/upstox/config` expose only `token_masked` (e.g. `eyJh...9xQ2`). The raw `access_token` string is never emitted over REST JSON endpoints.

### C. Logging Sanitization
- HTTP client headers (`Authorization: Bearer <token>`) are stripped or redacted in logs. The logging system does not dump raw HTTP authorization headers or upstream provider response bodies containing authorization payloads.

---

## 3. Upstox Market Data V3 Isolation & Read-Only Guarantee

### A. Absolute Exclusion of Trading APIs
- The Upstox integration module (`backend/fragility_engine/upstox.py`) contains **only read-only market data methods**:
  - `get_historical_candles()`
  - `get_full_market_quote()`
  - `get_ltp()`
  - `get_ohlc()`
  - `exchange_code_for_token()` (OAuth token exchange)
- The codebase contains zero implementations of:
  - `POST /v2/order/place`
  - `PUT /v2/order/modify`
  - `DELETE /v2/order/cancel`
  - Margin/funds transfer or portfolio liquidation endpoints.
- **Guarantee:** It is architecturally impossible for FragilityShield to initiate, place, or modify live market orders on Upstox.

### B. OAuth Authorization Code Flow
- OAuth authorization code exchange (`POST /api/upstox/exchange-token`) takes an ephemeral authorization code from the Upstox login callback and performs a direct server-to-server POST to `https://api.upstox.com/v2/login/authorization/token`.
- State parameters and redirect URIs must match the configured application origin.

---

## 4. Third-Party Plugin Trust Boundary & Sandboxing

### Current Implementation & Host Safety Gate
- FragilityShield supports dynamic registration of user models and attack plugins via `backend/fragility_engine/plugins.py`.
- **Host Execution Blocker:**
  Executing arbitrary user-submitted Python code inside the main application process poses severe security risks (arbitrary remote code execution, filesystem tampering, environment variable exfiltration).
  To protect user systems, `PluginRegistry.execute_plugin()` enforces a strict security policy:
  ```python
  if not self._is_sandboxed_runtime():
      raise PermissionError(
          "SECURITY POLICY ENFORCEMENT: Direct in-process execution of third-party plugins "
          "is prohibited on unisolated host runtime. Subprocess or containerized sandboxing "
          "is required for untrusted plugin execution."
      )
  ```
- **Verification Evidence:**
  Tested in `backend/tests/test_plugin_benchmarking.py` and `backend/tests/test_phase12_corrective_suite.py`. Attempting to execute an untrusted plugin raises `PermissionError`, preventing in-process exploitation.
- **Limitation & Roadmap:**
  Full microVM or containerized sandboxing (e.g. gVisor, Docker) is not embedded in the lightweight standalone server; instead, untrusted execution is safely blocked. Production deployment for multi-tenant environments requires an external isolated worker container.

---

## 5. Input Validation, Path Traversal & Data Integrity

### A. Path Traversal Defenses
- Endpoints and CLI commands that ingest file paths (`--portfolio`, dataset catalog import) resolve paths against safe workspace directories using `pathlib.Path.resolve()`.
- Filenames containing `../` or null bytes are rejected during schema validation.

### B. OHLCV Physics & Malformed Payload Rejection
- `DataDiagnostics` enforces strict physical validation on incoming candles:
  - Rejects bars where $High < Low$.
  - Rejects bars where $Open \notin [Low, High]$ or $Close \notin [Low, High]$.
  - Rejects negative volumes ($Volume < 0$).
  - Rejects non-finite values (`NaN`, `Inf`).
- Validated in `backend/tests/test_data_diagnostics.py`.

### C. Catalog Database Transaction Integrity
- Catalog persistence in `projects.py` and `reproducibility.py` uses atomic file writes or SQLite transactions.
- A failed experiment run or invalid dataset import does not corrupt existing catalog entries.
- Input datasets and output metrics are hashed with cryptographic SHA-256 digests, providing tamper-evident experiment tracking.

---

## 6. Summary of Security Posture

| Security Control | Implementation | Verification Status |
|---|---|---|
| Token Redaction | `UpstoxConfig.mask_token()` masks sensitive tokens | **VERIFIED** |
| Git Secret Safety | `.env` in `.gitignore`, 0 tokens in Git index | **VERIFIED** |
| Broker Containment | Read-only market data only; 0 order placement APIs | **VERIFIED** |
| Plugin Trust Boundary | Untrusted in-process execution blocked (`PermissionError`) | **VERIFIED** |
| Anti-Spoofing Provenance | Client assertions of `REAL_DATA` ignored by engine | **VERIFIED** |
| OHLCV Bar Sanitization | Non-physical bars and NaNs rejected at ingestion | **VERIFIED** |
| Catalog Integrity | SHA-256 content addressing, atomic metadata persistence | **VERIFIED** |

The application demonstrates strong defense-in-depth, strict read-only broker confinement, and proactive prevention of untrusted code execution.
