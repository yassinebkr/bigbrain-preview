"""Serve the qualified SolidCraft web build through its recorded asset identity."""

import hashlib
import json
import os
from pathlib import Path

from aiohttp import web


class BrowserCadAssets:
    def __init__(self):
        self.root = Path(os.environ['BIGBRAIN_SOLIDCRAFT_WEB_DIR']).resolve() if os.environ.get('BIGBRAIN_SOLIDCRAFT_WEB_DIR') else None
        self.manifest_path = os.environ.get('BIGBRAIN_SOLIDCRAFT_WEB_MANIFEST')
        self.manifest = None
        self.identity = None

    def capability(self):
        try:
            if self.root is None or not self.manifest_path:
                raise ValueError('La distribution web SolidCraft doit être configurée sur ce serveur.')
            if self.manifest is None:
                data = Path(self.manifest_path).read_bytes()
                manifest = json.loads(data)
                if (manifest.get('source_tag') != 'v0.28.0'
                        or manifest.get('source_commit') != 'ee6b85605a32948bcbd9ae437a564cab826689ec'
                        or manifest.get('patches') != []):
                    raise ValueError('Cette compilation SolidCraft attend sa qualification navigateur.')
                assets = manifest['assets']
                if 'index.html' not in assets or not any(name.endswith('.wasm') for name in assets):
                    raise ValueError('Le manifeste web SolidCraft est incomplet.')
                for name, expected in assets.items():
                    path = (self.root / name).resolve()
                    if not path.is_relative_to(self.root) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                        raise ValueError('Les fichiers web SolidCraft diffèrent de la compilation qualifiée.')
                self.manifest = manifest
                self.identity = hashlib.sha256(data).hexdigest()
            return {'available': True, 'version': '0.28.0', 'build': self.identity,
                    'url': f'/cad-engine/index.html?build={self.identity}'}
        except (OSError, ValueError, KeyError) as error:
            return {'available': False, 'diagnostic': str(error)}

    async def serve(self, request):
        if not self.capability()['available']:
            raise web.HTTPServiceUnavailable(text='Qualified SolidCraft browser build unavailable')
        name = request.match_info['asset']
        if name not in self.manifest['assets']:
            raise web.HTTPNotFound()
        path = (self.root / name).resolve()
        if not path.is_relative_to(self.root):
            raise web.HTTPNotFound()
        return web.FileResponse(path, headers={'Cache-Control': 'no-cache',
                                              'X-Content-Type-Options': 'nosniff'})
