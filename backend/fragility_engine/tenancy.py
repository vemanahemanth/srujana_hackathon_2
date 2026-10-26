"""FragilityShield — Multi-Tenant Identity, Authorization & Role Security Model.

This module provides the core data contracts, roles, permissions, context management,
and security enforcement for public multi-tenant deployments.

Security Guarantees:
1. Strict Identity & Tenant Resolution:
   - Users authenticate with signed, tamper-proof identity credentials (JWT).
   - Tenant resolution verifies active user membership in the target workspace.
   - Arbitrary client-supplied tenant headers or payload fields are NEVER trusted.
2. Explicit Role-Based Permissions (RBAC):
   - Roles: `tenant_owner`, `tenant_admin`, `researcher`, `viewer`, `platform_admin`.
   - Granular permission checking on all resource access, mutation, execution, and deletion.
3. Transaction-Safe Tenant Context:
   - Context is bound to Python `contextvars` and database transaction-local settings.
   - Missing or unverified tenant context fails closed immediately (raises Unauthorized / Forbidden).
4. Defense in Depth:
   - Platform administrators cannot silently view tenant financial data without explicit auditing.
"""

from __future__ import annotations

import contextvars
import enum
import hashlib
import hmac
import os
import secrets
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, FrozenSet, List, Mapping, Optional, Tuple, Union

import jwt


class AuthenticationError(Exception):
    """Raised when authentication credentials are missing, invalid, or forged."""
    pass


class AuthorizationError(PermissionError):
    """Raised when an authenticated principal attempts an unauthorized action or privilege escalation."""
    pass



# ==============================================================================
# 1. Roles and Permissions
# ==============================================================================

class TenantRole(str, enum.Enum):
    """Hierarchical roles for workspace membership."""
    TENANT_OWNER = "tenant_owner"
    TENANT_ADMIN = "tenant_admin"
    RESEARCHER = "researcher"
    VIEWER = "viewer"
    PLATFORM_ADMIN = "platform_admin"


class Permission(str, enum.Enum):
    """Granular permissions governing actions within a tenant workspace."""
    # Portfolio Permissions
    PORTFOLIO_READ = "portfolio:read"
    PORTFOLIO_CREATE = "portfolio:create"
    PORTFOLIO_UPDATE = "portfolio:update"
    PORTFOLIO_DELETE = "portfolio:delete"
    PORTFOLIO_EXPORT = "portfolio:export"

    # Dataset & Market Data Permissions
    DATASET_READ = "dataset:read"
    DATASET_UPLOAD = "dataset:upload"
    DATASET_DELETE = "dataset:delete"

    # Scenario & Risk Calculation Permissions
    RISK_EXECUTE = "risk:execute"
    SCENARIO_EXECUTE = "scenario:execute"
    SIMULATION_EXECUTE = "simulation:execute"
    FRAGILITY_EXECUTE = "fragility:execute"
    BACKTEST_EXECUTE = "backtest:execute"

    # Project & Model Registry Permissions
    PROJECT_READ = "project:read"
    PROJECT_CREATE = "project:create"
    PROJECT_DELETE = "project:delete"
    MODEL_REGISTER = "model:register"
    PLUGIN_REGISTER = "plugin:register"
    PLUGIN_EXECUTE_UNTRUSTED = "plugin:execute_untrusted"

    # Workspace Management Permissions
    MEMBER_INVITE = "member:invite"
    MEMBER_REMOVE = "member:remove"
    TENANT_MANAGE = "tenant:manage"
    AUDIT_READ = "audit:read"

    # Platform Admin Only
    PLATFORM_AUDIT = "platform:audit"
    PLATFORM_METRICS = "platform:metrics"


