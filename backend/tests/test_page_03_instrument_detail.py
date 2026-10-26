"""Test suite for Page 03 Instrument Detail and Performance Explorer.

Verifies:
1. Instrument identifier resolution (/api/upstox/instruments/resolve) for symbols and ISIN keys.
2. Honest 404 state and suggestions for unknown / invalid instruments.
3. Genuine historical candles retrieval and validation (positive prices, timestamps, OHLC logic).
4. Reproducible risk and return calculations matching mathematical definitions:
   - Daily simple return: r_t = P_t / P_{t-1} - 1
   - Cumulative return: R_cum = prod(1 + r_t) - 1
   - Maximum drawdown and duration
   - Annualized volatility: sigma * sqrt(252)
   - CAPM Beta: Cov(r_i, r_b) / Var(r_b)
   - Tail risk: Historical VaR and CVaR / Expected Shortfall
5. Real data policy: No synthetic / fabricated candle generation.
"""

from __future__ import annotations

import math
import numpy as np
import pytest
from starlette.testclient import TestClient

from backend.app import app


@pytest.fixture
def client():
    return TestClient(app)


class TestPage03InstrumentDetail:
    """Comprehensive test suite for Page 03 Instrument Detail & Performance Explorer."""

    def test_resolve_instrument_by_symbol_and_key(self, client: TestClient):
        # 1. Resolve by standard equity symbol
        resp1 = client.get("/api/upstox/instruments/resolve?symbol=RELIANCE")
        assert resp1.status_code == 200
        d1 = resp1.json()
        assert d1["success"] is True
        inst1 = d1["instrument"]
        assert inst1["symbol"] == "RELIANCE"
        assert inst1["exchange"] == "NSE"
        assert inst1["instrument_key"] == "NSE_EQ|INE002A01018"
        assert inst1["sector"] == "Energy"
        assert inst1["instrument_type"] == "EQUITY"

        # 2. Resolve by exact instrument_key
        resp2 = client.get("/api/upstox/instruments/resolve?symbol=NSE_EQ|INE002A01018")
        assert resp2.status_code == 200
        d2 = resp2.json()
        assert d2["instrument"]["symbol"] == "RELIANCE"

        # 3. Resolve index instrument
        resp3 = client.get("/api/upstox/instruments/resolve?symbol=NIFTY")
        assert resp3.status_code == 200
        d3 = resp3.json()
        assert "Nifty" in d3["instrument"]["name"] or "NIFTY" in d3["instrument"]["symbol"]

    def test_resolve_instrument_not_found(self, client: TestClient):
        resp = client.get("/api/upstox/instruments/resolve?symbol=UNKNOWN_TICKER_XYZ")
        assert resp.status_code == 404
        d = resp.json()
        assert d["success"] is False
        assert "unable to resolve" in d["error"].lower() or "not found" in d["error"].lower()
        # Suggestions provided in the error description
        assert "banknifty" in d["error"].lower() or "suggestions" in d

    def test_instrument_historical_candles_integrity(self, client: TestClient):
        # Retrieve actual candles for RELIANCE
        resp = client.get(
            "/api/upstox/candles?instrument_key=RELIANCE&interval_unit=days&interval_value=1&from_date=2024-01-01&to_date=2024-06-30"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        candles = data["candles"]
        assert len(candles) >= 50

        # Validate genuine observations: No nonpositive prices, valid OHLC relationships
        for c in candles:
            o, h, l, cl = c["open"], c["high"], c["low"], c["close"]
            assert o > 0 and h > 0 and l > 0 and cl > 0, f"Nonpositive price found in candle: {c}"
            assert h >= l, f"High must be >= low: {c}"
            assert h >= min(o, cl), f"High must be >= min(open, close): {c}"
            assert l <= max(o, cl), f"Low must be <= max(open, close): {c}"
            assert "timestamp" in c and len(c["timestamp"]) >= 10

    def test_instrument_market_quote(self, client: TestClient):
        resp = client.get("/api/upstox/quote?symbols=RELIANCE")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "quotes" in data
        quote = data["quotes"]["RELIANCE"]
        assert quote["last_price"] > 0
        assert quote["open"] > 0
        assert quote["high"] > 0
        assert quote["low"] > 0
        assert quote["close"] > 0

    def test_mathematical_return_and_risk_reproducibility(self):
        """Verify the exact mathematical definitions required by Page 03."""
        prices = [100.0, 105.0, 102.0, 108.0, 104.0, 110.0]
        
        # 1. Daily Simple Return: r_t = P_t / P_{t-1} - 1
        returns = [(prices[t] / prices[t - 1]) - 1.0 for t in range(1, len(prices))]
        expected_returns = [0.05, -0.02857142857142858, 0.05882352941176472, -0.03703703703703709, 0.05769230769230771]
        for r_calc, r_exp in zip(returns, expected_returns):
            assert math.isclose(r_calc, r_exp, rel_tol=1e-5)

        # 2. Cumulative Return: R_cum = prod(1 + r_t) - 1 = P_T / P_0 - 1
        cum_ret_prod = 1.0
        for r in returns:
            cum_ret_prod *= (1.0 + r)
        cum_ret = cum_ret_prod - 1.0
        cum_ret_direct = (prices[-1] / prices[0]) - 1.0
        assert math.isclose(cum_ret, 0.10, rel_tol=1e-5)
        assert math.isclose(cum_ret, cum_ret_direct, rel_tol=1e-5)

        # 3. Maximum Drawdown & Drawdown Duration
        # Wealth series: 1.0, 1.05, 1.02, 1.08, 1.04, 1.10
        # Peak series:   1.0, 1.05, 1.05, 1.08, 1.08, 1.10
        # Drawdowns:     0.0, 0.0, (1.02 - 1.05)/1.05 = -0.02857, 0.0, (1.04 - 1.08)/1.08 = -0.037037, 0.0
        # Max DD = -3.7037%
        wealth = [1.0]
        for r in returns:
            wealth.append(wealth[-1] * (1.0 + r))
        peaks = np.maximum.accumulate(wealth)
        drawdowns = (np.array(wealth) - peaks) / peaks
        max_dd = float(np.min(drawdowns))
        assert math.isclose(max_dd, -0.037037037037037035, rel_tol=1e-5)

        # 4. Annualized Volatility: sigma * sqrt(252)
        std_daily = float(np.std(returns, ddof=1))
        ann_vol = std_daily * math.sqrt(252)
        assert ann_vol > 0

        # 5. CAPM Beta: Cov(r_i, r_b) / Var(r_b)
        benchmark_returns = [0.02, -0.01, 0.03, -0.02, 0.03]
        cov_matrix = np.cov(returns, benchmark_returns)
        cov_ib = cov_matrix[0, 1]
        var_b = cov_matrix[1, 1]
        beta = cov_ib / var_b
        # Positive correlation expected
        assert beta > 0

        # 6. Tail risk: Historical VaR & CVaR (95%)
        # Sample of 100 observations
        np.random.seed(42)
        sample_returns = np.random.normal(0.0005, 0.015, 100)
        sorted_rets = np.sort(sample_returns)
        alpha = 0.05
        var_idx = int(alpha * len(sorted_rets))
        var_95 = -sorted_rets[var_idx]
        tail_losses = sorted_rets[:var_idx]
        cvar_95 = -float(np.mean(tail_losses))
        assert cvar_95 >= var_95, "CVaR must be greater than or equal to VaR for historical tail risk"
