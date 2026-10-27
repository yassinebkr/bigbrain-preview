"""Replay first-wave discovery captures through budget admission and settlement."""
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from bigbrain.llm.conversation import conversation_scope
from bigbrain.llm.usage import UsageRecord, get_tracker
from bigbrain.research import Limits, ModelPolicy, ResearchBudgetExhausted, ResearchRuntime
from bigbrain.research_workflow import WorkflowBudget
from tests.test_research_runtime import page
from tests.test_research_workflow import FACT, StageInference

CAPTURES = json.loads((Path(__file__).parent / 'fixtures/research_gate4_first_collection.json').read_text())


@pytest.mark.parametrize('capture', CAPTURES, ids=lambda c: c['id'])
def test_live_consumption_preserves_monitored_admission(capture):
    recorded = capture['budget']
    budget = WorkflowBudget(policy='monitored')
    budget.inputs, budget.outputs = recorded['input_units'], recorded['output_units']
    budget.calls = recorded['logical_calls']
    # The live second packet and the fixed closing reserve can exceed the
    # forecast envelope before the consumed threshold has been reached.
    budget.admit(14000, 400, reserve_input=24000, reserve_output=2400)
    admission = budget.snapshot()['admissions'][-1]
    assert admission['allowed']
    assert admission['projected_input_units'] > 32000
    strict = WorkflowBudget()
    strict.inputs, strict.outputs = budget.inputs, budget.outputs
    with pytest.raises(ResearchBudgetExhausted):
        strict.admit(14000, 400, reserve_input=24000, reserve_output=2400)


@pytest.mark.parametrize('field,value', [('inputs', 32000), ('outputs', 4000), ('calls', 7)])
def test_monitored_admission_stops_at_consumed_threshold(field, value):
    budget = WorkflowBudget(policy='monitored')
    setattr(budget, field, value)
    with pytest.raises(ResearchBudgetExhausted):
        budget.admit(1, 1)
    assert not budget.snapshot()['admissions'][-1]['allowed']


class CapturedDiscoveryInference(StageInference):
    retains_conversation_context = True
    research_budget_policy = 'monitored'

    def __init__(self, capture):
        super().__init__(report_usage=False)
        self.capture, self.turn = capture, 0

    def estimate_tokens(self, text):
        return max(1, len(text) // 4)

    async def complete(self, prompt, **kwargs):
        self.turn += 1
        incoming = [4939, 8500, 7000, 9500][self.turn - 1]
        get_tracker().record(UsageRecord(model_id='gpt-6-luna', provider='fixture',
            input_tokens=incoming, output_tokens=200, total_tokens=incoming + 200))
        data = json.loads(prompt.split('\n', 1)[1])
        if kwargs['tool_schema']['name'] == 'research_collectiondecision':
            sources = data['state']['sources']
            request = dict(question_id='q1', rationale='Read the requested reference')
            if not sources:
                request.update(tool='search', query=self.capture['sources'][0]['discovered_by'])
            else:
                request.update(tool='open', source_id=sources[0]['id'])
            return json.dumps({'requests':[request]})
        return await super().complete(prompt, **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize('capture', CAPTURES, ids=lambda c: c['id'])
async def test_real_discovery_packet_reaches_reads_draft_control_and_terminal(capture):
    search, reader, progress = AsyncMock(), AsyncMock(), AsyncMock()
    search.search.return_value = capture['sources']
    reader.read.return_value = page(FACT)
    provider = CapturedDiscoveryInference(capture)
    runtime = ResearchRuntime(search, reader, ModelPolicy(provider), progress,
        staged=True, limits=Limits(actions=7, searches=3, pages=4, seconds=120))
    with conversation_scope('replay-' + capture['id'], 'research'):
        state = await runtime.run(capture['objective'], original_request=capture['objective'])
    assert state.execution_outcome == 'complete', state.reason
    assert runtime.model_calls == 4
    reader.read.assert_awaited_once()
    assert state.assessments
    assert state.workflow['budget']['input_units'] == 29939
    assert state.workflow['budget']['admissions']
    assert progress.call_args.args[0]['stage'] == 'research_finished'
    assert state.original_request == capture['objective']