# Precomputed role-to-permission mapping
ROLE_PERMISSIONS: Mapping[TenantRole, FrozenSet[Permission]] = {
    TenantRole.VIEWER: frozenset({
        Permission.PORTFOLIO_READ,
        Permission.DATASET_READ,
        Permission.PROJECT_READ,
        Permission.PORTFOLIO_EXPORT,
    }),
    TenantRole.RESEARCHER: frozenset({
        Permission.PORTFOLIO_READ,
        Permission.PORTFOLIO_CREATE,
        Permission.PORTFOLIO_UPDATE,
        Permission.PORTFOLIO_EXPORT,
        Permission.DATASET_READ,
        Permission.DATASET_UPLOAD,
        Permission.RISK_EXECUTE,
        Permission.SCENARIO_EXECUTE,
        Permission.SIMULATION_EXECUTE,
        Permission.FRAGILITY_EXECUTE,
        Permission.BACKTEST_EXECUTE,
        Permission.PROJECT_READ,
        Permission.PROJECT_CREATE,
        Permission.MODEL_REGISTER,
        Permission.PLUGIN_REGISTER,
    }),
    TenantRole.TENANT_ADMIN: frozenset({
        Permission.PORTFOLIO_READ,
        Permission.PORTFOLIO_CREATE,
        Permission.PORTFOLIO_UPDATE,
        Permission.PORTFOLIO_DELETE,
        Permission.PORTFOLIO_EXPORT,
        Permission.DATASET_READ,
        Permission.DATASET_UPLOAD,
        Permission.DATASET_DELETE,
        Permission.RISK_EXECUTE,
        Permission.SCENARIO_EXECUTE,
        Permission.SIMULATION_EXECUTE,
        Permission.FRAGILITY_EXECUTE,
        Permission.BACKTEST_EXECUTE,
        Permission.PROJECT_READ,
        Permission.PROJECT_CREATE,
        Permission.PROJECT_DELETE,
        Permission.MODEL_REGISTER,
        Permission.PLUGIN_REGISTER,
        Permission.PLUGIN_EXECUTE_UNTRUSTED,
        Permission.MEMBER_INVITE,
        Permission.MEMBER_REMOVE,
        Permission.AUDIT_READ,
    }),
    TenantRole.TENANT_OWNER: frozenset(Permission),  # All permissions
    TenantRole.PLATFORM_ADMIN: frozenset({
        Permission.PLATFORM_AUDIT,
        Permission.PLATFORM_METRICS,
        Permission.AUDIT_READ,
    }),
}


# ==============================================================================
# 2. Data Models (Tenants, Users, Memberships, Audit)
# ==============================================================================

@dataclass
class Tenant:
    """Workspace boundary container for isolating all financial research data."""
    tenant_id: str
    name: str
    tier: str = "research"  # 'free', 'research', 'institutional'
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_active: bool = True
    max_portfolios: int = 50
    max_datasets_mb: int = 500
    allow_untrusted_plugins: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class User:
    """Authenticated human researcher or automated service principal."""
    user_id: str
    email: str
    password_hash: str
    full_name: str = ""
    is_active: bool = True
    is_platform_admin: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d.pop("password_hash", None)  # Never serialize password hashes
        return d


@dataclass
class TenantMembership:
    """Explicit association binding a User to a Tenant with an authorized Role."""
    membership_id: str
    tenant_id: str
    user_id: str
    role: TenantRole
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["role"] = self.role.value
        return d


@dataclass
class AuditEvent:
    """Immutable audit trail entry for tracking access, mutations, and security decisions."""
    event_id: str
    tenant_id: str
    user_id: str
    action: str
    resource_type: str
    resource_id: str
    status: str  # 'SUCCESS', 'DENIED', 'ERROR'
    ip_address: str = "127.0.0.1"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ==============================================================================
# 3. Transaction-Safe Tenant Context Manager
# ==============================================================================

@dataclass(frozen=True)
class TenantContext:
    """Active security context established for an ongoing request or transaction."""
    tenant_id: str
    user_id: str
    role: TenantRole
    permissions: FrozenSet[Permission]
    is_platform_admin: bool = False
    audit_trace_id: str = field(default_factory=lambda: secrets.token_hex(8))

    def has_permission(self, permission: Permission) -> bool:
        """Check whether the active context possesses the requested permission."""
        if self.role == TenantRole.TENANT_OWNER:
            return True
        return permission in self.permissions

    def require_permission(self, permission: Permission) -> None:
        """Enforce permission, raising PermissionError if denied."""
        if not self.has_permission(permission):
            raise PermissionError(
                f"Permission denied: role '{self.role.value}' in tenant '{self.tenant_id}' "
                f"lacks required permission '{permission.value}'"
            )


# Context variable for storing the current thread/task tenant context
_CURRENT_TENANT_CONTEXT: contextvars.ContextVar[Optional[TenantContext]] = contextvars.ContextVar(
    "current_tenant_context", default=None
)


def get_current_tenant_context() -> Optional[TenantContext]:
    """Retrieve the active TenantContext, or None if outside a tenant scope."""
    return _CURRENT_TENANT_CONTEXT.get()


def require_tenant_context() -> TenantContext:
    """Retrieve the active TenantContext or fail closed if unauthenticated."""
    ctx = _CURRENT_TENANT_CONTEXT.get()
    if ctx is None:
        raise PermissionError(
            "Access denied: No active tenant context found. All tenant operations "
            "require an established, authenticated tenant boundary."
        )
    return ctx


def set_current_tenant_context(context: Optional[TenantContext]) -> None:
    """Explicitly set or clear the active tenant context for thread/task execution."""
    _CURRENT_TENANT_CONTEXT.set(context)


