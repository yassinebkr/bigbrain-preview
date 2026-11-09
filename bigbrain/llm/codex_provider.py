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

Scoped calls reuse a durable thread per conversation/account/agent. BigBrain
sends unseen message suffixes and resumes the thread after restart. Native
history still contributes to model input; reuse is not a cost-free-context
guarantee. Unidentified callers stay ephemeral to avoid cross-user leakage.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from typing import Any, Callable, Optional

from .model_registry import get_model
from .provider import LLMProvider
from .usage import UsageRecord, get_tracker
from .conversation import current_conversation
from .codex_sessions import CodexSessions, digest, incremental_messages

CODEX_MODEL_KEY = "codex-chatgpt"
RPC_FRAME_LIMIT = 8 * 1024 * 1024  # source-bearing native notifications exceed asyncio's 64 KiB default

class CodexUnavailable(RuntimeError):
    """The codex CLI is not installed or the app-server failed to start."""


class CodexNativeToolAttempt(CodexUnavailable):
    """A native agent action interrupted a BigBrain inference turn."""

    def __init__(self, item_type: str, tool_name: str | None = None):
        self.item_type = item_type
        self.tool_name = tool_name
        super().__init__(
            "L’intégration Codex a tenté un outil natif pendant la décision. "
            "Le tour a été interrompu ; la recherche reste incomplète. "
            "La configuration actuelle ne garantit pas une inférence sans outils."
        )


class CodexJsonRpcClient:
    """Newline-delimited JSON-RPC 2.0 over the app-server's stdio."""

    def __init__(self, process: asyncio.subprocess.Process):
        self.proc = process
        self._next_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._listeners: list[Callable[[dict], None]] = []
        self._request_handlers: list[Callable[[dict], bool]] = []
        self._reader_task: Optional[asyncio.Task] = None
        self._closed = False

    @classmethod
    async def start(cls) -> "CodexJsonRpcClient":
        executable = os.environ.get("BIGBRAIN_CODEX_BINARY") or shutil.which("codex")
        if not executable:
            raise CodexUnavailable(
                "codex CLI not found on PATH — install codex-cli to use the "
                "ChatGPT subscription provider"
            )
        process = await asyncio.create_subprocess_exec(
            executable, "app-server",
            "-c", "features.code_mode_host=true",
            "-c", "features.memories=false",
            "-c", "features.shell_tool=false",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            limit=RPC_FRAME_LIMIT,
        )
        client = cls(process)
        client._reader_task = asyncio.create_task(client._read_loop())
        return client

    async def _read_loop(self) -> None:
        assert self.proc.stdout is not None
        failure = 'app-server closed its output'
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
                elif message.get("method") and message.get("id") is not None:
                    if not any(handler(message) for handler in list(self._request_handlers)):
                        self.respond(message['id'], error={'code': -32601, 'message': 'Client operation unavailable'})
                elif message.get("method"):
                    for listener in list(self._listeners):
                        listener(message)
        except Exception as exc:
            failure = 'app-server transport failed: ' + type(exc).__name__
        finally:
            self._closed = True
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(CodexUnavailable(failure))
            # A turn can be awaiting completion after turn/start has already
            # replied: it is then absent from _pending and still needs waking.
            for listener in list(self._listeners):
                try:
                    listener({'method': 'bigbrain/transport/error', 'params': {'reason': failure}})
                except Exception:
                    pass

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

    def respond(self, request_id, result=None, error=None):
        """Resolve an app-server request without executing arbitrary client code."""
        frame = {'id': request_id, **({'error': error} if error else {'result': result})}
        self.proc.stdin.write((json.dumps(frame) + '\n').encode())

    def on_request(self, handler):
        self._request_handlers.append(handler)
        return lambda: self._request_handlers.remove(handler)

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
                if value._reader_task:
                    value._reader_task.cancel()
                    await asyncio.gather(value._reader_task, return_exceptions=True)
                async def drain():
                    if value.proc.stdout:
                        while await value.proc.stdout.read(65536):
                            pass
                # wait() alone may hang when a failed reader left the pipe full.
                await asyncio.wait_for(asyncio.gather(value.proc.wait(), drain()), timeout=5)


