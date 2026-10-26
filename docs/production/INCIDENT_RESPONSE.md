# FragilityShield — Security Incident Response & Forensics Runbook

**Document Version:** 1.0.0  
**Authority:** Application Security & Infrastructure Lead  
**Scope:** Security Breaches, Unauthorized Cross-Tenant Access, Secret Compromise, and Sandbox Violations  

---

## 1. Incident Severity Classification

| Severity Level | Definition | Response SLA | Examples |
| :--- | :--- | :--- | :--- |
| **SEV-1 (CRITICAL)** | Active cross-tenant data breach, arbitrary code execution on host, compromise of JWT signing keys. | **< 15 minutes** | Tenant B successfully accessing Tenant A portfolios, malicious plugin reading host `/etc/shadow`. |
| **SEV-2 (HIGH)** | Broken authentication, denial of service on financial calculations, unauthorized resource deletion. | **< 1 hour** | Repeated authentication bypass attempts, failure of RLS enforcement on a secondary table. |
| **SEV-3 (MEDIUM)** | Rate limit exhaustion, suspicious token reuse, repeated validation failures. | **< 4 hours** | Brute-force credential attempts, excessive simulation requests from a single tenant. |
| **SEV-4 (LOW)** | Security header anomaly, minor dependency vulnerability without exploit path. | **< 24 hours** | Dependency scan warning on non-critical dev library. |

---

## 2. SEV-1 Incident Playbooks

### Playbook A: JWT Signing Key Compromise
If the `FRAGILITY_JWT_SECRET` is suspected of being leaked or committed:

1. **Immediate Revocation & Rotation:**
   - Generate new cryptographically secure 64-character secret:
     ```bash
     openssl rand -hex 32
     ```
   - Update `FRAGILITY_JWT_SECRET` in AWS Secrets Manager / Zoho Catalyst Console.
2. **Invalidate Active Sessions:**
   - Restart the FastAPI container service. All existing tokens signed with the compromised key will immediately fail verification (`Invalid JWT signature`).
3. **Audit Token Usage:**
   - Query `audit_events` for all events during the suspected compromise window:
     ```sql
     SELECT * FROM audit_events WHERE timestamp >= '2026-10-25T00:00:00Z' ORDER BY timestamp DESC;
     ```

### Playbook B: Cross-Tenant Data Access Attempt (IDOR)
If an unauthorized tenant query is detected:

1. **Verify RLS Status:**
   - Execute diagnostic query to confirm RLS policies are active:
     ```sql
     SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = 'portfolios';
     ```
2. **Inspect Context Setting:**
   - Inspect transaction logs to verify whether `SET LOCAL app.current_tenant_id` was set correctly or if connection pooling leaked context.
3. **Account Isolation:**
   - Immediately suspend the offending user account:
     ```sql
     UPDATE users SET is_active = FALSE WHERE user_id = 'usr_adversary';
     ```

### Playbook C: Third-Party Plugin Sandbox Escape Attempt
If a plugin attempts unauthorized host access or timeout evasion:

1. **Forced Container Termination:**
   - The worker controller automatically sends `SIGKILL` on timeout expiration (5.0s).
2. **Review Worker Isolation:**
   - Inspect container execution logs:
     ```bash
     docker logs --tail 200 fs_sandbox_worker_container
     ```
3. **Blacklist Plugin Digest:**
   - Revoke plugin registration and log security violation:
     ```sql
     UPDATE plugin_registrations SET is_trusted = FALSE WHERE plugin_id = 'malicious_plugin';
     ```

---

## 3. Forensic Logging & Privacy Preservation

- **Never Log Sensitive Financial Data:** Asset prices, portfolio valuations, and individual holding share counts must be excluded from error traces.
- **Never Log Secrets:** Authorization headers, passwords, and raw JWT signatures are redacted before logging.
- **Immutable Audit Trail:** `audit_events` rows are strictly append-only. No `UPDATE` or `DELETE` grants are given to `fragility_app_user` on the `audit_events` table.
