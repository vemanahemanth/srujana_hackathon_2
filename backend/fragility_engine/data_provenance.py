"""FragilityShield Data Provenance, Lineage, and Data-Source Policy Engine.

Enforces strict, transparent data classification across all quantitative labs:
- REAL_DATA: Data originates from an authoritative live/historical provider (e.g. Upstox V3) or certified external source.
- USER_UPLOADED_DATA: Data supplied directly by user or imported from external file.
- SYNTHETIC_TEST_DATA: Data generated for unit tests, fixtures, demos, or simulations. Visibly labelled synthetic.
- MIXED_DATA: Combines empirical observed data with modeled, imputed, or simulated projections.

Zero Silent Substitution:
Synthetic fixtures are NEVER silently returned as observed market history.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union


class DataSourceMode(str, Enum):
    """Canonical data-source classification modes."""
    REAL_DATA = "REAL_DATA"
    USER_UPLOADED_DATA = "USER_UPLOADED_DATA"
    SYNTHETIC_TEST_DATA = "SYNTHETIC_TEST_DATA"
    MIXED_DATA = "MIXED_DATA"


class DataFreshnessStatus(str, Enum):
    """Temporal freshness classification of market data."""
    LIVE = "LIVE"
    CACHED_REAL = "CACHED_REAL"
    HISTORICAL_OBSERVED = "HISTORICAL_OBSERVED"
    SIMULATED = "SIMULATED"
    SYNTHETIC = "SYNTHETIC"
    STALE = "STALE"


@dataclass(frozen=True)
class DataProvenance:
    """Immutable data lineage, freshness, and provenance record."""

    data_source_mode: DataSourceMode
    provider: Optional[str] = None
    dataset_id: Optional[str] = None
    instrument: Optional[str] = None
    date_range: Optional[Tuple[str, str]] = None
    sampling_interval: str = "1D"
    retrieval_timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    freshness_status: DataFreshnessStatus = DataFreshnessStatus.HISTORICAL_OBSERVED
    is_synthetic: bool = False
    is_user_uploaded: bool = False
    is_live_provider: bool = False
    warnings: Tuple[str, ...] = ()
    assumptions: Tuple[str, ...] = ()
    transformations: Tuple[str, ...] = ()
    fingerprint: Optional[str] = None
    disclaimer: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.data_source_mode, DataSourceMode):
            try:
                object.__setattr__(
                    self, "data_source_mode", DataSourceMode(self.data_source_mode)
                )
            except ValueError:
                object.__setattr__(self, "data_source_mode", DataSourceMode.MIXED_DATA)

        if not isinstance(self.freshness_status, DataFreshnessStatus):
            try:
                object.__setattr__(
                    self, "freshness_status", DataFreshnessStatus(self.freshness_status)
                )
            except ValueError:
                object.__setattr__(
                    self, "freshness_status", DataFreshnessStatus.HISTORICAL_OBSERVED
                )

    def to_dict(self) -> Dict[str, Any]:
        """Convert provenance to JSON-serializable dictionary."""
        return {
            "data_source_mode": self.data_source_mode.value,
            "provider": self.provider,
            "dataset_id": self.dataset_id,
            "instrument": self.instrument,
            "date_range": list(self.date_range) if self.date_range else None,
            "sampling_interval": self.sampling_interval,
            "retrieval_timestamp": self.retrieval_timestamp,
            "freshness_status": self.freshness_status.value,
            "is_synthetic": self.is_synthetic,
            "is_user_uploaded": self.is_user_uploaded,
            "is_live_provider": self.is_live_provider,
            "warnings": list(self.warnings),
            "assumptions": list(self.assumptions),
            "transformations": list(self.transformations),
            "fingerprint": self.fingerprint,
            "disclaimer": self.disclaimer,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DataProvenance:
        """Instantiate DataProvenance from dictionary."""
        d = dict(data)
        mode_val = d.get("data_source_mode", DataSourceMode.MIXED_DATA.value)
        fresh_val = d.get("freshness_status", DataFreshnessStatus.HISTORICAL_OBSERVED.value)
        dr_raw = d.get("date_range")
        date_range = tuple(dr_raw) if dr_raw and isinstance(dr_raw, (list, tuple)) else None

        return cls(
            data_source_mode=DataSourceMode(mode_val),
            provider=d.get("provider"),
            dataset_id=d.get("dataset_id"),
            instrument=d.get("instrument"),
            date_range=date_range,
            sampling_interval=d.get("sampling_interval", "1D"),
            retrieval_timestamp=d.get(
                "retrieval_timestamp", datetime.now(timezone.utc).isoformat()
            ),
            freshness_status=DataFreshnessStatus(fresh_val),
            is_synthetic=bool(d.get("is_synthetic", False)),
            is_user_uploaded=bool(d.get("is_user_uploaded", False)),
            is_live_provider=bool(d.get("is_live_provider", False)),
            warnings=tuple(d.get("warnings", ())),
            assumptions=tuple(d.get("assumptions", ())),
            transformations=tuple(d.get("transformations", ())),
            fingerprint=d.get("fingerprint"),
            disclaimer=d.get("disclaimer"),
        )

    # --------------------------------------------------------------------------
    # Standard Factory Constructors
    # --------------------------------------------------------------------------

    @classmethod
    def real_provider(
        cls,
        provider: str = "upstox_v3",
        instrument: str = "",
        date_range: Optional[Tuple[str, str]] = None,
        sampling_interval: str = "1D",
        is_live: bool = False,
        fingerprint: Optional[str] = None,
        warnings: Sequence[str] = (),
        provider_name: Optional[str] = None,
        sample_count: Optional[int] = None,
        **kwargs: Any,
    ) -> DataProvenance:
        """Create provenance for data directly retrieved from an authenticated real provider."""
        resolved_provider = provider_name or provider
        resolved_assumptions = [
            f"Genuine historical market observations retrieved from connected market-data provider '{resolved_provider}'.",
        ]
        if sample_count is not None:
            resolved_assumptions.append(f"Observation sample size: {sample_count} points.")
        return cls(
            data_source_mode=DataSourceMode.REAL_DATA,
            provider=resolved_provider,
            instrument=instrument,
            date_range=date_range,
            sampling_interval=sampling_interval,
            freshness_status=DataFreshnessStatus.LIVE if is_live else DataFreshnessStatus.HISTORICAL_OBSERVED,
            is_synthetic=False,
            is_user_uploaded=False,
            is_live_provider=True,
            warnings=tuple(warnings),
            assumptions=tuple(resolved_assumptions),
            fingerprint=fingerprint,
            disclaimer=None,
        )

    @classmethod
    def user_uploaded(
        cls,
        dataset_id: Optional[str] = None,
        instrument: Optional[str] = None,
        fingerprint: Optional[str] = None,
        warnings: Sequence[str] = (),
        date_range: Optional[Tuple[str, str]] = None,
        source_name: Optional[str] = None,
        sample_count: Optional[int] = None,
        **kwargs: Any,
    ) -> DataProvenance:
        """Create provenance for user-supplied payload observations."""
        resolved_id = dataset_id or source_name
        resolved_assumptions = [
            "Observations supplied directly by user; unverified against third-party broker.",
        ]
        if sample_count is not None:
            resolved_assumptions.append(f"Holding/sample count: {sample_count}.")
        return cls(
            data_source_mode=DataSourceMode.USER_UPLOADED_DATA,
            provider="user_upload",
            dataset_id=resolved_id,
            instrument=instrument or "USER_PROVIDED_SERIES",
            date_range=date_range,
            freshness_status=DataFreshnessStatus.HISTORICAL_OBSERVED,
            is_synthetic=False,
            is_user_uploaded=True,
            is_live_provider=False,
            warnings=tuple(warnings),
            assumptions=tuple(resolved_assumptions),
            fingerprint=fingerprint,
            disclaimer="User-provided observation series. Not independently verified against exchange trade tapes.",
        )

    @classmethod
    def synthetic_demo(
        cls,
        reason: str = "Demonstration fixture",
        warnings: Sequence[str] = (),
        sample_name: str = "synthetic_normal_benchmark",
    ) -> DataProvenance:
        """Create provenance for explicitly requested synthetic demonstration data."""
        return cls(
            data_source_mode=DataSourceMode.SYNTHETIC_TEST_DATA,
            provider="synthetic_generator",
            dataset_id=f"synthetic_{sample_name}",
            instrument=f"SYNTHETIC:{sample_name.upper()}",
            freshness_status=DataFreshnessStatus.SYNTHETIC,
            is_synthetic=True,
            is_user_uploaded=False,
            is_live_provider=False,
            warnings=tuple(list(warnings) + [
                "SYNTHETIC TEST DATA: Output was computed using generated synthetic demonstration fixtures. "
                "Do NOT use as evidence of real-world trading performance or production risk decisions."
            ]),
            assumptions=(
                f"Generated synthetic observations ({reason}).",
                "Data does not represent observed market history.",
            ),
            disclaimer="SYNTHETIC DEMONSTRATION DATA: Not observed real-world market prices.",
        )

    @classmethod
    def mixed_simulation(
        cls,
        base_mode: DataSourceMode,
        simulation_type: str,
        warnings: Sequence[str] = (),
    ) -> DataProvenance:
        """Create provenance for empirical base series subjected to stochastic projection/resampling."""
        return cls(
            data_source_mode=DataSourceMode.MIXED_DATA,
            provider="simulation_engine",
            freshness_status=DataFreshnessStatus.SIMULATED,
            is_synthetic=False,
            is_user_uploaded=(base_mode == DataSourceMode.USER_UPLOADED_DATA),
            is_live_provider=(base_mode == DataSourceMode.REAL_DATA),
            warnings=tuple(warnings),
            assumptions=(
                f"Combines empirical historical baseline ({base_mode.value}) with {simulation_type}.",
                "Simulated future trajectories do not guarantee observed market outcomes.",
            ),
            transformations=(f"Stochastic generation: {simulation_type}",),
            disclaimer="MIXED DATA: Results incorporate simulated projections and historical observations.",
        )
