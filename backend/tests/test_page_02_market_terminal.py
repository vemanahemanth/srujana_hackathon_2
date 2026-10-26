"""Test suite for Page 02 Market Terminal & Watchlists endpoints."""

from __future__ import annotations

import json
from typing import Any, Dict
import pytest
from starlette.testclient import TestClient

from backend.app import app


@pytest.fixture
def client():
    return TestClient(app)


class TestMarketTerminalEndpoints:
    """Test suite for Market Terminal instruments, watchlists, quotes, and candles."""

    def test_list_market_instruments(self, client: TestClient):
        resp = client.get("/api/market/instruments")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["count"] >= 50
        instruments = data["instruments"]
        
        # Verify indices exist
        symbols = [i["symbol"] for i in instruments]
        assert "NIFTY" in symbols
        assert "BANKNIFTY" in symbols
        assert "FINNIFTY" in symbols
        assert "NIFTY IT" in symbols

        # Verify equities exist
        assert "RELIANCE" in symbols
        assert "TCS" in symbols
        assert "HDFCBANK" in symbols
        assert "INFY" in symbols

        # Verify fields on instrument
        rel = next(i for i in instruments if i["symbol"] == "RELIANCE")
        assert rel["exchange"] == "NSE"
        assert rel["segment"] == "NSE_EQ"
        assert rel["instrument_key"] == "NSE_EQ|INE002A01018"
        assert rel["sector"] == "Energy"
        assert rel["instrument_type"] == "EQUITY"

    def test_watchlists_lifecycle(self, client: TestClient):
        # 1. List watchlists
        list_resp = client.get("/api/market/watchlists")
        assert list_resp.status_code == 200
        wls = list_resp.json()["watchlists"]
        assert len(wls) >= 1

        # 2. Create new watchlist
        create_payload = {
            "name": "Test Energy & FMCG Watchlist",
            "description": "Sector specific surveillance",
            "symbols": ["RELIANCE", "ITC", "HINDUNILVR"],
        }
        create_resp = client.post("/api/market/watchlists", json=create_payload)
        assert create_resp.status_code == 200
        created_data = create_resp.json()
        wl_id = created_data["watchlist_id"]
        assert wl_id.startswith("wl_")

        # 3. Update watchlist (add symbol)
        update_payload = {
            "id": wl_id,
            "name": "Updated Energy & FMCG",
            "description": "Updated description",
            "symbols": ["RELIANCE", "ITC", "HINDUNILVR", "ONGC"],
        }
        update_resp = client.post("/api/market/watchlists", json=update_payload)
        assert update_resp.status_code == 200
        updated_wls = update_resp.json()["watchlists"]
        target = next(w for w in updated_wls if w["id"] == wl_id)
        assert target["name"] == "Updated Energy & FMCG"
        assert "ONGC" in target["symbols"]

        # 4. Delete watchlist
        del_resp = client.delete(f"/api/market/watchlists/{wl_id}")
        assert del_resp.status_code == 200
        remaining_ids = [w["id"] for w in del_resp.json()["watchlists"]]
        assert wl_id not in remaining_ids

    def test_candles_endpoint_real_format(self, client: TestClient):
        resp = client.get("/api/upstox/candles?symbol=RELIANCE")
        # In configured environment with token, it returns 200 with candles
        # In unconfigured environment without token, it returns 400 or 401
        assert resp.status_code in (200, 400, 401)
        if resp.status_code == 200:
            data = resp.json()
            assert data["success"] is True
            assert "candles" in data
            if data["count"] > 0:
                c = data["candles"][0]
                assert "open" in c
                assert "high" in c
                assert "low" in c
                assert "close" in c
                assert "volume" in c
                assert "timestamp" in c

    def test_quote_endpoint_real_format(self, client: TestClient):
        resp = client.get("/api/upstox/quote?symbols=NIFTY,RELIANCE")
        assert resp.status_code in (200, 400, 401)
        if resp.status_code == 200:
            data = resp.json()
            assert data["success"] is True
            assert "quotes" in data
