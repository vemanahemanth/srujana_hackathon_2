import React, { useState, useEffect } from 'react';
import {
  Terminal,
  Play,
  CheckCircle2,
  AlertTriangle,
  Code2,
  Copy,
  Layers,
  Boxes,
  Plus,
  RefreshCw,
  Search,
  ExternalLink,
  ShieldCheck,
  Zap,
  Activity,
  Sliders,
  Check,
  Server,
  ArrowRight,
  Database,
  FileCode,
  Lock,
  ChevronRight
} from 'lucide-react';
import { api } from '@/lib/api';

interface SDKDeveloperHubProps {
  navigate?: (path: string) => void;
  notify?: (msg: string) => void;
}

const SDK_METHODS = [
  {
    id: 'risk.calculate',
    name: 'client.risk.calculate([returns])',
    description: 'Calculate Parametric & Empirical VaR, Expected Shortfall, Volatility, and Drawdown.',
    defaultPayload: JSON.stringify(
      {
        returns: [0.012, -0.018, 0.005, -0.022, 0.015, -0.008, 0.019, -0.011, 0.004, -0.006],
        confidence_level: 0.95,
        horizon_days: 1
      },
      null,
      2
    )
  },
  {
    id: 'attribution.calculate',
    name: 'client.risk.attribution(portfolio)',
    description: 'Decompose risk using Euler marginal risk attribution ensuring exact mathematical reconciliation.',
    defaultPayload: JSON.stringify(
      {
        portfolio: {
          portfolio_id: "sdk_demo_port",
          name: "SDK Research Portfolio",
          holdings: [
            { asset_id: "RELIANCE", quantity: 100, price: 1200.0, sector: "Energy" },
            { asset_id: "TCS", quantity: 50, price: 3200.0, sector: "Information Technology" }
          ]
        },
        confidence_level: 0.95
      },
      null,
      2
    )
  },
  {
    id: 'scenarios.evaluate',
    name: 'client.scenarios.evaluate(portfolio, scenario)',
    description: 'Apply macroeconomic or custom stress vectors and calculate asset P&L.',
    defaultPayload: JSON.stringify(
      {
        portfolio: {
          portfolio_id: "sdk_stress_port",
          name: "Stress Test Portfolio",
          holdings: [
            { asset_id: "RELIANCE", quantity: 100, price: 1200.0, sector: "Energy" },
            { asset_id: "HDFCBANK", quantity: 150, price: 1650.0, sector: "Banking" }
          ]
        },
        preset_id: "banking_minus_20_it_minus_10"
      },
      null,
      2
    )
  },
  {
    id: 'fragility.run',
    name: 'client.fragility.run_audit([returns])',
    description: 'Perform assumption attacks: lookback shifts, friction shocks, and correlation perturbations.',
    defaultPayload: JSON.stringify(
      {
        symbol: "RELIANCE",
        lookback_short: 20,
        lookback_long: 60
      },
      null,
      2
    )
  },
  {
    id: 'allocation.optimize',
    name: 'client.allocation.optimize(universe)',
    description: 'Optimize weights via SciPy SLSQP (Max Sharpe, Min Variance, Equal Risk Contribution).',
    defaultPayload: JSON.stringify(
      {
        objective: "max_sharpe",
        asset_universe: ["RELIANCE", "TCS", "INFY", "HDFCBANK"],
        min_weight: 0.05,
        max_weight: 0.40
      },
      null,
      2
    )
  },
  {
    id: 'model_lab.register_model',
    name: 'client.model_lab.register_model(config)',
    description: 'Register a user-defined algorithm or model into the central capability registry.',
    defaultPayload: JSON.stringify(
      {
        model_id: "custom_garch_v2",
        name: "Custom Student-t GARCH(1,1)",
        model_type: "risk_model",
        version: "1.0.0",
        capabilities: ["var_calculation", "expected_shortfall", "volatility_forecast"],
        parameters: { omega: 0.00001, alpha: 0.08, beta: 0.90 }
      },
      null,
      2
    )
  }
];

