'use client';
import { useState, useRef, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { Search, X } from 'lucide-react';

const DEBOUNCE_MS = 300;

export default function SearchBar({ className = '' }: { className?: string }) {
  const [value, setValue] = useState('');
  const [focused, setFocused] = useState(false);
  const [debouncedValue, setDebouncedValue] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  // Debounce the value for live preview / auto-search
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [value]);

  // Keyboard shortcut: Cmd+K or Ctrl+K to focus
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        inputRef.current?.focus();
      }
      if (e.key === 'Escape' && focused) {
        inputRef.current?.blur();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [focused]);

  const handleSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = value.trim();
    if (trimmed.length >= 2) {
      router.push(`/search?q=${encodeURIComponent(trimmed)}`);
    }
  }, [value, router]);

  const handleClear = useCallback(() => {
    setValue('');
    setDebouncedValue('');
    inputRef.current?.focus();
  }, []);

  return (
    <form
      onSubmit={handleSubmit}
      className={`relative group ${className}`}
      role="search"
    >
      <div
        className={`
          flex items-center gap-1.5 px-2.5 py-1.5 rounded-md border transition-all duration-200
          ${focused
            ? 'border-neon-cyan/40 bg-bg-elevated shadow-[0_0_8px_rgba(0,255,247,0.08)]'
            : 'border-bg-border/60 bg-bg-secondary group-hover:border-bg-border'
          }
        `}
      >
        <Search
          className={`w-3.5 h-3.5 shrink-0 transition-colors ${
            focused ? 'text-neon-cyan' : 'text-text-dim'
          }`}
          strokeWidth={1.5}
        />
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          placeholder="Search trades, news, signals..."
          aria-label="Global search"
          className={`
            w-36 sm:w-44 lg:w-56 bg-transparent text-sm text-text-primary
            placeholder:text-text-dim outline-none font-mono
          `}
        />
        {value && (
          <button
            type="button"
            onClick={handleClear}
            className="text-text-dim hover:text-text-primary transition-colors p-0.5"
            aria-label="Clear search"
          >
            <X className="w-3 h-3" strokeWidth={1.5} />
          </button>
        )}
      </div>
    </form>
  );
}
