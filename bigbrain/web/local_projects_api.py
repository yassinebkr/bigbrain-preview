"""Loopback project attachment endpoints backed by a native chooser."""

import asyncio
import ipaddress
import os
from pathlib import Path
import secrets
import time

from aiohttp import web

from ..local_projects import ProjectAccessError, ProjectFiles, ProjectRegistry


def setup_local_project_routes(app, *, registry=None, chooser=None):
    registry = registry or ProjectRegistry(
        Path(os.environ.get('BIGBRAIN_LOCAL_PROJECTS_DIR',
                            str(Path(__file__).resolve().parents[2] / 'data' / 'local-projects')))
        / 'registry.json')
    tickets = {}
    chooser_lock = asyncio.Lock()

    async def native_chooser():
        process = await asyncio.create_subprocess_exec(
            'zenity', '--file-selection', '--directory', '--title=Attach a project folder',
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        try:
            output, _ = await asyncio.wait_for(process.communicate(), 120)
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
        return output.decode().strip() if process.returncode == 0 else None

    def guard(request):
        try:
            local = ipaddress.ip_address(request.remote).is_loopback
        except ValueError:
            local = False
        host = request.url.host
        if (not local or host not in {'127.0.0.1', 'localhost', '::1'}
                or request.headers.get('X-BigBrain-Local') != '1'
                or request.headers.get('Origin') != f'{request.scheme}://{request.host}'):
            raise web.HTTPForbidden(text='Local same-origin project access required')

    async def handle(request):
        guard(request)
        try:
            action = request.match_info.get('action', '')
            if request.method == 'GET':
                return web.json_response({'projects': registry.list()})
            body = await request.json()
            if not isinstance(body, dict):
                raise ProjectAccessError('A project request object is required')
            if action == 'choose':
                if chooser_lock.locked():
                    raise web.HTTPConflict(text='A folder chooser is already open')
                async with chooser_lock:
                    root = await (chooser or native_chooser)()
                if root is None:
                    return web.json_response({'cancelled': True})
                tickets.clear()
                token = secrets.token_urlsafe(32)
                tickets[token] = (str(Path(root).resolve(strict=True)), time.monotonic() + 120)
                return web.json_response({'ticket': token, 'path': tickets[token][0]})
            if action == 'attach':
                selected = tickets.pop(body.get('ticket', ''), None)
                if selected is None or selected[1] < time.monotonic():
                    raise ProjectAccessError('Folder selection expired; choose the folder again')
                return web.json_response(registry.attach(selected[0], body.get('rights', ['read'])))
            project_id, revision = body.get('projectId'), body.get('revision')
            if type(revision) is not int:
                raise ProjectAccessError('A project revision is required')
            if action == 'grant':
                return web.json_response(registry.change(project_id, revision, rights=body['rights']))
            if action in {'detach', 'revoke'}:
                return web.json_response(registry.change(
                    project_id, revision, state='detached' if action == 'detach' else 'revoked'))
            files = ProjectFiles(registry, project_id, revision)
            if action == 'list':
                return web.json_response({'entries': files.list(body.get('path', ''))})
            if action == 'read':
                data = files.read(body.get('path'))
                import hashlib
                return web.json_response({'content': data.decode('utf-8'),
                                          'sha256': hashlib.sha256(data).hexdigest()})
            raise web.HTTPNotFound()
        except (ProjectAccessError, OSError, UnicodeError, KeyError, TypeError, ValueError) as exc:
            return web.json_response({'error': str(exc)}, status=400)

    app.router.add_get('/api/local-projects', handle)
    app.router.add_post('/api/local-projects/{action}', handle)
