"""Serve isolated SolidCraft browser qualification and retain observed evidence."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

from aiohttp import web


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--plate', type=Path, required=True)
    parser.add_argument('--drawing42', type=Path, required=True)
    parser.add_argument('--port', type=int, default=3135)
    parser.add_argument('--rustc', default='rustc')
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--require-webgpu', action='store_true')
    args = parser.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=True)
    fixtures = args.evidence / 'fixtures'
    fixtures.mkdir(exist_ok=True)
    identities = {}
    for name, source in [('plate', args.plate), ('drawing42', args.drawing42)]:
        target = fixtures / f'{name}.sc'
        if not target.exists():
            shutil.copy2(source, target)
        digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
        if digest(target) != digest(source):
            raise ValueError(f'Fixture identity changed: {name}')
        identities[name] = {'source': str(source), 'sha256': digest(target)}
    manifest = json.loads(args.manifest.read_text()) if args.manifest else {'source_tag': 'v0.28.0', 'source_commit': 'ee6b85605a32948bcbd9ae437a564cab826689ec',
                'patches': [], 'fixtures': identities,
                'trunk_version': '0.22.1',
                'trunk_archive_sha256': '2ab8d548fd5ed9cda50906f61fd8654204e7893bd52ebbfd90533862b7d71ee1',
                'rustc_version': subprocess.check_output([args.rustc, '--version'], text=True).strip(),
                'assets': {str(path.relative_to(args.build)): hashlib.sha256(path.read_bytes()).hexdigest()
                           for path in args.build.rglob('*') if path.is_file()}}
    # A retained build manifest keeps the original compiler provenance. Verify
    # its asset identities before serving the qualification copy.
    for name, expected in manifest['assets'].items():
        if hashlib.sha256((args.build / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f'Build asset identity changed: {name}')
    (args.evidence / 'build-identity.json').write_text(json.dumps(manifest, indent=2))
    app = web.Application(client_max_size=256 * 1024**2)

    async def index(request):
        return web.Response(text=('''<!doctype html><html><head><title>SolidCraft 0.28.0 qualification</title></head>
<body style="margin:0;background:#171717;color:#eee;font:14px sans-serif">
<div style="padding:12px"><strong>Isolated SolidCraft 0.28.0 qualification</strong>
<button id="plate">Run plate</button><button id="drawing42">Run drawing42</button>
<button id="runtime42">Measure drawing42 runtime</button>
<label><input id="webgl" type="checkbox">Request WebGL fallback</label></div>
<iframe style="width:100%;height:70vh;border:0" title="SolidCraft browser"></iframe>
<pre style="white-space:pre-wrap;padding:12px">Ready</pre><script>window.requireWebGpu=REQUIRE_WEBGPU;</script><script src="/driver.js"></script></body></html>''').replace('REQUIRE_WEBGPU', json.dumps(args.require_webgpu)), content_type='text/html')

    async def driver(request):
        return web.FileResponse(Path(__file__).with_name('solidcraft_web_qualification.js'))

    async def report(request):
        value = await request.json()
        path = args.evidence / 'browser-report.json'
        if path.exists():
            prior = json.loads(path.read_text())
            value['cases'] = {**prior.get('cases', {}), **value.get('cases', {})}
        path.write_text(json.dumps(value, indent=2, allow_nan=False))
        return web.json_response({'saved': True})

    async def artifact(request):
        case, name = request.match_info['case'], request.match_info['name']
        if case not in identities or not re.fullmatch(r'[A-Za-z0-9_-]+\.(sc|step|json)', name):
            raise web.HTTPBadRequest()
        folder = args.evidence / case
        folder.mkdir(exist_ok=True)
        target = folder / name
        if request.method == 'POST':
            target.write_bytes(await request.read())
            return web.json_response({'saved': True})
        return web.FileResponse(target)

    app.router.add_get('/', index)
    app.router.add_get('/driver.js', driver)
    app.router.add_post('/report', report)
    app.router.add_route('*', '/artifact/{case}/{name}', artifact)
    app.router.add_static('/fixture', fixtures)
    app.router.add_static('/app', args.build)
    web.run_app(app, host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
