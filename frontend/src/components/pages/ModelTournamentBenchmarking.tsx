import React, { useState, useEffect, useMemo } from 'react';
import {
  Trophy,
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
  Award,
  Filter,
  Flame,
  ArrowRight
} from 'lucide-react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Legend,
  ScatterChart,
  Scatter,
  ZAxis,
  Cell,
  LineChart,
  Line
} from 'recharts';
import { api } from '@/lib/api';

interface TournamentCandidate {
  candidate_id: string;
  name: string;
  candidate_type: string;
  strategy_type?: string;
  family: string;
  parameters: Record<string, any>;
  enabled?: boolean;
}

interface LeaderboardItem {
  rank: number;
  candidate_id: string;
  name: string;
  family: string;
  candidate_type: string;
  status: string;
  disqualification_reason?: string;
  primary_metric_name: string;
  primary_score: number;
  cumulative_return_pct: number;
  annualized_return_pct: number;
  annualized_volatility_pct: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown_pct: number;
  win_rate_pct: number;
  total_trades: number;
  profit_factor: number;
  stability_score: number;
  equity_final?: number;
  equity_curve_sample?: Array<{ date: string; equity: number }>;
}

const DATASETS = [
  { symbol: 'RELIANCE', name: 'Reliance Industries Ltd. (NSE)' },
  { symbol: 'NIFTY 50', name: 'Nifty 50 Index (NSE)' },
  { symbol: 'TCS', name: 'Tata Consultancy Services (NSE)' },
  { symbol: 'INFY', name: 'Infosys Limited (NSE)' },
];

