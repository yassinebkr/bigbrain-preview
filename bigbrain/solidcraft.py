"""Bounded headless SolidCraft sessions and revision-bound CAD captures."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess

from .cad_contracts import CadArtifact, CadPreview, CadRevision, GeometryObservation


class CadError(RuntimeError):
    """An engine, transport or artifact diagnostic suitable for the run journal."""


def solidcraft_executable() -> Path:
    """Resolve an explicit installation or the platform's executable search path."""
    configured = os.environ.get('BIGBRAIN_SOLIDCRAFT_CLI')
    candidate = configured or shutil.which('solidcraft-cli')
    if not candidate and os.name == 'posix':
        candidate = Path.home() / '.local/opt/solidcraft-0.25.1/bin/solidcraft-cli'
    if not candidate or not Path(candidate).is_file():
        raise CadError('SolidCraft CLI unavailable; configure BIGBRAIN_SOLIDCRAFT_CLI')
    return Path(candidate).resolve(strict=True)


@dataclass(frozen=True)
class CadCapture:
    document: CadRevision
    geometry: GeometryObservation
    preview: CadPreview | None
    preview_error: str | None


class SolidCraftSession:
    """Serialize MCP requests; uncertain transport outcomes retire the session."""

    def __init__(self, scratch: Path, *, executable=None, timeout=30):
        self.scratch = Path(scratch).resolve(strict=True)
        if not self.scratch.is_dir():
            raise CadError('CAD scratch root must be an existing owned directory')
        self.executable = Path(executable).resolve(strict=True) if executable else solidcraft_executable()
        if not 0 < timeout <= 120:
            raise ValueError('CAD request timeout must be within 120 seconds')
        self.timeout = timeout
        self.process = None
        self._stderr_task = None
        self.stderr = bytearray()
        self._lock = asyncio.Lock()
        self._counter = 0
        self.version = None
        self.observations = []

    async def __aenter__(self):
        launch = ({'start_new_session': True} if os.name == 'posix'
                  else {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP})
        self.process = await asyncio.create_subprocess_exec(
            str(self.executable), 'mcp', '--headless', '--param-check', 'strict',
            '--allow-path', str(self.scratch), cwd=self.scratch,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, limit=4_000_000, **launch)
        self._stderr_task = asyncio.create_task(self._drain_stderr())
        try:
            result = await self.request('initialize', {'protocolVersion': '2025-03-26',
                'capabilities': {}, 'clientInfo': {'name': 'bigbrain-cad', 'version': '1.0'}})
            self.version = result.get('serverInfo', {}).get('version')
            if result.get('serverInfo', {}).get('name') != 'solidcraft' or self.version != '0.25.1':
                raise CadError('CAD adapter requires the qualified SolidCraft 0.25.1 engine')
            # Server-provided instructions remain tool data. Product authority
            # and the user's contract stay with BigBrain.
            self.process.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
            await self.process.stdin.drain()
            return self
        except BaseException:
            await self.close()
            raise

    async def __aexit__(self, *_):
        await self.close()

    async def _drain_stderr(self):
        while chunk := await self.process.stderr.read(8192):
            self.stderr.extend(chunk)
            del self.stderr[:-32_000]

    async def close(self):
        process = self.process
        if process is None:
            return
        if process.returncode is None:
            try:
                if os.name == 'posix':
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except ProcessLookupError:
                pass
        if self._stderr_task:
            self._stderr_task.cancel()
            await asyncio.gather(self._stderr_task, return_exceptions=True)
        # Drain pipes before waiting so a saturated transport cannot hold Stop.
        await asyncio.wait_for(process.communicate(), 5)
        self.process = None

    async def request(self, method, params):
        async with self._lock:
            if self.process is None or self.process.returncode is not None:
                raise CadError('CAD session is closed; reopen the last saved revision')
            self._counter += 1
            identity = self._counter
            packet = json.dumps({'jsonrpc': '2.0', 'id': identity,
                                 'method': method, 'params': params}, allow_nan=False).encode()
            if len(packet) > 128_000:
                raise CadError('CAD request exceeds its byte budget')

            async def exchange():
                self.process.stdin.write(packet + b'\n')
                await self.process.stdin.drain()
                for _ in range(128):
                    line = await self.process.stdout.readline()
                    if not line:
                        raise CadError('CAD engine exited before responding')
                    response = json.loads(line)
                    if response.get('jsonrpc') != '2.0':
                        raise CadError('Invalid CAD transport response')
                    if 'id' not in response:
                        continue
                    if response['id'] != identity:
                        raise CadError('CAD response identity mismatch')
                    if 'error' in response:
                        raise CadError('CAD RPC rejected: ' + str(response['error'])[:1000])
                    if not isinstance(response.get('result'), dict):
                        raise CadError('CAD response requires an object result')
                    return response['result']
                raise CadError('CAD notification budget exhausted')

            try:
                result = await asyncio.wait_for(exchange(), self.timeout)
            except BaseException:
                # A timeout may have interrupted a mutation. Closing prevents
                # an automatic retry against an unobserved live state.
                await self.close()
                raise
            return result

    async def tool(self, name, arguments=None):
        result = await self.request('tools/call', {'name': name, 'arguments': arguments or {}})
        text = '\n'.join(item['text'] for item in result.get('content', [])
                         if item.get('type') == 'text')
        try:
            value = json.loads(text)
        except ValueError:
            value = {'text': text[:16_000]}
        self.observations.append({'tool': name, 'arguments': arguments or {}, 'result': value,
                                  'is_error': bool(result.get('isError'))})
        if len(self.observations) > 128:
            raise CadError('CAD session observation budget exhausted')
        if result.get('isError') or isinstance(value, dict) and value.get('ok') is False:
            raise CadError('CAD tool failed: ' + json.dumps(value)[:2000])
        return value

    async def batch(self, commands):
        """Restrict model mutations to geometry and parameter operations."""
        if not isinstance(commands, list) or not 1 <= len(commands) <= 32:
            raise CadError('CAD batch requires 1–32 commands')
        for item in commands:
            if (not isinstance(item, dict) or set(item) != {'command', 'params'}
                    or not isinstance(item['command'], str) or not isinstance(item['params'], dict)
                    or not (item['command'].startswith(('solid.', 'sketch.', 'pattern.', 'construction.'))
                            or item['command'] == 'parameters.change')):
                raise CadError('CAD command lies outside the geometry mutation contract')
        return await self.tool('batch', {'commands': commands, 'rollback': True, 'verbose': False})

    def _artifact(self, path, format, source=None):
        if (path.resolve() != path.absolute() or not path.resolve().is_relative_to(self.scratch)
                or path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1):
            raise CadError('CAD artifact must be a regular owned file')
        if not 0 < path.stat().st_size <= 32_000_000:
            raise CadError('CAD artifact exceeds its byte budget')
        with path.open('rb') as stream:
            data = stream.read(32_000_001)
        if len(data) > 32_000_000:
            raise CadError('CAD artifact exceeds its byte budget')
        return CadArtifact(path=path.relative_to(self.scratch).as_posix(), format=format,
                           sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data),
                           source_sha256=source)

    async def capture(self, project_id, document_id, revision) -> CadCapture:
        """Persist a fresh immutable revision and collect actual engine evidence."""
        if type(revision) is not int or revision < 1:
            raise CadError('CAD capture requires a positive revision')
        folder = self.scratch / f'revision-{revision}'
        folder.mkdir()  # Exclusive capture prevents rewriting an earlier revision.
        native_path = folder / 'part.sc'
        await self.tool('save', {'path': str(native_path)})
        native = self._artifact(native_path, 'solidcraft')
        measured = await self.tool('measure')
        evidence_path = folder / 'measure.json'
        evidence_path.write_text(json.dumps(measured, allow_nan=False), encoding='utf-8')
        bodies = measured.get('bodies', [])
        if not bodies:
            raise CadError('CAD measurement contains no bodies')
        geometry = GeometryObservation(source_sha256=native.sha256,
            evidence_ref=evidence_path.relative_to(self.scratch).as_posix(),
            body_count=measured['body_count'], closed_solid=all(body.get('closed') is True for body in bodies),
            bounds_min_mm=[min(body['bbox']['min'][i] for body in bodies) for i in range(3)],
            bounds_max_mm=[max(body['bbox']['max'][i] for body in bodies) for i in range(3)],
            volume_mm3=measured['total']['volume_mm3'])
        exports = []
        for format in ('step', 'stl'):
            path = folder / f'part.{format}'
            await self.tool('export', {'path': str(path), 'format': format})
            exports.append(self._artifact(path, format, native.sha256))
        document = CadRevision(project_id=project_id, document_id=document_id, revision=revision,
                               engine_version=self.version, native=native, exports=tuple(exports))
        preview, preview_error = None, None
        try:
            image_path = folder / 'preview.png'
            await self.tool('screenshot', {'path': str(image_path), 'width': 960, 'height': 600,
                                         'view': 'iso', 'grid': False, 'axes': False})
            image = self._artifact(image_path, 'png', native.sha256)
            if image_path.read_bytes()[:8] != b'\x89PNG\r\n\x1a\n':
                raise CadError('CAD renderer produced an invalid PNG')
            preview = CadPreview(project_id=project_id, document_id=document_id, revision=revision,
                                 image=image, width=960, height=600)
        except Exception as error:
            preview_error = str(error)[:1000]
        return CadCapture(document, geometry, preview, preview_error)

    async def reopen(self, artifact: CadArtifact):
        """Reopen a captured native/export artifact after checking its exact bytes."""
        path = self.scratch / artifact.path
        if self._artifact(path, artifact.format).sha256 != artifact.sha256:
            raise CadError('CAD revision changed before reopening')
        await self.tool('open', {'path': str(path)})
