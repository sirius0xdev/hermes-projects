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
              className={`px-3 py-1.5 rounded-md text-[11px] font-medium border transition-all ${
                chainFilter === c
                  ? 'bg-neon-cyan/[0.08] text-neon-cyan neon-border-cyan'
                  : 'bg-bg-elevated text-text-dim border-bg-border hover:border-bg-border-light'
              }`}>
              {c}
            </button>
          ))}
        </div>
        <div className="flex gap-1 ml-auto">
          {(['ALL', 'OPEN', 'PENDING'] as const).map(s => (
            <button key={s} onClick={() => setStatusFilter(s)}
              className={`px-3 py-1.5 rounded-md text-[11px] font-medium border transition-all ${
                statusFilter === s
                  ? 'bg-neon-cyan/[0.08] text-neon-cyan neon-border-cyan'
                  : 'bg-bg-elevated text-text-dim border-bg-border hover:border-bg-border-light'
              }`}>
              {s === 'ALL' ? 'All Status' : s}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto neon-border-cyan rounded-lg">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-bg-border text-[10px] text-text-dim uppercase tracking-wider bg-bg-elevated/50">
              <th className="text-left py-2.5 px-3 font-semibold font-mono">Symbol</th>
              <th className="text-left py-2.5 px-3 font-semibold font-mono">Side</th>
              <th className="text-left py-2.5 px-3 font-semibold font-mono">Type</th>
              <th className="text-right py-2.5 px-3 font-semibold font-mono">Price</th>
              {filtered.some(o => o.stopPrice) && (
                <th className="text-right py-2.5 px-3 font-semibold font-mono">Trigger</th>
              )}
              <th className="text-right py-2.5 px-3 font-semibold font-mono">Amount</th>
              <th className="text-right py-2.5 px-3 font-semibold font-mono">Filled</th>
              <th className="text-center py-2.5 px-3 font-semibold font-mono">Chain</th>
              <th className="text-center py-2.5 px-3 font-semibold font-mono">Status</th>
              <th className="text-right py-2.5 px-3 font-semibold font-mono">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr>
                <td colSpan={10} className="text-center py-8 text-text-dim text-sm">
                  No active orders
                </td>
              </tr>
            )}
            {filtered.map(o => {
              const fillPct = o.amount > 0 ? Math.round((o.filled / o.amount) * 100) : 0;
              return (
                <tr key={o.id} className="border-b border-bg-border/50 hover:bg-bg-hover transition-colors">
                  <td className="py-2.5 px-3 font-mono font-semibold text-text">{o.symbol}</td>
                  <td className={`py-2.5 px-3 font-bold ${o.side === 'BUY' ? 'text-neon-cyan' : 'text-neon-pink'}`}>{o.side}</td>
                  <td className="py-2.5 px-3 text-text-dim">{o.type}</td>
                  <td className="py-2.5 px-3 text-right font-mono text-text">
                    {o.price > 0 ? `$${fmt(o.price)}` : '—'}
                  </td>
                  {filtered.some(x => x.stopPrice) && (
                    <td className="py-2.5 px-3 text-right font-mono text-neon-green">
                      {o.stopPrice ? `$${fmt(o.stopPrice)}` : '—'}
                    </td>
                  )}
                  <td className="py-2.5 px-3 text-right font-mono text-text">{o.amount}</td>
                  <td className="py-2.5 px-3 text-right">
                    <span className="font-mono text-text-secondary">{o.filled}</span>
                    <span className="text-text-dim ml-1 text-[11px]">({fillPct}%)</span>
                  </td>
                  <td className="py-2.5 px-3 text-center">
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                      o.chain === 'Hyperliquid' ? 'bg-neon-cyan/[0.08] text-neon-cyan' : 'bg-neon-green/[0.08] text-neon-green'
                    }`}>
                      {o.chain === 'Hyperliquid' ? 'HL' : 'SOL'}
                    </span>
                  </td>
                  <td className="py-2.5 px-3 text-center">
                    <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${
                      o.status === 'OPEN' ? 'bg-neon-cyan/[0.1] text-neon-cyan' :
                      o.status === 'PENDING' ? 'bg-neon-green/[0.08] text-neon-green' :
                      'bg-bg-elevated text-text-dim'
                    }`}>{o.status}</span>
                  </td>
                  <td className="py-2.5 px-3 text-right">
                    {(o.status === 'OPEN' || o.status === 'PENDING') && (
                      <div className="flex items-center justify-end gap-2">
                        <button onClick={() => openModify(o)}
                          className="text-neon-cyan hover:text-neon-cyan/80 text-[11px] font-medium transition-colors">
                          Modify
                        </button>
                        <button onClick={() => handleCancel(o.id)} disabled={cancelling === o.id}
                          className="text-neon-pink hover:text-neon-pink/80 text-[11px] font-medium transition-colors disabled:opacity-50">
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
          <div className="card p-6 w-full max-w-sm mx-4 shadow-2xl neon-border-cyan">
            <h3 className="text-base font-bold text-text mb-4">
              Modify Order — {modifyTarget.symbol}
            </h3>
            <div className="space-y-3">
              <div className="text-[11px] text-text-dim space-y-1 mb-3 p-3 bg-bg-elevated rounded-md neon-border-cyan">
                <div className="flex justify-between">
                  <span>Side</span><span className={modifyTarget.side === 'BUY' ? 'text-neon-cyan' : 'text-neon-pink'}>{modifyTarget.side}</span>
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
                  <span className="text-[11px] text-text-dim">Price</span>
                  <input type="number" step="any" value={modifyPrice} onChange={e => setModifyPrice(e.target.value)}
                    className="input-field mt-1.5" />
                </label>
              )}
              {modifyTarget.type === 'STOP' && (
                <label className="block">
                  <span className="text-[11px] text-text-dim">Trigger Price</span>
                  <input type="number" step="any" value={modifyStopPrice} onChange={e => setModifyStopPrice(e.target.value)}
                    className="input-field mt-1.5 focus:ring-neon-green/50 focus:border-neon-green" />
                </label>
              )}
              <label className="block">
                <span className="text-[11px] text-text-dim">Amount</span>
                <input type="number" step="any" value={modifyAmount} onChange={e => setModifyAmount(e.target.value)}
                  className="input-field mt-1.5" />
              </label>
            </div>
            <div className="flex gap-3 mt-5">
              <button onClick={() => setModifyTarget(null)}
                className="flex-1 py-2.5 rounded-md border border-bg-border text-text-secondary hover:text-text transition-colors font-medium text-sm">
                Cancel
              </button>
              <button onClick={handleModify}
                className="flex-1 py-2.5 rounded-md bg-neon-cyan text-bg-primary font-bold text-sm hover:bg-neon-cyan/90 transition-colors">
                Update
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}