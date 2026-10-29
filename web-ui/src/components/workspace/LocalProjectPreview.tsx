import { useEffect, useRef, useState } from 'react';
import { Maximize2, Minimize2, RefreshCw, X, ArrowUp, ArrowDown } from 'lucide-react';

interface Scope { id: string; revision: number }
interface Lease { previewId: string; width: number; height: number }
type Request = <T>(action: string, data?: object) => Promise<T>;

export function LocalProjectPreview({ project, entryPoint, request, onClose }: {
  project: Scope; entryPoint: string; request: Request; onClose: () => void;
}) {
  const [stack, setStack] = useState('static');
  const [image, setImage] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState(true);
  const [running, setRunning] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [text, setText] = useState('');
  const [blocked, setBlocked] = useState(0);
  const lease = useRef<Lease | null>(null);
  const mounted = useRef(true);
  const chain = useRef(Promise.resolve());
  const scope = { projectId: project.id, revision: project.revision };
  const button = 'inline-flex items-center gap-2 rounded-lg px-3 py-2 text-xs hover:bg-white/10 disabled:opacity-40';

  function release() {
    const current = lease.current;
    lease.current = null;
    if (current) void fetch('/api/local-projects/preview-close', {
      method: 'POST', keepalive: true,
      headers: { 'Content-Type': 'application/json', 'X-BigBrain-Local': '1' },
      body: JSON.stringify({ ...scope, previewId: current.previewId }),
    }).catch(() => {}).finally(() => { if (mounted.current) setChecking(false); });
  }
  useEffect(() => {
    mounted.current = true;
    void request<{ content: string }>('/read', { ...scope, path: 'package.json' }).then(result => {
      const data = JSON.parse(result.content);
      if (mounted.current && (data.dependencies?.react || data.devDependencies?.react) &&
        (data.dependencies?.vite || data.devDependencies?.vite)) setStack('react_vite');
    }).catch(() => {});
    function hide() {
      if (document.visibilityState === 'hidden') { release(); setRunning(false); }
    }
    document.addEventListener('visibilitychange', hide);
    window.addEventListener('pagehide', release);
    return () => {
      mounted.current = false;
      document.removeEventListener('visibilitychange', hide);
      window.removeEventListener('pagehide', release);
      release();
    };
  }, [project.id, project.revision, entryPoint]);

  function send(action: object = { type: 'frame' }) {
    chain.current = chain.current.then(async () => {
      const current = lease.current;
      if (!current || !mounted.current) return;
      try {
        const frame = await request<{ image: string; blockedRequests: number }>('/preview-frame', { ...scope, previewId: current.previewId, action });
        if (mounted.current && lease.current === current) { setImage(`data:image/png;base64,${frame.image}`); setBlocked(frame.blockedRequests); }
      } catch (cause) {
        if (mounted.current && lease.current === current) { setError(String(cause)); setRunning(false); release(); }
      }
    });
    return chain.current;
  }
  useEffect(() => {
    if (!running) return;
    let waiting = false;
    const timer = window.setInterval(() => {
      if (!waiting) { waiting = true; void send().finally(() => { waiting = false; }); }
    }, 1000);
    return () => window.clearInterval(timer);
  }, [running]);

  async function start() {
    release(); setBusy(true); setError('');
    try {
      const opened = await request<Lease>('/preview-open', { ...scope, entryPoint, webStack: stack });
      lease.current = opened;
      if (!mounted.current) { release(); return; }
      setRunning(true);
      await send();
    } catch (cause) { if (mounted.current) setError(String(cause)); }
    finally { if (mounted.current) setBusy(false); }
  }

  return <section aria-label="Aperçu local isolé" className={`rounded-2xl p-3 flex flex-col gap-3 ${expanded ? 'fixed inset-6 z-[70] overflow-auto shadow-2xl' : ''}`}
    style={{ backgroundColor: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}>
    <header className="flex flex-wrap items-center gap-2">
      <span className="text-sm mr-auto">Aperçu · {entryPoint}</span>
      <select aria-label="Stack de l’aperçu" className="rounded-lg p-2 text-xs" disabled={busy || running}
        style={{ backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }} value={stack} onChange={event => setStack(event.target.value)}>
        <option value="static">HTML / CSS / JavaScript</option><option value="react_vite">React / Vite</option>
      </select>
      {running ? <button className={button} onClick={() => void send({ type: 'reload' })}><RefreshCw size={14} /> Recharger</button>
        : <button className={button} disabled={busy || checking} onClick={() => void start()}>{busy || checking ? 'Préparation…' : 'Ouvrir l’aperçu'}</button>}
      <button className={button} aria-label={expanded ? 'Réduire l’aperçu' : 'Agrandir l’aperçu'} onClick={() => setExpanded(!expanded)}>{expanded ? <Minimize2 size={14} /> : <Maximize2 size={14} />}</button>
      <button className={button} aria-label="Fermer l’aperçu" onClick={onClose}><X size={14} /></button>
    </header>
    <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>Navigateur isolé · requêtes HTTP limitées au projet · données d’aperçu temporaires</p>
    {error && <p role="alert" className="text-xs text-amber-400">{error}</p>}
    {blocked > 0 && <p className="text-xs text-amber-400">{blocked} requête(s) externe(s) bloquée(s) dans cet aperçu.</p>}
    {!running && image && <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>Aperçu arrêté. Rouvre-le pour interagir.</p>}
    {image && <img src={image} alt="Aperçu interactif du projet local" tabIndex={running ? 0 : -1} aria-disabled={!running}
      className={`w-full rounded-xl outline-none focus:ring-2 focus:ring-blue-500 ${running ? 'cursor-pointer' : 'opacity-60 pointer-events-none'}`}
      style={{ aspectRatio: '1280 / 800' }}
      onClick={event => {
        event.currentTarget.focus();
        const rect = event.currentTarget.getBoundingClientRect();
        void send({ type: 'click', x: Math.min(1279, (event.clientX - rect.left) * 1280 / rect.width),
          y: Math.min(799, (event.clientY - rect.top) * 800 / rect.height) });
      }} onKeyDown={event => {
        if (event.ctrlKey || event.metaKey || event.altKey) return;
        if (event.key.length === 1) { event.preventDefault(); void send({ type: 'text', text: event.key }); }
        else if (['Enter', 'Tab', 'Backspace', 'Delete', 'Escape', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Home', 'End', 'PageUp', 'PageDown'].includes(event.key)) {
          event.preventDefault(); void send({ type: 'key', key: event.key });
        }
      }} />}
    {running && <div className="flex flex-wrap gap-2">
      <input aria-label="Texte à saisir dans l’aperçu" placeholder="Texte pour le champ sélectionné" maxLength={1000} value={text} onChange={event => setText(event.target.value)}
        className="flex-1 min-w-40 rounded-lg px-3 py-2 text-xs" style={{ backgroundColor: 'var(--bg-primary)', color: 'var(--text-primary)' }} />
      <button className={button} disabled={!text} onClick={() => { void send({ type: 'text', text }); setText(''); }}>Saisir</button>
      <button className={button} aria-label="Défiler l’aperçu vers le haut" onClick={() => void send({ type: 'scroll', delta: -500 })}><ArrowUp size={14} /></button>
      <button className={button} aria-label="Défiler l’aperçu vers le bas" onClick={() => void send({ type: 'scroll', delta: 500 })}><ArrowDown size={14} /></button>
    </div>}
  </section>;
}
