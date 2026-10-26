# FragilityShield — Production Deployment Target & Architecture Specification (Phase 1)

**Date:** 2026-10-25  
**Auditing & Architecture Authority:** Independent Engineering Team  
**Document Status:** **FINAL SPECIFICATION**

---

## 1. Concrete Release Deployment Model

### Primary Target: Single-User Local Research Installation & Secured Single-Tenant Hosted App
The initial production release is explicitly defined as a **Single-User Local Research Installation** or **Secured Single-Tenant Hosted Application**. 
Because the existing backend lacks a native multi-tenant user authentication and session management layer (RBAC), multi-user public deployment is classified as **BLOCKED / OUT OF INITIAL RELEASE SCOPE**.

### Deployment Scenarios Supported:
1. **Scenario A (Primary): Local Quantitative Researcher Workstation**
   - Host: macOS / Linux x86_64 or arm64.
   - Runtime: Python 3.10+ ASGI service (`uvicorn backend.app:app --host 127.0.0.1 --port 8000`).
   - Access: Single researcher on localhost loopback.
   - Data Storage: Local filesystem (`data/catalog/`, `data/experiments/`).
2. **Scenario B (Secondary): Zoho Catalyst AppSail (Single-Tenant Container)**
   - Target: Zoho Catalyst AppSail custom Docker / Python container runtime.
   - Isolation: Single-tenant deployment behind Catalyst API Gateway / App Domain.
   - Authentication: Enforced at the Zoho Catalyst API Gateway level (Zoho OAuth / API Key Gate).

---

## 2. Data Retention, Uploads, and Persistence

| Data Type | Ingestion Vector | Storage Location | Retention Policy | Isolation Boundary |
|---|---|---|---|---|
| User Portfolios | CSV / JSON Upload | `data/experiments/projects/` | User-managed; persisted until deletion | Workspace directory |
| Market Data Candles | Upstox API Gateway | `data/experiments/datasets/` | Persisted for backtest cache | Content-addressed SHA-256 |
| Model Manifests | REST JSON Payload | `data/experiments/models/` | Immutable run artifact | UUID indexed |
| Experiment Runs | Studio Execution | `data/experiments/projects/` | Immutable audit trail | SHA-256 run manifest |
| Export Reports | JSON / CSV / LaTeX | `data/exports/` | Generated on-demand | Temporary / Download |

---

## 3. External Dependencies & Offline Operational Capability

### Mandatory vs. Optional External Services:
1. **Upstox API Gateway (`https://api.upstox.com/v3`):**
   - *Requirement:* Optional for general quantitative modeling; mandatory only when requesting live Indian equity quotes or live historical candles.
   - *Offline Fallback:* When offline or without credentials, all 17 core calculation laboratories function 100% on user-uploaded CSV/JSON datasets.
2. **Zoho Catalyst Cloud Services:**
   - *Requirement:* Mandatory only when deployed to Zoho Catalyst infrastructure.
3. **Third-Party Macro Feeds (RBI / FRED):**
   - *Requirement:* Optional external dependency. When absent, Scenario Lab accepts user-defined shock vectors.

---

## 4. Availability, Latency & Capacity Expectations

- **Core Risk Calculation (`/api/risk/calculate`):** Latency $< 25$ ms for series up to 5,000 observations.
- **Monte Carlo Simulation (`/api/simulation/monte-carlo`):** Latency $< 150$ ms for 250 paths $\times$ 30 days.
- **Stationary Bootstrap (`/api/simulation/bootstrap`):** Latency $< 350$ ms for 300 resamples.
- **Minimum-Variance Optimization (`/api/allocation/optimize`):** Latency $< 50$ ms for up to 50 assets.
- **Application Uptime:** 99.9% availability for local research services.

---

## 5. Regulatory, Compliance & Provider Terms

- **Read-Only Trade Tape Policy:** FragilityShield operates under strict read-only market data access. Zero broker order routing or automatic trade execution is permitted.
- **SEBI / Exchange Compliance Disclaimer:** Outputs represent mathematical model-stress diagnostics and static sensitivity projections. No financial advisory, automated trading signals, or investment guarantees are generated.
- **Upstox Data Terms:** Market data retrieved from Upstox API Gateway is for non-commercial quantitative analysis; redistribution of raw trade tape is prohibited.
