"""Tests for FragilityEngine Indian Market Layer and Data Providers."""

import pytest
import numpy as np

from fragility_engine.market_data import (
    NSETradingCalendar,
    calculate_indian_transaction_charges,
    NSEOfflineSampleDataProvider,
    UpstoxDataProvider,
    UpstoxConfigurationError,
)


def test_nse_trading_calendar():
    cal = NSETradingCalendar()

    # 2024-01-26 is Republic Day (Friday) -> Must be holiday (not trading day)
    assert cal.is_trading_day("2024-01-26") is False

    # 2024-01-27 is Saturday -> Not trading day
    assert cal.is_trading_day("2024-01-27") is False

    # 2024-01-28 is Sunday -> Not trading day
    assert cal.is_trading_day("2024-01-28") is False

    # 2024-01-29 is Monday (normal trading day)
    assert cal.is_trading_day("2024-01-29") is True

    # Check date range: Jan 22 to Jan 26, 2024
    # Jan 22 (Special holiday in our list), Jan 23 (T), Jan 24 (T), Jan 25 (T), Jan 26 (Holiday)
    # Expected trading days: Jan 23, 24, 25 (3 days)
    t_days = cal.get_trading_days("2024-01-22", "2024-01-26")
    assert "2024-01-23" in t_days
    assert "2024-01-24" in t_days
    assert "2024-01-25" in t_days
    assert "2024-01-26" not in t_days


def test_calculate_indian_transaction_charges():
    # Trade value = Rs 100,000 equity delivery
    charges = calculate_indian_transaction_charges(100_000.0, trade_type="delivery", brokerage_pct=0.0010)

    assert charges.trade_value_inr == 100_000.0
    assert pytest.approx(charges.brokerage_inr, abs=1e-4) == 100.0  # 0.1% of 100k
    assert pytest.approx(charges.stt_inr, abs=1e-4) == 100.0        # 0.1% STT on delivery
    assert pytest.approx(charges.stamp_duty_inr, abs=1e-4) == 15.0  # 0.015% stamp duty
    assert charges.total_charges_inr > 200.0
    assert charges.total_charges_bps > 20.0  # ~23-25 bps total friction

    d = charges.to_dict()
    assert "gst_inr" in d
    assert "total_charges_bps" in d


def test_nse_offline_sample_data_provider():
    provider = NSEOfflineSampleDataProvider()
    assert provider.is_connected is True
    assert provider.provider_id == "nse_offline_sample_provider"

    instruments = provider.get_instruments()
    assert "NSE:HDFCBANK" in instruments
    assert "NSE:RELIANCE" in instruments

    prices = provider.get_historical_prices("NSE:HDFCBANK")
    assert isinstance(prices, np.ndarray)
    assert len(prices) > 20
    assert np.all(prices > 0.0)


def test_upstox_data_provider_honesty_boundary():
    # Without credentials, it must declare itself unconfigured and raise UpstoxConfigurationError
    provider = UpstoxDataProvider(api_key=None, access_token=None)
    assert provider.is_connected is False
    assert "Blocked/Pending API Credentials" in provider.status_summary

    with pytest.raises(UpstoxConfigurationError) as exc_info:
        provider.get_historical_prices("NSE:INFY")
    assert "missing credentials" in str(exc_info.value)
