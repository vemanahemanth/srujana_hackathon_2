import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  BriefcaseBusiness, Plus, RefreshCw, Download, Upload, Trash2, Edit3,
  Copy, ShieldCheck, AlertTriangle, ArrowUpRight, ArrowDownRight,
  PieChart as PieChartIcon, BarChart2, Activity, HelpCircle, X, Check,
  Search, ExternalLink, Calendar, DollarSign, Layers, ChevronDown
} from 'lucide-react';
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip,
  ResponsiveContainer, Legend
} from 'recharts';
import {
  api,
  type Portfolio as ApiPortfolio,
  type Holding,
  type Transaction,
  type ConcentrationReport
} from '@/lib/api';

interface PortfolioWorkbenchProps {
  activePortfolio: ApiPortfolio | null;
  setActivePortfolio: (p: ApiPortfolio | null) => void;
  portfolioName: string;
  setPortfolioName: (name: string) => void;
  concentration: ConcentrationReport | null;
  setConcentration: (c: ConcentrationReport | null) => void;
  notify: (msg: string) => void;
  navigate: (path: string) => void;
}

const PALETTE = ['#2563eb', '#0d9488', '#d97706', '#dc2626', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'];

export const PortfolioWorkbench: React.FC<PortfolioWorkbenchProps> = ({
  activePortfolio,
  setActivePortfolio,
  portfolioName,
  setPortfolioName,
  concentration,
  setConcentration,
  notify,
  navigate,
}) => {
  // Navigation & Tabs
  const [activeTab, setActiveTab] = useState<'holdings' | 'allocation' | 'transactions' | 'reconciliation' | 'history' | 'provenance'>('holdings');

  // Portfolio Selector & CRUD State
  const [portfoliosList, setPortfoliosList] = useState<ApiPortfolio[]>([]);
  const [loadingPortfolios, setLoadingPortfolios] = useState(false);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [renameModalOpen, setRenameModalOpen] = useState(false);
  const [newPortName, setNewPortName] = useState('');
  const [newPortCurrency, setNewPortCurrency] = useState('INR');
  const [newPortBenchmark, setNewPortBenchmark] = useState('NIFTY');

  // Holding Creation & Search
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [symbolQuery, setSymbolQuery] = useState('');
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [searchingSymbols, setSearchingSymbols] = useState(false);
  const [selectedAsset, setSelectedAsset] = useState<any | null>(null);
  const [holdingQuantity, setHoldingQuantity] = useState('');
  const [holdingEntryPrice, setHoldingEntryPrice] = useState('');
  const [holdingSector, setHoldingSector] = useState('');
  const [holdingAssetClass, setHoldingAssetClass] = useState('equity');
  const [holdingNotes, setHoldingNotes] = useState('');

  // Live Market Quotes for Valuation
  const [liveQuotes, setLiveQuotes] = useState<Record<string, any>>({});
  const [refreshingQuotes, setRefreshingQuotes] = useState(false);
  const [quotesLastUpdated, setQuotesLastUpdated] = useState<string | null>(null);

  // Search & Filter within Table
  const [tableSearch, setTableSearch] = useState('');
  const [sortField, setSortField] = useState<'symbol' | 'value' | 'weight' | 'pnl' | 'change'>('value');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  // CSV Import / Export
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [csvText, setCsvText] = useState('');
  const [csvValidationErrors, setCsvValidationErrors] = useState<string[]>([]);
  const [csvParsedRows, setCsvParsedRows] = useState<Holding[]>([]);

  // Transactions State
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [loadingTransactions, setLoadingTransactions] = useState(false);
  const [txModalOpen, setTxModalOpen] = useState(false);
  const [txType, setTxType] = useState<'BUY' | 'SELL' | 'DEPOSIT' | 'WITHDRAWAL' | 'DIVIDEND' | 'FEE'>('BUY');
  const [txAssetId, setTxAssetId] = useState('');
  const [txQty, setTxQty] = useState('');
  const [txPrice, setTxPrice] = useState('');
  const [txFees, setTxFees] = useState('0');
  const [txNotes, setTxNotes] = useState('');

  // Holdings Reconciliation State
  const [reconciliationData, setReconciliationData] = useState<any | null>(null);
  const [loadingReconciliation, setLoadingReconciliation] = useState(false);

  // Historical Valuation State
  const [historicalSeries, setHistoricalSeries] = useState<any[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [historyLookback, setHistoryLookback] = useState<number>(180);

  // 1. Load available saved portfolios
  const loadSavedPortfolios = useCallback(async () => {
    setLoadingPortfolios(true);
    try {
      const res = await api.listPortfolios();
      const list = res.portfolios || [];
      setPortfoliosList(list);
      // If no active portfolio, set first if available
      if (!activePortfolio && list.length > 0) {
        setActivePortfolio(list[0]);
        setPortfolioName(list[0].name);
      }
    } catch (e: any) {
      console.warn('Could not list portfolios:', e.message);
    } finally {
      setLoadingPortfolios(false);
    }
  }, [activePortfolio, setActivePortfolio, setPortfolioName]);

  useEffect(() => {
    loadSavedPortfolios();
  }, []);

  // 2. Fetch live quotes for active portfolio holdings
  const fetchLiveQuotes = useCallback(async (holdings: Holding[]) => {
    if (!holdings || holdings.length === 0) return;
    setRefreshingQuotes(true);
    try {
      const symbols = Array.from(new Set(holdings.map(h => h.asset_id.trim().toUpperCase())));
      const quotes = await api.getQuotes(symbols);
      setLiveQuotes(quotes);
      setQuotesLastUpdated(new Date().toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata' }));
    } catch (e: any) {
      console.warn('Live quotes fetch error:', e.message);
    } finally {
      setRefreshingQuotes(false);
    }
  }, []);

  useEffect(() => {
    if (activePortfolio?.holdings?.length) {
      fetchLiveQuotes(activePortfolio.holdings);
    }
  }, [activePortfolio?.holdings, fetchLiveQuotes]);

  // 3. Load transactions and reconciliation when portfolio changes
  const loadTransactionsAndReconciliation = useCallback(async (portId: string) => {
    if (!portId) return;
    setLoadingTransactions(true);
    try {
      const txRes = await api.listTransactions(portId);
      setTransactions(txRes.transactions || []);
      const recRes = await api.reconcilePortfolio(portId);
      setReconciliationData(recRes);
    } catch (e: any) {
      console.warn('Transactions/Reconciliation error:', e.message);
    } finally {
      setLoadingTransactions(false);
    }
  }, []);

  useEffect(() => {
    if (activePortfolio?.portfolio_id) {
      loadTransactionsAndReconciliation(activePortfolio.portfolio_id);
    }
  }, [activePortfolio?.portfolio_id, loadTransactionsAndReconciliation]);

  // 4. Load historical valuation series
  const loadHistoricalValuation = useCallback(async () => {
    if (!activePortfolio || !activePortfolio.holdings?.length) return;
    setLoadingHistory(true);
    try {
      const res = await api.getHistoricalValuation(activePortfolio, historyLookback);
      setHistoricalSeries(res.series || []);
    } catch (e: any) {
      console.warn('Historical valuation fetch error:', e.message);
      setHistoricalSeries([]);
    } finally {
      setLoadingHistory(false);
    }
  }, [activePortfolio, historyLookback]);

  useEffect(() => {
    if (activeTab === 'history') {
      loadHistoricalValuation();
    }
  }, [activeTab, historyLookback, loadHistoricalValuation]);

  // 5. Symbol search in add modal
  useEffect(() => {
    if (symbolQuery.trim().length < 2) {
      setSearchResults([]);
      return;
    }
    const timer = setTimeout(async () => {
      setSearchingSymbols(true);
      try {
        const res = await api.searchInstruments(symbolQuery.trim());
        setSearchResults(res || []);
      } catch (e) {
        setSearchResults([]);
      } finally {
        setSearchingSymbols(false);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [symbolQuery]);

  // --- TRUTHFUL VALUATION & CALCULATIONS ---
  const evaluatedHoldings = useMemo(() => {
    const raw = activePortfolio?.holdings || [];
    let totMktVal = 0;
    let totCostBasis = 0;

    // First pass: Compute market values and cost basis
    const items = raw.map(h => {
      const sym = h.asset_id.trim().toUpperCase();
      const quote = liveQuotes[sym];
      // Live price priority: quote.last_price > quote.close > h.current_price
      const currentPx = quote?.last_price ?? quote?.close ?? h.current_price ?? 0;
      const mktVal = h.quantity * currentPx;
      const entryPx = h.entry_price ?? (h.current_price ?? currentPx);
      const costBasis = h.entry_price ? h.quantity * h.entry_price : 0;
      const hasCostBasis = h.entry_price !== undefined && h.entry_price !== null && h.entry_price > 0;
      const unrealizedPnl = hasCostBasis ? mktVal - costBasis : 0;
      const unrealizedPnlPct = hasCostBasis && costBasis > 0 ? (unrealizedPnl / costBasis) * 100 : 0;
      const dayChangePct = quote?.net_change_percentage ?? 0;

      totMktVal += mktVal;
      if (hasCostBasis) totCostBasis += costBasis;

      return {
        ...h,
        evaluatedPrice: currentPx,
        marketValue: mktVal,
        hasCostBasis,
        costBasis,
        unrealizedPnl,
        unrealizedPnlPct,
        dayChangePct,
        quoteTimestamp: quote?.timestamp || quotesLastUpdated,
        isLive: !!quote,
      };
    });

    // Second pass: Calculate normalized weights
    return items.map(item => ({
      ...item,
      weightPct: totMktVal > 0 ? (item.marketValue / totMktVal) * 100 : 0,
    }));
  }, [activePortfolio?.holdings, liveQuotes, quotesLastUpdated]);

  // Aggregate Portfolio Valuation Metrics
  const portfolioSummary = useMemo(() => {
    const totalMktVal = evaluatedHoldings.reduce((acc, h) => acc + h.marketValue, 0);
    const totalCostBasis = evaluatedHoldings.reduce((acc, h) => acc + (h.hasCostBasis ? h.costBasis : 0), 0);
    const pricedCount = evaluatedHoldings.filter(h => h.evaluatedPrice > 0).length;
    const valuationCoverage = evaluatedHoldings.length > 0 ? (pricedCount / evaluatedHoldings.length) * 100 : 0;
    const totalPnl = totalCostBasis > 0 ? totalMktVal - totalCostBasis : 0;
    const totalPnlPct = totalCostBasis > 0 ? (totalPnl / totalCostBasis) * 100 : 0;

    // Largest holding
    const sortedByWeight = [...evaluatedHoldings].sort((a, b) => b.weightPct - a.weightPct);
    const largestHolding = sortedByWeight[0];

    // HHI calculation from weights: sum(w_i^2)
    const hhiPoints = evaluatedHoldings.reduce((acc, h) => acc + Math.pow(h.weightPct, 2), 0);
    const hhiDecimal = hhiPoints / 10000;

    return {
      totalMarketValue: totalMktVal,
      totalCostBasis,
      totalPnl,
      totalPnlPct,
      valuationCoverage,
      holdingsCount: evaluatedHoldings.length,
      largestHoldingSymbol: largestHolding?.asset_id || '—',
      largestHoldingWeight: largestHolding?.weightPct || 0,
      hhiPoints: Math.round(hhiPoints),
      hhiDecimal: Number(hhiDecimal.toFixed(4)),
    };
  }, [evaluatedHoldings]);

  // Sector Breakdown
  const sectorAllocations = useMemo(() => {
    const map: Record<string, number> = {};
    for (const h of evaluatedHoldings) {
      const sec = h.sector?.trim() || 'Unassigned';
      map[sec] = (map[sec] || 0) + h.marketValue;
    }
    const total = portfolioSummary.totalMarketValue || 1;
    return Object.entries(map).map(([name, value]) => ({
      name,
      value: Math.round(value),
      weight: Number(((value / total) * 100).toFixed(1)),
    })).sort((a, b) => b.value - a.value);
  }, [evaluatedHoldings, portfolioSummary.totalMarketValue]);

  // Filtered & Sorted Table Rows
  const filteredHoldings = useMemo(() => {
    let rows = evaluatedHoldings.filter(h =>
      h.asset_id.toLowerCase().includes(tableSearch.toLowerCase()) ||
      (h.sector && h.sector.toLowerCase().includes(tableSearch.toLowerCase()))
    );

    rows.sort((a, b) => {
      let valA = 0;
      let valB = 0;
      if (sortField === 'symbol') return sortDir === 'asc' ? a.asset_id.localeCompare(b.asset_id) : b.asset_id.localeCompare(a.asset_id);
      if (sortField === 'value') { valA = a.marketValue; valB = b.marketValue; }
      if (sortField === 'weight') { valA = a.weightPct; valB = b.weightPct; }
      if (sortField === 'pnl') { valA = a.unrealizedPnl; valB = b.unrealizedPnl; }
      if (sortField === 'change') { valA = a.dayChangePct; valB = b.dayChangePct; }
      return sortDir === 'asc' ? valA - valB : valB - valA;
    });

    return rows;
  }, [evaluatedHoldings, tableSearch, sortField, sortDir]);

  // --- ACTIONS ---

  // Create new portfolio
  const handleCreatePortfolio = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newPortName.trim()) return;
    const newId = `port_${Date.now()}`;
    const newPort: ApiPortfolio = {
      portfolio_id: newId,
      name: newPortName.trim(),
      currency: newPortCurrency,
      benchmark: newPortBenchmark,
      holdings: [],
    };
    try {
      await api.savePortfolio(newPort);
      setActivePortfolio(newPort);
      setPortfolioName(newPort.name);
      setCreateModalOpen(false);
      setNewPortName('');
      notify(`Created portfolio '${newPort.name}'.`);
      loadSavedPortfolios();
    } catch (err: any) {
      notify(`Failed to create portfolio: ${err.message}`);
    }
  };

  // Delete portfolio
  const handleDeletePortfolio = async () => {
    if (!activePortfolio?.portfolio_id) return;
    if (!window.confirm(`Are you sure you want to delete portfolio '${activePortfolio.name}'? This action cannot be undone.`)) return;
    try {
      await api.deletePortfolio(activePortfolio.portfolio_id);
      notify(`Portfolio '${activePortfolio.name}' deleted.`);
      setActivePortfolio(null);
      setPortfolioName('No Portfolio Selected');
      loadSavedPortfolios();
    } catch (err: any) {
      notify(`Failed to delete portfolio: ${err.message}`);
    }
  };

  // Add holding to active portfolio
  const handleAddHolding = async (e: React.FormEvent) => {
    e.preventDefault();
    const sym = (selectedAsset?.symbol || symbolQuery).trim().toUpperCase();
    const qty = parseFloat(holdingQuantity);
    const entryPx = holdingEntryPrice ? parseFloat(holdingEntryPrice) : undefined;

    if (!sym) {
      notify('Please select or specify a valid instrument symbol.');
      return;
    }
    if (isNaN(qty) || qty <= 0) {
      notify('Holding quantity must be a strictly positive number.');
      return;
    }

    // Check duplicate
    if (activePortfolio?.holdings.some(h => h.asset_id.trim().toUpperCase() === sym)) {
      notify(`Instrument '${sym}' already exists in this portfolio. Edit the existing position instead.`);
      return;
    }

    const newH: Holding = {
      asset_id: sym,
      quantity: qty,
      entry_price: entryPx,
      sector: holdingSector || selectedAsset?.sector || 'General',
      asset_class: holdingAssetClass,
      currency: activePortfolio?.currency || 'INR',
      notes: holdingNotes || undefined,
    };

    const updatedHoldings = [...(activePortfolio?.holdings || []), newH];
    const updatedPort: ApiPortfolio = {
      ...(activePortfolio || { portfolio_id: `port_${Date.now()}`, name: 'New Portfolio', currency: 'INR' }),
      holdings: updatedHoldings,
    };

    try {
      await api.savePortfolio(updatedPort);
      setActivePortfolio(updatedPort);
      setAddModalOpen(false);
      // Reset form
      setSymbolQuery('');
      setSelectedAsset(null);
      setHoldingQuantity('');
      setHoldingEntryPrice('');
      setHoldingSector('');
      setHoldingNotes('');
      notify(`Added ${qty} units of ${sym} to portfolio.`);
    } catch (err: any) {
      notify(`Failed to save holding: ${err.message}`);
    }
  };

  // Remove holding
  const handleRemoveHolding = async (assetId: string) => {
    if (!activePortfolio) return;
    if (!window.confirm(`Remove ${assetId} from portfolio?`)) return;
    const updatedHoldings = activePortfolio.holdings.filter(h => h.asset_id !== assetId);
    const updatedPort = { ...activePortfolio, holdings: updatedHoldings };
    try {
      await api.savePortfolio(updatedPort);
      setActivePortfolio(updatedPort);
      notify(`Removed ${assetId}.`);
    } catch (err: any) {
      notify(`Failed to update portfolio: ${err.message}`);
    }
  };

  // Record Transaction
  const handleSaveTransaction = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activePortfolio?.portfolio_id) return;
    const qty = parseFloat(txQty);
    const price = parseFloat(txPrice);
    const fees = parseFloat(txFees || '0');

    if (!txAssetId.trim()) {
      notify('Asset symbol is required.');
      return;
    }
    if (isNaN(qty) || qty <= 0) {
      notify('Quantity must be strictly positive.');
      return;
    }

    try {
      await api.saveTransaction(activePortfolio.portfolio_id, {
        asset_id: txAssetId.trim().toUpperCase(),
        type: txType,
        quantity: qty,
        price: isNaN(price) ? 0 : price,
        fees: isNaN(fees) ? 0 : fees,
        notes: txNotes,
      });
      notify(`Transaction recorded for ${txAssetId}.`);
      setTxModalOpen(false);
      setTxAssetId('');
      setTxQty('');
      setTxPrice('');
      setTxNotes('');
      loadTransactionsAndReconciliation(activePortfolio.portfolio_id);
    } catch (err: any) {
      notify(`Transaction recording failed: ${err.message}`);
    }
  };

  // CSV Template download
  const handleDownloadCsvTemplate = () => {
    const csvContent = 'data:text/csv;charset=utf-8,asset_id,quantity,entry_price,sector,asset_class\nRELIANCE,25,1200.50,Energy,equity\nTCS,15,3500.00,IT,equity\nHDFCBANK,40,1650.00,Financials,equity\n';
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement('a');
    link.setAttribute('href', encodedUri);
    link.setAttribute('download', 'portfolio_holdings_template.csv');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // CSV Export of current holdings
  const handleExportHoldingsCsv = () => {
    if (!evaluatedHoldings.length) {
      notify('No holdings to export.');
      return;
    }
    const headers = ['asset_id', 'quantity', 'latest_price', 'market_value', 'entry_price', 'cost_basis', 'unrealized_pnl', 'weight_pct', 'sector', 'currency'];
    const rows = evaluatedHoldings.map(h => [
      h.asset_id,
      h.quantity,
      h.evaluatedPrice.toFixed(2),
      h.marketValue.toFixed(2),
      h.entry_price ? h.entry_price.toFixed(2) : '',
      h.hasCostBasis ? h.costBasis.toFixed(2) : '',
      h.hasCostBasis ? h.unrealizedPnl.toFixed(2) : '',
      h.weightPct.toFixed(2),
      h.sector || '',
      h.currency || 'INR',
    ]);
    const csvStr = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const blob = new Blob([csvStr], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${activePortfolio?.name || 'portfolio'}_holdings_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    notify('Exported holdings CSV.');
  };

  // CSV Parse and Validate
  const handleCsvTextChange = (text: string) => {
    setCsvText(text);
    const errors: string[] = [];
    const parsed: Holding[] = [];
    const lines = text.trim().split('\n');

    if (lines.length < 2) {
      setCsvValidationErrors(['CSV must contain a header row and at least one data row.']);
      setCsvParsedRows([]);
      return;
    }

    const header = lines[0].toLowerCase().split(',').map(s => s.trim());
    const idIdx = header.indexOf('asset_id');
    const qtyIdx = header.indexOf('quantity');
    const pxIdx = header.indexOf('entry_price') !== -1 ? header.indexOf('entry_price') : header.indexOf('price');
    const secIdx = header.indexOf('sector');

    if (idIdx === -1 || qtyIdx === -1) {
      setCsvValidationErrors(['Missing required columns: "asset_id" and "quantity" are mandatory.']);
      setCsvParsedRows([]);
      return;
    }

    const seenSymbols = new Set<string>();

    for (let i = 1; i < lines.length; i++) {
      const line = lines[i].trim();
      if (!line) continue;
      const cols = line.split(',').map(c => c.trim());
      const assetId = cols[idIdx]?.toUpperCase();
      const qty = parseFloat(cols[qtyIdx]);
      const entryPx = pxIdx !== -1 && cols[pxIdx] ? parseFloat(cols[pxIdx]) : undefined;
      const sector = secIdx !== -1 ? cols[secIdx] : 'General';

      if (!assetId) {
        errors.push(`Row ${i + 1}: Missing asset_id.`);
        continue;
      }
      if (seenSymbols.has(assetId)) {
        errors.push(`Row ${i + 1}: Duplicate symbol "${assetId}". Combine quantities instead.`);
        continue;
      }
      seenSymbols.add(assetId);

      if (isNaN(qty) || qty <= 0) {
        errors.push(`Row ${i + 1} (${assetId}): Quantity must be a strictly positive number.`);
        continue;
      }

      parsed.push({
        asset_id: assetId,
        quantity: qty,
        entry_price: entryPx,
        sector: sector || 'General',
        currency: activePortfolio?.currency || 'INR',
      });
    }

    setCsvValidationErrors(errors);
    setCsvParsedRows(parsed);
  };

  // Commit CSV Import
  const handleCommitImport = async () => {
    if (csvValidationErrors.length > 0 || csvParsedRows.length === 0) {
      notify('Cannot import CSV with validation errors.');
      return;
    }
    const updatedPort: ApiPortfolio = {
      ...(activePortfolio || { portfolio_id: `port_${Date.now()}`, name: 'Imported Portfolio', currency: 'INR' }),
      holdings: csvParsedRows,
    };
    try {
      await api.savePortfolio(updatedPort);
      setActivePortfolio(updatedPort);
      setImportModalOpen(false);
      setCsvText('');
      setCsvParsedRows([]);
      notify(`Successfully imported ${csvParsedRows.length} holdings.`);
    } catch (err: any) {
      notify(`Import failed: ${err.message}`);
    }
  };

  return (
    <div className="portfolio-workbench-page" style={{ padding: '1.5rem', maxWidth: '1600px', margin: '0 auto', color: 'var(--text-color, #f3f4f6)' }}>
      {/* 1. TOP HEADER & PORTFOLIO SELECTOR */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '1rem', borderBottom: '1px solid rgba(255,255,255,0.08)', paddingBottom: '1.25rem' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <BriefcaseBusiness size={24} color="#3b82f6" />
            <h1 style={{ margin: 0, fontSize: '1.75rem', fontWeight: 700, letterSpacing: '-0.02em' }}>
              Portfolio Workbench
            </h1>
            <span style={{ fontSize: '0.75rem', background: 'rgba(59,130,246,0.15)', color: '#60a5fa', padding: '0.2rem 0.6rem', borderRadius: '4px', fontWeight: 600 }}>
              PAGE 04
            </span>
          </div>
          <p style={{ margin: '0.35rem 0 0 0', color: 'rgba(255,255,255,0.6)', fontSize: '0.875rem' }}>
            Constituent holdings management, transparent mark-to-market valuation, and verifiable quantitative risk inputs.
          </p>
        </div>

        {/* Portfolio Selector & Management Buttons */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
          <div style={{ position: 'relative' }}>
            <select
              aria-label="Active portfolio selector"
              value={activePortfolio?.portfolio_id || ''}
              onChange={e => {
                const selected = portfoliosList.find(p => p.portfolio_id === e.target.value);
                if (selected) {
                  setActivePortfolio(selected);
                  setPortfolioName(selected.name);
                }
              }}
              style={{
                background: 'rgba(255,255,255,0.06)',
                border: '1px solid rgba(255,255,255,0.15)',
                color: '#fff',
                padding: '0.5rem 2rem 0.5rem 0.85rem',
                borderRadius: '6px',
                fontSize: '0.875rem',
                fontWeight: 600,
                appearance: 'none',
                cursor: 'pointer',
              }}
            >
              {portfoliosList.length === 0 && <option value="">No Portfolios Saved</option>}
              {portfoliosList.map(p => (
                <option key={p.portfolio_id} value={p.portfolio_id} style={{ background: '#111827', color: '#fff' }}>
                  {p.name} ({p.holdings?.length || 0} assets)
                </option>
              ))}
            </select>
            <ChevronDown size={14} style={{ position: 'absolute', right: '0.75rem', top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none', color: 'rgba(255,255,255,0.5)' }} />
          </div>

          <button
            className="button secondary"
            onClick={() => setCreateModalOpen(true)}
            style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.5rem 0.85rem', fontSize: '0.85rem' }}
          >
            <Plus size={15} /> New Portfolio
          </button>

          {activePortfolio && (
            <button
              className="button secondary"
              onClick={handleDeletePortfolio}
              title="Delete current portfolio"
              style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.5rem 0.75rem', fontSize: '0.85rem', color: '#ef4444' }}
            >
              <Trash2 size={15} />
            </button>
          )}

          {/* Jump to Page 05 Risk Lab */}
          <button
            className="button primary"
            onClick={() => navigate('/labs/risk-scenarios')}
            style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', background: '#2563eb', color: '#fff', fontWeight: 600, padding: '0.5rem 1rem', borderRadius: '6px' }}
          >
            <Activity size={16} /> Open Risk &amp; Scenario Lab
          </button>
        </div>
      </div>

      {/* 2. VALUATION & AUDIT METRICS BANNER */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
        {/* Total Market Value */}
        <div style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '1rem' }}>
          <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Total Market Value
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, margin: '0.25rem 0', color: '#fff' }}>
            ₹ {portfolioSummary.totalMarketValue.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)' }}>
            Base: {activePortfolio?.currency || 'INR'} • {portfolioSummary.holdingsCount} constituents
          </div>
        </div>

        {/* Invested Capital / Cost Basis */}
        <div style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '1rem' }}>
          <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Invested Cost Basis
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, margin: '0.25rem 0', color: '#fff' }}>
            {portfolioSummary.totalCostBasis > 0 ? `₹ ${portfolioSummary.totalCostBasis.toLocaleString('en-IN', { maximumFractionDigits: 2 })}` : '—'}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)' }}>
            {portfolioSummary.totalCostBasis > 0 ? 'Recorded acquisition basis' : 'No purchase prices supplied'}
          </div>
        </div>

        {/* Unrealized P/L */}
        <div style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '1rem' }}>
          <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Unrealized P&amp;L
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, margin: '0.25rem 0', color: portfolioSummary.totalPnl >= 0 ? '#10b981' : '#ef4444' }}>
            {portfolioSummary.totalCostBasis > 0
              ? `${portfolioSummary.totalPnl >= 0 ? '+' : ''}₹ ${portfolioSummary.totalPnl.toLocaleString('en-IN', { maximumFractionDigits: 2 })} (${portfolioSummary.totalPnlPct.toFixed(2)}%)`
              : '—'}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)' }}>
            Mark-to-market net difference
          </div>
        </div>

        {/* Valuation Coverage & Quality */}
        <div style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '1rem' }}>
          <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Valuation Coverage
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, margin: '0.25rem 0', color: portfolioSummary.valuationCoverage >= 100 ? '#10b981' : '#f59e0b' }}>
            {portfolioSummary.valuationCoverage.toFixed(0)}%
          </div>
          <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)' }}>
            Quotes: {quotesLastUpdated ? `Updated ${quotesLastUpdated}` : 'Pending refresh'}
          </div>
        </div>

        {/* Concentration / HHI */}
        <div style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '1rem' }}>
          <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.75rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            Concentration Index (HHI)
          </div>
          <div style={{ fontSize: '1.5rem', fontWeight: 700, margin: '0.25rem 0', color: portfolioSummary.hhiPoints > 2500 ? '#ef4444' : '#60a5fa' }}>
            {portfolioSummary.hhiPoints} pts
          </div>
          <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)' }}>
            Top: {portfolioSummary.largestHoldingSymbol} ({portfolioSummary.largestHoldingWeight.toFixed(1)}%)
          </div>
        </div>
      </div>

      {/* Partial Valuation Alert */}
      {portfolioSummary.valuationCoverage > 0 && portfolioSummary.valuationCoverage < 100 && (
        <div style={{ background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.3)', borderRadius: '6px', padding: '0.75rem 1rem', marginBottom: '1.25rem', display: 'flex', alignItems: 'center', gap: '0.75rem', fontSize: '0.85rem', color: '#fbbf24' }}>
          <AlertTriangle size={18} />
          <span>
            <b>Partial Valuation Notice:</b> Genuine market prices are missing for {(100 - portfolioSummary.valuationCoverage).toFixed(0)}% of constituents. The reported market value of ₹ {portfolioSummary.totalMarketValue.toLocaleString('en-IN')} represents a partial known subtotal, not an authoritative total portfolio valuation.
          </span>
        </div>
      )}

      {/* 3. WORKBENCH NAVIGATION TABS */}
      <div style={{ display: 'flex', gap: '0.5rem', borderBottom: '1px solid rgba(255,255,255,0.1)', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
        {[
          { key: 'holdings', label: `Constituent Holdings (${evaluatedHoldings.length})`, icon: BriefcaseBusiness },
          { key: 'allocation', label: 'Allocation & Weights', icon: PieChartIcon },
          { key: 'transactions', label: `Transaction Ledger (${transactions.length})`, icon: DollarSign },
          { key: 'reconciliation', label: 'Holdings Reconciliation', icon: ShieldCheck },
          { key: 'history', label: 'Historical Valuation', icon: Activity },
          { key: 'provenance', label: 'Data Provenance & Audit', icon: HelpCircle },
        ].map(tab => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key as any)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.4rem',
                padding: '0.65rem 1rem',
                background: isActive ? 'rgba(59,130,246,0.15)' : 'transparent',
                border: 'none',
                borderBottom: isActive ? '2px solid #3b82f6' : '2px solid transparent',
                color: isActive ? '#60a5fa' : 'rgba(255,255,255,0.6)',
                fontWeight: isActive ? 600 : 500,
                fontSize: '0.85rem',
                cursor: 'pointer',
                borderRadius: '4px 4px 0 0',
              }}
            >
              <Icon size={15} />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* 4. TAB PANELS */}

      {/* TAB 1: CONSTITUENT HOLDINGS TABLE */}
      {activeTab === 'holdings' && (
        <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '1.25rem' }}>
          {/* Action Bar */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem', flexWrap: 'wrap', gap: '0.75rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <div style={{ position: 'relative' }}>
                <Search size={14} style={{ position: 'absolute', left: '0.75rem', top: '50%', transform: 'translateY(-50%)', color: 'rgba(255,255,255,0.4)' }} />
                <input
                  type="text"
                  placeholder="Filter holdings..."
                  value={tableSearch}
                  onChange={e => setTableSearch(e.target.value)}
                  style={{
                    background: 'rgba(255,255,255,0.05)',
                    border: '1px solid rgba(255,255,255,0.15)',
                    borderRadius: '6px',
                    padding: '0.45rem 0.75rem 0.45rem 2.2rem',
                    color: '#fff',
                    fontSize: '0.85rem',
                    width: '220px',
                  }}
                />
              </div>

              <button
                className="button secondary"
                onClick={() => fetchLiveQuotes(activePortfolio?.holdings || [])}
                disabled={refreshingQuotes}
                style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.45rem 0.8rem', fontSize: '0.8rem' }}
              >
                <RefreshCw size={13} className={refreshingQuotes ? 'animate-spin' : ''} />
                {refreshingQuotes ? 'Fetching Quotes...' : 'Refresh Quotes'}
              </button>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              <button
                className="button secondary"
                onClick={() => setImportModalOpen(true)}
                style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.45rem 0.8rem', fontSize: '0.8rem' }}
              >
                <Upload size={13} /> Import CSV
              </button>

              <button
                className="button secondary"
                onClick={handleExportHoldingsCsv}
                style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.45rem 0.8rem', fontSize: '0.8rem' }}
              >
                <Download size={13} /> Export CSV
              </button>

              <button
                className="button secondary"
                onClick={() => setTxModalOpen(true)}
                style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.45rem 0.8rem', fontSize: '0.8rem' }}
              >
                <DollarSign size={13} /> Record Trade
              </button>

              <button
                className="button primary"
                onClick={() => setAddModalOpen(true)}
                style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.45rem 0.9rem', fontSize: '0.8rem', background: '#2563eb' }}
              >
                <Plus size={14} /> Add Holding
              </button>
            </div>
          </div>

          {/* Holdings Table */}
          {filteredHoldings.length === 0 ? (
            <div style={{ padding: '3.5rem 1rem', textAlign: 'center', color: 'rgba(255,255,255,0.5)' }}>
              <BriefcaseBusiness size={42} style={{ margin: '0 auto 1rem auto', opacity: 0.3 }} />
              <h3 style={{ margin: '0 0 0.5rem 0', color: '#fff' }}>This portfolio has no recorded constituents</h3>
              <p style={{ maxWidth: '460px', margin: '0 auto 1.5rem auto', fontSize: '0.875rem' }}>
                Build your portfolio by adding genuine NSE equities/indices using Upstox instrument search, or upload a validated CSV file.
              </p>
              <div style={{ display: 'flex', justifyContent: 'center', gap: '0.75rem' }}>
                <button className="button primary" onClick={() => setAddModalOpen(true)} style={{ background: '#2563eb' }}>
                  <Plus size={14} /> Add Instrument
                </button>
                <button className="button secondary" onClick={() => setImportModalOpen(true)}>
                  <Upload size={14} /> Import Holdings CSV
                </button>
              </div>
            </div>
          ) : (
            <div className="table-scroll" style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.12)', color: 'rgba(255,255,255,0.6)' }}>
                    <th style={{ padding: '0.75rem 0.5rem', cursor: 'pointer' }} onClick={() => { setSortField('symbol'); setSortDir(d => d === 'asc' ? 'desc' : 'asc'); }}>
                      Instrument {sortField === 'symbol' && (sortDir === 'asc' ? '↑' : '↓')}
                    </th>
                    <th style={{ padding: '0.75rem 0.5rem' }}>Sector</th>
                    <th style={{ padding: '0.75rem 0.5rem', textAlign: 'right' }}>Quantity</th>
                    <th style={{ padding: '0.75rem 0.5rem', textAlign: 'right' }}>Acquisition Cost</th>
                    <th style={{ padding: '0.75rem 0.5rem', textAlign: 'right' }}>Latest Price</th>
                    <th style={{ padding: '0.75rem 0.5rem', textAlign: 'right', cursor: 'pointer' }} onClick={() => { setSortField('value'); setSortDir(d => d === 'asc' ? 'desc' : 'asc'); }}>
                      Market Value {sortField === 'value' && (sortDir === 'asc' ? '↑' : '↓')}
                    </th>
                    <th style={{ padding: '0.75rem 0.5rem', textAlign: 'right', cursor: 'pointer' }} onClick={() => { setSortField('pnl'); setSortDir(d => d === 'asc' ? 'desc' : 'asc'); }}>
                      Unrealized P&amp;L {sortField === 'pnl' && (sortDir === 'asc' ? '↑' : '↓')}
                    </th>
                    <th style={{ padding: '0.75rem 0.5rem', textAlign: 'right', cursor: 'pointer' }} onClick={() => { setSortField('weight'); setSortDir(d => d === 'asc' ? 'desc' : 'asc'); }}>
                      Weight {sortField === 'weight' && (sortDir === 'asc' ? '↑' : '↓')}
                    </th>
                    <th style={{ padding: '0.75rem 0.5rem', textAlign: 'center' }}>Data Status</th>
                    <th style={{ padding: '0.75rem 0.5rem', textAlign: 'center' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredHoldings.map((h, i) => (
                    <tr key={`${h.asset_id}-${i}`} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                      {/* Instrument Symbol & Link to Page 03 */}
                      <td style={{ padding: '0.75rem 0.5rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                          <span style={{ fontWeight: 700, color: '#60a5fa' }}>{h.asset_id}</span>
                          <button
                            className="icon-btn"
                            title="Inspect in Page 03 Instrument Detail"
                            onClick={() => navigate(`/market/instrument/${encodeURIComponent(h.asset_id)}`)}
                            style={{ padding: '2px', background: 'transparent', border: 'none', color: 'rgba(255,255,255,0.4)', cursor: 'pointer' }}
                          >
                            <ExternalLink size={12} />
                          </button>
                        </div>
                      </td>

                      {/* Sector */}
                      <td style={{ padding: '0.75rem 0.5rem', color: 'rgba(255,255,255,0.7)' }}>
                        {h.sector || 'Unassigned'}
                      </td>

                      {/* Quantity */}
                      <td style={{ padding: '0.75rem 0.5rem', textAlign: 'right', fontWeight: 600 }}>
                        {h.quantity.toLocaleString('en-IN')}
                      </td>

                      {/* Acquisition Cost */}
                      <td style={{ padding: '0.75rem 0.5rem', textAlign: 'right', color: h.hasCostBasis ? '#fff' : 'rgba(255,255,255,0.4)' }}>
                        {h.hasCostBasis ? `₹ ${h.entry_price!.toFixed(2)}` : 'Unspecified'}
                      </td>

                      {/* Latest Price */}
                      <td style={{ padding: '0.75rem 0.5rem', textAlign: 'right', fontWeight: 600 }}>
                        {h.evaluatedPrice > 0 ? (
                          <div>
                            <div>₹ {h.evaluatedPrice.toFixed(2)}</div>
                            {h.dayChangePct !== 0 && (
                              <div style={{ fontSize: '0.7rem', color: h.dayChangePct >= 0 ? '#10b981' : '#ef4444' }}>
                                {h.dayChangePct >= 0 ? '+' : ''}{h.dayChangePct.toFixed(2)}%
                              </div>
                            )}
                          </div>
                        ) : (
                          <span style={{ color: 'rgba(255,255,255,0.4)' }}>Unavailable</span>
                        )}
                      </td>

                      {/* Market Value */}
                      <td style={{ padding: '0.75rem 0.5rem', textAlign: 'right', fontWeight: 700, color: '#fff' }}>
                        ₹ {h.marketValue.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
                      </td>

                      {/* Unrealized P&L */}
                      <td style={{ padding: '0.75rem 0.5rem', textAlign: 'right', fontWeight: 600 }}>
                        {h.hasCostBasis ? (
                          <span style={{ color: h.unrealizedPnl >= 0 ? '#10b981' : '#ef4444' }}>
                            {h.unrealizedPnl >= 0 ? '+' : ''}₹ {h.unrealizedPnl.toLocaleString('en-IN', { maximumFractionDigits: 2 })}
                            <div style={{ fontSize: '0.7rem' }}>
                              ({h.unrealizedPnlPct >= 0 ? '+' : ''}{h.unrealizedPnlPct.toFixed(2)}%)
                            </div>
                          </span>
                        ) : (
                          <span style={{ color: 'rgba(255,255,255,0.4)', fontSize: '0.75rem' }}>Requires input</span>
                        )}
                      </td>

                      {/* Weight */}
                      <td style={{ padding: '0.75rem 0.5rem', textAlign: 'right', fontWeight: 600, color: '#60a5fa' }}>
                        {h.weightPct.toFixed(2)}%
                      </td>

                      {/* Data Status */}
                      <td style={{ padding: '0.75rem 0.5rem', textAlign: 'center' }}>
                        {h.isLive ? (
                          <span style={{ fontSize: '0.7rem', background: 'rgba(16,185,129,0.15)', color: '#10b981', padding: '0.15rem 0.45rem', borderRadius: '4px', fontWeight: 600 }}>
                            Upstox Live
                          </span>
                        ) : (
                          <span style={{ fontSize: '0.7rem', background: 'rgba(245,158,11,0.15)', color: '#f59e0b', padding: '0.15rem 0.45rem', borderRadius: '4px', fontWeight: 600 }}>
                            Static Close
                          </span>
                        )}
                      </td>

                      {/* Actions */}
                      <td style={{ padding: '0.75rem 0.5rem', textAlign: 'center' }}>
                        <button
                          onClick={() => handleRemoveHolding(h.asset_id)}
                          title={`Remove ${h.asset_id}`}
                          style={{ background: 'transparent', border: 'none', color: 'rgba(255,255,255,0.4)', cursor: 'pointer', padding: '4px' }}
                        >
                          <Trash2 size={14} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* TAB 2: ALLOCATION & WEIGHTS */}
      {activeTab === 'allocation' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))', gap: '1.5rem' }}>
          {/* Sector Allocation */}
          <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '1.25rem' }}>
            <h3 style={{ margin: '0 0 1rem 0', fontSize: '1.05rem', fontWeight: 600 }}>Economic Sector Allocation</h3>
            <div style={{ height: '280px', width: '100%' }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={sectorAllocations}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={95}
                    innerRadius={55}
                    paddingAngle={3}
                  >
                    {sectorAllocations.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={PALETTE[index % PALETTE.length]} />
                    ))}
                  </Pie>
                  <RechartsTooltip formatter={(val: any) => [`₹ ${Number(val).toLocaleString('en-IN')}`, 'Market Value']} />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div style={{ marginTop: '1rem' }}>
              {sectorAllocations.map((sec, i) => (
                <div key={sec.name} style={{ display: 'flex', justifyContent: 'space-between', padding: '0.35rem 0', borderBottom: '1px solid rgba(255,255,255,0.04)', fontSize: '0.85rem' }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: PALETTE[i % PALETTE.length] }} />
                    {sec.name}
                  </span>
                  <span style={{ fontWeight: 600 }}>{sec.weight}% (₹ {sec.value.toLocaleString('en-IN')})</span>
                </div>
              ))}
            </div>
          </div>

          {/* Instrument Weights Bar Chart */}
          <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '1.25rem' }}>
            <h3 style={{ margin: '0 0 1rem 0', fontSize: '1.05rem', fontWeight: 600 }}>Individual Asset Weights (%)</h3>
            <div style={{ height: '320px', width: '100%' }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={evaluatedHoldings} margin={{ top: 10, right: 10, left: -20, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                  <XAxis dataKey="asset_id" stroke="rgba(255,255,255,0.5)" fontSize={11} angle={-30} textAnchor="end" />
                  <YAxis stroke="rgba(255,255,255,0.5)" fontSize={11} unit="%" />
                  <RechartsTooltip formatter={(val: any) => [`${Number(val).toFixed(2)}%`, 'Portfolio Weight']} />
                  <Bar dataKey="weightPct" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div style={{ background: 'rgba(255,255,255,0.03)', padding: '0.75rem', borderRadius: '6px', fontSize: '0.8rem', color: 'rgba(255,255,255,0.6)' }}>
              <b>Concentration Audit:</b> Herfindahl-Hirschman Index = {portfolioSummary.hhiPoints} points ({portfolioSummary.hhiDecimal} decimal). Effective $N$ assets = {portfolioSummary.hhiDecimal > 0 ? (1 / portfolioSummary.hhiDecimal).toFixed(1) : '—'}.
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: TRANSACTION LEDGER */}
      {activeTab === 'transactions' && (
        <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '1.25rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
            <div>
              <h3 style={{ margin: '0 0 0.25rem 0', fontSize: '1.05rem', fontWeight: 600 }}>Audited Transaction Ledger</h3>
              <p style={{ margin: 0, fontSize: '0.8rem', color: 'rgba(255,255,255,0.5)' }}>
                Immutable historical trades, acquisitions, deposits, and cash adjustments recorded against this portfolio.
              </p>
            </div>
            <button
              className="button primary"
              onClick={() => setTxModalOpen(true)}
              style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.8rem', background: '#2563eb' }}
            >
              <Plus size={14} /> Record Transaction
            </button>
          </div>

          {transactions.length === 0 ? (
            <div style={{ padding: '3rem 1rem', textAlign: 'center', color: 'rgba(255,255,255,0.5)' }}>
              <DollarSign size={36} style={{ margin: '0 auto 0.75rem auto', opacity: 0.3 }} />
              <p style={{ margin: '0 0 1rem 0' }}>No discrete transactions have been logged for this portfolio yet.</p>
              <button className="button secondary" onClick={() => setTxModalOpen(true)}>
                Record First Transaction
              </button>
            </div>
          ) : (
            <div className="table-scroll" style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.12)', color: 'rgba(255,255,255,0.6)' }}>
                    <th style={{ padding: '0.6rem 0.5rem' }}>Date &amp; Time</th>
                    <th style={{ padding: '0.6rem 0.5rem' }}>Type</th>
                    <th style={{ padding: '0.6rem 0.5rem' }}>Instrument</th>
                    <th style={{ padding: '0.6rem 0.5rem', textAlign: 'right' }}>Quantity</th>
                    <th style={{ padding: '0.6rem 0.5rem', textAlign: 'right' }}>Unit Price</th>
                    <th style={{ padding: '0.6rem 0.5rem', textAlign: 'right' }}>Gross Total</th>
                    <th style={{ padding: '0.6rem 0.5rem', textAlign: 'right' }}>Fees</th>
                    <th style={{ padding: '0.6rem 0.5rem' }}>Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {transactions.map(t => {
                    const gross = t.quantity * t.price;
                    return (
                      <tr key={t.transaction_id} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                        <td style={{ padding: '0.6rem 0.5rem', color: 'rgba(255,255,255,0.6)' }}>
                          {new Date(t.timestamp).toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata' })}
                        </td>
                        <td style={{ padding: '0.6rem 0.5rem' }}>
                          <span style={{
                            padding: '0.15rem 0.45rem',
                            borderRadius: '4px',
                            fontWeight: 600,
                            fontSize: '0.7rem',
                            background: t.type === 'BUY' ? 'rgba(16,185,129,0.15)' : t.type === 'SELL' ? 'rgba(239,68,68,0.15)' : 'rgba(59,130,246,0.15)',
                            color: t.type === 'BUY' ? '#10b981' : t.type === 'SELL' ? '#ef4444' : '#60a5fa',
                          }}>
                            {t.type}
                          </span>
                        </td>
                        <td style={{ padding: '0.6rem 0.5rem', fontWeight: 600, color: '#fff' }}>{t.asset_id}</td>
                        <td style={{ padding: '0.6rem 0.5rem', textAlign: 'right' }}>{t.quantity}</td>
                        <td style={{ padding: '0.6rem 0.5rem', textAlign: 'right' }}>₹ {t.price.toFixed(2)}</td>
                        <td style={{ padding: '0.6rem 0.5rem', textAlign: 'right', fontWeight: 600 }}>₹ {gross.toLocaleString('en-IN', { maximumFractionDigits: 2 })}</td>
                        <td style={{ padding: '0.6rem 0.5rem', textAlign: 'right', color: 'rgba(255,255,255,0.5)' }}>₹ {t.fees.toFixed(2)}</td>
                        <td style={{ padding: '0.6rem 0.5rem', color: 'rgba(255,255,255,0.5)', fontStyle: t.notes ? 'normal' : 'italic' }}>
                          {t.notes || '—'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* TAB 4: HOLDINGS RECONCILIATION */}
      {activeTab === 'reconciliation' && (
        <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '1.25rem' }}>
          <div style={{ marginBottom: '1.25rem' }}>
            <h3 style={{ margin: '0 0 0.25rem 0', fontSize: '1.05rem', fontWeight: 600 }}>Position Reconciliation Engine</h3>
            <p style={{ margin: 0, fontSize: '0.8rem', color: 'rgba(255,255,255,0.5)' }}>
              Verifies whether currently held positions correspond exactly to recorded trade history (Total Buys minus Total Sells).
            </p>
          </div>

          {!reconciliationData?.items ? (
            <div style={{ padding: '2rem', textAlign: 'center' }}>Loading reconciliation data...</div>
          ) : (
            <div>
              <div style={{
                background: reconciliationData.is_fully_reconciled ? 'rgba(16,185,129,0.1)' : 'rgba(245,158,11,0.1)',
                border: `1px solid ${reconciliationData.is_fully_reconciled ? 'rgba(16,185,129,0.3)' : 'rgba(245,158,11,0.3)'}`,
                padding: '0.75rem 1rem',
                borderRadius: '6px',
                marginBottom: '1rem',
                display: 'flex',
                alignItems: 'center',
                gap: '0.75rem',
                fontSize: '0.85rem',
                color: reconciliationData.is_fully_reconciled ? '#34d399' : '#fbbf24',
              }}>
                <ShieldCheck size={18} />
                <span>
                  {reconciliationData.is_fully_reconciled
                    ? 'All portfolio positions are fully reconciled with trade ledger or identified opening positions.'
                    : 'Discrepancies identified between current constituent quantities and transaction ledger sums.'}
                </span>
              </div>

              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.85rem' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.12)', color: 'rgba(255,255,255,0.6)' }}>
                    <th style={{ padding: '0.6rem 0.5rem' }}>Asset</th>
                    <th style={{ padding: '0.6rem 0.5rem', textAlign: 'right' }}>Holding Units</th>
                    <th style={{ padding: '0.6rem 0.5rem', textAlign: 'right' }}>Ledger Net Units</th>
                    <th style={{ padding: '0.6rem 0.5rem', textAlign: 'right' }}>Discrepancy</th>
                    <th style={{ padding: '0.6rem 0.5rem', textAlign: 'center' }}>Status</th>
                    <th style={{ padding: '0.6rem 0.5rem' }}>Audit Explanation</th>
                  </tr>
                </thead>
                <tbody>
                  {reconciliationData.items.map((item: any) => (
                    <tr key={item.asset_id} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                      <td style={{ padding: '0.6rem 0.5rem', fontWeight: 700, color: '#60a5fa' }}>{item.asset_id}</td>
                      <td style={{ padding: '0.6rem 0.5rem', textAlign: 'right', fontWeight: 600 }}>{item.holding_quantity}</td>
                      <td style={{ padding: '0.6rem 0.5rem', textAlign: 'right' }}>{item.ledger_quantity}</td>
                      <td style={{ padding: '0.6rem 0.5rem', textAlign: 'right', color: item.discrepancy !== 0 ? '#ef4444' : '#10b981', fontWeight: 600 }}>
                        {item.discrepancy > 0 ? `+${item.discrepancy}` : item.discrepancy}
                      </td>
                      <td style={{ padding: '0.6rem 0.5rem', textAlign: 'center' }}>
                        <span style={{
                          padding: '0.15rem 0.45rem',
                          borderRadius: '4px',
                          fontWeight: 600,
                          fontSize: '0.7rem',
                          background: item.status === 'RECONCILED' ? 'rgba(16,185,129,0.15)' : item.status === 'MANUAL_OPENING_POSITION' ? 'rgba(59,130,246,0.15)' : 'rgba(239,68,68,0.15)',
                          color: item.status === 'RECONCILED' ? '#10b981' : item.status === 'MANUAL_OPENING_POSITION' ? '#60a5fa' : '#ef4444',
                        }}>
                          {item.status}
                        </span>
                      </td>
                      <td style={{ padding: '0.6rem 0.5rem', color: 'rgba(255,255,255,0.6)', fontSize: '0.8rem' }}>
                        {item.explanation}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* TAB 5: HISTORICAL VALUATION */}
      {activeTab === 'history' && (
        <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '1.25rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem', flexWrap: 'wrap', gap: '0.75rem' }}>
            <div>
              <h3 style={{ margin: '0 0 0.25rem 0', fontSize: '1.05rem', fontWeight: 600 }}>Historical Portfolio Valuation Series</h3>
              <p style={{ margin: 0, fontSize: '0.8rem', color: 'rgba(255,255,255,0.5)' }}>
                Constructed from genuine Upstox historical candles aligning constituent prices across exchange trading dates.
              </p>
            </div>
            <div style={{ display: 'flex', gap: '0.4rem' }}>
              {[
                { label: '1M', days: 30 },
                { label: '3M', days: 90 },
                { label: '6M', days: 180 },
                { label: '1Y', days: 365 },
              ].map(btn => (
                <button
                  key={btn.label}
                  onClick={() => setHistoryLookback(btn.days)}
                  style={{
                    padding: '0.35rem 0.75rem',
                    borderRadius: '4px',
                    border: 'none',
                    background: historyLookback === btn.days ? '#3b82f6' : 'rgba(255,255,255,0.08)',
                    color: '#fff',
                    fontSize: '0.75rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  {btn.label}
                </button>
              ))}
            </div>
          </div>

          {loadingHistory ? (
            <div style={{ padding: '4rem 1rem', textAlign: 'center' }}>
              <RefreshCw size={24} className="animate-spin" style={{ margin: '0 auto 0.75rem auto' }} />
              <p>Reconstructing historical portfolio valuation from Upstox exchange candles...</p>
            </div>
          ) : historicalSeries.length === 0 ? (
            <div style={{ padding: '3rem 1rem', textAlign: 'center', color: 'rgba(255,255,255,0.5)' }}>
              <Activity size={36} style={{ margin: '0 auto 0.75rem auto', opacity: 0.3 }} />
              <p>No historical valuation series could be computed. Ensure portfolio contains constituents with genuine exchange history.</p>
            </div>
          ) : (
            <div>
              <div style={{ height: '340px', width: '100%', marginBottom: '1.25rem' }}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={historicalSeries} margin={{ top: 10, right: 10, left: 10, bottom: 20 }}>
                    <defs>
                      <linearGradient id="mktValGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.4} />
                        <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                    <XAxis dataKey="date" stroke="rgba(255,255,255,0.5)" fontSize={11} angle={-30} textAnchor="end" />
                    <YAxis
                      stroke="rgba(255,255,255,0.5)"
                      fontSize={11}
                      domain={['auto', 'auto']}
                      tickFormatter={val => `₹ ${(val / 1000).toFixed(0)}k`}
                    />
                    <RechartsTooltip formatter={(val: any) => [`₹ ${Number(val).toLocaleString('en-IN')}`, 'Portfolio Value']} />
                    <Area type="monotone" dataKey="market_value" stroke="#3b82f6" strokeWidth={2} fillOpacity={1} fill="url(#mktValGrad)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>

              <div style={{ background: 'rgba(255,255,255,0.03)', padding: '0.75rem 1rem', borderRadius: '6px', fontSize: '0.8rem', color: 'rgba(255,255,255,0.6)' }}>
                <b>Methodology Disclosure:</b> Historical valuation assumes constant current constituent quantities held over the lookback horizon. Holiday gaps are aligned by forward-filling the last known exchange close. Total observed points: {historicalSeries.length} trading days.
              </div>
            </div>
          )}
        </div>
      )}

      {/* TAB 6: DATA PROVENANCE & AUDIT */}
      {activeTab === 'provenance' && (
        <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '8px', padding: '1.25rem' }}>
          <h3 style={{ margin: '0 0 1rem 0', fontSize: '1.05rem', fontWeight: 600 }}>Data Provenance &amp; Valuation Audit</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem', fontSize: '0.85rem' }}>
            <div style={{ background: 'rgba(255,255,255,0.03)', padding: '0.85rem', borderRadius: '6px' }}>
              <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.75rem', fontWeight: 600 }}>MARKET DATA PROVIDER</div>
              <div style={{ fontWeight: 600, color: '#fff', marginTop: '0.25rem' }}>Upstox Market Data API V3</div>
              <div style={{ color: 'rgba(255,255,255,0.5)', marginTop: '0.25rem' }}>Direct live quotes &amp; normalized OHLCV exchange candles.</div>
            </div>

            <div style={{ background: 'rgba(255,255,255,0.03)', padding: '0.85rem', borderRadius: '6px' }}>
              <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.75rem', fontWeight: 600 }}>VALUATION PRICE CONVENTION</div>
              <div style={{ fontWeight: 600, color: '#fff', marginTop: '0.25rem' }}>Unadjusted Raw Exchange Closes</div>
              <div style={{ color: 'rgba(255,255,255,0.5)', marginTop: '0.25rem' }}>No corporate action adjustment or synthetic interpolation applied.</div>
            </div>

            <div style={{ background: 'rgba(255,255,255,0.03)', padding: '0.85rem', borderRadius: '6px' }}>
              <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.75rem', fontWeight: 600 }}>REAL-DATA POLICY STATUS</div>
              <div style={{ fontWeight: 600, color: '#10b981', marginTop: '0.25rem' }}>100% Genuine Market Observations</div>
              <div style={{ color: 'rgba(255,255,255,0.5)', marginTop: '0.25rem' }}>Zero mock prices, random holdings, or synthetic fallback values.</div>
            </div>

            <div style={{ background: 'rgba(255,255,255,0.03)', padding: '0.85rem', borderRadius: '6px' }}>
              <div style={{ color: 'rgba(255,255,255,0.5)', fontSize: '0.75rem', fontWeight: 600 }}>TIMEZONE CONVENTION</div>
              <div style={{ fontWeight: 600, color: '#fff', marginTop: '0.25rem' }}>Asia/Kolkata (+05:30 IST)</div>
              <div style={{ color: 'rgba(255,255,255,0.5)', marginTop: '0.25rem' }}>Aligned with National Stock Exchange of India (NSE) hours.</div>
            </div>
          </div>
        </div>
      )}

      {/* --- MODALS --- */}

      {/* CREATE PORTFOLIO MODAL */}
      {createModalOpen && (
        <div className="overlay" style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <form
            onSubmit={handleCreatePortfolio}
            style={{ background: '#111827', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '8px', padding: '1.5rem', width: '100%', maxWidth: '440px', color: '#fff' }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h3 style={{ margin: 0, fontSize: '1.15rem', fontWeight: 600 }}>Create New Portfolio</h3>
              <button type="button" onClick={() => setCreateModalOpen(false)} style={{ background: 'transparent', border: 'none', color: 'rgba(255,255,255,0.5)', cursor: 'pointer' }}>
                <X size={18} />
              </button>
            </div>

            <div style={{ marginBottom: '1rem' }}>
              <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: 'rgba(255,255,255,0.6)', marginBottom: '0.35rem' }}>
                PORTFOLIO NAME
              </label>
              <input
                type="text"
                required
                placeholder="e.g. India High-Growth Equity"
                value={newPortName}
                onChange={e => setNewPortName(e.target.value)}
                style={{ width: '100%', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '6px', padding: '0.5rem 0.75rem', color: '#fff', fontSize: '0.85rem' }}
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '1.25rem' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: 'rgba(255,255,255,0.6)', marginBottom: '0.35rem' }}>
                  BASE CURRENCY
                </label>
                <select
                  value={newPortCurrency}
                  onChange={e => setNewPortCurrency(e.target.value)}
                  style={{ width: '100%', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '6px', padding: '0.5rem 0.75rem', color: '#fff', fontSize: '0.85rem' }}
                >
                  <option value="INR">INR (₹)</option>
                  <option value="USD">USD ($)</option>
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: 'rgba(255,255,255,0.6)', marginBottom: '0.35rem' }}>
                  BENCHMARK
                </label>
                <select
                  value={newPortBenchmark}
                  onChange={e => setNewPortBenchmark(e.target.value)}
                  style={{ width: '100%', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '6px', padding: '0.5rem 0.75rem', color: '#fff', fontSize: '0.85rem' }}
                >
                  <option value="NIFTY">NIFTY 50</option>
                  <option value="BANKNIFTY">NIFTY BANK</option>
                  <option value="FINNIFTY">NIFTY FINANCIAL</option>
                </select>
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
              <button type="button" className="button secondary" onClick={() => setCreateModalOpen(false)}>
                Cancel
              </button>
              <button type="submit" className="button primary" style={{ background: '#2563eb' }}>
                Create Portfolio
              </button>
            </div>
          </form>
        </div>
      )}

      {/* ADD HOLDING MODAL */}
      {addModalOpen && (
        <div className="overlay" style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <form
            onSubmit={handleAddHolding}
            style={{ background: '#111827', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '8px', padding: '1.5rem', width: '100%', maxWidth: '480px', color: '#fff' }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h3 style={{ margin: 0, fontSize: '1.15rem', fontWeight: 600 }}>Add Portfolio Holding</h3>
              <button type="button" onClick={() => setAddModalOpen(false)} style={{ background: 'transparent', border: 'none', color: 'rgba(255,255,255,0.5)', cursor: 'pointer' }}>
                <X size={18} />
              </button>
            </div>

            {/* Instrument Search */}
            <div style={{ marginBottom: '1rem', position: 'relative' }}>
              <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: 'rgba(255,255,255,0.6)', marginBottom: '0.35rem' }}>
                INSTRUMENT SYMBOL
              </label>
              <input
                type="text"
                required
                placeholder="Search symbol (e.g. RELIANCE, TCS, INFY)"
                value={selectedAsset ? selectedAsset.symbol : symbolQuery}
                onChange={e => {
                  setSelectedAsset(null);
                  setSymbolQuery(e.target.value);
                }}
                style={{ width: '100%', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '6px', padding: '0.5rem 0.75rem', color: '#fff', fontSize: '0.85rem' }}
              />

              {/* Search dropdown */}
              {searchResults.length > 0 && !selectedAsset && (
                <div style={{ position: 'absolute', top: '100%', left: 0, right: 0, background: '#1f2937', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '6px', marginTop: '4px', maxHeight: '180px', overflowY: 'auto', zIndex: 10 }}>
                  {searchResults.map(item => (
                    <div
                      key={item.instrument_key || item.symbol}
                      onClick={() => {
                        setSelectedAsset(item);
                        setSymbolQuery(item.symbol);
                        if (item.sector) setHoldingSector(item.sector);
                      }}
                      style={{ padding: '0.5rem 0.75rem', borderBottom: '1px solid rgba(255,255,255,0.05)', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem' }}
                    >
                      <span style={{ fontWeight: 600, color: '#60a5fa' }}>{item.symbol}</span>
                      <span style={{ color: 'rgba(255,255,255,0.5)' }}>{item.name || item.sector}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Quantity and Entry Price */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '1rem' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: 'rgba(255,255,255,0.6)', marginBottom: '0.35rem' }}>
                  QUANTITY (UNITS)
                </label>
                <input
                  type="number"
                  step="any"
                  min="0.0001"
                  required
                  placeholder="e.g. 50"
                  value={holdingQuantity}
                  onChange={e => setHoldingQuantity(e.target.value)}
                  style={{ width: '100%', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '6px', padding: '0.5rem 0.75rem', color: '#fff', fontSize: '0.85rem' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: 'rgba(255,255,255,0.6)', marginBottom: '0.35rem' }}>
                  ACQUISITION COST (₹)
                </label>
                <input
                  type="number"
                  step="any"
                  min="0.01"
                  placeholder="Optional entry price"
                  value={holdingEntryPrice}
                  onChange={e => setHoldingEntryPrice(e.target.value)}
                  style={{ width: '100%', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '6px', padding: '0.5rem 0.75rem', color: '#fff', fontSize: '0.85rem' }}
                />
              </div>
            </div>

            {/* Sector & Asset Class */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '1rem' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: 'rgba(255,255,255,0.6)', marginBottom: '0.35rem' }}>
                  ECONOMIC SECTOR
                </label>
                <input
                  type="text"
                  placeholder="e.g. Energy, IT, Financials"
                  value={holdingSector}
                  onChange={e => setHoldingSector(e.target.value)}
                  style={{ width: '100%', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '6px', padding: '0.5rem 0.75rem', color: '#fff', fontSize: '0.85rem' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: 'rgba(255,255,255,0.6)', marginBottom: '0.35rem' }}>
                  ASSET CLASS
                </label>
                <select
                  value={holdingAssetClass}
                  onChange={e => setHoldingAssetClass(e.target.value)}
                  style={{ width: '100%', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '6px', padding: '0.5rem 0.75rem', color: '#fff', fontSize: '0.85rem' }}
                >
                  <option value="equity">Equity</option>
                  <option value="etf">ETF</option>
                  <option value="bond">Bond / Debt</option>
                  <option value="cash">Cash / Liquid</option>
                </select>
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
              <button type="button" className="button secondary" onClick={() => setAddModalOpen(false)}>
                Cancel
              </button>
              <button type="submit" className="button primary" style={{ background: '#2563eb' }}>
                Save Holding
              </button>
            </div>
          </form>
        </div>
      )}

      {/* RECORD TRANSACTION MODAL */}
      {txModalOpen && (
        <div className="overlay" style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <form
            onSubmit={handleSaveTransaction}
            style={{ background: '#111827', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '8px', padding: '1.5rem', width: '100%', maxWidth: '440px', color: '#fff' }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <h3 style={{ margin: 0, fontSize: '1.15rem', fontWeight: 600 }}>Record Trade in Ledger</h3>
              <button type="button" onClick={() => setTxModalOpen(false)} style={{ background: 'transparent', border: 'none', color: 'rgba(255,255,255,0.5)', cursor: 'pointer' }}>
                <X size={18} />
              </button>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '1rem' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: 'rgba(255,255,255,0.6)', marginBottom: '0.35rem' }}>
                  TRANSACTION TYPE
                </label>
                <select
                  value={txType}
                  onChange={e => setTxType(e.target.value as any)}
                  style={{ width: '100%', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '6px', padding: '0.5rem 0.75rem', color: '#fff', fontSize: '0.85rem' }}
                >
                  <option value="BUY">BUY</option>
                  <option value="SELL">SELL</option>
                  <option value="DIVIDEND">DIVIDEND</option>
                  <option value="FEE">FEE</option>
                  <option value="DEPOSIT">DEPOSIT</option>
                  <option value="WITHDRAWAL">WITHDRAWAL</option>
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: 'rgba(255,255,255,0.6)', marginBottom: '0.35rem' }}>
                  INSTRUMENT
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. RELIANCE"
                  value={txAssetId}
                  onChange={e => setTxAssetId(e.target.value)}
                  style={{ width: '100%', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '6px', padding: '0.5rem 0.75rem', color: '#fff', fontSize: '0.85rem' }}
                />
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '1rem' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: 'rgba(255,255,255,0.6)', marginBottom: '0.35rem' }}>
                  QUANTITY
                </label>
                <input
                  type="number"
                  step="any"
                  min="0.0001"
                  required
                  placeholder="e.g. 10"
                  value={txQty}
                  onChange={e => setTxQty(e.target.value)}
                  style={{ width: '100%', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '6px', padding: '0.5rem 0.75rem', color: '#fff', fontSize: '0.85rem' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: 'rgba(255,255,255,0.6)', marginBottom: '0.35rem' }}>
                  EXECUTION PRICE (₹)
                </label>
                <input
                  type="number"
                  step="any"
                  min="0"
                  required
                  placeholder="e.g. 1210.00"
                  value={txPrice}
                  onChange={e => setTxPrice(e.target.value)}
                  style={{ width: '100%', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '6px', padding: '0.5rem 0.75rem', color: '#fff', fontSize: '0.85rem' }}
                />
              </div>
            </div>

            <div style={{ marginBottom: '1.25rem' }}>
              <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 600, color: 'rgba(255,255,255,0.6)', marginBottom: '0.35rem' }}>
                FEES &amp; TAXES (₹)
              </label>
              <input
                type="number"
                step="any"
                min="0"
                placeholder="e.g. 25.50"
                value={txFees}
                onChange={e => setTxFees(e.target.value)}
                style={{ width: '100%', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '6px', padding: '0.5rem 0.75rem', color: '#fff', fontSize: '0.85rem' }}
              />
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
              <button type="button" className="button secondary" onClick={() => setTxModalOpen(false)}>
                Cancel
              </button>
              <button type="submit" className="button primary" style={{ background: '#2563eb' }}>
                Save Transaction
              </button>
            </div>
          </form>
        </div>
      )}

      {/* CSV IMPORT MODAL */}
      {importModalOpen && (
        <div className="overlay" style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div style={{ background: '#111827', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '8px', padding: '1.5rem', width: '100%', maxWidth: '640px', color: '#fff' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <div>
                <h3 style={{ margin: 0, fontSize: '1.15rem', fontWeight: 600 }}>Import Holdings from CSV</h3>
                <p style={{ margin: '0.2rem 0 0 0', color: 'rgba(255,255,255,0.5)', fontSize: '0.8rem' }}>
                  Paste or upload comma-separated holdings with columns: <code>asset_id,quantity,entry_price,sector,asset_class</code>
                </p>
              </div>
              <button type="button" onClick={() => setImportModalOpen(false)} style={{ background: 'transparent', border: 'none', color: 'rgba(255,255,255,0.5)', cursor: 'pointer' }}>
                <X size={18} />
              </button>
            </div>

            <div style={{ marginBottom: '1rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
                <label style={{ fontSize: '0.75rem', fontWeight: 600, color: 'rgba(255,255,255,0.6)' }}>CSV CONTENT</label>
                <button
                  type="button"
                  onClick={handleDownloadCsvTemplate}
                  style={{ background: 'transparent', border: 'none', color: '#60a5fa', fontSize: '0.75rem', cursor: 'pointer', padding: 0 }}
                >
                  Download Sample CSV Template
                </button>
              </div>
              <textarea
                rows={7}
                placeholder="asset_id,quantity,entry_price,sector,asset_class&#10;RELIANCE,25,1200.50,Energy,equity&#10;TCS,15,3500.00,IT,equity"
                value={csvText}
                onChange={e => handleCsvTextChange(e.target.value)}
                style={{ width: '100%', background: 'rgba(255,255,255,0.06)', border: '1px solid rgba(255,255,255,0.15)', borderRadius: '6px', padding: '0.6rem 0.75rem', color: '#fff', fontSize: '0.8rem', fontFamily: 'monospace' }}
              />
            </div>

            {/* Validation Feedback */}
            {csvValidationErrors.length > 0 && (
              <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', padding: '0.6rem 0.8rem', borderRadius: '6px', marginBottom: '1rem', maxHeight: '100px', overflowY: 'auto', fontSize: '0.75rem', color: '#fca5a5' }}>
                <b>Validation Errors ({csvValidationErrors.length}):</b>
                <ul style={{ margin: '0.25rem 0 0 1rem', padding: 0 }}>
                  {csvValidationErrors.map((err, i) => <li key={i}>{err}</li>)}
                </ul>
              </div>
            )}

            {csvParsedRows.length > 0 && csvValidationErrors.length === 0 && (
              <div style={{ background: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.3)', padding: '0.6rem 0.8rem', borderRadius: '6px', marginBottom: '1rem', fontSize: '0.75rem', color: '#34d399' }}>
                ✓ Successfully parsed {csvParsedRows.length} valid holdings ready to commit.
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
              <button type="button" className="button secondary" onClick={() => setImportModalOpen(false)}>
                Cancel
              </button>
              <button
                type="button"
                className="button primary"
                disabled={csvParsedRows.length === 0 || csvValidationErrors.length > 0}
                onClick={handleCommitImport}
                style={{ background: '#2563eb' }}
              >
                Commit Import
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
