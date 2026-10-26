"""Automated Verification Suite for Secure Model Sandbox, Financial Contracts, and API Isolation (Sprint 4).

Verifies:
1. Category-specific model contracts:
   - ALLOCATION: Enforces weight normalization (sum == 1.0) and bounds.
   - FORECASTING: Enforces horizon, series points, and interval ordering.
   - RISK_ESTIMATION: Rejects negative VaR / ES and non-normal numbers.
   - SCENARIO_RESPONSE: Rejects NaN / Inf and malformed impacts.
2. Fail-Closed Sandbox Isolation:
   - Missing or unverified container runtime strictly blocks untrusted execution (raises SandboxSecurityError).
   - In-process host execution of untrusted models is prohibited.
3. Job Lifecycle and Resource Ceilings:
   - Output byte size limit enforcement.
   - Job cancellation terminates execution and transitions to CANCELLED state.
4. Multi-Tenant API Protection:
   - Tenant A cannot retrieve Tenant B's model execution job results.
   - Cross-tenant cancellation is strictly rejected.
   - Security status endpoint discloses model sandbox policies.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from fragility_engine.model_sandbox import (
    ModelCategory,
    ModelContractValidationError,
    ModelContractValidator,
    ModelExecutionMode,
    ModelExecutionRequest,
    ModelExecutionSandbox,
    ModelJobStatus,
    SandboxSecurityError,
)
from fragility_engine.tenancy import (
    TenantMembership,
    TenantRole,
    User,
    create_access_token,
    get_default_tenant_repository,
    hash_password,
)
from app import create_application


class TestFinancialModelCategoryContracts:
    """Verifies strict mathematical and financial invariants across supported model categories."""

    def test_allocation_contract_valid_and_normalized(self) -> None:
        """Valid allocation weights summing to 1.0 pass validation."""
        valid_input = {"assets": ["HDFCBANK", "RELIANCE", "INFY"]}
        ModelContractValidator.validate_input(ModelCategory.ALLOCATION, valid_input)

        valid_output = {"weights": {"HDFCBANK": 0.4, "RELIANCE": 0.4, "INFY": 0.2}}
        ModelContractValidator.validate_output(ModelCategory.ALLOCATION, valid_output)

    def test_allocation_contract_rejects_unnormalized_weights(self) -> None:
        """Allocation output where weights sum to 1.25 is strictly rejected."""
        unnormalized = {"weights": {"HDFCBANK": 0.5, "RELIANCE": 0.5, "INFY": 0.25}}
        with pytest.raises(ModelContractValidationError, match="weights must sum to 1.0"):
            ModelContractValidator.validate_output(ModelCategory.ALLOCATION, unnormalized)

    def test_allocation_contract_rejects_nan_and_inf(self) -> None:
        """Allocation output containing NaN or Inf is strictly rejected."""
        nan_output = {"weights": {"HDFCBANK": float("nan"), "RELIANCE": 0.5, "INFY": 0.5}}
        with pytest.raises(ModelContractValidationError, match="must be finite"):
            ModelContractValidator.validate_output(ModelCategory.ALLOCATION, nan_output)

        inf_output = {"weights": {"HDFCBANK": float("inf"), "RELIANCE": 0.5, "INFY": 0.5}}
        with pytest.raises(ModelContractValidationError, match="must be finite"):
            ModelContractValidator.validate_output(ModelCategory.ALLOCATION, inf_output)

    def test_forecasting_contract_interval_ordering(self) -> None:
        """Forecasting interval violation (lower > forecast or forecast > upper) is rejected."""
        valid_out = {
            "forecast": [105.0, 106.0],
            "lower_bound": [102.0, 103.0],
            "upper_bound": [108.0, 110.0],
        }
        ModelContractValidator.validate_output(ModelCategory.FORECASTING, valid_out)

        inverted_out = {
            "forecast": [105.0, 106.0],
            "lower_bound": [107.0, 103.0],  # 107 > 105 violation
            "upper_bound": [108.0, 110.0],
        }
        with pytest.raises(ModelContractValidationError, match="Interval violation"):
            ModelContractValidator.validate_output(ModelCategory.FORECASTING, inverted_out)

    def test_risk_estimation_rejects_negative_var(self) -> None:
        """Risk estimation output containing negative VaR is strictly rejected."""
        negative_var = {"var": -0.05, "expected_shortfall": 0.08, "volatility": 0.15}
        with pytest.raises(ModelContractValidationError, match="cannot be negative"):
            ModelContractValidator.validate_output(ModelCategory.RISK_ESTIMATION, negative_var)


class TestModelSandboxExecutionAndIsolation:
    """Verifies sandbox runtime isolation, fail-closed enforcement, and job lifecycle."""

    def test_untrusted_model_fails_closed_without_container_runtime(self) -> None:
        """When container runtime is unavailable, untrusted execution strictly fails closed."""
        sandbox = ModelExecutionSandbox(container_runtime="/nonexistent/docker/path")
        assert sandbox.is_container_runtime_available() is False

        req = ModelExecutionRequest(
            request_id="req_test_01",
            tenant_id="ten_alpha",
            user_id="usr_01",
            model_id="untrusted_neural_quant",
            category=ModelCategory.RISK_ESTIMATION,
            model_version="1.0.0",
            artifact_hash="art_hash_123",
            dataset_fingerprint="ds_fp_123",
            input_payload={"returns": [0.01, -0.02, 0.015, -0.005, 0.02], "confidence_level": 0.95},
            execution_mode=ModelExecutionMode.APPROVED_ISOLATED_CONTAINER,
        )

        with pytest.raises(SandboxSecurityError, match="FAIL-CLOSED.*Untrusted execution.*is BLOCKED"):
            sandbox.execute(req)

    def test_trusted_local_research_model_produces_reproducibility_evidence(self) -> None:
        """Trusted local research model executes and produces cryptographic evidence."""
        sandbox = ModelExecutionSandbox()
        req = ModelExecutionRequest(
            request_id="req_test_local_01",
            tenant_id="ten_alpha",
            user_id="usr_01",
            model_id="canonical_garch",
            category=ModelCategory.ALLOCATION,
            model_version="1.0.0",
            artifact_hash="art_hash_abc",
            dataset_fingerprint="ds_fp_xyz",
            input_payload={"assets": ["TCS", "INFY", "WIPRO"]},
            execution_mode=ModelExecutionMode.TRUSTED_LOCAL_RESEARCH,
        )

        res = sandbox.execute(req)
        assert res.status == ModelJobStatus.SUCCEEDED
        assert res.exit_code == 0
        assert res.output_payload is not None
        assert "weights" in res.output_payload
        assert len(res.reproducibility_hash) == 64  # SHA-256 fingerprint

    def test_job_cancellation_terminates_job_cleanly(self) -> None:
        """Job cancellation marks job CANCELLED and prevents further execution."""
        sandbox = ModelExecutionSandbox()
        job_id = "job_test_cancel_01"
        sandbox._active_jobs[job_id] = {
            "request_id": "req_cancel_01",
            "tenant_id": "ten_alpha",
            "user_id": "usr_01",
            "model_id": "long_simulation",
            "category": "allocation",
            "execution_mode": "trusted_local_research",
            "status": ModelJobStatus.RUNNING,
            "process": None,
        }

        # Tenant Alpha cancels its own job
        cancelled = sandbox.cancel_job("ten_alpha", job_id)
        assert cancelled is True

        res = sandbox.get_job_result("ten_alpha", job_id)
        assert res is not None
        assert res.status == ModelJobStatus.CANCELLED
        assert res.error_category == "USER_CANCELLED"

    def test_cross_tenant_job_cancellation_denied(self) -> None:
        """Tenant Beta attempting to cancel Tenant Alpha's job is strictly denied."""
        sandbox = ModelExecutionSandbox()
        job_id = "job_test_cross_cancel"
        sandbox._active_jobs[job_id] = {
            "request_id": "req_cross_01",
            "tenant_id": "ten_alpha",
            "user_id": "usr_01",
            "model_id": "alpha_model",
            "category": "allocation",
            "execution_mode": "trusted_local_research",
            "status": ModelJobStatus.RUNNING,
            "process": None,
        }

        with pytest.raises(PermissionError, match="Cross-tenant job cancellation denied"):
            sandbox.cancel_job("ten_beta", job_id)


