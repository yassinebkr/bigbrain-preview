"""Persistent subscription conversations, entirely offline/scripted transport."""
import asyncio
import json

import pytest

from bigbrain.llm.codex_provider import CodexProvider, _set_rpc_for_test, _account_usage
from bigbrain.llm.codex_sessions import incremental_messages, digest
from bigbrain.llm.conversation import conversation_scope, current_conversation, scoped_conversation
from bigbrain.llm.usage import UsageTracker, set_tracker_for_test, get_tracker


class ConversationRpc:
    def __init__(self):
        self.calls, self.listeners, self.totals = [], [], {}
        self.next_thread = self.next_turn = 0
        self.fail_resume = False
        self.active = set()
        self.auto_compact = False
        self.hold = False

    async def call(self, method, params=None):
        params = params or {}
        self.calls.append((method, params))
        if method == 'initialize':
            return {}
        if method == 'account/read':
            return {'account': {'type': 'chatgpt', 'email': 'test@example.invalid'},
                    'workspaceRouting': {'chatgptAccountId': 'test-account'}}
        if method == 'thread/start':
            self.next_thread += 1
            return {'thread': {'id': f'thread-{self.next_thread}'}}
        if method == 'thread/resume':
            if self.fail_resume:
                raise RuntimeError('resume denied')
            return {'thread': {'id': params['threadId']}}
        if method in {'turn/start', 'thread/compact/start'}:
            thread = params['threadId']
            assert thread not in self.active, 'Overlapping turns in one conversation'
            self.active.add(thread)
            self.next_turn += 1
            turn = f'turn-{self.next_turn}'
            if not self.hold:
                asyncio.get_running_loop().call_soon(self.finish, thread, turn, method == 'thread/compact/start')
            return {'turn': {'id': turn}} if method == 'turn/start' else {}
        if method == 'turn/interrupt':
            self.active.discard(params['threadId'])
            return {}
        raise AssertionError(method)

    def finish(self, thread, turn, compact):
        self.active.remove(thread)
        n = self.totals.get(thread, 0) + 1
        self.totals[thread] = n
        self.emit('turn/started', thread, {'turn': {'id': turn}})
        if compact or self.auto_compact:
            self.emit('item/completed', thread, {'item': {'type': 'contextCompaction'}})
        if not compact:
            self.emit('item/completed', thread, {'item': {'type': 'agentMessage', 'text': 'ack'}})
        total = {'inputTokens': n * 100, 'outputTokens': n, 'totalTokens': n * 101,
                 'cachedInputTokens': n * 50, 'reasoningOutputTokens': 0}
        self.emit('thread/tokenUsage/updated', thread, {'tokenUsage': {'total': total, 'last': {}, 'modelContextWindow': 10000}})
        self.emit('turn/completed', thread, {'turn': {'id': turn, 'status': 'completed'}})

    def emit(self, method, thread, params):
        for callback in list(self.listeners):
            callback({'method': method, 'params': {'threadId': thread, **params}})

    def notify(self, *args):
        pass

    def on_notification(self, callback):
        self.listeners.append(callback)
        return lambda: self.listeners.remove(callback)


@pytest.fixture(autouse=True)
def transport():
    rpc = ConversationRpc()
    _set_rpc_for_test(rpc)
    set_tracker_for_test(UsageTracker())
    yield rpc
    _set_rpc_for_test(None)
    set_tracker_for_test(UsageTracker())


@pytest.mark.asyncio
async def test_same_conversation_reuses_thread_and_sends_only_new_suffix(transport):
    provider = CodexProvider()
    messages = [{'role': 'system', 'content': 'Rules'}, {'role': 'user', 'content': 'first'}]
    await provider.chat_complete(messages, conversation_id='sess-one')
    await provider.chat_complete([*messages, {'role': 'assistant', 'content': 'ack'},
        {'role': 'user', 'content': 'second'}], conversation_id='sess-one')
    assert sum(m == 'thread/start' for m, _ in transport.calls) == 1
    assert not any(m == 'thread/resume' for m, _ in transport.calls)
    turns = [p for m, p in transport.calls if m == 'turn/start']
    assert turns[0]['threadId'] == turns[1]['threadId']
    assert turns[1]['input'][0]['text'] == 'USER: second'
    assert get_tracker().totals()['total_tokens'] == 202  # not 101 + cumulative 202
    state = next(iter(provider._conversations.loaded.values()))
    assert state['usage_checkpoints'][-1]['delta']['cachedInputTokens'] == 50


