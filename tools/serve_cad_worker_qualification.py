"""Serve the isolated worker probe and retain its operation evidence."""

import argparse
import json
from pathlib import Path
from aiohttp import web


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', required=True, type=Path)
    parser.add_argument('--fixture', required=True, type=Path)
    parser.add_argument('--evidence', required=True, type=Path)
    parser.add_argument('--port', type=int, default=3155)
    args = parser.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=True)
    app = web.Application(client_max_size=140 * 1024**2)

    async def index(request):
        return web.Response(text='''<!doctype html><meta charset="utf-8"><title>CAD worker qualification</title>
<body style="background:#171717;color:#eee;font:14px sans-serif">
<button id="run">Run isolated geometry worker</button>
<button id="responsive">Check interface response</button><span id="clicks">0</span>
<pre>Ready</pre><script type="module" src="/driver.mjs"></script>''', content_type='text/html')

    async def driver(request):
        return web.FileResponse(Path(__file__).with_name('cad_worker_qualification.mjs'))

    async def fixture(request):
        return web.FileResponse(args.fixture)

    async def report(request):
        (args.evidence / 'report.json').write_text(json.dumps(await request.json(), indent=2, allow_nan=False))
        return web.json_response({'saved': True})

    async def save(request):
        (args.evidence / 'saved.sc').write_bytes(await request.read())
        return web.json_response({'saved': True})

    app.router.add_get('/', index)
    app.router.add_get('/driver.mjs', driver)
    app.router.add_get('/fixture.sc', fixture)
    app.router.add_post('/report', report)
    app.router.add_post('/saved.sc', save)
    app.router.add_static('/runtime', args.runtime)
    web.run_app(app, host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
