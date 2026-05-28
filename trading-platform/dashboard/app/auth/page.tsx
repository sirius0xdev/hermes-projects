'use client';
import { useState } from 'react';
import AppShell from '@/components/layout/AppShell';
import { getAuthNonce, verifyAuthSig } from '@/lib/api';
import { signMessageSolana, signMessageEVM } from '@/lib/wallet';
import { useWallet, WALLET_KEY } from '@/hooks/useWallet';

const chains = [
  { id: 'solana' as const, name: 'Solana', symbol: 'SOL', icon: '◎', color: '#9945ff', wallet: 'Phantom' },
  { id: 'ethereum' as const, name: 'Ethereum', symbol: 'ETH', icon: '⟠', color: '#627eea', wallet: 'MetaMask' },
  { id: 'base' as const, name: 'Base', symbol: 'BASE', icon: '🔵', color: '#0052ff', wallet: 'MetaMask' },
];

const DOMAIN = typeof window !== 'undefined' ? window.location.hostname || 'sirius-sec.com' : 'sirius-sec.com';

function buildSiwsMessage(walletAddress: string, nonce: string): string {
  return [
    `${DOMAIN} wants you to sign in with your Solana account:`,
    `${walletAddress}`,
    '',
    'Sign in to the trading terminal.',
    '',
    `URI: https://${DOMAIN}`,
    `Version: 1`,
    `Chain ID: solana`,
    `Nonce: ${nonce}`,
    `Issued At: ${new Date().toISOString()}`,
  ].join('\n');
}

function buildSiweMessage(chain: 'ethereum' | 'base', walletAddress: string, nonce: string): string {
  const chainId = chain === 'ethereum' ? 1 : 8453;
  const chainName = chain === 'ethereum' ? 'Ethereum' : 'Base';
  return [
    `${DOMAIN} wants you to sign in with your account:`,
    `${walletAddress}`,
    '',
    'Sign in to the trading terminal.',
    '',
    `URI: https://${DOMAIN}`,
    `Version: 1`,
    `Chain ID: ${chainId}`,
    `Nonce: ${nonce}`,
    `Issued At: ${new Date().toISOString()}`,
  ].join('\n');
}

export default function AuthPage() {
  const [step, setStep] = useState<'select' | 'connecting' | 'signing' | 'verifying'>('select');
  const [selectedChain, setSelectedChain] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { session, isConnected, disconnect, connectSolana, connectEVM } = useWallet();

  const connect = async (chain: 'solana' | 'ethereum' | 'base') => {
    setError(null);
    setSelectedChain(chain);
    setStep('connecting');

    try {
      // Step 1: Connect to the real wallet and get the address
      let walletAddress: string;
      if (chain === 'solana') {
        walletAddress = await connectSolana();
      } else {
        walletAddress = await connectEVM();
      }

      // Step 2: Request nonce from backend
      setStep('signing');
      const { nonce } = await getAuthNonce(walletAddress, chain);

      // Step 3: Build SIWS (Solana) or SIWE (EVM) message
      const message = chain === 'solana'
        ? buildSiwsMessage(walletAddress, nonce)
        : buildSiweMessage(chain, walletAddress, nonce);

      // Step 4: Sign with real wallet
      let signature: string;
      if (chain === 'solana') {
        signature = await signMessageSolana(walletAddress, message);
      } else {
        signature = await signMessageEVM(walletAddress, message);
      }

      // Step 5: Verify signature with backend
      setStep('verifying');
      const result = await verifyAuthSig(chain, walletAddress, message, signature);

      // Step 6: Persist session
      const sessionData = {
        chain,
        walletAddress: result.wallet_address,
        accessToken: result.access_token,
        expiresAt: Date.now() + result.expires_in * 1000,
      };
      localStorage.setItem(WALLET_KEY, JSON.stringify(sessionData));
      localStorage.setItem('token', result.access_token);

      setStep('select');
      window.location.href = '/market';
    } catch (err: any) {
      setError(err?.message || 'Connection failed');
      setStep('select');
    }
  };

  return (
    <AppShell>
      <div className="max-w-lg mx-auto space-y-6">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-text-primary">Connect Wallet</h2>
          <p className="text-sm text-text-secondary mt-2">Sign in with your Web3 wallet to access the trading terminal</p>
        </div>

        {isConnected && session ? (
          <div className="bg-bg-card rounded-xl border border-accent/30 p-6 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full flex items-center justify-center text-lg"
                  style={{ backgroundColor: '#0a0e17' }}>
                  {chains.find(c => c.id === session.chain)?.icon}
                </div>
                <div>
                  <div className="text-sm font-semibold text-text-primary">{chains.find(c => c.id === session.chain)?.name}</div>
                  <div className="text-xs font-mono text-text-secondary">{session.walletAddress.slice(0, 8)}...{session.walletAddress.slice(-6)}</div>
                  <div className="text-xs text-text-muted mt-1">Expires: {new Date(session.expiresAt ?? 0).toLocaleString()}</div>
                </div>
              </div>
              <button onClick={disconnect} className="text-text-muted hover:text-text-primary text-sm">Disconnect</button>
            </div>
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-up/10">
              <span className="w-2 h-2 rounded-full bg-up animate-pulse" />
              <span className="text-sm text-up font-medium">Connected & Ready to Trade</span>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            {chains.map(chain => (
              <button key={chain.id} onClick={() => connect(chain.id)} disabled={step !== 'select'}
                className="w-full flex items-center gap-4 p-4 rounded-xl border border-border bg-bg-card hover:border-accent transition-colors disabled:opacity-50 text-left">
                <div className="w-12 h-12 rounded-xl flex items-center justify-center text-2xl" style={{ backgroundColor: chain.color + '20' }}>
                  {chain.icon}
                </div>
                <div className="flex-1">
                  <div className="text-sm font-semibold text-text-primary">{chain.name}</div>
                  <div className="text-xs text-text-secondary">{chain.wallet} · {chain.symbol} network</div>
                </div>
                {step !== 'select' && selectedChain === chain.id ? (
                  <div className="w-5 h-5 border-2 border-accent border-t-transparent rounded-full animate-spin" />
                ) : (
                  <span className="text-accent text-sm font-medium">Connect</span>
                )}
              </button>
            ))}
          </div>
        )}

        {error && <p className="text-sm text-down text-center font-medium">{error}</p>}

        <div className="text-center text-xs text-text-muted space-y-1">
          <p>Supports SIWE (Ethereum / Base) and SIWS (Solana) authentication</p>
          <p>Auth endpoints: /api/auth/nonces, /api/auth/verify, /api/auth/refresh</p>
        </div>
      </div>
    </AppShell>
  );
}
