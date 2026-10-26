"""Automated Test Suite for Page 10: Data Quality & Provenance Observatory.

Validates:
- Authoritative dataset inventory listing.
- 9-point explainable data quality scorecard rules:
  1. Non-positive price violations
  2. OHLC physical bounds & High < Low violations
  3. Duplicate timestamps
  4. Chronological ordering & monotonicity
  5. Negative volume integrity
  6. Stale / frozen prices detection
  7. Statistical return outliers & discontinuities (Z >= 3.5)
  8. NSE Trading Calendar expected vs observed gaps
  9. Benchmark synchronous alignment
- SHA-256 deterministic dataset fingerprinting.
- Calendar-aware coverage analysis (NSE Equities).
- Data-treatment policy impact analysis (Raw vs Treated risk metrics).
- Non-destructive Anomaly Disposition ledger.
- Real API endpoints via Starlette TestClient.
"""

import json
import pytest
from starlette.testclient import TestClient

from app import create_application
from fragility_engine.data_observatory import (
    compute_dataset_fingerprint,
    audit_dataset_quality,
    compute_coverage_analysis,
    analyze_data_quality_impact,
    list_available_datasets,
    record_anomaly_disposition,
    get_anomaly_dispositions,
    QualityRuleViolation,
)


@pytest.fixture
def client():
    app = create_application()
    return TestClient(app)


@pytest.fixture
def clean_candle_series():
    """Deterministic clean daily candles for testing."""
    return [
        {"date": "2026-10-01", "open": 100.0, "high": 105.0, "low": 99.0, "close": 104.0, "volume": 150000},
        {"date": "2026-10-05", "open": 104.0, "high": 106.0, "low": 103.0, "close": 105.5, "volume": 120000},
        {"date": "2026-10-06", "open": 105.5, "high": 108.0, "low": 104.5, "close": 107.0, "volume": 180000},
        {"date": "2026-10-07", "open": 107.0, "high": 107.5, "low": 102.0, "close": 103.0, "volume": 220000},
        {"date": "2026-10-08", "open": 103.0, "high": 105.0, "low": 101.5, "close": 104.2, "volume": 140000},
        {"date": "2026-10-09", "open": 104.2, "high": 106.5, "low": 103.8, "close": 106.0, "volume": 160000},
        {"date": "2026-10-12", "open": 106.0, "high": 108.2, "low": 105.0, "close": 107.8, "volume": 190000},
        {"date": "2026-10-13", "open": 107.8, "high": 109.0, "low": 106.5, "close": 108.5, "volume": 175000},
    ]


# ==============================================================================
# 1. Dataset Inventory & Provenance Fingerprinting Tests
# ==============================================================================

def test_list_available_datasets():
    """Verify inventory lists genuine datasets with required metadata."""
    datasets = list_available_datasets()
    assert len(datasets) >= 3
    
    # Must contain market candles and portfolio inputs
    categories = {d["category"] for d in datasets}
    assert "market_candles" in categories
    assert "portfolio_input" in categories
    assert "benchmark" in categories

    for ds in datasets:
        assert "dataset_id" in ds
        assert "name" in ds
        assert "symbol" in ds
        assert "row_count" in ds
        assert "dataset_fingerprint" in ds
        assert ds["data_mode"] == "REAL_DATA"


def test_deterministic_dataset_fingerprint(clean_candle_series):
    """Verify SHA-256 fingerprint is deterministic and sensitive to changes."""
    fp1 = compute_dataset_fingerprint(clean_candle_series)
    fp2 = compute_dataset_fingerprint(clean_candle_series)
    assert fp1 == fp2
    assert len(fp1) == 64

    # Mutating a single price must change the digest
    mutated = [dict(c) for c in clean_candle_series]
    mutated[3]["close"] = 103.01
    fp3 = compute_dataset_fingerprint(mutated)
    assert fp1 != fp3


# ==============================================================================
# 2. Explainable Data Quality Scorecard Rules
# ==============================================================================

def test_audit_clean_dataset(clean_candle_series):
    """Clean dataset should pass with high score."""
    scorecard = audit_dataset_quality(clean_candle_series, symbol="TEST_CLEAN")
    assert scorecard.overall_quality_score >= 85.0
    assert scorecard.grade in ("A+", "A")
    assert scorecard.total_records == len(clean_candle_series)
    assert len(scorecard.checks) >= 8

    # All checks should have records_evaluated matching or appropriate
    for c in scorecard.checks:
        assert c.records_evaluated >= 0
        assert c.status in ("PASSED", "WARNING", "FAILED")


def test_audit_non_positive_price_violation(clean_candle_series):
    """Zero or negative price must trigger RULE_NON_POSITIVE_PRICE failure."""
    corrupted = [dict(c) for c in clean_candle_series]
    corrupted[2]["low"] = -5.0
    corrupted[4]["close"] = 0.0

    scorecard = audit_dataset_quality(corrupted, symbol="TEST_NEGATIVE")
    check = next(c for c in scorecard.checks if c.rule_id == "RULE_NON_POSITIVE_PRICE")
    assert check.status == "FAILED"
    assert check.violations_count == 2
    assert len(check.violations) == 2
    assert any("low" in v.field_name for v in check.violations)
    assert any("close" in v.field_name for v in check.violations)


