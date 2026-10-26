import React, { useState, useEffect, useMemo } from 'react';
import {
  Sparkles,
  Play,
  RotateCcw,
  Download,
  ShieldCheck,
  AlertTriangle,
  Activity,
  Sliders,
  TrendingUp,
  Layers,
  CheckCircle2,
  FileSpreadsheet,
  Info,
  ChevronRight,
  Zap,
  BarChart2,
  Scale,
  RefreshCw,
  Hash
} from 'lucide-react';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
  ReferenceLine
} from 'recharts';
import { api } from '@/lib/api';

const DATASETS = [
  { symbol: 'RELIANCE', name: 'Reliance Industries Ltd. (NSE)' },
  { symbol: 'NIFTY 50', name: 'Nifty 50 Index (NSE)' },
  { symbol: 'TCS', name: 'Tata Consultancy Services (NSE)' },
  { symbol: 'INFY', name: 'Infosys Limited (NSE)' },
];

export function MonteCarloSimulationLab({
  navigate,
  notify,
}: {
  navigate?: (path: string) => void;
  notify?: (msg: string) => void;
}) {
  const [marketInstruments, setMarketInstruments] = useState(DATASETS);
  const [selectedSymbol, setSelectedSymbol] = useState<string>('RELIANCE');

  useEffect(() => {
    api.listMarketInstruments().then((res: any) => {
      if (res?.instruments && res.instruments.length > 0) {
        setMarketInstruments(res.instruments.map((i: any) => ({
          symbol: i.symbol,
          name: `${i.name} (${i.exchange || "NSE"})`
        })));
      }
    }).catch(() => {});
  }, []);
  const [initialValue, setInitialValue] = useState<number>(1000000);
  const [method, setMethod] = useState<string>('student_t');
  const [degreesOfFreedom, setDegreesOfFreedom] = useState<number>(5);
  const [numPaths, setNumPaths] = useState<number>(500);
  const [horizonDays, setHorizonDays] = useState<number>(60);
  const [seed, setSeed] = useState<number>(42);
  const [drawdownThresholdPct, setDrawdownThresholdPct] = useState<number>(15.0);

  const [running, setRunning] = useState<boolean>(false);
  const [result, setResult] = useState<any | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [lastRunConfig, setLastRunConfig] = useState<any | null>(null);
  const [isRandomSeed, setIsRandomSeed] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'fan' | 'distribution' | 'convergence' | 'parameters'>('fan');

  const handleRandomizeSeed = () => {
    const newSeed = Math.floor(Math.random() * 1000000);
    setSeed(newSeed);
    setIsRandomSeed(true);
    if (notify) notify(`Random seed updated to ${newSeed}.`);
  };

  const isStale = useMemo(() => {
    if (!lastRunConfig) return false;
    return (
      lastRunConfig.symbol !== selectedSymbol ||
      lastRunConfig.initial_value !== initialValue ||
      lastRunConfig.num_paths !== numPaths ||
      lastRunConfig.horizon_days !== horizonDays ||
      lastRunConfig.method !== method ||
      (method === 'student_t' && lastRunConfig.degrees_of_freedom !== degreesOfFreedom) ||
      lastRunConfig.seed !== seed ||
      lastRunConfig.drawdown_threshold_pct !== drawdownThresholdPct
    );
  }, [lastRunConfig, selectedSymbol, initialValue, numPaths, horizonDays, method, degreesOfFreedom, seed, drawdownThresholdPct]);

  const handleRunSimulation = async () => {
    try {
      setRunning(true);
      setErrorMsg(null);
      const params = {
        symbol: selectedSymbol,
        initial_value: Number(initialValue),
        num_paths: Number(numPaths),
        horizon_days: Number(horizonDays),
        method: method,
        degrees_of_freedom: Number(degreesOfFreedom),
        seed: Number(seed),
        drawdown_threshold_pct: Number(drawdownThresholdPct),
      };

      const res = await api.runMonteCarloLab(params);
      if (res && res.success) {
        setResult(res);
        setRunId((res as any).run_id || `mc_${Date.now()}_seed${seed}_${selectedSymbol}`);
        setLastRunConfig({ ...params });
        if (notify) notify(`Monte Carlo simulation complete: ${numPaths} paths evaluated.`);
      } else {
        throw new Error('Simulation returned an incomplete response.');
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Error running Monte Carlo simulation');
      if (notify) notify(`Simulation error: ${err.message}`);
    } finally {
      setRunning(false);
    }
  };

  // Run on mount
  useEffect(() => {
    handleRunSimulation();
  }, [selectedSymbol]);

  // Format Fan Chart Data
  const fanChartData = useMemo(() => {
    if (!result || !result.percentile_bands) return [];
    const pb = result.percentile_bands;
    const timeGrid = pb.time_grid || [];
    const len = pb.p50th_median ? pb.p50th_median.length : 0;

    return Array.from({ length: len }, (_, i) => {
      const row: Record<string, any> = {
        step: timeGrid[i] ?? i,
        day: `T+${timeGrid[i] ?? i}`,
        p5th: pb.p5th ? pb.p5th[i] : null,
        p25th: pb.p25th ? pb.p25th[i] : null,
        median: pb.p50th_median ? pb.p50th_median[i] : null,
        p75th: pb.p75th ? pb.p75th[i] : null,
        p95th: pb.p95th ? pb.p95th[i] : null,
      };

      // Add sample trajectories
      if (result.sample_trajectories) {
        result.sample_trajectories.slice(0, 4).forEach((traj: any, tIdx: number) => {
          if (traj.values && traj.values[i] !== undefined) {
            row[`sample_${tIdx + 1}`] = traj.values[i];
          }
        });
      }

      return row;
    });
  }, [result]);

  // Export CSV
  const handleExportCSV = () => {
    if (!result || !result.percentile_bands) return;
    const pb = result.percentile_bands;
    const headers = ['Day', 'P5th', 'P25th', 'Median', 'P75th', 'P95th'];
    const rows = pb.p50th_median.map((_: any, i: number) => [
      `T+${i}`,
      pb.p5th[i],
      pb.p25th[i],
      pb.p50th_median[i],
      pb.p75th[i],
      pb.p95th[i],
    ]);
    const csvContent =
      'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map((e: any[]) => e.join(','))].join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `monte_carlo_${selectedSymbol}_trajectories.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    if (notify) notify('Monte Carlo trajectories exported to CSV.');
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between pb-4 border-b border-[var(--color-border-subtle)] gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-mono text-[var(--color-accent)] uppercase tracking-wider mb-1">
            <Sparkles className="w-3.5 h-3.5" />
            <span>FragilityShield Research Lab / Page 18</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-[var(--color-text-main)]">
            Monte Carlo Simulation Lab
          </h1>
          <p className="text-sm text-[var(--color-text-muted)] mt-0.5">
            Path-dependent stochastic simulation across parametric Gaussian, fat-tailed Student-t, historical resampling, and Markov regime-switching processes with strict seed reproducibility.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {result && (
            <button
              onClick={handleExportCSV}
              className="btn btn-secondary flex items-center gap-1.5 text-xs font-mono"
            >
              <Download className="w-3.5 h-3.5" />
              Export Paths CSV
            </button>
          )}
          <button
            onClick={handleRunSimulation}
            disabled={running}
            className="btn btn-primary flex items-center gap-2 text-xs font-mono"
          >
            {running ? (
              <>
                <RotateCcw className="w-3.5 h-3.5 animate-spin" />
                Simulating...
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5" />
                Run Simulation ({numPaths} Paths)
              </>
            )}
          </button>
        </div>
      </div>

      {errorMsg && (
        <div className="p-3 bg-red-950/40 border border-red-700/60 rounded flex items-center gap-3 text-red-200 text-sm">
          <AlertTriangle className="w-4 h-4 text-red-400 shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Control Configuration Grid */}
      <div className="panel p-4 space-y-4">
        <div className="flex items-center justify-between border-b border-[var(--color-border-subtle)] pb-2">
          <div className="flex items-center gap-2 font-mono text-sm text-[var(--color-text-main)] font-semibold">
            <Sliders className="w-4 h-4 text-[var(--color-accent)]" />
            Simulation Parameters & Stochastic Calibration
          </div>
          <span className="badge text-[10px] bg-[var(--color-bg-subtle)] text-[var(--color-text-muted)]">
            DETERMINISTIC RNG
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 text-xs">
          <div>
            <label className="block text-[var(--color-text-muted)] font-mono mb-1">DATASET / INSTRUMENT</label>
            <select
              value={selectedSymbol}
              onChange={(e) => setSelectedSymbol(e.target.value)}
              className="input w-full font-mono text-xs"
            >
              {marketInstruments.map((d) => (
                <option key={d.symbol} value={d.symbol}>
                  {d.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-[var(--color-text-muted)] font-mono mb-1">STOCHASTIC MODEL</label>
            <select
              value={method}
              onChange={(e) => setMethod(e.target.value)}
              className="input w-full font-mono text-xs"
            >
              <option value="student_t">Student-t (Fat-Tailed / Kurtosis)</option>
              <option value="parametric_gaussian">Parametric Gaussian (GBM)</option>
              <option value="historical_resampling">Non-Parametric Bootstrap</option>
              <option value="regime_switching">Markov Regime Switching (2-State)</option>
            </select>
          </div>

          {method === 'student_t' && (
            <div>
              <label className="block text-[var(--color-text-muted)] font-mono mb-1">DEGREES OF FREEDOM (ν)</label>
              <input
                type="number"
                value={degreesOfFreedom}
                onChange={(e) => setDegreesOfFreedom(parseInt(e.target.value) || 4)}
                className="input w-full font-mono text-xs"
                min="3"
                max="30"
              />
            </div>
          )}

          <div>
            <label className="block text-[var(--color-text-muted)] font-mono mb-1">INITIAL CAPITAL (₹)</label>
            <input
              type="number"
              value={initialValue}
              onChange={(e) => setInitialValue(parseFloat(e.target.value) || 1000000)}
              className="input w-full font-mono text-xs"
              step="50000"
            />
          </div>

          <div>
            <label className="block text-[var(--color-text-muted)] font-mono mb-1">NUMBER OF PATHS</label>
            <input
              type="number"
              value={numPaths}
              onChange={(e) => setNumPaths(parseInt(e.target.value) || 100)}
              className="input w-full font-mono text-xs"
              min="50"
              max="2000"
              step="50"
            />
          </div>

          <div>
            <label className="block text-[var(--color-text-muted)] font-mono mb-1">HORIZON (TRADING DAYS)</label>
            <input
              type="number"
              value={horizonDays}
              onChange={(e) => setHorizonDays(parseInt(e.target.value) || 20)}
              className="input w-full font-mono text-xs"
              min="5"
              max="252"
              step="5"
            />
          </div>

          <div>
            <label className="block text-[var(--color-text-muted)] font-mono mb-1">MAX DRAWDOWN THRESHOLD %</label>
            <input
              type="number"
              value={drawdownThresholdPct}
              onChange={(e) => setDrawdownThresholdPct(parseFloat(e.target.value) || 15)}
              className="input w-full font-mono text-xs"
              min="5"
              max="50"
              step="1"
            />
          </div>

          <div>
            <label className="block text-[var(--color-text-muted)] font-mono mb-1 flex items-center justify-between">
              <span>RANDOM SEED</span>
              <button
                type="button"
                onClick={handleRandomizeSeed}
                className="text-[var(--color-accent)] hover:underline flex items-center gap-1"
              >
                <RefreshCw className="w-2.5 h-2.5" /> Randomize
              </button>
            </label>
            <input
              type="number"
              value={seed}
              onChange={(e) => setSeed(parseInt(e.target.value) || 42)}
              className="input w-full font-mono text-xs"
            />
          </div>
        </div>
      </div>

      {/* Stale Results Warning */}
      {isStale && (
        <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded text-xs text-amber-300 flex items-center justify-between font-mono">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
            <span>Configuration changed. Displayed metrics correspond to Run ID: {runId || 'previous run'}. Click "Run Simulation" to execute with updated parameters.</span>
          </div>
          <button onClick={handleRunSimulation} className="text-amber-200 underline font-bold hover:text-amber-100">
            Re-run Simulation
          </button>
        </div>
      )}

      {/* Execution Provenance & Integrity Bar */}
      {result && (
        <div className="p-2.5 bg-[var(--color-bg-subtle)] border border-[var(--color-border-subtle)] rounded text-xs font-mono flex flex-wrap items-center justify-between gap-3 text-[var(--color-text-muted)]">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1.5 text-[var(--color-text-main)] font-semibold">
              <Hash className="w-3.5 h-3.5 text-[var(--color-accent)]" />
              Run ID: <span className="text-[var(--color-accent)]">{runId || result.run_id || 'mc_active'}</span>
            </span>
            <span>Paths Generated: <strong className="text-[var(--color-text-main)]">{result.paths_generated || numPaths}</strong></span>
            <span>Horizon: <strong className="text-[var(--color-text-main)]">{horizonDays}d</strong></span>
            <span>Model: <strong className="text-[var(--color-text-main)]">{method}</strong></span>
          </div>
          <div className="flex items-center gap-2">
            <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${isRandomSeed ? 'bg-purple-950/60 text-purple-300 border border-purple-700/60' : 'bg-emerald-950/60 text-emerald-300 border border-emerald-700/60'}`}>
              {isRandomSeed ? '🎲 RANDOMIZED SEED' : '🔒 SEEDED DETERMINISTIC (REPRODUCIBLE)'}
            </span>
            <span className="text-[11px]">Seed: {seed}</span>
          </div>
        </div>
      )}

      {/* Main Results Display */}
      {result ? (
        <div className="space-y-6">
          {/* Top KPI Cards */}
          <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
            <div className="panel p-3">
              <div className="text-[10px] font-mono text-[var(--color-text-muted)]">MEDIAN TERMINAL</div>
              <div className="text-base font-bold font-mono text-[var(--color-text-main)] mt-1">
                ₹{result.terminal_metrics?.median_terminal_value?.toLocaleString()}
              </div>
              <div className="text-[10px] text-[var(--color-text-muted)] mt-0.5">
                Mean: ₹{result.terminal_metrics?.mean_terminal_value?.toLocaleString()}
              </div>
            </div>

            <div className="panel p-3">
              <div className="text-[10px] font-mono text-[var(--color-text-muted)]">PROBABILITY OF LOSS</div>
              <div
                className={`text-base font-bold font-mono mt-1 ${
                  result.terminal_metrics?.prob_loss_pct > 50 ? 'text-red-400' : 'text-emerald-400'
                }`}
              >
                {result.terminal_metrics?.prob_loss_pct}%
              </div>
              <div className="text-[10px] text-[var(--color-text-muted)] mt-0.5">
                Terminal value &lt; Initial
              </div>
            </div>

            <div className="panel p-3">
              <div className="text-[10px] font-mono text-[var(--color-text-muted)]">
                DD BREACH (&gt;{drawdownThresholdPct}%)
              </div>
              <div
                className={`text-base font-bold font-mono mt-1 ${
                  result.terminal_metrics?.prob_drawdown_breach_pct > 25 ? 'text-red-400' : 'text-amber-400'
                }`}
              >
                {result.terminal_metrics?.prob_drawdown_breach_pct}%
              </div>
              <div className="text-[10px] text-[var(--color-text-muted)] mt-0.5">
                Path max drawdown breach
              </div>
            </div>

            <div className="panel p-3">
              <div className="text-[10px] font-mono text-[var(--color-text-muted)]">95% TERMINAL VAR</div>
              <div className="text-base font-bold font-mono text-red-400 mt-1">
                {result.terminal_metrics?.value_at_risk_95_pct}%
              </div>
              <div className="text-[10px] text-[var(--color-text-muted)] mt-0.5">
                99% VaR: {result.terminal_metrics?.value_at_risk_99_pct}%
              </div>
            </div>

            <div className="panel p-3">
              <div className="text-[10px] font-mono text-[var(--color-text-muted)]">95% EXPECTED SHORTFALL</div>
              <div className="text-base font-bold font-mono text-red-400 mt-1">
                {result.terminal_metrics?.expected_shortfall_95_pct}%
              </div>
              <div className="text-[10px] text-[var(--color-text-muted)] mt-0.5">
                Conditional tail expectation
              </div>
            </div>

            <div className="panel p-3">
              <div className="text-[10px] font-mono text-[var(--color-text-muted)]">MONTE CARLO STD ERR</div>
              <div className="text-base font-bold font-mono text-[var(--color-accent)] mt-1">
                ±₹{result.terminal_metrics?.monte_carlo_standard_error?.toLocaleString()}
              </div>
              <div className="text-[10px] text-[var(--color-text-muted)] mt-0.5">
                σ / √{numPaths} error bound
              </div>
            </div>
          </div>

          {/* Tab Navigation */}
          <div className="flex items-center gap-2 border-b border-[var(--color-border-subtle)] pb-2">
            <button
              onClick={() => setActiveTab('fan')}
              className={`px-3 py-1.5 text-xs font-mono rounded transition-colors ${
                activeTab === 'fan'
                  ? 'bg-[var(--color-accent)] text-black font-semibold'
                  : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-main)]'
              }`}
            >
              Fan Chart & Percentile Bands
            </button>
            <button
              onClick={() => setActiveTab('distribution')}
              className={`px-3 py-1.5 text-xs font-mono rounded transition-colors ${
                activeTab === 'distribution'
                  ? 'bg-[var(--color-accent)] text-black font-semibold'
                  : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-main)]'
              }`}
            >
              Terminal Value Distribution
            </button>
            <button
              onClick={() => setActiveTab('convergence')}
              className={`px-3 py-1.5 text-xs font-mono rounded transition-colors ${
                activeTab === 'convergence'
                  ? 'bg-[var(--color-accent)] text-black font-semibold'
                  : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-main)]'
              }`}
            >
              Convergence Diagnostics
            </button>
            <button
              onClick={() => setActiveTab('parameters')}
              className={`px-3 py-1.5 text-xs font-mono rounded transition-colors ${
                activeTab === 'parameters'
                  ? 'bg-[var(--color-accent)] text-black font-semibold'
                  : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-main)]'
              }`}
            >
              Calibration & Reproducibility
            </button>
          </div>

          {/* Tab 1: Fan Chart */}
          {activeTab === 'fan' && (
            <div className="panel p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-mono text-xs font-semibold text-[var(--color-text-main)]">
                    SIMULATED EQUITY FAN CHART (5TH TO 95TH PERCENTILE ENVELOPE)
                  </h3>
                  <p className="text-[11px] text-[var(--color-text-muted)]">
                    Shaded bands represent 5th–95th and 25th–75th interquartile confidence ranges with overlaid sample trajectories.
                  </p>
                </div>
                <span className="badge text-[10px] bg-slate-800 text-slate-300">
                  {numPaths} TRAJECTORIES
                </span>
              </div>

              <div className="h-80">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={fanChartData} margin={{ top: 10, right: 30, left: 20, bottom: 0 }}>
                    <defs>
                      <linearGradient id="p95Band" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#257d70" stopOpacity={0.25} />
                        <stop offset="95%" stopColor="#257d70" stopOpacity={0.02} />
                      </linearGradient>
                      <linearGradient id="p75Band" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#257d70" stopOpacity={0.45} />
                        <stop offset="95%" stopColor="#257d70" stopOpacity={0.10} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#262626" />
                    <XAxis dataKey="day" stroke="#666" fontSize={11} />
                    <YAxis
                      domain={['auto', 'auto']}
                      tickFormatter={(v) => `₹${(v / 1000).toFixed(0)}k`}
                      stroke="#666"
                      fontSize={11}
                    />
                    <Tooltip
                      formatter={(val: any) => [`₹${Number(val).toLocaleString()}`, '']}
                      contentStyle={{ backgroundColor: '#141414', borderColor: '#333' }}
                    />
                    <ReferenceLine y={initialValue} stroke="#666" strokeDasharray="3 3" label="Initial Capital" />

                    {/* Outer 90% Confidence Band (5th to 95th) */}
                    <Area
                      type="monotone"
                      dataKey="p95th"
                      stroke="#257d70"
                      strokeWidth={1}
                      fill="url(#p95Band)"
                      name="95th Percentile"
                    />
                    <Area
                      type="monotone"
                      dataKey="p75th"
                      stroke="#257d70"
                      strokeWidth={1}
                      fill="url(#p75Band)"
                      name="75th Percentile"
                    />
                    <Line
                      type="monotone"
                      dataKey="median"
                      stroke="#f59e0b"
                      strokeWidth={2}
                      dot={false}
                      name="Median (50th)"
                    />
                    <Area
                      type="monotone"
                      dataKey="p25th"
                      stroke="#257d70"
                      strokeWidth={1}
                      fill="none"
                      name="25th Percentile"
                    />
                    <Area
                      type="monotone"
                      dataKey="p5th"
                      stroke="#257d70"
                      strokeWidth={1}
                      fill="none"
                      name="5th Percentile"
                    />

                    {/* Sample Trajectory Overlays */}
                    <Line
                      type="monotone"
                      dataKey="sample_1"
                      stroke="#94a3b8"
                      strokeWidth={1}
                      strokeDasharray="2 2"
                      dot={false}
                      name="Sample Path 1"
                    />
                    <Line
                      type="monotone"
                      dataKey="sample_2"
                      stroke="#38bdf8"
                      strokeWidth={1}
                      strokeDasharray="2 2"
                      dot={false}
                      name="Sample Path 2"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Tab 2: Terminal Distribution */}
          {activeTab === 'distribution' && (
            <div className="panel p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-mono text-xs font-semibold text-[var(--color-text-main)]">
                    TERMINAL PORTFOLIO VALUE DENSITY (HORIZON: {horizonDays} DAYS)
                  </h3>
                  <p className="text-[11px] text-[var(--color-text-muted)]">
                    Empirical outcome distribution across {numPaths} paths with initial investment threshold.
                  </p>
                </div>
                <span className="badge text-[10px] bg-slate-800 text-slate-300">HISTOGRAM</span>
              </div>

              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={result.distribution_histogram} margin={{ top: 10, right: 30, left: 20, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#262626" />
                    <XAxis
                      dataKey="bin_mid"
                      tickFormatter={(v) => `₹${(v / 1000).toFixed(0)}k`}
                      stroke="#666"
                      fontSize={10}
                    />
                    <YAxis stroke="#666" fontSize={11} label={{ value: 'Paths Count', angle: -90, position: 'insideLeft', fill: '#888' }} />
                    <Tooltip
                      formatter={(val: any) => [`${val} paths`, 'Count']}
                      labelFormatter={(label) => `Midpoint: ₹${Number(label).toLocaleString()}`}
                      contentStyle={{ backgroundColor: '#141414', borderColor: '#333' }}
                    />
                    <ReferenceLine x={initialValue} stroke="#ef4444" strokeDasharray="3 3" label="Initial Capital" />
                    <Bar dataKey="count" fill="#257d70" radius={[2, 2, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Tab 3: Convergence Diagnostics */}
          {activeTab === 'convergence' && (
            <div className="panel p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-mono text-xs font-semibold text-[var(--color-text-main)]">
                    ESTIMATION CONVERGENCE & STANDARD ERROR DECAY
                  </h3>
                  <p className="text-[11px] text-[var(--color-text-muted)]">
                    Stability trace confirming running mean and running 95% VaR stabilize as path sample size scales.
                  </p>
                </div>
                <span className="badge text-[10px] bg-slate-800 text-slate-300">
                  MC ERROR: ±₹{result.terminal_metrics?.monte_carlo_standard_error}
                </span>
              </div>

              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={result.convergence_trace} margin={{ top: 10, right: 30, left: 20, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#262626" />
                    <XAxis dataKey="paths_evaluated" stroke="#666" fontSize={11} label={{ value: 'Paths Evaluated', position: 'insideBottom', offset: -5, fill: '#888' }} />
                    <YAxis yAxisId="left" stroke="#666" fontSize={11} tickFormatter={(v) => `₹${(v / 1000).toFixed(0)}k`} />
                    <YAxis yAxisId="right" orientation="right" stroke="#ef4444" fontSize={11} tickFormatter={(v) => `${v}%`} />
                    <Tooltip contentStyle={{ backgroundColor: '#141414', borderColor: '#333' }} />
                    <Legend />
                    <Line
                      yAxisId="left"
                      type="monotone"
                      dataKey="running_mean_value"
                      stroke="#257d70"
                      strokeWidth={2}
                      dot={{ r: 2 }}
                      name="Running Mean (₹)"
                    />
                    <Line
                      yAxisId="right"
                      type="monotone"
                      dataKey="running_var_95_pct"
                      stroke="#ef4444"
                      strokeWidth={1.5}
                      dot={false}
                      name="Running 95% VaR (%)"
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}

          {/* Tab 4: Parameters & Reproducibility */}
          {activeTab === 'parameters' && (
            <div className="panel p-4 space-y-4 font-mono text-xs">
              <div className="flex items-center gap-2 border-b border-[var(--color-border-subtle)] pb-2 font-semibold text-[var(--color-text-main)]">
                <ShieldCheck className="w-4 h-4 text-emerald-400" />
                Empirical Calibration & Cryptographic Reproducibility
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-3 bg-[var(--color-bg-subtle)] rounded border border-[var(--color-border-subtle)] space-y-2">
                  <div className="font-semibold text-[var(--color-text-main)]">
                    Calibrated Market Parameters (From {selectedSymbol})
                  </div>
                  <div className="space-y-1 text-[var(--color-text-muted)] text-[11px]">
                    <div>Historical Sessions: {result.calibration?.historical_observations_count}</div>
                    <div>Daily Drift (μ): {result.calibration?.daily_drift_pct}% (Ann: {result.calibration?.annualized_drift_pct}%)</div>
                    <div>Daily Volatility (σ): {result.calibration?.daily_volatility_pct}% (Ann: {result.calibration?.annualized_volatility_pct}%)</div>
                    <div>Stochastic Model: {result.method_description}</div>
                  </div>
                </div>

                <div className="p-3 bg-[var(--color-bg-subtle)] rounded border border-[var(--color-border-subtle)] space-y-2">
                  <div className="font-semibold text-[var(--color-text-main)]">
                    Audit Fingerprint & Seed Lock
                  </div>
                  <div className="space-y-1 text-[var(--color-text-muted)] text-[11px]">
                    <div>Seed: {result.reproducibility?.random_seed}</div>
                    <div className="truncate">Digest: {result.reproducibility?.simulation_fingerprint}</div>
                    <div>Execution Latency: {result.execution_time_ms} ms</div>
                    <div className="text-amber-400/90 text-[10px] mt-2">
                      {result.reproducibility?.methodology_disclaimer}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="panel py-16 text-center space-y-3">
          <Sparkles className="w-10 h-10 text-[var(--color-text-muted)] mx-auto opacity-40" />
          <h3 className="text-base font-semibold text-[var(--color-text-main)]">
            Monte Carlo Engine Ready
          </h3>
          <p className="text-xs text-[var(--color-text-muted)] max-w-md mx-auto">
            Configure parameters above and click &quot;Run Simulation&quot; to generate path-dependent stochastic trajectories.
          </p>
        </div>
      )}
    </div>
  );
}
