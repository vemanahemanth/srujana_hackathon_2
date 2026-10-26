"""FragilityShield — Command-Line Interface (CLI).

This module provides the command-line entrypoint for FragilityShield, invoking
the same domain engines via the SDK / core functions with JSON, table, and text outputs.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional, Sequence
import numpy as np

from fragility_engine.allocation import create_equal_weighted_portfolio
from fragility_engine.fragility import run_fragility_audit
from fragility_engine.market_data import calculate_indian_transaction_charges
from fragility_engine.models import Holding, Portfolio
from fragility_engine.plugins import get_global_registry
from fragility_engine.portfolio_loader import load_portfolio_from_csv, load_portfolio_from_json
from fragility_engine.risk import calculate_risk_report
from fragility_engine.scenarios import execute_scenario, list_preset_scenarios
from fragility_engine.sdk import Client
from fragility_engine.validation import run_portfolio_consistency_tests, run_reference_value_tests


def _parse_returns(returns_arg: str) -> List[float]:
    """Parse returns from a comma-separated string or a text file."""
    if os.path.isfile(returns_arg):
        with open(returns_arg, "r", encoding="utf-8") as f:
            content = f.read().strip()
    else:
        content = returns_arg.strip()

    items = [x.strip() for x in content.replace("\n", ",").split(",") if x.strip()]
    return [float(x) for x in items]


def _load_portfolio(path: str) -> Portfolio:
    """Load portfolio from CSV or JSON based on file extension."""
    if path.endswith(".csv"):
        return load_portfolio_from_csv(path)
    elif path.endswith(".json"):
        return load_portfolio_from_json(path)
    else:
        # Default try JSON then CSV
        try:
            return load_portfolio_from_json(path)
        except Exception:
            return load_portfolio_from_csv(path)


def handle_portfolio(args: argparse.Namespace) -> int:
    """Handle portfolio subcommands."""
    if args.action == "validate":
        port = _load_portfolio(args.filepath)
        print(f"Portfolio ID:       {port.portfolio_id}")
        print(f"Name:               {port.name}")
        print(f"Currency:           {port.currency}")
        print(f"Total Valuation:    {port.total_valuation():,.2f} {port.currency}")
        print(f"Invested Capital:   {port.invested_capital():,.2f} {port.currency}")
        print(f"Unrealized P&L:     {port.unrealized_pnl():,.2f} ({port.unrealized_pnl_pct():.2%})")
        print(f"Holdings Count:     {len(port.holdings)}")
        print("\nHoldings Breakdown:")
        for h in port.holdings:
            print(f"  - {h.asset_id:15s} | Qty: {h.quantity:8.2f} | Px: {h.price:8.2f} | MV: {h.market_value:10.2f} | Sector: {h.sector or 'N/A'}")
        return 0
    return 1


def handle_risk(args: argparse.Namespace) -> int:
    """Handle risk calculation command."""
    rets = _parse_returns(args.returns)
    rep = calculate_risk_report(rets, annualization_factor=args.annualization)
    print("=== FragilityShield Risk Report ===")
    print(f"Observations:          {len(rets)}")
    print(f"Annualized Volatility: {rep.volatility_annualized:.4f} ({rep.volatility_annualized:.2%})")
    print(f"Daily Volatility:      {rep.volatility_daily:.4f}")
    print(f"VaR (95%):             {rep.var_95:.4f} ({rep.var_95:.2%})")
    print(f"VaR (99%):             {rep.var_99:.4f} ({rep.var_99:.2%})")
    print(f"Expected Shortfall (95%): {rep.expected_shortfall_95:.4f}")
    print(f"Expected Shortfall (99%): {rep.expected_shortfall_99:.4f}")
    if rep.drawdown:
        print(f"Max Drawdown:          {rep.drawdown.max_drawdown:.2%}")
    return 0


def handle_scenario(args: argparse.Namespace) -> int:
    """Handle scenario commands."""
    if args.action == "list-presets":
        print("=== Standard Scenario Presets ===")
        for p in list_preset_scenarios():
            print(f"  [{p.scenario_id}] {p.name}: {p.description}")
        return 0
    elif args.action == "run":
        port = _load_portfolio(args.portfolio)
        presets = {p.scenario_id: p for p in list_preset_scenarios()}
        if args.preset not in presets:
            print(f"Error: Unknown preset '{args.preset}'. Available: {list(presets.keys())}", file=sys.stderr)
            return 1
        scen = presets[args.preset]
        res = execute_scenario(port, scen)
        print(f"=== Scenario Execution: {scen.name} ===")
        print(f"Baseline Value:    {res.baseline_value:,.2f}")
        print(f"Stressed Value:    {res.stressed_value:,.2f}")
        print(f"Absolute P&L:      {res.absolute_pnl:,.2f}")
        print(f"Percentage Change: {res.percentage_change:.2%}")
        return 0
    elif args.action == "reverse-stress":
        port = _load_portfolio(args.portfolio)
        target_loss = float(args.target_loss) if args.target_loss else 0.15
        shock_target = args.target_type or "market"
        target_id = args.target_id
        from fragility_engine.scenarios import run_reverse_stress_test
        res = run_reverse_stress_test(
            portfolio=port,
            target_loss_pct=target_loss,
            shock_target=shock_target,
            target_identifier=target_id,
        )
        print(f"=== Reverse Stress Test (Target Loss: {target_loss:.2%}) ===")
        print(f"Shock Target:        {res.shock_target} ({res.target_identifier or 'All Assets'})")
        print(f"Required Shock:      {res.required_shock_pct:.2%}")
        print(f"Feasible:            {res.feasible}")
        print(f"Baseline Valuation:  {res.baseline_portfolio_value:,.2f}")
        print(f"Stressed Valuation:  {res.stressed_portfolio_value:,.2f}")
        print(f"Realized Loss:       {res.realized_loss_amount:,.2f} ({res.realized_loss_pct:.2%})")
        print(f"Explanation:         {res.explanation}")
        return 0
    return 1


def handle_fragility(args: argparse.Namespace) -> int:
    """Handle fragility audit commands."""
    rets = _parse_returns(args.returns)
    audit = run_fragility_audit(rets, target_metric=args.target_metric, audit_id=args.audit_id)
    print("=== FragilityShield Assumption Audit Report ===")
    print(f"Audit ID:                  {audit.audit_id}")
    print(f"Target Metric:             {audit.target_metric}")
    print(f"Most Sensitive Assumption: {audit.sensitivity_ranking.most_sensitive_perturbation}")
    print(f"Max Absolute Shift:        {audit.sensitivity_ranking.max_absolute_change:.4f}")
    if audit.sensitivity_ranking.max_relative_change is not None:
        print(f"Max Relative Shift:        {audit.sensitivity_ranking.max_relative_change:.2%}")
    print("\nRanked Sensitivities:")
    for idx, imp in enumerate(audit.sensitivity_ranking.ranked_impacts, 1):
        rel_str = f"{imp.relative_change:.2%}" if imp.relative_change is not None else "N/A"
        print(f"  {idx}. {imp.perturbation_name:35s} | Δ: {imp.absolute_change:+8.4f} ({rel_str})")
    return 0


def handle_validation(args: argparse.Namespace) -> int:
    """Handle validation commands."""
    if args.action == "reference":
        rep = run_reference_value_tests()
        print(f"=== Reference Value Validation Suite (Status: {rep.status.value.upper()}) ===")
        print(f"Passed: {rep.passed_count} | Failed: {rep.failed_count} | Warnings: {rep.warning_count} | Skipped: {rep.skipped_count}")
        for r in rep.records:
            print(f"  [{r.status.value.upper():7s}] {r.test_name:30s} | {r.message}")
        return 0 if rep.passed else 1
    elif args.action == "portfolio":
        port = _load_portfolio(args.portfolio)
        rep = run_portfolio_consistency_tests(port)
        print(f"=== Portfolio Consistency Suite (Status: {rep.status.value.upper()}) ===")
        for r in rep.records:
            print(f"  [{r.status.value.upper():7s}] {r.test_name:30s} | {r.message}")
        return 0 if rep.passed else 1
    return 1


def handle_plugins(args: argparse.Namespace) -> int:
    """Handle plugin listing."""
    reg = get_global_registry()
    plugins = reg.list_plugins()
    print(f"=== Registered FragilityShield Plugins ({len(plugins)} total) ===")
    for p in plugins:
        print(f"  [{p.plugin_id}] {p.name} v{p.plugin_version} - {p.description}")
    return 0


def handle_charges(args: argparse.Namespace) -> int:
    """Handle Indian transaction charges calculation."""
    res = calculate_indian_transaction_charges(
        order_type=args.order_type,
        price=args.price,
        quantity=args.quantity,
    )
    print(f"=== Indian Statutory Transaction Charges ({args.order_type.upper()}) ===")
    print(f"Turnover:           {res['turnover']:,.2f}")
    print(f"STT:                {res['stt']:,.2f}")
    print(f"Brokerage:          {res['brokerage']:,.2f}")
    print(f"Exchange Charges:   {res['exchange_turnover_charges']:,.2f}")
    print(f"SEBI Turnover Fee:  {res['sebi_turnover_charges']:,.2f}")
    print(f"Stamp Duty:         {res['stamp_duty']:,.2f}")
    print(f"GST (18%):          {res['gst']:,.2f}")
    print(f"Total Charges:      {res['total_charges']:,.2f}")
    print(f"Effective BPS:      {res['effective_bps']:.2f} bps")
    return 0


def handle_project(args: argparse.Namespace) -> int:
    """Handle project management commands (§1)."""
    client = Client()
    if args.action == "create":
        proj = client.projects.create(
            project_id=args.id,
            name=args.name,
            description=args.description or "",
            objective=args.objective or "Quantitative model stress testing",
        )
        print(f"Project created successfully: {proj.project_id} - '{proj.name}'")
        return 0
    elif args.action == "list":
        projs = client.projects.list()
        print(f"=== Registered Projects ({len(projs)}) ===")
        for p in projs:
            print(f"  [{p.project_id}] {p.name} - Objective: {p.objective}")
        return 0
    return 1


def handle_dataset(args: argparse.Namespace) -> int:
    """Handle dataset validation and registration commands (§3)."""
    client = Client()
    if args.action == "validate":
        path = args.filepath
        if not os.path.isfile(path):
            print(f"Error: File not found '{path}'", file=sys.stderr)
            return 1
        with open(path, "r", encoding="utf-8") as f:
            lines = [l.strip() for l in f if l.strip()]
        if not lines:
            print("Error: Empty dataset file.", file=sys.stderr)
            return 1
        headers = [h.strip() for h in lines[0].split(",")]
        rows_cnt = len(lines) - 1
        print(f"=== Dataset Validation: {os.path.basename(path)} ===")
        print(f"Format:       CSV")
        print(f"Row count:    {rows_cnt}")
        print(f"Columns:      {', '.join(headers)}")
        ohlcv_cols = {"timestamp", "open", "high", "low", "close", "volume"}
        if ohlcv_cols.issubset({h.lower() for h in headers}):
            print("Profile:      Recognized financial OHLCV candlestick time series.")
        else:
            print("Profile:      Recognized general tabular dataset.")
        print("Status:       Validated successfully.")
        return 0
    elif args.action == "list":
        dsets = client.datasets.list()
        print(f"=== Registered Datasets ({len(dsets)}) ===")
        for d in dsets:
            print(f"  [{d.dataset_id}] {d.name} v{d.version} ({d.row_count} rows, {d.frequency})")
        return 0
    return 1


def handle_model(args: argparse.Namespace) -> int:
    """Handle model inspection and capability verification commands (§2, §4)."""
    client = Client()
    if args.action == "inspect":
        manifest = client.model_lab.get_manifest(args.model_id)
        if manifest is None:
            print(f"Model ID '{args.model_id}' not found in catalog.", file=sys.stderr)
            return 1
        cap_rep = client.model_lab.check_capabilities(manifest)
        print(f"=== Model Inspection: {manifest.name} ({manifest.model_id} v{manifest.version}) ===")
        print(f"Family:           {manifest.model_family.value}")
        print(f"Owner:            {manifest.owner}")
        print(f"Required Inputs:  {', '.join(manifest.required_inputs)}")
        print(f"Supported Labs:   {', '.join(manifest.supported_labs)}")
        print(f"Supported Tests:  {', '.join(manifest.supported_tests)}")
        print(f"Deterministic:    {manifest.is_deterministic}")
        print("\nCapability Evaluation:")
        for cap_name, item in cap_rep.capabilities.items():
            print(f"  - {cap_name:25s}: {item.status.value:25s} | {item.details}")
        return 0
    elif args.action == "list":
        models = client.model_lab.list_manifests()
        print(f"=== Registered Model Manifests ({len(models)}) ===")
        for m in models:
            print(f"  [{m.model_id}] {m.name} v{m.version} ({m.model_family.value})")
        return 0
    return 1


def handle_upstox(args: argparse.Namespace) -> int:
    """Handle Upstox market data subcommands."""
    from fragility_engine.upstox import UpstoxMarketDataAdapter
    from fragility_engine.projects import ProjectCatalog
    adapter = UpstoxMarketDataAdapter()

    if args.action == "status":
        status = adapter.check_connection()
        print(f"Configured:     {status.configured}")
        print(f"Authenticated:  {status.authenticated}")
        print(f"Status Code:    {status.status_code}")
        print(f"Message:        {status.message}")
        print(f"Read-Only:      {status.read_only}")
        return 0 if status.authenticated else 1

    elif args.action == "resolve":
        query = args.query
        if not query:
            print("Error: instrument symbol or key is required.", file=sys.stderr)
            return 1
        inst = adapter.resolve_instrument(query)
        print(f"Symbol:         {inst.symbol}")
        print(f"Instrument Key: {inst.instrument_key}")
        print(f"Name:           {inst.name}")
        print(f"Exchange:       {inst.exchange} ({inst.segment})")
        print(f"Type:           {inst.instrument_type}")
        return 0

    elif args.action == "quote":
        query = args.query
        if not query:
            print("Error: instrument symbol or key is required.", file=sys.stderr)
            return 1
        quotes = adapter.get_quote([query])
        if not quotes:
            print(f"No quote returned for {query}.", file=sys.stderr)
            return 1
        for sym, q in quotes.items():
            print(f"Symbol:         {sym}")
            print(f"Last Price:     {q.last_price}")
            print(f"Open:           {q.open}")
            print(f"High:           {q.high}")
            print(f"Low:            {q.low}")
            print(f"Close:          {q.close}")
            print(f"Volume:         {q.volume}")
        return 0

    elif args.action == "import":
        query = args.query
        if not query:
            print("Error: instrument symbol or key is required.", file=sys.stderr)
            return 1
        catalog = ProjectCatalog()
        rec, rep = adapter.import_and_register_dataset(
            symbol_or_key=query,
            catalog=catalog,
            from_date=args.from_date,
            to_date=args.to_date,
            dataset_name=args.name,
        )
        print(f"Dataset ID:     {rec.dataset_id}")
        print(f"Name:           {rec.name}")
        print(f"Rows:           {rec.row_count}")
        print(f"File Path:      {rec.file_path}")
        print(f"OHLCV Valid:    {rep.is_valid}")
        if rep.warnings:
            print(f"Warnings:       {rep.warnings}")
        return 0
    return 1


def create_parser() -> argparse.ArgumentParser:
    """Create CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="fragilityshield",
        description="FragilityShield — Quantitative Risk, Model Validation, and Fragility Testing Laboratory CLI.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. portfolio
    p_port = subparsers.add_parser("portfolio", help="Portfolio inspection and validation")
    p_port.add_argument("action", choices=["validate"])
    p_port.add_argument("filepath", help="Path to portfolio file (CSV or JSON)")

    # 2. risk
    p_risk = subparsers.add_parser("risk", help="Calculate portfolio or asset risk metrics")
    p_risk.add_argument("--returns", required=True, help="Comma-separated returns or path to returns file")
    p_risk.add_argument("--annualization", type=float, default=252.0, help="Annualization factor (default: 252)")

    # 3. scenario
    p_scen = subparsers.add_parser("scenario", help="Run scenario simulations and presets")
    p_scen.add_argument("action", choices=["list-presets", "run", "reverse-stress"])
    p_scen.add_argument("--portfolio", help="Path to portfolio file")
    p_scen.add_argument("--preset", help="Preset ID to execute")
    p_scen.add_argument("--target-loss", type=float, default=0.15, help="Target loss fraction for reverse stress (e.g. 0.15 for 15 percent)")
    p_scen.add_argument("--target-type", choices=["market", "sector", "asset"], default="market", help="Reverse stress target scope")
    p_scen.add_argument("--target-id", help="Sector name or Asset ID for targeted reverse stress")

    # 4. fragility
    p_frag = subparsers.add_parser("fragility", help="Run assumption perturbation audit")
    p_frag.add_argument("--returns", required=True, help="Comma-separated returns or path to returns file")
    p_frag.add_argument("--target-metric", default="volatility_annualized", help="Metric to rank sensitivities")
    p_frag.add_argument("--audit-id", default="audit_cli", help="Unique audit identifier")

    # 5. validation
    p_val = subparsers.add_parser("validation", help="Run analytical validation and consistency tests")
    p_val.add_argument("action", choices=["reference", "portfolio"])
    p_val.add_argument("--portfolio", help="Path to portfolio file (required for 'portfolio' action)")

    # 6. plugins
    p_plug = subparsers.add_parser("plugins", help="Inspect and list registered plugins")
    p_plug.add_argument("action", choices=["list"], default="list", nargs="?")

    # 7. charges
    p_chg = subparsers.add_parser("charges", help="Calculate Indian market statutory transaction charges")
    p_chg.add_argument("--order-type", required=True, choices=["delivery_equity", "intraday_equity", "futures", "options"])
    p_chg.add_argument("--price", type=float, required=True, help="Trade price")
    p_chg.add_argument("--quantity", type=float, required=True, help="Trade quantity")

    # 8. project (§1)
    p_proj = subparsers.add_parser("project", help="Manage high-level research project workspaces")
    p_proj.add_argument("action", choices=["create", "list"])
    p_proj.add_argument("--id", help="Project identifier")
    p_proj.add_argument("--name", help="Project display name")
    p_proj.add_argument("--description", help="Project description")
    p_proj.add_argument("--objective", help="Project research objective")

    # 9. dataset (§3)
    p_dset = subparsers.add_parser("dataset", help="Dataset verification, audit, and registration")
    p_dset.add_argument("action", choices=["validate", "list"])
    p_dset.add_argument("filepath", nargs="?", help="Path to dataset file to validate")

    # 10. model (§2, §4)
    p_mod = subparsers.add_parser("model", help="Model inspection, capabilities, and verification")
    p_mod.add_argument("action", choices=["inspect", "list"])
    p_mod.add_argument("model_id", nargs="?", help="Model identifier to inspect")

    # 11. upstox
    p_upx = subparsers.add_parser("upstox", help="Upstox Market Data V3 operations")
    p_upx.add_argument("action", choices=["status", "resolve", "quote", "import"])
    p_upx.add_argument("query", nargs="?", help="Symbol or instrument key (e.g. RELIANCE, NIFTY50)")
    p_upx.add_argument("--from-date", help="Start date (YYYY-MM-DD)")
    p_upx.add_argument("--to-date", help="End date (YYYY-MM-DD)")
    p_upx.add_argument("--name", help="Custom dataset name for catalog registration")

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI execution entrypoint."""
    parser = create_parser()
    args = parser.parse_args(argv)

    if args.command == "portfolio":
        return handle_portfolio(args)
    elif args.command == "risk":
        return handle_risk(args)
    elif args.command == "scenario":
        return handle_scenario(args)
    elif args.command == "fragility":
        return handle_fragility(args)
    elif args.command == "validation":
        return handle_validation(args)
    elif args.command == "plugins":
        return handle_plugins(args)
    elif args.command == "charges":
        return handle_charges(args)
    elif args.command == "project":
        return handle_project(args)
    elif args.command == "dataset":
        return handle_dataset(args)
    elif args.command == "model":
        return handle_model(args)
    elif args.command == "upstox":
        return handle_upstox(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())

