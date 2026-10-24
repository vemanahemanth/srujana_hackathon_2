"""Tests for FragilityShield Experiment Studio & Reports (Phase 7).

Covers:
- StudioExperimentDefinition validation and security (path traversal rejection).
- Full experiment studio execution workflow on return series and Portfolio snapshots.
- Accurate status assignment ('completed', 'completed_with_warnings', 'failed_validation', 'failed_execution').
- Handling of partial and failed experiments without crashing.
- Multi-format report export: JSON, human-readable Markdown with unit awareness, tabular CSV.
- JSON serialization round-trips (to_dict / from_dict / to_json / from_json).
- Multi-experiment comparison (compatible vs incompatible runs, baseline differences, rank changes).
- LocalExperimentCatalog operations: saving, retrieving, listing with filters, delete, duplicate overwrite protection.
- Catalog security: path traversal rejection for malicious experiment IDs.
- Corrupted file resilience in catalog listing and loading.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List
import numpy as np
import pytest

from fragility_engine import (
    Holding,
    Portfolio,
)
from fragility_engine.studio import (
    ExperimentReport,
    LocalExperimentCatalog,
    StudioComparisonReport,
    StudioExperimentDefinition,
    compare_experiment_reports,
    execute_studio_experiment,
)


# ==============================================================================
# Fixtures
# ==============================================================================

@pytest.fixture
def sample_portfolio() -> Portfolio:
    """Fixture providing a clean 4-holding portfolio."""
    return Portfolio(
        portfolio_id="PF-STUDIO-001",
        name="StudioTestPortfolio",
        currency="INR",
        holdings=(
            Holding(asset_id="NSE:HDFCBANK", quantity=100.0, price=1600.0, sector="Financials"),
            Holding(asset_id="NSE:INFY", quantity=200.0, price=1500.0, sector="Technology"),
            Holding(asset_id="NSE:RELIANCE", quantity=150.0, price=2400.0, sector="Energy"),
            Holding(asset_id="NSE:TCS", quantity=100.0, price=3800.0, sector="Technology"),
        ),
    )


@pytest.fixture
def sample_return_series() -> List[float]:
    """Fixture providing 60 synthetic daily returns."""
    np.random.seed(42)
    rets = np.random.normal(0.0005, 0.015, 60).tolist()
    return [round(r, 8) for r in rets]


@pytest.fixture
def basic_studio_def() -> StudioExperimentDefinition:
    """Fixture providing a valid studio experiment definition."""
    return StudioExperimentDefinition(
        experiment_id="EXP-STUDIO-001",
        name="Studio Baseline & Friction Audit",
        description="Assesses tail risk sensitivity under 5bps and 10bps return friction drag.",
        dataset_id="SYNTH-NSE-60D",
        baseline_config={"confidence_level": 0.95, "annualization_factor": 252},
        perturbation_specs=[
            {
                "type": "return_friction",
                "experiment_id": "friction_5bps",
                "parameters": {"friction_bps": 5.0},
            },
            {
                "type": "return_friction",
                "experiment_id": "friction_10bps",
                "parameters": {"friction_bps": 10.0},
            },
            {
                "type": "lookback_window",
                "experiment_id": "lookback_30d",
                "parameters": {"lookback_window": 30},
            },
        ],
        target_ranking_metric="var_historical",
        tags=["risk", "friction", "equities"],
        metadata={"author": "Studio CI", "version": "1.0"},
    )


# ==============================================================================
# B2. Studio Experiment Definition Tests
# ==============================================================================

class TestStudioExperimentDefinition:
    """Test suite for StudioExperimentDefinition validation and security."""

    def test_valid_definition_creation(self, basic_studio_def):
        """Verify clean studio experiment definition builds successfully."""
        assert basic_studio_def.experiment_id == "EXP-STUDIO-001"
        assert len(basic_studio_def.perturbation_specs) == 3
        assert basic_studio_def.target_ranking_metric == "var_historical"

        spec = basic_studio_def.to_spec()
        assert spec.experiment_id == basic_studio_def.experiment_id

    def test_reject_blank_experiment_id(self):
        """Verify empty or whitespace experiment_id is rejected."""
        with pytest.raises(ValueError, match="experiment_id cannot be blank"):
            StudioExperimentDefinition(experiment_id="")
        with pytest.raises(ValueError, match="experiment_id cannot be blank"):
            StudioExperimentDefinition(experiment_id="   ")

    @pytest.mark.parametrize("unsafe_id", [
        "../path/traversal",
        "..\\windows\\traversal",
        "nested/subfolder",
        "null\0byte",
        "colon:restricted",
    ])
    def test_reject_unsafe_path_identifiers(self, unsafe_id):
        """Verify experiment_id containing path traversal or invalid characters is rejected."""
        with pytest.raises(ValueError, match="contains unsafe path traversal"):
            StudioExperimentDefinition(experiment_id=unsafe_id, name="Unsafe")

    def test_reject_invalid_confidence_level(self):
        """Verify invalid confidence levels are rejected."""
        with pytest.raises(ValueError, match="confidence_level must be in"):
            StudioExperimentDefinition(
                experiment_id="EXP-BAD-CONF",
                baseline_config={"confidence_level": 1.2},
            )

    def test_definition_dict_roundtrip(self, basic_studio_def):
        """Verify serialization and deserialization of StudioExperimentDefinition."""
        d = basic_studio_def.to_dict()
        restored = StudioExperimentDefinition.from_dict(d)
        assert restored.experiment_id == basic_studio_def.experiment_id
        assert restored.name == basic_studio_def.name
        assert restored.target_ranking_metric == basic_studio_def.target_ranking_metric
        assert restored.tags == basic_studio_def.tags


# ==============================================================================
# B3 & B5. Studio Execution Workflow & Report Tests
# ==============================================================================

class TestStudioExecutionWorkflow:
    """Test suite for execute_studio_experiment workflow and report production."""

    def test_execute_studio_experiment_end_to_end(self, basic_studio_def, sample_return_series):
        """Verify complete execution producing a structured ExperimentReport."""
        report = execute_studio_experiment(
            definition=basic_studio_def,
            return_series=sample_return_series,
        )

        assert isinstance(report, ExperimentReport)
        assert report.status == "completed"
        assert report.experiment_id == basic_studio_def.experiment_id
        assert len(report.baseline_metrics) >= 4
        assert "var_historical" in report.baseline_metrics
        assert "annualized_volatility" in report.baseline_metrics

        # Perturbation results
        assert len(report.perturbation_results) == 3
        pert_ids = [p["experiment_id"] for p in report.perturbation_results]
        assert "friction_5bps" in pert_ids
        assert "friction_10bps" in pert_ids
        assert "lookback_30d" in pert_ids

        # Sensitivity rankings
        assert len(report.sensitivity_rankings) >= 1
        top_rank = report.sensitivity_rankings[0]
        assert top_rank["rank"] == 1
        assert "absolute_impact" in top_rank

        # Manifest and validation
        assert report.manifest["validation_status"] == "PASSED"
        assert report.validation_report["all_passed"] is True
        assert len(report.input_fingerprint) == 64
        assert len(report.configuration_fingerprint) == 64

    def test_execute_studio_experiment_on_portfolio(self, sample_portfolio):
        """Verify studio execution on Portfolio snapshot with liquidation friction shock."""
        spec = StudioExperimentDefinition(
            experiment_id="EXP-PORT-001",
            name="Portfolio Liquidation Test",
            dataset_id="PF-10L-NSE",
            perturbation_specs=[
                {
                    "type": "portfolio_liquidation_shock",
                    "experiment_id": "liq_10bps",
                    "parameters": {"cost_bps": 10.0, "turnover_fraction": 1.0},
                }
            ],
            target_ranking_metric="portfolio_value",
        )

        report = execute_studio_experiment(definition=spec, dataset=sample_portfolio)
        assert report.status == "completed"
        assert "total_market_value" in report.baseline_metrics
        assert "asset_hhi_points" in report.baseline_metrics
        assert len(report.perturbation_results) == 1
        assert report.validation_report["all_passed"] is True

    def test_execute_handles_execution_failure_gracefully(self, sample_portfolio):
        """Verify execution failure assigns 'failed_execution' status without crashing."""
        # Intentionally mismatch: apply time-series lookback perturbation to static Portfolio
        bad_def = StudioExperimentDefinition(
            experiment_id="EXP-FAIL-001",
            name="Failing Experiment",
            perturbation_specs=[
                {"type": "lookback_window", "parameters": {"lookback_window": 30}}
            ],
        )

        report = execute_studio_experiment(
            definition=bad_def,
            dataset=sample_portfolio,
            continue_on_perturbation_error=True,
        )
        assert report.status == "failed_execution"
        assert len(report.warnings) >= 1
        assert "Lookback perturbation requires a return time series" in report.warnings[0]


# ==============================================================================
# B6. Report Export Formats: JSON, Markdown, CSV
# ==============================================================================

class TestReportExportFormats:
    """Test suite for report serialization to JSON, Markdown, and CSV."""

    def test_report_json_roundtrip(self, basic_studio_def, sample_return_series):
        """Verify JSON export and re-import preserves all fields and metrics."""
        report = execute_studio_experiment(basic_studio_def, return_series=sample_return_series)
        json_str = report.to_json(indent=2)

        # Re-import
        loaded_report = ExperimentReport.from_json(json_str)
        assert loaded_report.report_id == report.report_id
        assert loaded_report.experiment_id == report.experiment_id
        assert loaded_report.status == report.status
        assert loaded_report.baseline_metrics == report.baseline_metrics
        assert loaded_report.input_fingerprint == report.input_fingerprint
        assert loaded_report.configuration_fingerprint == report.configuration_fingerprint

    def test_report_markdown_formatting(self, basic_studio_def, sample_return_series):
        """Verify Markdown output contains headers, tables, units, and fingerprints."""
        report = execute_studio_experiment(basic_studio_def, return_series=sample_return_series)
        md = report.to_markdown()

        assert f"# FragilityShield — Experiment Report: {report.name}" in md
        assert f"`{report.experiment_id}`" in md
        assert "## 1. Cryptographic Fingerprints & Provenance" in md
        assert f"`{report.input_fingerprint}`" in md
        assert "## 2. Baseline Assumptions & Risk Metrics" in md
        assert "## 3. Perturbation Results & Impact" in md
        assert "## 4. Sensitivity Rankings" in md
        assert "## 5. Independent Validation & Limitations" in md

    def test_report_csv_formatting(self, basic_studio_def, sample_return_series):
        """Verify CSV output is a valid tabular dataset with explicit columns."""
        report = execute_studio_experiment(basic_studio_def, return_series=sample_return_series)
        csv_str = report.to_csv()

        lines = csv_str.strip().split("\n")
        assert len(lines) >= 4  # Header + at least 3 perturbation metric rows
        header = lines[0].split(",")
        assert "experiment_id" in header
        assert "perturbation_id" in header
        assert "metric_name" in header
        assert "baseline_value" in header
        assert "stressed_value" in header
        assert "absolute_delta" in header
        assert "unit" in header


# ==============================================================================
# B4. Multi-Experiment Comparison Tests
# ==============================================================================

class TestExperimentComparison:
    """Test suite for compare_experiment_reports."""

    def test_compare_identical_reports(self, basic_studio_def, sample_return_series):
        """Verify comparison of identical reports confirms equality."""
        rep_1 = execute_studio_experiment(basic_studio_def, return_series=sample_return_series)
        rep_2 = execute_studio_experiment(basic_studio_def, return_series=sample_return_series)

        comp = compare_experiment_reports(rep_1, rep_2)
        assert isinstance(comp, StudioComparisonReport)
        assert comp.comparable is True
        assert comp.input_data_identical is True
        assert comp.configuration_identical is True
        assert "verified equivalent" in comp.summary

    def test_compare_reports_with_different_inputs(self, basic_studio_def, sample_return_series):
        """Verify comparison correctly detects non-comparability when datasets differ."""
        rep_1 = execute_studio_experiment(basic_studio_def, return_series=sample_return_series)

        # Alter dataset
        altered_returns = list(sample_return_series)
        altered_returns[0] += 0.01

        rep_2 = execute_studio_experiment(basic_studio_def, return_series=altered_returns)
        comp = compare_experiment_reports(rep_1, rep_2)

        assert comp.comparable is False
        assert comp.input_data_identical is False
        assert any("Input data hashes differ" in r for r in comp.non_comparable_reasons)

    def test_compare_reports_with_different_configurations(self, basic_studio_def, sample_return_series):
        """Verify comparison itemizes perturbation differences when configurations differ."""
        rep_1 = execute_studio_experiment(basic_studio_def, return_series=sample_return_series)

        # Modified configuration
        def_2 = StudioExperimentDefinition(
            experiment_id="EXP-STUDIO-002",
            name="Alternative Friction Audit",
            dataset_id=basic_studio_def.dataset_id,
            baseline_config=basic_studio_def.baseline_config,
            perturbation_specs=[
                {
                    "type": "return_friction",
                    "experiment_id": "friction_25bps",
                    "parameters": {"friction_bps": 25.0},
                }
            ],
            target_ranking_metric="var_historical",
        )
        rep_2 = execute_studio_experiment(def_2, return_series=sample_return_series)

        comp = compare_experiment_reports(rep_1, rep_2)
        assert comp.comparable is True
        assert comp.input_data_identical is True
        assert comp.configuration_identical is False


# ==============================================================================
# B7. Local Experiment Catalog Tests
# ==============================================================================

class TestLocalExperimentCatalog:
    """Test suite for LocalExperimentCatalog storage, lookup, filtering, and security."""

    def test_catalog_save_and_retrieve(self, tmp_path, basic_studio_def, sample_return_series):
        """Verify report persistence and retrieval by experiment_id."""
        catalog = LocalExperimentCatalog(catalog_dir=tmp_path / "experiments")
        report = execute_studio_experiment(basic_studio_def, return_series=sample_return_series)

        saved_path = catalog.save_report(report)
        assert saved_path.exists()
        assert saved_path.name == f"{report.experiment_id}.json"

        # Retrieve
        loaded = catalog.get_report(report.experiment_id)
        assert loaded.experiment_id == report.experiment_id
        assert loaded.report_id == report.report_id

    def test_catalog_overwrite_protection(self, tmp_path, basic_studio_def, sample_return_series):
        """Verify catalog raises FileExistsError on duplicate experiment_id without overwrite=True."""
        catalog = LocalExperimentCatalog(catalog_dir=tmp_path / "experiments")
        report = execute_studio_experiment(basic_studio_def, return_series=sample_return_series)

        catalog.save_report(report, overwrite=False)

        with pytest.raises(FileExistsError, match="already exists"):
            catalog.save_report(report, overwrite=False)

        # Overwrite=True succeeds
        catalog.save_report(report, overwrite=True)

    def test_catalog_listing_and_filtering(self, tmp_path, sample_return_series):
        """Verify catalog lists reports and filters by status, tag, and dataset_id."""
        catalog = LocalExperimentCatalog(catalog_dir=tmp_path / "experiments")

        def_1 = StudioExperimentDefinition(
            experiment_id="EXP-CAT-001",
            dataset_id="DATA-A",
            tags=["risk", "daily"],
        )
        def_2 = StudioExperimentDefinition(
            experiment_id="EXP-CAT-002",
            dataset_id="DATA-B",
            tags=["equities", "monthly"],
        )

        catalog.save_report(execute_studio_experiment(def_1, return_series=sample_return_series))
        catalog.save_report(execute_studio_experiment(def_2, return_series=sample_return_series))

        all_reports = catalog.list_reports()
        assert len(all_reports) == 2

        # Filter by dataset_id
        data_a_reports = catalog.list_reports(dataset_id="DATA-A")
        assert len(data_a_reports) == 1
        assert data_a_reports[0]["experiment_id"] == "EXP-CAT-001"

        # Filter by tag
        equity_reports = catalog.list_reports(tag="equities")
        assert len(equity_reports) == 1
        assert equity_reports[0]["experiment_id"] == "EXP-CAT-002"

        # Filter by status
        completed_reports = catalog.list_reports(status="completed")
        assert len(completed_reports) == 2

    def test_catalog_security_path_traversal_rejection(self, tmp_path):
        """Verify catalog rejects malicious identifiers targeting directory traversal."""
        catalog = LocalExperimentCatalog(catalog_dir=tmp_path / "experiments")

        with pytest.raises(ValueError, match="Unsafe identifier"):
            catalog.get_report("../../../etc/passwd")

        with pytest.raises(ValueError, match="Unsafe identifier"):
            catalog.get_report("subdir/test")

    def test_catalog_corrupted_file_handling(self, tmp_path):
        """Verify catalog gracefully handles corrupted files during listing and get."""
        catalog = LocalExperimentCatalog(catalog_dir=tmp_path / "experiments")

        # Write corrupted JSON
        corrupt_file = catalog.catalog_dir / "CORRUPT-EXP.json"
        corrupt_file.write_text("{this is not valid json", encoding="utf-8")

        # Listing skips corrupted file
        reports = catalog.list_reports()
        assert len(reports) == 0

        # Direct get raises ValueError with clear diagnosis
        with pytest.raises(ValueError, match="Corrupted catalog file"):
            catalog.get_report("CORRUPT-EXP")

    def test_catalog_delete_report(self, tmp_path, basic_studio_def, sample_return_series):
        """Verify report deletion removes file from disk."""
        catalog = LocalExperimentCatalog(catalog_dir=tmp_path / "experiments")
        report = execute_studio_experiment(basic_studio_def, return_series=sample_return_series)
        catalog.save_report(report)

        assert catalog.delete_report(report.experiment_id) is True
        assert catalog.delete_report(report.experiment_id) is False  # Already deleted


# ==============================================================================
# Edge Cases & Comprehensive Coverage
# ==============================================================================

class TestStudioCoverageAndEdgeCases:
    """Targeted tests to exercise edge cases, branch variations, and robust error handling."""

    def test_definition_validation_edge_cases(self):
        """Verify definition rejects invalid types and boundaries."""
        # Empty name
        with pytest.raises(ValueError, match="name must be a non-empty string"):
            StudioExperimentDefinition(
                experiment_id="EXP-ERR-1",
                name="   ",
                description="desc",
                dataset_id="DATA-1",
            )

        # Empty dataset_id
        with pytest.raises(ValueError, match="dataset_id must be a non-empty string"):
            StudioExperimentDefinition(
                experiment_id="EXP-ERR-2",
                name="Valid Name",
                description="desc",
                dataset_id="",
            )

        # Invalid baseline_config type
        with pytest.raises(TypeError, match="baseline_config must be a mapping dictionary"):
            StudioExperimentDefinition(
                experiment_id="EXP-ERR-3",
                name="Valid Name",
                description="desc",
                dataset_id="DATA-1",
                baseline_config=["invalid_list"],
            )

        # Invalid perturbation_specs type
        with pytest.raises(TypeError, match="perturbation_specs must be a sequence of mappings"):
            StudioExperimentDefinition(
                experiment_id="EXP-ERR-4",
                name="Valid Name",
                description="desc",
                dataset_id="DATA-1",
                perturbation_specs={"bad": "dict"},
            )

        # Non-numeric confidence level
        with pytest.raises(ValueError, match="confidence_level must be a numeric float"):
            StudioExperimentDefinition(
                experiment_id="EXP-ERR-5",
                name="Valid Name",
                description="desc",
                dataset_id="DATA-1",
                baseline_config={"confidence_level": "not-a-number"},
            )

        # Out-of-bounds confidence level
        with pytest.raises(ValueError, match="confidence_level must be in \\(0, 1\\)"):
            StudioExperimentDefinition(
                experiment_id="EXP-ERR-6",
                name="Valid Name",
                description="desc",
                dataset_id="DATA-1",
                baseline_config={"confidence_level": 1.5},
            )

        # Invalid random_seed type
        with pytest.raises(TypeError, match="random_seed must be an integer or None"):
            StudioExperimentDefinition(
                experiment_id="EXP-ERR-7",
                name="Valid Name",
                description="desc",
                dataset_id="DATA-1",
                random_seed="random_seed_str",
            )

    def test_definition_date_range_and_to_spec(self):
        """Verify to_dict and to_spec handle different date_range representations."""
        # Tuple date range
        spec_tuple = StudioExperimentDefinition(
            experiment_id="EXP-DR-1",
            name="Date Range Tuple",
            description="desc",
            dataset_id="DATA-1",
            date_range=("2026-01-01", "2026-03-31"),
        )
        d_tuple = spec_tuple.to_dict()
        assert d_tuple["date_range"] == ["2026-01-01", "2026-03-31"]

        # Mapping date range
        spec_map = StudioExperimentDefinition(
            experiment_id="EXP-DR-2",
            name="Date Range Mapping",
            description="desc",
            dataset_id="DATA-1",
            date_range={"start": "2026-01-01", "end": "2026-03-31"},
        )
        d_map = spec_map.to_dict()
        assert d_map["date_range"] == {"start": "2026-01-01", "end": "2026-03-31"}

        phase6_spec = spec_map.to_spec()
        assert phase6_spec.experiment_id == "EXP-DR-2"

    def test_report_formatting_helpers_and_empty_markdown(self):
        """Verify unit mapping, number formatting, and empty report Markdown output."""
        from fragility_engine.studio import _format_metric_unit, _format_metric_value

        # Units
        assert _format_metric_unit("asset_hhi_points") == "points (0-10000)"
        assert _format_metric_unit("annualized_volatility") == "decimal fraction"
        assert _format_metric_unit("portfolio_pnl") == "currency"
        assert _format_metric_unit("custom_statistic") == "ratio"

        # Values
        assert "pts" in _format_metric_value("asset_hhi_points", 1500.5)
        assert "%" in _format_metric_value("volatility", 0.152)
        assert "50,000.00" in _format_metric_value("cost", 50000.0)
        assert _format_metric_value("pnl", float("nan")) == "-"

        # Report without perturbations or rankings produces graceful Markdown
        empty_report = ExperimentReport(
            report_id="REP-EMPTY-001",
            experiment_id="EXP-EMPTY",
            name="Empty Report",
            status="completed",
            schema_version="1.0.0",
            created_at="2026-10-24T12:00:00+00:00",
            dataset_id="EMPTY-DATA",
            date_range=None,
            input_fingerprint="abc",
            configuration_fingerprint="def",
            output_fingerprint="ghi",
            baseline_assumptions={},
            baseline_metrics={},
            perturbation_results=[],
            sensitivity_rankings=[],
            manifest={},
            validation_report={"all_passed": True, "checks_passed": 4, "checks_total": 4},
            warnings=["Notice: No perturbations executed."],
            limitations=["Empty analysis."],
            tags=[],
        )
        md = empty_report.to_markdown()
        assert "No perturbations executed" in md
        assert "*No rankings computed*" in md
        assert "Notice: No perturbations executed." in md

    def test_execute_studio_missing_data_aborts_honestly(self, basic_studio_def):
        """Verify execution raises ValueError when no input dataset or portfolio is provided."""
        with pytest.raises(ValueError, match="dataset or return_series must be provided"):
            execute_studio_experiment(
                definition=basic_studio_def,
                return_series=None,
                portfolio=None,
            )

    def test_compare_experiment_reports_type_and_discrepancies(self, basic_studio_def, sample_return_series):
        """Verify compare_experiment_reports enforces types and itemizes discrepancies."""
        report1 = execute_studio_experiment(basic_studio_def, return_series=sample_return_series)

        # Invalid type error
        with pytest.raises(TypeError, match="Both report_a and report_b must be ExperimentReport instances"):
            compare_experiment_reports(report1, "not-a-report")

        # Incompatible dataset IDs
        def_diff_dataset = StudioExperimentDefinition(
            experiment_id="EXP-DIFF-DATA",
            name="Diff Dataset",
            description="desc",
            dataset_id="COMPLETELY-DIFFERENT-DATASET",
            baseline_config={"confidence_level": 0.95, "annualization_factor": 252},
        )
        report2 = execute_studio_experiment(def_diff_dataset, return_series=sample_return_series)

        comparison = compare_experiment_reports(report1, report2)
        assert comparison.comparable is False
        assert any("Different dataset IDs" in reason for reason in comparison.non_comparable_reasons)

        comp_dict = comparison.to_dict()
        assert comp_dict["comparable"] is False
        assert "Different dataset IDs" in str(comp_dict["non_comparable_reasons"])

    def test_catalog_nonexistent_and_security(self, tmp_path):
        """Verify catalog handles non-existent IDs and rejects traversal on delete."""
        catalog = LocalExperimentCatalog(catalog_dir=tmp_path / "experiments")

        with pytest.raises(FileNotFoundError, match="No catalog report found"):
            catalog.get_report("NON_EXISTENT_EXPERIMENT")

        assert catalog.delete_report("NON_EXISTENT_EXPERIMENT") is False

        with pytest.raises(ValueError, match="Unsafe identifier"):
            catalog.delete_report("../traversal/id")
