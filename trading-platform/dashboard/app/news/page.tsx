'use client';
import { useState, useEffect, useCallback, useMemo } from 'react';
import AppShell from '@/components/layout/AppShell';
import { fetchNews, fetchNewsSignals, fetchNewsSentiment } from '@/lib/api';
import type { NewsArticle } from '@/lib/api';
import {
  Newspaper,
  Filter,
  X,
  TrendingUp,
  TrendingDown,
  Minus,
  ArrowUpRight,
} from 'lucide-react';

// ========== Utility functions ==========

function timeAgo(dateStr: string): string {
  const now = new Date();
  const date = new Date(dateStr);
  const mins = Math.floor((now.getTime() - date.getTime()) / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function highlightTickers(text: string, tickers: string[]): string {
  if (!tickers.length) return text;
  const pattern = new RegExp(`\\b(${tickers.join('|')})\\b`, 'gi');
  return text.replace(pattern, '<mark class="bg-accent/20 text-accent px-1 rounded text-[10px]">$1</mark>');
}

// ========== Components ==========

function SentimentPill({ sentiment }: { sentiment: string }) {
  const styles: Record<string, string> = {
    bullish: 'bg-long-muted text-long',
    bearish: 'bg-short-muted text-short',
    neutral: 'bg-bg-elevated text-text-dim',
  };
  const icons: Record<string, React.ReactNode> = {
    bullish: <TrendingUp className="w-3 h-3" />,
    bearish: <TrendingDown className="w-3 h-3" />,
    neutral: <Minus className="w-3 h-3" />,
  };
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold ${styles[sentiment] ?? styles.neutral}`}>
      {icons[sentiment]}
      {sentiment.charAt(0).toUpperCase() + sentiment.slice(1)}
    </span>
  );
}

function SignalBadge({ signal }: { signal?: string }) {
  if (!signal) return null;
  const isBuy = signal.includes('BUY');
  const isStrong = signal.includes('STRONG');
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold tracking-wider ${
      isBuy
        ? isStrong ? 'bg-long text-bg' : 'bg-long-muted text-long'
        : isStrong ? 'bg-short text-white' : 'bg-short-muted text-short'
    }`}>
      {isBuy ? <ArrowUpRight className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
      {signal.replace(/_/g, ' ')}
    </span>
  );
}

function SentimentGauge({ sentiment }: { sentiment: { overall: number; bullish: number; bearish: number; neutral: number } }) {
  const circumference = 2 * Math.PI * 40;
  const bullishLen = (sentiment.bullish / 100) * circumference;
  const bearishLen = (sentiment.bearish / 100) * circumference;

  return (
    <div className="card-hover p-5">
      <h3 className="text-sm font-semibold text-text mb-4">Market Sentiment</h3>
      <div className="flex items-center gap-5">
        <div className="relative w-24 h-24 shrink-0">
          <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
            <circle cx="50" cy="50" r="40" fill="none" stroke="#1e293b" strokeWidth="10" />
            <circle cx="50" cy="50" r="40" fill="none" stroke="#10b981" strokeWidth="10"
              strokeDasharray={`${bullishLen} ${circumference - bullishLen}`}
              className="transition-all duration-700" />
            <circle cx="50" cy="50" r="40" fill="none" stroke="#ef4444" strokeWidth="10"
              strokeDasharray={`${bearishLen} ${circumference}`}
              strokeDashoffset={`-${bullishLen}`}
              className="transition-all duration-700" />
          </svg>
          <div className="absolute inset-0 flex items-center justify-center text-sm font-bold text-text">
            {sentiment.overall > 0 ? '+' : ''}{sentiment.overall}
          </div>
        </div>
        <div className="space-y-2 text-sm">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-long" />
            <span className="text-text-secondary">{sentiment.bullish}% Bullish</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-short" />
            <span className="text-text-secondary">{sentiment.bearish}% Bearish</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-text-dim" />
            <span className="text-text-secondary">{sentiment.neutral}% Neutral</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function ActiveSignals({ signals }: { signals: any[] }) {
  return (
    <div className="card-hover p-5">
      <h3 className="text-sm font-semibold text-text mb-4 flex items-center gap-2">
        <span className="relative flex h-2 w-2">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-long opacity-60"></span>
          <span className="relative inline-flex rounded-full h-2 w-2 bg-long"></span>
        </span>
        Active Signals
      </h3>
      <div className="grid grid-cols-2 gap-2">
        {signals.slice(0, 4).map((s, i) => (
          <div key={i} className="flex items-center justify-between p-3 rounded-lg bg-bg-elevated border border-bg-border">
            <div>
              <span className="text-sm font-bold text-text">{s.ticker}</span>
              <div className="text-[10px] text-text-dim">{timeAgo(s.timestamp)}</div>
            </div>
            <SignalBadge signal={s.signal} />
          </div>
        ))}
      </div>
    </div>
  );
}

function ArticleCard({ article }: { article: NewsArticle }) {
  const highlightedSummary = useMemo(
    () => highlightTickers(article.summary, article.tickers),
    [article.summary, article.tickers],
  );

  return (
    <article className="card-hover p-5 hover:border-bg-border_light transition-all group">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-text leading-snug group-hover:text-accent transition-colors">
            {article.title}
          </h3>
          <p
            className="text-xs text-text-secondary mt-1.5 leading-relaxed line-clamp-2"
            dangerouslySetInnerHTML={{ __html: highlightedSummary }}
          />
        </div>
        <div className="flex flex-col items-end gap-1.5 shrink-0">
          <SentimentPill sentiment={article.sentiment} />
          {article.signal && <SignalBadge signal={article.signal} />}
        </div>
      </div>

      <div className="flex items-center gap-3 mt-3 text-[11px] text-text-dim flex-wrap">
        <span className="font-medium text-text-secondary">{article.source}</span>
        <span>·</span>
        <span>{timeAgo(article.publishedAt)}</span>
        <div className="flex gap-1 ml-auto">
          {article.tickers.map(t => (
            <span
              key={t}
              className="px-1.5 py-0.5 rounded bg-accent/10 text-accent font-mono text-[10px] font-semibold"
            >
              {t}
            </span>
          ))}
        </div>
      </div>

      {article.sentimentScore !== undefined && article.sentimentScore !== 0 && (
        <div className="mt-3 h-1 rounded-full bg-bg-elevated overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-300 ${
              article.sentimentScore > 0 ? 'bg-long' : 'bg-short'
            }`}
            style={{ width: `${Math.abs(Math.round(article.sentimentScore * 100))}%` }}
          />
        </div>
      )}
    </article>
  );
}

// ========== Main page ==========

export default function NewsPage() {
  const [articles, setArticles] = useState<NewsArticle[]>([]);
  const [signals, setSignals] = useState<any[]>([]);
  const [sentiment, setSentiment] = useState<{ overall: number; bullish: number; bearish: number; neutral: number } | null>(null);
  const [loading, setLoading] = useState(true);

  const [sentimentFilter, setSentimentFilter] = useState<'all' | 'bullish' | 'bearish' | 'neutral'>('all');
  const [selectedTicker, setSelectedTicker] = useState<string>('');

  useEffect(() => {
    (async () => {
      const [a, s, sent] = await Promise.all([
        fetchNews(),
        fetchNewsSignals(),
        fetchNewsSentiment(),
      ]);
      setArticles(a);
      setSignals(s);
      setSentiment(sent);
      setLoading(false);
    })();
  }, []);

  const allTickers = useMemo(() => {
    const tickerSet = new Set<string>();
    articles.forEach(a => a.tickers.forEach(t => tickerSet.add(t)));
    return Array.from(tickerSet).sort();
  }, [articles]);

  const filtered = useMemo(() => {
    let result = articles;
    if (sentimentFilter !== 'all') {
      result = result.filter(a => a.sentiment === sentimentFilter);
    }
    if (selectedTicker) {
      result = result.filter(a => a.tickers.includes(selectedTicker));
    }
    return result;
  }, [articles, sentimentFilter, selectedTicker]);

  const hasActiveFilters = sentimentFilter !== 'all' || selectedTicker;

  if (loading) {
    return (
      <AppShell>
        <div className="flex items-center justify-center h-64">
          <div className="flex flex-col items-center gap-3">
            <div className="w-8 h-8 border-2 border-accent/30 border-t-accent rounded-full animate-spin" />
            <div className="text-text-dim text-sm">Loading news feed...</div>
          </div>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="space-y-5">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-accent/10 flex items-center justify-center">
              <Newspaper className="w-4 h-4 text-accent" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-text">News & Signals</h2>
              <p className="text-[11px] text-text-dim mt-0.5">Sentiment analysis and trading signals</p>
            </div>
          </div>
          {hasActiveFilters && (
            <button
              onClick={() => { setSentimentFilter('all'); setSelectedTicker(''); }}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-text-dim hover:text-text-secondary border border-bg-border hover:border-bg-border_light transition-colors"
            >
              <X className="w-3 h-3" />
              Clear filters
            </button>
          )}
        </div>

        {/* Sentiment overview + Signal strip */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {sentiment && <SentimentGauge sentiment={sentiment} />}
          <ActiveSignals signals={signals} />
        </div>

        {/* Filters bar */}
        <div className="card-hover p-4">
          <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
            <div className="flex items-center gap-2 text-[11px] text-text-dim">
              <Filter className="w-3.5 h-3.5" />
              <span className="font-medium">Filters:</span>
            </div>
            <div className="flex gap-1">
              {(['all', 'bullish', 'bearish', 'neutral'] as const).map(f => (
                <button
                  key={f}
                  onClick={() => setSentimentFilter(f)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                    sentimentFilter === f
                      ? 'bg-accent/10 text-accent'
                      : 'text-text-dim hover:text-text-secondary'
                  }`}
                >
                  {f.charAt(0).toUpperCase() + f.slice(1)}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2 ml-auto">
              <label className="text-[11px] text-text-dim">Symbol:</label>
              <select
                value={selectedTicker}
                onChange={(e) => setSelectedTicker(e.target.value)}
                className="bg-bg-elevated border border-bg-border rounded-lg px-2.5 py-1.5 text-xs text-text focus:outline-none focus:ring-1 focus:ring-accent/50 focus:border-accent"
              >
                <option value="">All</option>
                {allTickers.map(t => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="mt-2 text-[11px] text-text-dim">
            Showing {filtered.length} of {articles.length} articles
            {hasActiveFilters && ' (filtered)'}
          </div>
        </div>

        {/* News feed */}
        <div className="space-y-3">
          {filtered.length === 0 ? (
            <div className="text-center py-16 card">
              <Newspaper className="w-8 h-8 text-text-dim mx-auto mb-3 opacity-50" />
              <p className="text-text-dim text-sm">No articles match your filters.</p>
              <button
                onClick={() => { setSentimentFilter('all'); setSelectedTicker(''); }}
                className="mt-3 text-xs text-accent hover:underline"
              >
                Clear all filters
              </button>
            </div>
          ) : (
            filtered.map(article => (
              <ArticleCard key={article.id} article={article} />
            ))
          )}
        </div>
      </div>
    </AppShell>
  );
}