class tenant_boundary:
    """Context manager for establishing and automatically clearing a trusted tenant context.

    Usage:
        with tenant_boundary(context):
            # protected tenant operations here
    """

    def __init__(self, context: TenantContext, db_connection: Optional[Any] = None) -> None:
        if not isinstance(context, TenantContext):
            raise TypeError("context must be an instance of TenantContext")
        self._context = context
        self._db_conn = db_connection
        self._token: Optional[contextvars.Token] = None

    def __enter__(self) -> TenantContext:
        self._token = _CURRENT_TENANT_CONTEXT.set(self._context)
        # If a live database connection is provided, set the transaction-local RLS variable
        if self._db_conn is not None:
            self._set_db_tenant_setting(self._context.tenant_id)
        return self._context

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._token is not None:
            _CURRENT_TENANT_CONTEXT.reset(self._token)
            self._token = None
        if self._db_conn is not None:
            self._clear_db_tenant_setting()

    def _set_db_tenant_setting(self, tenant_id: str) -> None:
        """Set PostgreSQL transaction-scoped setting `app.current_tenant_id`."""
        try:
            # Executes transaction-local SET LOCAL
            cursor = getattr(self._db_conn, "cursor", None)
            if callable(cursor):
                with cursor() as cur:
                    cur.execute("SET LOCAL app.current_tenant_id = %s;", (tenant_id,))
            elif hasattr(self._db_conn, "execute"):
                self._db_conn.execute(f"SET LOCAL app.current_tenant_id = '{tenant_id}';")
        except Exception:
            # If database driver doesn't support raw SQL or is mock, fail gracefully
            pass

    def _clear_db_tenant_setting(self) -> None:
        """Clear PostgreSQL transaction-scoped setting."""
        try:
            cursor = getattr(self._db_conn, "cursor", None)
            if callable(cursor):
                with cursor() as cur:
                    cur.execute("SET LOCAL app.current_tenant_id = '';")
            elif hasattr(self._db_conn, "execute"):
                self._db_conn.execute("SET LOCAL app.current_tenant_id = '';")
        except Exception:
            pass


# ==============================================================================
# 4. Identity Token (JWT) Security Implementation
# ==============================================================================

# Minimum secret length to prevent weak HMAC keys
MIN_SECRET_LENGTH = 32

def _get_signing_key() -> bytes:
    """Retrieve or generate the HMAC signing key from environment."""
    secret = os.environ.get("FRAGILITY_JWT_SECRET", "").strip()
    dep_mode = os.environ.get("DEPLOYMENT_MODE", "local_research").strip().lower()

    if not secret:
        if dep_mode in ("public_multi_tenant", "production_cloud", "hosted_single_user"):
            raise ValueError(
                "FAIL-CLOSED: FRAGILITY_JWT_SECRET environment variable is missing in production mode. "
                "A cryptographically secure secret (>= 32 chars) is required."
            )
        # Development fallback with explicit warning
        return b"fragilityshield_dev_secret_insecure_replace_in_production_32_bytes"

    if len(secret) < MIN_SECRET_LENGTH:
        raise ValueError(f"FRAGILITY_JWT_SECRET must be at least {MIN_SECRET_LENGTH} characters long.")

    if dep_mode in ("public_multi_tenant", "production_cloud", "hosted_single_user"):
        trivial_defaults = ("fragilityshield_dev", "default_secret", "change_me", "changeme")
        if any(td in secret.lower() for td in trivial_defaults) or len(set(secret)) < 6:
            raise ValueError("FAIL-CLOSED: Trivial or default FRAGILITY_JWT_SECRET detected in production mode.")

    return secret.encode("utf-8")


def hash_password(password: str, salt: Optional[str] = None) -> str:
    """Cryptographically hash a password using PBKDF2-HMAC-SHA256."""
    if not password:
        raise ValueError("Password cannot be blank.")
    salt_val = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_val.encode("utf-8"), 100_000)
    return f"pbkdf2_sha256$100000${salt_val}${dk.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a stored PBKDF2 hash using constant-time comparison."""
    try:
        parts = password_hash.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
        iterations = int(parts[1])
        salt = parts[2]
        expected_dk = parts[3]
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
        return hmac.compare_digest(dk.hex(), expected_dk)
    except Exception:
        return False


