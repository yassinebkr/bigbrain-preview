// The qualified build serves both modules under the same origin and identity.
const build = new URL(self.location.href).searchParams.get('build');
const runtime = import(`/cad-engine/worker/bigbrain_worker_probe.js?build=${encodeURIComponent(build)}`)
  .then(async module => { await module.default(); return module; });
let busy = false;
self.onmessage = async ({ data }) => {
  const { id, action } = data;
  if (busy) { self.postMessage({ id, error: 'CAD worker is busy' }); return; }
  busy = true;
  try {
    const module = await runtime;
    let result;
    if (action === 'open') module.open(data.bytes);
    else if (action === 'execute') result = JSON.parse(module.execute(data.command, JSON.stringify(data.params)));
    else if (action === 'save') result = module.save();
    else throw new Error('Unknown CAD worker request');
    self.postMessage({ id, result }, result instanceof Uint8Array ? [result.buffer] : []);
  } catch (error) { self.postMessage({ id, error: String(error) }); }
  finally { busy = false; }
};
