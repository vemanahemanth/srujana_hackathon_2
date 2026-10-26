# FragilityShield — Threat Model & Security Architecture (Phase 1)

**Date:** 2026-10-25  
**Auditing Authority:** Independent Application Security Team  
**Methodology:** STRIDE Threat Analysis on Quantitative Financial Research Engine

---

## 1. Asset Inventory & Trust Boundaries

### Primary Protected Assets:
1. **Broker Credentials & API Keys:** Upstox API keys, client secrets, and OAuth access tokens.
2. **Proprietary Financial Models:** Custom model code, optimization parameters, proprietary trading signals.
3. **Sensitive Portfolio Holdings:** Position sizes, asset quantities, acquisition costs.
4. **Host System Integrity:** Preventing arbitrary code execution from malicious dataset files or untrusted plugin scripts.

### Trust Boundaries:
- **Boundary 1 (Client <-> Backend REST API):** HTTP JSON requests and file uploads.
- **Boundary 2 (Backend <-> Upstox Gateway):** TLS-encrypted outbound API calls (`https://api.upstox.com`).
- **Boundary 3 (Core Engine <-> Plugin Architecture):** Python in-memory execution perimeter.

---

## 2. STRIDE Threat Analysis & Implemented Countermeasures

| Threat Category | Potential Attack Vector | Impact Level | Implemented Architectural Countermeasure | Verification Status |
|---|---|---|---|---|
| **Spoofing** | Client sends `data_source_mode="REAL_DATA"` with fake numbers | High | Server-side provenance enforcement: `resolve_returns_with_provenance` derives provenance exclusively from verified backend source tags. | **VERIFIED** |
| **Tampering** | Parameter manipulation or malformed OHLCV candle injection | Medium | OHLCV bar physics validation: Bars where $High < Low$ or $Open/Close \notin [Low, High]$ are rejected at ingestion. | **VERIFIED** |
| **Repudiation** | Modification or unrecorded alteration of experiment results | Low | Cryptographic SHA-256 digests generated on all inputs, parameters, and output artifacts. | **VERIFIED** |
| **Information Disclosure** | Leakage of Upstox access tokens via logs, error responses, or Git | Critical | Tokens masked (`mask_token()`); `.env` listed in `.gitignore` and verified untracked; zero secrets emitted in REST responses. | **VERIFIED** |
| **Denial of Service** | Oversized simulation payloads ($100,000$ paths or infinite horizons) | High | Explicit resource bounds: $num\_paths \le 2000$, $horizon \le 252$ days. Oversized inputs raise immediate HTTP 400. | **VERIFIED** |
| **Elevation of Privilege** | Untrusted plugin execution on host machine attempting remote code execution | Critical | Host execution blocker: `PluginRegistry.execute_plugin()` raises `PermissionError` on untrusted plugins. | **VERIFIED** |

---

## 3. Sandboxing & Plugin Security Clarification

- **Current Security Guarantee:** Untrusted plugins cannot execute on the host runtime in the default configuration.
- **Limitation:** In-process permission checking is not an OS-level sandbox. If untrusted third-party code execution is required in a multi-tenant cloud environment, an external container runner (Docker/gVisor) is mandatory.

---

## 4. Multi-Tenant Exposure Boundary

Because the application does not feature per-user JWT/session authorization tables in this release, **exposing FragilityShield directly to an untrusted public network without an upstream gateway authentication proxy is strictly prohibited.**
In hosted deployments (e.g. Zoho Catalyst), an authentication barrier must be enforced at the API gateway layer.