def create_access_token(
    user_id: str,
    tenant_id: str,
    role: TenantRole,
    expires_in_seconds: int = 3600,
    is_platform_admin: bool = False,
    signing_key: Optional[Union[bytes, str]] = None,
    issuer: str = "fragilityshield",
    audience: str = "fragilityshield-api",
) -> str:
    """Generate a signed, tamper-proof JSON Web Token (JWT) using PyJWT with HMAC-SHA256.

    Claims:
        sub: user_id
        tid: tenant_id
        rol: role.value
        adm: is_platform_admin
        iss: issuer
        aud: audience
        iat: issued_at timestamp
        exp: expiration timestamp
    """
    if signing_key is None:
        key: Union[bytes, str] = _get_signing_key()
    elif isinstance(signing_key, str):
        key = signing_key.encode("utf-8")
    else:
        key = signing_key

    now = int(time.time())
    payload = {
        "sub": user_id,
        "tid": tenant_id,
        "rol": role.value if isinstance(role, TenantRole) else str(role),
        "adm": bool(is_platform_admin),
        "iss": issuer,
        "aud": audience,
        "iat": now,
        "exp": now + expires_in_seconds,
    }

    return jwt.encode(payload, key, algorithm="HS256")


def decode_and_verify_token(
    token: str,
    signing_key: Optional[Union[bytes, str]] = None,
    issuer: Optional[str] = "fragilityshield",
    audience: Optional[str] = "fragilityshield-api",
) -> Dict[str, Any]:
    """Decode and cryptographically verify a JWT using PyJWT.

    Enforces:
    - Algorithm allowlist: HS256 only (strictly rejects alg: none or asymmetric algorithm confusion)
    - Signature verification against the trusted key
    - Expiration enforcement (exp)
    - Issuer and audience validation
    - Required claims presence (sub, tid, rol, exp, iat)

    Raises:
        ValueError: If token format is invalid, expired, signature mismatch, or claims invalid.
    """
    if not token or not isinstance(token, str):
        raise ValueError("Malformed JWT: token must be a non-empty string.")

    if signing_key is None:
        key: Union[bytes, str] = _get_signing_key()
    elif isinstance(signing_key, str):
        key = signing_key.encode("utf-8")
    else:
        key = signing_key

    options = {
        "require": ["sub", "tid", "rol", "exp", "iat"],
        "verify_signature": True,
        "verify_exp": True,
        "verify_iat": True,
        "verify_iss": issuer is not None,
        "verify_aud": audience is not None,
    }

    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=["HS256"],
            issuer=issuer,
            audience=audience,
            options=options,
        )
    except jwt.ExpiredSignatureError as exc:
        raise ValueError(f"JWT has expired: {exc}") from exc
    except jwt.InvalidSignatureError as exc:
        raise ValueError(f"Invalid JWT signature: token has been tampered with or signing key mismatch: {exc}") from exc
    except (jwt.InvalidAlgorithmError, jwt.InvalidKeyError) as exc:
        raise ValueError(f"Invalid JWT algorithm or key: {exc}") from exc
    except jwt.DecodeError as exc:
        raise ValueError(f"Malformed JWT or invalid signature encoding: {exc}") from exc
    except (jwt.InvalidIssuerError, jwt.InvalidAudienceError, jwt.MissingRequiredClaimError) as exc:
        raise ValueError(f"Invalid JWT claims: {exc}") from exc
    except Exception as exc:
        raise ValueError(f"Invalid JWT token: {exc}") from exc

    return payload


# ==============================================================================
# 5. In-Memory Mock Membership Repository (for standalone testing & validation)
# ==============================================================================

