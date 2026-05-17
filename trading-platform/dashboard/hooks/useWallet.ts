import { useLocalStorage } from './useLocalStorage';

export interface WalletSession {
  chain: 'ethereum' | 'solana' | 'base';
  walletAddress: string;
  accessToken: string | null;
  expiresAt: number | null;
}

export const WALLET_KEY = 'wt-wallet-session';

export function useWallet() {
  const [session, setSession] = useLocalStorage<WalletSession | null>(WALLET_KEY, null);

  const isConnected = session !== null;
  const isExpired = session?.expiresAt ? Date.now() > session.expiresAt : false;

  const setWallet = (s: WalletSession) => setSession(s);
  const disconnect = () => setSession(null);

  return {
    session,
    isConnected,
    isExpired,
    setWallet,
    disconnect,
  };
}
