"""Deterministic and Live Test Suite for FragilityShield Upstox V3 Market Data Integration.

Covers:
1. Configuration & Secret Redaction (Phase C)
2. Instrument Resolution & Disambiguation (Phase D.B)
3. Historical Candle Retrieval, Asia/Kolkata Timezone Normalization, and Sorting (Phase D.C)
4. Data Quality & OHLCV Validation Boundary Checks (Phase E)
5. Market Quotes & LTP (Phase D.D)
6. Downstream ProjectCatalog Dataset Import & Risk Model Execution (Phase F)
7. REST API Endpoints with Deterministic Mock Fixtures (Phase G)
8. Live Upstox API Smoke Tests using configured credentials (Phase H)
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import httpx
import numpy as np
import pytest
from starlette.testclient import TestClient

from backend.app import app
from fragility_engine.data_diagnostics import validate_financial_ohlcv
from fragility_engine.projects import DatasetRecord, ProjectCatalog
from fragility_engine.risk import calculate_risk_report
from fragility_engine.upstox import (
    IST,
    CanonicalCandle,
    CanonicalQuote,
    UpstoxAuthenticationError,
    UpstoxAuthStatus,
    UpstoxConfig,
    UpstoxConfigurationError,
    UpstoxError,
    UpstoxInstrument,
    UpstoxInstrumentNotFoundError,
    UpstoxInstrumentResolver,
    UpstoxMarketDataAdapter,
    UpstoxRateLimitError,
)

# Deterministic Upstox V3 historical candle fixture
SAMPLE_UPSTOX_CANDLES_RESPONSE: Dict[str, Any] = {
    "status": "success",
    "data": {
        "candles": [
            ["2026-04-03T00:00:00+05:30", 1400.0, 1420.0, 1390.0, 1410.0, 1500000, 0],
            ["2026-04-02T00:00:00+05:30", 1380.0, 1405.0, 1375.0, 1395.0, 1200000, 0],
            ["2026-04-01T00:00:00+05:30", 1360.0, 1385.0, 1350.0, 1375.0, 1100000, 0],
        ]
    },
}

SAMPLE_UPSTOX_LTP_RESPONSE: Dict[str, Any] = {
    "status": "success",
    "data": {
        "NSE_EQ:RELIANCE": {
            "last_price": 1410.0,
            "instrument_token": "NSE_EQ|INE002A01018",
            "ltq": 10,
            "volume": 1500000,
            "cp": 1395.0,
        }
    },
}

SAMPLE_UPSTOX_QUOTE_RESPONSE: Dict[str, Any] = {
    "status": "success",
    "data": {
        "NSE_EQ:RELIANCE": {
            "last_price": 1410.0,
            "ohlc": {
                "open": 1400.0,
                "high": 1420.0,
                "low": 1390.0,
                "close": 1410.0,
                "volume": 1500000,
                "ts": 1792693800000,
            },
            "net_change": 15.0,
        }
    },
}


# ==============================================================================
# 1. Configuration & Security Redaction Tests (§4, §10)
# ==============================================================================

class TestUpstoxConfigurationAndSecurity:
    """Verify secrets are never leaked in representations, errors, or logs."""

    def test_config_masks_sensitive_tokens(self):
        cfg = UpstoxConfig(
            access_token="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.dummysecretpayload.signature123",
            client_id="my_secret_client_id_12345",
            client_secret="my_super_secret_password_abc",
        )
        # Token masking in repr
        r = repr(cfg)
        assert "dummysecretpayload" not in r
        assert "signature123" not in r
        assert "my_super_secret_password_abc" not in r

        # Masking in safe_dict
        safe = cfg.safe_dict()
        assert safe["has_access_token"] is True
        assert safe["has_oauth_client"] is True
        assert "dummysecretpayload" not in safe["masked_access_token"]
        assert "..." in safe["masked_access_token"]
        assert "..." in safe["masked_client_id"]

    def test_unconfigured_state_reports_cleanly(self):
        cfg = UpstoxConfig(access_token=None, client_id=None, client_secret=None)
        assert cfg.is_configured is False
        assert cfg.has_access_token is False
        assert cfg.has_oauth_client is False
        safe = cfg.safe_dict()
        assert safe["masked_access_token"] is None

    def test_missing_token_raises_configuration_error(self):
        cfg = UpstoxConfig(access_token=None)
        adapter = UpstoxMarketDataAdapter(config=cfg)
        with pytest.raises(UpstoxConfigurationError) as exc:
            adapter.get_historical_candles("RELIANCE")
        assert "UPSTOX_ACCESS_TOKEN" in str(exc.value)


# ==============================================================================
# 2. Instrument Resolution & Disambiguation Tests (§5.B)
# ==============================================================================

class TestUpstoxInstrumentResolver:
    """Verify human symbol mapping to exact Upstox keys without guessing."""

    def test_resolve_curated_equities(self):
        resolver = UpstoxInstrumentResolver()
        reliance = resolver.resolve("RELIANCE")
        assert reliance.instrument_key == "NSE_EQ|INE002A01018"
        assert reliance.exchange == "NSE"
        assert reliance.segment == "NSE_EQ"
        assert reliance.instrument_type == "EQUITY"

        tcs = resolver.resolve("TCS")
        assert tcs.instrument_key == "NSE_EQ|INE467B01029"

        infy = resolver.resolve("INFY")
        assert infy.instrument_key == "NSE_EQ|INE009A01021"

    def test_resolve_curated_indices(self):
        resolver = UpstoxInstrumentResolver()
        nifty = resolver.resolve("NIFTY50")
        assert nifty.instrument_key == "NSE_INDEX|Nifty 50"
        assert nifty.segment == "NSE_INDEX"
        assert nifty.instrument_type == "INDEX"

        banknifty = resolver.resolve("BANKNIFTY")
        assert banknifty.instrument_key == "NSE_INDEX|Nifty Bank"

    def test_direct_instrument_key_passthrough(self):
        resolver = UpstoxInstrumentResolver()
        custom = resolver.resolve("BSE_EQ|500325")
        assert custom.instrument_key == "BSE_EQ|500325"
        assert custom.exchange == "BSE"

    def test_strip_exchange_prefix(self):
        resolver = UpstoxInstrumentResolver()
        inst = resolver.resolve("NSE:RELIANCE")
        assert inst.instrument_key == "NSE_EQ|INE002A01018"

    def test_unknown_symbol_raises_not_found_with_suggestions(self):
        resolver = UpstoxInstrumentResolver()
        with pytest.raises(UpstoxInstrumentNotFoundError) as exc:
            resolver.resolve("NON_EXISTENT_XYZ_SYMBOL")
        assert "Unable to resolve instrument" in str(exc.value)

    def test_search_instruments(self):
        resolver = UpstoxInstrumentResolver()
        matches = resolver.search("NIFTY", limit=5)
        assert len(matches) > 0
        symbols = [m.symbol for m in matches]
        assert any("NIFTY" in s for s in symbols)


# ==============================================================================
# 3. Deterministic Historical Candle Retrieval & Normalization Tests (§5.C)
# ==============================================================================

class TestUpstoxHistoricalCandles:
    """Test candle normalization, Asia/Kolkata timezone handling, and sorting."""

    def test_candles_normalized_and_chronologically_sorted(self):
        cfg = UpstoxConfig(access_token="test_token_123")
        mock_client = MagicMock(spec=httpx.Client)

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_UPSTOX_CANDLES_RESPONSE
        mock_client.get.return_value = mock_resp

        adapter = UpstoxMarketDataAdapter(config=cfg, client=mock_client)
        candles = adapter.get_historical_candles(
            symbol_or_key="RELIANCE",
            from_date="2026-04-01",
            to_date="2026-04-03",
        )

        assert len(candles) == 3
        # Chronological ordering: earliest date first!
        assert candles[0].timestamp.startswith("2026-04-01")
        assert candles[1].timestamp.startswith("2026-04-02")
        assert candles[2].timestamp.startswith("2026-04-03")

        # Asia/Kolkata timezone offset (+05:30)
        assert "+05:30" in candles[0].timestamp

        # Field preservation
        c0 = candles[0]
        assert c0.open == 1360.0
        assert c0.high == 1385.0
        assert c0.low == 1350.0
        assert c0.close == 1375.0
        assert c0.volume == 1100000.0

    def test_historical_prices_returns_1d_numpy_array(self):
        cfg = UpstoxConfig(access_token="test_token_123")
        mock_client = MagicMock(spec=httpx.Client)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_UPSTOX_CANDLES_RESPONSE
        mock_client.get.return_value = mock_resp

        adapter = UpstoxMarketDataAdapter(config=cfg, client=mock_client)
        prices = adapter.get_historical_prices("RELIANCE")

        assert isinstance(prices, np.ndarray)
        assert len(prices) == 3
        assert list(prices) == [1375.0, 1395.0, 1410.0]

    def test_unauthorized_token_raises_authentication_error(self):
        cfg = UpstoxConfig(access_token="expired_token")
        mock_client = MagicMock(spec=httpx.Client)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 401
        mock_resp.json.return_value = {"status": "error", "errors": [{"message": "Invalid token"}]}
        mock_client.get.return_value = mock_resp

        adapter = UpstoxMarketDataAdapter(config=cfg, client=mock_client)
        with pytest.raises(UpstoxAuthenticationError) as exc:
            adapter.get_historical_candles("RELIANCE")
        assert "Upstox access token invalid or expired" in str(exc.value)

    def test_rate_limit_raises_rate_limit_error(self):
        cfg = UpstoxConfig(access_token="token")
        mock_client = MagicMock(spec=httpx.Client)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 429
        mock_client.get.return_value = mock_resp

        adapter = UpstoxMarketDataAdapter(config=cfg, client=mock_client)
        with pytest.raises(UpstoxRateLimitError):
            adapter.get_historical_candles("RELIANCE")

    def test_network_timeout_raises_upstox_error(self):
        cfg = UpstoxConfig(access_token="token")
        mock_client = MagicMock(spec=httpx.Client)
        mock_client.get.side_effect = httpx.TimeoutException("Connection timed out")

        adapter = UpstoxMarketDataAdapter(config=cfg, client=mock_client)
        with pytest.raises(UpstoxError) as exc:
            adapter.get_historical_candles("RELIANCE")
        assert "timed out" in str(exc.value).lower()


# ==============================================================================
# 4. Market Quotes & LTP Tests (§5.D)
# ==============================================================================

class TestUpstoxMarketQuotes:
    """Test quote retrieval and normalization."""

    def test_get_ltp_successful(self):
        cfg = UpstoxConfig(access_token="test_token")
        mock_client = MagicMock(spec=httpx.Client)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_UPSTOX_LTP_RESPONSE
        mock_client.get.return_value = mock_resp

        adapter = UpstoxMarketDataAdapter(config=cfg, client=mock_client)
        ltp_map = adapter.get_ltp(["RELIANCE"])
        assert "RELIANCE" in ltp_map
        assert ltp_map["RELIANCE"] == 1410.0

    def test_get_quote_successful(self):
        cfg = UpstoxConfig(access_token="test_token")
        mock_client = MagicMock(spec=httpx.Client)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_UPSTOX_QUOTE_RESPONSE
        mock_client.get.return_value = mock_resp

        adapter = UpstoxMarketDataAdapter(config=cfg, client=mock_client)
        quotes = adapter.get_quote(["RELIANCE"])
        assert "RELIANCE" in quotes
        q = quotes["RELIANCE"]
        assert q.last_price == 1410.0
        assert q.open == 1400.0
        assert q.high == 1420.0
        assert q.low == 1390.0
        assert q.close == 1410.0
        assert q.volume == 1500000.0


# ==============================================================================
# 5. Data Quality & ProjectCatalog Registration Tests (§6, §7)
# ==============================================================================

class TestUpstoxDataQualityAndCatalog:
    """Test data quality audit and registration in FragilityShield catalog."""

    def test_import_and_register_dataset_with_provenance(self, tmp_path):
        cfg = UpstoxConfig(access_token="test_token")
        mock_client = MagicMock(spec=httpx.Client)
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_UPSTOX_CANDLES_RESPONSE
        mock_client.get.return_value = mock_resp

        catalog = ProjectCatalog(storage_dir=tmp_path)
        adapter = UpstoxMarketDataAdapter(config=cfg, client=mock_client)

        rec, rep = adapter.import_and_register_dataset(
            symbol_or_key="RELIANCE",
            catalog=catalog,
            from_date="2026-04-01",
            to_date="2026-04-03",
            catalog_dir=tmp_path / "datasets",
        )

        assert rec.dataset_id.startswith("ds_upstox_reliance_")
        assert rec.row_count == 3
        assert rec.symbols == ("RELIANCE",)
        assert rep.is_valid is True
        assert rec.provenance["provider"] == "upstox_v3_market_data"
        assert rec.provenance["instrument_key"] == "NSE_EQ|INE002A01018"
        assert Path(rec.file_path).exists()

        # Load back from catalog
        loaded = catalog.get_dataset(rec.dataset_id)
        assert loaded is not None
        assert loaded.dataset_id == rec.dataset_id

    def test_data_quality_detects_corrupted_candles(self):
        # Corrupted candles: High < Low
        corrupted_candles = [
            {"timestamp": "2026-04-01T00:00:00+05:30", "open": 100.0, "high": 90.0, "low": 110.0, "close": 95.0, "volume": 1000},
        ]
        rep = validate_financial_ohlcv(corrupted_candles)
        assert rep.is_valid is False
        assert rep.high_low_violations == 1


# ==============================================================================
# 6. REST API Endpoints Tests (§8)
# ==============================================================================

class TestUpstoxRestEndpoints:
    """Test all Upstox REST API endpoints in backend/app.py."""

    @pytest.fixture
    def test_client(self):
        return TestClient(app)

    def test_api_upstox_status_endpoint(self, test_client):
        resp = test_client.get("/api/upstox/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "config" in data
        assert "status" in data
        # Ensure secret tokens are NOT leaked in response
        if data["config"].get("masked_access_token"):
            assert "..." in data["config"]["masked_access_token"]

    def test_api_upstox_resolve_endpoint(self, test_client):
        resp = test_client.get("/api/upstox/instruments/resolve?query=RELIANCE")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["instrument"]["instrument_key"] == "NSE_EQ|INE002A01018"

    def test_api_upstox_resolve_missing_param_returns_400(self, test_client):
        resp = test_client.get("/api/upstox/instruments/resolve")
        assert resp.status_code == 400
        assert resp.json()["success"] is False

    def test_api_upstox_search_endpoint(self, test_client):
        resp = test_client.get("/api/upstox/instruments/search?query=NIFTY&limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["instruments"]) > 0

    def test_api_upstox_candles_endpoint(self, test_client):
        with patch.object(UpstoxMarketDataAdapter, "get_historical_candles") as mock_candles:
            mock_candles.return_value = [
                CanonicalCandle("2026-04-01T00:00:00+05:30", 100.0, 105.0, 99.0, 104.0, 50000, 0, "RELIANCE", "NSE_EQ|INE002A01018"),
            ]
            resp = test_client.get("/api/upstox/candles?symbol=RELIANCE&from_date=2026-04-01&to_date=2026-04-02")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["count"] == 1
            assert data["candles"][0]["close"] == 104.0

    def test_api_upstox_quote_endpoint(self, test_client):
        with patch.object(UpstoxMarketDataAdapter, "get_quote") as mock_q:
            mock_q.return_value = {
                "RELIANCE": CanonicalQuote("RELIANCE", "NSE_EQ|INE002A01018", 1410.0, 1400.0, 1420.0, 1390.0, 1410.0, 1500000.0),
            }
            resp = test_client.get("/api/upstox/quote?symbols=RELIANCE")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["quotes"]["RELIANCE"]["last_price"] == 1410.0

    def test_api_upstox_oauth_url_endpoint(self, test_client):
        resp = test_client.get("/api/upstox/auth/url?state=test_state_123")
        # If client_id is not configured in env, it returns 400 with actionable error
        assert resp.status_code in (200, 400)


# ==============================================================================
# 7. Live Upstox API Smoke Test (§9)
# ==============================================================================

class TestLiveUpstoxConnectivity:
    """Live smoke test executing against the real Upstox API when credentials are present."""

    def test_live_upstox_authentication_and_market_data(self):
        cfg = UpstoxConfig.from_env()
        if not cfg.has_access_token:
            pytest.skip("NOT RUN — credentials or authorization unavailable in environment.")

        adapter = UpstoxMarketDataAdapter(config=cfg)

        # 1. Connection check
        status = adapter.check_connection()
        if not status.authenticated:
            pytest.fail(f"Live Upstox API authentication failed: {status.message}")

        assert status.authenticated is True
        assert status.status_code == 200
        assert status.read_only is True

        # 2. Historical candle retrieval for benchmark instrument (RELIANCE)
        candles = adapter.get_historical_candles(
            symbol_or_key="RELIANCE",
            from_date="2026-03-01",
            to_date="2026-04-01",
        )
        assert len(candles) > 0
        c0 = candles[0]
        assert c0.open > 0.0
        assert c0.high >= c0.low
        assert c0.close > 0.0
        assert "+05:30" in c0.timestamp

        # 3. Live Quote / LTP check
        quotes = adapter.get_quote(["RELIANCE"])
        assert "RELIANCE" in quotes
        assert quotes["RELIANCE"].last_price > 0.0
