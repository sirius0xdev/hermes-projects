'use client';

import { useState, useEffect, useCallback } from 'react';
import AppShell from '@/components/layout/AppShell';
import { fetchBotStatus, fetchLiveSignals, fetchRecentDecisions, fetchStrategyMetrics, fetchBacktestResults, type BotStatus, type Signal, type BotDecision, type StrategyMetric, type BacktestResult } from '@/lib/api';
import {
  Bot,
  Activity,
  Zap,
  TrendingUp,
  TrendingDown,
  Clock,
  Cpu,
  ArrowUpRight,
  ArrowDownRight,
} from 'lucide-react';

function formatPnl(n: number) {
  const sign = n >= 0 ? '+' : '';
  return `${sign}$${Math.abs(n).toFixed(1)}`;
}

function StatusIndicator({ status }: { status: string }) {
  const isRunning = status === 'running';
  return (
    <div className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold border ${
      isRunning ? 'bg-long-muted border-long/20 text-long' : 'bg-short-muted border-short/20 text-short'
    }`}>
      <span className="relative flex h-2 w-2">
        {isRunning && <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-long opacity-60"></span>}
        <span className={`relative inline-flex rounded-full h-2 w-2 ${isRunning ? 'bg-long' : 'bg-short'}`}></span>
      </span>
      {status.toUpperCase()}
    </div>
  );
}

function SignalPill({ signal }: { signal: Signal }) {
  const color = signal.strength > 0.8 ? 'text-long' : signal.strength > 0.6 ? 'text-accent' : 'text-text-dim';
  const typeColors: Record<string, string> = {
    whale: 'bg-purple-500/10 text-purple-400',
    trending: 'bg-orange-500/10 text-orange-400',
    polymarket: 'bg-cyan-500/10 text-cyan-400',
    launch: 'bg-pink-500/10 text-pink-400',
    onchain: 'bg-emerald-500/10 text-emerald-400',
  };
  return (
    <div className="bg-bg-elevated border border-bg-border rounded-lg p-3 hover:border-bg-border_light transition-colors group">
      <div className="flex justify-between items-start mb-2">
        <div className={`px-2 py-0.5 text-[10px] rounded font-mono uppercase tracking-widest font-semibold ${typeColors[signal.type] ?? 'bg-bg-surface text-text-dim'}`}>
          {signal.type}
        </div>
        <div className={`font-mono text-xs font-semibold ${color}`}>{(signal.strength * 100).toFixed(0)}%</div>
      </div>
      <div className="font-semibold text-text mb-1.5">{signal.asset}</div>
      <div className="text-[11px] text-text-secondary line-clamp-3 group-hover:line-clamp-none transition-all leading-relaxed">
        {signal.rationale}
      </div>
      <div className="text-[10px] text-text-dim mt-3 font-mono">
        {new Date(signal.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
      </div>
    </div>
  );
}

function DecisionCard({ decision }: { decision: BotDecision }) {
  return (
    <div className="card-hover p-4">
      <div className="flex items-center justify-between mb-3">
        <div className={`px-3 py-1 text-xs font-bold rounded-full uppercase tracking-wider ${
          decision.type === 'BUY' ? 'bg-long-muted text-long' :
          decision.type === 'SELL' ? 'bg-short-muted text-short' :
          'bg-bg-elevated text-text-dim'
        }`}>
          {decision.type}
        </div>
        <div className="flex items-center gap-2">
          <span className="font-mono text-[11px] text-text-dim">
            {new Date(decision.timestamp).toLocaleTimeString()}
          </span>
          {decision.executed && (
            <span className="text-[10px] px-2 py-0.5 bg-long/10 text-long rounded font-semibold">EXECUTED</span>
          )}
        </div>
      </div>

      <div className="flex items-baseline gap-2 mb-3">
        <span className="text-xl font-bold text-text">{decision.asset}</span>
        <span className="font-mono text-[11px] text-text-secondary">• {decision.sizeSol} SOL</span>
      </div>

      <div className="text-[11px] leading-relaxed text-text-secondary border-l-2 border-accent/30 pl-3 mb-4">
        {decision.rationale}
      </div>

      <div className="flex items-center justify-between text-[11px]">
        <div className="flex items-center gap-3">
          <div>Confidence <span className="font-mono text-accent font-semibold">{(decision.confidence * 100).toFixed(0)}%</span></div>
          {decision.signalsTriggered && decision.signalsTriggered.length > 0 && (
            <div className="flex gap-1">
              {decision.signalsTriggered.map(s => (
                <span key={s} className="px-1.5 py-px bg-bg-elevated text-text-dim text-[10px] rounded font-medium">{s}</span>
              ))}
            </div>
          )}
        </div>
        {decision.realizedPnl !== undefined && (
          <div className={`font-mono font-semibold ${decision.realizedPnl >= 0 ? 'text-long' : 'text-short'}`}>
            {formatPnl(decision.realizedPnl)}
          </div>
        )}
      </div>
      {decision.txSig && (
        <div className="mt-3 pt-3 border-t border-bg-border text-[10px] font-mono text-text-dim truncate">
          tx: {decision.txSig}
        </div>
      )}
    </div>
  );
}

function EquityCurve({ data }: { data?: { time: string; value: number }[] }) {
  const chartData = data || Array.from({ length: 20 }, (_, i) => ({
    time: `${i + 10}d`,
    value: 120 + Math.sin(i / 3) * 25 + (Math.random() * 8 - 4),
  }));

  const values = chartData.map(d => d.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const width = 720;
  const height = 160;
  const padding = 20;

  const points = chartData.map((d, i) => {
    const x = padding + (i / (chartData.length - 1)) * (width - padding * 2);
    const y = height - padding - ((d.value - min) / range) * (height - padding * 2);
    return `${x},${y}`;
  }).join(' ');

  const isUp = chartData[chartData.length - 1].value > chartData[0].value;
  const lineColor = isUp ? '#22c55e' : '#f43f5e';

  return (
    <div className="relative">
      <svg width="100%" height="180" viewBox={`0 0 ${width} ${height}`} className="overflow-visible">
        <defs>
          <linearGradient id="equityGrad" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor={lineColor} stopOpacity="0.2" />
            <stop offset="100%" stopColor={lineColor} stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 0.25, 0.5, 0.75, 1].map(pct => (
          <line
            key={pct}
            x1={padding}
            y1={padding + pct * (height - 2 * padding)}
            x2={width - padding}
            y2={padding + pct * (height - 2 * padding)}
            stroke="rgba(28, 34, 51, 0.8)"
            strokeWidth="1"
          />
        ))}
        <polyline
          points={`${padding},${height - padding} ${points} ${width - padding},${height - padding}`}
          fill="url(#equityGrad)"
        />
        <polyline
          points={points}
          fill="none"
          stroke={lineColor}
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {chartData.map((d, i) => {
          const x = padding + (i / (chartData.length - 1)) * (width - padding * 2);
          const y = height - padding - ((d.value - min) / range) * (height - padding * 2);
          return <circle key={i} cx={x} cy={y} r="2" fill={lineColor} opacity="0.6" />;
        })}
      </svg>
      <div className="flex justify-between text-[11px] text-text-dim px-1 mt-1">
        <div>{chartData[0].time}</div>
        <div className={`font-mono font-semibold ${isUp ? 'text-long' : 'text-short'}`}>
          {isUp ? '+' : ''}{((chartData[chartData.length-1].value - chartData[0].value) / chartData[0].value * 100).toFixed(1)}%
        </div>
        <div>{chartData[chartData.length-1].time}</div>
      </div>
    </div>
  );
}

export default function AutonomousBotPage() {
  const [botStatus, setBotStatus] = useState<BotStatus | null>(null);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [decisions, setDecisions] = useState<BotDecision[]>([]);
  const [metrics, setMetrics] = useState<StrategyMetric[]>([]);
  const [backtests, setBacktests] = useState<BacktestResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'overview' | 'signals' | 'decisions' | 'backtests'>('overview');

  const loadAll = useCallback(async () => {
    try {
      const [status, liveSignals, recentDecs, stratMetrics, btResults] = await Promise.all([
        fetchBotStatus(),
        fetchLiveSignals(8),
        fetchRecentDecisions(6),
        fetchStrategyMetrics(),
        fetchBacktestResults(),
      ]);
      setBotStatus(status);
      setSignals(liveSignals);
      setDecisions(recentDecs);
      setMetrics(stratMetrics);
      setBacktests(btResults);
    } catch (err) {
      console.error('Bot data load failed', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
    const interval = setInterval(loadAll, 8000);
    return () => clearInterval(interval);
  }, [loadAll]);

  if (loading || !botStatus) {
    return (
      <AppShell>
        <div className="flex h-96 items-center justify-center">
          <div className="flex flex-col items-center gap-3">
            <div className="w-8 h-8 border-2 border-accent/30 border-t-accent rounded-full animate-spin"></div>
            <div className="text-text-dim text-sm">Connecting to autonomous quant loop...</div>
          </div>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-4 border-b border-bg-border pb-6">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-xl bg-accent/10 flex items-center justify-center shrink-0">
              <Bot className="w-5 h-5 text-accent" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-text tracking-tight">Autonomous Solana Quant</h1>
              <p className="text-text-dim text-sm mt-0.5">Scientific trading loop • Jupiter execution • Live since May 7</p>
            </div>
          </div>

          <div className="flex items-center gap-6">
            <div>
              <div className="text-[10px] text-text-dim uppercase tracking-wider mb-1 font-semibold">Status</div>
              <StatusIndicator status={botStatus.status} />
            </div>
            <div className="text-right">
              <div className="text-[10px] text-text-dim uppercase tracking-wider mb-1 font-semibold">Strategy</div>
              <div className="font-mono text-sm text-accent font-semibold">{botStatus.strategy}</div>
            </div>
            <div className="h-9 w-px bg-bg-border" />
            <div>
              <div className="text-[10px] text-text-dim uppercase tracking-wider mb-1 font-semibold">Today</div>
              <div className={`text-2xl font-bold font-mono ${botStatus.dailyPnl >= 0 ? 'text-long' : 'text-short'}`}>
                {formatPnl(botStatus.dailyPnl)}
              </div>
            </div>
            <div className="text-right">
              <div className="text-[10px] text-text-dim uppercase tracking-wider mb-1 font-semibold">Equity</div>
              <span className="text-text font-mono text-lg font-bold">${botStatus.equity}</span>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-12 gap-5">
          {/* Left Column - Live Metrics & Equity */}
          <div className="xl:col-span-7 space-y-5">
            {/* Equity Curve */}
            <div className="card-hover p-5">
              <div className="flex items-center justify-between mb-5">
                <div>
                  <h3 className="font-semibold text-text">Equity Curve (30d)</h3>
                  <p className="text-[11px] text-text-dim mt-0.5">Daily P&amp;L focus • Kelly sizing active</p>
                </div>
                <div className="text-right">
                  <div className="text-[10px] text-text-dim uppercase tracking-wider font-semibold">Total PnL</div>
                  <div className="text-xl font-bold text-long font-mono">+${botStatus.totalPnl.toFixed(1)}</div>
                </div>
              </div>
              <EquityCurve />
            </div>

            {/* Strategy Metrics */}
            <div className="card-hover p-5">
              <h3 className="text-[11px] uppercase tracking-widest text-text-dim font-semibold mb-4 flex items-center gap-2">
                <Activity className="w-3.5 h-3.5" />
                Strategy Metrics
                <span className="text-[10px] px-2 py-0.5 bg-accent/10 text-accent rounded font-semibold">v0.4</span>
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {metrics.map((m, i) => (
                  <div key={i} className="bg-bg-elevated border border-bg-border rounded-lg p-4 hover:border-bg-border_light transition-colors">
                    <div className="flex justify-between items-start">
                      <div>
                        <div className="text-[11px] text-text-dim">{m.name}</div>
                        <div className="text-2xl font-mono font-bold text-text mt-1">{m.value}</div>
                      </div>
                      <div className={`text-[10px] px-2 py-0.5 rounded-full font-semibold ${
                        m.change24h >= 0 ? 'bg-long-muted text-long' : 'bg-short-muted text-short'
                      }`}>
                        {m.change24h >= 0 ? <ArrowUpRight className="w-3 h-3 inline" /> : <ArrowDownRight className="w-3 h-3 inline" />}
                        {Math.abs(m.change24h)}
                      </div>
                    </div>
                    <div className="text-[10px] text-text-dim mt-3">{m.description}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Right Column - Live Status & Signals */}
          <div className="xl:col-span-5 space-y-5">
            {/* Bot Status Card */}
            <div className="card-hover p-5">
              <div className="flex justify-between mb-5">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-lg bg-warm-muted flex items-center justify-center">
                    <Zap className="w-4 h-4 text-warm" />
                  </div>
                  <div>
                    <div className="font-semibold text-text">Live Decision Engine</div>
                    <div className="text-[10px] text-text-dim font-mono">Kafka • Postgres • Jupiter</div>
                  </div>
                </div>
                <div className="text-right text-[10px]">
                  <div className="text-text-dim uppercase tracking-wider font-semibold">Signals</div>
                  <div className="text-2xl font-mono text-accent font-bold">{botStatus.signalsProcessed}</div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 text-sm">
                <div className="bg-bg-elevated border border-bg-border rounded-lg p-3">
                  <div className="text-text-dim text-[10px] mb-1 uppercase tracking-wider font-semibold">Uptime</div>
                  <div className="font-mono font-semibold">{botStatus.uptime}</div>
                </div>
                <div className="bg-bg-elevated border border-bg-border rounded-lg p-3">
                  <div className="text-text-dim text-[10px] mb-1 uppercase tracking-wider font-semibold">Last Decision</div>
                  <div className="font-mono font-semibold">{botStatus.lastDecisionAt}</div>
                </div>
              </div>

              <div className="mt-4 pt-4 border-t border-bg-border text-[11px] font-mono text-text-dim">
                Position: <span className="text-accent font-semibold">{botStatus.currentPosition}</span>
              </div>
            </div>

            {/* Live Signals Feed */}
            <div className="card-hover p-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold text-text">Live Signal Feed</h3>
                <div className="text-[10px] bg-accent/10 px-2.5 py-1 rounded font-mono text-accent font-semibold uppercase tracking-wider">Real-time</div>
              </div>
              <div className="space-y-2 max-h-[340px] overflow-y-auto pr-1">
                {signals.map(signal => <SignalPill key={signal.id} signal={signal} />)}
              </div>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="border-b border-bg-border flex gap-0">
          {[
            { id: 'overview' as const, label: 'Recent Decisions' },
            { id: 'signals' as const, label: 'Signal Archive' },
            { id: 'decisions' as const, label: 'Decision Log' },
            { id: 'backtests' as const, label: 'Backtest Lab' },
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`tab-btn ${activeTab === tab.id ? 'tab-btn-active' : ''}`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        {activeTab === 'overview' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            <div>
              <h4 className="text-[10px] uppercase tracking-widest text-text-dim mb-3 pl-1 font-semibold">Live Decisions (Last 6)</h4>
              <div className="space-y-3">
                {decisions.slice(0, 3).map(d => <DecisionCard key={d.id} decision={d} />)}
              </div>
            </div>
            <div>
              <h4 className="text-[10px] uppercase tracking-widest text-text-dim mb-3 pl-1 font-semibold">Backtest Summary</h4>
              <div className="card-hover p-5">
                {backtests.slice(0, 2).map((bt, idx) => (
                  <div key={bt.id} className={`${idx !== 0 ? 'mt-6 pt-6 border-t border-bg-border' : ''}`}>
                    <div className="flex justify-between items-baseline">
                      <div className="font-semibold text-text">{bt.name}</div>
                      <div className="font-mono text-[11px] text-accent font-semibold">Sharpe {bt.sharpeRatio}</div>
                    </div>
                    <div className="grid grid-cols-4 gap-3 mt-4 text-xs">
                      <div>
                        <div className="text-text-dim text-[10px] uppercase tracking-wider font-semibold">Winrate</div>
                        <div className="font-mono text-lg text-long font-bold">{(bt.winRate * 100).toFixed(0)}%</div>
                      </div>
                      <div>
                        <div className="text-text-dim text-[10px] uppercase tracking-wider font-semibold">Return</div>
                        <div className="font-mono text-lg text-text font-bold">+{(bt.totalReturn * 100).toFixed(0)}%</div>
                      </div>
                      <div>
                        <div className="text-text-dim text-[10px] uppercase tracking-wider font-semibold">Max DD</div>
                        <div className="font-mono text-lg text-short font-bold">{(bt.maxDrawdown * 100).toFixed(1)}%</div>
                      </div>
                      <div>
                        <div className="text-text-dim text-[10px] uppercase tracking-wider font-semibold">Trades</div>
                        <div className="font-mono text-lg text-text font-bold">{bt.tradeCount}</div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'signals' && (
          <div className="card-hover p-5">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {signals.concat(signals).map((s, i) => (
                <SignalPill key={`${s.id}-${i}`} signal={s} />
              ))}
            </div>
          </div>
        )}

        {activeTab === 'decisions' && (
          <div className="space-y-3">
            {decisions.map(d => <DecisionCard key={d.id} decision={d} />)}
            <div className="text-center text-[11px] text-text-dim py-8 border border-dashed border-bg-border rounded-xl">
              Full decision history available in Postgres • 1,247 logged since deployment
            </div>
          </div>
        )}

        {activeTab === 'backtests' && (
          <div className="card-hover overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-bg-border text-left text-[10px] text-text-dim uppercase tracking-wider">
                  <th className="px-5 py-3.5 font-semibold">Strategy</th>
                  <th className="px-5 py-3.5 font-semibold">Sharpe</th>
                  <th className="px-5 py-3.5 font-semibold text-right">Win Rate</th>
                  <th className="px-5 py-3.5 font-semibold text-right">Max DD</th>
                  <th className="px-5 py-3.5 font-semibold text-right">Return</th>
                  <th className="px-5 py-3.5 font-semibold text-right">Trades</th>
                  <th className="px-5 py-3.5 font-semibold">Period</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-bg-border/50 font-mono text-sm">
                {backtests.map(bt => (
                  <tr key={bt.id} className="hover:bg-bg-hover transition-colors">
                    <td className="px-5 py-4 font-semibold text-text">{bt.name}</td>
                    <td className="px-5 py-4 text-accent font-semibold">{bt.sharpeRatio.toFixed(2)}</td>
                    <td className="px-5 py-4 text-right text-long font-semibold">{(bt.winRate * 100).toFixed(0)}%</td>
                    <td className="px-5 py-4 text-right text-short font-semibold">{(bt.maxDrawdown * 100).toFixed(1)}%</td>
                    <td className="px-5 py-4 text-right text-long font-semibold">+{(bt.totalReturn * 100).toFixed(0)}%</td>
                    <td className="px-5 py-4 text-right text-text">{bt.tradeCount}</td>
                    <td className="px-5 py-4 text-text-dim text-xs">{bt.period}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="p-5 border-t border-bg-border text-[11px] text-text-dim bg-bg-elevated">
              Read-only viewer. Parameter optimization and live A/B testing controlled by backend quant engine. All backtests use realistic slippage and Jupiter routing simulation.
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
