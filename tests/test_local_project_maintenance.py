"""Shared repair protocol with real isolated checks and deterministic model actions."""

import hashlib
import json
from types import SimpleNamespace
import pytest

from bigbrain.local_projects import ProjectAccessError, ProjectRegistry
from bigbrain.local_project_maintenance import maintain_attached
from bigbrain.local_project_transmission import prepare_source_consent, provider_recipient
from bigbrain.verification.evidence import default_repository
from bigbrain.verification.gate import RunGate


class ProtocolProvider:
    """Offline fixture; model decisions exercise the production runtime."""
    entry = SimpleNamespace(provider='openai_compat', base_url='https://provider.invalid/v1')

    def __init__(self):
        self.calls = []
        self.worker_step = 0
        self.review_step = 0

    async def chat_complete(self, **kwargs):
        self.calls.append(kwargs)
        from bigbrain.llm.usage import UsageRecord, get_tracker
        get_tracker().record(UsageRecord(model_id='offline-protocol', provider='test',
            input_tokens=100, output_tokens=30, total_tokens=130))
        name = kwargs['tool_schema']['name']
        if name == 'project_maintenance_step':
            self.worker_step += 1
            if self.worker_step == 1:
                action = {'type': 'read', 'path': 'arithmetic.py'}
            elif self.worker_step == 2:
                action = {'type': 'patch', 'path': 'arithmetic.py',
                    'sha256': hashlib.sha256(b'def add(a, b):\n    return a - b\n').hexdigest(),
                    'edits': [{'old': 'return a - b', 'new': 'return a + b'}]}
            else:
                action = {'type': 'arbitrate', 'reason': 'Unexpected further repair action'}
            return json.dumps({'action': action, 'notebook': 'Inspect reproduced addition failure'})
        self.review_step += 1
        if self.review_step == 1:
            return json.dumps({'action': {'type': 'read_many', 'pages': [
                {'path': path, 'start': 1, 'count': 80} for path in ['arithmetic.py', 'test_arithmetic.py', 'main.py']]},
                'notebook': 'Inspect implementation, assertions and entry path'})
        return json.dumps({'action': None, 'decision': 'pass', 'contradictions': [],
            'missing_evidence': [], 'notebook': 'Addition assertion exercises the repaired implementation',
            'coverage': [{'criterion_id': '0', 'tests': ['test_arithmetic.py::Tests::test_add'],
                          'runtime': [], 'sources': ['arithmetic.py', 'test_arithmetic.py'],
                          'reason': 'The executed assertion verifies add(2, 3) equals five through the actual function'}]})


class Worker:
    _cancelled = False

    def __init__(self, provider):
        self.llm_provider = provider
        self.events = []

    async def send_progress(self, data):
        self.events.append(data)

    async def send_event(self, event, data):
        self.events.append((event, data))


def setup(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'arithmetic.py').write_text('def add(a, b):\n    return a - b\n')
    (source / 'main.py').write_text('from arithmetic import add\nprint(add(2, 3))\n')
    (source / 'test_arithmetic.py').write_text('import unittest\nfrom arithmetic import add\n'
        'class Tests(unittest.TestCase):\n'
        '    def test_add(self): self.assertEqual(add(2, 3), 5)\n')
    (source / 'config.py').write_text('api_key = "synthetic-sensitive-value"\n')
    registry = ProjectRegistry(tmp_path / 'state' / 'registry.json')
    project = registry.attach(source, ('read', 'write', 'execute', 'transmit'))
    provider = ProtocolProvider()
    consent = prepare_source_consent(registry, project['id'], 1, provider_recipient(provider))
    request = 'Repair addition so add(2, 3) returns five'
    repository = default_repository()
    spec = RunGate(repository).build_spec(request, ['main.py'])
    spec.metadata.update(local_project={'project_id': project['id'], 'revision': 1},
                         source_transmission=consent, business_criteria=['add(2, 3) returns five'])
    repository.save_spec(spec)
    approved = repository.approve_spec(spec.design_id, plan_id='attached-offline')
    payload = {'user_request': request, 'deliverable_type': 'python', 'entry_point': 'main.py',
               'contract_revision': {'design_id': approved.design_id, 'revision': approved.revision}}
    return source, registry, project, provider, payload


@pytest.mark.asyncio
async def test_existing_repair_engine_publishes_verified_attached_change(tmp_path):
    source, registry, project, provider, payload = setup(tmp_path)
    result = await maintain_attached(Worker(provider), registry, project['id'], 1, payload)
    assert result['success'], result
    assert result['changed_paths'] == ['arithmetic.py']
    assert (source / 'arithmetic.py').read_text() == 'def add(a, b):\n    return a + b\n'
    assert (source / 'config.py').read_text() == 'api_key = "synthetic-sensitive-value"\n'
    assert provider.worker_step == 2
    assert provider.review_step == 2
    assert 'synthetic-sensitive-value' not in json.dumps(provider.calls)
    assert 'diagnostic_output' not in json.dumps(result)


@pytest.mark.asyncio
async def test_changed_source_prevents_model_calls(tmp_path):
    source, registry, project, provider, payload = setup(tmp_path)
    (source / 'arithmetic.py').write_text('user edit\n')
    with pytest.raises(ProjectAccessError, match='inventory changed'):
        await maintain_attached(Worker(provider), registry, project['id'], 1, payload)
    assert provider.calls == []
    assert (source / 'arithmetic.py').read_text() == 'user edit\n'


@pytest.mark.asyncio
async def test_provider_change_requires_renewed_approval(tmp_path):
    source, registry, project, provider, payload = setup(tmp_path)
    provider.entry = SimpleNamespace(provider='openai_compat', base_url='https://other.invalid/v1')
    with pytest.raises(ProjectAccessError):
        await maintain_attached(Worker(provider), registry, project['id'], 1, payload)
    assert provider.calls == []
    assert 'return a - b' in (source / 'arithmetic.py').read_text()


@pytest.mark.asyncio
async def test_python_specialist_dispatches_approved_attached_repair(tmp_path, monkeypatch):
    from bigbrain.brains.python_brain import PythonBrain
    from bigbrain.bus.bus import MessageBus
    from bigbrain.bus.message import BusMessage, MessageType
    import bigbrain.local_projects as projects

    source, registry, project, provider, payload = setup(tmp_path)
    monkeypatch.setattr(projects, 'default_registry', lambda: registry)
    brain = PythonBrain(bus=MessageBus(log_dir=tmp_path / 'logs'),
                        work_dir=tmp_path / 'worker', llm_provider=provider)
    message = BusMessage(type=MessageType.TASK, source='orchestrator', target=brain.name,
        payload={**payload, 'type': 'maintain_project',
                 'local_project': {'project_id': project['id'], 'revision': 1}})
    result = await brain.handle_task(message)
    assert result['success'], result
    assert result['changed_paths'] == ['arithmetic.py']
    assert 'return a + b' in (source / 'arithmetic.py').read_text()
    assert brain._directory_context.get() is None
