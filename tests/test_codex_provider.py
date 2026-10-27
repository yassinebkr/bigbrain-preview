"""Tests for the codex provider (Phase 4a).

Uses the provider's test hook (_set_rpc_for_test) — no codex spawn, no
real ChatGPT account, no paid calls. Mirrors shopifast's provider tests.
"""

import asyncio
import json

import pytest

from bigbrain.llm.codex_provider import (
    CodexProvider,
    _set_rpc_for_test,
    codex_auth_status,
    codex_start_login,
)
from bigbrain.llm.codex_provider import CodexJsonRpcClient, CodexUnavailable, CodexNativeToolAttempt, RPC_FRAME_LIMIT


@pytest.mark.asyncio
async def test_native_large_source_notification_is_not_limited_to_64k(monkeypatch):
    from types import SimpleNamespace
    captured = {}
    async def spawn(*args, **kwargs):
        captured.update(kwargs)
        stream = asyncio.StreamReader(limit=kwargs['limit'])
        return SimpleNamespace(stdout=stream, returncode=0)
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', spawn)
    monkeypatch.setenv('BIGBRAIN_CODEX_BINARY', '/synthetic/codex')
    client = await CodexJsonRpcClient.start()
    seen = []
    client.on_notification(seen.append)
    frame = {'method': 'item/completed', 'params': {'item': {'text': 'source' * 40000}}}
    client.proc.stdout.feed_data(json.dumps(frame).encode() + b'\n')
    client.proc.stdout.feed_eof()
    await asyncio.wait_for(client._reader_task, 1)
    assert captured['limit'] == RPC_FRAME_LIMIT
    assert seen[0] == frame
    assert seen[-1]['method'] == 'bigbrain/transport/error'


@pytest.mark.asyncio
async def test_reader_failure_notifies_active_turns_and_pending_requests():
    from types import SimpleNamespace
    stream = asyncio.StreamReader(limit=64)
    client = CodexJsonRpcClient(SimpleNamespace(stdout=stream))
    seen = []
    client.on_notification(seen.append)
    pending = asyncio.get_running_loop().create_future()
    client._pending[1] = pending
    stream.feed_data(b'x' * 1000 + b'\n')
    stream.feed_eof()
    await asyncio.wait_for(client._read_loop(), 1)
    with pytest.raises(CodexUnavailable, match='ValueError'):
        await pending
    assert client._closed
    assert seen[-1]['method'] == 'bigbrain/transport/error'
from bigbrain.llm.usage import UsageRecord, UsageTracker, set_tracker_for_test


def test_nested_research_defaults_restore_through_schema_references():
    from bigbrain.llm.codex_provider import _restore_optional_fields
    from bigbrain.research import Action
    raw = {'tool': 'conclude', 'question_id': 'q1', 'rationale': 'Observed evidence',
           'claims': [{'id': 'c1', 'question_id': 'q1', 'text': 'Draft', 'basis': 'Passage',
                       'status': 'unverified', 'limitations': None,
                       'evidence': [{'passage_id': 's1:p1', 'relation': 'supports', 'schema_version': None}]}]}
    restored = _restore_optional_fields(raw, Action.model_json_schema())
    assert 'limitations' not in restored['claims'][0]
    assert 'schema_version' not in restored['claims'][0]['evidence'][0]
    assert Action.model_validate(restored).claims[0].limitations == []


def test_front_union_restoration_selects_the_tagged_reference():
    from bigbrain.llm.codex_provider import _restore_optional_fields
    from bigbrain.front.decision import FrontDecision
    raw = {'decision': {'operation': 'delegate', 'reply': 'Research', 'objective': 'Question',
                       'route': {'brain': 'researcher', 'payload': {'type': 'research'}},
                       'project_target': None}}
    restored = _restore_optional_fields(raw, FrontDecision.model_json_schema())
    assert FrontDecision.model_validate(restored).decision.operation == 'delegate'


