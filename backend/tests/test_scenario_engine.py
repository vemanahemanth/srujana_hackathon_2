"""Unit tests for Phase 4 Scenario Lab Engine.

Covers:
1. Benchmark scenario: Banking -20% and IT -10% on the illustrative ₹10 lakh portfolio.
2. Exact expected stressed portfolio value and monetary P&L.
3. Holding-level calculations (prices, market values, P&L contributions, shock source).
4. Sector-level P&L attribution and reconciliation.
5. Explicit unshocked holdings identification.
6. Asset-specific shocks.
7. Sector/asset conflict rejection (no silent combination or precedence).
8. Zero-shock invariance.
9. Positive shocks and mixed shocks.
10. Non-finite shocks and non-positive-price-producing shocks.
11. Unknown sectors and assets.
12. Duplicate/invalid scenario definitions.
13. Input and portfolio immutability.
14. Deterministic repeated execution.
15. Mathematical reconciliation of total P&L to holding and sector contributions.
16. Regression tests for confirmed Phase 3 defects.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from fragility_engine.models import Holding, Portfolio
from fragility_engine.portfolio_loader import load_portfolio_from_json
from fragility_engine.risk import (
    calculate_expected_shortfall,
    calculate_historical_var,
    calculate_maximum_drawdown,
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


@pytest.fixture
def sample_portfolio() -> Portfolio:
    """Load standard ₹10 lakh 10-holding sample portfolio."""
    fixture_path = (
        Path(__file__).parent.parent.parent
        / "data"
        / "sample_portfolios"
        / "nse_10l.json"
    )
    return load_portfolio_from_json(fixture_path)


@pytest.fixture
def simple_three_holding_portfolio() -> Portfolio:
    """Small deterministic three-holding portfolio for isolated edge cases."""
    holdings = (
        Holding("ASSET_A", 10.0, 100.0, "Tech"),      # MV = 1,000.0
        Holding("ASSET_B", 20.0, 50.0, "Finance"),    # MV = 1,000.0
        Holding("ASSET_C", 5.0, 200.0, "Tech"),       # MV = 1,000.0
    )
    return Portfolio("test_port", "Test Portfolio", "INR", holdings)


class TestBenchmarkScenarioOnSamplePortfolio:
    """Requirement 1-5: Banking -20% and IT -10% on ₹10 Lakh Portfolio."""

    def test_benchmark_preset_exact_values(self, sample_portfolio: Portfolio) -> None:
        """Verify exact hand-calculated figures for Banking -20% and IT -10%."""
        scenario = create_preset_scenario("banking_minus_20_it_minus_10")
        result = apply_scenario(sample_portfolio, scenario)

        # 1. Total Portfolio figures
        assert result.original_portfolio_value == 1_000_000.0
        # Banking total: 160k + 80k + 60k = 300k. At -20% -> 240k (-60k P&L)
        # IT total: 120k + 80k = 200k. At -10% -> 180k (-20k P&L)
        # Unshocked: 500k.
        # Stressed portfolio = 240k + 180k + 500k = 920,000.0
        assert result.stressed_portfolio_value == 920_000.0
        assert result.total_pnl == -80_000.0
        assert result.scenario_return == -0.08
        assert result.loss_magnitude == 80_000.0

        # 2. Sector-level attribution
        sector_results_dict = {s.sector: s for s in result.sector_results}
        portfolio_sectors = {h.sector for h in sample_portfolio.holdings if h.sector}
        assert set(sector_results_dict.keys()) == portfolio_sectors

        # Banking sector
        banking_s = sector_results_dict["Banking"]
        assert banking_s.original_value == 300_000.0
        assert banking_s.stressed_value == 240_000.0
        assert banking_s.pnl_contribution == -60_000.0
        assert math.isclose(banking_s.percentage_return, -0.20, rel_tol=1e-12)

        # Information Technology sector
        it_s = sector_results_dict["Information Technology"]
        assert it_s.original_value == 200_000.0
        assert it_s.stressed_value == 180_000.0
        assert it_s.pnl_contribution == -20_000.0
        assert math.isclose(it_s.percentage_return, -0.10, rel_tol=1e-12)

        # Unshocked sectors (Energy, FMCG, Healthcare, Industrials)
        for s_name in ["Energy", "FMCG", "Healthcare", "Industrials"]:
            s_res = sector_results_dict[s_name]
            assert s_res.pnl_contribution == 0.0
            assert s_res.stressed_value == s_res.original_value
            assert s_res.percentage_return == 0.0

        # 3. Holding-level calculations
        holding_map = {h.asset_id: h for h in result.holding_results}
        assert len(holding_map) == 10

        # NSE:HDFCBANK: 100 * 1600 = 160,000 -> -20% -> price 1280, MV 128,000, PnL -32,000
        hdfc = holding_map["NSE:HDFCBANK"]
        assert hdfc.applied_shock == -0.20
        assert hdfc.shock_source == "sector"
        assert hdfc.stressed_price == 1280.0
        assert hdfc.stressed_market_value == 128_000.0
        assert hdfc.pnl_contribution == -32_000.0

        # NSE:ICICIBANK: 80 * 1000 = 80,000 -> -20% -> price 800, MV 64,000, PnL -16,000
        icici = holding_map["NSE:ICICIBANK"]
        assert icici.applied_shock == -0.20
        assert icici.shock_source == "sector"
        assert icici.stressed_price == 800.0
        assert icici.stressed_market_value == 64_000.0
        assert icici.pnl_contribution == -16_000.0

        # NSE:SBIN: 100 * 600 = 60,000 -> -20% -> price 480, MV 48,000, PnL -12,000
        sbin = holding_map["NSE:SBIN"]
        assert sbin.applied_shock == -0.20
        assert sbin.shock_source == "sector"
        assert sbin.stressed_price == 480.0
        assert sbin.stressed_market_value == 48_000.0
        assert sbin.pnl_contribution == -12_000.0

        # NSE:INFY: 80 * 1500 = 120,000 -> -10% -> price 1350, MV 108,000, PnL -12,000
        infy = holding_map["NSE:INFY"]
        assert infy.applied_shock == -0.10
        assert infy.shock_source == "sector"
        assert infy.stressed_price == 1350.0
        assert infy.stressed_market_value == 108_000.0
        assert infy.pnl_contribution == -12_000.0

        # NSE:TCS: 20 * 4000 = 80,000 -> -10% -> price 3600, MV 72,000, PnL -8,000
        tcs = holding_map["NSE:TCS"]
        assert tcs.applied_shock == -0.10
        assert tcs.shock_source == "sector"
        assert tcs.stressed_price == 3600.0
        assert tcs.stressed_market_value == 72_000.0
        assert tcs.pnl_contribution == -8_000.0

        # 4. Explicit unshocked holdings identification
        expected_unshocked = {"NSE:RELIANCE", "NSE:ITC", "NSE:HINDUNILVR", "NSE:SUNPHARMA", "NSE:LT"}
        assert set(result.unshocked_assets) == expected_unshocked
        for unshocked_id in expected_unshocked:
            u_res = holding_map[unshocked_id]
            assert u_res.applied_shock == 0.0
            assert u_res.shock_source == "none"
            assert u_res.pnl_contribution == 0.0
            assert u_res.stressed_price == u_res.original_price
            assert u_res.stressed_market_value == u_res.original_market_value


class TestAssetSpecificShocks:
    """Requirement 6: Asset-specific shocks."""

    def test_pure_asset_specific_shocks(self, sample_portfolio: Portfolio) -> None:
        """Apply shocks targeted exclusively to individual assets."""
        scenario = ScenarioDefinition(
            scenario_id="asset_shock_custom",
            name="Custom Asset Shocks",
            asset_shocks={"NSE:RELIANCE": 0.05, "NSE:TCS": -0.15},
            sector_shocks={},
        )
        res = apply_scenario(sample_portfolio, scenario)

        # NSE:RELIANCE: 150,000 * +5% = +7,500 PnL, stressed MV = 157,500
        rel = [h for h in res.holding_results if h.asset_id == "NSE:RELIANCE"][0]
        assert rel.applied_shock == 0.05
        assert rel.shock_source == "asset"
        assert rel.stressed_market_value == 157_500.0
        assert rel.pnl_contribution == 7_500.0

        # NSE:TCS: 80,000 * -15% = -12,000 PnL, stressed MV = 68,000
        tcs = [h for h in res.holding_results if h.asset_id == "NSE:TCS"][0]
        assert tcs.applied_shock == -0.15
        assert tcs.shock_source == "asset"
        assert tcs.stressed_market_value == 68_000.0
        assert tcs.pnl_contribution == -12_000.0

        # Total PnL = +7,500 - 12,000 = -4,500
        assert res.total_pnl == -4_500.0
        assert res.stressed_portfolio_value == 995_500.0
        assert res.loss_magnitude == 4_500.0
        assert len(res.unshocked_assets) == 8


class TestSectorAssetConflictRejection:
    """Requirement 7: Sector and asset-specific conflict rejection policy."""

    def test_conflict_rejected_by_default(self, sample_portfolio: Portfolio) -> None:
        """Reject execution when a holding is targeted by both sector and asset shocks."""
        scenario = ScenarioDefinition(
            scenario_id="conflicting_scenario",
            name="Conflicting Scenario",
            sector_shocks={"Banking": -0.20},
            asset_shocks={"NSE:HDFCBANK": -0.10},  # NSE:HDFCBANK is in Banking!
        )
        with pytest.raises(ValueError, match="Conflicting scenario rules targeting holding 'NSE:HDFCBANK'"):
            apply_scenario(sample_portfolio, scenario)

    def test_non_overlapping_sector_and_asset_shocks_allowed(
        self, sample_portfolio: Portfolio
    ) -> None:
        """Sector and asset shocks targeting disjoint holdings are valid."""
        scenario = ScenarioDefinition(
            scenario_id="disjoint_scenario",
            name="Disjoint Scenario",
            sector_shocks={"Banking": -0.20},
            asset_shocks={"NSE:RELIANCE": 0.10},  # RELIANCE is Energy, not Banking
        )
        res = apply_scenario(sample_portfolio, scenario)
        assert res.stressed_portfolio_value is not None
        rel = [h for h in res.holding_results if h.asset_id == "NSE:RELIANCE"][0]
        assert rel.shock_source == "asset"
        hdfc = [h for h in res.holding_results if h.asset_id == "NSE:HDFCBANK"][0]
        assert hdfc.shock_source == "sector"


class TestZeroShockInvariance:
    """Requirement 8: Zero-shock invariance."""

    def test_empty_scenario_leaves_portfolio_unchanged(
        self, sample_portfolio: Portfolio
    ) -> None:
        """A scenario with empty shocks preserves all values with zero P&L."""
        scenario = ScenarioDefinition(
            scenario_id="null_scenario",
            name="Null Scenario",
            sector_shocks={},
            asset_shocks={},
        )
        res = apply_scenario(sample_portfolio, scenario)
        assert res.stressed_portfolio_value == res.original_portfolio_value == 1_000_000.0
        assert res.total_pnl == 0.0
        assert res.scenario_return == 0.0
        assert res.loss_magnitude == 0.0
        assert len(res.unshocked_assets) == 10

    def test_explicit_zero_shocks(self, sample_portfolio: Portfolio) -> None:
        """Explicit 0.0 sector shocks produce zero P&L."""
        scenario = ScenarioDefinition(
            scenario_id="zero_shock_scenario",
            name="Zero Shock Scenario",
            sector_shocks={"Banking": 0.0},
            asset_shocks={"NSE:RELIANCE": 0.0},
        )
        res = apply_scenario(sample_portfolio, scenario)
        assert res.total_pnl == 0.0
        assert res.stressed_portfolio_value == 1_000_000.0
        assert res.loss_magnitude == 0.0


class TestPositiveAndMixedShocks:
    """Requirement 9: Positive shocks and gain behavior."""

    def test_positive_shock_yields_zero_loss_magnitude(
        self, sample_portfolio: Portfolio
    ) -> None:
        """When total P&L is positive, loss_magnitude must be exactly 0.0."""
        scenario = ScenarioDefinition(
            scenario_id="rally_scenario",
            name="Broad Rally",
            sector_shocks={"Information Technology": 0.25},  # +25% on 200k = +50,000
            asset_shocks={},
        )
        res = apply_scenario(sample_portfolio, scenario)
        assert res.total_pnl == 50_000.0
        assert res.stressed_portfolio_value == 1_050_000.0
        assert res.scenario_return == 0.05
        assert res.loss_magnitude == 0.0


class TestInvalidAndNonFiniteShocks:
    """Requirement 10: Validation of non-finite and price-destroying shocks."""

    @pytest.mark.parametrize("invalid_shock", [float("nan"), float("inf"), float("-inf")])
    def test_reject_non_finite_sector_shock(self, invalid_shock: float) -> None:
        with pytest.raises(ValueError, match="must be a finite numeric value"):
            ScenarioDefinition(
                scenario_id="bad_sector",
                name="Bad Sector",
                sector_shocks={"Banking": invalid_shock},
            )

    @pytest.mark.parametrize("invalid_shock", [float("nan"), float("inf"), float("-inf")])
    def test_reject_non_finite_asset_shock(self, invalid_shock: float) -> None:
        with pytest.raises(ValueError, match="must be a finite numeric value"):
            ScenarioDefinition(
                scenario_id="bad_asset",
                name="Bad Asset",
                asset_shocks={"NSE:TCS": invalid_shock},
            )

    @pytest.mark.parametrize("lethal_shock", [-1.0, -1.05, -2.0])
    def test_reject_shock_producing_zero_or_negative_price(self, lethal_shock: float) -> None:
        with pytest.raises(ValueError, match="produces zero or negative prices"):
            ScenarioDefinition(
                scenario_id="lethal_shock",
                name="Lethal Shock",
                sector_shocks={"Banking": lethal_shock},
            )


class TestUnknownSectorsAndAssets:
    """Requirement 11: Reject unknown sectors and assets."""

    def test_reject_unknown_sector(self, sample_portfolio: Portfolio) -> None:
        scenario = ScenarioDefinition(
            scenario_id="unknown_sec",
            name="Unknown Sector",
            sector_shocks={"Cryptocurrency": -0.50},
        )
        with pytest.raises(ValueError, match="Unknown sector in scenario: 'Cryptocurrency'"):
            apply_scenario(sample_portfolio, scenario)

    def test_reject_unknown_asset(self, sample_portfolio: Portfolio) -> None:
        scenario = ScenarioDefinition(
            scenario_id="unknown_asset",
            name="Unknown Asset",
            asset_shocks={"BITCOIN": -0.50},
        )
        with pytest.raises(ValueError, match="Unknown asset in scenario: 'BITCOIN'"):
            apply_scenario(sample_portfolio, scenario)


class TestScenarioDefinitionValidation:
    """Requirement 12: Scenario specification constraints."""

    @pytest.mark.parametrize("bad_id", ["", "   ", None])
    def test_reject_invalid_scenario_id(self, bad_id: str) -> None:
        with pytest.raises(ValueError, match="scenario_id must be a non-empty string"):
            ScenarioDefinition(scenario_id=bad_id, name="Valid Name")

    @pytest.mark.parametrize("bad_name", ["", "   ", None])
    def test_reject_invalid_scenario_name(self, bad_name: str) -> None:
        with pytest.raises(ValueError, match="name must be a non-empty string"):
            ScenarioDefinition(scenario_id="valid_id", name=bad_name)

    def test_reject_unknown_preset_id(self) -> None:
        with pytest.raises(ValueError, match="Unknown preset scenario ID"):
            create_preset_scenario("non_existent_preset")


class TestImmutabilityAndDeterminism:
    """Requirement 13-14: Immutability and deterministic execution."""

    def test_portfolio_not_mutated_by_scenario(self, sample_portfolio: Portfolio) -> None:
        """Ensure original portfolio holdings and prices remain strictly unchanged."""
        holdings_before = [(h.asset_id, h.price, h.quantity, h.market_value) for h in sample_portfolio.holdings]
        scenario = create_preset_scenario("banking_minus_20_it_minus_10")
        _ = apply_scenario(sample_portfolio, scenario)
        holdings_after = [(h.asset_id, h.price, h.quantity, h.market_value) for h in sample_portfolio.holdings]
        assert holdings_before == holdings_after

    def test_deterministic_repeated_runs(self, sample_portfolio: Portfolio) -> None:
        """Executing the same scenario multiple times yields bitwise-identical results."""
        scenario = create_preset_scenario("banking_minus_20_it_minus_10")
        res1 = apply_scenario(sample_portfolio, scenario)
        res2 = apply_scenario(sample_portfolio, scenario)
        assert res1.to_dict() == res2.to_dict()


class TestPnLReconciliation:
    """Requirement 15: Exact reconciliation of total P&L to components."""

    def test_pnl_reconciliation_exactness(self, sample_portfolio: Portfolio) -> None:
        """Verify sum(holding_pnl) == portfolio_pnl and sum(sector_pnl) == portfolio_pnl."""
        scenario = ScenarioDefinition(
            scenario_id="multi_shock",
            name="Multi Shock",
            sector_shocks={"Banking": -0.15, "Energy": 0.08, "Healthcare": -0.05},
            asset_shocks={"NSE:TCS": 0.03},
        )
        res = apply_scenario(sample_portfolio, scenario)

        sum_holding_pnl = sum(h.pnl_contribution for h in res.holding_results)
        sum_sector_pnl = sum(s.pnl_contribution for s in res.sector_results)

        assert math.isclose(res.total_pnl, sum_holding_pnl, rel_tol=1e-12, abs_tol=1e-9)
        assert math.isclose(res.total_pnl, sum_sector_pnl, rel_tol=1e-12, abs_tol=1e-9)
        assert math.isclose(
            res.stressed_portfolio_value,
            res.original_portfolio_value + res.total_pnl,
            rel_tol=1e-12,
            abs_tol=1e-9,
        )


class TestPhase3DefectRegressionsInPhase4:
    """Requirement 16: Continuous regression protection for all confirmed Phase 3 defects."""

    def test_es_acerbi_tasche_coherence_preserved(self) -> None:
        """Verify Acerbi & Tasche (2002) Expected Shortfall fractional weighting."""
        returns = [-0.10, -0.04, -0.03, -0.02, -0.01, 0.01, 0.02, 0.03, 0.04, 0.05]
        # At 90% confidence, tail probability = 0.10. 10 * 0.10 = 1 observation.
        # Losses = -returns. Max loss = -(-0.10) = 0.10.
        es_90 = calculate_expected_shortfall(returns, confidence_level=0.90)
        var_90 = calculate_historical_var(returns, confidence_level=0.90)
        assert es_90 >= var_90
        assert math.isclose(es_90, 0.10, rel_tol=1e-9)

    def test_drawdown_unrecovered_partial_rebound(self) -> None:
        """Verify partial rebound is never classified as full recovery."""
        curve = [100.0, 70.0, 95.0]
        dd = calculate_maximum_drawdown(curve)
        assert dd.is_recovered is False
        assert dd.recovery_duration is None
        assert dd.recovery_index is None
        assert math.isclose(dd.max_drawdown, 0.30, rel_tol=1e-9)
