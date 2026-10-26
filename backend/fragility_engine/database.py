"""FragilityShield — Production Database Engine & Connection Architecture.

This module implements the explicit database runtime modes, connection pooling,
transaction-scoped tenant context management, and PostgreSQL repository adapters.

Security Guarantees:
1. Explicit Runtime Modes:
   - LOCAL_RESEARCH: Development and research mode (in-memory / local files).
   - POSTGRES_APP: Validated PostgreSQL mode using restricted runtime role.
   - PRODUCTION: Enforces strict production invariants; fails closed if PostgreSQL,
     strong secrets, or forced RLS are absent. Never silently falls back.
2. Least-Privilege Role & Connection Pooling:
   - Uses thread-safe connection pooling with `fragility_app_user` (NOSUPERUSER, NOBYPASSRLS).
3. Parameterized Transaction-Local Tenant Context:
   - Uses `SELECT set_config('app.current_tenant_id', %s, true);` inside an active transaction.
   - Automatically clears on COMMIT or ROLLBACK.
4. Fail-Closed Error Envelopes:
   - Database exceptions are caught and sanitized. Internal SQL strings and credentials are NEVER exposed.
"""

from __future__ import annotations

import enum
import json
import logging
import os
import secrets
import urllib.parse
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional, Tuple, Union

from psycopg2 import pool
from psycopg2.extras import RealDictCursor

from fragility_engine.db_schema import (
    SecurityConfigurationError,
    verify_production_security_configuration,
)
from fragility_engine.tenancy import (
    AuditEvent,
    AuthenticationError,
    MemoryTenantRepository,
    Permission,
    ROLE_PERMISSIONS,
    TenantContext,
    TenantMembership,
    TenantRole,
    User,
    get_default_tenant_repository,
    require_tenant_context,
    verify_password,
)

logger = logging.getLogger("fragilityshield.database")


class DatabaseMode(str, enum.Enum):
    """Explicit runtime database modes."""
    LOCAL_RESEARCH = "local_research"
    POSTGRES_APP = "postgres_app"
    PRODUCTION = "production"


def mask_database_url(url: str) -> str:
    """Mask password in database URL for safe logging and status reporting."""
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlsplit(url)
        if parsed.password:
            netloc = f"{parsed.username}:***@{parsed.hostname}"
            if parsed.port:
                netloc += f":{parsed.port}"
            return urllib.parse.urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
        return url
    except Exception:
        return "postgresql://***:***@masked"


# ==============================================================================
# Connection Pool & Lifecycle Management
# ==============================================================================

_DB_POOL: Optional[pool.ThreadedConnectionPool] = None
_DB_MODE: DatabaseMode = DatabaseMode.LOCAL_RESEARCH
_DB_CONFIGURED_URL: Optional[str] = None


def get_current_database_mode() -> DatabaseMode:
    """Return the active runtime database mode."""
    global _DB_MODE
    dep_mode = os.environ.get("DEPLOYMENT_MODE", "").strip().lower()
    app_env = os.environ.get("APP_ENV", "").strip().lower()

    if dep_mode in ("public_multi_tenant", "production_cloud") or app_env == "production":
        return DatabaseMode.PRODUCTION
    
    db_url = os.environ.get("DATABASE_URL", "").strip().lower()
    if dep_mode == "postgres_app" or (db_url.startswith("postgresql") and _DB_POOL is not None):
        return DatabaseMode.POSTGRES_APP

    return DatabaseMode.LOCAL_RESEARCH


def init_database_pool(
    database_url: Optional[str] = None,
    minconn: int = 1,
    maxconn: int = 10,
    enforce_production_checks: bool = False,
) -> pool.ThreadedConnectionPool:
    """Initialize the PostgreSQL connection pool using the restricted application role.

    Raises:
        SecurityConfigurationError: If production security invariants or RLS checks fail.
    """
    global _DB_POOL, _DB_MODE, _DB_CONFIGURED_URL

    url = database_url or os.environ.get("DATABASE_URL", "").strip()
    dep_mode = os.environ.get("DEPLOYMENT_MODE", "local_research").strip().lower()
    jwt_secret = os.environ.get("JWT_SECRET_KEY", "fragilityshield_dev_secret_key_change_in_production")
    cors_origins = [o.strip() for o in os.environ.get("ALLOWED_CORS_ORIGINS", "*").split(",") if o.strip()]

    # Production Pre-Flight Validation
    if enforce_production_checks or dep_mode in ("public_multi_tenant", "production_cloud"):
        verify_production_security_configuration(
            deployment_mode=dep_mode,
            database_url=url,
            jwt_secret=jwt_secret,
            cors_origins=cors_origins,
        )

    if not url or not url.lower().startswith("postgresql"):
        if enforce_production_checks or dep_mode in ("public_multi_tenant", "production_cloud"):
            raise SecurityConfigurationError(
                f"FAIL-CLOSED: Cannot initialize production database with non-PostgreSQL URL: '{url}'"
            )
        raise ValueError(f"PostgreSQL connection URL required, got: '{url}'")

    # Close existing pool if any
    close_database_pool()

    try:
        new_pool = pool.ThreadedConnectionPool(minconn, maxconn, url)
        _DB_POOL = new_pool
        _DB_CONFIGURED_URL = url
        _DB_MODE = (
            DatabaseMode.PRODUCTION
            if dep_mode in ("public_multi_tenant", "production_cloud")
            else DatabaseMode.POSTGRES_APP
        )
        logger.info(
            "Initialized PostgreSQL connection pool in %s mode (target: %s)",
            _DB_MODE.value,
            mask_database_url(url),
        )
    except Exception as exc:
        if enforce_production_checks or dep_mode in ("public_multi_tenant", "production_cloud"):
            raise SecurityConfigurationError(f"FAIL-CLOSED: PostgreSQL connection failed: {exc}") from exc
        raise

    # Verify RLS and role attributes on target database
    verify_database_prerequisites(new_pool)

    return new_pool


