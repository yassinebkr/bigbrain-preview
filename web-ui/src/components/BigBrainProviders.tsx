// BigBrainProviders — model registry + subscription connection buttons.
// Talks to the BigBrain server REST endpoints (Phase 3/4 of the models
// plan): GET /api/models, GET/POST /api/auth/codex/*, /api/auth/mistral/*.

import { useCallback, useEffect, useRef, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { startCodexLogin } from '@/lib/codexLogin';

interface ModelEntry {
  key: string;
  display_name: string;
  provider: string;
  available: boolean;
  reasoning: boolean;
}

const POLL_MS = 3000;

async function api(path: string, opts?: RequestInit) {
  const response = await fetch(path, { ...opts, signal: opts?.signal
    ? AbortSignal.any([opts.signal, AbortSignal.timeout(15000)]) : AbortSignal.timeout(15000) });
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
  const [orKey, setOrKey] = useState('');
  const [orStatus, setOrStatus] = useState<string>('');
  const [mistralStudioKey, setMistralStudioKey] = useState('');
  const [mistralStudioStatus, setMistralStudioStatus] = useState<string>('');
  const [busy, setBusy] = useState(false);
  const [codexPending, setCodexPending] = useState(false);
  const [codexUrl, setCodexUrl] = useState('');
  const codexFlow = useRef<ReturnType<typeof startCodexLogin> | null>(null);
  useEffect(() => () => { codexFlow.current?.stop(); codexFlow.current = null; }, []);

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
    if (codexFlow.current) return;
    setCodexPending(true);
    const flow = startCodexLogin({ request: api,
      open: () => window.open('about:blank', '_blank'), status: setCodexStatus,
      link: setCodexUrl, connected: () => { void refresh(); } });
    codexFlow.current = flow;
    try {
      await flow.done;
    } finally {
      if (codexFlow.current === flow) { codexFlow.current = null; setCodexPending(false); }
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
          setMistralStatus(`Connected (${result.health}) — provider reloaded`);
          await api('/api/system/reload-provider', { method: 'POST' }).catch(() => {});
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

      <details className="rounded-lg" style={{ border: '1px solid var(--border-subtle)' }}>
        <summary className="px-3 py-2 text-[12.5px] cursor-pointer select-none" style={{ color: 'var(--text-secondary)' }}>
          {models.filter((model) => model.available).length} modèles disponibles
          <span className="ml-1 text-[11px]" style={{ color: 'var(--text-tertiary)' }}>sur {models.length}</span>
        </summary>
      <ul className="flex flex-col gap-1 px-2 pb-2">
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
            const group = m.key.startsWith('openrouter-')
              ? 'OpenRouter'
              : m.key.startsWith('mistral-studio-')
                ? 'Mistral Studio'
              : m.key.startsWith('mistral-')
                ? 'Mistral Vibe'
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
      </details>

      <div className="flex flex-col gap-2">
        {/* OpenRouter (API): paste-key flow. Validated server-side with the
            FREE /auth/key probe, stored like the Mistral key (never
            returned to the client). */}
        <input
          type="password"
          value={orKey}
          onChange={(e) => setOrKey(e.target.value)}
          placeholder="OpenRouter API key (sk-or-v1-…)"
          className="px-3 py-2 rounded-lg text-[12.5px] outline-none"
          style={{
            backgroundColor: 'var(--bg-input)',
            border: '1px solid var(--border-input)',
            color: 'var(--text-primary)',
          }}
        />
        <button
          onClick={async () => {
            if (!orKey.trim()) { setOrStatus('Paste a key first'); return; }
            setBusy(true);
            try {
              await api('/api/auth/openrouter/key', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key: orKey.trim() }),
              });
              setOrKey('');
              setOrStatus('OpenRouter connected — provider reloaded');
              await api('/api/system/reload-provider', { method: 'POST' }).catch(() => {});
              refresh();
            } catch (e: any) {
              setOrStatus(e.message);
            } finally {
              setBusy(false);
            }
          }}
          disabled={busy}
          className="px-3 py-2 rounded-lg text-[13px] font-medium transition-colors duration-150 cursor-pointer"
          style={{
            backgroundColor: 'var(--bg-button, #1a1a1a)',
            color: 'var(--text-primary)',
            border: '1px solid var(--border-subtle)',
          }}
        >
          Connect with OpenRouter (API)
        </button>
        {orStatus && (
          <span className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>
            {orStatus}
          </span>
        )}

        <input
          type="password"
          value={mistralStudioKey}
          onChange={(e) => setMistralStudioKey(e.target.value)}
          placeholder="Mistral Studio API key"
          className="px-3 py-2 rounded-lg text-[12.5px] outline-none"
          style={{ backgroundColor: 'var(--bg-input)', border: '1px solid var(--border-input)', color: 'var(--text-primary)' }}
        />
        <button
          onClick={async () => {
            if (!mistralStudioKey.trim()) { setMistralStudioStatus('Paste a key first'); return; }
            setBusy(true);
            try {
              await api('/api/auth/mistral-studio/key', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key: mistralStudioKey.trim() }),
              });
              setMistralStudioKey('');
              setMistralStudioStatus('Mistral Studio connected — provider reloaded');
              await api('/api/system/reload-provider', { method: 'POST' }).catch(() => {});
              refresh();
            } catch (e: any) {
              setMistralStudioStatus(e.message);
            } finally {
              setBusy(false);
            }
          }}
          disabled={busy}
          className="px-3 py-2 rounded-lg text-[13px] font-medium cursor-pointer"
          style={{ backgroundColor: 'var(--bg-button, #1a1a1a)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
        >
          Connect Mistral Studio API
        </button>
        {mistralStudioStatus && <span className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>{mistralStudioStatus}</span>}

        <button
          onClick={connectCodex}
          disabled={busy || codexPending}
          className="px-3 py-2 rounded-lg text-[13px] font-medium transition-colors duration-150 cursor-pointer"
          style={{
            backgroundColor: 'var(--accent-blue, #0071e3)',
            color: '#fff',
          }}
        >
          {codexPending ? 'Connexion ChatGPT en cours…' : 'Connect with ChatGPT'}
        </button>
        <span className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>
          {codexStatus}
        </span>

        {codexUrl && <a href={codexUrl} target="_blank" rel="noreferrer" className="text-[12px] underline" style={{ color: 'var(--accent-blue)' }}>Ouvrir la connexion ChatGPT</a>}

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
