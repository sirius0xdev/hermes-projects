'use client';
import { useState, useEffect, useCallback } from 'react';
import AppShell from '@/components/layout/AppShell';
import OrderForm from '@/components/trading/OrderForm';
import ActiveOrdersList from '@/components/trading/ActiveOrdersList';
import TradeHistory from '@/components/trading/TradeHistory';
import { fetchTickers, fetchTradeOrders, fetchTradeHistory } from '@/lib/api';
import type { TickerPrice, Order, TradeHistoryItem } from '@/lib/api';

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

  // Load tickers once
  useEffect(() => {
    fetchTickers().then(t => setTickers(t));
  }, []);

  // Load orders
  const loadOrders = useCallback(async () => {
    setOrdersLoading(true);
    const o = await fetchTradeOrders();
    setOrders(o);
    setOrdersLoading(false);
  }, []);

  // Load trade history
  const loadHistory = useCallback(async () => {
    setHistoryLoading(true);
    const h = await fetchTradeHistory();
    setTrades(h);
    setHistoryLoading(false);
  }, []);

  // Initial load
  useEffect(() => {
    loadOrders();
    loadHistory();
  }, [loadOrders, loadHistory]);

  // Auto-refresh
  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(() => {
      loadOrders();
      loadHistory();
    }, 30000); // every 30 seconds
    return () => clearInterval(interval);
  }, [autoRefresh, loadOrders, loadHistory]);

  const activeOrders = orders.filter(o => o.status === 'OPEN' || o.status === 'PENDING');

  const selected = tickers.find(t => t.symbol === symbol);

  return (
    <AppShell>
      <div className="space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h2 className="text-xl font-bold text-text-primary">Trade Execution</h2>
            <p className="text-sm text-text-secondary mt-0.5">Place, manage, and track your orders</p>
          </div>
          <div className="flex items-center gap-3">
            <button onClick={() => setAutoRefresh(!autoRefresh)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${autoRefresh ? 'bg-accent/20 text-accent border-accent' : 'bg-bg-secondary text-text-muted border-border'}`}>
              {autoRefresh ? '● Auto-refresh ON' : '○ Auto-refresh OFF'}
            </button>
            <button onClick={() => { loadOrders(); loadHistory(); }}
              className="px-3 py-1.5 rounded-lg text-xs font-medium bg-bg-secondary text-text-secondary border border-border hover:text-text-primary transition-colors">
              ↻ Refresh
            </button>
          </div>
        </div>

        {/* Symbol selector */}
        <div className="flex flex-wrap gap-2">
          {tickers.map(t => (
            <button key={t.symbol} onClick={() => setSymbol(t.symbol)}
              className={`px-3 py-2 rounded-lg border text-sm font-medium transition-colors ${symbol === t.symbol ? 'bg-bg-card border-accent text-accent' : 'bg-bg-secondary border-border text-text-secondary hover:text-text-primary'}`}>
              {t.symbol}
            </button>
          ))}
        </div>

        {/* Selected ticker info */}
        {selected && (
          <div className="bg-bg-card rounded-xl border border-border p-4">
            <div className="flex items-center gap-4 flex-wrap">
              <span className="text-lg font-bold text-text-primary">{selected.symbol}</span>
              <span className={`text-lg font-mono font-semibold ${selected.change24h >= 0 ? 'text-up' : 'text-down'}`}>
                ${fmt(selected.price)}
              </span>
              <span className={`text-sm font-medium px-2 py-0.5 rounded ${selected.change24h >= 0 ? 'bg-up/10 text-up' : 'bg-down/10 text-down'}`}>
                {selected.change24h >= 0 ? '+' : ''}{selected.change24h.toFixed(2)}%
              </span>
              <span className="text-xs text-text-secondary ml-auto">
                24h: ${fmt(selected.low24h)} — ${fmt(selected.high24h)}
              </span>
              <span className="text-xs text-text-muted">
                Vol: ${(selected.volume24h / 1e6).toFixed(0)}M
              </span>
            </div>
          </div>
        )}

        {/* Tab navigation */}
        <div className="flex gap-1 bg-bg-secondary rounded-xl border border-border p-1">
          {([
            { key: 'order' as Tab, label: 'Place Order', icon: '⚡' },
            { key: 'active' as Tab, label: `Active Orders (${activeOrders.length})`, icon: '📋' },
            { key: 'history' as Tab, label: 'Trade History', icon: '📊' },
          ]).map(tab => (
            <button key={tab.key} onClick={() => setActiveTab(tab.key)}
              className={`flex-1 py-2.5 px-4 rounded-lg text-sm font-medium transition-all ${
                activeTab === tab.key
                  ? 'bg-bg-card text-accent shadow-sm'
                  : 'text-text-muted hover:text-text-secondary'
              }`}>
              {tab.icon} {tab.label}
            </button>
          ))}
        </div>

        {/* Content */}
        {activeTab === 'order' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Order form */}
            <div className="bg-bg-card rounded-xl border border-border p-5">
              <h3 className="text-sm font-semibold text-text-primary mb-4 flex items-center gap-2">
                <span className="text-accent">⚡</span> New Order
              </h3>
              <OrderForm symbol={symbol} onPlaced={() => { loadOrders(); loadHistory(); }} />
            </div>

            {/* Quick order book */}
            <div className="bg-bg-card rounded-xl border border-border p-4">
              <h3 className="text-sm font-semibold text-text-primary mb-3">Order Book</h3>
              {ordersLoading ? (
                <p className="text-text-muted text-sm">Loading...</p>
              ) : (
                <div className="space-y-1 max-h-80 overflow-y-auto">
                  {orders
                    .filter(o => o.symbol === symbol && (o.status === 'OPEN' || o.status === 'PENDING'))
                    .slice(0, 8)
                    .map(o => (
                      <div key={o.id} className="flex justify-between items-center text-xs p-2 rounded bg-bg-primary border border-border/50">
                        <div>
                          <span className={`font-semibold ${o.side === 'BUY' ? 'text-up' : 'text-down'}`}>{o.side}</span>
                          <span className="text-text-muted ml-1">{o.type}</span>
                        </div>
                        <span className="font-mono text-text-secondary">${fmt(o.price)}</span>
                        <span className="font-mono text-text-muted">{o.amount}</span>
                        <span className={`px-1 rounded text-xs ${o.chain === 'Hyperliquid' ? 'bg-accent/10 text-accent' : 'bg-purple-500/10 text-purple-400'}`}>
                          {o.chain === 'Hyperliquid' ? '⬡' : '◎'}
                        </span>
                      </div>
                    ))}
                  {orders.filter(o => o.symbol === symbol && (o.status === 'OPEN' || o.status === 'PENDING')).length === 0 && (
                    <p className="text-text-muted text-sm text-center py-4">No active orders for {symbol}</p>
                  )}
                </div>
              )}
            </div>

            {/* Recent positions */}
            <div className="bg-bg-card rounded-xl border border-border p-4">
              <h3 className="text-sm font-semibold text-text-primary mb-3">Positions</h3>
              <div className="space-y-2">
                {orders
                  .filter(o => o.symbol === symbol && o.status === 'FILLED')
                  .slice(0, 5)
                  .map(o => (
                    <div key={o.id} className="p-3 rounded-lg bg-bg-primary border border-border">
                      <div className="flex justify-between items-center mb-1">
                        <span className={`text-sm font-semibold ${o.side === 'BUY' ? 'text-up' : 'text-down'}`}>{o.side} {o.type}</span>
                        <span className="text-xs text-text-muted">{new Date(o.timestamp).toLocaleDateString()}</span>
                      </div>
                      <div className="flex justify-between text-xs text-text-secondary">
                        <span className="font-mono">${fmt(o.price)}</span>
                        <span className="font-mono">Qty: {o.amount}</span>
                      </div>
                    </div>
                  ))}
                {orders.filter(o => o.symbol === symbol && o.status === 'FILLED').length === 0 && (
                  <p className="text-sm text-text-muted text-center py-4">No filled orders for {symbol}</p>
                )}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'active' && (
          <div className="bg-bg-card rounded-xl border border-border p-5">
            <h3 className="text-sm font-semibold text-text-primary mb-4 flex items-center gap-2">
              <span>📋</span> Active Orders
            </h3>
            {ordersLoading ? (
              <p className="text-text-muted text-sm text-center py-8">Loading orders...</p>
            ) : (
              <ActiveOrdersList orders={activeOrders} onRefresh={loadOrders} />
            )}
          </div>
        )}

        {activeTab === 'history' && (
          <div className="bg-bg-card rounded-xl border border-border p-5">
            <h3 className="text-sm font-semibold text-text-primary mb-4 flex items-center gap-2">
              <span>📊</span> Trade History
            </h3>
            <TradeHistory trades={trades} loading={historyLoading} />
          </div>
        )}
      </div>
    </AppShell>
  );
}
