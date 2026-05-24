'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

const navItems = [
  { label: 'Market', path: '/market', icon: '📊' },
  { label: 'Portfolio', path: '/portfolio', icon: '💼' },
  { label: 'Trades', path: '/trades', icon: '⚡' },
  { label: 'Autonomous Bot', path: '/bot', icon: '🧠' },
  { label: 'News Feed', path: '/news', icon: '📰' },
];

export default function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const pathname = usePathname();

  return (
    <>
      {open && <div className="fixed inset-0 bg-black/50 z-30 lg:hidden" onClick={onClose} />}
      <aside className={`fixed lg:sticky top-0 left-0 h-screen z-40 w-64 bg-bg-secondary border-r border-border flex flex-col transition-transform duration-200 ${open ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}`}>
        <div className="p-5 border-b border-border">
          <h1 className="text-xl font-bold text-accent">DeFi Trader</h1>
          <p className="text-xs text-text-muted mt-1">Private Trading Terminal</p>
        </div>
        <nav className="flex-1 p-3 space-y-1">
          {navItems.map(item => {
            const active = pathname === item.path;
            return (
              <Link key={item.path} href={item.path} onClick={onClose}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${active ? 'bg-accent-muted text-accent' : 'text-text-secondary hover:text-text-primary hover:bg-bg-tertiary'}`}>
                <span className="text-base">{item.icon}</span>
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="p-4 border-t border-border">
          <Link href="/auth" onClick={onClose} className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-colors">
            <span className="text-base">&#128274;</span>
            Wallet
          </Link>
        </div>
      </aside>
    </>
  );
}