class FakeRpc:
    """Scripted JSON-RPC client mimicking the codex app-server."""

    def __init__(self):
        self.calls = []
        self.notifications = []  # queued server notifications to replay
        self._listeners = []
        self._request_handlers = []
        self.responses = []

    async def call(self, method, params=None):
        self.calls.append((method, params or {}))
        if method == "initialize":
            return {"ok": True}
        if method == 'config/read':
            return {'config': {'mcp_servers': {'inherited': {}}}}
        if method == "account/read":
            return self.account_result
        if method == "account/login/start":
            return self.login_result
        if method == "thread/start":
            return {"thread": {"id": "thread-1"}}
        if method == "turn/start":
            # App server pushes notifications after the call resolves.
            loop = asyncio.get_event_loop()
            for message in self.notifications:
                loop.call_soon(self._emit, message)
            return {"turn": {"id": "turn-1"}}
        if method == "turn/interrupt":
            asyncio.get_running_loop().call_soon(self._emit, {'method': 'turn/completed',
                'params': {'threadId': params['threadId'],
                    'turn': {'id': params['turnId'], 'status': 'interrupted'}}})
            return {"ok": True}
        raise RuntimeError(f"unexpected method {method}")

    def notify(self, method, params=None):
        pass

    def on_notification(self, listener):
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def on_request(self, handler):
        self._request_handlers.append(handler)
        return lambda: self._request_handlers.remove(handler)

    def respond(self, request_id, result=None, error=None):
        self.responses.append((request_id, result, error))

    def _emit(self, message):
        if message.get('id') is not None:
            for handler in list(self._request_handlers):
                if handler(message):
                    return
        for listener in list(self._listeners):
            listener(message)

    # Scripting knobs
    account_result = {"account": None}
    login_result = {"authUrl": "https://auth.example/url", "loginId": "login-1"}


@pytest.fixture(autouse=True)
def clean_state():
    fake = FakeRpc()
    _set_rpc_for_test(fake)
    set_tracker_for_test(UsageTracker())
    yield fake
    _set_rpc_for_test(None)
    set_tracker_for_test(UsageTracker())


@pytest.mark.asyncio
async def test_auth_status_signed_out(clean_state):
    assert (await codex_auth_status()) == {"authenticated": False}


@pytest.mark.asyncio
async def test_auth_status_signed_in(clean_state):
    clean_state.account_result = {
        "account": {"email": "user@example.com", "planType": "plus", "type": "chatgpt"}
    }
    status = await codex_auth_status()
    assert status["authenticated"] is True
    assert status["email"] == "user@example.com"
    assert status["planType"] == "plus"


@pytest.mark.asyncio
async def test_start_login_returns_auth_url(clean_state, monkeypatch):
    # Never open a browser from tests.
    monkeypatch.setattr("webbrowser.open", lambda url: True)
    result = await codex_start_login(open_browser=True)
    assert result["authUrl"] == "https://auth.example/url"
    assert result["loginId"] == "login-1"
    # The login method is the one the app-server owns.
    methods = [c[0] for c in clean_state.calls]
    assert "account/login/start" in methods


@pytest.mark.asyncio
async def test_start_login_without_auth_url_raises(clean_state):
    clean_state.login_result = {"unexpected": True}
    with pytest.raises(RuntimeError, match="unexpected login/start"):
        await codex_start_login(open_browser=False)


@pytest.mark.asyncio
async def test_run_turn_collects_text_and_usage(clean_state):
    clean_state.notifications = [
        {"method": "item/agentMessage", "params": {"item": {"type": "agentMessage", "text": "Hello "}}},
        {"method": "item/agentMessage", "params": {"item": {"type": "agentMessage", "text": "world"}}},
        # Usage rides on turn/completed exactly like the real server.
        {"method": "turn/completed",
         "params": {"usage": {"prompt_tokens": 12, "completion_tokens": 7,
                              "total_tokens": 19}}},
    ]
    provider = CodexProvider()
    text, usage = await provider.run_turn([{"role": "user", "content": "hi"}])
    assert text == "Hello world"
    assert isinstance(usage, UsageRecord)
    assert usage.input_tokens == 12
    assert usage.output_tokens == 7
    assert usage.provider == "codex"


