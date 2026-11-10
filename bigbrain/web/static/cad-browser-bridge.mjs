// Revision-scoped transport and pinned SolidCraft browser execution adapter.
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const sha256 = async bytes => [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))]
  .map(b => b.toString(16).padStart(2, '0')).join('');
const base64 = bytes => {
  let text = '';
  for (let i = 0; i < bytes.length; i += 8192) text += String.fromCharCode(...bytes.subarray(i, i + 8192));
  return btoa(text);
};

export class CadBrowserTransport {
  constructor(documentId, sessionId, fetcher = fetch) {
    this.scope = { documentId, sessionId };
    this.fetcher = (...args) => fetcher(...args);
  }
  async call(action, data = {}) {
    const response = await this.fetcher(`/api/cad/browser/${action}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-BigBrain-CAD': '1' },
      body: JSON.stringify({ ...data, ...this.scope }), cache: 'no-store',
    });
    if (!response.ok) throw new Error((await response.json()).error || `CAD bridge ${response.status}`);
    return action === 'checkpoint' ? new Uint8Array(await response.arrayBuffer()) : (await response.json()).value;
  }
}

export class CadBrowserExecutor {
  constructor(transport, engine, onState = () => {}) {
    this.transport = transport;
    this.engine = engine;
    this.onState = onState;
    this.ready = false;
    this.busy = false;
    this.dirty = false;
    this.engine.onManualInput = () => { this.dirty = true; };
    this.engine.loadCheckpoint = async bytes => this.transport.call('load', { hash: await sha256(bytes) });
  }
  update(state) {
    this.state = state;
    this.engine.setLocked(!this.ready || state.owner !== 'user' || !!state.pause || this.busy);
    this.onState(state);
    return state;
  }
  async connect() {
    this.ready = false;
    this.engine.setLocked(true);
    // Restoring before claiming makes uncertain executions safe to repeat.
    const initialBytes = await this.transport.call('checkpoint');
    await this.engine.restore(initialBytes);
    const capabilities = await this.engine.capabilities();
    const state = await this.transport.call('connect', { capabilities });
    // Read again after obtaining the generation: a previous client may have
    // committed while this browsing context was loading the first checkpoint.
    const bytes = await this.transport.call('checkpoint');
    if (await sha256(bytes) !== await sha256(initialBytes)) await this.engine.restore(bytes);
    this.ready = true;
    this.dirty = false;
    const current = await this.transport.call('state');
    const hash = await sha256(bytes);
    if (current.generation !== state.generation || current.hash !== hash) {
      this.ready = false;
      throw new Error('CAD checkpoint changed during reconnect; connect again');
    }
    return this.update(current);
  }
  async step() {
    if (!this.ready || this.busy) return null;
    this.busy = true;
    this.engine.setLocked(true);
    let operation;
    try {
      operation = await this.transport.call('claim', { generation: this.state.generation });
      if (!operation) return null;
      let result;
      try {
        try {
          result = await this.engine.execute(operation.command, operation.params);
        } catch (error) {
          await this.transport.call('fail', { generation: operation.generation,
            operationId: operation.id, error: String(error) });
          await this.connect();
          throw error;
        }
        // The saved document and observations belong to this exact operation.
        const native = base64(await this.engine.save());
        return await this.transport.call('accept', {
          generation: operation.generation, operationId: operation.id, native, result,
        });
      } catch (error) {
        // A transport error after execution leaves the receipt uncertain. A new
        // connection restores the committed checkpoint and reconciles the journal.
        this.ready = false;
        throw error;
      }
    } finally {
      this.busy = false;
      if (this.ready) this.update(await this.transport.call('state'));
      else this.engine.setLocked(true);
    }
  }
  async run(signal) {
    // The host owns reconnection policy and presents failures. One serial pump
    // prevents overlapping engine commands while a tab is suspended or slow.
    try {
      while (!signal.aborted && this.ready) {
        const state = await this.transport.call('state');
        if (state.generation !== this.state.generation) {
          throw new Error('This CAD editor was replaced by another connection');
        }
        this.update(state);
        if (state.owner === 'agent' && !state.pause) await this.step();
        await sleep(500);
      }
    } catch (error) {
      this.ready = false;
      this.engine.setLocked(true);
      throw error;
    }
  }
  async control(action) {
    if (!this.ready) throw new Error('Reconnect the CAD document first');
    if (action === 'resume' && this.dirty) throw new Error('Save manual changes before resuming');
    // Freeze input before requesting the lease so a click cannot change the
    // local document between the saved revision check and its server response.
    this.engine.setLocked(true);
    const state = await this.transport.call(action, { revision: this.state.revision, hash: this.state.hash });
    this.update(state);
    if (action === 'stop') return this.connect();
    return state;
  }
  async saveManual() {
    if (this.busy || this.state.owner !== 'user') throw new Error('Pause CAD construction before editing');
    this.engine.setLocked(true);
    try {
      const native = base64(await this.engine.save());
      this.update(await this.transport.call('save', { generation: this.state.generation,
        revision: this.state.revision, hash: this.state.hash, native }));
      this.dirty = false;
    } catch (error) { this.ready = false; this.engine.setLocked(true); throw error; }
  }
}

export class SolidCraftBrowserEngine {
  constructor(container, appUrl, buildIdentity) {
    if (new URL(appUrl, location.href).origin !== location.origin) throw new Error('Same-origin SolidCraft build required');
    this.container = container;
    this.appUrl = appUrl;
    this.buildIdentity = buildIdentity;
    this.locked = true;
  }
  setLocked(value) {
    this.locked = value;
    if (this.frame) {
      // The editor canvas includes sketch tools and keyboard shortcuts. Inert
      // blocks all manual editor input while the agent owns the document.
      this.frame.inert = value;
      this.frame.style.pointerEvents = value ? 'none' : 'auto';
    }
  }
  async restore(bytes) {
    // SolidCraft's pinned URL loader accepts HTTPS or same-origin HTTP files.
    // A scoped single-use server ticket supplies the immutable checkpoint.
    const url = await this.loadCheckpoint(bytes);
    const frame = document.createElement('iframe');
    frame.dataset.cadInstance = crypto.randomUUID();
    frame.title = 'SolidCraft CAD document';
    frame.style.cssText = 'width:100%;height:100%;border:0';
    const loaded = new Promise(resolve => frame.addEventListener('load', resolve, { once: true }));
    const address = new URL(this.appUrl, location.href);
    address.searchParams.set('open', url);
    frame.src = address.href;
    this.container.replaceChildren(frame);
    this.frame = frame;
    this.setLocked(true);
    try {
      await loaded;
      const deadline = performance.now() + 180000;
      while (performance.now() < deadline) {
        const api = frame.contentWindow?.solidcraft;
        if (api) {
          const inspection = await api.inspect({ measure: false });
          if (inspection.timeline?.length) {
            this.api = api;
            frame.contentDocument.addEventListener('pointerdown', () => { if (!this.locked) this.onManualInput?.(); }, true);
            frame.contentDocument.addEventListener('keydown', () => { if (!this.locked) this.onManualInput?.(); }, true);
            return;
          }
        }
        await sleep(100);
      }
      throw new Error('SolidCraft checkpoint load timed out');
    } finally { this.setLocked(this.locked); }
  }
  async capabilities() {
    const catalog = await this.api.commands();
    return { protocol: 'bigbrain.cad.browser/1', build: this.buildIdentity,
      commands: catalog.map(command => command.id).sort(),
      catalog: catalog.map(({id, label, params, planned}) => ({id, label, params, ...(planned ? {planned} : {})}))
        .sort((a, b) => a.id.localeCompare(b.id)),
      checkpoint: 'native-sc', ownership: 'exclusive' };
  }
  async execute(command, params) {
    const output = await this.api.execute(command, params);
    const observation = await this.api.inspect({ measure: false });
    return { output, observation };
  }
  async save() {
    const win = this.frame.contentWindow;
    const original = win.HTMLAnchorElement.prototype.click;
    let captured;
    win.HTMLAnchorElement.prototype.click = function () {
      if (this.download?.endsWith('.sc') && this.href.startsWith('blob:'))
        captured = fetch(this.href).then(response => response.arrayBuffer());
      else original.call(this);
    };
    try {
      await this.api.execute('file.save_as', { path: '/downloads/bigbrain-checkpoint.sc' });
      for (let i = 0; !captured && i < 100; i++) await sleep(50);
      if (!captured) throw new Error('SolidCraft native save produced no checkpoint');
      return new Uint8Array(await captured);
    } finally { win.HTMLAnchorElement.prototype.click = original; }
  }
}
