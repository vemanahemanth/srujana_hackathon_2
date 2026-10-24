"""Validation edge cases, boundary audits, and HHI re-verification tests.

Fulfills Phase 4.1 verification requirements across:
- Domain models (Holding, Portfolio, MetricResult)
- Price and simple return validation
- Concentration and independent HHI scaling
- Risk estimation boundaries (VaR, ES, Drawdown)
- Scenario engine validation and edge cases
"""

from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Dict, List

import pytest

from fragility_engine.concentration import (
    ConcentrationAnalysis,
    calculate_hhi,
    calculate_portfolio_concentration,
    calculate_sector_allocations,
)
from fragility_engine.models import Holding, MetricResult, Portfolio
from fragility_engine.portfolio_loader import (
    export_portfolio_to_csv,
    load_portfolio_from_csv,
    load_portfolio_from_json,
)
from fragility_engine.returns import compute_simple_returns
from fragility_engine.risk import (
    DrawdownResult,
    RiskMetricsReport,
    calculate_annualized_volatility,
    calculate_expected_shortfall,
    calculate_historical_var,
    calculate_maximum_drawdown,
    calculate_risk_report,
)
from fragility_engine.scenarios import (
    HoldingScenarioResult,
    ScenarioDefinition,
    ScenarioResult,
    SectorScenarioResult,
    apply_scenario,
    create_preset_scenario,
    validate_scenario_against_portfolio,
)


class TestDomainModelEdgeCases:
    """Audit domain model boundary conditions and serialization."""

    def test_holding_very_large_and_very_small_values(self) -> None:
        """Verify Holding handles extreme but finite floating-point magnitudes."""
        # Very large holding
        h_large = Holding("LARGE_ASSET", 1e12, 1e4, "MegaCap")
        assert h_large.market_value == 1e16

        # Very small holding
        h_small = Holding("TINY_ASSET", 1e-6, 1e-2, "MicroCap")
        assert math.isclose(h_small.market_value, 1e-8, rel_tol=1e-12)

    def test_holding_reject_empty_or_whitespace_sector(self) -> None:
        """Sector must be None or a non-empty string."""
        with pytest.raises(ValueError, match="sector must be None or a non-empty string"):
            Holding("ASSET_A", 10.0, 100.0, sector="   ")

    def test_portfolio_get_holding_unknown_returns_none(self) -> None:
        """get_holding returns None when asset is not present."""
        port = Portfolio("p1", "Test Port", "INR", (Holding("A1", 10.0, 100.0),))
        assert port.get_holding("UNKNOWN_ASSET") is None
        assert port.get_holding("a1") is not None  # Case-insensitive lookup

    def test_portfolio_dict_roundtrip(self) -> None:
        """Portfolio serialization to and from dictionary matches."""
        h1 = Holding("A1", 10.0, 100.0, "Tech", metadata={"source": "manual"})
        port = Portfolio("p1", "Test Port", "USD", (h1,), metadata={"created_by": "quant"})
        d = port.to_dict()
        reconstructed = Portfolio.from_dict(d)
        assert reconstructed.portfolio_id == port.portfolio_id
        assert reconstructed.currency == port.currency
        assert reconstructed.total_value == port.total_value
        assert reconstructed.holdings[0].asset_id == "A1"

    def test_metric_result_serialization_and_validation(self) -> None:
        """MetricResult validates unit, methodology, and serializes correctly."""
        with pytest.raises(ValueError, match="unit must be a non-empty string"):
            MetricResult("var_95", 0.05, "   ", "Historical method")

        with pytest.raises(ValueError, match="methodology must be a non-empty string"):
            MetricResult("var_95", 0.05, "ratio", "   ")

        m = MetricResult(
            metric_id="test_metric",
            value=42.0,
            unit="points",
            methodology="Analytical formula",
            parameters={"alpha": 0.05},
            warnings=("Sample size is low",),
        )
        d = m.to_dict()
        assert d["metric_id"] == "test_metric"
        assert d["value"] == 42.0
        assert d["unit"] == "points"
        assert d["warnings"] == ["Sample size is low"]


class TestReturnsValidationEdgeCases:
    """Audit returns calculation error handling and non-mutation."""

    def test_returns_reject_unsized_or_none_inputs(self) -> None:
        with pytest.raises(TypeError, match="prices sequence cannot be None"):
            compute_simple_returns(None)  # type: ignore

        with pytest.raises(TypeError, match="prices must be a sized sequence or array"):
            compute_simple_returns(12345)  # type: ignore

    def test_returns_repeated_constant_prices(self) -> None:
        """Flat constant prices yield strictly zero returns."""
        prices = [100.0, 100.0, 100.0, 100.0]
        r = compute_simple_returns(prices)
        assert len(r) == 3
        assert all(val == 0.0 for val in r)

    def test_returns_reject_non_numeric_elements(self) -> None:
        with pytest.raises(ValueError, match="Price at index 1 could not be converted to float"):
            compute_simple_returns([100.0, "not_a_number", 105.0])  # type: ignore

    def test_returns_input_immutability(self) -> None:
        original = [100.0, 105.0, 110.0]
        original_copy = list(original)
        _ = compute_simple_returns(original)
        assert original == original_copy


