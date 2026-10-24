"""Unit tests for FragilityEngine foundation models and return calculation.

Validates domain contracts, error boundaries, input immutability, and deterministic returns.
"""

from __future__ import annotations

import math
import numpy as np
import pytest

from fragility_engine.models import Holding, Portfolio, MetricResult
from fragility_engine.returns import compute_simple_returns


# ============================================================================
# Holding Domain Model Tests
# ============================================================================

class TestHoldingModel:
    """Test suite for the Holding domain model."""

    def test_valid_holding_creation(self) -> None:
        """Verify standard valid holding instantiates correctly."""
        h = Holding(asset_id="NSE:HDFCBANK", quantity=100.0, price=1650.50, sector="Banking")
        assert h.asset_id == "NSE:HDFCBANK"
        assert h.quantity == 100.0
        assert h.price == 1650.50
        assert h.sector == "Banking"
        assert math.isclose(h.market_value, 165050.0, rel_tol=1e-9)

    def test_holding_immutability(self) -> None:
        """Verify holding fields cannot be mutated post-initialization."""
        h = Holding(asset_id="NSE:INFY", quantity=50.0, price=1500.0)
        with pytest.raises(Exception):  # FrozenInstanceError
            h.quantity = 60.0  # type: ignore

    def test_holding_serialization_roundtrip(self) -> None:
        """Verify to_dict and from_dict produce identical Holding objects."""
        original = Holding(
            asset_id="NSE:RELIANCE",
            quantity=25.0,
            price=2900.0,
            sector="Energy",
            metadata={"source": "NSE_HISTORICAL"},
        )
        data = original.to_dict()
        restored = Holding.from_dict(data)
        assert original == restored
        assert math.isclose(restored.market_value, 72500.0)

    @pytest.mark.parametrize(
        "invalid_id",
        ["", "   ", None, 123],
    )
    def test_reject_invalid_asset_id(self, invalid_id: str) -> None:
        """Verify empty or non-string asset_id is rejected."""
        with pytest.raises(ValueError):
            Holding(asset_id=invalid_id, quantity=10.0, price=100.0)

    @pytest.mark.parametrize(
        "invalid_qty",
        [0.0, -5.0, float("nan"), float("inf"), float("-inf"), "invalid"],
    )
    def test_reject_invalid_quantity(self, invalid_qty: float) -> None:
        """Verify non-positive and non-finite quantities are rejected."""
        with pytest.raises(ValueError):
            Holding(asset_id="NSE:TCS", quantity=invalid_qty, price=3800.0)

    @pytest.mark.parametrize(
        "invalid_px",
        [0.0, -100.0, float("nan"), float("inf"), float("-inf"), "invalid"],
    )
    def test_reject_invalid_price(self, invalid_px: float) -> None:
        """Verify non-positive and non-finite prices are rejected."""
        with pytest.raises(ValueError):
            Holding(asset_id="NSE:TCS", quantity=10.0, price=invalid_px)

    def test_reject_empty_sector_string(self) -> None:
        """Verify empty whitespace sector string is rejected."""
        with pytest.raises(ValueError):
            Holding(asset_id="NSE:TCS", quantity=10.0, price=100.0, sector="  ")


# ============================================================================
# Portfolio Domain Model Tests
# ============================================================================

