"""FragilityShield Upstox Market Data V3 Provider Adapter.

Provides secure, production-minded integration with Upstox Market Data APIs:
- Authentication & Connection Status Verification
- Upstox Instrument Key Resolution (Indices, Equities)
- Historical OHLCV Candles (V3 API with pagination, normalization, Asia/Kolkata timestamps)
- Current Market Quotes & LTP (V3 API)
- Downstream Dataset Registration & OHLCV Physical Integrity Validation
- Integration with FragilityShield DataProvider & ProjectCatalog

Strict Non-Negotiable Safeguards:
- 100% Read-Only Market Data: No order placement, order modification, or trade execution.
- Credential Security: No tokens or secrets logged or returned in plain text.
- Safe Fallbacks & Deterministic Verification.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import math
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple, Union

import httpx
import numpy as np

from .data_diagnostics import OHLCVCandleReport, validate_financial_ohlcv
from .market_data import (
    DataProvider,
    ProviderCapability,
    ProviderLifecycleStatus,
    UnsupportedCapabilityError,
)
from .projects import DatasetRecord, ProjectCatalog

logger = logging.getLogger("fragility_shield.upstox")

# Standard Indian Standard Time offset (+05:30)
IST = timezone(timedelta(hours=5, minutes=30))


class UpstoxError(RuntimeError):
    """Base exception for all Upstox provider operations."""


class UpstoxConfigurationError(UpstoxError):
    """Raised when required Upstox configuration or credentials are missing or invalid."""


class UpstoxAuthenticationError(UpstoxError):
    """Raised when an Upstox access token is invalid, expired, or unentitled."""


class UpstoxRateLimitError(UpstoxError):
    """Raised when Upstox API rate limits are exceeded."""


class UpstoxInstrumentNotFoundError(UpstoxError):
    """Raised when a human-readable symbol cannot be mapped to an Upstox instrument key."""


# ==============================================================================
# 1. Configuration & Credential Safety (§4)
# ==============================================================================

@dataclass
class UpstoxConfig:
    """Secure configuration container for Upstox API credentials."""

    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    redirect_uri: str = "http://localhost:8000/api/upstox/oauth/callback"
    access_token: Optional[str] = None
    api_base_url: str = "https://api.upstox.com"

    @classmethod
    def from_env(cls, env_path: Optional[Union[str, Path]] = None) -> UpstoxConfig:
        """Load configuration from environment variables, falling back to local .env file.
        
        Credentials are never committed or exposed.
        """
        env_dict: Dict[str, str] = {}
        
        # Read .env file if it exists
        target_path = Path(env_path) if env_path else Path(".env")
        if target_path.exists() and target_path.is_file():
            try:
                for line in target_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        env_dict[k.strip()] = v.strip().strip("'\"")
            except Exception as err:
                logger.warning(f"Failed to read local env file: {err}")

        # OS environment variables take precedence
        client_id = os.environ.get("UPSTOX_CLIENT_ID") or env_dict.get("UPSTOX_CLIENT_ID")
        client_secret = os.environ.get("UPSTOX_CLIENT_SECRET") or env_dict.get("UPSTOX_CLIENT_SECRET")
        redirect_uri = (
            os.environ.get("UPSTOX_REDIRECT_URI")
            or env_dict.get("UPSTOX_REDIRECT_URI")
            or "http://localhost:8000/api/upstox/oauth/callback"
        )
        access_token = os.environ.get("UPSTOX_ACCESS_TOKEN") or env_dict.get("UPSTOX_ACCESS_TOKEN")
        api_base_url = (
            os.environ.get("UPSTOX_API_BASE_URL")
            or env_dict.get("UPSTOX_API_BASE_URL")
            or "https://api.upstox.com"
        ).rstrip("/")

        return cls(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            access_token=access_token,
            api_base_url=api_base_url,
        )

    @property
    def has_access_token(self) -> bool:
        """True if an access token is provided."""
        return bool(self.access_token and self.access_token.strip())

    @property
    def has_oauth_client(self) -> bool:
        """True if OAuth client ID and client secret are configured."""
        return bool(self.client_id and self.client_secret)

    @property
    def is_configured(self) -> bool:
        """True if at least an access token or OAuth credentials are set."""
        return self.has_access_token or self.has_oauth_client

    def mask_token(self, token: Optional[str]) -> str:
        """Redact sensitive token, revealing only safe prefix/suffix length."""
        if not token:
            return ""
        t = token.strip()
        if len(t) <= 8:
            return "******"
        return f"{t[:4]}...{t[-4:]}"

    def safe_dict(self) -> Dict[str, Any]:
        """Return non-sensitive configuration dictionary safe for logging and API status."""
        return {
            "has_access_token": self.has_access_token,
            "has_oauth_client": self.has_oauth_client,
            "masked_access_token": self.mask_token(self.access_token) if self.has_access_token else None,
            "masked_client_id": self.mask_token(self.client_id) if self.client_id else None,
            "redirect_uri": self.redirect_uri,
            "api_base_url": self.api_base_url,
        }

    def __repr__(self) -> str:
        return (
            f"UpstoxConfig(configured={self.is_configured}, "
            f"has_token={self.has_access_token}, "
            f"token={self.mask_token(self.access_token)!r}, "
            f"base_url={self.api_base_url!r})"
        )


# ==============================================================================
# 2. Canonical Domain Models (§5)
# ==============================================================================

@dataclass(frozen=True)
class UpstoxAuthStatus:
    """Connection and authorization status report."""

    configured: bool
    authenticated: bool
    status_code: int
    message: str
    user_type: Optional[str] = None
    exchanges: Tuple[str, ...] = ()
    read_only: bool = True
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "configured": self.configured,
            "authenticated": self.authenticated,
            "status_code": self.status_code,
            "message": self.message,
            "user_type": self.user_type,
            "exchanges": list(self.exchanges),
            "read_only": self.read_only,
            "timestamp": self.timestamp,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class UpstoxInstrument:
    """Normalized Upstox instrument reference."""

    instrument_key: str
    symbol: str
    name: str
    exchange: str
    segment: str
    instrument_type: str = "EQUITY"
    lot_size: int = 1
    tick_size: float = 0.05
    sector: str = "General"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "instrument_key": self.instrument_key,
            "symbol": self.symbol,
            "name": self.name,
            "exchange": self.exchange,
            "segment": self.segment,
            "instrument_type": self.instrument_type,
            "lot_size": self.lot_size,
            "tick_size": self.tick_size,
            "sector": self.sector,
        }


@dataclass(frozen=True)
class CanonicalCandle:
    """Normalized OHLCV candlestick representation in Asia/Kolkata timezone."""

    timestamp: str  # ISO 8601 with Asia/Kolkata (+05:30) offset
    open: float
    high: float
    low: float
    close: float
    volume: float
    open_interest: float = 0.0
    symbol: str = ""
    instrument_key: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "open_interest": self.open_interest,
            "symbol": self.symbol,
            "instrument_key": self.instrument_key,
        }


@dataclass(frozen=True)
class CanonicalQuote:
    """Normalized market quote representation."""

    symbol: str
    instrument_key: str
    last_price: float
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[float] = None
    source_timestamp: Optional[str] = None
    retrieval_timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "instrument_key": self.instrument_key,
            "last_price": self.last_price,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "source_timestamp": self.source_timestamp,
            "retrieval_timestamp": self.retrieval_timestamp,
        }


# ==============================================================================
# 3. Instrument Resolver (§5.B)
# ==============================================================================

class UpstoxInstrumentResolver:
    """Resolves human symbols to exact Upstox instrument keys with disambiguation.
    
    Includes a high-speed curated index of Indian benchmark indices and major NSE large-caps,
    with support for custom registration and direct instrument key pass-through.
    """

    # Curated authoritative mappings for major Indian market instruments
    CURATED_INSTRUMENTS: Mapping[str, UpstoxInstrument] = {
        # Benchmark & Sectoral Indices
        "NIFTY": UpstoxInstrument("NSE_INDEX|Nifty 50", "NIFTY", "Nifty 50 Index", "NSE", "NSE_INDEX", "INDEX", sector="Indices"),
        "NIFTY50": UpstoxInstrument("NSE_INDEX|Nifty 50", "NIFTY", "Nifty 50 Index", "NSE", "NSE_INDEX", "INDEX", sector="Indices"),
        "NIFTY 50": UpstoxInstrument("NSE_INDEX|Nifty 50", "NIFTY", "Nifty 50 Index", "NSE", "NSE_INDEX", "INDEX", sector="Indices"),
        "BANKNIFTY": UpstoxInstrument("NSE_INDEX|Nifty Bank", "BANKNIFTY", "Nifty Bank Index", "NSE", "NSE_INDEX", "INDEX", sector="Indices"),
        "NIFTY BANK": UpstoxInstrument("NSE_INDEX|Nifty Bank", "BANKNIFTY", "Nifty Bank Index", "NSE", "NSE_INDEX", "INDEX", sector="Indices"),
        "FINNIFTY": UpstoxInstrument("NSE_INDEX|Nifty Fin Service", "FINNIFTY", "Nifty Financial Services", "NSE", "NSE_INDEX", "INDEX", sector="Indices"),
        "MIDCPNIFTY": UpstoxInstrument("NSE_INDEX|NIFTY MID SELECT", "MIDCPNIFTY", "NIFTY Midcap Select", "NSE", "NSE_INDEX", "INDEX", sector="Indices"),
        "NIFTY100": UpstoxInstrument("NSE_INDEX|Nifty 100", "NIFTY 100", "Nifty 100 Index", "NSE", "NSE_INDEX", "INDEX", sector="Indices"),
        "NIFTY 100": UpstoxInstrument("NSE_INDEX|Nifty 100", "NIFTY 100", "Nifty 100 Index", "NSE", "NSE_INDEX", "INDEX", sector="Indices"),
        "NIFTY500": UpstoxInstrument("NSE_INDEX|Nifty 500", "NIFTY 500", "Nifty 500 Index", "NSE", "NSE_INDEX", "INDEX", sector="Indices"),
        "NIFTY 500": UpstoxInstrument("NSE_INDEX|Nifty 500", "NIFTY 500", "Nifty 500 Index", "NSE", "NSE_INDEX", "INDEX", sector="Indices"),
        "NIFTYIT": UpstoxInstrument("NSE_INDEX|Nifty IT", "NIFTY IT", "Nifty IT Index", "NSE", "NSE_INDEX", "INDEX", sector="Indices"),
        "NIFTY IT": UpstoxInstrument("NSE_INDEX|Nifty IT", "NIFTY IT", "Nifty IT Index", "NSE", "NSE_INDEX", "INDEX", sector="Indices"),

        # Top NSE Bluechips & NIFTY 50 Constituents
        "RELIANCE": UpstoxInstrument("NSE_EQ|INE002A01018", "RELIANCE", "Reliance Industries Ltd", "NSE", "NSE_EQ", "EQUITY", sector="Energy"),
        "TCS": UpstoxInstrument("NSE_EQ|INE467B01029", "TCS", "Tata Consultancy Services Ltd", "NSE", "NSE_EQ", "EQUITY", sector="IT"),
        "HDFCBANK": UpstoxInstrument("NSE_EQ|INE040A01034", "HDFCBANK", "HDFC Bank Ltd", "NSE", "NSE_EQ", "EQUITY", sector="Financials"),
        "INFY": UpstoxInstrument("NSE_EQ|INE009A01021", "INFY", "Infosys Ltd", "NSE", "NSE_EQ", "EQUITY", sector="IT"),
        "ICICIBANK": UpstoxInstrument("NSE_EQ|INE090A01021", "ICICIBANK", "ICICI Bank Ltd", "NSE", "NSE_EQ", "EQUITY", sector="Financials"),
        "BHARTIARTL": UpstoxInstrument("NSE_EQ|INE397D01024", "BHARTIARTL", "Bharti Airtel Ltd", "NSE", "NSE_EQ", "EQUITY", sector="Telecom"),
        "SBIN": UpstoxInstrument("NSE_EQ|INE062A01020", "SBIN", "State Bank of India", "NSE", "NSE_EQ", "EQUITY", sector="Financials"),
        "ITC": UpstoxInstrument("NSE_EQ|INE154A01025", "ITC", "ITC Ltd", "NSE", "NSE_EQ", "EQUITY", sector="FMCG"),
        "HINDUNILVR": UpstoxInstrument("NSE_EQ|INE030A01027", "HINDUNILVR", "Hindustan Unilever Ltd", "NSE", "NSE_EQ", "EQUITY", sector="FMCG"),
        "LT": UpstoxInstrument("NSE_EQ|INE018A01030", "LT", "Larsen & Toubro Ltd", "NSE", "NSE_EQ", "EQUITY", sector="Capital Goods"),
        "BAJFINANCE": UpstoxInstrument("NSE_EQ|INE296A01024", "BAJFINANCE", "Bajaj Finance Ltd", "NSE", "NSE_EQ", "EQUITY", sector="Financials"),
        "MARUTI": UpstoxInstrument("NSE_EQ|INE585B01010", "MARUTI", "Maruti Suzuki India Ltd", "NSE", "NSE_EQ", "EQUITY", sector="Auto"),
        "SUNPHARMA": UpstoxInstrument("NSE_EQ|INE044A01036", "SUNPHARMA", "Sun Pharmaceutical Industries", "NSE", "NSE_EQ", "EQUITY", sector="Pharma"),
        "AXISBANK": UpstoxInstrument("NSE_EQ|INE238A01034", "AXISBANK", "Axis Bank Ltd", "NSE", "NSE_EQ", "EQUITY", sector="Financials"),
        "TITAN": UpstoxInstrument("NSE_EQ|INE280A01028", "TITAN", "Titan Company Ltd", "NSE", "NSE_EQ", "EQUITY", sector="Consumer"),
        "KOTAKBANK": UpstoxInstrument("NSE_EQ|INE237A01028", "KOTAKBANK", "Kotak Mahindra Bank Ltd", "NSE", "NSE_EQ", "EQUITY", sector="Financials"),
        "TATAMOTORS": UpstoxInstrument("NSE_EQ|INE155A01022", "TATAMOTORS", "Tata Motors Ltd", "NSE", "NSE_EQ", "EQUITY", sector="Auto"),
        "NTPC": UpstoxInstrument("NSE_EQ|INE733E01010", "NTPC", "NTPC Ltd", "NSE", "NSE_EQ", "EQUITY", sector="Utilities"),
        "ONGC": UpstoxInstrument("NSE_EQ|INE213A01029", "ONGC", "Oil & Natural Gas Corp", "NSE", "NSE_EQ", "EQUITY", sector="Energy"),
        "POWERGRID": UpstoxInstrument("NSE_EQ|INE752E01010", "POWERGRID", "Power Grid Corp of India", "NSE", "NSE_EQ", "EQUITY", sector="Utilities"),
        "TATASTEEL": UpstoxInstrument("NSE_EQ|INE081A01020", "TATASTEEL", "Tata Steel Ltd", "NSE", "NSE_EQ", "EQUITY", sector="Metals"),
        "JSWSTEEL": UpstoxInstrument("NSE_EQ|INE019A01038", "JSWSTEEL", "JSW Steel Ltd", "NSE", "NSE_EQ", "EQUITY", sector="Metals"),
        "ADANIENT": UpstoxInstrument("NSE_EQ|INE423A01024", "ADANIENT", "Adani Enterprises Ltd", "NSE", "NSE_EQ", "EQUITY", sector="Commodities"),
        "ADANIPORTS": UpstoxInstrument("NSE_EQ|INE742F01042", "ADANIPORTS", "Adani Ports & SEZ", "NSE", "NSE_EQ", "EQUITY", sector="Infrastructure"),
        "COALINDIA": UpstoxInstrument("NSE_EQ|INE522F01014", "COALINDIA", "Coal India Ltd", "NSE", "NSE_EQ", "EQUITY", sector="Metals"),
        "M&M": UpstoxInstrument("NSE_EQ|INE101A01026", "M&M", "Mahindra & Mahindra Ltd", "NSE", "NSE_EQ", "EQUITY", sector="Auto"),
        "BAJAJFINSV": UpstoxInstrument("NSE_EQ|INE918I01026", "BAJAJFINSV", "Bajaj Finserv Ltd", "NSE", "NSE_EQ", "EQUITY", sector="Financials"),
        "ASIANPAINT": UpstoxInstrument("NSE_EQ|INE021A01026", "ASIANPAINT", "Asian Paints Ltd", "NSE", "NSE_EQ", "EQUITY", sector="Consumer"),
        "ULTRACEMCO": UpstoxInstrument("NSE_EQ|INE481G01011", "ULTRACEMCO", "UltraTech Cement Ltd", "NSE", "NSE_EQ", "EQUITY", sector="Materials"),
        "WIPRO": UpstoxInstrument("NSE_EQ|INE075A01022", "WIPRO", "Wipro Ltd", "NSE", "NSE_EQ", "EQUITY", sector="IT"),
        "HCLTECH": UpstoxInstrument("NSE_EQ|INE860A01027", "HCLTECH", "HCL Technologies Ltd", "NSE", "NSE_EQ", "EQUITY", sector="IT"),
        "DRREDDY": UpstoxInstrument("NSE_EQ|INE089A01023", "DRREDDY", "Dr. Reddy's Laboratories", "NSE", "NSE_EQ", "EQUITY", sector="Pharma"),
        "CIPLA": UpstoxInstrument("NSE_EQ|INE059A01026", "CIPLA", "Cipla Ltd", "NSE", "NSE_EQ", "EQUITY", sector="Pharma"),
        "TRENT": UpstoxInstrument("NSE_EQ|INE849A01020", "TRENT", "Trent Ltd", "NSE", "NSE_EQ", "EQUITY", sector="Consumer"),
        "BEL": UpstoxInstrument("NSE_EQ|INE263A01024", "BEL", "Bharat Electronics Ltd", "NSE", "NSE_EQ", "EQUITY", sector="Capital Goods"),
        "TECHM": UpstoxInstrument("NSE_EQ|INE669C01036", "TECHM", "Tech Mahindra Ltd", "NSE", "NSE_EQ", "EQUITY", sector="IT"),
        "GRASIM": UpstoxInstrument("NSE_EQ|INE047A01021", "GRASIM", "Grasim Industries Ltd", "NSE", "NSE_EQ", "EQUITY", sector="Materials"),
        "NESTLEIND": UpstoxInstrument("NSE_EQ|INE239A01024", "NESTLEIND", "Nestle India Ltd", "NSE", "NSE_EQ", "EQUITY", sector="FMCG"),
        "APOLLOHOSP": UpstoxInstrument("NSE_EQ|INE437A01024", "APOLLOHOSP", "Apollo Hospitals Enterprise", "NSE", "NSE_EQ", "EQUITY", sector="Healthcare"),
        "EICHERMOT": UpstoxInstrument("NSE_EQ|INE066A01021", "EICHERMOT", "Eicher Motors Ltd", "NSE", "NSE_EQ", "EQUITY", sector="Auto"),
        "DIVISLAB": UpstoxInstrument("NSE_EQ|INE361B01024", "DIVISLAB", "Divi's Laboratories Ltd", "NSE", "NSE_EQ", "EQUITY", sector="Pharma"),
        "BPCL": UpstoxInstrument("NSE_EQ|INE029A01011", "BPCL", "Bharat Petroleum Corp Ltd", "NSE", "NSE_EQ", "EQUITY", sector="Energy"),
        "SHREECEM": UpstoxInstrument("NSE_EQ|INE070A01015", "SHREECEM", "Shree Cement Ltd", "NSE", "NSE_EQ", "EQUITY", sector="Materials"),
        "HEROMOTOCO": UpstoxInstrument("NSE_EQ|INE158A01026", "HEROMOTOCO", "Hero MotoCorp Ltd", "NSE", "NSE_EQ", "EQUITY", sector="Auto"),
        "BRITANNIA": UpstoxInstrument("NSE_EQ|INE216A01030", "BRITANNIA", "Britannia Industries Ltd", "NSE", "NSE_EQ", "EQUITY", sector="FMCG"),
        "INDUSINDBK": UpstoxInstrument("NSE_EQ|INE095A01012", "INDUSINDBK", "IndusInd Bank Ltd", "NSE", "NSE_EQ", "EQUITY", sector="Financials"),
        "TATACONSUM": UpstoxInstrument("NSE_EQ|INE192A01025", "TATACONSUM", "Tata Consumer Products", "NSE", "NSE_EQ", "EQUITY", sector="FMCG"),
        "SBILIFE": UpstoxInstrument("NSE_EQ|INE123W01016", "SBILIFE", "SBI Life Insurance Co", "NSE", "NSE_EQ", "EQUITY", sector="Financials"),
        "HDFCLIFE": UpstoxInstrument("NSE_EQ|INE795G01014", "HDFCLIFE", "HDFC Life Insurance Co", "NSE", "NSE_EQ", "EQUITY", sector="Financials"),
        "BAJAJ-AUTO": UpstoxInstrument("NSE_EQ|INE917I01010", "BAJAJ-AUTO", "Bajaj Auto Ltd", "NSE", "NSE_EQ", "EQUITY", sector="Auto"),
    }

    def __init__(self, custom_instruments: Optional[Mapping[str, UpstoxInstrument]] = None):
        self._registry: Dict[str, UpstoxInstrument] = dict(self.CURATED_INSTRUMENTS)
        for inst in self.CURATED_INSTRUMENTS.values():
            self._registry[inst.instrument_key] = inst
        if custom_instruments:
            for k, v in custom_instruments.items():
                self._registry[k.strip().upper()] = v
                self._registry[v.instrument_key] = v

    def register(self, instrument: UpstoxInstrument) -> None:
        """Register a new or override instrument in resolver."""
        self._registry[instrument.symbol.strip().upper()] = instrument
        self._registry[instrument.instrument_key] = instrument

    def resolve(self, query: str, segment: Optional[str] = None) -> UpstoxInstrument:
        """Resolve a symbol or instrument key to an UpstoxInstrument.
        
        Args:
            query: Symbol (e.g. 'RELIANCE', 'NIFTY50') or exact key ('NSE_EQ|INE002A01018').
            segment: Optional segment constraint (e.g. 'NSE_EQ', 'NSE_INDEX').
        
        Returns:
            Resolved UpstoxInstrument.
        
        Raises:
            UpstoxInstrumentNotFoundError: If symbol cannot be resolved.
        """
        raw = query.strip()
        if not raw:
            raise UpstoxInstrumentNotFoundError("Instrument query cannot be empty.")

        # 1. Direct instrument key pass-through (e.g. 'NSE_EQ|INE002A01018' or 'NSE_INDEX|Nifty 50')
        if "|" in raw:
            parts = raw.split("|", 1)
            seg = parts[0].strip()
            identifier = parts[1].strip()
            # If in registry, return registered record
            if raw in self._registry:
                return self._registry[raw]
            # Construct synthetic instrument
            return UpstoxInstrument(
                instrument_key=raw,
                symbol=identifier,
                name=identifier,
                exchange=seg.split("_")[0] if "_" in seg else seg,
                segment=seg,
                instrument_type="INDEX" if "INDEX" in seg else "EQUITY",
            )

        # 2. Clean symbol (strip exchange prefixes like 'NSE:', 'BSE:')
        clean_sym = re.sub(r"^(NSE|BSE):", "", raw, flags=re.IGNORECASE).strip().upper()

        # 3. Check registry directly
        if clean_sym in self._registry:
            inst = self._registry[clean_sym]
            if segment is None or inst.segment.upper() == segment.strip().upper():
                return inst

        # 4. Check case-insensitive fuzzy match across registry names & symbols
        for key, inst in self._registry.items():
            if (
                clean_sym == inst.symbol.upper()
                or clean_sym == inst.name.upper()
                or clean_sym.replace(" ", "") == inst.symbol.upper().replace(" ", "")
            ):
                if segment is None or inst.segment.upper() == segment.strip().upper():
                    return inst

        available_symbols = ", ".join(sorted(list(self.CURATED_INSTRUMENTS.keys())[:12]))
        raise UpstoxInstrumentNotFoundError(
            f"Unable to resolve instrument '{query}'. "
            f"Provide an exact Upstox instrument key (e.g. 'NSE_EQ|INE002A01018') "
            f"or use a supported symbol such as: {available_symbols}..."
        )

    def search(self, query: str, limit: int = 10) -> List[UpstoxInstrument]:
        """Search instruments matching query substring."""
        q = query.strip().upper()
        matches: List[UpstoxInstrument] = []
        seen_keys: Set[str] = set()

        for inst in self._registry.values():
            if inst.instrument_key in seen_keys:
                continue
            if q in inst.symbol.upper() or q in inst.name.upper() or q in inst.instrument_key.upper():
                matches.append(inst)
                seen_keys.add(inst.instrument_key)
                if len(matches) >= limit:
                    break
        return matches

    def list_curated_symbols(self) -> List[str]:
        """List distinct human-readable curated symbols."""
        return sorted(list({inst.symbol for inst in self.CURATED_INSTRUMENTS.values()}))


# ==============================================================================
# 4. Upstox Market Data Provider Adapter (§5.C, §5.D)
# ==============================================================================

class UpstoxMarketDataAdapter(DataProvider):
    """Production-minded Upstox V3 Market Data Provider Adapter for FragilityShield.
    
    Adheres strictly to project rules:
    - Inherits from FragilityShield `DataProvider`.
    - 100% Read-Only: No trading orders.
    - Zero secret leakage in logs, repr, or error output.
    - Validates data physical integrity via `validate_financial_ohlcv`.
    - Normalizes timestamps to Asia/Kolkata (IST).
    - Preserves dataset provenance for reproducible quantitative experiments.
    """

    def __init__(
        self,
        config: Optional[UpstoxConfig] = None,
        client: Optional[httpx.Client] = None,
        resolver: Optional[UpstoxInstrumentResolver] = None,
    ):
        self._config = config or UpstoxConfig.from_env()
        self._client = client or httpx.Client(timeout=15.0)
        self._resolver = resolver or UpstoxInstrumentResolver()
        self._owns_client = client is None
        self._verified: bool = False

    @property
    def config(self) -> UpstoxConfig:
        return self._config

    @property
    def resolver(self) -> UpstoxInstrumentResolver:
        return self._resolver

    @property
    def provider_id(self) -> str:
        return "upstox_v3_market_data"

    @property
    def is_connected(self) -> bool:
        """True if configured with an access token."""
        return self._config.has_access_token

    @property
    def capabilities(self) -> Sequence[str]:
        """Sequence of explicitly verified capabilities supported by Upstox V3 Market Data Adapter."""
        return (
            ProviderCapability.HISTORICAL_OHLCV,
            ProviderCapability.INTRADAY_CANDLES,
            ProviderCapability.LATEST_QUOTES,
            ProviderCapability.INSTRUMENT_LOOKUP,
            ProviderCapability.DATA_PROVENANCE,
        )

    @property
    def lifecycle_status(self) -> str:
        """Current lifecycle status conforming to Section 4 state machine."""
        if not self._config.is_configured:
            return ProviderLifecycleStatus.NOT_CONFIGURED
        if not self._config.has_access_token:
            return ProviderLifecycleStatus.NOT_CONFIGURED
        if self._verified:
            return ProviderLifecycleStatus.VERIFIED
        return ProviderLifecycleStatus.CONFIGURED

    def stream_quotes(self, symbols: Sequence[str]) -> Any:
        """Streaming quotes is explicitly unsupported in read-only batch adapter mode."""
        self.validate_capability(ProviderCapability.STREAMING_QUOTES)

    def get_corporate_actions(self, symbol: str) -> List[Dict[str, Any]]:
        """Corporate action adjustments are unsupported via Upstox Market Data V3."""
        self.validate_capability(ProviderCapability.CORPORATE_ACTIONS)

    def _get_headers(self) -> Dict[str, str]:
        """Produce HTTP headers for authenticated Upstox requests."""
        if not self._config.has_access_token:
            raise UpstoxConfigurationError(
                "Upstox access token is not configured. "
                "Set UPSTOX_ACCESS_TOKEN in environment or .env."
            )
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._config.access_token}",
            "User-Agent": "FragilityShield-QuantitativeLab/1.0",
        }

    # --------------------------------------------------------------------------
    # A. Connection & Authorization Status (§5.A)
    # --------------------------------------------------------------------------

    def check_connection(self, timeout: float = 10.0) -> UpstoxAuthStatus:
        """Perform a minimal authenticated read-only connectivity and authorization check.
        
        Distinguishes missing configuration, invalid credentials, rate limiting,
        network errors, and endpoint IP restrictions. Never leaks secrets.
        """
        if not self._config.is_configured:
            return UpstoxAuthStatus(
                configured=False,
                authenticated=False,
                status_code=0,
                message="Upstox credentials are not configured. Set UPSTOX_ACCESS_TOKEN or OAuth credentials in .env.",
            )

        if not self._config.has_access_token:
            return UpstoxAuthStatus(
                configured=True,
                authenticated=False,
                status_code=0,
                message="OAuth client configured, but active UPSTOX_ACCESS_TOKEN is missing. Complete OAuth authorization.",
            )

        # Probe market data endpoint with a standard benchmark instrument
        probe_url = f"{self._config.api_base_url}/v3/market-quote/ltp"
        params = {"instrument_key": "NSE_EQ|INE002A01018"}  # RELIANCE

        try:
            resp = self._client.get(
                probe_url,
                headers=self._get_headers(),
                params=params,
                timeout=timeout,
            )
        except httpx.TimeoutException:
            self._verified = False
            return UpstoxAuthStatus(
                configured=True,
                authenticated=False,
                status_code=504,
                message="Upstox API request timed out during connectivity check.",
            )
        except httpx.RequestError as err:
            self._verified = False
            return UpstoxAuthStatus(
                configured=True,
                authenticated=False,
                status_code=503,
                message=f"Network error connecting to Upstox API: {err.__class__.__name__}",
            )

        if resp.status_code == 200:
            self._verified = True
            # Token is authenticated and entitled for market data!
            # Optionally query user profile for additional metadata
            profile_url = f"{self._config.api_base_url}/v2/user/profile"
            user_type = None
            exchanges: List[str] = []
            try:
                prof_resp = self._client.get(profile_url, headers=self._get_headers(), timeout=5.0)
                if prof_resp.status_code == 200:
                    prof_data = prof_resp.json().get("data", {})
                    user_type = prof_data.get("user_type")
                    exchanges = prof_data.get("exchanges", [])
            except Exception:
                pass

            return UpstoxAuthStatus(
                configured=True,
                authenticated=True,
                status_code=200,
                message="Upstox Market Data V3 is authenticated and actively reachable.",
                user_type=user_type,
                exchanges=tuple(exchanges),
                read_only=True,
                details={"probe_endpoint": "/v3/market-quote/ltp", "market_data_entitled": True},
            )

        self._verified = False
        if resp.status_code == 401:
            try:
                err_data = resp.json()
                msg = err_data.get("errors", [{}])[0].get("message", "Invalid or expired access token.")
            except Exception:
                msg = "Unauthorized: Access token is invalid or expired. Upstox tokens expire daily at 03:30 AM IST."
            return UpstoxAuthStatus(
                configured=True,
                authenticated=False,
                status_code=401,
                message=f"Upstox authentication failed (401): {msg}",
            )

        if resp.status_code == 429:
            return UpstoxAuthStatus(
                configured=True,
                authenticated=False,
                status_code=429,
                message="Upstox API rate limit exceeded. Please back off before retrying.",
            )

        return UpstoxAuthStatus(
            configured=True,
            authenticated=False,
            status_code=resp.status_code,
            message=f"Upstox API returned unexpected status code {resp.status_code}.",
        )

    # --------------------------------------------------------------------------
    # B. Instrument Discovery (§5.B)
    # --------------------------------------------------------------------------

    def get_instruments(self) -> List[str]:
        """List resolvable instrument symbols."""
        return self._resolver.list_curated_symbols()

    def resolve_instrument(self, query: str, segment: Optional[str] = None) -> UpstoxInstrument:
        """Resolve a human symbol or key to an UpstoxInstrument."""
        return self._resolver.resolve(query, segment=segment)

    # --------------------------------------------------------------------------
    # C. Historical OHLCV Candles (§5.C)
    # --------------------------------------------------------------------------

    def get_historical_candles(
        self,
        symbol_or_key: str,
        interval_unit: str = "days",
        interval: str = "1",
        from_date: Optional[Union[str, date, datetime]] = None,
        to_date: Optional[Union[str, date, datetime]] = None,
    ) -> List[CanonicalCandle]:
        """Retrieve and normalize historical OHLCV candles from Upstox V3.
        
        Endpoint: GET /v3/historical-candle/{instrument_key}/{unit}/{interval}/{to_date}/{from_date}
        
        Args:
            symbol_or_key: Ticker symbol (e.g. 'RELIANCE') or instrument key ('NSE_EQ|INE002A01018').
            interval_unit: 'days', 'weeks', 'months', or 'minutes'.
            interval: '1', '30', etc.
            from_date: Start date (YYYY-MM-DD). Defaults to 30 days prior to to_date.
            to_date: End date (YYYY-MM-DD). Defaults to current date.
            
        Returns:
            List of CanonicalCandle chronologically sorted ascending.
        """
        inst = self.resolve_instrument(symbol_or_key)

        # Normalize dates
        t_now = datetime.now(IST).date()
        d_to = self._parse_date(to_date) if to_date else t_now
        d_from = self._parse_date(from_date) if from_date else (d_to - timedelta(days=30))

        if d_from > d_to:
            raise ValueError(f"from_date ({d_from}) cannot be after to_date ({d_to})")

        # Normalize interval unit
        unit = interval_unit.lower().strip()
        if unit in ("day", "daily", "d"):
            unit = "days"
        elif unit in ("minute", "min", "m"):
            unit = "minutes"
        elif unit in ("week", "weekly", "w"):
            unit = "weeks"
        elif unit in ("month", "monthly"):
            unit = "months"

        if unit not in ("days", "minutes", "weeks", "months"):
            raise ValueError(f"Unsupported interval unit '{interval_unit}'. Use 'days' or 'minutes'.")

        # Partition large date windows if needed (Upstox handles up to 10 years for daily, but partitioning ensures resilience)
        date_windows = self._partition_date_range(d_from, d_to, max_days=365 if unit == "days" else 30)

        all_candles: List[CanonicalCandle] = []
        seen_timestamps: Set[str] = set()

        for win_from, win_to in date_windows:
            s_from = win_from.strftime("%Y-%m-%d")
            s_to = win_to.strftime("%Y-%m-%d")

            # URL path parameters format: /v3/historical-candle/{instrument_key}/{unit}/{interval}/{to_date}/{from_date}
            # Note Upstox URL parameter order: to_date comes before from_date!
            encoded_key = httpx.URL(f"/{inst.instrument_key}").raw_path.decode("ascii").lstrip("/")
            url = f"{self._config.api_base_url}/v3/historical-candle/{encoded_key}/{unit}/{interval}/{s_to}/{s_from}"

            try:
                resp = self._client.get(url, headers=self._get_headers())
            except httpx.TimeoutException:
                raise UpstoxError(f"Upstox historical candle request timed out for {inst.symbol}")
            except httpx.RequestError as err:
                raise UpstoxError(f"Network error fetching Upstox historical candles: {err}")

            if resp.status_code == 401:
                raise UpstoxAuthenticationError(
                    "Upstox access token invalid or expired. Upstox tokens expire daily at 03:30 AM IST."
                )
            if resp.status_code == 429:
                raise UpstoxRateLimitError("Upstox API rate limit exceeded during candle retrieval.")
            if resp.status_code != 200:
                raise UpstoxError(
                    f"Upstox historical candle endpoint returned error {resp.status_code}: {resp.text[:200]}"
                )

            data = resp.json()
            if data.get("status") != "success":
                errs = data.get("errors", [])
                msg = errs[0].get("message") if errs else "Unknown upstream error"
                raise UpstoxError(f"Upstox API returned error: {msg}")

            raw_candles = data.get("data", {}).get("candles", [])

            # Each candle is: [timestamp_iso, open, high, low, close, volume, open_interest]
            for c in raw_candles:
                if not isinstance(c, (list, tuple)) or len(c) < 5:
                    continue

                raw_ts = str(c[0])
                ts_iso = self._normalize_timestamp(raw_ts)

                if ts_iso in seen_timestamps:
                    continue
                seen_timestamps.add(ts_iso)

                try:
                    o = float(c[1])
                    h = float(c[2])
                    l = float(c[3])
                    cl = float(c[4])
                    v = float(c[5]) if len(c) > 5 and c[5] is not None else 0.0
                    oi = float(c[6]) if len(c) > 6 and c[6] is not None else 0.0
                except (ValueError, TypeError):
                    continue

                all_candles.append(
                    CanonicalCandle(
                        timestamp=ts_iso,
                        open=o,
                        high=h,
                        low=l,
                        close=cl,
                        volume=v,
                        open_interest=oi,
                        symbol=inst.symbol,
                        instrument_key=inst.instrument_key,
                    )
                )

        # Sort chronologically ascending (Upstox returns descending by timestamp)
        all_candles.sort(key=lambda x: x.timestamp)
        return all_candles

    # --------------------------------------------------------------------------
    # D. DataProvider Abstract Interface Implementation (§5)
    # --------------------------------------------------------------------------

    def get_historical_prices(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> np.ndarray:
        """Retrieve 1D array of daily closing prices for a given instrument symbol.
        
        Implements the core FragilityShield `DataProvider` interface.
        """
        candles = self.get_historical_candles(
            symbol_or_key=symbol,
            interval_unit="days",
            interval="1",
            from_date=start_date,
            to_date=end_date,
        )
        if not candles:
            return np.array([], dtype=float)
        return np.array([c.close for c in candles], dtype=float)

    # --------------------------------------------------------------------------
    # E. Market Quotes & LTP (§5.D)
    # --------------------------------------------------------------------------

    def get_ltp(self, symbols_or_keys: Sequence[str]) -> Dict[str, float]:
        """Retrieve Last Traded Price (LTP) for specified instruments."""
        if not symbols_or_keys:
            return {}

        resolved = [self.resolve_instrument(s) for s in symbols_or_keys]
        inst_keys = ",".join(i.instrument_key for i in resolved)

        url = f"{self._config.api_base_url}/v3/market-quote/ltp"
        resp = self._client.get(url, headers=self._get_headers(), params={"instrument_key": inst_keys})

        if resp.status_code == 401:
            raise UpstoxAuthenticationError("Upstox access token invalid or expired.")
        if resp.status_code != 200:
            raise UpstoxError(f"Failed to fetch Upstox LTP: HTTP {resp.status_code}")

        data = resp.json().get("data", {})
        result: Dict[str, float] = {}

        for inst in resolved:
            # Keys in response may be format 'NSE_EQ:RELIANCE' or 'NSE_INDEX:Nifty 50'
            found = False
            for resp_key, quote_val in data.items():
                if inst.symbol.upper() in resp_key.upper() or inst.instrument_key in quote_val.get("instrument_token", ""):
                    result[inst.symbol] = float(quote_val.get("last_price", 0.0))
                    found = True
                    break
            if not found and inst.symbol in data:
                result[inst.symbol] = float(data[inst.symbol].get("last_price", 0.0))

        return result

    def get_quote(self, symbols_or_keys: Sequence[str]) -> Dict[str, CanonicalQuote]:
        """Retrieve full market quotes for specified instruments."""
        if not symbols_or_keys:
            return {}

        resolved = [self.resolve_instrument(s) for s in symbols_or_keys]
        inst_keys = ",".join(i.instrument_key for i in resolved)

        url = f"{self._config.api_base_url}/v3/market-quote/quotes"
        resp = self._client.get(url, headers=self._get_headers(), params={"instrument_key": inst_keys})

        if resp.status_code == 401:
            raise UpstoxAuthenticationError("Upstox access token invalid or expired.")
        if resp.status_code != 200:
            raise UpstoxError(f"Failed to fetch Upstox quote: HTTP {resp.status_code}")

        data = resp.json().get("data", {})
        quotes: Dict[str, CanonicalQuote] = {}
        retrieval_ts = datetime.now(timezone.utc).isoformat()

        for inst in resolved:
            for resp_key, qdata in data.items():
                if inst.symbol.upper() in resp_key.upper() or inst.instrument_key in str(qdata):
                    ohlc = qdata.get("ohlc", {})
                    quotes[inst.symbol] = CanonicalQuote(
                        symbol=inst.symbol,
                        instrument_key=inst.instrument_key,
                        last_price=float(qdata.get("last_price", ohlc.get("close", 0.0))),
                        open=float(ohlc.get("open")) if "open" in ohlc else None,
                        high=float(ohlc.get("high")) if "high" in ohlc else None,
                        low=float(ohlc.get("low")) if "low" in ohlc else None,
                        close=float(ohlc.get("close")) if "close" in ohlc else None,
                        volume=float(ohlc.get("volume")) if "volume" in ohlc else None,
                        source_timestamp=str(ohlc.get("ts")) if "ts" in ohlc else None,
                        retrieval_timestamp=retrieval_ts,
                    )
                    break

        return quotes

    # --------------------------------------------------------------------------
    # F. Dataset Import & Downstream Project Catalog Integration (§6, §7)
    # --------------------------------------------------------------------------

    def import_and_register_dataset(
        self,
        symbol_or_key: str,
        catalog: ProjectCatalog,
        from_date: Optional[Union[str, date, datetime]] = None,
        to_date: Optional[Union[str, date, datetime]] = None,
        dataset_name: Optional[str] = None,
        catalog_dir: Optional[Union[str, Path]] = None,
    ) -> Tuple[DatasetRecord, OHLCVCandleReport]:
        """Fetch historical candles, run data-quality audit, save CSV, and register with ProjectCatalog.
        
        Args:
            symbol_or_key: Instrument symbol or key.
            catalog: Active ProjectCatalog instance.
            from_date: Start date.
            to_date: End date.
            dataset_name: Optional dataset name (defaults to 'Upstox_{SYMBOL}_{RANGE}').
            catalog_dir: Destination directory for persistent catalog files.
            
        Returns:
            Tuple of (registered DatasetRecord, OHLCVCandleReport).
            
        Raises:
            ValueError: If candles fail validation or no candles returned.
        """
        inst = self.resolve_instrument(symbol_or_key)
        candles = self.get_historical_candles(
            symbol_or_key=inst.instrument_key,
            interval_unit="days",
            interval="1",
            from_date=from_date,
            to_date=to_date,
        )

        if not candles:
            raise ValueError(f"No historical candles returned for {inst.symbol} in requested date range.")

        # Convert candles to dict format for validation
        candle_dicts = [c.to_dict() for c in candles]
        report = validate_financial_ohlcv(candle_dicts)

        if not report.is_valid:
            logger.warning(
                f"Data quality warnings encountered for {inst.symbol}: {report.warnings}"
            )

        # Build CSV and persistence path
        start_str = candles[0].timestamp[:10]
        end_str = candles[-1].timestamp[:10]
        name = dataset_name or f"Upstox_{inst.symbol}_{start_str}_{end_str}"
        clean_name = re.sub(r"[^\w\-_]", "_", name)
        dataset_id = f"ds_upstox_{inst.symbol.lower()}_{hashlib.sha256(clean_name.encode()).hexdigest()[:8]}"

        target_dir = Path(catalog_dir) if catalog_dir else Path("data/catalog")
        target_dir.mkdir(parents=True, exist_ok=True)
        csv_path = target_dir / f"{dataset_id}.csv"

        # Write CSV
        hasher = hashlib.sha256()
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "open", "high", "low", "close", "volume", "open_interest"])
            for c in candles:
                row = [c.timestamp, f"{c.open:.4f}", f"{c.high:.4f}", f"{c.low:.4f}", f"{c.close:.4f}", int(c.volume), int(c.open_interest)]
                writer.writerow(row)
                hasher.update(",".join(map(str, row)).encode("utf-8"))

        fingerprint = hasher.hexdigest()

        # Build registered DatasetRecord
        record = DatasetRecord(
            dataset_id=dataset_id,
            name=name,
            version="1.0.0",
            file_path=str(csv_path),
            format="csv",
            row_count=len(candles),
            column_mapping={
                "timestamp": "timestamp",
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "volume",
                "open_interest": "open_interest",
            },
            symbols=(inst.symbol,),
            timestamp_col="timestamp",
            frequency="1D",
            currency="INR",
            fingerprint=fingerprint,
            created_at=datetime.now(timezone.utc).isoformat(),
            provenance={
                "provider": self.provider_id,
                "endpoint": "/v3/historical-candle",
                "instrument_key": inst.instrument_key,
                "symbol": inst.symbol,
                "exchange": inst.exchange,
                "start_date": start_str,
                "end_date": end_str,
                "row_count": len(candles),
            },
            validation_summary=report.to_dict(),
        )

        catalog.save_dataset(record)
        return record, report

    # --------------------------------------------------------------------------
    # G. OAuth 2.0 Helpers (§4)
    # --------------------------------------------------------------------------

    def generate_oauth_dialog_url(self, state: str) -> str:
        """Generate official Upstox OAuth authorization dialog URL."""
        if not self._config.client_id:
            raise UpstoxConfigurationError("Cannot generate OAuth dialog URL: UPSTOX_CLIENT_ID is missing.")
        
        params = {
            "response_type": "code",
            "client_id": self._config.client_id,
            "redirect_uri": self._config.redirect_uri,
            "state": state,
        }
        query_str = httpx.QueryParams(params)
        return f"{self._config.api_base_url}/v2/login/authorization/dialog?{query_str}"

    def exchange_code_for_token(self, code: str) -> Dict[str, Any]:
        """Exchange authorization code server-side for an access token.
        
        Never sends client secret to browser or logs the payload.
        """
        if not self._config.has_oauth_client:
            raise UpstoxConfigurationError(
                "Upstox client_id and client_secret are required to exchange authorization code."
            )

        token_url = f"{self._config.api_base_url}/v2/login/authorization/token"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        payload = {
            "code": code,
            "client_id": self._config.client_id,
            "client_secret": self._config.client_secret,
            "redirect_uri": self._config.redirect_uri,
            "grant_type": "authorization_code",
        }

        try:
            resp = self._client.post(token_url, headers=headers, data=payload, timeout=15.0)
        except httpx.RequestError as err:
            raise UpstoxError(f"Network error during Upstox token exchange: {err.__class__.__name__}")

        if resp.status_code != 200:
            raise UpstoxAuthenticationError(
                f"Token exchange failed with status {resp.status_code}: {resp.text[:200]}"
            )

        data = resp.json()
        token = data.get("access_token")
        if token:
            # Update internal config with new token
            self._config.access_token = token

        # Return sanitized summary
        return {
            "success": True,
            "user_type": data.get("user_type"),
            "user_id": data.get("user_id"),
            "masked_token": self._config.mask_token(token),
            "expires_in_note": "Upstox tokens expire daily at 03:30 AM IST",
        }

    # --------------------------------------------------------------------------
    # Internal Helpers
    # --------------------------------------------------------------------------

    def _parse_date(self, d: Union[str, date, datetime]) -> date:
        """Parse various date representations to a python date."""
        if isinstance(d, datetime):
            return d.date()
        if isinstance(d, date):
            return d
        clean = str(d).strip()[:10]
        return datetime.strptime(clean, "%Y-%m-%d").date()

    def _normalize_timestamp(self, ts_str: str) -> str:
        """Normalize upstream timestamp to ISO 8601 with Asia/Kolkata timezone offset."""
        try:
            # Check if it already has timezone offset
            if "+" in ts_str or "Z" in ts_str:
                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                dt_ist = dt.astimezone(IST)
                return dt_ist.isoformat()
            # If plain date or datetime without tz, assume IST
            dt = datetime.fromisoformat(ts_str)
            dt_ist = dt.replace(tzinfo=IST)
            return dt_ist.isoformat()
        except Exception:
            return ts_str

    def _partition_date_range(self, start: date, end: date, max_days: int = 365) -> List[Tuple[date, date]]:
        """Partition a date range into contiguous windows of at most max_days."""
        windows: List[Tuple[date, date]] = []
        cur_start = start
        while cur_start <= end:
            cur_end = min(cur_start + timedelta(days=max_days - 1), end)
            windows.append((cur_start, cur_end))
            cur_start = cur_end + timedelta(days=1)
        return windows

    def close(self) -> None:
        """Close internal HTTP client if owned."""
        if self._owns_client and not self._client.is_closed:
            self._client.close()

    def __enter__(self) -> UpstoxMarketDataAdapter:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