def test_audit_ohlc_relationship_violation(clean_candle_series):
    """High < Low or Open outside High/Low must trigger RULE_OHLC_RELATIONSHIPS."""
    corrupted = [dict(c) for c in clean_candle_series]
    corrupted[1]["high"] = 90.0  # High (90) < Low (103)

    scorecard = audit_dataset_quality(corrupted, symbol="TEST_OHLC")
    check = next(c for c in scorecard.checks if c.rule_id == "RULE_OHLC_RELATIONSHIPS")
    assert check.status == "FAILED"
    assert check.violations_count >= 1
    assert "High" in check.violations[0].message and "Low" in check.violations[0].message


def test_audit_duplicate_timestamps(clean_candle_series):
    """Duplicate dates must be detected by RULE_DUPLICATE_TIMESTAMPS."""
    corrupted = [dict(c) for c in clean_candle_series]
    corrupted.append(dict(clean_candle_series[2]))  # duplicate of 2026-10-06

    scorecard = audit_dataset_quality(corrupted, symbol="TEST_DUPS")
    check = next(c for c in scorecard.checks if c.rule_id == "RULE_DUPLICATE_TIMESTAMPS")
    assert check.status == "FAILED"
    assert check.violations_count == 1
    assert check.violations[0].timestamp == "2026-10-06"


def test_audit_chronological_ordering_violation(clean_candle_series):
    """Unsorted timestamps must trigger RULE_CHRONOLOGICAL_ORDER."""
    corrupted = [dict(c) for c in clean_candle_series]
    corrupted[2], corrupted[3] = corrupted[3], corrupted[2]  # swap order

    scorecard = audit_dataset_quality(corrupted, symbol="TEST_CHRONO")
    check = next(c for c in scorecard.checks if c.rule_id == "RULE_CHRONOLOGICAL_ORDER")
    assert check.status == "FAILED"
    assert check.violations_count >= 1


def test_audit_negative_volume(clean_candle_series):
    """Negative volume must trigger RULE_VOLUME_INTEGRITY."""
    corrupted = [dict(c) for c in clean_candle_series]
    corrupted[3]["volume"] = -50000

    scorecard = audit_dataset_quality(corrupted, symbol="TEST_VOL")
    check = next(c for c in scorecard.checks if c.rule_id == "RULE_VOLUME_INTEGRITY")
    assert check.status == "FAILED"
    assert check.violations_count == 1


def test_audit_stale_prices(clean_candle_series):
    """Consecutive identical closes must trigger RULE_STALE_PRICES warning."""
    corrupted = [dict(c) for c in clean_candle_series]
    # Set 4 consecutive identical closes
    for i in range(2, 6):
        corrupted[i]["close"] = 105.0

    scorecard = audit_dataset_quality(corrupted, symbol="TEST_STALE")
    check = next(c for c in scorecard.checks if c.rule_id == "RULE_STALE_PRICES")
    assert check.status == "WARNING"
    assert check.violations_count >= 1


def test_audit_statistical_outlier(clean_candle_series):
    """A sudden 35% return jump must be detected as an outlier."""
    corrupted = [dict(c) for c in clean_candle_series]
    corrupted[4]["close"] = 150.0  # ~45% jump from 103.0

    scorecard = audit_dataset_quality(corrupted, symbol="TEST_OUTLIER")
    check = next(c for c in scorecard.checks if c.rule_id == "RULE_STATISTICAL_OUTLIERS")
    assert check.status == "WARNING"
    assert check.violations_count >= 1


def test_audit_empty_candles_raises_error():
    """Empty dataset must raise ValueError."""
    with pytest.raises(ValueError):
        audit_dataset_quality([], symbol="EMPTY")


# ==============================================================================
# 3. NSE Calendar Coverage Analysis Tests
# ==============================================================================

def test_compute_coverage_analysis():
    """Verify coverage against official NSE Trading Calendar."""
    candles = [
        {"date": "2026-10-01", "close": 100.0},
        {"date": "2026-10-05", "close": 101.0},
        {"date": "2026-10-06", "close": 102.0},
        {"date": "2026-10-07", "close": 103.0},
    ]
    # In Oct 2026: Oct 2 is Gandhi Jayanti (holiday), Oct 3/4 is weekend.
    # Trading days: Oct 1, 5, 6, 7. All present!
    cov = compute_coverage_analysis(candles, start_date="2026-10-01", end_date="2026-10-07")
    assert cov["expected_sessions_count"] == 4
    assert cov["actual_sessions_count"] == 4
    assert cov["coverage_percentage"] == 100.0
    assert len(cov["missing_sessions"]) == 0
    assert "2026-10-02" in cov["official_holidays_in_window"]


