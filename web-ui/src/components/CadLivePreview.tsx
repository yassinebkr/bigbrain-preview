import { useEffect, useRef, useState } from 'react';
import type { CadView } from '@/lib/cad';
import { CadWorkerChannel } from '@/lib/cadWorker';
import { CadPreviewQueue } from '@/lib/cadPreviewQueue';

type Working = NonNullable<CadView['working']>;
type PreviewSource = Working & { publishedRevision?: number };
type PreviewMode = 'solid' | 'construction' | 'full';
interface NativeViewer {
  presentCached(bytes: Uint8Array): Promise<void>;
  presentation(mode: PreviewMode, sketches?: number[]): Promise<void>;
  dispose(): void;
}

/** Follow accepted native checkpoints while keeping geometry preparation off the UI thread. */
export default function CadLivePreview({ cad, sessionId, mode }: {
  cad: CadView; sessionId: string; mode: PreviewMode;
}) {
  const host = useRef<HTMLDivElement>(null);
  const queue = useRef<CadPreviewQueue<PreviewSource> | undefined>(undefined);
  const viewer = useRef<NativeViewer | undefined>(undefined);
  const published = cad.status === 'ready' ? cad.snapshot?.document : undefined;
  const source: PreviewSource | undefined = cad.working ? {
    ...cad.working, native:published?.native || cad.working.native,
    publishedRevision:published?.revision,
  } : undefined;
  const latest = useRef(source);
  latest.current = source;
  const currentMode = useRef(mode);
  currentMode.current = mode;
  const [status, setStatus] = useState('Préparation de la vue…');

  useEffect(() => {
    const container = host.current;
    if (!container) return;
    const abort = new AbortController();
    let channel: CadWorkerChannel | undefined;
    let native: NativeViewer | undefined;
    let requests: CadPreviewQueue<PreviewSource> | undefined;
    const headers = { 'Content-Type': 'application/json', 'X-BigBrain-CAD': '1' };
    const start = async () => {
      const path = '/static/cad-browser-bridge.mjs?v=live-preview-1';
      const bridge = await import(/* @vite-ignore */ path);
      const transport = new bridge.CadBrowserTransport(cad.document_id, sessionId);
      const capability = await transport.call('capability');
      if (abort.signal.aborted) return;
      if (!capability.available || !capability.worker)
        throw new Error(capability.diagnostic || 'Moteur de preview indisponible');
      native = new bridge.SolidCraftBrowserEngine(container, capability.url, capability.build);
      viewer.current = native;
      const address = new URL(capability.worker, location.href);
      if (address.origin !== location.origin) throw new Error('Origine du moteur de preview invalide');
      channel = new CadWorkerChannel(new Worker(address, { type: 'module' }));
      requests = new CadPreviewQueue<PreviewSource>(async working => {
        const endpoint = working.publishedRevision ? 'artifact' : 'working-artifact';
        const response = await fetch(`/api/cad/${endpoint}`, { method:'POST', headers,
          signal:abort.signal, body:JSON.stringify({ documentId:cad.document_id,
            sessionId, checkpointId:working.checkpoint_id, kind:'native', revision:working.publishedRevision }) });
        if (!response.ok) throw new Error((await response.json()).error || 'Étape indisponible');
        const bytes = new Uint8Array(await response.arrayBuffer());
        const hash = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)))
          .map(value => value.toString(16).padStart(2, '0')).join('');
        if (hash !== working.native.sha256) throw new Error('Identité de la preview modifiée');
        await channel!.request('open', { bytes });
        const cached = await channel!.request('save');
        if (!(cached instanceof Uint8Array)) throw new Error('État de preview invalide');
        return cached;
      }, async (bytes, working) => {
        await native!.presentCached(bytes);
        const sketches = working.design.sketches.flatMap(value => {
          if (typeof value !== 'object' || value === null || !('id' in value)) return [];
          return typeof value.id === 'number' && Number.isSafeInteger(value.id) ? [value.id] : [];
        });
        await native!.presentation(currentMode.current, sketches);
      }, error => setStatus(error ? error.message : ''));
      queue.current = requests;
      if (latest.current) requests.update(latest.current);
    };
    void start().catch(error => { if (!abort.signal.aborted) setStatus(String(error)); });
    return () => {
      abort.abort(); requests?.close(); channel?.stop(); native?.dispose();
      queue.current = undefined; viewer.current = undefined;
    };
  }, [cad.document_id, sessionId]);

  useEffect(() => {
    if (source) queue.current?.update(source);
  }, [cad.working?.checkpoint_id, source?.native.sha256, source?.publishedRevision]);
  useEffect(() => {
    void viewer.current?.presentation(mode).catch(error => setStatus(String(error)));
  }, [mode]);

  return <div className="relative h-full w-full overflow-hidden" aria-label="Preview de construction en direct">
    <div ref={host} className="absolute inset-0 overflow-hidden" />
    {status && <p role="status" className="absolute bottom-2 inset-x-2 rounded-full bg-black/70 px-3 py-1 text-center text-[11px] text-white">{status}</p>}
  </div>;
}
