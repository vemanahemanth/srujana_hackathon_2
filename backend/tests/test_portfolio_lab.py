"""Unit and integration test suite for Portfolio Lab.

Covers:
- Sample fixture loading (JSON & CSV ₹10 Lakh NSE portfolio).
- Mathematical verification of exact ₹10,00,000 total market value.
- Strict CSV and JSON validation and error diagnostics.
- Portfolio valuation, asset weights, and sector breakdown.
- Herfindahl-Hirschman Index (HHI) hand-calculated reference verifications.
- CSV export/import round-trip equivalence.
"""

from __future__ import annotations

import math
from pathlib import Path
import pytest

from fragility_engine.concentration import (
    ConcentrationAnalysis,
    calculate_hhi,
    calculate_portfolio_concentration,
    calculate_sector_allocations,
)
from fragility_engine.models import Holding, Portfolio
from fragility_engine.portfolio_loader import (
    export_portfolio_to_csv,
    load_portfolio_from_csv,
    load_portfolio_from_json,
)


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SAMPLE_DIR = REPO_ROOT / "data" / "sample_portfolios"
JSON_FIXTURE = SAMPLE_DIR / "nse_10l.json"
CSV_FIXTURE = SAMPLE_DIR / "nse_10l.csv"


# ============================================================================
# 1. Sample Fixture & Valuation Tests
# ============================================================================

class TestSamplePortfolioFixtures:
    """Tests verifying the illustrative ₹10 Lakh NSE sample fixtures."""

    def test_json_fixture_exists_and_loads(self) -> None:
        """Verify that nse_10l.json exists and loads into a valid Portfolio."""
        assert JSON_FIXTURE.is_file(), f"Fixture file not found: {JSON_FIXTURE}"
        p = load_portfolio_from_json(JSON_FIXTURE)
        assert isinstance(p, Portfolio)
        assert p.currency == "INR"
        assert len(p.holdings) == 10
        assert "disclaimer" in p.metadata

    def test_csv_fixture_exists_and_loads(self) -> None:
        """Verify that nse_10l.csv exists and loads into a valid Portfolio."""
        assert CSV_FIXTURE.is_file(), f"Fixture file not found: {CSV_FIXTURE}"
        p = load_portfolio_from_csv(
            CSV_FIXTURE,
            portfolio_id="nse_10l_csv",
            name="Illustrative ₹10 Lakh NSE Portfolio (CSV)",
            currency="INR",
        )
        assert isinstance(p, Portfolio)
        assert p.currency == "INR"
        assert len(p.holdings) == 10

    def test_unrounded_total_equals_exactly_ten_lakh(self) -> None:
        """Verify unrounded holding market values sum to exactly ₹10,00,000.0."""
        p_json = load_portfolio_from_json(JSON_FIXTURE)
        p_csv = load_portfolio_from_csv(CSV_FIXTURE)

        # Exact unrounded float equality
        assert p_json.total_value == 1000000.0
        assert p_csv.total_value == 1000000.0

    def test_json_and_csv_fixtures_represent_identical_holdings(self) -> None:
        """Verify that JSON and CSV sample fixtures specify the same portfolio."""
        p_json = load_portfolio_from_json(JSON_FIXTURE)
        p_csv = load_portfolio_from_csv(CSV_FIXTURE)

        assert p_json.total_value == p_csv.total_value
        assert len(p_json.holdings) == len(p_csv.holdings)

        for h_json in p_json.holdings:
            h_csv = p_csv.get_holding(h_json.asset_id)
            assert h_csv is not None, f"Asset {h_json.asset_id} missing from CSV"
            assert h_json.quantity == h_csv.quantity
            assert h_json.price == h_csv.price
            assert h_json.sector == h_csv.sector
            assert h_json.market_value == h_csv.market_value


# ============================================================================
# 2. Strict Loader Validation Tests
# ============================================================================

