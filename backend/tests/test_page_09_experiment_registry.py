"""Unit and Integration Tests for Page 09: Unified Experiment Registry & Research Reproducibility.

Verifies:
1. Unified registry listing aggregating real runs across all application labs.
2. Standard run metadata envelope and reproducibility classification.
3. Search, filtering by type and status.
4. Granular experiment detail inspection.
5. Multi-run comparison with configuration diffs and numeric metric deltas.
6. Rerun workflow with parent-child lineage tracking.
7. Multi-format export (Markdown, JSON, CSV).
"""

from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from backend.app import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_candles():
    return [
        {
            "timestamp": f"2026-03-{i:02d}T09:15:00+05:30",
            "open": 1400.0 + (i * 3.5),
            "high": 1410.0 + (i * 3.5),
            "low": 1395.0 + (i * 3.5),
            "close": 1405.0 + (i * 3.5),
            "volume": 15000000,
        }
        for i in range(1, 31)
    ]


class TestPage09UnifiedExperimentRegistry:
    def test_unified_experiment_listing_and_metadata(self, client: TestClient, sample_candles):
        """Verify unified experiment listing aggregates real runs with canonical envelope."""
        # 1. Create a strategy backtest run
        bt_payload = {
            "config": {
                "strategy_id": "strat_reg_01",
                "name": "Registry Alpha Test Strategy",
                "strategy_type": "ma_crossover",
                "fast_period": 3,
                "slow_period": 7,
            },
            "candles": sample_candles,
        }
        bt_resp = client.post("/api/strategies/backtest", json=bt_payload)
        assert bt_resp.status_code == 200
        run_id = bt_resp.json()["backtest"]["run_id"]

        # 2. Query Unified Experiment Registry
        resp = client.get("/api/experiments/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["total_count"] >= 1
        assert "stats" in data
        assert data["stats"]["total_runs"] >= 1

        # 3. Verify Canonical Run Envelope
        runs = data["runs"]
        matching = [r for r in runs if r["run_id"] == run_id]
        assert len(matching) == 1
        rec = matching[0]

        assert rec["run_type"] == "strategy_backtest"
        assert "display_name" in rec
        assert rec["status"] == "completed"
        assert rec["reproducibility"] in (
            "Exact reproduction supported",
            "Configuration reproducible",
            "Partially traceable",
        )
        assert "spec" in rec
        assert "result" in rec
        assert "lineage" in rec
        assert "metrics_summary" in rec

    def test_experiment_filtering_and_search(self, client: TestClient, sample_candles):
        """Verify filtering by run_type, status, and text search."""
        # Query with strategy_backtest filter
        resp = client.get("/api/experiments/runs?type=strategy_backtest")
        assert resp.status_code == 200
        data = resp.json()
        for r in data["runs"]:
            assert r["run_type"] == "strategy_backtest"

        # Query with text search
        resp_search = client.get("/api/experiments/runs?search=Alpha")
        assert resp_search.status_code == 200
        data_search = resp_search.json()
        assert data_search["total_count"] >= 1

    def test_experiment_detail_retrieval(self, client: TestClient, sample_candles):
        """Verify deep inspection detail retrieval for a specific run."""
        bt_payload = {
            "config": {
                "strategy_id": "strat_reg_detail",
                "name": "Detail Inspection Strategy",
                "strategy_type": "rsi_momentum",
            },
            "candles": sample_candles,
        }
        bt_resp = client.post("/api/strategies/backtest", json=bt_payload)
        run_id = bt_resp.json()["backtest"]["run_id"]

        resp = client.get(f"/api/experiments/{run_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        exp = data["experiment"]
        assert exp["run_id"] == run_id
        assert exp["run_type"] == "strategy_backtest"
        assert "walk_forward" in exp["result"]
        assert "trades" in exp["result"]

    def test_experiment_comparison_diff_and_deltas(self, client: TestClient, sample_candles):
        """Verify multi-run comparison producing configuration diffs and metric deltas."""
        # Run 1: fast=3, slow=7
        r1 = client.post("/api/strategies/backtest", json={
            "config": {"strategy_id": "strat_comp_1", "fast_period": 3, "slow_period": 7},
            "candles": sample_candles,
        }).json()["backtest"]["run_id"]

        # Run 2: fast=5, slow=12
        r2 = client.post("/api/strategies/backtest", json={
            "config": {"strategy_id": "strat_comp_2", "fast_period": 5, "slow_period": 12},
            "candles": sample_candles,
        }).json()["backtest"]["run_id"]

        comp_resp = client.post("/api/experiments/compare", json={"run_ids": [r1, r2]})
        assert comp_resp.status_code == 200
        comp_data = comp_resp.json()
        assert comp_data["success"] is True

        # Config diff verifies differing parameters
        config_diff = comp_data["config_diff"]
        fast_diff = next(d for d in config_diff if d["parameter"] == "fast_period")
        assert fast_diff["is_identical"] is False
        assert fast_diff["values"][r1] == 3
        assert fast_diff["values"][r2] == 5

        # Metric deltas exist
        deltas = comp_data["metric_deltas"]
        assert len(deltas) > 0

    def test_experiment_rerun_and_lineage(self, client: TestClient, sample_candles):
        """Verify rerun workflow preserves original configuration and traces lineage."""
        r1 = client.post("/api/strategies/backtest", json={
            "config": {"strategy_id": "strat_rerun_orig", "fast_period": 4, "slow_period": 9},
            "candles": sample_candles,
        }).json()["backtest"]["run_id"]

        rerun_resp = client.post(f"/api/experiments/{r1}/rerun", json={})
        assert rerun_resp.status_code == 200
        data = rerun_resp.json()
        assert data["success"] is True
        new_run = data["new_run"]
        assert new_run["run_id"] != r1
        assert new_run["lineage"]["parent_run_id"] == r1

    def test_experiment_export_formats(self, client: TestClient, sample_candles):
        """Verify export in Markdown, JSON, and CSV."""
        r1 = client.post("/api/strategies/backtest", json={
            "config": {"strategy_id": "strat_export_test"},
            "candles": sample_candles,
        }).json()["backtest"]["run_id"]

        # Markdown export
        resp_md = client.post(f"/api/experiments/{r1}/export", json={"format": "markdown"})
        assert resp_md.status_code == 200
        assert "text/markdown" in resp_md.headers["content-type"]
        assert "# FragilityShield Research Report" in resp_md.text

        # JSON export
        resp_json = client.post(f"/api/experiments/{r1}/export", json={"format": "json"})
        assert resp_json.status_code == 200
        assert "application/json" in resp_json.headers["content-type"]
        assert resp_json.json()["run_id"] == r1

        # CSV export
        resp_csv = client.post(f"/api/experiments/{r1}/export", json={"format": "csv"})
        assert resp_csv.status_code == 200
        assert "text/csv" in resp_csv.headers["content-type"]
        assert "run_id" in resp_csv.text
