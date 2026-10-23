"""Offline budget exhaustion must yield a decision, never weaker acceptance."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from bigbrain.llm.usage import UsageRecord, capture_usage, get_tracker
from bigbrain.verification.review_budget import ReviewBudget
from bigbrain.verification.semantics import review_semantics


@pytest.mark.asyncio
@pytest.mark.parametrize('limit', ['calls', 'tokens', 'seconds'])
async def test_outer_capacity_forces_explicit_missing_evidence_decision(limit):
    calls = []
    async def complete(**kwargs):
        calls.append(kwargs)
        get_tracker().record(UsageRecord(model_id='fixture', provider='test',
                                         input_tokens=100, total_tokens=100))
        if kwargs['tool_schema']['name'] == 'acceptance_review_decision':
            return json.dumps({'decision': 'needs_evidence', 'contradictions': [], 'coverage': [],
                'missing_evidence': [{'criterion_id': '0', 'kind': 'executed_assertion',
                    'path': 'test_main.py', 'source_revision': 'current',
                    'request': 'Inspect and execute real output assertions'}]})
        return json.dumps({'action': {'type': 'read', 'path': 'main.py', 'start': 1, 'count': 1}})
    def capacity():
        available = {'calls': 12, 'tokens': 150000, 'seconds': 300}
        available[limit] = {'calls': 2, 'tokens': 20000, 'seconds': 30}[limit] if calls else available[limit]
        return available
    provider = SimpleNamespace(chat_complete=complete, review_budget_status=capacity)
    result = await review_semantics(provider, request='Print six', contracts=['Print six'],
        sources={'main.py': 'print(6)\n' * 7000, 'test_main.py': 'assert True'},
        tests={'status': 'passed', 'passed_cases': ['test_main.py::test_output']}, progressive=True)
    assert len(calls) == 2
    assert result.status == 'inconclusive'
    assert result.details['next_action'] == 'inspect'
    assert not result.details['repairable_evidence_gap']
    assert calls[-1]['tool_schema']['name'] == 'acceptance_review_decision'
    assert 'action' not in calls[-1]['tool_schema']['parameters']['properties']


@pytest.mark.asyncio
async def test_missing_usage_forces_conclusion_not_unbounded_reading():
    provider = SimpleNamespace(chat_complete=lambda: None)
    with capture_usage() as records:
        budget = ReviewBudget(records)
        async def no_usage(**kwargs):
            return '{}'
        provider.chat_complete = no_usage
        await budget.call(provider)
        assert not budget.status(provider)['usage_known']
        assert budget.status(provider)['conclude_now']


@pytest.mark.asyncio
async def test_capture_excludes_concurrent_review_usage_and_restores_parent():
    async def count(value):
        with capture_usage() as records:
            await asyncio.sleep(0)
            get_tracker().record(UsageRecord(model_id='fixture', provider='test', total_tokens=value))
            return sum(r.total_tokens for r in records)
    assert await asyncio.gather(count(13), count(29)) == [13, 29]


@pytest.mark.asyncio
async def test_exhausted_budget_refuses_call():
    async def forbidden(**kwargs):
        pytest.fail('Exhausted budget must not dispatch')
    budget = ReviewBudget([], max_calls=0)
    with pytest.raises(RuntimeError, match='exhausted'):
        await budget.call(SimpleNamespace(chat_complete=forbidden))


@pytest.mark.asyncio
async def test_budget_pressure_never_approves_unread_assertions():
    async def complete(**kwargs):
        assert kwargs['tool_schema']['name'] == 'acceptance_review_decision'
        return json.dumps({'decision': 'pass', 'contradictions': [], 'coverage': [
            {'criterion_id': '0', 'tests': ['test_main.py::test_output'], 'sources': ['main.py'],
             'reason': 'Unsubstantiated approval'}]})
    provider = SimpleNamespace(chat_complete=complete, review_budget_status=lambda: {'calls': 1})
    result = await review_semantics(provider, request='Print six', contracts=['Print six'],
        sources={'main.py': 'print(6)\n' * 7000, 'test_main.py': 'assert True'},
        tests={'status': 'passed', 'passed_cases': ['test_main.py::test_output']}, progressive=True)
    assert result.status == 'inconclusive'
