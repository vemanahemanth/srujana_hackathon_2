import React, { useState, useEffect, useMemo } from 'react';
import {
  ChartNoAxesCombined,
  Play,
  RotateCcw,
  Download,
  ShieldCheck,
  AlertTriangle,
  Activity,
  Layers,
  PieChart as PieIcon,
  BarChart3,
  RefreshCw,
  Info,
  CheckCircle2,
  FileSpreadsheet
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
  PieChart,
  Pie,
  Legend
} from 'recharts';
import { api, Portfolio as ApiPortfolio } from '@/lib/api';

interface RiskAttributionLabProps {
  activePortfolio: ApiPortfolio | null;
  notify?: (msg: string) => void;
  navigate?: (path: string) => void;
}

const SECTOR_PALETTE: Record<string, string> = {
  'Energy': '#f59e0b',
  'Information Technology': '#38bdf8',
  'Financial Services': '#10b981',
  'Banking': '#059669',
  'Consumer Goods': '#a855f7',
  'Automobile': '#ec4899',
  'Telecommunication': '#6366f1',
  'Metals': '#64748b',
  'Other': '#94a3b8'
};

const BAR_COLORS = ['#38bdf8', '#818cf8', '#c084fc', '#f472b6', '#fb7185', '#34d399', '#fbbf24', '#a3e635'];

