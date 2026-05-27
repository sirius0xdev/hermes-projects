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
        <div className="flex flex-col items-center gap-3">
          <div className="cyber-spinner" />
          <div className="text-text-dim text-sm">Loading trade history...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Stats cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: 'Total P&L', value: `${totalPnl >= 0 ? '+' : ''}$${fmt(totalPnl)}`, cls: totalPnl >= 0 ? 'text-neon-cyan' : 'text-neon-pink' },
          { label: 'Win Rate', value: `${winRate}%`, cls: 'text-text', sub: `${winCount}W / ${filledCount - winCount}L` },
          { label: 'Total Fees', value: `$${fmt(totalFees)}`, cls: 'text-text-dim' },
          { label: 'Total Trades', value: `${filtered.length}`, cls: 'text-text', sub: `${filtered.filter(t => t.status === 'CANCELLED').length} cancelled` },
        ].map(stat => (
          <div key={stat.label} className="card-hover p-4 neon-border-cyan">
            <div className="text-[10px] text-text-dim mb-1.5 font-mono uppercase tracking-wider">{stat.label}</div>
            <div className={`text-lg font-bold font-mono tracking-tight ${stat.cls}`}>{stat.value}</div>
            {'sub' in stat && stat.sub && <div className="text-[10px] text-text-dim mt-1">{stat.sub}</div>}
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        <div className="flex gap-1">
          {(['All', 'Hyperliquid', 'Solana'] as const).map(c => (
            <button key={c} onClick={() => setChainFilter(c)}
              className={`px-3 py-1.5 rounded-md text-[11px] font-medium border transition-all ${
                chainFilter === c
                  ? 'bg-neon-cyan/[0.08] text-neon-cyan neon-border-cyan'
                  : 'bg-bg-elevated text-text-dim border-bg-border hover:border-bg-border-light'
              }`}>{c}</button>
          ))}
        </div>
        <div className="flex gap-1">
          {(['ALL', 'FILLED', 'CANCELLED'] as const).map(s => (
            <button key={s} onClick={() => setStatusFilter(s)}
              className={`px-3 py-1.5 rounded-md text-[11px] font-medium border transition-all ${
                statusFilter === s
                  ? 'bg-neon-cyan/[0.08] text-neon-cyan neon-border-cyan'
                  : 'bg-bg-elevated text-text-dim border-bg-border hover:border-bg-border-light'
              }`}>{s === 'ALL' ? 'All Status' : s}</button>
          ))}
        </div>
        <div className="flex gap-1">
          {['ALL', ...uniqueSymbols].map(s => (
            <button key={s} onClick={() => setSymbolFilter(s)}
              className={`px-3 py-1.5 rounded-md text-[11px] font-medium border transition-all ${
                symbolFilter === s
                  ? 'bg-neon-cyan/[0.08] text-neon-cyan neon-border-cyan'
                  : 'bg-bg-elevated text-text-dim border-bg-border hover:border-bg-border-light'
              }`}>{s === 'ALL' ? 'All Symbols' : s}</button>
          ))}
        </div>
        <div className="flex gap-1 ml-auto">
          {(['ALL', 'BUY', 'SELL'] as const).map(s => (
            <button key={s} onClick={() => setSideFilter(s)}
              className={`px-3 py-1.5 rounded-md text-[11px] font-medium border transition-all ${
                sideFilter === s
                  ? 'bg-neon-cyan/[0.08] text-neon-cyan neon-border-cyan'
                  : 'bg-bg-elevated text-text-dim border-bg-border hover:border-bg-border-light'
              }`}>{s === 'ALL' ? 'All Sides' : s}</button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto neon-border-cyan rounded-lg">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-bg-border text-[10px] text-text-dim uppercase tracking-wider bg-bg-elevated/50">
              <th className="text-left py-2.5 px-3 font-semibold font-mono">Date</th>
              <th className="text-left py-2.5 px-3 font-semibold font-mono">Symbol</th>
              <th className="text-left py-2.5 px-3 font-semibold font-mono">Side</th>
              <th className="text-left py-2.5 px-3 font-semibold font-mono">Type</th>
              <th className="text-right py-2.5 px-3 font-semibold font-mono">Price</th>
              <th className="text-right py-2.5 px-3 font-semibold font-mono">Amount</th>
              <th className="text-right py-2.5 px-3 font-semibold font-mono">Fee</th>
              <th className="text-right py-2.5 px-3 font-semibold font-mono">P&L</th>
              <th className="text-center py-2.5 px-3 font-semibold font-mono">Chain</th>
              <th className="text-center py-2.5 px-3 font-semibold font-mono">Status</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr>
                <td colSpan={10} className="text-center py-8 text-text-dim text-sm">No trades found</td>
              </tr>
            )}
            {filtered.map(t => (
              <tr key={t.id} className="border-b border-bg-border/50 hover:bg-bg-hover transition-colors">
                <td className="py-2.5 px-3 text-[11px] text-text-dim whitespace-nowrap font-mono">{formatTimestamp(t.timestamp)}</td>
                <td className="py-2.5 px-3 font-mono font-semibold text-text">{t.symbol}</td>
                <td className={`py-2.5 px-3 font-bold ${t.side === 'BUY' ? 'text-neon-cyan' : 'text-neon-pink'}`}>{t.side}</td>
                <td className="py-2.5 px-3 text-text-dim">{t.type}</td>
                <td className="py-2.5 px-3 text-right font-mono text-text">${fmt(t.price)}</td>
                <td className="py-2.5 px-3 text-right font-mono text-text">{t.amount}</td>
                <td className="py-2.5 px-3 text-right font-mono text-text-dim">${fmt(t.fee)}</td>
                <td className={`py-2.5 px-3 text-right font-mono font-semibold ${
                  t.pnl > 0 ? 'text-neon-cyan' : t.pnl < 0 ? 'text-neon-pink' : 'text-text-dim'
                }`}>
                  {t.pnl !== 0 ? `${t.pnl >= 0 ? '+' : ''}$${fmt(t.pnl)}` : '—'}
                </td>
                <td className="py-2.5 px-3 text-center">
                  <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                    t.chain === 'Hyperliquid' ? 'bg-neon-cyan/[0.08] text-neon-cyan' : 'bg-neon-green/[0.08] text-neon-green'
                  }`}>{t.chain === 'Hyperliquid' ? 'HL' : 'SOL'}</span>
                </td>
                <td className="py-2.5 px-3 text-center">
                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${
                    t.status === 'FILLED' ? 'bg-neon-cyan/[0.1] text-neon-cyan' :
                    t.status === 'CANCELLED' ? 'bg-bg-elevated text-text-dim' :
                    'bg-neon-green/[0.08] text-neon-green'
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