class TestIndependentHHIAndConcentration:
    """Independent verification of HHI mathematical properties."""

    def test_hhi_weight_normalization_behavior(self) -> None:
        """Unnormalized weights (sum != 1.0) must be normalized automatically."""
        # Raw proportions summing to 4.0: [2.0, 2.0] -> normalized: [0.5, 0.5]
        # HHI = 0.5^2 + 0.5^2 = 0.5 (5,000 points)
        dec_hhi, pts_hhi = calculate_hhi([2.0, 2.0])
        assert math.isclose(dec_hhi, 0.50, rel_tol=1e-12)
        assert math.isclose(pts_hhi, 5000.0, rel_tol=1e-12)

    def test_hhi_single_asset_portfolio(self) -> None:
        """A single asset portfolio has HHI of exactly 1.0 (10,000 points)."""
        dec_hhi, pts_hhi = calculate_hhi([1.0])
        assert dec_hhi == 1.0
        assert pts_hhi == 10000.0

    def test_hhi_equal_weight_spectrum(self) -> None:
        """N equal-weight assets yield HHI = 1/N and points = 10,000/N."""
        for n in [2, 4, 5, 10, 20, 50, 100]:
            weights = [1.0 / n] * n
            dec_hhi, pts_hhi = calculate_hhi(weights)
            expected_dec = 1.0 / n
            expected_pts = 10000.0 / n
            assert math.isclose(dec_hhi, expected_dec, rel_tol=1e-9)
            assert math.isclose(pts_hhi, expected_pts, rel_tol=1e-9)

    def test_hhi_reject_zero_or_negative_sum(self) -> None:
        with pytest.raises(ValueError, match="Sum of weights must be positive"):
            calculate_hhi([0.0, 0.0])

    def test_concentration_analysis_serialization(self) -> None:
        holdings = (
            Holding("A1", 10.0, 100.0, "Tech"),
            Holding("A2", 20.0, 50.0, "Finance"),
        )
        port = Portfolio("p1", "Test Port", "INR", holdings)
        conc = calculate_portfolio_concentration(port)
        d = conc.to_dict()
        assert d["total_market_value"] == 2000.0
        assert "asset_weights" in d
        assert "sector_market_values" in d
        assert "asset_hhi_decimal" in d
        assert "sector_hhi_points" in d


class TestPortfolioLoaderEdgeCases:
    """Audit JSON and CSV loader stream inputs and invalid formats."""

    def test_load_json_from_textio_stream(self) -> None:
        json_content = """{
            "portfolio_id": "stream_port",
            "name": "Stream Portfolio",
            "currency": "INR",
            "holdings": [
                {"asset_id": "NSE:INFY", "quantity": 10.0, "price": 1500.0, "sector": "IT"}
            ]
        }"""
        stream = io.StringIO(json_content)
        port = load_portfolio_from_json(stream)
        assert port.portfolio_id == "stream_port"
        assert port.total_value == 15000.0

    def test_load_json_reject_non_dict_root(self) -> None:
        with pytest.raises(ValueError, match="JSON root must be an object/dict"):
            load_portfolio_from_json('["not", "a", "dict"]')

    def test_load_json_reject_invalid_holding_type(self) -> None:
        bad_json = """{
            "portfolio_id": "p1", "name": "P1", "currency": "INR",
            "holdings": ["not_a_dict_holding"]
        }"""
        with pytest.raises(ValueError, match="Holding at index 1 must be a dictionary"):
            load_portfolio_from_json(bad_json)

    def test_load_json_reject_missing_holding_fields(self) -> None:
        bad_json = """{
            "portfolio_id": "p1", "name": "P1", "currency": "INR",
            "holdings": [{"asset_id": "A1", "quantity": 10.0}]
        }"""
        with pytest.raises(ValueError, match="Holding at index 1 missing required field: 'price'"):
            load_portfolio_from_json(bad_json)

    def test_load_csv_from_textio_stream(self) -> None:
        csv_content = "asset_id,quantity,price,sector\nNSE:TCS,10,4000.0,IT\n"
        stream = io.StringIO(csv_content)
        port = load_portfolio_from_csv(stream)
        assert port.total_value == 40000.0

    def test_export_portfolio_to_textio_stream(self) -> None:
        port = Portfolio("p1", "P1", "INR", (Holding("A1", 10.0, 100.0, "Tech"),))
        stream = io.StringIO()
        csv_str = export_portfolio_to_csv(port, stream)
        assert "asset_id,quantity,price,sector" in csv_str
        assert "A1,10.0,100.0,Tech" in stream.getvalue()

    def test_export_reject_non_portfolio_instance(self) -> None:
        with pytest.raises(TypeError, match="portfolio must be a Portfolio instance"):
            export_portfolio_to_csv("not_a_portfolio")  # type: ignore


