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

        {/* Wallet status - prominent CTA on mobile */}
        <div className="flex items-center gap-2 text-sm">
          {session ? (
            <Link href="/auth" className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-bg-elevated border border-bg-border hover:border-neon-cyan/50 transition-all text-xs">
              <span className="font-mono text-[10px] sm:text-[11px] text-neon-cyan">{session.walletAddress.slice(0, 6)}...{session.walletAddress.slice(-4)}</span>
              <span className="hidden sm:inline text-text-dim text-[10px]">• {session.chain}</span>
            </Link>
          ) : (
            <Link 
              href="/auth" 
              className="flex items-center gap-2 px-4 py-1.5 rounded-md bg-neon-cyan text-bg-primary font-semibold text-xs sm:text-sm hover:bg-neon-cyan/90 active:scale-[0.985] transition-all shadow-[0_0_12px_rgba(0,255,247,0.3)]"
            >
              <span>Connect Wallet</span>
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}