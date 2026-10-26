# FragilityShield Plugin Architecture & Sandbox Security Model

## 1. Overview
FragilityShield employs an **isolated container / gVisor execution boundary** to ensure that third-party quantitative algorithms, broker adapters, and custom pricing models execute safely without compromising host resources, production databases, or host network sockets.

```
                      +---------------------------------------+
                      |       FragilityShield Core API        |
                      |          (FastAPI / ASGI)             |
                      +-------------------+-------------------+
                                          |
                        Validates Manifest & Hash Digest
                                          |
                      +-------------------v-------------------+
                      |   Isolated Worker Controller Daemon   |
                      |         (plugin_sandbox.py)           |
                      +-------------------+-------------------+
                                          |
                       Spawns Isolated Container/gVisor
                                          |
    +-------------------------------------v-------------------------------------+
    |                        ISOLATED SANDBOX RUNTIME                           |
    |                                                                           |
    |  - Non-Root UID: 10001              - Memory Limit: <= 256MB              |
    |  - Read-Only Root Filesystem        - CPU Limit: <= 1.0 Core              |
    |  - Dropped Linux Capabilities       - Execution Timeout: <= 5.0 Seconds   |
    |  - Network Egress: DISABLED         - Disposable Temp: /tmp/scratch       |
    |  - No Host Environment Inheritance  - Bounded Output Stream: <= 1MB       |
    +---------------------------------------------------------------------------+
```

---

## 2. Security Invariants
1. **Zero Unrestricted Host Execution:** Third-party untrusted code is NEVER executed directly inside the FastAPI main process or unrestricted host OS.
2. **Fail-Closed Sandbox:** If no verified isolated container runtime (e.g. Docker, Podman, or gVisor `runsc`) is detected or configured, execution fails closed with `SandboxUnavailableError`.
3. **Declarative Capability Whitelist:** Only pre-approved declarative capabilities are permitted:
   - `dataset:read`: Grants read-only access to the designated input dataset slice.
   - `workspace:write`: Allows writes strictly to `/tmp/scratch`.
   - `result:return`: Allows bounded JSON metric emission to stdout.
   Any request for unauthorized capabilities (e.g. `raw_socket:unrestricted`, `os:exec_root`) is rejected during manifest validation.
4. **Deterministic Contract Digest:** Every registered manifest generates a canonical SHA-256 fingerprint ensuring the deployed code matches its registered contract.

---

## 3. Resource Ceilings
- **Max Memory:** 512 MB (Default: 128–256 MB)
- **Max Execution Time:** 30.0s (Default: 5.0s)
- **Max CPU Cores:** 2.0 cores (Default: 1.0 core)
- **Max Process IDs (PIDs):** 32
- **Max Output Stream:** 1,048,576 bytes (1 MB)
