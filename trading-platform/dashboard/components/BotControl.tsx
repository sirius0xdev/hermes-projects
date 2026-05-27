'use client';

import { useState, useEffect } from 'react';
import { Play, Square, Settings, TrendingUp, Zap, Target, BarChart3 } from 'lucide-react';

type Strategy = 'meme-sniper' | 'volume-spike' | 'jupiter-arbitrage' | 'drift-perps' | 'solana-vwap';

interface BotStatus {
  running: boolean;
  strategy: Strategy;
  pnl: number;
  tradesToday: number;
  currentPosition: string;
  lastAction: string;
}

export default function BotControl() {
  const [status, setStatus] = useState<BotStatus>({
    running: false,
    strategy: 'meme-sniper',
    pnl: 1240.75,
    tradesToday: 17,
    currentPosition: '4.2 SOL long WIF',
    lastAction: 'Sniped new launch 2m ago',
  });

  const [selectedStrategy, setSelectedStrategy] = useState<Strategy>('meme-sniper');
  const [params, setParams] = useState({
    minVolume: 50000,
    minLiquidity: 25000,
    maxSlippage: 0.8,
    priorityFee: 0.0005,
  });

  const strategies = [
    { id: 'meme-sniper' as Strategy, label: 'Meme Sniper', icon: Zap, desc: 'New launches + volume spike' },
    { id: 'volume-spike' as Strategy, label: 'Volume Spike', icon: TrendingUp, desc: 'Sudden buy pressure' },
    { id: 'jupiter-arbitrage' as Strategy, label: 'Jupiter Arb', icon: BarChart3, desc: 'Cross-DEX routing' },
    { id: 'drift-perps' as Strategy, label: 'Drift Perps', icon: Target, desc: 'Leveraged SOL perps' },
    { id: 'solana-vwap' as Strategy, label: 'Solana VWAP', icon: Settings, desc: 'Session anchored waves' },
  ];

  const toggleBot = () => {
    setStatus(prev => ({ ...prev, running: !prev.running }));
    // In real version this would call the backend executor
    console.log(status.running ? '🛑 Bot stopped' : '🚀 Bot started with ' + selectedStrategy);
  };

  const executeManual = (action: string) => {
    console.log(`Manual ${action} executed via Jupiter/Drift`);
    // Would call SolanaExecutor.swap() or Drift order
  };

  return (
    <div className="bg-zinc-950 border border-zinc-800 rounded-3xl p-6 h-full flex flex-col">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className={`w-3 h-3 rounded-full ${status.running ? 'bg-emerald-400 animate-pulse' : 'bg-zinc-500'}`} />
          <h3 className="font-mono uppercase tracking-widest text-sm text-zinc-400">AUTONOMOUS BOT</h3>
        </div>
        <button
          onClick={toggleBot}
          className={`px-6 py-2 rounded-2xl font-medium flex items-center gap-2 transition-all ${
            status.running 
              ? 'bg-rose-500/10 text-rose-400 hover:bg-rose-500/20' 
              : 'bg-emerald-500 text-black hover:bg-emerald-400'
          }`}
        >
          {status.running ? <Square className="w-4 h-4" /> : <Play className="w-4 h-4" />}
          {status.running ? 'STOP BOT' : 'START BOT'}
        </button>
      </div>

      {/* Strategy Selector */}
      <div className="mb-6">
        <div className="text-xs text-zinc-500 mb-3 font-mono">STRATEGY</div>
        <div className="grid grid-cols-2 gap-2">
          {strategies.map(s => (
            <button
              key={s.id}
              onClick={() => setSelectedStrategy(s.id)}
              className={`p-3 rounded-2xl text-left transition-all flex flex-col gap-1 ${
                selectedStrategy === s.id 
                  ? 'bg-cyan-500/10 border border-cyan-400 text-cyan-300' 
                  : 'bg-zinc-900 hover:bg-zinc-800 border border-transparent'
              }`}
            >
              <div className="flex items-center gap-2">
                <s.icon className="w-4 h-4" />
                <span className="font-medium">{s.label}</span>
              </div>
              <span className="text-[10px] text-zinc-500">{s.desc}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Live Status */}
      <div className="bg-zinc-900 rounded-2xl p-5 mb-6 space-y-4">
        <div className="flex justify-between text-sm">
          <span className="text-zinc-400">PNL Today</span>
          <span className={`font-mono ${status.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
            +${status.pnl.toLocaleString()}
          </span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-zinc-400">Trades</span>
          <span className="font-mono text-cyan-400">{status.tradesToday}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-zinc-400">Position</span>
          <span className="font-mono text-amber-400">{status.currentPosition}</span>
        </div>
        <div className="text-xs text-emerald-400 font-mono border-t border-zinc-800 pt-3">
          {status.lastAction}
        </div>
      </div>

      {/* Parameters */}
      <div className="mb-6">
        <div className="text-xs text-zinc-500 mb-3 font-mono flex items-center justify-between">
          PARAMETERS
          <button onClick={() => alert('Settings saved to bot config')} className="text-cyan-400 text-[10px] hover:underline">SAVE</button>
        </div>
        <div className="space-y-4 text-sm">
          <div>
            <div className="text-zinc-400 text-xs mb-1">MIN VOLUME (USD)</div>
            <input 
              type="range" 
              min="10000" 
              max="250000" 
              step="10000"
              value={params.minVolume}
              onChange={(e) => setParams(p => ({...p, minVolume: +e.target.value}))}
              className="w-full accent-cyan-400"
            />
            <div className="text-right text-xs text-cyan-400 font-mono">${params.minVolume.toLocaleString()}</div>
          </div>
          
          <div>
            <div className="text-zinc-400 text-xs mb-1">MAX SLIPPAGE (%)</div>
            <input 
              type="range" 
              min="0.1" 
              max="3" 
              step="0.1"
              value={params.maxSlippage}
              onChange={(e) => setParams(p => ({...p, maxSlippage: +e.target.value}))}
              className="w-full accent-cyan-400"
            />
            <div className="text-right text-xs text-cyan-400 font-mono">{params.maxSlippage}%</div>
          </div>

          <div>
            <div className="text-zinc-400 text-xs mb-1">PRIORITY FEE (SOL)</div>
            <input 
              type="range" 
              min="0.0001" 
              max="0.005" 
              step="0.0001"
              value={params.priorityFee}
              onChange={(e) => setParams(p => ({...p, priorityFee: +e.target.value}))}
              className="w-full accent-cyan-400"
            />
            <div className="text-right text-xs text-cyan-400 font-mono">{params.priorityFee}</div>
          </div>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="mt-auto pt-6 border-t border-zinc-800">
        <div className="text-xs text-zinc-500 mb-3 font-mono">QUICK EXECUTION</div>
        <div className="grid grid-cols-2 gap-3">
          <button onClick={() => executeManual('BUY SOL')} className="bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/30 text-emerald-400 py-3 rounded-2xl text-sm font-medium transition">BUY SOL</button>
          <button onClick={() => executeManual('SWAP MEME')} className="bg-violet-500/10 hover:bg-violet-500/20 border border-violet-500/30 text-violet-400 py-3 rounded-2xl text-sm font-medium transition">SWAP MEME</button>
          <button onClick={() => executeManual('DRIFT LONG')} className="bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/30 text-cyan-400 py-3 rounded-2xl text-sm font-medium transition">DRIFT LONG</button>
          <button onClick={() => executeManual('JUP ROUTE')} className="bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 text-amber-400 py-3 rounded-2xl text-sm font-medium transition">BEST ROUTE</button>
        </div>
      </div>

      <div className="text-[10px] text-center text-zinc-600 mt-8 mono">
        CONNECTED TO HELIUS RPC • JUPITER V6 • DRIFT PERPS ENABLED
      </div>
    </div>
  );
}
