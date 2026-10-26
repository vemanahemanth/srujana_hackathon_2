# Security Policy — FragilityShield

## 1. Supported Versions

| Version | Supported | Notes |
| :--- | :--- | :--- |
| `1.0.0-rc1` (Current) | :white_check_mark: | Active production-readiness release candidate. |
| `< 1.0.0` | :x: | Development snapshots; unsupported. |

---

## 2. Reporting a Vulnerability

The FragilityShield engineering team takes security seriously. If you discover a security vulnerability, **do not open a public GitHub issue**.

Please report vulnerabilities privately via email to:
- **Security Contact:** `security@fragilityshield.internal` (or repository owner)
- **Response SLA:** Initial acknowledgment within 24 hours; triage within 72 hours.

---

## 3. Threat Model & Security Posture

### 3.1 Single-User / Local Research Scope
- FragilityShield is currently certified as a **Single-User Local Research Installation** and a **Secured Single-Tenant Application**.
- It does **not** provide row-level tenant isolation for untrusted multi-user environments. Any multi-tenant deployment must be protected by an upstream identity and authentication gateway (e.g., Zoho Catalyst API Gateway).

### 3.2 Read-Only Confinement
- FragilityShield is strictly a research and simulation system. It contains **zero broker trade placement, order execution, or account mutation capabilities**.
- Upstox API keys require only market data read permissions (`read`). Never grant trading permissions to FragilityShield API tokens.

### 3.3 Plugin Isolation
- Untrusted plugins attempting execution on the host machine are rejected with `PermissionError`.
- Only trusted, vetted plugins under an explicit trust policy may be executed. For untrusted execution, an external container or gVisor sandbox must be provided.

### 3.4 Secret Management
- Never commit `.env` or paste real credentials into logs, tests, or documentation.
- All tokens are masked via `UpstoxConfig.mask_token()` in all diagnostic outputs and UI responses.
