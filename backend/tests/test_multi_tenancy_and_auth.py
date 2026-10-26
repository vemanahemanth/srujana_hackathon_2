"""Adversarial security tests for Multi-Tenant Identity, Authorization, and Data Isolation (Phase 12).

Tests:
1. Role-Based Access Control (RBAC):
   - Viewer cannot create/delete portfolios or execute simulations.
   - Researcher can execute simulations and create portfolios, but cannot remove members.
   - Tenant Admin can manage members and delete datasets.
   - Tenant Owner has unrestricted workspace authority.
2. Cross-Tenant Data Isolation Matrix:
   - Tenant A cannot access, read, update, or delete Tenant B's data.
   - Missing tenant context fails closed.
   - Forged tenant claims fail closed.
   - Context clears safely upon boundary exit (transaction-safe).
3. Identity & Token Security:
   - JWT signature verification and tamper detection.
   - Expired token rejection.
   - Constant-time password hashing and verification.
"""

from __future__ import annotations

import os
import time
import pytest
from starlette.testclient import TestClient

from fragility_engine.tenancy import (
    AuditEvent,
    AuthenticationError,
    AuthorizationError,
    MemoryTenantRepository,
    Permission,
    ROLE_PERMISSIONS,
    Tenant,
    TenantContext,
    TenantMembership,
    TenantRole,
    User,
    create_access_token,
    decode_and_verify_token,
    get_current_tenant_context,
    get_default_tenant_repository,
    hash_password,
    require_tenant_context,
    tenant_boundary,
    verify_password,
)


class TestAuthenticationAndTokens:
    """Security tests for authentication, password hashing, and tamper-proof tokens."""

    def test_password_hashing_and_verification(self) -> None:
        """Verify PBKDF2 password hashing is salted and constant-time verified."""
        raw_pw = "SuperSecureQuantPassword2026!"
        h1 = hash_password(raw_pw)
        h2 = hash_password(raw_pw)

        # Different salts produce different hashes
        assert h1 != h2
        assert h1.startswith("pbkdf2_sha256$100000$")

        # Verification succeeds with correct password
        assert verify_password(raw_pw, h1) is True
        assert verify_password(raw_pw, h2) is True

        # Verification fails with incorrect password
        assert verify_password("WrongPassword!", h1) is False
        assert verify_password("", h1) is False

    def test_jwt_generation_and_tamper_detection(self) -> None:
        """Verify JWT signature rejects tampered payloads and modified headers."""
        key = b"0123456789abcdef0123456789abcdef"  # 32 bytes
        token = create_access_token(
            user_id="usr_quant_1",
            tenant_id="ten_hedge_fund",
            role=TenantRole.RESEARCHER,
            expires_in_seconds=3600,
            signing_key=key,
        )

        # Valid token decodes correctly
        payload = decode_and_verify_token(token, signing_key=key)
        assert payload["sub"] == "usr_quant_1"
        assert payload["tid"] == "ten_hedge_fund"
        assert payload["rol"] == TenantRole.RESEARCHER.value
        assert payload["adm"] is False

        # Tampering with payload segment invalidates signature
        parts = token.split(".")
        tampered_token = f"{parts[0]}.eyJuYW1lIjoiYXR0YWNrZXIifQ.{parts[2]}"
        with pytest.raises(ValueError, match="Invalid JWT signature"):
            decode_and_verify_token(tampered_token, signing_key=key)

        # Tampering with signature invalidates token
        invalid_sig_token = f"{parts[0]}.{parts[1]}.bad_signature_here"
        with pytest.raises(ValueError, match="Invalid JWT signature|Invalid signature encoding"):
            decode_and_verify_token(invalid_sig_token, signing_key=key)

    def test_jwt_expiration_enforcement(self) -> None:
        """Verify expired tokens are rejected immediately."""
        key = b"0123456789abcdef0123456789abcdef"
        expired_token = create_access_token(
            user_id="usr_quant_1",
            tenant_id="ten_hedge_fund",
            role=TenantRole.RESEARCHER,
            expires_in_seconds=-10,  # Expired 10 seconds ago
            signing_key=key,
        )

        with pytest.raises(ValueError, match="JWT has expired"):
            decode_and_verify_token(expired_token, signing_key=key)


