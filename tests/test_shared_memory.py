"""Read contracts, durable references and bounded LLM consultation."""

import json
from unittest.mock import Mock

import pytest

from bigbrain.bus.bus import MessageBus
from bigbrain.memory.shared import SharedMemory, execute_memory


async def project(bus, session='sess-a', task='run-a', path='sandbox/klipper-gcode-offline'):
    for event, payload in [
        ('contracts.proposal', {'project_target': {'mode': 'new', 'path': path}}),
        ('workspace.file_written', {'path': path + '/main.py'}),
        ('workspace.file_written', {'path': path + '/tests/test_parser.py'}),
        ('verification.run_recorded', {'verdict': 'failed', 'run_id': 'gate-real-fixture'}),
        ('task.failed', {'error': 'Tests failed'}),
    ]:
        await bus.broadcast_event(source='orchestrator_default', event_type=event,
            payload={'session_id': session, 'task_id': task, **payload})


@pytest.mark.asyncio
async def test_projects_survive_failure_restart_and_incremental_reads(tmp_path):
    bus = MessageBus(tmp_path / 'logs', auth=None)
    await project(bus)
    await project(bus, session='sess-b', task='run-b', path='sandbox/private')
    await bus.close()
    shared = SharedMemory(bus.logger.log_dir)
    listing = shared.projects('sess-a')
    assert listing['projects'][0]['path'] == 'sandbox/klipper-gcode-offline'
    assert len(listing['projects']) == 1
    assert shared.owns_partial_project('sess-a', 'sandbox/klipper-gcode-offline')
    assert not shared.owns_partial_project('sess-b', 'sandbox/klipper-gcode-offline')
    assert not shared.owns_partial_project('sess-a', 'sandbox/invented')
    restarted = SharedMemory(bus.logger.log_dir)
    detail = restarted.projects('sess-a', 'run-a')['projects'][0]
    assert detail['status'] == 'failed' and detail['verdict'] == 'failed'
    assert detail['error'] == 'Tests failed'
    assert len(detail['files']) == 2
    assert detail['evidence'] == 'gate-real-fixture'
    assert restarted.projects('sess-a', 'run-b')['status'] == 'empty'
    assert restarted.projects('sess-new')['status'] == 'empty'
    from bigbrain.web.sessions import SessionStore
    sessions = SessionStore()
    sessions.ensure('sess-a')
    sessions.delete('sess-a')
    assert restarted.projects('sess-a')['status'] == 'unavailable'
    assert not restarted.owns_partial_project('sess-a', 'sandbox/klipper-gcode-offline')


@pytest.mark.asyncio
async def test_partial_project_proposal_without_writes_is_not_ownership(tmp_path):
    bus = MessageBus(tmp_path / 'logs', auth=None)
    await bus.broadcast_event(source='orchestrator_default', event_type='contracts.proposal',
        payload={'session_id': 'sess-a', 'task_id': 'unapproved',
                 'project_target': {'mode': 'new', 'path': 'sandbox/unapproved'}})
    await bus.close()
    assert not SharedMemory(bus.logger.log_dir).owns_partial_project('sess-a', 'sandbox/unapproved')


def test_tools_cannot_change_scope_or_write(tmp_path):
    shared = SharedMemory(tmp_path / 'logs')
    persistent = Mock()
    for request in [
        {'tool': 'projects.list', 'arguments': {'session_id': 'sess-b'}},
        {'tool': 'projects.read', 'arguments': {'id': 'run-b', 'path': '../../secret'}},
        {'tool': 'memory.write', 'arguments': {'content': 'invented'}},
        {'tool': 'memory.search', 'arguments': {'query': 'x' * 501}},
    ]:
        assert execute_memory(request, shared, persistent, 'sess-a')['status'] == 'invalid'
    persistent.query_report.assert_not_called()


