// BigBrainProviders — model registry + subscription connection buttons.
// Talks to the BigBrain server REST endpoints (Phase 3/4 of the models
// plan): GET /api/models, GET/POST /api/auth/codex/*, /api/auth/mistral/*.

import { useCallback, useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';

interface ModelEntry {
  key: string;
  display_name: string;
  provider: string;
  available: boolean;
  reasoning: boolean;
}

const POLL_MS = 3000;

async function api(path: string, opts?: RequestInit) {
  const response = await fetch(path, opts);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error((body as any).error || `HTTP ${response.status}`);
  }
  return response.json();
}

export function BigBrainProviders() {
  const [models, setModels] = useState<ModelEntry[]>([]);
  const [codexStatus, setCodexStatus] = useState<string>('Checking…');
  const [mistralStatus, setMistralStatus] = useState<string>('');
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const data = await api('/api/models');
      setModels(data.models || []);
    } catch (e) {
      setModels([]);
    }
    try {
      const status = await api('/api/auth/codex/status');
      setCodexStatus(
        status.authenticated
          ? `Signed in: ${status.email || status.type}`
          : (status.error || 'Not signed in')
      );
    } catch (e) {
      setCodexStatus('Unavailable');
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const connectCodex = async () => {
    setBusy(true);
    try {
      // The server opens the authUrl in a browser; codex owns the OAuth
      // callback and writes ~/.codex. Poll status until signed in.
      await api('/api/auth/codex/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ open_browser: true }),
      });
      setCodexStatus('Waiting for sign-in…');
      const poll = setInterval(async () => {
        const status = await api('/api/auth/codex/status');
        if (status.authenticated) {
          clearInterval(poll);
          setCodexStatus(`Signed in: ${status.email || status.type}`);
          refresh();
        }
      }, POLL_MS);
    } catch (e: any) {
      setCodexStatus(e.message);
    } finally {
      setBusy(false);
    }
  };

  const connectMistral = async () => {
    setBusy(true);
    try {
      const summary = await api('/api/auth/mistral/start', { method: 'POST' });
      if (summary.sign_in_url) window.open(summary.sign_in_url, '_blank');
      setMistralStatus('Waiting for sign-in…');
      const poll = setInterval(async () => {
        const state = await api('/api/auth/mistral/poll');
        setMistralStatus(`Mistral: ${state.status}`);
        if (state.status === 'completed') {
          clearInterval(poll);
          const result = await api('/api/auth/mistral/complete', { method: 'POST' });
          setMistralStatus(`Connected (${result.health})`);
          refresh();
        } else if (['expired', 'denied', 'error'].includes(state.status)) {
          clearInterval(poll);
          setMistralStatus(`Mistral: ${state.message || state.status}`);
        }
      }, POLL_MS);
    } catch (e: any) {
      setMistralStatus(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-4 px-4 py-3">
      <div className="flex items-center gap-2">
        <span
          className="text-[11px] font-semibold uppercase tracking-wider"
          style={{ color: 'var(--text-tertiary)' }}
        >
          Providers
        </span>
        <button
          onClick={refresh}
          disabled={busy}
          className="ml-auto p-1.5 rounded-md transition-colors duration-150 cursor-pointer"
          style={{ color: 'var(--text-tertiary)' }}
          aria-label="Refresh providers"
        >
          <RefreshCw size={13} />
        </button>
      </div>

      {/* Compact: one row per CONNECTED provider group, then a muted
          summary line for the rest of the registry. */}
      <ul className="flex flex-col gap-1">
        {models.length === 0 && (
          <li className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
            Registry unavailable (server not connected?)
          </li>
        )}
        {(() => {
          const available = models.filter((m) => m.available);
          const rest = models.length - available.length;
          // Group available models by provider label.
          const groups = new Map<string, number>();
          for (const m of available) {
            const group = m.provider.includes('openrouter')
              ? 'OpenRouter'
              : m.provider === 'codex'
                ? 'Codex (ChatGPT)'
                : m.provider === 'anthropic_oauth'
                  ? 'Claude subscription'
                  : m.display_name.split('(')[0].trim();
            groups.set(group, (groups.get(group) || 0) + 1);
          }
          const rows = [...groups.entries()];
          if (rows.length === 0 && models.length > 0) {
            return (
              <li className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                No provider connected — set a key or use a button below.
              </li>
            );
          }
          return (
            <>
              {rows.map(([group, count]) => (
                <li
                  key={group}
                  className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-[12.5px]"
                  style={{
                    backgroundColor: 'var(--bg-surface)',
                    border: '1px solid var(--border-subtle)',
                    color: 'var(--text-primary)',
                  }}
                >
                  <span
                    aria-hidden
                    className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                    style={{ backgroundColor: 'var(--success)' }}
                  />
                  <span className="truncate">{group}</span>
                  <span className="ml-auto text-[11px]" style={{ color: 'var(--text-tertiary)' }}>
                    {count} model{count > 1 ? 's' : ''}
                  </span>
                </li>
              ))}
              {rest > 0 && (
                <li
                  className="flex items-center gap-2 px-3 py-1 text-[11.5px]"
                  style={{ color: 'var(--text-tertiary)' }}
                >
                  + {rest} more in registry (no key set)
                </li>
              )}
            </>
          );
        })()}
      </ul>

      <div className="flex flex-col gap-2">
        <button
          onClick={connectCodex}
          disabled={busy}
          className="px-3 py-2 rounded-lg text-[13px] font-medium transition-colors duration-150 cursor-pointer"
          style={{
            backgroundColor: 'var(--accent-blue, #0071e3)',
            color: '#fff',
          }}
        >
          Connect with ChatGPT
        </button>
        <span className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>
          {codexStatus}
        </span>

        <button
          onClick={connectMistral}
          disabled={busy}
          className="px-3 py-2 rounded-lg text-[13px] font-medium transition-colors duration-150 cursor-pointer"
          style={{
            backgroundColor: 'var(--bg-button, #1a1a1a)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border-subtle)',
          }}
        >
          Connect with Mistral
        </button>
        <span className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>
          {mistralStatus}
        </span>
      </div>
    </div>
  );
}
