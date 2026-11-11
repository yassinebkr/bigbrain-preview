/** Retain browser CAD instances while React switches Atelier surfaces. */
import { CadHostedEngine } from './cadHostedEngine';
export interface BrowserCadState {
  revision: number; hash: string; owner: 'agent' | 'user'; pause: number;
  generation: string; operations: {id: string; status: string}[];
}
interface Transport { call(action: string, data?: Record<string, unknown>): Promise<unknown> }
interface Engine { setLocked(value: boolean): void; hosted?: boolean; interrupt?(): void; camera?(view: string): Promise<void> }
interface Executor {
  ready: boolean; dirty: boolean; busy: boolean;
  connect(): Promise<BrowserCadState>;
  control(action: string): Promise<BrowserCadState>;
  saveManual(): Promise<void>;
  run(signal: AbortSignal): Promise<void>;
}
interface BridgeModule {
  CadBrowserTransport: new (documentId: string, sessionId: string) => Transport;
  SolidCraftBrowserEngine: new (host: HTMLElement, url: string, build: string) => Engine & { presentCached(bytes: Uint8Array): Promise<void>; camera(view: string): Promise<void> };
  CadBrowserExecutor: new (transport: Transport, engine: Engine, onState: (state: BrowserCadState) => void) => Executor;
}
export interface EditorRuntime {
  host: HTMLDivElement; executor?: Executor; state?: BrowserCadState;
  error: string; loading: boolean; initialized: boolean; touched: number;
  listeners: Set<() => void>; pending?: Promise<void>; stop?: AbortController;
  engine?: Engine; attached: boolean;
  selected?: boolean;
}
const cache = new Map<string, EditorRuntime>();
if (import.meta.hot) import.meta.hot.dispose(() => {
  // Development replacements release their old execution loops and iframes.
  // Production view switches continue to retain the module-owned instances.
  for (const runtime of cache.values()) { runtime.stop?.abort(); runtime.engine?.interrupt?.(); runtime.host.remove(); }
  cache.clear();
});
const notify = (runtime: EditorRuntime) => runtime.listeners.forEach(listener => listener());
const keyFor = (documentId: string, sessionId: string) => `${sessionId}:${documentId}`;
export const editorWasOpen = (documentId: string, sessionId: string) => cache.get(keyFor(documentId, sessionId))?.selected || false;
export function selectEditor(documentId: string, sessionId: string, selected: boolean) {
  const runtime = cache.get(keyFor(documentId, sessionId));
  if (runtime) runtime.selected = selected;
}

export function editorRuntime(documentId: string, sessionId: string): EditorRuntime {
  const key = keyFor(documentId, sessionId);
  const prior = cache.get(key);
  if (prior) return prior;
  // Two idle documents may remain warm. Dirty, attached and agent-owned instances
  // retain their state until the user saves or stops them explicitly.
  if (cache.size >= 2) {
    const victim = [...cache.entries()].filter(([, item]) => !item.attached && !item.loading
      && !item.executor?.dirty && !item.executor?.busy && item.state?.owner !== 'agent')
      .sort((a, b) => a[1].touched - b[1].touched)[0];
    if (!victim) throw new Error('Deux éditeurs sont actifs. Enregistre et ferme une pièce avant d’en ouvrir une autre.');
    victim[1].stop?.abort(); victim[1].engine?.interrupt?.(); victim[1].host.remove(); cache.delete(victim[0]);
  }
  const host = document.createElement('div');
  host.dataset.cadEditor = key;
  host.style.cssText = 'position:fixed;left:-20000px;top:0;width:800px;height:600px;z-index:60;visibility:hidden';
  // Moving an iframe between DOM parents reloads it in several browsers. A stable
  // host follows the visible slot while its browsing context stays mounted.
  document.body.appendChild(host);
  const runtime: EditorRuntime = { host, error: '', loading: false, initialized: false,
    touched: Date.now(), listeners: new Set(), attached: false, selected: true };
  cache.set(key, runtime);
  return runtime;
}

