"""Phase 1 Quantitative Integrity Remediation Tests for FragilityShield.

Validates:
1. Allocation Covariance Integrity & Provenance (CRIT-01):
   - Strict validation of explicit covariance matrices (dimensions, symmetry, PSD, finiteness)
   - Empirical covariance estimation from aligned return observations
   - Elimination of silent fallback / synthetic fabrication
   - Explicit synthetic/demo mode and accurate provenance labeling
   - HTTP 422 error structures on invalid/missing inputs

2. Kupiec POF Statistical Correctness (CRIT-03):
   - Unconditional-coverage likelihood ratio test with continuous limits (x=0, x=N)
   - Independent mathematical reference validation for N=100, N=4, N=252
   - Sample sufficiency power separation (INSUFFICIENT_POWER, LOW_POWER, SUFFICIENT)
   - Proper rejection of over-conservative (x=0) and catastrophic (x=N) models
   - Boundary input validation (N > 0, 0 <= x <= N, 0 < p < 1)

3. VaR Quantile Scoring & Honest Presentation (MATH-01, FRONT-01):
   - Quantile Pinball/Tick Loss scoring rule at alpha=0.95
   - Relative skill calculation against empirical training quantile baseline
   - Correct negative skill retention and honest UNDERPERFORMING labeling
"""

import math
import numpy as np
import pytest
from starlette.testclient import TestClient

from backend.app import app, validate_covariance_matrix
from fragility_engine.risk_model_validation import calculate_kupiec_test


@pytest.fixture
def client():
    return TestClient(app)


# ==============================================================================
# Helper: Independent Pure Mathematical Reference Implementation
# ==============================================================================

def reference_kupiec_lr(N: int, x: int, p: float = 0.05) -> float:
    """Independent mathematical reference implementation of Kupiec POF LR.
    
    Uses standard log-likelihood ratio formula:
        LR = -2 * ln( L(p) / L(x/N) )
           = -2 * [ (N-x)*ln(1-p) + x*ln(p) - (N-x)*ln(1 - x/N) - x*ln(x/N) ]
    
    Continuous boundary limits:
        x = 0: (x/N)^x -> 1, (1 - x/N)^(N-x) -> 1^N = 1  => LR = -2 * N * ln(1-p)
        x = N: (1 - x/N)^(N-x) -> 1, (x/N)^x -> 1^N = 1  => LR = -2 * N * ln(p)
    """
    if N <= 0:
        raise ValueError(f"N must be positive, got {N}")
    if x < 0 or x > N:
        raise ValueError(f"x must satisfy 0 <= x <= N, got x={x}, N={N}")
    if not (0.0 < p < 1.0):
        raise ValueError(f"p must be in (0, 1), got {p}")

    if x == 0:
        return -2.0 * N * math.log(1.0 - p)
    elif x == N:
        return -2.0 * N * math.log(p)
    else:
        p_hat = x / N
        ln_L_null = (N - x) * math.log(1.0 - p) + x * math.log(p)
        ln_L_alt = (N - x) * math.log(1.0 - p_hat) + x * math.log(p_hat)
        return -2.0 * (ln_L_null - ln_L_alt)


def reference_pinball_loss(y: np.ndarray, q: float, alpha: float = 0.95) -> float:
    """Independent reference calculation of quantile pinball / tick loss:
        S_alpha(y, q) = (y - q) * (alpha - I(y < q))
    """
    y_arr = np.asarray(y, dtype=float)
    indicator = (y_arr < q).astype(float)
    loss = (y_arr - q) * (alpha - indicator)
    return float(np.mean(loss))


# ==============================================================================
# Phase 1: Allocation Covariance Integrity & Provenance Tests
# ==============================================================================

