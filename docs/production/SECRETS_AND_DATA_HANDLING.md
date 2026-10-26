# FragilityShield — Secrets and Data Handling Protocol (Phase 6)

**Date:** 2026-10-25  
**Auditing Authority:** Independent Application Security Engineer  
**Scope:** Credential Protection, Git Hygiene, Token Redaction, and Data Ingestion Security

---

## 1. Zero Secrets in Source Control

### Git Tracking Evidence:
- `.env` is uncommitted and listed on line 52 of `.gitignore`.
- Verification command `git ls-files .env` returns zero entries.
- Verification command `git log --oneline -- .env` confirms that `.env` has never been committed in Git history.
- Template file `.env.example` provides empty variable keys with non-sensitive guidance:
  ```ini
  UPSTOX_API_KEY=
  UPSTOX_API_SECRET=
  UPSTOX_REDIRECT_URI=http://localhost:8000/api/upstox/oauth/callback
  UPSTOX_ACCESS_TOKEN=
  ```

---

## 2. Token Masking & Redaction in Memory and APIs

- **Masking Algorithm:** In [`backend/fragility_engine/upstox.py:UpstoxConfig.mask_token()`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/upstox.py#L136):
  ```python
  def mask_token(self, token: Optional[str]) -> str:
      if not token:
          return ""
      if len(token) <= 8:
          return "****"
      return f"{token[:4]}...{token[-4:]}"
  ```
- **Serialization Guarantee:** REST endpoints `/api/upstox/status` and `/api/upstox/config` serialize only `masked_access_token` (e.g. `eyJ0...-nmU`). Raw token strings are never emitted over HTTP.
- **Log Sanitization:** HTTP headers (`Authorization: Bearer ...`) are redacted before logging.

---

## 3. Data Ingestion Sanitization & Path Traversal Protections

### Path Traversal Defense:
- All file loading routines (`load_portfolio_from_json`, `load_portfolio_from_csv`) resolve paths against approved directories using `pathlib.Path.resolve()`.
- Filenames containing path traversal sequences (`../`, `..\`) or null bytes are rejected during schema validation.

### Numerical Data Hygiene:
- Missing observations (`None`) and non-finite numbers (`NaN`, `+Inf`, `-Inf`) are rejected at the data gateway level, preventing silent propagation into linear algebra routines.
- Prices must be strictly positive ($P > 0$); quantities must be non-negative ($Q \ge 0$).