async def _initialize(client: CodexJsonRpcClient) -> CodexJsonRpcClient:
    global _initialized_client
    if _initialized_client is client:
        return client
    await client.call(
        "initialize",
        {"clientInfo": {"name": "bigbrain", "version": "0.1.0"},
         "capabilities": {"experimentalApi": True}},
    )
    client.notify("initialized")
    _initialized_client = client
    return client


async def _get_session() -> CodexJsonRpcClient:
    global _session
    if _rpc_override is not None:
        return await _initialize(_rpc_override)
    if _session is not None:
        pending = _session
        try:
            client = await asyncio.shield(pending)
        except Exception:
            if _session is pending:
                _session = None
            raise
        if not client._closed:
            return client
        _session = None
    async def start_initialized():
        client = await CodexJsonRpcClient.start()
        try:
            return await asyncio.wait_for(_initialize(client), timeout=15)
        except BaseException:
            client.kill()
            raise
    task = asyncio.get_event_loop().create_task(start_initialized())
    _session = task
    try:
        client = await asyncio.shield(task)
    except Exception:
        _session = None
        raise
    return client


# -- auth (the "Connect with ChatGPT" button pipeline) ---------------------------

async def codex_auth_status() -> dict:
    """Who is signed in right now (settings sheet + connect polling)."""
    try:
        client = await _get_session()
        result = await asyncio.wait_for(client.call("account/read", {}), timeout=10)
        account = result.get("account") if isinstance(result, dict) else None
        if not account:
            return {"authenticated": False}
        return {
            "authenticated": True,
            "email": account.get("email"),
            "planType": account.get("planType"),
            "type": account.get("type"),
        }
    except asyncio.TimeoutError:
        return {"authenticated": False, "error": "Codex authentication status timed out"}
    except Exception as exc:
        return {"authenticated": False, "error": str(exc)}


async def codex_start_login(open_browser: bool = True) -> dict:
    """Begin the ChatGPT OAuth flow; returns the URL the browser must open.

    codex itself owns the callback, token exchange and credential storage
    in ``~/.codex``; the UI polls ``codex_auth_status()`` until the account
    appears.
    """
    client = await _get_session()
    result = await asyncio.wait_for(client.call("account/login/start", {"type": "chatgpt"}), timeout=15)
    if not isinstance(result, dict) or not result.get("authUrl"):
        raise RuntimeError(f"unexpected login/start response: {result!r}")
    if open_browser:
        import webbrowser
        webbrowser.open(result["authUrl"])
    return {"authUrl": result["authUrl"], "loginId": result.get("loginId")}


# -- LLM provider ----------------------------------------------------------------

