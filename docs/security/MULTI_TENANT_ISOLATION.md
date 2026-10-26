# FragilityShield — Multi-Tenant Architecture & PostgreSQL Row-Level Security (RLS)

**Document Version:** 1.0.0  
**Target Architecture:** Multi-Tenant Relational Isolation with Defense in Depth  
**Implementation Modules:** `backend/fragility_engine/tenancy.py`, `backend/fragility_engine/db_schema.py`  

---

## 1. Multi-Tenant Architectural Principles

FragilityShield enforces multi-tenancy through a **Defense in Depth** strategy across three independent layers:

```
[ Layer 1: API / Middleware Boundary ]
  └─ JWT verification -> User Identity -> Active Membership Validation -> Role Permissions

[ Layer 2: Application Context Layer ]
  └─ Python contextvars (TenantContext) -> Fail-Closed require_tenant_context()

[ Layer 3: Database Engine Kernel Layer ]
  └─ PostgreSQL Row-Level Security (RLS) -> Transaction-Scoped SET LOCAL -> Zero-Row Default
```

1. **Never Trust Client Claims:** Client-supplied tenant IDs in URLs, request bodies, query parameters, or HTTP headers (`X-Tenant-ID`) are never trusted on their own. They must match verified memberships in the database.
2. **Transaction-Local Isolation:** Tenant configuration is set on database connections via `SET LOCAL app.current_tenant_id = :tenant_id` inside each database transaction. When the transaction commits or aborts, the parameter is immediately cleared, eliminating connection-pool leakage risks.
3. **Fail-Closed Default:** If a query executes without an active tenant context, PostgreSQL evaluates `current_setting('app.current_tenant_id', true)` as `NULL`, returning zero rows and preventing insert/update/delete.
4. **Least-Privilege Database Role:** The runtime application accesses the database as `fragility_app_user`, which is created with `NOSUPERUSER` and `NOBYPASSRLS`. The application cannot disable RLS, drop policies, or view cross-tenant rows.

---

## 2. PostgreSQL Row-Level Security Implementation

### 2.1 Table Activation & Enforcement
Every tenant-owned table is configured with explicit RLS and forced policy evaluation:

```sql
ALTER TABLE portfolios ENABLE ROW LEVEL SECURITY;
ALTER TABLE portfolios FORCE ROW LEVEL SECURITY;
```

> **Why `FORCE ROW LEVEL SECURITY`?**  
> In PostgreSQL, table owners and superusers bypass RLS by default. Specifying `FORCE ROW LEVEL SECURITY` ensures policies apply even if queries execute under table owner privileges.

### 2.2 Transaction-Scoped Policy Definition
Each table enforces identical restrictive read and write policies:

```sql
CREATE POLICY tenant_isolation_portfolios ON portfolios
    AS RESTRICTIVE
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), ''))
    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), ''));
```

- **`USING` Clause (Reads & Deletes):** Filters rows visible to `SELECT`, `UPDATE`, and `DELETE` statements.
- **`WITH CHECK` Clause (Inserts & Updates):** Validates that newly inserted or modified rows strictly match the current transaction's tenant context, preventing one tenant from writing records into another tenant's workspace.
- **`AS RESTRICTIVE`:** Multiple policies are evaluated via `AND`, ensuring tenant isolation cannot be bypassed by permissive helper policies.

---

## 3. Role-Based Access Control (RBAC) Matrix

Within each tenant workspace, access is partitioned into five distinct roles:

| Role | Target Persona | Permissions Summary |
| :--- | :--- | :--- |
| **`viewer`** | External Auditor, Read-Only Stakeholder | Read portfolios, view scenarios, inspect simulation results, export reports. Cannot mutate data or trigger expensive compute. |
| **`researcher`** | Quantitative Analyst, Data Scientist | Create portfolios, execute scenarios, run Monte Carlo simulations, backtest models, upload datasets, register models. |
| **`tenant_admin`** | Workspace Lead, Department Manager | Full workspace management: delete portfolios, remove datasets, invite/remove members, manage plugins, inspect workspace audit logs. |
| **`tenant_owner`** | Account Creator, Enterprise Owner | Unrestricted authority over workspace data, billing tiers, quotas, and deletion. |
| **`platform_admin`** | Infrastructure Engineer (Root) | Platform health, global metrics, security incident auditing. Cannot silently view tenant financial data without an audit log event. |

---

## 4. Database Connection Pooling Safety

When using connection poolers like PgBouncer or SQLAlchemy connection pools:

1. Standard `SET app.current_tenant_id = '...'` sets session-level configuration that persists across pooled connection reuse, creating severe cross-tenant data leakage risks.
2. FragilityShield mandates `SET LOCAL app.current_tenant_id = '...'` inside an explicit transaction block:

```python
with db_connection.transaction():
    db_connection.execute("SET LOCAL app.current_tenant_id = :tenant_id", {"tenant_id": ctx.tenant_id})
    # Protected queries run here with active RLS
    results = db_connection.execute("SELECT * FROM portfolios;")
# Transaction ends -> SET LOCAL automatically expires!
```

---

## 5. Verification Evidence

The multi-tenant isolation layer is validated by 21 automated adversarial tests:
- `backend/tests/test_multi_tenancy_and_auth.py` (12 tests): Cross-tenant read denial, cross-tenant delete denial, RBAC boundaries, context clearing on exception, token tamper rejection.
- `backend/tests/test_postgres_rls_specification.py` (9 tests): Schema DDL verification, `FORCE ROW LEVEL SECURITY` presence on all 9 tenant tables, runtime role privilege restrictions, production fail-closed validator.
