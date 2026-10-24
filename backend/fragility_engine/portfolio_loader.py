"""Portfolio loader and export utilities for FragilityShield.

Provides robust, strict JSON and CSV parsing and CSV export for portfolio domain models.
Enforces all-or-nothing validation with actionable row-and-field error messages.
"""

from __future__ import annotations

import csv
import io
import json
import math
from pathlib import Path
from typing import Any, Dict, List, TextIO, Union

from fragility_engine.models import Holding, Portfolio


REQUIRED_CSV_COLUMNS = ("asset_id", "quantity", "price", "sector")


def load_portfolio_from_json(source: Union[str, Path, TextIO]) -> Portfolio:
    """Load and validate a Portfolio from a JSON file, path, or raw JSON string.

    Args:
        source: A file path (str or Path), open TextIO stream, or JSON string.

    Returns:
        A validated Portfolio instance.

    Raises:
        TypeError: If source type is unsupported.
        ValueError: If JSON is malformed, missing required fields, or contains invalid/contradictory data.
    """
    raw_text: str
    if isinstance(source, Path):
        raw_text = source.read_text(encoding="utf-8")
    elif isinstance(source, io.TextIOBase):
        raw_text = source.read()
    elif isinstance(source, str):
        # Check if it's a file path that exists
        try:
            p = Path(source)
            if p.is_file():
                raw_text = p.read_text(encoding="utf-8")
            else:
                raw_text = source
        except (OSError, ValueError):
            raw_text = source
    else:
        raise TypeError(f"source must be a str, Path, or TextIO stream; got {type(source)}")

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON: {exc.msg} (line {exc.lineno}, col {exc.colno})") from exc

    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be an object/dict; got {type(data).__name__}")

    for req_field in ("portfolio_id", "name", "currency", "holdings"):
        if req_field not in data:
            raise ValueError(f"JSON portfolio missing required field: {req_field!r}")

    holdings_raw = data.get("holdings")
    if not isinstance(holdings_raw, list):
        raise ValueError(f"'holdings' must be a list of objects; got {type(holdings_raw).__name__}")

    if len(holdings_raw) == 0:
        raise ValueError("Portfolio must contain at least one holding")

    holdings_list: List[Holding] = []
    seen_ids: set[str] = set()

    for idx, h_raw in enumerate(holdings_raw, start=1):
        if not isinstance(h_raw, dict):
            raise ValueError(f"Holding at index {idx} must be a dictionary; got {type(h_raw).__name__}")

        for h_field in ("asset_id", "quantity", "price"):
            if h_field not in h_raw:
                raise ValueError(f"Holding at index {idx} missing required field: {h_field!r}")

        asset_id = str(h_raw["asset_id"]).strip()
        if not asset_id:
            raise ValueError(f"Holding at index {idx}: asset_id cannot be empty")

        norm_id = asset_id.upper()
        if norm_id in seen_ids:
            raise ValueError(f"Holding at index {idx}: duplicate asset_id {asset_id!r}")
        seen_ids.add(norm_id)

        try:
            qty = float(h_raw["quantity"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Holding at index {idx} ({asset_id}): invalid quantity {h_raw['quantity']!r}") from exc

        if not math.isfinite(qty) or qty <= 0.0:
            raise ValueError(f"Holding at index {idx} ({asset_id}): quantity must be strictly positive and finite")

        try:
            price = float(h_raw["price"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Holding at index {idx} ({asset_id}): invalid price {h_raw['price']!r}") from exc

        if not math.isfinite(price) or price <= 0.0:
            raise ValueError(f"Holding at index {idx} ({asset_id}): price must be strictly positive and finite")

        # Guard against contradictory representations of holding value
        if "market_value" in h_raw and h_raw["market_value"] is not None:
            try:
                stated_mv = float(h_raw["market_value"])
                computed_mv = qty * price
                if not math.isclose(stated_mv, computed_mv, rel_tol=1e-5, abs_tol=1e-5):
                    raise ValueError(
                        f"Holding at index {idx} ({asset_id}): contradictory market_value stated ({stated_mv}) "
                        f"versus computed ({computed_mv})"
                    )
            except (TypeError, ValueError) as exc:
                if isinstance(exc, ValueError) and "contradictory" in str(exc):
                    raise
                raise ValueError(f"Holding at index {idx} ({asset_id}): invalid market_value {h_raw['market_value']!r}") from exc

        sector = h_raw.get("sector")
        if sector is not None:
            sector = str(sector).strip()
            if not sector:
                raise ValueError(f"Holding at index {idx} ({asset_id}): sector cannot be empty whitespace")

        holdings_list.append(
            Holding(
                asset_id=asset_id,
                quantity=qty,
                price=price,
                sector=sector,
                metadata=dict(h_raw.get("metadata", {})),
            )
        )

    metadata = dict(data.get("metadata", {}))
    # Preserve top-level disclaimer or target_value if provided
    if "disclaimer" in data and "disclaimer" not in metadata:
        metadata["disclaimer"] = data["disclaimer"]

    return Portfolio(
        portfolio_id=str(data["portfolio_id"]).strip(),
        name=str(data["name"]).strip(),
        currency=str(data["currency"]).strip().upper(),
        holdings=tuple(holdings_list),
        metadata=metadata,
    )


def load_portfolio_from_csv(
    source: Union[str, Path, TextIO],
    portfolio_id: str = "imported_portfolio",
    name: str = "Imported Portfolio",
    currency: str = "INR",
) -> Portfolio:
    """Load and validate a Portfolio from a CSV file, path, or raw CSV string.

    Expected CSV columns:
        asset_id,quantity,price,sector

    Args:
        source: File path, Path object, open TextIO stream, or raw CSV string.
        portfolio_id: Identifier to assign to the loaded portfolio.
        name: Name to assign to the loaded portfolio.
        currency: Three-letter currency code (defaults to 'INR').

    Returns:
        A validated Portfolio instance.

    Raises:
        ValueError: If CSV headers or rows fail strict validation.
    """
    raw_text: str
    if isinstance(source, Path):
        raw_text = source.read_text(encoding="utf-8")
    elif isinstance(source, io.TextIOBase):
        raw_text = source.read()
    elif isinstance(source, str):
        try:
            p = Path(source)
            if p.is_file():
                raw_text = p.read_text(encoding="utf-8")
            else:
                raw_text = source
        except (OSError, ValueError):
            raw_text = source
    else:
        raise TypeError(f"source must be a str, Path, or TextIO stream; got {type(source)}")

    reader = csv.reader(io.StringIO(raw_text.strip()))
    try:
        header_row = next(reader)
    except StopIteration as exc:
        raise ValueError("CSV is completely empty") from exc

    normalized_headers = [col.strip().lower() for col in header_row]
    col_map: Dict[str, int] = {}
    for req_col in REQUIRED_CSV_COLUMNS:
        if req_col not in normalized_headers:
            raise ValueError(
                f"CSV missing required column {req_col!r}; present columns: {header_row}"
            )
        col_map[req_col] = normalized_headers.index(req_col)

    holdings_list: List[Holding] = []
    seen_ids: set[str] = set()

    for row_num, row in enumerate(reader, start=2):  # Header is row 1, data starts row 2
        if not row or all(not cell.strip() for cell in row):
            continue  # Skip trailing empty lines

        max_idx = max(col_map.values())
        if len(row) <= max_idx:
            raise ValueError(
                f"Row {row_num}: incomplete row; expected at least {max_idx + 1} columns but got {len(row)}"
            )

        asset_id_raw = row[col_map["asset_id"]].strip()
        if not asset_id_raw:
            raise ValueError(f"Row {row_num}: 'asset_id' cannot be empty")

        norm_id = asset_id_raw.upper()
        if norm_id in seen_ids:
            raise ValueError(f"Row {row_num}: duplicate asset_id {asset_id_raw!r} already defined")
        seen_ids.add(norm_id)

        qty_str = row[col_map["quantity"]].strip()
        try:
            qty = float(qty_str)
        except ValueError as exc:
            raise ValueError(
                f"Row {row_num}: invalid numeric quantity {qty_str!r} for asset {asset_id_raw!r}"
            ) from exc

        if not math.isfinite(qty) or qty <= 0.0:
            raise ValueError(
                f"Row {row_num}: quantity must be strictly positive and finite; got {qty_str!r}"
            )

        price_str = row[col_map["price"]].strip()
        try:
            price = float(price_str)
        except ValueError as exc:
            raise ValueError(
                f"Row {row_num}: invalid numeric price {price_str!r} for asset {asset_id_raw!r}"
            ) from exc

        if not math.isfinite(price) or price <= 0.0:
            raise ValueError(
                f"Row {row_num}: price must be strictly positive and finite; got {price_str!r}"
            )

        sector_raw = row[col_map["sector"]].strip()
        if not sector_raw:
            raise ValueError(f"Row {row_num}: 'sector' cannot be empty for asset {asset_id_raw!r}")

        holdings_list.append(
            Holding(
                asset_id=asset_id_raw,
                quantity=qty,
                price=price,
                sector=sector_raw,
            )
        )

    if not holdings_list:
        raise ValueError("CSV contains no valid holding data rows")

    return Portfolio(
        portfolio_id=portfolio_id,
        name=name,
        currency=currency,
        holdings=tuple(holdings_list),
        metadata={"source": "csv_import"},
    )


def export_portfolio_to_csv(
    portfolio: Portfolio,
    target: Union[str, Path, TextIO, None] = None,
) -> str:
    """Export a Portfolio instance to standard CSV format.

    Column order:
        asset_id,quantity,price,sector

    Args:
        portfolio: The Portfolio instance to export.
        target: Optional file path, Path object, or open TextIO stream.
                If None, the CSV content is returned as a string.

    Returns:
        The generated CSV string.
    """
    if not isinstance(portfolio, Portfolio):
        raise TypeError(f"portfolio must be a Portfolio instance; got {type(portfolio)}")

    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(REQUIRED_CSV_COLUMNS)

    for h in portfolio.holdings:
        writer.writerow([
            h.asset_id,
            h.quantity,
            h.price,
            h.sector or "",
        ])

    csv_text = output.getvalue()

    if isinstance(target, Path):
        target.write_text(csv_text, encoding="utf-8")
    elif isinstance(target, io.TextIOBase):
        target.write(csv_text)
    elif isinstance(target, str):
        Path(target).write_text(csv_text, encoding="utf-8")

    return csv_text