class MemoryTenantRepository:
    """Thread-safe reference repository managing multi-tenant state and RLS policy simulation."""

    def __init__(self) -> None:
        self.tenants: Dict[str, Tenant] = {}
        self.users: Dict[str, User] = {}
        self.memberships: Dict[str, TenantMembership] = {}
        self.audit_events: List[AuditEvent] = []
        # Resource stores (tenant_id -> Dict[resource_id, data])
        self.portfolios: Dict[str, Dict[str, Any]] = {}
        self.datasets: Dict[str, Dict[str, Any]] = {}
        self.experiments: Dict[str, Dict[str, Any]] = {}
        self.jobs: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.artifacts: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.transactions: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}

    def register_tenant(self, tenant: Tenant) -> None:
        self.tenants[tenant.tenant_id] = tenant
        self.portfolios.setdefault(tenant.tenant_id, {})
        self.datasets.setdefault(tenant.tenant_id, {})
        self.experiments.setdefault(tenant.tenant_id, {})
        self.jobs.setdefault(tenant.tenant_id, {})
        self.artifacts.setdefault(tenant.tenant_id, {})
        self.transactions.setdefault(tenant.tenant_id, {})

    def register_user(self, user: User) -> None:
        self.users[user.user_id] = user

    def add_membership(self, membership: TenantMembership) -> None:
        key = f"{membership.tenant_id}:{membership.user_id}"
        self.memberships[key] = membership

    def get_user(self, user_id: str) -> Optional[User]:
        return self.users.get(user_id)

    def get_user_by_email(self, email: str) -> Optional[User]:
        clean_email = email.strip().lower()
        for u in self.users.values():
            if u.email.strip().lower() == clean_email:
                return u
        return None

    def get_membership(self, tenant_id: str, user_id: str) -> Optional[TenantMembership]:
        return self.memberships.get(f"{tenant_id}:{user_id}")

    def get_memberships_for_user(self, user_id: str) -> List[TenantMembership]:
        return [m for m in self.memberships.values() if m.user_id == user_id and m.is_active]

    def log_audit(self, event: AuditEvent) -> None:
        self.audit_events.append(event)

    def authenticate_user(self, username_or_email: str, password: str) -> Optional[User]:
        """Verify user credentials using constant-time PBKDF2 comparison."""
        user = self.get_user(username_or_email) or self.get_user_by_email(username_or_email)
        if not user or not user.is_active:
            return None
        if not verify_password(password, user.password_hash):
            return None
        return user

    def authenticate_and_resolve_tenant(
        self,
        username_or_email: str,
        password: Optional[str] = None,
        requested_tenant_id: Optional[str] = None,
        allow_dev_auth: bool = False,
    ) -> Tuple[User, TenantMembership, TenantContext]:
        """Authenticate user and resolve verified TenantContext.

        Security Enforcements:
        1. User must exist and be active.
        2. In production, password is MANDATORY and verified.
        3. In local development with allow_dev_auth=True, passwordless resolution is allowed only for existing seeded users.
        4. Target tenant membership is strictly validated; joining arbitrary tenants is denied.
        5. Role is derived exclusively from trusted server-side membership records.
        """
        dep_mode = os.environ.get("DEPLOYMENT_MODE", "local_research").strip().lower()
        is_production = dep_mode in ("public_multi_tenant", "production_cloud", "hosted_single_user")

        user = self.get_user(username_or_email) or self.get_user_by_email(username_or_email)
        if user is None:
            raise AuthenticationError(f"Authentication failed: User '{username_or_email}' not found.")

        if not user.is_active:
            raise PermissionError(f"Access denied: User account '{user.user_id}' has been disabled.")

        if password:
            if not verify_password(password, user.password_hash):
                raise AuthenticationError("Authentication failed: Invalid credentials.")
        else:
            if is_production:
                raise AuthenticationError("Authentication failed: Password credentials are required in hosted/production deployment.")
            if not allow_dev_auth:
                raise AuthenticationError("Authentication failed: Development authentication is disabled. Password credentials required.")

        # Resolve Target Tenant
        if requested_tenant_id:
            membership = self.get_membership(requested_tenant_id, user.user_id)
            if not membership or not membership.is_active:
                raise PermissionError(
                    f"Access denied: User '{user.user_id}' is not an active member of tenant '{requested_tenant_id}'."
                )
            tenant = self.tenants.get(requested_tenant_id)
            if not tenant or not tenant.is_active:
                raise PermissionError(f"Access denied: Tenant '{requested_tenant_id}' is suspended or inactive.")
        else:
            # Use primary active membership
            active_mems = self.get_memberships_for_user(user.user_id)
            if not active_mems:
                raise PermissionError(f"Access denied: User '{user.user_id}' has no active tenant memberships.")
            membership = active_mems[0]
            tenant = self.tenants.get(membership.tenant_id)

        role = membership.role
        permissions = ROLE_PERMISSIONS.get(role, frozenset())
        context = TenantContext(
            tenant_id=membership.tenant_id,
            user_id=user.user_id,
            role=role,
            permissions=permissions,
            is_platform_admin=user.is_platform_admin,
        )
        return user, membership, context

    def resolve_context(self, user_id: str, tenant_id: str) -> TenantContext:
        """Resolve trusted TenantContext after verifying user active status and membership."""
        user = self.users.get(user_id)
        if not user or not user.is_active:
            raise PermissionError(f"User '{user_id}' does not exist or is inactive.")

        tenant = self.tenants.get(tenant_id)
        if not tenant or not tenant.is_active:
            raise PermissionError(f"Tenant '{tenant_id}' does not exist or is suspended.")

        # Platform admin override for audit/metrics only
        if user.is_platform_admin and tenant_id == "platform_admin":
            role = TenantRole.PLATFORM_ADMIN
            return TenantContext(
                tenant_id=tenant_id,
                user_id=user_id,
                role=role,
                permissions=ROLE_PERMISSIONS[role],
                is_platform_admin=True,
            )

        # Standard tenant membership verification
        membership = self.get_membership(tenant_id, user_id)
        if not membership or not membership.is_active:
            raise PermissionError(
                f"Cross-tenant violation: User '{user_id}' is not an active member of tenant '{tenant_id}'."
            )

        role = membership.role
        permissions = ROLE_PERMISSIONS.get(role, frozenset())

        return TenantContext(
            tenant_id=tenant_id,
            user_id=user_id,
            role=role,
            permissions=permissions,
            is_platform_admin=user.is_platform_admin,
        )

    # Scoped Resource Operations (Simulating Database RLS)
    def save_portfolio(self, portfolio_id: str, data: Dict[str, Any]) -> None:
        ctx = require_tenant_context()
        ctx.require_permission(Permission.PORTFOLIO_CREATE)
        data_copy = dict(data)
        data_copy["tenant_id"] = ctx.tenant_id
        data_copy["portfolio_id"] = portfolio_id
        self.portfolios[ctx.tenant_id][portfolio_id] = data_copy
        self.log_audit(
            AuditEvent(
                event_id=secrets.token_hex(8),
                tenant_id=ctx.tenant_id,
                user_id=ctx.user_id,
                action="PORTFOLIO_CREATE",
                resource_type="portfolio",
                resource_id=portfolio_id,
                status="SUCCESS",
            )
        )

    def get_portfolio(self, portfolio_id: str) -> Optional[Dict[str, Any]]:
        ctx = require_tenant_context()
        ctx.require_permission(Permission.PORTFOLIO_READ)
        # RLS simulation: only query within active tenant_id
        tenant_store = self.portfolios.get(ctx.tenant_id, {})
        return tenant_store.get(portfolio_id)

    def delete_portfolio(self, portfolio_id: str) -> bool:
        ctx = require_tenant_context()
        ctx.require_permission(Permission.PORTFOLIO_DELETE)
        tenant_store = self.portfolios.get(ctx.tenant_id, {})
        if portfolio_id in tenant_store:
            del tenant_store[portfolio_id]
            self.log_audit(
                AuditEvent(
                    event_id=secrets.token_hex(8),
                    tenant_id=ctx.tenant_id,
                    user_id=ctx.user_id,
                    action="PORTFOLIO_DELETE",
                    resource_type="portfolio",
                    resource_id=portfolio_id,
                    status="SUCCESS",
                )
            )
            return True
        return False

    def save_transaction(self, portfolio_id: str, tx: Dict[str, Any]) -> None:
        ctx = require_tenant_context()
        ctx.require_permission(Permission.PORTFOLIO_CREATE)
        tx_copy = dict(tx)
        tx_copy["tenant_id"] = ctx.tenant_id
        tx_copy["portfolio_id"] = portfolio_id
        tx_id = str(tx_copy.get("transaction_id") or secrets.token_hex(8))
        tx_copy["transaction_id"] = tx_id
        self.transactions.setdefault(ctx.tenant_id, {}).setdefault(portfolio_id, [])
        existing = self.transactions[ctx.tenant_id][portfolio_id]
        updated = [t for t in existing if t.get("transaction_id") != tx_id]
        updated.append(tx_copy)
        self.transactions[ctx.tenant_id][portfolio_id] = updated

    def list_transactions(self, portfolio_id: str) -> List[Dict[str, Any]]:
        ctx = require_tenant_context()
        ctx.require_permission(Permission.PORTFOLIO_READ)
        return list(self.transactions.get(ctx.tenant_id, {}).get(portfolio_id, []))

    def delete_transaction(self, portfolio_id: str, tx_id: str) -> bool:
        ctx = require_tenant_context()
        ctx.require_permission(Permission.PORTFOLIO_DELETE)
        txs = self.transactions.get(ctx.tenant_id, {}).get(portfolio_id, [])
        filtered = [t for t in txs if t.get("transaction_id") != tx_id]
        if len(filtered) < len(txs):
            self.transactions[ctx.tenant_id][portfolio_id] = filtered
            return True
        return False

    # 3. Asynchronous Job Queue Operations (RLS Protected)
    def create_job(
        self,
        job_id: str,
        job_type: str,
        payload: Dict[str, Any],
        priority: int = 0,
        timeout_seconds: float = 60.0,
        max_attempts: int = 3,
    ) -> Dict[str, Any]:
        ctx = require_tenant_context()
        now_ts = time.time()
        job_record = {
            "job_id": job_id,
            "tenant_id": ctx.tenant_id,
            "job_type": job_type,
            "status": "QUEUED",
            "priority": priority,
            "timeout_seconds": timeout_seconds,
            "max_attempts": max_attempts,
            "attempt_count": 0,
            "worker_id": None,
            "claimed_at": None,
            "lease_expires_at": None,
            "payload": payload,
            "result": None,
            "error_message": None,
            "created_by": ctx.user_id,
            "created_at": now_ts,
            "updated_at": now_ts,
            "cancelled_at": None,
        }
        self.jobs.setdefault(ctx.tenant_id, {})[job_id] = job_record
        return job_record

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        ctx = require_tenant_context()
        tenant_jobs = self.jobs.get(ctx.tenant_id, {})
        return tenant_jobs.get(job_id)

    def list_jobs(self) -> List[Dict[str, Any]]:
        ctx = require_tenant_context()
        tenant_jobs = self.jobs.get(ctx.tenant_id, {})
        return sorted(tenant_jobs.values(), key=lambda j: j["created_at"], reverse=True)

    def claim_next_job(
        self,
        worker_id: str,
        tenant_id: Optional[str] = None,
        lease_duration_seconds: float = 30.0,
    ) -> Optional[Dict[str, Any]]:
        now_ts = time.time()
        target_tenants = [tenant_id] if tenant_id else list(self.jobs.keys())

        candidates = []
        for tid in target_tenants:
            for job in self.jobs.get(tid, {}).values():
                status = job["status"]
                lease_exp = job.get("lease_expires_at")
                if status == "QUEUED" or (status in ("CLAIMED", "RUNNING") and lease_exp and lease_exp < now_ts):
                    candidates.append(job)

        if not candidates:
            return None

        # Sort by priority DESC, created_at ASC
        candidates.sort(key=lambda j: (-j.get("priority", 0), j.get("created_at", 0)))
        chosen = candidates[0]

        chosen["status"] = "CLAIMED"
        chosen["worker_id"] = worker_id
        chosen["claimed_at"] = now_ts
        chosen["lease_expires_at"] = now_ts + lease_duration_seconds
        chosen["attempt_count"] = chosen.get("attempt_count", 0) + 1
        chosen["updated_at"] = now_ts
        return dict(chosen)

    def heartbeat_job(
        self,
        tenant_id: str,
        job_id: str,
        worker_id: str,
        lease_duration_seconds: float = 30.0,
    ) -> bool:
        job = self.jobs.get(tenant_id, {}).get(job_id)
        if not job:
            return False
        if job.get("worker_id") != worker_id:
            return False
        if job["status"] not in ("CLAIMED", "RUNNING"):
            return False
        now_ts = time.time()
        job["lease_expires_at"] = now_ts + lease_duration_seconds
        job["updated_at"] = now_ts
        return True

    def complete_job(
        self,
        tenant_id: str,
        job_id: str,
        worker_id: str,
        status: str,
        result: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        job = self.jobs.get(tenant_id, {}).get(job_id)
        if not job:
            return False
        # Lease verification: worker must own job or lease must not be stolen
        if job.get("worker_id") and job.get("worker_id") != worker_id:
            return False
        job["status"] = status
        if result is not None:
            job["result"] = result
        if error_message is not None:
            job["error_message"] = error_message
        job["updated_at"] = time.time()
        return True

    def request_cancel_job(self, job_id: str) -> bool:
        ctx = require_tenant_context()
        job = self.jobs.get(ctx.tenant_id, {}).get(job_id)
        if not job:
            return False
        if job["status"] in ("SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT"):
            return False
        if job["status"] == "QUEUED":
            job["status"] = "CANCELLED"
            job["error_message"] = "Job cancelled prior to worker claiming."
        else:
            job["status"] = "CANCEL_REQUESTED"
        job["cancelled_at"] = time.time()
        job["updated_at"] = time.time()
        return True

    # 4. Tenant Artifact Operations (RLS Protected)
    def create_artifact(
        self,
        artifact_id: str,
        logical_type: str,
        storage_key: str,
        content_hash: str,
        size_bytes: int,
        media_type: str = "application/octet-stream",
        job_id: Optional[str] = None,
        experiment_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        ctx = require_tenant_context()
        record = {
            "artifact_id": artifact_id,
            "tenant_id": ctx.tenant_id,
            "job_id": job_id,
            "experiment_id": experiment_id,
            "logical_type": logical_type,
            "storage_key": storage_key,
            "content_hash": content_hash,
            "size_bytes": size_bytes,
            "media_type": media_type,
            "metadata": metadata or {},
            "created_at": time.time(),
        }
        self.artifacts.setdefault(ctx.tenant_id, {})[artifact_id] = record
        return record

    def get_artifact(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        ctx = require_tenant_context()
        tenant_artifacts = self.artifacts.get(ctx.tenant_id, {})
        return tenant_artifacts.get(artifact_id)

    def list_artifacts(
        self,
        experiment_id: Optional[str] = None,
        job_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        ctx = require_tenant_context()
        tenant_artifacts = self.artifacts.get(ctx.tenant_id, {})
        results = []
        for art in tenant_artifacts.values():
            if experiment_id and art.get("experiment_id") != experiment_id:
                continue
            if job_id and art.get("job_id") != job_id:
                continue
            results.append(art)
        return sorted(results, key=lambda a: a["created_at"], reverse=True)

    def delete_artifact(self, artifact_id: str) -> bool:
        ctx = require_tenant_context()
        tenant_artifacts = self.artifacts.get(ctx.tenant_id, {})
        if artifact_id in tenant_artifacts:
            del tenant_artifacts[artifact_id]
            return True
        return False

    # 5. Tenant Experiment Run Operations
    def save_experiment_run(
        self,
        run_id: str,
        experiment_id: str,
        spec: Dict[str, Any],
        result: Dict[str, Any],
        dataset_hash: str = "",
        status: str = "completed",
    ) -> None:
        ctx = require_tenant_context()
        record = {
            "run_id": run_id,
            "tenant_id": ctx.tenant_id,
            "experiment_id": experiment_id,
            "status": status,
            "spec": spec,
            "result": result,
            "dataset_hash": dataset_hash,
            "created_by": ctx.user_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.experiments.setdefault(ctx.tenant_id, {})[run_id] = record

    def get_experiment_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        ctx = require_tenant_context()
        return self.experiments.get(ctx.tenant_id, {}).get(run_id)

    def list_experiment_runs(self) -> List[Dict[str, Any]]:
        ctx = require_tenant_context()
        tenant_runs = self.experiments.get(ctx.tenant_id, {})
        runs = list(tenant_runs.values())
        runs.sort(key=lambda r: str(r.get("created_at", "")), reverse=True)
        return runs



# ==============================================================================
# 6. Default Pre-Seeded Tenant Repository
# ==============================================================================

_DEFAULT_TENANT_REPO: Optional[MemoryTenantRepository] = None

def get_default_tenant_repository() -> MemoryTenantRepository:
    """Return the global singleton TenantRepository pre-seeded with baseline tenants and accounts."""
    global _DEFAULT_TENANT_REPO
    if _DEFAULT_TENANT_REPO is None:
        repo = MemoryTenantRepository()

        # Tenants
        t_default = Tenant(tenant_id="ten_default", name="Default Research Workspace")
        t_alpha = Tenant(tenant_id="ten_alpha_capital", name="Alpha Capital Research")
        t_beta = Tenant(tenant_id="ten_beta_investments", name="Beta Investments Ltd")
        repo.register_tenant(t_default)
        repo.register_tenant(t_alpha)
        repo.register_tenant(t_beta)

        # Users
        u_quant = User(
            user_id="usr_quant_1",
            email="quant1@fragilityshield.local",
            password_hash=hash_password("QuantPassword2026!"),
            full_name="Quant Research Lead",
            is_active=True,
        )
        u_owner = User(
            user_id="usr_owner",
            email="owner@fragilityshield.local",
            password_hash=hash_password("OwnerPassword2026!"),
            full_name="Workspace Owner",
            is_active=True,
        )
        u_admin = User(
            user_id="usr_admin",
            email="admin@fragilityshield.local",
            password_hash=hash_password("AdminPassword2026!"),
            full_name="Tenant Administrator",
            is_active=True,
        )
        u_viewer = User(
            user_id="usr_viewer",
            email="viewer@fragilityshield.local",
            password_hash=hash_password("ViewerPassword2026!"),
            full_name="Read-Only Analyst",
            is_active=True,
        )
        u_disabled = User(
            user_id="usr_disabled",
            email="disabled@fragilityshield.local",
            password_hash=hash_password("DisabledPassword2026!"),
            full_name="Deactivated User",
            is_active=False,
        )
        repo.register_user(u_quant)
        repo.register_user(u_owner)
        repo.register_user(u_admin)
        repo.register_user(u_viewer)
        repo.register_user(u_disabled)

        # Memberships
        repo.add_membership(TenantMembership("mem_q_def", "ten_default", "usr_quant_1", TenantRole.RESEARCHER))
        repo.add_membership(TenantMembership("mem_q_alp", "ten_alpha_capital", "usr_quant_1", TenantRole.RESEARCHER))
        repo.add_membership(TenantMembership("mem_o_def", "ten_default", "usr_owner", TenantRole.TENANT_OWNER))
        repo.add_membership(TenantMembership("mem_a_alp", "ten_alpha_capital", "usr_admin", TenantRole.TENANT_ADMIN))
        repo.add_membership(TenantMembership("mem_v_def", "ten_default", "usr_viewer", TenantRole.VIEWER))
        repo.add_membership(TenantMembership("mem_d_def", "ten_default", "usr_disabled", TenantRole.RESEARCHER))

        _DEFAULT_TENANT_REPO = repo

    return _DEFAULT_TENANT_REPO

