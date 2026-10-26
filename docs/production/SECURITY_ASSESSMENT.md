# FragilityShield — Production Security Assessment

**Date:** 2026-10-25  
**Auditing Authority:** Independent Application Security Engineer & DevSecOps Lead  
**Standard:** OWASP Top 10 API Security Risks (2023) & Sandboxed Quantitative Execution Policy

---

## 1. Executive Summary & Security Gates

This security assessment audits FragilityShield's application endpoints, broker integration, secret-handling conventions, execution boundaries, and tenant isolation mechanisms.

- **Critical Vulnerabilities:** 0
- **High-Severity Vulnerabilities:** 0
- **Architectural Security Gates:**
  1. **Multi-User Hosting Gated (NO-GO):** Gated until row-level database security (RLS) is implemented.
  2. **Untrusted Plugin Execution Gated (NO-GO):** Host execution of untrusted plugins is strictly blocked with `PermissionError`. In-process checks are NOT OS sandboxes.
  3. **Broker Confinement Verified:** 100% read-only market data interface; zero order execution endpoints exist.

---

## 2. API Security Evaluation (OWASP API Top 10)

| Risk Code | Vulnerability Category | Evaluation in FragilityShield | Mitigating Security Control | Status |
| :--- | :--- | :--- | :--- | :--- |
| **API1:2023** | Broken Object Level Authorization (BOLA) | In multi-user deployment, project or experiment IDs could be accessed if exposed. | Scoped strictly to Single-User Research Release. Multi-user deployment classified as **NO-GO / BLOCKED** without upstream gateway proxy. | **RESOLVED FOR SCOPE** |
| **API2:2023** | Broken Authentication | Unauthenticated REST endpoints. | Local loopback binding (`127.0.0.1`). Upstream gateway authentication required for hosted single-user deployment. | **RESOLVED FOR SCOPE** |
| **API3:2023** | Broken Object Property Level Authorization | Client attempting to tamper with `data_source_mode`. | Server-side provenance derivation: client-supplied mode parameter is ignored; mode is derived strictly from real source verification. | **VERIFIED** |
| **API4:2023** | Unrestricted Resource Consumption | Large simulation horizons, unbounded Monte Carlo paths, or oversized CSVs. | Explicit input clamps ($num\_paths \le 2000$, $horizon \le 365$, $resamples \le 1000$, payload $\le 10$ MB). Rejects non-finite floats (`NaN`, `Inf`). | **VERIFIED** |
| **API5:2023** | Broken Function Level Authorization | In-process execution of untrusted third-party plugins. | Execution blocked via `PermissionError` in `PluginRegistry.execute_plugin()`. Only trusted internal attacks execute. | **VERIFIED** |
| **API6:2023** | Server-Side Request Forgery (SSRF) | Outbound HTTP requests to arbitrary URLs. | Outbound requests strictly confined to hardcoded Upstox Gateway URL (`https://api.upstox.com`). No user-controlled URLs permitted. | **VERIFIED** |
| **API7:2023** | Security Misconfiguration | Committing `.env` file with real credentials. | `.env` in `.gitignore` on line 52. Confirmed zero commits in Git history (`git ls-files .env` empty). | **VERIFIED** |
| **API8:2023** | Lack of Protection from Automated Threats | Upstox API rate limits and throttling. | Rate limiting handling and exponential backoff enforced in `UpstoxMarketDataAdapter`. | **VERIFIED** |
| **API9:2023** | Improper Inventory Management | Deprecated or unverified endpoints. | Authoritative 18-lab inventory reconciled with exact REST routes. Redundant/untested routes eliminated. | **VERIFIED** |
| **API10:2023**| Unsafe Consumption of APIs | Corrupted candles or stale quotes from external provider. | Physical bar validation ($High \ge \max(Open, Close)$, $Low \le \min(Open, Close)$) rejects corrupted bars. | **VERIFIED** |

---

## 3. Upstox OAuth & Secret Handling Audit

1. **Token Masking:**
   - All tokens are masked via `UpstoxConfig.mask_token()`:
     ```python
     def mask_token(self, token: Optional[str]) -> str:
         if not token or len(token) < 12:
             return "***"
         return f"{token[:4]}...{token[-4:]}"
     ```
   - Logs, exceptions, and REST endpoints return masked tokens (e.g., `eyJh...vr4k`), never raw secret values.
2. **OAuth State & CSRF Analysis:**
   - Endpoint `/api/upstox/auth/url` generates high-entropy random state tokens via `secrets.token_urlsafe(16)`.
   - In single-user local research mode, the user opens the dialog and enters the code manually.
   - For hosted public web applications, server-side session-binding and single-use state validation are required to prevent OAuth login CSRF. This is an explicit prerequisite for multi-user hosting.
3. **Absence of Secrets in Version Control:**
   - Verified that `.env` is absent from Git history and excluded via `.gitignore`.
   - `.env.example` contains only descriptive placeholders with zero actual tokens.

---

## 4. Plugin Isolation: In-Process vs. Operating System Sandboxing

### 4.1 In-Process Gate Is NOT an OS Sandbox
- FragilityShield explicitly acknowledges that in-process Python inspection (e.g., inspecting AST, restricting builtins) does not constitute a true operating system sandbox.
- Standard CPython escapes (via ctypes, gc, introspection, or shared memory) make true in-process sandboxing impossible.

### 4.2 Host Security Policy
- Untrusted third-party plugins are **strictly blocked from executing on the host** by raising `PermissionError`.
- Only trusted, vetted internal plugins (`builtin.ewma`, `builtin.historical_simulation`, `builtin.parametric_gaussian`, etc.) execute under explicit trust policy.

### 4.3 Prerequisites for Untrusted Plugin Execution
Untrusted plugin execution remains **NO-GO / BLOCKED** until:
1. Process isolation via gVisor (`runsc`), Firecracker microVMs, or hardened rootless Docker containers is deployed.
2. Restrictive network egress (no access to metadata endpoints or local network) is enforced via network namespaces.
3. CPU, memory, and timeout bounds (cgroups v2) terminate runaway processes.

---

## 5. Multi-User Isolation & Tenant Security

- FragilityShield currently operates with a single SQLite database (`fragilityshield.db`).
- SQLite lacks native Row-Level Security (RLS) or tenant schema separation.
- Client-supplied `user_id` or `tenant_id` query parameters are not currently authenticated against JWT session claims.
- **Release Mandate:** Multi-user hosted deployment is **STRICTLY PROHIBITED (NO-GO)** until:
  1. PostgreSQL with Row-Level Security (RLS) or schema-per-tenant isolation is deployed.
  2. A cryptographically signed JWT authentication layer (e.g., Zoho Catalyst Authentication or OAuth2 gateway) establishes user identity server-side.
