"""Adversarial security tests for Third-Party Plugin Sandbox Isolation (Phase 5 & Phase 12.3).

Verifies:
1. Plugin manifest validation and strict capability allowlist enforcement.
2. Resource boundary definitions (memory, CPU, PIDs, timeout, payload size).
3. Fail-closed behavior: In the absence of an OS container/gVisor sandbox runtime,
   untrusted third-party plugin execution is STRICTLY BLOCKED (raises SandboxUnavailableError).
4. Prevention of in-process fallback: Untrusted code is NEVER silently executed on host.
5. Trusted first-party built-in plugins continue to execute without regression.
"""

from __future__ import annotations

import pytest

from fragility_engine.plugin_sandbox import (
    ALLOWED_PLUGIN_CAPABILITIES,
    IsolatedWorkerController,
    PluginManifest,
    PluginValidationError,
    SandboxExecutionResult,
    SandboxResourceLimits,
    SandboxUnavailableError,
)
from fragility_engine.plugins import (
    HistoricalSimulationPlugin,
    ParametricGaussianPlugin,
    PluginRegistry,
    get_default_registry,
)


class TestPluginManifestValidation:
    """Tests manifest schema, identifier validation, and capability allowlisting."""

    def test_valid_manifest_creation(self) -> None:
        """Verify compliant manifest is created successfully."""
        manifest = PluginManifest(
            plugin_id="community.tail_risk_t",
            name="Community Student-t Estimator",
            version="1.2.0",
            entry_point="custom_pkg.estimator",
            requested_capabilities=("dataset:read", "result:return"),
            hash_digest="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )
        assert manifest.plugin_id == "community.tail_risk_t"
        assert set(manifest.requested_capabilities) == {"dataset:read", "result:return"}

    def test_reject_unauthorized_capabilities(self) -> None:
        """Verify plugin requesting unauthorized capabilities (e.g. network egress) is rejected."""
        with pytest.raises(PluginValidationError, match="unauthorized capabilities:.*network:egress"):
            PluginManifest(
                plugin_id="malicious.exfiltrator",
                name="Malicious Plugin",
                version="1.0.0",
                entry_point="exploit.run",
                requested_capabilities=("dataset:read", "network:egress"),
                hash_digest="abc123",
            )

        with pytest.raises(PluginValidationError, match="unauthorized capabilities:.*host:shell"):
            PluginManifest(
                plugin_id="malicious.shell",
                name="Shell Plugin",
                version="1.0.0",
                entry_point="exploit.run",
                requested_capabilities=("host:shell",),
                hash_digest="abc123",
            )

    def test_reject_invalid_plugin_identifiers(self) -> None:
        """Verify path traversal or malformed characters in plugin_id are rejected."""
        with pytest.raises(PluginValidationError, match="Invalid plugin_id"):
            PluginManifest(
                plugin_id="../../etc/passwd",
                name="Traversal Plugin",
                version="1.0.0",
                entry_point="exploit.run",
                requested_capabilities=("dataset:read",),
                hash_digest="abc",
            )

        with pytest.raises(PluginValidationError, match="Invalid plugin_id"):
            PluginManifest(
                plugin_id="plugin with spaces!",
                name="Invalid ID",
                version="1.0.0",
                entry_point="test.run",
                requested_capabilities=("dataset:read",),
                hash_digest="abc",
            )


class TestFailClosedSandboxEnforcement:
    """Adversarial tests verifying that missing sandbox runtime FAILS CLOSED."""

    def test_untrusted_plugin_fails_closed_when_runtime_missing(self) -> None:
        """Verify untrusted execution raises SandboxUnavailableError and NEVER falls back to host execution."""
        controller = IsolatedWorkerController(container_runtime_path="/nonexistent/docker/path")
        assert controller.is_sandbox_available() is False

        manifest = PluginManifest(
            plugin_id="thirdparty.arbitrary_code",
            name="Untrusted Code",
            version="1.0.0",
            entry_point="untrusted.module",
            requested_capabilities=("dataset:read", "result:return"),
            hash_digest="1234567890abcdef",
        )

        with pytest.raises(SandboxUnavailableError, match="BLOCKED on host.*No isolated container runtime"):
            controller.execute_untrusted(
                manifest=manifest,
                input_data={"test": 123},
                tenant_id="tenant_123",
                execution_id="exec_999",
            )

    def test_registry_untrusted_block_integration(self) -> None:
        """Verify PluginRegistry blocks untrusted execution with PermissionError when in-process execution is attempted."""
        registry = PluginRegistry(enforce_trusted_execution=True)

        plugin = HistoricalSimulationPlugin()
        # Explicitly register as untrusted
        registry.register(plugin, overwrite=True, trusted=False)
        assert registry.is_trusted(plugin.metadata.plugin_id) is False

        with pytest.raises(PermissionError, match="blocked on unisolated host runtime"):
            registry.execute_plugin(plugin.metadata.plugin_id, [-0.01, 0.02, -0.03])

    def test_builtin_plugins_execute_safely(self) -> None:
        """Verify built-in first-party plugins continue to run safely in-process."""
        registry = get_default_registry()
        assert registry.is_trusted("builtin.historical_simulation") is True
        assert registry.is_trusted("builtin.parametric_gaussian") is True

        returns = [-0.01, 0.02, 0.01, -0.02, 0.03]
        res_hist = registry.execute_plugin("builtin.historical_simulation", returns)
        res_param = registry.execute_plugin("builtin.parametric_gaussian", returns)

        assert res_hist.metrics["var_95"] > 0.0
        assert res_param.metrics["var_95"] > 0.0
        assert res_hist.execution_time_ms >= 0.0


class TestSandboxResourceLimits:
    """Verifies default resource bounds for sandbox workers."""

    def test_default_resource_limits(self) -> None:
        limits = SandboxResourceLimits()
        assert limits.max_memory_mb == 256
        assert limits.max_cpu_cores == 1.0
        assert limits.timeout_seconds == 5.0
        assert limits.max_pids == 32
        assert limits.max_output_bytes == 1_048_576  # 1 MB
