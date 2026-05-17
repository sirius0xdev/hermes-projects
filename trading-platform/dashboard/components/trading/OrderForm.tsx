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

  // Percentage presets based on available balance mock
  const pctValues = [25, 50, 75, 100];
  const handlePctClick = (pct: number) => {
    const mockBalance = 18250;
    const currentPrice = parseFloat(price || '0') || 43250;
    const total = (mockBalance * pct / 100) * leverage.length;
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
        <div className="flex gap-1 mb-2">
          {(['Hyperliquid', 'Solana'] as const).map(c => (
            <button key={c} type="button" onClick={() => setChain(c)}
              className={chain === c
                ? 'bg-accent/20 text-accent border border-accent'
                : 'bg-bg-tertiary text-text-muted border border-border'}
              style={{ flex: 1, padding: '5px 0', fontSize: '12px', fontWeight: 600, borderRadius: '6px' }}>
              {c === 'Hyperliquid' ? '⬡ Hyperliquid Futures' : '◎ Solana Swaps'}
            </button>
          ))}
        </div>

        {/* Buy/Sell toggle */}
        <div className="flex gap-1">
          {(['BUY', 'SELL'] as const).map(s => (
            <button key={s} type="button" onClick={() => setSide(s)}
              className={side === s
                ? (s === 'BUY' ? 'bg-up text-bg-primary' : 'bg-down text-white')
                : 'bg-bg-tertiary text-text-secondary'}
              style={{ flex: 1, padding: '8px 0', fontSize: '14px', fontWeight: 700, borderRadius: '8px' }}>
              {s}
            </button>
          ))}
        </div>

        {/* Order type toggle */}
        <div className="flex gap-1">
          {(['MARKET', 'LIMIT', 'STOP'] as const).map(t => (
            <button key={t} type="button" onClick={() => setType(t)}
              className={type === t
                ? 'border-accent text-accent bg-accent/10'
                : 'border-border text-text-muted bg-bg-tertiary'}
              style={{ flex: 1, padding: '5px 0', fontSize: '12px', fontWeight: 500, borderRadius: '6px', borderStyle: 'solid', borderWidth: '1px' }}>
              {t}
            </button>
          ))}
        </div>

        {/* Price input */}
        {showPriceInput && (
          <label className="block">
            <span className="text-xs text-text-secondary">{showStopInput ? 'Limit Price' : 'Price (USDC)'}</span>
            <input type="number" step="any" value={price} onChange={e => setPrice(e.target.value)}
              className="w-full mt-1 px-3 py-2.5 bg-bg-tertiary border border-border rounded-lg text-sm font-mono text-text-primary focus:outline-none focus:border-accent"
              placeholder="0.00" />
          </label>
        )}

        {/* Stop price input */}
        {showStopInput && (
          <label className="block">
            <span className="text-xs text-text-secondary">Trigger Price (USDC)</span>
            <input type="number" step="any" value={stopPrice} onChange={e => setStopPrice(e.target.value)}
              className="w-full mt-1 px-3 py-2.5 bg-bg-tertiary border border-border rounded-lg text-sm font-mono text-text-primary focus:outline-none focus:border-amber-500"
              placeholder="0.00" />
          </label>
        )}

        {/* Amount input */}
        <label className="block">
          <span className="text-xs text-text-secondary">Amount ({symbol.split('-')[0]})</span>
          <input type="number" step="any" value={amount} onChange={e => setAmount(e.target.value)}
            className="w-full mt-1 px-3 py-2.5 bg-bg-tertiary border border-border rounded-lg text-sm font-mono text-text-primary focus:outline-none focus:border-accent"
            placeholder="0.00" />
        </label>

        {/* Percentage presets */}
        <div className="flex gap-1">
          {pctValues.map(pct => (
            <button key={pct} type="button" onClick={() => handlePctClick(pct)}
              className="flex-1 py-1 text-xs font-medium bg-bg-tertiary text-text-muted border border-border rounded hover:text-accent hover:border-accent/50 transition-colors">
              {pct}%
            </button>
          ))}
        </div>

        {/* Leverage */}
        <label className="block">
          <span className="text-xs text-text-secondary">Leverage: <span className="text-accent font-semibold">{leverage}x</span></span>
          <input type="range" min="1" max="50" value={leverage} onChange={e => setLeverage(e.target.value)}
            className="w-full mt-1 accent-accent" />
          <div className="flex justify-between text-xs text-text-muted mt-0.5">
            <span>1x</span><span>25x</span><span>50x</span>
          </div>
        </label>

        {/* Estimated cost */}
        <div className="text-xs text-text-secondary space-y-1 pt-2 border-t border-border">
          <div className="flex justify-between">
            <span>Price</span>
            <span className="font-mono">{typeof effectivePrice === 'string' && effectivePrice === 'Market' ? 'Market' : `$${Number(effectivePrice).toLocaleString()}`}</span>
          </div>
          <div className="flex justify-between">
            <span>Amount</span>
            <span className="font-mono">{amount || '0'}</span>
          </div>
          <div className="flex justify-between">
            <span>Est. Total</span>
            <span className="font-mono text-text-primary font-semibold">
              ${(amount && effectivePrice !== 'Market') ? (parseFloat(amount) * parseFloat(effectivePrice as string)).toLocaleString(undefined, { minimumFractionDigits: 2 }) : '—'}
            </span>
          </div>
        </div>

        <button type="submit" disabled={loading}
          className={`w-full py-3 rounded-lg text-sm font-semibold ${side === 'BUY' ? 'bg-up hover:bg-up/90' : 'bg-down hover:bg-down/90'} text-bg-primary disabled:opacity-50 transition-colors`}>
          {loading ? 'Submitting...' : `Place ${side === 'BUY' ? 'Buy' : 'Sell'} ${type}`}
        </button>
      </form>

      {/* Confirmation modal */}
      {confirmOpen && confirmOrder && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" role="dialog" aria-modal="true">
          <div className="bg-bg-card border border-border rounded-2xl p-6 w-full max-w-sm mx-4 shadow-2xl">
            <h3 className="text-lg font-bold text-text-primary mb-4">Confirm Order</h3>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-text-secondary">Side</span>
                <span className={`font-semibold ${confirmOrder.side === 'BUY' ? 'text-up' : 'text-down'}`}>{confirmOrder.side}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">Type</span>
                <span className="text-text-primary font-semibold">{confirmOrder.type}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">Symbol</span>
                <span className="text-text-primary font-mono">{confirmOrder.symbol}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">Chain</span>
                <span className="text-text-primary">{confirmOrder.chain === 'Hyperliquid' ? '⬡ Hyperliquid' : '◎ Solana'}</span>
              </div>
              {confirmOrder.price && (
                <div className="flex justify-between">
                  <span className="text-text-secondary">Price</span>
                  <span className="text-text-primary font-mono">${Number(confirmOrder.price).toLocaleString()}</span>
                </div>
              )}
              {confirmOrder.stopPrice && (
                <div className="flex justify-between">
                  <span className="text-text-secondary">Trigger</span>
                  <span className="text-amber-400 font-mono">${Number(confirmOrder.stopPrice).toLocaleString()}</span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-text-secondary">Amount</span>
                <span className="text-text-primary font-mono">{confirmOrder.amount}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">Leverage</span>
                <span className="text-accent font-semibold">{confirmOrder.leverage}x</span>
              </div>
              <div className="flex justify-between pt-2 border-t border-border">
                <span className="text-text-secondary font-semibold">Total</span>
                <span className="text-text-primary font-mono font-bold">
                  ${confirmOrder.price ? (confirmOrder.amount * confirmOrder.price).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : 'Market'}
                </span>
              </div>
            </div>

            <div className="flex gap-3 mt-6">
              <button onClick={() => setConfirmOpen(false)}
                className="flex-1 py-2.5 rounded-lg border border-border text-text-secondary hover:text-text-primary transition-colors font-medium">
                Cancel
              </button>
              <button onClick={handleConfirm}
                className={`flex-1 py-2.5 rounded-lg ${confirmOrder.side === 'BUY' ? 'bg-up' : 'bg-down'} text-bg-primary font-semibold hover:opacity-90 transition-colors`}>
                Confirm {confirmOrder.side}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
