"""Execute project snapshots in a private Linux filesystem and process namespace."""

import asyncio
import os
from pathlib import Path
import shutil
import sys
import tempfile

from .local_projects import ProjectAccessError, ProjectFiles


class ProjectRunner:
    """Keep execution artifacts separate and enforce live grant revocation."""

    def __init__(self, registry):
        self.registry = registry

    async def run(self, project_id, revision, argv, *, timeout=30):
        if (not isinstance(argv, list) or not argv or len(argv) > 40
                or any(not isinstance(arg, str) or '\x00' in arg for arg in argv)
                or argv[0] not in {'python', 'python3'}):
            raise ProjectAccessError('Choose a Python project command')
        if type(timeout) is not int or not 1 <= timeout <= 120:
            raise ProjectAccessError('Execution timeout must be between 1 and 120 seconds')
        with self.registry.access(project_id, revision, 'execute'):
            pass
        if shutil.which('bwrap') is None:
            raise ProjectAccessError('Project execution requires Bubblewrap')
        files = ProjectFiles(self.registry, project_id, revision)
        with tempfile.TemporaryDirectory(prefix='bigbrain-project-run-') as temporary:
            snapshot = Path(temporary)
            count, total = 0, 0

            def copy(relative=''):
                nonlocal count, total
                for entry in files.list(relative):
                    destination = snapshot / entry['path']
                    count += 1
                    if count > 2000:
                        raise ProjectAccessError('Project snapshot exceeds file count limit')
                    if entry['type'] == 'folder':
                        destination.mkdir()
                        copy(entry['path'])
                    else:
                        data = files.read(entry['path'], limit=4_000_000)
                        total += len(data)
                        if total > 32_000_000:
                            raise ProjectAccessError('Project snapshot exceeds size limit')
                        destination.write_bytes(data)

            copy()
            interpreter = Path(sys.executable).resolve()
            prefix = interpreter.parent.parent
            command = ['bwrap', '--unshare-all', '--die-with-parent', '--new-session',
                       '--clearenv', '--setenv', 'PATH', '/usr/bin:/bin',
                       '--setenv', 'HOME', '/tmp', '--setenv', 'PYTHONDONTWRITEBYTECODE', '1',
                       '--tmpfs', '/tmp', '--proc', '/proc', '--dev', '/dev']
            for mount in ['/usr', '/bin', '/lib', '/lib64']:
                if Path(mount).exists():
                    command += ['--ro-bind', mount, mount]
            if not str(prefix).startswith('/usr/'):
                command += ['--ro-bind', str(prefix), str(prefix)]
            command += ['--bind', str(snapshot), '/project', '--chdir', '/project',
                        '--', str(interpreter), *argv[1:]]
            with self.registry.access(project_id, revision, 'execute'):
                process = await asyncio.create_subprocess_exec(
                    *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    env={'PATH': '/usr/bin:/bin'}, start_new_session=True)
            output = bytearray()

            async def consume(stream):
                while chunk := await stream.read(8192):
                    output.extend(chunk)
                    if len(output) > 512_000:
                        raise ProjectAccessError('Project output exceeds limit')

            async def watch():
                while process.returncode is None:
                    await asyncio.sleep(0.1)
                    with self.registry.access(project_id, revision, 'execute'):
                        pass

            tasks = [asyncio.create_task(consume(process.stdout)),
                     asyncio.create_task(consume(process.stderr)),
                     asyncio.create_task(watch()), asyncio.create_task(process.wait())]
            try:
                await asyncio.wait_for(asyncio.gather(*tasks), timeout)
                return {'exitCode': process.returncode,
                        'output': output.decode('utf-8', errors='replace'),
                        'snapshotFiles': count, 'snapshotBytes': total}
            finally:
                if process.returncode is None:
                    import signal
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                await process.wait()
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
