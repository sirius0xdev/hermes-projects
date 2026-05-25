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
      {open && <div className="fixed inset-0 bg-black/50 z-30 lg:hidden" onClick={onClose} />}
      <aside className={`fixed lg:sticky top-0 left-0 h-screen z-40 w-64 bg-bg-secondary border-r border-bg-border flex flex-col transition-transform duration-200 ${open ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}`}>
        <div className="p-5 border-b border-bg-border">
          <h1 className="text-base font-bold text-text-primary tracking-tight">DeFi Trader</h1>
          <p className="text-[11px] text-text-dim mt-0.5">Private Trading Terminal</p>
        </div>
        <nav className="flex-1 p-2 space-y-0.5">
          {navItems.map(item => {
            const Icon = item.icon;
            const active = pathname === item.path;
            return (
              <Link key={item.path} href={item.path} onClick={onClose}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${active ? 'bg-accent/10 text-accent' : 'text-text-dim hover:text-text-primary hover:bg-bg-tertiary'}`}>
                <Icon className="w-4 h-4 shrink-0" />
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="p-3 border-t border-bg-border">
          <Link href="/auth" onClick={onClose} className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-text-dim hover:text-text-primary hover:bg-bg-tertiary transition-colors">
            <Wallet className="w-4 h-4 shrink-0" />
            Wallet
          </Link>
        </div>
      </aside>
    </>
  );
}
