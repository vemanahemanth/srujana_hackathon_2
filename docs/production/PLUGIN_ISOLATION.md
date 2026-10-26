# FragilityShield — Plugin Isolation & Execution Security Architecture (Phase 6)

**Date:** 2026-10-25  
**Auditing Authority:** Independent Application Security Team  
**Scope:** Trust Boundaries, Execution Permissions, and Sandboxing Strategy

---

## 1. The Core Principle: In-Process Checks Are Not Sandboxes

FragilityShield explicitly states as an architectural premise:
> **An in-process software check is NOT an OS-level sandbox.**

Python executes in a shared process space. Any third-party code running in the same process has access to:
- Process memory (including masked or unmasked tokens).
- Local filesystem permissions of the running OS user.
- Network sockets and environment variables.

Therefore, FragilityShield rejects the false claim that a custom classloader or Python exception provides containment for untrusted code.

---

## 2. Implemented Execution Policy

In [`backend/fragility_engine/plugins.py:PluginRegistry.execute_plugin()`](file:///Users/vemanahemanthbabu/srujana_hackathon_2/backend/fragility_engine/plugins.py#L880):

```python
if self._enforce_trusted_execution and not self.is_trusted(plugin_id) and not trusted_override:
    raise PermissionError(
        f"Execution of untrusted plugin '{plugin_id}' is blocked on unisolated host runtime. "
        "In-process execution of arbitrary third-party code is prohibited by FragilityShield "
        "security policy. An isolated worker container (gVisor/container) is required."
    )
```

### Policy Rules:
1. **Built-in Plugins (`builtin.*`):** Trusted by default; statically verified implementations of standard historical simulation and risk models.
2. **Third-Party Plugins:** Default to untrusted status. Cannot be executed in-process without an explicit `trusted_override=True` passed by a local developer who has vetted the source code.
3. **Execution Diagnostics (`get_isolation_status()`):**
   - Explicitly returns `os_isolation_active: False`.
   - Returns a security warning explaining that local runtime executes in-process and requires an isolated worker container for untrusted code.

---

## 3. Production Multi-Tenant Sandboxing Roadmap

For cloud-hosted deployments allowing arbitrary user-submitted models:
1. **Container Runner:** Delegate execution to ephemeral worker containers (Docker, gVisor, or AWS Lambda microVMs).
2. **Resource Constraints:** Enforce cgroup limits (e.g. 512MB RAM, 1 vCPU, 5-second hard timeout).
3. **Network Isolation:** Disable outbound network connectivity on worker containers (`--network none`) to prevent exfiltration.
4. **Read-Only Root Filesystem:** Mount input datasets into `/data` as read-only; output serialized metrics over stdout pipe.