class TestPortfolioLoaderValidation:
    """Tests verifying strict all-or-nothing validation for JSON and CSV loaders."""

    def test_csv_reject_missing_required_column(self) -> None:
        """Verify CSV missing required columns (e.g. price) is rejected."""
        bad_csv = "asset_id,quantity,sector\nNSE:INFY,10,IT"
        with pytest.raises(ValueError, match="missing required column 'price'"):
            load_portfolio_from_csv(bad_csv)

    def test_csv_reject_empty_content(self) -> None:
        """Verify completely empty CSV is rejected."""
        with pytest.raises(ValueError, match="CSV is completely empty"):
            load_portfolio_from_csv("")

    def test_csv_reject_no_data_rows(self) -> None:
        """Verify CSV with only header row is rejected."""
        with pytest.raises(ValueError, match="no valid holding data rows"):
            load_portfolio_from_csv("asset_id,quantity,price,sector\n")

    def test_csv_reject_incomplete_row(self) -> None:
        """Verify truncated rows with too few columns are rejected with row number."""
        bad_csv = "asset_id,quantity,price,sector\nNSE:INFY,10,1500.0"
        with pytest.raises(ValueError, match="Row 2: incomplete row"):
            load_portfolio_from_csv(bad_csv)

    @pytest.mark.parametrize(
        ("qty_str", "err_match"),
        [
            ("abc", "invalid numeric quantity"),
            ("-10", "quantity must be strictly positive"),
            ("0", "quantity must be strictly positive"),
            ("nan", "quantity must be strictly positive and finite"),
            ("inf", "quantity must be strictly positive and finite"),
        ],
    )
    def test_csv_reject_invalid_quantity(self, qty_str: str, err_match: str) -> None:
        """Verify invalid quantities in CSV raise informative errors."""
        bad_csv = f"asset_id,quantity,price,sector\nNSE:INFY,{qty_str},1500.0,IT"
        with pytest.raises(ValueError, match=err_match):
            load_portfolio_from_csv(bad_csv)

    @pytest.mark.parametrize(
        ("px_str", "err_match"),
        [
            ("xyz", "invalid numeric price"),
            ("-50.0", "price must be strictly positive"),
            ("0.0", "price must be strictly positive"),
            ("nan", "price must be strictly positive and finite"),
            ("inf", "price must be strictly positive and finite"),
        ],
    )
    def test_csv_reject_invalid_price(self, px_str: str, err_match: str) -> None:
        """Verify invalid prices in CSV raise informative errors."""
        bad_csv = f"asset_id,quantity,price,sector\nNSE:INFY,10,{px_str},IT"
        with pytest.raises(ValueError, match=err_match):
            load_portfolio_from_csv(bad_csv)

    def test_csv_reject_duplicate_asset_ids(self) -> None:
        """Verify duplicate asset IDs in CSV are rejected with row number."""
        bad_csv = (
            "asset_id,quantity,price,sector\n"
            "NSE:INFY,10,1500.0,IT\n"
            "NSE:infy,20,1500.0,IT\n"
        )
        with pytest.raises(ValueError, match="Row 3: duplicate asset_id 'NSE:infy'"):
            load_portfolio_from_csv(bad_csv)

    def test_csv_reject_empty_asset_id_or_sector(self) -> None:
        """Verify empty asset_id or sector strings are rejected."""
        csv1 = "asset_id,quantity,price,sector\n  ,10,1500.0,IT"
        with pytest.raises(ValueError, match="'asset_id' cannot be empty"):
            load_portfolio_from_csv(csv1)

        csv2 = "asset_id,quantity,price,sector\nNSE:INFY,10,1500.0,   "
        with pytest.raises(ValueError, match="'sector' cannot be empty"):
            load_portfolio_from_csv(csv2)

    def test_json_reject_malformed_syntax(self) -> None:
        """Verify syntax errors in JSON raise ValueError."""
        with pytest.raises(ValueError, match="Malformed JSON"):
            load_portfolio_from_json("{invalid_json: true,}")

    def test_json_reject_missing_required_fields(self) -> None:
        """Verify missing root fields in JSON are rejected."""
        with pytest.raises(ValueError, match="missing required field: 'portfolio_id'"):
            load_portfolio_from_json('{"name": "test", "currency": "INR", "holdings": []}')

    def test_json_reject_empty_holdings_list(self) -> None:
        """Verify JSON with empty holdings list is rejected."""
        payload = '{"portfolio_id": "p1", "name": "test", "currency": "INR", "holdings": []}'
        with pytest.raises(ValueError, match="at least one holding"):
            load_portfolio_from_json(payload)

    def test_json_reject_contradictory_market_value(self) -> None:
        """Verify JSON with contradictory market_value raises ValueError."""
        payload = """
        {
            "portfolio_id": "p1",
            "name": "Test",
            "currency": "INR",
            "holdings": [
                {
                    "asset_id": "NSE:INFY",
                    "quantity": 10.0,
                    "price": 1000.0,
                    "market_value": 99999.0,
                    "sector": "IT"
                }
            ]
        }
        """
        with pytest.raises(ValueError, match="contradictory market_value"):
            load_portfolio_from_json(payload)


# ============================================================================
# 3. Portfolio Allocation & HHI Analytics Tests
# ============================================================================

