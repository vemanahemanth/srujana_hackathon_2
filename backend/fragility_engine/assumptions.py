"""Assumption Registry & Failure Regimes for FragilityShield.

Centralizes formal mathematical definitions, preconditions, limitations, and
empirically documented failure regimes across all quantitative risk models.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Sequence, Tuple


@dataclass(frozen=True)
class ModelAssumption:
    """Formal mathematical assumption specification and failure regime profile."""

    model_id: str
    model_name: str
    family: str
    mathematical_formulation: str
    distributional_assumption: str
    temporal_assumption: str
    sample_size_precondition: str
    parameter_assumptions: Tuple[str, ...]
    known_failure_regimes: Tuple[str, ...]
    fragility_attack_vulnerabilities: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        """Convert specification to a serializable dictionary."""
        return {
            "model_id": self.model_id,
            "model_name": self.model_name,
            "name": self.model_name,
            "family": self.family,
            "mathematical_formulation": self.mathematical_formulation,
            "distributional_assumption": self.distributional_assumption,
            "distributional_assumptions": self.distributional_assumption,
            "temporal_assumption": self.temporal_assumption,
            "temporal_assumptions": self.temporal_assumption,
            "sample_size_precondition": self.sample_size_precondition,
            "parameter_assumptions": list(self.parameter_assumptions),
            "known_failure_regimes": list(self.known_failure_regimes),
            "fragility_attack_vulnerabilities": list(self.fragility_attack_vulnerabilities),
            "fragility_vulnerabilities": list(self.fragility_attack_vulnerabilities),
        }


def get_model_assumptions_catalog() -> List[ModelAssumption]:
    """Return the exhaustive catalogue of model assumptions and failure regimes."""
    return [
        ModelAssumption(
            model_id="builtin.parametric_gaussian",
            model_name="Parametric Gaussian VaR & ES",
            family="Parametric Normal",
            mathematical_formulation=r"\text{VaR}_\alpha = -\mu + \sigma \cdot \Phi^{-1}(\alpha)",
            distributional_assumption="Assumes periodic returns are identically normally distributed with zero skewness and kurtosis=3.",
            temporal_assumption="Assumes independent returns with zero serial autocorrelation (i.i.d.).",
            sample_size_precondition="Minimum N >= 20 for stable mean and variance calibration.",
            parameter_assumptions=(
                "Annualization factor = 252 business days (assumes constant volatility across trading days).",
                "Degrees of freedom ddof = 1 (Bessel's sample correction).",
            ),
            known_failure_regimes=(
                "Market Crash & Tail Asymmetry: Severely underestimates loss quantiles during Black Swan events due to exponential tail decay.",
                "Volatility Regime Shifts: Cannot adapt to sudden volatility spikes; relies on static window average.",
                "Illiquidity & Zero Returns: Distorts sample standard deviation when prices are stale.",
            ),
            fragility_attack_vulnerabilities=(
                "Extremely fragile to lookback window selection during turbulent transition periods.",
                "Highly fragile to extreme tail confidence shifts (95% to 99.9% extrapolation).",
            ),
        ),
        ModelAssumption(
            model_id="builtin.historical_simulation",
            model_name="Empirical Historical Simulation",
            family="Non-parametric Quantile",
            mathematical_formulation=r"\text{VaR}_\alpha = -Q_{1-\alpha}(R)",
            distributional_assumption="Distribution-free. Assumes the future statistical distribution exactly replicates the historical sample window.",
            temporal_assumption="Assumes stationary returns without volatility clustering or auto-regressive drift.",
            sample_size_precondition="Rule-of-thumb N >= 100 observations to observe at least 5 breaches for 95% VaR.",
            parameter_assumptions=(
                "Linear quantile interpolation method.",
                "Acerbi & Tasche fractional weighting for Expected Shortfall sub-additivity.",
            ),
            known_failure_regimes=(
                "Unseen Extremes: Zero probability assigned to any loss greater than the worst historical observation in the window.",
                "Ghosting Effect: A past extreme crash creates an elevated VaR that abruptly drops to zero once the event rolls out of the window.",
                "Clustering Neglect: Weights a crash from 6 months ago identically to a crash from yesterday.",
            ),
            fragility_attack_vulnerabilities=(
                "Highly fragile to lookback window boundary truncations.",
                "Extremely fragile to missing return observations and synthetic friction drag.",
            ),
        ),
        ModelAssumption(
            model_id="builtin.ewma",
            model_name="RiskMetrics Exponentially Weighted Moving Average (EWMA)",
            family="Conditional Volatility",
            mathematical_formulation=r"\sigma_{t+1|t}^2 = \lambda \sigma_{t|t-1}^2 + (1-\lambda) r_t^2",
            distributional_assumption="Assumes returns follow conditional normal distribution with time-varying conditional variance.",
            temporal_assumption="Relaxes i.i.d. assumption by explicitly modeling volatility clustering with exponential decay memory.",
            sample_size_precondition="Effective memory window requires at least 40-60 observations for decay stabilization.",
            parameter_assumptions=(
                "Decay factor lambda = 0.94 (J.P. Morgan RiskMetrics daily standard).",
                "Mean return assumed to be zero or sample mean.",
            ),
            known_failure_regimes=(
                "Persistence Overestimation: High lambda (>0.96) can trap volatility estimates at elevated levels long after calm returns.",
                "Sudden Single-Day Crashes: 1-day shock causes huge variance spike that decays exponentially.",
                "Non-Normal Tail Fatness: Still assumes conditional Gaussianity, missing heavy-tail tail risk even with time-varying variance.",
            ),
            fragility_attack_vulnerabilities=(
                "Vulnerable to lambda decay parameter perturbation (e.g. 0.94 vs 0.90 shifts volatility significantly).",
                "Fragile to sudden friction shocks in sequential rolling forecasts.",
            ),
        ),
        ModelAssumption(
            model_id="custom.student_t",
            model_name="Parametric Student-t Heavy-Tail Model",
            family="Parametric Fat-Tailed",
            mathematical_formulation=r"\text{VaR}_\alpha = -\mu + \sigma \sqrt{\frac{\nu-2}{\nu}} \cdot t_\nu^{-1}(\alpha)",
            distributional_assumption="Assumes returns follow a Student-t distribution with degrees of freedom nu, allowing power-law polynomial tail decay.",
            temporal_assumption="Assumes stationary innovations with constant degrees of freedom over the estimation window.",
            sample_size_precondition="Requires N >= 30 observations for degrees of freedom estimation.",
            parameter_assumptions=(
                "Degrees of freedom nu in [3, 30] (typically 4-6 for financial equity returns).",
                "Variance exists only when nu > 2; kurtosis exists only when nu > 4.",
            ),
            known_failure_regimes=(
                "Overestimating Routine Risk: Heavy-tail calibration can inflate standard 90% or 95% VaR estimates compared to empirical history.",
                "Degrees of Freedom Parameter Instability: Estimating nu via maximum likelihood is noisy in small samples.",
            ),
            fragility_attack_vulnerabilities=(
                "Sensitive to degrees of freedom parameter perturbation.",
                "Fragile to regime shifts where tail thickness changes across market cycles.",
            ),
        ),
        ModelAssumption(
            model_id="custom.cornish_fisher",
            model_name="Cornish-Fisher Semiparametric Expansion",
            family="Semiparametric Moment Expansion",
            mathematical_formulation=r"z_c = z_\alpha + \frac{1}{6}(z^2-1)S + \frac{1}{24}(z^3-3z)K - \frac{1}{36}(2z^3-5z)S^2",
            distributional_assumption="Expands Gaussian quantile using sample Skewness (S) and Excess Kurtosis (K).",
            temporal_assumption="Assumes higher moments are stationary over the calibration window.",
            sample_size_precondition="Requires N >= 50 observations because sample kurtosis has high estimation variance.",
            parameter_assumptions=(
                "Higher moments (S and K) are well-defined and stable.",
            ),
            known_failure_regimes=(
                "Quantile Non-Monotonicity: Under extreme skewness or kurtosis, the Cornish-Fisher polynomial becomes non-monotonic, causing 99% VaR to be smaller than 95% VaR.",
                "Sample Kurtosis Sensitivity: A single outlier can cause kurtosis to spike by orders of magnitude.",
            ),
            fragility_attack_vulnerabilities=(
                "Extremely fragile to outlier addition/deletion attacks.",
                "Fragile to return friction shifts that alter higher moment balances.",
            ),
        ),
    ]
