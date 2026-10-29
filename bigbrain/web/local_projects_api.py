"""Loopback project attachment endpoints backed by a native chooser."""

import asyncio
import ipaddress
import json
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

    def overview(session):
        projects = registry.list()
        for project in projects:
            if project['state'] == 'attached':
                try:
                    with registry.access(project['id'], project['revision'], 'read'):
                        pass
                    project['availability'] = 'available'
                except ProjectAccessError as exc:
                    project['availability'] = 'unavailable'
                    project['diagnostic'] = str(exc)
        return {'projects': projects,
                'selectedProjectId': registry.selection(session) if session else None}

    async def handle(request):
        guard(request)
        try:
            action = request.match_info.get('action', '')
            if request.method == 'GET':
                return web.json_response(overview(request.query.get('sessionId')))
            body = await request.json()
            if not isinstance(body, dict):
                raise ProjectAccessError('A project request object is required')
            if action == 'projects':
                return web.json_response(overview(body.get('sessionId')))
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
            if action == 'select':
                return web.json_response({'selectedProjectId': registry.selection(
                    body.get('sessionId'), project_id=body.get('projectId'), update=True)})
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
            if action == 'run-stream':
                from ..local_project_runner import ProjectRunner
                response = web.StreamResponse(headers={'Content-Type': 'application/x-ndjson',
                                                        'Cache-Control': 'no-store'})
                await response.prepare(request)
                stream_lock = asyncio.Lock()

                async def emit(event):
                    async with stream_lock:
                        await response.write((json.dumps(event) + '\n').encode())

                async def output(text):
                    await emit({'type': 'output', 'text': text})

                try:
                    result = await ProjectRunner(registry).run(
                        project_id, revision, body.get('argv'), timeout=body.get('timeout', 30),
                        on_output=output)
                    await emit({'type': 'result', **result})
                except (ProjectAccessError, OSError, TimeoutError) as exc:
                    await emit({'type': 'error', 'error': str(exc) or 'Execution time limit reached'})
                await response.write_eof()
                return response
            if action == 'run':
                from ..local_project_runner import ProjectRunner
                return web.json_response(await ProjectRunner(registry).run(
                    project_id, revision, body.get('argv'), timeout=body.get('timeout', 30)))
            if action == 'patch':
                from ..local_project_patches import verify_and_apply
                return web.json_response(await verify_and_apply(
                    registry, project_id, revision, body.get('patches'), body.get('checks')))
            raise web.HTTPNotFound()
        except TimeoutError:
            return web.json_response({'error': 'Project execution reached its time limit'}, status=408)
        except (ProjectAccessError, OSError, UnicodeError, KeyError, TypeError, ValueError) as exc:
            return web.json_response({'error': str(exc)}, status=400)

    app.router.add_get('/api/local-projects', handle)
    app.router.add_post('/api/local-projects/{action}', handle)
