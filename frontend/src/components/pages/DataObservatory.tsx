import React, { useState, useEffect, useMemo } from 'react';
import {
  Database, ShieldCheck, AlertTriangle, AlertCircle, CheckCircle,
  RefreshCw, Download, FileText, ChevronRight, Eye, Check, Copy, X,
  ExternalLink, Calendar, GitBranch, Search, Filter, Layers, ArrowRight,
  TrendingDown, TrendingUp, Sparkles, Scale, Info, Clock, Hash
} from 'lucide-react';
import { api } from '@/lib/api';

interface QualityViolation {
  record_index: number;
  timestamp: string;
  field_name: string;
  observed_value: any;
  expected_condition: string;
  severity: string;
  message: string;
}

interface QualityCheck {
  rule_id: string;
  name: string;
  category: string;
  status: 'PASSED' | 'WARNING' | 'FAILED';
  records_evaluated: number;
  violations_count: number;
  severity: string;
  methodology: string;
  threshold?: string;
  violations: QualityViolation[];
  warnings: string[];
}

interface DataQualityScorecard {
  dataset_id: string;
  symbol: string;
  evaluation_timestamp: string;
  total_records: number;
  overall_quality_score: number;
  grade: string;
  checks: QualityCheck[];
  summary_verdict: string;
  sha256_fingerprint: string;
}

interface DatasetItem {
  dataset_id: string;
  name: string;
  category: string;
  symbol: string;
  interval: string;
  date_range: string;
  row_count: number;
  provider: string;
  data_mode: string;
  last_successful_update: string;
  dataset_fingerprint: string;
  status: string;
  description: string;
}

