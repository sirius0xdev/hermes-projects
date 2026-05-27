'use client';
import { getLivePrices } from '@/lib/prices';
import { useState, useEffect, useCallback, useRef } from 'react';
import AppShell from '@/components/layout/AppShell';
import CandlestickChart from '@/components/chart/CandlestickChart';
import { fetchTickers, fetchCandles, fetchOrderBook } from '@/lib/api';
import type { TickerPrice, Candle, OrderBookEntry } from '@/lib/api';
import {
  Search,
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
  const prevPriceRef = useRef<number>(0);
  const [chartHeight, setChartHeight] = useState(380);

  // Responsive chart height
  useEffect(() => {
    const update = () => setChartHeight(window.innerWidth < 640 ? 250 : 380);
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
              if (ticker.price > prevTicker.price) {
                setPriceFlash('up');
              } else if (ticker.price < prevTicker.price) {
                setPriceFlash('down');
              }
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
  }, [tickers]);

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
      <div className="space-y-4">
        {/* Page Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-md bg-neon-cyan/[0.08] flex items-center justify-center neon-border-cyan">
              <BarChart3 className="w-4 h-4 text-neon-cyan" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-text tracking-tight">Market Surveillance</h2>
              <p className="text-[10px] text-text-dim mt-0.5 flex items-center gap-1.5 font-mono">
                <Clock className="w-3 h-3" />
                Updated {lastUpdate.toLocaleTimeString()}
              </p>
            </div>
          </div>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-dim" />
            <input
              type="text"
              placeholder="Search symbol..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full sm:w-56 pl-9 pr-8 py-2 bg-bg-elevated border border-bg-border rounded-md text-sm text-text placeholder:text-text-dim focus:outline-none focus:ring-1 focus:ring-neon-cyan/50 focus:border-neon-cyan transition-all"
            />
            {search && (
              <button
                onClick={() => setSearch('')}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-dim hover:text-text text-xs transition-colors"
              >
                ✕
              </button>
            )}
          </div>
        </div>

        {/* Ticker Strip */}
        <div className="flex flex-wrap items-center gap-2 overflow-x-auto pb-1">
          {filteredTickers.length === 0 && search && (
            <p className="text-sm text-text-dim py-2">No symbols match &quot;{search}&quot;</p>
          )}
          {filteredTickers.map(t => (
            <button
              key={t.symbol}
              onClick={() => setSelected(t.symbol)}
              className={`flex items-center gap-2.5 px-3 py-2 rounded-md border text-sm transition-all duration-150 whitespace-nowrap ${
                selected === t.symbol
                  ? 'bg-neon-cyan/[0.08] neon-border-cyan'
                  : 'bg-bg-card border-bg-border hover:border-bg-border-light'
              }`}
            >
              <span className="font-semibold text-text">{t.symbol}</span>
              <span className={`font-mono text-xs transition-colors ${
                t.change24h >= 0 ? 'text-neon-cyan' : 'text-neon-pink'
              }`}>
                ${formatPrice(t.price)}
              </span>
              <span className={`inline-flex items-center gap-0.5 text-[11px] font-mono px-1.5 py-0.5 rounded-md font-medium ${
                t.change24h >= 0 ? 'bg-neon-cyan/[0.08] text-neon-cyan' : 'bg-neon-pink/[0.08] text-neon-pink'
              }`}>
                {t.change24h >= 0 ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                {Math.abs(t.change24h).toFixed(2)}%
              </span>
            </button>
          ))}
        </div>

        {/* Main Content: Chart + Order Book */}
        <div className="grid grid-cols-1 xl:grid-cols-4 gap-4">
          {/* Chart Area */}
          <div className="xl:col-span-3 bg-bg-card rounded-md neon-border-cyan">
            {/* Chart Header */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between p-4 pb-0 gap-3">
              <div className="flex items-baseline gap-3">
                <span className="text-base font-semibold text-text tracking-tight font-mono">{selected}</span>
                {current && (
                  <span className={`font-mono text-2xl font-bold tracking-tight transition-colors ${
                    priceFlash === 'up' ? 'text-neon-cyan' :
                    priceFlash === 'down' ? 'text-neon-pink' :
                    current.change24h >= 0 ? 'text-neon-cyan' : 'text-neon-pink'
                  }`}>
                    ${formatPrice(current.price)}
                  </span>
                )}
                {current && (
                  <span className={`flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded ${
                    current.change24h >= 0 ? 'bg-neon-cyan/[0.08] text-neon-cyan' : 'bg-neon-pink/[0.08] text-neon-pink'
                  }`}>
                    {current.change24h >= 0 ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
                    {current.change24h >= 0 ? '+' : ''}{current.change24h.toFixed(2)}%
                  </span>
                )}
              </div>
              <div className="flex gap-1 bg-bg-elevated p-1 rounded-md border border-bg-border overflow-x-auto scrollbar-thin">
                {TIMEFRAMES.map(tf => (
                  <button
                    key={tf.value}
                    onClick={() => setIntervalState(tf.value)}
                    className={`px-2.5 py-1 text-xs rounded-md font-medium transition-colors duration-150 whitespace-nowrap ${
                      interval === tf.value
                        ? 'bg-neon-cyan/[0.15] text-neon-cyan'
                        : 'text-text-dim hover:text-text-secondary'
                    }`}
                  >
                    {tf.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Chart */}
            <div className="p-3">
              {chartLoading ? (
                <div className="flex items-center justify-center" style={{ height: `${chartHeight}px` }}>
                  <div className="cyber-spinner" />
                </div>
              ) : (
                <CandlestickChart data={candles} height={chartHeight} />
              )}
            </div>
          </div>

          {/* Order Book */}
          <div className="bg-bg-card rounded-md neon-border-cyan">
            <div className="px-4 py-3 border-b border-bg-border flex items-center justify-between">
              <h3 className="text-xs font-semibold text-text tracking-tight font-mono uppercase tracking-wider">Order Book</h3>
              <span className="relative flex h-1.5 w-1.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-neon-cyan opacity-60"></span>
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-neon-cyan"></span>
              </span>
            </div>
            <div className="px-1 py-2">
              <div className="flex justify-between text-[10px] text-text-dim mb-1 px-2 font-medium uppercase tracking-wider font-mono">
                <span>Price</span>
                <span>Size</span>
              </div>
              {/* Asks */}
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
              {/* Mid Price */}
              <div className="flex items-center justify-center py-2.5 border-y border-bg-border my-1">
                <span className={`text-sm font-bold font-mono tracking-tight ${
                  current?.change24h !== undefined && current.change24h >= 0 ? 'text-neon-cyan' : 'text-neon-pink'
                }`}>
                  ${formatPrice(midPrice)}
                </span>
              </div>
              {/* Bids */}
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

        {/* Stats Row */}
        {current && (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 sm:gap-3">
            {[
              { label: '24h High', value: `$${formatPrice(current.high24h)}`, icon: <ArrowUpRight className="w-3.5 h-3.5" /> },
              { label: '24h Low', value: `$${formatPrice(current.low24h)}`, icon: <ArrowDownRight className="w-3.5 h-3.5" /> },
              { label: '24h Change', value: `${current.change24h >= 0 ? '+' : ''}${current.change24h.toFixed(2)}%`, color: current.change24h >= 0 ? 'text-neon-cyan' : 'text-neon-pink', icon: current.change24h >= 0 ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" /> },
              { label: '24h Volume', value: `$${formatN(current.volume24h)}`, icon: <BarChart3 className="w-3.5 h-3.5" /> },
              { label: 'Mark Price', value: `$${formatPrice(midPrice)}`, icon: <span className="text-neon-cyan">◎</span> },
              { label: 'Spread', value: asks.length > 0 && bids.length > 0
                ? `${((asks[0].price - bids[0].price) / midPrice * 100).toFixed(3)}%`
                : '—', icon: <span className="text-text-dim">↔</span> },
            ].map(m => (
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
        )}
      </div>
    </AppShell>
  );
}