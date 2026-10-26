# FragilityShield — Production Release Checklist & Adversarial Gate

**Date:** 2026-10-25  
**Auditing Authority:** Independent Quantitative & Application QA Lead  
**Release Candidate:** FragilityShield `v1.0.0-rc1`  
**Git Baseline:** Commit `74ef3fe7ad6f9ef681e8eab66cf0c080438637f7` on branch `main`

---

## 1. Release Gates & Verification Matrix

| Release Gate | Acceptance Requirement | Evidence / Artifact Reference | Adversarial Status |
| :--- | :--- | :--- | :--- |
| **Gate 0: Baseline & Git Protection** | Git status clean, no destructive operations, `.env` untracked. | `git ls-files .env` empty; `docs/production/BASELINE.md` | **VERIFIED** |
| **Gate 1: Production Target Definition** | Concrete target defined; STRIDE threat model documented. | `docs/production/DEPLOYMENT_TARGET.md` | **VERIFIED** |
| **Gate 2: Reconciled Capability Inventory**| 18 Core Labs reconciled; separated from 2 external feeds. | `docs/production/CAPABILITY_INVENTORY.md` | **VERIFIED** |
| **Gate 3: Backend Correctness** | Full backend test suite passes without collection/runtime errors. | `pytest backend/tests` (585 passed, 0 failed) | **VERIFIED** |
| **Gate 4: Independent Quantitative Oracles**| Acerbi & Tasche fractional ES, Euler homogeneity, analytical QP. | `docs/production/QUANTITATIVE_VERIFICATION.md` | **VERIFIED** |
| **Gate 5: Market Data & Provenance** | Live Upstox candle & quote extraction; provenance tags enforced. | `docs/production/TEST_EVIDENCE.md` | **VERIFIED** |
| **Gate 6: Security Hardening** | Token masking (`mask_token`), read-only broker confinement. | `docs/production/SECURITY_ASSESSMENT.md` | **VERIFIED** |
| **Gate 7: Persistence & State** | Experiment manifests capture seeds, parameters, input fingerprints. | `test_reproducibility_lab.py` (38 passed) | **VERIFIED** |
| **Gate 8: Interface Parity** | REST API, Python SDK, and CLI share identical defaults and units. | `test_sdk_and_cli.py` (13 passed) | **VERIFIED** |
| **Gate 9: Real Browser Workflows** | Chrome automation of portfolio, risk, Monte Carlo, assumptions. | `e2e_reverification_1792904532475.webp` | **VERIFIED** |
| **Gate 10: Performance & Limits** | Empirical benchmarks recorded; bounds enforced (max 10k obs). | `docs/production/PERFORMANCE_BENCHMARKS.md` | **VERIFIED** |
| **Gate 11: Frontend Protection** | Zero modifications to `frontend/index.html`, `app.js`, `style.css`. | `git diff frontend/` untouched in session | **VERIFIED** |

---

## 2. Zoho Catalyst Deployment Readiness Breakdown

Per Section 7 of the adversarial mandate, deployment readiness stages are strictly distinguished:

| Deployment Readiness Stage | Current Status | Description & Limitations |
| :--- | :--- | :--- |
| **Stage 1: Architecture Documented** | **VERIFIED** | AppSail container service selected over serverless functions; architecture, container port (8000), and storage mapped in `ZOHO_CATALYST_DEPLOYMENT.md`. |
| **Stage 2: Configuration Locally Validated** | **VERIFIED** | Local server binding, health checks (`/api/health`), and environment variable ingestion (`UPSTOX_ACCESS_TOKEN`, `PORT`) validated locally. |
| **Stage 3: Deployment Artifact Built & Tested** | **CONDITIONALLY VERIFIED** | Container Dockerfile specified and validated against local Python 3.11/3.14 dependencies. |
| **Stage 4: Hosted Deployment Smoke-Tested** | **NOT VERIFIED (BLOCKED)** | No live deployment to Zoho Catalyst cloud servers was performed (in compliance with rule prohibiting unauthorized deployment or cloud costs). |
| **Stage 5: Persistence / Restart in Hosted Cloud** | **NOT VERIFIED (BLOCKED)** | Local SQLite backup and restore verified; cloud persistent volume behavior remains untested in live Catalyst cloud. |
| **Stage 6: Hosted Security Controls Verified** | **NOT VERIFIED (BLOCKED)** | Local token masking, path traversal rejection, and untrusted plugin rejection verified locally; cloud perimeter controls untested. |

---

## 3. Four Separate Release Determinations

### A. Local Research Release
- **Status:** **GO — APPROVED / VERIFIED**
- **Justification:** All 18 core laboratories, quantitative models, data provenance enforcement, and CLI/SDK/REST interfaces are verified with 585 passing automated tests and real Chrome browser workflows.

### B. Hosted Single-User Release
- **Status:** **GO — CONDITIONALLY APPROVED**
- **Justification:** Approved ONLY behind an authenticated reverse proxy or API gateway (e.g., Zoho Catalyst API Gateway with HTTP Basic Auth / JWT token verification) with single-user access. Direct, unauthenticated exposure to the public internet is strictly prohibited.

### C. Hosted Multi-User Release
- **Status:** **NO-GO — STRICTLY BLOCKED**
- **Justification:** Multi-tenant row-level database security (RLS) and isolated tenant workspaces are not present in the current SQLite architecture. Cross-tenant data isolation cannot be defended.

### D. Execution of Untrusted Third-Party Plugins
- **Status:** **NO-GO — STRICTLY BLOCKED**
- **Justification:** In-process software checks are NOT an OS-level sandbox. Host execution of untrusted plugins is strictly blocked by raising `PermissionError`. Untrusted plugin execution on public servers requires container/gVisor sandboxing.
