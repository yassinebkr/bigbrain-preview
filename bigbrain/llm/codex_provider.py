"""Codex provider — ChatGPT subscription access via ``codex app-server``.

Python port of shopifast-local's ``canvas/server/llm/codexProvider.mjs``
(protocol verified live there against codex-cli 0.153.4 on 2026-09-08):
spawns ``codex app-server`` and speaks newline-delimited JSON-RPC over
stdio. ``initialize`` → ``initialized`` → ``account/read``, ``thread/start``,
``turn/start``, ``turn/interrupt``, ``account/login/start`` all answered;
notifications include item/agentMessage, item/delta and turn/completed.

Connect-with-ChatGPT flow: ``codex_start_login()`` → the app-server returns
an ``authUrl`` the browser must open; codex itself owns the OAuth callback,
token exchange and credential storage in ``~/.codex``; completion is
observed by polling ``codex_auth_status()``.

Runtime uses one ephemeral App Server thread per visible request
(the shopifast "Runtime v2" discipline): BigBrain owns the durable
conversation, so old raw tool payloads are never re-sent — and therefore
never re-charged — on every inference.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from typing import Any, Callable, Optional

from .model_registry import get_model
from .provider import LLMProvider
from .usage import UsageRecord, get_tracker

CODEX_MODEL_KEY = "codex-chatgpt"

# Inactivity timeout (not total duration) so a healthy multi-tool turn can
# finish normally. Mirrors the shopifast provider's 120s inactivity cap.
_TURN_INACTIVE_TIMEOUT_S = 120


class CodexUnavailable(RuntimeError):
    """The codex CLI is not installed or the app-server failed to start."""


class CodexJsonRpcClient:
    """Newline-delimited JSON-RPC 2.0 over the app-server's stdio."""

    def __init__(self, process: asyncio.subprocess.Process):
        self.proc = process
        self._next_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._listeners: list[Callable[[dict], None]] = []
        self._reader_task: Optional[asyncio.Task] = None
        self._closed = False

    @classmethod
    async def start(cls) -> "CodexJsonRpcClient":
        if shutil.which("codex") is None:
            raise CodexUnavailable(
                "codex CLI not found on PATH — install codex-cli to use the "
                "ChatGPT subscription provider"
            )
        process = await asyncio.create_subprocess_exec(
            "codex", "app-server",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        client = cls(process)
        client._reader_task = asyncio.create_task(client._read_loop())
        return client

    async def _read_loop(self) -> None:
        assert self.proc.stdout is not None
        try:
            while True:
                line = await self.proc.stdout.readline()
                if not line:
                    break
                try:
                    message = json.loads(line)
                except ValueError:
                    continue  # non-JSON noise on stdout: ignore
                if message.get("id") is not None and (
                    "result" in message or "error" in message
                ):
                    future = self._pending.pop(message["id"], None)
                    if future and not future.done():
                        if "error" in message:
                            future.set_exception(
                                RuntimeError(str(message["error"].get("message")))
                            )
                        else:
                            future.set_result(message["result"])
                elif message.get("method"):
                    for listener in list(self._listeners):
                        listener(message)
        finally:
            self._closed = True
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(CodexUnavailable("app-server exited"))

    async def call(self, method: str, params: dict | None = None) -> Any:
        if self._closed:
            raise CodexUnavailable("app-server has exited")
        self._next_id += 1
        request_id = self._next_id
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[request_id] = future
        assert self.proc.stdin is not None
        self.proc.stdin.write(
            (json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method,
                         "params": params or {}}) + "\n").encode()
        )
        await self.proc.stdin.drain()
        return await future

    def notify(self, method: str, params: dict | None = None) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(
            (json.dumps({"jsonrpc": "2.0", "method": method,
                         "params": params or {}}) + "\n").encode()
        )

    def on_notification(self, listener: Callable[[dict], None]) -> Callable[[], None]:
        self._listeners.append(listener)
        def off() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)
        return off

    def kill(self) -> None:
        if self.proc.returncode is None:
            self.proc.kill()


# -- process-wide app-server session ---------------------------------------------

_session: Optional[asyncio.Task] = None
_initialized_client: Optional[CodexJsonRpcClient] = None
# Test hook: inject a fake JSON-RPC client so unit tests can exercise the
# chat path without spawning codex or burning a real ChatGPT account.
_rpc_override: Optional[CodexJsonRpcClient] = None


def _set_rpc_for_test(client: CodexJsonRpcClient | None) -> None:
    global _rpc_override, _session, _initialized_client
    _rpc_override = client
    _initialized_client = None


async def close_codex_app_server() -> None:
    """Stop the one app-server child owned by this process (shutdown/tests)."""
    global _session, _initialized_client
    task, _session = _session, None
    _initialized_client = None
    if task is not None:
        client = await asyncio.gather(task, return_exceptions=True)
        for value in client:
            if isinstance(value, CodexJsonRpcClient):
                value.kill()


async def _initialize(client: CodexJsonRpcClient) -> CodexJsonRpcClient:
    global _initialized_client
    if _initialized_client is client:
        return client
    await client.call(
        "initialize",
        {"clientInfo": {"name": "bigbrain", "version": "0.1.0"},
         "capabilities": {}},
    )
    client.notify("initialized")
    _initialized_client = client
    return client


