/** Retain the interactive renderer while accepted checkpoints replace mesh geometry. */
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { CadMeshViewport } from '@/lib/cadMeshViewport';
import { cadArtifact, cadWorkingMesh, cadMeshSource, type CadView } from '@/lib/cad';
import { cadSketchLines } from '@/lib/cadSketchLines';
import { Scan } from 'lucide-react';
import { liveRuntime } from '@/lib/cadLiveRuntime';

export default function CadMeshViewer({ cad, sessionId, fallback, construction = false, selectedBounds }: { cad: CadView; sessionId: string; fallback: React.ReactNode; construction?: boolean; selectedBounds?: [[number, number, number], [number, number, number]] | null }) {
  const host = useRef<HTMLDivElement>(null);
  const viewport = useRef<CadMeshViewport>(undefined);
  const constructionMode = useRef(construction);
  useLayoutEffect(() => { constructionMode.current = construction; }, [construction]);
  const [error, setError] = useState('');
  const [displayedMesh, setDisplayedMesh] = useState<string>();
  const ready = displayedMesh !== undefined;
  const [preview, setPreview] = useState<{ documentId: string; sessionId: string; mesh?: Uint8Array; checkpointId?: string; status: string }>();
  // A component can be reused while changing conversations or documents.
  // Keep the fallback worker's asynchronous output bound to its original owner.
  const current = preview?.documentId === cad.document_id && preview.sessionId === sessionId ? preview : undefined;
  const liveMesh = current?.checkpointId === cad.working?.checkpoint_id ? current?.mesh : undefined;
  const runtimeStatus = current?.status || '';
  useEffect(() => {
    if (cadMeshSource(cad) !== 'worker') return;
    const runtime = liveRuntime(cad.document_id, sessionId);
    runtime.setMode('solid');
    const changed = () => {
      setPreview({ documentId: cad.document_id, sessionId, mesh: runtime.mesh, checkpointId: runtime.meshCheckpointId, status: runtime.status });
    };
    runtime.listeners.add(changed);
    runtime.update(cad);
    changed();
    return () => { runtime.listeners.delete(changed); };
  }, [cad, sessionId]);
  useEffect(() => {
    const node = host.current;
    if (!node) return;
    setError(''); setDisplayedMesh(undefined);
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

  const source = cadMeshSource(cad);
  // Status and timing frames can share the same immutable artifact.
  const publishedRevision = source === 'published' ? cad.snapshot?.document.revision : undefined;
  const publishedHash = source === 'published' ? cad.snapshot?.document.native.sha256 : undefined;
  const checkpointId = cad.working?.checkpoint_id;
  const checkpointMeshHash = source === 'checkpoint' ? cad.working?.mesh?.sha256 : undefined;
  const workerMesh = source === 'worker' ? liveMesh : undefined;
  const meshIdentity = JSON.stringify([sessionId, cad.document_id, source, publishedRevision,
    publishedHash, checkpointId, checkpointMeshHash]);
  useEffect(() => {
    const abort = new AbortController();
    if (source === 'empty') {
      viewport.current?.clear();
      setDisplayedMesh(undefined);
      setError('');
      return;
    }
    let mesh: Promise<ArrayBuffer>;
    if (source === 'published') {
      mesh = cadArtifact(cad, sessionId, 'stl', abort.signal).then(blob => blob.arrayBuffer());
    } else if (source === 'checkpoint') {
      mesh = cadWorkingMesh(cad, sessionId, abort.signal);
    } else if (workerMesh) {
      mesh = Promise.resolve(new Uint8Array(workerMesh).buffer);
    } else return;
    void mesh.then(buffer => {
      if (!abort.signal.aborted && viewport.current) {
        // Commit both scene layers before Three.js draws the next checkpoint.
        const curves = cad.working?.design.sketches;
        const vertices = constructionMode.current && curves ? cadSketchLines(curves, true) : [];
        viewport.current.update(buffer, vertices);
        setError('');
        setDisplayedMesh(meshIdentity);
      }
    }).catch(failure => {
      if (!abort.signal.aborted) setError(String(failure));
    });
    return () => abort.abort();
  }, [source, cad.document_id, sessionId, publishedRevision, publishedHash, checkpointId, checkpointMeshHash, workerMesh, meshIdentity]);
  // Keep the visible checkpoint's overlays while its successor is loading.
  const sketches = useRef<{ identity: string; curves: unknown[] | undefined }>(undefined);
  const displayedCheckpoint = source === 'empty' || displayedMesh === meshIdentity;
  if (displayedCheckpoint) {
    sketches.current = {
      identity: JSON.stringify([sessionId, cad.document_id]),
      curves: cad.working?.design.sketches,
    };
  }
  const visibleSketches = sketches.current?.identity === JSON.stringify([sessionId, cad.document_id])
    ? sketches.current.curves : undefined;
  const [hasSketch, setHasSketch] = useState(false);
  useEffect(() => {
    const vertices = construction && visibleSketches ? cadSketchLines(visibleSketches, true) : [];
    viewport.current?.updateSketches(vertices);
    setHasSketch(vertices.length > 0);
  }, [construction, visibleSketches, cad.document_id, sessionId]);
  const bounds = source === 'published' && displayedMesh === meshIdentity ? selectedBounds : undefined;
  useEffect(() => {
    // The selected occurrence belongs to the published revision.
    viewport.current?.selectBounds(bounds);
  }, [bounds, ready, cad.document_id, sessionId]);
  const visible = ready || hasSketch;
  return <div className="relative w-full h-full min-h-0">
    {!visible && <div className="absolute inset-0">{fallback}</div>}
    <div ref={host} className="absolute inset-0" style={{ visibility: visible ? 'visible' : 'hidden' }} />
    {visible && !error && <button className="absolute top-2 left-2 grid size-8 place-items-center rounded-full bg-black/60 text-white"
      aria-label="Recentrer la pièce" title="Recentrer la pièce" onClick={() => viewport.current?.fit()}><Scan size={15} /></button>}
    <span className="absolute bottom-2 left-2 right-2 text-[10px] text-center rounded-full px-2 py-1 bg-black/60 text-white pointer-events-none">
      {error || (!hasSketch && cadMeshSource(cad) === 'empty' && 'Aucun solide à cette étape · voir Construction') || (!ready && runtimeStatus) || (visible ? 'Glisser pour tourner · clic droit pour déplacer · molette pour zoomer' : 'Chargement de la vue 3D…')}</span>
  </div>;
}
