/**
 * Web3 wallet integration utilities.
 *
 * Phantom  (Solana) — window.phantom?.solana
 * MetaMask (EVM)    — window.ethereum
 */

// ── Window type declarations ──────────────────────────────────────────────
declare global {
  interface Window {
    phantom?: {
      solana?: SolanaProvider;
    };
    ethereum?: EvmProvider;
  }
}

// ── Provider interfaces ────────────────────────────────────────────────────
interface SolanaProvider {
  isPhantom?: boolean;
  connect: () => Promise<{ publicKey: { toString: () => string } }>;
  signMessage: (
    message: Uint8Array | string,
    options?: { encoding?: 'utf8' | 'utf8bytes' }
  ) => Promise<{ signature: Uint8Array }>;
}

interface EvmProvider {
  isMetaMask?: boolean;
  request: (request: { method: string; params?: unknown[] }) => Promise<unknown>;
}

// ── Helpers ─────────────────────────────────────────────────────────────────
function toHex(bytes: Uint8Array): string {
  return '0x' + Array.from(bytes)
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');
}

// ── Solana / Phantom ───────────────────────────────────────────────────────
export async function detectAndConnectSolana(): Promise<string> {
  const provider = window.phantom?.solana;
  if (!provider) {
    throw new Error(
      'Phantom wallet not detected. Install it from phantom.app and try again.'
    );
  }

  // Auto-open extension if available
  if ((provider as any).isConnected === false && (provider as any).connected === false) {
    await provider.connect();
  }

  const { publicKey } = await provider.connect();
  return publicKey.toString();
}

export async function signMessageSolana(
  address: string,
  message: string,
): Promise<string> {
  const provider = window.phantom?.solana;
  if (!provider) {
    throw new Error('Phantom wallet not available.');
  }

  const uint8Msg = typeof message === 'string'
    ? new TextEncoder().encode(message)
    : message;

  const { signature } = await provider.signMessage(uint8Msg, { encoding: 'utf8' });
  return toHex(signature);
}

// ── EVM / MetaMask ─────────────────────────────────────────────────────────
export async function detectAndConnectEVM(): Promise<string> {
  const provider = window.ethereum;
  if (!provider) {
    throw new Error(
      'MetaMask not detected. Install it from metamask.io and try again.'
    );
  }

  const accounts = await provider.request({
    method: 'eth_requestAccounts',
  }) as string[];

  if (!accounts?.length) {
    throw new Error('No accounts returned from MetaMask.');
  }

  return accounts[0].toLowerCase();
}

export async function signMessageEVM(address: string, message: string): Promise<string> {
  const provider = window.ethereum;
  if (!provider) {
    throw new Error('MetaMask not available.');
  }

  const signature = await provider.request({
    method: 'eth_sign',
    params: [address, message],
  });

  return signature as string;
}
