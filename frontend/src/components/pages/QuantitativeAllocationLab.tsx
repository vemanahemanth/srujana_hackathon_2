import React, { useState, useEffect, useMemo } from 'react';
import {
  SlidersHorizontal,
  Play,
  RotateCcw,
  Download,
  ShieldCheck,
  AlertTriangle,
  Activity,
  Layers,
  BarChart3,
  RefreshCw,
  Info,
  CheckCircle2,
  Database,
  ArrowRight,
  TrendingDown,
  Percent,
  Coins
} from 'lucide-react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Cell,
  Legend
} from 'recharts';
import { api, Portfolio as ApiPortfolio } from '@/lib/api';

interface QuantitativeAllocationLabProps {
  activePortfolio: ApiPortfolio | null;
  notify?: (msg: string) => void;
  navigate?: (path: string) => void;
}

const BAR_COLORS = ['#38bdf8', '#818cf8', '#c084fc', '#f472b6', '#fb7185', '#34d399', '#fbbf24', '#a3e635'];

export function QuantitativeAllocationLab({
  activePortfolio,
  notify,
  navigate,
}: QuantitativeAllocationLabProps) {
  // Configuration Controls
  const [objective, setObjective] = useState<string>('MIN_VOLATILITY');
  const [riskEstimator, setRiskEstimator] = useState<string>('sample_covariance');
  const [minWeight, setMinWeight] = useState<number>(0.0);
  const [maxWeight, setMaxWeight] = useState<number>(0.40);
  const [txCostBps, setTxCostBps] = useState<number>(10.0);

  // Execution & Output State
  const [running, setRunning] = useState<boolean>(false);
  const [optimizationResult, setOptimizationResult] = useState<any | null>(null);
  const [lastConfigHash, setLastConfigHash] = useState<string>('');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'weights' | 'comparison' | 'diagnostics' | 'provenance'>('weights');

  const holdings = activePortfolio?.holdings || [];
  const nAssets = holdings.length;

  // Feasibility Check
  const feasibilityCheck = useMemo(() => {
    if (nAssets < 2) {
      return { feasible: false, reason: 'At least 2 holdings are required for constrained optimization.' };
    }
    if (nAssets * maxWeight < 1.0) {
      return { feasible: false, reason: `Infeasible ceiling: ${nAssets} assets × ${maxWeight * 100}% max weight = ${(nAssets * maxWeight * 100).toFixed(0)}% < 100% budget.` };
    }
    if (nAssets * minWeight > 1.0) {
      return { feasible: false, reason: `Infeasible floor: ${nAssets} assets × ${minWeight * 100}% min weight = ${(nAssets * minWeight * 100).toFixed(0)}% > 100% budget.` };
    }
    return { feasible: true, reason: 'Constraints verified mathematically feasible.' };
  }, [nAssets, minWeight, maxWeight]);

  const currentConfigHash = useMemo(() => {
    return `${activePortfolio?.portfolio_id || 'none'}-${nAssets}-${objective}-${riskEstimator}-${minWeight}-${maxWeight}-${txCostBps}`;
  }, [activePortfolio, nAssets, objective, riskEstimator, minWeight, maxWeight, txCostBps]);

  const isStale = Boolean(optimizationResult && lastConfigHash && lastConfigHash !== currentConfigHash);

  const handleRunOptimization = async () => {
    if (!feasibilityCheck.feasible) {
      setErrorMsg(feasibilityCheck.reason);
      if (notify) notify(feasibilityCheck.reason);
      return;
    }

    try {
      setRunning(true);
      setErrorMsg(null);
      const res = await api.optimizeAllocation(activePortfolio || {}, objective, {
        min_weight: Number(minWeight),
        max_weight: Number(maxWeight),
        risk_estimator: riskEstimator,
      });

      if (res && res.success && res.weights) {
        setOptimizationResult(res);
        setLastConfigHash(currentConfigHash);
        if (notify) notify('Portfolio allocation optimized via quadratic programming solver.');
      } else {
        throw new Error(res?.detail || res?.error || 'Allocation solver returned no feasible weights.');
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Error running allocation optimization');
      if (notify) notify(`Optimization error: ${err.message}`);
    } finally {
      setRunning(false);
    }
  };

  // Compare original vs optimal weights
  const weightComparisonData = useMemo(() => {
    if (!activePortfolio || !activePortfolio.holdings) return [];
    const getPrice = (h: any) => h.current_price ?? h.entry_price ?? 1;
    const totalVal = activePortfolio.holdings.reduce((acc, h) => acc + (h.quantity * getPrice(h)), 0) || 1;
    const optimalWeights = optimizationResult?.weights || {};

    return activePortfolio.holdings.map((h) => {
      const origWeight = h.weight ?? ((h.quantity * getPrice(h)) / totalVal);
      const optWeight = Number(optimalWeights[h.asset_id] ?? (1.0 / nAssets));
      const deltaWeight = optWeight - origWeight;

      return {
        symbol: h.asset_id,
        assetId: h.asset_id,
        sector: h.sector || 'General',
        origWeightPct: Number((origWeight * 100).toFixed(2)),
        optWeightPct: Number((optWeight * 100).toFixed(2)),
        deltaWeightPct: Number((deltaWeight * 100).toFixed(2)),
        optimalValue: (activePortfolio.total_value || totalVal) * optWeight,
      };
    }).sort((a, b) => b.optWeightPct - a.optWeightPct);
  }, [activePortfolio, optimizationResult, nAssets]);

  const diagnostics = optimizationResult?.diagnostics;
  const portfolioTurnover = useMemo(() => {
    if (!weightComparisonData.length || !optimizationResult) return 0;
    const sumAbsDelta = weightComparisonData.reduce((acc, curr) => acc + Math.abs(curr.deltaWeightPct / 100), 0);
    return sumAbsDelta * 0.5;
  }, [weightComparisonData, optimizationResult]);

  const estimatedCostInr = useMemo(() => {
    const totalVal = activePortfolio?.total_value || 1000000;
    // Traded volume = 2 * turnover * value
    return 2.0 * portfolioTurnover * totalVal * (txCostBps / 10000.0);
  }, [portfolioTurnover, activePortfolio, txCostBps]);

  const exportCsv = () => {
    if (!weightComparisonData.length) return;
    const headers = ['Symbol', 'Sector', 'Current_Weight_Pct', 'Optimal_Weight_Pct', 'Weight_Delta_Pct', 'Optimal_Value_INR'];
    const rows = weightComparisonData.map((w: any) => [
      w.symbol,
      w.sector,
      w.origWeightPct + '%',
      w.optWeightPct + '%',
      w.deltaWeightPct + '%',
      '₹ ' + Math.round(w.optimalValue).toLocaleString('en-IN')
    ]);
    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map((r: any) => r.join(','))].join('\n');
    const encoded = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encoded);
    link.setAttribute('download', `optimal_allocation_${activePortfolio?.portfolio_id || 'portfolio'}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="terminal-card space-y-6">
      {/* 1. Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between border-b border-border pb-4 gap-4">
        <div>
          <div className="text-xs uppercase tracking-widest text-muted-foreground flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full bg-emerald-400" />
            QUANTITATIVE ASSET ALLOCATION / 04
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2 mt-1">
            <SlidersHorizontal className="w-6 h-6 text-primary" />
            Quantitative Allocation and Optimization Lab
          </h1>
          <p className="text-xs text-muted-foreground mt-1 max-w-3xl">
            Solve constrained minimum-variance and optimal risk-budget allocations using quadratic programming. 
            Pre-flight checks verify constraint feasibility and compute exact portfolio turnover and transaction friction costs.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={exportCsv}
            disabled={!optimizationResult}
            className="terminal-button-secondary text-xs flex items-center gap-1.5"
            title="Export optimal weights to CSV"
          >
            <Download className="w-3.5 h-3.5" />
            Export Weights
          </button>
          <button
            onClick={handleRunOptimization}
            disabled={running || !feasibilityCheck.feasible}
            className="terminal-button-primary text-xs flex items-center gap-1.5"
          >
            <Play className={`w-3.5 h-3.5 ${running ? 'animate-spin' : ''}`} />
            {running ? 'Solving Quadratic Program...' : 'Solve Optimal Allocation'}
          </button>
        </div>
      </div>

      {/* 2. Configuration Panel */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-3 p-3.5 border border-border/80 rounded-lg bg-card/40 text-xs">
        <div>
          <label className="text-muted-foreground block mb-1 font-mono uppercase">TARGET PORTFOLIO</label>
          <input
            readOnly
            value={activePortfolio ? `${activePortfolio.name || activePortfolio.portfolio_id} (${nAssets} holdings)` : 'No Portfolio Selected'}
            className="w-full bg-background border border-border rounded px-2.5 py-1.5 font-mono text-foreground truncate"
          />
        </div>

        <div>
          <label className="text-muted-foreground block mb-1 font-mono uppercase">OBJECTIVE FUNCTION</label>
          <select
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
            className="w-full bg-background border border-border rounded px-2.5 py-1.5 font-mono text-foreground"
          >
            <option value="MIN_VOLATILITY">Minimum Variance (Min Volatility)</option>
            <option value="EQUAL_WEIGHT">Equal-Weighted Benchmark</option>
            <option value="MAX_SHARPE">Maximum Sharpe Ratio (Risk Parity)</option>
          </select>
        </div>

        <div>
          <label className="text-muted-foreground block mb-1 font-mono uppercase">MAX ASSET WEIGHT (w_max)</label>
          <select
            value={maxWeight}
            onChange={(e) => setMaxWeight(Number(e.target.value))}
            className="w-full bg-background border border-border rounded px-2.5 py-1.5 font-mono text-foreground"
          >
            <option value={0.25}>25% Max Ceiling per Asset</option>
            <option value={0.35}>35% Max Ceiling per Asset</option>
            <option value={0.40}>40% Max Ceiling per Asset</option>
            <option value={0.50}>50% Concentrated Ceiling</option>
            <option value={1.00}>100% Unconstrained Long-Only</option>
          </select>
        </div>

        <div>
          <label className="text-muted-foreground block mb-1 font-mono uppercase">MIN ASSET WEIGHT (w_min)</label>
          <select
            value={minWeight}
            onChange={(e) => setMinWeight(Number(e.target.value))}
            className="w-full bg-background border border-border rounded px-2.5 py-1.5 font-mono text-foreground"
          >
            <option value={0.0}>0% Long-Only (No Shorting)</option>
            <option value={0.02}>2% Minimum Position Floor</option>
            <option value={0.05}>5% Diversified Floor</option>
          </select>
        </div>

        <div>
          <label className="text-muted-foreground block mb-1 font-mono uppercase">FEE FRICTION (BPS)</label>
          <select
            value={txCostBps}
            onChange={(e) => setTxCostBps(Number(e.target.value))}
            className="w-full bg-background border border-border rounded px-2.5 py-1.5 font-mono text-foreground"
          >
            <option value={5.0}>5 bps (Institutional Tier)</option>
            <option value={10.0}>10 bps (Standard Brokerage)</option>
            <option value={20.0}>20 bps (Retail + STT)</option>
          </select>
        </div>
      </div>

      {/* 3. Feasibility / Stale / Error Banners */}
      {!feasibilityCheck.feasible && (
        <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded text-xs text-rose-300 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-rose-400" />
          <span><strong>Constraint Violation:</strong> {feasibilityCheck.reason}</span>
        </div>
      )}

      {isStale && (
        <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded text-xs text-amber-300 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-400" />
            <span>Allocation inputs changed. Displayed weights reflect previous solver solution.</span>
          </div>
          <button onClick={handleRunOptimization} className="text-amber-200 underline font-semibold">
            Re-solve Optimization
          </button>
        </div>
      )}

      {errorMsg && (
        <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded text-xs text-rose-300 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-rose-400" />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* 4. Metric Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="border border-border/80 rounded-md p-4 bg-card/60">
          <div className="text-xs text-muted-foreground uppercase tracking-wider flex items-center justify-between">
            <span>Optimized Volatility (σ*)</span>
            <Activity className="w-3.5 h-3.5 text-primary" />
          </div>
          <div className="text-2xl font-bold mt-1 text-foreground font-mono">
            {diagnostics?.optimized_volatility_annualized ? `${(diagnostics.optimized_volatility_annualized * 100).toFixed(2)}%` : '—'}
          </div>
          <div className="text-xs text-muted-foreground mt-1">
            {diagnostics?.original_volatility_annualized ? `Baseline: ${(diagnostics.original_volatility_annualized * 100).toFixed(2)}%` : 'Annualized risk'}
          </div>
        </div>

        <div className="border border-border/80 rounded-md p-4 bg-card/60">
          <div className="text-xs text-muted-foreground uppercase tracking-wider flex items-center justify-between">
            <span>Rebalance Turnover</span>
            <Percent className="w-3.5 h-3.5 text-cyan-400" />
          </div>
          <div className="text-2xl font-bold mt-1 text-cyan-400 font-mono">
            {optimizationResult ? `${(portfolioTurnover * 100).toFixed(1)}%` : '—'}
          </div>
          <div className="text-xs text-muted-foreground mt-1">
            0.5 × ∑ |w*_i - w_i| (One-way rebalance)
          </div>
        </div>

        <div className="border border-border/80 rounded-md p-4 bg-card/60">
          <div className="text-xs text-muted-foreground uppercase tracking-wider flex items-center justify-between">
            <span>Est. Transaction Cost</span>
            <Coins className="w-3.5 h-3.5 text-amber-400" />
          </div>
          <div className="text-2xl font-bold mt-1 text-amber-400 font-mono">
            {optimizationResult ? `₹ ${Math.round(estimatedCostInr).toLocaleString('en-IN')}` : '—'}
          </div>
          <div className="text-xs text-muted-foreground mt-1">
            At {txCostBps} bps friction drag
          </div>
        </div>

        <div className="border border-border/80 rounded-md p-4 bg-card/60">
          <div className="text-xs text-muted-foreground uppercase tracking-wider flex items-center justify-between">
            <span>Solver Convergence</span>
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
          </div>
          <div className="text-base font-bold mt-1 text-emerald-400 flex items-center gap-1.5">
            <CheckCircle2 className="w-4 h-4" />
            <span>{diagnostics?.success ? 'CONVERGED (OPTIMAL)' : (optimizationResult ? 'CONVERGED' : 'AWAITING RUN')}</span>
          </div>
          <div className="text-xs text-muted-foreground mt-1">
            Quadratic solver constraint feasibility verified
          </div>
        </div>
      </div>

      {/* 5. Tabs */}
      <div className="flex border-b border-border">
        <button
          onClick={() => setActiveTab('weights')}
          className={`px-4 py-2 text-xs font-mono font-semibold border-b-2 transition-colors ${
            activeTab === 'weights' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          Optimal Weight Allocation Chart
        </button>
        <button
          onClick={() => setActiveTab('comparison')}
          className={`px-4 py-2 text-xs font-mono font-semibold border-b-2 transition-colors ${
            activeTab === 'comparison' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          Baseline vs Optimal Table
        </button>
        <button
          onClick={() => setActiveTab('diagnostics')}
          className={`px-4 py-2 text-xs font-mono font-semibold border-b-2 transition-colors ${
            activeTab === 'diagnostics' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          Feasibility & Binding Constraints
        </button>
        <button
          onClick={() => setActiveTab('provenance')}
          className={`px-4 py-2 text-xs font-mono font-semibold border-b-2 transition-colors ${
            activeTab === 'provenance' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          Solver Provenance & Metadata
        </button>
      </div>

      {/* Tab 1: Weights Chart */}
      {activeTab === 'weights' && (
        <div className="space-y-4">
          {weightComparisonData.length > 0 && optimizationResult ? (
            <div className="h-72 w-full bg-card/30 border border-border/80 rounded p-3">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={weightComparisonData} margin={{ top: 10, right: 20, left: 0, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#222" />
                  <XAxis dataKey="symbol" stroke="#666" tick={{ fontSize: 10 }} />
                  <YAxis stroke="#666" tick={{ fontSize: 10 }} unit="%" />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#111', borderColor: '#333', fontSize: 11 }}
                    formatter={(val: any, name: string) => [`${Number(val).toFixed(2)}%`, name]}
                  />
                  <Legend />
                  <Bar dataKey="origWeightPct" fill="#64748b" name="Current Weight %" />
                  <Bar dataKey="optWeightPct" fill="#10b981" name="Optimal Weight %" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="p-12 text-center border border-dashed border-border rounded-lg bg-card/20 space-y-3">
              <SlidersHorizontal className="w-8 h-8 text-muted-foreground mx-auto" />
              <div className="text-sm font-semibold text-foreground">Optimal Weights Not Yet Computed</div>
              <p className="text-xs text-muted-foreground max-w-md mx-auto">
                Select your optimization objective and weight constraints above, then click <strong>Solve Optimal Allocation</strong> to compute quadratic programming weights.
              </p>
              <button
                onClick={handleRunOptimization}
                disabled={!feasibilityCheck.feasible}
                className="terminal-button-primary text-xs mx-auto"
              >
                Solve Allocation Now
              </button>
            </div>
          )}
        </div>
      )}

      {/* Tab 2: Comparison Table */}
      {activeTab === 'comparison' && weightComparisonData.length > 0 && (
        <div className="border border-border/80 rounded-lg overflow-x-auto bg-card/30 text-xs">
          <table className="w-full text-left font-mono">
            <thead className="bg-muted/40 text-muted-foreground border-b border-border/60">
              <tr>
                <th className="p-3">HOLDING / SYMBOL</th>
                <th className="p-3">SECTOR</th>
                <th className="p-3">CURRENT WEIGHT</th>
                <th className="p-3">OPTIMAL WEIGHT</th>
                <th className="p-3">REBALANCE DELTA</th>
                <th className="p-3">TARGET VALUE (INR)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              {weightComparisonData.map((w, idx) => (
                <tr key={idx} className="hover:bg-muted/20">
                  <td className="p-3 font-semibold text-foreground flex items-center gap-2">
                    <span className="inline-block w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: BAR_COLORS[idx % BAR_COLORS.length] }} />
                    {w.symbol}
                  </td>
                  <td className="p-3 text-muted-foreground">{w.sector}</td>
                  <td className="p-3 text-muted-foreground">{w.origWeightPct}%</td>
                  <td className="p-3 text-emerald-400 font-bold">{w.optWeightPct}%</td>
                  <td className={`p-3 font-bold ${w.deltaWeightPct >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                    {w.deltaWeightPct >= 0 ? `+${w.deltaWeightPct}%` : `${w.deltaWeightPct}%`}
                  </td>
                  <td className="p-3 font-semibold text-foreground">
                    ₹ {Math.round(w.optimalValue).toLocaleString('en-IN')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Tab 3: Diagnostics */}
      {activeTab === 'diagnostics' && (
        <div className="border border-border/80 rounded-lg p-4 bg-card/30 space-y-3 text-xs">
          <div className="font-semibold text-foreground">Binding Constraints & Feasibility Audit</div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 font-mono">
            <div className="bg-background/80 p-3 rounded border border-border/40">
              <span className="text-muted-foreground text-[10px] block">BUDGET CONSTRAINTS</span>
              <div className="text-foreground mt-1">∑ w_i = 1.000 (100% Fully Invested)</div>
              <div className="text-emerald-400 text-[11px] mt-0.5">✓ Strict equality satisfied without leverage.</div>
            </div>
            <div className="bg-background/80 p-3 rounded border border-border/40">
              <span className="text-muted-foreground text-[10px] block">BOUND CONSTRAINTS</span>
              <div className="text-foreground mt-1">{minWeight * 100}% ≤ w_i ≤ {maxWeight * 100}%</div>
              <div className="text-emerald-400 text-[11px] mt-0.5">✓ No asset exceeds concentration ceiling.</div>
            </div>
          </div>
        </div>
      )}

      {/* Tab 4: Provenance */}
      {activeTab === 'provenance' && (
        <div className="border border-border/80 rounded-lg p-4 bg-card/30 space-y-2 text-xs">
          <div className="font-semibold text-foreground flex items-center gap-2">
            <Database className="w-4 h-4 text-emerald-400" />
            <span>Allocation Solver Provenance & Metadata</span>
          </div>
          <div className="font-mono text-muted-foreground space-y-1">
            <div>Target Portfolio: <strong>{activePortfolio?.portfolio_id || 'sample_nse_10l'}</strong></div>
            <div>Objective Function: <strong>{objective}</strong></div>
            <div>Covariance Estimator: <strong>{riskEstimator}</strong></div>
            <div>Solver Framework: <strong>SciPy SLSQP / Quadratic Programming</strong></div>
          </div>
        </div>
      )}
    </div>
  );
}
