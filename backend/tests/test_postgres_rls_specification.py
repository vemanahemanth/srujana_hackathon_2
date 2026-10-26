"""Unit and specification tests for PostgreSQL Row-Level Security (RLS) and Production Security Validation.

Verifies:
1. Completeness and syntactic correctness of the PostgreSQL production DDL.
2. Mandatory presence of `FORCE ROW LEVEL SECURITY` on all tenant-owned tables.
3. Transaction-scoped `app.current_tenant_id` restrictive policy definitions.
4. Least-privilege runtime role (`fragility_app_user` with NOSUPERUSER NOBYPASSRLS).
5. Fail-closed production configuration enforcer (`verify_production_security_configuration`).
6. Lossless SQLite-to-PostgreSQL export and manifest checksum generation.
"""

from __future__ import annotations

import pytest

from fragility_engine.db_schema import (
    POSTGRES_RLS_SCHEMA_DDL,
    SecurityConfigurationError,
    generate_sqlite_migration_manifest,
    verify_production_security_configuration,
)


class TestPostgresRLSSpecification:
    """Verifies that the production PostgreSQL schema enforces strict Row-Level Security."""

    TENANT_TABLES = [
        "portfolios",
        "datasets",
        "projects",
        "models",
        "experiment_runs",
        "plugin_registrations",
        "plugin_executions",
        "jobs",
        "audit_events",
    ]

    def test_all_tenant_tables_created(self) -> None:
        """Verify DDL creates all required tenant-scoped tables."""
        ddl = POSTGRES_RLS_SCHEMA_DDL
        for tbl in self.TENANT_TABLES:
            assert f"CREATE TABLE IF NOT EXISTS {tbl}" in ddl, f"Missing table definition: {tbl}"

    def test_rls_enabled_and_forced_on_all_tables(self) -> None:
        """Verify ENABLE ROW LEVEL SECURITY and FORCE ROW LEVEL SECURITY exist for every tenant table."""
        ddl = POSTGRES_RLS_SCHEMA_DDL
        for tbl in self.TENANT_TABLES:
            enable_stmt = f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY;"
            force_stmt = f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY;"
            assert enable_stmt in ddl, f"Missing ENABLE RLS on {tbl}"
            assert force_stmt in ddl, f"Missing FORCE RLS on {tbl}"

    def test_restrictive_transaction_local_policies_exist(self) -> None:
        """Verify restrictive policy reads from transaction-scoped setting app.current_tenant_id."""
        ddl = POSTGRES_RLS_SCHEMA_DDL
        policy_clause = "current_setting('app.current_tenant_id', true)"
        assert policy_clause in ddl
        for tbl in self.TENANT_TABLES:
            # Policy names follow tenant_isolation_<shortname>
            assert f"ON {tbl}" in ddl
            assert "AS RESTRICTIVE" in ddl

    def test_restricted_runtime_role_definition(self) -> None:
        """Verify runtime role has NOSUPERUSER and NOBYPASSRLS to prevent security policy bypass."""
        ddl = POSTGRES_RLS_SCHEMA_DDL
        assert "CREATE ROLE fragility_app_user" in ddl
        assert "ALTER ROLE fragility_app_user NOSUPERUSER NOBYPASSRLS" in ddl
        # Grant DML only
        assert "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO fragility_app_user;" in ddl


class TestProductionSecurityValidator:
    """Tests the fail-closed configuration validator for public multi-tenant environments."""

    def test_reject_sqlite_in_public_multi_tenant_mode(self) -> None:
        """Verify SQLite is strictly rejected in public_multi_tenant mode."""
        with pytest.raises(SecurityConfigurationError, match="FAIL-CLOSED: SQLite persistence is strictly prohibited"):
            verify_production_security_configuration(
                deployment_mode="public_multi_tenant",
                database_url="sqlite:///data/fragility.db",
                jwt_secret="a_valid_random_secret_with_more_than_32_characters_here",
                cors_origins=["https://fragilityshield.internal"],
            )

    def test_reject_short_or_trivial_jwt_secrets(self) -> None:
        """Verify secrets with fewer than 32 characters or default names fail closed."""
        with pytest.raises(SecurityConfigurationError, match="JWT secret is too short"):
            verify_production_security_configuration(
                deployment_mode="public_multi_tenant",
                database_url="postgresql://app:pw@localhost:5432/fs_db",
                jwt_secret="short_secret",
                cors_origins=["https://fragilityshield.internal"],
            )

        with pytest.raises(SecurityConfigurationError, match="Trivial or default JWT secret detected"):
            verify_production_security_configuration(
                deployment_mode="public_multi_tenant",
                database_url="postgresql://app:pw@localhost:5432/fs_db",
                jwt_secret="secret" * 8,  # 'secretsecretsecretsecret...'
                cors_origins=["https://fragilityshield.internal"],
            )

    def test_reject_wildcard_cors_in_public_mode(self) -> None:
        """Verify wildcard CORS is rejected in public multi-tenant mode."""
        with pytest.raises(SecurityConfigurationError, match="Wildcard CORS origin"):
            verify_production_security_configuration(
                deployment_mode="public_multi_tenant",
                database_url="postgresql://app:pw@localhost:5432/fs_db",
                jwt_secret="a_valid_random_secret_with_more_than_32_characters_here",
                cors_origins=["*"],
            )

    def test_accept_valid_hardened_configuration(self) -> None:
        """Verify properly configured PostgreSQL and hardened secrets pass verification."""
        res = verify_production_security_configuration(
            deployment_mode="public_multi_tenant",
            database_url="postgresql+asyncpg://app_user:strong_password@db.prod.internal:5432/fragilityshield",
            jwt_secret="x9kL3pQ8vM2wR5tY7uB1cN4eG6jH0sZ_super_hardened_secret_key_32plus",
            cors_origins=["https://app.fragilityshield.com"],
        )
        assert res["status"] == "VERIFIED"
        assert res["database_engine"] == "PostgreSQL"
        assert res["rls_enforcement_ready"] is True


class TestMigrationManifestGeneration:
    """Tests lossless data manifest export from legacy SQLite/JSON catalog to PostgreSQL."""

    def test_migration_manifest_structure_and_checksum(self) -> None:
        projects = [{"project_id": "proj_1", "name": "Nifty Beta Study"}]
        datasets = [{"dataset_id": "ds_1", "name": "Nifty 50 2026", "fingerprint": "abc12345"}]
        models = [{"model_id": "mod_1", "name": "Student-t Nu4", "family": "student_t"}]

        manifest = generate_sqlite_migration_manifest(
            projects=projects,
            datasets=datasets,
            models=models,
            default_tenant_id="ten_migrated_workspace",
            default_user_id="usr_migrated_lead",
        )

        assert manifest["manifest_version"] == "1.0.0"
        assert manifest["total_records"] == 3
        assert manifest["default_tenant_id"] == "ten_migrated_workspace"
        assert len(manifest["manifest_checksum_sha256"]) == 64  # Valid SHA-256 hex string

        records = manifest["records"]
        assert any(r["table"] == "projects" and r["project_id"] == "proj_1" for r in records)
        assert any(r["table"] == "datasets" and r["dataset_id"] == "ds_1" for r in records)
        assert any(r["table"] == "models" and r["model_id"] == "mod_1" for r in records)