@pytest.mark.asyncio
async def test_chat_complete_records_usage(clean_state):
    clean_state.notifications = [
        {"method": "item/agentMessage", "params": {"item": {"type": "agentMessage", "text": "hi"}}},
        {"method": "turn/completed",
         "params": {"usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}}},
    ]
    provider = CodexProvider()
    text = await provider.chat_complete([{"role": "user", "content": "hi"}])
    assert text == "hi"
    from bigbrain.llm.usage import get_tracker
    assert get_tracker().totals()["total_tokens"] == 5


@pytest.mark.asyncio
async def test_ephemeral_thread_per_request(clean_state):
    clean_state.notifications = [
        {"method": "turn/completed", "params": {}},
    ]
    provider = CodexProvider()
    await provider.run_turn([{"role": "user", "content": "one"}])
    await provider.run_turn([{"role": "user", "content": "two"}])
    thread_starts = [p for m, p in clean_state.calls if m == "thread/start"]
    assert len(thread_starts) == 2
    assert all(p.get("ephemeral") is True for p in thread_starts)


@pytest.mark.asyncio
async def test_current_protocol_schema_and_usage(clean_state, monkeypatch):
    monkeypatch.setenv('CODEX_CHATGPT_MODEL', 'gpt-6.1-sol')
    clean_state.notifications = [
        {'method': 'item/completed', 'params': {'threadId': 'thread-1',
            'item': {'id': 'draft', 'type': 'agentMessage', 'phase': 'commentary', 'text': '{"draft":true}'}}},
        {'method': 'item/completed', 'params': {'threadId': 'another-thread',
            'item': {'type': 'agentMessage', 'text': 'wrong'}}},
        {'method': 'item/started', 'params': {'threadId': 'thread-1',
            'item': {'type': 'agentMessage', 'text': 'duplicate'}}},
        {'method': 'item/completed', 'params': {'threadId': 'thread-1',
            'item': {'id': 'final', 'type': 'agentMessage', 'phase': 'final_answer', 'text': '{"ok":true}'}}},
        {'method': 'item/completed', 'params': {'threadId': 'thread-1',
            'item': {'id': 'final', 'type': 'agentMessage', 'phase': 'final_answer', 'text': '{"ok":true}'}}},
        {'method': 'thread/tokenUsage/updated', 'params': {'threadId': 'thread-1',
            'tokenUsage': {'total': {'inputTokens': 10, 'outputTokens': 4,
                'cachedInputTokens': 3, 'reasoningOutputTokens': 2, 'totalTokens': 14}}}},
        {'method': 'turn/completed', 'params': {'threadId': 'thread-1', 'turn': {'status': 'completed'}}},
    ]
    provider = CodexProvider()
    schema = {'type': 'object', 'properties': {'ok': {'type': 'boolean'}}, 'required': ['ok'], 'additionalProperties': False}
    text = await provider.chat_complete([{'role': 'user', 'content': 'hi'}],
        tool_schema={'name': 'test', 'parameters': schema})
    assert json.loads(text) == {'ok': True}
    start = next(p for m, p in clean_state.calls if m == 'thread/start')
    turn = next(p for m, p in clean_state.calls if m == 'turn/start')
    assert start['model'] == 'gpt-6.1-sol'
    assert start['allowProviderModelFallback'] is False
    assert start['experimentalRawEvents'] is True
    assert start['config']['features.code_mode_host'] is False
    assert start['config']['features.memories'] is False
    assert turn['outputSchema'] == schema
    assert turn['input'][0]['type'] == 'text'
    assert start['permissions'] == 'bigbrain-inference'
    assert start['config']['default_permissions'] == start['permissions']
    assert start['config']['permissions.bigbrain-inference']['filesystem'][':root'] == 'deny'
    from bigbrain.llm.usage import get_tracker
    assert get_tracker().totals()['total_tokens'] == 14


@pytest.mark.asyncio
@pytest.mark.parametrize('notification', [
    {'method': 'turn/completed', 'params': {'turn': {'status': 'failed', 'error': {'message': 'denied'}}}},
    {'method': 'item/started', 'params': {'item': {'type': 'commandExecution'}}},
    {'method': 'rawResponseItem/completed', 'params': {'item': {'type': 'custom_tool_call', 'name': 'exec'}}},
])
async def test_failed_or_autonomous_turn_is_not_success(clean_state, notification):
    clean_state.notifications = [notification]
    with pytest.raises(RuntimeError):
        await CodexProvider().run_turn([{'role': 'user', 'content': 'hi'}])
    assert sum(method == 'turn/start' for method, _ in clean_state.calls) == 1
    assert any(method == 'turn/interrupt' for method, _ in clean_state.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize('kind,name', [
    ('custom_tool_call', 'exec'), ('function_call', 'shell'),
    ('local_shell_call', None), ('web_search_call', None),
])
async def test_native_boundary_preserves_diagnostic_and_ignores_later_answer(clean_state, kind, name):
    clean_state.notifications = [
        {'method': 'rawResponseItem/completed', 'params': {
            'item': {'type': kind, 'name': name, 'input': 'private native arguments'}}},
        {'method': 'item/completed', 'params': {'item': {
            'type': 'agentMessage', 'phase': 'final_answer', 'text': '{"ok":true}'}}},
        {'method': 'turn/completed', 'params': {'turn': {'status': 'completed'}}},
    ]
    with pytest.raises(CodexNativeToolAttempt) as caught:
        await CodexProvider().run_turn([{'role': 'user', 'content': 'Return a decision'}])
    assert caught.value.item_type == kind
    assert caught.value.tool_name == name
    assert 'private native arguments' not in str(caught.value)
    assert sum(method == 'turn/start' for method, _ in clean_state.calls) == 1
    assert any(method == 'turn/interrupt' for method, _ in clean_state.calls)


@pytest.mark.asyncio
async def test_resumed_thread_preserves_identity_and_leaves_raw_visibility_unverified(clean_state):
    original = clean_state.call
    async def resume(method, params=None):
        if method == 'thread/resume':
            clean_state.calls.append((method, params))
            return {'thread': {'id':'existing-native-thread'}}
        return await original(method, params)
    clean_state.call = resume
    provider = CodexProvider()
    state = {'thread_id':'existing-native-thread', '_save':lambda:None}
    thread = await provider._open_thread(clean_state, provider.default_model, '', None, state)
    assert thread == 'existing-native-thread'
    assert thread not in provider._raw_event_threads
    assert not any(method == 'thread/start' for method, _ in clean_state.calls)


@pytest.mark.asyncio
async def test_bridge_receives_one_proposal_and_interrupts_before_runtime_execution(clean_state):
    clean_state.notifications = [
        {'method': 'rawResponseItem/completed', 'params': {'item': {'type': 'custom_tool_call', 'name': 'exec'}}},
        {'method': 'item/started', 'params': {'item': {'type': 'dynamicToolCall', 'tool': 'bigbrain_submit_decision'}}},
        {'id': 100, 'method': 'item/tool/call', 'params': {'threadId': 'thread-1', 'turnId': 'turn-1',
            'callId': 'proposal-1', 'tool': 'bigbrain_submit_decision',
            'arguments': {'decision_json': '{"ok":true}'}}},
    ]
    schema = {'type': 'object', 'properties': {'ok': {'type': 'boolean'}}, 'required': ['ok'], 'additionalProperties': False}
    answer = await CodexProvider().chat_complete([{'role': 'user', 'content': 'Propose'}],
        native_action_bridge=True, tool_schema={'parameters': schema})
    assert json.loads(answer) == {'ok': True}
    assert clean_state.responses[0][1]['success'] is True
    assert any(method == 'turn/interrupt' for method, _ in clean_state.calls)
    start = next(params for method, params in clean_state.calls if method == 'thread/start')
    assert start['dynamicTools'][0]['name'] == 'bigbrain_submit_decision'
    assert start['config']['mcp_servers.inherited.enabled'] is False
    assert start['config']['features.shell_tool'] is False
    turn = next(params for method, params in clean_state.calls if method == 'turn/start')
    assert 'outputSchema' not in turn
    assert not clean_state._request_handlers


@pytest.mark.asyncio
@pytest.mark.parametrize('arguments,tool', [
    ({'decision_json': 'invalid'}, 'bigbrain_submit_decision'),
    ({'decision_json': '[]'}, 'bigbrain_submit_decision'),
    ({'decision_json': '{}', 'extra': True}, 'bigbrain_submit_decision'),
    ({'decision_json': '{}'}, 'shell'),
])
async def test_bridge_rejects_invalid_or_unexpected_submissions(clean_state, arguments, tool):
    clean_state.notifications = [{'id': 100, 'method': 'item/tool/call', 'params': {
        'threadId': 'thread-1', 'turnId': 'turn-1', 'callId': 'one', 'tool': tool, 'arguments': arguments}}]
    with pytest.raises(CodexUnavailable):
        await CodexProvider().run_turn([{'role': 'user', 'content': 'Propose'}],
            output_schema={'type': 'object'}, action_bridge=True)
    assert clean_state.responses[0][1]['success'] is False
    assert any(method == 'turn/interrupt' for method, _ in clean_state.calls)


@pytest.mark.asyncio
async def test_bridge_caps_native_orchestration_calls(clean_state):
    clean_state.notifications = [{'method': 'rawResponseItem/completed', 'params': {
        'item': {'type': 'custom_tool_call', 'name': 'exec'}}}] * 4
    with pytest.raises(CodexNativeToolAttempt):
        await CodexProvider().run_turn([{'role': 'user', 'content': 'Propose'}],
            output_schema={'type': 'object'}, action_bridge=True)
    assert sum(method == 'turn/start' for method, _ in clean_state.calls) == 1


@pytest.mark.asyncio
async def test_bridge_requires_submission_even_with_final_json(clean_state):
    clean_state.notifications = [
        {'method': 'item/completed', 'params': {'item': {'type': 'agentMessage', 'text': '{}'}}},
        {'method': 'turn/completed', 'params': {'turn': {'status': 'completed'}}},
    ]
    with pytest.raises(CodexUnavailable, match='without submitting'):
        await CodexProvider().run_turn([{'role': 'user', 'content': 'Propose'}],
            output_schema={'type': 'object'}, action_bridge=True)


@pytest.mark.asyncio
async def test_bridge_wrong_turn_is_rejected(clean_state):
    clean_state.notifications = [{'id': 100, 'method': 'item/tool/call', 'params': {
        'threadId': 'thread-1', 'turnId': 'stale-turn', 'callId': 'one',
        'tool': 'bigbrain_submit_decision', 'arguments': {'decision_json': '{}'}}}]
    with pytest.raises(CodexUnavailable):
        await CodexProvider().run_turn([{'role': 'user', 'content': 'Propose'}],
            output_schema={'type': 'object'}, action_bridge=True)
    assert clean_state.responses[0][1]['success'] is False


@pytest.mark.asyncio
async def test_research_policy_uses_bridge_and_keeps_action_validation(clean_state):
    from bigbrain.research import Action, ModelPolicy, ModelResponseError, parse_model_contract
    clean_state.notifications = [{'id': 100, 'method': 'item/tool/call', 'params': {
        'threadId': 'thread-1', 'turnId': 'turn-1', 'callId': 'one',
        'tool': 'bigbrain_submit_decision', 'arguments': {'decision_json':
            '{"tool":"search","question_id":"q1","rationale":"Find primary source","query":"official Git stash"}'}}}]
    raw = await ModelPolicy(CodexProvider()).complete('Choose research action', 1000,
        {'tokens': 120000}, contract=Action)
    assert parse_model_contract(Action, raw).query == 'official Git stash'
    assert any('dynamicTools' in params for method, params in clean_state.calls if method == 'thread/start')
    with pytest.raises(ModelResponseError):
        parse_model_contract(Action, '{"tool":"search","question_id":"q1","rationale":"Empty query"}')


@pytest.mark.asyncio
async def test_reader_dispatches_server_requests_and_denies_unhandled_operations():
    from types import SimpleNamespace
    stream = asyncio.StreamReader(limit=RPC_FRAME_LIMIT)
    writes = []
    client = CodexJsonRpcClient(SimpleNamespace(stdout=stream,
        stdin=SimpleNamespace(write=writes.append)))
    client.on_request(lambda frame: frame.get('method') == 'owned')
    stream.feed_data(b'{"id":7,"method":"owned","params":{}}\n')
    stream.feed_data(b'{"id":8,"method":"unhandled","params":{}}\n')
    stream.feed_eof()
    await client._read_loop()
    assert len(writes) == 1
    assert json.loads(writes[0])['id'] == 8
    assert json.loads(writes[0])['error']['code'] == -32601


@pytest.mark.asyncio
async def test_bridge_reuses_versioned_conversation_after_provider_restart(clean_state):
    clean_state.account_result = {'account': {'type': 'chatgpt', 'email': 'bridge@example.test'}}
    clean_state.notifications = [{'id': 100, 'method': 'item/tool/call', 'params': {
        'threadId': 'thread-1', 'turnId': 'turn-1', 'callId': 'one',
        'tool': 'bigbrain_submit_decision', 'arguments': {'decision_json': '{"ok":true}'}}}]
    original = clean_state.call
    async def call(method, params=None):
        if method == 'thread/resume':
            clean_state.calls.append((method, params))
            return {'thread': {'id': params['threadId']}}
        return await original(method, params)
    clean_state.call = call
    schema = {'type': 'object', 'properties': {'ok': {'type': 'boolean'}},
        'required': ['ok'], 'additionalProperties': False}
    for _ in range(2):
        await CodexProvider().chat_complete([{'role': 'user', 'content': 'Propose'}],
            conversation_id='bridge-restart', conversation_role='research',
            native_action_bridge=True, tool_schema={'parameters': schema})
    starts = [params for method, params in clean_state.calls if method == 'thread/start']
    resumes = [params for method, params in clean_state.calls if method == 'thread/resume']
    assert len(starts) == len(resumes) == 1
    assert resumes[0]['threadId'] == 'thread-1'
    assert 'dynamicTools' not in resumes[0]


@pytest.mark.asyncio
async def test_bridge_buffers_request_until_turn_start_response(clean_state):
    original = clean_state.call
    async def call(method, params=None):
        if method == 'turn/start':
            clean_state.calls.append((method, params))
            clean_state._emit({'id': 100, 'method': 'item/tool/call', 'params': {
                'threadId': 'thread-1', 'turnId': 'turn-1', 'callId': 'one',
                'tool': 'bigbrain_submit_decision', 'arguments': {'decision_json': '{}'}}})
            return {'turn': {'id': 'turn-1'}}
        return await original(method, params)
    clean_state.call = call
    answer, _ = await CodexProvider().run_turn([{'role': 'user', 'content': 'Propose'}],
        output_schema={'type': 'object'}, action_bridge=True)
    assert answer == '{}'
    assert clean_state.responses[0][1]['success'] is True


@pytest.mark.asyncio
async def test_bridge_ignores_previous_turn_completion(clean_state):
    clean_state.notifications = [
        {'method': 'turn/completed', 'params': {'threadId': 'thread-1',
            'turn': {'id': 'previous-turn', 'status': 'completed'}}},
        {'id': 100, 'method': 'item/tool/call', 'params': {
            'threadId': 'thread-1', 'turnId': 'turn-1', 'callId': 'one',
            'tool': 'bigbrain_submit_decision', 'arguments': {'decision_json': '{}'}}},
    ]
    answer, _ = await CodexProvider().run_turn([{'role': 'user', 'content': 'Propose'}],
        output_schema={'type': 'object'}, action_bridge=True)
    assert answer == '{}'
    assert clean_state.responses[0][1]['success'] is True


@pytest.mark.asyncio
async def test_cancel_interrupts_owned_turn(clean_state):
    task = asyncio.create_task(CodexProvider().run_turn([{'role': 'user', 'content': 'hi'}]))
    while not any(m == 'turn/start' for m, _ in clean_state.calls):
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert ('turn/interrupt', {'threadId': 'thread-1', 'turnId': 'turn-1'}) in clean_state.calls


@pytest.mark.asyncio
async def test_optional_action_fields_round_trip(clean_state):
    import copy
    import json
    from bigbrain.maintenance import action_schema
    from bigbrain.llm.codex_provider import _strict_schema
    schema = action_schema()['parameters']
    original = copy.deepcopy(schema)
    strict = _strict_schema(schema)
    action = {key: None for key in schema['properties']['action']['properties']}
    action['type'] = 'state_read'
    clean_state.notifications = [
        {'method': 'item/completed', 'params': {'item': {'type': 'agentMessage',
            'text': json.dumps({'action': action, 'notebook': 'inspect'})}}},
        {'method': 'turn/completed', 'params': {'turn': {'status': 'completed'}}},
    ]
    result = await CodexProvider().chat_complete([{'role': 'user', 'content': 'inspect'}],
        tool_schema=action_schema())
    assert json.loads(result) == {'action': {'type': 'state_read'}, 'notebook': 'inspect'}
    assert schema == original
    encoded = strict['properties']['action']
    assert set(encoded['required']) == set(encoded['properties'])
    assert encoded['properties']['count']['anyOf'][0]['maximum'] == 200
    assert encoded['properties']['type']['enum'] == original['properties']['action']['properties']['type']['enum']


def test_strict_schema_preserves_required_null_and_rejects_open_objects():
    from bigbrain.llm.codex_provider import _strict_schema, _restore_optional_fields
    schema = {'type': 'object', 'properties': {'value': {'type': ['string', 'null']},
        'optional': {'type': 'string'}}, 'required': ['value'], 'additionalProperties': False}
    assert _restore_optional_fields({'value': None, 'optional': None}, schema) == {'value': None}
    assert _strict_schema(schema)['properties']['value'] == schema['properties']['value']
    with pytest.raises(ValueError, match='closed object'):
        _strict_schema({'type': 'object', 'additionalProperties': True})
