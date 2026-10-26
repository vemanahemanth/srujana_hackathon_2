"""Tests for Project, Dataset, Model Manifest, and Capability Registry (Blueprint §1-§3)."""

import tempfile
from pathlib import Path
import pytest

from fragility_engine.projects import (
    ArtifactEntity,
    CapabilityReport,
    CapabilityStatus,
    DatasetRecord,
    ExperimentEntity,
    ModelFamily,
    ModelManifest,
    Project,
    ProjectCatalog,
    ResultEntity,
    RunEntity,
    RunStatus,
    check_model_capabilities,
)


def test_project_entity_and_catalog() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        catalog = ProjectCatalog(storage_dir=tmpdir)
        proj = Project(
            project_id="alpha_res_2026",
            name="Alpha Factor Research 2026",
            description="Stress testing quantitative long/short factors under liquidity dry-ups",
            objective="Evaluate factor decay under elevated transaction costs",
            asset_universe=("NIFTY_50", "BANKNIFTY"),
            model_type="trading_strategy",
        )
        catalog.save_project(proj)

        loaded = catalog.get_project("alpha_res_2026")
        assert loaded is not None
        assert loaded.project_id == "alpha_res_2026"
        assert loaded.name == "Alpha Factor Research 2026"
        assert loaded.asset_universe == ("NIFTY_50", "BANKNIFTY")
        assert loaded.model_type == "trading_strategy"

        all_projects = catalog.list_projects()
        assert len(all_projects) == 1
        assert all_projects[0].project_id == "alpha_res_2026"


def test_dataset_record_and_catalog() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        catalog = ProjectCatalog(storage_dir=tmpdir)
        dset = DatasetRecord(
            dataset_id="nifty_daily_ohlcv",
            name="Nifty 50 Daily OHLCV 2020-2025",
            version="1.2.0",
            row_count=1250,
            column_mapping={"t": "timestamp", "c": "close", "v": "volume"},
            symbols=("NIFTY50",),
            frequency="1D",
            currency="INR",
            fingerprint="hash_abc123456",
        )
        catalog.save_dataset(dset)

        loaded = catalog.get_dataset("nifty_daily_ohlcv")
        assert loaded is not None
        assert loaded.dataset_id == "nifty_daily_ohlcv"
        assert loaded.row_count == 1250
        assert loaded.column_mapping["c"] == "close"
        assert loaded.symbols == ("NIFTY50",)

        all_dsets = catalog.list_datasets()
        assert len(all_dsets) == 1


def test_model_manifest_validation_and_catalog() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        catalog = ProjectCatalog(storage_dir=tmpdir)
        manifest = ModelManifest(
            model_id="ewma_vol_decay94",
            name="EWMA Volatility Estimator (RiskMetrics lambda=0.94)",
            version="2.0.0",
            owner="quant_risk_team",
            model_family=ModelFamily.RISK_ESTIMATOR,
            required_inputs=("returns",),
            expected_output_schema={"volatility_annualized": "float", "var_99": "float"},
            supported_labs=("risk", "fragility", "benchmarking"),
            supported_tests=("historical_var", "parametric_var", "lookback_sensitivity"),
            is_deterministic=True,
            code_isolation_required=False,
        )
        catalog.save_model(manifest)

        loaded = catalog.get_model("ewma_vol_decay94")
        assert loaded is not None
        assert loaded.model_id == "ewma_vol_decay94"
        assert loaded.model_family == ModelFamily.RISK_ESTIMATOR
        assert loaded.is_deterministic is True
        assert loaded.code_isolation_required is False

        # Serialization round-trip
        data = loaded.to_dict()
        reconstituted = ModelManifest.from_dict(data)
        assert reconstituted.model_id == loaded.model_id
        assert reconstituted.model_family == loaded.model_family