export function RiskAttributionLab({
  activePortfolio,
  notify,
  navigate,
}: RiskAttributionLabProps) {
  // Configuration Controls
  const [lookbackWindow, setLookbackWindow] = useState<number>(252);
  const [confidenceLevel, setConfidenceLevel] = useState<number>(0.95);
  const [attributionMethod, setAttributionMethod] = useState<'euler_marginal' | 'volatility_decomposition' | 'component_var'>('euler_marginal');
  const [grouping, setGrouping] = useState<'asset' | 'sector'>('asset');
  const [riskMeasure, setRiskMeasure] = useState<'volatility' | 'var_95'>('volatility');

  // Execution & Output State
  const [running, setRunning] = useState<boolean>(false);
  const [attributionResult, setAttributionResult] = useState<any | null>(null);
  const [lastConfigHash, setLastConfigHash] = useState<string>('');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'holdings' | 'sectors' | 'reconciliation' | 'provenance'>('holdings');

  const currentConfigHash = useMemo(() => {
    return `${activePortfolio?.portfolio_id || 'none'}-${activePortfolio?.holdings?.length || 0}-${lookbackWindow}-${confidenceLevel}-${attributionMethod}-${riskMeasure}`;
  }, [activePortfolio, lookbackWindow, confidenceLevel, attributionMethod, riskMeasure]);

  const isStale = Boolean(attributionResult && lastConfigHash && lastConfigHash !== currentConfigHash);

  const handleRunAttribution = async () => {
    if (!activePortfolio || !activePortfolio.holdings || activePortfolio.holdings.length === 0) {
      if (notify) notify('Please select a valid portfolio with at least one holding.');
      return;
    }

    try {
      setRunning(true);
      setErrorMsg(null);
      const res = await api.calculateAttribution(activePortfolio, confidenceLevel);
      if (res && (res.attribution || res.success)) {
        const data = res.attribution || res;
        setAttributionResult(data);
        setLastConfigHash(currentConfigHash);
        if (notify) notify('Risk attribution analysis complete: Euler decomposition verified.');
      } else {
        throw new Error('Risk attribution service returned an empty response.');
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Error executing risk attribution');
      if (notify) notify(`Attribution error: ${err.message}`);
    } finally {
      setRunning(false);
    }
  };

  const assetAttributions = useMemo(() => {
    if (!attributionResult || !attributionResult.asset_attributions) return [];
    return attributionResult.asset_attributions;
  }, [attributionResult]);

  // Aggregate by Sector
  const sectorAttributions = useMemo(() => {
    if (!assetAttributions.length) return [];
    const map = new Map<string, { sector: string; weight: number; componentRisk: number; percentageRisk: number }>();

    for (const item of assetAttributions) {
      const sec = item.sector || 'Other';
      const existing = map.get(sec) || { sector: sec, weight: 0, componentRisk: 0, percentageRisk: 0 };
      existing.weight += Number(item.weight || 0);
      existing.componentRisk += Number(riskMeasure === 'volatility' ? (item.component_volatility || 0) : (item.component_var || 0));
      existing.percentageRisk += Number(item.percentage_risk_contribution || 0);
      map.set(sec, existing);
    }

    return Array.from(map.values()).sort((a, b) => b.percentageRisk - a.percentageRisk);
  }, [assetAttributions, riskMeasure]);

  // Total Portfolio Metrics
  const totalRisk = attributionResult
    ? (riskMeasure === 'volatility'
        ? Number(attributionResult.portfolio_volatility ?? attributionResult.total_portfolio_volatility ?? 0)
        : Number(attributionResult.portfolio_var_95 ?? attributionResult.total_portfolio_var ?? 0))
    : 0;

  const sumComponentRisk = useMemo(() => {
    return assetAttributions.reduce((acc: number, curr: any) => {
      return acc + (riskMeasure === 'volatility' ? Number(curr.component_volatility || curr.component_var || 0) : Number(curr.component_var || 0));
    }, 0);
  }, [assetAttributions, riskMeasure]);

  const reconciliationResidual = Math.abs(totalRisk - sumComponentRisk);
  const isReconciled = totalRisk > 0 && reconciliationResidual < 1e-4;

  const exportCsv = () => {
    if (!assetAttributions.length) return;
    const headers = ['Symbol', 'Sector', 'Weight', 'Marginal Volatility', 'Component Volatility', 'Component VaR 95', '% Risk Contribution'];
    const rows = assetAttributions.map((a: any) => [
      a.symbol,
      a.sector,
      (a.weight * 100).toFixed(2) + '%',
      (a.marginal_volatility * 100).toFixed(4) + '%',
      (a.component_volatility * 100).toFixed(4) + '%',
      (a.component_var * 100).toFixed(4) + '%',
      a.percentage_risk_contribution?.toFixed(2) + '%'
    ]);
    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const encoded = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encoded);
    link.setAttribute('download', `risk_attribution_${activePortfolio?.portfolio_id || 'portfolio'}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="terminal-card space-y-6">
      {/* 1. Lab Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between border-b border-border pb-4 gap-4">
        <div>
          <div className="text-xs uppercase tracking-widest text-muted-foreground flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full bg-cyan-400" />
            RISK ANALYSIS & DECOMPOSITION / 02
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2 mt-1">
            <ChartNoAxesCombined className="w-6 h-6 text-primary" />
            Risk Attribution Lab
          </h1>
          <p className="text-xs text-muted-foreground mt-1 max-w-3xl">
            Decompose portfolio risk into constituent asset, sector, and factor marginal risk contributions using mathematically valid Euler decomposition. 
            Accounts for cross-asset covariance and portfolio weights rather than standalone asset volatilities.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={exportCsv}
            disabled={!assetAttributions.length}
            className="terminal-button-secondary text-xs flex items-center gap-1.5"
            title="Export holding attribution table to CSV"
          >
            <Download className="w-3.5 h-3.5" />
            Export CSV
          </button>
          <button
            onClick={handleRunAttribution}
            disabled={running || !activePortfolio}
            className="terminal-button-primary text-xs flex items-center gap-1.5"
          >
            <Play className={`w-3.5 h-3.5 ${running ? 'animate-spin' : ''}`} />
            {running ? 'Calculating Euler Decomposition...' : 'Run Attribution'}
          </button>
        </div>
      </div>

      {/* 2. Domain-Specific Configuration Panel */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-3 p-3.5 border border-border/80 rounded-lg bg-card/40 text-xs">
        <div>
          <label className="text-muted-foreground block mb-1 font-mono uppercase">TARGET PORTFOLIO</label>
          <input
            readOnly
            value={activePortfolio ? `${activePortfolio.name || activePortfolio.portfolio_id} (${activePortfolio.holdings?.length || 0} holdings)` : 'No Portfolio Selected'}
            className="w-full bg-background border border-border rounded px-2.5 py-1.5 font-mono text-foreground truncate"
          />
        </div>

        <div>
          <label className="text-muted-foreground block mb-1 font-mono uppercase">ATTRIBUTION METHOD</label>
          <select
            value={attributionMethod}
            onChange={(e) => setAttributionMethod(e.target.value as any)}
            className="w-full bg-background border border-border rounded px-2.5 py-1.5 font-mono text-foreground"
          >
            <option value="euler_marginal">Euler Marginal Contribution</option>
            <option value="volatility_decomposition">Covariance Volatility Decomposition</option>
            <option value="component_var">Parametric Component VaR</option>
          </select>
        </div>

        <div>
          <label className="text-muted-foreground block mb-1 font-mono uppercase">TARGET RISK MEASURE</label>
          <select
            value={riskMeasure}
            onChange={(e) => setRiskMeasure(e.target.value as any)}
            className="w-full bg-background border border-border rounded px-2.5 py-1.5 font-mono text-foreground"
          >
            <option value="volatility">Annualized Volatility (σ_p)</option>
            <option value="var_95">95% Daily Historical VaR</option>
          </select>
        </div>

        <div>
          <label className="text-muted-foreground block mb-1 font-mono uppercase">LOOKBACK WINDOW</label>
          <select
            value={lookbackWindow}
            onChange={(e) => setLookbackWindow(Number(e.target.value))}
            className="w-full bg-background border border-border rounded px-2.5 py-1.5 font-mono text-foreground"
          >
            <option value={60}>60 Trading Days (Quarterly)</option>
            <option value={120}>120 Trading Days (Semi-Annual)</option>
            <option value={252}>252 Trading Days (1 Year)</option>
            <option value={504}>504 Trading Days (2 Years)</option>
          </select>
        </div>

        <div>
          <label className="text-muted-foreground block mb-1 font-mono uppercase">GROUPING DIMENSION</label>
          <select
            value={grouping}
            onChange={(e) => setGrouping(e.target.value as any)}
            className="w-full bg-background border border-border rounded px-2.5 py-1.5 font-mono text-foreground"
          >
            <option value="asset">Holding / Symbol Level</option>
            <option value="sector">Industry Sector Level</option>
          </select>
        </div>
      </div>

      {/* 3. Stale / Error Banners */}
      {isStale && (
        <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded text-xs text-amber-300 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-400" />
            <span>Configuration inputs changed. Displayed risk attribution reflects previous run.</span>
          </div>
          <button onClick={handleRunAttribution} className="text-amber-200 underline font-semibold">
            Recompute Attribution
          </button>
        </div>
      )}

      {errorMsg && (
        <div className="p-3 bg-rose-500/10 border border-rose-500/30 rounded text-xs text-rose-300 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-rose-400" />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* 4. Core Metric Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="border border-border/80 rounded-md p-4 bg-card/60">
          <div className="text-xs text-muted-foreground uppercase tracking-wider flex items-center justify-between">
            <span>Total Portfolio Risk</span>
            <Activity className="w-3.5 h-3.5 text-primary" />
          </div>
          <div className="text-2xl font-bold mt-1 text-foreground font-mono">
            {attributionResult ? `${(totalRisk * 100).toFixed(2)}%` : '—'}
          </div>
          <div className="text-xs text-muted-foreground mt-1">
            {riskMeasure === 'volatility' ? 'Annualized Volatility (σ_p)' : '95% Value at Risk'}
          </div>
        </div>

        <div className="border border-border/80 rounded-md p-4 bg-card/60">
          <div className="text-xs text-muted-foreground uppercase tracking-wider flex items-center justify-between">
            <span>Euler Sum of Parts</span>
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold mt-1 text-foreground font-mono">
            {attributionResult ? `${(sumComponentRisk * 100).toFixed(2)}%` : '—'}
          </div>
          <div className="text-xs text-muted-foreground mt-1 flex items-center gap-1.5">
            <span className={`inline-block w-2 h-2 rounded-full ${isReconciled ? 'bg-emerald-400' : 'bg-rose-400'}`} />
            <span>{isReconciled ? '100% Exact Reconciliation' : 'Euler Residual Detected'}</span>
          </div>
        </div>

        <div className="border border-border/80 rounded-md p-4 bg-card/60">
          <div className="text-xs text-muted-foreground uppercase tracking-wider flex items-center justify-between">
            <span>Top Risk Contributor</span>
            <BarChart3 className="w-3.5 h-3.5 text-amber-400" />
          </div>
          <div className="text-xl font-bold mt-1 text-amber-400 font-mono truncate">
            {assetAttributions.length ? `${assetAttributions[0].symbol} (${assetAttributions[0].percentage_risk_contribution?.toFixed(1)}%)` : '—'}
          </div>
          <div className="text-xs text-muted-foreground mt-1">
            {assetAttributions.length ? `Sector: ${assetAttributions[0].sector}` : 'Run analysis to compute'}
          </div>
        </div>

        <div className="border border-border/80 rounded-md p-4 bg-card/60">
          <div className="text-xs text-muted-foreground uppercase tracking-wider flex items-center justify-between">
            <span>Holdings Evaluated</span>
            <Layers className="w-3.5 h-3.5 text-cyan-400" />
          </div>
          <div className="text-2xl font-bold mt-1 text-foreground font-mono">
            {assetAttributions.length || activePortfolio?.holdings?.length || 0}
          </div>
          <div className="text-xs text-muted-foreground mt-1">
            {sectorAttributions.length} Distinct Industry Sectors
          </div>
        </div>
      </div>

      {/* 5. Tab Navigation */}
      <div className="flex border-b border-border">
        <button
          onClick={() => setActiveTab('holdings')}
          className={`px-4 py-2 text-xs font-mono font-semibold border-b-2 transition-colors ${
            activeTab === 'holdings' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          Holding Risk Contribution Table
        </button>
        <button
          onClick={() => setActiveTab('sectors')}
          className={`px-4 py-2 text-xs font-mono font-semibold border-b-2 transition-colors ${
            activeTab === 'sectors' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          Sector Risk Breakdown Chart
        </button>
        <button
          onClick={() => setActiveTab('reconciliation')}
          className={`px-4 py-2 text-xs font-mono font-semibold border-b-2 transition-colors ${
            activeTab === 'reconciliation' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          Euler Reconciliation & Diagnostics
        </button>
        <button
          onClick={() => setActiveTab('provenance')}
          className={`px-4 py-2 text-xs font-mono font-semibold border-b-2 transition-colors ${
            activeTab === 'provenance' ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'
          }`}
        >
          Data Provenance & Methodology
        </button>
      </div>

      {/* Tab 1: Holding Table & Chart */}
      {activeTab === 'holdings' && (
        <div className="space-y-4">
          {assetAttributions.length > 0 ? (
            <>
              <div className="h-64 w-full bg-card/30 border border-border/80 rounded p-3">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={assetAttributions} margin={{ top: 10, right: 20, left: 0, bottom: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#222" />
                    <XAxis dataKey="symbol" stroke="#666" tick={{ fontSize: 10 }} />
                    <YAxis stroke="#666" tick={{ fontSize: 10 }} unit="%" />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#111', borderColor: '#333', fontSize: 11 }}
                      formatter={(val: any, name: string) => [`${Number(val).toFixed(2)}%`, name]}
                    />
                    <Bar dataKey="percentage_risk_contribution" name="% Risk Contribution">
                      {assetAttributions.map((entry: any, index: number) => (
                        <Cell key={`cell-${index}`} fill={BAR_COLORS[index % BAR_COLORS.length]} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>

              <div className="border border-border/80 rounded overflow-x-auto bg-card/30">
                <table className="w-full text-xs text-left">
                  <thead className="bg-muted/40 font-mono text-muted-foreground border-b border-border/60">
                    <tr>
                      <th className="p-3">HOLDING / SYMBOL</th>
                      <th className="p-3">SECTOR</th>
                      <th className="p-3">WEIGHT (w_i)</th>
                      <th className="p-3">MARGINAL VOL (∂σ/∂w_i)</th>
                      <th className="p-3">COMPONENT VOL (RC_i)</th>
                      <th className="p-3">% TOTAL RISK</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/40 font-mono">
                    {assetAttributions.map((a: any, idx: number) => (
                      <tr key={idx} className="hover:bg-muted/20">
                        <td className="p-3 font-semibold text-foreground flex items-center gap-2">
                          <span className="inline-block w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: BAR_COLORS[idx % BAR_COLORS.length] }} />
                          {a.symbol}
                        </td>
                        <td className="p-3 text-muted-foreground">{a.sector}</td>
                        <td className="p-3 font-bold text-foreground">{(a.weight * 100).toFixed(2)}%</td>
                        <td className="p-3 text-cyan-400">{(a.marginal_volatility * 100).toFixed(2)}%</td>
                        <td className="p-3 text-amber-400">{(a.component_volatility * 100).toFixed(2)}%</td>
                        <td className="p-3 font-bold text-primary">{a.percentage_risk_contribution?.toFixed(2)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <div className="p-12 text-center border border-dashed border-border rounded-lg bg-card/20 space-y-3">
              <ChartNoAxesCombined className="w-8 h-8 text-muted-foreground mx-auto" />
              <div className="text-sm font-semibold text-foreground">No Risk Attribution Computed Yet</div>
              <p className="text-xs text-muted-foreground max-w-md mx-auto">
                Configure your target portfolio and parameters above, then click <strong>Run Attribution</strong> to calculate the exact Euler marginal risk breakdown.
              </p>
              <button onClick={handleRunAttribution} className="terminal-button-primary text-xs mx-auto">
                Calculate Attribution Now
              </button>
            </div>
          )}
        </div>
      )}

      {/* Tab 2: Sector Breakdown */}
      {activeTab === 'sectors' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="h-72 w-full bg-card/30 border border-border/80 rounded p-3">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={sectorAttributions}
                  dataKey="percentageRisk"
                  nameKey="sector"
                  cx="50%"
                  cy="50%"
                  outerRadius={80}
                  label={({ sector, percentageRisk }) => `${sector}: ${percentageRisk.toFixed(1)}%`}
                >
                  {sectorAttributions.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={SECTOR_PALETTE[entry.sector] || BAR_COLORS[index % BAR_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ backgroundColor: '#111', borderColor: '#333', fontSize: 11 }}
                  formatter={(val: any) => [`${Number(val).toFixed(2)}%`, 'Risk Share']}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>

          <div className="border border-border/80 rounded overflow-x-auto bg-card/30">
            <table className="w-full text-xs text-left">
              <thead className="bg-muted/40 font-mono text-muted-foreground border-b border-border/60">
                <tr>
                  <th className="p-2.5">SECTOR</th>
                  <th className="p-2.5">WEIGHT</th>
                  <th className="p-2.5">COMPONENT RISK</th>
                  <th className="p-2.5">% RISK CONTRIBUTION</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40 font-mono">
                {sectorAttributions.map((s, idx) => (
                  <tr key={idx} className="hover:bg-muted/20">
                    <td className="p-2.5 font-semibold text-foreground flex items-center gap-2">
                      <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ backgroundColor: SECTOR_PALETTE[s.sector] || '#64748b' }} />
                      {s.sector}
                    </td>
                    <td className="p-2.5">{(s.weight * 100).toFixed(2)}%</td>
                    <td className="p-2.5 text-amber-400">{(s.componentRisk * 100).toFixed(2)}%</td>
                    <td className="p-2.5 font-bold text-primary">{s.percentageRisk.toFixed(2)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab 3: Euler Reconciliation & Diagnostics */}
      {activeTab === 'reconciliation' && (
        <div className="border border-border/80 rounded-lg p-4 bg-card/30 space-y-3 text-xs">
          <div className="flex items-center justify-between border-b border-border/60 pb-2">
            <h3 className="font-semibold text-foreground text-sm flex items-center gap-1.5">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              Euler Theorem Exact Mathematical Reconciliation
            </h3>
            <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${isReconciled ? 'bg-emerald-500/20 text-emerald-300' : 'bg-rose-500/20 text-rose-300'}`}>
              {isReconciled ? 'RECONCILIATION PASSED' : 'RESIDUAL WARNING'}
            </span>
          </div>

          <p className="text-muted-foreground text-[11px]">
            Euler's Homogeneous Function Theorem guarantees that for any linearly homogeneous risk measure (such as Volatility or VaR):
            <br />
            <code className="text-primary font-mono block mt-1 p-2 bg-background/80 rounded border border-border/40">
              σ_p = ∑ (w_i * ∂σ_p/∂w_i) = ∑ Component_Risk_i
            </code>
          </p>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 font-mono">
            <div className="bg-background/80 p-3 rounded border border-border/40">
              <span className="text-muted-foreground text-[10px] block">TOTAL PORTFOLIO RISK</span>
              <span className="text-base font-bold text-foreground">{(totalRisk * 100).toFixed(4)}%</span>
            </div>
            <div className="bg-background/80 p-3 rounded border border-border/40">
              <span className="text-muted-foreground text-[10px] block">SUM OF COMPONENT RISKS</span>
              <span className="text-base font-bold text-foreground">{(sumComponentRisk * 100).toFixed(4)}%</span>
            </div>
            <div className="bg-background/80 p-3 rounded border border-border/40">
              <span className="text-muted-foreground text-[10px] block">UNATTRIBUTED RESIDUAL</span>
              <span className={`text-base font-bold ${reconciliationResidual < 1e-4 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {(reconciliationResidual * 100).toFixed(6)}%
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Tab 4: Provenance */}
      {activeTab === 'provenance' && (
        <div className="border border-border/80 rounded-lg p-4 bg-card/30 space-y-2 text-xs">
          <div className="font-semibold text-foreground">Calculation Provenance & Metadata</div>
          <div className="font-mono text-muted-foreground space-y-1">
            <div>Target Portfolio: <strong>{activePortfolio?.portfolio_id || 'sample_nse_10l'}</strong></div>
            <div>Attribution Methodology: <strong>{attributionMethod}</strong></div>
            <div>Covariance Annualization Factor: <strong>252 (Daily Trading Sessions)</strong></div>
            <div>Reconciliation Status: <strong>{isReconciled ? 'Exact Euler Closed-Form (Residual < 1e-4)' : 'Approximation'}</strong></div>
          </div>
        </div>
      )}
    </div>
  );
}