@pytest.mark.asyncio
async def test_restart_resumes_exact_id_and_failed_resume_never_starts_new_thread(transport):
    first = CodexProvider()
    await first.chat_complete([{'role': 'user', 'content': 'first'}], conversation_id='sess-one')
    second = CodexProvider()
    await second.chat_complete([{'role': 'user', 'content': 'second'}], conversation_id='sess-one')
    assert sum(m == 'thread/start' for m, _ in transport.calls) == 1
    assert any(m == 'thread/resume' and p['threadId'] == 'thread-1' for m, p in transport.calls)
    transport.fail_resume = True
    with pytest.raises(RuntimeError, match='resume denied'):
        await CodexProvider().chat_complete([{'role': 'user', 'content': 'third'}], conversation_id='sess-one')
    assert sum(m == 'thread/start' for m, _ in transport.calls) == 1


@pytest.mark.asyncio
async def test_concurrent_chats_and_roles_are_separate(transport):
    provider = CodexProvider()
    async def call(session, role='front'):
        return await provider.chat_complete([{'role': 'user', 'content': session}],
            conversation_id=session, conversation_role=role)
    assert await asyncio.gather(call('sess-a'), call('sess-a'), call('sess-b'), call('sess-a', 'worker')) == ['ack'] * 4
    assert sum(m == 'thread/start' for m, _ in transport.calls) == 3
    assert not transport.active


@pytest.mark.asyncio
async def test_manual_compaction_keeps_binding_cursor_and_records_usage(transport):
    provider = CodexProvider()
    messages = [{'role': 'user', 'content': 'first'}]
    await provider.chat_complete(messages, conversation_id='sess-one')
    assert (await provider.compact_conversation('sess-one'))['status'] == 'compacted'
    await provider.chat_complete([*messages, {'role': 'assistant', 'content': 'ack'},
        {'role': 'user', 'content': 'after'}], conversation_id='sess-one')
    turns = [p for m, p in transport.calls if m == 'turn/start']
    assert turns[-1]['input'][0]['text'] == 'USER: after'
    assert sum(m == 'thread/start' for m, _ in transport.calls) == 1
    assert get_tracker().totals()['total_tokens'] == 303
    start = next(p for m, p in transport.calls if m == 'thread/start')
    assert start['config']['model_auto_compact_token_limit'] == 128000


def test_rolling_history_and_updated_instructions_do_not_replay_known_turns():
    old = [{'role': 'user', 'content': 'old'}, {'role': 'assistant', 'content': 'ack'},
           {'role': 'user', 'content': 'recent'}, {'role': 'assistant', 'content': 'ack2'}]
    state = {'message_hashes': [digest(m) for m in old], 'instructions_hash': digest([])}
    delta, _ = incremental_messages([*old[2:], {'role': 'user', 'content': 'new'}], state)
    assert delta == [{'role': 'user', 'content': 'new'}]
    delta, _ = incremental_messages([{'role': 'system', 'content': 'updated'}, *old[2:]], state)
    assert any(m['content'] == 'updated' for m in delta)
    assert not any(m['content'] == 'recent' for m in delta)


@pytest.mark.asyncio
async def test_maintenance_checkpoint_after_compaction_survives_provider_restart(transport):
    first = CodexProvider()
    messages = [{'role': 'user', 'content': 'initial event'}]
    await first.chat_complete(messages, conversation_id='maintenance')
    await first.compact_conversation('maintenance')
    second = CodexProvider()
    checkpoint = {'runtime_state': {'source_epoch': 7}, 'acceptance': ['Preserve CLI']}
    await second.chat_complete([*messages, {'role': 'user', 'content': 'next event'}],
        conversation_id='maintenance', context_checkpoint=checkpoint)
    turns = [p for m, p in transport.calls if m == 'turn/start']
    assert 'authoritative_checkpoint' in turns[-1]['input'][0]['text']
    assert 'source_epoch' in turns[-1]['input'][0]['text']
    assert turns[-1]['threadId'] == turns[0]['threadId']
    await second.chat_complete([*messages, {'role': 'user', 'content': 'next event'},
        {'role': 'user', 'content': 'last event'}], conversation_id='maintenance', context_checkpoint=checkpoint)
    turns = [p for m, p in transport.calls if m == 'turn/start']
    assert turns[-1]['input'][0]['text'] == 'USER: last event'


