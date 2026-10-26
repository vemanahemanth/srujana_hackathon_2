# FragilityShield — Phase 11 Security Model Reassessment

**Audit Date:** October 25, 2026  
**Auditor:** Application Security Architecture & Systems Integrity Reviewer  
**Scope:** Re-evaluation of Plugin Security Claims, In-Process Execution Boundaries, and Sandboxing Deficiencies  
**Repository:** `/Users/vemanahemanthbabu/srujana_hackathon_2`  

---

## 1. Executive Security Reassessment

In Phase 10, the security model was marked `PARTIALLY VERIFIED` on the grounds that the capability audit matrix in `projects.py` accurately identifies when arbitrary code isolation is required (`code_isolation_required: True`).

**Phase 11 Reassessment Finding:**
> [!CAUTION]
> **RECLASSIFICATION TO BROKEN / NOT IMPLEMENTED (AS A SECURITY CONTROL):**
> Setting a metadata string `"Isolated Worker Required"` in a JSON capability report does not restrict, isolate, or sandbox executing Python code in any way.
> 
> When a custom model or plugin is executed through `PluginRegistry.execute()` or `run_model_integration_suite()`, the supplied Python code runs **in-process within the main Python runtime**, sharing memory, process credentials, open file descriptors, and environment variables with the ASGI server.

---

## 2. End-to-End Execution Trace of a Custom Plugin

### 2.1 Registration
```python
# fragility_engine/plugins.py lines 833-853:
def register(self, plugin: ModelPlugin, overwrite: bool = False) -> None:
    if not isinstance(plugin, ModelPlugin):
        raise TypeError(...)
    self._plugins[pid] = plugin
```
- The plugin is stored as an in-memory Python object reference in `self._plugins`.
- No bytecode inspection, AST verification, or dependency isolation occurs.

### 2.2 Execution
```python
# fragility_engine/plugins.py lines 855-863 & model_lab.py lines 358-360:
plugin = registry.get(plugin_id)
result = plugin.execute(data, config)
```
- The method `plugin.execute()` is called as a standard Python method call on the main thread.
- If the plugin raises an exception, the caller catches `Exception` and logs an error string.

---

## 3. Systematic Access Surface Inspection

Using an authorized non-destructive diagnostic probe plugin (`InspectingPlugin`), we inspected the access boundaries of the plugin execution context:

| Access Surface | Tested Probe | Observed Behavior | Security Boundary Status |
| :--- | :--- | :--- | :---: |
| **Process Environment** | `os.environ` keys count | Successfully accessed all 54 environment variables present in the shell. | **UNRESTRICTED** |
| **Local Filesystem** | `os.path.exists("/etc")` and `os.getcwd()` | Successfully read `/Users/vemanahemanthbabu/srujana_hackathon_2` and checked root `/etc` path existence. | **UNRESTRICTED** |
| **Host Network Sockets** | `socket.socket` creation | Unrestricted ability to open outbound TCP/UDP sockets. | **UNRESTRICTED** |
| **Memory & CPU Limits** | Memory allocation / CPU loops | No `setrlimit` or cgroups quotas applied; plugin can consume 100% of host CPU or allocate memory until host OOM killer activates. | **UNRESTRICTED** |
| **Process State & Subprocesses** | `sys.modules`, `subprocess.Popen` | Direct access to all loaded Python modules and standard library subprocess capabilities. | **UNRESTRICTED** |

---

## 4. Taxonomic Distinctions in Security Architecture

To prevent misleading claims in documentation, the following four concepts must be clearly separated:

1. **Capability Declaration (Implemented):**
   - In `projects.py`, `ModelManifest.code_isolation_required: True` causes `check_model_capabilities` to emit `Arbitrary code isolation: Required before execution`.
   - *Status:* This is an advisory metadata label for users; it does not alter execution mechanics.
2. **Exception Containment (Implemented):**
   - In `plugins.py`, `try: ... except Exception as exc: return ModelExecutionResult(..., error_message=str(exc))`.
   - *Status:* This is standard application fault tolerance; it prevents a single runtime error from terminating the process. It does not prevent malicious actions or memory exhaustion.
3. **Subprocess Execution (Not Implemented):**
   - Spawning a separate Python subprocess via `multiprocessing` or `subprocess.Popen` with dropped privileges (`setuid`/`setgid`).
   - *Status:* Not implemented.
4. **Operating System Sandboxing (Not Implemented):**
   - Isolating execution via Linux namespaces, cgroups, seccomp-BPF filters, gVisor, Firecracker microVMs, or rootless Docker containers.
   - *Status:* Not implemented.

---

## 5. Security Model Classification & Threat Context

- **Local Quantitative Research Context (Current Use Case):**
  - When the developer runs FragilityShield locally on their own workstation to test their own quantitative models, in-process execution is normal, low-friction, and acceptable.
- **Hosted / Multi-Tenant / Web API Context (Future SaaS Deployment):**
  - If FragilityShield is exposed over a public network where external users can upload or register arbitrary Python code, the current architecture represents a **Critical Remote Code Execution (RCE) vulnerability by design**.
  - No untrusted Python code must be executed in the main API runtime.

---

## 6. Required Architectural Security Controls

Before any multi-tenant deployment, FragilityShield must implement:
1. **Isolated Worker Protocol:** Replace in-process `plugin.execute()` with an abstract worker interface (`WorkerBackend`).
2. **Containerized Worker Service:** Untrusted model adapters must run in disposable, ephemeral containers with:
   - Read-only root filesystem.
   - Network access disabled (`--network none`).
   - Hard memory cap (e.g. `--memory 512m`).
   - Non-root user (`USER nobody`).
   - Strict execution timeout enforcement (5.0s kill signal).
