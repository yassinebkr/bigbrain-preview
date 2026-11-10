"""Same-origin transport for conversation-scoped browser CAD execution."""

import base64
from pathlib import Path
import time
from uuid import uuid4

from aiohttp import web

from ..cad_browser import BrowserCadBridge, BridgeConflict
from ..cad_store import CadStore
from ..solidcraft import CadError


def setup_browser_cad_routes(app, *, store=None):
    store = store or CadStore()
    tickets = {}

    async def load_checkpoint(request):
        ticket = tickets.pop(request.match_info['ticket'], None)
        if ticket is None or ticket[0] < time.monotonic():
            raise web.HTTPNotFound()
        return web.Response(body=ticket[1], content_type='application/octet-stream',
                            headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})

    async def handle(request):
        if (request.headers.get('Origin') != f'{request.scheme}://{request.host}'
                or request.headers.get('X-BigBrain-CAD') != '1'):
            raise web.HTTPForbidden(text='Same-origin CAD access required')
        try:
            body = await request.clone(client_max_size=140 * 1024**2).json()
            document = body['documentId']
            root = store.authorize(document, body['sessionId'])
            bridge = BrowserCadBridge(root / 'browser')
            action = request.match_info['action']
            if action == 'initialize':
                # Only an owned retained native revision can initialize execution.
                _, native = store.artifact(document, body['sessionId'], body['revision'], 'native')
                bridge.initialize(native)
                result = bridge.state()
            elif action == 'connect':
                result = bridge.connect(body['capabilities'])
            elif action == 'state':
                result = bridge.state()
            elif action == 'result':
                result = bridge.result(body['operationId'])
            elif action == 'checkpoint':
                return web.Response(body=bridge.checkpoint(body.get('revision')), content_type='application/octet-stream',
                                    headers={'Cache-Control': 'no-store'})
            elif action == 'load':
                from ..cad_browser import digest
                native = bridge.checkpoint()
                if digest(native) != body['hash']:
                    raise BridgeConflict('Checkpoint changed before browser loading')
                now = time.monotonic()
                for key in list(tickets):
                    if tickets[key][0] < now:
                        del tickets[key]
                if len(tickets) >= 16:
                    raise BridgeConflict('Too many pending checkpoint loads')
                ticket = uuid4().hex
                tickets[ticket] = (now + 180, native)
                result = f'/api/cad/browser/load/{ticket}/checkpoint.sc'
            elif action == 'enqueue':
                result = bridge.enqueue(body['operationId'], body['revision'], body['hash'],
                                        body['command'], body['params'])
            elif action == 'claim':
                result = bridge.claim(body['generation'])
            elif action == 'accept':
                result = bridge.accept(body['operationId'], body['generation'],
                                       base64.b64decode(body['native'], validate=True), body['result'])
            elif action == 'fail':
                result = bridge.fail(body['operationId'], body['generation'], body['error'])
            elif action == 'save':
                result = bridge.save_manual(body['generation'], body['revision'], body['hash'],
                                            base64.b64decode(body['native'], validate=True))
            else:
                result = bridge.control(action, body['revision'], body['hash'])
            return web.json_response({'documentId': document, 'value': result},
                                     headers={'Cache-Control': 'no-store'})
        except BridgeConflict as error:
            return web.json_response({'error': str(error)}, status=409)
        except (CadError, ValueError, TypeError, KeyError) as error:
            return web.json_response({'error': str(error)[:1000]}, status=400)

    actions = 'initialize|connect|state|result|checkpoint|load|enqueue|claim|accept|fail|save|pause|stop|resume'
    app.router.add_post('/api/cad/browser/{action:' + actions + '}', handle)
    app.router.add_get('/api/cad/browser/load/{ticket}/checkpoint.sc', load_checkpoint)
    assets = Path(__file__).parent / 'static'
    async def script(request):
        return web.FileResponse(assets / 'cad-browser-bridge.mjs')
    app.router.add_get('/static/cad-browser-bridge.mjs', script)
