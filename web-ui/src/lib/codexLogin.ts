/** Browser-owned login UX with a visible link and a bounded, cancellable poll. */
type Request = (path: string, options?: RequestInit) => Promise<any>;
export function startCodexLogin(options: {
  request: Request; open: () => Window | null;
  status: (text: string) => void; link: (url: string) => void; connected: () => void;
}, timeoutMs = 180_000) {
  const controller = new AbortController();
  let stopped = false;
  let opened = false;
  let popup: Window | null = null;
  try { popup = options.open(); if (popup) popup.opener = null; } catch { /* The link remains available. */ }
  const deadline = setTimeout(() => controller.abort(new Error('Connexion non confirmée dans le délai prévu. Réessaie.')), timeoutMs);
  const pause = () => new Promise<void>((resolve, reject) => {
    const abort = () => { clearTimeout(timer); reject(controller.signal.reason); };
    const timer = setTimeout(() => { controller.signal.removeEventListener('abort', abort); resolve(); }, 3000);
    controller.signal.addEventListener('abort', abort, { once: true });
    if (controller.signal.aborted) abort();
  });
  const done = (async () => {
    options.status('Préparation de la connexion ChatGPT…');
    options.link('');
    try {
      const result = await options.request('/api/auth/codex/login', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ open_browser: false }), signal: controller.signal,
      });
      if (controller.signal.aborted) throw controller.signal.reason;
      const url = new URL(result.authUrl);
      if (url.protocol !== 'https:' || url.username || url.password) throw new Error('URL de connexion invalide.');
      options.link(url.href);
      if (popup && !popup.closed) { try { popup.location.href = url.href; opened = true; } catch { /* Click the visible link. */ } }
      options.status(opened ? 'Termine la connexion dans le nouvel onglet.' : 'Ouvre le lien ci-dessous pour te connecter.');
      while (!controller.signal.aborted) {
        await pause();
        const state = await options.request('/api/auth/codex/status', { signal: controller.signal });
        if (controller.signal.aborted) throw controller.signal.reason;
        if (state.error) throw new Error(state.error);
        if (state.authenticated && state.type === 'chatgpt') {
          options.status('Connecté à ChatGPT.'); options.link(''); options.connected(); return;
        }
      }
    } catch (error) {
      if (!stopped) options.status(error instanceof Error ? error.message : String(error));
      if (!opened && popup && !popup.closed) popup.close();
    } finally { clearTimeout(deadline); }
  })();
  return { done, stop: () => { stopped = true; controller.abort(); } };
}
