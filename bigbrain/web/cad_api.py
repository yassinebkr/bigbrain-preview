"""Same-origin reads of conversation-owned CAD artifacts."""

from aiohttp import web

from ..cad_store import CadStore
from ..solidcraft import CadError


def setup_cad_routes(app, *, store=None):
    store = store or CadStore()

    async def handle(request):
        if (request.headers.get('Origin') != f'{request.scheme}://{request.host}'
                or request.headers.get('X-BigBrain-CAD') != '1'):
            raise web.HTTPForbidden(text='Same-origin CAD access required')
        try:
            body = await request.json()
            if not isinstance(body, dict):
                raise CadError('CAD artifact request object required')
            document_id, session_id = body.get('documentId'), body.get('sessionId')
            revision = body.get('revision')
            if request.match_info['action'] == 'view':
                return web.json_response(store.view(document_id, session_id, revision))
            artifact, data = store.artifact(document_id, session_id, revision, body.get('kind'))
            content_type = 'image/png' if artifact.format == 'png' else 'application/octet-stream'
            return web.Response(body=data, content_type=content_type,
                headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff',
                         'Content-Disposition': f'attachment; filename="part.{"sc" if artifact.format == "solidcraft" else artifact.format}"'})
        except (CadError, ValueError, TypeError) as error:
            return web.json_response({'error': str(error)[:1000]}, status=400)

    app.router.add_post('/api/cad/{action:view|artifact}', handle)
