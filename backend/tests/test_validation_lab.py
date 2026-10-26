"""Tests for FragilityEngine Validation Lab."""

import pytest
from fragility_engine.validation import (
    ValidationStatus,
    ValidationRecord,
    ValidationSuiteReport,
    run_reference_value_tests,
    run_portfolio_consistency_tests,
)
from fragility_engine.models import Holding, Portfolio


def test_reference_value_suite_execution():
    report = run_reference_value_tests()
    assert report.total_tests >= 5
    assert report.passed_count >= 5
    assert report.failed_count == 0
    assert report.overall_status in (ValidationStatus.PASS, ValidationStatus.WARNING)
    assert report.execution_time_ms > 0.0

    d = report.to_dict()
    assert "suite_name" in d
    assert "records" in d
    assert len(d["records"]) == report.total_tests

    # Verify each test record conforms to taxonomy
    for r in report.records:
        assert r.status in ValidationStatus
        assert r.execution_time_ms >= 0.0
        assert len(r.name) > 0


def test_portfolio_consistency_suite():
    h1 = Holding(asset_id="A", quantity=10.0, price=100.0)
    h2 = Holding(asset_id="B", quantity=20.0, price=200.0)
    port = Portfolio(portfolio_id="test", name="Test", currency="INR", holdings=(h1, h2))

    report = run_portfolio_consistency_tests(port)
    assert report.total_tests == 3
    assert report.passed_count == 3
    assert report.failed_count == 0
    assert report.overall_status == ValidationStatus.PASS
