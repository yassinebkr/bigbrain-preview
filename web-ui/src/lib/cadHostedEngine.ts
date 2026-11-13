import { CadWorkerChannel } from './cadWorker';

interface CheckpointViewer {
  onManualInput?: () => void;
  camera(view: string): Promise<void>;
  presentCached(bytes: Uint8Array): Promise<void>;
  setLocked(locked: boolean): void;
  presentation?(mode: 'full'): Promise<void>;
  capabilities?(): Promise<unknown>;
  execute?(command: string, params: unknown): Promise<unknown>;
  save?(): Promise<Uint8Array>;
}

interface CatalogEntry { id: string; label: string; params: unknown; planned?: boolean }

/** Prepare native documents in a worker and transfer exclusive editing to the full editor. */
export class CadHostedEngine {
  readonly hosted: boolean;
  private worker?: CadWorkerChannel;
  private readonly viewer: CheckpointViewer;
  private readonly url: string;
  private readonly build: string;
  private readonly manual: boolean;
  constructor(viewer: CheckpointViewer, url: string, build: string, manual = false) {
    this.viewer = viewer; this.url = url; this.build = build;
    this.manual = manual;
    this.hosted = !manual;
  }

  setLocked(locked: boolean) { this.viewer.setLocked(this.manual ? locked : true); }

  set onManualInput(listener: () => void) { this.viewer.onManualInput = listener; }

  camera(view: string) { return this.viewer.camera(view); }

  interrupt() { this.worker?.stop(); this.worker = undefined; }

  private channel() {
    if (!this.worker) throw new Error('CAD worker session unavailable');
    return this.worker;
  }

  async restore(bytes: Uint8Array) {
    this.interrupt();
    const address = new URL(this.url, location.href);
    if (address.origin !== location.origin) throw new Error('Same-origin CAD worker required');
    this.worker = new CadWorkerChannel(new Worker(address, { type: 'module' }));
    try {
      await this.channel().request('open', { bytes });
      // A retained native source can lack a compatible browser cache. The
      // worker computes its presentation copy; the accepted source is retained.
      const cached = await this.channel().request('save') as Uint8Array;
      await this.viewer.presentation?.('full');
      await this.viewer.presentCached(cached);
      // The interactive editor becomes the sole editing session after loading.
      if (this.manual) this.interrupt();
    } catch (error) { this.interrupt(); throw error; }
  }

  async capabilities() {
    if (this.manual) return this.viewer.capabilities!();
    const catalog = await this.channel().request('execute', { command: 'engine.commands', params: {} }) as CatalogEntry[];
    return { protocol: 'bigbrain.cad.browser/1', build: this.build, commands: catalog.map(entry => entry.id).sort(),
      catalog: catalog.map(({id, label, params, planned}) => ({id, label, params, ...(planned ? {planned} : {})}))
        .sort((a, b) => a.id.localeCompare(b.id)), checkpoint: 'native-sc', ownership: 'exclusive' };
  }

  async execute(command: string, params: unknown) {
    if (this.manual) return this.viewer.execute!(command, params);
    const channel = this.channel();
    const output = await channel.request('execute', { command, params });
    const observation = await channel.request('execute', { command: 'document.inspect', params: { measure: false } });
    return { output, observation };
  }

  async save() {
    if (this.manual) return this.viewer.save!();
    const bytes = await this.channel().request('save');
    if (!(bytes instanceof Uint8Array) || !bytes.length || bytes.length > 3 * 1024**2)
      throw new Error('Invalid or oversized hosted CAD checkpoint');
    return bytes;
  }

  async presentAccepted(bytes: Uint8Array) { await this.viewer.presentCached(bytes); }
}
