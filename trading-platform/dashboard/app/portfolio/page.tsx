'use client';
import { useState, useEffect, useCallback } from 'react';
import AppShell from '@/components/layout/AppShell';
import { fetchPositions, fetchBalance, fetchOrders, cancelOrder } from '@/lib/api';
import type { Position, Balance, Order } from '@/lib/api';
import {
  PieChart,
  TrendingUp,
  TrendingDown,
  ArrowUpRight,
  ArrowDownRight,
  Activity,
  DollarSign,
} from 'lucide-react';

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

const ALLOCATION_COLORS = ['#6366f1', '#22c55e', '#f59e0b', '#8b5cf6', '#f43f5e', '#3b82f6'];

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
    const id = setInterval(loadData, 30000);
    return () => clearInterval(id);
  }, [loadData]);

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

  const totalPnl = positions.reduce((sum, p) => sum + p.pnl, 0);
  const totalPnlPct = balance ? +((totalPnl / balance.total) * 100).toFixed(2) : 0;

  if (loading) {
    return (
      <AppShell>
        <div className="flex items-center justify-center h-64">
          <div className="w-10 h-10 border-3 border-accent/30 border-t-accent rounded-full animate-spin" />
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="space-y-5">
        {/* Page Header */}
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-accent/10 flex items-center justify-center">
            <PieChart className="w-4 h-4 text-accent" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-text">Portfolio</h2>
            <p className="text-[11px] text-text-dim mt-0.5">Real-time positions, orders, and performance</p>
          </div>
        </div>

        {/* Balance Cards */}
        {balance && (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {[
              { label: 'Total Balance', value: `$${fmt(balance.total)}`, cls: 'text-accent', icon: DollarSign },
              { label: 'Available', value: `$${fmt(balance.available)}`, cls: 'text-text', icon: Activity },
              { label: 'In Positions', value: `$${fmt(balance.inPositions)}`, cls: 'text-text', icon: PieChart },
              { label: 'Unrealized PnL', value: `${balance.unrealizedPnl >= 0 ? '+' : ''}$${fmt(balance.unrealizedPnl)}`, cls: balance.unrealizedPnl >= 0 ? 'text-long' : 'text-short', icon: balance.unrealizedPnl >= 0 ? TrendingUp : TrendingDown },
            ].map(item => {
              const Icon = item.icon;
              return (
                <div key={item.label} className="card-hover p-4">
                  <div className="flex items-center gap-2 text-[11px] text-text-dim mb-2">
                    <Icon className="w-3.5 h-3.5 opacity-70" />
                    {item.label}
                  </div>
                  <div className={`text-lg font-bold font-mono tracking-tight ${item.cls}`}>{item.value}</div>
                </div>
              );
            })}
          </div>
        )}

        {/* Aggregate PnL */}
        {positions.length > 0 && (
          <div className="card-hover p-5 flex flex-wrap items-center justify-between gap-4">
            <div>
              <span className="text-xs text-text-dim">Open PnL</span>
              <div className={`text-2xl font-bold font-mono tracking-tight ${totalPnl >= 0 ? 'text-long' : 'text-short'}`}>
                {totalPnl >= 0 ? '+' : ''}${fmt(totalPnl)}
                <span className="text-base ml-1.5 font-medium">({totalPnlPct >= 0 ? '+' : ''}{totalPnlPct}%)</span>
              </div>
            </div>
            <div className="flex items-center gap-6 text-sm">
              <span className="text-text-dim">{positions.length} position{positions.length !== 1 ? 's' : ''}</span>
              <span className="text-text-dim">{orders.length} order{orders.length !== 1 ? 's' : ''}</span>
            </div>
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-0 border-b border-bg-border">
          {[
            { key: 'positions' as const, label: 'Positions', count: positions.length },
            { key: 'orders' as const, label: 'Orders', count: orders.length },
            { key: 'history' as const, label: 'History' },
            { key: 'analytics' as const, label: 'Analytics' },
          ].map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`tab-btn ${
                activeTab === tab.key ? 'tab-btn-active' : ''
              }`}
            >
              {tab.label}
              {'count' in tab && tab.count !== undefined && (
                <span className={`ml-1.5 text-[10px] px-1.5 py-0.5 rounded font-medium ${
                  activeTab === tab.key ? 'bg-accent/20 text-accent' : 'bg-bg-elevated text-text-dim'
                }`}>
                  {tab.count}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        {activeTab === 'positions' && (
          <div className="card-hover overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[10px] text-text-dim uppercase tracking-wider border-b border-bg-border">
                    <th className="text-left px-5 py-3 font-medium">Symbol</th>
                    <th className="text-left px-5 py-3 font-medium">Side</th>
                    <th className="text-right px-5 py-3 font-medium">Size</th>
                    <th className="text-right px-5 py-3 font-medium">Entry</th>
                    <th className="text-right px-5 py-3 font-medium">Mark</th>
                    <th className="text-right px-5 py-3 font-medium">PnL</th>
                    <th className="text-right px-5 py-3 font-medium">Lev</th>
                    <th className="text-left px-5 py-3 font-medium">Platform</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map(p => (
                    <tr key={p.id} className="border-b border-bg-border/50 hover:bg-bg-hover transition-colors">
                      <td className="px-5 py-3 font-semibold text-text">{p.symbol}</td>
                      <td className={`px-5 py-3 font-semibold`}>
                        <span className={`px-2 py-0.5 rounded text-xs font-bold uppercase tracking-wider ${
                          p.side === 'LONG' ? 'bg-long-muted text-long' : 'bg-short-muted text-short'
                        }`}>{p.side}</span>
                      </td>
                      <td className="px-5 py-3 font-mono text-text text-right">{p.size}</td>
                      <td className="px-5 py-3 font-mono text-text text-right">${fmt(p.entryPrice)}</td>
                      <td className="px-5 py-3 font-mono text-text text-right">${fmt(p.markPrice)}</td>
                      <td className={`px-5 py-3 font-mono font-semibold text-right ${p.pnl >= 0 ? 'text-long' : 'text-short'}`}>
                        {p.pnl >= 0 ? '+' : ''}{fmt(p.pnl)}
                        <span className="text-xs ml-1">({p.pnlPct >= 0 ? '+' : ''}{p.pnlPct.toFixed(2)}%)</span>
                      </td>
                      <td className="px-5 py-3 font-mono text-text text-right">
                        <span className="px-2 py-0.5 rounded bg-bg-elevated text-xs">{p.leverage}x</span>
                      </td>
                      <td className="px-5 py-3 text-text">
                        <PlatformBadge platform={p.platform} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!positions.length && (
                <p className="px-5 py-12 text-sm text-text-dim text-center">No open positions</p>
              )}
            </div>
          </div>
        )}

        {activeTab === 'orders' && (
          <div className="card-hover overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-[10px] text-text-dim uppercase tracking-wider border-b border-bg-border">
                    <th className="text-left px-5 py-3 font-medium">Symbol</th>
                    <th className="text-left px-5 py-3 font-medium">Side</th>
                    <th className="text-left px-5 py-3 font-medium">Type</th>
                    <th className="text-right px-5 py-3 font-medium">Price</th>
                    <th className="text-right px-5 py-3 font-medium">Amount</th>
                    <th className="text-right px-5 py-3 font-medium">Filled</th>
                    <th className="text-left px-5 py-3 font-medium">Status</th>
                    <th className="text-left px-5 py-3 font-medium">Platform</th>
                    <th className="text-left px-5 py-3 font-medium"></th>
                  </tr>
                </thead>
                <tbody>
                  {orders.map(o => (
                    <tr key={o.id} className="border-b border-bg-border/50 hover:bg-bg-hover transition-colors">
                      <td className="px-5 py-3 font-semibold text-text">{o.symbol}</td>
                      <td className={`px-5 py-3 font-semibold ${o.side === 'BUY' ? 'text-long' : 'text-short'}`}>{o.side}</td>
                      <td className="px-5 py-3 font-mono text-text-secondary">{o.type}</td>
                      <td className="px-5 py-3 font-mono text-text text-right">${fmt(o.price)}</td>
                      <td className="px-5 py-3 font-mono text-text text-right">{o.amount}</td>
                      <td className="px-5 py-3 font-mono text-text-secondary text-right">{o.filled}/{o.amount}</td>
                      <td className="px-5 py-3">
                        <StatusBadge status={o.status} />
                      </td>
                      <td className="px-5 py-3">
                        <PlatformBadge platform={o.platform} />
                      </td>
                      <td className="px-5 py-3">
                        {(o.status === 'OPEN' || o.status === 'PENDING') && (
                          <button
                            onClick={() => handleCancel(o.id)}
                            className="text-short hover:text-short/80 text-xs font-medium transition-colors"
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
                <p className="px-5 py-12 text-sm text-text-dim text-center">No open orders</p>
              )}
            </div>
          </div>
        )}

        {activeTab === 'history' && <PositionHistoryTable />}

        {activeTab === 'analytics' && (
          <div className="space-y-5">
            {/* PnL Chart */}
            <div className="card-hover p-5">
              <h3 className="text-sm font-semibold text-text mb-4">30-Day Equity Curve</h3>
              <PnLChart data={pnlData} />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              {/* Asset Allocation */}
              {allocation.length > 0 && (
                <div className="card-hover p-5">
                  <h3 className="text-sm font-semibold text-text mb-4">Asset Allocation</h3>
                  <div className="flex items-center gap-6">
                    {/* Donut chart */}
                    <DonutChart allocation={allocation} />
                    <div className="space-y-3 flex-1">
                      {allocation.map((a, i) => (
                        <div key={a.symbol}>
                          <div className="flex items-center justify-between text-sm mb-1">
                            <div className="flex items-center gap-2">
                              <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: ALLOCATION_COLORS[i % ALLOCATION_COLORS.length] }} />
                              <span className="font-medium text-text">{a.symbol}</span>
                            </div>
                            <span className="font-mono text-text-dim">{a.pct}%</span>
                          </div>
                          <div className="h-1.5 bg-bg-elevated rounded-full overflow-hidden">
                            <div
                              className="h-full rounded-full transition-all duration-500"
                              style={{ width: `${Math.min(a.pct, 100)}%`, backgroundColor: ALLOCATION_COLORS[i % ALLOCATION_COLORS.length] }}
                            />
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* Key Stats */}
              {balance && (
                <div className="card-hover p-5">
                  <h3 className="text-sm font-semibold text-text mb-4">Performance Metrics</h3>
                  <div className="grid grid-cols-2 gap-3">
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
                      <div key={s.label} className="bg-bg-elevated rounded-lg p-3">
                        <div className="text-[11px] text-text-dim">{s.label}</div>
                        <div className="text-sm font-mono text-text mt-1">{s.value}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}

// ---------- Donut Chart ----------
function DonutChart({ allocation }: { allocation: { symbol: string; pct: number; value: number }[] }) {
  const radius = 60;
  const strokeW = 20;
  const center = 80;
  const circumference = 2 * Math.PI * radius;
  let cumulative = 0;

  return (
    <div className="shrink-0">
      <svg width={center * 2} height={center * 2} viewBox={`0 0 ${center * 2} ${center * 2}`} className="-rotate-90">
        {allocation.map((a, i) => {
          const segLen = (a.pct / 100) * circumference;
          const offset = (cumulative / 100) * circumference;
          cumulative += a.pct;
          return (
            <circle
              key={a.symbol}
              cx={center}
              cy={center}
              r={radius}
              fill="none"
              stroke={ALLOCATION_COLORS[i % ALLOCATION_COLORS.length]}
              strokeWidth={strokeW}
              strokeDasharray={`${segLen} ${circumference - segLen}`}
              strokeDashoffset={`-${offset}`}
              className="transition-all duration-500"
            />
          );
        })}
      </svg>
    </div>
  );
}

// ---------- PnL Chart ----------
function PnLChart({ data }: { data: { time: string; value: number }[] }) {
  if (data.length === 0) return <p className="text-sm text-text-dim">No data</p>;

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
  const lineColor = isPositive ? '#22c55e' : '#f43f5e';

  return (
    <div className="w-full">
      <div className="flex items-end justify-between text-xs text-text-dim mb-2 px-1">
        <span>{data[0].time}</span>
        <span className={`font-mono font-semibold ${isPositive ? 'text-long' : 'text-short'}`}>
          {endVal >= startVal ? '+' : '-'}${fmt(Math.abs(endVal - startVal))}
        </span>
        <span>{data[data.length - 1].time}</span>
      </div>
      <svg viewBox={`0 0 ${svgWidth} ${svgHeight}`} className="w-full h-auto" preserveAspectRatio="none">
        <defs>
          <linearGradient id="pnl-gradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={lineColor} stopOpacity="0.25" />
            <stop offset="100%" stopColor={lineColor} stopOpacity="0.02" />
          </linearGradient>
        </defs>
        {[0, 0.25, 0.5, 0.75, 1].map(pct => (
          <line
            key={pct}
            x1={padding}
            y1={padding + pct * (svgHeight - 2 * padding)}
            x2={svgWidth - padding}
            y2={padding + pct * (svgHeight - 2 * padding)}
            stroke="rgba(28, 34, 51, 0.8)"
            strokeWidth="1"
          />
        ))}
        <polygon points={areaPoints} fill="url(#pnl-gradient)" />
        <polyline
          points={points}
          fill="none"
          stroke={lineColor}
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {(() => {
          const lastX = svgWidth - padding;
          const lastY = svgHeight - padding - ((endVal - min) / range) * (svgHeight - 2 * padding);
          return <circle cx={lastX} cy={lastY} r="4" fill={lineColor} />;
        })()}
      </svg>
      <div className="flex justify-between text-xs text-text-dim mt-1 px-1">
        <span className="font-mono">{fmt(max)}</span>
        <span className="font-mono">{fmt(min)}</span>
      </div>
    </div>
  );
}

// ---------- Position History Table ----------
function PositionHistoryTable() {
  const history = generatePositionHistory();

  return (
    <div className="card-hover overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[10px] text-text-dim uppercase tracking-wider border-b border-bg-border">
              <th className="text-left px-5 py-3 font-medium">Symbol</th>
              <th className="text-left px-5 py-3 font-medium">Side</th>
              <th className="text-right px-5 py-3 font-medium">Size</th>
              <th className="text-right px-5 py-3 font-medium">Entry</th>
              <th className="text-right px-5 py-3 font-medium">Exit</th>
              <th className="text-right px-5 py-3 font-medium">PnL</th>
              <th className="text-right px-5 py-3 font-medium">Duration</th>
              <th className="text-left px-5 py-3 font-medium">Platform</th>
              <th className="text-left px-5 py-3 font-medium">Closed</th>
            </tr>
          </thead>
          <tbody>
            {history.map(h => (
              <tr key={h.id} className="border-b border-bg-border/50 hover:bg-bg-hover transition-colors">
                <td className="px-5 py-3 font-semibold text-text">{h.symbol}</td>
                <td className={`px-5 py-3 font-semibold`}>
                  <span className={`px-2 py-0.5 rounded text-xs font-bold uppercase tracking-wider ${
                    h.side === 'LONG' ? 'bg-long-muted text-long' : 'bg-short-muted text-short'
                  }`}>{h.side}</span>
                </td>
                <td className="px-5 py-3 font-mono text-text text-right">{h.size}</td>
                <td className="px-5 py-3 font-mono text-text text-right">${fmt(h.entry)}</td>
                <td className="px-5 py-3 font-mono text-text text-right">${fmt(h.exit)}</td>
                <td className={`px-5 py-3 font-mono font-semibold text-right ${h.pnl >= 0 ? 'text-long' : 'text-short'}`}>
                  {h.pnl >= 0 ? '+' : ''}{fmt(h.pnl)}
                  <span className="text-xs ml-1">({h.pnlPct >= 0 ? '+' : ''}{h.pnlPct.toFixed(2)}%)</span>
                </td>
                <td className="px-5 py-3 text-text-secondary text-right">{h.duration}</td>
                <td className="px-5 py-3"><PlatformBadge platform={h.platform} /></td>
                <td className="px-5 py-3 text-text-dim text-right text-xs">{h.closedAt}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    OPEN: 'bg-accent/20 text-accent',
    FILLED: 'bg-long/20 text-long',
    CANCELLED: 'bg-text-dim/20 text-text-dim',
    PENDING: 'bg-warm-muted text-warm',
  };
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-semibold ${colors[status] ?? 'bg-text-dim/20 text-text-dim'}`}>
      {status}
    </span>
  );
}

function PlatformBadge({ platform }: { platform: string }) {
  const isHL = platform === 'Hyperliquid';
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${
      isHL ? 'bg-accent/10 text-accent' : 'bg-warm-muted text-warm'
    }`}>
      {isHL ? 'Hyperliquid' : 'Solana'}
    </span>
  );
}
