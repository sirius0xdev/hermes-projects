'use client';
import { useState, useEffect, useCallback } from 'react';
import AppShell from '@/components/layout/AppShell';
import { fetchPositions, fetchBalance, fetchOrders, cancelOrder } from '@/lib/api';
import type { Position, Balance, Order } from '@/lib/api';

function fmt(n: number) {
  return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// Mock PnL history data
function generatePnlHistory(days = 30): { time: string; value: number }[] {
  const data: { time: string; value: number }[] = [];
  let value = 24000 + Math.random() * 500 - 250;
  const now = new Date();
  for (let i = days; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    value += (Math.random() - 0.45) * 800;
    value = Math.max(20000, Math.min(30000, value));
    data.push({
      time: d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      value: +value.toFixed(2),
    });
  }
  return data;
}

// Mock trade history data
function generatePositionHistory(): {
  id: string; symbol: string; side: string; size: number;
  entry: number; exit: number; pnl: number; pnlPct: number;
  duration: string; platform: string; closedAt: string;
}[] {
  return [
    { id: 'h1', symbol: 'BTC-PERP', side: 'LONG', size: 0.5, entry: 41200, exit: 43100, pnl: 950, pnlPct: 4.61, duration: '3d 14h', platform: 'Hyperliquid', closedAt: '2025-01-14' },
    { id: 'h2', symbol: 'SOL-PERP', side: 'LONG', size: 20, entry: 102.50, exit: 98.20, pnl: -86, pnlPct: -4.20, duration: '1d 6h', platform: 'Solana', closedAt: '2025-01-13' },
    { id: 'h3', symbol: 'ETH-PERP', side: 'SHORT', size: 3, entry: 2400, exit: 2280, pnl: 360, pnlPct: 5.00, duration: '5d 2h', platform: 'Hyperliquid', closedAt: '2025-01-12' },
    { id: 'h4', symbol: 'ARB-PERP', side: 'LONG', size: 500, entry: 0.88, exit: 0.95, pnl: 35, pnlPct: 7.95, duration: '12h', platform: 'Solana', closedAt: '2025-01-11' },
    { id: 'h5', symbol: 'DOGE-PERP', side: 'SHORT', size: 10000, entry: 0.084, exit: 0.082, pnl: 20, pnlPct: 2.38, duration: '2d 8h', platform: 'Hyperliquid', closedAt: '2025-01-10' },
  ];
}

export default function PortfolioPage() {
  const [balance, setBalance] = useState<Balance | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'positions' | 'orders' | 'history' | 'analytics'>('positions');
  const [pnlData, setPnlData] = useState<{ time: string; value: number }[]>([]);

  const loadData = useCallback(async () => {
    try {
      const [b, p, o] = await Promise.all([fetchBalance(), fetchPositions(), fetchOrders()]);
      setBalance(b);
      setPositions(p);
      setOrders(o);
    } catch (e) {
      console.error('Failed to load portfolio data:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    // Refresh every 30 seconds
    const id = setInterval(loadData, 30000);
    return () => clearInterval(id);
  }, [loadData]);

  // Generate mock analytics data
  useEffect(() => {
    setPnlData(generatePnlHistory(30));
  }, []);

  const handleCancel = async (id: string) => {
    try {
      await cancelOrder(id);
      setOrders(prev => prev.filter(o => o.id !== id));
    } catch (e) {
      console.error('Failed to cancel order:', e);
    }
  };

  // Compute asset allocation from positions
  const allocation = (() => {
    if (!balance) return [];
    const total = balance.inPositions || 1;
    const bySymbol: Record<string, number> = {};
    for (const p of positions) {
      const value = p.size * p.markPrice;
      bySymbol[p.symbol] = (bySymbol[p.symbol] || 0) + value;
    }
    return Object.entries(bySymbol)
      .map(([symbol, value]) => ({ symbol, pct: +((value / total) * 100).toFixed(1), value }))
      .sort((a, b) => b.value - a.value);
  })();

  // Compute aggregate PnL
  const totalPnl = positions.reduce((sum, p) => sum + p.pnl, 0);
  const totalPnlPct = balance ? +((totalPnl / balance.total) * 100).toFixed(2) : 0;

  if (loading) {
    return (
      <AppShell>
        <div className="flex items-center justify-center h-64">
          <div className="w-10 h-10 border-3 border-accent border-t-transparent rounded-full animate-spin" />
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="space-y-5">
        {/* Page Header */}
        <div>
          <h2 className="text-xl font-bold text-text-primary">Portfolio</h2>
          <p className="text-xs text-text-muted mt-0.5">
            Auto-refresh every 30s
          </p>
        </div>

        {/* Balance Cards */}
        {balance && (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {[
              { label: 'Total Balance', value: `$${fmt(balance.total)}`, cls: 'text-accent', icon: '◎' },
              { label: 'Available', value: `$${fmt(balance.available)}`, cls: 'text-text-primary', icon: '◈' },
              { label: 'In Positions', value: `$${fmt(balance.inPositions)}`, cls: 'text-text-primary', icon: '◉' },
              { label: 'Unrealized PnL', value: `${balance.unrealizedPnl >= 0 ? '+' : ''}$${fmt(balance.unrealizedPnl)}`, cls: balance.unrealizedPnl >= 0 ? 'text-up' : 'text-down', icon: totalPnl >= 0 ? '↑' : '↓' },
            ].map(item => (
              <div key={item.label} className="bg-bg-card rounded-xl border border-border p-4 hover:border-text-muted/50 transition-colors">
                <div className="flex items-center gap-1.5 text-xs text-text-muted mb-1">
                  <span className="opacity-60">{item.icon}</span>
                  {item.label}
                </div>
                <div className={`text-xl font-bold font-mono mt-1 ${item.cls}`}>{item.value}</div>
              </div>
            ))}
          </div>
        )}

        {/* Aggregate PnL */}
        {positions.length > 0 && (
          <div className="bg-bg-card rounded-xl border border-border p-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <span className="text-sm text-text-muted">Open PnL</span>
              <div className={`text-2xl font-bold font-mono ${totalPnl >= 0 ? 'text-up' : 'text-down'}`}>
                {totalPnl >= 0 ? '+' : ''}${fmt(totalPnl)}
                <span className="text-base ml-1">({totalPnlPct >= 0 ? '+' : ''}{totalPnlPct}%)</span>
              </div>
            </div>
            <div className="flex items-center gap-4 text-sm">
              <span className="text-text-muted">{positions.length} position{positions.length !== 1 ? 's' : ''}</span>
              <span className="text-text-muted">{orders.length} order{orders.length !== 1 ? 's' : ''}</span>
            </div>
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-1 border-b border-border">
          {[
            { key: 'positions' as const, label: 'Positions', count: positions.length },
            { key: 'orders' as const, label: 'Orders', count: orders.length },
            { key: 'history' as const, label: 'History' },
            { key: 'analytics' as const, label: 'Analytics' },
          ].map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px ${
                activeTab === tab.key
                  ? 'text-accent border-accent'
                  : 'text-text-muted border-transparent hover:text-text-primary'
              }`}
            >
              {tab.label}
              {'count' in tab && tab.count !== undefined && (
                <span className={`ml-1.5 text-xs px-1.5 py-0.5 rounded ${
                  activeTab === tab.key ? 'bg-accent/20 text-accent' : 'bg-bg-secondary text-text-muted'
                }`}>
                  {tab.count}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        {activeTab === 'positions' && (
          <div className="bg-bg-card rounded-xl border border-border overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-text-muted border-b border-border">
                    <th className="text-left px-4 py-3 font-medium">Symbol</th>
                    <th className="text-left px-4 py-3 font-medium">Side</th>
                    <th className="text-right px-4 py-3 font-medium">Size</th>
                    <th className="text-right px-4 py-3 font-medium">Entry</th>
                    <th className="text-right px-4 py-3 font-medium">Mark</th>
                    <th className="text-right px-4 py-3 font-medium">PnL</th>
                    <th className="text-right px-4 py-3 font-medium">Lev</th>
                    <th className="text-left px-4 py-3 font-medium">Platform</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map(p => (
                    <tr key={p.id} className="border-b border-border/50 hover:bg-bg-secondary/50 transition-colors">
                      <td className="px-4 py-3 font-semibold text-text-primary">{p.symbol}</td>
                      <td className={`px-4 py-3 font-semibold ${p.side === 'LONG' ? 'text-up' : 'text-down'}`}>
                        <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                          p.side === 'LONG' ? 'bg-up/10 text-up' : 'bg-down/10 text-down'
                        }`}>{p.side}</span>
                      </td>
                      <td className="px-4 py-3 font-mono text-text-primary text-right">{p.size}</td>
                      <td className="px-4 py-3 font-mono text-text-primary text-right">{fmt(p.entryPrice)}</td>
                      <td className="px-4 py-3 font-mono text-text-primary text-right">{fmt(p.markPrice)}</td>
                      <td className={`px-4 py-3 font-mono font-semibold text-right ${p.pnl >= 0 ? 'text-up' : 'text-down'}`}>
                        {p.pnl >= 0 ? '+' : ''}{fmt(p.pnl)}
                        <span className="text-xs ml-1">({p.pnlPct >= 0 ? '+' : ''}{p.pnlPct.toFixed(2)}%)</span>
                      </td>
                      <td className="px-4 py-3 font-mono text-text-primary text-right">
                        <span className="px-1.5 py-0.5 rounded bg-bg-secondary text-xs">{p.leverage}x</span>
                      </td>
                      <td className="px-4 py-3 text-text-primary">
                        <PlatformBadge platform={p.platform} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!positions.length && (
                <p className="px-4 py-12 text-sm text-text-muted text-center">No open positions</p>
              )}
            </div>
          </div>
        )}

        {activeTab === 'orders' && (
          <div className="bg-bg-card rounded-xl border border-border overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-xs text-text-muted border-b border-border">
                    <th className="text-left px-4 py-3 font-medium">Symbol</th>
                    <th className="text-left px-4 py-3 font-medium">Side</th>
                    <th className="text-left px-4 py-3 font-medium">Type</th>
                    <th className="text-right px-4 py-3 font-medium">Price</th>
                    <th className="text-right px-4 py-3 font-medium">Amount</th>
                    <th className="text-right px-4 py-3 font-medium">Filled</th>
                    <th className="text-left px-4 py-3 font-medium">Status</th>
                    <th className="text-left px-4 py-3 font-medium">Platform</th>
                    <th className="text-left px-4 py-3 font-medium"></th>
                  </tr>
                </thead>
                <tbody>
                  {orders.map(o => (
                    <tr key={o.id} className="border-b border-border/50 hover:bg-bg-secondary/50 transition-colors">
                      <td className="px-4 py-3 font-semibold text-text-primary">{o.symbol}</td>
                      <td className={`px-4 py-3 font-semibold ${o.side === 'BUY' ? 'text-up' : 'text-down'}`}>{o.side}</td>
                      <td className="px-4 py-3 font-mono text-text-secondary">{o.type}</td>
                      <td className="px-4 py-3 font-mono text-text-primary text-right">{fmt(o.price)}</td>
                      <td className="px-4 py-3 font-mono text-text-primary text-right">{o.amount}</td>
                      <td className="px-4 py-3 font-mono text-text-secondary text-right">{o.filled}/{o.amount}</td>
                      <td className="px-4 py-3">
                        <StatusBadge status={o.status} />
                      </td>
                      <td className="px-4 py-3">
                        <PlatformBadge platform={o.platform} />
                      </td>
                      <td className="px-4 py-3">
                        {(o.status === 'OPEN' || o.status === 'PENDING') && (
                          <button
                            onClick={() => handleCancel(o.id)}
                            className="text-down hover:text-down/80 text-xs font-medium transition-colors"
                          >
                            Cancel
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!orders.length && (
                <p className="px-4 py-12 text-sm text-text-muted text-center">No open orders</p>
              )}
            </div>
          </div>
        )}

        {activeTab === 'history' && (
          <PositionHistoryTable />
        )}

        {activeTab === 'analytics' && (
          <div className="space-y-4">
            {/* PnL Chart */}
            <div className="bg-bg-card rounded-xl border border-border p-4">
              <h3 className="text-sm font-semibold text-text-primary mb-4">30-Day PnL</h3>
              <PnLChart data={pnlData} />
            </div>

            {/* Asset Allocation */}
            {allocation.length > 0 && (
              <div className="bg-bg-card rounded-xl border border-border p-4">
                <h3 className="text-sm font-semibold text-text-primary mb-4">Asset Allocation</h3>
                <div className="space-y-3">
                  {allocation.map(a => (
                    <div key={a.symbol}>
                      <div className="flex items-center justify-between text-sm mb-1">
                        <span className="font-medium text-text-primary">{a.symbol}</span>
                        <span className="font-mono text-text-muted">{a.pct}%</span>
                      </div>
                      <div className="h-2 bg-bg-secondary rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full bg-accent transition-all"
                          style={{ width: `${Math.min(a.pct, 100)}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Key Stats */}
            {balance && (
              <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
                {[
                  { label: 'Margin Used', value: `${((balance.inPositions / balance.total) * 100).toFixed(1)}%` },
                  { label: 'Free Margin', value: `${((balance.available / balance.total) * 100).toFixed(1)}%` },
                  { label: 'Win Rate (last 5)', value: `${(() => {
                    const hist = generatePositionHistory();
                    const wins = hist.filter(h => h.pnl > 0).length;
                    return `${(wins / hist.length * 100).toFixed(0)}%`;
                  })()}` },
                  { label: 'Best Trade', value: `+$${fmt(Math.max(...generatePositionHistory().map(h => h.pnl)))}` },
                  { label: 'Worst Trade', value: `$${fmt(Math.min(...generatePositionHistory().map(h => h.pnl)))}` },
                  { label: 'Avg PnL/Trade', value: `${(() => {
                    const hist = generatePositionHistory();
                    const avg = hist.reduce((s, h) => s + h.pnl, 0) / hist.length;
                    return `${avg >= 0 ? '+' : ''}$${fmt(avg)}`;
                  })()}` },
                ].map(s => (
                  <div key={s.label} className="bg-bg-card rounded-lg border border-border p-3">
                    <div className="text-xs text-text-muted">{s.label}</div>
                    <div className="text-sm font-mono text-text-primary mt-1">{s.value}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </AppShell>
  );
}

// ---------- Sub-components ----------

function PositionHistoryTable() {
  const history = generatePositionHistory();

  return (
    <div className="bg-bg-card rounded-xl border border-border overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs text-text-muted border-b border-border">
              <th className="text-left px-4 py-3 font-medium">Symbol</th>
              <th className="text-left px-4 py-3 font-medium">Side</th>
              <th className="text-right px-4 py-3 font-medium">Size</th>
              <th className="text-right px-4 py-3 font-medium">Entry</th>
              <th className="text-right px-4 py-3 font-medium">Exit</th>
              <th className="text-right px-4 py-3 font-medium">PnL</th>
              <th className="text-right px-4 py-3 font-medium">Duration</th>
              <th className="text-left px-4 py-3 font-medium">Platform</th>
              <th className="text-left px-4 py-3 font-medium">Closed</th>
            </tr>
          </thead>
          <tbody>
            {history.map(h => (
              <tr key={h.id} className="border-b border-border/50 hover:bg-bg-secondary/50 transition-colors">
                <td className="px-4 py-3 font-semibold text-text-primary">{h.symbol}</td>
                <td className={`px-4 py-3 font-semibold ${h.side === 'LONG' ? 'text-up' : 'text-down'}`}>
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                    h.side === 'LONG' ? 'bg-up/10 text-up' : 'bg-down/10 text-down'
                  }`}>{h.side}</span>
                </td>
                <td className="px-4 py-3 font-mono text-text-primary text-right">{h.size}</td>
                <td className="px-4 py-3 font-mono text-text-primary text-right">{fmt(h.entry)}</td>
                <td className="px-4 py-3 font-mono text-text-primary text-right">{fmt(h.exit)}</td>
                <td className={`px-4 py-3 font-mono font-semibold text-right ${h.pnl >= 0 ? 'text-up' : 'text-down'}`}>
                  {h.pnl >= 0 ? '+' : ''}{fmt(h.pnl)}
                  <span className="text-xs ml-1">({h.pnlPct >= 0 ? '+' : ''}{h.pnlPct.toFixed(2)}%)</span>
                </td>
                <td className="px-4 py-3 text-text-secondary text-right">{h.duration}</td>
                <td className="px-4 py-3"><PlatformBadge platform={h.platform} /></td>
                <td className="px-4 py-3 text-text-muted text-right text-xs">{h.closedAt}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function PnLChart({ data }: { data: { time: string; value: number }[] }) {
  if (data.length === 0) return <p className="text-sm text-text-muted">No data</p>;

  const values = data.map(d => d.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const svgWidth = 800;
  const svgHeight = 200;
  const padding = 5;

  const points = data.map((d, i) => {
    const x = padding + (i / (data.length - 1)) * (svgWidth - 2 * padding);
    const y = svgHeight - padding - ((d.value - min) / range) * (svgHeight - 2 * padding);
    return `${x},${y}`;
  }).join(' ');

  const areaPoints = `${padding},${svgHeight - padding} ${points} ${svgWidth - padding},${svgHeight - padding}`;
  const startVal = data[0].value;
  const endVal = data[data.length - 1].value;
  const isPositive = endVal >= startVal;
  const lineColor = isPositive ? '#00d4aa' : '#f44336';
  const gradientId = 'pnl-gradient';

  return (
    <div className="w-full">
      <div className="flex items-end justify-between text-xs text-text-muted mb-2 px-1">
        <span>{data[0].time}</span>
        <span className={`font-mono font-semibold ${isPositive ? 'text-up' : 'text-down'}`}>
          {endVal >= startVal ? '+' : '-'}${fmt(Math.abs(endVal - startVal))}
        </span>
        <span>{data[data.length - 1].time}</span>
      </div>
      <svg viewBox={`0 0 ${svgWidth} ${svgHeight}`} className="w-full h-auto" preserveAspectRatio="none">
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={lineColor} stopOpacity="0.3" />
            <stop offset="100%" stopColor={lineColor} stopOpacity="0.02" />
          </linearGradient>
        </defs>
        {/* Grid lines */}
        {[0, 0.25, 0.5, 0.75, 1].map(pct => (
          <line
            key={pct}
            x1={padding}
            y1={padding + pct * (svgHeight - 2 * padding)}
            x2={svgWidth - padding}
            y2={padding + pct * (svgHeight - 2 * padding)}
            stroke="#1e293b"
            strokeWidth="1"
          />
        ))}
        {/* Area */}
        <polygon points={areaPoints} fill={`url(#${gradientId})`} />
        {/* Line */}
        <polyline
          points={points}
          fill="none"
          stroke={lineColor}
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {/* Endpoint dot */}
        {(() => {
          const lastX = svgWidth - padding;
          const lastY = svgHeight - padding - ((endVal - min) / range) * (svgHeight - 2 * padding);
          return <circle cx={lastX} cy={lastY} r="4" fill={lineColor} />;
        })()}
      </svg>
      <div className="flex justify-between text-xs text-text-muted mt-1 px-1">
        <span className="font-mono">{fmt(max)}</span>
        <span className="font-mono">{fmt(min)}</span>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    OPEN: 'bg-accent/20 text-accent',
    FILLED: 'bg-up/20 text-up',
    CANCELLED: 'bg-text-muted/20 text-text-muted',
    PENDING: 'bg-yellow-500/20 text-yellow-400',
  };
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${colors[status] ?? 'bg-text-muted/20 text-text-muted'}`}>
      {status}
    </span>
  );
}

function PlatformBadge({ platform }: { platform: string }) {
  const isHL = platform === 'Hyperliquid';
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${
      isHL ? 'bg-blue-500/20 text-blue-400' : 'bg-purple-500/20 text-purple-400'
    }`}>
      {platform}
    </span>
  );
}
