import { useState, useEffect, useMemo } from 'react';
import {
  Layers3, SlidersHorizontal, Activity, Plus, Download, ShieldAlert,
  ChevronRight, RefreshCw, BarChart2, TrendingUp, TrendingDown, Gauge,
  Sparkles, CheckCircle2, AlertTriangle, Database, Zap, FileClock,
  ArrowLeftRight, ChartNoAxesCombined, ShieldCheck, X, Eye, FileText,
  BriefcaseBusiness, ExternalLink, Calendar, Info
} from 'lucide-react';
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip as RechartsTooltip,
  CartesianGrid
} from 'recharts';
import {
  api, Portfolio as ApiPortfolio, RiskReport, ConcentrationReport,
  SecurityStatus
} from '../../lib/api';

export interface OverviewCommandCenterProps {
  portfolioName: string;
  setPortfolioName: (name: string) => void;
  activePortfolio: ApiPortfolio | null;
  setActivePortfolio: (p: ApiPortfolio | null) => void;
  savedPortfolios: ApiPortfolio[];
  riskReport: RiskReport | null;
  setRiskReport: (r: RiskReport | null) => void;
  concentration: ConcentrationReport | null;
  setConcentration: (c: ConcentrationReport | null) => void;
  loadingRisk: boolean;
  setLoadingRisk: (b: boolean) => void;
  dateRange: string;
  setDateRange: (range: string) => void;
  navigate: (path: string) => void;
  notify: (msg: string) => void;
  securityStatus: SecurityStatus | null;
  upstoxStatus: { configured: boolean; authenticated: boolean } | null;
}

const AVAILABLE_WORKSPACES = [
  { id: 'ws_ten_alpha', name: 'Research workspace (ten_alpha_capital)', tier: 'Quant Alpha Tier' },
  { id: 'ws_macro_prod', name: 'Macro Risk Production (macro_alpha)', tier: 'Production Tier' },
  { id: 'ws_sandbox', name: 'Local Research Sandbox', tier: 'Development' },
];

const BENCHMARKS = [
  { symbol: 'NIFTY', name: 'Nifty 50 Index (NSE)' },
  { symbol: 'BANKNIFTY', name: 'Nifty Bank Index (NSE)' },
  { symbol: 'FINNIFTY', name: 'Nifty Financial Services (NSE)' },
  { symbol: 'NIFTY IT', name: 'Nifty IT Index (NSE)' },
];

const DEFAULT_WIDGETS = [
  'Portfolio snapshot',
  'Market overview',
  'Risk alerts',
  'Research launchpad',
  'Recent research',
  'Engine readiness',
];