class CodexProvider(LLMProvider):
    """LLMProvider backed by the codex app-server (ChatGPT subscription)."""

    maintenance_event_context = True
    review_event_context = True
    retains_conversation_context = True
    # The approved subscription policy monitors cumulative usage after each
    # turn. An in-flight turn may exceed the forecast; further turns then stop.
    supports_bounded_research_context = False
    research_budget_policy = "monitored"
    supports_research_action_bridge = True

    def __init__(self, registry_key: str = CODEX_MODEL_KEY):
        self.registry_key = registry_key
        self.entry = get_model(registry_key)
        self.default_model = self.entry.model_id
        self.reasoning_effort = self.entry.reasoning_effort_default or os.environ.get("BIGBRAIN_CODEX_EFFORT", "low")
        # The caller's task budget and explicit Stop remain authoritative.
        self.reasoning_timeout_seconds = None
        self._inference_directory = tempfile.TemporaryDirectory(prefix="bigbrain-codex-inference-")
        self._conversations = CodexSessions()
        self._loaded_threads = {}
        self._raw_event_threads = set()
        self.last_context_tokens = None
        self.auto_compact_tokens = int(os.environ.get('BIGBRAIN_CODEX_AUTO_COMPACT_TOKENS', '128000'))
        if self.auto_compact_tokens < 1024:
            raise ValueError('Codex automatic compaction threshold must be at least 1024 tokens')

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
        schema = None
        if kwargs.get("tool_schema"):
            schema = kwargs["tool_schema"]["parameters"]
        elif (kwargs.get("response_format") or {}).get("type") == "json_schema":
            schema = kwargs["response_format"]["json_schema"]["schema"]
        scope = current_conversation.get()
        if kwargs.get('conversation_id'):
            scope = (kwargs['conversation_id'], kwargs.get('conversation_role', 'front'))
        encoded_schema = _strict_schema(schema) if schema else None
        bridge = bool(kwargs.get('native_action_bridge') and schema)
        if bridge and scope:
            scope = (scope[0], scope[1] + '-actions-v1')
        if scope:
            text, usage = await self._scoped_turn(messages, model, encoded_schema, scope, schema,
                                                 kwargs.get('context_checkpoint'), bridge)
        else:
            # Unidentified callers must not share a global anonymous history.
            text, usage = await self.run_turn(messages, model=model, output_schema=encoded_schema, action_bridge=bridge)
        if usage:
            get_tracker().record(usage)
        if schema:
            text = json.dumps(_restore_optional_fields(json.loads(text), schema), ensure_ascii=False)
        return text

    async def _binding(self, scope):
        client = await _get_session()
        account = await client.call('account/read', {})
        if (account.get('account') or {}).get('type') != 'chatgpt':
            raise CodexUnavailable('A signed-in ChatGPT account is required; no API fallback')
        identity = (account.get('workspaceRouting') or {}).get('chatgptAccountId') or account['account'].get('email')
        if not identity:
            raise CodexUnavailable('Cannot establish account identity for conversation isolation')
        path, lock = self._conversations.binding(*scope, digest(identity))
        return client, path, lock

    async def _scoped_turn(self, messages, model, encoded_schema, scope, original_schema, checkpoint=None, bridge=False):
        client, path, lock = await self._binding(scope)
        async with lock:
            # Reload under the shared lock, including when another provider
            # instance owns the same conversation.
            self._conversations.loaded.pop(path, None)
            state = self._conversations.load(path)
            state['_save'] = lambda: self._conversations.save(path, state, scope[0])
            delta, hashes = incremental_messages(messages, state)
            compactions = state.get('compactions', 0)
            checkpoint_due = checkpoint is not None and compactions > state.get('checkpoint_compactions', 0)
            if checkpoint_due:
                delta.insert(0, {'role': 'user', 'content': json.dumps({
                    'authoritative_checkpoint': checkpoint,
                    'instruction': 'Current runtime facts supersede stale historical observations.'}, ensure_ascii=False)})
            state['_pending_hashes'] = hashes
            text, usage = await self.run_turn(delta, model=model, output_schema=encoded_schema,
                                             _state=state, action_bridge=bridge)
            try:
                visible = (json.dumps(_restore_optional_fields(json.loads(text), original_schema), ensure_ascii=False)
                           if original_schema else text)
            except ValueError:
                # Preserve the accepted assistant cursor and let chat_complete
                # record usage BEFORE rejecting malformed structured output.
                visible = text
            state['message_hashes'] = [*hashes['message_hashes'], digest({'role': 'assistant', 'content': visible})][-256:]
            state['last_request'] = {'supplied_messages': len(messages), 'sent_messages': len(delta),
                'supplied_chars': len(_flatten(messages)), 'sent_chars': len(_flatten(delta))}
            if checkpoint_due:
                state['checkpoint_compactions'] = compactions
            self._conversations.check(scope[0])
            state['_save']()
            return text, usage

    async def run_turn(
        self, messages: list[dict], model: str = "default",
        instructions: str = "", cwd: str | None = None,
        output_schema: dict | None = None,
        _state: dict | None = None,
        action_bridge: bool = False,
    ) -> tuple[str, Optional[UsageRecord]]:
        """Run in the bound conversation, or an isolated ephemeral thread.

        Returns visible text and per-turn usage, never a lifetime counter.
        """
        from .call_trace import trace_stage
        trace_stage("codex.session.connecting")
        client = await _get_session()
        model_id = model if model and model != "default" else self.default_model
        trace_stage("codex.thread.opening", automatic_retries=0, attempt=1)
        thread_id = await self._open_thread(client, model_id, instructions, cwd, _state, action_bridge)
        trace_stage("codex.thread.ready", native_thread_id=thread_id,
                    raw_monitoring_requested=thread_id in self._raw_event_threads)
        turn_future: asyncio.Future = asyncio.get_event_loop().create_future()
        reply: dict[str, tuple[str | None, str]] = {}
        usage_holder: dict[str, dict] = {}
        turn_id = None
        completed_ok = False
        proposals = []
        native_calls = 0
        terminal_event = asyncio.Event()
        usage_event = asyncio.Event()
        pending_requests = []

        def on_request(message):
            params = message.get('params') or {}
            if params.get('threadId') != thread_id:
                return False
            if message.get('method') != 'item/tool/call':
                return False
            if turn_id is None:
                pending_requests.append(message)
                return True
            accepted = False
            try:
                if (not action_bridge or params.get('tool') != 'bigbrain_submit_decision'
                        or params.get('namespace') is not None or turn_future.done() or proposals
                        or params.get('turnId') != turn_id):
                    raise ValueError('Unexpected or duplicate decision submission')
                arguments = params.get('arguments')
                if not isinstance(arguments, dict) or set(arguments) != {'decision_json'}:
                    raise ValueError('Invalid decision envelope')
                raw = arguments['decision_json']
                if not isinstance(raw, str) or len(raw.encode()) > 65536 or not isinstance(json.loads(raw), dict):
                    raise ValueError('Invalid decision JSON')
                proposals.append(raw)
                accepted = True
                trace_stage('codex.decision_submitted', native_call_id=params.get('callId'))
            except (ValueError, TypeError):
                if not turn_future.done():
                    turn_future.set_exception(CodexUnavailable('Invalid native decision submission'))
            client.respond(message['id'], result={'success': accepted, 'contentItems': [{
                'type': 'inputText', 'text': 'Proposal received for runtime validation. End this turn; the external runtime owns execution.' if accepted else 'Proposal rejected.'}]})
            if accepted:
                turn_future.set_result(None)
            return True

        def _on_notification(message: dict) -> None:
            nonlocal native_calls
            params = message.get("params") or {}
            if params.get("threadId") not in (None, thread_id):
                return
            method = message.get("method", "")
            if method == 'bigbrain/transport/error':
                if not turn_future.done():
                    turn_future.set_exception(CodexUnavailable(params.get('reason', 'app-server transport failed')))
                return
            item = params.get("item") or {}
            if method == "rawResponseItem/completed":
                trace_stage('codex.raw_item_observed', item_type=item.get('type'))
            if (method == "rawResponseItem/completed" and item.get("type") in {
                    "custom_tool_call", "function_call", "local_shell_call", "web_search_call"}):
                bridge_call = action_bridge and (
                    item.get('type') == 'custom_tool_call' and item.get('name') == 'exec'
                    or item.get('type') == 'function_call' and item.get('name') == 'bigbrain_submit_decision')
                if bridge_call:
                    native_calls += 1
                    trace_stage('codex.bridge_call', item_type=item.get('type'), native_calls=native_calls)
                if bridge_call and native_calls <= 3:
                    return
                if not turn_future.done():
                    trace_stage('codex.native_tool_rejected', item_type=item.get('type'),
                                tool_name=item.get('name'), boundary='raw_response')
                    turn_future.set_exception(CodexNativeToolAttempt(item['type'], item.get('name')))
            if method == "item/agentMessage" or (method == "item/completed" and item.get("type") == "agentMessage"):
                text = item.get("text") or params.get("text") or ""
                if text:
                    phase = item.get('phase')
                    identity = item.get('id') or f'legacy-{len(reply)}'
                    trace_stage('codex.agent_message', message_phase=phase, message_id=identity)
                    # item/completed carries the full item, not a text delta.
                    # Commentary and terminal answers must never become one JSON.
                    previous = reply.get(identity)
                    if method == 'item/agentMessage' and previous:
                        text = previous[1] + text
                    reply[identity] = (phase, text)
            usage = params.get("usage") or item.get("usage")
            if usage:
                usage_holder["usage"] = usage
            if method == "thread/tokenUsage/updated":
                usage_holder['native'] = params['tokenUsage']
                usage_event.set()
                last = params['tokenUsage'].get('last') or {}
                self.last_context_tokens = last.get('inputTokens', 0) + last.get('outputTokens', 0)
                trace_stage('codex.usage_observed', cumulative=params['tokenUsage'].get('total'), last=last)
            if method == 'item/completed' and item.get('type') == 'contextCompaction' and _state is not None:
                _state['compactions'] = _state.get('compactions', 0) + 1
            if method == "item/started" and item.get("type") not in {"userMessage", "agentMessage", "reasoning", "contextCompaction"} and not (action_bridge and item.get('type') == 'dynamicToolCall' and item.get('tool') == 'bigbrain_submit_decision'):
                if not turn_future.done():
                    trace_stage('codex.native_tool_rejected', item_type=item.get('type'),
                                boundary='typed_item')
                    turn_future.set_exception(CodexNativeToolAttempt(item.get('type', 'unknown')))
            if method == "turn/completed" or item.get("type") == "turn/completed":
                completed_id = (params.get('turn') or {}).get('id') or params.get('turnId')
                if completed_id and turn_id and completed_id != turn_id:
                    return
                terminal_event.set()
                if not turn_future.done():
                    turn = params.get("turn") or {}
                    if turn.get("status") in {"failed", "interrupted"}:
                        turn_future.set_exception(RuntimeError(f"Codex turn {turn.get('status')}: {turn.get('error')}"))
                    else:
                        turn_future.set_result(None)

        off = client.on_notification(_on_notification)
        off_requests = client.on_request(on_request) if action_bridge else lambda: None
        try:
            trace_stage("codex.turn.starting", native_thread_id=thread_id)
            started = await client.call("turn/start", {
                "threadId": thread_id, 'model': model_id,
                "input": _native_inputs(messages) + ([{'type': 'text', 'text':
                    'Submit the decision using bigbrain_submit_decision with decision_json containing the JSON object. '
                    'The external runtime validates it and returns observations next turn. Current decision schema: '
                    + json.dumps(output_schema)}] if action_bridge else []),
                "effort": self.reasoning_effort,
                **({"outputSchema": output_schema} if output_schema and not action_bridge else {}),
            })
            turn_id = (started or {}).get("turn", {}).get("id")
            for request in pending_requests:
                on_request(request)
            pending_requests.clear()
            trace_stage("codex.turn.accepted", native_thread_id=thread_id, native_turn_id=turn_id)
            if _state is not None:
                _state.update(_state.get('_pending_hashes', {}))
                _state['_save']()
            await turn_future
            if proposals:
                # Let the accepted submission's bookkeeping arrive before
                # interrupting its enclosing native code-mode cell.
                if not usage_event.is_set():
                    try:
                        await asyncio.wait_for(usage_event.wait(), .2)
                    except TimeoutError:
                        pass
                if not terminal_event.is_set():
                    await asyncio.wait_for(client.call('turn/interrupt', {'threadId': thread_id, 'turnId': turn_id}), 5)
                    await asyncio.wait_for(terminal_event.wait(), 5)
            trace_stage("codex.turn.completed", native_thread_id=thread_id, native_turn_id=turn_id)
            completed_ok = True
        except BaseException:
            if turn_id:
                try:
                    trace_stage("codex.turn.interrupting", native_thread_id=thread_id, native_turn_id=turn_id)
                    await asyncio.wait_for(client.call("turn/interrupt", {
                        "threadId": thread_id, "turnId": turn_id}), timeout=5)
                    trace_stage("codex.turn.interrupted", native_thread_id=thread_id, native_turn_id=turn_id)
                except Exception:
                    pass
            raise
        finally:
            off()
            off_requests()
            if usage_holder.get('native'):
                usage_holder['usage'] = _account_usage(usage_holder['native'], _state)
                if _state is not None:
                    _state['_save']()
            if not completed_ok and usage_holder.get('usage'):
                get_tracker().record(UsageRecord.from_openai_usage(
                    usage_holder['usage'], model_id=model_id, provider='codex'))

        usage_record = None
        if usage_holder.get("usage"):
            usage_record = UsageRecord.from_openai_usage(usage_holder["usage"], model_id=model_id, provider="codex")
        if proposals:
            return proposals[0], usage_record
        if action_bridge:
            if usage_record:
                get_tracker().record(usage_record)
            raise CodexUnavailable('Codex completed without submitting a research decision')
        terminal = [text for phase, text in reply.values() if phase == 'final_answer']
        legacy = [text for phase, text in reply.values() if phase is None]
        selected = terminal or legacy
        if output_schema and len(selected) > 1:
            if usage_record:
                get_tracker().record(usage_record)
            raise ValueError('Multiple assistant answers without one unambiguous terminal structured response')
        if output_schema and not selected:
            if usage_record:
                get_tracker().record(usage_record)
            raise ValueError('No terminal structured response; intermediate messages cannot authorize an action')
        return "".join(selected) or "(no agent text returned)", usage_record

    async def _open_thread(self, client, model_id, instructions, cwd, state, action_bridge=False):
        if state and self._loaded_threads.get(state.get('thread_id')) is client:
            return state['thread_id']
        params = {
                "cwd": cwd or self._inference_directory.name,
                "model": model_id,
                "allowProviderModelFallback": False,
                "ephemeral": state is None,
                "experimentalRawEvents": True,
                "threadSource": "bigbrain",
                "approvalPolicy": "never",
                "permissions": "bigbrain-inference",
                "baseInstructions": "You are the inference component of BigBrain. Return only the requested response. Do not invoke Codex tools: BigBrain alone executes actions. Selecting a structured action in JSON does not require direct tool access: the external runtime executes it after validation. Disabled native tools do not mean the requested external action protocol is unavailable. " + instructions,
                "environments": [],
                "developerInstructions": "Produce the requested BigBrain response using only the supplied messages. BigBrain owns all tool execution and memory access. Return the requested JSON directly as the final answer.",
                "config": {
                    "model_auto_compact_token_limit": self.auto_compact_tokens,
                    # Defining a profile requires a default even when the
                    # thread explicitly selects it. Otherwise Codex reports
                    # the config error as "failed to load workspace requirements".
                    "default_permissions": "bigbrain-inference",
                    "permissions.bigbrain-inference": {
                        "filesystem": {":root": "deny", ":minimal": "read", self._inference_directory.name: "read"},
                        "network": {"enabled": False}},
                    "web_search": "disabled",
                    "features.shell_tool": False,
                    "features.apply_patch_freeform": False,
                    "features.multi_agent_v2": False,
                    "agents.enabled": False,
                    "features.plugins": False,
                    "features.apps": False,
                    "features.code_mode_host": False,
                    "features.memories": False,
                },
            }
        resuming = bool(state and state.get('thread_id'))
        if action_bridge:
            # Disable inherited MCP servers before exposing the code-mode host.
            # Code-mode scripts can then discover only this client-owned bridge
            # and the restricted native surfaces configured on this thread.
            effective = await client.call('config/read', {'includeLayers': False})
            for name in (effective.get('config', {}).get('mcp_servers') or {}):
                params['config'][f'mcp_servers.{name}.enabled'] = False
            params['config']['features.code_mode_host'] = True
            for feature in ('browser_use', 'browser_use_external', 'computer_use',
                            'image_generation', 'sleep_tool', 'tool_suggest'):
                params['config']['features.' + feature] = False
            params['baseInstructions'] = 'You are the BigBrain research decision agent. Use bigbrain_submit_decision to submit exactly one proposed action. BigBrain validates and executes the proposal. ' + instructions
            params['developerInstructions'] = 'Use only the supplied evidence and bigbrain_submit_decision. The external runtime owns search, page acquisition, budgets and validation.'
            params['dynamicTools'] = [{'type': 'function', 'name': 'bigbrain_submit_decision',
                'description': 'Submit one research decision to the external BigBrain runtime for validation.',
                'inputSchema': {'type': 'object', 'properties': {'decision_json': {'type': 'string'}},
                    'required': ['decision_json'], 'additionalProperties': False}}]
        if resuming:
            resume = {k: v for k, v in params.items() if k in {
                'cwd', 'model', 'approvalPolicy', 'permissions', 'baseInstructions', 'developerInstructions', 'config'}}
            thread_result = await client.call('thread/resume', {**resume, 'threadId': state['thread_id'], 'excludeTurns': True})
        else:
            thread_result = await client.call('thread/start', params)
        thread_id = (thread_result or {}).get("thread", {}).get("id")
        if not thread_id:
            raise RuntimeError(f"thread/start returned no thread id: {thread_result!r}")
        if not resuming:
            self._raw_event_threads.add(thread_id)

        if state is not None:
            if state.get('thread_id') not in (None, thread_id):
                raise RuntimeError('Codex resumed a different thread; conversation was not reset')
            state['thread_id'] = thread_id
            state['model'] = model_id
            state['_save']()
            self._loaded_threads[thread_id] = client
        return thread_id

    async def compact_conversation(self, session_id, role='front', timeout=180):
        """Explicit native compaction, serialized with turns of this conversation."""
        scope = (session_id, role)
        client, path, lock = await self._binding(scope)
        async with lock:
            self._conversations.loaded.pop(path, None)
            state = self._conversations.load(path)
            if not state.get('thread_id'):
                return {'status': 'not_started'}
            state['_save'] = lambda: self._conversations.save(path, state, session_id)
            thread_id = await self._open_thread(client, self.default_model, '', None, state)
            done = asyncio.get_running_loop().create_future()
            compacted = False
            turn_id = None
            native = None

            def observe(message):
                nonlocal compacted, turn_id, native
                params = message.get('params') or {}
                if params.get('threadId') != thread_id:
                    return
                method = message.get('method')
                if method == 'turn/started':
                    turn_id = params.get('turn', {}).get('id')
                if method == 'thread/tokenUsage/updated':
                    native = params['tokenUsage']
                if method == 'item/completed' and params.get('item', {}).get('type') == 'contextCompaction':
                    compacted = True
                if method == 'turn/completed' and not done.done():
                    if params.get('turn', {}).get('status') == 'completed' and compacted:
                        done.set_result(None)
                    else:
                        done.set_exception(RuntimeError('Codex compaction did not complete'))

            off = client.on_notification(observe)
            try:
                await client.call('thread/compact/start', {'threadId': thread_id})
                await asyncio.wait_for(done, timeout)
                state['compactions'] = state.get('compactions', 0) + 1
                usage_reported = False
                if native:
                    usage = _account_usage(native, state)
                    if usage and usage['total_tokens'] > 0:
                        get_tracker().record(UsageRecord.from_openai_usage(usage, self.default_model, 'codex'))
                        usage_reported = True
                if not usage_reported:
                    state['compaction_usage_unknown'] = True
                state['_save']()
                return {'status': 'compacted', 'thread_id': thread_id, 'usage_reported': usage_reported}
            except BaseException:
                if native:
                    usage = _account_usage(native, state)
                    if usage and usage['total_tokens'] > 0:
                        get_tracker().record(UsageRecord.from_openai_usage(usage, self.default_model, 'codex'))
                    else:
                        state['compaction_usage_unknown'] = True
                else:
                    state['compaction_usage_unknown'] = True
                state['_save']()
                if turn_id:
                    try:
                        await asyncio.wait_for(client.call('turn/interrupt', {'threadId': thread_id, 'turnId': turn_id}), 5)
                    except Exception:
                        pass
                raise
            finally:
                off()

    async def aclose(self):
        await close_codex_app_server()
        self._inference_directory.cleanup()

    def get_available_models(self) -> list[str]:
        return [self.default_model]

    def estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)