class TestPortfolioModel:
    """Test suite for the Portfolio domain model."""

    def test_valid_portfolio_creation(self) -> None:
        """Verify valid portfolio instantiates and computes valuations and weights."""
        h1 = Holding(asset_id="NSE:HDFCBANK", quantity=100.0, price=1000.0, sector="Banking")
        h2 = Holding(asset_id="NSE:INFY", quantity=200.0, price=500.0, sector="IT")
        p = Portfolio(
            portfolio_id="port_01",
            name="Illustrative Balanced",
            currency="INR",
            holdings=(h1, h2),
        )

        assert p.portfolio_id == "port_01"
        assert p.name == "Illustrative Balanced"
        assert p.currency == "INR"
        assert math.isclose(p.total_value, 200000.0)
        assert math.isclose(p.weights["NSE:HDFCBANK"], 0.5)
        assert math.isclose(p.weights["NSE:INFY"], 0.5)
        assert sum(p.weights.values()) == pytest.approx(1.0)
        assert p.asset_ids == ["NSE:HDFCBANK", "NSE:INFY"]

    def test_portfolio_get_holding(self) -> None:
        """Verify case-insensitive lookup of holdings."""
        h = Holding(asset_id="NSE:TCS", quantity=10.0, price=3500.0)
        p = Portfolio(
            portfolio_id="p1",
            name="Tech Only",
            currency="INR",
            holdings=(h,),
        )
        assert p.get_holding("NSE:TCS") == h
        assert p.get_holding("nse:tcs") == h
        assert p.get_holding("NON_EXISTENT") is None

    def test_portfolio_serialization_roundtrip(self) -> None:
        """Verify to_dict and from_dict roundtrip."""
        h1 = Holding(asset_id="NSE:ITC", quantity=500.0, price=400.0, sector="FMCG")
        p = Portfolio(
            portfolio_id="port_fmcg",
            name="FMCG Portfolio",
            currency="INR",
            holdings=(h1,),
            metadata={"created_by": "unit_test"},
        )
        data = p.to_dict()
        restored = Portfolio.from_dict(data)
        assert p.portfolio_id == restored.portfolio_id
        assert p.currency == restored.currency
        assert math.isclose(p.total_value, restored.total_value)
        assert len(restored.holdings) == 1
        assert restored.holdings[0].asset_id == "NSE:ITC"

    def test_reject_empty_holdings(self) -> None:
        """Verify portfolio with empty holdings is rejected."""
        with pytest.raises(ValueError, match="at least one holding"):
            Portfolio(portfolio_id="p0", name="Empty", currency="INR", holdings=())

    def test_reject_duplicate_asset_ids(self) -> None:
        """Verify duplicate asset IDs in a portfolio are rejected."""
        h1 = Holding(asset_id="NSE:RELIANCE", quantity=10.0, price=2800.0)
        h2 = Holding(asset_id="NSE:RELIANCE", quantity=20.0, price=2850.0)
        with pytest.raises(ValueError, match="Duplicate asset_id"):
            Portfolio(portfolio_id="p_dup", name="Dup", currency="INR", holdings=(h1, h2))

    @pytest.mark.parametrize("invalid_currency", ["", "IN", "INDIA", "12", None])
    def test_reject_invalid_currency(self, invalid_currency: str) -> None:
        """Verify currency must be 3 characters."""
        h = Holding(asset_id="NSE:SBIN", quantity=100.0, price=750.0)
        with pytest.raises(ValueError, match="3-letter"):
            Portfolio(portfolio_id="p_curr", name="Currency Test", currency=invalid_currency, holdings=(h,))


# ============================================================================
# MetricResult Domain Model Tests
# ============================================================================

class TestMetricResultModel:
    """Test suite for MetricResult domain model."""

    def test_valid_metric_result(self) -> None:
        """Verify valid metric result creation and dictionary serialization."""
        m = MetricResult(
            metric_id="historical_var_95",
            value=0.0215,
            unit="ratio",
            methodology="Historical simulation on 252 daily returns (Northstar definition)",
            parameters={"confidence_level": 0.95, "window": 252},
            warnings=("Data lookback contains 1 holiday gap",),
        )
        assert m.metric_id == "historical_var_95"
        assert math.isclose(m.value, 0.0215)
        assert m.unit == "ratio"
        assert "Historical simulation" in m.methodology
        assert len(m.warnings) == 1
        assert isinstance(m.timestamp, str)

        d = m.to_dict()
        assert d["metric_id"] == "historical_var_95"
        assert d["value"] == 0.0215
        assert d["warnings"] == ["Data lookback contains 1 holiday gap"]

    @pytest.mark.parametrize("invalid_val", [float("nan"), float("inf"), float("-inf"), "invalid"])
    def test_reject_non_finite_metric_value(self, invalid_val: float) -> None:
        """Verify non-finite metric values are rejected."""
        with pytest.raises(ValueError, match="strictly finite"):
            MetricResult(
                metric_id="test_metric",
                value=invalid_val,
                unit="percentage",
                methodology="Test method",
            )

    @pytest.mark.parametrize("invalid_field", ["", "   "])
    def test_reject_empty_metric_fields(self, invalid_field: str) -> None:
        """Verify empty metric_id, unit, or methodology are rejected."""
        with pytest.raises(ValueError):
            MetricResult(metric_id=invalid_field, value=1.0, unit="ratio", methodology="valid")
        with pytest.raises(ValueError):
            MetricResult(metric_id="valid", value=1.0, unit=invalid_field, methodology="valid")
        with pytest.raises(ValueError):
            MetricResult(metric_id="valid", value=1.0, unit="ratio", methodology=invalid_field)


