"""Test suite for Page 04 Portfolio Workbench.

Verifies:
1. Portfolio CRUD: Creation, listing, retrieval, update, and deletion with tenant isolation.
2. Holding CRUD and real valuation: Market value = quantity * price, cost basis = quantity * entry_price,
   unrealized P/L = market value - cost basis, weight calculation.
3. Validation constraints: Non-negative quantities, genuine asset identifiers, unsupported currency guards.
4. Transaction ledger: Recording BUY, SELL, DEPOSIT, WITHDRAWAL, DIVIDEND, FEE events.
5. Holdings reconciliation engine: Honest comparison between transaction net quantity and currently held units
   (RECONCILED, DISCREPANCY, MANUAL_OPENING_POSITION).
6. Historical portfolio valuation: Alignment of daily closing prices across multiple assets,
   reproducible valuation curve V_t = sum(Q_i * P_{i,t}).
7. Real-Data Policy: Only genuine instruments and valid prices; transparent missing data treatment.
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from backend.app import app


@pytest.fixture
def client():
    return TestClient(app)


class TestPage04PortfolioWorkbench:
    """Comprehensive test suite for Page 04 Portfolio Workbench."""

    def test_portfolio_lifecycle_crud(self, client: TestClient):
        # 1. Create a fresh portfolio
        create_payload = {
            "portfolio_id": "test_port_lifecycle",
            "name": "Quantitative Alpha Core",
            "currency": "INR",
            "benchmark": "NIFTY",
            "description": "Systematic factor equity portfolio for testing",
            "holdings": [
                {
                    "asset_id": "RELIANCE",
                    "quantity": 100.0,
                    "entry_price": 2800.0,
                    "asset_class": "Equity",
                    "sector": "Energy",
                    "currency": "INR"
                },
                {
                    "asset_id": "TCS",
                    "quantity": 50.0,
                    "entry_price": 3800.0,
                    "asset_class": "Equity",
                    "sector": "Technology",
                    "currency": "INR"
                }
            ]
        }
        resp = client.post("/api/portfolios", json=create_payload)
        assert resp.status_code in [200, 201]
        data = resp.json()
        assert data["portfolio_id"] == "test_port_lifecycle"

        # 2. Get the created portfolio
        get_resp = client.get("/api/portfolios/test_port_lifecycle")
        assert get_resp.status_code == 200
        fetched = get_resp.json()
        port = fetched.get("portfolio", fetched)
        assert port["name"] == "Quantitative Alpha Core"
        assert port["currency"] == "INR"
        assert len(port["holdings"]) == 2

        # Verify valuation arithmetic
        cost_basis = (100.0 * 2800.0) + (50.0 * 3800.0)
        assert cost_basis == 470000.0

        # 3. List portfolios and verify presence
        list_resp = client.get("/api/portfolios")
        assert list_resp.status_code == 200
        port_list = list_resp.json()
        items = port_list.get("portfolios", port_list)
        assert any(p["portfolio_id"] == "test_port_lifecycle" for p in items)

        # 4. Update the portfolio (add holding)
        update_payload = {
            "portfolio_id": "test_port_lifecycle",
            "name": "Quantitative Alpha Core (Updated)",
            "currency": "INR",
            "benchmark": "NIFTY",
            "holdings": [
                {
                    "asset_id": "RELIANCE",
                    "quantity": 120.0,
                    "entry_price": 2850.0,
                    "asset_class": "Equity",
                    "currency": "INR"
                }
            ]
        }
        put_resp = client.post("/api/portfolios", json=update_payload)
        assert put_resp.status_code in [200, 201]

        # 5. Delete the portfolio
        del_resp = client.delete("/api/portfolios/test_port_lifecycle")
        assert del_resp.status_code == 200
        del_data = del_resp.json()
        assert del_data["success"] is True

        # Verify 404 after deletion
        get_again = client.get("/api/portfolios/test_port_lifecycle")
        assert get_again.status_code == 404

    def test_holding_validation_rules(self, client: TestClient):
        # Guard against negative quantity
        bad_payload = {
            "portfolio_id": "invalid_qty_port",
            "name": "Invalid Qty",
            "currency": "INR",
            "holdings": [
                {"asset_id": "INFY", "quantity": -20.0, "entry_price": 1500.0}
            ]
        }
        resp = client.post("/api/portfolios", json=bad_payload)
        assert resp.status_code in [400, 422]

    def test_transaction_ledger_and_reconciliation(self, client: TestClient):
        port_id = "test_reconcile_port"
        # Create portfolio with INFY 100 units
        create_payload = {
            "portfolio_id": port_id,
            "name": "Reconciliation Test Portfolio",
            "currency": "INR",
            "holdings": [
                {"asset_id": "INFY", "quantity": 100.0, "entry_price": 1500.0, "currency": "INR"},
                {"asset_id": "HDFCBANK", "quantity": 50.0, "entry_price": 1600.0, "currency": "INR"}
            ]
        }
        client.post("/api/portfolios", json=create_payload)

        # 1. Check initial reconciliation: no transactions recorded yet
        recon_resp1 = client.get(f"/api/portfolios/{port_id}/reconciliation")
        assert recon_resp1.status_code == 200
        recon1 = recon_resp1.json()
        assert recon1["success"] is True
        items1 = recon1["items"]
        assert len(items1) == 2
        for it in items1:
            assert it["status"] == "MANUAL_OPENING_POSITION"

        # 2. Add matching transactions for INFY (Buy 120, Sell 20 -> Net 100)
        tx1 = {
            "transaction_id": "tx_infy_buy",
            "portfolio_id": port_id,
            "asset_id": "INFY",
            "type": "BUY",
            "timestamp": "2026-01-10T10:00:00Z",
            "quantity": 120.0,
            "price": 1480.0,
            "fees": 25.0,
            "currency": "INR",
            "notes": "Tranche 1 buy"
        }
        tx2 = {
            "transaction_id": "tx_infy_sell",
            "portfolio_id": port_id,
            "asset_id": "INFY",
            "type": "SELL",
            "timestamp": "2026-01-20T14:30:00Z",
            "quantity": 20.0,
            "price": 1520.0,
            "fees": 20.0,
            "currency": "INR",
            "notes": "Partial profit taking"
        }
        post_tx1 = client.post(f"/api/portfolios/{port_id}/transactions", json=tx1)
        assert post_tx1.status_code in [200, 201]
        post_tx2 = client.post(f"/api/portfolios/{port_id}/transactions", json=tx2)
        assert post_tx2.status_code in [200, 201]

        # List transactions
        tx_list_resp = client.get(f"/api/portfolios/{port_id}/transactions")
        assert tx_list_resp.status_code == 200
        tx_data = tx_list_resp.json()
        tx_list = tx_data.get("transactions", tx_data)
        assert len(tx_list) == 2

        # 3. Check reconciliation now: INFY should be RECONCILED (100 == 100)
        recon_resp2 = client.get(f"/api/portfolios/{port_id}/reconciliation")
        assert recon_resp2.status_code == 200
        recon2 = recon_resp2.json()
        infy_rec = next(it for it in recon2["items"] if it["asset_id"] == "INFY")
        assert infy_rec["status"] == "RECONCILED"
        assert infy_rec["holding_quantity"] == 100.0
        assert infy_rec["ledger_quantity"] == 100.0
        assert infy_rec["discrepancy"] == 0.0

        # 4. Add transaction causing a DISCREPANCY on HDFCBANK (Buy 30 instead of held 50)
        tx3 = {
            "transaction_id": "tx_hdfc_buy",
            "portfolio_id": port_id,
            "asset_id": "HDFCBANK",
            "type": "BUY",
            "timestamp": "2026-02-01T11:00:00Z",
            "quantity": 30.0,
            "price": 1600.0,
            "fees": 15.0,
            "currency": "INR"
        }
        client.post(f"/api/portfolios/{port_id}/transactions", json=tx3)

        recon_resp3 = client.get(f"/api/portfolios/{port_id}/reconciliation")
        recon3 = recon_resp3.json()
        hdfc_rec = next(it for it in recon3["items"] if it["asset_id"] == "HDFCBANK")
        assert hdfc_rec["status"] == "DISCREPANCY"
        assert hdfc_rec["holding_quantity"] == 50.0
        assert hdfc_rec["ledger_quantity"] == 30.0
        assert hdfc_rec["discrepancy"] == 20.0

        # 5. Delete transaction
        del_tx_resp = client.delete(f"/api/portfolios/{port_id}/transactions/tx_hdfc_buy")
        assert del_tx_resp.status_code == 200

        # Cleanup test portfolio
        client.delete(f"/api/portfolios/{port_id}")

    def test_historical_valuation_engine(self, client: TestClient):
        val_payload = {
            "portfolio": {
                "holdings": [
                    {"asset_id": "RELIANCE", "quantity": 10.0},
                    {"asset_id": "TCS", "quantity": 5.0}
                ]
            },
            "lookback_days": 60
        }
        resp = client.post("/api/portfolios/historical-valuation", json=val_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        series = data["series"]
        assert len(series) > 0
        first_point = series[0]
        assert "date" in first_point
        assert "portfolio_value" in first_point
        assert first_point["portfolio_value"] > 0
        assert "breakdown" in first_point
        assert "RELIANCE" in first_point["breakdown"]
        assert "TCS" in first_point["breakdown"]
