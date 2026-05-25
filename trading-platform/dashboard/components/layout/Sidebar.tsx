'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  BarChart3,
  PieChart,
  ArrowRightLeft,
  Cpu,
  Newspaper,
  Wallet,
} from 'lucide-react';

const navItems = [
  { label: 'Market', path: '/market', icon: BarChart3 },
  { label: 'Portfolio', path: '/portfolio', icon: PieChart },
  { label: 'Trades', path: '/trades', icon: ArrowRightLeft },
  { label: 'Autonomous Bot', path: '/bot', icon: Cpu },
  { label: 'News Feed', path: '/news', icon: Newspaper },
];

export default function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const pathname = usePathname();

  return (
    <>
      {open && <div className="fixed inset-0 bg-black/60 z-30 lg:hidden backdrop-blur-sm" onClick={onClose} />}
      <aside className={`fixed lg:sticky top-0 left-0 h-screen z-40 w-64 bg-bg-secondary border-r border-bg-border flex flex-col transition-transform duration-200 ${open ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}`}>
        {/* Brand */}
        <div className="h-16 flex items-center px-5 border-b border-bg-border shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-md bg-accent/15 flex items-center justify-center">
              <ArrowRightLeft className="w-3.5 h-3.5 text-accent" />
            </div>
            <div>
              <h1 className="text-sm font-semibold text-text-primary tracking-tight">DeFi Trader</h1>
              <p className="text-[10px] text-text-dim -mt-0.5">Private Terminal</p>
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 p-2 space-y-0.5 overflow-y-auto">
          {navItems.map(item => {
            const Icon = item.icon;
            const active = pathname === item.path;
            return (
              <Link
                key={item.path}
                href={item.path}
                onClick={onClose}
                className={`flex items-center gap-2.5 px-3 py-2 rounded-md text-sm transition-colors duration-150 ${
                  active
                    ? 'bg-accent/[0.08] text-accent font-medium'
                    : 'text-text-dim hover:text-text-primary hover:bg-bg-tertiary'
                }`}
              >
                <Icon className="w-4 h-4 shrink-0" strokeWidth={1.5} />
                {item.label}
              </Link>
            );
          })}
        </nav>

        {/* Wallet */}
        <div className="p-3 border-t border-bg-border shrink-0">
          <Link
            href="/auth"
            onClick={onClose}
            className="flex items-center gap-2.5 px-3 py-2 rounded-md text-sm text-text-dim hover:text-text-primary hover:bg-bg-tertiary transition-colors duration-150"
          >
            <Wallet className="w-4 h-4 shrink-0" strokeWidth={1.5} />
            Wallet
          </Link>
        </div>
      </aside>
    </>
  );
}
