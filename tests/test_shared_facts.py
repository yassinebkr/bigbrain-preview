import json
from unittest.mock import AsyncMock

import pytest

from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType
from bigbrain.memory.shared import SharedMemory, execute_memory
from bigbrain.web.sessions import SessionStore


def user_source(session, text, role='user'):
    updated = SessionStore().append_message(session, role, text)
    return updated['messages'][-1]


def write_args(source, value='Chichi', revision=0):
    return {'key': 'user.cat.name', 'value': value, 'quote': source['text'],
            'source_message_id': source['id'], 'expected_revision': revision}


def write(shared, session, args, allow=True):
    return execute_memory({'tool': 'facts.write', 'arguments': args}, shared, None, session, allow_write=allow)


def test_fact_revisions_sources_restart_and_stale_writes(tmp_path):
    shared = SharedMemory(tmp_path / 'logs')
    first = user_source('sess-a', 'Mon chat se nomme Chichi.')
    assert write(shared, 'sess-a', write_args(first))['revision'] == 1
    assert write(shared, 'sess-a', write_args(first))['duplicate']
    corrected = user_source('sess-a', 'Correction : il se nomme Moka.')
    assert write(shared, 'sess-a', write_args(corrected, 'Moka', 0))['status'] == 'conflict'
    assert write(shared, 'sess-a', write_args(corrected, 'Moka', 1))['revision'] == 2
    assert write(shared, 'sess-a', write_args(first, revision=2))['status'] == 'conflict'
    restarted = SharedMemory(tmp_path / 'logs')
    result = restarted.facts_read('user.cat.name')
    assert result['fact']['value'] == 'Moka'
    assert result['fact']['source_message'] == corrected['id']
    assert result['history'][0]['value'] == 'Chichi'
    assert restarted.facts_search('chat')['facts'][0]['value'] == 'Moka'


def test_fact_write_rejects_assistant_cross_session_and_invented_quote(tmp_path):
    shared = SharedMemory(tmp_path / 'logs')
    human = user_source('sess-a', 'Mon chat se nomme Chichi.')
    assistant = user_source('sess-a', 'Mon chat se nomme Chichi.', role='assistant')
    assert write(shared, 'sess-a', write_args(assistant))['status'] == 'invalid'
    assert write(shared, 'sess-b', write_args(human))['status'] == 'invalid'
    assert write(shared, 'sess-a', {**write_args(human), 'quote': 'Mon chat se nomme Moka.', 'value': 'Moka'})['status'] == 'invalid'
    assert write(shared, 'sess-a', write_args(human), allow=False)['status'] == 'invalid'
    assert shared.facts_read('user.cat.name')['status'] == 'empty'


def test_concurrent_revisions_cannot_overwrite_each_other(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    shared = SharedMemory(tmp_path / 'logs')
    one = user_source('sess-a', 'Mon chat se nomme Chichi.')
    two = user_source('sess-a', 'Mon chat se nomme Moka.')
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(write, shared, 'sess-a', write_args(source, value))
                for source, value in [(one, 'Chichi'), (two, 'Moka')]]
        statuses = sorted(job.result()['status'] for job in jobs)
    assert statuses == ['conflict', 'ok']


@pytest.mark.asyncio
async def test_front_records_current_user_source_without_tool_json_in_chat(tmp_path):
    from bigbrain.front.front_brain import FrontBrain
    source = user_source('sess-a', 'Mon chat se nomme Chichi.')
    class Provider:
        calls = 0
        async def chat_complete(self, messages, **kwargs):
            self.calls += 1
            if self.calls == 1:
                assert source['id'] in json.dumps(messages)
                return json.dumps({'decision': {'operation':'consult_memory','tool': 'facts.write', 'arguments': write_args(source)}})
            assert '"revision": 1' in json.dumps(messages, ensure_ascii=False).replace('\\"', '"')
            return json.dumps({'decision':{'operation':'respond','reply':'Je retiens Chichi.'}})
    bus = MessageBus(tmp_path / 'logs', auth=None)
    front = FrontBrain(bus, llm_provider=Provider())
    front._emit_chat_message = AsyncMock()
    await front._handle_ui_message(BusMessage(type=MessageType.TASK, source='morphable_ui', target='front_brain',
        payload={'text': source['text'], 'session_id': 'sess-a', 'user_message_id': source['id']}))
    assert SharedMemory(bus.logger.log_dir).facts_read('user.cat.name')['fact']['value'] == 'Chichi'
    assert front._history_for('sess-a')[-1]['content'] == 'Je retiens Chichi.'
    assert front._source_message_context.get() is None
    await bus.close()


