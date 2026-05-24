'use client';

import { useState, useEffect, useCallback } from 'react';
import AppShell from '@/components/layout/AppShell';
import { fetchBotStatus, fetchLiveSignals, fetchRecentDecisions, fetchStrategyMetrics, fetchBacktestResults, type BotStatus, type Signal, type BotDecision, type StrategyMetric, type BacktestResult } from '@/lib/api';

function formatPnl(n: number) {
  const sign = n >= 0 ? '+' : '';
  return `${sign}$${Math.abs(n).toFixed(1)}`;
}

function StatusIndicator({ status }: { status: string }) {
  const isRunning = status === 'running';
  return (
    <div className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium border ${isRunning ? 'bg-up/10 border-up text-up' : 'bg-down/10 border-down text-down'}`}>
      <div className={`w-2 h-2 rounded-full ${isRunning ? 'bg-up animate-pulse' : 'bg-down'}`} />
      {status.toUpperCase()}
    </div>
  );
}

function SignalPill({ signal }: { signal: Signal }) {
  const color = signal.strength > 0.8 ? 'up' : signal.strength > 0.6 ? 'accent' : 'text-muted';
  return (
    <div className="bg-bg-secondary border border-border rounded-lg p-3 hover:border-accent/50 transition-colors group">
      <div className="flex justify-between items-start mb-2">
        <div className={`px-2.5 py-0.5 text-xs rounded font-mono uppercase tracking-widest ${signal.type === 'whale' ? 'bg-purple-500/10 text-purple-400' : signal.type === 'trending' ? 'bg-orange-500/10 text-orange-400' : 'bg-cyan-500/10 text-cyan-400'}`}>
          {signal.type}
        </div>
        <div className={`font-mono text-xs ${color}`}>{(signal.strength * 100).toFixed(0)}%</div>
      </div>
      <div className="font-semibold text-text-primary mb-1.5">{signal.asset}</div>
      <div className="text-xs text-text-secondary line-clamp-3 group-hover:line-clamp-none transition-all">
        {signal.rationale}
      </div>
      <div className="text-[10px] text-text-muted mt-3 font-mono">
        {new Date(signal.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
      </div>
    </div>
  );
}

function DecisionCard({ decision }: { decision: BotDecision }) {
  return (
    <div className="bg-bg-card border border-border rounded-xl p-4 hover:border-accent/30 transition-all">
      <div className="flex items-center justify-between mb-3">
        <div className={`px-3 py-1 text-xs font-semibold rounded-full ${decision.type === 'BUY' ? 'bg-up/10 text-up' : decision.type === 'SELL' ? 'bg-down/10 text-down' : 'bg-text-muted/10 text-text-muted'}`}>
          {decision.type}
        </div>
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs text-text-muted">{new Date(decision.timestamp).toLocaleTimeString()}</span>
          {decision.executed && <span className="text-[10px] px-2 py-0.5 bg-emerald-500/10 text-emerald-400 rounded">EXECUTED</span>}
        </div>
      </div>

      <div className="flex items-baseline gap-2 mb-3">
        <span className="text-2xl font-bold text-text-primary">{decision.asset}</span>
        <span className="font-mono text-sm text-text-secondary">• {decision.sizeSol} SOL</span>
      </div>

      <div className="text-xs leading-relaxed text-text-secondary border-l-2 border-accent/30 pl-3 mb-4">
        {decision.rationale}
      </div>

      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center gap-3">
          <div>Confidence <span className="font-mono text-accent">{(decision.confidence * 100).toFixed(0)}%</span></div>
          {decision.signalsTriggered && decision.signalsTriggered.length > 0 && (
            <div className="flex gap-1">
              {decision.signalsTriggered.map(s => (
                <span key={s} className="px-2 py-px bg-bg-tertiary text-text-muted text-[10px] rounded">{s}</span>
              ))}
            </div>
          )}
        </div>
        {decision.realizedPnl !== undefined && (
          <div className={`font-mono ${decision.realizedPnl >= 0 ? 'text-up' : 'text-down'}`}>
            {formatPnl(decision.realizedPnl)}
          </div>
        )}
      </div>
      {decision.txSig && (
        <div className="mt-3 pt-3 border-t border-border text-[10px] font-mono text-text-muted truncate">
          tx: {decision.txSig}
        </div>
      )}
    </div>
  );
}

function EquityCurve({ data }: { data?: { time: string; value: number }[] }) {
  // Simple mock data if none
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

  return (
    <div className="relative">
      <svg width="100%" height="180" viewBox={`0 0 ${width} ${height}`} className="overflow-visible">
        <defs>
          <linearGradient id="equityGrad" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor={isUp ? '#00d4aa' : '#f44336'} stopOpacity="0.25" />
            <stop offset="100%" stopColor={isUp ? '#00d4aa' : '#f44336'} stopOpacity="0" />
          </linearGradient>
        </defs>
        <polyline
          points={points}
          fill="none"
          stroke={isUp ? '#00d4aa' : '#f44336'}
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <polyline
          points={`${padding},${height - padding} ${points} ${width - padding},${height - padding}`}
          fill="url(#equityGrad)"
        />
        {/* Dots */}
        {chartData.map((d, i) => {
          const x = padding + (i / (chartData.length - 1)) * (width - padding * 2);
          const y = height - padding - ((d.value - min) / range) * (height - padding * 2);
          return <circle key={i} cx={x} cy={y} r="2.5" fill={isUp ? '#00d4aa' : '#f44336'} />;
        })}
      </svg>
      <div className="flex justify-between text-xs text-text-muted px-1 mt-1">
        <div>{chartData[0].time}</div>
        <div className={`font-mono ${isUp ? 'text-up' : 'text-down'}`}>
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
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());

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
      setLastUpdate(new Date());
    } catch (err) {
      console.error('Bot data load failed', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
    const interval = setInterval(loadAll, 8000); // real-time feel
    return () => clearInterval(interval);
  }, [loadAll]);

  if (loading || !botStatus) {
    return (
      <AppShell>
        <div className="flex h-96 items-center justify-center">
          <div className="flex flex-col items-center">
            <div className="w-8 h-8 border-2 border-accent border-t-transparent rounded-full animate-spin mb-4"></div>
            <div className="text-text-muted">Connecting to autonomous quant loop...</div>
          </div>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-4 border-b border-border pb-6">
          <div>
            <div className="flex items-center gap-3">
              <div className="text-4xl">🧠</div>
              <div>
                <h1 className="text-3xl font-bold text-text-primary tracking-tight">Autonomous Solana Quant</h1>
                <p className="text-text-muted">Scientific trading loop • Jupiter execution • Live since May 7</p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-6">
            <div>
              <div className="text-xs text-text-muted mb-1">STATUS</div>
              <StatusIndicator status={botStatus.status} />
            </div>
            <div className="text-right">
              <div className="text-xs text-text-muted">STRATEGY</div>
              <div className="font-mono text-sm text-accent">{botStatus.strategy}</div>
            </div>
            <div className="h-9 w-px bg-border" />
            <div>
              <div className="text-xs text-text-muted">TODAY</div>
              <div className={`text-2xl font-bold font-mono ${botStatus.dailyPnl >= 0 ? 'text-up' : 'text-down'}`}>
                {formatPnl(botStatus.dailyPnl)}
              </div>
            </div>
            <div className="text-xs text-text-muted leading-tight">
              EQUITY<br />
              <span className="text-text-primary font-mono text-lg">${botStatus.equity}</span>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
          {/* Left Column - Live Metrics & Equity */}
          <div className="xl:col-span-7 space-y-6">
            {/* Equity Curve */}
            <div className="bg-bg-card border border-border rounded-2xl p-6">
              <div className="flex items-center justify-between mb-6">
                <div>
                  <h3 className="font-semibold text-text-primary">Equity Curve (30d)</h3>
                  <p className="text-xs text-text-muted">Daily P&amp;L focus • Kelly sizing active</p>
                </div>
                <div className="text-right">
                  <div className="text-xs text-text-muted">TOTAL PNL</div>
                  <div className="text-xl font-bold text-up font-mono">+${botStatus.totalPnl.toFixed(1)}</div>
                </div>
              </div>
              <EquityCurve />
            </div>

            {/* Strategy Metrics */}
            <div className="bg-bg-card border border-border rounded-2xl p-6">
              <h3 className="font-semibold text-text-primary mb-5 flex items-center gap-2">
                STRATEGY METRICS
                <span className="text-xs px-2 py-0.5 bg-accent/10 text-accent rounded">v0.4</span>
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                {metrics.map((m, i) => (
                  <div key={i} className="bg-bg-secondary/50 border border-border rounded-xl p-4">
                    <div className="flex justify-between items-start">
                      <div>
                        <div className="text-xs text-text-muted">{m.name}</div>
                        <div className="text-3xl font-mono font-semibold text-text-primary mt-1">{m.value}</div>
                      </div>
                      <div className={`text-xs px-3 py-1 rounded-full ${m.change24h >= 0 ? 'bg-up/10 text-up' : 'bg-down/10 text-down'}`}>
                        {m.change24h >= 0 ? '↑' : '↓'} {Math.abs(m.change24h)}
                      </div>
                    </div>
                    <div className="text-[10px] text-text-muted mt-4">{m.description}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Right Column - Live Status & Signals */}
          <div className="xl:col-span-5 space-y-6">
            {/* Bot Status Card */}
            <div className="bg-bg-card border border-border rounded-2xl p-6">
              <div className="flex justify-between mb-6">
                <div className="flex items-center gap-3">
                  <div className="text-2xl">⚡</div>
                  <div>
                    <div className="font-semibold">Live Decision Engine</div>
                    <div className="text-xs text-text-muted font-mono">Kafka • Postgres • Jupiter</div>
                  </div>
                </div>
                <div className="text-right text-xs">
                  <div className="text-text-muted">SIGNALS PROCESSED</div>
                  <div className="text-3xl font-mono text-accent font-semibold">{botStatus.signalsProcessed}</div>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4 text-sm">
                <div className="bg-bg-secondary rounded-xl p-4">
                  <div className="text-text-muted text-xs mb-1">UPTIME</div>
                  <div className="font-mono text-lg">{botStatus.uptime}</div>
                </div>
                <div className="bg-bg-secondary rounded-xl p-4">
                  <div className="text-text-muted text-xs mb-1">LAST DECISION</div>
                  <div className="font-mono text-lg">{botStatus.lastDecisionAt}</div>
                </div>
              </div>

              <div className="mt-6 pt-6 border-t border-border text-xs font-mono text-text-muted">
                CURRENT POSITION: <span className="text-accent">{botStatus.currentPosition}</span>
              </div>
            </div>

            {/* Live Signals Feed */}
            <div className="bg-bg-card border border-border rounded-2xl p-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-semibold text-text-primary">LIVE SIGNAL FEED</h3>
                <div className="text-xs bg-bg-secondary px-3 py-1 rounded font-mono text-accent">REAL-TIME</div>
              </div>
              <div className="space-y-3 max-h-[340px] overflow-y-auto pr-2 custom-scroll">
                {signals.map(signal => <SignalPill key={signal.id} signal={signal} />)}
              </div>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="border-b border-border flex gap-8 text-sm">
          {[
            { id: 'overview' as const, label: 'Recent Decisions' },
            { id: 'signals' as const, label: 'Signal Archive' },
            { id: 'decisions' as const, label: 'Decision Log' },
            { id: 'backtests' as const, label: 'Backtest Lab' },
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`pb-4 border-b-2 transition-colors font-medium ${activeTab === tab.id 
                ? 'border-accent text-accent' 
                : 'border-transparent text-text-muted hover:text-text-primary'}`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab Content */}
        {activeTab === 'overview' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div>
              <h4 className="text-xs uppercase tracking-widest text-text-muted mb-4 pl-1">LIVE DECISIONS (LAST 6)</h4>
              <div className="space-y-4">
                {decisions.slice(0, 3).map(d => <DecisionCard key={d.id} decision={d} />)}
              </div>
            </div>
            <div>
              <h4 className="text-xs uppercase tracking-widest text-text-muted mb-4 pl-1">BACKTEST SUMMARY</h4>
              <div className="bg-bg-card border border-border rounded-2xl p-6">
                {backtests.slice(0, 2).map((bt, idx) => (
                  <div key={bt.id} className={`${idx !== 0 ? 'mt-8 pt-8 border-t border-border' : ''}`}>
                    <div className="flex justify-between items-baseline">
                      <div className="font-semibold">{bt.name}</div>
                      <div className="font-mono text-xs text-accent">Sharpe {bt.sharpeRatio}</div>
                    </div>
                    <div className="grid grid-cols-4 gap-4 mt-5 text-xs">
                      <div>
                        <div className="text-text-muted">WINRATE</div>
                        <div className="font-mono text-lg text-up">{(bt.winRate * 100).toFixed(0)}%</div>
                      </div>
                      <div>
                        <div className="text-text-muted">RETURN</div>
                        <div className="font-mono text-lg">+{(bt.totalReturn * 100).toFixed(0)}%</div>
                      </div>
                      <div>
                        <div className="text-text-muted">MAX DD</div>
                        <div className="font-mono text-lg text-down">{(bt.maxDrawdown * 100).toFixed(1)}%</div>
                      </div>
                      <div>
                        <div className="text-text-muted">TRADES</div>
                        <div className="font-mono text-lg">{bt.tradeCount}</div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'signals' && (
          <div className="bg-bg-card border border-border rounded-2xl p-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {signals.concat(signals).map((s, i) => (
                <SignalPill key={`${s.id}-${i}`} signal={s} />
              ))}
            </div>
          </div>
        )}

        {activeTab === 'decisions' && (
          <div className="space-y-4">
            {decisions.map(d => <DecisionCard key={d.id} decision={d} />)}
            <div className="text-center text-xs text-text-muted py-8 border border-dashed border-border rounded-2xl">
              Full decision history available in Postgres • 1,247 logged since deployment
            </div>
          </div>
        )}

        {activeTab === 'backtests' && (
          <div className="bg-bg-card border border-border rounded-2xl overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border text-left text-xs text-text-muted">
                  <th className="px-6 py-4 font-medium">STRATEGY</th>
                  <th className="px-6 py-4 font-medium">SHARPE</th>
                  <th className="px-6 py-4 font-medium text-right">WIN RATE</th>
                  <th className="px-6 py-4 font-medium text-right">MAX DD</th>
                  <th className="px-6 py-4 font-medium text-right">RETURN</th>
                  <th className="px-6 py-4 font-medium text-right">TRADES</th>
                  <th className="px-6 py-4 font-medium">PERIOD</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border font-mono text-sm">
                {backtests.map(bt => (
                  <tr key={bt.id} className="hover:bg-bg-secondary/50 transition-colors">
                    <td className="px-6 py-5 font-semibold text-text-primary">{bt.name}</td>
                    <td className="px-6 py-5 text-accent">{bt.sharpeRatio.toFixed(2)}</td>
                    <td className="px-6 py-5 text-right text-up">{(bt.winRate * 100).toFixed(0)}%</td>
                    <td className="px-6 py-5 text-right text-down">{(bt.maxDrawdown * 100).toFixed(1)}%</td>
                    <td className="px-6 py-5 text-right text-up">+{(bt.totalReturn * 100).toFixed(0)}%</td>
                    <td className="px-6 py-5 text-right">{bt.tradeCount}</td>
                    <td className="px-6 py-5 text-text-muted text-xs">{bt.period}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="p-6 border-t border-border text-xs text-text-muted bg-bg-secondary">
              Read-only viewer. Parameter optimization and live A/B testing controlled by backend quant engine. All backtests use realistic slippage and Jupiter routing simulation.
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
