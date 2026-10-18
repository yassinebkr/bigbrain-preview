"""Concurrency/Stop regressions use real async tasks and the real bus."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from bigbrain.bus.bus import MessageBus
from bigbrain.bus.message import BusMessage, MessageType
from bigbrain.front.front_brain import FrontBrain
from bigbrain.orchestrator.orchestrator import WorkspaceOrchestrator, TaskPlan, TaskStatus, SubTask
from bigbrain.web.server import WebServer


@pytest.mark.asyncio
@pytest.mark.parametrize('streaming', [False, True])
async def test_concurrent_front_replies_keep_their_session_context(tmp_path, streaming):
    waiting, release = asyncio.Event(), asyncio.Event()
    class Provider:
        async def chat_complete(self, messages, **kwargs):
            name = messages[-1]['content']
            if name == 'A':
                waiting.set()
                await release.wait()
            if streaming:
                async def chunks():
                    yield 'reply ' + name
                return chunks()
            return 'reply ' + name
    bus = MessageBus(tmp_path / 'logs', auth=None)
    events = []
    async def observe(message):
        events.append(message)
    bus.subscribe('*', observe)
    front = FrontBrain(bus, llm_provider=Provider())
    def message(name):
        return BusMessage(type=MessageType.TASK, source='morphable_ui', target='front_brain',
            payload={'text': name, 'session_id': 'sess-' + name, 'conversation_history': []})
    first = asyncio.create_task(front._handle_ui_message(message('A')))
    try:
        await asyncio.wait_for(waiting.wait(), timeout=2)
        await front._handle_ui_message(message('B'))
        release.set()
        await asyncio.wait_for(first, timeout=2)
        kind = 'chat.done' if streaming else 'chat.message'
        replies = [event.payload for event in events if event.payload.get('event') == kind]
        assert {(reply['session_id'], reply['text']) for reply in replies} == {
            ('sess-A', 'reply A'), ('sess-B', 'reply B')}
        if streaming:
            deltas = [e.payload for e in events if e.payload.get('event') == 'chat.delta']
            assert {(d['session_id'], d['delta']) for d in deltas} == {
                ('sess-A', 'reply A'), ('sess-B', 'reply B')}
    finally:
        first.cancel()
        await asyncio.gather(first, return_exceptions=True)
        await bus.close()


@pytest.mark.asyncio
async def test_stop_only_cancels_chat_delivery_for_the_requested_session(tmp_path, monkeypatch):
    from bigbrain.web import server as module
    bus = MessageBus(tmp_path / 'logs', auth=None)
    server = WebServer(bus)
    started = {name: asyncio.Event() for name in ['A', 'B']}
    cancelled = set()
    async def pending(ws, data):
        name = data['payload']['sessionId']
        started[name].set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.add(name)
    monkeypatch.setattr(server, '_handle_chat_send', pending)
    hook = AsyncMock()
    monkeypatch.setattr(module, 'CANCEL_HOOK', hook)
    ws = AsyncMock()
    try:
        for name in ['A', 'B']:
            await server._handle_ws_message(ws, json.dumps({'type': 'chat.send', 'payload': {'sessionId': name}}))
        await asyncio.wait_for(asyncio.gather(*(event.wait() for event in started.values())), timeout=2)
        await server._handle_ws_message(ws, json.dumps({'type': 'chat.cancel', 'payload': {'sessionId': 'A'}}))
        assert cancelled == {'A'}
        assert len(server._chat_tasks) == 1
        hook.assert_awaited_once_with(session_id='A')
        # Missing scope must never mean "cancel every other conversation".
        await server._handle_ws_message(ws, json.dumps({'type': 'chat.cancel'}))
        assert cancelled == {'A'}
        assert len(server._chat_tasks) == 1
    finally:
        tasks = list(server._chat_tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await bus.close()


@pytest.mark.asyncio
async def test_scoped_orchestrator_stop_leaves_other_plans_running(tmp_path):
    bus = MessageBus(tmp_path / 'logs', auth=None)
    orch = WorkspaceOrchestrator('default', bus)
    for name in ['A', 'B']:
        orch.task_plans[name] = TaskPlan(id=name, status=TaskStatus.RUNNING,
            original_task=BusMessage(type=MessageType.TASK, source='front_brain', target=orch.name,
                                     payload={'session_id': name}))
    await orch._handle_cancel_request(BusMessage(type=MessageType.CANCEL,
        source='morphable_ui', target=orch.name, payload={'session_id': 'A', 'mode': 'hard'}))
    assert orch.task_plans['A'].status == TaskStatus.CANCELLED
    assert orch.task_plans['B'].status == TaskStatus.RUNNING
    await bus.close()


@pytest.mark.asyncio
async def test_system_scoped_stop_never_broadcasts_a_global_worker_cancel():
    from bigbrain.system import BigBrainSystem
    system = BigBrainSystem.__new__(BigBrainSystem)
    system.front_brain = SimpleNamespace(request_stop=Mock())
    system.orchestrator = SimpleNamespace(_handle_cancel_request=AsyncMock(), name='orch')
    system.bus = SimpleNamespace(send=AsyncMock())
    await system.cancel_current(session_id='A')
    system.front_brain.request_stop.assert_called_once_with(session_id='A')
    assert system.orchestrator._handle_cancel_request.await_args.args[0].payload['session_id'] == 'A'
    system.bus.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_stop_between_started_event_and_bus_delivery_prevents_worker_execution(tmp_path):
    bus = MessageBus(tmp_path / 'logs', auth=None)
    orch = WorkspaceOrchestrator('default', bus)
    step = SubTask(id='step', description='write', brain_target='worker', payload={'type': 'write_web_file'})
    plan = TaskPlan(id='plan', subtasks=[step], status=TaskStatus.RUNNING,
        original_task=BusMessage(type=MessageType.TASK, source='front_brain', target=orch.name,
                                 payload={'session_id': 'A'}))
    orch.task_plans[plan.id] = plan
    events = []
    async def observe(message):
        events.append(message)
        if message.payload.get('event') == 'subtask.started':
            await orch._cancel_task(plan.id, 'hard')
    bus.subscribe('*', observe)
    await orch._dispatch_subtask(plan, step)
    assert plan.status == TaskStatus.CANCELLED
    assert not any(m.type == MessageType.TASK for m in events)
    assert orch.brain_load['worker'] == 0
    assert orch.active_subtasks == {}
    await bus.close()


def test_one_terminal_plan_does_not_erase_another_pending_contract(tmp_path):
    server = WebServer(MessageBus(tmp_path / 'logs', auth=None))
    for name in ['A', 'B']:
        for event in ['task.routing', 'task.received', 'contracts.proposal']:
            payload = {'event': event, 'session_id': name, 'plan_id': name, 'task_id': name}
            server._maybe_buffer('event', event, {'source': 'orchestrator', 'payload': payload})
    server._maybe_buffer('event', 'task.failed', {
        'source': 'orchestrator', 'payload': {'event': 'task.failed', 'session_id': 'A', 'task_id': 'A'}})
    pending_b = [d['payload']['event'] for _, d in server._replay_buffer if d['payload'].get('session_id') == 'B']
    assert set(pending_b) == {'task.routing', 'task.received', 'contracts.proposal'}


@pytest.mark.asyncio
async def test_worker_events_carry_server_owned_plan_and_session_ids(tmp_path):
    from bigbrain.brains.python_brain import PythonBrain
    bus = MessageBus(tmp_path / 'logs', auth=None)
    events = []
    async def observe(message):
        events.append(message)
    bus.subscribe('*', observe)
    brain = PythonBrain('worker', bus, work_dir=tmp_path / 'workspace')
    brain._current_task = BusMessage(type=MessageType.TASK, source='orchestrator', target=brain.name,
        payload={'session_id': 'A', '_plan_id': 'plan-A', '_subtask_id': 'step-A'})
    await brain.send_event('verification.run_recorded', {'session_id': 'wrong', 'run_id': 'evidence-A'})
    await brain.send_progress({'stage': 'testing'})
    for event in events:
        assert event.payload['session_id'] == 'A'
        assert event.payload['task_id'] == 'plan-A'
        assert event.payload['subtask_id'] == 'step-A'
    await bus.close()


@pytest.mark.asyncio
async def test_tabs_without_an_explicit_session_never_inherit_another_tab_history(tmp_path):
    bus = MessageBus(tmp_path / 'logs', auth=None)
    server = WebServer(bus)
    server._active_session_id = 'sess-other'
    server._sessions.append_message('sess-other', 'user', 'private old conversation')
    first, second, empty = AsyncMock(), AsyncMock(), AsyncMock()
    await server._handle_chat_send(first, {'payload': {'text': 'first'}})
    await server._handle_chat_send(second, {'payload': {'text': 'second'}})
    assert server._ws_session_ids[first] != server._ws_session_ids[second]
    assert server._ws_session_ids[first] != 'sess-other'
    await server._handle_request(empty, {'id': 'r', 'method': 'chat.history'})
    assert empty.send_json.await_args.args[0]['payload']['messages'] == []
    await bus.close()


@pytest.mark.asyncio
async def test_two_tabs_sending_to_one_conversation_are_serialized_with_fresh_history(tmp_path):
    bus = MessageBus(tmp_path / 'logs', auth=None)
    server = WebServer(bus)
    bus.subscribe('*', server._on_bus_message)
    started, release = asyncio.Event(), asyncio.Event()
    delivered = []
    async def front(message):
        if message.type != MessageType.TASK:
            return
        delivered.append(message.payload)
        if message.payload['text'] == 'first':
            started.set()
            await release.wait()
            await bus.broadcast_event(source='front_brain', event_type='chat.message',
                payload={'text': 'first reply', 'role': 'assistant', 'session_id': 'sess-same'})
    bus.subscribe('front_brain', front)
    def data(text):
        return {'payload': {'text': text, 'sessionId': 'sess-same'}}
    first = asyncio.create_task(server._handle_chat_send(AsyncMock(), data('first')))
    second = None
    try:
        await asyncio.wait_for(started.wait(), timeout=2)
        second = asyncio.create_task(server._handle_chat_send(AsyncMock(), data('second')))
        await asyncio.sleep(0)
        assert len(delivered) == 1
        release.set()
        await asyncio.wait_for(asyncio.gather(first, second), timeout=2)
        assert delivered[1]['conversation_history'] == [
            {'role': 'user', 'content': 'first'}, {'role': 'assistant', 'content': 'first reply'}]
    finally:
        for task in [first, second]:
            if task:
                task.cancel()
        await asyncio.gather(*(t for t in [first, second] if t), return_exceptions=True)
        await bus.close()


@pytest.mark.asyncio
async def test_chat_remains_available_after_ack_while_planning_continues(tmp_path):
    bus = MessageBus(tmp_path / 'logs', auth=None)
    server = WebServer(bus)
    bus.subscribe('*', server._on_bus_message)
    planning, release = asyncio.Event(), asyncio.Event()
    second_answered = asyncio.Event()
    async def front(message):
        if message.type != MessageType.TASK:
            return
        if message.payload['text'] == 'first':
            await bus.broadcast_event(source='front_brain', event_type='chat.message', payload={
                'text': 'Je prépare le projet', 'session_id': 'sess-same',
                'turn_id': message.payload['turn_id']})
            planning.set()
            await release.wait()
        else:
            second_answered.set()
    bus.subscribe('front_brain', front)
    def data(text):
        return {'payload': {'text': text, 'sessionId': 'sess-same'}}
    first = asyncio.create_task(server._handle_chat_send(AsyncMock(), data('first')))
    second = None
    try:
        await asyncio.wait_for(planning.wait(), timeout=2)
        second = asyncio.create_task(server._handle_chat_send(AsyncMock(), data('another question')))
        await asyncio.wait_for(second_answered.wait(), timeout=2)
        assert not first.done()
        release.set()
        await asyncio.gather(first, second)
        assert server._reply_events == {}
    finally:
        for task in [first, second]:
            if task:
                task.cancel()
        await asyncio.gather(*(t for t in [first, second] if t), return_exceptions=True)
        await bus.close()
