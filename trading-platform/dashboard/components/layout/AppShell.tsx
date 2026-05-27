'use client';
import { useState } from 'react';
import Sidebar from './Sidebar';
import Header from './Header';

export default function AppShell({ children }: { children: React.ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false);
  return (
    <div className="min-h-screen flex bg-bg-primary">
      <Sidebar open={menuOpen} onClose={() => setMenuOpen(false)} />
      <div className="flex-1 flex flex-col min-w-0">
        <Header onMenuClick={() => setMenuOpen(true)} />
        <main className="flex-1 p-3 sm:p-4 xl:p-6 max-w-[1440px] w-full mx-auto animate-hud-appear pb-safe pb-16 xl:pb-6">{children}</main>
        
        {/* Mobile Bottom Navigation - trading app style */}
        <nav className="fixed bottom-0 left-0 right-0 xl:hidden bg-bg-elevated border-t border-bg-border z-50 pb-safe">
          <div className="flex items-center justify-around h-14 px-2 text-xs font-medium">
            <a href="/market" className="flex flex-col items-center gap-0.5 text-neon-cyan">
              <span className="text-lg">📊</span>
              <span>Market</span>
            </a>
            <a href="/trade" className="flex flex-col items-center gap-0.5 text-text-dim hover:text-text">
              <span className="text-lg">⚡</span>
              <span>Trade</span>
            </a>
            <a href="/portfolio" className="flex flex-col items-center gap-0.5 text-text-dim hover:text-text">
              <span className="text-lg">💼</span>
              <span>Portfolio</span>
            </a>
            <a href="/watchlist" className="flex flex-col items-center gap-0.5 text-text-dim hover:text-text">
              <span className="text-lg">⭐</span>
              <span>Watch</span>
            </a>
          </div>
        </nav>
      </div>
    </div>
  );
}