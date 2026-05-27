'use client';
import { useEffect, useState } from 'react';
import {
  ArrowUpRight,
  ArrowDownRight,
  TrendingUp,
  DollarSign,
  BarChart3,
  Clock,
} from 'lucide-react';

export interface Opportunity {
  opportunity_id: string;
  opportunity_type: string;
  symbol: string;
  title: string;
  description?: string;
  platform_a: string;
  platform_a_value: number;
  platform_a_url?: string;
  platform_b: string;
  platform_b_value: number;
  platform_b_url?: string;
  spread_pct: number;
  estimated_apr: number;
  risk_level: string;
  detected_at: string;
  expires_at?: string;
  metadata?: Record<string, unknown>;
}

type FilterType = 'all' | 'yield_spread' | 'funding_arbitrage' | 'price_differential' | 'delta_neutral_arb';

function OpportunityTypeBadge({ type }: { type: string }) {
  const config: Record<string, { label: string; bg: string; text: string }> = {
    yield_spread: { label: 'Yield Spread', bg: 'bg-neon-cyan/[0.08]', text: 'text-neon-cyan' },
    funding_arbitrage: { label: 'Funding Arb', bg: 'bg-neon-green/[0.08]', text: 'text-neon-green' },
    price_differential: { label: 'Price Diff', bg: 'bg-neon-pink/[0.08]', text: 'text-neon-pink' },
    delta_neutral_arb: { label: 'Delta Neutral', bg: 'bg-neon-purple/[0.08]', text: 'text-neon-purple' },
  };
  const c = config[type] || { label: type, bg: 'bg-bg-elevated', text: 'text-text-secondary' };
  return (
    <span className={`px-2 py-0.5 rounded text-[10px] font-semibold font-mono ${c.bg} ${c.text}`}>
      {c.label}
    </span>
  );
}

function RiskBadge({ level }: { level: string }) {
  const config: Record<string, { dot: string; label: string }> = {
    low: { dot: 'bg-neon-green', label: 'Low' },
    medium: { dot: 'bg-yellow-500', label: 'Medium' },
    high: { dot: 'bg-neon-pink', label: 'High' },
  };
  const c = config[level] || { dot: 'bg-text-dim', label: level };
  return (
    <span className="flex items-center gap-1 text-[10px] text-text-dim font-mono">
      <span className={`w-1.5 h-1.5 rounded-full ${c.dot}`} />
      {c.label} risk
    </span>
  );
}

function fmtTime(iso: string) {
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return d.toLocaleDateString();
}

export default function OpportunityCard({ opportunity }: { opportunity: Opportunity }) {
  const isPositive = opportunity.spread_pct > 0;

  return (
    <div className="bg-bg-card rounded-lg border border-bg-border p-4 hover:border-neon-cyan/20 transition-all duration-200 group">
      {/* Header */}
      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-7 h-7 rounded-md bg-neon-cyan/[0.06] flex items-center justify-center shrink-0">
            <TrendingUp className="w-3.5 h-3.5 text-neon-cyan" />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-bold text-text font-mono">{opportunity.symbol}</span>
              <OpportunityTypeBadge type={opportunity.opportunity_type} />
            </div>
            <p className="text-xs text-text-dim truncate">{opportunity.title}</p>
          </div>
        </div>
        <div className={`flex items-center gap-1 text-sm font-bold font-mono shrink-0 ${isPositive ? 'text-neon-cyan' : 'text-neon-pink'}`}>
          {isPositive ? <ArrowUpRight className="w-4 h-4" /> : <ArrowDownRight className="w-4 h-4" />}
          {opportunity.spread_pct > 0 ? '+' : ''}{opportunity.spread_pct.toFixed(2)}%
        </div>
      </div>

      {/* Description */}
      {opportunity.description && (
        <p className="text-xs text-text-dim mb-3 line-clamp-2">{opportunity.description}</p>
      )}

      {/* Platform comparison */}
      <div className="grid grid-cols-2 gap-2 mb-3">
        <div className="bg-bg-elevated rounded-md p-2.5">
          <div className="text-[10px] text-text-dim font-mono uppercase tracking-wider mb-1">{opportunity.platform_a}</div>
          <div className="text-sm font-bold font-mono text-text-secondary">
            {opportunity.platform_a_value.toFixed(2)}%
          </div>
        </div>
        <div className="bg-bg-elevated rounded-md p-2.5">
          <div className="text-[10px] text-text-dim font-mono uppercase tracking-wider mb-1">{opportunity.platform_b}</div>
          <div className="text-sm font-bold font-mono text-text-secondary">
            {opportunity.platform_b_value.toFixed(2)}%
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between text-[10px] text-text-dim font-mono">
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1">
            <DollarSign className="w-3 h-3" />
            {opportunity.estimated_apr.toFixed(2)}% APR
          </span>
          <RiskBadge level={opportunity.risk_level} />
        </div>
        <span className="flex items-center gap-1">
          <Clock className="w-3 h-3" />
          {fmtTime(opportunity.detected_at)}
        </span>
      </div>
    </div>
  );
}
