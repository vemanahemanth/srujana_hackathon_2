import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import {
  FileClock, Search, Filter, ShieldAlert, ArrowUpRight, Plus,
  Download, CheckCircle2, ChevronRight, X, AlertTriangle, BookOpen
} from 'lucide-react';

export interface ModelAssumptionItem {
  model_id: string;
  model_name: string;
  name?: string;
  family: string;
  mathematical_formulation: string;
  distributional_assumption: string;
  temporal_assumption: string;
  sample_size_precondition: string;
  parameter_assumptions: string[];
  known_failure_regimes: string[];
  fragility_attack_vulnerabilities: string[];
}

export function AssumptionsRegistry({
  navigate,
  notify,
}: {
  navigate: (path: string) => void;
  notify: (msg: string) => void;
}) {
  const [assumptions, setAssumptions] = useState<ModelAssumptionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [activeCategory, setActiveCategory] = useState('ALL');
  const [selectedAssumption, setSelectedAssumption] = useState<ModelAssumptionItem | null>(null);
  const [createModal, setCreateModal] = useState(false);
  const [newAssumption, setNewAssumption] = useState({
    model_id: '',
    model_name: '',
    family: 'Custom User Assumption',
    mathematical_formulation: 'y = f(x)',
    distributional_assumption: 'Empirical sample observations without parametric distribution prior.',
    temporal_assumption: 'Stationary return intervals over selected window.',
    sample_size_precondition: 'N >= 30',
    failure_regimes: 'Extreme volatility regime shifts and illiquid trading days.',
    vulnerabilities: 'Confidence level sensitivity, lookback horizon shifts',
  });

  useEffect(() => {
    loadCatalog();
  }, []);

  const loadCatalog = async () => {
    try {
      setLoading(true);
      const res = await api.getAssumptionsCatalog();
      if (res && res.assumptions) {
        setAssumptions(res.assumptions);
      }
    } catch (err: any) {
      notify(`Failed to load assumptions: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const categories = ['ALL', 'Parametric Normal', 'Non-Parametric', 'Time-Varying Volatility', 'Linear Regression'];

  const filtered = assumptions.filter(a => {
    const matchesSearch =
      (a.model_name || '').toLowerCase().includes(search.toLowerCase()) ||
      (a.model_id || '').toLowerCase().includes(search.toLowerCase()) ||
      (a.distributional_assumption || '').toLowerCase().includes(search.toLowerCase()) ||
      (a.temporal_assumption || '').toLowerCase().includes(search.toLowerCase());
    const matchesCat = activeCategory === 'ALL' || a.family === activeCategory;
    return matchesSearch && matchesCat;
  });

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newAssumption.model_id || !newAssumption.model_name) {
      notify('Please enter both Assumption ID and Model Name.');
      return;
    }
    const item: ModelAssumptionItem = {
      model_id: newAssumption.model_id.trim(),
      model_name: newAssumption.model_name.trim(),
      family: newAssumption.family,
      mathematical_formulation: newAssumption.mathematical_formulation,
      distributional_assumption: newAssumption.distributional_assumption,
      temporal_assumption: newAssumption.temporal_assumption,
      sample_size_precondition: newAssumption.sample_size_precondition,
      parameter_assumptions: ['User registered parameters'],
      known_failure_regimes: [newAssumption.failure_regimes],
      fragility_attack_vulnerabilities: [newAssumption.vulnerabilities],
    };
    setAssumptions([item, ...assumptions]);
    setCreateModal(false);
    notify(`Registered custom assumption "${item.model_name}".`);
  };

  const exportRegistry = (format: 'json' | 'csv') => {
    if (format === 'json') {
      const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(assumptions, null, 2));
      const downloadAnchor = document.createElement('a');
      downloadAnchor.setAttribute('href', dataStr);
      downloadAnchor.setAttribute('download', 'fragilityshield_assumptions_registry.json');
      document.body.appendChild(downloadAnchor);
      downloadAnchor.click();
      downloadAnchor.remove();
      notify('Exported assumptions registry as JSON.');
    } else {
      const headers = ['model_id', 'model_name', 'family', 'distributional_assumption', 'temporal_assumption', 'precondition'];
      const rows = assumptions.map(a => [
        `"${a.model_id}"`,
        `"${a.model_name}"`,
        `"${a.family}"`,
        `"${(a.distributional_assumption || '').replace(/"/g, '""')}"`,
        `"${(a.temporal_assumption || '').replace(/"/g, '""')}"`,
        `"${(a.sample_size_precondition || '').replace(/"/g, '""')}"`,
      ]);
      const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
      const encodedUri = encodeURI(csvContent);
      const link = document.createElement('a');
      link.setAttribute('href', encodedUri);
      link.setAttribute('download', 'fragilityshield_assumptions_registry.csv');
      document.body.appendChild(link);
      link.click();
      link.remove();
      notify('Exported assumptions registry as CSV.');
    }
  };

  return (
    <div className="stack-layout">
      {/* Hero Banner */}
      <section className="panel generic-hero">
        <div className="generic-mark"><FileClock size={22} /></div>
        <div>
          <span className="section-kicker">GOVERNANCE &amp; METHODOLOGY / PAGE 11</span>
          <h2>Assumptions Registry &amp; Failure Regimes</h2>
          <p>
            Searchable, versioned inventory of mathematical preconditions, distributional hypotheses, and documented breakdown modes across all quantitative risk models.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button className="button secondary small inline-flex items-center gap-1" onClick={() => exportRegistry('csv')}>
            <Download size={14} /> Export CSV
          </button>
          <button className="button secondary small inline-flex items-center gap-1" onClick={() => exportRegistry('json')}>
            <Download size={14} /> Export JSON
          </button>
          <button className="button primary small inline-flex items-center gap-1" onClick={() => setCreateModal(true)}>
            <Plus size={14} /> Register Assumption
          </button>
        </div>
      </section>

      {/* Filter and Search Bar */}
      <section className="panel">
        <div className="flex flex-wrap items-center justify-between gap-3 p-4">
          <div className="flex items-center gap-2 flex-1 min-w-[280px]">
            <Search size={16} className="text-muted" />
            <input
              type="text"
              placeholder="Search assumptions by ID, name, formula or breakdown mode..."
              className="bg-transparent border-0 text-sm focus:outline-none w-full"
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            {search && (
              <button onClick={() => setSearch('')} className="text-muted hover:text-foreground">
                <X size={14} />
              </button>
            )}
          </div>
          <div className="flex items-center gap-1">
            <Filter size={14} className="text-muted mr-1" />
            {categories.map(cat => (
              <button
                key={cat}
                className={`button text-xs py-1 px-2.5 ${activeCategory === cat ? 'primary' : 'secondary'}`}
                onClick={() => setActiveCategory(cat)}
              >
                {cat}
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* Assumptions Table */}
      <section className="panel table-panel">
        <div className="panel-head">
          <div>
            <span className="section-kicker">MODEL SPECIFICATIONS</span>
            <h2>Active Registered Assumptions ({filtered.length})</h2>
          </div>
          <span className="badge" style={{ background: 'rgba(37,125,112,0.2)', color: '#257d70' }}>
            NATIVE CATALOG
          </span>
        </div>

        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Assumption ID</th>
                <th>Model / Framework</th>
                <th>Family</th>
                <th>Distributional Prior</th>
                <th>Precondition</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} className="text-center py-8 text-muted">
                    Loading formal mathematical assumptions from FragilityEngine...
                  </td>
                </tr>
              ) : filtered.length ? (
                filtered.map(item => (
                  <tr key={item.model_id} className="cursor-pointer hover:bg-white/[0.02]" onClick={() => setSelectedAssumption(item)}>
                    <td>
                      <span className="font-mono text-xs font-semibold text-primary">{item.model_id}</span>
                    </td>
                    <td>
                      <div className="font-semibold text-sm">{item.model_name}</div>
                      <div className="text-xs text-muted font-mono truncate max-w-xs">{item.mathematical_formulation}</div>
                    </td>
                    <td>
                      <span className="badge text-xs" style={{ background: 'rgba(210,155,74,0.15)', color: '#d29b4a' }}>
                        {item.family}
                      </span>
                    </td>
                    <td>
                      <div className="text-xs max-w-sm line-clamp-2 text-muted">{item.distributional_assumption}</div>
                    </td>
                    <td>
                      <span className="font-mono text-xs">{item.sample_size_precondition}</span>
                    </td>
                    <td>
                      <button
                        className="button secondary small inline-flex items-center gap-1"
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedAssumption(item);
                        }}
                      >
                        Inspect <ChevronRight size={13} />
                      </button>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={6} className="text-center py-8 text-muted">
                    No model assumptions match the current filter criteria.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Detailed Inspection Drawer / Modal */}
      {selectedAssumption && (
        <div className="overlay" onMouseDown={() => setSelectedAssumption(null)}>
          <div className="command-modal max-w-2xl" onMouseDown={e => e.stopPropagation()}>
            <div className="panel-head border-b border-border p-4">
              <div>
                <span className="section-kicker font-mono">{selectedAssumption.model_id}</span>
                <h2 className="text-lg font-bold">{selectedAssumption.model_name}</h2>
              </div>
              <button onClick={() => setSelectedAssumption(null)} className="icon-btn">
                <X size={16} />
              </button>
            </div>

            <div className="p-6 space-y-4 max-h-[70vh] overflow-y-auto">
              <div>
                <span className="text-xs font-semibold text-muted block mb-1">MATHEMATICAL FORMULATION</span>
                <div className="bg-black/40 p-3 rounded font-mono text-sm border border-border/50 text-accent">
                  {selectedAssumption.mathematical_formulation}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <span className="text-xs font-semibold text-muted block mb-1">DISTRIBUTIONAL HYPOTHESIS</span>
                  <p className="text-xs text-foreground bg-white/[0.02] p-2.5 rounded border border-border/30">
                    {selectedAssumption.distributional_assumption}
                  </p>
                </div>
                <div>
                  <span className="text-xs font-semibold text-muted block mb-1">TEMPORAL DYNAMICS</span>
                  <p className="text-xs text-foreground bg-white/[0.02] p-2.5 rounded border border-border/30">
                    {selectedAssumption.temporal_assumption}
                  </p>
                </div>
              </div>

              <div>
                <span className="text-xs font-semibold text-muted block mb-1">PRECONDITION REQUIREMENTS</span>
                <div className="text-xs text-foreground bg-white/[0.02] p-2.5 rounded border border-border/30">
                  {selectedAssumption.sample_size_precondition}
                </div>
              </div>

              <div>
                <span className="text-xs font-semibold text-muted flex items-center gap-1 mb-1 text-destructive">
                  <AlertTriangle size={13} /> DOCUMENTED FAILURE REGIMES
                </span>
                <ul className="space-y-1.5">
                  {selectedAssumption.known_failure_regimes.map((reg, idx) => (
                    <li key={idx} className="text-xs text-muted flex items-start gap-2 bg-destructive/10 p-2 rounded border border-destructive/20">
                      <span className="text-destructive font-bold">•</span>
                      <span>{reg}</span>
                    </li>
                  ))}
                </ul>
              </div>

              <div>
                <span className="text-xs font-semibold text-muted flex items-center gap-1 mb-1 text-primary">
                  <ShieldAlert size={13} /> FRAGILITY ATTACK VULNERABILITIES
                </span>
                <ul className="space-y-1.5">
                  {selectedAssumption.fragility_attack_vulnerabilities.map((vuln, idx) => (
                    <li key={idx} className="text-xs text-muted flex items-start gap-2 bg-primary/10 p-2 rounded border border-primary/20">
                      <span className="text-primary font-bold">•</span>
                      <span>{vuln}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            <div className="border-t border-border p-4 flex items-center justify-between bg-black/20">
              <span className="text-xs text-muted">FragilityShield Governance Protocol (§4)</span>
              <div className="flex items-center gap-2">
                <button
                  className="button secondary small"
                  onClick={() => {
                    setSelectedAssumption(null);
                    navigate('/labs/fragility');
                  }}
                >
                  <ArrowUpRight size={13} /> Attack in Fragility Lab
                </button>
                <button className="button primary small" onClick={() => setSelectedAssumption(null)}>
                  Done
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Register Custom Assumption Modal */}
      {createModal && (
        <div className="overlay" onMouseDown={() => setCreateModal(false)}>
          <div className="command-modal max-w-xl" onMouseDown={e => e.stopPropagation()}>
            <form onSubmit={handleCreate}>
              <div className="panel-head border-b border-border p-4">
                <div>
                  <span className="section-kicker">METHODOLOGY EXPANSION</span>
                  <h2 className="text-lg font-bold">Register Model Assumption</h2>
                </div>
                <button type="button" onClick={() => setCreateModal(false)} className="icon-btn">
                  <X size={16} />
                </button>
              </div>

              <div className="p-6 space-y-3 max-h-[70vh] overflow-y-auto">
                <label className="field-label">
                  ASSUMPTION IDENTIFIER *
                  <input
                    placeholder="e.g. user.student_t_copula"
                    value={newAssumption.model_id}
                    onChange={e => setNewAssumption({ ...newAssumption, model_id: e.target.value })}
                    required
                  />
                </label>
                <label className="field-label">
                  MODEL / FRAMEWORK NAME *
                  <input
                    placeholder="e.g. Multivariate Student-t Copula VaR"
                    value={newAssumption.model_name}
                    onChange={e => setNewAssumption({ ...newAssumption, model_name: e.target.value })}
                    required
                  />
                </label>
                <label className="field-label">
                  MATHEMATICAL FORMULATION
                  <input
                    placeholder="e.g. C(u_1, u_2; \nu, R)"
                    value={newAssumption.mathematical_formulation}
                    onChange={e => setNewAssumption({ ...newAssumption, mathematical_formulation: e.target.value })}
                  />
                </label>
                <label className="field-label">
                  DISTRIBUTIONAL HYPOTHESIS
                  <textarea
                    rows={2}
                    value={newAssumption.distributional_assumption}
                    onChange={e => setNewAssumption({ ...newAssumption, distributional_assumption: e.target.value })}
                  />
                </label>
                <label className="field-label">
                  FAILURE REGIMES (BREAKDOWN MODES)
                  <textarea
                    rows={2}
                    value={newAssumption.failure_regimes}
                    onChange={e => setNewAssumption({ ...newAssumption, failure_regimes: e.target.value })}
                  />
                </label>
              </div>

              <div className="border-t border-border p-4 flex items-center justify-end gap-2 bg-black/20">
                <button type="button" className="button secondary small" onClick={() => setCreateModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="button primary small">
                  Save to Registry
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
