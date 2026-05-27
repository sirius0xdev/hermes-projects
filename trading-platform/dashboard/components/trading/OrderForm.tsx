'use client';
import { useState } from 'react';
import { postTrade } from '@/lib/api';

type Side = 'BUY' | 'SELL';
type OrderType = 'LIMIT' | 'MARKET' | 'STOP';

interface OrderFormProps {
  symbol: string;
  onPlaced: () => void;
}

export default function OrderForm({ symbol, onPlaced }: OrderFormProps) {
  const [side, setSide] = useState<Side>('BUY');
  const [type, setType] = useState<OrderType>('MARKET');
  const [chain, setChain] = useState<'Hyperliquid' | 'Solana'>('Hyperliquid');
  const [price, setPrice] = useState('');
  const [stopPrice, setStopPrice] = useState('');
  const [amount, setAmount] = useState('');
  const [leverage, setLeverage] = useState('5');
  const [loading, setLoading] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmOrder, setConfirmOrder] = useState<null | ReturnType<typeof buildOrderData>>(null);

  function buildOrderData() {
    return {
      symbol,
      side,
      type,
      chain,
      price: type !== 'MARKET' ? parseFloat(price || '0') : undefined,
      stopPrice: type === 'STOP' ? parseFloat(stopPrice || '0') : undefined,
      amount: parseFloat(amount || '0'),
      leverage: parseInt(leverage),
    };
  }

  const handlePreSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!amount || parseFloat(amount) <= 0) return;
    if (type !== 'MARKET' && (!price || parseFloat(price) <= 0)) return;
    if (type === 'STOP' && (!stopPrice || parseFloat(stopPrice) <= 0)) return;
    setConfirmOrder(buildOrderData());
    setConfirmOpen(true);
  };

  const handleConfirm = async () => {
    if (!confirmOrder) return;
    setLoading(true);
    const result = await postTrade({
      symbol: confirmOrder.symbol,
      side: confirmOrder.side,
      type: confirmOrder.type,
      price: confirmOrder.price,
      stopPrice: confirmOrder.stopPrice,
      amount: confirmOrder.amount,
      leverage: confirmOrder.leverage,
      chain: confirmOrder.chain,
    });
    setLoading(false);
    setConfirmOpen(false);
    if (result.ok) {
      setAmount('');
      setPrice('');
      setStopPrice('');
      onPlaced();
    }
  };

  const pctValues = [25, 50, 75, 100];
  const handlePctClick = (pct: number) => {
    const mockBalance = 18250;
    const currentPrice = parseFloat(price || '0') || 43250;
    const total = (mockBalance * pct / 100) * parseInt(leverage);
    const calculatedAmount = total / currentPrice;
    setAmount(calculatedAmount.toFixed(6));
  };

  const showPriceInput = type !== 'MARKET';
  const showStopInput = type === 'STOP';
  const effectivePrice = type === 'MARKET' ? 'Market' : price;

  return (
    <>
      <form onSubmit={handlePreSubmit} className="space-y-3">
        {/* Chain selector */}
        <div className="flex gap-1.5 mb-2">
          {(['Hyperliquid', 'Solana'] as const).map(c => (
            <button key={c} type="button" onClick={() => setChain(c)}
              className={`flex-1 py-2 text-[11px] font-semibold rounded-md border transition-all ${
                chain === c
                  ? 'bg-neon-cyan/[0.08] text-neon-cyan neon-border-cyan'
                  : 'bg-bg-elevated text-text-dim border-bg-border hover:border-bg-border-light'
              }`}>
              {c === 'Hyperliquid' ? '⬡ Hyperliquid' : '◎ Solana'}
            </button>
          ))}
        </div>

        {/* Buy/Sell toggle */}
        <div className="flex gap-1.5">
          {(['BUY', 'SELL'] as const).map(s => (
            <button key={s} type="button" onClick={() => setSide(s)}
              className={`flex-1 py-2.5 text-sm font-bold rounded-md transition-all ${
                side === s
                  ? (s === 'BUY' ? 'bg-neon-cyan text-bg-primary shadow-sm shadow-neon-cyan/20' : 'bg-neon-pink text-bg-primary shadow-sm shadow-neon-pink/20')
                  : 'bg-bg-elevated text-text-dim hover:text-text-secondary'
              }`}>
              {s === 'BUY' ? '▲ BUY' : '▼ SELL'}
            </button>
          ))}
        </div>

        {/* Order type toggle */}
        <div className="flex gap-1.5">
          {(['MARKET', 'LIMIT', 'STOP'] as const).map(t => (
            <button key={t} type="button" onClick={() => setType(t)}
              className={`flex-1 py-2 text-[11px] font-semibold rounded-md border transition-all ${
                type === t
                  ? 'neon-border-cyan text-neon-cyan bg-neon-cyan/[0.06]'
                  : 'border-bg-border text-text-dim bg-bg-elevated'
              }`}>
              {t}
            </button>
          ))}
        </div>

        {/* Price input */}
        {showPriceInput && (
          <label className="block">
            <span className="text-[11px] text-text-dim">{showStopInput ? 'Limit Price' : 'Price (USDC)'}</span>
            <input type="number" step="any" value={price} onChange={e => setPrice(e.target.value)}
              className="input-field mt-1.5" placeholder="0.00" />
          </label>
        )}

        {/* Stop price input */}
        {showStopInput && (
          <label className="block">
            <span className="text-[11px] text-text-dim">Trigger Price (USDC)</span>
            <input type="number" step="any" value={stopPrice} onChange={e => setStopPrice(e.target.value)}
              className="input-field mt-1.5 focus:ring-neon-green/50 focus:border-neon-green"
              placeholder="0.00" />
          </label>
        )}

        {/* Amount input */}
        <label className="block">
          <span className="text-[11px] text-text-dim">Amount ({symbol.split('-')[0]})</span>
          <input type="number" step="any" value={amount} onChange={e => setAmount(e.target.value)}
            className="input-field mt-1.5" placeholder="0.00" />
        </label>

        {/* Percentage presets */}
        <div className="flex gap-1.5">
          {pctValues.map(pct => (
            <button key={pct} type="button" onClick={() => handlePctClick(pct)}
              className="flex-1 py-1.5 text-[11px] font-medium bg-bg-elevated text-text-dim border border-bg-border rounded-md hover:text-neon-cyan hover:border-neon-cyan/30 transition-colors">
              {pct}%
            </button>
          ))}
        </div>

        {/* Leverage */}
        <label className="block">
          <div className="flex justify-between items-center">
            <span className="text-[11px] text-text-dim">Leverage</span>
            <span className="text-xs font-mono font-bold text-neon-cyan">{leverage}x</span>
          </div>
          <input type="range" min="1" max="50" value={leverage} onChange={e => setLeverage(e.target.value)}
            className="w-full mt-2 accent-accent" />
          <div className="flex justify-between text-[10px] text-text-dim mt-0.5">
            <span>1x</span><span>25x</span><span>50x</span>
          </div>
        </label>

        {/* Estimated cost */}
        <div className="text-[11px] text-text-dim space-y-1.5 pt-3 border-t border-bg-border">
          <div className="flex justify-between">
            <span>Price</span>
            <span className="font-mono text-text-secondary">
              {typeof effectivePrice === 'string' && effectivePrice === 'Market' ? 'Market' : `$${Number(effectivePrice).toLocaleString()}`}
            </span>
          </div>
          <div className="flex justify-between">
            <span>Amount</span>
            <span className="font-mono text-text-secondary">{amount || '0'}</span>
          </div>
          <div className="flex justify-between font-semibold">
            <span className="text-text-secondary">Est. Total</span>
            <span className="font-mono text-text">
              ${amount && effectivePrice !== 'Market' ? (parseFloat(amount) * parseFloat(effectivePrice as string)).toLocaleString(undefined, { minimumFractionDigits: 2 }) : '—'}
            </span>
          </div>
        </div>

        <button type="submit" disabled={loading}
          className={`w-full py-3 rounded-md text-sm font-bold transition-all active:scale-[0.98] ${
            side === 'BUY'
              ? 'bg-neon-cyan hover:bg-neon-cyan/90 text-bg-primary shadow-sm shadow-neon-cyan/20'
              : 'bg-neon-pink hover:bg-neon-pink/90 text-bg-primary shadow-sm shadow-neon-pink/20'
          } disabled:opacity-50`}>
          {loading ? 'Submitting...' : `Place ${side === 'BUY' ? '▲ Buy' : '▼ Sell'} ${type}`}
        </button>
      </form>

      {/* Confirmation modal */}
      {confirmOpen && confirmOrder && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" role="dialog" aria-modal="true">
          <div className="card p-6 w-full max-w-sm mx-4 shadow-2xl neon-border-cyan">
            <h3 className="text-base font-bold text-text mb-4 glitch-text" data-text="Confirm Order">Confirm Order</h3>
            <div className="space-y-2 text-sm">
              {[
                { label: 'Side', value: confirmOrder.side, cls: confirmOrder.side === 'BUY' ? 'text-neon-cyan' : 'text-neon-pink' },
                { label: 'Type', value: confirmOrder.type, cls: 'text-text' },
                { label: 'Symbol', value: confirmOrder.symbol, cls: 'text-text font-mono' },
                { label: 'Chain', value: confirmOrder.chain === 'Hyperliquid' ? '⬡ Hyperliquid' : '◎ Solana', cls: 'text-text' },
              ].map(row => (
                <div key={row.label} className="flex justify-between">
                  <span className="text-text-dim">{row.label}</span>
                  <span className={`font-semibold ${row.cls}`}>{row.value}</span>
                </div>
              ))}
              {confirmOrder.price && (
                <div className="flex justify-between">
                  <span className="text-text-dim">Price</span>
                  <span className="text-text font-mono font-semibold">${Number(confirmOrder.price).toLocaleString()}</span>
                </div>
              )}
              {confirmOrder.stopPrice && (
                <div className="flex justify-between">
                  <span className="text-text-dim">Trigger</span>
                  <span className="text-neon-green font-mono font-semibold">${Number(confirmOrder.stopPrice).toLocaleString()}</span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-text-dim">Amount</span>
                <span className="text-text font-mono font-semibold">{confirmOrder.amount}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-dim">Leverage</span>
                <span className="text-neon-cyan font-bold">{confirmOrder.leverage}x</span>
              </div>
              <div className="flex justify-between pt-2 border-t border-bg-border">
                <span className="text-text-secondary font-semibold">Total</span>
                <span className="text-text font-mono font-bold">
                  ${confirmOrder.price ? (confirmOrder.amount * confirmOrder.price).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : 'Market'}
                </span>
              </div>
            </div>

            <div className="flex gap-3 mt-5">
              <button onClick={() => setConfirmOpen(false)}
                className="flex-1 py-2.5 rounded-md border border-bg-border text-text-secondary hover:text-text transition-colors font-medium text-sm">
                Cancel
              </button>
              <button onClick={handleConfirm}
                className={`flex-1 py-2.5 rounded-md text-bg-primary font-bold text-sm ${
                  confirmOrder.side === 'BUY' ? 'bg-neon-cyan hover:bg-neon-cyan/90' : 'bg-neon-pink hover:bg-neon-pink/90'
                } transition-colors`}>
                Confirm {confirmOrder.side}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}