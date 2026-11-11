import type { CadView } from './cad';
import { CadWorkerChannel } from './cadWorker';
import { CadPreviewQueue } from './cadPreviewQueue';

export type CadPreviewMode = 'solid' | 'construction' | 'full';
type Working = NonNullable<CadView['working']>;
type PreviewSource = Working & { publishedRevision?: number };
interface Viewer {
  camera(view: string): Promise<void>;
  presentCached(bytes: Uint8Array): Promise<void>;
  presentation(mode: CadPreviewMode, sketches?: number[]): Promise<void>;
  dispose(): void;
}

/** One stable preview host follows its document between Atelier surfaces. */
export class CadLiveRuntime {
  readonly host = document.createElement('div');
  readonly listeners = new Set<() => void>();
  attached = false;
  touched = Date.now();
  status = 'Préparation de la vue…';
  private mode: CadPreviewMode = 'solid';
  compactMode: 'solid' | 'construction' = 'solid';
  private source?: PreviewSource;
  private signature = '';
  private viewer?: Viewer;
  private worker?: CadWorkerChannel;
  private queue?: CadPreviewQueue<PreviewSource>;
  private readonly abort = new AbortController();
  private readonly documentId: string;
  private readonly sessionId: string;

  constructor(documentId: string, sessionId: string) {
    this.documentId = documentId;
    this.sessionId = sessionId;
    this.host.style.cssText = 'position:fixed;left:-20000px;top:0;width:800px;height:500px;overflow:hidden;visibility:hidden';
    this.host.dataset.cadPreview = documentId;
    document.body.append(this.host);
    void this.start().catch(error => this.report(String(error)));
  }

  private report(status = '') {
    if (this.abort.signal.aborted) return;
    this.status = status;
    this.listeners.forEach(listener => listener());
  }

  update(cad: CadView) {
    if (!cad.working) return;
    const published = cad.status === 'ready' ? cad.snapshot?.document : undefined;
    const source = { ...cad.working, native:published?.native || cad.working.native,
      publishedRevision:published?.revision };
    const signature = `${source.checkpoint_id}:${source.native.sha256}:${source.publishedRevision}`;
    if (signature === this.signature) return;
    this.signature = signature;
    this.source = source;
    this.queue?.update(source);
  }

  setMode(mode: CadPreviewMode) {
    this.mode = mode;
    if (mode !== 'full') this.compactMode = mode;
    void this.viewer?.presentation(mode).catch(error => this.report(String(error)));
  }

  fit() { void this.viewer?.camera('fit').catch(error => this.report(String(error))); }

  dispose() {
    this.abort.abort();
    this.queue?.close();
    this.worker?.stop();
    this.viewer?.dispose();
    this.host.remove();
    this.listeners.clear();
  }

  private async start() {
    const path = '/static/cad-browser-bridge.mjs?v=live-preview-2';
    const bridge = await import(/* @vite-ignore */ path);
    const transport = new bridge.CadBrowserTransport(this.documentId, this.sessionId);
    const capability = await transport.call('capability');
    if (this.abort.signal.aborted) return;
    if (!capability.available || !capability.worker)
      throw new Error(capability.diagnostic || 'Moteur de preview indisponible');
    const viewer: Viewer = new bridge.SolidCraftBrowserEngine(this.host, capability.url, capability.build);
    this.viewer = viewer;
    const address = new URL(capability.worker, location.href);
    if (address.origin !== location.origin) throw new Error('Origine du moteur de preview invalide');
    const worker = new CadWorkerChannel(new Worker(address, { type:'module' }));
    this.worker = worker;
    this.queue = new CadPreviewQueue(async source => {
      const endpoint = source.publishedRevision ? 'artifact' : 'working-artifact';
      const response = await fetch(`/api/cad/${endpoint}`, {
        method:'POST', signal:this.abort.signal,
        headers:{'Content-Type':'application/json', 'X-BigBrain-CAD':'1'},
        body:JSON.stringify({ documentId:this.documentId, sessionId:this.sessionId,
          checkpointId:source.checkpoint_id, kind:'native', revision:source.publishedRevision }),
      });
      if (!response.ok) throw new Error((await response.json()).error || 'Étape indisponible');
      const bytes = new Uint8Array(await response.arrayBuffer());
      const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
      const hash = Array.from(digest).map(value => value.toString(16).padStart(2, '0')).join('');
      if (hash !== source.native.sha256) throw new Error('Identité de la preview modifiée');
      await worker.request('open', {bytes});
      const cached = await worker.request('save');
      if (!(cached instanceof Uint8Array)) throw new Error('État de preview invalide');
      return cached;
    }, async (bytes, source) => {
      await viewer.presentCached(bytes);
      const sketches = source.design.sketches.flatMap(value => {
        if (typeof value !== 'object' || value === null || !('id' in value)) return [];
        return typeof value.id === 'number' && Number.isSafeInteger(value.id) ? [value.id] : [];
      });
      await viewer.presentation(this.mode, sketches);
    }, error => this.report(error?.message));
    if (this.source) this.queue.update(this.source);
  }
}

const runtimes = new Map<string, CadLiveRuntime>();

export function retainedPreviewMode(documentId: string, sessionId: string) {
  return runtimes.get(JSON.stringify([sessionId, documentId]))?.compactMode || 'solid';
}

export function liveRuntime(documentId: string, sessionId: string) {
  const key = JSON.stringify([sessionId, documentId]);
  const existing = runtimes.get(key);
  if (existing) return existing;
  if (runtimes.size >= 2) {
    const idle = [...runtimes.entries()].filter(([, runtime]) => !runtime.attached)
      .sort((a, b) => a[1].touched - b[1].touched)[0];
    if (!idle) throw new Error('Deux vues CAD sont déjà actives. Ferme une pièce pour continuer.');
    idle[1].dispose();
    runtimes.delete(idle[0]);
  }
  const runtime = new CadLiveRuntime(documentId, sessionId);
  runtimes.set(key, runtime);
  return runtime;
}

if (import.meta.hot) import.meta.hot.dispose(() => {
  runtimes.forEach(runtime => runtime.dispose());
  runtimes.clear();
});