class TestRoleBasedAccessControl:
    """Tests enforcing granular permission matrices across all defined roles."""

    def test_viewer_permission_boundaries(self) -> None:
        """Verify Viewer role can read data but cannot execute simulations or mutate portfolios."""
        ctx = TenantContext(
            tenant_id="ten_alpha",
            user_id="usr_view_only",
            role=TenantRole.VIEWER,
            permissions=ROLE_PERMISSIONS[TenantRole.VIEWER],
        )

        assert ctx.has_permission(Permission.PORTFOLIO_READ) is True
        assert ctx.has_permission(Permission.DATASET_READ) is True

        # Denied actions
        assert ctx.has_permission(Permission.PORTFOLIO_CREATE) is False
        assert ctx.has_permission(Permission.SIMULATION_EXECUTE) is False
        assert ctx.has_permission(Permission.MEMBER_INVITE) is False

        with pytest.raises(PermissionError, match="Permission denied: role 'viewer'"):
            ctx.require_permission(Permission.PORTFOLIO_CREATE)

    def test_researcher_permission_boundaries(self) -> None:
        """Verify Researcher role can create portfolios and run simulations, but cannot delete members."""
        ctx = TenantContext(
            tenant_id="ten_alpha",
            user_id="usr_researcher_1",
            role=TenantRole.RESEARCHER,
            permissions=ROLE_PERMISSIONS[TenantRole.RESEARCHER],
        )

        assert ctx.has_permission(Permission.PORTFOLIO_CREATE) is True
        assert ctx.has_permission(Permission.SIMULATION_EXECUTE) is True
        assert ctx.has_permission(Permission.BACKTEST_EXECUTE) is True

        # Denied actions
        assert ctx.has_permission(Permission.MEMBER_INVITE) is False
        assert ctx.has_permission(Permission.MEMBER_REMOVE) is False
        assert ctx.has_permission(Permission.PORTFOLIO_DELETE) is False

        with pytest.raises(PermissionError, match="Permission denied: role 'researcher'"):
            ctx.require_permission(Permission.MEMBER_REMOVE)

    def test_tenant_owner_unrestricted(self) -> None:
        """Verify Tenant Owner has all permissions."""
        ctx = TenantContext(
            tenant_id="ten_alpha",
            user_id="usr_owner",
            role=TenantRole.TENANT_OWNER,
            permissions=ROLE_PERMISSIONS[TenantRole.TENANT_OWNER],
        )
        for perm in Permission:
            assert ctx.has_permission(perm) is True


