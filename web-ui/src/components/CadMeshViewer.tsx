/** Retain the interactive renderer while accepted checkpoints replace mesh geometry. */
import { useEffect, useRef, useState } from 'react';
import { CadMeshViewport } from '@/lib/cadMeshViewport';
import { cadArtifact, cadWorkingMesh, cadMeshSource, type CadView } from '@/lib/cad';
import { Scan } from 'lucide-react';
import { liveRuntime } from '@/lib/cadLiveRuntime';

export default function CadMeshViewer({ cad, sessionId, fallback }: { cad: CadView; sessionId: string; fallback: React.ReactNode }) {
  const host = useRef<HTMLDivElement>(null);
  const viewport = useRef<CadMeshViewport>(undefined);
  const [error, setError] = useState('');
  const [ready, setReady] = useState(false);
  const [preview, setPreview] = useState<{ documentId: string; sessionId: string; mesh?: Uint8Array; status: string }>();
  // A component can be reused while changing conversations or documents.
  // Keep the fallback worker's asynchronous output bound to its original owner.
  const current = preview?.documentId === cad.document_id && preview.sessionId === sessionId ? preview : undefined;
  const liveMesh = current?.mesh;
  const runtimeStatus = current?.status || '';
  useEffect(() => {
    if (cadMeshSource(cad) !== 'worker') return;
    const runtime = liveRuntime(cad.document_id, sessionId);
    runtime.setMode('solid');
    const changed = () => {
      setPreview({ documentId: cad.document_id, sessionId, mesh: runtime.mesh, status: runtime.status });
    };
    runtime.listeners.add(changed);
    runtime.update(cad);
    changed();
    return () => { runtime.listeners.delete(changed); };
  }, [cad, sessionId]);
  useEffect(() => {
    const node = host.current;
    if (!node) return;
    setError(''); setReady(false);
    let currentViewport: CadMeshViewport;
    try {
      currentViewport = new CadMeshViewport(node, setError);
      viewport.current = currentViewport;
    } catch (failure) {
      setError(String(failure));
      return;
    }
    return () => {
      viewport.current = undefined;
      currentViewport.dispose();
    };
  }, [cad.document_id, sessionId]);

  useEffect(() => {
    const abort = new AbortController();
    const source = cadMeshSource(cad);
    if (source === 'empty') {
      viewport.current?.clear();
      setReady(false);
      setError('');
      return;
    }
    let mesh: Promise<ArrayBuffer>;
    if (source === 'published') {
      mesh = cadArtifact(cad, sessionId, 'stl', abort.signal).then(blob => blob.arrayBuffer());
    } else if (source === 'checkpoint') {
      mesh = cadWorkingMesh(cad, sessionId, abort.signal);
    } else if (liveMesh) {
      mesh = Promise.resolve(new Uint8Array(liveMesh).buffer);
    } else return;
    void mesh.then(buffer => {
      if (!abort.signal.aborted && viewport.current) {
        viewport.current.update(buffer);
        setError('');
        setReady(true);
      }
    }).catch(failure => {
      if (!abort.signal.aborted) setError(String(failure));
    });
    return () => abort.abort();
  }, [cad.document_id, cad.status, cad.snapshot?.document.revision, cad.snapshot?.document.native.sha256, sessionId, liveMesh, cad.working?.checkpoint_id, cad.working?.mesh?.sha256]);
  return <div className="relative w-full h-full min-h-0">
    {!ready && <div className="absolute inset-0">{fallback}</div>}
    <div ref={host} className="absolute inset-0" style={{ visibility: ready ? 'visible' : 'hidden' }} />
    {ready && !error && <button className="absolute top-2 left-2 grid size-8 place-items-center rounded-full bg-black/60 text-white"
      aria-label="Recentrer la pièce" title="Recentrer la pièce" onClick={() => viewport.current?.fit()}><Scan size={15} /></button>}
    <span className="absolute bottom-2 left-2 right-2 text-[10px] text-center rounded-full px-2 py-1 bg-black/60 text-white pointer-events-none">
      {error || (cadMeshSource(cad) === 'empty' && 'Aucun solide à cette étape · voir Construction') || (!ready && runtimeStatus) || (ready ? 'Glisser pour tourner · clic droit pour déplacer · molette pour zoomer' : 'Chargement de la vue 3D…')}</span>
  </div>;
}
