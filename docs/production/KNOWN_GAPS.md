# FragilityShield — Known Gaps and Risk Register (Phase 0)

**Date:** 2026-10-25  
**Baseline Commit:** `74ef3fe7ad6f9ef681e8eab66cf0c080438637f7`  
**Purpose:** Honest enumeration of all architectural, security, deployment, and external data limitations.

---

## 1. External Data Feed Dependencies (BLOCKED)

### Gap 1.1: Missing Corporate Actions Adjustments (`EXT-01`)
- **Description:** Upstox Market Data V3 provides raw exchange historical candles. Stock splits, bonus issuances, and cash dividends are not adjusted in the candle stream.
- **Impact:** Backtesting long historical horizons (>1 year) without accounting for stock splits can distort returns.
- **Policy Enforcement:** Long historical backtests require user upload of split-adjusted series or explicit disclosure in metadata.

### Gap 1.2: Missing Sovereign Macroeconomic & Yield Curve Feeds (`EXT-02`)
- **Description:** Upstox is strictly an exchange equity/derivatives gateway. Central bank policy rates (RBI repo rate) and sovereign bond yield curves are not provided.
- **Impact:** Scenario Lab (`LAB-04`) can only run user-uploaded shock vectors or static crisis presets (`lehman_2008`, `covid_2020`); it cannot project live macro economic telemetry.
- **Readiness Classification:** `LAB-04` is classified as `CONDITIONALLY READY`.

---

## 2. Security & Multi-Tenancy Architecture Gaps

### Gap 2.1: In-Process Plugin Execution Limitation
- **Description:** Third-party model and attack plugins execute in Python's memory space if invoked.
- **Current Mitigation:** `PluginRegistry.execute_plugin()` raises `PermissionError` when untrusted plugins attempt execution on the host runtime.
- **Limitation:** In-process permission checking is not an OS-level sandbox. Multi-tenant hosted environments require an external containerized worker (Docker/gVisor).

### Gap 2.2: Unauthenticated Multi-User Boundary
- **Description:** The current backend operates as an open local research laboratory without built-in user authentication (JWT/OAuth session cookies per user).
- **Impact:** In a public multi-user deployment, any user can list or access all projects and datasets stored in `data/experiments/`.
- **Target Scope:** The initial production release must be designated **GO — LOCAL RESEARCH RELEASE** or **GO — HOSTED SINGLE-USER RELEASE** until tenant authentication is implemented.

---

## 3. Deployment & Operational Gaps

### Gap 3.1: Serverless Filesystem Ephemerality (Zoho Catalyst)
- **Description:** The platform currently persists projects and datasets to local filesystem paths (`data/experiments/`).
- **Impact:** On serverless cloud runtimes with ephemeral filesystems (e.g., standard serverless functions), files written to disk are lost across cold starts.
- **Mitigation:** Production deployment on Zoho Catalyst requires AppSail (persistent container service) or Catalyst Data Store (NoSQL / Relational persistence).

### Gap 3.2: Browser UI End-to-End Automation Gap
- **Description:** While all REST API, SDK, CLI, and quantitative unit/integration tests pass (585 tests), live browser automation has not been executed in this turn.
- **Impact:** In accordance with non-negotiable rules, full UI production readiness cannot be claimed without live browser test recordings.
