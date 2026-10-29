"""Execute project snapshots in a private Linux filesystem and process namespace."""

import asyncio
from contextlib import ExitStack
import hashlib
import os
from pathlib import Path
import shutil
import sys
import tempfile

from .local_projects import ProjectAccessError, ProjectFiles, _parts, _parent


def copy_project(files, destination, *, allowed_versions=None):
    """Copy bounded visible sources and recheck their observed revisions."""
    observed = {}
    count, total = 0, 0

    def copy(relative=''):
        nonlocal count, total
        if len(Path(relative).parts) > 32:
            raise ProjectAccessError('Project snapshot exceeds directory depth limit')
        for entry in files.list(relative):
            target = destination / entry['path']
            count += 1
            if count > 2000:
                raise ProjectAccessError('Project snapshot exceeds file count limit')
            if entry['type'] == 'folder':
                target.mkdir()
                copy(entry['path'])
            else:
                if allowed_versions is not None and entry['path'] not in allowed_versions:
                    continue
                data = files.read(entry['path'], limit=4_000_000)
                if (allowed_versions is not None
                        and hashlib.sha256(data).hexdigest() != allowed_versions[entry['path']]):
                    raise ProjectAccessError('Approved source revision changed during snapshot creation')
                total += len(data)
                if total > 32_000_000:
                    raise ProjectAccessError('Project snapshot exceeds size limit')
                target.write_bytes(data)
                observed[entry['path']] = data

    copy()
    if allowed_versions is not None and set(observed) != set(allowed_versions):
        raise ProjectAccessError('Approved source inventory is incomplete')
    for path, expected in observed.items():
        if files.read(path, limit=4_000_000) != expected:
            raise ProjectAccessError('Project source changed during snapshot')
    return observed, count, total


class ProjectRunner:
    """Keep execution artifacts separate and enforce live grant revocation."""

    def __init__(self, registry):
        self.registry = registry

    async def run(self, project_id, revision, argv, *, timeout=30, on_output=None,
                  patches=None, include_versions=False, capture_paths=()):
        if len(capture_paths) > 4:
            raise ProjectAccessError('Execution artifact count exceeds limit')
        for path in capture_paths:
            _parts(path)
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
        with ExitStack() as resources:
            temporary = resources.enter_context(tempfile.TemporaryDirectory(prefix='bigbrain-project-run-'))
            snapshot = Path(temporary)
            observed, count, total = copy_project(files, snapshot)
            if patches is not None:
                if not isinstance(patches, list) or not 1 <= len(patches) <= 32:
                    raise ProjectAccessError('Invalid candidate patch set')
                patched = set()
                for patch in patches:
                    path = patch.get('path')
                    _parts(path)
                    content = patch.get('content')
                    if path in patched or not isinstance(content, str):
                        raise ProjectAccessError('Candidate patch paths must be unique with text content')
                    patched.add(path)
                    before = observed.get(path)
                    version = hashlib.sha256(before).hexdigest() if before is not None else None
                    if version != patch.get('sha256'):
                        raise ProjectAccessError('Candidate source version changed')
                    data = content.encode('utf-8')
                    if len(data) > 4_000_000:
                        raise ProjectAccessError('Candidate patch exceeds size limit')
                    destination = snapshot / path
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(data)
            interpreter = Path(sys.executable).resolve()
            prefix = interpreter.parent.parent
            environment_fd = None
            with self.registry.access(project_id, revision, 'execute', environment=True) as root:
                try:
                    environment_fd = os.open('.venv', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                             dir_fd=root)
                except FileNotFoundError:
                    pass
            executable = str(interpreter)
            if environment_fd is not None:
                resources.callback(os.close, environment_fd)
                environment = Path(f'/proc/self/fd/{environment_fd}')
                try:
                    project_python = (environment / 'bin' / 'python').resolve(strict=True)
                except OSError as exc:
                    raise ProjectAccessError('Project Python environment is incomplete') from exc
                if project_python != interpreter:
                    raise ProjectAccessError('Project Python runtime differs from the supported base runtime')
                executable = '/venv/bin/python'
            command = ['bwrap', '--unshare-all', '--die-with-parent', '--new-session',
                       '--clearenv', '--setenv', 'PATH', '/usr/bin:/bin',
                       '--setenv', 'HOME', '/tmp', '--setenv', 'PYTHONDONTWRITEBYTECODE', '1',
                       '--tmpfs', '/tmp', '--proc', '/proc', '--dev', '/dev']
            for mount in ['/usr', '/bin', '/lib', '/lib64']:
                if Path(mount).exists():
                    command += ['--ro-bind', mount, mount]
            if not str(prefix).startswith('/usr/'):
                command += ['--ro-bind', str(prefix), str(prefix)]
            if environment_fd is not None:
                command += ['--ro-bind-fd', str(environment_fd), '/venv',
                            '--tmpfs', '/venv/bin', '--symlink', str(interpreter), '/venv/bin/python',
                            '--setenv', 'VIRTUAL_ENV', '/venv']
            command += ['--bind', str(snapshot), '/project', '--chdir', '/project',
                        '--', executable, *argv[1:]]
            with self.registry.access(project_id, revision, 'execute'):
                process = await asyncio.create_subprocess_exec(
                    *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    env={'PATH': '/usr/bin:/bin'}, start_new_session=True,
                    pass_fds=(environment_fd,) if environment_fd is not None else ())
            output = bytearray()

            async def consume(stream):
                while chunk := await stream.read(8192):
                    output.extend(chunk)
                    if len(output) > 512_000:
                        raise ProjectAccessError('Project output exceeds limit')
                    if on_output is not None:
                        await on_output(chunk.decode('utf-8', errors='replace'))

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
                artifacts = {}
                root_fd = os.open(snapshot, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                try:
                    for path in capture_paths:
                        with _parent(root_fd, path) as (parent, name):
                            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
                            with os.fdopen(fd, 'rb') as stream:
                                import stat
                                info = os.fstat(stream.fileno())
                                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                                    raise ProjectAccessError('Execution artifact must be a regular file')
                                data = stream.read(1_000_001)
                                if len(data) > 1_000_000:
                                    raise ProjectAccessError('Execution artifact exceeds size limit')
                                artifacts[path] = data.decode('utf-8')
                finally:
                    os.close(root_fd)
                return {'exitCode': process.returncode,
                        'output': output.decode('utf-8', errors='replace'),
                        'environment': 'project' if environment_fd is not None else 'base',
                        'snapshotFiles': count, 'snapshotBytes': total,
                        **({'artifacts': artifacts} if capture_paths else {}),
                        **({'sourceVersions': {path: hashlib.sha256(data).hexdigest()
                                               for path, data in observed.items()}}
                           if include_versions else {})}
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
