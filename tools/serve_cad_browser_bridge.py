"""Exercise the browser execution bridge against a disposable native copy."""

import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from aiohttp import web

from bigbrain.cad_browser import BrowserCadBridge
from bigbrain.cad_store import CadStore
from bigbrain.web.cad_browser_api import setup_browser_cad_routes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--port', type=int, default=3137)
    args = parser.parse_args()
    root = Path(tempfile.mkdtemp(prefix='bigbrain-browser-bridge-'))
    store = CadStore(root / 'cad')
    document = store.create('browser-qualification')
    BrowserCadBridge(store.authorize(document, 'browser-qualification') / 'browser').initialize(args.fixture.read_bytes())
    build = hashlib.sha256(b''.join(path.read_bytes() for path in sorted(args.build.glob('*.wasm')))).hexdigest()
    config = {'documentId': document, 'sessionId': 'browser-qualification',
              'build': f'SolidCraft-0.28.0-wasm-sha256:{build}', 'evidence': str(root)}
    app = web.Application(client_max_size=140 * 1024**2)
    setup_browser_cad_routes(app, store=store)

    async def index(request):
        return web.Response(text='''<!doctype html><meta charset="utf-8"><title>CAD browser bridge qualification</title>
<body style="background:#151515;color:#eee;font:14px sans-serif;margin:0">
<div style="padding:12px"><button id="run">Run recovery qualification</button><span id="status">Ready</span></div>
<div id="editor" style="height:75vh"></div><pre id="report" style="white-space:pre-wrap"></pre>
<script type="module" src="/qualification.mjs"></script>''', content_type='text/html')

    async def configuration(request):
        return web.json_response(config)

    async def report(request):
        path = root / 'browser-report.json'
        if request.method == 'POST':
            path.write_text(json.dumps(await request.json(), indent=2))
        return web.json_response(json.loads(path.read_text()) if path.exists() else {'stages': []})

    app.router.add_get('/', index)
    app.router.add_get('/config', configuration)
    app.router.add_get('/qualification.mjs', lambda request: web.FileResponse(Path(__file__).with_name('cad_browser_bridge_qualification.mjs')))
    app.router.add_route('*', '/report', report)
    app.router.add_static('/app', args.build)
    print(f'Qualification evidence: {root}', flush=True)
    web.run_app(app, host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
