# Changelog — FragilityShield

All notable changes to FragilityShield are documented in this file, adhering to [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0-rc1] - 2026-10-25

### Added
- **18 Core Quantitative Laboratories:** Complete coverage across risk modeling, Euler attribution, reverse stress testing, walk-forward backtesting, ML robustness, Monte Carlo, and perturbation analysis.
- **Production Documentation Baseline:** Comprehensive production readiness documents in `docs/production/`:
  - `BASELINE.md`, `REPOSITORY_INVENTORY.md`, `KNOWN_GAPS.md`
  - `DEPLOYMENT_TARGET.md`, `THREAT_MODEL.md`, `ACCEPTANCE_CRITERIA.md`
  - `CAPABILITY_INVENTORY.md`, `CAPABILITY_TRACEABILITY_MATRIX.md`
  - `QUANTITATIVE_SPECIFICATION.md`, `QUANTITATIVE_VERIFICATION.md`
  - `SECURITY_ASSESSMENT.md`, `PLUGIN_ISOLATION.md`, `SECRETS_AND_DATA_HANDLING.md`
  - `PERFORMANCE_BENCHMARKS.md`, `RESOURCE_LIMITS.md`
  - `ZOHO_CATALYST_DEPLOYMENT.md`, `DEPLOYMENT_RUNBOOK.md`, `ROLLBACK_AND_RECOVERY.md`
- **Security & Operational Controls:** Token redaction in logs/diagnostics (`mask_token()`), read-only broker constraint enforcement, host execution security gates (`PermissionError` on untrusted plugins).
- **Independent Mathematical Oracles:** Closed-form verification tests for Acerbi & Tasche (2002) fractional Expected Shortfall and Euler homogeneity.

### Fixed
- Reconciled inventory discrepancy between 18 core laboratories and external data dependencies (`EXT-01`, `EXT-02`).
- Live Upstox market data integration verified with real NSE instrument resolution and historical candle extraction.

### Changed
- Certified deployment model defined: **Go for Local Research Release** and **Go for Hosted Single-User Release** on Zoho Catalyst AppSail.
