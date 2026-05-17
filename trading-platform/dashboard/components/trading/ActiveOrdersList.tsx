'use client';
import { useState } from 'react';
import { cancelOrder, modifyOrder } from '@/lib/api';
import type { Order } from '@/lib/api';

function fmt(n: number, decimals = 2) {
  return n.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function timeAgo(ts: number): string {
  const diff = Date.now() - ts;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

interface ActiveOrdersListProps {
  orders: Order[];
  onRefresh: () => void;
}

export default function ActiveOrdersList({ orders, onRefresh }: ActiveOrdersListProps) {
  const [cancelling, setCancelling] = useState<string | null>(null);
  const [modifyTarget, setModifyTarget] = useState<Order | null>(null);
  const [modifyPrice, setModifyPrice] = useState('');
  const [modifyAmount, setModifyAmount] = useState('');
  const [modifyStopPrice, setModifyStopPrice] = useState('');
  const [chainFilter, setChainFilter] = useState<'All' | 'Hyperliquid' | 'Solana'>('All');
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'OPEN' | 'PENDING'>('ALL');

  const handleCancel = async (id: string) => {
    setCancelling(id);
    await cancelOrder(id);
    setCancelling(null);
    onRefresh();
  };

  const openModify = (order: Order) => {
    setModifyTarget(order);
    setModifyPrice(order.price > 0 ? String(order.price) : '');
    setModifyAmount(String(order.amount));
    setModifyStopPrice(order.stopPrice ? String(order.stopPrice) : '');
  };

  const handleModify = async () => {
    if (!modifyTarget) return;
    const updates: { price?: number; amount?: number; stopPrice?: number } = {};
    if (modifyPrice) updates.price = parseFloat(modifyPrice);
    if (modifyAmount) updates.amount = parseFloat(modifyAmount);
    if (modifyStopPrice) updates.stopPrice = parseFloat(modifyStopPrice);
    await modifyOrder(modifyTarget.id, updates);
    setModifyTarget(null);
    onRefresh();
  };

  const filtered = orders.filter(o => {
    if (chainFilter !== 'All' && o.chain !== chainFilter) return false;
    if (statusFilter !== 'ALL' && o.status !== statusFilter) return false;
    return true;
  });

  return (
    <div className="space-y-4">
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
        <div className="flex gap-1 ml-auto">
          {(['ALL', 'OPEN', 'PENDING'] as const).map(s => (
            <button key={s} onClick={() => setStatusFilter(s)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${statusFilter === s
                ? 'bg-accent/20 text-accent border-accent'
                : 'bg-bg-secondary text-text-muted border-border hover:text-text-secondary'}`}>
              {s === 'ALL' ? 'All Status' : s}
            </button>
          ))}
        </div>
      </div>

      {/* Responsive table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border">
              <th className="text-left py-2 px-3 text-xs font-semibold text-text-muted uppercase tracking-wider">Symbol</th>
              <th className="text-left py-2 px-3 text-xs font-semibold text-text-muted uppercase tracking-wider">Side</th>
              <th className="text-left py-2 px-3 text-xs font-semibold text-text-muted uppercase tracking-wider">Type</th>
              <th className="text-right py-2 px-3 text-xs font-semibold text-text-muted uppercase tracking-wider">Price</th>
              {filtered.some(o => o.stopPrice) && (
                <th className="text-right py-2 px-3 text-xs font-semibold text-text-muted uppercase tracking-wider">Trigger</th>
              )}
              <th className="text-right py-2 px-3 text-xs font-semibold text-text-muted uppercase tracking-wider">Amount</th>
              <th className="text-right py-2 px-3 text-xs font-semibold text-text-muted uppercase tracking-wider">Filled</th>
              <th className="text-center py-2 px-3 text-xs font-semibold text-text-muted uppercase tracking-wider">Chain</th>
              <th className="text-center py-2 px-3 text-xs font-semibold text-text-muted uppercase tracking-wider">Status</th>
              <th className="text-right py-2 px-3 text-xs font-semibold text-text-muted uppercase tracking-wider">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr>
                <td colSpan={9} className="text-center py-8 text-text-muted">
                  No active orders
                </td>
              </tr>
            )}
            {filtered.map(o => {
              const fillPct = o.amount > 0 ? Math.round((o.filled / o.amount) * 100) : 0;
              return (
                <tr key={o.id} className="border-b border-border/50 hover:bg-bg-card/50 transition-colors">
                  <td className="py-2.5 px-3 font-mono font-medium text-text-primary">{o.symbol}</td>
                  <td className={`py-2.5 px-3 font-semibold ${o.side === 'BUY' ? 'text-up' : 'text-down'}`}>{o.side}</td>
                  <td className="py-2.5 px-3 text-text-secondary">{o.type}</td>
                  <td className="py-2.5 px-3 text-right font-mono text-text-primary">
                    {o.price > 0 ? `$${fmt(o.price)}` : '—'}
                  </td>
                  {filtered.some(x => x.stopPrice) && (
                    <td className="py-2.5 px-3 text-right font-mono text-amber-400">
                      {o.stopPrice ? `$${fmt(o.stopPrice)}` : '—'}
                    </td>
                  )}
                  <td className="py-2.5 px-3 text-right font-mono text-text-primary">{o.amount}</td>
                  <td className="py-2.5 px-3 text-right">
                    <span className="font-mono text-text-secondary">{o.filled}</span>
                    <span className="text-text-muted ml-1 text-xs">({fillPct}%)</span>
                  </td>
                  <td className="py-2.5 px-3 text-center text-xs">
                    <span className={`px-1.5 py-0.5 rounded ${o.chain === 'Hyperliquid' ? 'bg-accent/10 text-accent' : 'bg-purple-500/10 text-purple-400'}`}>
                      {o.chain === 'Hyperliquid' ? '⬡' : '◎'}
                    </span>
                  </td>
                  <td className="py-2.5 px-3 text-center">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                      o.status === 'OPEN' ? 'bg-green-500/20 text-green-400' :
                      o.status === 'PENDING' ? 'bg-amber-500/20 text-amber-400' :
                      'bg-text-muted/20 text-text-muted'
                    }`}>{o.status}</span>
                  </td>
                  <td className="py-2.5 px-3 text-right">
                    {(o.status === 'OPEN' || o.status === 'PENDING') && (
                      <div className="flex items-center justify-end gap-2">
                        <button onClick={() => openModify(o)}
                          className="text-accent hover:text-accent/80 text-xs font-medium transition-colors">
                          Modify
                        </button>
                        <button onClick={() => handleCancel(o.id)} disabled={cancelling === o.id}
                          className="text-down hover:text-down/80 text-xs font-medium transition-colors disabled:opacity-50">
                          {cancelling === o.id ? '...' : 'Cancel'}
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Modify modal */}
      {modifyTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" role="dialog" aria-modal="true">
          <div className="bg-bg-card border border-border rounded-2xl p-6 w-full max-w-sm mx-4 shadow-2xl">
            <h3 className="text-lg font-bold text-text-primary mb-4">
              Modify Order — {modifyTarget.symbol}
            </h3>
            <div className="space-y-3">
              <div className="text-xs text-text-secondary space-y-1 mb-3 p-2 bg-bg-primary rounded-lg">
                <div className="flex justify-between">
                  <span>Side</span><span className={modifyTarget.side === 'BUY' ? 'text-up' : 'text-down'}>{modifyTarget.side}</span>
                </div>
                <div className="flex justify-between">
                  <span>Type</span><span>{modifyTarget.type}</span>
                </div>
                <div className="flex justify-between">
                  <span>Chain</span><span>{modifyTarget.chain}</span>
                </div>
              </div>

              {modifyTarget.type !== 'MARKET' && (
                <label className="block">
                  <span className="text-xs text-text-secondary">Price</span>
                  <input type="number" step="any" value={modifyPrice} onChange={e => setModifyPrice(e.target.value)}
                    className="w-full mt-1 px-3 py-2 bg-bg-tertiary border border-border rounded-lg text-sm font-mono text-text-primary focus:outline-none focus:border-accent" />
                </label>
              )}
              {modifyTarget.type === 'STOP' && (
                <label className="block">
                  <span className="text-xs text-text-secondary">Trigger Price</span>
                  <input type="number" step="any" value={modifyStopPrice} onChange={e => setModifyStopPrice(e.target.value)}
                    className="w-full mt-1 px-3 py-2 bg-bg-tertiary border border-border rounded-lg text-sm font-mono text-text-primary focus:outline-none focus:border-amber-500" />
                </label>
              )}
              <label className="block">
                <span className="text-xs text-text-secondary">Amount</span>
                <input type="number" step="any" value={modifyAmount} onChange={e => setModifyAmount(e.target.value)}
                  className="w-full mt-1 px-3 py-2 bg-bg-tertiary border border-border rounded-lg text-sm font-mono text-text-primary focus:outline-none focus:border-accent" />
              </label>
            </div>
            <div className="flex gap-3 mt-6">
              <button onClick={() => setModifyTarget(null)}
                className="flex-1 py-2.5 rounded-lg border border-border text-text-secondary hover:text-text-primary transition-colors font-medium">
                Cancel
              </button>
              <button onClick={handleModify}
                className="flex-1 py-2.5 rounded-lg bg-accent text-bg-primary font-semibold hover:bg-accent/90 transition-colors">
                Update
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
