'use client';
import Link from 'next/link';
import { useWallet } from '@/hooks/useWallet';
import { Menu } from 'lucide-react';

export default function Header({ onMenuClick }: { onMenuClick: () => void }) {
  const { session } = useWallet();

  return (
    <header className="sticky top-0 z-20 border-b border-bg-border bg-bg-secondary px-4 py-3 flex items-center justify-between">
      <button onClick={onMenuClick} className="lg:hidden text-text-primary p-2 -ml-2" aria-label="Open menu">
        <Menu className="w-5 h-5" />
      </button>
      <div className="flex items-center gap-2 ml-auto text-sm">
        {session ? (
          <>
            <Link href="/auth" className="text-text-dim hover:text-text-primary transition-colors">
              <span className="font-mono text-xs">{session.walletAddress.slice(0,6)}...{session.walletAddress.slice(-4)}</span>
            </Link>
            <span className="w-1.5 h-1.5 rounded-full bg-long" />
            <span className="text-text-dim text-xs">{session.chain}</span>
          </>
        ) : (
          <>
            <Link href="/auth" className="text-text-dim hover:text-accent transition-colors text-xs font-medium">Connect Wallet</Link>
            <span className="w-1.5 h-1.5 rounded-full bg-text-muted" />
            <span className="text-text-dim text-xs">Not connected</span>
          </>
        )}
      </div>
    </header>
  );
}
