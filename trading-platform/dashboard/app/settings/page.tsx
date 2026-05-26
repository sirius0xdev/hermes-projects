'use client';
import { useState, useEffect } from 'react';
import AppShell from '@/components/layout/AppShell';
import { Settings, Save, CheckCircle2, AlertCircle, Eye, EyeOff, RefreshCw } from 'lucide-react';

const EXEC_BASE = '/api/execute';
const CONFIG_FIELDS: { key: string; label: string; secret: boolean; description: string }[] = [
  { key: 'jwt_secret_key', label: 'JWT Secret Key', secret: true, description: 'Signing key for auth tokens — required for login to work' },
  { key: 'db_password', label: 'Database Password', secret: true, description: 'PostgreSQL password for the trading database' },
  { key: 'hyperliquid_private_key', label: 'Hyperliquid Private Key', secret: true, description: 'Wallet private key for Hyperliquid order execution' },
  { key: 'hyperliquid_wallet_address', label: 'Hyperliquid Wallet Address', secret: false, description: 'Public wallet address on Hyperliquid' },
  { key: 'hyperliquid_testnet', label: 'Hyperliquid Testnet Mode', secret: false, description: 'Use testnet instead of mainnet (true/false)' },
  { key: 'solana_private_key_base58', label: 'Solana Private Key (Base58)', secret: true, description: 'Wallet private key for Solana order execution' },
  { key: 'solana_rpc_url', label: 'Solana RPC URL', secret: false, description: 'Solana RPC endpoint (default: https://api.devnet.solana.com)' },
];

export default function SettingsPage() {
  const [configStatus, setConfigStatus] = useState<Record<string, boolean>>({});
  const [formValues, setFormValues] = useState<Record<string, string>>({});
  const [visible, setVisible] = useState<Record<string, boolean>>({});
  const [statusMsg, setStatusMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);

  const loadStatus = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${EXEC_BASE}/settings`);
      if (!res.ok) throw new Error('Failed to load');
      const data = await res.json();
      setConfigStatus(data.configured || {});
    } catch {
      // Settings endpoint may not exist yet — silent fail
    }
    setLoading(false);
  };

  useEffect(() => { loadStatus(); }, []);

  const save = async () => {
    setSaving(true);
    setStatusMsg(null);
    try {
      const payload: Record<string, string> = {};
      for (const key of Object.keys(formValues)) {
        if (formValues[key].trim()) {
          payload[key] = formValues[key].trim();
        }
      }
      if (Object.keys(payload).length === 0) {
        setStatusMsg({ ok: false, text: 'No values to save — fill in at least one field.' });
        setSaving(false);
        return;
      }
      const res = await fetch(`${EXEC_BASE}/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error((await res.json()).detail || 'Save failed');
      const data = await res.json();
      setConfigStatus(data.configured || {});
      setFormValues({});
      setStatusMsg({ ok: true, text: 'Settings saved. Changes take effect on next service restart.' });
    } catch (e: any) {
      setStatusMsg({ ok: false, text: e.message || 'Failed to save settings' });
    }
    setSaving(false);
  };

  return (
    <AppShell>
      <div className="max-w-2xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-accent/10 flex items-center justify-center">
            <Settings className="w-4 h-4 text-accent" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-text">Service Settings</h2>
            <p className="text-[11px] text-text-dim mt-0.5">Configure API keys and credentials for the trading platform</p>
          </div>
        </div>

        {/* Status message */}
        {statusMsg && (
          <div className={`flex items-center gap-2 px-4 py-3 rounded-lg text-sm ${
            statusMsg.ok ? 'bg-long-muted text-long border border-long/20' : 'bg-short-muted text-short border border-short/20'
          }`}>
            {statusMsg.ok ? <CheckCircle2 className="w-4 h-4 shrink-0" /> : <AlertCircle className="w-4 h-4 shrink-0" />}
            <span>{statusMsg.text}</span>
          </div>
        )}

        {/* Config fields */}
        <div className="space-y-4">
          {CONFIG_FIELDS.map(field => {
            const isSet = configStatus[field.key];
            const val = formValues[field.key] || '';
            const show = visible[field.key] || false;

            return (
              <div key={field.key} className="card-hover p-4">
                <div className="flex items-center justify-between mb-1">
                  <label className="text-sm font-semibold text-text">{field.label}</label>
                  <span className={`text-[10px] font-medium px-2 py-0.5 rounded ${
                    isSet ? 'bg-long-muted text-long' : 'bg-bg-tertiary text-text-dim'
                  }`}>
                    {isSet ? 'configured' : 'not set'}
                  </span>
                </div>
                <p className="text-xs text-text-dim mb-2">{field.description}</p>
                <div className="flex gap-2">
                  <div className="relative flex-1">
                    <input
                      type={field.secret && !show ? 'password' : 'text'}
                      placeholder={isSet ? 'Leave blank to keep current value' : `Enter ${field.label.toLowerCase()}...`}
                      value={val}
                      onChange={e => setFormValues({ ...formValues, [field.key]: e.target.value })}
                      className="w-full bg-bg-elevated border border-bg-border rounded-lg px-3 py-2 text-sm text-text placeholder-text-dim/40 outline-none focus:border-accent/50 transition-colors"
                    />
                    {field.secret && (
                      <button
                        onClick={() => setVisible({ ...visible, [field.key]: !show })}
                        className="absolute right-2 top-1/2 -translate-y-1/2 text-text-dim hover:text-text-secondary"
                        tabIndex={-1}
                      >
                        {show ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Save */}
        <button
          onClick={save}
          disabled={saving}
          className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-lg bg-accent text-white font-medium text-sm hover:bg-accent/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {saving ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          {saving ? 'Saving...' : 'Save Settings'}
        </button>

        {/* Key info */}
        <div className="text-xs text-text-dim text-center space-y-1">
          <p>Values are stored in the service database and are never exposed in logs or responses.</p>
          <p>Secret fields show only whether they are configured — the values cannot be read back.</p>
        </div>
      </div>
    </AppShell>
  );
}