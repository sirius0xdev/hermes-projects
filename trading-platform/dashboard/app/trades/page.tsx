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
            <div className="w-8 h-8 rounded-md bg-neon-cyan/[0.08] flex items-center justify-center neon-border-cyan">
              <ArrowRightLeft className="w-4 h-4 text-neon-cyan" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-text tracking-tight">Trade Execution</h2>
              <p className="text-[10px] text-text-dim mt-0.5 font-mono">Place, manage, and track your orders</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setAutoRefresh(!autoRefresh)}
              className={`px-3 py-1.5 rounded-md text-xs font-medium border transition-all ${
                autoRefresh
                  ? 'bg-neon-cyan/[0.08] text-neon-cyan neon-border-cyan'
                  : 'bg-bg-card text-text-dim border-bg-border'
              }`}
            >
              {autoRefresh ? '● Auto-refresh' : '○ Auto-refresh off'}
            </button>
            <button
              onClick={() => { loadOrders(); loadHistory(); }}
              className="p-1.5 rounded-md bg-bg-card border border-bg-border text-text-dim hover:text-text-secondary transition-colors"
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
              className={`px-3 py-1.5 rounded-md border text-sm font-medium transition-all duration-150 ${
                symbol === t.symbol
                  ? 'bg-neon-cyan/[0.08] neon-border-cyan text-neon-cyan'
                  : 'bg-bg-card border-bg-border text-text-secondary hover:text-text hover:border-bg-border-light'
              }`}
            >
              {t.symbol}
            </button>
          ))}
        </div>

        {/* Selected ticker info */}
        {selected && (
          <div className="bg-bg-card rounded-md neon-border-cyan p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-4">
              <span className="text-lg font-bold text-text tracking-tight font-mono">{selected.symbol}</span>
              <span className={`text-lg font-mono font-bold ${selected.change24h >= 0 ? 'text-neon-cyan' : 'text-neon-pink'}`}>
                ${fmt(selected.price)}
              </span>
              <span className={`text-xs font-semibold px-2 py-0.5 rounded ${
                selected.change24h >= 0 ? 'bg-neon-cyan/[0.08] text-neon-cyan' : 'bg-neon-pink/[0.08] text-neon-pink'
              }`}>
                {selected.change24h >= 0 ? '+' : ''}{selected.change24h.toFixed(2)}%
              </span>
            </div>
            <div className="flex items-center gap-4 text-xs text-text-dim font-mono">
              <span>24h Range: ${fmt(selected.low24h)} — ${fmt(selected.high24h)}</span>
              <span>Vol: ${(selected.volume24h / 1e6).toFixed(0)}M</span>
            </div>
          </div>
        )}

        {/* Tab navigation */}
        <div className="flex gap-0 bg-bg-card rounded-md neon-border-cyan p-1">
          {([
            { key: 'order' as Tab, label: 'Place Order', icon: Activity },
            { key: 'active' as Tab, label: `Active (${activeOrders.length})`, icon: null },
            { key: 'history' as Tab, label: 'History', icon: null },
          ]).map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex-1 py-2.5 px-4 rounded-md text-sm font-medium transition-all duration-150 ${
                activeTab === tab.key
                  ? 'bg-bg-elevated text-neon-cyan shadow-sm'
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
              <h3 className="text-xs font-semibold text-text mb-4 font-mono uppercase tracking-wider">New Order</h3>
              <OrderForm symbol={symbol} onPlaced={() => { loadOrders(); loadHistory(); }} />
            </div>

            {/* Active orders */}
            <div className="card-hover p-4">
              <h3 className="text-xs font-semibold text-text mb-3 font-mono uppercase tracking-wider">Active Orders</h3>
              {ordersLoading ? (
                <p className="text-text-dim text-sm text-center py-8">Loading...</p>
              ) : (
                <div className="space-y-1.5 max-h-80 overflow-y-auto">
                  {orders
                    .filter(o => o.symbol === symbol && (o.status === 'OPEN' || o.status === 'PENDING'))
                    .slice(0, 8)
                    .map(o => (
                      <div key={o.id} className="flex justify-between items-center text-xs p-2.5 rounded-md bg-bg-elevated neon-border-cyan">
                        <div>
                          <span className={`font-semibold ${o.side === 'BUY' ? 'text-neon-cyan' : 'text-neon-pink'}`}>{o.side}</span>
                          <span className="text-text-dim ml-1">{o.type}</span>
                        </div>
                        <span className="font-mono text-text-secondary">${fmt(o.price)}</span>
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                          o.chain === 'Hyperliquid' ? 'bg-neon-cyan/[0.08] text-neon-cyan' : 'bg-neon-green/[0.08] text-neon-green'
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
              <h3 className="text-xs font-semibold text-text mb-3 font-mono uppercase tracking-wider">Recent Fills</h3>
              <div className="space-y-2">
                {orders
                  .filter(o => o.symbol === symbol && o.status === 'FILLED')
                  .slice(0, 5)
                  .map(o => (
                    <div key={o.id} className="p-3 rounded-md bg-bg-elevated neon-border-cyan">
                      <div className="flex justify-between items-center mb-1">
                        <span className={`text-sm font-semibold ${o.side === 'BUY' ? 'text-neon-cyan' : 'text-neon-pink'}`}>{o.side} {o.type}</span>
                        <span className="text-[10px] text-text-dim font-mono">{new Date(o.timestamp).toLocaleDateString()}</span>
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
            <h3 className="text-xs font-semibold text-text mb-4 font-mono uppercase tracking-wider">Active Orders</h3>
            {ordersLoading ? (
              <p className="text-text-dim text-sm text-center py-8">Loading orders...</p>
            ) : (
              <ActiveOrdersList orders={activeOrders} onRefresh={loadOrders} />
            )}
          </div>
        )}

        {activeTab === 'history' && (
          <div className="card-hover p-5">
            <h3 className="text-xs font-semibold text-text mb-4 font-mono uppercase tracking-wider">Trade History</h3>
            <TradeHistory trades={trades} loading={historyLoading} />
          </div>
        )}
      </div>
    </AppShell>
  );
}