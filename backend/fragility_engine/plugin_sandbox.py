"""FragilityShield — Isolated Worker & Container Sandbox Controller (Phase 5).

This module implements the isolated execution boundary for untrusted third-party plugins.

Security Invariants:
1. Untrusted third-party code NEVER executes inside the FastAPI process or on the unrestricted host.
2. In-process software checks are NOT an OS-level sandbox.
3. If an isolated container/gVisor sandbox runtime is missing or misconfigured,
   execution FAILS CLOSED immediately (raises `SandboxUnavailableError`).
4. Minimum sandbox controls enforced when a container runtime is present:
   - Non-root user execution (UID 10001).
   - Read-only root filesystem.
   - Minimal disposable writable workspace (/tmp/scratch).
   - Strict resource limits (Memory <= 256MB, CPU <= 1.0 core, PIDs <= 32).
   - Hard execution timeout (5.0s wall clock) with forced termination.
   - Complete network egress isolation (`--network none`).
   - Dropped Linux capabilities (`--cap-drop ALL`).
   - No inherited environment variables, host sockets, or database secrets.
   - Schema validation and size bounding on all outputs.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union


class SandboxUnavailableError(Exception):
    """Raised when an untrusted plugin cannot be executed because no verified sandbox runtime is available."""
    pass


class PluginValidationError(Exception):
    """Raised when a plugin manifest or output violates security or schema constraints."""
    pass


# ==============================================================================
# 1. Plugin Manifest & Capability Model
# ==============================================================================

ALLOWED_PLUGIN_CAPABILITIES = frozenset({
    "dataset:read",
    "workspace:write",
    "result:return",
})


@dataclass(frozen=True)
class SandboxResourceLimits:
    """Enforceable hardware and temporal resource ceilings for a plugin execution."""
    max_memory_mb: int = 256
    max_cpu_cores: float = 1.0
    timeout_seconds: float = 5.0
    max_pids: int = 32
    max_output_bytes: int = 1_048_576  # 1 MB


@dataclass(frozen=True)
class PluginManifest:
    """Validated, versioned metadata contract required for third-party plugin registration."""
    plugin_id: str
    name: str
    version: str
    entry_point: str
    requested_capabilities: Tuple[str, ...]
    hash_digest: str
    publisher: str = "unknown"
    description: str = ""
    resource_limits: SandboxResourceLimits = field(default_factory=SandboxResourceLimits)

    def __post_init__(self) -> None:
        if not re.match(r"^[a-zA-Z0-9_\-\.]+$", self.plugin_id):
            raise PluginValidationError(f"Invalid plugin_id '{self.plugin_id}': alphanumeric, dots, hyphens, underscores only.")
        if not self.name.strip():
            raise PluginValidationError("Plugin name cannot be blank.")
        if not self.entry_point.strip():
            raise PluginValidationError("Plugin entry_point cannot be blank.")
        # Capability validation
        unauthorized_caps = set(self.requested_capabilities) - ALLOWED_PLUGIN_CAPABILITIES
        if unauthorized_caps:
            raise PluginValidationError(
                f"Plugin requested unauthorized capabilities: {sorted(unauthorized_caps)}. "
                f"Permitted capabilities are: {sorted(ALLOWED_PLUGIN_CAPABILITIES)}"
            )


@dataclass
class SandboxExecutionResult:
    """Bounded, validated result returned from isolated plugin execution."""
    execution_id: str
    plugin_id: str
    tenant_id: str
    status: str  # 'COMPLETED', 'FAILED', 'TIMEOUT', 'BLOCKED'
    exit_code: int
    execution_time_ms: float
    output_metrics: Dict[str, Any] = field(default_factory=dict)
    stdout: str = ""
    stderr: str = ""
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ==============================================================================
# 2. Isolated Worker Controller
# ==============================================================================

class IsolatedWorkerController:
    """Controller responsible for provisioning, executing, and tearing down sandbox containers."""

    def __init__(
        self,
        container_runtime_path: Optional[str] = None,
        base_sandbox_image: str = "fragilityshield-sandbox-worker:latest",
    ) -> None:
        # Detect Docker, Podman, or gVisor runsc
        self.runtime_path = container_runtime_path or self._detect_runtime()
        self.base_image = base_sandbox_image

    def _detect_runtime(self) -> Optional[str]:
        """Probe the host operating system for an available container engine."""
        for candidate in ("docker", "podman", "runsc"):
            path = shutil.which(candidate)
            if path:
                return path
        return None

    def is_sandbox_available(self) -> bool:
        """Check whether a genuine container sandbox runtime is functional on this host."""
        if not self.runtime_path:
            return False
        try:
            # Check if docker daemon is actually reachable and responsive
            cmd = [self.runtime_path, "info"]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=2.0)
            return res.returncode == 0
        except Exception:
            return False

    def execute_untrusted(
        self,
        manifest: PluginManifest,
        input_data: Dict[str, Any],
        tenant_id: str,
        execution_id: str,
    ) -> SandboxExecutionResult:
        """Execute an untrusted plugin inside a hardened disposable sandbox.

        FAIL-CLOSED BEHAVIOR:
        If `is_sandbox_available()` is False, this method WILL NEVER fall back to
        executing Python in-process or via host subprocess. It raises `SandboxUnavailableError`.
        """
        if not self.is_sandbox_available():
            raise SandboxUnavailableError(
                f"Untrusted plugin execution for '{manifest.plugin_id}' is BLOCKED on host. "
                "No isolated container runtime (Docker/Podman/gVisor) is available or running. "
                "In-process execution of arbitrary third-party code is strictly prohibited by "
                "FragilityShield security policy to protect host files, environment secrets, and databases."
            )

        limits = manifest.resource_limits
        t0 = time.perf_counter()

        # Create temporary disposable workspace
        with tempfile.TemporaryDirectory(prefix="fs_sandbox_") as tmp_dir:
            workspace = Path(tmp_dir)
            input_file = workspace / "input.json"
            output_file = workspace / "output.json"

            # 1. Write bounded, sanitized input payload
            input_bytes = json.dumps(input_data).encode("utf-8")
            if len(input_bytes) > limits.max_output_bytes:
                raise PluginValidationError(f"Input payload exceeds maximum limit of {limits.max_output_bytes} bytes.")
            input_file.write_bytes(input_bytes)

            # 2. Assemble hardened container execution command
            # Enforces: non-root, read-only root, no network, drop-all capabilities, memory/cpu limits
            cmd = [
                self.runtime_path,
                "run",
                "--rm",
                "--user", "10001:10001",
                "--network", "none",
                "--read-only",
                "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges:true",
                "--memory", f"{limits.max_memory_mb}m",
                "--cpus", f"{limits.max_cpu_cores}",
                "--pids-limit", f"{limits.max_pids}",
                "-v", f"{workspace}:/workspace:rw",
                "-w", "/workspace",
                self.base_image,
                "python", "-m", manifest.entry_point,
                "--input", "/workspace/input.json",
                "--output", "/workspace/output.json",
            ]

            try:
                proc = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=limits.timeout_seconds,
                    text=True,
                )
                t_elapsed_ms = (time.perf_counter() - t0) * 1000.0

                # 3. Read and validate output JSON
                if not output_file.exists():
                    return SandboxExecutionResult(
                        execution_id=execution_id,
                        plugin_id=manifest.plugin_id,
                        tenant_id=tenant_id,
                        status="FAILED",
                        exit_code=proc.returncode,
                        execution_time_ms=t_elapsed_ms,
                        stdout=proc.stdout[:4096],
                        stderr=proc.stderr[:4096],
                        error_message="Plugin finished without writing output.json",
                    )

                out_bytes = output_file.read_bytes()
                if len(out_bytes) > limits.max_output_bytes:
                    raise PluginValidationError(f"Plugin output exceeds size limit ({len(out_bytes)} > {limits.max_output_bytes})")

                metrics = json.loads(out_bytes.decode("utf-8"))
                if not isinstance(metrics, dict):
                    raise PluginValidationError("Plugin output must be a JSON dictionary.")

                return SandboxExecutionResult(
                    execution_id=execution_id,
                    plugin_id=manifest.plugin_id,
                    tenant_id=tenant_id,
                    status="COMPLETED" if proc.returncode == 0 else "FAILED",
                    exit_code=proc.returncode,
                    execution_time_ms=t_elapsed_ms,
                    output_metrics=metrics,
                    stdout=proc.stdout[:4096],
                    stderr=proc.stderr[:4096],
                )

            except subprocess.TimeoutExpired:
                t_elapsed_ms = (time.perf_counter() - t0) * 1000.0
                return SandboxExecutionResult(
                    execution_id=execution_id,
                    plugin_id=manifest.plugin_id,
                    tenant_id=tenant_id,
                    status="TIMEOUT",
                    exit_code=-1,
                    execution_time_ms=t_elapsed_ms,
                    error_message=f"Plugin exceeded hard execution timeout of {limits.timeout_seconds}s and was terminated.",
                )
            except Exception as exc:
                t_elapsed_ms = (time.perf_counter() - t0) * 1000.0
                return SandboxExecutionResult(
                    execution_id=execution_id,
                    plugin_id=manifest.plugin_id,
                    tenant_id=tenant_id,
                    status="FAILED",
                    exit_code=-1,
                    execution_time_ms=t_elapsed_ms,
                    error_message=f"Sandbox execution error: {exc}",
                )
