"""Browser verification for attached static web snapshots."""

import asyncio
import base64
import hashlib
import json
import mimetypes
import os
import secrets
from pathlib import Path

from aiohttp import web

from .brains.web_acceptance import normalize_acceptance
from .local_projects import ProjectAccessError, ProjectFiles, _parts
from .verification.web_gate import browser_report


async def run_web_tests(registry, project_id, revision, entry_point, *, patches=None,
                        include_versions=False, web_stack='static'):
    """Run existing executable scenarios against a project-scoped working copy."""
    _parts(entry_point)
    if web_stack not in {'static', 'react_vite'}:
        raise ProjectAccessError('Unsupported attached web stack')
    for right in ('read', 'execute'):
        with registry.access(project_id, revision, right):
            pass
    record = registry.get(project_id)
    owned = record.get('origin') != 'runtime_snapshot'
    if not owned and patches:
        raise ProjectAccessError('Candidate web patches require an attached source project')
    snapshot = registry.create_snapshot(project_id, revision) if owned else record
    runner = None
    task = None
    try:
        files = ProjectFiles(registry, snapshot['id'], 1)
        versions = {}
        def inventory(directory=''):
            for item in files.list(directory):
                if item['type'] == 'folder':
                    inventory(item['path'])
                else:
                    versions[item['path']] = hashlib.sha256(files.read(item['path'], 4_000_000)).hexdigest()
        inventory()
        if patches:
            if not isinstance(patches, list) or len(patches) > 32:
                raise ProjectAccessError('Invalid web candidate patch set')
            seen = set()
            for patch in patches:
                path = patch.get('path')
                _parts(path)
                if path in seen or versions.get(path) != patch.get('sha256'):
                    raise ProjectAccessError('Web candidate source version changed')
                seen.add(path)
                content = patch.get('content')
                if not isinstance(content, str) or len(content.encode()) > 4_000_000:
                    raise ProjectAccessError('Invalid web candidate content')
                destination = Path(snapshot['root']) / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(content)
        if entry_point not in versions:
            raise ProjectAccessError('The inspected web entry point is unavailable')
        try:
            acceptance = normalize_acceptance(json.loads(files.read('tests/acceptance.json')))
        except (FileNotFoundError, ValueError, TypeError) as exc:
            return {'status': 'inconclusive', 'cause': 'missing_test', 'next_action': 'add_validation',
                    'reason': 'Executable browser scenarios are required in tests/acceptance.json: ' + str(exc)[:300],
                    **({'sourceVersions': versions} if include_versions else {})}

        built = None
        if web_stack == 'react_vite':
            from .local_project_runner import ProjectRunner
            tools = [('vite/bin/vite.js', ['build', '--outDir', 'dist', '--emptyOutDir'])]
            if 'tsconfig.json' in versions:
                tools.insert(0, ('typescript/bin/tsc', ['--noEmit', '--pretty', 'false']))
            for tool, args in tools:
                descriptor = None
                try:
                    with registry.access(snapshot['id'], 1, 'execute', environment=True) as root:
                        descriptor = os.dup(root)
                        for component in ('node_modules/' + tool).split('/'):
                            child = os.open(component, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=descriptor)
                            os.close(descriptor)
                            descriptor = child
                except OSError:
                    return {'status': 'inconclusive', 'cause': 'environment_blocked', 'next_action': 'stop',
                        'reason': f'Prepare the project dependency node_modules/{tool} before verification',
                        **({'sourceVersions': versions} if include_versions else {})}
                finally:
                    if descriptor is not None:
                        os.close(descriptor)
                build = await ProjectRunner(registry).run(snapshot['id'], 1,
                    ['node', '/project/node_modules/' + tool, *args], timeout=120,
                    capture_tree='dist' if tool.startswith('vite/') else None)
                if build['exitCode'] != 0:
                    return {'status': 'failed', 'framework': 'browser', 'cause': 'reproduced_defect',
                        'next_action': 'repair', 'diagnostic_output': build['output'],
                        **({'sourceVersions': versions} if include_versions else {})}
                if tool.startswith('vite/'):
                    built = build['treeArtifacts']
            if 'index.html' not in built:
                raise ProjectAccessError('The isolated web build produced no index.html')

        capability = secrets.token_urlsafe(32)
        cookie_name = 'bigbrain_preview_' + capability[:12]
        async def serve(request):
            credential = request.query.get('cap') or request.cookies.get(cookie_name)
            if not secrets.compare_digest(credential or '', capability):
                raise web.HTTPForbidden()
            path = request.match_info.get('path') or entry_point
            try:
                _parts(path)
                data = base64.b64decode(built[path], validate=True) if built is not None else files.read(path, 4_000_000)
                content_type = mimetypes.guess_type(path)[0] or 'application/octet-stream'
                response = web.Response(body=data, content_type=content_type,
                    headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
                             'Referrer-Policy': 'no-referrer'})
                response.set_cookie(cookie_name, capability, httponly=True, samesite='Strict')
                return response
            except (ProjectAccessError, OSError, ValueError, KeyError):
                raise web.HTTPNotFound()

        app = web.Application()
        app.router.add_get('/{path:.*}', serve)
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, '127.0.0.1', 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        task = asyncio.create_task(browser_report(f'http://127.0.0.1:{port}/{entry_point}?cap={capability}', acceptance))
        while not task.done():
            await asyncio.wait({task}, timeout=0.1)
            with registry.access(project_id, revision, 'execute'):
                pass
        report = await task
        from .verification.evidence import default_repository
        for index, case in enumerate(report.get('cases', [])):
            screenshot = case.pop('screenshot', None)
            if screenshot:
                artifact = default_repository().put_artifact(base64.b64decode(screenshot, validate=True),
                    name=f'attached-browser-case-{index + 1}.png', media_type='image/png')
                case['screenshot_sha256'] = artifact.sha256
        passed = [case['name'] for case in report.get('cases', []) if case['status'] == 'passed']
        result = {'status': report['status'], 'framework': 'browser', 'passed_cases': passed,
                  'diagnostic_output': json.dumps(report, ensure_ascii=False), 'report': report}
        if report['status'] == 'failed':
            result.update(cause='reproduced_defect', next_action='repair')
        elif report['status'] != 'passed':
            result.update(cause='environment_blocked', next_action='stop')
        if include_versions:
            result['sourceVersions'] = versions
        return result
    finally:
        if task is not None:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if runner is not None:
            await runner.cleanup()
        if owned:
            registry.change(snapshot['id'], 1, state='detached')
