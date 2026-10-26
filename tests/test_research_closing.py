"""Offline admission, native-context forecasts and evidence-review generation."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import jsonschema
import pytest

from bigbrain.llm.conversation import conversation_scope
from bigbrain.llm.usage import UsageRecord
from bigbrain.research import Action, Limits, ModelPolicy, ResearchRuntime
from bigbrain.research_assessment import AssessmentReport, ModelReviewer
from bigbrain.research_budget import ContextForecast, closing_envelope
from tests.test_research_assessment import evidence, report


def native_provider():
    return SimpleNamespace(retains_conversation_context=True,
        estimate_tokens=lambda text: max(1, len(text)//4), complete=AsyncMock())


def test_context_forecast_uses_latest_call_context_and_separate_output():
    forecast = ContextForecast()
    forecast.observe([UsageRecord('fixture', 'codex', input_tokens=10000, output_tokens=400, total_tokens=10400)])
    assert forecast.request(500, 100, 200, retained=True) == 11200
    forecast.observe([UsageRecord('fixture', 'codex', input_tokens=12000, output_tokens=300, total_tokens=12300)])
    assert forecast.retained_units == 12300
    assert forecast.request(500, 100, 200) == 800


def test_closing_envelope_holds_each_review_and_its_native_history():
    assert closing_envelope(10000, 12000, 1) == 10000
    assert closing_envelope(10000, 12000, 2) == 22000
    assert closing_envelope(10000, 12000, 2, retained=True) == 32000


def test_review_reservation_uses_its_independent_native_context():
    provider = native_provider()
    policy, reviewer = ModelPolicy(provider), ModelReviewer(provider)
    ResearchRuntime(AsyncMock(), AsyncMock(), policy, AsyncMock(), reviewer=reviewer)
    assert policy.context_forecast is not reviewer.context_forecast
    policy.context_forecast.retained_units = 18000
    reviewer.context_forecast.retained_units = 18000
    with conversation_scope('offline-review', 'research'):
        assert reviewer.allowance('Observed evidence', 6000, AssessmentReport) > 24000
        held = reviewer.closing_allowance(evidence(), attempts=2)
        assert held > reviewer.closing_allowance(evidence(), attempts=1)


def test_native_review_schema_rejects_omitted_source_before_runtime_validation():
    state = evidence(('The API returns an integer.', 'The audit questions this claim.'))
    reviewer = ModelReviewer(AsyncMock())
    reviewer.request(state)
    schema = reviewer.protocol(AssessmentReport)['tool_schema']['parameters']
    candidate = report(state).model_dump(mode='json', exclude_none=True)
    jsonschema.Draft202012Validator(schema).validate(candidate)
    candidate['claims'][0]['considered_source_ids'] = ['s0']
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(candidate)


@pytest.mark.asyncio
async def test_closing_phase_prevents_more_collection_and_exposes_budget():
    state = evidence()
    provider = native_provider()
    provider.complete.return_value = Action(tool='conclude', question_id='q', rationale='Close available evidence').model_dump_json()
    policy = ModelPolicy(provider)
    policy.context_forecast = ContextForecast(retained_units=15000)
    with conversation_scope('offline-close', 'research'):
        decision = await policy.choose(state, {'tokens':90000, 'actions':5,
            'review_reserve':50000, 'review_attempts_reserved':2})
    assert decision.tool == 'conclude'
    assert policy.last_budget_decision['phase'] == 'closing'
    assert policy.last_budget_decision['closing_units'] > 50000
    schema = provider.complete.call_args.kwargs['tool_schema']['parameters']
    assert schema['properties']['tool']['enum'] == ['conclude', 'clarify']


@pytest.mark.asyncio
async def test_rejected_review_correction_uses_diagnostic_and_original_evidence():
    state = evidence()
    reviewer = ModelReviewer(AsyncMock())
    invalid = report(state)
    invalid.claims[0].citations[0].quote = 'Invented evidence that must be rejected.'
    reviewer.reject_report(invalid, 'Quote must be an observed contiguous substring')
    prompt, _, _ = reviewer.request(state)
    assert 'Quote must be an observed contiguous substring' in prompt
    assert state.passages[0].text in prompt
    assert 'Invented evidence that must be rejected.' not in prompt


@pytest.mark.asyncio
async def test_closing_commits_to_one_full_review_when_correction_cannot_fit():
    state = evidence()
    provider = native_provider()
    provider.complete.return_value = Action(tool='conclude', question_id='q', rationale='Close available evidence').model_dump_json()
    policy = ModelPolicy(provider)
    policy.context_forecast = ContextForecast(retained_units=15000)
    with conversation_scope('offline-single-review', 'research'):
        await policy.choose(state, {'tokens':70000, 'actions':5, 'review_reserve':65000,
            'single_review_reserve':25000, 'review_attempts_reserved':2})
    admission = policy.last_budget_decision
    assert admission['phase'] == 'closing' and admission['review_attempts'] == 1
    assert admission['decision_units'] + admission['closing_units'] <= admission['remaining_units']


@pytest.mark.asyncio
async def test_committed_single_review_stops_on_invalid_citation():
    import time
    state = evidence()
    invalid = report(state)
    invalid.claims[0].citations[0].quote = 'An invented quotation.'
    provider = AsyncMock()
    provider.complete.return_value = invalid.model_dump_json()
    runtime = ResearchRuntime(AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock(),
        reviewer=ModelReviewer(provider), limits=Limits(tokens=120000, reviews=2))
    runtime.state, runtime.started = state, time.monotonic()
    runtime.closing_review_cap = 1
    await runtime.execute(state, Action(tool='conclude', question_id='q', claims=state.claims,
        rationale='Verify within the admitted envelope'), runtime.counts, set(), 0)
    assert runtime.counts['reviews'] == provider.complete.await_count == 1
    assert state.status == 'partial' and state.answer_status != 'complete'
    assert state.claims[0].status == 'unverified'


def test_independent_provider_contexts_keep_separate_forecasts():
    policy, reviewer = ModelPolicy(native_provider()), ModelReviewer(native_provider())
    ResearchRuntime(AsyncMock(), AsyncMock(), policy, AsyncMock(), reviewer=reviewer)
    policy.context_forecast.retained_units = 19000
    assert reviewer.context_forecast.retained_units == 0
