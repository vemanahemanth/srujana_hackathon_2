# FRAGILITYSHIELD — SPRINT 4 THREAT MODEL
## Custom Financial Model & Third-Party Plugin Execution Security

**Classification:** Engineering Security Specification  
**Status:** ACTIVE  
**Target:** Containerized Model Runner / Untrusted Quantitative Code  

---

### 1. Threat Landscape & Adversary Profiles

FragilityShield enables quantitative analysts and institutional research teams to run models, backtests, and fragility assessments. In multi-tenant environments, custom models and third-party plugins authored by external users must be treated as **hostile, untrusted code**.

#### Adversary Goals:
1. **Host & Tenant Compromise:** Break out of the execution environment to access host files, source code, or application memory.
2. **Credential Theft:** Exfiltrate environment variables, AWS/GCP/Catalyst secrets, JWT signing keys, or PostgreSQL credentials.
3. **Cross-Tenant Data Hijacking:** Read or modify other tenants' confidential portfolios, trading positions, or proprietary datasets.
4. **Denial of Service (DoS):** Exhaust compute cores, memory, disk space, or process tables, causing platform instability.
5. **Data Poisoning / Forgery:** Inject NaN, Inf, non-normal floats, or manipulated risk metrics to distort risk reports or trading signals.
6. **Command & Control / Exfiltration:** Open outbound TCP/UDP sockets to exfiltrate financial data to external command servers.

---

### 2. Threat Matrix, Enforced Controls & Verification Tests

| Threat ID | Attack Vector | Security Control | Verification Test |
| :--- | :--- | :--- | :--- |
| **THREAT-01** | **Host File System & Secret Access** (Reading `/etc/passwd`, `.env`, mounted source, or DB passwords) | **Non-root execution (UID 10001)**, **read-only root filesystem**, no host mounts beyond ephemeral per-job `/tmp/scratch`, and zero inheritance of host environment variables. | `test_sandbox_receives_no_host_secrets` |
| **THREAT-02** | **Cross-Tenant Data Exposure** (Accessing another tenant's files or database rows) | **Zero database connection in sandbox**. Tenant data is pre-extracted under PostgreSQL RLS by the backend and passed strictly as a bounded input JSON payload to the isolated container. Container has no network access to PostgreSQL. | `test_tenant_a_cannot_access_tenant_b_model_job` |
| **THREAT-03** | **Network Egress & Exfiltration** (Outbound HTTP/DNS/socket connections) | Complete network isolation via `--network none` flag on container runtime. | `test_sandbox_network_isolation_configured` |
| **THREAT-04** | **Resource Exhaustion & Fork Bombs** (Unbounded memory allocation, infinite subprocess spawning) | Enforced cgroup ceilings: `max_memory_mb` (256MB), `max_cpu_cores` (1.0), `pids_limit` (32 processes). | `test_sandbox_resource_limits_enforced` |
| **THREAT-05** | **Infinite Loops & Calculation Freezes** (Deadlocks, unbounded while loops) | Hard wall-clock execution timeout (5.0s default) enforced with `SIGKILL` termination. | `test_sandbox_wall_clock_timeout_enforced` |
| **THREAT-06** | **Output Spoofing & Numerical Corruption** (Returning NaN, Inf, negative VaR, unnormalized portfolio weights) | **Financial Model Interface Contracts**: Strict category-specific schema validators rejecting NaN, Inf, unnormalized weights, out-of-order timestamps, or negative risk numbers. | `test_financial_model_output_validation_rejects_nan_and_inf` |
| **THREAT-07** | **Disk Space Exhaustion & Bomb Artifacts** (Generating multi-gigabyte log or output files) | Enforced output byte ceiling (1 MB default). Payloads exceeding the limit trigger immediate validation failure. | `test_sandbox_output_size_limit_enforced` |
| **THREAT-08** | **Privilege Escalation & Container Breakout** (Exploiting kernel vulnerabilities to acquire root) | Enforce `--security-opt no-new-privileges:true`, `--cap-drop ALL`, and unprivileged non-root user. Prefer gVisor (`runsc`) or microVMs where supported. | `test_sandbox_container_capabilities_dropped` |
| **THREAT-09** | **Silent Host Execution Fallback** (Executing untrusted code on the host if Docker/sandbox daemon is absent) | **Strict Fail-Closed Invariant:** If `is_sandbox_available()` is False, execution FAILS CLOSED (`SandboxUnavailableError`). In-process Python execution of untrusted code is prohibited by system design. | `test_untrusted_model_fails_closed_without_container_runtime` |
| **THREAT-10** | **Cross-Tenant Job Hijacking & Cancellation** (Tenant A querying or terminating Tenant B's execution jobs) | All model jobs are tagged with `tenant_id` and verified against the caller's server-side JWT `tenant_id`. Cross-tenant queries return 404/403. | `test_cross_tenant_job_cancellation_denied` |

---

### 3. Execution Boundaries & Trust Hierarchy

```
+-------------------------------------------------------------------------+
| TRUSTED HOST APPLICATION LAYER (FastAPI / Starlette)                    |
| - Runs verified first-party code                                        |
| - Authenticates JWTs and evaluates RBAC                                 |
| - Connects to PostgreSQL via restricted fragility_app_user under RLS   |
+------------------------------------+------------------------------------+
                                     |
                                     | [Fail-Closed Gateway]
                                     | Checks if container daemon exists
                                     v
+-------------------------------------------------------------------------+
| HARDENED SANDBOX CONTAINER (Docker / Podman / gVisor)                   |
| - UID: 10001 (Non-root)                                                 |
| - Read-Only Root Filesystem                                             |
| - Capabilities: ALL DROPPED                                             |
| - Network: NONE (No egress, no DNS)                                     |
| - Memory Limit: <= 256MB                                                |
| - CPU Quota: <= 1.0 core                                                |
| - PID Limit: <= 32                                                      |
| - Timeout: <= 5.0 seconds (SIGKILL on expiry)                           |
| - Writable Dir: Ephemeral /tmp/scratch only                             |
| - Environment: Sanitized (NO database passwords, NO JWT secrets)        |
+------------------------------------+------------------------------------+
                                     |
                                     | [Output Contract Validation]
                                     | Rejects NaN/Inf, checks dimensions
                                     v
+-------------------------------------------------------------------------+
| REPRODUCIBILITY & AUDIT CATALOG                                         |
| - Records execution fingerprint, duration, exit code, output hash       |
+-------------------------------------------------------------------------+
```

---

### 4. Residual Risks & Infrastructure Hardening

1. **Shared Host Kernel:**  
   Standard Docker containers share the host Linux kernel. In public cloud multi-tenant deployments, kernel-level isolation must be hardened using **gVisor (`runsc`)** or **Kata Containers / Firecracker microVMs**.
2. **Side-Channel Timing Attacks:**  
   Co-located processes on physical hardware may leak CPU cache timing. Dedicated isolated worker nodes should be provisioned for untrusted multi-tenant workloads.
