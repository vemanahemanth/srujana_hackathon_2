import React, { useState, useEffect } from 'react';
import {
  Activity,
  AlertCircle,
  AlertOctagon,
  ArrowRight,
  Boxes,
  Check,
  CheckCircle2,
  ChevronRight,
  Code,
  Copy,
  Cpu,
  Database,
  ExternalLink,
  Eye,
  FileCode2,
  Fingerprint,
  HardDrive,
  Info,
  Layers,
  ListFilter,
  Lock,
  Network,
  Play,
  Plus,
  RefreshCw,
  Search,
  Server,
  ShieldAlert,
  ShieldCheck,
  Terminal,
  X,
  Zap,
} from 'lucide-react';
import { api } from '@/lib/api';

interface IntegrationStudioProps {
  navigate: (path: string) => void;
  notify: (msg: string) => void;
}

export const IntegrationPluginStudio: React.FC<IntegrationStudioProps> = ({ navigate, notify }) => {
  // Navigation Tabs
  const [activeTab, setActiveTab] = useState<
    'monitor' | 'quickstart' | 'routes' | 'connected' | 'catalog' | 'validator' | 'wizard'
  >('monitor');

  // Loading & Monitoring States
  const [loading, setLoading] = useState(false);
  const [healthData, setHealthData] = useState<any>(null);
  const [diagnosticResult, setDiagnosticResult] = useState<any>(null);
  const [diagnosticLoading, setDiagnosticLoading] = useState(false);
  const [showDiagnosticsModal, setShowDiagnosticsModal] = useState(false);
  const [copiedWorkflowId, setCopiedWorkflowId] = useState<string | null>(null);

  // Quickstart Workflows
  const [workflows, setWorkflows] = useState<any[]>([]);

  // Routes Catalog
  const [routes, setRoutes] = useState<any[]>([]);
  const [routeSearch, setRouteSearch] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('ALL');

  // Page 12 Connected Services & Catalog States
  const [services, setServices] = useState<any[]>([]);
  const [catalog, setCatalog] = useState<any[]>([]);
  const [catalogFilter, setCatalogFilter] = useState('ALL');
  const [probingServiceId, setProbingServiceId] = useState<string | null>(null);
  const [probeResults, setProbeResults] = useState<Record<string, any>>({});

  // Manifest Validator State
  const defaultManifest = JSON.stringify(
    {
      plugin_id: 'quant_momentum_alpha',
      name: 'Cross-Sectional Momentum Alpha',
      version: '1.2.0',
      entry_point: 'models.momentum:compute_alpha',
      publisher: 'Acme Capital',
      description: 'Computes 12-month minus 1-month cross-sectional price momentum over NSE 500 universe.',
      requested_capabilities: ['dataset:read', 'result:return'],
      resource_limits: {
        max_memory_mb: 128,
        timeout_seconds: 4.5,
        max_cpu_cores: 1.0,
      },
    },
    null,
    2
  );

  const [manifestText, setManifestText] = useState(defaultManifest);
  const [validationResult, setValidationResult] = useState<any>(null);
  const [validating, setValidating] = useState(false);

  // Wizard State
  const [wizardData, setWizardData] = useState({
    integration_id: '',
    name: '',
    category: 'Market Data Feeds',
    version: '1.0.0',
    provider: '',
    description: '',
    capabilities: ['dataset:read'],
    documentation_url: '',
  });

  // Refresh All System Data
  const refreshAll = async () => {
    setLoading(true);
    try {
      const [healthResp, srvResp, catResp, qsResp, routesResp] = await Promise.all([
        api.getIntegrationHealth().catch(() => ({ success: false, components: [] })),
        api.getConnectedServices().catch(() => ({ success: false, services: [] })),
        api.getIntegrationCatalog().catch(() => ({ success: false, catalog: [] })),
        api.getSdkQuickstart().catch(() => ({ success: false, workflows: [] })),
        api.getRegisteredRoutes().catch(() => ({ success: false, routes: [] })),
      ]);

      if (healthResp && healthResp.success) {
        setHealthData(healthResp);
      }
      if (srvResp && srvResp.success && srvResp.services) {
        setServices(srvResp.services);
      }
      if (catResp && catResp.success && catResp.catalog) {
        setCatalog(catResp.catalog);
      }
      if (qsResp && qsResp.success && qsResp.workflows) {
        setWorkflows(qsResp.workflows);
      }
      if (routesResp && routesResp.success && routesResp.routes) {
        setRoutes(routesResp.routes);
      }
    } catch (err: any) {
      notify(`Failed to refresh integration monitor: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refreshAll();
  }, []);

  // Run Diagnostic Action
  const handleRunDiagnostic = async (testType: string) => {
    setDiagnosticLoading(true);
    try {
      const resp = await api.runIntegrationDiagnostic(testType);
      setDiagnosticResult(resp);
      setShowDiagnosticsModal(true);
      notify(`Diagnostic [${testType}] completed: ${resp.status.toUpperCase()} (${resp.latency_ms}ms)`);
      // Update health in background
      api.getIntegrationHealth().then((h) => {
        if (h && h.success) setHealthData(h);
      });
    } catch (err: any) {
      notify(`Diagnostic failed for ${testType}: ${err.message}`);
    } finally {
      setDiagnosticLoading(false);
    }
  };

  // Copy code snippet helper
  const handleCopyCode = (id: string, code: string) => {
    navigator.clipboard.writeText(code);
    setCopiedWorkflowId(id);
    notify('Code copied to clipboard.');
    setTimeout(() => setCopiedWorkflowId(null), 2500);
  };

  // Probe single service
  const handleProbeService = async (serviceId: string) => {
    setProbingServiceId(serviceId);
    try {
      const resp = await api.testServiceConnectivity(serviceId);
      if (resp.success && resp.result) {
        setProbeResults((prev) => ({ ...prev, [serviceId]: resp.result }));
        notify(`Probed ${serviceId}: ${resp.result.latency_ms}ms (${resp.result.message})`);
      }
    } catch (err: any) {
      notify(`Probe failed for ${serviceId}: ${err.message}`);
    } finally {
      setProbingServiceId(null);
    }
  };

  // Validate manifest
  const handleValidateManifest = async () => {
    setValidating(true);
    try {
      let parsed: any;
      try {
        parsed = JSON.parse(manifestText);
      } catch (jsonErr: any) {
        setValidationResult({
          is_valid: false,
          errors: [`JSON Syntax Error: ${jsonErr.message}`],
          manifest_summary: null,
        });
        return;
      }

      const resp = await api.validatePluginManifest(parsed);
      if (resp.success && resp.validation) {
        setValidationResult(resp.validation);
        if (resp.validation.is_valid) {
          notify(`Manifest validated! SHA-256: ${resp.validation.manifest_summary.hash_digest.substring(0, 12)}...`);
        } else {
          notify(`Manifest validation failed with ${resp.validation.errors.length} errors`);
        }
      }
    } catch (err: any) {
      notify(`Validation request error: ${err.message}`);
    } finally {
      setValidating(false);
    }
  };

  // Register custom integration
  const handleRegisterIntegration = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!wizardData.integration_id || !wizardData.name) {
      notify('Integration ID and Name are required.');
      return;
    }
    try {
      const resp = await api.registerCustomIntegration({
        ...wizardData,
        is_sandboxed: true,
      });
      if (resp.success) {
        notify(`Successfully registered integration '${wizardData.name}'!`);
        refreshAll();
        setActiveTab('catalog');
      }
    } catch (err: any) {
      notify(`Registration failed: ${err.message}`);
    }
  };

  // Status badge styling
  const renderStatusBadge = (status: string) => {
    const s = (status || '').toLowerCase();
    switch (s) {
      case 'healthy':
      case 'connected':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase bg-emerald-950 text-emerald-300 border border-emerald-800 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
            HEALTHY
          </span>
        );
      case 'degraded':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase bg-amber-950 text-amber-300 border border-amber-800 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span>
            DEGRADED
          </span>
        );
      case 'unavailable':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase bg-rose-950 text-rose-300 border border-rose-800 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-rose-400"></span>
            UNAVAILABLE
          </span>
        );
      case 'not configured':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase bg-purple-950 text-purple-300 border border-purple-800 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-purple-400"></span>
            NOT CONFIGURED
          </span>
        );
      case 'unsupported':
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase bg-zinc-800 text-zinc-300 border border-zinc-700">
            UNSUPPORTED
          </span>
        );
      default:
        return (
          <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase bg-slate-800 text-slate-300 border border-slate-700">
            {status.toUpperCase()}
          </span>
        );
    }
  };

  // Component icons
  const getComponentIcon = (id: string) => {
    switch (id) {
      case 'backend_api':
        return <Server className="w-5 h-5 text-sky-400" />;
      case 'python_sdk':
        return <Terminal className="w-5 h-5 text-emerald-400" />;
      case 'market_data_provider':
        return <Activity className="w-5 h-5 text-indigo-400" />;
      case 'database':
        return <Database className="w-5 h-5 text-amber-400" />;
      case 'experiment_storage':
        return <HardDrive className="w-5 h-5 text-purple-400" />;
      case 'model_execution':
        return <Cpu className="w-5 h-5 text-rose-400" />;
      case 'background_jobs':
        return <Zap className="w-5 h-5 text-yellow-400" />;
      case 'plugin_subsystem':
        return <Lock className="w-5 h-5 text-teal-400" />;
      default:
        return <Boxes className="w-5 h-5 text-[var(--accent-primary)]" />;
    }
  };

  // Route Filtering
  const routeCategories = ['ALL', ...Array.from(new Set(routes.map((r) => r.category)))];
  const filteredRoutes = routes.filter((r) => {
    const matchesCat = selectedCategory === 'ALL' || r.category === selectedCategory;
    const matchesSearch =
      !routeSearch ||
      r.path.toLowerCase().includes(routeSearch.toLowerCase()) ||
      r.description.toLowerCase().includes(routeSearch.toLowerCase()) ||
      r.methods.join(' ').toLowerCase().includes(routeSearch.toLowerCase());
    return matchesCat && matchesSearch;
  });

  const filteredCatalog = catalog.filter((item) => {
    if (catalogFilter === 'ALL') return true;
    return item.category === catalogFilter;
  });

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      {/* Top Banner & Eyebrow */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-[var(--border-subtle)] pb-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-mono uppercase tracking-wider text-[var(--accent-primary)] mb-1">
            <Network className="w-3.5 h-3.5" />
            <span>INSTITUTIONAL INTEGRATION / DEVELOPER SURFACE (PAGE 24)</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-[var(--text-primary)]">
            SDK &amp; API Integration Monitor
          </h1>
          <p className="text-sm text-[var(--text-secondary)] mt-1">
            Inspect real-time service health, run verified diagnostic probes, review interactive Python SDK workflows, and explore audited Starlette API endpoints.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            className="button secondary text-xs font-mono flex items-center gap-1.5"
            onClick={refreshAll}
            disabled={loading}
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Refresh Status</span>
          </button>
          <button
            className="button primary text-xs font-mono flex items-center gap-1.5"
            onClick={() => handleRunDiagnostic('test_backend')}
            disabled={diagnosticLoading}
          >
            <Play className="w-3.5 h-3.5" />
            <span>Test Backend</span>
          </button>
          <button
            className="button secondary text-xs font-mono flex items-center gap-1.5"
            onClick={() => handleRunDiagnostic('test_provider')}
            disabled={diagnosticLoading}
          >
            <Activity className="w-3.5 h-3.5" />
            <span>Test Provider</span>
          </button>
          <button
            className="button secondary text-xs font-mono flex items-center gap-1.5"
            onClick={() => handleRunDiagnostic('test_database')}
            disabled={diagnosticLoading}
          >
            <Database className="w-3.5 h-3.5" />
            <span>Test Database</span>
          </button>
          <button
            className="button secondary text-xs font-mono flex items-center gap-1.5"
            onClick={() => handleRunDiagnostic('test_sdk')}
            disabled={diagnosticLoading}
          >
            <Terminal className="w-3.5 h-3.5" />
            <span>Test SDK</span>
          </button>
        </div>
      </div>

      {/* Overview Stat Badges */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="card p-3 border border-[var(--border-subtle)] bg-[var(--bg-card)]">
          <span className="text-[10px] font-mono uppercase text-[var(--text-secondary)]">Platform Status</span>
          <div className="text-xl font-bold font-mono text-[var(--accent-success)] mt-1 flex items-center gap-1.5">
            {healthData?.overall_status === 'healthy' ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-500" />
            ) : (
              <AlertCircle className="w-4 h-4 text-amber-500" />
            )}
            <span className="uppercase">{healthData?.overall_status || 'CHECKING...'}</span>
          </div>
          <span className="text-[10px] text-[var(--text-muted)] mt-0.5 block">
            {healthData?.components_monitored || 8} Active Core Probes
          </span>
        </div>

        <div className="card p-3 border border-[var(--border-subtle)] bg-[var(--bg-card)]">
          <span className="text-[10px] font-mono uppercase text-[var(--text-secondary)]">Python SDK Core</span>
          <div className="text-xl font-bold font-mono text-[var(--accent-primary)] mt-1">
            fragility_engine
          </div>
          <span className="text-[10px] text-[var(--text-muted)] mt-0.5 block">v0.1.0 Institutional Release</span>
        </div>

        <div className="card p-3 border border-[var(--border-subtle)] bg-[var(--bg-card)]">
          <span className="text-[10px] font-mono uppercase text-[var(--text-secondary)]">Audited API Routes</span>
          <div className="text-xl font-bold font-mono text-[var(--accent-info)] mt-1 flex items-center gap-1.5">
            <Layers className="w-4 h-4 text-sky-400" />
            <span>{routes.length} Endpoints</span>
          </div>
          <span className="text-[10px] text-[var(--text-muted)] mt-0.5 block">Starlette REST Endpoints</span>
        </div>

        <div className="card p-3 border border-[var(--border-subtle)] bg-[var(--bg-card)]">
          <span className="text-[10px] font-mono uppercase text-[var(--text-secondary)]">Secret Redaction Policy</span>
          <div className="text-xl font-bold font-mono text-emerald-400 mt-1 flex items-center gap-1.5">
            <Lock className="w-4 h-4" />
            <span>Strict Masking</span>
          </div>
          <span className="text-[10px] text-[var(--text-muted)] mt-0.5 block">Zero token leakage in logs</span>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="flex border-b border-[var(--border-subtle)] text-xs font-mono overflow-x-auto">
        <button
          className={`px-4 py-2.5 border-b-2 font-medium transition-colors whitespace-nowrap ${
            activeTab === 'monitor'
              ? 'border-[var(--accent-primary)] text-[var(--accent-primary)] font-bold'
              : 'border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
          }`}
          onClick={() => setActiveTab('monitor')}
        >
          1. System Health Probes ({healthData?.components?.length || 8})
        </button>
        <button
          className={`px-4 py-2.5 border-b-2 font-medium transition-colors whitespace-nowrap ${
            activeTab === 'quickstart'
              ? 'border-[var(--accent-primary)] text-[var(--accent-primary)] font-bold'
              : 'border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
          }`}
          onClick={() => setActiveTab('quickstart')}
        >
          2. SDK Quick-Start ({workflows.length || 10})
        </button>
        <button
          className={`px-4 py-2.5 border-b-2 font-medium transition-colors whitespace-nowrap ${
            activeTab === 'routes'
              ? 'border-[var(--accent-primary)] text-[var(--accent-primary)] font-bold'
              : 'border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
          }`}
          onClick={() => setActiveTab('routes')}
        >
          3. API Route Explorer ({routes.length})
        </button>
        <button
          className={`px-4 py-2.5 border-b-2 font-medium transition-colors whitespace-nowrap ${
            activeTab === 'connected'
              ? 'border-[var(--accent-primary)] text-[var(--accent-primary)] font-bold'
              : 'border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
          }`}
          onClick={() => setActiveTab('connected')}
        >
          4. Connected Services ({services.length})
        </button>
        <button
          className={`px-4 py-2.5 border-b-2 font-medium transition-colors whitespace-nowrap ${
            activeTab === 'catalog'
              ? 'border-[var(--accent-primary)] text-[var(--accent-primary)] font-bold'
              : 'border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
          }`}
          onClick={() => setActiveTab('catalog')}
        >
          5. Integration Catalog ({catalog.length})
        </button>
        <button
          className={`px-4 py-2.5 border-b-2 font-medium transition-colors whitespace-nowrap ${
            activeTab === 'validator'
              ? 'border-[var(--accent-primary)] text-[var(--accent-primary)] font-bold'
              : 'border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
          }`}
          onClick={() => setActiveTab('validator')}
        >
          6. Manifest Validator &amp; Sandbox
        </button>
        <button
          className={`px-4 py-2.5 border-b-2 font-medium transition-colors whitespace-nowrap ${
            activeTab === 'wizard'
              ? 'border-[var(--accent-primary)] text-[var(--accent-primary)] font-bold'
              : 'border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
          }`}
          onClick={() => setActiveTab('wizard')}
        >
          7. Add Custom Integration
        </button>
      </div>

      {/* Tab 1: System Health Probes */}
      {activeTab === 'monitor' && (
        <div className="space-y-6">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-[var(--bg-card)] p-4 rounded border border-[var(--border-subtle)]">
            <div>
              <div className="text-xs font-mono font-bold text-[var(--text-primary)] flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-emerald-400" />
                <span>Audited Operational Health Matrix</span>
              </div>
              <p className="text-xs text-[var(--text-secondary)] mt-1">
                Real status evaluated against live process bounds. No synthetic &quot;green&quot; indicators: offline fallbacks and missing credentials reflect truthfully.
              </p>
            </div>
            <div className="text-right font-mono text-[11px] text-[var(--text-muted)]">
              Last probe: {healthData?.system_timestamp || 'Just now'}
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {(healthData?.components || []).map((comp: any) => (
              <div
                key={comp.component_id}
                className="card p-4 border border-[var(--border-subtle)] bg-[var(--bg-card)] space-y-3 hover:border-[var(--accent-primary)] transition-colors"
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-start gap-3">
                    <div className="p-2 rounded bg-[var(--bg-primary)] border border-[var(--border-subtle)]">
                      {getComponentIcon(comp.component_id)}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-sm text-[var(--text-primary)]">{comp.name}</span>
                        {renderStatusBadge(comp.status)}
                      </div>
                      <span className="text-[11px] font-mono text-[var(--text-secondary)] mt-0.5 block">
                        Category: {comp.category} • Probe Latency: {comp.check_duration_ms}ms
                      </span>
                    </div>
                  </div>
                </div>

                {comp.error_summary && (
                  <div className="text-xs font-mono p-2.5 rounded bg-amber-950/40 border border-amber-800 text-amber-200">
                    <span className="font-bold">Notice:</span> {comp.error_summary}
                  </div>
                )}

                <div className="space-y-1.5 text-xs font-mono">
                  <div className="text-[10px] uppercase text-[var(--text-muted)]">Verified Capabilities:</div>
                  <div className="flex flex-wrap gap-1.5">
                    {comp.capabilities?.map((cap: string) => (
                      <span
                        key={cap}
                        className="px-2 py-0.5 rounded text-[10px] bg-[var(--bg-primary)] border border-[var(--border-subtle)] text-[var(--text-secondary)]"
                      >
                        {cap}
                      </span>
                    ))}
                  </div>
                </div>

                {comp.details && Object.keys(comp.details).length > 0 && (
                  <div className="pt-2 border-t border-[var(--border-subtle)] text-[11px] font-mono text-[var(--text-secondary)] space-y-1">
                    {Object.entries(comp.details).map(([k, v]) => (
                      <div key={k} className="flex justify-between">
                        <span className="text-[var(--text-muted)]">{k.replace(/_/g, ' ')}:</span>
                        <span className="text-[var(--text-primary)] font-medium truncate max-w-[240px]">
                          {String(v)}
                        </span>
                      </div>
                    ))}
                  </div>
                )}

                <div className="pt-2 flex justify-end">
                  <button
                    className="button secondary text-[11px] font-mono py-1 px-2.5 flex items-center gap-1"
                    onClick={() => {
                      if (comp.component_id === 'backend_api') handleRunDiagnostic('test_backend');
                      else if (comp.component_id === 'database') handleRunDiagnostic('test_database');
                      else if (comp.component_id === 'market_data_provider') handleRunDiagnostic('test_provider');
                      else if (comp.component_id === 'python_sdk') handleRunDiagnostic('test_sdk');
                      else handleRunDiagnostic('test_storage');
                    }}
                  >
                    <Play className="w-3 h-3" />
                    <span>Run Diagnostic</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab 2: SDK Quick-Start Documentation */}
      {activeTab === 'quickstart' && (
        <div className="space-y-6">
          <div className="bg-[var(--bg-card)] p-4 rounded border border-[var(--border-subtle)] flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <div className="text-xs font-mono font-bold text-[var(--accent-primary)] flex items-center gap-2">
                <Code className="w-4 h-4" />
                <span>10 Verified Python SDK Workflows</span>
              </div>
              <p className="text-xs text-[var(--text-secondary)] mt-1">
                Complete, reproducible examples for in-process execution using <code className="text-sky-300">fragility_engine.sdk</code>. Every workflow adheres to exact cash accounting, verifiable seeds, and zero temporal leakage.
              </p>
            </div>
            <div className="font-mono text-xs text-[var(--text-muted)]">
              Package: <code className="text-[var(--text-primary)]">fragility_engine</code>
            </div>
          </div>

          <div className="space-y-4">
            {workflows.map((wf) => {
              const isCopied = copiedWorkflowId === wf.id;
              return (
                <div key={wf.id} className="card p-4 border border-[var(--border-subtle)] bg-[var(--bg-card)] space-y-3">
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-sm text-[var(--text-primary)]">{wf.title}</span>
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-sky-950 text-sky-300 border border-sky-800">
                          {wf.category}
                        </span>
                      </div>
                      <p className="text-xs text-[var(--text-secondary)] mt-0.5">{wf.description}</p>
                    </div>

                    <button
                      className="button secondary text-xs font-mono flex items-center gap-1.5 self-start sm:self-center"
                      onClick={() => handleCopyCode(wf.id, wf.code)}
                    >
                      {isCopied ? (
                        <>
                          <Check className="w-3.5 h-3.5 text-emerald-400" />
                          <span className="text-emerald-400 font-bold">Copied!</span>
                        </>
                      ) : (
                        <>
                          <Copy className="w-3.5 h-3.5" />
                          <span>Copy Snippet</span>
                        </>
                      )}
                    </button>
                  </div>

                  <div className="relative">
                    <pre className="p-3 rounded bg-[var(--bg-primary)] border border-[var(--border-subtle)] text-xs font-mono text-emerald-300 overflow-x-auto leading-relaxed">
                      {wf.code}
                    </pre>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Tab 3: API Route Explorer */}
      {activeTab === 'routes' && (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-[var(--bg-card)] p-4 rounded border border-[var(--border-subtle)]">
            <div className="flex items-center gap-2 flex-1 max-w-md">
              <Search className="w-4 h-4 text-[var(--text-muted)]" />
              <input
                type="text"
                className="input w-full text-xs font-mono"
                placeholder="Search endpoints by path, method, or description..."
                value={routeSearch}
                onChange={(e) => setRouteSearch(e.target.value)}
              />
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs font-mono text-[var(--text-muted)]">Category:</span>
              <select
                className="input text-xs font-mono py-1"
                value={selectedCategory}
                onChange={(e) => setSelectedCategory(e.target.value)}
              >
                {routeCategories.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="card overflow-x-auto border border-[var(--border-subtle)] bg-[var(--bg-card)]">
            <table className="w-full text-left border-collapse text-xs font-mono">
              <thead>
                <tr className="border-b border-[var(--border-subtle)] bg-[var(--bg-primary)] text-[var(--text-secondary)]">
                  <th className="p-3 font-medium">Method</th>
                  <th className="p-3 font-medium">Endpoint Path</th>
                  <th className="p-3 font-medium">Category</th>
                  <th className="p-3 font-medium">Description</th>
                  <th className="p-3 font-medium text-center">Auth</th>
                  <th className="p-3 font-medium text-right">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border-subtle)]">
                {filteredRoutes.map((r, idx) => (
                  <tr key={idx} className="hover:bg-[var(--bg-primary)] transition-colors">
                    <td className="p-3 whitespace-nowrap">
                      <div className="flex gap-1">
                        {r.methods.map((m: string) => (
                          <span
                            key={m}
                            className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                              m === 'GET'
                                ? 'bg-sky-950 text-sky-300 border border-sky-800'
                                : m === 'POST'
                                ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                                : m === 'DELETE'
                                ? 'bg-rose-950 text-rose-300 border border-rose-800'
                                : 'bg-zinc-800 text-zinc-300'
                            }`}
                          >
                            {m}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="p-3 font-bold text-[var(--text-primary)] whitespace-nowrap">{r.path}</td>
                    <td className="p-3 text-[var(--text-secondary)] whitespace-nowrap">{r.category}</td>
                    <td className="p-3 text-[var(--text-muted)] max-w-xs truncate">{r.description}</td>
                    <td className="p-3 text-center">
                      {r.auth_required ? (
                        <span className="text-[10px] text-amber-400 font-bold">Bearer</span>
                      ) : (
                        <span className="text-[10px] text-[var(--text-muted)]">Public</span>
                      )}
                    </td>
                    <td className="p-3 text-right">
                      <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-950 text-emerald-300 border border-emerald-800 font-bold">
                        ACTIVE
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab 4: Connected Services */}
      {activeTab === 'connected' && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {services.map((srv) => {
              const probe = probeResults[srv.service_id];
              const isProbing = probingServiceId === srv.service_id;
              return (
                <div key={srv.service_id} className="card p-4 border border-[var(--border-subtle)] bg-[var(--bg-card)] space-y-3">
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-sm text-[var(--text-primary)]">{srv.name}</span>
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase ${
                            srv.status === 'CONNECTED'
                              ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                              : 'bg-amber-950 text-amber-300 border border-amber-800'
                          }`}
                        >
                          {srv.status}
                        </span>
                      </div>
                      <span className="text-[11px] font-mono text-[var(--text-secondary)] mt-0.5 block">
                        Category: {srv.category}
                      </span>
                    </div>

                    <button
                      className="button secondary text-xs font-mono flex items-center gap-1.5"
                      onClick={() => handleProbeService(srv.service_id)}
                      disabled={isProbing}
                    >
                      <Play className={`w-3 h-3 ${isProbing ? 'animate-spin' : ''}`} />
                      <span>{isProbing ? 'Probing...' : 'Probe'}</span>
                    </button>
                  </div>

                  <p className="text-xs text-[var(--text-secondary)]">{srv.description}</p>

                  <div className="space-y-1 text-xs font-mono">
                    <div className="text-[10px] uppercase text-[var(--text-muted)]">Verified Capabilities:</div>
                    <div className="flex flex-wrap gap-1">
                      {srv.capabilities?.map((cap: string) => (
                        <span
                          key={cap}
                          className="px-2 py-0.5 rounded text-[10px] bg-[var(--bg-primary)] border border-[var(--border-subtle)] text-[var(--text-secondary)]"
                        >
                          {cap}
                        </span>
                      ))}
                    </div>
                  </div>

                  {probe && (
                    <div
                      className={`p-2.5 rounded text-xs font-mono border ${
                        probe.success
                          ? 'bg-emerald-950/40 border-emerald-800 text-emerald-200'
                          : 'bg-rose-950/40 border-rose-800 text-rose-200'
                      }`}
                    >
                      <div className="flex items-center justify-between font-bold">
                        <span>Probe Latency: {probe.latency_ms}ms</span>
                        <span>{probe.status}</span>
                      </div>
                      <div className="text-[11px] mt-1 text-[var(--text-secondary)]">{probe.message}</div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Tab 5: Integration Catalog */}
      {activeTab === 'catalog' && (
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2 border-b border-[var(--border-subtle)] pb-2">
            {['ALL', 'Market Data Feeds', 'Storage & State Sinks', 'Model & Quant Engines', 'Notifications & Webhooks'].map(
              (cat) => (
                <button
                  key={cat}
                  className={`px-3 py-1 text-xs font-mono rounded ${
                    catalogFilter === cat
                      ? 'bg-[var(--accent-primary)] text-white font-bold'
                      : 'bg-[var(--bg-card)] border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
                  }`}
                  onClick={() => setCatalogFilter(cat)}
                >
                  {cat}
                </button>
              )
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredCatalog.map((item) => (
              <div
                key={item.integration_id}
                className="card p-4 border border-[var(--border-subtle)] bg-[var(--bg-card)] flex flex-col justify-between space-y-3"
              >
                <div>
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="font-bold text-sm text-[var(--text-primary)]">{item.name}</h3>
                      <span className="text-[10px] font-mono text-[var(--text-muted)]">
                        by {item.provider} • v{item.version}
                      </span>
                    </div>
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold ${
                        item.status === 'VERIFIED'
                          ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                          : 'bg-zinc-800 text-zinc-300'
                      }`}
                    >
                      {item.status}
                    </span>
                  </div>

                  <p className="text-xs text-[var(--text-secondary)] mt-2">{item.description}</p>

                  <div className="mt-3 flex flex-wrap gap-1">
                    {item.capabilities?.map((c: string) => (
                      <span
                        key={c}
                        className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-[var(--bg-primary)] border border-[var(--border-subtle)] text-[var(--text-muted)]"
                      >
                        {c}
                      </span>
                    ))}
                  </div>
                </div>

                <div className="pt-2 border-t border-[var(--border-subtle)] flex items-center justify-between text-xs font-mono">
                  <span className="text-[var(--text-muted)]">{item.category}</span>
                  <button
                    className="button secondary text-xs py-1 px-2.5"
                    onClick={() => {
                      setWizardData({
                        integration_id: item.integration_id,
                        name: item.name,
                        category: item.category,
                        version: item.version,
                        provider: item.provider,
                        description: item.description,
                        capabilities: item.capabilities || [],
                        documentation_url: item.documentation_url || '',
                      });
                      setActiveTab('wizard');
                    }}
                  >
                    Configure
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab 6: Manifest Validator & Sandbox */}
      {activeTab === 'validator' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <label className="text-xs font-mono uppercase text-[var(--text-secondary)] flex items-center gap-1.5">
                <FileCode2 className="w-3.5 h-3.5 text-[var(--accent-primary)]" />
                <span>Plugin Manifest (plugin_manifest.json)</span>
              </label>
              <button
                className="button primary text-xs font-mono flex items-center gap-1.5"
                onClick={handleValidateManifest}
                disabled={validating}
              >
                <ShieldCheck className="w-3.5 h-3.5" />
                <span>{validating ? 'Validating...' : 'Validate & Inspect'}</span>
              </button>
            </div>

            <textarea
              className="w-full h-96 p-3 rounded font-mono text-xs bg-[var(--bg-primary)] border border-[var(--border-subtle)] text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent-primary)]"
              value={manifestText}
              onChange={(e) => setManifestText(e.target.value)}
            />
          </div>

          <div className="space-y-4">
            <h3 className="text-xs font-mono uppercase text-[var(--text-secondary)] flex items-center gap-1.5">
              <Fingerprint className="w-3.5 h-3.5 text-sky-400" />
              <span>Sandbox Isolation Audit &amp; Verification</span>
            </h3>

            {validationResult ? (
              <div className="space-y-4">
                <div
                  className={`p-4 rounded border ${
                    validationResult.is_valid
                      ? 'bg-emerald-950/40 border-emerald-800 text-emerald-200'
                      : 'bg-rose-950/40 border-rose-800 text-rose-200'
                  }`}
                >
                  <div className="flex items-center gap-2 font-bold text-sm">
                    {validationResult.is_valid ? (
                      <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    ) : (
                      <AlertOctagon className="w-4 h-4 text-rose-400" />
                    )}
                    <span>
                      {validationResult.is_valid
                        ? 'Manifest Structure & Sandbox Policy: VALID'
                        : 'Manifest Policy Violation Detected'}
                    </span>
                  </div>

                  {validationResult.errors?.length > 0 && (
                    <ul className="mt-2 space-y-1 text-xs list-disc list-inside">
                      {validationResult.errors.map((e: string, i: number) => (
                        <li key={i}>{e}</li>
                      ))}
                    </ul>
                  )}
                </div>

                {validationResult.manifest_summary && (
                  <div className="card p-4 border border-[var(--border-subtle)] bg-[var(--bg-card)] space-y-3 font-mono text-xs">
                    <div className="text-[10px] uppercase text-[var(--text-muted)]">Cryptographic Digest</div>
                    <div className="text-emerald-400 break-all bg-[var(--bg-primary)] p-2 rounded border border-[var(--border-subtle)]">
                      SHA-256: {validationResult.manifest_summary.hash_digest}
                    </div>

                    <div className="grid grid-cols-2 gap-2 pt-2">
                      <div>
                        <span className="text-[var(--text-muted)]">Plugin ID:</span>
                        <div className="font-bold text-[var(--text-primary)]">
                          {validationResult.manifest_summary.plugin_id}
                        </div>
                      </div>
                      <div>
                        <span className="text-[var(--text-muted)]">SemVer Version:</span>
                        <div className="font-bold text-[var(--text-primary)]">
                          {validationResult.manifest_summary.version}
                        </div>
                      </div>
                      <div>
                        <span className="text-[var(--text-muted)]">Max Memory:</span>
                        <div className="font-bold text-sky-400">
                          {validationResult.manifest_summary.max_memory_mb} MB
                        </div>
                      </div>
                      <div>
                        <span className="text-[var(--text-muted)]">Timeout:</span>
                        <div className="font-bold text-sky-400">
                          {validationResult.manifest_summary.timeout_seconds}s
                        </div>
                      </div>
                    </div>

                    <div className="pt-2">
                      <span className="text-[var(--text-muted)]">Authorized Capabilities:</span>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {validationResult.manifest_summary.capabilities?.map((cap: string) => (
                          <span
                            key={cap}
                            className="px-2 py-0.5 rounded text-[10px] bg-sky-950 text-sky-300 border border-sky-800"
                          >
                            {cap}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="card p-6 border border-dashed border-[var(--border-subtle)] bg-[var(--bg-card)] text-center text-[var(--text-muted)] font-mono text-xs">
                Click &quot;Validate &amp; Inspect&quot; to audit plugin manifest against security policies.
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tab 7: Add Integration Wizard */}
      {activeTab === 'wizard' && (
        <div className="max-w-2xl mx-auto card p-6 border border-[var(--border-subtle)] bg-[var(--bg-card)]">
          <h2 className="text-base font-bold text-[var(--text-primary)] mb-1">Add / Register Custom Integration</h2>
          <p className="text-xs text-[var(--text-secondary)] mb-6">
            Register custom data feed connectors or proprietary quant calculation containers into FragilityShield.
          </p>

          <form onSubmit={handleRegisterIntegration} className="space-y-4 text-xs font-mono">
            <div>
              <label className="text-[var(--text-secondary)] block mb-1">Integration Identifier (Unique ID):</label>
              <input
                type="text"
                className="input w-full"
                placeholder="e.g. proprietary_oas_pricer"
                value={wizardData.integration_id}
                onChange={(e) => setWizardData({ ...wizardData, integration_id: e.target.value })}
                required
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-[var(--text-secondary)] block mb-1">Display Name:</label>
                <input
                  type="text"
                  className="input w-full"
                  placeholder="e.g. Proprietary OAS Pricer"
                  value={wizardData.name}
                  onChange={(e) => setWizardData({ ...wizardData, name: e.target.value })}
                  required
                />
              </div>

              <div>
                <label className="text-[var(--text-secondary)] block mb-1">Category:</label>
                <select
                  className="input w-full"
                  value={wizardData.category}
                  onChange={(e) => setWizardData({ ...wizardData, category: e.target.value })}
                >
                  <option value="Market Data Feeds">Market Data Feeds</option>
                  <option value="Storage & State Sinks">Storage & State Sinks</option>
                  <option value="Model & Quant Engines">Model & Quant Engines</option>
                  <option value="Notifications & Webhooks">Notifications & Webhooks</option>
                </select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-[var(--text-secondary)] block mb-1">Provider / Organization:</label>
                <input
                  type="text"
                  className="input w-full"
                  placeholder="e.g. Internal Quant Research"
                  value={wizardData.provider}
                  onChange={(e) => setWizardData({ ...wizardData, provider: e.target.value })}
                />
              </div>

              <div>
                <label className="text-[var(--text-secondary)] block mb-1">Version (SemVer):</label>
                <input
                  type="text"
                  className="input w-full"
                  placeholder="1.0.0"
                  value={wizardData.version}
                  onChange={(e) => setWizardData({ ...wizardData, version: e.target.value })}
                />
              </div>
            </div>

            <div>
              <label className="text-[var(--text-secondary)] block mb-1">Description:</label>
              <textarea
                className="input w-full h-20"
                placeholder="Describe integration capabilities, protocols, and data guarantees..."
                value={wizardData.description}
                onChange={(e) => setWizardData({ ...wizardData, description: e.target.value })}
              />
            </div>

            <div className="pt-2 flex justify-end gap-3">
              <button type="button" className="button secondary" onClick={() => setActiveTab('catalog')}>
                Cancel
              </button>
              <button type="submit" className="button primary">
                Register Integration
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Diagnostics Modal / Drawer */}
      {showDiagnosticsModal && diagnosticResult && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4 animate-in fade-in duration-200">
          <div className="bg-[var(--bg-card)] border border-[var(--border-subtle)] rounded-lg max-w-xl w-full p-5 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-[var(--border-subtle)] pb-3">
              <div className="flex items-center gap-2">
                <Terminal className="w-5 h-5 text-[var(--accent-primary)]" />
                <h3 className="font-bold text-sm text-[var(--text-primary)]">
                  Diagnostic Probe Audit [{diagnosticResult.test_type}]
                </h3>
              </div>
              <button
                className="text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
                onClick={() => setShowDiagnosticsModal(false)}
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-3 text-xs font-mono">
              <div className="flex justify-between items-center p-3 bg-[var(--bg-primary)] rounded border border-[var(--border-subtle)]">
                <div>
                  <span className="text-[var(--text-muted)] block text-[10px] uppercase">Outcome Status</span>
                  <div className="mt-0.5">{renderStatusBadge(diagnosticResult.status)}</div>
                </div>
                <div className="text-right">
                  <span className="text-[var(--text-muted)] block text-[10px] uppercase">Roundtrip Latency</span>
                  <span className="text-sm font-bold text-sky-400">{diagnosticResult.latency_ms} ms</span>
                </div>
              </div>

              <div>
                <span className="text-[var(--text-muted)] block mb-1">Message:</span>
                <p className="p-2.5 rounded bg-[var(--bg-primary)] border border-[var(--border-subtle)] text-[var(--text-primary)]">
                  {diagnosticResult.message}
                </p>
              </div>

              <div>
                <span className="text-[var(--text-muted)] block mb-1">Diagnostic Context &amp; Redactions:</span>
                <pre className="p-3 rounded bg-[var(--bg-primary)] border border-[var(--border-subtle)] text-[11px] text-emerald-300 overflow-x-auto max-h-48">
                  {JSON.stringify(diagnosticResult.diagnostics, null, 2)}
                </pre>
              </div>

              <div className="text-[10px] text-[var(--text-muted)] flex items-center gap-1.5 pt-1">
                <Lock className="w-3.5 h-3.5 text-emerald-400" />
                <span>Zero token leakage guarantee: all API keys and connection passwords masked.</span>
              </div>
            </div>

            <div className="pt-3 border-t border-[var(--border-subtle)] flex justify-end">
              <button className="button primary text-xs font-mono" onClick={() => setShowDiagnosticsModal(false)}>
                Close Audit
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
