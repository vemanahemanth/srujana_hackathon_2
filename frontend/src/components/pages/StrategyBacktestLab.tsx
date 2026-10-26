import React, { useState, useEffect, useMemo } from 'react';
import {
  BriefcaseBusiness, Play, RefreshCw, Download, ArrowUpRight, ArrowDownRight,
  ShieldCheck, AlertTriangle, Activity, Sliders, TrendingUp, Layers, CheckCircle,
  FileSpreadsheet, History, Info, ChevronRight, Lock, Zap, CheckCircle2,
  AlertOctagon, SlidersHorizontal, Scale, FileText, Copy, Save, Check
} from 'lucide-react';
import {
  ResponsiveContainer, LineChart, Line, AreaChart, Area, XAxis, YAxis,
  Tooltip, CartesianGrid, Legend, BarChart, Bar
} from 'recharts';
import { api } from '@/lib/api';

interface StrategyTemplate {
  template_id: string;
  name: string;
  description: string;
  category: string;
  default_params: Record<string, any>;
  required_inputs: string[];
  supported_assets: string[];
}

const SUPPORTED_SYMBOLS = [
  { symbol: 'RELIANCE', name: 'Reliance Industries Ltd.', exchange: 'NSE_EQ' },
  { symbol: 'NIFTY 50', name: 'Nifty 50 Index', exchange: 'NSE_INDEX' },
  { symbol: 'TCS', name: 'Tata Consultancy Services', exchange: 'NSE_EQ' },
  { symbol: 'INFY', name: 'Infosys Limited', exchange: 'NSE_EQ' },
];