class TestPortfolioAnalytics:
    """Tests verifying sector allocations and Herfindahl-Hirschman Index math."""

    def test_hand_calculated_equal_weight_hhi(self) -> None:
        """Verify HHI on an equal-weighted 4-asset portfolio (w_i = 0.25).

        Hand calculation:
            w_i = 0.25
            HHI_decimal = 4 * (0.25 ** 2) = 4 * 0.0625 = 0.2500
            HHI_points = 0.25 * 10,000 = 2500.0
        """
        weights = {"A": 0.25, "B": 0.25, "C": 0.25, "D": 0.25}
        dec_hhi, pts_hhi = calculate_hhi(weights)
        assert math.isclose(dec_hhi, 0.25, rel_tol=1e-9)
        assert math.isclose(pts_hhi, 2500.0, rel_tol=1e-9)

    def test_hand_calculated_sample_portfolio_hhi(self) -> None:
        """Verify HHI on the illustrative ₹10 Lakh NSE portfolio using hand calculations.

        Hand calculation for assets:
            Weights:
                HDFCBANK: 0.16 -> 0.16^2 = 0.0256
                ICICIBANK: 0.08 -> 0.08^2 = 0.0064
                SBIN:      0.06 -> 0.06^2 = 0.0036
                INFY:      0.12 -> 0.12^2 = 0.0144
                TCS:       0.08 -> 0.08^2 = 0.0064
                RELIANCE:  0.15 -> 0.15^2 = 0.0225
                ITC:       0.09 -> 0.09^2 = 0.0081
                HINDUNILVR:0.06 -> 0.06^2 = 0.0036
                SUNPHARMA: 0.10 -> 0.10^2 = 0.0100
                LT:        0.10 -> 0.10^2 = 0.0100
            Sum = 0.1106
            Asset HHI Decimal: 0.1106
            Asset HHI Points: 1106.0

        Hand calculation for sectors:
            Banking:     0.30 -> 0.30^2 = 0.0900
            IT:          0.20 -> 0.20^2 = 0.0400
            Energy:      0.15 -> 0.15^2 = 0.0225
            FMCG:        0.15 -> 0.15^2 = 0.0225
            Healthcare:  0.10 -> 0.10^2 = 0.0100
            Industrials: 0.10 -> 0.10^2 = 0.0100
            Sum = 0.1950
            Sector HHI Decimal: 0.1950
            Sector HHI Points: 1950.0
        """
        p = load_portfolio_from_json(JSON_FIXTURE)
        analysis = calculate_portfolio_concentration(p)

        assert isinstance(analysis, ConcentrationAnalysis)
        assert math.isclose(analysis.total_market_value, 1000000.0)

        # Asset HHI
        assert math.isclose(analysis.asset_hhi_decimal, 0.1106, rel_tol=1e-7)
        assert math.isclose(analysis.asset_hhi_points, 1106.0, rel_tol=1e-7)

        # Sector allocations
        assert math.isclose(analysis.sector_weights["Banking"], 0.30)
        assert math.isclose(analysis.sector_weights["Information Technology"], 0.20)
        assert math.isclose(analysis.sector_weights["Energy"], 0.15)
        assert math.isclose(analysis.sector_weights["FMCG"], 0.15)
        assert math.isclose(analysis.sector_weights["Healthcare"], 0.10)
        assert math.isclose(analysis.sector_weights["Industrials"], 0.10)
        assert sum(analysis.sector_weights.values()) == pytest.approx(1.0)

        # Sector HHI
        assert math.isclose(analysis.sector_hhi_decimal, 0.1950, rel_tol=1e-7)
        assert math.isclose(analysis.sector_hhi_points, 1950.0, rel_tol=1e-7)

    def test_decimal_and_points_hhi_scale_agreement(self) -> None:
        """Verify decimal and conventional points scales always satisfy points = dec * 10,000."""
        p = load_portfolio_from_json(JSON_FIXTURE)
        analysis = calculate_portfolio_concentration(p)

        assert math.isclose(analysis.asset_hhi_points, analysis.asset_hhi_decimal * 10000.0)
        assert math.isclose(analysis.sector_hhi_points, analysis.sector_hhi_decimal * 10000.0)

    def test_hhi_reject_empty_or_negative_weights(self) -> None:
        """Verify HHI raises ValueError on empty or invalid weights."""
        with pytest.raises(ValueError, match="empty set of weights"):
            calculate_hhi([])

        with pytest.raises(ValueError, match="cannot be negative"):
            calculate_hhi([0.5, -0.1, 0.6])

        with pytest.raises(ValueError, match="must be finite"):
            calculate_hhi([0.5, float("nan")])


# ============================================================================
# 4. CSV Export Round-Trip Tests
# ============================================================================

class TestExportRoundTrip:
    """Tests verifying portfolio export to CSV and round-trip preservation."""

    def test_export_and_reimport_matches_original(self, tmp_path: Path) -> None:
        """Verify exported CSV can be reloaded without loss of holding information."""
        original = load_portfolio_from_json(JSON_FIXTURE)
        export_file = tmp_path / "exported_portfolio.csv"

        csv_str = export_portfolio_to_csv(original, target=export_file)
        assert export_file.is_file()
        assert "asset_id,quantity,price,sector" in csv_str

        # Re-import from written file
        reloaded = load_portfolio_from_csv(
            export_file,
            portfolio_id=original.portfolio_id,
            name=original.name,
            currency=original.currency,
        )

        assert reloaded.total_value == pytest.approx(original.total_value)
        assert len(reloaded.holdings) == len(original.holdings)

        for h_orig in original.holdings:
            h_reload = reloaded.get_holding(h_orig.asset_id)
            assert h_reload is not None
            assert math.isclose(h_orig.quantity, h_reload.quantity)
            assert math.isclose(h_orig.price, h_reload.price)
            assert h_orig.sector == h_reload.sector
            assert math.isclose(h_orig.market_value, h_reload.market_value)