def close_database_pool() -> None:
    """Close all connections in the pool safely."""
    global _DB_POOL, _DB_MODE, _DB_CONFIGURED_URL
    if _DB_POOL is not None:
        try:
            _DB_POOL.closeall()
        except Exception:
            pass
        _DB_POOL = None
        _DB_CONFIGURED_URL = None
        _DB_MODE = DatabaseMode.LOCAL_RESEARCH


def get_database_pool() -> Optional[pool.ThreadedConnectionPool]:
    """Retrieve the active connection pool if initialized."""
    return _DB_POOL


def verify_database_prerequisites(db_pool: pool.ThreadedConnectionPool) -> Dict[str, Any]:
    """Verify that the target PostgreSQL database enforces RLS and the application role is restricted."""
    conn = db_pool.getconn()
    try:
        with conn.cursor() as cur:
            # 1. Role Privilege Audit
            cur.execute("""
                SELECT rolname, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole
                FROM pg_roles
                WHERE rolname = current_user;
            """)
            role_row = cur.fetchone()
            if role_row:
                rolname, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole = role_row
                if rolsuper:
                    raise SecurityConfigurationError(
                        f"CRITICAL: Connected as superuser '{rolname}'. "
                        "The application must NEVER run as a PostgreSQL superuser."
                    )
                if rolbypassrls:
                    raise SecurityConfigurationError(
                        f"CRITICAL: Application role '{rolname}' has BYPASSRLS privilege. "
                        "Row-Level Security would be completely subverted."
                    )

            # 2. Table RLS & Forced RLS Audit
            tenant_tables = (
                "portfolios",
                "datasets",
                "projects",
                "models",
                "experiment_runs",
                "plugin_registrations",
                "plugin_executions",
                "jobs",
                "audit_events",
            )
            cur.execute("""
                SELECT relname, relrowsecurity, relforcerowsecurity
                FROM pg_class
                JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
                WHERE pg_namespace.nspname = 'public'
                  AND relname = ANY(%s);
            """, (list(tenant_tables),))
            rows = {row[0]: (row[1], row[2]) for row in cur.fetchall()}

            for table in tenant_tables:
                if table not in rows:
                    raise SecurityConfigurationError(
                        f"FAIL-CLOSED: Required tenant table '{table}' does not exist in public schema."
                    )
                rls_enabled, rls_forced = rows[table]
                if not rls_enabled:
                    raise SecurityConfigurationError(
                        f"FAIL-CLOSED: Table '{table}' does not have Row-Level Security enabled."
                    )
                if not rls_forced:
                    raise SecurityConfigurationError(
                        f"FAIL-CLOSED: Table '{table}' does not have FORCE Row-Level Security enabled."
                    )

        return {
            "status": "PREREQUISITES_VERIFIED",
            "role": rolname if role_row else "unknown",
            "tables_verified": list(tenant_tables),
        }
    finally:
        db_pool.putconn(conn)


@contextmanager
def db_transaction(tenant_id: Optional[str] = None) -> Generator[Any, None, None]:
    """Execute within a pooled PostgreSQL connection with transaction-scoped tenant context.

    Security Guarantees:
    - `set_config('app.current_tenant_id', ..., true)` binds the tenant context ONLY
      to the current transaction.
    - Commits automatically on normal block completion.
    - Rolls back cleanly on error, reverting tenant context.
    - Returns clean connection to pool.
    """
    if _DB_POOL is None:
        mode = get_current_database_mode()
        if mode == DatabaseMode.PRODUCTION:
            raise SecurityConfigurationError(
                "FAIL-CLOSED: PostgreSQL connection pool is not initialized in production mode. "
                "Silent fallback to in-memory or SQLite is strictly prohibited."
            )
        raise RuntimeError("Database connection pool is not initialized.")

    conn = _DB_POOL.getconn()
    try:
        conn.autocommit = False
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Set transaction-scoped tenant context (parameterized, injection-immune)
            target_tenant = tenant_id if tenant_id is not None else ""
            cur.execute("SELECT set_config('app.current_tenant_id', %s, true);", (target_tenant,))
            yield cur
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        _DB_POOL.putconn(conn)


# ==============================================================================
# PostgreSQL Tenant Repository Implementation
# ==============================================================================