def _flatten(messages: list[dict]) -> str:
    """Render the selected message suffix as one attributed turn input."""
    return "\n\n".join(
        f"{m.get('role', 'user').upper()}: " + (
            '\n'.join(block.get('text', '[image attachment]') for block in m['content'])
            if isinstance(m.get('content'), list) else str(m.get('content', '')))
        for m in messages
    )


def _native_inputs(messages):
    """Send image content through app-server image inputs alongside attributed text."""
    if not any(isinstance(message.get('content'), list) for message in messages):
        return [{'type': 'text', 'text': _flatten(messages)}]
    inputs = []
    for message in messages:
        content = message.get('content', '')
        if not isinstance(content, list):
            inputs.append({'type': 'text', 'text': _flatten([message])})
            continue
        inputs.append({'type': 'text', 'text': message.get('role', 'user').upper() + ':'})
        for block in content:
            if block.get('type') == 'text' and isinstance(block.get('text'), str):
                inputs.append({'type': 'text', 'text': block['text']})
            elif block.get('type') == 'image_url':
                url = (block.get('image_url') or {}).get('url')
                if not isinstance(url, str) or not url.startswith(('data:image/png;base64,',
                        'data:image/jpeg;base64,', 'data:image/webp;base64,', 'data:image/gif;base64,')):
                    raise ValueError('Codex image inputs require an inline supported image')
                inputs.append({'type': 'image', 'url': url})
            else:
                raise ValueError('Unsupported Codex multimodal input block')
    return inputs


