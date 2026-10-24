"""Return calculation utilities for the FragilityShield calculation engine.

Implements pure, deterministic arithmetic return calculations from consecutive price series.
"""

from __future__ import annotations

import math
from typing import Sequence
import numpy as np


def compute_simple_returns(prices: Sequence[float] | np.ndarray) -> np.ndarray:
    """Compute arithmetic simple returns from a chronological sequence of prices.

    Formula:
        return_t = (price_t / price_{t-1}) - 1.0

    Requirements:
        - Input must contain at least two strictly positive, finite price observations.
        - Rejects missing (None, NaN), infinite, zero, and negative price values.
        - Does not interpolate, impute, or fabricate missing data.
        - Does not mutate the caller-owned input sequence.
        - Preserves chronological ordering: output[t] represents the return between
          prices[t] and prices[t+1].

    Args:
        prices: A sequence or 1D array of consecutive positive prices.

    Returns:
        A 1D numpy array of float64 simple returns of length (len(prices) - 1).

    Raises:
        TypeError: If prices is None or contains incompatible data types.
        ValueError: If prices contains fewer than 2 elements, or contains any
                    non-finite (NaN, Inf), zero, or negative prices.
    """
    if prices is None:
        raise TypeError("prices sequence cannot be None")

    try:
        n_obs = len(prices)
    except TypeError as exc:
        raise TypeError(f"prices must be a sized sequence or array; got {type(prices)}") from exc

    if n_obs < 2:
        raise ValueError(
            f"Return calculation requires at least two price observations; received {n_obs}"
        )

    # Validate elements individually to pinpoint exact failure index and value
    cleaned: list[float] = []
    for idx, raw_val in enumerate(prices):
        if raw_val is None:
            raise ValueError(f"Price at index {idx} is None; missing values are rejected")

        try:
            val = float(raw_val)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Price at index {idx} could not be converted to float: {raw_val!r}"
            ) from exc

        if not math.isfinite(val):
            raise ValueError(
                f"Price at index {idx} must be finite (not NaN or Inf); got {val!r}"
            )

        if val <= 0.0:
            raise ValueError(
                f"Price at index {idx} must be strictly positive; got {val!r}"
            )

        cleaned.append(val)

    # Convert to a newly allocated numpy array (guaranteeing caller immutability)
    price_arr = np.array(cleaned, dtype=np.float64, copy=True)

    # Vectorized arithmetic return calculation: p_t / p_{t-1} - 1.0
    returns = (price_arr[1:] / price_arr[:-1]) - 1.0

    return returns
