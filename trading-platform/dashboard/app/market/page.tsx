'use client';
import { getLivePrices } from '@/lib/prices';
import { useState, useEffect, useCallback, useRef } from 'react';
import AppShell from '@/components/layout/AppShell';
import CandlestickChart from '@/components/chart/CandlestickChart';
import { fetchTickers, fetchCandles, fetchOrderBook } from '@/lib/api';
import type { TickerPrice, Candle, OrderBookEntry } from '@/lib/api';
import {
  Clock,
  TrendingUp,
  TrendingDown,
  BarChart3,
  ArrowUpRight,
  ArrowDownRight,
} from 'lucide-react';

function formatPrice(price: number) {
  if (price < 1) return price.toFixed(6);
  if (price < 10) return price.toFixed(4);
  if (price < 1000) return price.toFixed(2);
  return price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatN(n: number) {
  if (n >= 1e9) return (n / 1e9).toFixed(1) + 'B';
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
  return n.toLocaleString();
}

const TIMEFRAMES = [
  { label: '1m', value: '1m' },
  { label: '5m', value: '5m' },
  { label: '15m', value: '15m' },
  { label: '1h', value: '1h' },
  { label: '4h', value: '4h' },
  { label: '1d', value: '1d' },
  { label: '1w', value: '1w' },
];

export default function MarketPage() {
  const [tickers, setTickers] = useState<TickerPrice[]>([]);
  const [selected, setSelected] = useState('BTC-PERP');
  const [candles, setCandles] = useState<Candle[]>([]);
  const [bids, setBids] = useState<OrderBookEntry[]>([]);
  const [asks, setAsks] = useState<OrderBookEntry[]>([]);
  const [interval, setIntervalState] = useState('5m');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [chartLoading, setChartLoading] = useState(false);
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());
  const [priceFlash, setPriceFlash] = useState<'up' | 'down' | null>(null);
  const [chartHeight, setChartHeight] = useState(300);

  // Responsive chart height
  useEffect(() => {
    const update = () => {
      const w = window.innerWidth;
      if (w < 480) setChartHeight(260);
      else if (w < 640) setChartHeight(320);
      else setChartHeight(400);
    };
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, []);

  const filteredTickers = tickers.filter(t =>
    t.symbol.toLowerCase().includes(search.toLowerCase())
  );

  const loadTickers = useCallback(async () => {
    try {
      const t = await getLivePrices();
      setTickers(prev => {
        if (prev.length > 0 && t.length > 0) {
          const prevMap = new Map(prev.map(p => [p.symbol, p]));
          for (const ticker of t) {
            const prevTicker = prevMap.get(ticker.symbol);
            if (prevTicker && ticker.symbol === selected) {
              if (ticker.price > prevTicker.price) setPriceFlash('up');
              else if (ticker.price < prevTicker.price) setPriceFlash('down');
            }
          }
        }
        return t;
      });
      setLastUpdate(new Date());
    } catch (e) {
      console.error('Failed to fetch tickers:', e);
    }
  }, [selected]);

  const loadCandlesAndOB = useCallback(async (symbol: string, tf: string) => {
    setChartLoading(true);
    try {
      const [c, ob] = await Promise.all([
        fetchCandles(symbol, tf),
        fetchOrderBook(symbol),
      ]);
      setCandles(c);
      setBids(ob.bids);
      setAsks(ob.asks);
    } catch (e) {
      console.error('Failed to fetch candles/orderbook:', e);
    } finally {
      setChartLoading(false);
    }
  }, []);

  useEffect(() => {
    loadTickers();
    const id = setInterval(loadTickers, 10000);
    return () => clearInterval(id);
  }, [loadTickers]);

  useEffect(() => {
    if (tickers.length > 0) setLoading(false);
  }, [tickers.length]);

  useEffect(() => {
    if (tickers.length === 0) return;
    loadCandlesAndOB(selected, interval);
  }, [selected, interval, tickers.length, loadCandlesAndOB]);

  useEffect(() => {
    if (!priceFlash) return;
    const timer = setTimeout(() => setPriceFlash(null), 500);
    return () => clearTimeout(timer);
  }, [priceFlash]);

  const current = tickers.find(t => t.symbol === selected);
  const midPrice = bids.length > 0
    ? (bids[0].price + (asks[0]?.price ?? bids[0].price)) / 2
    : current?.price ?? 0;

  return (
    <AppShell>
      <div className="space-y-3 sm:space-y-4">

        {/* Page Header — compact on mobile */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 sm:w-7 sm:h-7 rounded-md bg-neon-cyan/[0.08] flex items-center justify-center border border-bg-border/80 shrink-0">
              <BarChart3 className="w-3 h-3 sm:w-3.5 sm:h-3.5 text-neon-cyan" />
            </div>
            <div className="min-w-0">
              <h2 className="text-sm sm:text-base font-bold text-text tracking-tight">Market</h2>
            </div>
          </div>

          {/* Search — compact on mobile */}
          <div className="relative">
            <input
              type="text"
              placeholder="Symbol..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-24 sm:w-40 lg:w-56 pl-3 pr-7 py-1.5 bg-bg-elevated border border-bg-border rounded-md text-xs sm:text-sm text-text placeholder:text-text-dim focus:outline-none focus:border-neon-cyan/50 transition-all"
            />
            {search && (
              <button
                onClick={() => setSearch('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-text-dim hover:text-text text-xs"
              >
                ✕
              </button>
            )}
          </div>
        </div>

        {/* Ticker Strip — horizontal scroller */}
        <div className="flex gap-1.5 overflow-x-auto pb-1 -mx-1 px-1 snap-x snap-mandatory scrollbar-hide">
          {filteredTickers.length === 0 && search && (
            <p className="text-xs text-text-dim py-2 px-1">No symbols match &quot;{search}&quot;</p>
          )}
          {filteredTickers.map(t => (
            <button
              key={t.symbol}
              onClick={() => setSelected(t.symbol)}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-sm transition-all whitespace-nowrap snap-start min-w-[100px] active:scale-[0.98] ${
                selected === t.symbol
                  ? 'bg-neon-cyan/[0.1] border-neon-cyan/40 text-text'
                  : 'bg-bg-card border-bg-border hover:border-bg-border-light active:bg-bg-elevated'
              }`}
            >
              <span className="font-semibold text-text text-xs">{t.symbol.replace('-PERP','')}</span>
              <span className={`font-mono text-[11px] ${t.change24h >= 0 ? 'text-neon-cyan' : 'text-neon-pink'}`}>
                ${formatPrice(t.price)}
              </span>
              <span className={`text-[10px] font-mono font-medium ${
                t.change24h >= 0 ? 'text-neon-cyan' : 'text-neon-pink'
              }`}>
                {t.change24h >= 0 ? '+' : ''}{Math.abs(t.change24h).toFixed(1)}%
              </span>
            </button>
          ))}
        </div>

        {/* Chart + Order Book */}
        <div className="grid grid-cols-1 xl:grid-cols-4 gap-3 sm:gap-4">
          {/* Chart Area */}
          <div className="xl:col-span-3 bg-bg-card rounded-lg border border-bg-border">
            {/* Chart Header — price + timeframes */}
            <div className="flex flex-col gap-2 p-2 sm:p-3 sm:gap-3">
              <div className="flex items-baseline sm:items-center justify-between gap-2">
                <div className="flex items-baseline gap-2 min-w-0">
                  <span className="text-xs sm:text-sm font-semibold text-text font-mono shrink-0">{selected}</span>
                  {current && (
                    <span className={`font-mono text-2xl sm:text-3xl font-bold tracking-tight transition-colors ${
                      priceFlash === 'up' ? 'text-neon-cyan' :
                      priceFlash === 'down' ? 'text-neon-pink' :
                      current.change24h >= 0 ? 'text-neon-cyan' : 'text-neon-pink'
                    }`}>
                      ${formatPrice(current.price)}
                    </span>
                  )}
                </div>
                {current && (
                  <span className={`flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full shrink-0 ${
                    current.change24h >= 0 ? 'bg-neon-cyan/[0.1] text-neon-cyan' : 'bg-neon-pink/[0.1] text-neon-pink'
                  }`}>
                    {current.change24h >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                    {current.change24h >= 0 ? '+' : ''}{current.change24h.toFixed(1)}%
                  </span>
                )}
              </div>

              {/* Timeframe pills */}
              <div className="flex gap-0.5 bg-bg-elevated p-0.5 rounded-lg border border-bg-border overflow-x-auto scrollbar-hide">
                {TIMEFRAMES.map(tf => (
                  <button
                    key={tf.value}
                    onClick={() => setIntervalState(tf.value)}
                    className={`px-3 py-1 text-xs rounded-md font-medium transition-all whitespace-nowrap min-w-[36px] active:scale-95 ${
                      interval === tf.value
                        ? 'bg-neon-cyan text-bg-primary shadow-sm'
                        : 'text-text-dim hover:text-text hover:bg-bg-hover'
                    }`}
                  >
                    {tf.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Chart */}
            <div className="px-2 pb-2">
              {chartLoading ? (
                <div className="flex items-center justify-center" style={{ height: `${chartHeight}px` }}>
                  <div className="cyber-spinner" />
                </div>
              ) : (
                <CandlestickChart data={candles} height={chartHeight} />
              )}
            </div>
          </div>

          {/* Order Book — hidden on mobile */}
          <div className="hidden xl:block bg-bg-card rounded-lg border border-bg-border">
            <div className="px-4 py-3 border-b border-bg-border flex items-center justify-between">
              <h3 className="text-xs font-semibold text-text tracking-tight font-mono uppercase">Order Book</h3>
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-neon-cyan opacity-60"></span>
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-neon-cyan"></span>
              </span>
            </div>
            <div className="px-1 py-2">
              <div className="flex justify-between text-[10px] text-text-dim mb-1 px-2 font-medium uppercase tracking-wider font-mono">
                <span>Price</span><span>Size</span>
              </div>
              <div className="space-y-px max-h-[180px] overflow-y-auto font-mono text-xs mb-1 scrollbar-thin">
                {asks.slice().reverse().map((a, i) => {
                  const depth = asks.reduce((sum, x) => sum + x.size, 0);
                  const pct = Math.min(a.size / depth * 100 * 3, 60);
                  return (
                    <div key={`ask-${i}`} className="flex justify-between px-2 py-0.5 text-neon-pink relative group hover:bg-bg-hover rounded cursor-default">
                      <span className="absolute inset-0 bg-neon-pink/[0.06] rounded" style={{ right: `${100 - pct}%` }} />
                      <span className="relative z-10">{formatPrice(a.price)}</span>
                      <span className="relative z-10">{a.size.toFixed(4)}</span>
                    </div>
                  );
                })}
              </div>
              <div className="flex items-center justify-center py-2 border-y border-bg-border my-1">
                <span className={`text-sm font-bold font-mono ${(current?.change24h ?? 0) >= 0 ? 'text-neon-cyan' : 'text-neon-pink'}`}>
                  ${formatPrice(midPrice)}
                </span>
              </div>
              <div className="space-y-px max-h-[180px] overflow-y-auto font-mono text-xs mt-1 scrollbar-thin">
                {bids.map((b, i) => {
                  const depth = bids.reduce((sum, x) => sum + x.size, 0);
                  const pct = Math.min(b.size / depth * 100 * 3, 60);
                  return (
                    <div key={`bid-${i}`} className="flex justify-between px-2 py-0.5 text-neon-cyan relative group hover:bg-bg-hover rounded cursor-default">
                      <span className="absolute inset-0 bg-neon-cyan/[0.06] rounded" style={{ right: `${100 - pct}%` }} />
                      <span className="relative z-10">{formatPrice(b.price)}</span>
                      <span className="relative z-10">{b.size.toFixed(4)}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>

        {/* Stats Row — horizontal scroll on mobile, grid on desktop */}
        {current && (() => {
          const stats = [
            { label: '24h High', value: `$${formatPrice(current.high24h)}`, icon: <ArrowUpRight className="w-3 h-3" /> },
            { label: '24h Low', value: `$${formatPrice(current.low24h)}`, icon: <ArrowDownRight className="w-3 h-3" /> },
            { label: 'Change', value: `${current.change24h >= 0 ? '+' : ''}${current.change24h.toFixed(2)}%`, color: current.change24h >= 0 ? 'text-neon-cyan' : 'text-neon-pink', icon: current.change24h >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" /> },
            { label: 'Volume', value: `$${formatN(current.volume24h)}`, icon: <BarChart3 className="w-3 h-3" /> },
            { label: 'Mark', value: `$${formatPrice(midPrice)}`, icon: <span className="text-neon-cyan text-xs">◎</span> },
            { label: 'Spread', value: asks.length > 0 && bids.length > 0
              ? `${((asks[0].price - bids[0].price) / midPrice * 100).toFixed(3)}%`
              : '—', icon: <span className="text-text-dim text-xs">↔</span> },
          ];
          return (
            <>
              {/* Mobile: horizontal scroll cards */}
              <div className="flex gap-2 overflow-x-auto pb-1 sm:hidden scrollbar-hide">
                {stats.map(m => (
                  <div key={m.label} className="card-hover p-3 shrink-0" style={{ width: 'calc(50vw - 12px)' }}>
                    <div className="flex items-center gap-1 text-[9px] text-text-dim mb-1 font-mono uppercase tracking-wider">
                      <span className="opacity-70">{m.icon}</span>
                      {m.label}
                    </div>
                    <div className={`text-sm font-mono font-semibold text-text ${m.color ?? ''}`}>
                      {m.value}
                    </div>
                  </div>
                ))}
              </div>
              {/* Desktop: grid */}
              <div className="hidden sm:grid sm:grid-cols-3 lg:grid-cols-6 gap-2 sm:gap-3">
                {stats.map(m => (
                  <div key={m.label} className="card-hover p-4">
                    <div className="flex items-center gap-1.5 text-[10px] text-text-dim mb-1.5 font-mono uppercase tracking-wider">
                      <span className="opacity-70">{m.icon}</span>
                      {m.label}
                    </div>
                    <div className={`text-sm font-mono font-semibold text-text ${m.color ?? ''}`}>
                      {m.value}
                    </div>
                  </div>
                ))}
              </div>
            </>
          );
        })()}
      </div>
    </AppShell>
  );
}