export function ModelTournamentBenchmarking({
  navigate,
  notify,
}: {
  navigate?: (path: string) => void;
  notify?: (msg: string) => void;
}) {
  const [candidates, setCandidates] = useState<TournamentCandidate[]>([]);
  const [loadingCandidates, setLoadingCandidates] = useState<boolean>(true);
  const [runningTournament, setRunningTournament] = useState<boolean>(false);
  const [tournamentResult, setTournamentResult] = useState<any | null>(null);
  const [selectedCandidate, setSelectedCandidate] = useState<LeaderboardItem | null>(null);
  const [marketInstruments, setMarketInstruments] = useState(DATASETS);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Tournament Protocol Configuration
  const [tournamentName, setTournamentName] = useState<string>('Q4 Quantitative Alpha & Risk Tournament');
  const [selectedSymbol, setSelectedSymbol] = useState<string>('RELIANCE');
  const [primaryMetric, setPrimaryMetric] = useState<string>('sharpe_ratio');
  const [transactionCostBps, setTransactionCostBps] = useState<number>(10.0);
  const [slippageBps, setSlippageBps] = useState<number>(5.0);
  const [maxDrawdownLimit, setMaxDrawdownLimit] = useState<number>(25.0);
  const [minObservations, setMinObservations] = useState<number>(15);
  const [activeTab, setActiveTab] = useState<'leaderboard' | 'visualizations' | 'bias' | 'protocol'>('leaderboard');

  // Load default candidate roster
  useEffect(() => {
    let mounted = true;
    async function loadCandidates() {
      try {
        setLoadingCandidates(true);
        const res = await api.listTournamentCandidates();
        if (mounted && res && res.candidates) {
          setCandidates(res.candidates.map((c: any) => ({ ...c, enabled: true })));
        }
        api.listMarketInstruments().then((mRes: any) => {
          if (mounted && mRes?.instruments && mRes.instruments.length > 0) {
            setMarketInstruments(mRes.instruments.map((i: any) => ({
              symbol: i.symbol,
              name: `${i.name} (${i.exchange || "NSE"})`
            })));
          }
        }).catch(() => {});
      } catch (err: any) {
        if (mounted) {
          setErrorMsg(`Failed to load tournament candidates: ${err.message}`);
        }
      } finally {
        if (mounted) setLoadingCandidates(false);
      }
    }
    loadCandidates();
    return () => {
      mounted = false;
    };
  }, []);

  const toggleCandidate = (id: string) => {
    setCandidates((prev) =>
      prev.map((c) => (c.candidate_id === id ? { ...c, enabled: !c.enabled } : c))
    );
  };

  const handleSelectAll = (select: boolean) => {
    setCandidates((prev) => prev.map((c) => ({ ...c, enabled: select })));
  };

  const enabledCount = useMemo(() => candidates.filter((c) => c.enabled).length, [candidates]);

  // Execute Tournament
  const handleRunTournament = async () => {
    const activeCandidates = candidates.filter((c) => c.enabled);
    if (activeCandidates.length === 0) {
      if (notify) notify('Select at least one candidate model or strategy to evaluate.');
      return;
    }

    try {
      setRunningTournament(true);
      setErrorMsg(null);
      const protocol = {
        name: tournamentName,
        symbol: selectedSymbol,
        benchmark_symbol: 'NIFTY 50',
        primary_metric: primaryMetric,
        transaction_cost_bps: Number(transactionCostBps),
        slippage_bps: Number(slippageBps),
        max_drawdown_limit_pct: Number(maxDrawdownLimit),
        min_observations: Number(minObservations),
        tie_breaker: 'lowest_max_drawdown',
      };

      const res = await api.runTournament(protocol, activeCandidates);
      if (res && res.success) {
        setTournamentResult(res);
        if (res.leaderboard && res.leaderboard.length > 0) {
          setSelectedCandidate(res.leaderboard[0]);
        }
        if (notify) notify(`Tournament executed: ${res.leaderboard.length} candidates ranked.`);
      } else {
        throw new Error('Tournament execution returned an incomplete result.');
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Error running tournament');
      if (notify) notify(`Tournament error: ${err.message}`);
    } finally {
      setRunningTournament(false);
    }
  };

  // Export CSV
  const handleExportCSV = () => {
    if (!tournamentResult || !tournamentResult.leaderboard) return;
    const headers = [
      'Rank',
      'Candidate ID',
      'Name',
      'Family',
      'Status',
      'Primary Score',
      'Sharpe Ratio',
      'Sortino Ratio',
      'Cumulative Return %',
      'Ann. Return %',
      'Ann. Volatility %',
      'Max Drawdown %',
      'Win Rate %',
      'Total Trades',
      'Profit Factor',
      'Stability Score',
    ];
    const rows = tournamentResult.leaderboard.map((item: LeaderboardItem) => [
      item.rank,
      `"${item.candidate_id}"`,
      `"${item.name}"`,
      `"${item.family}"`,
      item.status,
      item.primary_score,
      item.sharpe_ratio,
      item.sortino_ratio,
      item.cumulative_return_pct,
      item.annualized_return_pct,
      item.annualized_volatility_pct,
      item.max_drawdown_pct,
      item.win_rate_pct,
      item.total_trades,
      item.profit_factor,
      item.stability_score,
    ]);
    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map((e: any[]) => e.join(','))].join('\n');
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', `fragilityshield_tournament_${selectedSymbol}_leaderboard.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    if (notify) notify('Tournament leaderboard exported to CSV.');
  };

  // Scatter chart data (Risk vs Return)
  const scatterData = useMemo(() => {
    if (!tournamentResult || !tournamentResult.leaderboard) return [];
    return tournamentResult.leaderboard.map((item: LeaderboardItem) => ({
      name: item.name,
      x: item.annualized_volatility_pct,
      y: item.annualized_return_pct,
      z: Math.max(1, item.stability_score),
      sharpe: item.sharpe_ratio,
      rank: item.rank,
      family: item.family,
    }));
  }, [tournamentResult]);

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between pb-4 border-b border-[var(--color-border-subtle)] gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-mono text-[var(--color-accent)] uppercase tracking-wider mb-1">
            <Trophy className="w-3.5 h-3.5" />
            <span>FragilityShield Research Lab / Page 17</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-[var(--color-text-main)]">
            Model Tournament & Benchmarking
          </h1>
          <p className="text-sm text-[var(--color-text-muted)] mt-0.5">
            Fair, auditable evaluation across quantitative strategies and risk models under a shared observation window, common transaction costs, and Deflated Sharpe Ratio multi-testing corrections.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {tournamentResult && (
            <button
              onClick={handleExportCSV}
              className="btn btn-secondary flex items-center gap-1.5 text-xs font-mono"
            >
              <Download className="w-3.5 h-3.5" />
              Export Leaderboard
            </button>
          )}
          <button
            onClick={handleRunTournament}
            disabled={runningTournament || enabledCount === 0}
            className="btn btn-primary flex items-center gap-2 text-xs font-mono"
          >
            {runningTournament ? (
              <>
                <RotateCcw className="w-3.5 h-3.5 animate-spin" />
                Evaluating Candidates...
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5" />
                Run Tournament ({enabledCount})
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

      {/* Protocol Configuration & Candidate Roster Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Tournament Protocol */}
        <div className="panel p-4 space-y-4">
          <div className="flex items-center justify-between border-b border-[var(--color-border-subtle)] pb-2">
            <div className="flex items-center gap-2 font-mono text-sm text-[var(--color-text-main)] font-semibold">
              <Sliders className="w-4 h-4 text-[var(--color-accent)]" />
              Shared Protocol
            </div>
            <span className="badge text-[10px] bg-[var(--color-bg-subtle)] text-[var(--color-text-muted)]">
              VERIFIED RULES
            </span>
          </div>

          <div className="space-y-3 text-xs">
            <div>
              <label className="block text-[var(--color-text-muted)] font-mono mb-1">TOURNAMENT TITLE</label>
              <input
                type="text"
                value={tournamentName}
                onChange={(e) => setTournamentName(e.target.value)}
                className="input w-full font-mono text-xs"
              />
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-[var(--color-text-muted)] font-mono mb-1">DATASET / ASSET</label>
                <select
                  value={selectedSymbol}
                  onChange={(e) => setSelectedSymbol(e.target.value)}
                  className="input w-full font-mono text-xs"
                >
                  {marketInstruments.map((d) => (
                    <option key={d.symbol} value={d.symbol}>
                      {d.symbol}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-[var(--color-text-muted)] font-mono mb-1">PRIMARY RANK METRIC</label>
                <select
                  value={primaryMetric}
                  onChange={(e) => setPrimaryMetric(e.target.value)}
                  className="input w-full font-mono text-xs"
                >
                  <option value="sharpe_ratio">Sharpe Ratio</option>
                  <option value="cumulative_return">Cumulative Return</option>
                  <option value="sortino_ratio">Sortino Ratio</option>
                  <option value="calmar_ratio">Calmar Ratio</option>
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-[var(--color-text-muted)] font-mono mb-1">FEE FRICTION (BPS)</label>
                <input
                  type="number"
                  value={transactionCostBps}
                  onChange={(e) => setTransactionCostBps(parseFloat(e.target.value) || 0)}
                  className="input w-full font-mono text-xs"
                  min="0"
                  max="100"
                  step="1"
                />
              </div>
              <div>
                <label className="block text-[var(--color-text-muted)] font-mono mb-1">SLIPPAGE (BPS)</label>
                <input
                  type="number"
                  value={slippageBps}
                  onChange={(e) => setSlippageBps(parseFloat(e.target.value) || 0)}
                  className="input w-full font-mono text-xs"
                  min="0"
                  max="50"
                  step="1"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-[var(--color-text-muted)] font-mono mb-1">MAX DRAWDOWN LIMIT %</label>
                <input
                  type="number"
                  value={maxDrawdownLimit}
                  onChange={(e) => setMaxDrawdownLimit(parseFloat(e.target.value) || 0)}
                  className="input w-full font-mono text-xs"
                  min="5"
                  max="50"
                />
              </div>
              <div>
                <label className="block text-[var(--color-text-muted)] font-mono mb-1">MIN SESSIONS</label>
                <input
                  type="number"
                  value={minObservations}
                  onChange={(e) => setMinObservations(parseInt(e.target.value) || 10)}
                  className="input w-full font-mono text-xs"
                  min="10"
                />
              </div>
            </div>

            <div className="p-2.5 bg-[var(--color-bg-subtle)] rounded border border-[var(--color-border-subtle)] space-y-1 text-[11px] text-[var(--color-text-muted)]">
              <div className="flex items-center gap-1.5 font-semibold text-[var(--color-text-main)]">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                Fairness Protocol Invariant
              </div>
              <p>
                All candidates are evaluated over synchronous, identical Upstox bar feeds with mandatory 1-bar execution lag ($T+1$) and uniform statutory exchange frictions.
              </p>
            </div>
          </div>
        </div>

        {/* Right 2 Columns: Candidate Roster Selector */}
        <div className="panel p-4 space-y-4 lg:col-span-2">
          <div className="flex items-center justify-between border-b border-[var(--color-border-subtle)] pb-2">
            <div className="flex items-center gap-2 font-mono text-sm text-[var(--color-text-main)] font-semibold">
              <Layers className="w-4 h-4 text-[var(--color-accent)]" />
              Candidate Roster ({enabledCount}/{candidates.length} Selected)
            </div>
            <div className="flex items-center gap-2 text-xs font-mono">
              <button
                onClick={() => handleSelectAll(true)}
                className="text-[var(--color-accent)] hover:underline"
              >
                Select All
              </button>
              <span className="text-[var(--color-text-muted)]">|</span>
              <button
                onClick={() => handleSelectAll(false)}
                className="text-[var(--color-text-muted)] hover:underline"
              >
                Deselect All
              </button>
            </div>
          </div>

          {loadingCandidates ? (
            <div className="py-8 text-center text-xs font-mono text-[var(--color-text-muted)] animate-pulse">
              Loading verified model and strategy candidates...
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 max-h-[280px] overflow-y-auto pr-1">
              {candidates.map((cand) => (
                <div
                  key={cand.candidate_id}
                  onClick={() => toggleCandidate(cand.candidate_id)}
                  className={`p-2.5 rounded border transition-all cursor-pointer flex items-start gap-2.5 text-xs ${
                    cand.enabled
                      ? 'border-[var(--color-accent)] bg-[var(--color-accent)]/5'
                      : 'border-[var(--color-border-subtle)] bg-[var(--color-bg-subtle)] opacity-60'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={cand.enabled}
                    onChange={() => {}}
                    className="mt-0.5"
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-1">
                      <span className="font-semibold text-[var(--color-text-main)] truncate">
                        {cand.name}
                      </span>
                      <span className="badge text-[9px] bg-slate-800 text-slate-300 shrink-0">
                        {cand.family}
                      </span>
                    </div>
                    <div className="text-[11px] font-mono text-[var(--color-text-muted)] mt-1 truncate">
                      {cand.strategy_type || cand.candidate_type} | {JSON.stringify(cand.parameters)}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Main Results Workspace */}
      {tournamentResult ? (
        <div className="space-y-6">
          {/* Top Banner: Winner & Multi-Testing Corrections */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className={`panel p-4 border ${
              tournamentResult.champion
                ? 'bg-gradient-to-br from-amber-950/30 to-amber-900/10 border-amber-600/40'
                : 'bg-muted/30 border-border/80'
            }`}>
              <div className="flex items-center justify-between text-xs font-mono text-amber-400">
                <span>{tournamentResult.champion ? 'TOURNAMENT CHAMPION' : 'TOURNAMENT VERDICT'}</span>
                <Award className="w-4 h-4" />
              </div>
              <div className="mt-2 text-lg font-bold truncate">
                {tournamentResult.champion ? (
                  <span className="text-amber-200">{tournamentResult.champion.name}</span>
                ) : (
                  <span className="text-muted-foreground text-sm">NO CANDIDATE QUALIFIED</span>
                )}
              </div>
              <div className="text-xs font-mono text-muted-foreground mt-1">
                {tournamentResult.champion
                  ? `Score: ${tournamentResult.champion.primary_score} (${tournamentResult.champion.primary_metric_name})`
                  : 'All candidates failed trade activity, observations, or risk limits'}
              </div>
            </div>

            <div className="panel p-4">
              <div className="text-xs font-mono text-[var(--color-text-muted)]">
                DEFLATED SHARPE PROB (DSR)
              </div>
              <div className="mt-2 text-xl font-bold font-mono text-[var(--color-text-main)] flex items-center gap-2">
                {(tournamentResult.multiple_testing_diagnostics?.deflated_sharpe_ratio_prob * 100).toFixed(1)}%
                <span
                  className={`badge text-[10px] ${
                    tournamentResult.multiple_testing_diagnostics?.deflated_sharpe_ratio_prob >= 0.95
                      ? 'bg-emerald-950 text-emerald-400 border border-emerald-700'
                      : tournamentResult.multiple_testing_diagnostics?.deflated_sharpe_ratio_prob >= 0.80
                      ? 'bg-amber-950 text-amber-400 border border-amber-700'
                      : 'bg-red-950 text-red-400 border border-red-700'
                  }`}
                >
                  {tournamentResult.multiple_testing_diagnostics?.selection_bias_verdict}
                </span>
              </div>
              <div className="text-[11px] text-[var(--color-text-muted)] mt-1">
                Tested across {tournamentResult.multiple_testing_diagnostics?.num_candidates_tested} candidate models
              </div>
            </div>

            <div className="panel p-4">
              <div className="text-xs font-mono text-[var(--color-text-muted)]">
                BONFERRONI ADJUSTED P-VAL
              </div>
              <div className="mt-2 text-xl font-bold font-mono text-[var(--color-text-main)]">
                {tournamentResult.multiple_testing_diagnostics?.bonferroni_adjusted_p_value}
              </div>
              <div className="text-[11px] text-[var(--color-text-muted)] mt-1">
                Multi-testing family-wise error control
              </div>
            </div>

            <div className="panel p-4">
              <div className="text-xs font-mono text-[var(--color-text-muted)]">
                TOURNAMENT SHA-256 DIGEST
              </div>
              <div className="mt-2 text-xs font-mono text-[var(--color-accent)] truncate">
                {tournamentResult.tournament_fingerprint}
              </div>
              <div className="text-[11px] text-[var(--color-text-muted)] mt-1">
                Immutable evaluation fingerprint
              </div>
            </div>
          </div>

          {/* Tab Navigation */}
          <div className="flex items-center gap-2 border-b border-[var(--color-border-subtle)] pb-2">
            <button
              onClick={() => setActiveTab('leaderboard')}
              className={`px-3 py-1.5 text-xs font-mono rounded transition-colors ${
                activeTab === 'leaderboard'
                  ? 'bg-[var(--color-accent)] text-black font-semibold'
                  : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-main)]'
              }`}
            >
              Leaderboard ({tournamentResult.leaderboard.length})
            </button>
            <button
              onClick={() => setActiveTab('visualizations')}
              className={`px-3 py-1.5 text-xs font-mono rounded transition-colors ${
                activeTab === 'visualizations'
                  ? 'bg-[var(--color-accent)] text-black font-semibold'
                  : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-main)]'
              }`}
            >
              Comparison Visualizations
            </button>
            <button
              onClick={() => setActiveTab('bias')}
              className={`px-3 py-1.5 text-xs font-mono rounded transition-colors ${
                activeTab === 'bias'
                  ? 'bg-[var(--color-accent)] text-black font-semibold'
                  : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-main)]'
              }`}
            >
              Selection Bias Audit
            </button>
            <button
              onClick={() => setActiveTab('protocol')}
              className={`px-3 py-1.5 text-xs font-mono rounded transition-colors ${
                activeTab === 'protocol'
                  ? 'bg-[var(--color-accent)] text-black font-semibold'
                  : 'text-[var(--color-text-muted)] hover:text-[var(--color-text-main)]'
              }`}
            >
              Evaluation Logs & Protocol
            </button>
          </div>

          {/* Tab 1: Leaderboard Table */}
          {activeTab === 'leaderboard' && (
            <div className="panel p-0 overflow-hidden">
              <div className="overflow-x-auto">
                <table className="table w-full text-xs">
                  <thead>
                    <tr className="bg-[var(--color-bg-subtle)] border-b border-[var(--color-border-subtle)] font-mono text-[var(--color-text-muted)]">
                      <th className="py-2.5 px-3 text-left">RANK</th>
                      <th className="py-2.5 px-3 text-left">CANDIDATE</th>
                      <th className="py-2.5 px-3 text-left">FAMILY</th>
                      <th className="py-2.5 px-3 text-right">PRIMARY SCORE</th>
                      <th className="py-2.5 px-3 text-right">SHARPE</th>
                      <th className="py-2.5 px-3 text-right">SORTINO</th>
                      <th className="py-2.5 px-3 text-right">CUMULATIVE %</th>
                      <th className="py-2.5 px-3 text-right">MAX DD %</th>
                      <th className="py-2.5 px-3 text-right">WIN RATE %</th>
                      <th className="py-2.5 px-3 text-right">TRADES</th>
                      <th className="py-2.5 px-3 text-right">STABILITY</th>
                      <th className="py-2.5 px-3 text-center">STATUS</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tournamentResult.leaderboard.map((item: LeaderboardItem) => (
                      <tr
                        key={item.candidate_id}
                        onClick={() => setSelectedCandidate(item)}
                        className={`border-b border-[var(--color-border-subtle)] hover:bg-[var(--color-bg-subtle)]/70 transition-colors cursor-pointer ${
                          selectedCandidate?.candidate_id === item.candidate_id
                            ? 'bg-[var(--color-accent)]/10'
                            : ''
                        }`}
                      >
                        <td className="py-2.5 px-3 font-mono font-bold">
                          {item.rank === 1 ? (
                            <span className="text-amber-400 flex items-center gap-1">
                              <Trophy className="w-3.5 h-3.5" /> 1
                            </span>
                          ) : (
                            `#${item.rank}`
                          )}
                        </td>
                        <td className="py-2.5 px-3 font-semibold text-[var(--color-text-main)]">
                          {item.name}
                        </td>
                        <td className="py-2.5 px-3 font-mono text-[var(--color-text-muted)]">
                          {item.family}
                        </td>
                        <td className="py-2.5 px-3 font-mono text-right font-bold text-[var(--color-accent)]">
                          {item.primary_score}
                        </td>
                        <td className="py-2.5 px-3 font-mono text-right">{item.sharpe_ratio}</td>
                        <td className="py-2.5 px-3 font-mono text-right">{item.sortino_ratio}</td>
                        <td
                          className={`py-2.5 px-3 font-mono text-right ${
                            item.cumulative_return_pct >= 0 ? 'text-emerald-400' : 'text-red-400'
                          }`}
                        >
                          {item.cumulative_return_pct > 0 ? '+' : ''}
                          {item.cumulative_return_pct}%
                        </td>
                        <td className="py-2.5 px-3 font-mono text-right text-red-400">
                          {item.max_drawdown_pct}%
                        </td>
                        <td className="py-2.5 px-3 font-mono text-right">{item.win_rate_pct}%</td>
                        <td className="py-2.5 px-3 font-mono text-right">{item.total_trades}</td>
                        <td className="py-2.5 px-3 font-mono text-right">
                          <span
                            className={`badge text-[10px] ${
                              item.stability_score >= 80
                                ? 'bg-emerald-950 text-emerald-400'
                                : item.stability_score >= 50
                                ? 'bg-amber-950 text-amber-400'
                                : 'bg-red-950 text-red-400'
                            }`}
                          >
                            {item.stability_score}%
                          </span>
                        </td>
                        <td className="py-2.5 px-3 text-center">
                          <span
                            className={`badge text-[10px] ${
                              item.status === 'QUALIFIED'
                                ? 'bg-emerald-950 text-emerald-400 border border-emerald-700/60'
                                : item.status === 'ZERO_TRADES_INACTIVE'
                                ? 'bg-amber-950 text-amber-300 border border-amber-700/60'
                                : item.status === 'INSUFFICIENT_OBSERVATIONS'
                                ? 'bg-purple-950 text-purple-300 border border-purple-700/60'
                                : 'bg-red-950 text-red-400 border border-red-700/60'
                            }`}
                            title={item.disqualification_reason || item.status}
                          >
                            {item.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Candidate Detail Drawer */}
              {selectedCandidate && (
                <div className="p-4 bg-[var(--color-bg-subtle)] border-t border-[var(--color-border-subtle)] flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <div>
                    <div className="text-xs font-mono text-[var(--color-text-muted)]">
                      INSPECTING RANK #{selectedCandidate.rank}
                    </div>
                    <div className="text-sm font-bold text-[var(--color-text-main)]">
                      {selectedCandidate.name} ({selectedCandidate.family})
                    </div>
                    <div className="text-xs text-[var(--color-text-muted)] mt-0.5">
                      Profit Factor: {selectedCandidate.profit_factor} | Win Rate: {selectedCandidate.win_rate_pct}% | Volatility: {selectedCandidate.annualized_volatility_pct}%
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {navigate && (
                      <button
                        onClick={() => navigate('/experiments')}
                        className="btn btn-secondary text-xs font-mono flex items-center gap-1.5"
                      >
                        Create Experiment <ArrowRight className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Tab 2: Comparison Visualizations */}
          {activeTab === 'visualizations' && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Risk vs Return Scatter */}
              <div className="panel p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="font-mono text-xs font-semibold text-[var(--color-text-main)]">
                    RISK VS RETURN (VOLATILITY VS ANNUALIZED RETURN)
                  </h3>
                  <span className="badge text-[10px] bg-slate-800 text-slate-300">SCATTER</span>
                </div>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <ScatterChart margin={{ top: 10, right: 20, bottom: 20, left: 10 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#262626" />
                      <XAxis
                        type="number"
                        dataKey="x"
                        name="Volatility %"
                        unit="%"
                        stroke="#666"
                        fontSize={11}
                      />
                      <YAxis
                        type="number"
                        dataKey="y"
                        name="Return %"
                        unit="%"
                        stroke="#666"
                        fontSize={11}
                      />
                      <ZAxis type="number" dataKey="z" range={[60, 300]} name="Stability" />
                      <Tooltip
                        cursor={{ strokeDasharray: '3 3' }}
                        contentStyle={{ backgroundColor: '#141414', borderColor: '#333' }}
                      />
                      <Scatter name="Candidates" data={scatterData} fill="#257d70">
                        {scatterData.map((entry, index) => (
                          <Cell
                            key={`cell-${index}`}
                            fill={entry.rank === 1 ? '#f59e0b' : index % 2 === 0 ? '#257d70' : '#38bdf8'}
                          />
                        ))}
                      </Scatter>
                    </ScatterChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Sharpe Ratio Ranking Bar Chart */}
              <div className="panel p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="font-mono text-xs font-semibold text-[var(--color-text-main)]">
                    PRIMARY SCORE RANKING ({primaryMetric.toUpperCase()})
                  </h3>
                  <span className="badge text-[10px] bg-slate-800 text-slate-300">RANKED</span>
                </div>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={tournamentResult.leaderboard}
                      layout="vertical"
                      margin={{ top: 5, right: 30, left: 40, bottom: 5 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="#262626" />
                      <XAxis type="number" stroke="#666" fontSize={11} />
                      <YAxis
                        dataKey="name"
                        type="category"
                        stroke="#888"
                        fontSize={10}
                        width={120}
                      />
                      <Tooltip contentStyle={{ backgroundColor: '#141414', borderColor: '#333' }} />
                      <Bar dataKey="primary_score" fill="#257d70">
                        {tournamentResult.leaderboard.map((entry: any, index: number) => (
                          <Cell
                            key={`bar-${index}`}
                            fill={entry.rank === 1 ? '#f59e0b' : '#257d70'}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          )}

          {/* Tab 3: Selection Bias Audit */}
          {activeTab === 'bias' && (
            <div className="panel p-4 space-y-4">
              <div className="flex items-center gap-2 border-b border-[var(--color-border-subtle)] pb-2 font-mono text-sm font-semibold text-[var(--color-text-main)]">
                <Scale className="w-4 h-4 text-[var(--color-accent)]" />
                Multiple Testing & Data Mining Bias Corrections
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                <div className="p-3 bg-[var(--color-bg-subtle)] rounded border border-[var(--color-border-subtle)] space-y-2">
                  <div className="font-semibold text-[var(--color-text-main)]">
                    Bailey & López de Prado (2014) Deflated Sharpe Ratio
                  </div>
                  <p className="text-[var(--color-text-muted)] leading-relaxed">
                    Standard backtesting exhibits substantial selection bias when the researcher runs multiple trials and selects the maximum Sharpe ratio. The DSR corrects the observed Sharpe ratio for:
                  </p>
                  <ul className="list-disc pl-5 text-[var(--color-text-muted)] space-y-1">
                    <li>The number of independent models evaluated ($K = {tournamentResult.multiple_testing_diagnostics?.num_candidates_tested}$)</li>
                    <li>Variance and non-normality (skewness and kurtosis of returns)</li>
                    <li>Sample observation size ($N = {tournamentResult.multiple_testing_diagnostics?.sample_size}$)</li>
                  </ul>
                  <div className="mt-2 font-mono text-emerald-400">
                    Expected Maximum Sharpe under Null: {tournamentResult.multiple_testing_diagnostics?.expected_max_sharpe_null}
                  </div>
                </div>

                <div className="p-3 bg-[var(--color-bg-subtle)] rounded border border-[var(--color-border-subtle)] space-y-2">
                  <div className="font-semibold text-[var(--color-text-main)]">
                    Bonferroni Multiple Testing Adjustment
                  </div>
                  <p className="text-[var(--color-text-muted)] leading-relaxed">
                    To strictly bound family-wise error rate ($\alpha = 0.05$), the nominal hypothesis test $p$-value is inflated by the candidate test dimension $K$:
                  </p>
                  <div className="p-2 bg-slate-900 font-mono text-xs text-amber-300 rounded">
                    Adjusted p-value = {tournamentResult.multiple_testing_diagnostics?.bonferroni_adjusted_p_value}
                  </div>
                  <p className="text-[var(--color-text-muted)] text-[11px]">
                    Candidate rankings must show statistical significance after this penalty to rule out pure backtest overfitting.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Tab 4: Evaluation Logs & Protocol */}
          {activeTab === 'protocol' && (
            <div className="panel p-4 space-y-3 font-mono text-xs">
              <div className="font-semibold text-[var(--color-text-main)] border-b border-[var(--color-border-subtle)] pb-2">
                EVALUATION PROTOCOL & SYSTEM EXECUTION TRACE
              </div>
              <div className="p-3 bg-black/60 rounded border border-neutral-800 space-y-1 max-h-60 overflow-y-auto text-[11px] text-neutral-300">
                {tournamentResult.evaluation_logs?.map((log: string, idx: number) => (
                  <div key={idx} className="flex gap-2">
                    <span className="text-neutral-500">[{idx + 1}]</span>
                    <span>{log}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="panel py-16 text-center space-y-3">
          <Trophy className="w-10 h-10 text-[var(--color-text-muted)] mx-auto opacity-40" />
          <h3 className="text-base font-semibold text-[var(--color-text-main)]">
            Ready to Conduct Model Tournament
          </h3>
          <p className="text-xs text-[var(--color-text-muted)] max-w-md mx-auto">
            Select the desired candidates from the roster above and click &quot;Run Tournament&quot; to perform an aligned, multi-candidate evaluation on historical Upstox data.
          </p>
          <button
            onClick={handleRunTournament}
            disabled={runningTournament || enabledCount === 0}
            className="btn btn-primary text-xs font-mono mt-2"
          >
            <Play className="w-3.5 h-3.5 mr-1.5" />
            Launch Tournament Now
          </button>
        </div>
      )}
    </div>
  );
}