@pytest.mark.asyncio
async def test_current_source_reference_is_server_owned(tmp_path):
    from bigbrain.web.server import WebServer
    bus = MessageBus(tmp_path / 'logs', auth=None)
    bus.send = AsyncMock()
    server = WebServer(bus)
    await server._deliver_chat_send(AsyncMock(), {'payload': {'text': 'Mon chat se nomme Chichi.',
        'sessionId': 'sess-a', 'user_message_id': 'forged-by-client'}})
    message = bus.send.call_args.args[0]
    saved = SessionStore().get('sess-a')['messages'][-1]
    assert message.payload['user_message_id'] == saved['id']
    assert saved['role'] == 'user'
    await bus.close()


@pytest.mark.asyncio
async def test_worker_ordinary_code_does_not_consult_and_loop_is_bounded(tmp_path):
    from bigbrain.brains.python_brain import PythonBrain
    class Provider:
        calls = 0
        repeat = False
        async def complete(self, *args, **kwargs):
            self.calls += 1
            return '{"memory":{"tool":"projects.list","arguments":{}}}' if self.repeat else 'print(1)'
    bus = MessageBus(tmp_path / 'logs', auth=None)
    provider = Provider()
    worker = PythonBrain(bus=bus, llm_provider=provider, work_dir=tmp_path / 'python')
    token = worker._task_context.set(BusMessage(type=MessageType.TASK, source='orchestrator_default', target=worker.name,
                                              payload={'session_id': 'sess-a'}))
    worker.consult_memory = AsyncMock(return_value={'status': 'empty', 'projects': []})
    try:
        assert await worker.complete_with_memory(prompt='Write code', stream=False) == 'print(1)'
        assert provider.calls == 1
        worker.consult_memory.assert_not_called()
        provider.repeat = True
        with pytest.raises(ValueError, match='budget'):
            await worker.complete_with_memory(prompt='Write code', stream=False)
        assert worker.consult_memory.await_count == 2
        assert provider.calls == 4
    finally:
        worker._task_context.reset(token)
    await bus.close()


@pytest.mark.asyncio
async def test_python_and_web_workers_read_same_fact_but_own_project_scope(tmp_path):
    from bigbrain.brains.python_brain import PythonBrain
    from bigbrain.brains.web_app_brain import WebAppBrain
    shared = SharedMemory(tmp_path / 'logs')
    source = user_source('sess-a', 'Mon chat se nomme Chichi.')
    write(shared, 'sess-a', write_args(source))
    bus = MessageBus(tmp_path / 'logs', auth=None)
    class Provider:
        calls = 0
        async def complete(self, prompt, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return '{"memory":{"tool":"facts.read","arguments":{"key":"user.cat.name"}}}'
            assert 'Chichi' in prompt
            return 'print("Chichi")'
        async def chat_complete(self, messages, **kwargs):
            return await self.complete(json.dumps(messages), **kwargs)
    for brain_type in (PythonBrain, WebAppBrain):
        worker = brain_type(name=brain_type.__name__, bus=bus, llm_provider=Provider(), work_dir=tmp_path / brain_type.__name__)
        task = BusMessage(type=MessageType.TASK, source='orchestrator_default', target=worker.name,
                          payload={'session_id': 'sess-b', '_plan_id': 'run-b'})
        token = worker._task_context.set(task)
        try:
            if brain_type is PythonBrain:
                result = await worker.complete_with_memory(prompt='Write Python.', stream=False)
            else:
                result = await worker.complete_with_memory(messages=[{'role': 'user', 'content': 'Write code.'}], stream=False)
            assert result == 'print("Chichi")'
            assert worker.llm_provider.calls == 2
            denied = await worker.consult_memory({'tool': 'facts.write', 'arguments': write_args(source)})
            assert denied['status'] == 'invalid'
            missing = await worker.consult_memory({'tool': 'projects.read', 'arguments': {'id': 'run-a', 'session_id': 'sess-a'}})
            assert missing['status'] == 'invalid'
        finally:
            worker._task_context.reset(token)
    await bus.close()
