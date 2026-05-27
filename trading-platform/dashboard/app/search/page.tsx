'use client';
import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'next/navigation';
import AppShell from '@/components/layout/AppShell';
import SearchBar from '@/components/SearchBar';
import SearchResults from '@/components/SearchResults';
import { semanticSearch, SemanticSearchResult } from '@/lib/api';
import { Search } from 'lucide-react';

export default function SearchPage() {
  const searchParams = useSearchParams();
  const initialQuery = searchParams?.get('q') || '';

  const [query, setQuery] = useState(initialQuery);
  const [results, setResults] = useState<SemanticSearchResult[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runSearch = useCallback(async (q: string) => {
    if (!q || q.trim().length < 2) {
      setResults([]);
      setTotal(0);
      setError(null);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const data = await semanticSearch(q.trim(), { top_k: 20, min_similarity: 0.3 });
      setResults(data.results);
      setTotal(data.total);
      if (data.error) setError(data.error);
    } catch (err) {
      setError('Search request failed');
      console.error('[Search] Error:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Run search when query changes (from URL)
  useEffect(() => {
    if (initialQuery) {
      setQuery(initialQuery);
      runSearch(initialQuery);
    }
  }, [initialQuery, runSearch]);

  const handleSearch = useCallback((q: string) => {
    setQuery(q);
    runSearch(q);
  }, [runSearch]);

  return (
    <AppShell>
      <div className="max-w-3xl mx-auto">
        {/* Page header */}
        <div className="mb-6">
          <div className="flex items-center gap-2.5 mb-1">
            <Search className="w-4 h-4 text-neon-cyan" strokeWidth={1.5} />
            <h1 className="text-lg font-semibold text-text-primary font-mono uppercase tracking-wider">
              Semantic Search
            </h1>
          </div>
          <p className="text-xs text-text-dim font-mono">
            Search across trades, news, signals, and analysis using vector embeddings
          </p>
        </div>

        {/* Search bar */}
        <div className="mb-6">
          <SearchBar className="w-full" />
        </div>

        {/* Results */}
        <div className="bg-bg-card border border-bg-border/60 rounded-lg overflow-hidden">
          <SearchResults
            results={results}
            query={query}
            total={total}
            loading={loading}
            error={error}
          />
        </div>
      </div>
    </AppShell>
  );
}