def _account_usage(native, state):
    """A thread's cumulative counters must be differenced, never recharged."""
    total = native['total']
    before = (state or {}).get('native_usage_total', {})
    keys = ['inputTokens', 'outputTokens', 'cachedInputTokens', 'cacheWriteInputTokens',
            'reasoningOutputTokens', 'totalTokens']
    delta = {key: total.get(key, 0) - before.get(key, 0) for key in keys}
    if state is not None:
        state['native_usage_total'] = total
        state['native_usage_last'] = native.get('last')
        state['model_context_window'] = native.get('modelContextWindow')
        gap = any(value < 0 for value in delta.values())
        state['usage_incomplete'] = state.get('usage_incomplete', False) or gap
        state['usage_checkpoints'] = [*state.get('usage_checkpoints', []),
            {'before': before, 'after': total, 'delta': delta,
             'complete': not gap}][-64:]
    if any(value < 0 for value in delta.values()):
        return None  # counter reset: retain raw evidence, do not invent usage
    return {'prompt_tokens': delta['inputTokens'], 'completion_tokens': delta['outputTokens'],
            'total_tokens': delta['totalTokens'],
            'prompt_tokens_details': {'cached_tokens': delta['cachedInputTokens'],
                                     'cache_write_tokens': delta['cacheWriteInputTokens']},
            'completion_tokens_details': {'reasoning_tokens': delta['reasoningOutputTokens']}}


