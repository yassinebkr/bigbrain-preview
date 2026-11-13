"""Same-origin reads of conversation-owned CAD artifacts."""

from aiohttp import web
from urllib.parse import urlsplit

from ..cad_store import CadStore
from ..solidcraft import CadError
from ..cad_desktop import CadDesktop


def setup_cad_routes(app, *, store=None, bus=None):
    store = store or CadStore()
    desktop = CadDesktop()

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
            if request.match_info['action'] in {'working', 'working-artifact'}:
                from ..cad_live import working_checkpoint
                from ..cad_contracts import CadArtifact
                checkpoint = working_checkpoint(store, document_id, session_id)
                if request.match_info['action'] == 'working':
                    return web.json_response({'working': checkpoint})
                if checkpoint is None or checkpoint['checkpoint_id'] != body.get('checkpointId'):
                    raise CadError('CAD working checkpoint changed; refresh the presentation')
                kind = body.get('kind', 'native')
                if kind not in {'native', 'stl'}:
                    raise CadError('Unsupported CAD checkpoint artifact')
                selected = checkpoint['native'] if kind == 'native' else checkpoint.get('mesh')
                if selected is None:
                    raise CadError('CAD checkpoint mesh is unavailable')
                artifact = CadArtifact.model_validate(selected)
                if kind == 'stl' and (artifact.format != 'stl'
                        or artifact.source_sha256 != checkpoint['native']['sha256']):
                    raise CadError('CAD checkpoint mesh source changed')
                return web.Response(body=store.read_artifact(document_id, session_id, artifact),
                    content_type='application/octet-stream',
                    headers={'Cache-Control': 'private, no-store',
                             'X-BigBrain-CAD-SHA256': artifact.sha256})
            if request.match_info['action'] == 'recovery':
                from ..cad_recovery import retained_recovery
                root = store.authorize(document_id, session_id)
                return web.json_response(retained_recovery(root))
            if request.match_info['action'] == 'resume':
                from ..cad_runs import confirmed_continuation
                from ..bus.message import BusMessage, MessageType
                if bus is None:
                    raise CadError('CAD continuation service is unavailable')
                confirmed_continuation(document_id, session_id)
                from ..cad_recovery import retained_recovery
                recovery = retained_recovery(store.authorize(document_id, session_id))
                if not recovery['enabled']:
                    raise CadError(recovery['label'])
                await bus.send(BusMessage(type=MessageType.TASK, source='morphable_ui',
                    target='orchestrator_default', payload={'type': 'cad.resume',
                    'document_id': document_id, 'session_id': session_id}))
                return web.json_response({'queued': True})
            if request.match_info['action'] in {'capability', 'open'}:
                if (request.remote not in {'127.0.0.1', '::1'}
                        or urlsplit('//' + request.host).hostname not in {'127.0.0.1', 'localhost', '::1'}):
                    raise web.HTTPForbidden(text='Local desktop access required')
                store.authorize(document_id, session_id)
                if request.match_info['action'] == 'capability':
                    return web.json_response(desktop.capability())
                if type(revision) is not int or revision < 1:
                    raise CadError('An explicit CAD revision is required')
                return web.json_response(desktop.open(store, document_id, session_id, revision))
            if request.match_info['action'] == 'view':
                return web.json_response(store.view(document_id, session_id, revision))
            artifact, data = store.artifact(document_id, session_id, revision, body.get('kind'))
            content_type = 'image/png' if artifact.format == 'png' else 'application/octet-stream'
            return web.Response(body=data, content_type=content_type,
                headers={'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff',
                         'Content-Disposition': f'attachment; filename="part.{"sc" if artifact.format == "solidcraft" else artifact.format}"'})
        except (CadError, ValueError, TypeError) as error:
            return web.json_response({'error': str(error)[:1000]}, status=400)

    app.router.add_post('/api/cad/{action:view|artifact|capability|open|resume|recovery|working|working-artifact}', handle)