async def _get_session() -> CodexJsonRpcClient:
    global _session
    if _rpc_override is not None:
        return await _initialize(_rpc_override)
    if _session is not None:
        return await _session
    task = asyncio.get_event_loop().create_task(CodexJsonRpcClient.start())
    _session = task
    try:
        client = await task
    except Exception:
        _session = None
        raise
    # Respawn on next use if the child exits.
    def _on_exit(_future) -> None:
        global _session, _initialized_client
        _session = None
        _initialized_client = None
    task.add_done_callback(_on_exit)
    return await _initialize(client)


# -- auth (the "Connect with ChatGPT" button pipeline) ---------------------------

async def codex_auth_status() -> dict:
    """Who is signed in right now (settings sheet + connect polling)."""
    try:
        client = await _get_session()
        result = await client.call("account/read", {})
        account = result.get("account") if isinstance(result, dict) else None
        if not account:
            return {"authenticated": False}
        return {
            "authenticated": True,
            "email": account.get("email"),
            "planType": account.get("planType"),
            "type": account.get("type"),
        }
    except Exception as exc:
        return {"authenticated": False, "error": str(exc)}


async def codex_start_login(open_browser: bool = True) -> dict:
    """Begin the ChatGPT OAuth flow; returns the URL the browser must open.

    codex itself owns the callback, token exchange and credential storage
    in ``~/.codex``; the UI polls ``codex_auth_status()`` until the account
    appears.
    """
    client = await _get_session()
    result = await client.call("account/login/start", {"type": "chatgpt"})
    if not isinstance(result, dict) or not result.get("authUrl"):
        raise RuntimeError(f"unexpected login/start response: {result!r}")
    if open_browser:
        import webbrowser
        webbrowser.open(result["authUrl"])
    return {"authUrl": result["authUrl"], "loginId": result.get("loginId")}


# -- LLM provider ----------------------------------------------------------------

class CodexProvider(LLMProvider):
    """LLMProvider backed by the codex app-server (ChatGPT subscription)."""

    def __init__(self, registry_key: str = CODEX_MODEL_KEY):
        self.entry = get_model(registry_key)
        self.default_model = self.entry.model_id

    async def complete(
        self,
        prompt: str,
        model: str = "default",
        stream: bool = False,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs,
    ):
        messages = [{"role": "user", "content": prompt}]
        return await self.chat_complete(
            messages, model=model, stream=stream, max_tokens=max_tokens,
            temperature=temperature, **kwargs,
        )

    async def chat_complete(
        self,
        messages: list[dict],
        model: str = "default",
        stream: bool = False,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs,
    ):
        text, usage = await self.run_turn(messages, model=model)
        if usage:
            get_tracker().record(usage)
        return text

    async def run_turn(
        self, messages: list[dict], model: str = "default",
        instructions: str = "", cwd: str | None = None,
    ) -> tuple[str, Optional[UsageRecord]]:
        """One ephemeral thread per visible request (shopifast Runtime v2).

        Returns (text, usage). The ephemeral thread is abandoned after the
        turn: BigBrain keeps the durable conversation, so old raw payloads
        are never re-sent on the next inference.
        """
        client = await _get_session()
        model_id = model if model and model != "default" else self.default_model
        thread_result = await client.call(
            "thread/start",
            {
                "cwd": cwd or os.getcwd(),
                "model": model_id,
                "ephemeral": True,
                "threadSource": "bigbrain",
                "approvalPolicy": "never",
                "sandbox": "read-only",
            },
        )
        thread_id = (thread_result or {}).get("thread", {}).get("id")
        if not thread_id:
            raise RuntimeError(f"thread/start returned no thread id: {thread_result!r}")

        turn_future: asyncio.Future = asyncio.get_event_loop().create_future()
        reply: list[str] = []
        usage_holder: dict[str, dict] = {}

        def _on_notification(message: dict) -> None:
            params = message.get("params") or {}
            method = message.get("method", "")
            item = params.get("item") or {}
            if method == "item/agentMessage" or item.get("type") == "agentMessage":
                text = item.get("text") or params.get("text") or ""
                if text:
                    reply.append(text)
            # Usage may ride on any notification (item/completed,
            # turn/completed): always extract it, never elif past it.
            usage = params.get("usage") or item.get("usage")
            if usage:
                usage_holder["usage"] = usage
            if method == "turn/completed" or item.get("type") == "turn/completed":
                if not turn_future.done():
                    turn_future.set_result(None)

        off = client.on_notification(_on_notification)
        try:
            await client.call(
                "turn/start",
                {
                    "threadId": thread_id,
                    # The conversation flattened to one visible turn: the
                    # durable history lives in BigBrain, not in codex.
                    "input": [{"type": "message", "role": "user",
                               "content": [{"type": "input_text",
                                            "text": _flatten(messages)}]}],
                    "effort": "low",
                },
            )
            try:
                await asyncio.wait_for(turn_future, timeout=_TURN_INACTIVE_TIMEOUT_S)
            except asyncio.TimeoutError as exc:
                await client.call("turn/interrupt", {"threadId": thread_id})
                raise RuntimeError("codex turn inactive for 120s") from exc
        finally:
            off()

        usage_record = None
        if usage_holder.get("usage"):
            usage_record = UsageRecord.from_openai_usage(
                usage_holder["usage"], model_id=model_id, provider="codex"
            )
        return "".join(reply) or "(no agent text returned)", usage_record

    def get_available_models(self) -> list[str]:
        return [self.default_model]

    def estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)


def _flatten(messages: list[dict]) -> str:
    """Flatten a chat transcript to the turn input format (one request,
    one codex turn — the durable history stays in BigBrain)."""
    return "\n\n".join(
        f"{m.get('role', 'user').upper()}: {m.get('content', '')}" for m in messages
    )
