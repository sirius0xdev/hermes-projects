'use client';
import { useState, useEffect, useRef, useCallback } from 'react';
import AppShell from '@/components/layout/AppShell';
import OpportunityCard, { type Opportunity } from '@/components/opportunities/OpportunityCard';
import { RefreshCw, Zap, Bell, Filter } from 'lucide-react';
import { DATA_BASE } from '@/lib/api';

type FilterType = 'all' | 'yield_spread' | 'funding_arbitrage' | 'price_differential' | 'delta_neutral_arb';

export default function OpportunitiesPage() {
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<FilterType>('all');
  const [sseConnected, setSseConnected] = useState(false);
  const [newCount, setNewCount] = useState(0);
  const eventSourceRef = useRef<EventSource | null>(null);

  // Load initial opportunities
  const loadOpportunities = useCallback(async () => {
    try {
      const res = await fetch(`${DATA_BASE}/api/v1/opportunities`);
      if (res.ok) {
        const data = await res.json();
        setOpportunities(data);
      }
    } catch {
      // Will use SSE to populate
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    loadOpportunities();
  }, [loadOpportunities]);

  // SSE connection
  useEffect(() => {
    const connectSSE = () => {
      try {
        const es = new EventSource(`${DATA_BASE}/api/v1/opportunities/stream`);
        eventSourceRef.current = es;

        es.onopen = () => {
          setSseConnected(true);
        };

        es.addEventListener('opportunity', (event) => {
          try {
            const opp: Opportunity = JSON.parse(event.data);
            setOpportunities(prev => {
              if (prev.find(o => o.opportunity_id === opp.opportunity_id)) {
                return prev;
              }
              setNewCount(c => c + 1);
              return [opp, ...prev].slice(0, 100);
            });
          } catch {
            // Ignore parse errors
          }
        });

        es.onerror = () => {
          setSseConnected(false);
          es.close();
          // Reconnect after 5 seconds
          setTimeout(connectSSE, 5000);
        };
      } catch {
        setSseConnected(false);
      }
    };

    connectSSE();

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  // Filter opportunities
  const filtered = filter === 'all'
    ? opportunities
    : opportunities.filter(o => o.opportunity_type === filter);

  const filterOptions: { key: FilterType; label: string; count: number }[] = [
    { key: 'all', label: 'All', count: opportunities.length },
    { key: 'yield_spread', label: 'Yield Spread', count: opportunities.filter(o => o.opportunity_type === 'yield_spread').length },
    { key: 'funding_arbitrage', label: 'Funding Arb', count: opportunities.filter(o => o.opportunity_type === 'funding_arbitrage').length },
    { key: 'price_differential', label: 'Price Diff', count: opportunities.filter(o => o.opportunity_type === 'price_differential').length },
  ];

  return (
    <AppShell>
      <div className="space-y-5">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-md bg-neon-cyan/[0.08] flex items-center justify-center neon-border-cyan">
              <Zap className="w-4 h-4 text-neon-cyan" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-text tracking-tight">Opportunity Scanner</h2>
              <p className="text-[10px] text-text-dim mt-0.5 font-mono">Cross-chain arbitrage and yield spread detection</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {/* SSE status */}
            <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium border ${
              sseConnected
                ? 'bg-neon-green/[0.06] text-neon-green border-neon-green/20'
                : 'bg-bg-card text-text-dim border-bg-border'
            }`}>
              <Bell className="w-3.5 h-3.5" />
              {sseConnected ? 'Live' : 'Connecting...'}
              {newCount > 0 && (
                <span className="ml-1 px-1.5 py-0.5 rounded-full bg-neon-cyan text-bg-secondary text-[10px] font-bold">
                  {newCount}
                </span>
              )}
            </div>
            <button
              onClick={() => { loadOpportunities(); setNewCount(0); }}
              className="p-1.5 rounded-md bg-bg-card border border-bg-border text-text-dim hover:text-text-secondary transition-colors"
              aria-label="Refresh"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <div className="bg-bg-card rounded-md border border-bg-border p-3">
            <div className="text-[10px] text-text-dim font-mono uppercase tracking-wider">Active</div>
            <div className="text-xl font-bold text-text font-mono">{opportunities.length}</div>
          </div>
          <div className="bg-bg-card rounded-md border border-bg-border p-3">
            <div className="text-[10px] text-text-dim font-mono uppercase tracking-wider">Best APR</div>
            <div className="text-xl font-bold text-neon-cyan font-mono">
              {opportunities.length > 0
                ? `${Math.max(...opportunities.map(o => o.estimated_apr)).toFixed(1)}%`
                : '—'}
            </div>
          </div>
          <div className="bg-bg-card rounded-md border border-bg-border p-3">
            <div className="text-[10px] text-text-dim font-mono uppercase tracking-wider">Low Risk</div>
            <div className="text-xl font-bold text-neon-green font-mono">
              {opportunities.filter(o => o.risk_level === 'low').length}
            </div>
          </div>
          <div className="bg-bg-card rounded-md border border-bg-border p-3">
            <div className="text-[10px] text-text-dim font-mono uppercase tracking-wider">Assets</div>
            <div className="text-xl font-bold text-text font-mono">
              {new Set(opportunities.map(o => o.symbol)).size}
            </div>
          </div>
        </div>

        {/* Filters */}
        <div className="flex items-center gap-1 bg-bg-card rounded-md border border-bg-border p-1 overflow-x-auto">
          <Filter className="w-3.5 h-3.5 text-text-dim mr-1 shrink-0" />
          {filterOptions.map(f => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all duration-150 whitespace-nowrap ${
                filter === f.key
                  ? 'bg-neon-cyan/[0.08] text-neon-cyan'
                  : 'text-text-dim hover:text-text-secondary'
              }`}
            >
              {f.label}
              <span className="ml-1 text-[10px] opacity-60">({f.count})</span>
            </button>
          ))}
        </div>

        {/* Opportunities grid */}
        {loading ? (
          <div className="text-center py-16">
            <div className="inline-flex items-center gap-2 text-text-dim text-sm">
              <RefreshCw className="w-4 h-4 animate-spin" />
              Loading opportunities...
            </div>
          </div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-16 bg-bg-card rounded-lg border border-bg-border">
            <Zap className="w-8 h-8 text-text-dim mx-auto mb-3 opacity-50" />
            <p className="text-text-dim text-sm">No opportunities detected</p>
            <p className="text-text-dim text-xs mt-1">
              {sseConnected ? 'Scanner is running — alerts will appear here' : 'Waiting for scanner data...'}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
            {filtered.map(opp => (
              <OpportunityCard key={opp.opportunity_id} opportunity={opp} />
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