export async function openEditor(runtime: EditorRuntime, documentId: string, sessionId: string, revision: number) {
  if (runtime.initialized && runtime.executor?.ready) return;
  if (runtime.pending) return runtime.pending;
  runtime.pending = (async () => {
    runtime.loading = true; runtime.error = ''; notify(runtime);
    try {
      const path = '/static/cad-browser-bridge.mjs?v=hosted-camera-2';
      const bridge = await import(/* @vite-ignore */ path) as BridgeModule;
      const transport = new bridge.CadBrowserTransport(documentId, sessionId);
      const capability = await transport.call('capability') as {available: boolean; url: string; build: string; worker?: string; diagnostic?: string};
      if (!capability.available) throw new Error(capability.diagnostic || 'Éditeur navigateur indisponible');
      await transport.call('initialize', { revision });
      runtime.stop?.abort();
      runtime.engine?.interrupt?.();
      const viewer = new bridge.SolidCraftBrowserEngine(runtime.host, capability.url, capability.build);
      runtime.engine = capability.worker ? new CadHostedEngine(viewer, capability.worker, capability.build) : viewer;
      const executor = new bridge.CadBrowserExecutor(transport, runtime.engine, state => {
        runtime.state = state; notify(runtime);
      });
      runtime.executor = executor;
      await executor.connect();
      runtime.initialized = true;
      const stop = new AbortController(); runtime.stop = stop;
      void executor.run(stop.signal).catch(error => { runtime.error = String(error); notify(runtime); });
    } catch (error) { runtime.error = String(error); }
    finally { runtime.loading = false; runtime.pending = undefined; notify(runtime); }
  })();
  return runtime.pending;
}

export function attachEditor(runtime: EditorRuntime, slot: HTMLElement) {
  const started = performance.now();
  runtime.attached = true; runtime.touched = Date.now();
  const position = () => {
    const rect = slot.getBoundingClientRect();
    const visible = rect.width > 0 && rect.height > 0 && rect.bottom > 0 && rect.top < innerHeight;
    if (!visible) { runtime.host.style.visibility = 'hidden'; return; }
    let top = Math.max(0, -rect.top), bottom = Math.max(0, rect.bottom - innerHeight);
    let left = Math.max(0, -rect.left), right = Math.max(0, rect.right - innerWidth);
    // The full editor belongs to the workspace scroll area as well. Clipping
    // keeps its stable iframe below the Atelier header and above its footer.
    for (let parent = slot.parentElement; parent; parent = parent.parentElement) {
      if (!/(auto|scroll|hidden|clip)/.test(getComputedStyle(parent).overflow)) continue;
      const bounds = parent.getBoundingClientRect();
      top = Math.max(top, bounds.top - rect.top); bottom = Math.max(bottom, rect.bottom - bounds.bottom);
      left = Math.max(left, bounds.left - rect.left); right = Math.max(right, rect.right - bounds.right);
    }
    Object.assign(runtime.host.style, { left: `${rect.left}px`, top: `${rect.top}px`, width: `${rect.width}px`,
      height: `${rect.height}px`, visibility: 'visible', zIndex:'60',
      clipPath: `inset(${top}px ${right}px ${bottom}px ${left}px)` });
  };
  const observer = new ResizeObserver(position); observer.observe(slot);
  window.addEventListener('scroll', position, true); window.addEventListener('resize', position);
  let frame = 0;
  const follow = () => { position(); frame = requestAnimationFrame(follow); };
  follow();
  requestAnimationFrame(() => { runtime.host.dataset.warmAttachMs = String(performance.now() - started); });
  return () => {
    cancelAnimationFrame(frame);
    observer.disconnect(); window.removeEventListener('scroll', position, true); window.removeEventListener('resize', position);
    runtime.attached = false; runtime.touched = Date.now();
    Object.assign(runtime.host.style, {left: '-20000px', visibility: 'hidden'});
    runtime.host.inert = true;
  };
}

export async function editorAction(runtime: EditorRuntime, action: 'save' | 'pause' | 'stop' | 'resume') {
  runtime.error = '';
  try {
    if (!runtime.executor) throw new Error('L’éditeur est en préparation');
    if (action === 'save') await runtime.executor.saveManual();
    else await runtime.executor.control(action);
  } catch (error) { runtime.error = String(error); }
  notify(runtime);
}
