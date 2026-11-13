import { useEffect, useRef, useState } from 'react';
import { Scan } from 'lucide-react';
import type { CadView } from '@/lib/cad';
import { attachEditor } from '@/lib/cadBrowser';
import { liveRuntime, type CadLiveRuntime, type CadPreviewMode } from '@/lib/cadLiveRuntime';

/** Attach the persistent document preview to the current Atelier surface. */
export default function CadLivePreview({ cad, sessionId, mode }: {
  cad: CadView; sessionId: string; mode: CadPreviewMode;
}) {
  const slot = useRef<HTMLDivElement>(null);
  const runtime = useRef<CadLiveRuntime | undefined>(undefined);
  const [status, setStatus] = useState('Préparation de la vue…');
  useEffect(() => {
    if (!slot.current) return;
    try {
      const current = liveRuntime(cad.document_id, sessionId);
      runtime.current = current;
      const changed = () => setStatus(current.status);
      current.listeners.add(changed);
      changed();
      const detach = attachEditor(current, slot.current);
      return () => { current.listeners.delete(changed); detach(); runtime.current = undefined; };
    } catch (error) { setStatus(String(error)); }
  }, [cad.document_id, sessionId]);
  useEffect(() => { runtime.current?.update(cad); }, [cad]);
  useEffect(() => { runtime.current?.setMode(mode); }, [mode]);

  return <div className="relative h-full w-full overflow-hidden" aria-label="Preview de construction en direct">
    <div ref={slot} className="absolute inset-0 overflow-hidden" />
    <button aria-label="Recentrer" title="Recentrer" className="absolute z-[61] top-2 left-2 grid size-8 place-items-center rounded-full bg-black/60 text-white"
      onClick={() => runtime.current?.fit()}><Scan size={14} /></button>
    {mode === 'full' && <span className="absolute z-[61] bottom-2 right-2 rounded-full bg-black/70 px-3 py-1 text-[11px] text-white">Observation en lecture seule</span>}
    {status && <p role="status" className="absolute z-[61] bottom-2 inset-x-2 rounded-full bg-black/70 px-3 py-1 text-center text-[11px] text-white">{status}</p>}
  </div>;
}