def _strict_schema(value):
    """Encode optional fields as nullable, as required by Responses strict JSON.

    This changes transport shape only. The original schema is retained to remove
    those null placeholders before BigBrain dispatches an action.
    """
    if isinstance(value, list):
        return [_strict_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: _strict_schema(item) for key, item in value.items()}
    if result.get('type') == 'object':
        if result.get('additionalProperties') is not False:
            raise ValueError('Codex structured output requires closed object schemas')
        required = set(value.get('required', []))
        for key, item in list(result.get('properties', {}).items()):
            if key not in required and not _nullable(item):
                result['properties'][key] = {'anyOf': [item, {'type': 'null'}]}
        result['required'] = list(result.get('properties', {}))
    return result


def _nullable(schema):
    types = schema.get('type', [])
    return (types == 'null' or isinstance(types, list) and 'null' in types
            or any(_nullable(branch) for branch in schema.get('anyOf', [])))


def _restore_optional_fields(value, schema, _root=None):
    """Remove transport null placeholders through local refs and tagged unions.

    Nested Pydantic contracts use $defs/$ref. Resolving against the original
    root retains their optional/default fields without inventing domain values.
    Explicitly nullable and required fields keep their original semantics.
    """
    root = schema if _root is None else _root

    def resolve(node):
        visited = set()
        while '$ref' in node:
            ref = node['$ref']
            if not ref.startswith('#/') or ref in visited:
                raise ValueError('Unsupported or cyclic schema reference')
            visited.add(ref)
            node = root
            for part in ref[2:].split('/'):
                node = node[part.replace('~1', '/').replace('~0', '~')]
        return node

    schema = resolve(schema)
    if isinstance(value, dict):
        if 'anyOf' in schema or 'oneOf' in schema:
            branches = [resolve(b) for b in schema.get('anyOf', schema.get('oneOf', []))]
            schema = next((b for b in branches if b.get('type') == 'object' and all(
                key in value and value[key] == spec['const']
                for key, spec in b.get('properties', {}).items() if 'const' in spec)), {})
        properties = schema.get('properties', {})
        required = set(schema.get('required', []))
        return {key: _restore_optional_fields(item, properties.get(key, {}), root)
                for key, item in value.items()
                if not (item is None and key in properties and key not in required
                        and not _nullable(resolve(properties[key])))}
    if isinstance(value, list):
        return [_restore_optional_fields(item, schema.get('items', {}), root) for item in value]
    return value
