# FragilityShield — Sprint 5 Operations & Incident Response Runbook

## 1. Operational Diagnostics & Monitoring

### 1.1 Worker Status Endpoint
Operators can inspect worker health and queue status via authenticated HTTP request:
```bash
curl -H "Authorization: Bearer <ADMIN_OR_RESEARCHER_JWT>" \
     http://localhost:8000/api/workers/status
```
Example Output:
```json
{
  "success": true,
  "worker": {
    "worker_id": "worker_prod_01",
    "uptime_seconds": 1420.5,
    "current_job_id": null,
    "jobs_processed": 42,
    "jobs_failed": 1,
    "last_heartbeat": 1740000000.0,
    "queue_depth": 0,
    "artifact_storage": {
      "backend": "LocalFilesystemArtifactStorage",
      "base_directory": "/opt/fragilityshield/data/artifacts",
      "max_size_bytes": 52428800
    }
  }
}
```

---

## 2. Standard Incident Scenarios & Recovery Procedures

### 2.1 Scenario A: Worker Crashes Mid-Execution
**Symptom:** Worker process dies due to host OOM killer, power disruption, or unhandled segfault while executing a model.
**Automated Recovery:**
1. The crashed worker stops sending heartbeats.
2. The job's lease in PostgreSQL (`jobs.lease_expires_at`) lapses after `lease_duration_seconds` (default: 30s).
3. Healthy worker instances running `claim_next_job()` query:
   ```sql
   WHERE status = 'QUEUED' OR (status IN ('CLAIMED', 'RUNNING') AND lease_expires_at < NOW())
   ```
4. A healthy worker reclaims the job, increments `attempt_count`, logs a warning, and executes the experiment.
5. If `attempt_count >= max_attempts` (default: 3), the job transitions permanently to `FAILED` with failure category `INFRASTRUCTURE_FAILURE`.

**Manual Operator Action (if needed):**
Check system logs:
```bash
journalctl -u fragilityshield-worker@* -n 100 --no-pager
```
Restart failed worker services:
```bash
sudo systemctl restart fragilityshield-worker@1
```

---

### 2.2 Scenario B: Artifact Storage Disk Full
**Symptom:** Worker raises `ArtifactStorageError: [Errno 28] No space left on device` during artifact write.
**Procedure:**
1. Workers fail the job cleanly, recording `status = 'FAILED'`, failure reason in database, and unlinking incomplete `.tmp_*` files.
2. Operator inspects disk usage:
   ```bash
   df -h /opt/fragilityshield/data/artifacts
   ```
3. Run the artifact cleanup utility to prune expired temporary files and deleted artifacts:
   ```bash
   python -m fragility_engine.artifact_storage --prune-orphans --dry-run
   ```
4. Allocate additional block storage volume if storage utilization exceeds 85%.

---

### 2.3 Scenario C: Job Exceeds Execution Timeout
**Symptom:** A rogue model enters an infinite calculation loop or long sleep.
**Automated Recovery:**
1. The worker's execution thread monitors wall-clock duration against `job.timeout_seconds` (or default 60.0s).
2. If exceeded, the worker runtime triggers timeout cancellation, kills the isolated process/container, and updates job state to `TIMED_OUT`.
3. An audit record `JOB_TIMEOUT_TERMINATED` is written to `audit_events`.

---

### 2.4 Scenario D: PostgreSQL Connection Failure
**Symptom:** Worker loses database connectivity (`psycopg2.OperationalError: could not connect to server`).
**Procedure:**
1. The worker enters exponential backoff (initial delay 1s, doubling up to 30s max with jitter).
2. The worker does NOT crash or terminate; it continues retrying connection until the database pool recovers.
3. Once restored, the worker checks its active leases:
   - If its lease did not expire, it resumes execution.
   - If its lease expired during the outage and another worker claimed it, the worker drops the in-flight calculation safely without publishing stale results.
