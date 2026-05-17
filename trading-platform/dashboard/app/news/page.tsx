'use client';
import { useState, useEffect, useMemo } from 'react';
import AppShell from '@/components/layout/AppShell';
import { fetchNews, fetchNewsSignals, fetchNewsSentiment } from '@/lib/api';
import type { NewsArticle } from '@/lib/api';

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

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function highlightTickers(text: string, tickers: string[]): string {
  if (!tickers.length) return text;
  const pattern = new RegExp(`\\b(${tickers.join('|')})\\b`, 'gi');
  return text.replace(pattern, '<mark class="bg-accent-muted/50 text-accent px-1 rounded">$1</mark>');
}

// ========== Components ==========

function SentimentPill({ sentiment }: { sentiment: string }) {
  const styles: Record<string, string> = {
    bullish: 'bg-up/20 text-up',
    bearish: 'bg-down/20 text-down',
    neutral: 'bg-text-muted/20 text-text-muted',
  };
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${styles[sentiment] ?? styles.neutral}`}>
      {sentiment.charAt(0).toUpperCase() + sentiment.slice(1)}
    </span>
  );
}

function SignalBadge({ signal }: { signal?: string }) {
  if (!signal) return null;
  const isBuy = signal.includes('BUY');
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-bold tracking-wide ${isBuy ? 'bg-up/25 text-up' : 'bg-down/25 text-down'}`}>
      {signal.replace(/_/g, ' ')}
    </span>
  );
}

function SentimentGauge({ sentiment }: { sentiment: { overall: number; bullish: number; bearish: number; neutral: number } }) {
  const circumference = 2 * Math.PI * 40;
  const bullishLen = (sentiment.bullish / 100) * circumference;
  const bearishLen = (sentiment.bearish / 100) * circumference;
  const neutralLen = (sentiment.neutral / 100) * circumference;

  return (
    <div className="bg-bg-card rounded-xl border border-border p-4">
      <h3 className="text-sm font-semibold text-text-primary mb-3">Overall Sentiment</h3>
      <div className="flex items-center gap-4">
        <div className="relative w-24 h-24">
          <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
            <circle cx="50" cy="50" r="40" fill="none" stroke="#2a3548" strokeWidth="12" />
            <circle cx="50" cy="50" r="40" fill="none" stroke="#00d4aa" strokeWidth="12"
              strokeDasharray={`${bullishLen} ${circumference - bullishLen}`} />
            <circle cx="50" cy="50" r="40" fill="none" stroke="#f44336" strokeWidth="12"
              strokeDasharray={`${bearishLen} ${circumference}`}
              strokeDashoffset={`-${bullishLen}`} />
          </svg>
          <div className="absolute inset-0 flex items-center justify-center text-sm font-bold text-text-primary">
            {sentiment.overall > 0 ? '+' : ''}{sentiment.overall}
          </div>
        </div>
        <div className="space-y-1.5 text-sm">
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-up" />
            <span className="text-text-secondary">{sentiment.bullish}% Bullish</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-down" />
            <span className="text-text-secondary">{sentiment.bearish}% Bearish</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-text-muted" />
            <span className="text-text-secondary">{sentiment.neutral}% Neutral</span>
          </div>
        </div>
      </div>
    </div>
  );
}

function ActiveSignals({ signals }: { signals: any[] }) {
  return (
    <div className="bg-bg-card rounded-xl border border-border p-4">
      <h3 className="text-sm font-semibold text-text-primary mb-3">Active Signals</h3>
      <div className="grid grid-cols-2 gap-2">
        {signals.slice(0, 4).map((s, i) => (
          <div key={i} className="flex items-center justify-between p-2 rounded bg-bg-primary border border-border">
            <div>
              <span className="text-sm font-semibold text-text-primary">{s.ticker}</span>
              <div className="text-xs text-text-muted">{timeAgo(s.timestamp)}</div>
            </div>
            <SignalBadge signal={s.signal} />
          </div>
        ))}
      </div>
    </div>
  );
}

