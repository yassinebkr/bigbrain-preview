"""Serve Atelier qualification APIs over a disposable retained document copy."""

import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile

from aiohttp import web

from bigbrain.cad_store import CadStore
from bigbrain.web.cad_api import setup_cad_routes
from bigbrain.web.cad_browser_api import setup_browser_cad_routes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--document', type=Path, required=True)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--port', type=int, default=3140)
    args = parser.parse_args()
    os.environ['BIGBRAIN_SOLIDCRAFT_WEB_DIR'] = str(args.build)
    os.environ['BIGBRAIN_SOLIDCRAFT_WEB_MANIFEST'] = str(args.manifest)
    root = Path(tempfile.mkdtemp(prefix='cad-atelier-browser-'))
    store = CadStore(root / 'cad')
    source = args.document
    revision = json.loads((source / 'current.json').read_text())['revision']
    target = store.directory(source.name)
    target.mkdir(parents=True)
    shutil.copytree(source / f'revision-{revision}', target / f'revision-{revision}')
    (target / 'owner.json').write_text(json.dumps({'session_id':'atelier-browser-qualification'}))
    (target / 'current.json').write_text(json.dumps({'revision':revision}))
    view = store.view(source.name, 'atelier-browser-qualification')
    run = {'id':'atelier-browser-run', 'sessionId':'atelier-browser-qualification',
           'description':view['title'], 'status':'done', 'startedAt':1, 'files':[], 'steps':[],
           'deliveryStatus':view['delivery_status'],
           'cad':{'schema_version':'1.0', 'document_id':source.name, 'title':view['title'],
                  'sequence':1, 'status':'ready' if view['delivery_status']=='ready' else 'failed',
                  'elapsed_seconds':0, 'snapshot':view, 'diagnostic':None}}
    app = web.Application(client_max_size=140 * 1024**2)
    setup_cad_routes(app, store=store)
    setup_browser_cad_routes(app, store=store)
    async def fixture(request):
        return web.json_response(run)
    app.router.add_get('/cad-qualification-fixture', fixture)
    print(f'Atelier evidence: {root}', flush=True)
    web.run_app(app, host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