export function SDKDeveloperHub({ navigate, notify }: SDKDeveloperHubProps) {
  const [activeTab, setActiveTab] = useState<'overview' | 'console' | 'register' | 'inventory' | 'snippets'>('overview');
  
  // Connection & Health States
  const [serverUrl, setServerUrl] = useState<string>('http://localhost:8000');
  const [apiToken, setApiToken] = useState<string>('fs_live_token_7a9f82d1e04b');
  const [healthStatus, setHealthStatus] = useState<{ status: string; engine?: string; version?: string } | null>(null);
  const [checkingHealth, setCheckingHealth] = useState<boolean>(false);
  const [copiedToken, setCopiedToken] = useState<boolean>(false);

  // Live Console States
  const [selectedMethodId, setSelectedMethodId] = useState<string>('risk.calculate');
  const [consolePayload, setConsolePayload] = useState<string>(SDK_METHODS[0].defaultPayload);
  const [executing, setExecuting] = useState<boolean>(false);
  const [consoleResponse, setConsoleResponse] = useState<any | null>(null);
  const [executionTimeMs, setExecutionTimeMs] = useState<number | null>(null);
  const [consoleError, setConsoleError] = useState<string | null>(null);

  // Algorithm Registration Form
  const [regForm, setRegForm] = useState({
    model_id: 'user_lstm_alpha_v1',
    name: 'Institutional LSTM Multi-Horizon Alpha',
    category: 'forecasting_model',
    version: '1.0.0',
    description: 'Bi-directional recurrent neural network for forward return distribution forecasting',
    capabilities: ['return_forecast', 'volatility_forecast'],
    parameters: '{\n  "lookback_window": 30,\n  "hidden_units": 64,\n  "learning_rate": 0.001\n}',
    code: 'import numpy as np\n\ndef predict(features, weights):\n    # Sandboxed inference\n    return np.tanh(features @ weights)\n'
  });
  const [registering, setRegistering] = useState<boolean>(false);
  const [regSuccess, setRegSuccess] = useState<boolean>(false);

  // Registered Models Inventory
  const [registeredModels, setRegisteredModels] = useState<any[]>([]);
  const [loadingModels, setLoadingModels] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>('');

  // Check health on mount
  useEffect(() => {
    checkConnection();
    loadModels();
  }, []);

  const checkConnection = async () => {
    try {
      setCheckingHealth(true);
      const res = await api.getHealth();
      setHealthStatus(res);
      if (notify) notify('Connected to FragilityShield Backend API.');
    } catch (err: any) {
      setHealthStatus({ status: 'offline', version: 'unknown' });
      if (notify) notify(`Health check failed: ${err.message}`);
    } finally {
      setCheckingHealth(false);
    }
  };

  const loadModels = async () => {
    try {
      setLoadingModels(true);
      const res = await api.getModelManifests();
      const list = Array.isArray(res) ? res : (res?.models || []);
      setRegisteredModels(list);
    } catch {
      setRegisteredModels([]);
    } finally {
      setLoadingModels(false);
    }
  };

  const handleSelectMethod = (id: string) => {
    setSelectedMethodId(id);
    const m = SDK_METHODS.find((item) => item.id === id);
    if (m) {
      setConsolePayload(m.defaultPayload);
      setConsoleResponse(null);
      setConsoleError(null);
      setExecutionTimeMs(null);
    }
  };

  const handleExecuteSDKMethod = async () => {
    try {
      setExecuting(true);
      setConsoleError(null);
      setConsoleResponse(null);
      const start = performance.now();
      const parsedBody = JSON.parse(consolePayload);

      let resp: any = null;
      if (selectedMethodId === 'risk.calculate') {
        resp = await api.calculateRisk(parsedBody);
      } else if (selectedMethodId === 'attribution.calculate') {
        resp = await api.calculateAttribution(parsedBody);
      } else if (selectedMethodId === 'scenarios.evaluate') {
        resp = await api.executeScenario(parsedBody);
      } else if (selectedMethodId === 'fragility.run') {
        resp = await api.runFragility(parsedBody);
      } else if (selectedMethodId === 'allocation.optimize') {
        resp = await api.optimizeAllocation(parsedBody);
      } else if (selectedMethodId === 'model_lab.register_model') {
        resp = await api.registerModelManifest(parsedBody);
        loadModels();
      }

      const elapsed = Math.round(performance.now() - start);
      setExecutionTimeMs(elapsed);
      setConsoleResponse(resp);
      if (notify) notify(`SDK method executed successfully in ${elapsed}ms.`);
    } catch (err: any) {
      setConsoleError(err.message || 'Execution failed');
      if (notify) notify(`Execution error: ${err.message}`);
    } finally {
      setExecuting(false);
    }
  };

  const handleRegisterAlgorithm = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setRegistering(true);
      let parsedParams = {};
      try {
        parsedParams = JSON.parse(regForm.parameters);
      } catch {
        throw new Error('Parameters must be a valid JSON object.');
      }

      const payload = {
        model_id: regForm.model_id.trim(),
        name: regForm.name.trim(),
        model_type: regForm.category,
        version: regForm.version.trim(),
        description: regForm.description.trim(),
        capabilities: regForm.capabilities,
        parameters: parsedParams,
        is_active: true
      };

      await api.registerModelManifest(payload);
      setRegSuccess(true);
      loadModels();
      if (notify) notify(`Algorithm '${payload.model_id}' successfully registered into SDK inventory!`);
      setTimeout(() => setRegSuccess(false), 4000);
    } catch (err: any) {
      if (notify) notify(`Registration failed: ${err.message}`);
    } finally {
      setRegistering(false);
    }
  };

  const toggleCapability = (cap: string) => {
    setRegForm((prev) => {
      const exists = prev.capabilities.includes(cap);
      return {
        ...prev,
        capabilities: exists ? prev.capabilities.filter((c) => c !== cap) : [...prev.capabilities, cap]
      };
    });
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedToken(true);
    setTimeout(() => setCopiedToken(false), 2000);
    if (notify) notify('Copied to clipboard!');
  };

  const filteredModels = registeredModels.filter((m) => {
    const q = searchQuery.toLowerCase();
    return (
      (m.model_id || '').toLowerCase().includes(q) ||
      (m.name || '').toLowerCase().includes(q) ||
      (m.model_type || '').toLowerCase().includes(q)
    );
  });

  return (
    <div className="space-y-6 max-w-7xl mx-auto p-4 md:p-6 text-slate-100">
      {/* Header Banner */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-xl">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-blue-600/20 text-blue-400 rounded-lg border border-blue-500/30">
              <Terminal className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
                Python SDK & Algorithm Hub
                <span className="text-xs font-mono font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 px-2 py-0.5 rounded-full">
                  fragility-engine v0.1.0
                </span>
              </h1>
              <p className="text-sm text-slate-400 mt-1">
                Institutional Python SDK, live interactive execution console, capability registration & developer runtime.
              </p>
            </div>
          </div>
        </div>

        {/* Live Status Controls */}
        <div className="flex items-center gap-3">
          <button
            onClick={checkConnection}
            disabled={checkingHealth}
            className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg border border-slate-700 transition"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${checkingHealth ? 'animate-spin' : ''}`} />
            {checkingHealth ? 'Checking...' : 'Ping Endpoint'}
          </button>
          <div className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            Live Backend Connected
          </div>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="flex border-b border-slate-800 space-x-2">
        <button
          onClick={() => setActiveTab('overview')}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition ${
            activeTab === 'overview'
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Zap className="w-4 h-4" />
          SDK Overview & Status
        </button>
        <button
          onClick={() => setActiveTab('console')}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition ${
            activeTab === 'console'
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Play className="w-4 h-4" />
          Interactive Live Console
        </button>
        <button
          onClick={() => setActiveTab('register')}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition ${
            activeTab === 'register'
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Plus className="w-4 h-4" />
          Register Custom Algorithm
        </button>
        <button
          onClick={() => setActiveTab('inventory')}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition ${
            activeTab === 'inventory'
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Boxes className="w-4 h-4" />
          Algorithm & Model Inventory ({registeredModels.length})
        </button>
        <button
          onClick={() => setActiveTab('snippets')}
          className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition ${
            activeTab === 'snippets'
              ? 'border-blue-500 text-blue-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Code2 className="w-4 h-4" />
          Python Quickstart Snippets
        </button>
      </div>

      {/* TAB 1: OVERVIEW & STATUS */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Public Package</span>
                <ShieldCheck className="w-4 h-4 text-emerald-400" />
              </div>
              <div className="text-xl font-mono font-bold text-white">fragility-engine</div>
              <p className="text-xs text-slate-400">
                Official institutional quantitative Python library. Supports Python 3.10 - 3.14.
              </p>
              <div className="pt-2 border-t border-slate-800 font-mono text-xs text-slate-300 bg-slate-950 p-2.5 rounded-lg border flex items-center justify-between">
                <code>pip install -e .</code>
                <button
                  onClick={() => copyToClipboard('pip install -e .')}
                  className="text-slate-400 hover:text-white"
                  title="Copy command"
                >
                  <Copy className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Active API Endpoint</span>
                <Server className="w-4 h-4 text-blue-400" />
              </div>
              <div className="text-lg font-mono font-bold text-blue-300 truncate">{serverUrl}</div>
              <p className="text-xs text-slate-400">
                Configured via <code className="text-blue-400 font-mono">FRAGILITYSHIELD_API_URL</code> environment variable.
              </p>
              <div className="pt-2 border-t border-slate-800 text-xs text-emerald-400 flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Status: {healthStatus?.status || 'Online'} (Phase 9/10 Architecture)</span>
              </div>
            </div>

            <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-sm space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Scoped Tenant API Token</span>
                <Lock className="w-4 h-4 text-amber-400" />
              </div>
              <div className="text-sm font-mono text-slate-200 truncate bg-slate-950 p-2 rounded border border-slate-800">
                {apiToken}
              </div>
              <p className="text-xs text-slate-400">
                Authenticated for workspace: <span className="text-slate-200 font-medium">ten_alpha_capital</span>
              </p>
              <button
                onClick={() => copyToClipboard(apiToken)}
                className="w-full flex items-center justify-center gap-2 px-3 py-1.5 text-xs font-medium bg-slate-800 hover:bg-slate-700 text-white rounded-lg border border-slate-700 transition"
              >
                {copiedToken ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                {copiedToken ? 'Copied Token!' : 'Copy API Token'}
              </button>
            </div>
          </div>

          {/* Quickstart Callout */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4">
            <h2 className="text-lg font-bold text-white flex items-center gap-2">
              <Code2 className="w-5 h-5 text-blue-400" />
              Canonical Python SDK Initialization
            </h2>
            <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 font-mono text-xs text-slate-300 leading-relaxed overflow-x-auto">
              <pre>{`from fragility_engine.sdk import FragilityShield, CustomModelConfig

# Initialize client pointing to live platform endpoint
client = FragilityShield(
    base_url="${serverUrl}",
    api_token="${apiToken}",
    workspace_id="ten_alpha_capital",
    timeout=30.0,
    max_retries=3
)

# 1. Execute Parametric & Historical Value-at-Risk
risk_report = client.risk.calculate(
    returns=[0.012, -0.018, 0.005, -0.022, 0.015, -0.008, 0.019],
    confidence_level=0.95
)
print("VaR 95%:", risk_report.var_95)
print("Expected Shortfall 95%:", risk_report.expected_shortfall_95)

# 2. Decompose Risk with Euler Marginal Attribution
attr_report = client.risk.attribution(
    portfolio={
        "holdings": [
            {"asset_id": "RELIANCE", "quantity": 100, "price": 1200.0},
            {"asset_id": "TCS", "quantity": 50, "price": 3200.0}
        ]
    }
)
print("Asset Attributions:", len(attr_report.asset_attributions))`}</pre>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: INTERACTIVE LIVE CONSOLE */}
      {activeTab === 'console' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Method Request Setup */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4 shadow-sm">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                <Terminal className="w-5 h-5 text-blue-400" />
                Live SDK Execution Console
              </h2>
              <span className="text-xs font-mono bg-blue-500/10 text-blue-400 px-2 py-0.5 rounded border border-blue-500/20">
                Direct RPC
              </span>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                Select SDK Domain Method
              </label>
              <select
                value={selectedMethodId}
                onChange={(e) => handleSelectMethod(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-blue-500 font-mono"
              >
                {SDK_METHODS.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </select>
              <p className="text-xs text-slate-400 mt-1.5">
                {SDK_METHODS.find((m) => m.id === selectedMethodId)?.description}
              </p>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                Interactive JSON Request Payload
              </label>
              <textarea
                value={consolePayload}
                onChange={(e) => setConsolePayload(e.target.value)}
                rows={12}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg p-3 font-mono text-xs text-emerald-400 focus:outline-none focus:border-blue-500 leading-relaxed"
                spellCheck={false}
              />
            </div>

            <button
              onClick={handleExecuteSDKMethod}
              disabled={executing}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg font-medium text-sm transition shadow-lg shadow-blue-600/20 disabled:opacity-50"
            >
              <Play className={`w-4 h-4 ${executing ? 'animate-spin' : ''}`} />
              {executing ? 'Executing via Live SDK...' : 'Run SDK Method'}
            </button>
          </div>

          {/* Response Output Panel */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4 shadow-sm flex flex-col">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                <Activity className="w-5 h-5 text-emerald-400" />
                Live Response & Diagnostics
              </h2>
              {executionTimeMs !== null && (
                <span className="text-xs font-mono bg-emerald-500/10 text-emerald-400 px-2 py-0.5 rounded border border-emerald-500/20">
                  {executionTimeMs} ms
                </span>
              )}
            </div>

            {consoleError && (
              <div className="p-4 bg-red-950/40 border border-red-500/30 rounded-lg text-xs text-red-300 space-y-1">
                <div className="font-bold flex items-center gap-1.5">
                  <AlertTriangle className="w-4 h-4 text-red-400" />
                  SDK Execution Error:
                </div>
                <div>{consoleError}</div>
              </div>
            )}

            <div className="flex-1 bg-slate-950 border border-slate-800 rounded-lg p-4 font-mono text-xs overflow-auto max-h-[480px]">
              {consoleResponse ? (
                <pre className="text-slate-200 whitespace-pre-wrap">{JSON.stringify(consoleResponse, null, 2)}</pre>
              ) : (
                <div className="h-full flex flex-col items-center justify-center text-slate-500 space-y-2 py-12">
                  <Code2 className="w-8 h-8 stroke-[1.5]" />
                  <p>Click "Run SDK Method" to execute and inspect live JSON results.</p>
                </div>
              )}
            </div>

            {consoleResponse?.data_provenance && (
              <div className="text-xs text-slate-400 bg-slate-950 p-2.5 rounded-lg border border-slate-800 flex items-center justify-between">
                <span>Mode: <strong className="text-slate-200">{consoleResponse.data_provenance.data_source_mode || 'REAL_DATA'}</strong></span>
                <span>Provider: <strong className="text-slate-200">{consoleResponse.data_provenance.provider || 'FragilityShield Core'}</strong></span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 3: REGISTER CUSTOM ALGORITHM */}
      {activeTab === 'register' && (
        <form onSubmit={handleRegisterAlgorithm} className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-6 shadow-sm">
          <div className="flex items-center justify-between border-b border-slate-800 pb-4">
            <div>
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                <Plus className="w-5 h-5 text-blue-400" />
                Register User-Defined Algorithm into SDK Registry
              </h2>
              <p className="text-xs text-slate-400 mt-1">
                Registered models automatically appear in compatible research labs based on capability tags.
              </p>
            </div>
            {regSuccess && (
              <div className="flex items-center gap-1.5 text-xs font-medium text-emerald-400 bg-emerald-500/10 border border-emerald-500/20 px-3 py-1.5 rounded-lg">
                <CheckCircle2 className="w-4 h-4" />
                Algorithm Registered!
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                  Algorithm Stable ID
                </label>
                <input
                  type="text"
                  value={regForm.model_id}
                  onChange={(e) => setRegForm({ ...regForm, model_id: e.target.value })}
                  required
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white font-mono focus:border-blue-500 focus:outline-none"
                  placeholder="e.g. garch_vol_student_t"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                  Display Name
                </label>
                <input
                  type="text"
                  value={regForm.name}
                  onChange={(e) => setRegForm({ ...regForm, name: e.target.value })}
                  required
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
                  placeholder="e.g. Student-t GARCH(1,1) Volatility Model"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                    Category
                  </label>
                  <select
                    value={regForm.category}
                    onChange={(e) => setRegForm({ ...regForm, category: e.target.value })}
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
                  >
                    <option value="risk_model">Risk Model (VaR/ES)</option>
                    <option value="forecasting_model">ML Forecasting Model</option>
                    <option value="trading_strategy">Trading Strategy</option>
                    <option value="allocation_model">Portfolio Allocation</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                    Version
                  </label>
                  <input
                    type="text"
                    value={regForm.version}
                    onChange={(e) => setRegForm({ ...regForm, version: e.target.value })}
                    required
                    className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white font-mono focus:border-blue-500 focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                  Description
                </label>
                <textarea
                  value={regForm.description}
                  onChange={(e) => setRegForm({ ...regForm, description: e.target.value })}
                  rows={2}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2.5 text-xs text-white focus:border-blue-500 focus:outline-none"
                />
              </div>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
                  Capability Flags (Defines Lab Compatibility)
                </label>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  {[
                    { id: 'var_calculation', label: 'VaR Calculation' },
                    { id: 'expected_shortfall', label: 'Expected Shortfall' },
                    { id: 'volatility_forecast', label: 'Volatility Forecast' },
                    { id: 'return_forecast', label: 'Return Forecast' },
                    { id: 'generate_signals', label: 'Generate Signals' },
                    { id: 'position_sizing', label: 'Position Sizing' },
                    { id: 'optimize_weights', label: 'Optimize Weights' },
                    { id: 'covariance_estimation', label: 'Covariance Matrix' }
                  ].map((cap) => {
                    const checked = regForm.capabilities.includes(cap.id);
                    return (
                      <button
                        type="button"
                        key={cap.id}
                        onClick={() => toggleCapability(cap.id)}
                        className={`flex items-center gap-2 p-2 rounded-lg border text-left transition ${
                          checked
                            ? 'bg-blue-600/20 border-blue-500/40 text-blue-300'
                            : 'bg-slate-950 border-slate-800 text-slate-400 hover:border-slate-700'
                        }`}
                      >
                        <span className={`w-3.5 h-3.5 rounded flex items-center justify-center border ${checked ? 'bg-blue-500 border-blue-500 text-white' : 'border-slate-600'}`}>
                          {checked && <Check className="w-2.5 h-2.5" />}
                        </span>
                        <span>{cap.label}</span>
                      </button>
                    );
                  })}
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1.5">
                  Parameters Schema (JSON)
                </label>
                <textarea
                  value={regForm.parameters}
                  onChange={(e) => setRegForm({ ...regForm, parameters: e.target.value })}
                  rows={4}
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2.5 font-mono text-xs text-white focus:border-blue-500 focus:outline-none"
                />
              </div>
            </div>
          </div>

          <div className="border-t border-slate-800 pt-4 flex justify-end">
            <button
              type="submit"
              disabled={registering}
              className="flex items-center gap-2 px-6 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg font-medium text-sm transition shadow-lg shadow-blue-600/20 disabled:opacity-50"
            >
              <Plus className="w-4 h-4" />
              {registering ? 'Validating & Registering...' : 'Register Algorithm into Central Catalog'}
            </button>
          </div>
        </form>
      )}

      {/* TAB 4: INVENTORY */}
      {activeTab === 'inventory' && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-4 shadow-sm">
          <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
            <div>
              <h2 className="text-base font-bold text-white flex items-center gap-2">
                <Boxes className="w-5 h-5 text-blue-400" />
                Registered SDK Algorithms & Compatibility Matrix
              </h2>
              <p className="text-xs text-slate-400 mt-1">
                Authoritative registry of built-in and user-registered quantitative algorithms.
              </p>
            </div>
            <div className="relative w-full md:w-64">
              <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-500" />
              <input
                type="text"
                placeholder="Search models & algorithms..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-3 py-1.5 text-xs text-white focus:outline-none focus:border-blue-500"
              />
            </div>
          </div>

          <div className="border border-slate-800 rounded-lg overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="bg-slate-950 text-slate-400 border-b border-slate-800 font-semibold uppercase tracking-wider">
                <tr>
                  <th className="py-3 px-4">Algorithm ID</th>
                  <th className="py-3 px-4">Display Name</th>
                  <th className="py-3 px-4">Category</th>
                  <th className="py-3 px-4">Version</th>
                  <th className="py-3 px-4">Capabilities</th>
                  <th className="py-3 px-4">Compatible Labs</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800 font-mono">
                {filteredModels.length > 0 ? (
                  filteredModels.map((m) => (
                    <tr key={m.model_id} className="hover:bg-slate-800/40 transition">
                      <td className="py-3 px-4 font-bold text-blue-400">{m.model_id}</td>
                      <td className="py-3 px-4 font-sans text-white">{m.name || m.display_name}</td>
                      <td className="py-3 px-4">
                        <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                          {m.model_type || 'risk_model'}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-slate-400">{m.version || '1.0.0'}</td>
                      <td className="py-3 px-4">
                        <div className="flex flex-wrap gap-1">
                          {(m.capabilities || ['var_calculation']).map((c: string) => (
                            <span key={c} className="px-1.5 py-0.5 rounded text-[10px] bg-slate-950 border border-slate-800 text-slate-300">
                              {c}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="py-3 px-4 font-sans">
                        <div className="flex flex-wrap gap-1">
                          {(m.capabilities || []).includes('var_calculation') && (
                            <span className="px-2 py-0.5 rounded-full text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                              Risk Analytics
                            </span>
                          )}
                          {(m.capabilities || []).includes('return_forecast') && (
                            <span className="px-2 py-0.5 rounded-full text-[10px] bg-purple-500/10 text-purple-400 border border-purple-500/20">
                              ML Forecasting
                            </span>
                          )}
                          {(m.capabilities || []).includes('generate_signals') && (
                            <span className="px-2 py-0.5 rounded-full text-[10px] bg-blue-500/10 text-blue-400 border border-blue-500/20">
                              Backtest Lab
                            </span>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={6} className="py-8 text-center text-slate-500 font-sans">
                      No registered models match the current filter.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* TAB 5: PYTHON SNIPPETS */}
      {activeTab === 'snippets' && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <FileCode className="w-4 h-4 text-blue-400" />
              1. Local Script or Jupyter Notebook Execution
            </h3>
            <div className="bg-slate-950 border border-slate-800 rounded-lg p-3 font-mono text-xs text-slate-300 leading-relaxed overflow-x-auto">
              <pre>{`from fragility_engine.sdk import FragilityShield

client = FragilityShield(base_url="${serverUrl}")

# Run VaR and Expected Shortfall
res = client.risk.calculate(
    returns=[0.015, -0.012, 0.008, -0.025, 0.019],
    confidence_level=0.99
)
print("VaR 99%:", res.var_99)`}</pre>
            </div>
            <button
              onClick={() => copyToClipboard(`from fragility_engine.sdk import FragilityShield\nclient = FragilityShield(base_url="${serverUrl}")\nres = client.risk.calculate([0.015, -0.012, 0.008, -0.025, 0.019])\nprint(res.var_95)`)}
              className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 font-medium"
            >
              <Copy className="w-3.5 h-3.5" /> Copy Code
            </button>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-3">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <FileCode className="w-4 h-4 text-purple-400" />
              2. Remote Run Ingestion & Provenance Upload
            </h3>
            <div className="bg-slate-950 border border-slate-800 rounded-lg p-3 font-mono text-xs text-slate-300 leading-relaxed overflow-x-auto">
              <pre>{`sub = client.external.submit_run(
    experiment_id="exp_equity_risk_01",
    run_id="run_colab_alpha_01",
    model_id="custom_garch_v2",
    metrics=[
        {"metric_name": "rmse", "observed_value": 0.0142},
        {"metric_name": "var_95", "observed_value": 0.0215}
    ]
)
print("Run Ingested with Provenance:", sub.success)`}</pre>
            </div>
            <button
              onClick={() => copyToClipboard(`sub = client.external.submit_run(experiment_id="exp_01", run_id="run_01", model_id="garch", metrics=[{"metric_name": "var_95", "observed_value": 0.02}])`)}
              className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 font-medium"
            >
              <Copy className="w-3.5 h-3.5" /> Copy Code
            </button>
          </div>
        </div>
      )}
    </div>
  );
}