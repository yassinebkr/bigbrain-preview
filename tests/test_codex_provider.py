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
from bigbrain.llm.codex_provider import CodexJsonRpcClient, CodexUnavailable, RPC_FRAME_LIMIT


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


class FakeRpc:
    """Scripted JSON-RPC client mimicking the codex app-server."""

    def __init__(self):
        self.calls = []
        self.notifications = []  # queued server notifications to replay
        self._listeners = []

    async def call(self, method, params=None):
        self.calls.append((method, params or {}))
        if method == "initialize":
            return {"ok": True}
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
            return {"ok": True}
        raise RuntimeError(f"unexpected method {method}")

    def notify(self, method, params=None):
        pass

    def on_notification(self, listener):
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def _emit(self, message):
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
        {'method': 'item/completed', 'params': {'threadId': 'another-thread',
            'item': {'type': 'agentMessage', 'text': 'wrong'}}},
        {'method': 'item/started', 'params': {'threadId': 'thread-1',
            'item': {'type': 'agentMessage', 'text': 'duplicate'}}},
        {'method': 'item/completed', 'params': {'threadId': 'thread-1',
            'item': {'type': 'agentMessage', 'text': '{"ok":true}'}}},
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
])
async def test_failed_or_autonomous_turn_is_not_success(clean_state, notification):
    clean_state.notifications = [notification]
    with pytest.raises(RuntimeError):
        await CodexProvider().run_turn([{'role': 'user', 'content': 'hi'}])


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
