"""Structured Python test evidence collected through the isolated project runner."""

import ast
import json
import uuid

from .local_projects import ProjectFiles
from .local_project_runner import ProjectRunner


UNITTEST_REPORTER = '''
import inspect, json, os, sys, unittest
sys.path.insert(0, "/project")
class Recorder(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []
    def record(self, test, outcome):
        source = os.path.relpath(inspect.getsourcefile(test.__class__), "/project")
        self.records.append({"nodeid": source + "::" + test.__class__.__name__ + "::" + test._testMethodName,
                             "phase": "call", "outcome": outcome})
    def addSuccess(self, test):
        super().addSuccess(test)
        self.record(test, "passed")
    def addFailure(self, test, error):
        super().addFailure(test, error)
        self.record(test, "failed")
    def addError(self, test, error):
        super().addError(test, error)
        self.record(test, "failed")
suite = unittest.defaultTestLoader.discover(".")
result = unittest.TextTestRunner(verbosity=2, resultclass=Recorder).run(suite)
records = {"count": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
           "skipped": len(result.skipped), "records": result.records}
with open(sys.argv[1], "w", encoding="utf-8") as stream:
    json.dump(records, stream)
raise SystemExit(0 if result.wasSuccessful() and result.testsRun else 1)
'''


async def run_project_tests(registry, project_id, revision):
    """Choose an observed framework and preserve structured failure diagnostics."""
    files = ProjectFiles(registry, project_id, revision)
    paths = []

    def inventory(directory=''):
        if len(directory.split('/')) > 32 or len(paths) > 2000:
            raise ValueError('Test inventory exceeds project limits')
        for entry in files.list(directory):
            if entry['type'] == 'folder':
                inventory(entry['path'])
            elif entry['name'].endswith('.py') and (
                    entry['name'].startswith('test_') or entry['name'].endswith('_test.py')):
                paths.append(entry['path'])

    inventory()
    if not paths:
        return {'status': 'not_applicable', 'cause': 'missing_test',
                'next_action': 'extend_validation', 'tests': [], 'passed_cases': []}
    imports = set()
    for path in paths:
        try:
            tree = ast.parse(files.read(path).decode('utf-8'), filename=path)
        except SyntaxError as exc:
            return {'status': 'failed', 'cause': 'reproduced_defect', 'next_action': 'repair',
                    'tests': paths, 'diagnostic_output': str(exc), 'passed_cases': []}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split('.')[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add((node.module or '').split('.')[0])
    unittest = 'unittest' in imports and 'pytest' not in imports
    report = 'bigbrain-test-report-' + uuid.uuid4().hex + '.json'
    if unittest:
        script = UNITTEST_REPORTER
    else:
        from .verification.executors import _PYTEST_REPORTER
        probe = await ProjectRunner(registry).run(project_id, revision,
            ['python', '-I', '-c', 'import pytest; print(pytest.__version__)'])
        if probe['exitCode'] != 0:
            return {'status': 'inconclusive', 'cause': 'environment_blocked', 'next_action': 'stop',
                    'reason': 'pytest is unavailable in the project environment',
                    'diagnostic_output': probe['output'], 'tests': paths, 'passed_cases': []}
        script = 'import pytest,sys;sys.path.insert(0,"/project")\n' + _PYTEST_REPORTER
    result = await ProjectRunner(registry).run(project_id, revision,
        ['python', '-I', '-c', script, report, '-q'], capture_paths=[report])
    records = json.loads(result['artifacts'][report])
    if unittest:
        count = records.get('count', 0)
        passed = result['exitCode'] == 0 and count > 0
        passed_cases = [record['nodeid'] for record in records.get('records', [])
                        if record.get('outcome') == 'passed']
    else:
        valid = isinstance(records, list) and all(isinstance(item, dict)
            and isinstance(item.get('nodeid'), str) and item.get('phase') in {'setup', 'call', 'teardown'}
            and item.get('outcome') in {'passed', 'failed', 'skipped'} for item in records)
        count = sum(item.get('phase') == 'call' for item in records) if valid else 0
        passed = valid and result['exitCode'] == 0 and count > 0
        passed_cases = sorted({item['nodeid'] for item in records
                              if item.get('phase') == 'call' and item.get('outcome') == 'passed'}) if valid else []
    inconclusive = result['exitCode'] == 0 and not passed_cases
    return {'status': 'inconclusive' if inconclusive else 'passed' if passed else 'failed',
            'framework': 'unittest' if unittest else 'pytest', 'returncode': result['exitCode'],
            **({'cause': 'missing_test', 'next_action': 'extend_validation',
                'reason': 'No passing executable assertion was observed'} if inconclusive else {}),
            'tests': paths, 'passed_cases': passed_cases, 'test_count': count,
            'records': records, 'diagnostic_output': result['output'],
            'environment': result['environment']}