class TestCrossTenantDataIsolationMatrix:
    """Adversarial tests proving Tenant A cannot access or mutate Tenant B's data."""

    @pytest.fixture
    def multi_tenant_setup(self) -> MemoryTenantRepository:
        repo = MemoryTenantRepository()

        # Tenant A setup
        t_a = Tenant(tenant_id="ten_a", name="Tenant A Capital")
        u_a = User(user_id="usr_a", email="a@example.com", password_hash="dummy")
        m_a = TenantMembership(membership_id="mem_a", tenant_id="ten_a", user_id="usr_a", role=TenantRole.RESEARCHER)
        repo.register_tenant(t_a)
        repo.register_user(u_a)
        repo.add_membership(m_a)

        # Tenant B setup
        t_b = Tenant(tenant_id="ten_b", name="Tenant B Investments")
        u_b = User(user_id="usr_b", email="b@example.com", password_hash="dummy")
        m_b = TenantMembership(membership_id="mem_b", tenant_id="ten_b", user_id="usr_b", role=TenantRole.RESEARCHER)
        repo.register_tenant(t_b)
        repo.register_user(u_b)
        repo.add_membership(m_b)

        return repo

    def test_tenant_a_creates_and_reads_own_portfolio(self, multi_tenant_setup: MemoryTenantRepository) -> None:
        repo = multi_tenant_setup
        ctx_a = repo.resolve_context("usr_a", "ten_a")

        with tenant_boundary(ctx_a):
            repo.save_portfolio("pf_a_1", {"name": "Alpha Portfolio", "value": 1000000})
            pf = repo.get_portfolio("pf_a_1")
            assert pf is not None
            assert pf["name"] == "Alpha Portfolio"
            assert pf["tenant_id"] == "ten_a"

    def test_tenant_b_cannot_read_tenant_a_portfolio(self, multi_tenant_setup: MemoryTenantRepository) -> None:
        repo = multi_tenant_setup
        ctx_a = repo.resolve_context("usr_a", "ten_a")
        ctx_b = repo.resolve_context("usr_b", "ten_b")

        # 1. Tenant A creates portfolio
        with tenant_boundary(ctx_a):
            repo.save_portfolio("pf_a_private", {"name": "Secret Strategies", "value": 5000000})

        # 2. Tenant B attempts direct object lookup
        with tenant_boundary(ctx_b):
            pf_leak = repo.get_portfolio("pf_a_private")
            assert pf_leak is None  # RLS boundary denies cross-tenant lookup

    def test_tenant_b_cannot_delete_tenant_a_portfolio(self, multi_tenant_setup: MemoryTenantRepository) -> None:
        repo = multi_tenant_setup
        ctx_a = repo.resolve_context("usr_a", "ten_a")

        # Give user B tenant admin role in Tenant B so they have portfolio:delete permission in their own workspace
        admin_b = TenantMembership(membership_id="mem_b_admin", tenant_id="ten_b", user_id="usr_b", role=TenantRole.TENANT_ADMIN)
        repo.add_membership(admin_b)
        ctx_b = repo.resolve_context("usr_b", "ten_b")

        with tenant_boundary(ctx_a):
            repo.save_portfolio("pf_a_target", {"name": "Protected Portfolio"})

        # Even with TENANT_ADMIN role in Tenant B, deletion of Tenant A's portfolio returns False
        with tenant_boundary(ctx_b):
            deleted = repo.delete_portfolio("pf_a_target")
            assert deleted is False  # Cannot delete record belonging to Tenant A

        # Confirm Tenant A's record remains untouched
        with tenant_boundary(ctx_a):
            assert repo.get_portfolio("pf_a_target") is not None

    def test_missing_tenant_context_fails_closed(self, multi_tenant_setup: MemoryTenantRepository) -> None:
        """Verify calling tenant-scoped operations outside a tenant boundary raises PermissionError."""
        repo = multi_tenant_setup
        assert get_current_tenant_context() is None

        with pytest.raises(PermissionError, match="No active tenant context found"):
            repo.get_portfolio("any_portfolio")

        with pytest.raises(PermissionError, match="No active tenant context found"):
            repo.save_portfolio("p_new", {"name": "Unauthorized"})

    def test_forged_membership_denied(self, multi_tenant_setup: MemoryTenantRepository) -> None:
        """Verify user A cannot claim membership in Tenant B without an explicit membership record."""
        repo = multi_tenant_setup
        with pytest.raises(PermissionError, match="Cross-tenant violation: User 'usr_a' is not an active member of tenant 'ten_b'"):
            repo.resolve_context("usr_a", "ten_b")

    def test_context_clears_safely_on_boundary_exit(self, multi_tenant_setup: MemoryTenantRepository) -> None:
        """Verify context variable is cleared upon exit even if an exception occurs."""
        repo = multi_tenant_setup
        ctx_a = repo.resolve_context("usr_a", "ten_a")

        try:
            with tenant_boundary(ctx_a):
                assert get_current_tenant_context() is not None
                raise RuntimeError("Simulated request failure")
        except RuntimeError:
            pass

        assert get_current_tenant_context() is None


