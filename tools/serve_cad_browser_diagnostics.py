"""Record browser GPU admission and pinned application startup phases."""

import argparse
import json
from pathlib import Path
import tempfile

from aiohttp import web


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--port', type=int, default=3152)
    args = parser.parse_args()
    evidence = Path(tempfile.mkdtemp(prefix='cad-browser-diagnostics-'))
    app = web.Application()

    async def index(request):
        return web.Response(text=r'''<!doctype html><meta charset="utf-8"><title>CAD runtime diagnostics</title>
<body style="background:#161616;color:white;font:14px sans-serif"><button id="run">Inspect GPU and blank startup</button>
<pre id="result">Ready</pre><iframe style="width:95vw;height:65vh;border:0" title="Pinned SolidCraft"></iframe>
<script type="module">
const result = document.querySelector('#result');
document.querySelector('#run').onclick = async () => {
  document.querySelector('#run').disabled = true;
  const record = {userAgent:navigator.userAgent, secureContext:isSecureContext, gpu:{available:!!navigator.gpu}};
  const persist = async () => { result.textContent = JSON.stringify(record,null,2); await fetch('/report',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(record)}); };
  try {
    if (navigator.gpu) {
      // Compare feature levels explicitly: compatibility-only hardware can be
      // reported as accelerated while the default core request returns null.
      record.gpu.requests = [];
      for (const options of [{}, {featureLevel:'core'}, {featureLevel:'compatibility'}]) {
        const candidate = await navigator.gpu.requestAdapter(options);
        const entry = {options, adapterFound:!!candidate};
        if (candidate) {
          entry.info = {vendor:candidate.info.vendor, architecture:candidate.info.architecture, device:candidate.info.device, description:candidate.info.description};
          entry.features = [...candidate.features];
          try { const device = await candidate.requestDevice(); entry.deviceCreated=true; device.destroy(); }
          catch(error) { entry.deviceError=String(error); }
        }
        record.gpu.requests.push(entry);
      }
      const adapter = await navigator.gpu.requestAdapter({powerPreference:'high-performance'});
      record.gpu.adapterFound = !!adapter;
      if (adapter) {
        record.gpu.info = {...adapter.info};
        const device = await adapter.requestDevice();
        record.gpu.deviceCreated = true;
        device.destroy();
      }
    }
    await persist();
    const frame = document.querySelector('iframe');
    const start = performance.now();
    let previous = start, maximumGap = 0, observing = true;
    const tick = now => { maximumGap = Math.max(maximumGap,now-previous);previous=now;if(observing)requestAnimationFrame(tick); };
    requestAnimationFrame(tick);
    const loaded = new Promise(resolve => frame.addEventListener('load',resolve,{once:true}));
    frame.src = '/app/index.html?webgpu';
    await loaded;
    const deadline = performance.now()+120000;
    while (!frame.contentWindow.solidcraft && performance.now()<deadline) await new Promise(resolve=>setTimeout(resolve,100));
    if (!frame.contentWindow.solidcraft) throw new Error('Pinned browser API unavailable');
    record.blank = {apiReadyMs:performance.now()-start, runtime:await frame.contentWindow.solidcraft.request('ui.inspect',{})};
    record.blank.resources = frame.contentWindow.performance.getEntriesByType('resource').filter(e=>/wasm|\.js/.test(e.name)).map(e=>({name:e.name,duration:e.duration,transferSize:e.transferSize,encodedBodySize:e.encodedBodySize,decodedBodySize:e.decodedBodySize}));
    record.blank.maxHostFrameGapMs = maximumGap;
    observing = false;
    record.status = 'observed';
  } catch(error) { record.status='failed';record.error=String(error); }
  await persist();
};
</script>''', content_type='text/html')

    async def report(request):
        (evidence / 'report.json').write_text(json.dumps(await request.json(), indent=2))
        return web.json_response({'saved': True})

    app.router.add_get('/', index)
    app.router.add_post('/report', report)
    app.router.add_static('/app', args.build)
    print(f'Diagnostic evidence: {evidence}', flush=True)
    web.run_app(app, host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
