"""Structured checks on disposable projects and their bound working copies."""

import pytest

from bigbrain.local_projects import ProjectRegistry
from bigbrain.local_project_checks import run_project_tests
from bigbrain.local_project_runner import ProjectRunner


@pytest.mark.asyncio
async def test_unittest_reports_real_cases_and_failures(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'main.py').write_text('def value(): return 1\n')
    (source / 'test_main.py').write_text('import unittest\nfrom main import value\n'
        'class Tests(unittest.TestCase):\n'
        '    def test_value(self): self.assertEqual(value(), 2)\n')
    registry = ProjectRegistry(tmp_path / 'state' / 'registry.json')
    project = registry.attach(source, ('read', 'write', 'execute'))
    before = await run_project_tests(registry, project['id'], 1)
    assert before['status'] == 'failed'
    assert before['test_count'] == 1
    assert before['passed_cases'] == []
    snapshot = registry.create_snapshot(project['id'], 1)
    from bigbrain.local_projects import ProjectFiles
    import hashlib
    ProjectFiles(registry, snapshot['id'], 1).write('main.py', b'def value(): return 2\n',
        hashlib.sha256(b'def value(): return 1\n').hexdigest())
    after = await run_project_tests(registry, snapshot['id'], 1)
    assert after['status'] == 'passed', after
    assert after['passed_cases'] == ['test_main.py::Tests::test_value']
    assert (source / 'main.py').read_text() == 'def value(): return 1\n'


@pytest.mark.asyncio
async def test_capture_refuses_symlink_artifact(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'main.py').write_text('import os\nos.symlink("/etc/passwd", "report.json")\n')
    registry = ProjectRegistry(tmp_path / 'state' / 'registry.json')
    project = registry.attach(source, ('read', 'execute'))
    with pytest.raises(OSError):
        await ProjectRunner(registry).run(project['id'], 1, ['python', 'main.py'], capture_paths=['report.json'])


@pytest.mark.asyncio
async def test_empty_test_inventory_remains_unverified(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'main.py').write_text('print(42)\n')
    registry = ProjectRegistry(tmp_path / 'state' / 'registry.json')
    project = registry.attach(source, ('read', 'execute'))
    result = await run_project_tests(registry, project['id'], 1)
    assert result['status'] == 'not_applicable'
    assert result['cause'] == 'missing_test'
