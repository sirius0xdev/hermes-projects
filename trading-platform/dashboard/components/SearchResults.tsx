'use client';
import { useMemo } from 'react';
import Link from 'next/link';
import { Search, Clock, FileText, TrendingUp, Newspaper, Cpu, BarChart3, Loader2 } from 'lucide-react';
import { SemanticSearchResult } from '@/lib/api';

/**
 * Map entity types to icons and link paths
 */
const entityTypeConfig: Record<string, { icon: typeof Search; path: string; label: string; color: string }> = {
  trade: { icon: TrendingUp, path: '/trades', label: 'Trade', color: 'text-neon-cyan' },
  news: { icon: Newspaper, path: '/news', label: 'News', color: 'text-neon-green' },
  signal: { icon: Cpu, path: '/bot', label: 'Signal', color: 'text-neon-pink' },
  analysis: { icon: BarChart3, path: '/market', label: 'Analysis', color: 'text-warm' },
};

const defaultConfig = { icon: FileText, path: '/', label: 'Doc', color: 'text-text-dim' };

function getEntityTypeConfig(type: string) {
  return entityTypeConfig[type.toLowerCase()] || defaultConfig;
}

function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  const diffHr = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHr / 24);

  if (diffMin < 1) return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHr < 24) return `${diffHr}h ago`;
  if (diffDay < 7) return `${diffDay}d ago`;
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function formatScore(score: number): string {
  return `${Math.round(score * 100)}%`;
}

function getScoreColor(score: number): string {
  if (score >= 0.8) return 'text-neon-green';
  if (score >= 0.6) return 'text-neon-cyan';
  if (score >= 0.4) return 'text-warm';
  return 'text-text-dim';
}

export default function SearchResults({
  results,
  query,
  total,
  loading,
  error,
}: {
  results: SemanticSearchResult[];
  query: string;
  total: number;
  loading: boolean;
  error?: string | null;
}) {
  const highlightedResults = useMemo(() =>
    results.map(r => {
      // Simple text highlighting — wrap query match in a span
      const text = r.text;
      const idx = text.toLowerCase().indexOf(query.toLowerCase());
      if (idx < 0) return { ...r, before: '', match: '', after: text.substring(0, 120) };

      const before = text.substring(0, Math.max(0, idx - 20));
      const match = text.substring(idx, idx + query.length);
      const after = text.substring(idx + query.length, idx + query.length + 80);
      return { ...r, before, match, after };
    }),
    [results, query]
  );

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-text-dim gap-3">
        <Loader2 className="w-5 h-5 animate-spin text-neon-cyan/60" strokeWidth={1.5} />
        <span className="text-xs font-mono uppercase tracking-wider">Searching vector index...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-text-dim gap-2">
        <span className="text-xs font-mono text-short">ERROR</span>
        <span className="text-xs font-mono">{error}</span>
      </div>
    );
  }

  if (results.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-text-dim gap-2">
        <Search className="w-5 h-5 text-text-muted" strokeWidth={1.5} />
        <span className="text-xs font-mono uppercase tracking-wider">No results found</span>
        <span className="text-xs">Try different keywords or check the embedding index status</span>
      </div>
    );
  }

  return (
    <div className="space-y-0.5">
      {/* Results header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-bg-border/60">
        <span className="text-[10px] font-mono uppercase tracking-wider text-text-dim">
          {total} result{total !== 1 ? 's' : ''} for &ldquo;{query}&rdquo;
        </span>
      </div>

      {/* Results list */}
      {highlightedResults.map((r) => {
        const config = getEntityTypeConfig(r.entityType);
        const Icon = config.icon;
        return (
          <Link
            key={r.id}
            href={`${config.path}`}
            className="block px-3 py-2.5 border-b border-bg-border/30 hover:bg-bg-tertiary/60 transition-colors group"
          >
            <div className="flex items-start gap-2.5">
              {/* Entity type badge */}
              <div className={`mt-0.5 shrink-0 ${config.color}`}>
                <Icon className="w-3.5 h-3.5" strokeWidth={1.5} />
              </div>

              {/* Content */}
              <div className="flex-1 min-w-0">
                <p className="text-sm text-text-secondary leading-snug">
                  {r.before && <span>{r.before}</span>}
                  <span className="text-neon-cyan font-medium">{r.match}</span>
                  {r.after && <span>{r.after}</span>}
                </p>
                <div className="flex items-center gap-2.5 mt-1">
                  <span className={`text-[10px] font-mono uppercase tracking-wider ${config.color}`}>
                    {config.label}
                  </span>
                  <span className="text-text-muted">|</span>
                  <span className={`text-[10px] font-mono ${getScoreColor(r.score)}`}>
                    {formatScore(r.score)} match
                  </span>
                  <span className="text-text-muted">|</span>
                  <span className="text-[10px] font-mono text-text-dim flex items-center gap-1">
                    <Clock className="w-2.5 h-2.5" strokeWidth={1.5} />
                    {formatTimestamp(r.timestamp)}
                  </span>
                </div>
              </div>

              {/* Score bar */}
              <div className="shrink-0 w-16 text-right">
                <div className="text-[10px] font-mono text-text-dim">
                  {formatScore(r.score)}
                </div>
                <div className="mt-1 h-1 bg-bg-elevated rounded-sm overflow-hidden">
                  <div
                    className={`h-full rounded-sm transition-all ${
                      r.score >= 0.8 ? 'bg-neon-green' : r.score >= 0.6 ? 'bg-neon-cyan' : r.score >= 0.4 ? 'bg-warm' : 'bg-text-dim'
                    }`}
                    style={{ width: `${r.score * 100}%` }}
                  />
                </div>
              </div>
            </div>
          </Link>
        );
      })}
    </div>
  );
}
