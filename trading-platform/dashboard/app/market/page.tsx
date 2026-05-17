'use client';
import { useState, useEffect, useCallback, useRef } from 'react';
import AppShell from '@/components/layout/AppShell';
import CandlestickChart from '@/components/chart/CandlestickChart';
import { fetchTickers, fetchCandles, fetchOrderBook } from '@/lib/api';
import type { TickerPrice, Candle, OrderBookEntry } from '@/lib/api';

function formatN(n: number) {
  if (n >= 1e9) return (n / 1e9).toFixed(1) + 'B';
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
  return n.toLocaleString();
}

function formatPrice(price: number) {
  if (price < 1) return price.toFixed(6);
  if (price < 10) return price.toFixed(4);
  if (price < 1000) return price.toFixed(2);
  return price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
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

  const filteredTickers = tickers.filter(t =>
    t.symbol.toLowerCase().includes(search.toLowerCase())
  );

  const loadTickers = useCallback(async () => {
    try {
      const t = await fetchTickers();
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

  // Initial ticker load
  useEffect(() => {
    loadTickers();
    const id = setInterval(loadTickers, 10000);
    return () => clearInterval(id);
  }, [loadTickers]);

  // Loading state
  useEffect(() => {
    if (tickers.length > 0) setLoading(false);
  }, [tickers]);

  // Load candles + orderbook on symbol/timeframe change
  useEffect(() => {
    if (tickers.length === 0) return;
    loadCandlesAndOB(selected, interval);
  }, [selected, interval, tickers.length, loadCandlesAndOB]);

  // Price flash animation
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
          <div>
            <h2 className="text-xl font-bold text-text-primary">Markets</h2>
            <p className="text-xs text-text-muted mt-0.5">
              Last updated: {lastUpdate.toLocaleTimeString()}
            </p>
          </div>
          <div className="relative">
            <input
              type="text"
              placeholder="Search symbol..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full sm:w-56 pl-3 pr-8 py-2 bg-bg-secondary border border-border rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent"
            />
            {search && (
              <button
                onClick={() => setSearch('')}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary text-xs"
              >
                ✕
              </button>
            )}
          </div>
        </div>

        {/* Ticker Strip */}
        <div className="flex flex-wrap items-center gap-2 overflow-x-auto pb-1">
          {filteredTickers.length === 0 && search && (
            <p className="text-sm text-text-muted py-2">No symbols match "{search}"</p>
          )}
          {filteredTickers.map(t => (
            <button
              key={t.symbol}
              onClick={() => setSelected(t.symbol)}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg border text-sm transition-all whitespace-nowrap ${
                selected === t.symbol
                  ? 'bg-bg-card border-accent shadow-lg shadow-accent/5'
                  : 'bg-bg-secondary border-border hover:border-text-muted'
              }`}
            >
              <span className="font-semibold text-text-primary">{t.symbol}</span>
              <span className={`font-mono text-xs transition-colors ${
                t.change24h >= 0 ? 'text-up' : 'text-down'
              }`}>
                {formatPrice(t.price)}
              </span>
              <span className={`text-xs font-mono px-1.5 py-0.5 rounded ${
                t.change24h >= 0 ? 'bg-up/10 text-up' : 'bg-down/10 text-down'
              }`}>
                {t.change24h >= 0 ? '+' : ''}{t.change24h.toFixed(2)}%
              </span>
            </button>
          ))}
        </div>

        {/* Main Content: Chart + Order Book */}
        <div className="grid grid-cols-1 xl:grid-cols-4 gap-4">
          {/* Chart Area */}
          <div className="xl:col-span-3 bg-bg-card rounded-xl border border-border p-4">
            {/* Chart Header */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-3 gap-3">
              <div className="flex items-center gap-3">
                <span className="text-lg font-bold text-text-primary">{selected}</span>
                {current && (
                  <span className={`font-mono text-lg font-semibold transition-colors ${
                    priceFlash === 'up' ? 'text-up' :
                    priceFlash === 'down' ? 'text-down' :
                    current.change24h >= 0 ? 'text-up' : 'text-down'
                  }`}>
                    {formatPrice(current.price)}
                  </span>
                )}
              </div>
              <div className="flex gap-1 flex-wrap">
                {TIMEFRAMES.map(tf => (
                  <button
                    key={tf.value}
                    onClick={() => setIntervalState(tf.value)}
                    className={`px-2.5 py-1 text-xs rounded-md transition-colors ${
                      interval === tf.value
                        ? 'bg-accent/20 text-accent font-semibold'
                        : 'text-text-muted hover:text-text-primary hover:bg-bg-secondary'
                    }`}
                  >
                    {tf.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Chart */}
            {chartLoading ? (
              <div className="flex items-center justify-center h-[380px]">
                <div className="w-8 h-8 border-2 border-accent border-t-transparent rounded-full animate-spin" />
              </div>
            ) : (
              <CandlestickChart data={candles} height={380} />
            )}
          </div>

          {/* Order Book */}
          <div className="bg-bg-card rounded-xl border border-border p-4">
            <h3 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
              <span>Order Book</span>
              <span className="w-2 h-2 rounded-full bg-up animate-pulse" />
            </h3>
            <div className="flex justify-between text-xs text-text-muted mb-1 px-1 font-medium">
              <span>Price</span>
              <span>Size</span>
            </div>
            {/* Asks (reversed so lowest ask is at bottom, closest to mid price) */}
            <div className="space-y-px max-h-[180px] overflow-y-auto font-mono text-xs mb-2 scrollbar-thin">
              {asks.slice().reverse().map((a, i) => {
                const depth = asks.reduce((sum, x) => sum + x.size, 0);
                const pct = Math.min(a.size / depth * 100 * 3, 60);
                return (
                  <div key={`ask-${i}`} className="flex justify-between px-1 py-0.5 text-down relative">
                    <span className="absolute inset-0 bg-down/5" style={{ right: `${pct}%` }} />
                    <span className="relative">{formatPrice(a.price)}</span>
                    <span className="relative">{a.size.toFixed(4)}</span>
                  </div>
                );
              })}
            </div>
            {/* Mid Price */}
            <div className="flex items-center justify-center py-2 border-y border-border my-2">
              <span className={`text-sm font-bold font-mono ${
                current?.change24h !== undefined && current.change24h >= 0 ? 'text-up' : 'text-down'
              }`}>
                {formatPrice(midPrice)}
              </span>
            </div>
            {/* Bids */}
            <div className="space-y-px max-h-[180px] overflow-y-auto font-mono text-xs mt-2 scrollbar-thin">
              {bids.map((b, i) => {
                const depth = bids.reduce((sum, x) => sum + x.size, 0);
                const pct = Math.min(b.size / depth * 100 * 3, 60);
                return (
                  <div key={`bid-${i}`} className="flex justify-between px-1 py-0.5 text-up relative">
                    <span className="absolute inset-0 bg-up/5" style={{ right: `${pct}%` }} />
                    <span className="relative">{formatPrice(b.price)}</span>
                    <span className="relative">{b.size.toFixed(4)}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Stats Row */}
        {current && (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            {[
              { label: '24h High', value: formatPrice(current.high24h), icon: '↑' },
              { label: '24h Low', value: formatPrice(current.low24h), icon: '↓' },
              { label: '24h Change', value: `${current.change24h >= 0 ? '+' : ''}${current.change24h.toFixed(2)}%`, icon: '±', color: current.change24h >= 0 ? 'text-up' : 'text-down' },
              { label: '24h Volume', value: formatN(current.volume24h), icon: '◈' },
              { label: 'Mark Price', value: formatPrice(midPrice), icon: '◎' },
              { label: 'Spread', value: asks.length > 0 && bids.length > 0
                ? `${((asks[0].price - bids[0].price) / midPrice * 100).toFixed(3)}%`
                : '—', icon: '↔' },
            ].map(m => (
              <div key={m.label} className="bg-bg-card rounded-lg border border-border p-3 transition-colors hover:border-text-muted/50">
                <div className="flex items-center gap-1.5 text-xs text-text-muted mb-1">
                  <span className="opacity-60">{m.icon}</span>
                  {m.label}
                </div>
                <div className={`text-sm font-mono font-medium text-text-primary mt-0.5 ${m.color ?? ''}`}>
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