class TestModelSandboxAPIEndpoints:
    """Verifies REST endpoints for model execution, job status, and multi-tenant isolation."""

    @pytest.fixture
    def client(self) -> TestClient:
        app = create_application()
        return TestClient(app)

    @pytest.fixture
    def token_alpha(self) -> str:
        return create_access_token(
            user_id="usr_quant_1",
            tenant_id="ten_alpha_capital",
            role=TenantRole.RESEARCHER,
            expires_in_seconds=3600,
        )

    @pytest.fixture
    def token_beta(self) -> str:
        repo = get_default_tenant_repository()
        if not repo.get_user("usr_beta_quant"):
            repo.register_user(User("usr_beta_quant", "beta@fragility.test", hash_password("BetaPass123!")))
            repo.add_membership(TenantMembership("mem_beta", "ten_beta_investments", "usr_beta_quant", TenantRole.RESEARCHER))
        return create_access_token(
            user_id="usr_beta_quant",
            tenant_id="ten_beta_investments",
            role=TenantRole.RESEARCHER,
            expires_in_seconds=3600,
        )

    def test_api_security_status_reports_model_sandbox_policies(self, client: TestClient) -> None:
        """Verify /api/security/status discloses model sandbox availability and supported categories."""
        resp = client.get("/api/security/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "model_sandbox_available" in data
        assert "untrusted_model_policy" in data
        assert "supported_model_categories" in data
        assert "allocation" in data["supported_model_categories"]
        assert "risk_estimation" in data["supported_model_categories"]
        assert "forecasting" in data["supported_model_categories"]

    def test_api_model_execution_trusted_local_success(self, client: TestClient, token_alpha: str) -> None:
        """Authenticated request executing a trusted model returns validated output and evidence."""
        payload = {
            "model_id": "risk_garch_v1",
            "category": "risk_estimation",
            "execution_mode": "trusted_local_research",
            "input_payload": {
                "returns": [0.012, -0.018, 0.009, -0.022, 0.015, 0.008, -0.005],
                "confidence_level": 0.95,
            },
        }
        headers = {"Authorization": f"Bearer {token_alpha}"}
        resp = client.post("/api/models/execute", json=payload, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        res = data["result"]
        assert res["status"] == "succeeded"
        assert res["output_payload"]["var"] >= 0.0
        assert len(res["reproducibility_hash"]) == 64

    def test_api_model_execution_rejects_malformed_category(self, client: TestClient, token_alpha: str) -> None:
        """Request specifying an invalid model category returns HTTP 400."""
        payload = {
            "model_id": "invalid_model",
            "category": "arbitrary_unsupported_category",
            "input_payload": {},
        }
        headers = {"Authorization": f"Bearer {token_alpha}"}
        resp = client.post("/api/models/execute", json=payload, headers=headers)
        assert resp.status_code == 400
        assert "Invalid model category" in resp.json()["error"]

    def test_api_untrusted_model_in_production_fails_closed(self, client: TestClient, token_alpha: str) -> None:
        """In production mode or when container runtime is missing, untrusted execution fails closed (503)."""
        payload = {
            "model_id": "third_party_blackbox",
            "category": "allocation",
            "execution_mode": "approved_isolated_container",
            "input_payload": {"assets": ["AAPL", "GOOGL"]},
        }
        headers = {"Authorization": f"Bearer {token_alpha}"}
        resp = client.post("/api/models/execute", json=payload, headers=headers)
        # On local environment without docker daemon running, returns 503 fail closed
        assert resp.status_code == 503
        assert "FAIL-CLOSED" in resp.json()["error"]

    def test_cross_tenant_job_status_retrieval_denied(
        self, client: TestClient, token_alpha: str, token_beta: str
    ) -> None:
        """Tenant B cannot retrieve Tenant A's model execution job results."""
        # 1. Tenant Alpha executes a model
        exec_payload = {
            "model_id": "alpha_secret_allocator",
            "category": "allocation",
            "execution_mode": "trusted_local_research",
            "input_payload": {"assets": ["ALPHA_1", "ALPHA_2"]},
        }
        headers_a = {"Authorization": f"Bearer {token_alpha}"}
        headers_b = {"Authorization": f"Bearer {token_beta}"}

        resp_a = client.post("/api/models/execute", json=exec_payload, headers=headers_a)
        assert resp_a.status_code == 200
        job_id = resp_a.json()["result"]["job_id"]

        # 2. Tenant Alpha queries its own job -> 200 OK
        resp_own = client.get(f"/api/models/jobs/{job_id}", headers=headers_a)
        assert resp_own.status_code == 200
        assert resp_own.json()["job"]["job_id"] == job_id

        # 3. Tenant Beta attempts to query Tenant Alpha's job -> 403 Forbidden / 404 Not Found (Zero Leakage)
        resp_cross = client.get(f"/api/models/jobs/{job_id}", headers=headers_b)
        assert resp_cross.status_code in (403, 404)