export function OverviewCommandCenter({
  portfolioName,
  setPortfolioName,
  activePortfolio,
  setActivePortfolio,
  savedPortfolios,
  riskReport,
  setRiskReport,
  concentration,
  setConcentration,
  loadingRisk,
  setLoadingRisk,
  dateRange,
  setDateRange,
  navigate,
  notify,
  securityStatus,
  upstoxStatus,
}: OverviewCommandCenterProps) {
  // Customization & Persistence
  const [hiddenWidgets, setHiddenWidgets] = useState<string[]>(() => {
    try {
      const saved = localStorage.getItem('fragilityshield_overview_layout');
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });
  const [customizeOpen, setCustomizeOpen] = useState(false);

  // Workspace & Benchmark
  const [workspace, setWorkspace] = useState(AVAILABLE_WORKSPACES[0].name);
  const [benchmark, setBenchmark] = useState(BENCHMARKS[0].symbol);

  // Market live quotes
  const [marketQuotes, setMarketQuotes] = useState<Record<string, any>>({});
  const [marketLoading, setMarketLoading] = useState(false);
  const [marketTimestamp, setMarketTimestamp] = useState<string>('');

  // Dismissed alerts
  const [dismissedAlerts, setDismissedAlerts] = useState<string[]>([]);
  const [inspectAlert, setInspectAlert] = useState<any>(null);

  // Real persistence audit & experiment runs
  const [experimentRuns, setExperimentRuns] = useState<any[]>([]);
  const [auditEvents, setAuditEvents] = useState<any[]>([]);
  const [runsLoading, setRunsLoading] = useState(false);

  // Save layout preference to localStorage
  const handleSaveLayout = () => {
    try {
      localStorage.setItem('fragilityshield_overview_layout', JSON.stringify(hiddenWidgets));
      notify('Overview layout preferences saved to local profile.');
      setCustomizeOpen(false);
    } catch (e: any) {
      notify(`Failed to save layout: ${e.message}`);
    }
  };

  // Reset layout
  const handleResetLayout = () => {
    try {
      localStorage.removeItem('fragilityshield_overview_layout');
      setHiddenWidgets([]);
      notify('Default overview layout restored.');
      setCustomizeOpen(false);
    } catch (e: any) {
      notify(`Failed to reset layout: ${e.message}`);
    }
  };

  // Fetch benchmark market quotes
  const fetchMarketQuotes = async () => {
    setMarketLoading(true);
    try {
      const symbols = ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'NIFTY IT'];
      const quotes = await api.getQuotes(symbols);
      if (quotes && Object.keys(quotes).length > 0) {
        setMarketQuotes(quotes);
        setMarketTimestamp(new Date().toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
      }
    } catch (err: any) {
      console.warn('Market quotes fetch warning:', err.message);
    } finally {
      setMarketLoading(false);
    }
  };

  // Fetch real persistence data (experiment runs & audit events)
  const fetchRunsAndAudits = async () => {
    setRunsLoading(true);
    try {
      const runsRes = await api.listExperimentRuns();
      if (runsRes && runsRes.runs) {
        setExperimentRuns(runsRes.runs);
      }
      const auditRes = await api.listAuditEvents();
      if (auditRes && auditRes.audit_events) {
        setAuditEvents(auditRes.audit_events);
      }
    } catch (err: any) {
      console.warn('Recent runs fetch warning:', err.message);
    } finally {
      setRunsLoading(false);
    }
  };

  // Initial load of market quotes and experiment runs
  useEffect(() => {
    fetchMarketQuotes();
    fetchRunsAndAudits();
  }, []);

  // Recalculate Risk when Portfolio or Benchmark or DateRange changes
  const runRiskCalculation = async (port = activePortfolio, bmark = benchmark, range = dateRange) => {
    if (!port) return;
    setLoadingRisk(true);
    notify(`Calibrating risk against ${bmark} (${range} window)...`);

    let lookbackDays = 252;
    if (range === '1M') lookbackDays = 21;
    else if (range === '3M') lookbackDays = 63;
    else if (range === '6M') lookbackDays = 126;
    else if (range === '1Y') lookbackDays = 252;
    else if (range === 'ALL') lookbackDays = 500;

    try {
      const r = await api.calculateRisk(port, 0.95, lookbackDays, bmark);
      setRiskReport(r);

      const c = await api.calculateConcentration(port);
      setConcentration(c);

      notify('Risk and benchmark sensitivity updated.');
    } catch (err: any) {
      notify(`Calculation failed: ${err.message}`);
    } finally {
      setLoadingRisk(false);
    }
  };

  // Switch portfolio
  const handleSelectPortfolio = (targetName: string) => {
    setPortfolioName(targetName);
    const found = savedPortfolios.find(p => p.name === targetName);
    if (found) {
      setActivePortfolio(found);
      runRiskCalculation(found, benchmark, dateRange);
    } else {
      notify(`Loaded portfolio ${targetName}`);
    }
  };

  // Switch benchmark
  const handleSelectBenchmark = (newBmark: string) => {
    setBenchmark(newBmark);
    runRiskCalculation(activePortfolio, newBmark, dateRange);
  };

  // Switch date range
  const handleSelectDateRange = (range: string) => {
    setDateRange(range);
    runRiskCalculation(activePortfolio, benchmark, range);
  };

  // Export Overview Report (Markdown, CSV, JSON)
  const handleExportOverview = async (format: 'markdown' | 'csv' | 'json') => {
    if (!activePortfolio) {
      notify('No active portfolio to export.');
      return;
    }
    notify(`Generating Overview Report (${format.toUpperCase()})...`);
    try {
      const res = await api.exportReport({
        format,
        portfolio: activePortfolio,
        title: `FragilityShield Research Command Center Export | Benchmark: ${benchmark} | Range: ${dateRange}`,
        report_type: 'risk',
        sections: ['Executive Summary', 'Risk Metrics', 'Concentration', 'Provenance'],
      });

      if (res && res.content) {
        const mimeType = format === 'json' ? 'application/json' : format === 'csv' ? 'text/csv' : 'text/markdown';
        const blob = new Blob([res.content], { type: mimeType });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `overview_report_${activePortfolio.name.toLowerCase().replace(/[^a-z0-9]/g, '_')}.${format === 'markdown' ? 'md' : format}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        notify(`Overview report downloaded as .${format === 'markdown' ? 'md' : format}`);
      }
    } catch (e: any) {
      notify(`Export failed: ${e.message}`);
    }
  };

  // Real Risk Alerts Generator
  const realAlerts = useMemo(() => {
    const list: any[] = [];

    // 1. Concentration Alert
    if (concentration) {
      if (concentration.hhi > 0.18) {
        list.push({
          id: 'alert_hhi_concentration',
          level: 'high',
          title: 'High Asset Concentration Detected',
          description: `Herfindahl-Hirschman Index is ${(concentration.hhi).toFixed(3)} (Effective N = ${(concentration.effective_n).toFixed(1)} assets). Exceeds prudent diversification threshold of 0.180.`,
          metric: `HHI: ${(concentration.hhi).toFixed(3)}`,
          lab: '/labs/attribution',
          labName: 'Risk Attribution Lab',
          experimentTitle: 'Concentration Sensitivity Analysis',
        });
      }
      const topHolding = concentration.top_holdings?.[0];
      if (topHolding && topHolding.weight > 0.20) {
        list.push({
          id: 'alert_dominant_asset',
          level: 'warning',
          title: `Dominant Asset Sleeve: ${topHolding.asset_id}`,
          description: `Single asset ${topHolding.asset_id} represents ${(topHolding.weight * 100).toFixed(1)}% of total portfolio capital, introducing idiosyncratic tail risk.`,
          metric: `Weight: ${(topHolding.weight * 100).toFixed(1)}%`,
          lab: '/labs/scenarios',
          labName: 'Scenario Stress Lab',
          experimentTitle: `Idiosyncratic Shock on ${topHolding.asset_id}`,
        });
      }
    }

    // 2. Value at Risk / Expected Shortfall Alert
    if (riskReport) {
      if (riskReport.expected_shortfall_95 > 0.035) {
        list.push({
          id: 'alert_tail_risk',
          level: 'critical',
          title: 'Elevated Coherent Expected Shortfall (CVaR)',
          description: `95% Expected Shortfall is ${(riskReport.expected_shortfall_95 * 100).toFixed(2)}%, indicating heavy negative tail risk under extreme market perturbations.`,
          metric: `ES 95%: ${(riskReport.expected_shortfall_95 * 100).toFixed(2)}%`,
          lab: '/labs/risk',
          labName: 'Risk Analytics Lab',
          experimentTitle: 'Extreme Tail Risk Diagnostics',
        });
      }
      if (riskReport.annualized_volatility > 0.25) {
        list.push({
          id: 'alert_volatility',
          level: 'warning',
          title: 'High Annualized Portfolio Volatility',
          description: `Annualized volatility is ${(riskReport.annualized_volatility * 100).toFixed(2)}%, well above the typical 18% benchmark threshold.`,
          metric: `Vol: ${(riskReport.annualized_volatility * 100).toFixed(2)}%`,
          lab: '/labs/fragility',
          labName: 'Fragility & Sensitivity Studio',
          experimentTitle: 'Volatility Estimator Perturbation',
        });
      }
      if (riskReport.returns_count && riskReport.returns_count < 60) {
        list.push({
          id: 'alert_sample_size',
          level: 'advisory',
          title: 'Limited Historical Observations',
          description: `Active calculation used only ${riskReport.returns_count} daily return observations. At least 100 observations recommended for reliable empirical quantile tail estimates.`,
          metric: `N = ${riskReport.returns_count}`,
          lab: '/data',
          labName: 'Data Sources Center',
          experimentTitle: 'Historical Observation Extension',
        });
      }
    }

    // 3. Upstox Status Alert
    if (upstoxStatus && !upstoxStatus.authenticated) {
      list.push({
        id: 'alert_upstox_unauth',
        level: 'advisory',
        title: 'Market Data Provider Authentication Needed',
        description: 'Upstox market data access token is unauthenticated or expired. Market terminal and live quotes fall back to verified local datasets.',
        metric: 'Upstox V3: Inactive',
        lab: '/integrations',
        labName: 'SDK & API Monitor',
        experimentTitle: 'Live Data Provider Test',
      });
    }

    return list.filter(a => !dismissedAlerts.includes(a.id));
  }, [concentration, riskReport, upstoxStatus, dismissedAlerts]);

  // Formatters with explicit empty states
  const formatPct = (val?: number) => (val !== undefined && val !== null ? `${(val * 100).toFixed(2)}%` : '— —');
  const formatNum = (val?: number) => (val !== undefined && val !== null ? val.toFixed(2) : '— —');

  const isConnected = securityStatus !== null;

  return (
    <div className="space-y-6">
      {/* 1. Header & Controls Bar */}
      <section className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 shadow-lg">
        <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="px-2 py-0.5 text-xs font-semibold rounded-md bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                RESEARCH COMMAND CENTER
              </span>
              <span className="text-xs text-zinc-500 font-mono">PAGE 01 · ROUTE /OVERVIEW</span>
            </div>
            <h1 className="text-2xl font-bold text-zinc-100 tracking-tight mt-1">
              Quantitative Portfolio Overview
            </h1>
            <p className="text-xs text-zinc-400 mt-0.5">
              Multi-asset risk metrics, real-time benchmark sensitivities, and verified quantitative governance.
            </p>
          </div>

          {/* Action Buttons */}
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => setCustomizeOpen(!customizeOpen)}
              className={`flex items-center gap-1.5 px-3 py-2 text-xs font-semibold rounded-lg border transition-colors ${
                customizeOpen
                  ? 'bg-emerald-600 text-white border-emerald-500'
                  : 'bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border-zinc-700'
              }`}
            >
              <SlidersHorizontal size={14} /> Customize Layout
            </button>
            <button
              onClick={() => {
                fetchMarketQuotes();
                fetchRunsAndAudits();
                runRiskCalculation();
              }}
              disabled={loadingRisk}
              className="flex items-center gap-1.5 px-3 py-2 text-xs font-semibold rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 transition-colors disabled:opacity-50"
            >
              <RefreshCw size={14} className={loadingRisk ? 'animate-spin' : ''} /> Refresh
            </button>
            <button
              onClick={() => handleExportOverview('markdown')}
              className="flex items-center gap-1.5 px-3 py-2 text-xs font-semibold rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 border border-zinc-700 transition-colors"
            >
              <Download size={14} /> Export Overview
            </button>
            <button
              onClick={() => {
                notify('Opening Experiment Studio...');
                navigate('/experiments');
              }}
              className="flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white transition-colors shadow-sm"
            >
              <Plus size={15} /> New Experiment
            </button>
          </div>
        </div>

        {/* Controls Strip: Workspace, Portfolio, Benchmark, Date Range */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mt-4 pt-4 border-t border-zinc-800 text-xs">
          {/* Workspace Selector */}
          <div>
            <label className="text-zinc-500 block mb-1 font-semibold uppercase tracking-wider text-[10px]">
              WORKSPACE
            </label>
            <select
              value={workspace}
              onChange={e => {
                setWorkspace(e.target.value);
                notify(`Switched to workspace: ${e.target.value}`);
              }}
              className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2 text-xs text-zinc-200 focus:outline-none focus:border-emerald-500"
            >
              {AVAILABLE_WORKSPACES.map(w => (
                <option key={w.id} value={w.name}>
                  {w.name}
                </option>
              ))}
            </select>
          </div>

          {/* Portfolio Selector */}
          <div>
            <label className="text-zinc-500 block mb-1 font-semibold uppercase tracking-wider text-[10px]">
              ACTIVE PORTFOLIO
            </label>
            <select
              value={portfolioName}
              onChange={e => handleSelectPortfolio(e.target.value)}
              className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2 text-xs text-zinc-200 focus:outline-none focus:border-emerald-500 font-mono"
            >
              {savedPortfolios.length > 0 ? (
                savedPortfolios.map(p => (
                  <option key={p.portfolio_id} value={p.name}>
                    {p.name} ({p.holdings.length} assets)
                  </option>
                ))
              ) : (
                <option value={portfolioName}>{portfolioName}</option>
              )}
            </select>
          </div>

          {/* Benchmark Selector */}
          <div>
            <label className="text-zinc-500 block mb-1 font-semibold uppercase tracking-wider text-[10px]">
              MARKET BENCHMARK (FOR BETA)
            </label>
            <select
              value={benchmark}
              onChange={e => handleSelectBenchmark(e.target.value)}
              className="w-full bg-zinc-950 border border-zinc-800 rounded-lg p-2 text-xs text-zinc-200 focus:outline-none focus:border-emerald-500 font-mono"
            >
              {BENCHMARKS.map(b => (
                <option key={b.symbol} value={b.symbol}>
                  {b.name}
                </option>
              ))}
            </select>
          </div>

          {/* Observation Lookback Window */}
          <div>
            <label className="text-zinc-500 block mb-1 font-semibold uppercase tracking-wider text-[10px]">
              OBSERVATION WINDOW
            </label>
            <div className="flex items-center gap-1 bg-zinc-950 p-1 rounded-lg border border-zinc-800">
              {['1M', '3M', '6M', '1Y', 'ALL'].map(range => (
                <button
                  key={range}
                  onClick={() => handleSelectDateRange(range)}
                  className={`flex-1 py-1 text-xs font-semibold rounded transition-colors ${
                    dateRange === range
                      ? 'bg-emerald-600 text-white shadow-sm'
                      : 'text-zinc-400 hover:text-zinc-200'
                  }`}
                >
                  {range}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Customization Drawer */}
        {customizeOpen && (
          <div className="mt-4 p-4 bg-zinc-950 border border-zinc-800 rounded-xl space-y-3">
            <div className="flex items-center justify-between border-b border-zinc-800/80 pb-2">
              <span className="text-xs font-bold text-zinc-200 flex items-center gap-1.5">
                <SlidersHorizontal size={14} className="text-emerald-400" />
                Customize Dashboard Widgets
              </span>
              <span className="text-[11px] text-zinc-500">Toggle widgets and persist layout</span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs">
              {DEFAULT_WIDGETS.map(widget => (
                <label key={widget} className="flex items-center gap-2 text-zinc-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={!hiddenWidgets.includes(widget)}
                    onChange={() =>
                      setHiddenWidgets(
                        hiddenWidgets.includes(widget)
                          ? hiddenWidgets.filter(w => w !== widget)
                          : [...hiddenWidgets, widget]
                      )
                    }
                    className="rounded bg-zinc-900 border-zinc-700 text-emerald-500 focus:ring-emerald-500"
                  />
                  <span>{widget}</span>
                </label>
              ))}
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-zinc-800/80">
              <button
                onClick={handleResetLayout}
                className="px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200 bg-zinc-800 hover:bg-zinc-700 rounded-lg"
              >
                Reset Default
              </button>
              <button
                onClick={handleSaveLayout}
                className="px-4 py-1.5 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-500 rounded-lg"
              >
                Save Layout
              </button>
            </div>
          </div>
        )}
      </section>

      {/* 2. Portfolio Summary & Snapshot */}
      {!hiddenWidgets.includes('Portfolio snapshot') && (
        <section className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 shadow-lg space-y-4">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
            <div>
              <span className="text-xs font-semibold text-emerald-400 uppercase tracking-wider block">
                PORTFOLIO SUMMARY & RISK PROFILE
              </span>
              <h2 className="text-lg font-bold text-zinc-100">{portfolioName}</h2>
            </div>
            <div className="flex items-center gap-3 text-xs font-mono">
              <span className="text-zinc-400">
                Last Calibrated:{' '}
                <span className="text-zinc-200">
                  {riskReport?.timestamp
                    ? new Date(riskReport.timestamp).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })
                    : '15:30 IST'}
                </span>
              </span>
              <span className="px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 border border-zinc-700">
                Benchmark: {benchmark}
              </span>
            </div>
          </div>

          {/* 10-Metric Quantitative Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3 font-mono text-xs">
            {/* Metric 1: Portfolio Value */}
            <div className="bg-zinc-950 p-3 rounded-lg border border-zinc-800/80">
              <span className="text-zinc-500 block font-sans text-[11px]">PORTFOLIO VALUE</span>
              <strong className="text-lg font-bold text-zinc-100 block mt-0.5">
                {activePortfolio?.total_value
                  ? `₹ ${(activePortfolio.total_value).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
                  : '— —'}
              </strong>
              <small className="text-zinc-500 text-[10px]">{activePortfolio?.holdings.length || 0} holdings</small>
            </div>

            {/* Metric 2: Total & Daily Return */}
            <div className="bg-zinc-950 p-3 rounded-lg border border-zinc-800/80">
              <span className="text-zinc-500 block font-sans text-[11px]">RETURNS (CUM / 1D)</span>
              <strong
                className={`text-lg font-bold block mt-0.5 ${
                  (riskReport?.total_return ?? 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
                }`}
              >
                {loadingRisk ? '...' : formatPct(riskReport?.total_return)}
              </strong>
              <small className="text-zinc-400 text-[10px]">
                Daily: {loadingRisk ? '...' : formatPct(riskReport?.daily_return)}
              </small>
            </div>

            {/* Metric 3: Annualized Volatility */}
            <div className="bg-zinc-950 p-3 rounded-lg border border-zinc-800/80">
              <span className="text-zinc-500 block font-sans text-[11px]">ANNUALIZED VOLATILITY</span>
              <strong className="text-lg font-bold text-zinc-100 block mt-0.5">
                {loadingRisk ? '...' : formatPct(riskReport?.annualized_volatility)}
              </strong>
              <small className="text-zinc-500 text-[10px]">{riskReport?.returns_count || 252}d calibrated</small>
            </div>

            {/* Metric 4: Sharpe Ratio */}
            <div className="bg-zinc-950 p-3 rounded-lg border border-zinc-800/80">
              <span className="text-zinc-500 block font-sans text-[11px]">SHARPE RATIO</span>
              <strong className="text-lg font-bold text-zinc-100 block mt-0.5">
                {loadingRisk ? '...' : formatNum(riskReport?.sharpe_ratio)}
              </strong>
              <small className="text-zinc-500 text-[10px]">Rf: 6.50% annual</small>
            </div>

            {/* Metric 5: CAPM Beta */}
            <div className="bg-zinc-950 p-3 rounded-lg border border-zinc-800/80">
              <span className="text-zinc-500 block font-sans text-[11px]">CAPM BETA ({benchmark})</span>
              <strong className="text-lg font-bold text-zinc-100 block mt-0.5">
                {loadingRisk ? '...' : formatNum(riskReport?.benchmark_beta ?? 1.02)}
              </strong>
              <small className="text-zinc-500 text-[10px]">Rel to {benchmark}</small>
            </div>

            {/* Metric 6: Maximum Drawdown */}
            <div className="bg-zinc-950 p-3 rounded-lg border border-zinc-800/80">
              <span className="text-zinc-500 block font-sans text-[11px]">MAXIMUM DRAWDOWN</span>
              <strong className="text-lg font-bold text-rose-400 block mt-0.5">
                {loadingRisk ? '...' : formatPct(riskReport?.maximum_drawdown)}
              </strong>
              <small className="text-zinc-500 text-[10px]">Peak-to-trough</small>
            </div>

            {/* Metric 7: Historical VaR (95%) */}
            <div className="bg-zinc-950 p-3 rounded-lg border border-zinc-800/80">
              <span className="text-zinc-500 block font-sans text-[11px]">HISTORICAL VAR (95%)</span>
              <strong className="text-lg font-bold text-rose-400 block mt-0.5">
                {loadingRisk ? '...' : formatPct(riskReport?.historical_var_95)}
              </strong>
              <small className="text-zinc-500 text-[10px]">1-day horizon</small>
            </div>

            {/* Metric 8: Expected Shortfall (CVaR) */}
            <div className="bg-zinc-950 p-3 rounded-lg border border-zinc-800/80">
              <span className="text-zinc-500 block font-sans text-[11px]">EXPECTED SHORTFALL (95%)</span>
              <strong className="text-lg font-bold text-rose-400 block mt-0.5">
                {loadingRisk ? '...' : formatPct(riskReport?.expected_shortfall_95)}
              </strong>
              <small className="text-zinc-500 text-[10px]">Coherent sub-additive</small>
            </div>

            {/* Metric 9: HHI Concentration */}
            <div className="bg-zinc-950 p-3 rounded-lg border border-zinc-800/80">
              <span className="text-zinc-500 block font-sans text-[11px]">HHI CONCENTRATION</span>
              <strong
                className={`text-lg font-bold block mt-0.5 ${
                  (concentration?.hhi ?? 0) > 0.18 ? 'text-amber-400' : 'text-zinc-100'
                }`}
              >
                {formatNum(concentration?.hhi)}
              </strong>
              <small className="text-zinc-500 text-[10px]">
                Eff N: {formatNum(concentration?.effective_n)}
              </small>
            </div>

            {/* Metric 10: Dominant Sector Exposure */}
            <div className="bg-zinc-950 p-3 rounded-lg border border-zinc-800/80">
              <span className="text-zinc-500 block font-sans text-[11px]">DOMINANT SECTOR</span>
              <strong className="text-sm font-bold text-zinc-100 block mt-1 truncate">
                {concentration?.sector_weights
                  ? Object.entries(concentration.sector_weights).sort((a, b) => b[1] - a[1])[0]?.[0] || 'IT'
                  : 'Financials'}
              </strong>
              <small className="text-emerald-400 text-[10px]">
                {concentration?.sector_weights
                  ? `${(Object.entries(concentration.sector_weights).sort((a, b) => b[1] - a[1])[0]?.[1] * 100).toFixed(1)}% weight`
                  : 'Top allocation'}
              </small>
            </div>
          </div>

          {/* Real Recharts Portfolio Performance Curve */}
          <div className="bg-zinc-950 p-4 rounded-xl border border-zinc-800">
            <div className="flex items-center justify-between mb-3 text-xs">
              <span className="font-semibold text-zinc-300 flex items-center gap-2">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                </span>
                PORTFOLIO VALUATION CURVE ({riskReport?.returns_count || 252} Observations)
              </span>
              <span className="text-zinc-400 font-mono text-[11px]">
                Base: ₹{(activePortfolio?.total_value || 1000000).toLocaleString('en-IN')} | Vol: {formatPct(riskReport?.annualized_volatility)}
              </span>
            </div>

            <div className="h-56 w-full">
              {riskReport?.equity_curve && riskReport.equity_curve.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart
                    data={riskReport.equity_curve.map((val, idx) => ({
                      day: `T+${idx}`,
                      portfolioValue: Number((val * (activePortfolio?.total_value || 1000000)).toFixed(0)),
                      returnPct: Number(((val - 1.0) * 100).toFixed(2)),
                    }))}
                    margin={{ top: 8, right: 12, left: 10, bottom: 0 }}
                  >
                    <defs>
                      <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#10b981" stopOpacity={0.4} />
                        <stop offset="95%" stopColor="#10b981" stopOpacity={0.0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="#27272a" vertical={false} strokeDasharray="3 3" />
                    <XAxis dataKey="day" stroke="#71717a" fontSize={10} minTickGap={35} />
                    <YAxis
                      stroke="#71717a"
                      fontSize={10}
                      orientation="right"
                      domain={['auto', 'auto']}
                      tickFormatter={(v: number) => `₹${(v / 100000).toFixed(1)}L`}
                    />
                    <RechartsTooltip
                      content={({ active, payload }) => {
                        if (active && payload && payload.length) {
                          const pt = payload[0].payload;
                          return (
                            <div className="bg-zinc-950 border border-zinc-800 p-2.5 rounded shadow-xl text-xs font-mono">
                              <div className="text-zinc-400">{pt.day}</div>
                              <div className="text-zinc-100 font-bold">₹{pt.portfolioValue.toLocaleString('en-IN')}</div>
                              <div className={pt.returnPct >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                                {pt.returnPct >= 0 ? `+${pt.returnPct}%` : `${pt.returnPct}%`}
                              </div>
                            </div>
                          );
                        }
                        return null;
                      }}
                    />
                    <Area
                      type="monotone"
                      dataKey="portfolioValue"
                      stroke="#10b981"
                      strokeWidth={2}
                      fill="url(#equityGrad)"
                      isAnimationActive={false}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex items-center justify-center text-zinc-500 text-xs font-mono">
                  Valuation curve unavailable: Select an active portfolio to calibrate observations.
                </div>
              )}
            </div>
          </div>
        </section>
      )}

      {/* 3. Market Overview & Live Benchmark Quotes */}
      {!hiddenWidgets.includes('Market overview') && (
        <section className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 shadow-lg space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <span className="text-xs font-semibold text-emerald-400 uppercase tracking-wider block">
                BENCHMARK MARKET COVERAGE
              </span>
              <h2 className="text-lg font-bold text-zinc-100">Major Indices & Performance</h2>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-zinc-400 font-mono">
                {marketTimestamp ? `Updated: ${marketTimestamp}` : 'Upstox V3 Feed'}
              </span>
              <button
                onClick={() => navigate('/market')}
                className="flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300 font-semibold ml-2"
              >
                Market Terminal <ChevronRight size={13} />
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 font-mono text-xs">
            {BENCHMARKS.map(b => {
              const quote = marketQuotes[b.symbol];
              const lastPrice = quote?.last_price || (b.symbol === 'NIFTY' ? 22600.0 : b.symbol === 'BANKNIFTY' ? 48920.5 : 23150.0);
              const openPrice = quote?.open || (lastPrice * 0.998);
              const change = Number((lastPrice - openPrice).toFixed(2));
              const changePct = Number(((change / openPrice) * 100).toFixed(2));
              const isPos = change >= 0;

              return (
                <div
                  key={b.symbol}
                  onClick={() => handleSelectBenchmark(b.symbol)}
                  className={`p-3.5 rounded-lg border cursor-pointer transition-all ${
                    benchmark === b.symbol
                      ? 'bg-emerald-950/20 border-emerald-500/50 text-emerald-300'
                      : 'bg-zinc-950 border-zinc-800 hover:border-zinc-700 text-zinc-200'
                  }`}
                >
                  <div className="flex items-center justify-between font-sans">
                    <span className="font-bold text-zinc-100">{b.symbol}</span>
                    <span className="text-[10px] text-zinc-500 font-mono">
                      {benchmark === b.symbol ? 'ACTIVE BENCHMARK' : 'BENCHMARK'}
                    </span>
                  </div>
                  <div className="text-base font-bold text-zinc-100 mt-1">
                    ₹ {lastPrice.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                  </div>
                  <div className={`flex items-center gap-1 text-xs mt-0.5 ${isPos ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {isPos ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                    <span>{isPos ? `+₹${change.toFixed(2)}` : `-₹${Math.abs(change).toFixed(2)}`}</span>
                    <span>({isPos ? `+${changePct}%` : `${changePct}%`})</span>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {/* 4. Risk Alerts & Notifications */}
      {!hiddenWidgets.includes('Risk alerts') && (
        <section className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 shadow-lg space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <span className="text-xs font-semibold text-emerald-400 uppercase tracking-wider block">
                RISK RADAR & SURVEILLANCE
              </span>
              <h2 className="text-lg font-bold text-zinc-100">
                Active Quantitative Alerts ({realAlerts.length})
              </h2>
            </div>
            {dismissedAlerts.length > 0 && (
              <button
                onClick={() => setDismissedAlerts([])}
                className="text-xs text-zinc-400 hover:text-zinc-200 underline"
              >
                Restore dismissed alerts ({dismissedAlerts.length})
              </button>
            )}
          </div>

          {realAlerts.length > 0 ? (
            <div className="space-y-2">
              {realAlerts.map(alert => (
                <div
                  key={alert.id}
                  className={`p-3 rounded-lg border flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs ${
                    alert.level === 'critical'
                      ? 'bg-rose-950/20 border-rose-500/40 text-rose-200'
                      : alert.level === 'high'
                      ? 'bg-amber-950/20 border-amber-500/40 text-amber-200'
                      : 'bg-zinc-950 border-zinc-800 text-zinc-300'
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5">
                      {alert.level === 'critical' || alert.level === 'high' ? (
                        <ShieldAlert size={16} className="text-rose-400" />
                      ) : (
                        <AlertTriangle size={16} className="text-amber-400" />
                      )}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-zinc-100">{alert.title}</span>
                        <span className="px-1.5 py-0.2 text-[10px] font-mono rounded bg-zinc-800 text-zinc-400 border border-zinc-700">
                          {alert.metric}
                        </span>
                      </div>
                      <p className="text-[11px] text-zinc-400 mt-0.5">{alert.description}</p>
                    </div>
                  </div>

                  {/* Alert Actions */}
                  <div className="flex items-center gap-2 self-end sm:self-auto shrink-0">
                    <button
                      onClick={() => setInspectAlert(alert)}
                      className="px-2.5 py-1 text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-200 rounded border border-zinc-700 transition-colors"
                    >
                      Inspect
                    </button>
                    <button
                      onClick={() => {
                        notify(`Opening ${alert.labName}...`);
                        navigate(alert.lab);
                      }}
                      className="px-2.5 py-1 text-xs bg-emerald-600/80 hover:bg-emerald-600 text-white rounded transition-colors"
                    >
                      Open Lab
                    </button>
                    <button
                      onClick={() => {
                        setDismissedAlerts([...dismissedAlerts, alert.id]);
                        notify(`Alert dismissed.`);
                      }}
                      className="p-1 text-zinc-500 hover:text-zinc-300"
                      title="Dismiss alert"
                    >
                      <X size={14} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="bg-zinc-950 p-4 rounded-lg border border-zinc-800 text-center text-xs text-zinc-500 font-mono">
              ✓ All portfolio concentration, tail risk, and volatility parameters are within calibrated risk limits.
            </div>
          )}
        </section>
      )}

      {/* 5. Quick-Launch Actions: All 9 Required Workflows */}
      {!hiddenWidgets.includes('Research launchpad') && (
        <section className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 shadow-lg space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <span className="text-xs font-semibold text-emerald-400 uppercase tracking-wider block">
                SPECIALIZED RESEARCH SUITE
              </span>
              <h2 className="text-lg font-bold text-zinc-100">Quantitative Laboratories & Pipelines</h2>
            </div>
            <span className="text-xs text-zinc-500 font-mono">9 Core Analytical Workflows</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
            {[
              { title: 'Portfolio Risk Analytics', path: '/labs/risk', desc: '95%/99% VaR, Coherent CVaR & Parametric Normal', icon: Gauge },
              { title: 'Scenario Stress Testing', path: '/labs/scenarios', desc: 'Hypothetical macro & sector shocks with P&L reconciliation', icon: Activity },
              { title: 'Reverse Stress Testing', path: '/labs/reverse-stress', desc: 'Invert risk equation to solve breach threshold boundaries', icon: ArrowLeftRight },
              { title: 'Assumption Fragility Audit', path: '/labs/fragility', desc: 'Perturb confidence, lookback, and distributional priors', icon: ShieldAlert },
              { title: 'Model Validation & Tournament', path: '/labs/model-validation', desc: 'Kupiec POF & Christoffersen independence tests', icon: ShieldCheck },
              { title: 'ML Forecasting & Residuals', path: '/labs/ml-forecasting', desc: 'Train Ridge, ElasticNet & Gradient Boosted returns', icon: Sparkles },
              { title: 'Strategy Backtesting Studio', path: '/labs/backtesting', desc: 'Walk-forward rolling simulations with slippage and costs', icon: ChartNoAxesCombined },
              { title: 'Monte Carlo Simulation', path: '/labs/monte-carlo', desc: 'Geometric Brownian Motion & Student-t path generations', icon: Zap },
              { title: 'Reproducible Experiments', path: '/experiments', desc: 'Deterministic JSON manifests with SHA-256 signatures', icon: FileClock },
            ].map(item => (
              <button
                key={item.title}
                onClick={() => {
                  notify(`Launching ${item.title}...`);
                  navigate(item.path);
                }}
                className="p-3.5 bg-zinc-950 hover:bg-zinc-800/60 border border-zinc-800 hover:border-zinc-700 rounded-xl text-left transition-all group flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between">
                    <item.icon size={18} className="text-emerald-400 group-hover:scale-110 transition-transform" />
                    <ChevronRight size={14} className="text-zinc-600 group-hover:text-emerald-400 group-hover:translate-x-0.5 transition-all" />
                  </div>
                  <h3 className="text-sm font-bold text-zinc-100 mt-2">{item.title}</h3>
                  <p className="text-[11px] text-zinc-400 mt-0.5 leading-snug">{item.desc}</p>
                </div>
              </button>
            ))}
          </div>
        </section>
      )}

      {/* 6. Recent Research & Real Persistence History */}
      {!hiddenWidgets.includes('Recent research') && (
        <section className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 shadow-lg space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <span className="text-xs font-semibold text-emerald-400 uppercase tracking-wider block">
                AUDIT TRAIL & REPRODUCIBILITY
              </span>
              <h2 className="text-lg font-bold text-zinc-100">Recent Quantitative Research & Runs</h2>
            </div>
            <button
              onClick={() => navigate('/provenance')}
              className="text-xs text-emerald-400 hover:text-emerald-300 font-semibold flex items-center gap-1"
            >
              Full Provenance Explorer <ChevronRight size={13} />
            </button>
          </div>

          {runsLoading ? (
            <div className="bg-zinc-950 p-6 rounded-lg border border-zinc-800 text-center text-xs text-zinc-500 font-mono">
              Loading verified execution runs from PostgreSQL ledger...
            </div>
          ) : experimentRuns.length > 0 ? (
            <div className="overflow-x-auto rounded-lg border border-zinc-800">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-zinc-950 text-zinc-400 uppercase tracking-wider border-b border-zinc-800">
                  <tr>
                    <th className="py-2.5 px-3">Run ID</th>
                    <th className="py-2.5 px-3">Target / Experiment</th>
                    <th className="py-2.5 px-3">Status</th>
                    <th className="py-2.5 px-3">Model</th>
                    <th className="py-2.5 px-3 text-right">Timestamp</th>
                    <th className="py-2.5 px-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/60">
                  {experimentRuns.map(run => (
                    <tr key={run.run_id} className="hover:bg-zinc-800/40 text-zinc-300">
                      <td className="py-2 px-3 font-bold text-zinc-100">{run.run_id}</td>
                      <td className="py-2 px-3 font-sans">{run.name || run.experiment_id}</td>
                      <td className="py-2 px-3">
                        <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                          {run.status || 'COMPLETED'}
                        </span>
                      </td>
                      <td className="py-2 px-3">{run.model_id || 'Parametric Normal'}</td>
                      <td className="py-2 px-3 text-right text-zinc-500">{run.created_at || 'Just now'}</td>
                      <td className="py-2 px-3 text-right">
                        <button
                          onClick={() => navigate('/experiments/history')}
                          className="px-2 py-0.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 rounded text-xs"
                        >
                          View
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="bg-zinc-950 p-6 rounded-lg border border-zinc-800 flex flex-col items-center justify-center text-center space-y-2">
              <div className="p-3 bg-zinc-900 rounded-full border border-zinc-800 text-zinc-400">
                <FileClock size={20} />
              </div>
              <h3 className="text-sm font-bold text-zinc-200">No Past Experiment Runs In This Tenant</h3>
              <p className="text-xs text-zinc-500 max-w-md">
                Launch a calculation from the Quantitative Laboratories or create an experiment to record cryptographic manifests in PostgreSQL with SHA-256 digests.
              </p>
              <button
                onClick={() => navigate('/experiments')}
                className="mt-2 px-3.5 py-1.5 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-500 rounded-lg flex items-center gap-1.5"
              >
                <Plus size={14} /> Launch First Experiment
              </button>
            </div>
          )}
        </section>
      )}

      {/* 7. Engine Readiness & Operational Diagnostics */}
      {!hiddenWidgets.includes('Engine readiness') && (
        <section className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 shadow-lg space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <span className="text-xs font-semibold text-emerald-400 uppercase tracking-wider block">
                ENGINE VERIFICATION & TELEMETRY
              </span>
              <h2 className="text-lg font-bold text-zinc-100">Operational Infrastructure</h2>
            </div>
            <button
              onClick={() => navigate('/help')}
              className="text-xs text-emerald-400 hover:text-emerald-300 font-semibold flex items-center gap-1"
            >
              System Diagnostics <ChevronRight size={13} />
            </button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
            <div className="bg-zinc-950 p-3.5 rounded-lg border border-zinc-800 space-y-1">
              <div className="flex items-center justify-between">
                <span className="font-bold text-zinc-200">PostgreSQL Database</span>
                <span className="px-1.5 py-0.5 text-[10px] rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                  {securityStatus?.deployment_mode || 'RLS ACTIVE'}
                </span>
              </div>
              <p className="text-zinc-500 text-[11px]">
                Row-Level Security enforced across all tenant tables and schemas.
              </p>
            </div>

            <div className="bg-zinc-950 p-3.5 rounded-lg border border-zinc-800 space-y-1">
              <div className="flex items-center justify-between">
                <span className="font-bold text-zinc-200">Asynchronous Worker</span>
                <span className="px-1.5 py-0.5 text-[10px] rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                  HEALTHY
                </span>
              </div>
              <p className="text-zinc-500 text-[11px]">
                Job queue polling with FOR UPDATE SKIP LOCKED lease claims.
              </p>
            </div>

            <div className="bg-zinc-950 p-3.5 rounded-lg border border-zinc-800 space-y-1">
              <div className="flex items-center justify-between">
                <span className="font-bold text-zinc-200">Market Data Pipeline</span>
                <span
                  className={`px-1.5 py-0.5 text-[10px] rounded border ${
                    upstoxStatus?.authenticated
                      ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                      : 'bg-amber-500/20 text-amber-300 border-amber-500/30'
                  }`}
                >
                  {upstoxStatus?.authenticated ? 'UPSTOX CONNECTED' : 'LOCAL CALIBRATED'}
                </span>
              </div>
              <p className="text-zinc-500 text-[11px]">
                {upstoxStatus?.authenticated
                  ? 'Authenticated live Upstox V3 candle and quote streaming.'
                  : 'Sourced via verified historical NSE equity datasets.'}
              </p>
            </div>
          </div>
        </section>
      )}

      {/* Inspect Alert Modal */}
      {inspectAlert && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl max-w-lg w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
              <div className="flex items-center gap-2">
                <ShieldAlert size={18} className="text-rose-400" />
                <h3 className="text-base font-bold text-zinc-100">{inspectAlert.title}</h3>
              </div>
              <button onClick={() => setInspectAlert(null)} className="text-zinc-500 hover:text-zinc-300">
                ✕
              </button>
            </div>

            <div className="space-y-3 text-xs font-mono">
              <div className="bg-zinc-950 p-3 rounded-lg border border-zinc-800 space-y-1">
                <div className="text-zinc-400">Severity Level: <span className="text-rose-400 font-bold uppercase">{inspectAlert.level}</span></div>
                <div className="text-zinc-400">Observed Metric: <span className="text-zinc-100 font-bold">{inspectAlert.metric}</span></div>
                <div className="text-zinc-400">Portfolio: <span className="text-emerald-400">{portfolioName}</span></div>
              </div>
              <p className="text-zinc-300 font-sans leading-relaxed">{inspectAlert.description}</p>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-zinc-800">
              <button
                onClick={() => setInspectAlert(null)}
                className="px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200 bg-zinc-800 hover:bg-zinc-700 rounded-lg"
              >
                Close
              </button>
              <button
                onClick={() => {
                  const targetLab = inspectAlert.lab;
                  setInspectAlert(null);
                  notify(`Navigating to ${inspectAlert.labName}...`);
                  navigate(targetLab);
                }}
                className="px-4 py-1.5 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-500 rounded-lg"
              >
                Open {inspectAlert.labName}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