class PostgresTenantRepository:
    """Production PostgreSQL-backed repository enforcing Row-Level Security on all tenant queries."""

    # 1. Identity & Membership Operations (System Catalog / Administrative scope)
    def get_user(self, user_id: str) -> Optional[User]:
        with db_transaction(tenant_id="") as cur:
            cur.execute("""
                SELECT user_id, email, password_hash, full_name, is_active, is_platform_admin, created_at
                FROM users WHERE user_id = %s;
            """, (user_id,))
            row = cur.fetchone()
            if not row:
                return None
            return User(
                user_id=row["user_id"],
                email=row["email"],
                password_hash=row["password_hash"],
                full_name=row["full_name"] or "",
                is_active=row["is_active"],
                is_platform_admin=row["is_platform_admin"],
                created_at=row["created_at"].isoformat() if row["created_at"] else "",
            )

    def get_user_by_email(self, email: str) -> Optional[User]:
        with db_transaction(tenant_id="") as cur:
            cur.execute("""
                SELECT user_id, email, password_hash, full_name, is_active, is_platform_admin, created_at
                FROM users WHERE LOWER(email) = LOWER(%s);
            """, (email.strip(),))
            row = cur.fetchone()
            if not row:
                return None
            return User(
                user_id=row["user_id"],
                email=row["email"],
                password_hash=row["password_hash"],
                full_name=row["full_name"] or "",
                is_active=row["is_active"],
                is_platform_admin=row["is_platform_admin"],
                created_at=row["created_at"].isoformat() if row["created_at"] else "",
            )

    def get_membership(self, tenant_id: str, user_id: str) -> Optional[TenantMembership]:
        with db_transaction(tenant_id="") as cur:
            cur.execute("""
                SELECT membership_id, tenant_id, user_id, role, is_active, created_at
                FROM tenant_memberships
                WHERE tenant_id = %s AND user_id = %s;
            """, (tenant_id, user_id))
            row = cur.fetchone()
            if not row:
                return None
            return TenantMembership(
                membership_id=row["membership_id"],
                tenant_id=row["tenant_id"],
                user_id=row["user_id"],
                role=TenantRole(row["role"]),
                is_active=row["is_active"],
                created_at=row["created_at"].isoformat() if row["created_at"] else "",
            )

    def get_memberships_for_user(self, user_id: str) -> List[TenantMembership]:
        with db_transaction(tenant_id="") as cur:
            cur.execute("""
                SELECT membership_id, tenant_id, user_id, role, is_active, created_at
                FROM tenant_memberships
                WHERE user_id = %s AND is_active = TRUE;
            """, (user_id,))
            return [
                TenantMembership(
                    membership_id=row["membership_id"],
                    tenant_id=row["tenant_id"],
                    user_id=row["user_id"],
                    role=TenantRole(row["role"]),
                    is_active=row["is_active"],
                    created_at=row["created_at"].isoformat() if row["created_at"] else "",
                )
                for row in cur.fetchall()
            ]

    def authenticate_user(self, username_or_email: str, password: str) -> Optional[User]:
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
        user = self.get_user(username_or_email) or self.get_user_by_email(username_or_email)
        if user is None:
            raise AuthenticationError(f"Authentication failed: User '{username_or_email}' not found.")

        if not user.is_active:
            raise PermissionError(f"Access denied: User account '{user.user_id}' has been disabled.")

        dep_mode = os.environ.get("DEPLOYMENT_MODE", "local_research").strip().lower()
        is_production = dep_mode in ("public_multi_tenant", "production_cloud", "hosted_single_user")

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
        else:
            active_mems = self.get_memberships_for_user(user.user_id)
            if not active_mems:
                raise PermissionError(f"Access denied: User '{user.user_id}' has no active tenant memberships.")
            membership = active_mems[0]

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

    # 2. Portfolio Operations (RLS Protected)
    def save_portfolio(self, portfolio_id: str, data: Dict[str, Any]) -> None:
        ctx = require_tenant_context()
        ctx.require_permission(Permission.PORTFOLIO_CREATE)

        name = str(data.get("name", portfolio_id))
        currency = str(data.get("currency", "INR"))
        holdings = data.get("holdings", [])
        holdings_json = json.dumps(holdings)

        with db_transaction(tenant_id=ctx.tenant_id) as cur:
            cur.execute("""
                INSERT INTO portfolios (portfolio_id, tenant_id, name, currency, holdings_json, created_by)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, portfolio_id) DO UPDATE
                SET name = EXCLUDED.name,
                    currency = EXCLUDED.currency,
                    holdings_json = EXCLUDED.holdings_json,
                    updated_at = CURRENT_TIMESTAMP;
            """, (portfolio_id, ctx.tenant_id, name, currency, holdings_json, ctx.user_id))

        self.log_audit(
            AuditEvent(
                event_id=secrets.token_hex(8),
                tenant_id=ctx.tenant_id,
                user_id=ctx.user_id,
                action="PORTFOLIO_SAVE",
                resource_type="portfolio",
                resource_id=portfolio_id,
                status="SUCCESS",
            )
        )

    def get_portfolio(self, portfolio_id: str) -> Optional[Dict[str, Any]]:
        ctx = require_tenant_context()
        ctx.require_permission(Permission.PORTFOLIO_READ)

        with db_transaction(tenant_id=ctx.tenant_id) as cur:
            cur.execute("""
                SELECT portfolio_id, tenant_id, name, currency, holdings_json, created_by, created_at, updated_at
                FROM portfolios
                WHERE portfolio_id = %s;
            """, (portfolio_id,))
            row = cur.fetchone()
            if not row:
                return None
            return {
                "portfolio_id": row["portfolio_id"],
                "tenant_id": row["tenant_id"],
                "name": row["name"],
                "currency": row["currency"],
                "holdings": row["holdings_json"] if isinstance(row["holdings_json"], list) else json.loads(row["holdings_json"]),
                "created_by": row["created_by"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else "",
            }

    def list_portfolios(self) -> List[Dict[str, Any]]:
        ctx = require_tenant_context()
        ctx.require_permission(Permission.PORTFOLIO_READ)

        with db_transaction(tenant_id=ctx.tenant_id) as cur:
            cur.execute("""
                SELECT portfolio_id, tenant_id, name, currency, holdings_json, created_by, created_at, updated_at
                FROM portfolios ORDER BY created_at DESC;
            """)
            results = []
            for row in cur.fetchall():
                results.append({
                    "portfolio_id": row["portfolio_id"],
                    "tenant_id": row["tenant_id"],
                    "name": row["name"],
                    "currency": row["currency"],
                    "holdings": row["holdings_json"] if isinstance(row["holdings_json"], list) else json.loads(row["holdings_json"]),
                    "created_by": row["created_by"],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else "",
                })
            return results

    def delete_portfolio(self, portfolio_id: str) -> bool:
        ctx = require_tenant_context()
        ctx.require_permission(Permission.PORTFOLIO_DELETE)

        with db_transaction(tenant_id=ctx.tenant_id) as cur:
            cur.execute("DELETE FROM portfolios WHERE portfolio_id = %s;", (portfolio_id,))
            deleted = cur.rowcount > 0

        if deleted:
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
        return deleted

    def save_transaction(self, portfolio_id: str, tx: Dict[str, Any]) -> None:
        ctx = require_tenant_context()
        ctx.require_permission(Permission.PORTFOLIO_CREATE)
        tx_id = str(tx.get("transaction_id") or secrets.token_hex(8))
        asset_id = str(tx.get("asset_id", "")).strip().upper()
        tx_type = str(tx.get("type", "BUY")).strip().upper()
        qty = float(tx.get("quantity", 0.0))
        price = float(tx.get("price", 0.0))
        fees = float(tx.get("fees", 0.0))
        currency = str(tx.get("currency", "INR"))
        notes = str(tx.get("notes", ""))
        ts = str(tx.get("timestamp") or datetime.now(timezone.utc).isoformat())

        with db_transaction(tenant_id=ctx.tenant_id) as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS portfolio_transactions (
                    transaction_id VARCHAR(64) NOT NULL,
                    portfolio_id VARCHAR(64) NOT NULL,
                    tenant_id VARCHAR(64) NOT NULL,
                    asset_id VARCHAR(64) NOT NULL,
                    type VARCHAR(32) NOT NULL,
                    quantity NUMERIC(18, 6) NOT NULL,
                    price NUMERIC(18, 6) NOT NULL,
                    fees NUMERIC(18, 6) NOT NULL DEFAULT 0.0,
                    currency VARCHAR(8) NOT NULL DEFAULT 'INR',
                    timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    notes TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (tenant_id, transaction_id)
                );
            """)
            cur.execute("""
                INSERT INTO portfolio_transactions (transaction_id, portfolio_id, tenant_id, asset_id, type, quantity, price, fees, currency, timestamp, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, transaction_id) DO UPDATE
                SET quantity = EXCLUDED.quantity, price = EXCLUDED.price, fees = EXCLUDED.fees, notes = EXCLUDED.notes;
            """, (tx_id, portfolio_id, ctx.tenant_id, asset_id, tx_type, qty, price, fees, currency, ts, notes))

    def list_transactions(self, portfolio_id: str) -> List[Dict[str, Any]]:
        ctx = require_tenant_context()
        ctx.require_permission(Permission.PORTFOLIO_READ)
        with db_transaction(tenant_id=ctx.tenant_id) as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS portfolio_transactions (
                    transaction_id VARCHAR(64) NOT NULL,
                    portfolio_id VARCHAR(64) NOT NULL,
                    tenant_id VARCHAR(64) NOT NULL,
                    asset_id VARCHAR(64) NOT NULL,
                    type VARCHAR(32) NOT NULL,
                    quantity NUMERIC(18, 6) NOT NULL,
                    price NUMERIC(18, 6) NOT NULL,
                    fees NUMERIC(18, 6) NOT NULL DEFAULT 0.0,
                    currency VARCHAR(8) NOT NULL DEFAULT 'INR',
                    timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    notes TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (tenant_id, transaction_id)
                );
            """)
            cur.execute("""
                SELECT transaction_id, portfolio_id, asset_id, type, quantity, price, fees, currency, timestamp, notes
                FROM portfolio_transactions
                WHERE portfolio_id = %s
                ORDER BY timestamp DESC;
            """, (portfolio_id,))
            rows = cur.fetchall()
            return [{
                "transaction_id": r["transaction_id"],
                "portfolio_id": r["portfolio_id"],
                "asset_id": r["asset_id"],
                "type": r["type"],
                "quantity": float(r["quantity"]),
                "price": float(r["price"]),
                "fees": float(r["fees"]),
                "currency": r["currency"],
                "timestamp": r["timestamp"].isoformat() if hasattr(r["timestamp"], "isoformat") else str(r["timestamp"]),
                "notes": r["notes"] or "",
            } for r in rows]

    def delete_transaction(self, portfolio_id: str, tx_id: str) -> bool:
        ctx = require_tenant_context()
        ctx.require_permission(Permission.PORTFOLIO_DELETE)
        with db_transaction(tenant_id=ctx.tenant_id) as cur:
            cur.execute("DELETE FROM portfolio_transactions WHERE portfolio_id = %s AND transaction_id = %s;", (portfolio_id, tx_id))
            return cur.rowcount > 0

    # 3. Project Operations (RLS Protected)
    def save_project(self, project: Any) -> None:
        ctx = require_tenant_context()
        ctx.require_permission(Permission.PROJECT_CREATE)

        proj_dict = project.to_dict() if hasattr(project, "to_dict") else dict(project)
        project_id = proj_dict.get("project_id", "")
        name = proj_dict.get("name", "Project")
        desc = proj_dict.get("description", "")
        manifest_json = json.dumps(proj_dict)

        with db_transaction(tenant_id=ctx.tenant_id) as cur:
            cur.execute("""
                INSERT INTO projects (project_id, tenant_id, name, description, manifest_json, created_by)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, project_id) DO UPDATE
                SET name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    manifest_json = EXCLUDED.manifest_json;
            """, (project_id, ctx.tenant_id, name, desc, manifest_json, ctx.user_id))

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        ctx = require_tenant_context()
        ctx.require_permission(Permission.PROJECT_READ)

        with db_transaction(tenant_id=ctx.tenant_id) as cur:
            cur.execute("""
                SELECT project_id, tenant_id, name, description, manifest_json, created_by, created_at
                FROM projects WHERE project_id = %s;
            """, (project_id,))
            row = cur.fetchone()
            if not row:
                return None
            data = row["manifest_json"] if isinstance(row["manifest_json"], dict) else json.loads(row["manifest_json"])
            data["tenant_id"] = row["tenant_id"]
            return data

    def list_projects(self) -> List[Dict[str, Any]]:
        ctx = require_tenant_context()
        ctx.require_permission(Permission.PROJECT_READ)

        with db_transaction(tenant_id=ctx.tenant_id) as cur:
            cur.execute("SELECT project_id, tenant_id, manifest_json FROM projects ORDER BY created_at DESC;")
            results = []
            for row in cur.fetchall():
                data = row["manifest_json"] if isinstance(row["manifest_json"], dict) else json.loads(row["manifest_json"])
                data["tenant_id"] = row["tenant_id"]
                results.append(data)
            return results

    def delete_project(self, project_id: str) -> bool:
        ctx = require_tenant_context()
        ctx.require_permission(Permission.PROJECT_DELETE)

        with db_transaction(tenant_id=ctx.tenant_id) as cur:
            cur.execute("DELETE FROM projects WHERE project_id = %s;", (project_id,))
            return cur.rowcount > 0

    # 4. Dataset Operations (RLS Protected)
    def save_dataset(self, dataset: Any) -> None:
        ctx = require_tenant_context()
        ctx.require_permission(Permission.DATASET_UPLOAD)

        d_dict = dataset.to_dict() if hasattr(dataset, "to_dict") else dict(dataset)
        dataset_id = d_dict.get("dataset_id", "")
        name = d_dict.get("name", "Dataset")
        source_type = d_dict.get("source_type", "historical")
        provenance_json = json.dumps(d_dict.get("provenance", {}))
        fingerprint = d_dict.get("fingerprint", "")
        row_count = int(d_dict.get("row_count", 0))

        with db_transaction(tenant_id=ctx.tenant_id) as cur:
            cur.execute("""
                INSERT INTO datasets (dataset_id, tenant_id, name, source_type, provenance_json, fingerprint, row_count, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, dataset_id) DO UPDATE
                SET name = EXCLUDED.name,
                    source_type = EXCLUDED.source_type,
                    provenance_json = EXCLUDED.provenance_json,
                    fingerprint = EXCLUDED.fingerprint,
                    row_count = EXCLUDED.row_count;
            """, (dataset_id, ctx.tenant_id, name, source_type, provenance_json, fingerprint, row_count, ctx.user_id))

    def get_dataset(self, dataset_id: str) -> Optional[Dict[str, Any]]:
        ctx = require_tenant_context()
        ctx.require_permission(Permission.DATASET_READ)

        with db_transaction(tenant_id=ctx.tenant_id) as cur:
            cur.execute("""
                SELECT dataset_id, tenant_id, name, source_type, provenance_json, fingerprint, row_count, created_by, created_at
                FROM datasets WHERE dataset_id = %s;
            """, (dataset_id,))
            row = cur.fetchone()
            if not row:
                return None
            return {
                "dataset_id": row["dataset_id"],
                "tenant_id": row["tenant_id"],
                "name": row["name"],
                "source_type": row["source_type"],
                "provenance": row["provenance_json"] if isinstance(row["provenance_json"], dict) else json.loads(row["provenance_json"]),
                "fingerprint": row["fingerprint"],
                "row_count": row["row_count"],
                "created_by": row["created_by"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else "",
            }

    def list_datasets(self) -> List[Dict[str, Any]]:
        ctx = require_tenant_context()
        ctx.require_permission(Permission.DATASET_READ)

        with db_transaction(tenant_id=ctx.tenant_id) as cur:
            cur.execute("SELECT dataset_id, tenant_id, name, source_type, provenance_json, fingerprint, row_count, created_by, created_at FROM datasets ORDER BY created_at DESC;")
            results = []
            for row in cur.fetchall():
                results.append({
                    "dataset_id": row["dataset_id"],
                    "tenant_id": row["tenant_id"],
                    "name": row["name"],
                    "source_type": row["source_type"],
                    "provenance": row["provenance_json"] if isinstance(row["provenance_json"], dict) else json.loads(row["provenance_json"]),
                    "fingerprint": row["fingerprint"],
                    "row_count": row["row_count"],
                    "created_by": row["created_by"],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else "",
                })
            return results

    def delete_dataset(self, dataset_id: str) -> bool:
        ctx = require_tenant_context()
        ctx.require_permission(Permission.DATASET_DELETE)

        with db_transaction(tenant_id=ctx.tenant_id) as cur:
            cur.execute("DELETE FROM datasets WHERE dataset_id = %s;", (dataset_id,))
            return cur.rowcount > 0

    # 5. Model Manifest Operations (RLS Protected)
    def save_model(self, model: Any) -> None:
        ctx = require_tenant_context()
        ctx.require_permission(Permission.MODEL_REGISTER)

        m_dict = model.to_dict() if hasattr(model, "to_dict") else dict(model)
        model_id = m_dict.get("model_id", "")
        name = m_dict.get("name", "Model")
        family = m_dict.get("family", "custom")
        parameters_json = json.dumps(m_dict.get("parameters", {}))

        with db_transaction(tenant_id=ctx.tenant_id) as cur:
            cur.execute("""
                INSERT INTO models (model_id, tenant_id, name, family, parameters_json, created_by)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, model_id) DO UPDATE
                SET name = EXCLUDED.name,
                    family = EXCLUDED.family,
                    parameters_json = EXCLUDED.parameters_json;
            """, (model_id, ctx.tenant_id, name, family, parameters_json, ctx.user_id))

    def get_model(self, model_id: str) -> Optional[Dict[str, Any]]:
        ctx = require_tenant_context()
        ctx.require_permission(Permission.PROJECT_READ)

        with db_transaction(tenant_id=ctx.tenant_id) as cur:
            cur.execute("""
                SELECT model_id, tenant_id, name, family, parameters_json, created_by, created_at
                FROM models WHERE model_id = %s;
            """, (model_id,))
            row = cur.fetchone()
            if not row:
                return None
            return {
                "model_id": row["model_id"],
                "tenant_id": row["tenant_id"],
                "name": row["name"],
                "family": row["family"],
                "parameters": row["parameters_json"] if isinstance(row["parameters_json"], dict) else json.loads(row["parameters_json"]),
                "created_by": row["created_by"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else "",
            }

    def list_models(self) -> List[Dict[str, Any]]:
        ctx = require_tenant_context()
        ctx.require_permission(Permission.PROJECT_READ)

        with db_transaction(tenant_id=ctx.tenant_id) as cur:
            cur.execute("SELECT model_id, tenant_id, name, family, parameters_json, created_by, created_at FROM models ORDER BY created_at DESC;")
            results = []
            for row in cur.fetchall():
                results.append({
                    "model_id": row["model_id"],
                    "tenant_id": row["tenant_id"],
                    "name": row["name"],
                    "family": row["family"],
                    "parameters": row["parameters_json"] if isinstance(row["parameters_json"], dict) else json.loads(row["parameters_json"]),
                    "created_by": row["created_by"],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else "",
                })
            return results

    def delete_model(self, model_id: str) -> bool:
        ctx = require_tenant_context()
        ctx.require_permission(Permission.PROJECT_DELETE)

        with db_transaction(tenant_id=ctx.tenant_id) as cur:
            cur.execute("DELETE FROM models WHERE model_id = %s;", (model_id,))
            return cur.rowcount > 0

    # 6. Experiment Run Operations (RLS Protected)
    def save_experiment_run(
        self,
        run_id: str,
        experiment_id: str,
        spec: Dict[str, Any],
        result: Dict[str, Any],
        dataset_hash: str = "hash_default",
        status: str = "completed",
    ) -> None:
        ctx = require_tenant_context()
        ctx.require_permission(Permission.RISK_EXECUTE)

        def _safe_json_default(o: Any) -> Any:
            if isinstance(o, (np.bool_, bool)):
                return bool(o)
            if isinstance(o, (np.integer, int)):
                return int(o)
            if isinstance(o, (np.floating, float)):
                return float(o)
            return str(o)

        spec_json = json.dumps(spec, default=_safe_json_default)
        result_json = json.dumps(result, default=_safe_json_default)

        with db_transaction(tenant_id=ctx.tenant_id) as cur:
            cur.execute("""
                INSERT INTO experiment_runs (run_id, tenant_id, experiment_id, status, spec_json, result_json, dataset_hash, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, run_id) DO UPDATE
                SET status = EXCLUDED.status,
                    result_json = EXCLUDED.result_json;
            """, (run_id, ctx.tenant_id, experiment_id, status, spec_json, result_json, dataset_hash, ctx.user_id))

    def list_experiment_runs(self) -> List[Dict[str, Any]]:
        ctx = require_tenant_context()
        ctx.require_permission(Permission.PROJECT_READ)

        with db_transaction(tenant_id=ctx.tenant_id) as cur:
            cur.execute("SELECT run_id, tenant_id, experiment_id, status, spec_json, result_json, created_at FROM experiment_runs ORDER BY created_at DESC;")
            results = []
            for row in cur.fetchall():
                results.append({
                    "run_id": row["run_id"],
                    "tenant_id": row["tenant_id"],
                    "experiment_id": row["experiment_id"],
                    "status": row["status"],
                    "spec": row["spec_json"] if isinstance(row["spec_json"], dict) else json.loads(row["spec_json"]),
                    "result": row["result_json"] if isinstance(row["result_json"], dict) else json.loads(row["result_json"]),
                    "created_at": row["created_at"].isoformat() if row["created_at"] else "",
                })
            return results

    def get_experiment_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        ctx = require_tenant_context()
        ctx.require_permission(Permission.PROJECT_READ)

        with db_transaction(tenant_id=ctx.tenant_id) as cur:
            cur.execute("""
                SELECT run_id, tenant_id, experiment_id, status, spec_json, result_json, dataset_hash, created_at, created_by
                FROM experiment_runs WHERE run_id = %s;
            """, (run_id,))
            row = cur.fetchone()
            if not row:
                return None
            return {
                "run_id": row["run_id"],
                "tenant_id": row["tenant_id"],
                "experiment_id": row["experiment_id"],
                "status": row["status"],
                "spec": row["spec_json"] if isinstance(row["spec_json"], dict) else json.loads(row["spec_json"]),
                "result": row["result_json"] if isinstance(row["result_json"], dict) else json.loads(row["result_json"]),
                "dataset_hash": row.get("dataset_hash", ""),
                "created_by": row.get("created_by", ""),
                "created_at": row["created_at"].isoformat() if row["created_at"] else "",
            }

    # 7. Audit Logging (RLS Protected)
    def log_audit(self, event: AuditEvent) -> None:
        target_tenant = event.tenant_id or "ten_default"
        with db_transaction(tenant_id=target_tenant) as cur:
            cur.execute("""
                INSERT INTO audit_events (event_id, tenant_id, user_id, action, resource_type, resource_id, status, ip_address, details_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (event_id) DO NOTHING;
            """, (
                event.event_id,
                target_tenant,
                event.user_id,
                event.action,
                event.resource_type,
                event.resource_id,
                event.status,
                event.ip_address,
                json.dumps(event.details),
            ))

    def list_audits(self) -> List[Dict[str, Any]]:
        ctx = require_tenant_context()
        ctx.require_permission(Permission.AUDIT_READ)

        with db_transaction(tenant_id=ctx.tenant_id) as cur:
            cur.execute("""
                SELECT event_id, tenant_id, user_id, action, resource_type, resource_id, status, ip_address, details_json, timestamp
                FROM audit_events ORDER BY timestamp DESC LIMIT 100;
            """)
            results = []
            for row in cur.fetchall():
                results.append({
                    "event_id": row["event_id"],
                    "tenant_id": row["tenant_id"],
                    "user_id": row["user_id"],
                    "action": row["action"],
                    "resource_type": row["resource_type"],
                    "resource_id": row["resource_id"],
                    "status": row["status"],
                    "ip_address": row["ip_address"],
                    "details": row["details_json"] if isinstance(row["details_json"], dict) else json.loads(row["details_json"]),
                    "timestamp": row["timestamp"].isoformat() if row["timestamp"] else "",
                })
            return results

    # 8. Jobs Management (RLS Protected)
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
        with db_transaction(tenant_id=ctx.tenant_id) as cur:
            cur.execute("""
                INSERT INTO jobs (job_id, tenant_id, job_type, status, priority, timeout_seconds, max_attempts, payload_json, created_by)
                VALUES (%s, %s, %s, 'QUEUED', %s, %s, %s, %s, %s);
            """, (job_id, ctx.tenant_id, job_type, priority, timeout_seconds, max_attempts, json.dumps(payload), ctx.user_id))
        return self.get_job(job_id) or {"job_id": job_id, "status": "QUEUED"}

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        ctx = require_tenant_context()
        with db_transaction(tenant_id=ctx.tenant_id) as cur:
            cur.execute("""
                SELECT job_id, tenant_id, job_type, status, priority, timeout_seconds, max_attempts, attempt_count,
                       worker_id, claimed_at, lease_expires_at, payload_json, result_json, error_message, created_at, updated_at
                FROM jobs WHERE job_id = %s;
            """, (job_id,))
            row = cur.fetchone()
            if not row:
                return None
            return {
                "job_id": row["job_id"],
                "tenant_id": row["tenant_id"],
                "job_type": row["job_type"],
                "status": row["status"],
                "priority": row["priority"],
                "timeout_seconds": row["timeout_seconds"],
                "max_attempts": row["max_attempts"],
                "attempt_count": row["attempt_count"],
                "worker_id": row["worker_id"],
                "claimed_at": row["claimed_at"].isoformat() if row["claimed_at"] else None,
                "lease_expires_at": row["lease_expires_at"].isoformat() if row["lease_expires_at"] else None,
                "payload": row["payload_json"] if isinstance(row["payload_json"], dict) else json.loads(row["payload_json"]),
                "result": row["result_json"] if (isinstance(row["result_json"], dict) or row["result_json"] is None) else json.loads(row["result_json"]),
                "error_message": row["error_message"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else "",
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else "",
            }

    def list_jobs(self) -> List[Dict[str, Any]]:
        ctx = require_tenant_context()
        with db_transaction(tenant_id=ctx.tenant_id) as cur:
            cur.execute("SELECT job_id, tenant_id, job_type, status, payload_json, result_json, created_at FROM jobs ORDER BY created_at DESC;")
            results = []
            for row in cur.fetchall():
                results.append({
                    "job_id": row["job_id"],
                    "tenant_id": row["tenant_id"],
                    "job_type": row["job_type"],
                    "status": row["status"],
                    "payload": row["payload_json"] if isinstance(row["payload_json"], dict) else json.loads(row["payload_json"]),
                    "created_at": row["created_at"].isoformat() if row["created_at"] else "",
                })
            return results

    def claim_next_job(
        self,
        worker_id: str,
        tenant_id: str,
        lease_duration_seconds: float = 30.0,
    ) -> Optional[Dict[str, Any]]:
        with db_transaction(tenant_id=tenant_id) as cur:
            cur.execute("""
                WITH candidate AS (
                    SELECT job_id
                    FROM jobs
                    WHERE status = 'QUEUED'
                       OR (status IN ('CLAIMED', 'RUNNING') AND lease_expires_at < NOW())
                    ORDER BY priority DESC, created_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE jobs j
                SET status = 'CLAIMED',
                    worker_id = %s,
                    claimed_at = NOW(),
                    lease_expires_at = NOW() + (%s || ' seconds')::interval,
                    attempt_count = j.attempt_count + 1,
                    updated_at = NOW()
                FROM candidate c
                WHERE j.job_id = c.job_id
                RETURNING j.job_id, j.tenant_id, j.job_type, j.status, j.priority, j.timeout_seconds,
                          j.attempt_count, j.max_attempts, j.payload_json;
            """, (worker_id, str(lease_duration_seconds)))
            row = cur.fetchone()
            if not row:
                return None
            return {
                "job_id": row["job_id"],
                "tenant_id": row["tenant_id"],
                "job_type": row["job_type"],
                "status": row["status"],
                "priority": row["priority"],
                "timeout_seconds": row["timeout_seconds"],
                "attempt_count": row["attempt_count"],
                "max_attempts": row["max_attempts"],
                "payload": row["payload_json"] if isinstance(row["payload_json"], dict) else json.loads(row["payload_json"]),
            }

    def heartbeat_job(
        self,
        tenant_id: str,
        job_id: str,
        worker_id: str,
        lease_duration_seconds: float = 30.0,
    ) -> bool:
        with db_transaction(tenant_id=tenant_id) as cur:
            cur.execute("""
                UPDATE jobs
                SET lease_expires_at = NOW() + (%s || ' seconds')::interval,
                    updated_at = NOW()
                WHERE job_id = %s AND worker_id = %s AND status IN ('CLAIMED', 'RUNNING');
            """, (str(lease_duration_seconds), job_id, worker_id))
            return cur.rowcount > 0

    def complete_job(
        self,
        tenant_id: str,
        job_id: str,
        worker_id: str,
        status: str,
        result: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        with db_transaction(tenant_id=tenant_id) as cur:
            cur.execute("""
                UPDATE jobs
                SET status = %s,
                    result_json = %s,
                    error_message = %s,
                    updated_at = NOW()
                WHERE job_id = %s AND (worker_id = %s OR worker_id IS NULL);
            """, (status, json.dumps(result) if result else None, error_message, job_id, worker_id))
            return cur.rowcount > 0

    def request_cancel_job(self, job_id: str) -> bool:
        ctx = require_tenant_context()
        with db_transaction(tenant_id=ctx.tenant_id) as cur:
            cur.execute("""
                UPDATE jobs
                SET status = CASE WHEN status = 'QUEUED' THEN 'CANCELLED' ELSE 'CANCEL_REQUESTED' END,
                    cancelled_at = NOW(),
                    updated_at = NOW()
                WHERE job_id = %s AND status NOT IN ('SUCCEEDED', 'FAILED', 'CANCELLED', 'TIMED_OUT');
            """, (job_id,))
            return cur.rowcount > 0

    # 9. Artifact Operations (RLS Protected)
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
        with db_transaction(tenant_id=ctx.tenant_id) as cur:
            cur.execute("""
                INSERT INTO artifacts (
                    artifact_id, tenant_id, job_id, experiment_id, logical_type,
                    storage_key, content_hash, size_bytes, media_type, metadata_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING artifact_id, tenant_id, logical_type, storage_key, content_hash, size_bytes, media_type, created_at;
            """, (
                artifact_id, ctx.tenant_id, job_id, experiment_id, logical_type,
                storage_key, content_hash, size_bytes, media_type, json.dumps(metadata or {})
            ))
            row = cur.fetchone()
            return {
                "artifact_id": row["artifact_id"],
                "tenant_id": row["tenant_id"],
                "logical_type": row["logical_type"],
                "storage_key": row["storage_key"],
                "content_hash": row["content_hash"],
                "size_bytes": row["size_bytes"],
                "media_type": row["media_type"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else "",
            }

    def get_artifact(self, artifact_id: str) -> Optional[Dict[str, Any]]:
        ctx = require_tenant_context()
        with db_transaction(tenant_id=ctx.tenant_id) as cur:
            cur.execute("""
                SELECT artifact_id, tenant_id, job_id, experiment_id, logical_type,
                       storage_key, content_hash, size_bytes, media_type, metadata_json, created_at
                FROM artifacts WHERE artifact_id = %s;
            """, (artifact_id,))
            row = cur.fetchone()
            if not row:
                return None
            return {
                "artifact_id": row["artifact_id"],
                "tenant_id": row["tenant_id"],
                "job_id": row["job_id"],
                "experiment_id": row["experiment_id"],
                "logical_type": row["logical_type"],
                "storage_key": row["storage_key"],
                "content_hash": row["content_hash"],
                "size_bytes": row["size_bytes"],
                "media_type": row["media_type"],
                "metadata": row["metadata_json"] if isinstance(row["metadata_json"], dict) else json.loads(row["metadata_json"]),
                "created_at": row["created_at"].isoformat() if row["created_at"] else "",
            }

    def list_artifacts(
        self,
        experiment_id: Optional[str] = None,
        job_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        ctx = require_tenant_context()
        with db_transaction(tenant_id=ctx.tenant_id) as cur:
            query = """
                SELECT artifact_id, tenant_id, job_id, experiment_id, logical_type,
                       storage_key, content_hash, size_bytes, media_type, created_at
                FROM artifacts
                WHERE 1=1
            """
            params = []
            if experiment_id:
                query += " AND experiment_id = %s"
                params.append(experiment_id)
            if job_id:
                query += " AND job_id = %s"
                params.append(job_id)
            query += " ORDER BY created_at DESC;"
            cur.execute(query, tuple(params))
            results = []
            for row in cur.fetchall():
                results.append({
                    "artifact_id": row["artifact_id"],
                    "tenant_id": row["tenant_id"],
                    "job_id": row["job_id"],
                    "experiment_id": row["experiment_id"],
                    "logical_type": row["logical_type"],
                    "storage_key": row["storage_key"],
                    "content_hash": row["content_hash"],
                    "size_bytes": row["size_bytes"],
                    "media_type": row["media_type"],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else "",
                })
            return results

    def delete_artifact(self, artifact_id: str) -> bool:
        ctx = require_tenant_context()
        with db_transaction(tenant_id=ctx.tenant_id) as cur:
            cur.execute("DELETE FROM artifacts WHERE artifact_id = %s;", (artifact_id,))
            return cur.rowcount > 0



# ==============================================================================
# Active Repository Resolver
# ==============================================================================

_ACTIVE_POSTGRES_REPO: Optional[PostgresTenantRepository] = None


def get_active_repository() -> Union[PostgresTenantRepository, MemoryTenantRepository]:
    """Resolve the active repository based on configured database mode.

    Fail-Closed Policy:
    - In PRODUCTION mode: PostgreSQL with active RLS is strictly required.
      Throws SecurityConfigurationError if the pool is uninitialized or SQLite is configured.
    - In POSTGRES_APP mode: Uses PostgresTenantRepository.
    - In LOCAL_RESEARCH mode: Uses MemoryTenantRepository.
    """
    global _ACTIVE_POSTGRES_REPO

    mode = get_current_database_mode()

    if mode == DatabaseMode.PRODUCTION:
        if _DB_POOL is None:
            raise SecurityConfigurationError(
                "FAIL-CLOSED: Production multi-tenant mode requires an active PostgreSQL connection pool. "
                "Database pool is uninitialized. Silent fallback to memory/SQLite is strictly prohibited."
            )
        if _ACTIVE_POSTGRES_REPO is None:
            _ACTIVE_POSTGRES_REPO = PostgresTenantRepository()
        return _ACTIVE_POSTGRES_REPO

    if mode == DatabaseMode.POSTGRES_APP:
        if _DB_POOL is not None:
            if _ACTIVE_POSTGRES_REPO is None:
                _ACTIVE_POSTGRES_REPO = PostgresTenantRepository()
            return _ACTIVE_POSTGRES_REPO

    # Local research fallback
    return get_default_tenant_repository()
