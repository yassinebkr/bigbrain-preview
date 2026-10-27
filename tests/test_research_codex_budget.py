"""Subscription research budget policy through the actual Codex RPC adapter."""
import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from bigbrain.llm.codex_provider import CodexProvider, _set_rpc_for_test
from bigbrain.llm.conversation import conversation_scope
from bigbrain.research import Limits, ModelPolicy, ResearchRuntime
from tests.test_codex_provider import FakeRpc, clean_state
from tests.test_research_runtime import page
from tests.test_research_workflow import FACT, StageInference


class ResearchRpc(FakeRpc):
    """Return structured proposals and native usage from isolated role threads."""

    account_result = {'account': {'type': 'chatgpt', 'email': 'research-fixture@example.test'}}

    def __init__(self, *, input_tokens=600, output_tokens=150, usage_known=True, overrun_turn=1, recovery=False):
        super().__init__()
        self.inference = StageInference(report_usage=False, recovery=recovery)
        self.input_tokens, self.output_tokens, self.usage_known = input_tokens, output_tokens, usage_known
        self.overrun_turn = overrun_turn
        self.threads, self.turns, self.totals = 0, 0, {}

    async def call(self, method, params=None):
        params = params or {}
        if method == 'thread/start':
            self.calls.append((method, params))
            self.threads += 1
            return {'thread': {'id': f'thread-{self.threads}'}}
        if method != 'turn/start':
            return await super().call(method, params)
        self.calls.append((method, params))
        self.turns += 1
        tid, turn = params['threadId'], f'turn-{self.turns}'
        prompt = params['input'][0]['text'].split('\nSubmit the decision using', 1)[0].rsplit('USER: ', 1)[1]
        data = json.loads(prompt.split('\n', 1)[1])
        contract = 'collectiondecision' if 'state' in data else 'control' if 'draft' in data else 'draft'
        raw = await self.inference.complete(prompt, tool_schema={'name': 'research_' + contract})
        events = []
        if self.usage_known:
            previous = self.totals.get(tid, {'inputTokens': 0, 'outputTokens': 0, 'totalTokens': 0})
            incoming = self.input_tokens if self.turns == self.overrun_turn else 600
            outgoing = self.output_tokens if self.turns == self.overrun_turn else 150
            last = {'inputTokens': incoming, 'outputTokens': outgoing,
                    'totalTokens': incoming + outgoing}
            total = {k: previous[k] + v for k, v in last.items()}
            self.totals[tid] = total
            events.append({'method': 'thread/tokenUsage/updated', 'params': {
                'threadId': tid, 'tokenUsage': {'total': total, 'last': last}}})
        events.append({'id': 100 + self.turns, 'method': 'item/tool/call', 'params': {
            'threadId': tid, 'turnId': turn, 'callId': f'proposal-{self.turns}',
            'tool': 'bigbrain_submit_decision', 'arguments': {'decision_json': raw}}})
        for event in events:
            asyncio.get_running_loop().call_soon(self._emit, event)
        return {'turn': {'id': turn}}


async def run_subscription(rpc, *, input_limit=32000):
    _set_rpc_for_test(rpc)
    reader = AsyncMock()
    reader.read.return_value = page(FACT)
    engine = ResearchRuntime(AsyncMock(), reader, ModelPolicy(CodexProvider('codex-luna-6')),
                             AsyncMock(), staged=True, limits=Limits(seconds=120,
                                 workflow_input_units=input_limit, tokens=input_limit + 4000))
    with conversation_scope('subscription-research-fixture', 'research'):
        state = await engine.run('Establish the API behavior and its input restriction')
    return state, engine


@pytest.mark.asyncio
async def test_codex_monitored_journey_reuses_collection_thread_and_isolates_final_control(clean_state):
    rpc = ResearchRpc()
    state, engine = await run_subscription(rpc)
    assert state.execution_outcome == 'complete', state.reason
    assert rpc.turns == engine.model_calls == 4
    assert rpc.threads == 3
    turns = [params for method, params in rpc.calls if method == 'turn/start']
    assert turns[0]['threadId'] == turns[1]['threadId']
    assert len({t['threadId'] for t in turns[1:]}) == 3
    budget = state.workflow['budget']
    assert budget['policy'] == 'monitored'
    assert budget['input_units'] == 2400 and budget['output_units'] == 600
    assert not budget['threshold_exceeded']
    assert state.usage['api_reference']['complete']


