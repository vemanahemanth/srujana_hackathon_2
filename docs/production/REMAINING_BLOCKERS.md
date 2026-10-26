# FragilityShield — Remaining Blockers & Known Limitations

**Date:** 2026-10-25  
**Auditing Authority:** Independent Quantitative & Application QA Lead  
**Standard:** Explicit Disclosure of Technical Limitations & External Dependencies

---

## 1. External Data Feed Blockers

### Blocker 1: Corporate Actions & Dividend Adjustment Feed (`EXT-01`)
- **Status:** **BLOCKED**
- **Root Cause:** The Upstox Market Data V3 REST API (`api.upstox.com/v3/historical-candle`) provides raw, unadjusted OHLCV price series. It does not provide corporate action split/bonus/dividend schedules or dividend reinvestment factor (DRIP) adjustment multipliers.
- **Impact on Platform:** Historical candle series crossing stock splits (e.g., a 2:1 stock split) will exhibit artificial price drops unless manually adjusted by the user. Total-return calculations cannot claim corporate-action adjustment.
- **Resolution Path:** Requires subscribing to a dedicated corporate actions data provider (e.g., NSE/BSE corporate action data feed, CMIE Prowess, or Bloomberg/FactSet API).

### Blocker 2: Sovereign Yield Curves & Macroeconomic Time Series (`EXT-02`)
- **Status:** **BLOCKED**
- **Root Cause:** Upstox is an equity and derivatives broker, not an institutional macroeconomic data provider. It does not provide Indian G-Sec / Treasury zero-coupon yield curves, RBI repo rates, CPI inflation, or GDP series.
- **Impact on Platform:** Macroeconomic scenario shocks and discount curves currently rely on user-supplied parameters or historical equity scenario replays rather than live macroeconomic sovereign yield feeds.
- **Resolution Path:** Ingest data from the Reserve Bank of India (RBI) Database on Indian Economy (DBIE) or FRED API for institutional rates.

---

## 2. Architecture & Security Blockers

### Blocker 3: Untrusted Third-Party Plugin Sandboxing (`LAB-17`)
- **Status:** **BLOCKED for Public Untrusted Execution**
- **Current Enforcement:** Host execution of untrusted third-party plugins is strictly blocked by raising `PermissionError`. Only trusted, vetted internal plugins execute under explicit policy.
- **Blocker for General Hosting:** An in-process Python check is **not** an operating system sandbox. Running arbitrary user-submitted Python plugins safely in a public cloud environment requires an isolated execution tier (e.g., gVisor `runsc`, Firecracker microVMs, or rootless containers) with cgroup CPU/memory limits and network egress restrictions.
- **Resolution Path:** Deploy an isolated worker tier running on a dedicated container platform supporting gVisor.

### Blocker 4: Multi-Tenant Row-Level Database Security (RLS)
- **Status:** **BLOCKED for Public Multi-User Hosting**
- **Current State:** FragilityShield uses a single SQLite database (`fragilityshield.db`) without Row-Level Security (RLS) or tenant schema separation.
- **Impact:** Any shared hosting environment without an external gateway would allow cross-user visibility of portfolios and experiments.
- **Resolution Path:** Migrate from SQLite to PostgreSQL with schema-per-tenant or Row-Level Security (RLS), and integrate cryptographically signed JWT user claims.

---

## 3. Infrastructure & Deployment Blockers

### Blocker 5: Live Zoho Catalyst Cloud Deployment Smoke-Testing
- **Status:** **BLOCKED on Explicit Authorization / Hosted Credentials**
- **Current State:** The deployment architecture, Dockerfile, environment mappings, and runbooks are fully specified and locally validated. However, in accordance with the rule prohibiting unauthorized deployment or cloud infrastructure costs, no live deployment to Zoho Catalyst cloud servers was performed.
- **Resolution Path:** Execute `catalyst appsail:deploy` upon receiving explicit user authorization and Catalyst project credentials.