class TestRiskMetricsEdgeCases:
    """Audit risk engine edge cases and validation."""

    def test_risk_metrics_report_serialization(self) -> None:
        returns = [0.01, -0.02, 0.015, -0.005, 0.02, -0.01]
        rep = calculate_risk_report(returns, annualization_factor=252.0)
        d = rep.to_dict()
        assert "volatility_annualized" in d
        assert "var_95" in d
        assert "expected_shortfall_95" in d
        assert "observations_count" in d
        assert d["observations_count"] == 6

    def test_drawdown_strictly_flat_equity_curve(self) -> None:
        """Constant equity curve has zero drawdown."""
        curve = [100.0, 100.0, 100.0, 100.0]
        dd = calculate_maximum_drawdown(curve)
        assert dd.max_drawdown == 0.0
        assert dd.peak_value == 100.0
        assert dd.trough_value == 100.0
        assert dd.peak_to_trough_duration == 0

    def test_drawdown_monotonically_decreasing_curve(self) -> None:
        """Steadily declining curve: unrecovered, trough at the very end."""
        curve = [100.0, 90.0, 80.0, 70.0]
        dd = calculate_maximum_drawdown(curve)
        assert math.isclose(dd.max_drawdown, 0.30, rel_tol=1e-9)
        assert dd.peak_index == 0
        assert dd.trough_index == 3
        assert dd.peak_to_trough_duration == 3
        assert dd.is_recovered is False
        assert dd.recovery_duration is None


class TestScenarioLabEdgeCases:
    """Audit Scenario Lab domain model validation and edge cases."""

    def test_scenario_definition_serialization(self) -> None:
        scen = ScenarioDefinition(
            scenario_id="scen_custom",
            name="Custom Scenario",
            description="Testing serialization",
            sector_shocks={"Banking": -0.10},
            asset_shocks={"NSE:TCS": 0.05},
            metadata={"source": "risk_team"},
            version="1.2",
        )
        d = scen.to_dict()
        assert d["scenario_id"] == "scen_custom"
        assert d["version"] == "1.2"
        assert d["sector_shocks"]["Banking"] == -0.10
        assert d["asset_shocks"]["NSE:TCS"] == 0.05

    def test_scenario_definition_reject_empty_version(self) -> None:
        with pytest.raises(ValueError, match="version must be a non-empty string"):
            ScenarioDefinition(scenario_id="s1", name="N1", version="   ")

    def test_scenario_definition_reject_blank_sector_name(self) -> None:
        with pytest.raises(ValueError, match="Sector names in sector_shocks must be non-empty strings"):
            ScenarioDefinition(scenario_id="s1", name="N1", sector_shocks={"  ": -0.10})

    def test_scenario_definition_reject_blank_asset_id(self) -> None:
        with pytest.raises(ValueError, match="Asset IDs in asset_shocks must be non-empty strings"):
            ScenarioDefinition(scenario_id="s1", name="N1", asset_shocks={"  ": 0.05})

    def test_validate_scenario_reject_non_portfolio_type(self) -> None:
        scen = ScenarioDefinition("s1", "N1")
        with pytest.raises(TypeError, match="portfolio must be an instance of Portfolio"):
            validate_scenario_against_portfolio(scen, "not_a_portfolio")  # type: ignore

    def test_validate_scenario_reject_non_scenario_type(self) -> None:
        port = Portfolio("p1", "P1", "INR", (Holding("A1", 10.0, 100.0),))
        with pytest.raises(TypeError, match="scenario must be an instance of ScenarioDefinition"):
            validate_scenario_against_portfolio("not_a_scenario", port)  # type: ignore

    def test_scenario_holding_without_sector_handled_safely(self) -> None:
        """Holding with sector=None is handled gracefully as unclassified."""
        port = Portfolio("p1", "P1", "INR", (Holding("A1", 10.0, 100.0, sector=None),))
        scen = ScenarioDefinition("s1", "N1", asset_shocks={"A1": -0.10})
        res = apply_scenario(port, scen)
        assert res.total_pnl == -100.0
        assert res.stressed_portfolio_value == 900.0
        assert res.holding_results[0].shock_source == "asset"
