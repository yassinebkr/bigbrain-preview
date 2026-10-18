"""Loopback preview servers owned by visible UI surfaces, not saved URLs."""
import asyncio
import time
import uuid
import json
from pathlib import Path

from aiohttp import web


class PreviewLeases:
    def __init__(self, registry_path=None):
        self.servers = {}
        self.leases = {}
        self.lock = asyncio.Lock()
        self.registry_path = registry_path

    def _ports(self):
        if self.registry_path is None or not self.registry_path.exists():
            return {}
        try:
            ports = json.loads(self.registry_path.read_text())
            if (not isinstance(ports, dict)
                    or any(not isinstance(k, str) or type(v) is not int or not 20000 <= v < 61000
                           for k, v in ports.items())
                    or len(set(ports.values())) != len(ports)):
                raise ValueError('invalid port registry')
            return ports
        except (OSError, ValueError) as error:
            raise web.HTTPConflict(text='Preview port registry unreadable; refusing to change stored origins') from error

    async def acquire(self, directory: Path):
        async with self.lock:
            directory = directory.resolve()
            key = str(directory)
            if key not in self.servers:
                async def serve(request):
                    relative = request.match_info['path'] or 'index.html'
                    if any(p.startswith('.') or p == 'node_modules' for p in Path(relative).parts):
                        raise web.HTTPNotFound()
                    target = (directory / relative).resolve()
                    if not target.is_relative_to(directory) or not target.is_file():
                        raise web.HTTPNotFound()
                    return web.FileResponse(target, headers={'Cache-Control': 'no-store'})

                app = web.Application()
                app.router.add_get('/{path:.*}', serve)
                runner = web.AppRunner(app)
                await runner.setup()
                try:
                    ports = self._ports()
                    port = ports.get(key, 0)
                    if self.registry_path is None or port:
                        await web.TCPSite(runner, '127.0.0.1', port).start()
                    else:
                        used = set(ports.values())
                        for candidate in range(20000, 61000):
                            if candidate in used:
                                continue
                            try:
                                await web.TCPSite(runner, '127.0.0.1', candidate).start()
                            except OSError:
                                continue
                            port = candidate
                            break
                        else:
                            raise web.HTTPServiceUnavailable(text='No preview port available')
                        ports[key] = port
                        temporary = self.registry_path.with_suffix('.tmp')
                        temporary.write_text(json.dumps(ports))
                        temporary.replace(self.registry_path)
                except OSError as error:
                    await runner.cleanup()
                    raise web.HTTPConflict(text='Preview port unavailable; refusing to change project storage origin') from error
                except BaseException:
                    await runner.cleanup()
                    raise
                port = runner.addresses[0][1]
                self.servers[key] = (runner, f'http://127.0.0.1:{port}')
            token = uuid.uuid4().hex
            self.leases[token] = (key, time.monotonic())
            return {'leaseId': token, 'previewUrl': self.servers[key][1]}

    async def touch(self, token):
        async with self.lock:
            if token not in self.leases:
                raise web.HTTPGone(text='Preview lease expired')
            key, _ = self.leases[token]
            self.leases[token] = (key, time.monotonic())

    async def release(self, token):
        async with self.lock:
            self.leases.pop(token, None)
            await self._prune()

    async def _prune(self):
        now = time.monotonic()
        self.leases = {k: v for k, v in self.leases.items() if now - v[1] < 45}
        used = {v[0] for v in self.leases.values()}
        for key in list(self.servers):
            if key not in used:
                runner, _ = self.servers.pop(key)
                await runner.cleanup()

    async def lifecycle(self, app):
        async def sweep():
            while True:
                await asyncio.sleep(10)
                async with self.lock:
                    await self._prune()
        task = asyncio.create_task(sweep())
        try:
            yield
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            self.leases.clear()
            await self._prune()
