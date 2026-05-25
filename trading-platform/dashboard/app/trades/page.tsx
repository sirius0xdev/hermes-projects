'use client';
import { useState, useEffect, useCallback } from 'react';
import AppShell from '@/components/layout/AppShell';
import OrderForm from '@/components/trading/OrderForm';
import ActiveOrdersList from '@/components/trading/ActiveOrdersList';
import TradeHistory from '@/components/trading/TradeHistory';
import { fetchTickers, fetchTradeOrders, fetchTradeHistory } from '@/lib/api';
import type { TickerPrice, Order, TradeHistoryItem } from '@/lib/api';
import {
  ArrowRightLeft,
  RefreshCw,
  Activity,
} from 'lucide-react';

function fmt(n: number) { return n.toLocaleString(undefined, { minimumFractionDigits: 2 }); }

type Tab = 'order' | 'active' | 'history';

export default function TradesPage() {
  const [tickers, setTickers] = useState<TickerPrice[]>([]);
  const [symbol, setSymbol] = useState('BTC-PERP');
  const [activeTab, setActiveTab] = useState<Tab>('order');
  const [orders, setOrders] = useState<Order[]>([]);
  const [trades, setTrades] = useState<TradeHistoryItem[]>([]);
  const [ordersLoading, setOrdersLoading] = useState(true);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [autoRefresh, setAutoRefresh] = useState(true);

  useEffect(() => {
    fetchTickers().then(t => setTickers(t));
  }, []);

  const loadOrders = useCallback(async () => {
    setOrdersLoading(true);
    const o = await fetchTradeOrders();
    setOrders(o);
    setOrdersLoading(false);
  }, []);

  const loadHistory = useCallback(async () => {
    setHistoryLoading(true);
    const h = await fetchTradeHistory();
    setTrades(h);
    setHistoryLoading(false);
  }, []);

  useEffect(() => {
    loadOrders();
    loadHistory();
  }, [loadOrders, loadHistory]);

  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(() => {
      loadOrders();
      loadHistory();
    }, 30000);
    return () => clearInterval(interval);
  }, [autoRefresh, loadOrders, loadHistory]);

  const activeOrders = orders.filter(o => o.status === 'OPEN' || o.status === 'PENDING');
  const selected = tickers.find(t => t.symbol === symbol);

  return (
    <AppShell>
      <div className="space-y-5">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-accent/10 flex items-center justify-center">
              <ArrowRightLeft className="w-4 h-4 text-accent" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-text">Trade Execution</h2>
              <p className="text-[11px] text-text-dim mt-0.5">Place, manage, and track your orders</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setAutoRefresh(!autoRefresh)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${
                autoRefresh
                  ? 'bg-accent/10 text-accent border-accent/30'
                  : 'bg-bg-card text-text-dim border-bg-border'
              }`}
            >
              {autoRefresh ? '● Auto-refresh' : '○ Auto-refresh off'}
            </button>
            <button
              onClick={() => { loadOrders(); loadHistory(); }}
              className="p-1.5 rounded-lg bg-bg-card border border-bg-border text-text-dim hover:text-text-secondary transition-colors"
              aria-label="Refresh"
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Symbol selector */}
        <div className="flex flex-wrap gap-2">
          {tickers.map(t => (
            <button
              key={t.symbol}
              onClick={() => setSymbol(t.symbol)}
              className={`px-3.5 py-2 rounded-lg border text-sm font-medium transition-all ${
                symbol === t.symbol
                  ? 'bg-accent/10 border-accent/30 text-accent'
                  : 'bg-bg-card border-bg-border text-text-secondary hover:text-text hover:border-bg-border_light'
              }`}
            >
              {t.symbol}
            </button>
          ))}
        </div>

        {/* Selected ticker info */}
        {selected && (
          <div className="bg-bg-card rounded-xl border border-bg-border p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-4">
              <span className="text-lg font-bold text-text">{selected.symbol}</span>
              <span className={`text-lg font-mono font-bold ${selected.change24h >= 0 ? 'text-long' : 'text-short'}`}>
                ${fmt(selected.price)}
              </span>
              <span className={`text-xs font-semibold px-2 py-0.5 rounded ${
                selected.change24h >= 0 ? 'bg-long-muted text-long' : 'bg-short-muted text-short'
              }`}>
                {selected.change24h >= 0 ? '+' : ''}{selected.change24h.toFixed(2)}%
              </span>
            </div>
            <div className="flex items-center gap-4 text-xs text-text-dim">
              <span>24h Range: ${fmt(selected.low24h)} — ${fmt(selected.high24h)}</span>
              <span>Vol: ${(selected.volume24h / 1e6).toFixed(0)}M</span>
            </div>
          </div>
        )}

        {/* Tab navigation */}
        <div className="flex gap-0 bg-bg-card rounded-xl border border-bg-border p-1">
          {([
            { key: 'order' as Tab, label: 'Place Order', icon: Activity },
            { key: 'active' as Tab, label: `Active (${activeOrders.length})`, icon: null },
            { key: 'history' as Tab, label: 'History', icon: null },
          ]).map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex-1 py-2.5 px-4 rounded-lg text-sm font-medium transition-all ${
                activeTab === tab.key
                  ? 'bg-bg-surface text-accent shadow-sm'
                  : 'text-text-dim hover:text-text-secondary'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        {activeTab === 'order' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Order form */}
            <div className="card-hover p-5">
              <h3 className="text-sm font-semibold text-text mb-4">New Order</h3>
              <OrderForm symbol={symbol} onPlaced={() => { loadOrders(); loadHistory(); }} />
            </div>

            {/* Active orders */}
            <div className="card-hover p-4">
              <h3 className="text-sm font-semibold text-text mb-3">Active Orders</h3>
              {ordersLoading ? (
                <p className="text-text-dim text-sm text-center py-8">Loading...</p>
              ) : (
                <div className="space-y-1.5 max-h-80 overflow-y-auto">
                  {orders
                    .filter(o => o.symbol === symbol && (o.status === 'OPEN' || o.status === 'PENDING'))
                    .slice(0, 8)
                    .map(o => (
                      <div key={o.id} className="flex justify-between items-center text-xs p-2.5 rounded-lg bg-bg-elevated border border-bg-border/50">
                        <div>
                          <span className={`font-semibold ${o.side === 'BUY' ? 'text-long' : 'text-short'}`}>{o.side}</span>
                          <span className="text-text-dim ml-1">{o.type}</span>
                        </div>
                        <span className="font-mono text-text-secondary">${fmt(o.price)}</span>
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                          o.chain === 'Hyperliquid' ? 'bg-accent/10 text-accent' : 'bg-warm-muted text-warm'
                        }`}>
                          {o.chain === 'Hyperliquid' ? 'HL' : 'SOL'}
                        </span>
                      </div>
                    ))}
                  {orders.filter(o => o.symbol === symbol && (o.status === 'OPEN' || o.status === 'PENDING')).length === 0 && (
                    <p className="text-text-dim text-sm text-center py-8">No active orders for {symbol}</p>
                  )}
                </div>
              )}
            </div>

            {/* Recent fills */}
            <div className="card-hover p-4">
              <h3 className="text-sm font-semibold text-text mb-3">Recent Fills</h3>
              <div className="space-y-2">
                {orders
                  .filter(o => o.symbol === symbol && o.status === 'FILLED')
                  .slice(0, 5)
                  .map(o => (
                    <div key={o.id} className="p-3 rounded-lg bg-bg-elevated border border-bg-border">
                      <div className="flex justify-between items-center mb-1">
                        <span className={`text-sm font-semibold ${o.side === 'BUY' ? 'text-long' : 'text-short'}`}>{o.side} {o.type}</span>
                        <span className="text-[10px] text-text-dim">{new Date(o.timestamp).toLocaleDateString()}</span>
                      </div>
                      <div className="flex justify-between text-xs text-text-secondary">
                        <span className="font-mono">${fmt(o.price)}</span>
                        <span className="font-mono">Qty: {o.amount}</span>
                      </div>
                    </div>
                  ))}
                {orders.filter(o => o.symbol === symbol && o.status === 'FILLED').length === 0 && (
                  <p className="text-sm text-text-dim text-center py-8">No filled orders for {symbol}</p>
                )}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'active' && (
          <div className="card-hover p-5">
            <h3 className="text-sm font-semibold text-text mb-4">Active Orders</h3>
            {ordersLoading ? (
              <p className="text-text-dim text-sm text-center py-8">Loading orders...</p>
            ) : (
              <ActiveOrdersList orders={activeOrders} onRefresh={loadOrders} />
            )}
          </div>
        )}

        {activeTab === 'history' && (
          <div className="card-hover p-5">
            <h3 className="text-sm font-semibold text-text mb-4">Trade History</h3>
            <TradeHistory trades={trades} loading={historyLoading} />
          </div>
        )}
      </div>
    </AppShell>
  );
}
