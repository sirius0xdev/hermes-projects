'use client';
import Link from 'next/link';
import { useWallet } from '@/hooks/useWallet';
import { Menu } from 'lucide-react';
import SearchBar from '@/components/SearchBar';

export default function Header({ onMenuClick }: { onMenuClick: () => void }) {
  const { session } = useWallet();

  return (
    <header className="h-16 sticky top-0 z-20 border-b border-bg-border bg-bg-secondary/80 backdrop-blur-sm px-4 flex items-center justify-between shrink-0">
      <button
        onClick={onMenuClick}
        className="lg:hidden text-text-dim hover:text-text-primary p-2 -ml-2 rounded-md transition-colors"
        aria-label="Open menu"
      >
        <Menu className="w-4 h-4" strokeWidth={1.5} />
      </button>

      {/* HUD status indicators */}
      <div className="hidden sm:flex items-center gap-3 text-[10px] text-text-dim">
        <span className="flex items-center gap-1.5">
          <span className="status-dot status-dot-active" />
          <span className="uppercase tracking-wider font-mono font-semibold text-neon-cyan/60">SYSTEM</span>
        </span>
        <span className="text-text-muted">|</span>
        <span className="flex items-center gap-1.5">
          <span className="status-dot status-dot-active" />
          <span className="uppercase tracking-wider font-mono font-semibold text-neon-green/60">DATA</span>
        </span>
      </div>

      <div className="flex items-center gap-3 ml-auto">
        {/* Global search */}
        <SearchBar />

        {/* Wallet status */}
        <div className="flex items-center gap-2.5 text-sm">
          {session ? (
            <>
              <Link href="/auth" className="text-text-dim hover:text-text-primary transition-colors">
                <span className="font-mono text-[11px]">{session.walletAddress.slice(0, 6)}...{session.walletAddress.slice(-4)}</span>
              </Link>
              <span className="w-1 h-1 rounded-full bg-long" />
              <span className="text-text-dim text-[11px]">{session.chain}</span>
            </>
          ) : (
            <>
              <Link href="/auth" className="text-text-dim hover:text-neon-cyan transition-colors text-xs font-medium neon-cyan">Connect Wallet</Link>
              <span className="w-1 h-1 rounded-full bg-text-muted" />
              <span className="text-text-dim text-[11px]">Not connected</span>
            </>
          )}
        </div>
      </div>
    </header>
  );
}