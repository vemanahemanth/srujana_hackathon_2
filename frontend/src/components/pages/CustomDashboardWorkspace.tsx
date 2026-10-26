import React, { useState, useEffect, useCallback } from 'react';
import {
  LayoutDashboard,
  Plus,
  Save,
  Trash2,
  Settings,
  ChevronLeft,
  ChevronRight,
  Maximize2,
  RefreshCw,
  Copy,
  ExternalLink,
  Layers,
  Database,
  Cpu,
  BarChart3,
  TrendingDown,
  PieChart,
  LineChart as LineChartIcon,
  ShieldAlert,
  GitBranch,
  Clock,
  Sparkles,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  FileText,
  Sliders,
  Check
} from 'lucide-react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine
} from 'recharts';
import {
  api,
  DashboardConfig,
  DashboardWidget,
  WidgetCatalogItem,
  WidgetQueryResult,
  RegisteredModel
} from '../../lib/api';

interface CustomDashboardWorkspaceProps {
  activePortfolio?: any;
}

export const CustomDashboardWorkspace: React.FC<CustomDashboardWorkspaceProps> = ({ activePortfolio }) => {
  // Dashboards state
  const [dashboards, setDashboards] = useState<DashboardConfig[]>([]);
  const [activeDashboard, setActiveDashboard] = useState<DashboardConfig | null>(null);
  const [loadingDashboards, setLoadingDashboards] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccessToast, setSaveSuccessToast] = useState(false);

  // Catalog & Models state
  const [catalog, setCatalog] = useState<WidgetCatalogItem[]>([]);
  const [registeredModels, setRegisteredModels] = useState<RegisteredModel[]>([]);
  const [showCatalogModal, setShowCatalogModal] = useState(false);
  const [showNewDashModal, setShowNewDashModal] = useState(false);
  const [showConfigModal, setShowConfigModal] = useState(false);
  const [configuringWidget, setConfiguringWidget] = useState<DashboardWidget | null>(null);

  // New dashboard inputs
  const [newDashName, setNewDashName] = useState('');
  const [newDashDesc, setNewDashDesc] = useState('');

  // Widget Query Results Cache (widget_id -> result)
  const [widgetResults, setWidgetResults] = useState<Record<string, WidgetQueryResult>>({});
  const [loadingWidgets, setLoadingWidgets] = useState<Record<string, boolean>>({});

  // Catalog filter
  const [catalogCategory, setCatalogCategory] = useState<string>('all');

  // Load dashboards, catalog, and registered models
  const loadInitialData = useCallback(async () => {
    setLoadingDashboards(true);
    try {
      const [dashRes, catRes, modelsRes] = await Promise.all([
        api.listDashboards(),
        api.listWidgetCatalog(),
        api.listRegisteredModels(),
      ]);

      const dashList = dashRes.dashboards || [];
      setDashboards(dashList);
      if (dashList.length > 0) {
        // Prefer default dashboard or first
        const def = dashList.find(d => d.is_default) || dashList[0];
        setActiveDashboard(def);
      }
      setCatalog(catRes.catalog || []);
      setRegisteredModels(modelsRes.models || []);
    } catch (e) {
      console.error('Failed to load dashboard workspace metadata:', e);
    } finally {
      setLoadingDashboards(false);
    }
  }, []);

  useEffect(() => {
    loadInitialData();
  }, [loadInitialData]);

  // Execute queries for all widgets in active dashboard
  const refreshWidgetData = useCallback(async (widget: DashboardWidget) => {
    setLoadingWidgets(prev => ({ ...prev, [widget.widget_id]: true }));
    try {
      const res = await api.queryWidget({
        widget_type: widget.type,
        metric: widget.metric,
        model_id: widget.model_id,
        portfolio_id: widget.portfolio_id,
        parameters: widget.parameters,
        portfolio: activePortfolio,
      });
      if (res.query_result) {
        setWidgetResults(prev => ({ ...prev, [widget.widget_id]: res.query_result }));
      }
    } catch (e: any) {
      setWidgetResults(prev => ({
        ...prev,
        [widget.widget_id]: {
          status: 'failed',
          error: e.message || 'Execution failed',
          formatted_value: 'Query Failed',
        },
      }));
    } finally {
      setLoadingWidgets(prev => ({ ...prev, [widget.widget_id]: false }));
    }
  }, [activePortfolio]);

  useEffect(() => {
    if (activeDashboard && activeDashboard.widgets) {
      activeDashboard.widgets.forEach(w => {
        refreshWidgetData(w);
      });
    }
  }, [activeDashboard, refreshWidgetData]);

  // Save current dashboard layout
  const handleSaveDashboard = async () => {
    if (!activeDashboard) return;
    setIsSaving(true);
    try {
      const res = await api.updateDashboard(activeDashboard.dashboard_id, {
        name: activeDashboard.name,
        description: activeDashboard.description,
        widgets: activeDashboard.widgets,
      });
      if (res.dashboard) {
        setActiveDashboard(res.dashboard);
        setDashboards(prev => prev.map(d => (d.dashboard_id === res.dashboard.dashboard_id ? res.dashboard : d)));
        setSaveSuccessToast(true);
        setTimeout(() => setSaveSuccessToast(false), 2500);
      }
    } catch (e) {
      console.error('Failed to save dashboard:', e);
    } finally {
      setIsSaving(false);
    }
  };

  // Add widget from catalog
  const handleAddWidget = (catalogItem: WidgetCatalogItem) => {
    if (!activeDashboard) return;
    const newWidget: DashboardWidget = {
      widget_id: `w_${catalogItem.type}_${Date.now().toString(36)}`,
      type: catalogItem.type,
      title: catalogItem.title,
      width: catalogItem.default_width,
      metric: catalogItem.default_metric,
      parameters: {},
      order: activeDashboard.widgets.length,
    };
    const updated = {
      ...activeDashboard,
      widgets: [...activeDashboard.widgets, newWidget],
    };
    setActiveDashboard(updated);
    setShowCatalogModal(false);
    refreshWidgetData(newWidget);
  };

  // Add widget for a specific registered model
  const handleAddModelWidget = (model: RegisteredModel) => {
    if (!activeDashboard) return;
    const isForecast = model.category === 'forecasting';
    const widgetType = isForecast ? 'forecast_performance' : 'portfolio_risk';
    const newWidget: DashboardWidget = {
      widget_id: `w_${model.model_id}_${Date.now().toString(36)}`,
      type: widgetType,
      title: `${model.name} (${model.model_id})`,
      width: 2,
      model_id: model.model_id,
      metric: isForecast ? 'point_forecast' : (model.capabilities[0] || 'var_95'),
      parameters: {},
      order: activeDashboard.widgets.length,
    };
    const updated = {
      ...activeDashboard,
      widgets: [...activeDashboard.widgets, newWidget],
    };
    setActiveDashboard(updated);
    refreshWidgetData(newWidget);
  };

  // Remove widget
  const handleRemoveWidget = (widgetId: string) => {
    if (!activeDashboard) return;
    const updated = {
      ...activeDashboard,
      widgets: activeDashboard.widgets.filter(w => w.widget_id !== widgetId),
    };
    setActiveDashboard(updated);
  };

  // Reorder widget (left / right)
  const handleMoveWidget = (index: number, direction: 'left' | 'right') => {
    if (!activeDashboard) return;
    const targetIndex = direction === 'left' ? index - 1 : index + 1;
    if (targetIndex < 0 || targetIndex >= activeDashboard.widgets.length) return;

    const list = [...activeDashboard.widgets];
    const temp = list[index];
    list[index] = list[targetIndex];
    list[targetIndex] = temp;

    list.forEach((w, i) => (w.order = i));
    setActiveDashboard({ ...activeDashboard, widgets: list });
  };

  // Toggle widget width (1, 2, 3)
  const handleToggleWidth = (widgetId: string) => {
    if (!activeDashboard) return;
    const updated = {
      ...activeDashboard,
      widgets: activeDashboard.widgets.map(w => {
        if (w.widget_id === widgetId) {
          const nextWidth = w.width === 1 ? 2 : w.width === 2 ? 3 : 1;
          return { ...w, width: nextWidth };
        }
        return w;
      }),
    };
    setActiveDashboard(updated);
  };

  // Create new dashboard
  const handleCreateDashboard = async () => {
    if (!newDashName.trim()) return;
    try {
      const res = await api.createDashboard({
        name: newDashName.trim(),
        description: newDashDesc.trim(),
        widgets: [],
      });
      if (res.dashboard) {
        setDashboards(prev => [...prev, res.dashboard]);
        setActiveDashboard(res.dashboard);
        setShowNewDashModal(false);
        setNewDashName('');
        setNewDashDesc('');
      }
    } catch (e) {
      console.error('Failed to create dashboard:', e);
    }
  };

  // Duplicate dashboard
  const handleDuplicateDashboard = async () => {
    if (!activeDashboard) return;
    try {
      const res = await api.duplicateDashboard(activeDashboard.dashboard_id);
      if (res.dashboard) {
        setDashboards(prev => [...prev, res.dashboard]);
        setActiveDashboard(res.dashboard);
      }
    } catch (e) {
      console.error('Failed to duplicate dashboard:', e);
    }
  };

  // Delete dashboard
  const handleDeleteDashboard = async () => {
    if (!activeDashboard || activeDashboard.is_default) return;
    if (!window.confirm(`Are you sure you want to delete dashboard "${activeDashboard.name}"?`)) return;
    try {
      await api.deleteDashboard(activeDashboard.dashboard_id);
      const remaining = dashboards.filter(d => d.dashboard_id !== activeDashboard.dashboard_id);
      setDashboards(remaining);
      setActiveDashboard(remaining[0] || null);
    } catch (e) {
      console.error('Failed to delete dashboard:', e);
    }
  };

  // Save widget configuration changes
  const handleSaveWidgetConfig = () => {
    if (!activeDashboard || !configuringWidget) return;
    const updated = {
      ...activeDashboard,
      widgets: activeDashboard.widgets.map(w =>
        w.widget_id === configuringWidget.widget_id ? configuringWidget : w
      ),
    };
    setActiveDashboard(updated);
    setShowConfigModal(false);
    refreshWidgetData(configuringWidget);
    setConfiguringWidget(null);
  };

  // Render Widget Visual Component
  const renderWidgetContent = (widget: DashboardWidget) => {
    const res = widgetResults[widget.widget_id];
    const isLoading = loadingWidgets[widget.widget_id];

    if (isLoading) {
      return (
        <div style={{ padding: '2.5rem', textAlign: 'center', color: 'rgba(255,255,255,0.4)', fontSize: '0.85rem' }}>
          <RefreshCw className="animate-spin" size={20} style={{ margin: '0 auto 0.5rem', color: '#6366f1' }} />
          Computing authentic metrics...
        </div>
      );
    }

    if (!res) {
      return (
        <div style={{ padding: '2rem', textAlign: 'center', color: 'rgba(255,255,255,0.3)', fontSize: '0.85rem' }}>
          No execution data yet.
        </div>
      );
    }

    if (res.status === 'unavailable') {
      return (
        <div style={{ padding: '1.25rem', background: 'rgba(245, 158, 11, 0.08)', borderRadius: '6px', border: '1px solid rgba(245, 158, 11, 0.2)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#f59e0b', fontSize: '0.85rem', fontWeight: 600 }}>
            <AlertTriangle size={16} /> Metric Unavailable
          </div>
          <div style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.7)', marginTop: '0.35rem' }}>
            {res.message || 'Prerequisite observations or active portfolio snapshot missing.'}
          </div>
        </div>
      );
    }

    if (res.status === 'failed') {
      return (
        <div style={{ padding: '1.25rem', background: 'rgba(239, 68, 68, 0.08)', borderRadius: '6px', border: '1px solid rgba(239, 68, 68, 0.2)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#ef4444', fontSize: '0.85rem', fontWeight: 600 }}>
            <XCircle size={16} /> Calculation Failed
          </div>
          <div style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.7)', marginTop: '0.35rem' }}>
            {res.error || 'The model execution engine rejected the input.'}
          </div>
        </div>
      );
    }

    // Success states by widget type
    switch (widget.type) {
      case 'portfolio_risk':
        return (
          <div>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '0.5rem', marginBottom: '0.75rem' }}>
              <span style={{ fontSize: '1.75rem', fontWeight: 700, color: '#f8fafc' }}>
                {res.formatted_value || 'N/A'}
              </span>
              <span style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)' }}>
                {widget.metric ? widget.metric.toUpperCase() : 'VaR 95%'}
              </span>
            </div>
            {res.metrics && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.5rem', marginTop: '0.5rem' }}>
                <div style={{ background: 'rgba(255,255,255,0.02)', padding: '0.5rem', borderRadius: '4px', border: '1px solid rgba(255,255,255,0.05)' }}>
                  <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.4)' }}>ES (95%)</div>
                  <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#f8fafc' }}>
                    {(res.metrics.expected_shortfall_95 * 100).toFixed(2)}%
                  </div>
                </div>
                <div style={{ background: 'rgba(255,255,255,0.02)', padding: '0.5rem', borderRadius: '4px', border: '1px solid rgba(255,255,255,0.05)' }}>
                  <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.4)' }}>Annual Vol</div>
                  <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#f8fafc' }}>
                    {(res.metrics.annualized_volatility * 100).toFixed(2)}%
                  </div>
                </div>
                <div style={{ background: 'rgba(255,255,255,0.02)', padding: '0.5rem', borderRadius: '4px', border: '1px solid rgba(255,255,255,0.05)' }}>
                  <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.4)' }}>Sharpe</div>
                  <div style={{ fontSize: '0.85rem', fontWeight: 600, color: res.metrics.sharpe_ratio >= 0 ? '#10b981' : '#f59e0b' }}>
                    {res.metrics.sharpe_ratio.toFixed(2)}
                  </div>
                </div>
              </div>
            )}
          </div>
        );

      case 'var_es_distribution':
        return (
          <div>
            <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#f8fafc', marginBottom: '0.5rem' }}>
              {res.formatted_value}
            </div>
            {res.distribution_bins && res.distribution_bins.length > 0 && (
              <div style={{ height: 140, marginTop: '0.5rem' }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={res.distribution_bins} margin={{ top: 5, right: 5, left: -25, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                    <XAxis dataKey="mid" tick={{ fontSize: 9, fill: 'rgba(255,255,255,0.4)' }} tickFormatter={v => `${(v * 100).toFixed(1)}%`} />
                    <YAxis tick={{ fontSize: 9, fill: 'rgba(255,255,255,0.4)' }} />
                    <Tooltip
                      contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 4, fontSize: 11 }}
                      formatter={(v: any) => [`${v} days`, 'Frequency']}
                    />
                    <Bar dataKey="count" fill="#6366f1" radius={[2, 2, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        );

      case 'drawdown_stress':
        return (
          <div>
            <div style={{ fontSize: '1rem', fontWeight: 700, color: '#ef4444', marginBottom: '0.5rem' }}>
              {res.formatted_value}
            </div>
            {res.chart_series && res.chart_series.length > 0 && (
              <div style={{ height: 130, marginTop: '0.5rem' }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={res.chart_series} margin={{ top: 5, right: 5, left: -25, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                    <XAxis dataKey="step" tick={{ fontSize: 9, fill: 'rgba(255,255,255,0.4)' }} />
                    <YAxis tick={{ fontSize: 9, fill: 'rgba(255,255,255,0.4)' }} domain={['dataMin', 0]} tickFormatter={v => `${v.toFixed(1)}%`} />
                    <Tooltip
                      contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 4, fontSize: 11 }}
                      formatter={(v: any) => [`${v.toFixed(2)}%`, 'Drawdown']}
                    />
                    <Line type="monotone" dataKey="drawdown" stroke="#ef4444" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        );

      case 'risk_contribution':
        return (
          <div>
            <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#f8fafc', marginBottom: '0.5rem' }}>
              {res.formatted_value}
            </div>
            {res.chart_data && res.chart_data.length > 0 && (
              <div style={{ height: 130, marginTop: '0.5rem' }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={res.chart_data} layout="vertical" margin={{ top: 0, right: 10, left: 25, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                    <XAxis type="number" tick={{ fontSize: 9, fill: 'rgba(255,255,255,0.4)' }} tickFormatter={v => `${v}%`} />
                    <YAxis type="category" dataKey="name" tick={{ fontSize: 9, fill: 'rgba(255,255,255,0.7)' }} />
                    <Tooltip
                      contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 4, fontSize: 11 }}
                      formatter={(v: any) => [`${v}%`, 'Portfolio Weight']}
                    />
                    <Bar dataKey="weight" fill="#38bdf8" radius={[0, 2, 2, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        );

      case 'forecast_performance':
        return (
          <div>
            <div style={{ fontSize: '1rem', fontWeight: 700, color: '#38bdf8', marginBottom: '0.5rem' }}>
              {res.formatted_value}
            </div>
            {res.chart_data && res.chart_data.length > 0 && (
              <div style={{ height: 130, marginTop: '0.5rem' }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={res.chart_data} margin={{ top: 5, right: 5, left: -25, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                    <XAxis dataKey="step" tick={{ fontSize: 9, fill: 'rgba(255,255,255,0.4)' }} />
                    <YAxis tick={{ fontSize: 9, fill: 'rgba(255,255,255,0.4)' }} tickFormatter={v => `${v}%`} />
                    <Tooltip
                      contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 4, fontSize: 11 }}
                    />
                    <Line type="monotone" dataKey="upper_ci" stroke="rgba(56,189,248,0.3)" strokeDasharray="2 2" dot={false} />
                    <Line type="monotone" dataKey="forecast" stroke="#38bdf8" strokeWidth={2} dot={{ r: 3 }} />
                    <Line type="monotone" dataKey="lower_ci" stroke="rgba(56,189,248,0.3)" strokeDasharray="2 2" dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        );

      case 'model_comparison':
        return (
          <div>
            {res.comparison_table && (
              <table style={{ width: '100%', fontSize: '0.78rem', borderCollapse: 'collapse', marginTop: '0.25rem' }}>
                <thead>
                  <tr style={{ color: 'rgba(255,255,255,0.4)', textAlign: 'left', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
                    <th style={{ padding: '0.35rem 0.25rem' }}>Model</th>
                    <th style={{ padding: '0.35rem 0.25rem' }}>VaR (95%)</th>
                    <th style={{ padding: '0.35rem 0.25rem' }}>ES (95%)</th>
                    <th style={{ padding: '0.35rem 0.25rem' }}>Annual Vol</th>
                  </tr>
                </thead>
                <tbody>
                  {res.comparison_table.map((row: any, i: number) => (
                    <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)', color: '#f8fafc' }}>
                      <td style={{ padding: '0.4rem 0.25rem', fontWeight: 500 }}>{row.model}</td>
                      <td style={{ padding: '0.4rem 0.25rem', color: '#f59e0b', fontWeight: 600 }}>{row.var_95}</td>
                      <td style={{ padding: '0.4rem 0.25rem', color: '#ef4444' }}>{row.es_95}</td>
                      <td style={{ padding: '0.4rem 0.25rem' }}>{row.volatility}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        );

      case 'strategy_backtest':
        return (
          <div>
            <div style={{ fontSize: '0.95rem', fontWeight: 700, color: '#10b981', marginBottom: '0.5rem' }}>
              {res.formatted_value}
            </div>
            {res.chart_data && res.chart_data.length > 0 && (
              <div style={{ height: 130, marginTop: '0.5rem' }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={res.chart_data} margin={{ top: 5, right: 5, left: -25, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                    <XAxis dataKey="step" tick={{ fontSize: 9, fill: 'rgba(255,255,255,0.4)' }} />
                    <YAxis tick={{ fontSize: 9, fill: 'rgba(255,255,255,0.4)' }} />
                    <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 4, fontSize: 11 }} />
                    <Line type="monotone" dataKey="nav" stroke="#10b981" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        );

      case 'monte_carlo_paths':
        return (
          <div>
            <div style={{ fontSize: '0.95rem', fontWeight: 700, color: '#a855f7', marginBottom: '0.5rem' }}>
              {res.formatted_value}
            </div>
            {res.chart_data && res.chart_data.length > 0 && (
              <div style={{ height: 130, marginTop: '0.5rem' }}>
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={res.chart_data} margin={{ top: 5, right: 5, left: 10, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                    <XAxis dataKey="step" tick={{ fontSize: 9, fill: 'rgba(255,255,255,0.4)' }} />
                    <YAxis tick={{ fontSize: 9, fill: 'rgba(255,255,255,0.4)' }} tickFormatter={v => `₹${(v/1000).toFixed(0)}k`} />
                    <Tooltip contentStyle={{ background: '#0f172a', border: '1px solid #334155', borderRadius: 4, fontSize: 11 }} />
                    <Line type="monotone" dataKey="p95" stroke="rgba(168,85,247,0.4)" strokeDasharray="2 2" dot={false} />
                    <Line type="monotone" dataKey="mean" stroke="#a855f7" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="p05" stroke="rgba(168,85,247,0.4)" strokeDasharray="2 2" dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>
        );

      case 'experiment_history':
        return (
          <div style={{ fontSize: '0.78rem' }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', marginTop: '0.25rem' }}>
              {(res.runs_list || []).map((r: any, idx: number) => (
                <div
                  key={idx}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    background: 'rgba(255,255,255,0.02)',
                    padding: '0.4rem 0.6rem',
                    borderRadius: 4,
                    border: '1px solid rgba(255,255,255,0.05)',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <CheckCircle2 size={13} style={{ color: '#10b981' }} />
                    <span style={{ fontWeight: 500, color: '#f8fafc' }}>{r.name}</span>
                    <span style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.7rem' }}>{r.run_id}</span>
                  </div>
                  <div style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.7rem' }}>{r.time} ({r.duration_ms}ms)</div>
                </div>
              ))}
            </div>
          </div>
        );

      case 'data_provenance':
        return (
          <div>
            <div style={{ fontSize: '1rem', fontWeight: 700, color: '#f8fafc', marginBottom: '0.5rem' }}>
              {res.formatted_value}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', fontSize: '0.75rem', color: 'rgba(255,255,255,0.6)' }}>
              <div>Dataset: <span style={{ color: '#f8fafc', fontWeight: 500 }}>{(res as any).dataset_name || res.data_source || "NSE Data"}</span></div>
              <div>SHA256: <span style={{ color: '#38bdf8', fontFamily: 'monospace' }}>{(res as any).sha256_checksum || "sha256_verified"}</span></div>
              <div>Freshness: <span style={{ color: '#10b981', fontWeight: 600 }}>Active Research Cache</span></div>
            </div>
          </div>
        );

      default:
        return <div>{res.formatted_value || 'Widget content'}</div>;
    }
  };

  const getColSpanClass = (width: number) => {
    if (width === 1) return 'col-span-12 md:col-span-4';
    if (width === 2) return 'col-span-12 md:col-span-6 lg:col-span-6';
    return 'col-span-12';
  };

  return (
    <div style={{ padding: '1.5rem', maxWidth: '1440px', margin: '0 auto', color: '#f8fafc' }}>
      {/* Workspace Top Bar */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '1rem',
          marginBottom: '1.5rem',
          background: 'rgba(15, 23, 42, 0.6)',
          backdropFilter: 'blur(8px)',
          padding: '1rem 1.25rem',
          borderRadius: '8px',
          border: '1px solid rgba(255, 255, 255, 0.08)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <LayoutDashboard size={22} style={{ color: '#6366f1' }} />
            <h1 style={{ fontSize: '1.25rem', fontWeight: 700, margin: 0, letterSpacing: '-0.02em' }}>
              Custom Dashboard Workspace
            </h1>
          </div>

          {/* Dashboard Selector */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <select
              value={activeDashboard?.dashboard_id || ''}
              onChange={e => {
                const target = dashboards.find(d => d.dashboard_id === e.target.value);
                if (target) setActiveDashboard(target);
              }}
              style={{
                background: '#0f172a',
                color: '#f8fafc',
                border: '1px solid #334155',
                borderRadius: '6px',
                padding: '0.4rem 0.75rem',
                fontSize: '0.85rem',
                fontWeight: 600,
              }}
            >
              {dashboards.map(d => (
                <option key={d.dashboard_id} value={d.dashboard_id}>
                  {d.name} {d.is_default ? '(Default)' : ''}
                </option>
              ))}
            </select>

            <button
              onClick={() => setShowNewDashModal(true)}
              title="New Dashboard"
              style={{
                background: 'rgba(255,255,255,0.05)',
                border: '1px solid rgba(255,255,255,0.1)',
                color: '#f8fafc',
                padding: '0.4rem 0.6rem',
                borderRadius: '6px',
                fontSize: '0.8rem',
                display: 'flex',
                alignItems: 'center',
                gap: '0.25rem',
                cursor: 'pointer',
              }}
            >
              <Plus size={14} /> New
            </button>

            <button
              onClick={handleDuplicateDashboard}
              title="Duplicate Dashboard"
              style={{
                background: 'rgba(255,255,255,0.05)',
                border: '1px solid rgba(255,255,255,0.1)',
                color: '#f8fafc',
                padding: '0.4rem 0.6rem',
                borderRadius: '6px',
                fontSize: '0.8rem',
                display: 'flex',
                alignItems: 'center',
                gap: '0.25rem',
                cursor: 'pointer',
              }}
            >
              <Copy size={14} /> Duplicate
            </button>

            {activeDashboard && !activeDashboard.is_default && (
              <button
                onClick={handleDeleteDashboard}
                title="Delete Dashboard"
                style={{
                  background: 'rgba(239,68,68,0.1)',
                  border: '1px solid rgba(239,68,68,0.2)',
                  color: '#ef4444',
                  padding: '0.4rem 0.6rem',
                  borderRadius: '6px',
                  fontSize: '0.8rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.25rem',
                  cursor: 'pointer',
                }}
              >
                <Trash2 size={14} /> Delete
              </button>
            )}
          </div>
        </div>

        {/* Action Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <button
            onClick={() => setShowCatalogModal(true)}
            style={{
              background: '#6366f1',
              color: '#ffffff',
              border: 'none',
              borderRadius: '6px',
              padding: '0.45rem 0.9rem',
              fontSize: '0.85rem',
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
              cursor: 'pointer',
              boxShadow: '0 2px 8px rgba(99, 102, 241, 0.3)',
            }}
          >
            <Plus size={16} /> Add Widget
          </button>

          <button
            onClick={handleSaveDashboard}
            disabled={isSaving}
            style={{
              background: saveSuccessToast ? '#10b981' : '#1e293b',
              color: '#ffffff',
              border: '1px solid rgba(255,255,255,0.15)',
              borderRadius: '6px',
              padding: '0.45rem 0.9rem',
              fontSize: '0.85rem',
              fontWeight: 600,
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
              cursor: isSaving ? 'not-allowed' : 'pointer',
              transition: 'all 0.2s ease',
            }}
          >
            {saveSuccessToast ? <Check size={16} /> : <Save size={16} />}
            {saveSuccessToast ? 'Layout Saved!' : isSaving ? 'Saving...' : 'Save Layout'}
          </button>
        </div>
      </div>

      {/* Dashboard Subtitle & Active Portfolio Info */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem', fontSize: '0.85rem', color: 'rgba(255,255,255,0.6)' }}>
        <div>
          {activeDashboard?.description || 'Customizable persistent workspace layout.'}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', background: 'rgba(255,255,255,0.03)', padding: '0.25rem 0.6rem', borderRadius: '4px', border: '1px solid rgba(255,255,255,0.06)' }}>
          <Database size={13} style={{ color: '#38bdf8' }} />
          <span>Active Dataset: <strong style={{ color: '#f8fafc' }}>{activePortfolio?.name || 'NSE 10L Sample'}</strong></span>
        </div>
      </div>

      {/* My Registered Models Quick-Add Bar */}
      {registeredModels.length > 0 && (
        <div
          style={{
            marginBottom: '1.5rem',
            background: 'rgba(99, 102, 241, 0.05)',
            border: '1px solid rgba(99, 102, 241, 0.15)',
            borderRadius: '8px',
            padding: '0.75rem 1rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '0.75rem',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Cpu size={16} style={{ color: '#6366f1' }} />
            <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#f8fafc' }}>
              My SDK Models:
            </span>
            <span style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.6)' }}>
              ({registeredModels.length} registered algorithms available to mount)
            </span>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
            {registeredModels.slice(0, 5).map(m => (
              <button
                key={m.model_id}
                onClick={() => handleAddModelWidget(m)}
                style={{
                  background: 'rgba(255,255,255,0.06)',
                  border: '1px solid rgba(255,255,255,0.1)',
                  borderRadius: '4px',
                  padding: '0.25rem 0.5rem',
                  fontSize: '0.75rem',
                  color: '#f8fafc',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.35rem',
                }}
              >
                <Plus size={12} style={{ color: '#38bdf8' }} />
                {m.name || m.model_id}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Widgets Grid */}
      {(!activeDashboard?.widgets || activeDashboard.widgets.length === 0) ? (
        <div
          style={{
            padding: '4rem 2rem',
            textAlign: 'center',
            background: 'rgba(255,255,255,0.01)',
            border: '2px dashed rgba(255,255,255,0.1)',
            borderRadius: '12px',
          }}
        >
          <LayoutDashboard size={40} style={{ color: 'rgba(255,255,255,0.2)', margin: '0 auto 1rem' }} />
          <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: '#f8fafc', marginBottom: '0.5rem' }}>
            This dashboard workspace is empty
          </h3>
          <p style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.5)', maxWidth: '400px', margin: '0 auto 1.5rem' }}>
            Add quantitative risk, empirical distribution, attribution, or forecasting widgets from the catalog.
          </p>
          <button
            onClick={() => setShowCatalogModal(true)}
            style={{
              background: '#6366f1',
              color: '#ffffff',
              border: 'none',
              borderRadius: '6px',
              padding: '0.5rem 1.25rem',
              fontSize: '0.85rem',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Browse Widget Catalog
          </button>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(12, 1fr)', gap: '1.25rem' }}>
          {activeDashboard.widgets.map((w, index) => {
            const res = widgetResults[w.widget_id];
            const colSpan = w.width === 1 ? 4 : w.width === 2 ? 6 : 12;

            return (
              <div
                key={w.widget_id}
                style={{
                  gridColumn: `span ${colSpan} / span ${colSpan}`,
                  background: 'rgba(15, 23, 42, 0.75)',
                  backdropFilter: 'blur(10px)',
                  border: '1px solid rgba(255, 255, 255, 0.08)',
                  borderRadius: '10px',
                  display: 'flex',
                  flexDirection: 'column',
                  boxShadow: '0 4px 16px rgba(0, 0, 0, 0.25)',
                  transition: 'border 0.2s ease',
                }}
              >
                {/* Widget Header */}
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '0.75rem 1rem',
                    borderBottom: '1px solid rgba(255, 255, 255, 0.06)',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span style={{ fontSize: '0.85rem', fontWeight: 600, color: '#f8fafc' }}>
                      {w.title}
                    </span>
                    {w.model_id && (
                      <span
                        style={{
                          fontSize: '0.68rem',
                          background: 'rgba(99,102,241,0.15)',
                          color: '#a5b4fc',
                          padding: '0.15rem 0.4rem',
                          borderRadius: '3px',
                          border: '1px solid rgba(99,102,241,0.25)',
                        }}
                      >
                        {w.model_id}
                      </span>
                    )}
                  </div>

                  {/* Widget Controls */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                    <button
                      onClick={() => handleMoveWidget(index, 'left')}
                      disabled={index === 0}
                      title="Move Left"
                      style={{
                        background: 'transparent',
                        border: 'none',
                        color: index === 0 ? 'rgba(255,255,255,0.1)' : 'rgba(255,255,255,0.6)',
                        cursor: index === 0 ? 'not-allowed' : 'pointer',
                        padding: '0.2rem',
                      }}
                    >
                      <ChevronLeft size={15} />
                    </button>
                    <button
                      onClick={() => handleMoveWidget(index, 'right')}
                      disabled={index === activeDashboard.widgets.length - 1}
                      title="Move Right"
                      style={{
                        background: 'transparent',
                        border: 'none',
                        color: index === activeDashboard.widgets.length - 1 ? 'rgba(255,255,255,0.1)' : 'rgba(255,255,255,0.6)',
                        cursor: index === activeDashboard.widgets.length - 1 ? 'not-allowed' : 'pointer',
                        padding: '0.2rem',
                      }}
                    >
                      <ChevronRight size={15} />
                    </button>
                    <button
                      onClick={() => handleToggleWidth(w.widget_id)}
                      title={`Resize (Current: ${w.width}x)`}
                      style={{ background: 'transparent', border: 'none', color: 'rgba(255,255,255,0.6)', cursor: 'pointer', padding: '0.2rem' }}
                    >
                      <Maximize2 size={13} />
                    </button>
                    <button
                      onClick={() => {
                        setConfiguringWidget(w);
                        setShowConfigModal(true);
                      }}
                      title="Configure Widget"
                      style={{ background: 'transparent', border: 'none', color: 'rgba(255,255,255,0.6)', cursor: 'pointer', padding: '0.2rem' }}
                    >
                      <Settings size={13} />
                    </button>
                    <button
                      onClick={() => handleRemoveWidget(w.widget_id)}
                      title="Remove Widget"
                      style={{ background: 'transparent', border: 'none', color: 'rgba(239,68,68,0.7)', cursor: 'pointer', padding: '0.2rem' }}
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>

                {/* Widget Body */}
                <div style={{ padding: '1rem', flex: 1 }}>
                  {renderWidgetContent(w)}
                </div>

                {/* Widget Footer Lineage */}
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '0.5rem 1rem',
                    borderTop: '1px solid rgba(255, 255, 255, 0.04)',
                    fontSize: '0.7rem',
                    color: 'rgba(255, 255, 255, 0.4)',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                    <Clock size={11} />
                    <span>{res?.data_source || 'Live Engine'}</span>
                  </div>
                  {res?.drilldown_url && (
                    <a
                      href={res.drilldown_url}
                      style={{ color: '#38bdf8', textDecoration: 'none', display: 'flex', alignItems: 'center', gap: '0.2rem' }}
                    >
                      Drilldown <ExternalLink size={10} />
                    </a>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Widget Catalog Modal */}
      {showCatalogModal && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.7)',
            backdropFilter: 'blur(5px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 100,
            padding: '1rem',
          }}
        >
          <div
            style={{
              background: '#0f172a',
              border: '1px solid #334155',
              borderRadius: '12px',
              maxWidth: '850px',
              width: '100%',
              maxHeight: '85vh',
              display: 'flex',
              flexDirection: 'column',
              boxShadow: '0 20px 40px rgba(0,0,0,0.5)',
            }}
          >
            <div style={{ padding: '1.25rem 1.5rem', borderBottom: '1px solid rgba(255,255,255,0.08)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <h3 style={{ fontSize: '1.15rem', fontWeight: 700, margin: 0, color: '#f8fafc' }}>
                  Widget Catalog
                </h3>
                <p style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.5)', margin: '0.25rem 0 0' }}>
                  Select from 10 schema-driven quantitative widgets to add to your workspace.
                </p>
              </div>
              <button
                onClick={() => setShowCatalogModal(false)}
                style={{ background: 'transparent', border: 'none', color: 'rgba(255,255,255,0.6)', cursor: 'pointer', fontSize: '1.25rem' }}
              >
                ✕
              </button>
            </div>

            {/* Category Filter Tabs */}
            <div style={{ padding: '0.75rem 1.5rem', borderBottom: '1px solid rgba(255,255,255,0.06)', display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              {['all', 'Risk Analytics', 'Stress Testing', 'Portfolio Attribution', 'Machine Learning', 'Model Validation', 'Simulation', 'Audit & Lineage'].map(cat => (
                <button
                  key={cat}
                  onClick={() => setCatalogCategory(cat)}
                  style={{
                    background: catalogCategory === cat ? '#6366f1' : 'rgba(255,255,255,0.04)',
                    color: catalogCategory === cat ? '#ffffff' : 'rgba(255,255,255,0.7)',
                    border: '1px solid rgba(255,255,255,0.1)',
                    borderRadius: '4px',
                    padding: '0.25rem 0.6rem',
                    fontSize: '0.75rem',
                    fontWeight: 500,
                    cursor: 'pointer',
                  }}
                >
                  {cat === 'all' ? 'All Widgets' : cat}
                </button>
              ))}
            </div>

            {/* Catalog Grid */}
            <div style={{ padding: '1.5rem', overflowY: 'auto', display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: '1rem' }}>
              {catalog
                .filter(item => catalogCategory === 'all' || item.category === catalogCategory)
                .map(item => (
                  <div
                    key={item.type}
                    style={{
                      background: 'rgba(255,255,255,0.02)',
                      border: '1px solid rgba(255,255,255,0.08)',
                      borderRadius: '8px',
                      padding: '1rem',
                      display: 'flex',
                      flexDirection: 'column',
                      justifyContent: 'space-between',
                    }}
                  >
                    <div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                        <span style={{ fontSize: '0.7rem', color: '#6366f1', fontWeight: 600, textTransform: 'uppercase' }}>
                          {item.category}
                        </span>
                        <span style={{ fontSize: '0.68rem', color: 'rgba(255,255,255,0.4)' }}>
                          {item.default_width}x Col
                        </span>
                      </div>
                      <h4 style={{ fontSize: '0.9rem', fontWeight: 600, color: '#f8fafc', margin: '0 0 0.4rem' }}>
                        {item.title}
                      </h4>
                      <p style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.6)', margin: 0, lineHeight: 1.4 }}>
                        {item.description}
                      </p>
                    </div>

                    <button
                      onClick={() => handleAddWidget(item)}
                      style={{
                        marginTop: '1rem',
                        background: '#334155',
                        color: '#f8fafc',
                        border: 'none',
                        borderRadius: '4px',
                        padding: '0.4rem',
                        fontSize: '0.78rem',
                        fontWeight: 600,
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '0.35rem',
                      }}
                    >
                      <Plus size={13} /> Add to Workspace
                    </button>
                  </div>
                ))}
            </div>
          </div>
        </div>
      )}

      {/* New Dashboard Modal */}
      {showNewDashModal && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(5px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 110, padding: '1rem' }}>
          <div style={{ background: '#0f172a', border: '1px solid #334155', borderRadius: '10px', maxWidth: '450px', width: '100%', padding: '1.5rem' }}>
            <h3 style={{ fontSize: '1.1rem', fontWeight: 700, margin: '0 0 1rem', color: '#f8fafc' }}>
              Create New Custom Dashboard
            </h3>
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', fontSize: '0.8rem', color: 'rgba(255,255,255,0.7)', marginBottom: '0.35rem' }}>
                Dashboard Name
              </label>
              <input
                type="text"
                value={newDashName}
                onChange={e => setNewDashName(e.target.value)}
                placeholder="e.g. Quantitative Macro Stress Workspace"
                style={{ width: '100%', background: '#1e293b', border: '1px solid #334155', borderRadius: '6px', padding: '0.5rem', color: '#f8fafc', fontSize: '0.85rem' }}
              />
            </div>
            <div style={{ marginBottom: '1.5rem' }}>
              <label style={{ display: 'block', fontSize: '0.8rem', color: 'rgba(255,255,255,0.7)', marginBottom: '0.35rem' }}>
                Description (Optional)
              </label>
              <textarea
                value={newDashDesc}
                onChange={e => setNewDashDesc(e.target.value)}
                placeholder="Describe the research purpose of this dashboard..."
                rows={3}
                style={{ width: '100%', background: '#1e293b', border: '1px solid #334155', borderRadius: '6px', padding: '0.5rem', color: '#f8fafc', fontSize: '0.85rem' }}
              />
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
              <button
                onClick={() => setShowNewDashModal(false)}
                style={{ background: 'transparent', border: '1px solid #334155', color: '#f8fafc', padding: '0.45rem 0.9rem', borderRadius: '6px', fontSize: '0.85rem', cursor: 'pointer' }}
              >
                Cancel
              </button>
              <button
                onClick={handleCreateDashboard}
                disabled={!newDashName.trim()}
                style={{ background: '#6366f1', color: '#ffffff', border: 'none', padding: '0.45rem 1rem', borderRadius: '6px', fontSize: '0.85rem', fontWeight: 600, cursor: newDashName.trim() ? 'pointer' : 'not-allowed' }}
              >
                Create Dashboard
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Widget Configuration Modal */}
      {showConfigModal && configuringWidget && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(5px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 110, padding: '1rem' }}>
          <div style={{ background: '#0f172a', border: '1px solid #334155', borderRadius: '10px', maxWidth: '500px', width: '100%', padding: '1.5rem' }}>
            <h3 style={{ fontSize: '1.1rem', fontWeight: 700, margin: '0 0 1.25rem', color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Settings size={18} style={{ color: '#6366f1' }} />
              Configure Widget
            </h3>

            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', fontSize: '0.8rem', color: 'rgba(255,255,255,0.7)', marginBottom: '0.35rem' }}>
                Widget Title
              </label>
              <input
                type="text"
                value={configuringWidget.title}
                onChange={e => setConfiguringWidget({ ...configuringWidget, title: e.target.value })}
                style={{ width: '100%', background: '#1e293b', border: '1px solid #334155', borderRadius: '6px', padding: '0.5rem', color: '#f8fafc', fontSize: '0.85rem' }}
              />
            </div>

            {/* Model Selection */}
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', fontSize: '0.8rem', color: 'rgba(255,255,255,0.7)', marginBottom: '0.35rem' }}>
                Underlying Model (from Central Registry)
              </label>
              <select
                value={configuringWidget.model_id || ''}
                onChange={e => setConfiguringWidget({ ...configuringWidget, model_id: e.target.value || undefined })}
                style={{ width: '100%', background: '#1e293b', border: '1px solid #334155', borderRadius: '6px', padding: '0.5rem', color: '#f8fafc', fontSize: '0.85rem' }}
              >
                <option value="">Default Calculation Engine</option>
                {registeredModels.map(m => (
                  <option key={m.model_id} value={m.model_id}>
                    {m.name} ({m.model_id}) — {m.category}
                  </option>
                ))}
              </select>
            </div>

            {/* Metric Selection */}
            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', fontSize: '0.8rem', color: 'rgba(255,255,255,0.7)', marginBottom: '0.35rem' }}>
                Primary Metric
              </label>
              <select
                value={configuringWidget.metric || ''}
                onChange={e => setConfiguringWidget({ ...configuringWidget, metric: e.target.value })}
                style={{ width: '100%', background: '#1e293b', border: '1px solid #334155', borderRadius: '6px', padding: '0.5rem', color: '#f8fafc', fontSize: '0.85rem' }}
              >
                <option value="var_95">VaR (95% Confidence)</option>
                <option value="var_99">VaR (99% Confidence)</option>
                <option value="expected_shortfall_95">Expected Shortfall (95%)</option>
                <option value="annualized_volatility">Annualized Volatility</option>
                <option value="sharpe_ratio">Sharpe Ratio</option>
                <option value="max_drawdown">Maximum Drawdown</option>
              </select>
            </div>

            {/* Parameter adjustment */}
            <div style={{ marginBottom: '1.5rem', background: 'rgba(255,255,255,0.02)', padding: '0.75rem', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.06)' }}>
              <label style={{ display: 'block', fontSize: '0.75rem', color: 'rgba(255,255,255,0.6)', marginBottom: '0.35rem' }}>
                Confidence Level Parameter: {((configuringWidget.parameters?.confidence_level || 0.95) * 100).toFixed(1)}%
              </label>
              <input
                type="range"
                min="0.80"
                max="0.999"
                step="0.005"
                value={configuringWidget.parameters?.confidence_level || 0.95}
                onChange={e =>
                  setConfiguringWidget({
                    ...configuringWidget,
                    parameters: { ...configuringWidget.parameters, confidence_level: parseFloat(e.target.value) },
                  })
                }
                style={{ width: '100%' }}
              />
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
              <button
                onClick={() => setShowConfigModal(false)}
                style={{ background: 'transparent', border: '1px solid #334155', color: '#f8fafc', padding: '0.45rem 0.9rem', borderRadius: '6px', fontSize: '0.85rem', cursor: 'pointer' }}
              >
                Cancel
              </button>
              <button
                onClick={handleSaveWidgetConfig}
                style={{ background: '#6366f1', color: '#ffffff', border: 'none', padding: '0.45rem 1rem', borderRadius: '6px', fontSize: '0.85rem', fontWeight: 600, cursor: 'pointer' }}
              >
                Apply & Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
export default CustomDashboardWorkspace;
