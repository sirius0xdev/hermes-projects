import { useLocalStorage } from './useLocalStorage';
import { detectAndConnectSolana, detectAndConnectEVM } from '@/lib/wallet';

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

  /** Connect to a Solana wallet (Phantom) and return the public key. */
  const connectSolana = async (): Promise<string> => detectAndConnectSolana();

  /** Connect to an EVM wallet (MetaMask) and return the address. */
  const connectEVM = async (): Promise<string> => detectAndConnectEVM();

  return {
    session,
    isConnected,
    isExpired,
    setWallet,
    disconnect,
    connectSolana,
    connectEVM,
  };
}