@pytest.mark.asyncio
async def test_failed_event_submission_does_not_advance_durable_cursor(transport):
    original_call = transport.call
    failed = False
    async def fail_once(method, params=None):
        nonlocal failed
        if method == 'turn/start' and not failed:
            failed = True
            raise RuntimeError('request rejected before acceptance')
        return await original_call(method, params)
    transport.call = fail_once
    messages = [{'role': 'user', 'content': 'immutable initial batch'}]
    with pytest.raises(RuntimeError, match='before acceptance'):
        await CodexProvider().chat_complete(messages, conversation_id='retry-events')
    provider = CodexProvider()
    await provider.chat_complete(messages, conversation_id='retry-events')
    await provider.chat_complete([*messages, {'role': 'user', 'content': 'new batch'}], conversation_id='retry-events')
    turns = [p for m, p in transport.calls if m == 'turn/start']
    assert 'immutable initial batch' in turns[0]['input'][0]['text']
    assert turns[-1]['input'][0]['text'] == 'USER: new batch'


@pytest.mark.asyncio
async def test_dead_transport_unblocks_turn_after_native_start_was_accepted(transport):
    from bigbrain.llm.codex_provider import CodexUnavailable
    transport.hold = True
    task = asyncio.create_task(CodexProvider().chat_complete(
        [{'role': 'user', 'content': 'work'}], conversation_id='dead-transport'))
    for _ in range(100):
        if transport.active:
            break
        await asyncio.sleep(0)
    assert transport.active
    transport.emit('bigbrain/transport/error', 'thread-1', {'reason': 'reader failed'})
    with pytest.raises(CodexUnavailable, match='reader failed'):
        await asyncio.wait_for(task, 1)


@pytest.mark.asyncio
async def test_deleted_chat_cannot_resume(transport):
    provider = CodexProvider()
    provider._conversations.store.ensure('sess-delete')
    await provider.chat_complete([{'role': 'user', 'content': 'first'}], conversation_id='sess-delete')
    provider._conversations.store.delete('sess-delete')
    with pytest.raises(ValueError, match='deleted'):
        await provider.chat_complete([{'role': 'user', 'content': 'again'}], conversation_id='sess-delete')
    assert sum(m == 'thread/start' for m, _ in transport.calls) == 1


def test_counter_reset_is_unknown_not_negative_or_double_counted():
    state = {'native_usage_total': {'inputTokens': 100, 'totalTokens': 100}}
    assert _account_usage({'total': {'inputTokens': 10, 'totalTokens': 10}}, state) is None
    assert state['usage_incomplete'] is True
    _account_usage({'total': {'inputTokens': 20, 'totalTokens': 20}}, state)
    assert state['usage_incomplete'] is True  # later samples cannot erase the gap


@pytest.mark.asyncio
async def test_native_auto_compaction_is_not_mistaken_for_an_agent_tool(transport):
    transport.auto_compact = True
    provider = CodexProvider()
    assert await provider.chat_complete([{'role': 'user', 'content': 'first'}], conversation_id='sess-one') == 'ack'
    state = next(iter(provider._conversations.loaded.values()))
    assert state['compactions'] == 1


@pytest.mark.asyncio
async def test_stop_scoped_turn_interrupts_only_its_thread_and_releases_lock(transport):
    transport.hold = True
    provider = CodexProvider()
    task = asyncio.create_task(provider.chat_complete([{'role': 'user', 'content': 'first'}], conversation_id='sess-stop'))
    while not transport.active:
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert ('turn/interrupt', {'threadId': 'thread-1', 'turnId': 'turn-1'}) in transport.calls
    transport.hold = False
    assert await provider.chat_complete([{'role': 'user', 'content': 'next'}], conversation_id='sess-stop') == 'ack'
    assert sum(m == 'thread/start' for m, _ in transport.calls) == 1


@pytest.mark.asyncio
async def test_independent_review_scope_does_not_inherit_worker_history():
    observed = []
    @scoped_conversation('review', independent=True)
    async def review():
        observed.append(current_conversation.get())
    with conversation_scope('sess-one', 'worker'):
        await review()
        await review()
        assert current_conversation.get() == ('sess-one', 'worker')
    assert observed[0][0] == observed[1][0] == 'sess-one'
    assert observed[0][1] != observed[1][1]
    assert current_conversation.get() is None