export function DataObservatory({
  navigate,
  notify,
}: {
  navigate?: (path: string) => void;
  notify?: (msg: string) => void;
}) {
  const [datasets, setDatasets] = useState<DatasetItem[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState<string>('ds_market_reliance');
  const [selectedSymbol, setSelectedSymbol] = useState<string>('RELIANCE');
  
  const [scorecard, setScorecard] = useState<DataQualityScorecard | null>(null);
  const [coverage, setCoverage] = useState<any>(null);
  const [impactResult, setImpactResult] = useState<any>(null);
  const [dispositions, setDispositions] = useState<any[]>([]);

  const [activeTab, setActiveTab] = useState<'scorecard' | 'coverage' | 'provenance' | 'anomalies' | 'impact'>('scorecard');
  const [loading, setLoading] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [copiedFp, setCopiedFp] = useState<boolean>(false);

  // Anomaly Review Drawer
  const [selectedAnomaly, setSelectedAnomaly] = useState<QualityViolation | null>(null);
  const [selectedRuleId, setSelectedRuleId] = useState<string>('');
  const [dispositionStatus, setDispositionStatus] = useState<string>('reviewed_benign');
  const [dispositionNote, setDispositionNote] = useState<string>('');
  const [savingDisp, setSavingDisp] = useState<boolean>(false);

  // Impact Analysis Policy
  const [selectedPolicy, setSelectedPolicy] = useState<string>('reject_invalid');
  const [impactLoading, setImpactLoading] = useState<boolean>(false);

  // Load Inventory & Initial Audit
  useEffect(() => {
    loadInventory();
  }, []);

  useEffect(() => {
    if (selectedSymbol) {
      runFullAudit(selectedSymbol, selectedDatasetId);
    }
  }, [selectedSymbol, selectedDatasetId]);

  const loadInventory = async () => {
    try {
      const res = await api.listObservatoryDatasets();
      if (res.success && res.datasets) {
        setDatasets(res.datasets);
        if (res.datasets.length > 0 && !selectedDatasetId) {
          setSelectedDatasetId(res.datasets[0].dataset_id);
          setSelectedSymbol(res.datasets[0].symbol);
        }
      }
    } catch (err: any) {
      setErrorMsg(`Failed to load dataset inventory: ${err.message || err}`);
    }
  };

  const runFullAudit = async (sym: string, dsId: string) => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const [auditRes, covRes, dispRes] = await Promise.all([
        api.auditDatasetQuality({ symbol: sym, dataset_id: dsId }),
        api.computeDatasetCoverage({ symbol: sym }),
        api.listAnomalyDispositions(dsId),
      ]);

      if (auditRes.success && auditRes.scorecard) {
        setScorecard(auditRes.scorecard);
      }
      if (covRes.success && covRes.coverage) {
        setCoverage(covRes.coverage);
      }
      if (dispRes.success && dispRes.dispositions) {
        setDispositions(dispRes.dispositions);
      }

      // Pre-run default impact analysis
      runImpactAnalysis(sym, selectedPolicy);
    } catch (err: any) {
      setErrorMsg(`Audit evaluation failed: ${err.message || err}`);
    } finally {
      setLoading(false);
    }
  };

  const runImpactAnalysis = async (sym: string, pol: string) => {
    setImpactLoading(true);
    try {
      const res = await api.analyzeDataQualityImpact({ symbol: sym, policy: pol });
      if (res.success && res.impact) {
        setImpactResult(res.impact);
      }
    } catch (err: any) {
      notify?.(`Impact calculation failed: ${err.message || err}`);
    } finally {
      setImpactLoading(false);
    }
  };

  const handleSaveDisposition = async () => {
    if (!selectedAnomaly) return;
    setSavingDisp(true);
    try {
      const anomalyId = `anom_${selectedSymbol.toLowerCase()}_${selectedRuleId}_${selectedAnomaly.record_index}_${selectedAnomaly.timestamp}`;
      const res = await api.saveAnomalyDisposition({
        anomaly_id: anomalyId,
        dataset_id: selectedDatasetId,
        symbol: selectedSymbol,
        rule_id: selectedRuleId || 'RULE_ANOMALY',
        disposition: dispositionStatus,
        note: dispositionNote,
        reviewer: 'Quantitative Risk Specialist',
      });

      if (res.success) {
        notify?.('Anomaly review disposition recorded in audit ledger.');
        setSelectedAnomaly(null);
        setDispositionNote('');
        // Reload dispositions
        const dRes = await api.listAnomalyDispositions(selectedDatasetId);
        if (dRes.success) setDispositions(dRes.dispositions);
      }
    } catch (err: any) {
      notify?.(`Failed to save disposition: ${err.message || err}`);
    } finally {
      setSavingDisp(false);
    }
  };

  const copyFingerprint = (fp: string) => {
    navigator.clipboard.writeText(fp);
    setCopiedFp(true);
    setTimeout(() => setCopiedFp(false), 2000);
    notify?.('SHA-256 Dataset Fingerprint copied to clipboard.');
  };

  const exportAnomaliesCSV = () => {
    if (!scorecard) return;
    const allViolations: any[] = [];
    scorecard.checks.forEach((c) => {
      c.violations.forEach((v) => {
        allViolations.push({
          rule_id: c.rule_id,
          rule_name: c.name,
          category: c.category,
          severity: v.severity,
          record_index: v.record_index,
          timestamp: v.timestamp,
          field_name: v.field_name,
          observed_value: v.observed_value,
          expected_condition: v.expected_condition,
          message: v.message,
        });
      });
    });

    if (allViolations.length === 0) {
      notify?.('Zero anomalies present in current dataset.');
      return;
    }

    const headers = Object.keys(allViolations[0]).join(',');
    const rows = allViolations.map((row) =>
      Object.values(row)
        .map((val) => `"${String(val).replace(/"/g, '""')}"`)
        .join(',')
    );
    const csvContent = [headers, ...rows].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `${selectedSymbol}_anomalies_audit.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    notify?.(`Exported ${allViolations.length} anomalies to CSV.`);
  };

  const selectedDataset = useMemo(() => {
    return datasets.find((d) => d.dataset_id === selectedDatasetId) || datasets[0];
  }, [datasets, selectedDatasetId]);

  return (
    <div className="terminal-page" style={{ padding: '24px', maxWidth: '1440px', margin: '0 auto' }}>
      {/* Page Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' }}>
            <Database size={24} style={{ color: 'var(--color-primary, #3b82f6)' }} />
            <h1 style={{ fontSize: '24px', fontWeight: 700, margin: 0, letterSpacing: '-0.5px' }}>
              Data Quality &amp; Provenance Observatory
            </h1>
            <span
              style={{
                fontSize: '11px',
                fontWeight: 600,
                textTransform: 'uppercase',
                padding: '2px 8px',
                borderRadius: '4px',
                background: 'rgba(59, 130, 246, 0.15)',
                color: '#60a5fa',
                border: '1px solid rgba(59, 130, 246, 0.3)',
              }}
            >
              Page 10 • Lab Verified
            </span>
          </div>
          <p style={{ color: 'var(--color-text-muted, #94a3b8)', margin: 0, fontSize: '14px' }}>
            Verify market data integrity, chronological monotonicity, physical bounds, statutory NSE calendars, and risk impact prior to scenario modeling.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
          <select
            value={selectedDatasetId}
            onChange={(e) => {
              const ds = datasets.find((d) => d.dataset_id === e.target.value);
              if (ds) {
                setSelectedDatasetId(ds.dataset_id);
                setSelectedSymbol(ds.symbol);
              }
            }}
            className="terminal-select"
            style={{
              padding: '8px 12px',
              borderRadius: '6px',
              background: 'var(--color-surface, #1e293b)',
              color: 'var(--color-text, #f8fafc)',
              border: '1px solid var(--color-border, #334155)',
              fontSize: '13px',
              cursor: 'pointer',
            }}
          >
            {datasets.map((d) => (
              <option key={d.dataset_id} value={d.dataset_id}>
                {d.name} ({d.symbol}) — {d.row_count} bars
              </option>
            ))}
          </select>

          <button
            onClick={() => runFullAudit(selectedSymbol, selectedDatasetId)}
            disabled={loading}
            className="terminal-btn"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '8px 14px',
              borderRadius: '6px',
              background: 'var(--color-surface, #1e293b)',
              border: '1px solid var(--color-border, #334155)',
              color: 'var(--color-text, #f8fafc)',
              cursor: loading ? 'not-allowed' : 'pointer',
              fontSize: '13px',
            }}
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            {loading ? 'Auditing...' : 'Re-Run Audit'}
          </button>
        </div>
      </div>

      {errorMsg && (
        <div
          style={{
            padding: '12px 16px',
            marginBottom: '20px',
            borderRadius: '6px',
            background: 'rgba(239, 68, 68, 0.12)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            color: '#f87171',
            display: 'flex',
            alignItems: 'center',
            gap: '10px',
            fontSize: '14px',
          }}
        >
          <AlertCircle size={18} />
          <span>{errorMsg}</span>
        </div>
      )}

      {/* Dataset Overview Banner */}
      {selectedDataset && (
        <div
          className="terminal-card"
          style={{
            padding: '16px 20px',
            marginBottom: '24px',
            borderRadius: '8px',
            background: 'var(--color-surface, #1e293b)',
            border: '1px solid var(--color-border, #334155)',
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
            gap: '16px',
            alignItems: 'center',
          }}
        >
          <div>
            <div style={{ fontSize: '11px', textTransform: 'uppercase', color: '#94a3b8', marginBottom: '2px' }}>
              Selected Dataset
            </div>
            <div style={{ fontSize: '15px', fontWeight: 600, color: '#f8fafc' }}>
              {selectedDataset.name}
            </div>
            <div style={{ fontSize: '12px', color: '#64748b' }}>{selectedDataset.dataset_id}</div>
          </div>

          <div>
            <div style={{ fontSize: '11px', textTransform: 'uppercase', color: '#94a3b8', marginBottom: '2px' }}>
              Provider / Mode
            </div>
            <div style={{ fontSize: '13px', fontWeight: 600, color: '#38bdf8' }}>
              {selectedDataset.provider}
            </div>
            <div style={{ fontSize: '12px', color: '#22c55e' }}>{selectedDataset.data_mode}</div>
          </div>

          <div>
            <div style={{ fontSize: '11px', textTransform: 'uppercase', color: '#94a3b8', marginBottom: '2px' }}>
              Coverage Range
            </div>
            <div style={{ fontSize: '13px', fontWeight: 600, color: '#f8fafc' }}>
              {selectedDataset.date_range}
            </div>
            <div style={{ fontSize: '12px', color: '#64748b' }}>{selectedDataset.row_count} Daily Observations</div>
          </div>

          <div>
            <div style={{ fontSize: '11px', textTransform: 'uppercase', color: '#94a3b8', marginBottom: '2px' }}>
              SHA-256 Digest
            </div>
            <div
              onClick={() => copyFingerprint(scorecard?.sha256_fingerprint || selectedDataset.dataset_fingerprint)}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '4px 8px',
                borderRadius: '4px',
                background: 'rgba(0, 0, 0, 0.3)',
                fontSize: '12px',
                fontFamily: 'monospace',
                color: '#a78bfa',
                cursor: 'pointer',
                border: '1px solid rgba(167, 139, 250, 0.2)',
              }}
              title="Click to copy SHA-256 hash"
            >
              <Hash size={12} />
              {(scorecard?.sha256_fingerprint || selectedDataset.dataset_fingerprint).slice(0, 16)}...
              {copiedFp ? <Check size={12} style={{ color: '#22c55e' }} /> : <Copy size={12} />}
            </div>
          </div>

          {scorecard && (
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '11px', textTransform: 'uppercase', color: '#94a3b8', marginBottom: '2px' }}>
                Quality Grade
              </div>
              <div style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                <span
                  style={{
                    fontSize: '20px',
                    fontWeight: 800,
                    padding: '2px 10px',
                    borderRadius: '6px',
                    background:
                      scorecard.overall_quality_score >= 85
                        ? 'rgba(34, 197, 94, 0.2)'
                        : scorecard.overall_quality_score >= 70
                        ? 'rgba(234, 179, 8, 0.2)'
                        : 'rgba(239, 68, 68, 0.2)',
                    color:
                      scorecard.overall_quality_score >= 85
                        ? '#4ade80'
                        : scorecard.overall_quality_score >= 70
                        ? '#facc15'
                        : '#f87171',
                    border: '1px solid currentColor',
                  }}
                >
                  {scorecard.grade}
                </span>
                <span style={{ fontSize: '16px', fontWeight: 700, color: '#f8fafc' }}>
                  {scorecard.overall_quality_score} / 100
                </span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Tab Navigation */}
      <div
        style={{
          display: 'flex',
          gap: '8px',
          borderBottom: '1px solid var(--color-border, #334155)',
          marginBottom: '24px',
        }}
      >
        {[
          { id: 'scorecard', label: 'Quality Scorecard (9 Checks)', icon: ShieldCheck },
          { id: 'coverage', label: 'NSE Calendar Coverage', icon: Calendar },
          { id: 'impact', label: 'Data-Quality Impact Analysis', icon: Scale },
          { id: 'anomalies', label: 'Anomaly Investigation', icon: AlertTriangle },
          { id: 'provenance', label: 'Lineage & Provenance', icon: GitBranch },
        ].map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id as any)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '10px 16px',
                background: 'transparent',
                border: 'none',
                borderBottom: isActive ? '2px solid var(--color-primary, #3b82f6)' : '2px solid transparent',
                color: isActive ? '#f8fafc' : '#94a3b8',
                fontWeight: isActive ? 600 : 400,
                fontSize: '14px',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
            >
              <Icon size={16} style={{ color: isActive ? 'var(--color-primary, #3b82f6)' : '#64748b' }} />
              {tab.label}
              {tab.id === 'anomalies' && scorecard && (
                <span
                  style={{
                    fontSize: '11px',
                    padding: '1px 6px',
                    borderRadius: '10px',
                    background: 'rgba(239, 68, 68, 0.2)',
                    color: '#f87171',
                    fontWeight: 700,
                  }}
                >
                  {scorecard.checks.reduce((acc, c) => acc + c.violations_count, 0)}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Tab 1: Quality Scorecard */}
      {activeTab === 'scorecard' && scorecard && (
        <div>
          <div
            style={{
              padding: '16px',
              borderRadius: '8px',
              background: 'rgba(30, 41, 59, 0.7)',
              border: '1px solid var(--color-border, #334155)',
              marginBottom: '20px',
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
            }}
          >
            <Info size={20} style={{ color: '#38bdf8', flexShrink: 0 }} />
            <div style={{ fontSize: '13px', color: '#cbd5e1' }}>
              <strong>Scorecard Verdict:</strong> {scorecard.summary_verdict} Evaluated against 9 strict rules with no hidden denominators.
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(380px, 1fr))', gap: '16px' }}>
            {scorecard.checks.map((check) => {
              const isPassed = check.status === 'PASSED';
              const isWarning = check.status === 'WARNING';
              const isFailed = check.status === 'FAILED';

              return (
                <div
                  key={check.rule_id}
                  className="terminal-card"
                  style={{
                    padding: '16px',
                    borderRadius: '8px',
                    background: 'var(--color-surface, #1e293b)',
                    border: `1px solid ${
                      isFailed
                        ? 'rgba(239, 68, 68, 0.5)'
                        : isWarning
                        ? 'rgba(234, 179, 8, 0.4)'
                        : 'var(--color-border, #334155)'
                    }`,
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                  }}
                >
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                      <span
                        style={{
                          fontSize: '11px',
                          fontWeight: 600,
                          textTransform: 'uppercase',
                          color: '#94a3b8',
                          letterSpacing: '0.5px',
                        }}
                      >
                        {check.category} • {check.rule_id}
                      </span>
                      <span
                        style={{
                          fontSize: '11px',
                          fontWeight: 700,
                          padding: '2px 8px',
                          borderRadius: '4px',
                          background: isPassed
                            ? 'rgba(34, 197, 94, 0.15)'
                            : isWarning
                            ? 'rgba(234, 179, 8, 0.15)'
                            : 'rgba(239, 68, 68, 0.15)',
                          color: isPassed ? '#4ade80' : isWarning ? '#facc15' : '#f87171',
                          border: `1px solid ${
                            isPassed
                              ? 'rgba(34, 197, 94, 0.3)'
                              : isWarning
                              ? 'rgba(234, 179, 8, 0.3)'
                              : 'rgba(239, 68, 68, 0.3)'
                          }`,
                        }}
                      >
                        {check.status}
                      </span>
                    </div>

                    <h3 style={{ fontSize: '15px', fontWeight: 600, color: '#f8fafc', margin: '0 0 6px 0' }}>
                      {check.name}
                    </h3>
                    <p style={{ fontSize: '12px', color: '#94a3b8', margin: '0 0 12px 0', lineHeight: 1.4 }}>
                      {check.methodology}
                    </p>
                  </div>

                  <div
                    style={{
                      borderTop: '1px solid rgba(255, 255, 255, 0.06)',
                      paddingTop: '10px',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      fontSize: '12px',
                    }}
                  >
                    <div>
                      <span style={{ color: '#64748b' }}>Evaluated: </span>
                      <strong style={{ color: '#f8fafc' }}>{check.records_evaluated}</strong>
                      <span style={{ color: '#64748b', marginLeft: '12px' }}>Violations: </span>
                      <strong style={{ color: check.violations_count > 0 ? '#f87171' : '#4ade80' }}>
                        {check.violations_count}
                      </strong>
                    </div>

                    {check.violations_count > 0 && (
                      <button
                        onClick={() => {
                          setSelectedAnomaly(check.violations[0]);
                          setSelectedRuleId(check.rule_id);
                          setActiveTab('anomalies');
                        }}
                        style={{
                          background: 'transparent',
                          border: 'none',
                          color: '#38bdf8',
                          fontSize: '12px',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '4px',
                          cursor: 'pointer',
                          padding: 0,
                        }}
                      >
                        Inspect <ChevronRight size={14} />
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Tab 2: Coverage & Calendar Explorer */}
      {activeTab === 'coverage' && coverage && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
          <div className="terminal-card" style={{ padding: '20px', borderRadius: '8px', background: 'var(--color-surface, #1e293b)' }}>
            <h3 style={{ fontSize: '16px', fontWeight: 600, color: '#f8fafc', marginTop: 0, marginBottom: '16px' }}>
              NSE Trading Session Completeness
            </h3>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '20px' }}>
              <div style={{ padding: '12px', background: 'rgba(0,0,0,0.2)', borderRadius: '6px' }}>
                <div style={{ fontSize: '11px', textTransform: 'uppercase', color: '#94a3b8' }}>Expected Sessions</div>
                <div style={{ fontSize: '22px', fontWeight: 700, color: '#f8fafc' }}>
                  {coverage.expected_sessions_count}
                </div>
                <div style={{ fontSize: '11px', color: '#64748b' }}>Statutory NSE Calendar</div>
              </div>

              <div style={{ padding: '12px', background: 'rgba(0,0,0,0.2)', borderRadius: '6px' }}>
                <div style={{ fontSize: '11px', textTransform: 'uppercase', color: '#94a3b8' }}>Actual Sessions</div>
                <div style={{ fontSize: '22px', fontWeight: 700, color: '#38bdf8' }}>
                  {coverage.actual_sessions_count}
                </div>
                <div style={{ fontSize: '11px', color: '#64748b' }}>Observed in Feed</div>
              </div>
            </div>

            <div style={{ marginBottom: '20px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px', fontSize: '13px' }}>
                <span style={{ color: '#94a3b8' }}>Session Coverage Rate</span>
                <strong style={{ color: coverage.coverage_percentage >= 95 ? '#4ade80' : '#facc15' }}>
                  {coverage.coverage_percentage}%
                </strong>
              </div>
              <div style={{ width: '100%', height: '8px', background: '#334155', borderRadius: '4px', overflow: 'hidden' }}>
                <div
                  style={{
                    width: `${coverage.coverage_percentage}%`,
                    height: '100%',
                    background: coverage.coverage_percentage >= 95 ? '#22c55e' : '#eab308',
                    transition: 'width 0.4s ease',
                  }}
                />
              </div>
            </div>

            <div style={{ fontSize: '12px', color: '#64748b', lineHeight: 1.5 }}>
              * Calendar validation accurately accounts for weekends and statutory holidays (Gandhi Jayanti, Republic Day, Independence Day, Christmas). Legitimate market closures are not misclassified as missing observations.
            </div>
          </div>

          <div className="terminal-card" style={{ padding: '20px', borderRadius: '8px', background: 'var(--color-surface, #1e293b)' }}>
            <h3 style={{ fontSize: '16px', fontWeight: 600, color: '#f8fafc', marginTop: 0, marginBottom: '16px' }}>
              Statutory Holidays &amp; Gaps ({coverage.start_date} to {coverage.end_date})
            </h3>

            {coverage.missing_sessions_count > 0 ? (
              <div style={{ marginBottom: '16px' }}>
                <div style={{ fontSize: '12px', color: '#f87171', fontWeight: 600, marginBottom: '8px' }}>
                  Missing Expected Sessions ({coverage.missing_sessions_count})
                </div>
                <div style={{ maxHeight: '140px', overflowY: 'auto' }}>
                  {coverage.missing_sessions.map((d: string) => (
                    <div
                      key={d}
                      style={{
                        padding: '6px 10px',
                        marginBottom: '4px',
                        background: 'rgba(239, 68, 68, 0.1)',
                        borderRadius: '4px',
                        fontSize: '12px',
                        fontFamily: 'monospace',
                        color: '#fca5a5',
                        display: 'flex',
                        justifyContent: 'space-between',
                      }}
                    >
                      <span>{d}</span>
                      <span>Missing Candle</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div
                style={{
                  padding: '12px',
                  background: 'rgba(34, 197, 94, 0.1)',
                  borderRadius: '6px',
                  border: '1px solid rgba(34, 197, 94, 0.2)',
                  color: '#4ade80',
                  fontSize: '13px',
                  marginBottom: '16px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                }}
              >
                <CheckCircle size={16} /> Zero unexpected missing sessions. Complete trading coverage.
              </div>
            )}

            <div>
              <div style={{ fontSize: '12px', color: '#94a3b8', fontWeight: 600, marginBottom: '8px' }}>
                Recognized Official Statutory Holidays
              </div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                {coverage.official_holidays_in_window.length > 0 ? (
                  coverage.official_holidays_in_window.map((h: string) => (
                    <span
                      key={h}
                      style={{
                        padding: '4px 8px',
                        borderRadius: '4px',
                        background: 'rgba(255, 255, 255, 0.05)',
                        border: '1px solid #334155',
                        fontSize: '11px',
                        color: '#cbd5e1',
                        fontFamily: 'monospace',
                      }}
                    >
                      {h} (NSE Closed)
                    </span>
                  ))
                ) : (
                  <span style={{ fontSize: '12px', color: '#64748b' }}>No statutory holidays in sample window.</span>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tab 3: Data-Quality Impact Analysis */}
      {activeTab === 'impact' && (
        <div>
          <div
            className="terminal-card"
            style={{ padding: '20px', borderRadius: '8px', background: 'var(--color-surface, #1e293b)', marginBottom: '24px' }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <div>
                <h3 style={{ fontSize: '16px', fontWeight: 600, color: '#f8fafc', margin: 0 }}>
                  Controlled Data-Treatment Policy Simulation
                </h3>
                <p style={{ color: '#94a3b8', margin: '4px 0 0 0', fontSize: '13px' }}>
                  Compare quantitative risk metrics under Raw Data vs. an explicitly documented treatment policy. Zero silent forward-filling or interpolation.
                </p>
              </div>

              <div style={{ display: 'flex', gap: '10px' }}>
                <select
                  value={selectedPolicy}
                  onChange={(e) => {
                    setSelectedPolicy(e.target.value);
                    runImpactAnalysis(selectedSymbol, e.target.value);
                  }}
                  className="terminal-select"
                  style={{
                    padding: '8px 12px',
                    borderRadius: '6px',
                    background: '#0f172a',
                    color: '#f8fafc',
                    border: '1px solid #334155',
                    fontSize: '13px',
                  }}
                >
                  <option value="reject_invalid">Policy: Reject Invalid Observations</option>
                  <option value="deduplicate">Policy: Deduplicate Timestamps</option>
                  <option value="exclude_outliers">Policy: Exclude Statistical Outliers (&gt; 3.5σ)</option>
                  <option value="restrict_recent">Policy: Restrict to Recent 15 Bars</option>
                </select>

                <button
                  onClick={() => runImpactAnalysis(selectedSymbol, selectedPolicy)}
                  disabled={impactLoading}
                  className="terminal-btn"
                  style={{
                    padding: '8px 14px',
                    borderRadius: '6px',
                    background: 'var(--color-primary, #3b82f6)',
                    color: '#ffffff',
                    border: 'none',
                    fontWeight: 600,
                    cursor: 'pointer',
                    fontSize: '13px',
                  }}
                >
                  {impactLoading ? 'Simulating...' : 'Simulate Policy'}
                </button>
              </div>
            </div>

            {impactResult && (
              <div>
                <div
                  style={{
                    padding: '12px 16px',
                    borderRadius: '6px',
                    background: 'rgba(59, 130, 246, 0.1)',
                    border: '1px solid rgba(59, 130, 246, 0.25)',
                    color: '#93c5fd',
                    fontSize: '13px',
                    marginBottom: '20px',
                  }}
                >
                  {impactResult.explanation}
                </div>

                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', textAlign: 'left' }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid #334155', color: '#94a3b8' }}>
                        <th style={{ padding: '10px' }}>Risk Metric</th>
                        <th style={{ padding: '10px' }}>Raw Series</th>
                        <th style={{ padding: '10px' }}>Treated Series ({impactResult.policy})</th>
                        <th style={{ padding: '10px' }}>Absolute Delta</th>
                        <th style={{ padding: '10px' }}>Shift Impact</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                        <td style={{ padding: '10px', fontWeight: 600 }}>Sample Size</td>
                        <td style={{ padding: '10px' }}>{impactResult.sample_size_raw} bars</td>
                        <td style={{ padding: '10px' }}>{impactResult.sample_size_treated} bars</td>
                        <td style={{ padding: '10px', color: impactResult.records_modified_count > 0 ? '#facc15' : '#94a3b8' }}>
                          -{impactResult.records_modified_count} bars
                        </td>
                        <td style={{ padding: '10px' }}>
                          {impactResult.records_modified_count > 0 ? 'Observations Pruned' : 'Identical'}
                        </td>
                      </tr>

                      <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                        <td style={{ padding: '10px', fontWeight: 600 }}>Historical 95% VaR</td>
                        <td style={{ padding: '10px' }}>{(impactResult.raw_metrics.var_95 * 100).toFixed(2)}%</td>
                        <td style={{ padding: '10px' }}>{(impactResult.treated_metrics.var_95 * 100).toFixed(2)}%</td>
                        <td style={{ padding: '10px', color: impactResult.deltas.var_95_delta !== 0 ? '#38bdf8' : '#94a3b8' }}>
                          {(impactResult.deltas.var_95_delta * 100).toFixed(2)}%
                        </td>
                        <td style={{ padding: '10px' }}>
                          <span
                            style={{
                              padding: '2px 8px',
                              borderRadius: '4px',
                              fontSize: '11px',
                              fontWeight: 600,
                              background:
                                impactResult.deltas.var_95_delta < 0
                                  ? 'rgba(34, 197, 94, 0.15)'
                                  : 'rgba(239, 68, 68, 0.15)',
                              color: impactResult.deltas.var_95_delta < 0 ? '#4ade80' : '#f87171',
                            }}
                          >
                            {impactResult.deltas.var_95_delta < 0 ? 'Risk Reduced' : impactResult.deltas.var_95_delta > 0 ? 'Risk Elevated' : 'Unchanged'}
                          </span>
                        </td>
                      </tr>

                      <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                        <td style={{ padding: '10px', fontWeight: 600 }}>Expected Shortfall (95% ES/CVaR)</td>
                        <td style={{ padding: '10px' }}>{(impactResult.raw_metrics.es_95 * 100).toFixed(2)}%</td>
                        <td style={{ padding: '10px' }}>{(impactResult.treated_metrics.es_95 * 100).toFixed(2)}%</td>
                        <td style={{ padding: '10px', color: impactResult.deltas.es_95_delta !== 0 ? '#38bdf8' : '#94a3b8' }}>
                          {(impactResult.deltas.es_95_delta * 100).toFixed(2)}%
                        </td>
                        <td style={{ padding: '10px' }}>
                          <span
                            style={{
                              padding: '2px 8px',
                              borderRadius: '4px',
                              fontSize: '11px',
                              fontWeight: 600,
                              background:
                                impactResult.deltas.es_95_delta < 0
                                  ? 'rgba(34, 197, 94, 0.15)'
                                  : 'rgba(239, 68, 68, 0.15)',
                              color: impactResult.deltas.es_95_delta < 0 ? '#4ade80' : '#f87171',
                            }}
                          >
                            {impactResult.deltas.es_95_delta < 0 ? 'Tail Loss Reduced' : 'Tail Loss Elevated'}
                          </span>
                        </td>
                      </tr>

                      <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                        <td style={{ padding: '10px', fontWeight: 600 }}>Annualized Volatility (σ)</td>
                        <td style={{ padding: '10px' }}>{(impactResult.raw_metrics.volatility * 100).toFixed(2)}%</td>
                        <td style={{ padding: '10px' }}>{(impactResult.treated_metrics.volatility * 100).toFixed(2)}%</td>
                        <td style={{ padding: '10px' }}>{(impactResult.deltas.volatility_delta * 100).toFixed(2)}%</td>
                        <td style={{ padding: '10px' }}>Annualized 252d</td>
                      </tr>

                      <tr>
                        <td style={{ padding: '10px', fontWeight: 600 }}>Maximum Historical Drawdown</td>
                        <td style={{ padding: '10px' }}>{(impactResult.raw_metrics.max_drawdown * 100).toFixed(2)}%</td>
                        <td style={{ padding: '10px' }}>{(impactResult.treated_metrics.max_drawdown * 100).toFixed(2)}%</td>
                        <td style={{ padding: '10px' }}>{(impactResult.deltas.max_drawdown_delta * 100).toFixed(2)}%</td>
                        <td style={{ padding: '10px' }}>Peak to Trough</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tab 4: Anomaly Investigation & Review Disposition */}
      {activeTab === 'anomalies' && (
        <div style={{ display: 'grid', gridTemplateColumns: selectedAnomaly ? '1.2fr 1fr' : '1fr', gap: '20px' }}>
          <div className="terminal-card" style={{ padding: '20px', borderRadius: '8px', background: 'var(--color-surface, #1e293b)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <div>
                <h3 style={{ fontSize: '16px', fontWeight: 600, color: '#f8fafc', margin: 0 }}>
                  Identified Quality Anomalies ({scorecard ? scorecard.checks.reduce((acc, c) => acc + c.violations_count, 0) : 0})
                </h3>
                <div style={{ fontSize: '12px', color: '#94a3b8' }}>
                  Select an anomaly candidate to inspect affected fields or record an audit disposition.
                </div>
              </div>

              <button
                onClick={exportAnomaliesCSV}
                className="terminal-btn"
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '6px 12px',
                  borderRadius: '6px',
                  background: 'rgba(255, 255, 255, 0.05)',
                  border: '1px solid #334155',
                  color: '#f8fafc',
                  fontSize: '12px',
                  cursor: 'pointer',
                }}
              >
                <Download size={14} /> Export CSV
              </button>
            </div>

            {scorecard && scorecard.checks.some((c) => c.violations_count > 0) ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', maxHeight: '500px', overflowY: 'auto' }}>
                {scorecard.checks.map((c) =>
                  c.violations.map((v, vIdx) => (
                    <div
                      key={`${c.rule_id}_${vIdx}`}
                      onClick={() => {
                        setSelectedAnomaly(v);
                        setSelectedRuleId(c.rule_id);
                      }}
                      style={{
                        padding: '12px 14px',
                        borderRadius: '6px',
                        background: selectedAnomaly === v ? 'rgba(59, 130, 246, 0.15)' : 'rgba(0, 0, 0, 0.2)',
                        border: selectedAnomaly === v ? '1px solid #3b82f6' : '1px solid #334155',
                        cursor: 'pointer',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        transition: 'all 0.15s ease',
                      }}
                    >
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                          <span
                            style={{
                              fontSize: '10px',
                              fontWeight: 700,
                              textTransform: 'uppercase',
                              padding: '1px 6px',
                              borderRadius: '3px',
                              background: v.severity === 'CRITICAL' ? 'rgba(239, 68, 68, 0.2)' : 'rgba(234, 179, 8, 0.2)',
                              color: v.severity === 'CRITICAL' ? '#f87171' : '#facc15',
                            }}
                          >
                            {v.severity}
                          </span>
                          <span style={{ fontSize: '13px', fontWeight: 600, color: '#f8fafc' }}>
                            {c.name}
                          </span>
                          <span style={{ fontSize: '12px', color: '#64748b' }}>• {v.timestamp}</span>
                        </div>
                        <div style={{ fontSize: '12px', color: '#94a3b8' }}>{v.message}</div>
                      </div>

                      <ChevronRight size={16} style={{ color: '#64748b' }} />
                    </div>
                  ))
                )}
              </div>
            ) : (
              <div
                style={{
                  padding: '30px',
                  textAlign: 'center',
                  background: 'rgba(0,0,0,0.1)',
                  borderRadius: '6px',
                  color: '#4ade80',
                }}
              >
                <CheckCircle size={28} style={{ margin: '0 auto 10px auto' }} />
                <div style={{ fontWeight: 600, fontSize: '15px' }}>Zero Active Data Anomalies</div>
                <div style={{ fontSize: '13px', color: '#94a3b8', marginTop: '4px' }}>
                  The dataset satisfies all 9 mathematical and chronological verification criteria.
                </div>
              </div>
            )}
          </div>

          {/* Anomaly Detail & Review Disposition Form */}
          {selectedAnomaly && (
            <div className="terminal-card" style={{ padding: '20px', borderRadius: '8px', background: 'var(--color-surface, #1e293b)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h3 style={{ fontSize: '16px', fontWeight: 600, color: '#f8fafc', margin: 0 }}>
                  Review Disposition
                </h3>
                <button
                  onClick={() => setSelectedAnomaly(null)}
                  style={{ background: 'transparent', border: 'none', color: '#94a3b8', cursor: 'pointer' }}
                >
                  <X size={16} />
                </button>
              </div>

              <div style={{ marginBottom: '16px', fontSize: '13px', lineHeight: 1.6 }}>
                <div><span style={{ color: '#94a3b8' }}>Timestamp: </span><strong>{selectedAnomaly.timestamp}</strong></div>
                <div><span style={{ color: '#94a3b8' }}>Field Name: </span><strong>{selectedAnomaly.field_name}</strong></div>
                <div><span style={{ color: '#94a3b8' }}>Observed Value: </span><span style={{ color: '#f87171' }}>{String(selectedAnomaly.observed_value)}</span></div>
                <div><span style={{ color: '#94a3b8' }}>Expected Condition: </span><span style={{ color: '#4ade80' }}>{selectedAnomaly.expected_condition}</span></div>
                <div><span style={{ color: '#94a3b8' }}>Rule ID: </span><code>{selectedRuleId}</code></div>
              </div>

              <div style={{ borderTop: '1px solid #334155', paddingTop: '16px', marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#94a3b8', marginBottom: '6px' }}>
                  Disposition Decision
                </label>
                <select
                  value={dispositionStatus}
                  onChange={(e) => setDispositionStatus(e.target.value)}
                  className="terminal-select"
                  style={{
                    width: '100%',
                    padding: '8px 10px',
                    borderRadius: '6px',
                    background: '#0f172a',
                    color: '#f8fafc',
                    border: '1px solid #334155',
                    fontSize: '13px',
                    marginBottom: '12px',
                  }}
                >
                  <option value="reviewed_benign">Reviewed Benign (Genuine Market Event)</option>
                  <option value="confirmed_defect">Confirmed Defect (Requires Treatment Policy)</option>
                  <option value="suppressed">Suppressed (Known Exchange Quirk)</option>
                  <option value="pending_remediation">Pending Remediation</option>
                </select>

                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#94a3b8', marginBottom: '6px' }}>
                  Analyst Rationale / Explanation Note
                </label>
                <textarea
                  value={dispositionNote}
                  onChange={(e) => setDispositionNote(e.target.value)}
                  placeholder="e.g., Corporate action adjustment confirmed by exchange filing; return jump is genuine."
                  rows={3}
                  style={{
                    width: '100%',
                    padding: '8px 10px',
                    borderRadius: '6px',
                    background: '#0f172a',
                    color: '#f8fafc',
                    border: '1px solid #334155',
                    fontSize: '13px',
                    fontFamily: 'inherit',
                    resize: 'vertical',
                    marginBottom: '16px',
                  }}
                />

                <button
                  onClick={handleSaveDisposition}
                  disabled={savingDisp}
                  className="terminal-btn"
                  style={{
                    width: '100%',
                    padding: '10px',
                    borderRadius: '6px',
                    background: 'var(--color-primary, #3b82f6)',
                    color: '#ffffff',
                    border: 'none',
                    fontWeight: 600,
                    cursor: savingDisp ? 'not-allowed' : 'pointer',
                    fontSize: '13px',
                  }}
                >
                  {savingDisp ? 'Recording...' : 'Commit Non-Destructive Disposition'}
                </button>
                <div style={{ fontSize: '11px', color: '#64748b', marginTop: '6px', textAlign: 'center' }}>
                  * Source market data will NOT be mutated or silently overwritten.
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Tab 5: Lineage & Provenance */}
      {activeTab === 'provenance' && (
        <div className="terminal-card" style={{ padding: '24px', borderRadius: '8px', background: 'var(--color-surface, #1e293b)' }}>
          <h3 style={{ fontSize: '16px', fontWeight: 600, color: '#f8fafc', marginTop: 0, marginBottom: '16px' }}>
            Data Lineage &amp; Cryptographic Fingerprint
          </h3>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '16px', marginBottom: '24px' }}>
            <div style={{ padding: '16px', background: 'rgba(0,0,0,0.2)', borderRadius: '6px' }}>
              <div style={{ fontSize: '11px', textTransform: 'uppercase', color: '#94a3b8', marginBottom: '4px' }}>
                Primary Ingestion Provider
              </div>
              <div style={{ fontSize: '16px', fontWeight: 600, color: '#38bdf8' }}>
                {selectedDataset?.provider || 'upstox_v3'}
              </div>
              <div style={{ fontSize: '12px', color: '#64748b' }}>Canonical Financial API Adapter</div>
            </div>

            <div style={{ padding: '16px', background: 'rgba(0,0,0,0.2)', borderRadius: '6px' }}>
              <div style={{ fontSize: '11px', textTransform: 'uppercase', color: '#94a3b8', marginBottom: '4px' }}>
                Data Source Mode
              </div>
              <div style={{ fontSize: '16px', fontWeight: 600, color: '#4ade80' }}>
                {selectedDataset?.data_mode || 'REAL_DATA'}
              </div>
              <div style={{ fontSize: '12px', color: '#64748b' }}>Zero Synthetic / Mock Candles</div>
            </div>

            <div style={{ padding: '16px', background: 'rgba(0,0,0,0.2)', borderRadius: '6px' }}>
              <div style={{ fontSize: '11px', textTransform: 'uppercase', color: '#94a3b8', marginBottom: '4px' }}>
                Sampling Interval
              </div>
              <div style={{ fontSize: '16px', fontWeight: 600, color: '#f8fafc' }}>
                1-Day Regular Trading Hours (RTH)
              </div>
              <div style={{ fontSize: '12px', color: '#64748b' }}>IST Timezone (+05:30)</div>
            </div>
          </div>

          <div style={{ padding: '16px', background: 'rgba(0,0,0,0.3)', borderRadius: '6px', marginBottom: '24px' }}>
            <div style={{ fontSize: '12px', fontWeight: 600, color: '#94a3b8', marginBottom: '6px' }}>
              Deterministic SHA-256 Dataset Digest
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <code style={{ fontSize: '13px', color: '#a78bfa', fontFamily: 'monospace', wordBreak: 'break-all' }}>
                {scorecard?.sha256_fingerprint || selectedDataset?.dataset_fingerprint}
              </code>
              <button
                onClick={() => copyFingerprint(scorecard?.sha256_fingerprint || selectedDataset?.dataset_fingerprint || '')}
                style={{
                  background: 'rgba(255, 255, 255, 0.05)',
                  border: '1px solid #334155',
                  borderRadius: '4px',
                  color: '#cbd5e1',
                  padding: '4px 8px',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px',
                  fontSize: '12px',
                }}
              >
                {copiedFp ? <Check size={14} style={{ color: '#22c55e' }} /> : <Copy size={14} />}
                {copiedFp ? 'Copied' : 'Copy'}
              </button>
            </div>
          </div>

          <div>
            <h4 style={{ fontSize: '14px', fontWeight: 600, color: '#f8fafc', marginBottom: '10px' }}>
              Downstream Experiment Consumption
            </h4>
            <div style={{ fontSize: '13px', color: '#94a3b8', lineHeight: 1.5 }}>
              This dataset fingerprint is actively referenced across Strategy Backtest Lab runs and Model Validation experiments in the Unified Experiment Registry. If future observations differ or adjustments occur, reproducibility audits will immediately flag fingerprint mismatch.
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