# ============================================================================
# Return Calculation Utility Tests
# ============================================================================

class TestReturnCalculation:
    """Test suite for compute_simple_returns pure function."""

    def test_known_return_series(self) -> None:
        """Verify expected arithmetic returns on a known sequence."""
        # Prices: 100 -> 110 (+10%), 110 -> 99 (-10%), 99 -> 108.9 (+10%)
        prices = [100.0, 110.0, 99.0, 108.9]
        returns = compute_simple_returns(prices)
        assert isinstance(returns, np.ndarray)
        assert returns.dtype == np.float64
        assert len(returns) == 3

        expected = np.array([0.10, -0.10, 0.10], dtype=np.float64)
        np.testing.assert_allclose(returns, expected, rtol=1e-7, atol=1e-7)

    def test_constant_prices_yield_zero_returns(self) -> None:
        """Verify identical consecutive prices yield exactly zero returns."""
        prices = [500.0, 500.0, 500.0, 500.0]
        returns = compute_simple_returns(prices)
        assert len(returns) == 3
        np.testing.assert_array_equal(returns, np.zeros(3, dtype=np.float64))

    def test_numpy_array_input(self) -> None:
        """Verify function accepts numpy array as input."""
        prices = np.array([10.0, 15.0, 30.0], dtype=np.float64)
        returns = compute_simple_returns(prices)
        expected = np.array([0.5, 1.0], dtype=np.float64)
        np.testing.assert_allclose(returns, expected, rtol=1e-7)

    def test_input_immutability_list(self) -> None:
        """Verify caller-owned input list is not modified in-place."""
        original = [100.0, 120.0, 90.0]
        copy = list(original)
        _ = compute_simple_returns(original)
        assert original == copy

    def test_input_immutability_numpy(self) -> None:
        """Verify caller-owned numpy array is not modified in-place."""
        original = np.array([100.0, 120.0, 90.0], dtype=np.float64)
        copy = original.copy()
        _ = compute_simple_returns(original)
        np.testing.assert_array_equal(original, copy)

    @pytest.mark.parametrize("insufficient", [[], [100.0]])
    def test_reject_insufficient_data(self, insufficient: list[float]) -> None:
        """Verify fewer than two prices raises ValueError."""
        with pytest.raises(ValueError, match="at least two price observations"):
            compute_simple_returns(insufficient)

    def test_reject_none_input(self) -> None:
        """Verify passing None raises TypeError."""
        with pytest.raises(TypeError):
            compute_simple_returns(None)  # type: ignore

    @pytest.mark.parametrize(
        "invalid_price_sequence",
        [
            [100.0, 0.0, 105.0],          # Zero price
            [100.0, -10.0, 105.0],        # Negative price
            [100.0, float("nan"), 105.0], # NaN price
            [100.0, float("inf"), 105.0], # Infinite price
            [100.0, None, 105.0],         # None element
            [100.0, "invalid", 105.0],    # Non-numeric string
        ],
    )
    def test_reject_invalid_price_elements(self, invalid_price_sequence: list[object]) -> None:
        """Verify zero, negative, NaN, Inf, None, and non-numeric prices are rejected."""
        with pytest.raises(ValueError):
            compute_simple_returns(invalid_price_sequence)  # type: ignore

    def test_chronological_ordering_preserved(self) -> None:
        """Verify return series ordering corresponds strictly to chronological price steps."""
        prices = [100.0, 200.0, 100.0]
        returns = compute_simple_returns(prices)
        assert returns[0] == pytest.approx(1.0)   # 100 -> 200 is +100%
        assert returns[1] == pytest.approx(-0.5)  # 200 -> 100 is -50%
