'use client';
import Link from 'next/link';
import { useWallet } from '@/hooks/useWallet';

export default function Header({ onMenuClick }: { onMenuClick: () => void }) {
  const { session } = useWallet();

  return (
    <header className="sticky top-0 z-20 border-b border-border bg-bg-secondary/80 backdrop-blur px-4 py-3 flex items-center justify-between">
      <button onClick={onMenuClick} className="lg:hidden text-text-primary p-2 -ml-2" aria-label="Open menu">&#9776;</button>
      <div className="flex items-center gap-2 ml-auto text-sm">
        {session ? (
          <>
            <Link href="/auth" className="text-text-secondary hover:text-text-primary transition-colors">
              <span className="font-mono text-xs">{session.walletAddress.slice(0,6)}...{session.walletAddress.slice(-4)}</span>
            </Link>
            <span className="w-2 h-2 rounded-full bg-up animate-pulse" />
            <span className="text-text-secondary">{session.chain}</span>
          </>
        ) : (
          <>
            <Link href="/auth" className="text-text-muted hover:text-accent transition-colors font-medium">Connect Wallet</Link>
            <span className="w-2 h-2 rounded-full bg-text-muted" />
            <span className="text-text-muted">Not connected</span>
          </>
        )}
      </div>
    </header>
  );
}
