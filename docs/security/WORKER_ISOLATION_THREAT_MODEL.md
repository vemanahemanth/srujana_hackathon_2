# FragilityShield — Worker & Execution Isolation Threat Model

## 1. Threat Profile & Asset Classification

In FragilityShield, third-party and custom quantitative models represent untrusted code submissions. Models may contain malicious logic, infinite loops, resource starvation attacks, or attempts to access host credentials and multi-tenant databases.

### Assets at Risk:
1. **Database Credentials & Multi-Tenant Data:** PostgreSQL connection strings, application JWT secrets, other tenants' portfolios, positions, and experiment runs.
2. **Cloud Infrastructure & Host Resources:** Worker CPU, memory, filesystem, metadata services (`169.254.169.254`).
3. **Artifact Integrity:** Financial model forecasts, risk parameters, and regulatory audit records.

---

## 2. Threat Scenarios & Mitigations

| Threat ID | Threat Vector | Impact | Mitigations & Enforced Controls |
| :--- | :--- | :--- | :--- |
| **THREAT-W1** | **Arbitrary In-Process Execution** | Critical | FastAPI web application process strictly refuses to invoke untrusted model code directly. Models are submitted as asynchronous jobs to a queue. Web requests return HTTP 202. |
| **THREAT-W2** | **Credential & Environment Theft** | High | Workers strip database credentials, API secrets, and JWT tokens before spawning isolated container runtimes. The container does not inherit host environment variables. |
| **THREAT-W3** | **Network Data Exfiltration** | High | Containers run with `--network none` by default. Outbound internet and local LAN access are disabled unless an explicit administrative policy approves it. |
| **THREAT-W4** | **Resource Starvation (DoS / OOM)** | Medium | Configurable cgroup limits: max memory (256 MB), max CPU cores (1.0), max processes (32 PIDs), wall-clock execution timeout (default 60s). Workloads exceeding limits are SIGKILL'd. |
| **THREAT-W5** | **Container Escape / Kernel Vulnerability** | High | Rootless container execution, dropped capabilities (`--cap-drop=ALL`), non-root UID/GID inside container, read-only rootfs (`--read-only`), `no-new-privileges:true`. Support for gVisor (`runsc`) sandbox runtime. |
| **THREAT-W6** | **Cross-Tenant Artifact Access** | Critical | Strict path containment (`resolve().is_relative_to()`), tenant subfolder isolation, PostgreSQL Row-Level Security on artifact metadata queries. |
| **THREAT-W7** | **Zombie / Stranded Execution** | Medium | Workers check cooperative cancellation status before each execution step. Background worker heartbeats and dynamic lease expiry allow dead workers' jobs to be safely reclaimed. |

---

## 3. Trust Levels & Fail-Closed Policy

FragilityShield recognizes two distinct execution modes:

1. **`trusted_local_research`:**
   - Permitted only for verified development or approved internal baseline quantitative models.
   - Clearly logged with `execution_mode: "trusted_local_research"` in all audit events and manifests.
   - Never advertised as a secure sandbox for untrusted third-party code.

2. **`isolated_untrusted_execution`:**
   - Requires a verified, running container runtime (Docker, Podman, or gVisor `runsc`).
   - If the container runtime is absent, unconfigured, or failing, the system **fails closed**: returns HTTP 503 / raises `SandboxSecurityError`.
   - Under no circumstances does the engine fall back silently to in-process execution.

---

## 4. Residual Risks & Recommended Production Controls

1. **Shared Kernel Vulnerabilities:** Standard OCI containers share the host Linux kernel. Production deployments handling arbitrary third-party code should configure **gVisor (`runsc`)** or **Kata Containers (microVMs)** as the default runtime.
2. **Metadata Service Access:** On AWS/GCP worker instances, enforce IMDSv2 and block traffic to `169.254.169.254` via `iptables` rules on the worker host as defense-in-depth:
   ```bash
   iptables -A OUTPUT -m owner --uid-owner fragility_worker -d 169.254.169.254 -j DROP
   ```
