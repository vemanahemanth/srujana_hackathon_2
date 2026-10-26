"""Example 4: Custom Geometric Brownian Motion Simulation Engine."""
import math
import random
from typing import Any, Dict
from fragilityshield.contracts import SimulationEngine, SimulationOutput, IntParam, FloatParam


class CustomGBMSimulator(SimulationEngine):
    """Monte Carlo path simulator using Geometric Brownian Motion with drift and volatility."""

    def __init__(self) -> None:
        super().__init__(
            model_id="custom.gbm_simulator",
            name="Geometric Brownian Motion Simulator",
            version="1.0.0",
            author="quant_researcher",
            description="Simulates forward portfolio wealth trajectories under continuous Geometric Brownian Motion.",
            parameters=[
                FloatParam("mu", default=0.10, description="Annualized expected drift rate", min_value=-0.50, max_value=0.50),
                FloatParam("sigma", default=0.20, description="Annualized volatility", min_value=0.01, max_value=1.00),
                IntParam("steps", default=30, description="Forward trading days to simulate", min_value=5, max_value=252),
                IntParam("paths", default=500, description="Number of simulation trajectories", min_value=50, max_value=10000),
            ],
        )

    def generate_paths(self, initial_value: float, steps: int, paths: int, parameters: Dict[str, Any]) -> SimulationOutput:
        mu = float(parameters.get("mu", 0.10))
        sigma = float(parameters.get("sigma", 0.20))
        dt = 1.0 / 252.0

        drift = (mu - 0.5 * (sigma ** 2)) * dt
        vol_step = sigma * math.sqrt(dt)

        # Deterministic pseudo-random sequence with fixed seed for reproducibility
        rnd = random.Random(42)

        all_paths = []
        terminals = []

        for p in range(paths):
            current_p = initial_value
            path_pts = [current_p]
            for s in range(steps):
                z = rnd.gauss(0.0, 1.0)
                current_p = current_p * math.exp(drift + vol_step * z)
                path_pts.append(float(current_p))
            all_paths.append(tuple(path_pts))
            terminals.append(float(current_p))

        terminals.sort()
        mean_t = sum(terminals) / paths
        med_t = terminals[paths // 2]
        q05 = terminals[int(paths * 0.05)]
        q95 = terminals[int(paths * 0.95)]

        return SimulationOutput(
            paths=tuple(all_paths),
            terminal_values=tuple(terminals),
            mean_terminal=float(mean_t),
            median_terminal=float(med_t),
            q05_terminal=float(q05),
            q95_terminal=float(q95),
            metrics={
                "mean_terminal_wealth": float(mean_t),
                "median_terminal_wealth": float(med_t),
                "var_95_terminal_loss": float(max(0.0, initial_value - q05)),
                "expected_return_pct": float((mean_t - initial_value) / initial_value),
            },
            metadata={"drift_mu": mu, "vol_sigma": sigma, "paths_simulated": paths},
        )