@pytest.mark.asyncio
@pytest.mark.parametrize('turn,incoming,outgoing,excess_input,excess_output', [
    (1, 35000, 150, 3000, 0), (1, 600, 4500, 0, 500),
    (2, 35000, 150, 3600, 0), (3, 35000, 150, 4200, 0), (4, 35000, 150, 4800, 0)])
async def test_native_threshold_overrun_is_recorded_and_prevents_any_following_turn(
        clean_state, turn, incoming, outgoing, excess_input, excess_output):
    rpc = ResearchRpc(input_tokens=incoming, output_tokens=outgoing, overrun_turn=turn)
    state, engine = await run_subscription(rpc)
    if turn < 4:
        assert state.diagnostic['code'] == 'budget'
        assert state.execution_outcome == ('blocked' if turn == 1 else 'partial')
    else:
        assert state.diagnostic is None
        assert state.execution_outcome == 'complete'
        assert state.claims[0].status == 'supported'
    assert rpc.turns == engine.model_calls == turn
    assert engine.counts['reviews'] == int(turn == 4)
    budget = state.workflow['budget']
    assert budget['threshold_exceeded']
    assert budget['excess_input_units'] == excess_input
    assert budget['excess_output_units'] == excess_output
    if turn == 1:
        engine.reader.read.assert_not_awaited()
    else:
        engine.reader.read.assert_awaited_once()
    engine.search.search.assert_not_awaited()


@pytest.mark.asyncio
async def test_native_unknown_usage_keeps_conservative_reservations_and_partial_cost_coverage(clean_state):
    rpc = ResearchRpc(usage_known=False)
    state, engine = await run_subscription(rpc)
    assert engine.unknown_calls == rpc.turns
    assert state.workflow['budget']['input_units'] > 0
    assert all(not call['usage_known'] for call in state.workflow['budget']['calls'])
    assert not state.usage['api_reference']['complete']
    assert rpc.turns <= 7


@pytest.mark.asyncio
async def test_native_targeted_recovery_uses_measured_context_and_the_same_three_lanes(clean_state):
    rpc = ResearchRpc(recovery=True)
    state, engine = await run_subscription(rpc)
    assert state.execution_outcome == 'complete', state.reason
    assert rpc.turns == engine.model_calls == 7
    assert rpc.threads == 3
    assert state.dossier['revision'] == 2
    assert state.workflow['complement_used']
    assert set(state.workflow['budget']['retained_lane_units'].values()) == {750}


@pytest.mark.asyncio
async def test_six_concurrent_codex_journeys_keep_role_threads_and_terminal_results(clean_state):
    rpc = ResearchRpc()
    outcomes = await asyncio.gather(*(run_subscription(rpc) for _ in range(6)))
    assert rpc.turns == 24
    assert rpc.threads == 18
    for state, engine in outcomes:
        assert state.execution_outcome == 'complete', state.reason
        assert engine.model_calls == 4
        assert engine.counts['reviews'] == 1
        assert state.workflow['stage'] == 'settle'


@pytest.mark.asyncio
async def test_expanded_input_limit_reaches_control_and_still_stops_at_its_own_threshold(clean_state):
    rpc = ResearchRpc(input_tokens=35000, overrun_turn=3)
    state, engine = await run_subscription(rpc, input_limit=64000)
    assert state.execution_outcome == 'complete', state.reason
    assert state.workflow['budget']['input_limit'] == 64000
    assert state.workflow['budget']['input_units'] == 36800
    assert engine.model_calls == 4
    rpc = ResearchRpc(input_tokens=65000)
    state, engine = await run_subscription(rpc, input_limit=64000)
    assert engine.model_calls == 1
    assert state.workflow['budget']['excess_input_units'] == 1000
    assert state.diagnostic['code'] == 'budget'
