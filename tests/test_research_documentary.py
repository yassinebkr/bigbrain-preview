"""Compact documentary settlement and mandatory escalation regressions."""
from unittest.mock import AsyncMock
import time

import pytest

from bigbrain.research import Action, ResearchRuntime
from bigbrain.research_documentary import finish_documentary
from tests.test_research_assessment import evidence


def candidate():
    state = evidence()
    state.delivery_mode = "documentary"
    for passage in state.passages:
        source = next(s for s in state.sources if s.id == passage.source_id)
        source.content_sha256 = passage.observation_sha256 = "a" * 64
    return state


@pytest.mark.asyncio
async def test_documentary_conclusion_skips_review_and_preserves_unverified_status():
    state = candidate()
    reviewer = AsyncMock()
    runtime = ResearchRuntime(AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock(), reviewer=reviewer, documentary=True)
    runtime.state, runtime.started = state, time.monotonic()
    await runtime.execute(state, Action(tool="conclude", question_id="q", rationale="Return cited documentary findings",
        claims=state.claims), runtime.counts, set(), 0)
    assert state.status == "completed" and state.answer_status == "unassessed"
    assert all(claim.status == "unverified" for claim in state.claims)
    reviewer.review.assert_not_awaited()
    assert runtime.counts["reviews"] == 0


@pytest.mark.parametrize("failure", ["unknown", "stale", "missing_support"])
def test_documentary_delivery_rejects_invalid_evidence(failure):
    state = candidate()
    if failure == "unknown":
        state.claims[0].evidence[0].passage_id = "invented"
    elif failure == "stale":
        state.sources[0].content_sha256 = "b" * 64
    else:
        state.claims[0].evidence = []
    with pytest.raises(ValueError):
        finish_documentary(state, Action(tool="conclude", question_id="q", rationale="Conclude"), state.claims)


def test_remaining_gaps_keep_documentary_result_partial():
    state = candidate()
    finish_documentary(state, Action(tool="conclude", question_id="q", rationale="Keep missing scope explicit",
        remaining_gaps=["The older requested version remains unread"]), state.claims)
    assert state.status == "partial" and "older requested version" in state.reason


@pytest.mark.asyncio
async def test_explicit_review_requirement_is_retained_and_runs_review():
    state = candidate()
    reviewer = AsyncMock()
    reviewer.review.side_effect = ValueError("Controlled review diagnostic")
    runtime = ResearchRuntime(AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock(), reviewer=reviewer, documentary=True)
    runtime.state, runtime.started = state, time.monotonic()
    await runtime.execute(state, Action(tool="conclude", question_id="q", rationale="Inspect conflicting evidence",
        review_reason="Conflicting observed statements", claims=state.claims), runtime.counts, set(), 0)
    reviewer.review.assert_awaited_once()
    assert state.review_reason == "Conflicting observed statements" and state.status == "partial"


@pytest.mark.asyncio
async def test_default_worker_delivers_a_cited_result_after_independent_control(tmp_path, monkeypatch):
    monkeypatch.delenv('BIGBRAIN_RESEARCH_INPUT_UNITS', raising=False)
    monkeypatch.delenv('BIGBRAIN_RESEARCH_DOSSIER_BYTES', raising=False)
    import json
    from types import SimpleNamespace
    from bigbrain.brains.researcher import ResearcherBrain
    from bigbrain.bus.bus import MessageBus

    from tests.test_research_workflow import StageInference
    inference = StageInference(fact='The documented API returns an integer.', url='https://docs.test/api')
    reader = AsyncMock()
    reader.read.return_value = {'url':'https://docs.test/api', 'sha256':'a'*64,
        'text':'The documented API returns an integer.'}
    bus = MessageBus(tmp_path/'bus')
    worker = ResearcherBrain('researcher', bus, llm_provider=inference,
        search_provider=AsyncMock(), page_reader=reader)
    worker.send_progress = AsyncMock()
    try:
        result = await worker._full_research('What does the documented API return?', {})
        assert result['success'] and result['answer_status'] == 'complete', result.get('error')
        assert result['evidence']['delivery_mode'] == 'reviewed'
        assert [c[0] for c in inference.calls] == ['research_collectiondecision', 'research_collectiondecision',
                                                 'research_draft', 'research_control']
        assert result['evidence']['usage']['model_calls'] == 4
        assert result['evidence']['workflow']['budget']['input_limit'] == 64000
        assert result['evidence']['claims'][0]['status'] == 'supported'
        assert worker.send_progress.call_args.args[0]['research']['counts']['reviews'] == 1
    finally:
        await bus.close()


@pytest.mark.asyncio
async def test_documentary_collection_never_assembles_optional_review_reservations():
    from datetime import datetime, timezone
    from bigbrain.research_assessment import ModelReviewer
    from bigbrain.research import Limits
    state = candidate()
    for source in state.sources:
        source.consulted_at = datetime.now(timezone.utc).isoformat()
    policy = AsyncMock()
    policy.choose.return_value = Action(tool='conclude', question_id='q', rationale='Return the documented finding', claims=state.claims)
    reviewer = ModelReviewer(AsyncMock())
    def unexpected(*args, **kwargs):
        raise AssertionError('Optional review preparation must remain inactive')
    reviewer.required_allowance = unexpected
    reviewer.closing_allowance = unexpected
    runtime = ResearchRuntime(AsyncMock(), AsyncMock(), policy, AsyncMock(),
        reviewer=reviewer, documentary=True, limits=Limits(actions=2))
    result = await runtime.run(state.objective, continuation=(state, 0))
    assert result.status == 'completed', result.reason
    assert runtime.counts['reviews'] == 0


def test_empty_conclusion_requires_reading_available_discovered_sources():
    from bigbrain.research import ResearchState, Source, Question, ResearchActionRejected, research_tools
    state = ResearchState(objective='Read the reference', questions=[Question(id='q', text='Reference', evidence_needed='Read it')],
        sources=[Source(id='s1', url='https://reference.test/', discovered_by='query')])
    runtime = ResearchRuntime(AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock())
    action = Action(tool='conclude', question_id='q', rationale='Only snippets available')
    assert 'conclude' not in research_tools(state, {'actions':3, 'pages':2})
    with pytest.raises(ResearchActionRejected, match='Read an available'):
        runtime.validate_action(state, action, runtime.counts, set())
    runtime.collection_can_continue = False
    runtime.validate_action(state, action, runtime.counts, set())
    assert 'conclude' in research_tools(state, {'actions':1, 'pages':2})
    runtime.collection_can_continue = True
    state.sources[0].status = 'inaccessible'
    runtime.validate_action(state, action, runtime.counts, set())


def test_native_context_forecast_keeps_total_usage_separate_from_last_context():
    from bigbrain.research_budget import ContextForecast
    from bigbrain.llm.usage import UsageRecord
    forecast = ContextForecast()
    record = UsageRecord('fixture', 'codex', input_tokens=117791, output_tokens=1211, total_tokens=119002)
    forecast.observe([record], context_units=16307)
    assert forecast.retained_units == 16307
    assert record.total_tokens == 119002