def test_recall_failure_disabled_and_empty_are_distinct(tmp_path, monkeypatch):
    from bigbrain.memory.chromadb_backend import ChromaMemoryBackend
    backend = object.__new__(ChromaMemoryBackend)
    backend._collection = Mock()
    backend._collection.query.side_effect = RuntimeError('offline')
    shared = SharedMemory(tmp_path / 'logs')
    request = {'tool': 'memory.search', 'arguments': {'query': 'nom de mon chat'}}
    assert execute_memory(request, shared, backend, 'sess-a')['status'] == 'error'
    backend._collection = None
    assert execute_memory(request, shared, backend, 'sess-a')['status'] == 'unavailable'
    monkeypatch.setenv('BIGBRAIN_RECALL', '0')
    assert execute_memory(request, shared, backend, 'sess-a')['status'] == 'disabled'


@pytest.mark.asyncio
async def test_front_consults_project_then_delegates_without_initial_injection(tmp_path):
    from bigbrain.front.front_brain import FrontBrain
    bus = MessageBus(tmp_path / 'logs', auth=None)
    await project(bus)

    class Provider:
        def __init__(self):
            self.calls = []

        async def chat_complete(self, messages, **kwargs):
            self.calls.append(messages)
            if len(self.calls) == 1:
                assert 'sandbox/klipper-gcode-offline' not in json.dumps(messages)
                return '{"memory":{"tool":"projects.list","arguments":{}}}'
            if len(self.calls) == 2:
                assert 'sandbox/klipper-gcode-offline' in json.dumps(messages)
                return '{"memory":{"tool":"projects.read","arguments":{"id":"run-a"}}}'
            assert 'tests/test_parser.py' in json.dumps(messages)
            return json.dumps({'reply': 'Je corrige le projet existant.', 'task': 'Fix tests',
                'project_target': {'mode': 'existing', 'path': 'sandbox/klipper-gcode-offline'}})

    provider = Provider()
    front = FrontBrain(bus, llm_provider=provider)
    front._history_for('sess-a').append({'role': 'user', 'content': 'Modifie le projet pour passer les tests'})
    result = json.loads(await front._llm_respond('Modifie le projet', session_id='sess-a'))
    assert result['project_target']['path'] == 'sandbox/klipper-gcode-offline'
    assert len(provider.calls) == 3
    assert not any('Memory tool result' in m['content'] for m in front._history_for('sess-a'))
    await bus.close()


@pytest.mark.asyncio
async def test_memory_read_loop_is_bounded(tmp_path):
    from bigbrain.front.front_brain import FrontBrain
    bus = MessageBus(tmp_path / 'logs', auth=None)

    class Provider:
        calls = 0
        async def chat_complete(self, **kwargs):
            self.calls += 1
            return '{"memory":{"tool":"projects.list","arguments":{}}}'

    provider = Provider()
    front = FrontBrain(bus, llm_provider=provider)
    answer = await front._llm_respond('Projet ?', session_id='sess-a')
    assert provider.calls == 4
    assert 'limite' in answer
    await bus.close()


@pytest.mark.asyncio
async def test_streamed_tool_json_is_private_even_with_leading_whitespace(tmp_path):
    from bigbrain.front.front_brain import FrontBrain
    bus = MessageBus(tmp_path / 'logs', auth=None)
    class Provider:
        calls = 0
        async def chat_complete(self, **kwargs):
            self.calls += 1
            async def stream():
                chunks = ['\n', '{"memory":', '{"tool":"projects.list","arguments":{}}}'] if self.calls == 1 else ['Je ', 'retrouve le projet.']
                for chunk in chunks:
                    yield chunk
            return stream()
    front = FrontBrain(bus, llm_provider=Provider())
    from unittest.mock import AsyncMock
    front._emit_chat_delta = AsyncMock()
    answer = await front._llm_respond('Projet ?', session_id='sess-a')
    assert answer == 'Je retrouve le projet.'
    assert ''.join(call.args[0] for call in front._emit_chat_delta.call_args_list) == answer
    await bus.close()
