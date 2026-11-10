// Browser qualification driver for a locally served, pinned SolidCraft build.
let frame = document.querySelector('iframe');
const output = document.querySelector('pre');
const report = { userAgent: navigator.userAgent, cases: {}, frameGapsMs: [] };
let active, lastFrame;
function frames(now) {
  if (lastFrame && active) report.frameGapsMs.push(now - lastFrame);
  lastFrame = now;
  requestAnimationFrame(frames);
}
requestAnimationFrame(frames);
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
function show(message) { output.textContent = message; }
async function persist() {
  await fetch('/report', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(report) });
}
async function load(path, record) {
  // A fresh browsing context makes reopen independent of unsaved-document dialogs.
  if (frame.hasAttribute('src')) {
    const replacement = document.createElement('iframe');
    for (const attribute of frame.attributes) {
      if (attribute.name !== 'src') replacement.setAttribute(attribute.name, attribute.value);
    }
    frame.replaceWith(replacement);
    frame = replacement;
  }
  const start = performance.now();
  const navigated = new Promise(resolve => frame.addEventListener('load', resolve, {once:true}));
  frame.src = `/app/index.html?open=${encodeURIComponent(location.origin + path)}${document.querySelector('#webgl').checked ? '&webgl' : '&webgpu'}`;
  await navigated;
  for (let i = 0; i < 1200; i++) {
    await delay(100);
    const api = frame.contentWindow?.solidcraft;
    if (!api) continue;
    const value = await api.inspect({measure: false});
    const expectedName = decodeURIComponent(path.split('/').pop()).replace(/\.sc$/, '');
    if (!value.timeline?.length || value.name !== expectedName) continue;
    record.loadMs = performance.now() - start;
    record.loaded = value;
    // Capture actual browser download bytes for native round-trip inspection.
    const win = frame.contentWindow;
    win.HTMLAnchorElement.prototype.click = function () {
      if (!this.download || !this.href.startsWith('blob:')) return;
      const name = this.download;
      record.downloads ||= {};
      record.downloads[name] = fetch(this.href).then(r => r.arrayBuffer()).then(async bytes => {
        const result = await fetch(`/artifact/${active}/${encodeURIComponent(name)}`, {method: 'POST', body: bytes});
        if (!result.ok) throw new Error('Artifact capture failed');
        return { bytes: bytes.byteLength, url: `/artifact/${active}/${encodeURIComponent(name)}` };
      });
    };
    return api;
  }
  throw new Error('Browser document did not become ready within 120 seconds');
}
async function run(kind) {
  if (active) return;
  active = kind;
  report.frameGapsMs = [];
  const record = report.cases[kind] = { stages: [], requestedBackend: document.querySelector('#webgl').checked ? 'webgl' : 'default', started: new Date().toISOString() };
  async function stage(name, action) {
    show(`${kind}: ${name}`);
    const start = performance.now();
    const value = await action();
    record.stages.push({name, ms: performance.now() - start, value});
    if (frame.contentWindow?.wasmBindings) {
      const exports = await frame.contentWindow.wasmBindings.default();
      record.wasmMemoryBytes = exports.memory?.buffer.byteLength;
      record.peakWasmMemoryBytes = Math.max(record.peakWasmMemoryBytes || 0, record.wasmMemoryBytes || 0);
    }
    await persist();
    return value;
  }
  try {
    let api = await stage('load', () => load(`/fixture/${kind}.sc`, record));
    record.runtime = await stage('runtime', () => api.request('ui.inspect', {}));
    const initial = await stage('inspect initial', () => api.inspect({measure:true}));
    record.initial = initial;
    const parameter = kind === 'plate' ? initial.params.find(p => p.name === 'width') : initial.params.find(p => p.name === 'flange_thickness');
    if (!parameter) throw new Error('Qualification parameter unavailable; inspect retained parameter inventory');
    record.parameter = parameter;
    await stage('edit parameter', () => api.execute('parameters.change', {name: parameter.name, expression: `${parameter.value + 1} mm`}));
    record.edited = await stage('inspect edited', () => api.inspect({measure:true}));
    await stage('undo', () => api.execute('edit.undo', {}));
    record.undone = await stage('inspect undone', () => api.inspect({measure:true}));
    await stage('redo', () => api.execute('edit.redo', {}));
    record.redone = await stage('inspect redone', () => api.inspect({measure:true}));
    await stage('restore original', () => api.execute('edit.undo', {}));
    await stage('save', () => api.execute('file.save_as', {path:`/downloads/${kind}-roundtrip.sc`}));
    await stage('export STEP', () => api.execute('file.export', {path:`/downloads/${kind}-roundtrip.step`, format:'step'}));
    for (let i = 0; i < 200 && Object.keys(record.downloads || {}).length < 2; i++) await delay(100);
    const downloads = Object.fromEntries(await Promise.all(Object.entries(record.downloads || {}).map(async ([name, promise]) => [name, await promise])));
    record.downloads = downloads;
    const saved = downloads[`${kind}-roundtrip.sc`];
    if (!saved || !downloads[`${kind}-roundtrip.step`]) throw new Error('Save/export download missing');
    api = await stage('reopen saved', () => load(saved.url, record));
    record.reopened = await stage('inspect reopened', () => api.inspect({measure:true}));
    record.status = 'observed';
  } catch (error) {
    record.status = 'failed'; record.error = String(error);
  } finally {
    record.heap = performance.memory ? {usedJSHeapSize: performance.memory.usedJSHeapSize, totalJSHeapSize: performance.memory.totalJSHeapSize} : null;
    record.maxFrameGapMs = report.frameGapsMs.reduce((maximum, gap) => Math.max(maximum, gap), 0);
    delete record.downloads;
    active = null;
    await persist(); show(JSON.stringify(report, null, 2));
  }
}
document.querySelector('#plate').onclick = () => run('plate');
document.querySelector('#drawing42').onclick = () => run('drawing42');
document.querySelector('#runtime42').onclick = async () => {
  if (active) return;
  active = 'drawing42';
  show('Loading drawing42 for runtime measurements');
  const value = { stages: [] };
  try {
    const api = await load('/fixture/drawing42.sc', value);
    value.runtime = await api.request('ui.inspect', {});
    value.wasmMemoryBytes = (await frame.contentWindow.wasmBindings.default()).memory.buffer.byteLength;
    await fetch('/artifact/drawing42/runtime.json', {method:'POST', body:JSON.stringify(value)});
    show(JSON.stringify(value, null, 2));
  } catch(error) { show(String(error)); }
  finally { active = null; }
};