def test_compute_coverage_missing_session():
    """Omission of a trading session must be explicitly flagged."""
    candles = [
        {"date": "2026-10-01", "close": 100.0},
        # Missing 2026-10-05 (Monday)
        {"date": "2026-10-06", "close": 102.0},
        {"date": "2026-10-07", "close": 103.0},
    ]
    cov = compute_coverage_analysis(candles, start_date="2026-10-01", end_date="2026-10-07")
    assert cov["expected_sessions_count"] == 4
    assert cov["actual_sessions_count"] == 3
    assert cov["coverage_percentage"] == 75.0
    assert "2026-10-05" in cov["missing_sessions"]


# ==============================================================================
# 4. Data-Quality Impact Analysis Tests
# ==============================================================================

def test_data_quality_impact_reject_invalid(clean_candle_series):
    """Reject invalid policy must filter non-positive prices and recompute risk metrics."""
    corrupted = [dict(c) for c in clean_candle_series]
    corrupted.append({"date": "2026-10-14", "open": -10.0, "high": 50.0, "low": -20.0, "close": -5.0, "volume": 1000})

    res = analyze_data_quality_impact(corrupted, policy="reject_invalid", symbol="TEST_IMPACT")
    assert res["policy"] == "reject_invalid"
    assert res["sample_size_raw"] == len(corrupted)
    assert res["sample_size_treated"] == len(clean_candle_series)
    assert res["records_modified_count"] == 1
    assert "raw_metrics" in res
    assert "treated_metrics" in res
    assert "deltas" in res


def test_data_quality_impact_deduplicate(clean_candle_series):
    """Deduplicate policy must remove repeated timestamps."""
    corrupted = [dict(c) for c in clean_candle_series]
    corrupted.append(dict(clean_candle_series[-1]))  # duplicate last bar

    res = analyze_data_quality_impact(corrupted, policy="deduplicate", symbol="TEST_DUP_IMPACT")
    assert res["sample_size_treated"] == len(clean_candle_series)
    assert res["records_modified_count"] == 1


# ==============================================================================
# 5. Non-Destructive Anomaly Dispositions Tests
# ==============================================================================

def test_record_and_get_anomaly_disposition():
    """Verify recording and querying dispositions without mutating market data."""
    disp = record_anomaly_disposition(
        anomaly_id="anom_test_123",
        dataset_id="ds_market_reliance",
        symbol="RELIANCE",
        rule_id="RULE_STATISTICAL_OUTLIERS",
        disposition="reviewed_benign",
        note="Q2 Earnings release caused genuine 8.2% intraday gap.",
        reviewer="Senior Analyst",
    )
    assert disp["anomaly_id"] == "anom_test_123"
    assert disp["disposition"] == "reviewed_benign"

    all_disps = get_anomaly_dispositions("ds_market_reliance")
    assert any(d["anomaly_id"] == "anom_test_123" for d in all_disps)


# ==============================================================================
# 6. Starlette API Integration Endpoints Tests
# ==============================================================================

def test_api_data_observatory_datasets(client):
    """GET /api/data-observatory/datasets returns authoritative inventory."""
    resp = client.get("/api/data-observatory/datasets")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["count"] >= 3
    assert any(d["symbol"] == "RELIANCE" for d in data["datasets"])


def test_api_data_observatory_audit(client):
    """POST /api/data-observatory/audit evaluates market symbol."""
    resp = client.post("/api/data-observatory/audit", json={"symbol": "RELIANCE"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    sc = data["scorecard"]
    assert sc["symbol"] == "RELIANCE"
    assert sc["overall_quality_score"] > 0
    assert len(sc["checks"]) >= 8


def test_api_data_observatory_coverage(client):
    """POST /api/data-observatory/coverage calculates session completeness."""
    resp = client.post("/api/data-observatory/coverage", json={"symbol": "RELIANCE"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    cov = data["coverage"]
    assert cov["coverage_percentage"] >= 0.0
    assert "National Stock Exchange" in cov["trading_calendar"]


def test_api_data_observatory_impact_analysis(client):
    """POST /api/data-observatory/impact-analysis compares raw vs policy."""
    resp = client.post("/api/data-observatory/impact-analysis", json={
        "symbol": "RELIANCE",
        "policy": "reject_invalid",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "raw_metrics" in data["impact"]
    assert "treated_metrics" in data["impact"]


def test_api_data_observatory_dispositions_flow(client):
    """POST /api/data-observatory/disposition and GET /api/data-observatory/dispositions."""
    payload = {
        "anomaly_id": "anom_reliance_outlier_01",
        "dataset_id": "ds_market_reliance",
        "symbol": "RELIANCE",
        "rule_id": "RULE_STATISTICAL_OUTLIERS",
        "disposition": "reviewed_benign",
        "note": "Verified genuine dividend adjustment.",
        "reviewer": "Risk Specialist",
    }
    resp = client.post("/api/data-observatory/disposition", json=payload)
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    get_resp = client.get("/api/data-observatory/dispositions?dataset_id=ds_market_reliance")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["success"] is True
    assert any(d["anomaly_id"] == "anom_reliance_outlier_01" for d in data["dispositions"])
