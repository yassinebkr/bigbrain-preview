"""Bound final admission and preserve terminal evidence through delivery failures."""
from unittest.mock import AsyncMock

import pytest

from bigbrain.research import ModelPolicy
from bigbrain.research_direct import DirectReply, run_direct
from bigbrain.research_direct_controller import DirectController, DirectLimitReached
from bigbrain.research_sessions import ResearchSessions
from tests.test_research_direct_journey import ScriptedAdapter, runtime
from tests.test_research_direct_model import Provider


def test_unaffordable_final_forecast_starts_no_call():
    controller = DirectController(input_units=63500)
    with pytest.raises(DirectLimitReached, match='Final synthesis forecast'):
        controller.admit(decision_input=1000, decision_output=200,
            finish_input=2000, finish_output=1000, seconds_remaining=100)
    assert controller.calls == 0
    assert controller.pending is None


@pytest.mark.asyncio
async def test_retained_partial_survives_an_overrun_without_a_final_call():
    engine, _ = runtime()
    adapter = ScriptedAdapter()
    original = adapter.infer

    async def partial_then_overrun(*args):
        reply = await original(*args)
        if 'conclusion' in reply.value:
            reply.value['conclusion']['questions'][0]['gaps'] = ['A second release is unread']
            return DirectReply(reply.value, input_units=65000, output_units=100)
        return reply

    adapter.infer = partial_then_overrun
    state = await run_direct(engine, adapter)
    assert len(adapter.calls) == 2
    assert state.execution_outcome == 'partial'
    assert state.claims and state.usage['direct_result']['findings']
    assert state.original_request_coverage['gaps'] == ['A second release is unread']
    assert state.usage['stage_budget']['threshold_exceeded']
    assert state.usage['api_reference']['actual_subscription_charge_usd'] is None
    assert not state.usage['api_reference']['complete']
    assert all(record['packet_bytes'] > 0 for record in state.workflow['budget']['records'])


@pytest.mark.asyncio
async def test_terminal_publication_failure_is_durable_and_keeps_the_evidence():
    engine, _ = runtime()
    engine.direct = True
    engine.policy = ModelPolicy(Provider())
    engine.checkpoints = ResearchSessions('isolated-workspace', 'owner-chat')

    async def publish(event):
        if event['stage'] == 'research_finished':
            raise ConnectionError('Disconnected frontend')

    engine.progress = publish
    state = await engine.run('Establish the qualified limit')
    assert state.execution_outcome == 'complete', state.reason
    assert state.claims
    restored, _ = engine.checkpoints.load(state.research_id)
    assert restored.phase == 'settled'
    assert restored.execution_outcome == 'complete'
    assert restored.diagnostic['delivery_error']['type'] == 'ConnectionError'
    assert restored.usage['direct_result']['findings']
    with pytest.raises(FileNotFoundError):
        ResearchSessions('isolated-workspace', 'other-chat').load(state.research_id)


@pytest.mark.asyncio
async def test_initial_progress_failure_returns_a_terminal_diagnostic():
    engine, fetcher = runtime()
    engine.direct = True
    provider = Provider()
    engine.policy = ModelPolicy(provider)
    engine.progress = AsyncMock(side_effect=ConnectionError('Disconnected frontend'))
    state = await engine.run('Establish the qualified limit')
    assert state.phase == 'settled'
    assert state.execution_outcome == 'failed'
    assert state.diagnostic['code'] == 'direct_runtime_failure'
    assert state.diagnostic['delivery_error']
    assert not fetcher.calls and not provider.scopes


@pytest.mark.asyncio
async def test_native_partial_usage_keeps_zero_output_distinct_from_unknown_input():
    from bigbrain.llm.usage import UsageRecord, get_tracker
    from bigbrain.research_direct_model import DirectModelAdapter

    class PartialUsageProvider(Provider):
        async def complete(self, prompt, **kwargs):
            result = await super().complete(prompt, **kwargs)
            get_tracker().record(UsageRecord.from_openai_usage(
                {'completion_tokens': 0}, model_id='gpt-6-luna', provider='codex'))
            return result

    engine, _ = runtime()
    state = await run_direct(engine, DirectModelAdapter(engine, PartialUsageProvider()))
    assert state.execution_outcome == 'complete', state.reason
    assert state.usage['reported_usage'] == {
        'input_tokens': None, 'output_tokens': 0, 'cached_input_tokens': None}
    assert all(not record['input_known'] and record['output_known']
               for record in state.workflow['budget']['records'])
    assert not state.usage['api_reference']['complete']


@pytest.mark.asyncio
async def test_qualified_inference_survives_state_and_chat_delivery():
    from bigbrain.research import ResearchState
    from bigbrain.research_delivery import research_message
    engine, _ = runtime()
    adapter = ScriptedAdapter()
    original = adapter.infer

    async def inferred(*args):
        reply = await original(*args)
        for finding in (reply.value.get('conclusion') or {}).get('findings', []):
            finding['reasoning'] = 'qualified_inference'
            finding['limitations'] = ['Inference restricted to the quoted indoor configuration.']
        return reply

    adapter.infer = inferred
    state = await run_direct(engine, adapter)
    restored = ResearchState.model_validate_json(state.model_dump_json())
    assert restored.claims[0].reasoning == 'qualified_inference'
    assert 'Inférence qualifiée' in research_message(restored)
    assert 'Inference restricted' in research_message(restored)
