"""Real subprocess isolation and revocation checks on disposable projects."""

import asyncio
import shutil
import shlex
import sys
import subprocess
import socket
import pytest

from bigbrain.local_projects import ProjectAccessError, ProjectRegistry
from bigbrain.local_project_runner import ProjectRunner


@pytest.mark.asyncio
async def test_isolation_runtime_outside_sanitized_path(tmp_path, monkeypatch):
    """Launch the discovered binary after clearing the inherited environment."""
    tools = tmp_path / 'tools'
    tools.mkdir()
    selected = tools / 'bwrap'
    selected.write_text('#!/bin/sh\nprintf "selected runtime\\n"\nexec '
                        + shlex.quote(shutil.which('bwrap')) + ' "$@"\n')
    selected.chmod(0o700)
    monkeypatch.setenv('PATH', str(tools))
    root = tmp_path / 'source'
    root.mkdir()
    (root / 'main.py').write_text('print("isolated custom runtime")\n')
    registry = ProjectRegistry(tmp_path / 'registry.json')
    project = registry.attach(root, ('read', 'execute'))
    result = await ProjectRunner(registry).run(project['id'], 1, ['python', 'main.py'])
    assert result['exitCode'] == 0, result
    assert result['output'].splitlines() == ['selected runtime', 'isolated custom runtime']


@pytest.mark.asyncio
async def test_snapshot_executes_without_host_source_mutation(tmp_path):
    root = tmp_path / 'source'
    root.mkdir()
    secret = tmp_path / 'secret'
    secret.write_text('private')
    code = ('from pathlib import Path\n'
            f'assert not Path({str(secret)!r}).exists()\n'
            'Path("created.txt").write_text("scratch")\n'
            'print("isolated")\n')
    (root / 'main.py').write_text(code)
    (root / '.env').write_text('secret')
    registry = ProjectRegistry(tmp_path / 'registry.json')
    project = registry.attach(root, ('read', 'execute'))
    result = await ProjectRunner(registry).run(project['id'], 1, ['python', 'main.py'])
    assert result['exitCode'] == 0, result['output']
    assert result['output'].strip() == 'isolated'
    assert result['snapshotFiles'] == 1
    assert not (root / 'created.txt').exists()
    assert secret.read_text() == 'private'


@pytest.mark.asyncio
async def test_revocation_terminates_running_snapshot(tmp_path):
    root = tmp_path / 'source'
    root.mkdir()
    (root / 'main.py').write_text('import time\ntime.sleep(20)\n')
    registry = ProjectRegistry(tmp_path / 'registry.json')
    project = registry.attach(root, ('read', 'execute'))
    running = asyncio.create_task(ProjectRunner(registry).run(project['id'], 1, ['python', 'main.py']))
    await asyncio.sleep(0.4)
    registry.change(project['id'], 1, state='revoked')
    with pytest.raises(ProjectAccessError):
        await asyncio.wait_for(running, 3)


@pytest.mark.asyncio
async def test_project_environment_supplies_its_packages(tmp_path):
    root = tmp_path / 'source'
    root.mkdir()
    subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(root / '.venv')], check=True)
    packages = next((root / '.venv' / 'lib').glob('python*/site-packages'))
    (packages / 'project_only.py').write_text('VALUE = "project dependency"')
    (root / 'main.py').write_text('from project_only import VALUE\nprint(VALUE)\n')
    registry = ProjectRegistry(tmp_path / 'registry.json')
    project = registry.attach(root, ('read', 'execute'))
    result = await ProjectRunner(registry).run(project['id'], 1, ['python', 'main.py'])
    assert result['exitCode'] == 0, result['output']
    assert result['environment'] == 'project'
    assert result['output'].strip() == 'project dependency'


@pytest.mark.asyncio
async def test_private_environment_and_network_namespace(tmp_path, monkeypatch):
    root = tmp_path / 'source'
    root.mkdir()
    monkeypatch.setenv('BIGBRAIN_TEST_SECRET', 'synthetic-environment-canary')
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        port = listener.getsockname()[1]
        (root / 'main.py').write_text('import os, socket\n'
            'assert os.getenv("BIGBRAIN_TEST_SECRET") is None\n'
            f's = socket.socket(); s.settimeout(0.3); assert s.connect_ex(("127.0.0.1", {port})) != 0\n'
            f's.close(); s = socket.socket(); s.bind(("127.0.0.1", {port})); print("private namespace")\n')
        registry = ProjectRegistry(tmp_path / 'state/registry.json')
        project = registry.attach(root, ('read', 'execute'))
        result = await ProjectRunner(registry).run(project['id'], 1, ['python', 'main.py'])
    assert result['exitCode'] == 0, result
    assert result['output'].strip() == 'private namespace'


@pytest.mark.asyncio
async def test_timeout_and_output_limits_terminate_execution(tmp_path):
    root = tmp_path / 'source'
    root.mkdir()
    registry = ProjectRegistry(tmp_path / 'state/registry.json')
    project = registry.attach(root, ('read', 'execute'))
    runner = ProjectRunner(registry)
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(runner.run(project['id'], 1,
            ['python', '-c', 'import time; time.sleep(20)'], timeout=1), timeout=4)
    with pytest.raises(ProjectAccessError, match='output exceeds'):
        await asyncio.wait_for(runner.run(project['id'], 1,
            ['python', '-c', 'print("x" * 700000)']), timeout=4)
