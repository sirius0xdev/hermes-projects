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
        {/* Header — Section 9 tactical */}
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-neon-cyan/10 border border-neon-cyan/20 flex items-center justify-center">
            <Settings className="w-4 h-4 text-neon-cyan" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-text tracking-tight">Service Settings</h2>
            <p className="text-[11px] text-text-dim mt-0.5">Configure API keys and credentials for the trading platform</p>
          </div>
        </div>

        {/* Status message — neon alerts */}
        {statusMsg && (
          <div className={`flex items-center gap-2 px-4 py-3 rounded-lg text-sm border ${
            statusMsg.ok 
              ? 'bg-neon-cyan/5 text-neon-cyan border-neon-cyan/20' 
              : 'bg-pink/5 text-pink border-pink/20'
          }`}>
            {statusMsg.ok ? <CheckCircle2 className="w-4 h-4 shrink-0" /> : <AlertCircle className="w-4 h-4 shrink-0" />}
            <span>{statusMsg.text}</span>
          </div>
        )}

        {/* Config fields — neon cards */}
        <div className="space-y-4">
          {CONFIG_FIELDS.map(field => {
            const isSet = configStatus[field.key];
            const val = formValues[field.key] || '';
            const show = visible[field.key] || false;

            return (
              <div key={field.key} className="neon-card p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-sm font-semibold text-text">{field.label}</label>
                  <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full border ${
                    isSet 
                      ? 'bg-neon-cyan/10 text-neon-cyan border-neon-cyan/30' 
                      : 'bg-bg-tertiary text-text-dim border-bg-border'
                  }`}>
                    {isSet ? 'CONFIGURED' : 'NOT SET'}
                  </span>
                </div>
                <p className="text-xs text-text-dim leading-tight">{field.description}</p>
                
                <div className="relative">
                  <input
                    type={field.secret && !show ? 'password' : 'text'}
                    placeholder={isSet ? 'Leave blank to keep current value' : `Enter ${field.label.toLowerCase()}...`}
                    value={val}
                    onChange={e => setFormValues({ ...formValues, [field.key]: e.target.value })}
                    className="input-field w-full pr-10 font-mono text-sm"
                  />
                  {field.secret && (
                    <button
                      onClick={() => setVisible({ ...visible, [field.key]: !show })}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-text-dim hover:text-neon-cyan transition-colors"
                      tabIndex={-1}
                    >
                      {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Save button — strong neon action */}
        <button
          onClick={save}
          disabled={saving}
          className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-lg bg-neon-cyan text-[#0a0a0f] font-medium text-sm hover:bg-neon-cyan/90 disabled:opacity-50 disabled:cursor-not-allowed transition-all active:scale-[0.985] neon-glow-cyan"
        >
          {saving ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          {saving ? 'Saving to service...' : 'Save Settings'}
        </button>

        {/* Key info */}
        <div className="text-xs text-text-dim text-center space-y-1">
          <p>Values stored encrypted in service_config table. Never logged or returned by the API.</p>
          <p>Secrets are write-only from the dashboard for operational security.</p>
        </div>
      </div>
    </AppShell>
  );
}