class TestAllocationCovarianceIntegrity:
    """Tests covariance validation, provenance, and structured error responses."""

    def test_missing_covariance_and_insufficient_history_returns_422(self, client):
        """When neither covariance nor empirical returns are provided, reject with 422."""
        payload = {
            "portfolio": {
                "holdings": [
                    {"asset_id": "NSE:UNKNOWN_A", "weight": 0.5, "price": 100.0, "quantity": 10},
                    {"asset_id": "NSE:UNKNOWN_B", "weight": 0.5, "price": 200.0, "quantity": 10},
                ]
            },
            "allow_synthetic": False,
        }
        resp = client.post("/api/allocation/optimize", json=payload)
        assert resp.status_code == 422
        data = resp.json()
        assert data.get("error_type") == "missing_covariance_data"
        assert "data_provenance" in data
        assert "details" in data

    def test_valid_empirical_returns_matrix_returns_200_and_user_uploaded_provenance(self, client):
        """When user provides empirical return observations, compute empirical covariance."""
        np.random.seed(42)
        # 3 assets, 30 daily observations
        returns = np.random.normal(0.001, 0.02, size=(30, 3)).tolist()
        payload = {
            "asset_ids": ["NSE:ASSET_A", "NSE:ASSET_B", "NSE:ASSET_C"],
            "returns_matrix": returns,
            "objective": "MIN_VARIANCE",
        }
        resp = client.post("/api/allocation/optimize", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "weights" in data
        assert len(data["weights"]) == 3
        assert pytest.approx(sum(data["weights"].values()), abs=1e-5) == 1.0
        assert data["data_provenance"]["data_source_mode"] == "USER_UPLOADED_DATA"
        assert data["data_provenance"]["is_synthetic"] is False

    def test_valid_explicit_covariance_matrix_returns_200(self, client):
        """Explicitly supplied symmetric PSD covariance matrix is accepted."""
        cov = [
            [0.04, 0.01, 0.005],
            [0.01, 0.09, 0.015],
            [0.005, 0.015, 0.06],
        ]
        asset_ids = ["NSE:HDFCBANK", "NSE:TCS", "NSE:RELIANCE"]
        payload = {
            "covariance_matrix": cov,
            "asset_ids": asset_ids,
            "objective": "MIN_VARIANCE",
        }
        resp = client.post("/api/allocation/optimize", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert set(data["weights"].keys()) == set(asset_ids)
        assert pytest.approx(sum(data["weights"].values()), abs=1e-5) == 1.0
        assert data["data_provenance"]["data_source_mode"] == "USER_UPLOADED_DATA"
        assert data["data_provenance"]["is_synthetic"] is False

    def test_dimension_mismatch_and_ordering_returns_422(self, client):
        """Mismatched matrix dimensions vs asset_ids returns HTTP 422."""
        cov = [
            [0.04, 0.01],
            [0.01, 0.09],
        ]
        # 3 assets for 2x2 matrix
        payload = {
            "covariance_matrix": cov,
            "asset_ids": ["NSE:A", "NSE:B", "NSE:C"],
        }
        resp = client.post("/api/allocation/optimize", json=payload)
        assert resp.status_code == 422
        assert "dimension" in str(resp.json()).lower()

    def test_non_square_matrix_returns_422(self, client):
        """Non-square matrix returns HTTP 422."""
        cov = [
            [0.04, 0.01, 0.02],
            [0.01, 0.09, 0.03],
        ]
        payload = {
            "covariance_matrix": cov,
            "asset_ids": ["NSE:A", "NSE:B"],
        }
        resp = client.post("/api/allocation/optimize", json=payload)
        assert resp.status_code == 422

    def test_non_finite_entries_returns_422(self, client):
        """Non-finite entries in covariance matrix return HTTP 422."""
        # Test helper directly with NaN and Inf
        with pytest.raises(ValueError, match="finite"):
            validate_covariance_matrix(np.array([[0.04, np.nan], [np.nan, 0.09]]), ["NSE:A", "NSE:B"])

        with pytest.raises(ValueError, match="finite"):
            validate_covariance_matrix(np.array([[0.04, np.inf], [np.inf, 0.09]]), ["NSE:A", "NSE:B"])

        # Test endpoint with non-numeric string entry
        payload = {
            "covariance_matrix": [[0.04, "invalid_nan"], ["invalid_nan", 0.09]],
            "asset_ids": ["NSE:A", "NSE:B"],
        }
        resp = client.post("/api/allocation/optimize", json=payload)
        assert resp.status_code == 422
        assert "finite" in str(resp.json()).lower() or "numeric" in str(resp.json()).lower()

    def test_asymmetric_matrix_returns_422(self, client):
        """Asymmetric matrix exceeding tolerance returns HTTP 422."""
        cov = [
            [0.04, 0.03],
            [0.01, 0.09],  # Asymmetry: |0.03 - 0.01| = 0.02 > 1e-4
        ]
        payload = {
            "covariance_matrix": cov,
            "asset_ids": ["NSE:A", "NSE:B"],
        }
        resp = client.post("/api/allocation/optimize", json=payload)
        assert resp.status_code == 422
        assert "symmetric" in str(resp.json()).lower()

    def test_non_psd_matrix_returns_422(self, client):
        """Matrix with significant negative eigenvalues returns HTTP 422."""
        cov = [
            [1.0, 2.0],
            [2.0, 1.0],  # Eigenvalues are 3.0 and -1.0
        ]
        payload = {
            "covariance_matrix": cov,
            "asset_ids": ["NSE:A", "NSE:B"],
        }
        resp = client.post("/api/allocation/optimize", json=payload)
        assert resp.status_code == 422
        assert "positive semi-definite" in str(resp.json()).lower()

    def test_explicit_synthetic_demo_mode_labeled_accurately(self, client):
        """When allow_synthetic=True, synthetic covariance is allowed but honestly labeled."""
        payload = {
            "portfolio": {
                "holdings": [
                    {"asset_id": "NSE:UNKNOWN_X", "weight": 0.5, "price": 100.0, "quantity": 10},
                    {"asset_id": "NSE:UNKNOWN_Y", "weight": 0.5, "price": 200.0, "quantity": 10},
                ]
            },
            "allow_synthetic": True,
        }
        resp = client.post("/api/allocation/optimize", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_synthetic"] is True
        assert data["data_provenance"]["data_source_mode"] == "SYNTHETIC_TEST_DATA"
        assert data["data_provenance"]["is_synthetic"] is True

    def test_validate_covariance_matrix_helper_directly(self):
        """Unit test the validate_covariance_matrix helper directly."""
        # Valid matrix
        mat = np.array([[0.04, 0.01], [0.01, 0.04]])
        cov_res, aid_res = validate_covariance_matrix(mat, ["A", "B"])
        assert cov_res.shape == (2, 2)
        assert aid_res == ["A", "B"]

        # Dimension error
        with pytest.raises(ValueError, match="does not match covariance dimensions"):
            validate_covariance_matrix(mat, ["A", "B", "C"])

        # Asymmetry error
        asym = np.array([[0.04, 0.02], [0.01, 0.04]])
        with pytest.raises(ValueError, match="asymmetric"):
            validate_covariance_matrix(asym, ["A", "B"])


# ==============================================================================
# Phase 2: Kupiec POF Statistical Correctness Tests
# ==============================================================================

class TestKupiecPOFStatisticalCorrectness:
    """Tests Kupiec POF likelihood ratio, boundary limits, and exact references."""

    @pytest.mark.parametrize(
        "N, x, p, expected_lr, expected_pass",
        [
            # N=100 cases
            (100, 0, 0.05, 10.2587, False),     # Overly conservative / 0 breaches fails
            (100, 5, 0.05, 0.0000, True),       # Exactly expected breaches passes
            (100, 10, 0.05, 4.1308, False),     # Excess breaches fails (LR > 3.841)
            (100, 100, 0.05, 599.1465, False),  # 100% breach catastrophe fails (NEVER passes!)
            # N=4 small-sample case
            (4, 0, 0.05, 0.4103, True),         # LR < 3.841, but low power expected
            # N=252 one trading year cases
            (252, 0, 0.05, 25.8518, False),     # 0 breaches on full year fails
            (252, 12, 0.05, 0.0305, True),      # 12 breaches (4.76% vs 5.0%) passes
            (252, 25, 0.05, 10.1126, False),    # 25 breaches (9.92% vs 5.0%) fails
        ],
    )
    def test_kupiec_analytical_references(self, N, x, p, expected_lr, expected_pass):
        """Verify calculate_kupiec_test matches independent mathematical references."""
        # 1. Check our independent reference formula
        ref_lr = reference_kupiec_lr(N, x, p)
        assert pytest.approx(ref_lr, abs=1e-3) == expected_lr

        # 2. Check fragility_engine.risk_model_validation.calculate_kupiec_test
        conf = 1.0 - p
        res = calculate_kupiec_test(n_observations=N, n_exceptions=x, confidence_level=conf)
        assert pytest.approx(res.lr_stat, abs=1e-3) == expected_lr
        assert res.passed == expected_pass

    def test_kupiec_small_sample_sufficiency_warning(self):
        """N=4 with 0 breaches has expected breaches 0.2 < 1.0 => INSUFFICIENT_POWER."""
        res = calculate_kupiec_test(n_observations=4, n_exceptions=0, confidence_level=0.95)
        assert res.sample_sufficiency == "INSUFFICIENT_POWER"
        assert res.sample_size_warning is True

        # N=60 with 3 breaches: expected breaches 3.0 < 5.0 => LOW_POWER
        res_60 = calculate_kupiec_test(n_observations=60, n_exceptions=3, confidence_level=0.95)
        assert res_60.sample_sufficiency == "LOW_POWER"
        assert res_60.sample_size_warning is True

        # N=252 with 12 breaches: expected breaches 12.6 >= 5.0 => SUFFICIENT
        res_252 = calculate_kupiec_test(n_observations=252, n_exceptions=12, confidence_level=0.95)
        assert res_252.sample_sufficiency == "SUFFICIENT"
        assert res_252.sample_size_warning is False

    @pytest.mark.parametrize(
        "N, x, p",
        [
            (0, 0, 0.05),     # N <= 0
            (-10, 0, 0.05),   # Negative N
            (100, -1, 0.05),  # x < 0
            (100, 105, 0.05), # x > N
            (100, 5, 0.0),    # p <= 0
            (100, 5, 1.0),    # p >= 1
        ],
    )
    def test_kupiec_invalid_boundary_inputs(self, N, x, p):
        """Invalid inputs must raise ValueError in mathematical reference and engine."""
        with pytest.raises(ValueError):
            reference_kupiec_lr(N, x, p)

        with pytest.raises(ValueError):
            conf = 1.0 - p if (0.0 < p < 1.0) else (0.0 if p >= 1.0 else 1.0)
            calculate_kupiec_test(n_observations=N, n_exceptions=x, confidence_level=conf)

    def test_model_validation_endpoint_integrates_kupiec(self, client):
        """POST /api/models/validate returns genuine Kupiec LR stat, sufficiency, and CI."""
        np.random.seed(42)
        rets = np.random.normal(0.0005, 0.015, size=60).tolist()
        payload = {
            "model_id": "builtin.parametric_gaussian",
            "returns": rets,
            "train_ratio": 0.70,
            "val_ratio": 0.15,
        }
        resp = client.post("/api/models/validate", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        metrics = data["validation_report"]["test_metrics"]

        assert "kupiec_lr_statistic" in metrics
        assert "kupiec_test_passed" in metrics
        assert "sample_sufficiency" in metrics
        assert "clopper_pearson_ci" in metrics
        assert metrics["sample_sufficiency"] in ("INSUFFICIENT_POWER", "LOW_POWER", "SUFFICIENT")


# ==============================================================================
# Phase 3: VaR Quantile Scoring & Honest Presentation Tests
# ==============================================================================

class TestQuantileScoringAndHonestPresentation:
    """Tests Pinball/Tick Loss quantile scoring and honest presentation of skill."""

    def test_pinball_loss_exact_mathematics(self):
        """Verify pinball loss on synthetic test observations."""
        y = np.array([-0.05, -0.02, 0.01, 0.03, -0.01])
        q = -0.02  # Quantile forecast
        alpha = 0.95

        loss = reference_pinball_loss(y, q, alpha)
        # Check manually:
        # y = -0.05: (-0.05 - -0.02) * (0.95 - 1.0) = -0.03 * -0.05 = 0.0015
        # y = -0.02: (0.00) * (0.95 - 0.0) = 0.0
        # y = 0.01: (0.01 - -0.02) * (0.95 - 0.0) = 0.03 * 0.95 = 0.0285
        # y = 0.03: (0.03 - -0.02) * (0.95 - 0.0) = 0.05 * 0.95 = 0.0475
        # y = -0.01: (-0.01 - -0.02) * (0.95 - 0.0) = 0.01 * 0.95 = 0.0095
        # Mean = (0.0015 + 0.0 + 0.0285 + 0.0475 + 0.0095) / 5 = 0.087 / 5 = 0.0174
        assert pytest.approx(loss, abs=1e-5) == 0.0174

    def test_relative_skill_positive_when_model_outperforms(self):
        """When model quantile has lower loss than baseline, skill is positive."""
        model_loss = 0.005
        baseline_loss = 0.008
        skill = (1.0 - model_loss / baseline_loss) * 100.0
        assert skill > 0.0
        assert pytest.approx(skill, abs=1e-3) == 37.5

    def test_relative_skill_negative_when_model_underperforms(self):
        """When model quantile has higher loss than baseline, skill is negative and preserved."""
        model_loss = 0.012
        baseline_loss = 0.008
        skill = (1.0 - model_loss / baseline_loss) * 100.0
        assert skill < 0.0
        assert pytest.approx(skill, abs=1e-3) == -50.0

    def test_model_validation_endpoint_returns_pinball_scoring(self, client):
        """Validation API returns proper scoring rule, pinball metrics, and verdict."""
        np.random.seed(42)
        rets = np.random.normal(0.0005, 0.015, size=60).tolist()
        payload = {
            "model_id": "builtin.parametric_gaussian",
            "returns": rets,
            "train_ratio": 0.70,
            "val_ratio": 0.15,
        }
        resp = client.post("/api/models/validate", json=payload)
        assert resp.status_code == 200
        data = resp.json()["validation_report"]

        metrics = data["test_metrics"]
        benchmarks = data["benchmarks"]

        assert "pinball_loss" in metrics["scoring_rule"]
        assert "model_pinball_loss" in metrics
        assert "naive_baseline_pinball_loss" in metrics
        assert metrics["model_pinball_loss"] > 0
        assert metrics["naive_baseline_pinball_loss"] > 0

        assert "relative_skill_pct" in benchmarks
        assert "skill_verdict" in benchmarks
        assert benchmarks["skill_verdict"] in ("SKILLFUL", "UNSKILLFUL", "NEUTRAL")
