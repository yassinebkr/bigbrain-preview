"""Tests for the codex provider (Phase 4a).

Uses the provider's test hook (_set_rpc_for_test) — no codex spawn, no
real ChatGPT account, no paid calls. Mirrors shopifast's provider tests.
"""

import asyncio

import pytest

from bigbrain.llm.codex_provider import (
    CodexProvider,
    _set_rpc_for_test,
    codex_auth_status,
    codex_start_login,
)
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
            return {"ok": True}
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