export function StrategyBacktestLab({
  navigate,
  notify,
}: {
  navigate?: (path: string) => void;
  notify?: (msg: string) => void;
}) {
  const [templates, setTemplates] = useState<StrategyTemplate[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string>('ma_crossover');
  const [selectedSymbol, setSelectedSymbol] = useState<string>('RELIANCE');
  const [initialCapital, setInitialCapital] = useState<number>(1000000);
  const [feeBps, setFeeBps] = useState<number>(10);
  const [slippageBps, setSlippageBps] = useState<number>(5);
  const [trainRatio, setTrainRatio] = useState<number>(0.7);

  // Strategy specific parameters
  const [fastPeriod, setFastPeriod] = useState<number>(20);
  const [slowPeriod, setSlowPeriod] = useState<number>(50);
  const [rsiPeriod, setRsiPeriod] = useState<number>(14);
  const [rsiOversold, setRsiOversold] = useState<number>(30);
  const [rsiOverbought, setRsiOverbought] = useState<number>(70);
  const [bbPeriod, setBbPeriod] = useState<number>(20);
  const [bbStd, setBbStd] = useState<number>(2.0);
  const [targetVol, setTargetVol] = useState<number>(0.15);
  const [stopLossPct, setStopLossPct] = useState<number>(3.5);

  const [loading, setLoading] = useState<boolean>(false);
  const [runningBacktest, setRunningBacktest] = useState<boolean>(false);
  const [backtestResult, setBacktestResult] = useState<any | null>(null);
  const [recentRuns, setRecentRuns] = useState<any[]>([]);
  const [activeTab, setActiveTab] = useState<'workspace' | 'history'>('workspace');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Page 16 Extended States: Validation, Ablation, Anti-bias, Configs
  const [validationResult, setValidationResult] = useState<any | null>(null);
  const [validating, setValidating] = useState<boolean>(false);
  const [ablationResult, setAblationResult] = useState<any | null>(null);
  const [runningAblation, setRunningAblation] = useState<boolean>(false);
  const [numTopTrades, setNumTopTrades] = useState<number>(2);
  const [activeSubTab, setActiveSubTab] = useState<
    'overview' | 'antibias' | 'rolling' | 'ablation' | 'walkforward' | 'trades'
  >('overview');

  // Build unified config object
  const buildCurrentConfig = () => {
    const selectedTmpl = templates.find((t) => t.template_id === selectedTemplateId);
    const cfg: Record<string, any> = {
      strategy_id: selectedTemplateId,
      name: selectedTmpl ? selectedTmpl.name : 'Custom Quantitative Strategy',
      strategy_type: selectedTemplateId,
      symbol: selectedSymbol,
      initial_capital: Number(initialCapital),
      train_ratio: Number(trainRatio),
      fee_bps: Number(feeBps),
      slippage_bps: Number(slippageBps),
      transaction_cost_bps: Number(feeBps),
      execution_delay_bars: 1,
      stop_loss_pct: stopLossPct ? Number(stopLossPct) / 100 : undefined,
    };

    if (selectedTemplateId === 'ma_crossover') {
      cfg.fast_period = Number(fastPeriod);
      cfg.slow_period = Number(slowPeriod);
    } else if (selectedTemplateId === 'rsi_momentum') {
      cfg.rsi_period = Number(rsiPeriod);
      cfg.rsi_oversold = Number(rsiOversold);
      cfg.rsi_overbought = Number(rsiOverbought);
    } else if (selectedTemplateId === 'bollinger_reversion') {
      cfg.bb_period = Number(bbPeriod);
      cfg.bb_std = Number(bbStd);
    } else if (selectedTemplateId === 'vol_target') {
      cfg.target_vol = Number(targetVol);
    }
    return cfg;
  };

  // 1. Load Strategy Templates & Recent Runs
  useEffect(() => {
    async function init() {
      setLoading(true);
      try {
        const tmplRes = await api.listStrategyTemplates();
        let allTemplates: StrategyTemplate[] = tmplRes?.templates || [];

        try {
          const customRes = await api.listCustomStrategies();
          const customList = Array.isArray(customRes) ? customRes : (customRes?.strategies || []);
          if (customList.length > 0) {
            const mappedCustom: StrategyTemplate[] = customList.map((c: any) => ({
              template_id: c.id || c.strategy_id || `strat_custom_${Date.now()}`,
              name: `${c.name || 'Custom Strategy'} (User Strategy)`,
              description: c.description || 'User-defined registered strategy',
              category: c.family || 'Custom',
              default_params: c.defaultParams || c.default_params || {},
              required_inputs: ['OHLCV'],
              supported_assets: ['ALL'],
            }));
            const seen = new Set(allTemplates.map((t) => t.template_id));
            for (const mc of mappedCustom) {
              if (!seen.has(mc.template_id)) {
                seen.add(mc.template_id);
                allTemplates.push(mc);
              }
            }
          }
        } catch (e) {
          // Custom strategy loading fallback
        }

        if (allTemplates.length > 0) {
          setTemplates(allTemplates);
          const first = allTemplates[0];
          setSelectedTemplateId(first.template_id);
          applyTemplateDefaults(first);
        }
        const runsRes = await api.listStrategyRuns();
        if (runsRes?.runs) {
          setRecentRuns(runsRes.runs);
        }
      } catch (err: any) {
        console.error('Failed to load strategy templates:', err);
        setErrorMsg(`Failed to initialize strategy catalog: ${err.message}`);
      } finally {
        setLoading(false);
      }
    }
    init();
  }, []);

  const applyTemplateDefaults = (tmpl: StrategyTemplate) => {
    const p = tmpl.default_params || {};
    if (p.fast_period !== undefined) setFastPeriod(p.fast_period);
    if (p.slow_period !== undefined) setSlowPeriod(p.slow_period);
    if (p.rsi_period !== undefined) setRsiPeriod(p.rsi_period);
    if (p.rsi_oversold !== undefined) setRsiOversold(p.rsi_oversold);
    if (p.rsi_overbought !== undefined) setRsiOverbought(p.rsi_overbought);
    if (p.bb_period !== undefined) setBbPeriod(p.bb_period);
    if (p.bb_std !== undefined) setBbStd(p.bb_std);
    if (p.target_vol !== undefined) setTargetVol(p.target_vol);
    if (p.stop_loss_pct !== undefined) setStopLossPct(p.stop_loss_pct * 100);
  };

  const handleSelectTemplate = (tmplId: string) => {
    setSelectedTemplateId(tmplId);
    const tmpl = templates.find((t) => t.template_id === tmplId);
    if (tmpl) {
      applyTemplateDefaults(tmpl);
    }
  };

  // 2. Validate Backtest Configuration Pre-Flight
  const handleValidateBacktest = async () => {
    setValidating(true);
    try {
      const config = buildCurrentConfig();
      const res = await api.validateBacktest(config);
      if (res && res.success) {
        setValidationResult(res.validation);
        if (res.validation.is_valid) {
          notify?.('Pre-flight validation passed: all parameters sound.');
        } else {
          notify?.(`Validation identified ${res.validation.errors.length} errors.`);
        }
      }
    } catch (err: any) {
      notify?.(`Validation failed: ${err.message}`);
    } finally {
      setValidating(false);
    }
  };

  // 3. Save Configuration
  const handleSaveConfig = async () => {
    try {
      const config = buildCurrentConfig();
      const res = await api.saveBacktestConfig(config);
      if (res && res.success) {
        notify?.(`Configuration persisted with ID: ${res.config_id}`);
      }
    } catch (err: any) {
      notify?.(`Failed to save config: ${err.message}`);
    }
  };

  // 4. Duplicate Configuration
  const handleDuplicateConfig = async () => {
    try {
      const config = buildCurrentConfig();
      const saveRes = await api.saveBacktestConfig(config);
      if (saveRes && saveRes.success) {
        const dupRes = await api.duplicateBacktestConfig(saveRes.config_id, `${config.name} (Clone)`);
        if (dupRes && dupRes.success) {
          notify?.(`Configuration duplicated: ${dupRes.config.config_id}`);
        }
      }
    } catch (err: any) {
      notify?.(`Duplication failed: ${err.message}`);
    }
  };

  // 5. Execute Real Historical Backtest via Page 16 Pipeline
  const handleRunBacktest = async () => {
    setRunningBacktest(true);
    setErrorMsg(null);
    try {
      const config = buildCurrentConfig();
      const res = await api.runBacktestingLab(config);

      if (res && res.success) {
        setBacktestResult(res);
        notify?.(`Backtest completed for ${selectedSymbol} with anti-bias diagnostics & rolling risk.`);
        const runsRes = await api.listStrategyRuns();
        if (runsRes?.runs) setRecentRuns(runsRes.runs);
      } else {
        setErrorMsg('Backtest execution did not return expected response envelope.');
      }
    } catch (err: any) {
      console.error('Backtest error:', err);
      setErrorMsg(err.message || 'Execution failed on server.');
    } finally {
      setRunningBacktest(false);
    }
  };

  // 6. Run Trade Ablation Analysis
  const handleRunAblation = async () => {
    setRunningAblation(true);
    try {
      const config = buildCurrentConfig();
      const res = await api.runBacktestAblation({
        ...config,
        num_top_trades: numTopTrades,
      });
      if (res && res.success && res.ablation) {
        setAblationResult(res.ablation);
        notify?.(`Ablation complete: evaluated removal of top ${numTopTrades} winning trades.`);
      }
    } catch (err: any) {
      notify?.(`Ablation failed: ${err.message}`);
    } finally {
      setRunningAblation(false);
    }
  };

  // 3. Export Trades to CSV
  const handleExportTradesCSV = () => {
    const trades = backtestResult?.trades || [];
    if (trades.length === 0) {
      notify?.('No completed trades to export.');
      return;
    }
    const headers = [
      'Trade ID',
      'Entry Date',
      'Entry Price',
      'Exit Date',
      'Exit Price',
      'Direction',
      'Shares',
      'Entry Cost',
      'Gross PnL',
      'Exit Fees',
      'Net PnL',
      'Return %',
      'Holding Days',
      'Exit Reason',
    ];
    const rows = trades.map((t: any) => [
      t.trade_id,
      t.entry_date,
      Number(t.entry_price).toFixed(2),
      t.exit_date,
      Number(t.exit_price).toFixed(2),
      t.direction,
      t.shares,
      Number(t.entry_cost).toFixed(2),
      Number(t.gross_pnl).toFixed(2),
      Number(t.exit_fees).toFixed(2),
      Number(t.net_pnl).toFixed(2),
      (Number(t.return_pct) * 100).toFixed(2) + '%',
      t.holding_bars,
      `"${String(t.exit_reason || '').replace(/"/g, '""')}"`,
    ]);

    const csvContent = [headers.join(','), ...rows.map((r: any) => r.join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', `trades_${backtestResult?.strategy?.strategy_id || selectedTemplateId}_${selectedSymbol}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    notify?.('Trade ledger exported to CSV.');
  };

  // Safe Mappings & Derived Data
  const metrics = backtestResult?.metrics || {};
  const strategyInfo = backtestResult?.strategy || {};
  const walkForward = backtestResult?.walk_forward || {};
  const trainMetrics = walkForward?.train_window?.metrics || walkForward?.is_train || {};
  const testMetrics = walkForward?.test_window?.metrics || walkForward?.oos_test || {};
  const costStress = backtestResult?.cost_stress_test || backtestResult?.cost_sensitivity || [];
  const trades = backtestResult?.trades || [];
  const rawEquityCurve = backtestResult?.equity_curve || [];

  // Format equity curve for Recharts
  const formattedEquityCurve = useMemo(() => {
    return rawEquityCurve.map((bar: any) => ({
      date: bar.date,
      strategy_equity: bar.equity ?? bar.strategy_equity ?? 0,
      benchmark_equity: bar.benchmark_equity ?? 0,
      cash: bar.cash ?? 0,
      drawdown: bar.drawdown ?? 0,
    }));
  }, [rawEquityCurve]);

  // Reconciliation Values
  const initialCap = Number(strategyInfo.initial_capital || initialCapital || 1000000);
  const finalEquity = Number(metrics.final_equity || initialCap);
  const netPortfolioProfit = Number(metrics.net_profit || (finalEquity - initialCap));
  const sumTradeNetPnl = trades.reduce((acc: number, t: any) => acc + Number(t.net_pnl || 0), 0);
  const reconDiff = metrics.reconciliation_difference ?? Math.abs(netPortfolioProfit - sumTradeNetPnl);

  return (
    <div className="stack-layout space-y-6 p-6">
      {/* Header */}
      <section className="panel generic-hero flex items-center justify-between p-6 bg-slate-900 border border-slate-800 rounded-lg shadow-md">
        <div className="flex items-center gap-4">
          <div className="generic-mark p-3 bg-emerald-950/60 border border-emerald-500/30 text-emerald-400 rounded-lg">
            <BriefcaseBusiness size={24} />
          </div>
          <div>
            <span className="section-kicker text-xs font-mono tracking-wider text-emerald-400 font-semibold uppercase">
              STRATEGY RESEARCH / PAGE 08
            </span>
            <h2 className="text-xl font-bold text-slate-100 flex items-center gap-3">
              Strategy Research &amp; Walk-Forward Backtesting Lab
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-emerald-900/60 border border-emerald-500/30 text-emerald-300 font-mono">
                1-Bar Lagged • Real Upstox Data
              </span>
            </h2>
            <p className="text-xs text-slate-400 mt-1 max-w-2xl">
              Simulate quantitative strategies with realistic 1-bar execution delay, fee &amp; slippage friction,
              chronological walk-forward train/test degradation scores, and exact cash ledger reconciliation.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => setActiveTab(activeTab === 'workspace' ? 'history' : 'workspace')}
            className={`px-3 py-1.5 text-xs font-medium rounded border transition flex items-center gap-2 ${
              activeTab === 'history'
                ? 'bg-slate-800 border-slate-700 text-slate-200'
                : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200'
            }`}
          >
            <History size={14} />
            {activeTab === 'history' ? 'Back to Lab' : `History (${recentRuns.length})`}
          </button>
        </div>
      </section>

      {/* Disclaimers & Mathematical Safety Bar */}
      <div className="bg-amber-950/20 border border-amber-500/30 text-amber-300/90 px-4 py-3 rounded-lg text-xs flex items-center gap-3">
        <AlertTriangle size={18} className="text-amber-400 flex-shrink-0" />
        <div className="flex-1">
          <span className="font-semibold text-amber-200">Mathematical Validation Reality Check: </span>
          A profitable historical backtest is only a hypothesis test, never a guarantee of future alpha.
          Backtested returns must survive out-of-sample walk-forward degradation and friction stress tests before capital allocation.
        </div>
        <div className="text-[11px] font-mono text-amber-400/80 bg-amber-900/40 px-2 py-1 rounded border border-amber-500/20">
          Rf = 6.50% (RBI Repo)
        </div>
      </div>

      {errorMsg && (
        <div className="bg-rose-950/40 border border-rose-500/50 text-rose-300 p-4 rounded-lg text-xs flex items-start gap-3">
          <AlertTriangle size={16} className="text-rose-400 mt-0.5 flex-shrink-0" />
          <div className="flex-1">
            <div className="font-semibold text-rose-200">Execution Error</div>
            <div>{errorMsg}</div>
          </div>
          <button onClick={() => setErrorMsg(null)} className="text-rose-400 hover:text-rose-200 text-xs">
            Dismiss
          </button>
        </div>
      )}

      {activeTab === 'history' ? (
        /* History View */
        <div className="panel bg-slate-900 border border-slate-800 rounded-lg p-6 space-y-4">
          <h3 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
            <History size={16} className="text-emerald-400" />
            Previous Strategy Backtest Records ({recentRuns.length})
          </h3>
          {recentRuns.length === 0 ? (
            <div className="text-center py-12 text-slate-500 text-xs font-mono">
              No previous backtest runs recorded yet. Execute a backtest to log cryptographic records.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left border-collapse">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400 font-mono">
                    <th className="py-2.5 px-3">Run ID</th>
                    <th className="py-2.5 px-3">Strategy</th>
                    <th className="py-2.5 px-3">Symbol</th>
                    <th className="py-2.5 px-3">Created</th>
                    <th className="py-2.5 px-3">Return</th>
                    <th className="py-2.5 px-3">Sharpe</th>
                    <th className="py-2.5 px-3">Max DD</th>
                    <th className="py-2.5 px-3">Trades</th>
                    <th className="py-2.5 px-3">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-mono text-slate-300">
                  {recentRuns.map((r, idx) => {
                    const m = r.metrics || {};
                    return (
                      <tr key={idx} className="hover:bg-slate-800/40 text-slate-300">
                        <td className="py-2.5 px-3 text-emerald-400 font-semibold">{r.run_id}</td>
                        <td className="py-2.5 px-3 text-slate-200">{r.display_name || r.strategy_id}</td>
                        <td className="py-2.5 px-3 text-slate-300">{r.symbol}</td>
                        <td className="py-2.5 px-3 text-slate-400">{r.created_at ? new Date(r.created_at).toLocaleString() : 'N/A'}</td>
                        <td className="py-2.5 px-3">
                          <span className={Number(m.cumulative_return || 0) >= 0 ? 'text-emerald-400 font-semibold' : 'text-rose-400 font-semibold'}>
                            {(Number(m.cumulative_return || 0) * 100).toFixed(1)}%
                          </span>
                        </td>
                        <td className="py-2.5 px-3">{Number(m.sharpe_ratio || 0).toFixed(2)}</td>
                        <td className="py-2.5 px-3 text-rose-400">{(Number(m.max_drawdown || 0) * 100).toFixed(1)}%</td>
                        <td className="py-2.5 px-3">{m.total_trades || 0}</td>
                        <td className="py-2.5 px-3">
                          <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-950/60 text-emerald-400 border border-emerald-500/30">
                            {r.status?.toUpperCase() || 'COMPLETED'}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : (
        /* Workspace View */
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left Column: Strategy Template Selector & Configuration Controls */}
          <div className="lg:col-span-4 space-y-5">
            {/* Template Selector Card */}
            <div className="panel bg-slate-900 border border-slate-800 rounded-lg p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                  <Layers size={14} className="text-emerald-400" />
                  Strategy Catalog
                </h3>
                <span className="text-[11px] font-mono text-slate-500">
                  {templates.length} Models
                </span>
              </div>

              <div className="grid grid-cols-1 gap-2">
                {templates.map((tmpl) => {
                  const isSelected = tmpl.template_id === selectedTemplateId;
                  return (
                    <button
                      key={tmpl.template_id}
                      onClick={() => handleSelectTemplate(tmpl.template_id)}
                      className={`text-left p-3 rounded-lg border transition ${
                        isSelected
                          ? 'bg-emerald-950/30 border-emerald-500/50 text-slate-100 shadow-sm'
                          : 'bg-slate-950/60 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs font-semibold text-slate-200">{tmpl.name}</span>
                        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">
                          {tmpl.category}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-400 line-clamp-2 leading-relaxed">
                        {tmpl.description}
                      </p>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Configurator Card */}
            <div className="panel bg-slate-900 border border-slate-800 rounded-lg p-5 space-y-4">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                <Sliders size={14} className="text-emerald-400" />
                Parameters &amp; Friction Engine
              </h3>

              {/* Symbol Picker */}
              <div>
                <label className="block text-[11px] font-medium text-slate-400 mb-1">Target Asset Universe</label>
                <select
                  value={selectedSymbol}
                  onChange={(e) => setSelectedSymbol(e.target.value)}
                  className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
                >
                  {SUPPORTED_SYMBOLS.map((s) => (
                    <option key={s.symbol} value={s.symbol}>
                      {s.symbol} — {s.name} ({s.exchange})
                    </option>
                  ))}
                </select>
              </div>

              {/* Strategy Parameters Dynamic */}
              {selectedTemplateId === 'ma_crossover' && (
                <div className="grid grid-cols-2 gap-3 p-3 bg-slate-950 rounded border border-slate-800">
                  <div>
                    <label className="block text-[10px] font-mono text-slate-400 mb-1">Fast Period (Days)</label>
                    <input
                      type="number"
                      min={2}
                      max={100}
                      value={fastPeriod}
                      onChange={(e) => setFastPeriod(Number(e.target.value))}
                      className="w-full bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-slate-200"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-mono text-slate-400 mb-1">Slow Period (Days)</label>
                    <input
                      type="number"
                      min={5}
                      max={250}
                      value={slowPeriod}
                      onChange={(e) => setSlowPeriod(Number(e.target.value))}
                      className="w-full bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-slate-200"
                    />
                  </div>
                </div>
              )}

              {selectedTemplateId === 'rsi_momentum' && (
                <div className="grid grid-cols-3 gap-2 p-3 bg-slate-950 rounded border border-slate-800">
                  <div>
                    <label className="block text-[10px] font-mono text-slate-400 mb-1">RSI Period</label>
                    <input
                      type="number"
                      min={2}
                      max={50}
                      value={rsiPeriod}
                      onChange={(e) => setRsiPeriod(Number(e.target.value))}
                      className="w-full bg-slate-900 border border-slate-800 rounded px-2 py-1.5 text-xs text-slate-200"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-mono text-slate-400 mb-1">Oversold</label>
                    <input
                      type="number"
                      min={10}
                      max={45}
                      value={rsiOversold}
                      onChange={(e) => setRsiOversold(Number(e.target.value))}
                      className="w-full bg-slate-900 border border-slate-800 rounded px-2 py-1.5 text-xs text-slate-200"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-mono text-slate-400 mb-1">Overbought</label>
                    <input
                      type="number"
                      min={55}
                      max={90}
                      value={rsiOverbought}
                      onChange={(e) => setRsiOverbought(Number(e.target.value))}
                      className="w-full bg-slate-900 border border-slate-800 rounded px-2 py-1.5 text-xs text-slate-200"
                    />
                  </div>
                </div>
              )}

              {selectedTemplateId === 'bollinger_reversion' && (
                <div className="grid grid-cols-2 gap-3 p-3 bg-slate-950 rounded border border-slate-800">
                  <div>
                    <label className="block text-[10px] font-mono text-slate-400 mb-1">Period</label>
                    <input
                      type="number"
                      min={5}
                      max={100}
                      value={bbPeriod}
                      onChange={(e) => setBbPeriod(Number(e.target.value))}
                      className="w-full bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-slate-200"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-mono text-slate-400 mb-1">StDev Multiplier (σ)</label>
                    <input
                      type="number"
                      step={0.1}
                      min={1}
                      max={4}
                      value={bbStd}
                      onChange={(e) => setBbStd(Number(e.target.value))}
                      className="w-full bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-slate-200"
                    />
                  </div>
                </div>
              )}

              {selectedTemplateId === 'vol_target' && (
                <div className="p-3 bg-slate-950 rounded border border-slate-800">
                  <label className="block text-[10px] font-mono text-slate-400 mb-1">Target Annual Volatility</label>
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      step={0.01}
                      min={0.05}
                      max={0.5}
                      value={targetVol}
                      onChange={(e) => setTargetVol(Number(e.target.value))}
                      className="w-full bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-slate-200"
                    />
                    <span className="text-xs text-slate-400 font-mono">{(targetVol * 100).toFixed(0)}%</span>
                  </div>
                </div>
              )}

              {/* Stop Loss Input */}
              <div>
                <label className="block text-[11px] font-medium text-slate-400 mb-1">Stop Loss (% from entry)</label>
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min="1"
                    max="10"
                    step="0.5"
                    value={stopLossPct}
                    onChange={(e) => setStopLossPct(Number(e.target.value))}
                    className="flex-1 accent-emerald-500"
                  />
                  <span className="text-xs font-mono text-slate-200 w-12 text-right">{stopLossPct.toFixed(1)}%</span>
                </div>
              </div>

              {/* Capital & Friction */}
              <div className="space-y-3 pt-2 border-t border-slate-800/80">
                <div>
                  <label className="block text-[11px] font-medium text-slate-400 mb-1">Initial Capital (₹)</label>
                  <input
                    type="number"
                    step={50000}
                    value={initialCapital}
                    onChange={(e) => setInitialCapital(Number(e.target.value))}
                    className="w-full bg-slate-950 border border-slate-800 rounded px-3 py-1.5 text-xs font-mono text-slate-200"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[10px] font-mono text-slate-400 mb-1">Fee (bps)</label>
                    <input
                      type="number"
                      min={0}
                      max={50}
                      value={feeBps}
                      onChange={(e) => setFeeBps(Number(e.target.value))}
                      className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-xs font-mono text-slate-200"
                    />
                  </div>
                  <div>
                    <label className="block text-[10px] font-mono text-slate-400 mb-1">Slippage (bps)</label>
                    <input
                      type="number"
                      min={0}
                      max={50}
                      value={slippageBps}
                      onChange={(e) => setSlippageBps(Number(e.target.value))}
                      className="w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-xs font-mono text-slate-200"
                    />
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between text-[11px] text-slate-400 mb-1">
                    <span>Walk-Forward In-Sample Ratio</span>
                    <span className="font-mono text-slate-200">{(trainRatio * 100).toFixed(0)}% Train / {((1 - trainRatio) * 100).toFixed(0)}% Test</span>
                  </div>
                  <input
                    type="range"
                    min="0.5"
                    max="0.85"
                    step="0.05"
                    value={trainRatio}
                    onChange={(e) => setTrainRatio(Number(e.target.value))}
                    className="w-full accent-emerald-500"
                  />
                </div>
              </div>

              {/* Execution Delay Notification */}
              <div className="p-2.5 bg-slate-950/80 rounded border border-slate-800 text-[10px] text-slate-400 font-mono flex items-center gap-2">
                <Lock size={12} className="text-emerald-400 flex-shrink-0" />
                <span>Enforced 1-bar execution delay: Signals on Close(t) execute on Open(t+1). No lookahead bias.</span>
              </div>

              {/* Action Buttons: Validate, Run, Save, Duplicate */}
              <div className="space-y-2 pt-2">
                <div className="grid grid-cols-2 gap-2">
                  <button
                    onClick={handleValidateBacktest}
                    disabled={validating}
                    className="py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs rounded transition flex items-center justify-center gap-1.5"
                  >
                    {validating ? <RefreshCw size={12} className="animate-spin" /> : <ShieldCheck size={12} className="text-emerald-400" />}
                    Validate Setup
                  </button>
                  <button
                    onClick={handleSaveConfig}
                    className="py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 text-xs rounded transition flex items-center justify-center gap-1.5"
                  >
                    <Save size={12} className="text-blue-400" />
                    Save Config
                  </button>
                </div>
                <div className="flex justify-end">
                  <button
                    onClick={handleDuplicateConfig}
                    className="text-[11px] text-slate-400 hover:text-slate-200 flex items-center gap-1"
                  >
                    <Copy size={11} /> Clone Configuration
                  </button>
                </div>

                {validationResult && (
                  <div className={`p-2.5 rounded text-[11px] border font-mono ${
                    validationResult.is_valid
                      ? 'bg-emerald-950/40 border-emerald-500/30 text-emerald-300'
                      : 'bg-rose-950/40 border-rose-500/30 text-rose-300'
                  }`}>
                    <div className="font-semibold flex items-center gap-1.5 mb-1">
                      {validationResult.is_valid ? <CheckCircle2 size={13} /> : <AlertOctagon size={13} />}
                      {validationResult.is_valid ? 'CONFIGURATION SOUND' : 'VALIDATION ISSUES'}
                    </div>
                    {validationResult.errors?.length > 0 && (
                      <ul className="list-disc pl-4 space-y-0.5 text-[10px] text-rose-300">
                        {validationResult.errors.map((e: string, i: number) => <li key={i}>{e}</li>)}
                      </ul>
                    )}
                    {validationResult.warnings?.length > 0 && (
                      <ul className="list-disc pl-4 space-y-0.5 text-[10px] text-amber-300">
                        {validationResult.warnings.map((w: string, i: number) => <li key={i}>{w}</li>)}
                      </ul>
                    )}
                  </div>
                )}

                <button
                  onClick={handleRunBacktest}
                  disabled={runningBacktest}
                  className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-xs rounded-lg transition shadow-md flex items-center justify-center gap-2 disabled:opacity-50"
                >
                  {runningBacktest ? (
                    <>
                      <RefreshCw size={14} className="animate-spin" />
                      Executing Backtest Protocol...
                    </>
                  ) : (
                    <>
                      <Play size={14} />
                      Run Backtest Protocol
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>

          {/* Right Column: Performance Results, Charts & Walk-Forward Audit */}
          <div className="lg:col-span-8 space-y-6">
            {!backtestResult ? (
              <div className="panel bg-slate-900 border border-slate-800 rounded-lg p-12 text-center flex flex-col items-center justify-center space-y-4">
                <div className="w-12 h-12 rounded-full bg-slate-800 flex items-center justify-center text-slate-400">
                  <Activity size={24} />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-slate-200">No Backtest Executed Yet</h3>
                  <p className="text-xs text-slate-400 max-w-md mt-1">
                    Select a quantitative strategy template, configure execution frictions, and run a walk-forward simulation
                    against genuine market observations from Upstox.
                  </p>
                </div>
                <button
                  onClick={handleRunBacktest}
                  disabled={runningBacktest}
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-lg flex items-center gap-2"
                >
                  <Play size={14} /> Run First Backtest
                </button>
              </div>
            ) : (
              <>
                {/* Core KPI Metrics Grid */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  {/* Cumulative Return */}
                  <div className="panel bg-slate-900 border border-slate-800 rounded-lg p-4">
                    <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider block mb-1">
                      Cumulative Return
                    </span>
                    <div className="flex items-baseline gap-2">
                      <span className={`text-xl font-bold font-mono ${
                        Number(metrics.cumulative_return || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'
                      }`}>
                        {(Number(metrics.cumulative_return || 0) * 100).toFixed(1)}%
                      </span>
                      <span className="text-[10px] text-slate-500 font-mono">
                        CAGR {(Number(metrics.cagr || 0) * 100).toFixed(1)}%
                      </span>
                    </div>
                    <div className="mt-2 text-[10px] text-slate-400 flex items-center justify-between border-t border-slate-800/60 pt-1.5">
                      <span>Benchmark Buy&amp;Hold:</span>
                      <span className="font-mono text-slate-300">
                        {(Number(metrics.benchmark_return || 0) * 100).toFixed(1)}%
                      </span>
                    </div>
                  </div>

                  {/* Sharpe Ratio */}
                  <div className="panel bg-slate-900 border border-slate-800 rounded-lg p-4">
                    <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider block mb-1">
                      Sharpe Ratio (Rf=6.5%)
                    </span>
                    <div className="flex items-baseline gap-2">
                      <span className="text-xl font-bold font-mono text-slate-100">
                        {Number(metrics.sharpe_ratio || 0).toFixed(2)}
                      </span>
                      <span className="text-[10px] text-slate-500 font-mono">
                        Sortino {Number(metrics.sortino_ratio || 0).toFixed(2)}
                      </span>
                    </div>
                    <div className="mt-2 text-[10px] text-slate-400 flex items-center justify-between border-t border-slate-800/60 pt-1.5">
                      <span>Annualized Vol:</span>
                      <span className="font-mono text-slate-300">
                        {(Number(metrics.annualized_volatility || 0) * 100).toFixed(1)}%
                      </span>
                    </div>
                  </div>

                  {/* Max Drawdown */}
                  <div className="panel bg-slate-900 border border-slate-800 rounded-lg p-4">
                    <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider block mb-1">
                      Max Drawdown
                    </span>
                    <div className="flex items-baseline gap-2">
                      <span className="text-xl font-bold font-mono text-rose-400">
                        {(Number(metrics.max_drawdown || 0) * 100).toFixed(1)}%
                      </span>
                      <span className="text-[10px] text-slate-500 font-mono">
                        Calmar {Number(metrics.calmar_ratio || 0).toFixed(2)}
                      </span>
                    </div>
                    <div className="mt-2 text-[10px] text-slate-400 flex items-center justify-between border-t border-slate-800/60 pt-1.5">
                      <span>Alpha vs Bench:</span>
                      <span className="font-mono text-slate-300">
                        {(Number(metrics.alpha || 0) * 100).toFixed(1)}%
                      </span>
                    </div>
                  </div>

                  {/* Win Rate & Trades */}
                  <div className="panel bg-slate-900 border border-slate-800 rounded-lg p-4">
                    <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider block mb-1">
                      Win Rate &amp; Trades
                    </span>
                    <div className="flex items-baseline gap-2">
                      <span className="text-xl font-bold font-mono text-slate-100">
                        {(Number(metrics.win_rate || 0) * 100).toFixed(1)}%
                      </span>
                      <span className="text-[10px] text-slate-500 font-mono">
                        PF {Number(metrics.profit_factor || 0).toFixed(2)}
                      </span>
                    </div>
                    <div className="mt-2 text-[10px] text-slate-400 flex items-center justify-between border-t border-slate-800/60 pt-1.5">
                      <span>Trades (W / L):</span>
                      <span className="font-mono text-slate-300">
                        {metrics.winning_trades_count || 0} / {metrics.losing_trades_count || 0} ({metrics.total_trades || 0})
                      </span>
                    </div>
                  </div>
                </div>

                {/* Sub-Tab Navigation for Page 16 Diagnostics */}
                <div className="flex flex-wrap items-center gap-2 border-b border-slate-800 pb-2">
                  {[
                    { id: 'overview', label: '1. Equity & Drawdown' },
                    { id: 'antibias', label: `2. Anti-Bias Audit (${backtestResult.anti_bias_diagnostics?.length || 8})` },
                    { id: 'rolling', label: '3. Rolling Risk & Monthly' },
                    { id: 'ablation', label: '4. Trade Ablation' },
                    { id: 'walkforward', label: '5. Walk-Forward Audit' },
                    { id: 'trades', label: `6. Trade Ledger (${trades.length})` },
                  ].map((t) => (
                    <button
                      key={t.id}
                      onClick={() => setActiveSubTab(t.id as any)}
                      className={`px-3 py-1.5 text-xs font-medium rounded transition ${
                        activeSubTab === t.id
                          ? 'bg-emerald-600 text-white shadow-sm'
                          : 'bg-slate-900 border border-slate-800 text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>

                {/* SubTab 1: Overview (Equity Curve & Underwater Drawdown) */}
                {activeSubTab === 'overview' && (
                  <div className="space-y-4">
                    {/* Primary Visualization: Cumulative Equity Curve */}
                    <div className="panel bg-slate-900 border border-slate-800 rounded-lg p-5 space-y-3">
                      <div className="flex items-center justify-between">
                        <div>
                          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-200">
                            Equity Growth vs Benchmark
                          </h3>
                          <p className="text-[11px] text-slate-400">
                            Portfolio marked-to-market value over time incorporating transaction friction and 1-bar execution delay.
                          </p>
                        </div>
                        <div className="flex items-center gap-4 text-xs font-mono">
                          <span className="flex items-center gap-1.5 text-emerald-400">
                            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block" />
                            Strategy Net
                          </span>
                          <span className="flex items-center gap-1.5 text-sky-400">
                            <span className="w-2.5 h-2.5 rounded-full bg-sky-500 inline-block" />
                            Buy &amp; Hold
                          </span>
                          <span className="flex items-center gap-1.5 text-slate-400">
                            <span className="w-2.5 h-0.5 bg-slate-500 inline-block" />
                            Cash Baseline
                          </span>
                        </div>
                      </div>

                      <div className="h-64 w-full">
                        <ResponsiveContainer width="100%" height="100%">
                          <LineChart data={formattedEquityCurve} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                            <XAxis
                              dataKey="date"
                              stroke="#64748b"
                              tick={{ fontSize: 10, fill: '#64748b' }}
                              tickFormatter={(d) => (typeof d === 'string' && d.length >= 10 ? d.slice(5) : d)}
                            />
                            <YAxis
                              stroke="#64748b"
                              tick={{ fontSize: 10, fill: '#64748b' }}
                              tickFormatter={(v) => `₹${(v / 100000).toFixed(1)}L`}
                              domain={['auto', 'auto']}
                            />
                            <Tooltip
                              contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', fontSize: '11px' }}
                              formatter={(val: any, name: string) => [
                                `₹${Number(val).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`,
                                name === 'strategy_equity'
                                  ? 'Strategy Net'
                                  : name === 'benchmark_equity'
                                  ? 'Buy & Hold'
                                  : 'Cash',
                              ]}
                              labelFormatter={(label) => `Date: ${label}`}
                            />
                            <Line
                              type="monotone"
                              dataKey="strategy_equity"
                              name="strategy_equity"
                              stroke="#10b981"
                              strokeWidth={2}
                              dot={false}
                            />
                            <Line
                              type="monotone"
                              dataKey="benchmark_equity"
                              name="benchmark_equity"
                              stroke="#0284c7"
                              strokeWidth={1.5}
                              strokeDasharray="4 4"
                              dot={false}
                            />
                            <Line
                              type="monotone"
                              dataKey="cash"
                              name="cash"
                              stroke="#475569"
                              strokeWidth={1}
                              dot={false}
                            />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </div>

                    {/* Secondary Visualization: Underwater Drawdown */}
                    <div className="panel bg-slate-900 border border-slate-800 rounded-lg p-5 space-y-3">
                      <div className="flex items-center justify-between">
                        <div>
                          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-200">
                            Underwater Drawdown Profile
                          </h3>
                          <p className="text-[11px] text-slate-400">
                            Percentage decline from trailing historical equity peak across the backtest horizon.
                          </p>
                        </div>
                      </div>

                      <div className="h-36 w-full">
                        <ResponsiveContainer width="100%" height="100%">
                          <AreaChart data={formattedEquityCurve} margin={{ top: 5, right: 10, left: 10, bottom: 0 }}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                            <XAxis
                              dataKey="date"
                              stroke="#64748b"
                              tick={{ fontSize: 9, fill: '#64748b' }}
                              tickFormatter={(d) => (typeof d === 'string' && d.length >= 10 ? d.slice(5) : d)}
                            />
                            <YAxis
                              stroke="#64748b"
                              tick={{ fontSize: 9, fill: '#64748b' }}
                              tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
                            />
                            <Tooltip
                              contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', fontSize: '11px' }}
                              formatter={(val: any) => [`${(Number(val) * 100).toFixed(2)}%`, 'Drawdown']}
                            />
                            <Area
                              type="monotone"
                              dataKey="drawdown"
                              stroke="#f43f5e"
                              fill="#f43f5e"
                              fillOpacity={0.25}
                            />
                          </AreaChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  </div>
                )}

                {/* SubTab 2: Anti-Bias Diagnostics */}
                {activeSubTab === 'antibias' && (
                  <div className="panel bg-slate-900 border border-slate-800 rounded-lg p-5 space-y-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-200 flex items-center gap-2">
                          <ShieldCheck size={16} className="text-emerald-400" />
                          Quantitative Anti-Bias Diagnostic Audit (8 Verification Checks)
                        </h3>
                        <p className="text-[11px] text-slate-400 mt-0.5">
                          Evaluates structural backtest validity, look-ahead leakage, survivorship effects, execution delay, and sample sizes.
                        </p>
                      </div>
                      <span className="text-xs font-mono px-2.5 py-1 rounded bg-slate-800 text-slate-300 border border-slate-700">
                        {backtestResult.anti_bias_diagnostics?.filter((d: any) => d.status === 'passed').length || 0} / {backtestResult.anti_bias_diagnostics?.length || 8} Passed
                      </span>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {(backtestResult.anti_bias_diagnostics || []).map((diag: any) => (
                        <div
                          key={diag.check_id}
                          className={`p-3 rounded-lg border text-xs space-y-1.5 ${
                            diag.status === 'passed'
                              ? 'bg-emerald-950/20 border-emerald-500/30 text-emerald-200'
                              : diag.status === 'warning'
                              ? 'bg-amber-950/20 border-amber-500/30 text-amber-200'
                              : 'bg-rose-950/20 border-rose-500/30 text-rose-200'
                          }`}
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-semibold text-slate-100 flex items-center gap-1.5">
                              {diag.status === 'passed' ? (
                                <CheckCircle2 size={14} className="text-emerald-400" />
                              ) : (
                                <AlertTriangle size={14} className="text-amber-400" />
                              )}
                              {diag.name}
                            </span>
                            <span
                              className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase ${
                                diag.status === 'passed'
                                  ? 'bg-emerald-900/60 text-emerald-300 border border-emerald-500/40'
                                  : diag.status === 'warning'
                                  ? 'bg-amber-950/60 text-amber-300 border border-amber-500/40'
                                  : 'bg-rose-900/60 text-rose-300 border border-rose-500/40'
                              }`}
                            >
                              {diag.status}
                            </span>
                          </div>
                          <p className="text-[11px] text-slate-300 leading-relaxed">{diag.description}</p>
                          <div className="text-[10px] font-mono text-slate-400 bg-slate-950/60 p-2 rounded border border-slate-800">
                            <span className="text-slate-500 block">Evidence:</span>
                            {diag.evidence}
                          </div>
                          {diag.remediation && (
                            <div className="text-[10px] text-slate-400 italic">
                              <span className="font-medium text-slate-300 not-italic">Remediation: </span>
                              {diag.remediation}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* SubTab 3: Rolling Risk & Monthly Returns */}
                {activeSubTab === 'rolling' && (
                  <div className="space-y-4">
                    {/* Rolling Sharpe Chart */}
                    <div className="panel bg-slate-900 border border-slate-800 rounded-lg p-5 space-y-3">
                      <div className="flex items-center justify-between">
                        <div>
                          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-200">
                            Rolling 30-Day Annualized Sharpe Ratio
                          </h3>
                          <p className="text-[11px] text-slate-400">
                            Evolution of risk-adjusted excess returns over trailing rolling windows.
                          </p>
                        </div>
                      </div>
                      <div className="h-44 w-full">
                        <ResponsiveContainer width="100%" height="100%">
                          <LineChart
                            data={backtestResult.rolling_analytics?.rolling_sharpe || []}
                            margin={{ top: 5, right: 10, left: 10, bottom: 0 }}
                          >
                            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                            <XAxis
                              dataKey="date"
                              stroke="#64748b"
                              tick={{ fontSize: 9, fill: '#64748b' }}
                              tickFormatter={(d) => (typeof d === 'string' && d.length >= 10 ? d.slice(5) : d)}
                            />
                            <YAxis
                              stroke="#64748b"
                              tick={{ fontSize: 9, fill: '#64748b' }}
                              domain={['auto', 'auto']}
                            />
                            <Tooltip
                              contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', fontSize: '11px' }}
                              formatter={(val: any) => [Number(val).toFixed(2), 'Rolling Sharpe']}
                            />
                            <Line
                              type="monotone"
                              dataKey="rolling_sharpe"
                              stroke="#38bdf8"
                              strokeWidth={2}
                              dot={false}
                            />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </div>

                    {/* Rolling Volatility Chart */}
                    <div className="panel bg-slate-900 border border-slate-800 rounded-lg p-5 space-y-3">
                      <div className="flex items-center justify-between">
                        <div>
                          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-200">
                            Rolling 30-Day Annualized Volatility
                          </h3>
                          <p className="text-[11px] text-slate-400">
                            Rolling annualized standard deviation across market regimes.
                          </p>
                        </div>
                      </div>
                      <div className="h-44 w-full">
                        <ResponsiveContainer width="100%" height="100%">
                          <AreaChart
                            data={backtestResult.rolling_analytics?.rolling_volatility || []}
                            margin={{ top: 5, right: 10, left: 10, bottom: 0 }}
                          >
                            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                            <XAxis
                              dataKey="date"
                              stroke="#64748b"
                              tick={{ fontSize: 9, fill: '#64748b' }}
                              tickFormatter={(d) => (typeof d === 'string' && d.length >= 10 ? d.slice(5) : d)}
                            />
                            <YAxis
                              stroke="#64748b"
                              tick={{ fontSize: 9, fill: '#64748b' }}
                              tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
                            />
                            <Tooltip
                              contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', fontSize: '11px' }}
                              formatter={(val: any) => [`${(Number(val) * 100).toFixed(2)}%`, 'Rolling Volatility']}
                            />
                            <Area
                              type="monotone"
                              dataKey="rolling_volatility"
                              stroke="#f59e0b"
                              fill="#f59e0b"
                              fillOpacity={0.2}
                            />
                          </AreaChart>
                        </ResponsiveContainer>
                      </div>
                    </div>

                    {/* Monthly Returns Matrix */}
                    <div className="panel bg-slate-900 border border-slate-800 rounded-lg p-5 space-y-3">
                      <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-200">
                        Monthly Historical Returns
                      </h3>
                      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
                        {(backtestResult.rolling_analytics?.monthly_returns || []).map((m: any, idx: number) => {
                          const ret = Number(m.return_pct || 0);
                          return (
                            <div
                              key={idx}
                              className={`p-2.5 rounded border font-mono text-xs flex items-center justify-between ${
                                ret >= 0
                                  ? 'bg-emerald-950/30 border-emerald-500/20 text-emerald-300'
                                  : 'bg-rose-950/30 border-rose-500/20 text-rose-300'
                              }`}
                            >
                              <span className="text-slate-400 text-[10px]">{m.year_month}</span>
                              <span className="font-semibold font-mono">{(ret * 100).toFixed(1)}%</span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>
                )}

                {/* SubTab 4: Trade Ablation */}
                {activeSubTab === 'ablation' && (
                  <div className="panel bg-slate-900 border border-slate-800 rounded-lg p-5 space-y-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-200 flex items-center gap-2">
                          <SlidersHorizontal size={16} className="text-amber-400" />
                          Trade Ablation &amp; Fragility Analysis
                        </h3>
                        <p className="text-[11px] text-slate-400 mt-0.5">
                          Compare a diagnostic post-hoc removal of top winning trades against a genuine path-dependent portfolio re-simulation.
                        </p>
                      </div>

                      <div className="flex items-center gap-2">
                        <label className="text-xs font-mono text-slate-400">Remove Top N:</label>
                        <select
                          value={numTopTrades}
                          onChange={(e) => setNumTopTrades(Number(e.target.value))}
                          className="bg-slate-950 border border-slate-800 rounded px-2.5 py-1 text-xs font-mono text-slate-200"
                        >
                          <option value={1}>1 Trade</option>
                          <option value={2}>2 Trades</option>
                          <option value={3}>3 Trades</option>
                          <option value={5}>5 Trades</option>
                        </select>
                        <button
                          onClick={handleRunAblation}
                          disabled={runningAblation}
                          className="px-3 py-1.5 bg-amber-600 hover:bg-amber-500 text-white text-xs font-medium rounded-lg transition flex items-center gap-1.5 disabled:opacity-50"
                        >
                          {runningAblation ? <RefreshCw size={13} className="animate-spin" /> : <Play size={13} />}
                          Run Ablation
                        </button>
                      </div>
                    </div>

                    {/* Methodological Alert */}
                    <div className="p-3 bg-amber-950/20 border border-amber-500/30 rounded-lg text-xs text-amber-300 leading-relaxed">
                      <span className="font-bold text-amber-200">Critical Methodological Distinction: </span>
                      Removing trades from a report post-hoc does <b>not</b> reproduce the economic reality of changing the portfolio's trading path.
                      A true path-dependent re-simulation recalculates capital constraints, cash compounding, and entry opportunities from that point forward.
                    </div>

                    {ablationResult && (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
                        {/* Post-Hoc Diagnostic Removal */}
                        <div className="p-4 bg-slate-950 rounded-lg border border-slate-800 space-y-3">
                          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                            <span className="text-xs font-bold text-slate-200 uppercase font-mono">
                              1. Diagnostic Post-Hoc Removal
                            </span>
                            <span className="text-[10px] text-amber-400 font-mono">Statistical Heuristic</span>
                          </div>
                          <div className="space-y-2 text-xs font-mono">
                            <div className="flex justify-between">
                              <span className="text-slate-400">Net Profit Drop:</span>
                              <span className="text-rose-400 font-bold">
                                {Number(ablationResult.post_hoc_removal?.profit_drop_pct || 0).toFixed(1)}%
                              </span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-slate-400">Adjusted Profit:</span>
                              <span className="text-slate-200">
                                ₹{Number(ablationResult.post_hoc_removal?.new_net_profit || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                              </span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-slate-400">Adjusted Sharpe:</span>
                              <span className="text-slate-200">
                                {Number(ablationResult.post_hoc_removal?.new_sharpe || 0).toFixed(2)}
                              </span>
                            </div>
                          </div>
                          <p className="text-[11px] text-slate-400 pt-2 border-t border-slate-800">
                            {ablationResult.post_hoc_removal?.explanation}
                          </p>
                        </div>

                        {/* Path-Dependent Portfolio Re-Simulation */}
                        <div className="p-4 bg-slate-950 rounded-lg border border-slate-800 space-y-3">
                          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                            <span className="text-xs font-bold text-emerald-400 uppercase font-mono">
                              2. Path-Dependent Re-Simulation
                            </span>
                            <span className="text-[10px] text-emerald-400 font-mono">Economic Reality</span>
                          </div>
                          <div className="space-y-2 text-xs font-mono">
                            <div className="flex justify-between">
                              <span className="text-slate-400">Net Profit Drop:</span>
                              <span className="text-rose-400 font-bold">
                                {Number(ablationResult.path_dependent_resimulation?.profit_drop_pct || 0).toFixed(1)}%
                              </span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-slate-400">Adjusted Profit:</span>
                              <span className="text-slate-200">
                                ₹{Number(ablationResult.path_dependent_resimulation?.new_net_profit || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                              </span>
                            </div>
                            <div className="flex justify-between">
                              <span className="text-slate-400">Adjusted Sharpe:</span>
                              <span className="text-slate-200">
                                {Number(ablationResult.path_dependent_resimulation?.new_sharpe || 0).toFixed(2)}
                              </span>
                            </div>
                          </div>
                          <p className="text-[11px] text-slate-400 pt-2 border-t border-slate-800">
                            {ablationResult.path_dependent_resimulation?.explanation}
                          </p>
                        </div>
                      </div>
                    )}
                  </div>
                )}

                {/* SubTab 5: Walk-Forward & Friction Stress */}
                {activeSubTab === 'walkforward' && (
                  <div className="space-y-4">
                    {/* Walk-Forward Out-Of-Sample (OOS) Analysis Panel */}
                    <div className="panel bg-slate-900 border border-slate-800 rounded-lg p-5 space-y-4">
                      <div className="flex items-center justify-between">
                        <div>
                          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-200 flex items-center gap-2">
                            <ShieldCheck size={16} className="text-emerald-400" />
                            Walk-Forward Overfitting &amp; Regime Degradation Audit
                          </h3>
                          <p className="text-[11px] text-slate-400 mt-0.5">
                            Strict chronological split. Training end: <span className="font-mono text-slate-300 font-semibold">{walkForward?.train_window?.end_date || 'N/A'}</span>,
                            Test start: <span className="font-mono text-slate-300 font-semibold">{walkForward?.test_window?.start_date || 'N/A'}</span>.
                          </p>
                        </div>

                        <div className="flex items-center gap-2">
                          <span className={`px-2.5 py-1 rounded text-xs font-mono font-semibold border ${
                            walkForward?.overfitting_risk === 'HIGH'
                              ? 'bg-rose-950/60 border-rose-500/40 text-rose-300'
                              : walkForward?.overfitting_risk === 'MODERATE'
                              ? 'bg-amber-950/60 border-amber-500/40 text-amber-300'
                              : 'bg-emerald-950/60 border-emerald-500/40 text-emerald-300'
                          }`}>
                            OVERFIT RISK: {walkForward?.overfitting_risk || 'LOW'}
                          </span>
                        </div>
                      </div>

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {/* Comparative Table */}
                        <div className="overflow-x-auto border border-slate-800 rounded-lg">
                          <table className="w-full text-xs text-left">
                            <thead>
                              <tr className="bg-slate-950 border-b border-slate-800 text-slate-400 font-mono">
                                <th className="py-2 px-3">Metric</th>
                                <th className="py-2 px-3">In-Sample (Train)</th>
                                <th className="py-2 px-3">Out-Of-Sample (Test)</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-800/60 font-mono text-slate-300">
                              <tr>
                                <td className="py-2 px-3 text-slate-400">Cumulative Return</td>
                                <td className="py-2 px-3">{(Number(trainMetrics.cumulative_return || 0) * 100).toFixed(1)}%</td>
                                <td className="py-2 px-3 font-semibold text-slate-100">{(Number(testMetrics.cumulative_return || 0) * 100).toFixed(1)}%</td>
                              </tr>
                              <tr>
                                <td className="py-2 px-3 text-slate-400">Annualized Volatility</td>
                                <td className="py-2 px-3">{(Number(trainMetrics.annualized_volatility || 0) * 100).toFixed(1)}%</td>
                                <td className="py-2 px-3">{(Number(testMetrics.annualized_volatility || 0) * 100).toFixed(1)}%</td>
                              </tr>
                              <tr>
                                <td className="py-2 px-3 text-slate-400">Sharpe Ratio</td>
                                <td className="py-2 px-3">{Number(trainMetrics.sharpe_ratio || 0).toFixed(2)}</td>
                                <td className="py-2 px-3 font-semibold text-slate-100">{Number(testMetrics.sharpe_ratio || 0).toFixed(2)}</td>
                              </tr>
                              <tr>
                                <td className="py-2 px-3 text-slate-400">Max Drawdown</td>
                                <td className="py-2 px-3 text-rose-400">{(Number(trainMetrics.max_drawdown || 0) * 100).toFixed(1)}%</td>
                                <td className="py-2 px-3 text-rose-400">{(Number(testMetrics.max_drawdown || 0) * 100).toFixed(1)}%</td>
                              </tr>
                              <tr>
                                <td className="py-2 px-3 text-slate-400">Win Rate</td>
                                <td className="py-2 px-3">{(Number(trainMetrics.win_rate || 0) * 100).toFixed(1)}%</td>
                                <td className="py-2 px-3">{(Number(testMetrics.win_rate || 0) * 100).toFixed(1)}%</td>
                              </tr>
                            </tbody>
                          </table>
                        </div>

                        {/* Degradation Diagnostics */}
                        <div className="p-4 bg-slate-950 rounded-lg border border-slate-800 space-y-3 flex flex-col justify-between">
                          <div>
                            <span className="text-[10px] font-mono uppercase text-slate-400 block mb-1">
                              Sharpe Ratio Degradation
                            </span>
                            <div className="flex items-baseline gap-2">
                              <span className={`text-2xl font-bold font-mono ${
                                Number(walkForward?.sharpe_degradation_pct || 0) > 30 ? 'text-rose-400' : 'text-emerald-400'
                              }`}>
                                {Number(walkForward?.sharpe_degradation_pct || 0).toFixed(1)}%
                              </span>
                              <span className="text-xs text-slate-400">degradation from in-sample</span>
                            </div>
                          </div>

                          <div className="text-xs text-slate-400 leading-relaxed border-t border-slate-800/80 pt-2">
                            {walkForward?.overfitting_risk === 'HIGH' ? (
                              <span className="text-rose-300">
                                Warning: Severe performance decay detected when transitioning to out-of-sample data.
                                Strategy rules may be overfitted to historical market regimes.
                              </span>
                            ) : (
                              <span className="text-emerald-300">
                                Robust: Strategy maintains structural risk-adjusted performance on unseen forward data
                                without pathological degradation.
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Cost Sensitivity Stress Test Matrix */}
                    <div className="panel bg-slate-900 border border-slate-800 rounded-lg p-5 space-y-3">
                      <div className="flex items-center justify-between">
                        <div>
                          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-200">
                            Friction Stress Testing (Fee &amp; Slippage Sensitivity)
                          </h3>
                          <p className="text-[11px] text-slate-400">
                            Evaluates strategy survivability under escalating real-world execution frictions (0 to 50 bps).
                          </p>
                        </div>
                      </div>

                      <div className="overflow-x-auto">
                        <table className="w-full text-xs text-left border border-slate-800 rounded-lg">
                          <thead>
                            <tr className="bg-slate-950 border-b border-slate-800 text-slate-400 font-mono">
                              <th className="py-2.5 px-3">Friction Level</th>
                              <th className="py-2.5 px-3">Fee / Slippage</th>
                              <th className="py-2.5 px-3">Net Return</th>
                              <th className="py-2.5 px-3">Net Profit</th>
                              <th className="py-2.5 px-3">Sharpe</th>
                              <th className="py-2.5 px-3">Max DD</th>
                              <th className="py-2.5 px-3">Survivability</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-800/60 font-mono text-slate-300">
                            {costStress.map((cs: any, idx: number) => {
                              const frictionTotal = cs.friction_bps ?? cs.total_friction_bps ?? 0;
                              const slip = cs.slippage_bps ?? (frictionTotal / 2);
                              const fee = cs.fee_bps ?? (frictionTotal - slip);
                              const netRet = cs.net_return ?? cs.cumulative_return ?? 0;
                              const netProf = cs.net_profit ?? cs.net_pnl ?? 0;
                              const survives = cs.survives_friction ?? cs.survives_costs ?? false;
                              return (
                                <tr key={idx} className="hover:bg-slate-800/40">
                                  <td className="py-2 px-3 font-semibold text-slate-200">{frictionTotal} bps</td>
                                  <td className="py-2 px-3 text-slate-400">{fee} fee + {slip} slip</td>
                                  <td className={`py-2 px-3 font-semibold ${netRet >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                                    {(netRet * 100).toFixed(1)}%
                                  </td>
                                  <td className="py-2 px-3">
                                    ₹{Number(netProf).toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                                  </td>
                                  <td className="py-2 px-3">{Number(cs.sharpe_ratio || 0).toFixed(2)}</td>
                                  <td className="py-2 px-3 text-rose-400">{(Number(cs.max_drawdown || 0) * 100).toFixed(1)}%</td>
                                  <td className="py-2 px-3">
                                    {survives ? (
                                      <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-950/60 text-emerald-400 border border-emerald-500/30">
                                        SURVIVES
                                      </span>
                                    ) : (
                                      <span className="px-2 py-0.5 rounded text-[10px] bg-rose-950/60 text-rose-400 border border-rose-500/30">
                                        FAILS FRICTION
                                      </span>
                                    )}
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                )}

                {/* SubTab 6: Trade Ledger */}
                {activeSubTab === 'trades' && (
                  <div className="panel bg-slate-900 border border-slate-800 rounded-lg p-5 space-y-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-200 flex items-center gap-2">
                          <FileSpreadsheet size={16} className="text-emerald-400" />
                          Exact Trade Ledger &amp; Cash Reconciliation
                        </h3>
                        <p className="text-[11px] text-slate-400 mt-0.5">
                          {trades.length} completed trade executions with entry/exit timestamps and mathematical fee subtraction.
                        </p>
                      </div>

                      <div className="flex items-center gap-3">
                        {/* Reconciliation Badge */}
                        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-950/50 border border-emerald-500/40 text-emerald-300 text-xs font-mono">
                          <CheckCircle size={14} className="text-emerald-400" />
                          <span>Reconciliation Diff: ₹{Number(reconDiff).toFixed(2)}</span>
                        </div>

                        <button
                          onClick={handleExportTradesCSV}
                          className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium rounded-lg border border-slate-700 transition flex items-center gap-2"
                        >
                          <Download size={13} /> Export Ledger CSV
                        </button>
                      </div>
                    </div>

                    {/* Accounting Summary Bar */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 p-3 bg-slate-950 rounded-lg border border-slate-800 font-mono text-xs">
                      <div>
                        <span className="text-[10px] text-slate-500 block">Initial Capital</span>
                        <span className="text-slate-200 font-semibold">
                          ₹{initialCap.toLocaleString('en-IN')}
                        </span>
                      </div>
                      <div>
                        <span className="text-[10px] text-slate-500 block">Final Terminal Equity</span>
                        <span className="text-slate-200 font-semibold">
                          ₹{finalEquity.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                        </span>
                      </div>
                      <div>
                        <span className="text-[10px] text-slate-500 block">Net Portfolio Profit</span>
                        <span className={netPortfolioProfit >= 0 ? 'text-emerald-400 font-semibold' : 'text-rose-400 font-semibold'}>
                          ₹{netPortfolioProfit.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                        </span>
                      </div>
                      <div>
                        <span className="text-[10px] text-slate-500 block">Sum of Trade Net PnLs</span>
                        <span className="text-slate-200 font-semibold">
                          ₹{sumTradeNetPnl.toLocaleString('en-IN', { maximumFractionDigits: 0 })}
                        </span>
                      </div>
                    </div>

                    {/* Trades Table */}
                    <div className="overflow-x-auto max-h-72 border border-slate-800 rounded-lg">
                      <table className="w-full text-xs text-left">
                        <thead className="sticky top-0 bg-slate-950 border-b border-slate-800 text-slate-400 font-mono">
                          <tr>
                            <th className="py-2 px-3">#</th>
                            <th className="py-2 px-3">Entry</th>
                            <th className="py-2 px-3">Exit</th>
                            <th className="py-2 px-3">Shares</th>
                            <th className="py-2 px-3">Gross P&amp;L</th>
                            <th className="py-2 px-3">Fees &amp; Slip</th>
                            <th className="py-2 px-3">Net P&amp;L</th>
                            <th className="py-2 px-3">Return</th>
                            <th className="py-2 px-3">Days</th>
                            <th className="py-2 px-3">Exit Rationale</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/60 font-mono text-slate-300">
                          {trades.length === 0 ? (
                            <tr>
                              <td colSpan={10} className="py-6 text-center text-slate-500">
                                No trades triggered within this parameter window.
                              </td>
                            </tr>
                          ) : (
                            trades.map((t: any) => (
                              <tr key={t.trade_id} className="hover:bg-slate-800/40">
                                <td className="py-2 px-3 text-slate-500">{t.trade_id}</td>
                                <td className="py-2 px-3">
                                  <div>{t.entry_date}</div>
                                  <div className="text-[10px] text-slate-500">₹{Number(t.entry_price || 0).toFixed(2)}</div>
                                </td>
                                <td className="py-2 px-3">
                                  <div>{t.exit_date}</div>
                                  <div className="text-[10px] text-slate-500">₹{Number(t.exit_price || 0).toFixed(2)}</div>
                                </td>
                                <td className="py-2 px-3">{t.shares}</td>
                                <td className="py-2 px-3">₹{Number(t.gross_pnl || 0).toFixed(0)}</td>
                                <td className="py-2 px-3 text-amber-400/90">-₹{Number(t.exit_fees || 0).toFixed(0)}</td>
                                <td className={`py-2 px-3 font-semibold ${Number(t.net_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                                  ₹{Number(t.net_pnl || 0).toFixed(0)}
                                </td>
                                <td className={`py-2 px-3 ${Number(t.return_pct || 0) >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                                  {(Number(t.return_pct || 0) * 100).toFixed(2)}%
                                </td>
                                <td className="py-2 px-3">{t.holding_bars}</td>
                                <td className="py-2 px-3 text-[11px] text-slate-400">{t.exit_reason}</td>
                              </tr>
                            ))
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
