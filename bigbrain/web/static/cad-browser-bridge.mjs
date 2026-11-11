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
  step() {
    if (!this.ready || this.busy || this.stopping) return Promise.resolve(null);
    const task = this.executeStep();
    this.activeStep = task;
    return task.finally(() => { if (this.activeStep === task) this.activeStep = undefined; });
  }
  async executeStep() {
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
          if (this.stopping || this.interruptedGeneration === operation.generation) return null;
          await this.transport.call('fail', { generation: operation.generation,
            operationId: operation.id, error: String(error) });
          await this.connect();
          throw error;
        }
        // The saved document and observations belong to this exact operation.
        const bytes = await this.engine.save();
        const receipt = await this.transport.call('accept', {
          generation: operation.generation, operationId: operation.id, native: base64(bytes), result,
        });
        // A separate viewer receives only the server-accepted revision. Its
        // failure leaves the committed checkpoint available on reconnect.
        await this.engine.presentAccepted?.(bytes, receipt);
        return receipt;
      } catch (error) {
        if (this.stopping || this.interruptedGeneration === operation.generation) return null;
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
      while (!signal.aborted && (this.ready || this.stopping)) {
        if (this.stopping) { await sleep(50); continue; }
        const state = await this.transport.call('state');
        if (this.stopping) continue;
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
    if (action === 'stop' && this.engine.interrupt) {
      this.stopping = true;
      try {
        const generation = this.state.generation;
        const stop = state => this.transport.call('stop', { revision: state.revision, hash: state.hash });
        try { await stop(this.state); }
        catch (error) {
          const current = await this.transport.call('state');
          if (current.generation !== generation || current.revision === this.state.revision) throw error;
          await stop(current);
        }
        this.interruptedGeneration = generation;
        this.ready = false;
        this.engine.interrupt();
        await this.activeStep?.catch(() => {});
        return await this.connect();
      } finally { this.stopping = false; }
    }
    const state = await this.transport.call(action, { revision: this.state.revision, hash: this.state.hash });
    this.update(state);
    if (action === 'stop') return this.connect();
    return state;
  }
  async saveManual() {
    if (this.engine.hosted) throw new Error('Hosted CAD uses the worker as its editing session');
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
  async presentCached(bytes) {
    if (bytes.length > 3 * 1024**2) throw new Error('Hosted checkpoint exceeds the viewer transport limit');
    if (!this.hostedReady) {
      const frame = document.createElement('iframe');
      frame.title = 'SolidCraft · checkpoint';
      frame.style.cssText = 'width:100%;height:100%;border:0';
      const address = new URL(this.appUrl, location.href);
      address.searchParams.set('bigbrain-hosted', '1');
      frame.src = address.href;
      this.container.replaceChildren(frame);
      this.frame = frame;
      this.setLocked(true);
      const deadline = performance.now() + 30000;
      while (!frame.contentWindow?.solidcraft && performance.now() < deadline) await sleep(50);
      if (!frame.contentWindow?.solidcraft) throw new Error('Hosted SolidCraft API unavailable');
      this.api = frame.contentWindow.solidcraft;
      // Docked panels reserve their own area, giving camera input an explicit
      // viewport rectangle that excludes native toolbars and the document tree.
      await this.api.request('ui.set', { layout: 'docked' });
      this.hostedReady = true;
    }
    const camera = this.hostedReady && this.presented ? (await this.api.request('ui.inspect', {})).camera : null;
    const result = await this.api.request('bigbrain.present_cached', { bytes: Array.from(bytes) });
    if (result?.cacheAdopted !== true) throw new Error('Hosted viewer did not confirm cache adoption');
    if (camera) await this.api.request('ui.camera', camera);
    this.presented = true;
    await this.configurePresentation();
    await this.enableCameraNavigation();
  }
  async presentation(mode, sketches) {
    this.presentationMode = mode;
    if (sketches) this.previewSketches = sketches;
    if (this.api) {
      await this.configurePresentation();
      await this.enableCameraNavigation();
    }
  }
  async configurePresentation() {
    if (!this.presentationMode) return;
    const construction = this.presentationMode === 'construction';
    const full = this.presentationMode === 'full';
    await this.api.request('ui.set', { showBrowser:full, showTimeline:full,
      showNavigationBar:full, showSketches:construction || full, showOrigin:construction || full,
      shownSketches:construction ? this.previewSketches || [] : [], hiddenSketches:[],
      shownDims:construction ? this.previewSketches || [] : [] });
    // The compact surface displays the native viewport. The complete ribbon
    // remains available through the separate full-editor surface.
    this.frame.style.height = '100%';
    this.frame.style.transform = '';
    this.cropTop = 0;
    if (full) return;
    await sleep(30);
    const state = await this.api.request('ui.inspect', {});
    const viewport = state.viewport;
    if (viewport) {
      const top = viewport[1];
      const bottom = Math.max(0, this.container.clientHeight - top - viewport[3]);
      this.cropTop = top;
      this.frame.style.height = `calc(100% + ${top + bottom}px)`;
      this.frame.style.transform = `translateY(-${top}px)`;
    }
  }
  dispose() {
    this.navigationResize?.disconnect();
    this.navigation?.remove();
    this.frame?.remove();
  }
  async camera(view) {
    if (!this.api) throw new Error('SolidCraft est en cours de chargement');
    this.cameraState = await this.api.request('ui.view', { view });
  }
  async enableCameraNavigation() {
    // The native editor remains inert. Only camera state is forwarded through
    // this viewport overlay, so observation cannot change the geometry session.
    const layout = async () => {
      const state = await this.api.request('ui.inspect', {});
      this.cameraState = state.camera;
      const bounds = state.viewport;
      if (bounds && this.navigation) Object.assign(this.navigation.style, {
        left:`${bounds[0]}px`, top:`${bounds[1] - (this.cropTop || 0)}px`, width:`${bounds[2]}px`, height:`${bounds[3]}px`,
      });
    };
    if (!this.navigation) {
      const area = document.createElement('div');
      area.setAttribute('aria-label', 'Navigation 3D SolidCraft : glisser pour tourner, molette pour zoomer');
      area.style.cssText = 'position:absolute;touch-action:none;cursor:grab';
      this.container.append(area); this.navigation = area;
      let drag;
      let pending, sending = false;
      const send = async value => {
        pending = value;
        if (sending) return;
        sending = true;
        try {
          while (pending) {
            const value = pending; pending = undefined;
            this.cameraState = await this.api.request('ui.camera', value);
          }
        } catch (error) { area.setAttribute('aria-description', String(error)); }
        finally { sending = false; }
      };
      area.onpointerdown = event => {
        if (event.button !== 0 || !this.cameraState) return;
        drag = {x:event.clientX, y:event.clientY, ...this.cameraState};
        area.setPointerCapture(event.pointerId);
      };
      area.onpointermove = event => {
        if (drag) void send({yaw:drag.yaw-(event.clientX-drag.x)*0.008,
          pitch:Math.max(-Math.PI/2+0.000001,Math.min(Math.PI/2-0.000001,drag.pitch+(event.clientY-drag.y)*0.008))});
      };
      area.onpointerup = area.onpointercancel = () => { drag = undefined; };
      area.addEventListener('wheel', event => {
        event.preventDefault();
        if (this.cameraState) void send({distance:Math.max(0.001,this.cameraState.distance*Math.exp(Math.max(-1,Math.min(1,event.deltaY*0.001))))});
      }, {passive:false});
      this.navigationResize = new ResizeObserver(() => { void layout(); });
      this.navigationResize.observe(this.container);
    }
    // First presentation needs a rendered frame before the native viewport is known.
    await sleep(50);
    await layout();
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