function ArticleCard({ article }: { article: NewsArticle }) {
  // Create HTML with highlighted tickers in the summary
  const highlightedSummary = useMemo(
    () => highlightTickers(article.summary, article.tickers),
    [article.summary, article.tickers],
  );

  return (
    <article className="bg-bg-card rounded-xl border border-border p-4 hover:border-border/80 transition-colors group">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h3 className="text-sm font-semibold text-text-primary leading-snug">{article.title}</h3>
          </div>
          <p
            className="text-xs text-text-secondary mt-1 leading-relaxed line-clamp-2"
            dangerouslySetInnerHTML={{ __html: highlightedSummary }}
          />
        </div>
        <div className="flex flex-col items-end gap-1 shrink-0">
          <SentimentPill sentiment={article.sentiment} />
          {article.signal && <SignalBadge signal={article.signal} />}
        </div>
      </div>

      <div className="flex items-center gap-3 mt-3 text-xs text-text-muted">
        <span className="font-medium text-text-secondary">{article.source}</span>
        <span>·</span>
        <span>{timeAgo(article.publishedAt)}</span>
        <span className="hidden sm:inline">·</span>
        <span className="hidden sm:inline text-text-muted">{formatDate(article.publishedAt)}</span>
        <span>·</span>
        <div className="flex gap-1">
          {article.tickers.map(t => (
            <span
              key={t}
              className="px-1.5 py-0.5 rounded bg-accent-muted/30 text-accent font-mono text-xs font-medium"
            >
              {t}
            </span>
          ))}
        </div>
      </div>

      {article.sentimentScore !== undefined && article.sentimentScore !== 0 && (
        <div className="mt-2 h-1 rounded-full bg-bg-primary overflow-hidden">
          <div
            className={`h-full rounded-full ${article.sentimentScore > 0 ? 'bg-up' : 'bg-down'}`}
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

  // Filter states
  const [sentimentFilter, setSentimentFilter] = useState<'all' | 'bullish' | 'bearish' | 'neutral'>('all');
  const [selectedTicker, setSelectedTicker] = useState<string>('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

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

  // Collect all unique tickers for filter dropdown
  const allTickers = useMemo(() => {
    const tickerSet = new Set<string>();
    articles.forEach(a => a.tickers.forEach(t => tickerSet.add(t)));
    return Array.from(tickerSet).sort();
  }, [articles]);

  // Apply all filters
  const filtered = useMemo(() => {
    let result = articles;

    // Sentiment filter
    if (sentimentFilter !== 'all') {
      result = result.filter(a => a.sentiment === sentimentFilter);
    }

    // Ticker filter
    if (selectedTicker) {
      result = result.filter(a => a.tickers.includes(selectedTicker));
    }

    // Date range filter
    if (startDate) {
      const start = new Date(startDate).getTime();
      result = result.filter(a => new Date(a.publishedAt).getTime() >= start);
    }
    if (endDate) {
      const end = new Date(endDate).getTime() + 86400000; // include the end date fully
      result = result.filter(a => new Date(a.publishedAt).getTime() <= end);
    }

    return result;
  }, [articles, sentimentFilter, selectedTicker, startDate, endDate]);

  const clearFilters = () => {
    setSentimentFilter('all');
    setSelectedTicker('');
    setStartDate('');
    setEndDate('');
  };

  const hasActiveFilters = sentimentFilter !== 'all' || selectedTicker || startDate || endDate;

  if (loading) {
    return (
      <AppShell>
        <div className="flex items-center justify-center h-64">
          <div className="text-text-muted text-sm">Loading news feed...</div>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-text-primary">News & Signals Feed</h2>
            <p className="text-xs text-text-muted mt-1">Analyst-curated news with sentiment analysis and trading signals</p>
          </div>
          {hasActiveFilters && (
            <button
              onClick={clearFilters}
              className="px-3 py-1.5 rounded-lg text-xs font-medium text-text-muted hover:text-text-primary border border-border hover:border-text-muted transition-colors"
            >
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
        <div className="bg-bg-card rounded-xl border border-border p-4">
          <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
            {/* Sentiment filter */}
            <div className="flex gap-1">
              {(['all', 'bullish', 'bearish', 'neutral'] as const).map(f => (
                <button
                  key={f}
                  onClick={() => setSentimentFilter(f)}
                  className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                    sentimentFilter === f
                      ? 'bg-accent-muted text-accent'
                      : 'text-text-muted hover:text-text-primary'
                  }`}
                >
                  {f.charAt(0).toUpperCase() + f.slice(1)}
                </button>
              ))}
            </div>

            {/* Symbol filter */}
            <div className="flex items-center gap-2">
              <label className="text-xs text-text-muted">Symbol:</label>
              <select
                value={selectedTicker}
                onChange={(e) => setSelectedTicker(e.target.value)}
                className="bg-bg-primary border border-border rounded-lg px-2 py-1.5 text-xs text-text-primary focus:outline-none focus:border-accent"
              >
                <option value="">All</option>
                {allTickers.map(t => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>

            {/* Date range filter */}
            <div className="flex items-center gap-2">
              <label className="text-xs text-text-muted">From:</label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="bg-bg-primary border border-border rounded-lg px-2 py-1.5 text-xs text-text-primary focus:outline-none focus:border-accent"
              />
              <label className="text-xs text-text-muted">To:</label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="bg-bg-primary border border-border rounded-lg px-2 py-1.5 text-xs text-text-primary focus:outline-none focus:border-accent"
              />
            </div>
          </div>

          <div className="mt-2 text-xs text-text-muted">
            Showing {filtered.length} of {articles.length} articles
            {hasActiveFilters && ' (filtered)'}
          </div>
        </div>

        {/* News feed */}
        <div className="space-y-3">
          {filtered.length === 0 ? (
            <div className="text-center py-12">
              <div className="text-2xl mb-2">📭</div>
              <p className="text-text-muted text-sm">No articles match your filters.</p>
              <button
                onClick={clearFilters}
                className="mt-2 text-xs text-accent hover:underline"
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
