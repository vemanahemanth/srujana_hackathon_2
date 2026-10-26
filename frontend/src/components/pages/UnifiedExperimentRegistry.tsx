import React, { useState, useEffect, useMemo } from 'react';
import {
  FileClock, Search, Filter, RefreshCw, Download, ArrowRight,
  ShieldCheck, AlertTriangle, Eye, RotateCw, CheckCircle, Copy,
  ChevronRight, X, ExternalLink, GitBranch, Layers, Sliders, Database,
  FileText, Check, AlertCircle, Sparkles
} from 'lucide-react';
import { api } from '@/lib/api';

interface UnifiedExperimentRun {
  run_id: string;
  run_type: string;
  display_name: string;
  created_at: string;
  completed_at?: string;
  status: string;
  initiating_user: string;
  spec: any;
  result: any;
  dataset_hash: string;
  data_provenance: any;
  reproducibility: string;
  lineage: {
    parent_run_id?: string | null;
    child_run_ids?: string[];
    source_type: string;
    source_id?: string;
  };
  metrics_summary: Record<string, any>;
}

export function UnifiedExperimentRegistry({
  navigate,
  notify,
}: {
  navigate?: (path: string) => void;
  notify?: (msg: string) => void;
}) {
  const [runs, setRuns] = useState<UnifiedExperimentRun[]>([]);
  const [stats, setStats] = useState<any>({
    total_runs: 0,
    by_type: {},
    by_status: {},
    recent_completed_count: 0,
    recent_failed_count: 0,
  });
  const [loading, setLoading] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Filters & Search
  const [selectedType, setSelectedType] = useState<string>('all');
  const [selectedStatus, setSelectedStatus] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Selection for comparison
  const [selectedRunIds, setSelectedRunIds] = useState<string[]>([]);
  const [comparisonData, setComparisonData] = useState<any | null>(null);
  const [comparing, setComparing] = useState<boolean>(false);

  // Detailed Inspection Modal
  const [inspectRun, setInspectRun] = useState<UnifiedExperimentRun | null>(null);

  // Copied state
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Orchestrator Launch Modal (Phases 3, 4, 7)
  const [showOrchestratorModal, setShowOrchestratorModal] = useState<boolean>(false);
  const [orchTargetType, setOrchTargetType] = useState<string>('model');
  const [orchTargetSymbol, setOrchTargetSymbol] = useState<string>('NIFTY_50');
  const [orchProfileId, setOrchProfileId] = useState<string>('test_all');
  const [orchConfidence, setOrchConfidence] = useState<number>(0.95);
  const [orchLookback, setOrchLookback] = useState<number>(60);
  const [orchShockBoundary, setOrchShockBoundary] = useState<number>(0.20);
  const [orchRunning, setOrchRunning] = useState<boolean>(false);
  const [orchValidationResults, setOrchValidationResults] = useState<any[] | null>(null);
  const [orchValidating, setOrchValidating] = useState<boolean>(false);

  const handleValidateOrchestrator = async () => {
    setOrchValidating(true);
    try {
      const res = await api.validateOrchestrator({
        experiment_type: orchTargetType,
        profile_id: orchProfileId,
        data: { symbol: orchTargetSymbol },
      });
      if (res && res.success) {
        setOrchValidationResults(res.modules);
        notify?.(`Validation: ${res.applicable_count}/${res.total_modules} test modules executable.`);
      }
    } catch (err: any) {
      notify?.(`Validation failed: ${err.message}`);
    } finally {
      setOrchValidating(false);
    }
  };

  const handleExecuteOrchestrator = async () => {
    setOrchRunning(true);
    notify?.(`Executing Test Suite (${orchProfileId}) for ${orchTargetSymbol}...`);
    try {
      const res = await api.runOrchestrator({
        experiment_id: `exp_${orchTargetSymbol.toLowerCase()}_${Date.now()}`,
        experiment_type: orchTargetType,
        target_identity: { symbol: orchTargetSymbol, name: `${orchTargetSymbol} Quantitative Target` },
        profile_id: orchProfileId,
        config_overrides: {
          confidence_level: orchConfidence,
          lookback_window: orchLookback,
          target_loss_boundary: orchShockBoundary,
        },
      });

      if (res && res.run_id) {
        notify?.(`Test Suite Completed! Status: ${(res.run_status || res.status || 'completed').toUpperCase()}`);
        setShowOrchestratorModal(false);
        await fetchRuns();
        setInspectRun(res);
      }
    } catch (err: any) {
      console.error('Orchestrator execution error:', err);
      notify?.(`Execution failed: ${err.message}`);
    } finally {
      setOrchRunning(false);
    }
  };

  // 1. Fetch Runs from Unified API
  const fetchRuns = async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const res = await api.listUnifiedExperiments({
        type: selectedType !== 'all' ? selectedType : undefined,
        status: selectedStatus !== 'all' ? selectedStatus : undefined,
        search: searchQuery.trim() || undefined,
      });

      if (res.success) {
        setRuns(res.runs || []);
        if (res.stats) setStats(res.stats);
      } else {
        setErrorMsg('Failed to load experiment records.');
      }
    } catch (err: any) {
      console.error('Failed to fetch experiments:', err);
      setErrorMsg(err.message || 'Error loading experiment registry.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRuns();
  }, [selectedType, selectedStatus]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    fetchRuns();
  };

  // 2. Multi-run comparison
  const handleToggleSelect = (runId: string) => {
    if (selectedRunIds.includes(runId)) {
      setSelectedRunIds(selectedRunIds.filter((id) => id !== runId));
    } else {
      if (selectedRunIds.length >= 4) {
        notify?.('Maximum 4 runs can be compared simultaneously.');
        return;
      }
      setSelectedRunIds([...selectedRunIds, runId]);
    }
  };

  const handleLaunchComparison = async () => {
    if (selectedRunIds.length < 2) {
      notify?.('Please select at least 2 runs to compare.');
      return;
    }
    setComparing(true);
    try {
      const res = await api.compareExperiments(selectedRunIds);
      if (res.success) {
        setComparisonData(res);
      } else {
        notify?.('Comparison failed: invalid runs.');
      }
    } catch (err: any) {
      notify?.(`Comparison error: ${err.message}`);
    } finally {
      setComparing(false);
    }
  };

  // 3. Rerun experiment
  const handleRerun = async (runId: string) => {
    notify?.(`Rerunning experiment ${runId}...`);
    try {
      const res = await api.rerunExperiment(runId);
      if (res.success) {
        notify?.(`Rerun completed! New Child Run ID: ${res.new_run?.run_id}`);
        fetchRuns();
      }
    } catch (err: any) {
      notify?.(`Rerun failed: ${err.message}`);
    }
  };

  // 4. Export experiment
  const handleExport = async (runId: string, format: 'markdown' | 'json' | 'csv') => {
    try {
      notify?.(`Exporting ${runId} as ${format.toUpperCase()}...`);
      const data = await api.exportExperiment(runId, format);
      const mime =
        format === 'json'
          ? 'application/json'
          : format === 'csv'
          ? 'text/csv'
          : 'text/markdown';
      const ext = format === 'json' ? 'json' : format === 'csv' ? 'csv' : 'md';
      const content = typeof data === 'string' ? data : JSON.stringify(data, null, 2);

      const blob = new Blob([content], { type: `${mime};charset=utf-8;` });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.setAttribute('href', url);
      link.setAttribute('download', `experiment_${runId}.${ext}`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      notify?.(`Downloaded experiment_${runId}.${ext}`);
    } catch (err: any) {
      notify?.(`Export failed: ${err.message}`);
    }
  };

  const handleCopyId = (id: string) => {
    navigator.clipboard.writeText(id);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
    notify?.(`Copied Run ID: ${id}`);
  };

  const getRunTypeBadge = (type: string) => {
    switch (type) {
      case 'orchestrated_test_suite':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-gradient-to-r from-indigo-950/80 to-cyan-950/80 text-cyan-300 border border-cyan-500/40 inline-flex items-center gap-1 shadow-sm">
            <Sparkles size={11} className="text-cyan-400" />
            TEST ALL SUITE
          </span>
        );
      case 'strategy_backtest':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-emerald-950/60 text-emerald-400 border border-emerald-500/30">
            STRATEGY BACKTEST
          </span>
        );
      case 'model_validation':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-indigo-950/60 text-indigo-400 border border-indigo-500/30">
            MODEL VALIDATION
          </span>
        );
      case 'fragility_matrix':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-amber-950/60 text-amber-400 border border-amber-500/30">
            FRAGILITY MATRIX
          </span>
        );
      case 'studio_experiment':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-sky-950/60 text-sky-400 border border-sky-500/30">
            STUDIO EXPERIMENT
          </span>
        );
      case 'external_forecasting':
      case 'external_risk':
      case 'external_general':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-cyan-950/60 text-cyan-400 border border-cyan-500/30 inline-flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
            EXTERNAL: {type.replace('external_', '').toUpperCase()}
          </span>
        );
      default:
        if (type.startsWith('external')) {
          return (
            <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-cyan-950/60 text-cyan-400 border border-cyan-500/30 inline-flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
              EXTERNAL
            </span>
          );
        }
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-slate-800 text-slate-300">
            {type.toUpperCase()}
          </span>
        );
    }
  };

  return (
    <div className="stack-layout space-y-6 p-6">
      {/* Hero Header */}
      <section className="panel generic-hero flex items-center justify-between p-6 bg-slate-900 border border-slate-800 rounded-lg shadow-md">
        <div className="flex items-center gap-4">
          <div className="generic-mark p-3 bg-indigo-950/60 border border-indigo-500/30 text-indigo-400 rounded-lg">
            <FileClock size={24} />
          </div>
          <div>
            <span className="section-kicker text-xs font-mono tracking-wider text-indigo-400 font-semibold uppercase">
              REPRODUCIBILITY &amp; LINEAGE / PAGE 09
            </span>
            <h2 className="text-xl font-bold text-slate-100 flex items-center gap-3">
              Unified Experiment Registry &amp; Research Reproducibility
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-indigo-900/60 border border-indigo-500/30 text-indigo-300 font-mono">
                SHA-256 Provenance • Lineage Tree
              </span>
            </h2>
            <p className="text-xs text-slate-400 mt-1 max-w-2xl">
              Immutable ledger of all quantitative experiments, model stress tests, and strategy backtests.
              Compare configurations side-by-side, verify cryptographic data hashes, and audit parent-child lineage.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              setShowOrchestratorModal(true);
              setOrchValidationResults(null);
            }}
            className="px-3.5 py-1.5 text-xs font-semibold rounded bg-gradient-to-r from-indigo-600 to-cyan-600 hover:from-indigo-500 hover:to-cyan-500 text-white shadow-lg shadow-indigo-500/20 transition flex items-center gap-2"
          >
            <Sparkles size={14} className="text-cyan-200" />
            Run Test Suite (Test All)
          </button>
          <button
            onClick={fetchRuns}
            disabled={loading}
            className="px-3 py-1.5 text-xs font-medium rounded border border-slate-800 bg-slate-950 hover:bg-slate-850 text-slate-300 transition flex items-center gap-2"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </section>

      {/* Dashboard Summary Statistics Bar */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <div className="panel bg-slate-900 border border-slate-800 rounded-lg p-3">
          <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider block mb-1">
            Total Research Runs
          </span>
          <div className="text-2xl font-bold font-mono text-slate-100">{stats.total_runs || 0}</div>
          <div className="mt-1 text-[10px] text-slate-400 flex items-center gap-2">
            <span className="text-emerald-400 font-semibold">{stats.recent_completed_count || 0} completed</span>
            {stats.recent_failed_count > 0 && (
              <span className="text-rose-400 font-semibold">• {stats.recent_failed_count} failed</span>
            )}
          </div>
        </div>

        <div className="panel bg-slate-900 border border-cyan-500/30 bg-cyan-950/20 rounded-lg p-3">
          <span className="text-[10px] font-mono text-cyan-400 uppercase tracking-wider block mb-1">
            External / Colab Runs
          </span>
          <div className="text-2xl font-bold font-mono text-cyan-400">
            {Object.entries(stats.by_type || {}).reduce((acc: number, [k, v]: any) => k.startsWith('external') ? acc + (Number(v) || 0) : acc, 0)}
          </div>
          <div className="mt-1 text-[10px] text-cyan-300/70 font-mono">Verified SDK / Colab Ingestions</div>
        </div>

        <div className="panel bg-slate-900 border border-slate-800 rounded-lg p-3">
          <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider block mb-1">
            Strategy Backtests
          </span>
          <div className="text-2xl font-bold font-mono text-emerald-400">
            {stats.by_type?.strategy_backtest || 0}
          </div>
          <div className="mt-1 text-[10px] text-slate-400 font-mono">1-bar lagged walk-forward runs</div>
        </div>

        <div className="panel bg-slate-900 border border-slate-800 rounded-lg p-3">
          <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider block mb-1">
            Model Validations
          </span>
          <div className="text-2xl font-bold font-mono text-indigo-400">
            {stats.by_type?.model_validation || 0}
          </div>
          <div className="mt-1 text-[10px] text-slate-400 font-mono">Adversarial &amp; Kupiec audits</div>
        </div>

        <div className="panel bg-slate-900 border border-slate-800 rounded-lg p-3">
          <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider block mb-1">
            Fragility Matrices
          </span>
          <div className="text-2xl font-bold font-mono text-amber-400">
            {stats.by_type?.fragility_matrix || 0}
          </div>
          <div className="mt-1 text-[10px] text-slate-400 font-mono">2D assumption sensitivity runs</div>
        </div>
      </div>

      {/* Filter, Search & Batch Action Bar */}
      <div className="panel bg-slate-900 border border-slate-800 rounded-lg p-4 flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3">
          {/* Type Filter Pills */}
          <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-lg border border-slate-800">
            {[
              { id: 'all', label: 'All Types' },
              { id: 'orchestrated_test_suite', label: 'Test All Suites' },
              { id: 'external', label: 'External / Colab' },
              { id: 'strategy_backtest', label: 'Strategies' },
              { id: 'model_validation', label: 'Models' },
              { id: 'fragility_matrix', label: 'Fragility' },
              { id: 'studio_experiment', label: 'Studio' },
            ].map((tab) => (
              <button
                key={tab.id}
                onClick={() => setSelectedType(tab.id)}
                className={`px-2.5 py-1 text-xs rounded font-medium transition ${
                  selectedType === tab.id
                    ? 'bg-slate-800 text-slate-100 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Status Filter */}
          <select
            value={selectedStatus}
            onChange={(e) => setSelectedStatus(e.target.value)}
            className="bg-slate-950 border border-slate-800 rounded px-3 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-indigo-500"
          >
            <option value="all">All Statuses</option>
            <option value="completed">Completed</option>
            <option value="warning">Warning</option>
            <option value="failed">Failed</option>
          </select>
        </div>

        <div className="flex items-center gap-3">
          {/* Search Bar */}
          <form onSubmit={handleSearchSubmit} className="relative">
            <input
              type="text"
              placeholder="Search run ID, name, model..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-56 bg-slate-950 border border-slate-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
            />
            <Search size={14} className="absolute left-2.5 top-2 text-slate-500" />
          </form>

          {/* Comparison CTA Button */}
          {selectedRunIds.length >= 2 && (
            <button
              onClick={handleLaunchComparison}
              disabled={comparing}
              className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium rounded-lg shadow-sm transition flex items-center gap-2"
            >
              <GitBranch size={14} />
              Compare Selected ({selectedRunIds.length})
            </button>
          )}
        </div>
      </div>

      {/* Main Experiments Table */}
      <div className="panel bg-slate-900 border border-slate-800 rounded-lg overflow-hidden shadow-sm">
        {loading ? (
          <div className="py-16 text-center text-slate-400 text-xs flex flex-col items-center justify-center space-y-2">
            <RefreshCw size={20} className="animate-spin text-indigo-400" />
            <span>Querying unified experiment ledger...</span>
          </div>
        ) : runs.length === 0 ? (
          <div className="py-16 text-center text-slate-400 text-xs flex flex-col items-center justify-center space-y-3">
            <div className="w-12 h-12 rounded-full bg-slate-800 flex items-center justify-center text-slate-500">
              <Database size={22} />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-slate-200">No Research Experiments Logged</h3>
              <p className="text-xs text-slate-500 max-w-md mt-1">
                Execute runs in Strategy Backtest Lab (Page 08), Model Validation (Page 07), or Fragility Matrix (Page 06)
                to record cryptographic manifests in this central registry.
              </p>
            </div>
            <div className="flex items-center gap-3 pt-2">
              <button
                onClick={() => navigate?.('/strategies')}
                className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-medium rounded-lg"
              >
                Go to Strategy Lab
              </button>
              <button
                onClick={() => navigate?.('/models')}
                className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium rounded-lg"
              >
                Go to Model Validation
              </button>
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left border-collapse">
              <thead>
                <tr className="bg-slate-950 border-b border-slate-800 text-slate-400 font-mono">
                  <th className="py-3 px-3 w-10 text-center">
                    <span className="sr-only">Select</span>
                  </th>
                  <th className="py-3 px-3">Run ID</th>
                  <th className="py-3 px-3">Type</th>
                  <th className="py-3 px-3">Experiment Name</th>
                  <th className="py-3 px-3">Created</th>
                  <th className="py-3 px-3">Status</th>
                  <th className="py-3 px-3">Reproducibility</th>
                  <th className="py-3 px-3">Key Metrics</th>
                  <th className="py-3 px-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono text-slate-300">
                {runs.map((r) => {
                  const isSelected = selectedRunIds.includes(r.run_id);
                  return (
                    <tr
                      key={r.run_id}
                      className={`hover:bg-slate-800/40 transition ${isSelected ? 'bg-indigo-950/20' : ''}`}
                    >
                      <td className="py-3 px-3 text-center">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => handleToggleSelect(r.run_id)}
                          className="rounded border-slate-700 bg-slate-900 text-indigo-600 accent-indigo-500 focus:ring-0"
                        />
                      </td>

                      {/* Run ID with copy button */}
                      <td className="py-3 px-3">
                        <div className="flex items-center gap-1.5">
                          <span className="text-slate-100 font-semibold text-[11px]">{r.run_id}</span>
                          <button
                            onClick={() => handleCopyId(r.run_id)}
                            className="text-slate-500 hover:text-slate-300 p-0.5 rounded"
                            title="Copy Run ID"
                          >
                            {copiedId === r.run_id ? (
                              <Check size={12} className="text-emerald-400" />
                            ) : (
                              <Copy size={12} />
                            )}
                          </button>
                        </div>
                        {r.lineage?.parent_run_id && (
                          <div className="text-[10px] text-indigo-400 flex items-center gap-1 mt-0.5">
                            <GitBranch size={10} />
                            <span>Child of {r.lineage.parent_run_id}</span>
                          </div>
                        )}
                      </td>

                      {/* Run Type */}
                      <td className="py-3 px-3">{getRunTypeBadge(r.run_type)}</td>

                      {/* Name & Initiator */}
                      <td className="py-3 px-3 font-sans">
                        <div className="text-slate-200 font-semibold text-xs">{r.display_name}</div>
                        <div className="text-[10px] text-slate-500 font-mono">{r.initiating_user}</div>
                      </td>

                      {/* Timestamp */}
                      <td className="py-3 px-3 text-slate-400 text-[11px]">
                        {r.created_at ? new Date(r.created_at).toLocaleString() : 'N/A'}
                      </td>

                      {/* Status */}
                      <td className="py-3 px-3">
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${
                            r.status === 'completed'
                              ? 'bg-emerald-950/60 border-emerald-500/30 text-emerald-300'
                              : r.status === 'warning'
                              ? 'bg-amber-950/60 border-amber-500/30 text-amber-300'
                              : 'bg-rose-950/60 border-rose-500/30 text-rose-300'
                          }`}
                        >
                          {r.status?.toUpperCase() || 'COMPLETED'}
                        </span>
                      </td>

                      {/* Reproducibility */}
                      <td className="py-3 px-3">
                        <div className="flex items-center gap-1.5">
                          <ShieldCheck
                            size={14}
                            className={
                              r.reproducibility.includes('Exact') ? 'text-emerald-400' : 'text-sky-400'
                            }
                          />
                          <span
                            className={`text-[11px] ${
                              r.reproducibility.includes('Exact') ? 'text-emerald-300' : 'text-sky-300'
                            }`}
                          >
                            {r.reproducibility}
                          </span>
                        </div>
                        {r.dataset_hash && (
                          <div className="text-[10px] text-slate-500 mt-0.5 truncate max-w-[130px]" title={r.dataset_hash}>
                            SHA: {r.dataset_hash.slice(0, 10)}...
                          </div>
                        )}
                      </td>

                      {/* Key Metrics */}
                      <td className="py-3 px-3">
                        <div className="flex flex-wrap gap-1.5 max-w-[200px]">
                          {Object.entries(r.metrics_summary || {}).map(([k, v]) => (
                            <span
                              key={k}
                              className="px-1.5 py-0.5 rounded bg-slate-950 border border-slate-800 text-[10px] text-slate-300"
                            >
                              <span className="text-slate-500 mr-1">{k.replace('_', ' ')}:</span>
                              <span className="font-semibold text-slate-200">{String(v)}</span>
                            </span>
                          ))}
                        </div>
                      </td>

                      {/* Action Buttons */}
                      <td className="py-3 px-3 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          <button
                            onClick={() => setInspectRun(r)}
                            className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded transition"
                            title="Inspect Granular Record"
                          >
                            <Eye size={14} />
                          </button>

                          <button
                            onClick={() => handleRerun(r.run_id)}
                            className="p-1.5 text-slate-400 hover:text-indigo-300 hover:bg-slate-800 rounded transition"
                            title="Rerun with Lineage"
                          >
                            <RotateCw size={14} />
                          </button>

                          {/* Export dropdown menu */}
                          <div className="relative group inline-block text-left">
                            <button
                              className="p-1.5 text-slate-400 hover:text-emerald-300 hover:bg-slate-800 rounded transition"
                              title="Export Record"
                            >
                              <Download size={14} />
                            </button>
                            <div className="hidden group-hover:block absolute right-0 z-30 mt-1 w-32 rounded-md shadow-lg bg-slate-950 border border-slate-800 py-1">
                              <button
                                onClick={() => handleExport(r.run_id, 'markdown')}
                                className="block w-full text-left px-3 py-1.5 text-[11px] text-slate-300 hover:bg-slate-800"
                              >
                                Markdown Report
                              </button>
                              <button
                                onClick={() => handleExport(r.run_id, 'json')}
                                className="block w-full text-left px-3 py-1.5 text-[11px] text-slate-300 hover:bg-slate-800"
                              >
                                JSON Manifest
                              </button>
                              <button
                                onClick={() => handleExport(r.run_id, 'csv')}
                                className="block w-full text-left px-3 py-1.5 text-[11px] text-slate-300 hover:bg-slate-800"
                              >
                                CSV Metrics
                              </button>
                            </div>
                          </div>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Multi-Run Comparison Modal */}
      {comparisonData && (
        <div className="fixed inset-0 bg-black/75 z-50 flex items-center justify-center p-4 overflow-y-auto">
          <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto p-6 space-y-6 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-4">
              <div>
                <h3 className="text-base font-bold text-slate-100 flex items-center gap-2">
                  <GitBranch size={18} className="text-indigo-400" />
                  Side-by-Side Research Run Comparison
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Comparing {comparisonData.compared_runs?.length} runs against baseline:{' '}
                  <span className="font-mono text-indigo-300 font-semibold">
                    {comparisonData.compared_runs?.[0]?.run_id}
                  </span>
                </p>
              </div>
              <button
                onClick={() => setComparisonData(null)}
                className="text-slate-400 hover:text-slate-200 p-1 rounded-lg"
              >
                <X size={18} />
              </button>
            </div>

            {/* Warnings banner */}
            {comparisonData.warnings?.length > 0 && (
              <div className="p-3 bg-amber-950/30 border border-amber-500/40 rounded-lg text-xs text-amber-300 space-y-1">
                <div className="font-semibold flex items-center gap-1.5 text-amber-200">
                  <AlertTriangle size={14} className="text-amber-400" />
                  Comparison Incompatibility Warnings:
                </div>
                {comparisonData.warnings.map((w: string, i: number) => (
                  <div key={i} className="pl-5 text-[11px] text-amber-300/80">
                    • {w}
                  </div>
                ))}
              </div>
            )}

            {/* Section 1: Configuration Differences */}
            <div className="space-y-3">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                <Sliders size={14} className="text-indigo-400" />
                Configuration &amp; Hyperparameter Diff
              </h4>
              <div className="overflow-x-auto border border-slate-800 rounded-lg">
                <table className="w-full text-xs text-left">
                  <thead>
                    <tr className="bg-slate-950 border-b border-slate-800 text-slate-400 font-mono">
                      <th className="py-2.5 px-3">Parameter</th>
                      {comparisonData.compared_runs?.map((cr: any) => (
                        <th key={cr.run_id} className="py-2.5 px-3">
                          {cr.display_name} ({cr.run_id})
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-mono text-slate-300">
                    {comparisonData.config_diff?.map((row: any) => (
                      <tr
                        key={row.parameter}
                        className={!row.is_identical ? 'bg-amber-950/20 text-amber-200' : 'hover:bg-slate-800/30'}
                      >
                        <td className="py-2 px-3 font-semibold text-slate-300 flex items-center gap-1.5">
                          {!row.is_identical && <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />}
                          {row.parameter}
                        </td>
                        {comparisonData.compared_runs?.map((cr: any) => (
                          <td key={cr.run_id} className="py-2 px-3">
                            {row.values[cr.run_id] !== undefined
                              ? String(row.values[cr.run_id])
                              : '—'}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Section 2: Metric Deltas */}
            <div className="space-y-3">
              <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                <Sparkles size={14} className="text-emerald-400" />
                Metric Deltas vs Baseline
              </h4>
              <div className="overflow-x-auto border border-slate-800 rounded-lg">
                <table className="w-full text-xs text-left">
                  <thead>
                    <tr className="bg-slate-950 border-b border-slate-800 text-slate-400 font-mono">
                      <th className="py-2.5 px-3">Metric</th>
                      <th className="py-2.5 px-3">Baseline Value</th>
                      {comparisonData.compared_runs?.slice(1).map((cr: any) => (
                        <th key={cr.run_id} className="py-2.5 px-3">
                          {cr.display_name} (Delta)
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-mono text-slate-300">
                    {comparisonData.metric_deltas?.map((row: any) => (
                      <tr key={row.metric} className="hover:bg-slate-800/30">
                        <td className="py-2 px-3 font-semibold text-slate-300">
                          {row.metric.replace('_', ' ')}
                        </td>
                        <td className="py-2 px-3 text-slate-200">
                          {row.baseline_value !== null ? String(row.baseline_value) : '—'}
                        </td>
                        {comparisonData.compared_runs?.slice(1).map((cr: any) => {
                          const cand = row.candidates?.[cr.run_id];
                          if (!cand) return <td key={cr.run_id} className="py-2 px-3">—</td>;
                          const hasDelta = cand.delta !== null && cand.delta !== undefined;
                          return (
                            <td key={cr.run_id} className="py-2 px-3">
                              <span className="text-slate-100 mr-2">{cand.value}</span>
                              {hasDelta && (
                                <span
                                  className={`text-[10px] px-1.5 py-0.5 rounded ${
                                    cand.delta >= 0
                                      ? 'bg-emerald-950/60 text-emerald-400'
                                      : 'bg-rose-950/60 text-rose-400'
                                  }`}
                                >
                                  {cand.delta >= 0 ? '+' : ''}
                                  {cand.delta} ({cand.percentage_change >= 0 ? '+' : ''}
                                  {cand.percentage_change}%)
                                </span>
                              )}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setComparisonData(null)}
                className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium rounded-lg"
              >
                Close Comparison
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Detailed Inspection Drawer / Modal */}
      {inspectRun && (
        <div className="fixed inset-0 bg-black/75 z-50 flex items-center justify-center p-4 overflow-y-auto">
          <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-3xl w-full max-h-[90vh] overflow-y-auto p-6 space-y-6 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-4">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  {getRunTypeBadge(inspectRun.run_type)}
                  <span className="text-xs font-mono text-slate-400">ID: {inspectRun.run_id}</span>
                </div>
                <h3 className="text-base font-bold text-slate-100">{inspectRun.display_name}</h3>
              </div>
              <button
                onClick={() => setInspectRun(null)}
                className="text-slate-400 hover:text-slate-200 p-1 rounded-lg"
              >
                <X size={18} />
              </button>
            </div>

            {/* Overview Grid */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 p-3 bg-slate-950 rounded-lg border border-slate-800 text-xs font-mono">
              <div>
                <span className="text-[10px] text-slate-500 block">Created At</span>
                <span className="text-slate-300">
                  {inspectRun.created_at ? new Date(inspectRun.created_at).toLocaleString() : 'N/A'}
                </span>
              </div>
              <div>
                <span className="text-[10px] text-slate-500 block">Execution Status</span>
                <span className="text-emerald-400 font-semibold">{inspectRun.status.toUpperCase()}</span>
              </div>
              <div>
                <span className="text-[10px] text-slate-500 block">Initiating User</span>
                <span className="text-slate-300">{inspectRun.initiating_user}</span>
              </div>
              <div>
                <span className="text-[10px] text-slate-500 block">Reproducibility</span>
                <span className="text-emerald-300 font-semibold">{inspectRun.reproducibility}</span>
              </div>
            </div>

            {/* Data Provenance & Fingerprint */}
            <div className="p-4 bg-slate-950 rounded-lg border border-slate-800 space-y-2 text-xs">
              <h4 className="text-[11px] font-semibold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
                <Database size={14} className="text-emerald-400" />
                Data Provenance &amp; Cryptographic Fingerprint
              </h4>
              <div className="font-mono text-[11px] text-slate-400 space-y-1">
                <div>
                  <span className="text-slate-500">Provider:</span>{' '}
                  <span className="text-slate-200">
                    {inspectRun.data_provenance?.provider || 'upstox_v3'}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500">Dataset SHA-256:</span>{' '}
                  <span className="text-slate-200 break-all">
                    {inspectRun.dataset_hash || inspectRun.data_provenance?.fingerprint || 'N/A'}
                  </span>
                </div>
                <div>
                  <span className="text-slate-500">Observations Sampled:</span>{' '}
                  <span className="text-slate-200">
                    {inspectRun.data_provenance?.sample_size || 'N/A'} bars
                  </span>
                </div>
              </div>
            </div>

            {/* Specification / Configuration */}
            <div className="space-y-2">
              <h4 className="text-[11px] font-semibold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
                <Sliders size={14} className="text-indigo-400" />
                Specification &amp; Hyperparameters
              </h4>
              <pre className="p-3 bg-slate-950 border border-slate-800 rounded-lg text-[11px] font-mono text-emerald-300 overflow-x-auto max-h-48">
                {JSON.stringify(inspectRun.spec, null, 2)}
              </pre>
            </div>

            {/* Orchestrated Quantitative Test Suite Cards (if available) */}
            {inspectRun.result?.test_results && (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="text-[11px] font-semibold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
                    <Sparkles size={14} className="text-cyan-400" />
                    Multi-Engine Quantitative Test Suite Results
                  </h4>
                  <span className="text-xs font-mono text-cyan-400">
                    {Object.values(inspectRun.result.test_results).filter((t: any) => t.status === 'passed').length}/
                    {Object.keys(inspectRun.result.test_results).length} Modules Passed
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {Object.entries(inspectRun.result.test_results).map(([modId, mod]: [string, any]) => {
                    const isPassed = mod.status === 'passed';
                    const isUnsupported = mod.status === 'unsupported';
                    return (
                      <div
                        key={modId}
                        className={`p-3 rounded-lg border text-xs space-y-2 ${
                          isPassed
                            ? 'bg-slate-950 border-emerald-500/30'
                            : isUnsupported
                            ? 'bg-slate-950/60 border-amber-500/30'
                            : 'bg-slate-950 border-rose-500/30'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-slate-200">{mod.module_name || modId}</span>
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold ${
                              isPassed
                                ? 'bg-emerald-950 text-emerald-400 border border-emerald-500/40'
                                : isUnsupported
                                ? 'bg-amber-950 text-amber-400 border border-amber-500/40'
                                : 'bg-rose-950 text-rose-400 border border-rose-500/40'
                            }`}
                          >
                            {(mod.status || 'UNKNOWN').toUpperCase()}
                          </span>
                        </div>

                        {mod.execution_time_ms !== undefined && (
                          <div className="text-[10px] text-slate-500 font-mono">
                            Execution time: {mod.execution_time_ms}ms
                          </div>
                        )}

                        {mod.metrics && Object.keys(mod.metrics).length > 0 && (
                          <div className="p-2 bg-slate-900 rounded border border-slate-800 font-mono text-[11px] space-y-1">
                            {Object.entries(mod.metrics).slice(0, 4).map(([mKey, mVal]: [string, any]) => (
                              <div key={mKey} className="flex justify-between text-slate-400">
                                <span>{mKey}:</span>
                                <span className="text-slate-100 font-semibold">
                                  {typeof mVal.observed_value === 'number'
                                    ? Math.abs(mVal.observed_value) < 1
                                      ? `${(mVal.observed_value * 100).toFixed(2)}%`
                                      : mVal.observed_value.toFixed(4)
                                    : String(mVal.observed_value)}
                                </span>
                              </div>
                            ))}
                          </div>
                        )}

                        {mod.diagnostics && mod.diagnostics.length > 0 && (
                          <div className="text-[10px] text-slate-400 space-y-0.5">
                            {mod.diagnostics.slice(0, 2).map((diag: string, i: number) => (
                              <div key={i} className="flex items-start gap-1">
                                <span className={isPassed ? 'text-emerald-400' : isUnsupported ? 'text-amber-400' : 'text-rose-400'}>•</span>
                                <span>{diag}</span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Results & Metrics */}
            <div className="space-y-2">
              <h4 className="text-[11px] font-semibold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
                <FileText size={14} className="text-emerald-400" />
                Raw Execution Results &amp; Output Artifacts
              </h4>
              <pre className="p-3 bg-slate-950 border border-slate-800 rounded-lg text-[11px] font-mono text-slate-300 overflow-x-auto max-h-48">
                {JSON.stringify(inspectRun.result, null, 2)}
              </pre>
            </div>

            <div className="flex items-center justify-between pt-2 border-t border-slate-800">
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleExport(inspectRun.run_id, 'markdown')}
                  className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium rounded-lg flex items-center gap-1.5"
                >
                  <Download size={13} /> Export Markdown
                </button>
                <button
                  onClick={() => handleExport(inspectRun.run_id, 'json')}
                  className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium rounded-lg flex items-center gap-1.5"
                >
                  <Download size={13} /> Export JSON
                </button>
              </div>

              <button
                onClick={() => setInspectRun(null)}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium rounded-lg"
              >
                Close Inspector
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Test All / Custom Profile Launch Modal */}
      {showOrchestratorModal && (
        <div className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4 overflow-y-auto">
          <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto p-6 space-y-6 shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-800 pb-4">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-gradient-to-r from-indigo-950 to-cyan-950 text-cyan-300 border border-cyan-500/40">
                    TEST ORCHESTRATOR
                  </span>
                </div>
                <h3 className="text-base font-bold text-slate-100 flex items-center gap-2">
                  <Sparkles size={18} className="text-cyan-400" />
                  Execute Shared Test Suite &amp; Quantitative Laboratory
                </h3>
              </div>
              <button
                onClick={() => setShowOrchestratorModal(false)}
                className="text-slate-400 hover:text-slate-200 p-1 rounded-lg"
              >
                <X size={18} />
              </button>
            </div>

            <div className="space-y-4 text-xs">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="text-slate-400 block mb-1 font-medium">Experiment / Asset Type</label>
                  <select
                    value={orchTargetType}
                    onChange={(e) => {
                      setOrchTargetType(e.target.value);
                      setOrchValidationResults(null);
                    }}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-slate-200 font-mono"
                  >
                    <option value="model">Quantitative Model</option>
                    <option value="strategy">Trading Strategy</option>
                    <option value="portfolio">Multi-Asset Portfolio</option>
                    <option value="forecasting">Volatility Forecasting</option>
                  </select>
                </div>

                <div>
                  <label className="text-slate-400 block mb-1 font-medium">Target Instrument / Portfolio</label>
                  <select
                    value={orchTargetSymbol}
                    onChange={(e) => {
                      setOrchTargetSymbol(e.target.value);
                      setOrchValidationResults(null);
                    }}
                    className="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-slate-200 font-mono"
                  >
                    <option value="NIFTY_50">NSE NIFTY 50 Benchmark</option>
                    <option value="BANKNIFTY">NSE NIFTY BANK</option>
                    <option value="RELIANCE">RELIANCE Industries</option>
                    <option value="TCS">Tata Consultancy Services</option>
                    <option value="INFY">Infosys Ltd</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="text-slate-400 block mb-1 font-medium">Evaluation Profile</label>
                <div className="grid grid-cols-3 gap-2">
                  {[
                    { id: 'test_all', name: 'Test All (All 9 Engines)', desc: 'Full quantitative test coverage' },
                    { id: 'regulatory_basel_pack', name: 'Basel Regulatory Pack', desc: 'VaR, Kupiec POF & Basel traffic' },
                    { id: 'quick_risk_screen', name: 'Quick Risk Screen', desc: 'Stationarity & baseline risk' },
                  ].map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => {
                        setOrchProfileId(p.id);
                        setOrchValidationResults(null);
                      }}
                      className={`p-3 rounded-lg border text-left transition ${
                        orchProfileId === p.id
                          ? 'bg-indigo-950/60 border-indigo-500/60 text-indigo-200 shadow-md'
                          : 'bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      <div className="font-semibold text-[11px]">{p.name}</div>
                      <div className="text-[10px] text-slate-500 mt-1">{p.desc}</div>
                    </button>
                  ))}
                </div>
              </div>

              {/* Assumption Controls */}
              <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 space-y-3">
                <span className="text-[11px] font-semibold text-slate-300 block uppercase tracking-wider">
                  Configurable Quantitative Assumptions
                </span>
                <div className="grid grid-cols-3 gap-3">
                  <div>
                    <label className="text-[10px] text-slate-400 block mb-1">VaR / CVaR Confidence</label>
                    <select
                      value={orchConfidence}
                      onChange={(e) => setOrchConfidence(parseFloat(e.target.value))}
                      className="w-full bg-slate-900 border border-slate-750 rounded p-1.5 font-mono text-slate-200"
                    >
                      <option value={0.95}>95.0% Confidence</option>
                      <option value={0.99}>99.0% Confidence (Basel Standard)</option>
                    </select>
                  </div>

                  <div>
                    <label className="text-[10px] text-slate-400 block mb-1">Lookback Window</label>
                    <select
                      value={orchLookback}
                      onChange={(e) => setOrchLookback(parseInt(e.target.value, 10))}
                      className="w-full bg-slate-900 border border-slate-750 rounded p-1.5 font-mono text-slate-200"
                    >
                      <option value={30}>30 Days (Short-term)</option>
                      <option value={60}>60 Days (Quarterly)</option>
                      <option value={252}>252 Days (1 Year)</option>
                    </select>
                  </div>

                  <div>
                    <label className="text-[10px] text-slate-400 block mb-1">Reverse Stress Loss Boundary</label>
                    <select
                      value={orchShockBoundary}
                      onChange={(e) => setOrchShockBoundary(parseFloat(e.target.value))}
                      className="w-full bg-slate-900 border border-slate-750 rounded p-1.5 font-mono text-slate-200"
                    >
                      <option value={0.15}>15% Capital Drawdown</option>
                      <option value={0.20}>20% Capital Drawdown</option>
                      <option value={0.30}>30% Catastrophic Drawdown</option>
                    </select>
                  </div>
                </div>
              </div>

              {/* Pre-flight Validation Box */}
              {orchValidationResults && (
                <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 space-y-2">
                  <span className="text-[11px] font-semibold text-slate-300 block uppercase tracking-wider">
                    Pre-Flight Engine Compatibility
                  </span>
                  <div className="grid grid-cols-2 gap-2 max-h-36 overflow-y-auto">
                    {orchValidationResults.map((m) => (
                      <div
                        key={m.module_id}
                        className={`p-2 rounded border text-[11px] flex items-center justify-between ${
                          m.applicable
                            ? 'bg-emerald-950/40 border-emerald-500/30 text-emerald-300'
                            : 'bg-amber-950/40 border-amber-500/30 text-amber-400'
                        }`}
                      >
                        <span className="truncate pr-2">{m.name}</span>
                        <span className="font-mono text-[9px] font-bold">
                          {m.applicable ? 'READY' : 'UNSUPPORTED'}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="flex items-center justify-between pt-4 border-t border-slate-800">
              <button
                type="button"
                onClick={handleValidateOrchestrator}
                disabled={orchValidating || orchRunning}
                className="px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-medium flex items-center gap-1.5"
              >
                <ShieldCheck size={14} className={orchValidating ? 'animate-pulse' : ''} />
                {orchValidating ? 'Checking...' : 'Validate Compatibility'}
              </button>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setShowOrchestratorModal(false)}
                  className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-medium"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleExecuteOrchestrator}
                  disabled={orchRunning}
                  className="px-5 py-2 bg-gradient-to-r from-indigo-600 to-cyan-600 hover:from-indigo-500 hover:to-cyan-500 text-white rounded-lg text-xs font-bold shadow-lg shadow-indigo-500/20 flex items-center gap-2"
                >
                  <Sparkles size={14} className={orchRunning ? 'animate-spin' : ''} />
                  {orchRunning ? 'Running Test Suite...' : 'Execute Test Suite'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