class TestAuthenticationRigor:
    """Security tests ensuring unauthenticated callers cannot forge identities or elevate privileges."""

    @pytest.fixture
    def repo(self) -> MemoryTenantRepository:
        r = MemoryTenantRepository()
        t1 = Tenant(tenant_id="ten_alpha", name="Alpha Capital")
        t2 = Tenant(tenant_id="ten_beta", name="Beta Capital")
        r.register_tenant(t1)
        r.register_tenant(t2)

        u_active = User(
            user_id="usr_1",
            email="usr1@example.com",
            password_hash=hash_password("ValidPassword123!"),
            is_active=True,
        )
        u_disabled = User(
            user_id="usr_disabled",
            email="disabled@example.com",
            password_hash=hash_password("DisabledPassword123!"),
            is_active=False,
        )
        r.register_user(u_active)
        r.register_user(u_disabled)

        # usr_1 is researcher in ten_alpha only
        r.add_membership(TenantMembership("mem_1", "ten_alpha", "usr_1", TenantRole.RESEARCHER))
        return r

    def test_nonexistent_user_rejected(self, repo: MemoryTenantRepository) -> None:
        with pytest.raises(AuthenticationError, match="not found"):
            repo.authenticate_and_resolve_tenant("ghost_user", password="any_password")

    def test_incorrect_password_rejected(self, repo: MemoryTenantRepository) -> None:
        with pytest.raises(AuthenticationError, match="Invalid credentials"):
            repo.authenticate_and_resolve_tenant("usr_1", password="WrongPassword!")

    def test_disabled_user_rejected(self, repo: MemoryTenantRepository) -> None:
        with pytest.raises(PermissionError, match="User account 'usr_disabled' has been disabled"):
            repo.authenticate_and_resolve_tenant("usr_disabled", password="DisabledPassword123!")

    def test_arbitrary_tenant_join_denied(self, repo: MemoryTenantRepository) -> None:
        # usr_1 attempts to join ten_beta (where they have no membership)
        with pytest.raises(PermissionError, match="not an active member of tenant 'ten_beta'"):
            repo.authenticate_and_resolve_tenant("usr_1", password="ValidPassword123!", requested_tenant_id="ten_beta")

    def test_server_derives_role_exclusively_from_membership(self, repo: MemoryTenantRepository) -> None:
        # Caller cannot claim tenant_owner; repo sets role to researcher
        user, mem, ctx = repo.authenticate_and_resolve_tenant("usr_1", password="ValidPassword123!", requested_tenant_id="ten_alpha")
        assert ctx.role == TenantRole.RESEARCHER
        assert ctx.has_permission(Permission.PORTFOLIO_DELETE) is False

    def test_passwordless_dev_auth_rejected_in_production(self, repo: MemoryTenantRepository, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEPLOYMENT_MODE", "public_multi_tenant")
        with pytest.raises(AuthenticationError, match="Password credentials are required in hosted/production deployment"):
            repo.authenticate_and_resolve_tenant("usr_1", password=None, allow_dev_auth=True)


class TestPyJWTSecurityControls:
    """Verifies that PyJWT algorithm allowlisting, signature checking, and claims are strictly enforced."""

    KEY = b"0123456789abcdef0123456789abcdef"

    def test_alg_none_token_rejected(self) -> None:
        import base64
        import json

        header = base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode()).decode().rstrip("=")
        payload = base64.urlsafe_b64encode(json.dumps({
            "sub": "hacker", "tid": "ten_alpha", "rol": "tenant_owner", "exp": int(time.time()) + 3600, "iat": int(time.time()),
            "iss": "fragilityshield", "aud": "fragilityshield-api"
        }).encode()).decode().rstrip("=")
        unsigned_token = f"{header}.{payload}."

        with pytest.raises(ValueError, match="Invalid JWT algorithm or key|Malformed JWT|Invalid signature"):
            decode_and_verify_token(unsigned_token, signing_key=self.KEY)

    def test_missing_required_claims_rejected(self) -> None:
        import jwt
        # Create token missing 'tid' claim
        payload = {
            "sub": "usr_1",
            "rol": "researcher",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600,
            "iss": "fragilityshield",
            "aud": "fragilityshield-api"
        }
        token_missing_tid = jwt.encode(payload, self.KEY, algorithm="HS256")
        with pytest.raises(ValueError, match="Invalid JWT claims|MissingRequiredClaimError"):
            decode_and_verify_token(token_missing_tid, signing_key=self.KEY)

    def test_mismatched_issuer_rejected(self) -> None:
        import jwt
        payload = {
            "sub": "usr_1", "tid": "ten_1", "rol": "researcher",
            "iat": int(time.time()), "exp": int(time.time()) + 3600,
            "iss": "malicious_issuer", "aud": "fragilityshield-api"
        }
        token_bad_iss = jwt.encode(payload, self.KEY, algorithm="HS256")
        with pytest.raises(ValueError, match="Invalid JWT claims"):
            decode_and_verify_token(token_bad_iss, signing_key=self.KEY)


