'use client';
import { useState } from 'react';
import type { TradeHistoryItem } from '@/lib/api';

function fmt(n: number, decimals = 2) {
  return n.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function formatTimestamp(ts: number): string {
  const d = new Date(ts);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' ' +
    d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

interface TradeHistoryProps {
  trades: TradeHistoryItem[];
  loading: boolean;
}

export default function TradeHistory({ trades, loading }: TradeHistoryProps) {
  const [chainFilter, setChainFilter] = useState<'All' | 'Hyperliquid' | 'Solana'>('All');
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'FILLED' | 'CANCELLED'>('ALL');
  const [symbolFilter, setSymbolFilter] = useState<string>('ALL');
  const [sideFilter, setSideFilter] = useState<'ALL' | 'BUY' | 'SELL'>('ALL');

  const uniqueSymbols = Array.from(new Set(trades.map(t => t.symbol)));

  const filtered = trades.filter(t => {
    if (chainFilter !== 'All' && t.chain !== chainFilter) return false;
    if (statusFilter !== 'ALL' && t.status !== statusFilter) return false;
    if (symbolFilter !== 'ALL' && t.symbol !== symbolFilter) return false;
    if (sideFilter !== 'ALL' && t.side !== sideFilter) return false;
    return true;
  });

  // Calculate stats
  const totalPnl = filtered
    .filter(t => t.status === 'FILLED')
    .reduce((sum, t) => sum + t.pnl, 0);
  const totalFees = filtered
    .filter(t => t.status === 'FILLED')
    .reduce((sum, t) => sum + t.fee, 0);
  const winCount = filtered.filter(t => t.status === 'FILLED' && t.pnl > 0).length;
  const filledCount = filtered.filter(t => t.status === 'FILLED').length;
  const winRate = filledCount > 0 ? ((winCount / filledCount) * 100).toFixed(1) : '0';

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-text-muted animate-pulse">Loading trade history...</div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Stats cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="bg-bg-card rounded-xl border border-border p-3">
          <div className="text-xs text-text-secondary mb-1">Total P&L</div>
          <div className={`text-lg font-bold font-mono ${totalPnl >= 0 ? 'text-up' : 'text-down'}`}>
            {totalPnl >= 0 ? '+' : ''}${fmt(totalPnl)}
          </div>
        </div>
        <div className="bg-bg-card rounded-xl border border-border p-3">
          <div className="text-xs text-text-secondary mb-1">Win Rate</div>
          <div className="text-lg font-bold font-mono text-text-primary">{winRate}%</div>
          <div className="text-xs text-text-muted">{winCount}W / {filledCount - winCount}L</div>
        </div>
        <div className="bg-bg-card rounded-xl border border-border p-3">
          <div className="text-xs text-text-secondary mb-1">Total Fees</div>
          <div className="text-lg font-bold font-mono text-text-muted">${fmt(totalFees)}</div>
        </div>
        <div className="bg-bg-card rounded-xl border border-border p-3">
          <div className="text-xs text-text-secondary mb-1">Total Trades</div>
          <div className="text-lg font-bold font-mono text-text-primary">{filtered.length}</div>
          <div className="text-xs text-text-muted">{filtered.filter(t => t.status === 'CANCELLED').length} cancelled</div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        <div className="flex gap-1">
          {(['All', 'Hyperliquid', 'Solana'] as const).map(c => (
            <button key={c} onClick={() => setChainFilter(c)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${chainFilter === c
                ? 'bg-accent/20 text-accent border-accent'
                : 'bg-bg-secondary text-text-muted border-border hover:text-text-secondary'}`}>
              {c}
            </button>
          ))}
        </div>
        <div className="flex gap-1">
          {(['ALL', 'FILLED', 'CANCELLED'] as const).map(s => (
            <button key={s} onClick={() => setStatusFilter(s)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${statusFilter === s
                ? 'bg-accent/20 text-accent border-accent'
                : 'bg-bg-secondary text-text-muted border-border hover:text-text-secondary'}`}>
              {s === 'ALL' ? 'All Status' : s}
            </button>
          ))}
        </div>
        <div className="flex gap-1">
          {['ALL', ...uniqueSymbols].map(s => (
            <button key={s} onClick={() => setSymbolFilter(s)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${symbolFilter === s
                ? 'bg-accent/20 text-accent border-accent'
                : 'bg-bg-secondary text-text-muted border-border hover:text-text-secondary'}`}>
              {s === 'ALL' ? 'All Symbols' : s}
            </button>
          ))}
        </div>
        <div className="flex gap-1 ml-auto">
          {(['ALL', 'BUY', 'SELL'] as const).map(s => (
            <button key={s} onClick={() => setSideFilter(s)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${sideFilter === s ? 'bg-accent/20 text-accent border-accent' : 'bg-bg-secondary text-text-muted border-border hover:text-text-secondary'}`}>
              {s === 'ALL' ? 'All Sides' : s}
            </button>
          ))}
        </div>
      </div>

      {/* Responsive table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left py-2 px-3 text-xs font-semibold text-text-muted uppercase tracking-wider">Date</th>
              <th className="text-left py-2 px-3 text-xs font-semibold text-text-muted uppercase tracking-wider">Symbol</th>
              <th className="text-left py-2 px-3 text-xs font-semibold text-text-muted uppercase tracking-wider">Side</th>
              <th className="text-left py-2 px-3 text-xs font-semibold text-text-muted uppercase tracking-wider">Type</th>
              <th className="text-right py-2 px-3 text-xs font-semibold text-text-muted uppercase tracking-wider">Price</th>
              <th className="text-right py-2 px-3 text-xs font-semibold text-text-muted uppercase tracking-wider">Amount</th>
              <th className="text-right py-2 px-3 text-xs font-semibold text-text-muted uppercase tracking-wider">Fee</th>
              <th className="text-right py-2 px-3 text-xs font-semibold text-text-muted uppercase tracking-wider">P&L</th>
              <th className="text-center py-2 px-3 text-xs font-semibold text-text-muted uppercase tracking-wider">Chain</th>
              <th className="text-center py-2 px-3 text-xs font-semibold text-text-muted uppercase tracking-wider">Status</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr>
                <td colSpan={10} className="text-center py-8 text-text-muted">
                  No trades found
                </td>
              </tr>
            )}
            {filtered.map(t => (
              <tr key={t.id} className="border-b border-border/50 hover:bg-bg-card/50 transition-colors">
                <td className="py-2.5 px-3 text-xs text-text-secondary whitespace-nowrap">
                  {formatTimestamp(t.timestamp)}
                </td>
                <td className="py-2.5 px-3 font-mono font-medium text-text-primary">{t.symbol}</td>
                <td className={`py-2.5 px-3 font-semibold ${t.side === 'BUY' ? 'text-up' : 'text-down'}`}>{t.side}</td>
                <td className="py-2.5 px-3 text-text-secondary">{t.type}</td>
                <td className="py-2.5 px-3 text-right font-mono text-text-primary">${fmt(t.price)}</td>
                <td className="py-2.5 px-3 text-right font-mono text-text-primary">{t.amount}</td>
                <td className="py-2.5 px-3 text-right font-mono text-text-muted">${fmt(t.fee)}</td>
                <td className={`py-2.5 px-3 text-right font-mono font-semibold ${
                  t.pnl > 0 ? 'text-up' : t.pnl < 0 ? 'text-down' : 'text-text-muted'
                }`}>
                  {t.pnl !== 0 ? `${t.pnl >= 0 ? '+' : ''}$${fmt(t.pnl)}` : '—'}
                </td>
                <td className="py-2.5 px-3 text-center text-xs">
                  <span className={`px-1.5 py-0.5 rounded ${t.chain === 'Hyperliquid' ? 'bg-accent/10 text-accent' : 'bg-purple-500/10 text-purple-400'}`}>
                    {t.chain === 'Hyperliquid' ? '⬡' : '◎'}
                  </span>
                </td>
                <td className="py-2.5 px-3 text-center">
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                    t.status === 'FILLED' ? 'bg-green-500/20 text-green-400' :
                    t.status === 'CANCELLED' ? 'bg-text-muted/20 text-text-muted' :
                    'bg-amber-500/20 text-amber-400'
                  }`}>{t.status === 'FILLED' ? 'Filled' : t.status === 'CANCELLED' ? 'Cancelled' : 'Partial'}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