def test_model_capabilities_checking_truth_in_reporting() -> None:
    """Verifies that capability checking strictly adheres to §2 truth-in-reporting rules.

    - 'Not applicable' is returned for portfolio holdings on an ML model (not failure).
    - 'Unsupported' is returned for unsupported labs/tests (never silently passed).
    - 'Required before execution' is returned when arbitrary user code isolation is needed.
    """
    ml_manifest = ModelManifest(
        model_id="linear_reg_alpha",
        name="Linear Regression Alpha Predictor",
        model_family=ModelFamily.REGRESSION_MODEL,
        required_inputs=("features", "target"),
        supported_labs=("ml_testing", "benchmarking"),
        supported_tests=("mae", "rmse", "noise_robustness"),
        supports_historical_replay=False,
        code_isolation_required=True,
    )

    report = check_model_capabilities(ml_manifest)
    assert report.model_id == "linear_reg_alpha"
    assert report.model_family == ModelFamily.REGRESSION_MODEL

    # Portfolio holdings check on ML model must be NOT_APPLICABLE
    assert "Portfolio holdings" in report.capabilities
    assert report.capabilities["Portfolio holdings"].status == CapabilityStatus.NOT_APPLICABLE

    # Historical replay on a model without replay support must be UNSUPPORTED
    assert "Historical replay" in report.capabilities
    assert report.capabilities["Historical replay"].status == CapabilityStatus.UNSUPPORTED

    # Code isolation required
    assert "Arbitrary code isolation" in report.capabilities
    assert report.capabilities["Arbitrary code isolation"].status == CapabilityStatus.REQUIRED

    # Check filtering by unsupported lab
    lab_report = check_model_capabilities(ml_manifest, target_lab="portfolio_lab")
    assert lab_report.is_executable is False
    assert any("does not support target lab" in lim for lim in lab_report.limitations)
    assert lab_report.capabilities["Lab support (portfolio_lab)"].status == CapabilityStatus.UNSUPPORTED

    # Check filtering by supported lab
    valid_lab_report = check_model_capabilities(ml_manifest, target_lab="ml_testing")
    assert valid_lab_report.is_executable is True
    assert valid_lab_report.capabilities["Lab support (ml_testing)"].status == CapabilityStatus.SUPPORTED


def test_lifecycle_entities_stability() -> None:
    """Verifies stable IDs and serialization for Experiment, Run, Result, Artifact entities."""
    exp = ExperimentEntity(
        experiment_id="exp_gfc_stress_01",
        project_id="proj_bank_stress",
        name="Global Financial Crisis Shock Test",
        version="1.0.0",
        model_id="portfolio_nse_10l",
        dataset_id="returns_2008_2009",
        lab="scenarios",
        test_suite=("gfc_2008_replay", "liquidity_haircut"),
    )
    assert exp.experiment_id == "exp_gfc_stress_01"
    assert exp.to_dict()["lab"] == "scenarios"

    run = RunEntity(
        run_id="run_99812",
        experiment_id="exp_gfc_stress_01",
        status=RunStatus.COMPLETED,
        started_at="2026-10-25T01:00:00Z",
        completed_at="2026-10-25T01:00:02Z",
        random_seed=42,
    )
    assert run.status == RunStatus.COMPLETED
    assert run.to_dict()["status"] == "completed"

    res = ResultEntity(
        result_id="res_001",
        run_id="run_99812",
        metric_name="drawdown_max",
        observed_value=0.384,
        baseline_value=0.120,
        delta_abs=0.264,
        delta_pct=2.20,
        unit="fraction",
        status="warning",
        explanation="Stressed drawdown exceeds 35% risk budget.",
    )
    assert res.observed_value == 0.384
    assert res.to_dict()["status"] == "warning"

    art = ArtifactEntity(
        artifact_id="art_report_json",
        run_id="run_99812",
        artifact_type="report_json",
        file_path="/data/reports/exp_gfc_stress_01.json",
        fingerprint="sha256_e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        created_at="2026-10-25T01:00:03Z",
        size_bytes=4096,
    )
    assert art.size_bytes == 4096
    assert art.to_dict()["artifact_type"] == "report_json"