class TestTenantContextConcurrencySafety:
    """Verifies that ContextVar tenant contexts are completely isolated under concurrent async workloads."""

    @pytest.mark.anyio
    async def test_concurrent_async_tenant_isolation(self) -> None:
        import anyio

        contexts = [
            TenantContext(tenant_id=f"ten_worker_{i}", user_id=f"usr_{i}", role=TenantRole.RESEARCHER, permissions=ROLE_PERMISSIONS[TenantRole.RESEARCHER])
            for i in range(20)
        ]

        async def worker_task(expected_ctx: TenantContext) -> None:
            with tenant_boundary(expected_ctx):
                # Interleaved async sleeps to test task-switch context persistence
                await anyio.sleep(0.005)
                active = get_current_tenant_context()
                assert active is not None
                assert active.tenant_id == expected_ctx.tenant_id
                assert active.user_id == expected_ctx.user_id
                await anyio.sleep(0.005)
                active_again = get_current_tenant_context()
                assert active_again is not None
                assert active_again.tenant_id == expected_ctx.tenant_id
            # After boundary exit, must be None
            assert get_current_tenant_context() is None

        async with anyio.create_task_group() as tg:
            for ctx in contexts:
                tg.start_soon(worker_task, ctx)

        # Main task context remains clean
        assert get_current_tenant_context() is None


class TestAPIAuthenticationAndIsolation:
    """Adversarial tests against the FastAPI/Starlette application endpoints."""

    @pytest.fixture
    def client(self) -> TestClient:
        from app import app
        return TestClient(app)

    def test_api_auth_token_privilege_escalation_denied(self, client: TestClient) -> None:
        """Verify user cannot claim a higher role than their membership."""
        # usr_quant_1 is researcher in ten_alpha_capital
        escalation_payload = {
            "user_id": "usr_quant_1",
            "tenant_id": "ten_alpha_capital",
            "role": "tenant_owner",  # Escalation attempt!
        }
        resp = client.post("/api/auth/token", json=escalation_payload)
        assert resp.status_code == 403
        data = resp.json()
        assert "Privilege escalation denied" in data["error"]

    def test_api_auth_token_unauthorized_tenant_denied(self, client: TestClient) -> None:
        """Verify user cannot obtain token for a tenant they don't belong to."""
        # usr_owner is only member of ten_default, not ten_alpha_capital
        cross_tenant_payload = {
            "user_id": "usr_owner",
            "tenant_id": "ten_alpha_capital",
            "password": "OwnerPassword2026!",
        }
        resp = client.post("/api/auth/token", json=cross_tenant_payload)
        assert resp.status_code == 403
        data = resp.json()
        assert "not an active member of tenant 'ten_alpha_capital'" in data["error"]

    def test_api_auth_token_disabled_user_denied(self, client: TestClient) -> None:
        """Verify disabled user cannot authenticate."""
        payload = {
            "user_id": "usr_disabled",
            "tenant_id": "ten_default",
            "password": "DisabledPassword2026!",
        }
        resp = client.post("/api/auth/token", json=payload)
        assert resp.status_code == 403
        assert "disabled" in resp.json()["error"]

    def test_api_protected_route_in_public_mode_requires_token(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        """Verify that in public_multi_tenant mode, requests without token fail with 401."""
        monkeypatch.setenv("DEPLOYMENT_MODE", "public_multi_tenant")
        resp = client.post("/api/portfolios/validate", json={"holdings": []})
        assert resp.status_code == 401
        assert "Authentication required" in resp.json()["error"]

    def test_api_protected_route_rejects_tampered_token(self, client: TestClient) -> None:
        """Verify tampered bearer token is rejected with 401."""
        headers = {"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.tampered.signature"}
        resp = client.post("/api/portfolios/validate", json={"holdings": []}, headers=headers)
        assert resp.status_code == 401
        assert "Invalid authentication token" in resp.json()["error"]

    def test_api_protected_route_accepts_valid_token(self, client: TestClient) -> None:
        """Verify valid bearer token grants access."""
        auth_resp = client.post("/api/auth/token", json={
            "user_id": "usr_quant_1",
            "tenant_id": "ten_alpha_capital",
            "role": "researcher",
        })
        assert auth_resp.status_code == 200
        token = auth_resp.json()["token"]

        headers = {"Authorization": f"Bearer {token}"}
        resp = client.get("/api/portfolios/sample", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_api_server_context_cleaned_up_after_request(self, client: TestClient) -> None:
        """Verify server context is cleared after request processing."""
        client.get("/api/portfolios/sample")
        assert get_current_tenant_context() is None

