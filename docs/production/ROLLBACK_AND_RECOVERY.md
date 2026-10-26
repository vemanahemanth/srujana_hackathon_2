# FragilityShield — Rollback and Operational Recovery Procedures

## 1. Incident Classification & Severity

| Severity Level | Definition | Immediate Response Action |
| :--- | :--- | :--- |
| **P1 — Critical Outage** | Service returning 5xx across all routes; container crash loop. | Roll back to previous AppSail deployment immediately. |
| **P2 — Data Corruption** | Erroneous calculations, invalid database writes, or token leakage. | Enable maintenance mode; revert commit; restore DB backup. |
| **P3 — Provider Failure** | Upstox API returns 401/429; real data unavailable. | Degrade gracefully; surface provider error banners; refresh token. |

---

## 2. Fast Rollback Procedure (Zoho Catalyst AppSail)

If a new deployment exhibits regressions or failures:

1. **Via Catalyst Console:**
   - Go to **Catalyst Console > AppSail > Deployments**.
   - Select the previous stable deployment version (e.g., `Build #14`).
   - Click **Revert / Promote to Production**.
   - Traffic routes to the previous healthy container in $< 30$ seconds.

2. **Via Catalyst CLI:**
   ```bash
   catalyst appsail:rollback --app fragilityshield --version <STABLE_VERSION_ID>
   ```

3. **Verify Health Post-Rollback:**
   ```bash
   curl -s -f https://<your-catalyst-url>/api/v1/health || echo "HEALTH CHECK FAILED"
   ```

---

## 3. Database Recovery Procedures (SQLite / Mounted Volume)

1. **Daily Backup Location:**
   - Daily database snapshots are stored under `/data/backups/fragilityshield_YYYYMMDD_HHMM.db`.
2. **Restoration Command:**
   ```bash
   # Stop the running application instance
   catalyst appsail:stop --app fragilityshield

   # Restore backup file
   cp /data/backups/fragilityshield_STABLE.db /data/fragilityshield.db

   # Restart the application
   catalyst appsail:start --app fragilityshield
   ```

---

## 4. Upstox Token Invalidation / Emergency Revocation

In the event of accidental token leakage or unauthorized broker session:
1. Immediately log into [Upstox Developer Console](https://developer.upstox.com).
2. Delete or regenerate the `API Secret`.
3. In Catalyst Console, update `UPSTOX_CLIENT_SECRET` and clear `UPSTOX_ACCESS_TOKEN`.
4. Restart the AppSail instance to flush in-memory cached credentials.
