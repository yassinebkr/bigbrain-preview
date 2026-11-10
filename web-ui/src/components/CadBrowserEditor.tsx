import { useEffect, useRef, useState } from 'react';
import { Loader2, Pause, Save, Square, X } from 'lucide-react';
import { attachEditor, editorAction, editorRuntime, openEditor, type EditorRuntime } from '@/lib/cadBrowser';

export default function CadBrowserEditor({ documentId, sessionId, revision, onClose }: {
  documentId: string; sessionId: string; revision: number; onClose: () => void;
}) {
  const slot = useRef<HTMLDivElement>(null);
  const [runtime, setRuntime] = useState<EditorRuntime>();
  const [error, setError] = useState('');
  const [, refresh] = useState(0);
  const [acting, setActing] = useState(false);
  useEffect(() => {
    try { setRuntime(editorRuntime(documentId, sessionId)); }
    catch (failure) { setError(String(failure)); }
  }, [documentId, sessionId]);
  useEffect(() => {
    if (!runtime || !slot.current) return;
    runtime.host.inert = false;
    const detach = attachEditor(runtime, slot.current);
    const listener = () => refresh(value => value + 1);
    runtime.listeners.add(listener);
    void openEditor(runtime, documentId, sessionId, revision);
    return () => { runtime.listeners.delete(listener); detach(); };
  }, [runtime, documentId, sessionId, revision]);
  const state = runtime?.state;
  const agent = state?.owner === 'agent';
  const action = async (name: 'save' | 'pause' | 'stop') => {
    if (!runtime) return;
    setActing(true); await editorAction(runtime, name); setActing(false);
  };
  const failure = error || runtime?.error;
  return <div className="mt-3 flex flex-col min-h-0"
    style={{ background: 'var(--bg-surface)', color: 'var(--text-primary)' }} aria-label="Éditeur SolidCraft intégré">
    <div className="flex items-center gap-2 mb-3 flex-wrap text-[11px]">
      <span className="work-muted mr-auto">{agent ? state.pause ? 'Pause en cours…' : 'L’agent travaille' : 'Édition manuelle'} · copie de travail</span>
      {agent ? <>
        <button className="work-secondary !p-2" aria-label="Mettre le travail CAO en pause" disabled={acting || !!state?.pause} onClick={() => void action('pause')}><Pause size={14} /></button>
        <button className="work-secondary !p-2" aria-label="Arrêter le travail CAO" disabled={acting} onClick={() => void action('stop')}><Square size={14} /></button>
      </> : <button className="work-secondary !p-2" aria-label="Enregistrer la copie de travail" title="Enregistrer la copie de travail" disabled={acting || !runtime?.initialized || !!failure} onClick={() => void action('save')}>
        {acting ? <Loader2 size={14} className="animate-spin" /> : <Save size={14} />}</button>}
      <button className="work-secondary !p-2" aria-label="Revenir à l’aperçu" onClick={onClose}><X size={14} /></button>
    </div>
    <div data-cad-expanded="true" className="relative rounded-xl overflow-hidden border flex-1" style={{borderColor:'var(--border-subtle)', height:'calc(100dvh - 330px)', minHeight:400}}>
      <div ref={slot} className="absolute inset-0" />
      {runtime?.loading && <p role="status" className="absolute inset-0 grid place-content-center text-[12px] pointer-events-none"><Loader2 size={22} className="animate-spin mb-3" />Chargement de SolidCraft…</p>}
    </div>
    {failure && <div className="mt-3 text-[12px]" role="alert" style={{color:'var(--warning)'}}>{failure}
      {runtime && <button className="work-link ml-3" onClick={() => void openEditor(runtime, documentId, sessionId, revision)}>Reconnecter l’éditeur</button>}</div>}
    <p className="work-muted text-[10px] mt-2">Basée sur la révision publiée {revision}{state ? ` · sauvegarde de travail ${state.revision}` : ''}. Les modifications attendent leurs contrôles avant publication.</p>
  </div>;
}
