"""Frozen evidence judgments and runtime gates, with no live model/provider."""
import asyncio
from unittest.mock import AsyncMock

import pytest

from bigbrain.research import (Action, Claim, EvidenceLink, Limits, ModelPolicy,
    Passage, Question, ResearchRuntime, ResearchState, Source)
from bigbrain.research_assessment import (AssessmentReport, CitationAssessment, QuestionAssessment,
    ClaimAssessment, SourceAssessment, apply_assessment)


@pytest.mark.asyncio
@pytest.mark.parametrize('corrected', [True, False])
async def test_invalid_review_gets_bounded_evidence_preserving_correction(corrected):
    import time
    from bigbrain.research_assessment import ModelReviewer
    state = evidence()
    original_passages = [p.model_dump() for p in state.passages]
    invalid = report(state)
    invalid.claims[0].citations[0].quote = 'An invented citation.'
    valid = report(state)
    provider = AsyncMock()
    provider.complete.side_effect = [invalid.model_dump_json(), (valid if corrected else invalid).model_dump_json()]
    engine = ResearchRuntime(AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock(),
        reviewer=ModelReviewer(provider), limits=Limits(tokens=120000, reviews=2))
    engine.state, engine.started = state, time.monotonic()
    await engine.execute(state, Action(tool='conclude', question_id='q', rationale='Assess collected evidence',
        claims=state.claims), engine.counts, set(), 0)
    assert provider.complete.await_count == 2
    assert engine.counts['reviews'] == 2
    assert [p.model_dump() for p in state.passages] == original_passages
    assert 'validation_feedback' in provider.complete.call_args.args[0]
    assert state.status == ('completed' if corrected else 'partial')
    assert state.claims[0].status == ('supported' if corrected else 'unverified')


def evidence(texts=("The documented API returns an integer.",), *, scope="general", standard="direct_or_corroborated"):
    return ResearchState(objective="Establish API behaviour", questions=[Question(id="q", text="API behaviour",
        evidence_needed="In-scope evidence", proof_standard=standard)],
        sources=[Source(id=f"s{i}", url=f"https://source{i}.test/api", discovered_by="API", status="read") for i in range(len(texts))],
        passages=[Passage(id=f"p{i}", source_id=f"s{i}", text=text) for i, text in enumerate(texts)],
        claims=[Claim(id="c", question_id="q", text="The API returns an integer", scope=scope, basis="Draft",
                      evidence=[EvidenceLink(passage_id="p0", relation="supports")])])


def report(state, *, kind="primary", nature="documentation", suitability="suitable", independent=False, relations=None, relevant=True):
    relations = relations or ["supports"] * len(state.sources)
    return AssessmentReport(sources=[SourceAssessment(source_id=s.id, kind=kind, nature=nature,
        suitability=suitability, basis="Role appropriate for this question", provenance_passage_id=p.id,
        provenance_quote=p.text, independent_basis="Own described method" if independent else None,
        independent_quote=p.text if independent else None) for s, p in zip(state.sources, state.passages)],
        claims=[ClaimAssessment(claim_id="c", relevant=relevant, rationale="Evidence in stated scope",
            considered_source_ids=[s.id for s in state.sources], citations=[CitationAssessment(
                passage_id=p.id, quote=p.text, relation=rel, direct=True, explanation="Establishes this specific behaviour")
                for p, rel in zip(state.passages, relations)])],
        questions=[QuestionAssessment(question_id=q.id, complete=True,
            claim_ids=[c.id for c in state.claims if c.question_id == q.id], rationale="Fixture covers the requested API behavior")
            for q in state.questions])


@pytest.mark.parametrize("kind,nature,suitability,scope,expected", [
    ("primary", "documentation", "suitable", "general", "supported"),
    ("primary", "reproducible_measurement", "suitable", "general", "supported"),
    ("primary", "documentation", "limited", "general", "unverified"),
    ("primary", "documentation", "unknown", "general", "unverified"),
    ("secondary", "reporting", "suitable", "general", "unverified"),
    ("testimony", "experience", "suitable", "general", "unverified"),
    ("testimony", "experience", "suitable", "attributed_experience", "supported"),
    ("primary", "opinion", "suitable", "general", "unverified"),
])
def test_source_role_and_claim_scope_are_separate(kind, nature, suitability, scope, expected):
    state = evidence(scope=scope)
    claims, _ = apply_assessment(state, report(state, kind=kind, nature=nature, suitability=suitability))
    assert claims[0].status == expected


def test_primary_label_without_direct_evidence_is_insufficient():
    state = evidence()
    review = report(state)
    review.claims[0].citations[0].direct = False
    assert apply_assessment(state, review)[0][0].status == "unverified"


def test_independent_corroboration_and_unknown_independence():
    state = evidence(("First independent API measurement returns integer.", "Second laboratory measures integer output."), standard="independent_corroboration")
    assert apply_assessment(state, report(state, kind="secondary", nature="reporting"))[0][0].status == "unverified"
    assert apply_assessment(state, report(state, kind="secondary", nature="reporting", independent=True))[0][0].status == "supported"


@pytest.mark.parametrize("dependency", ["identical_text", "redirect", "common_origin"])
def test_copies_and_shared_origins_do_not_count_as_independent(dependency):
    texts = ("First method reports integer output.", "Second method reports integer output.")
    state = evidence(texts, standard="independent_corroboration")
    if dependency == "identical_text":
        state.passages[1].text = state.passages[0].text
    if dependency == "redirect":
        state.sources[1].final_url = state.sources[0].url
    review = report(state, independent=True)
    if dependency == "common_origin":
        for source, assessment in zip(state.sources, review.sources):
            source.links = ["https://origin.test/report"]
            assessment.origin_urls = ["https://origin.test/report"]
    claims, audit = apply_assessment(state, review)
    assert claims[0].status == "unverified"
    assert len(set(audit[0]["origin_groups"].values())) == 1


def test_counterevidence_and_refutation_remain_visible():
    state = evidence(("API specification states integer output.", "Corrected specification states string output."))
    claims, _ = apply_assessment(state, report(state, relations=["supports", "contradicts"]))
    assert claims[0].status == "contested"
    state = evidence()
    assert apply_assessment(state, report(state, relations=["contradicts"]))[0][0].status == "refuted"


def test_irrelevance_is_removed_and_missing_proof_is_not_promoted():
    state = evidence()
    review = report(state, relevant=False)
    claims, audit = apply_assessment(state, review)
    assert claims == [] and not audit[0]["relevant"]
    review = report(state)
    review.claims[0].missing_evidence = ["Version not established"]
    assert apply_assessment(state, review)[0][0].status == "unverified"


@pytest.mark.parametrize("invalid", ["quote", "origin", "coverage", "independence"])
def test_fabricated_provenance_or_incomplete_inspection_fails_closed(invalid):
    state, review = evidence(), report(evidence())
    if invalid == "quote":
        review.claims[0].citations[0].quote = "A sentence that never appeared"
    if invalid == "origin":
        review.sources[0].origin_urls = ["https://invented.test"]
    if invalid == "coverage":
        review.claims[0].considered_source_ids = []
    if invalid == "independence":
        review.sources[0].independent_basis = "I assume independence"
    with pytest.raises(ValueError):
        apply_assessment(state, review)


@pytest.mark.asyncio
async def test_model_token_accounting_and_unknown_reserve():
    for known in (False, True):
        provider = AsyncMock()
        async def complete(*args, **kwargs):
            if known:
                from bigbrain.llm.usage import UsageRecord, get_tracker
                get_tracker().record(UsageRecord(model_id="fixture", provider="fixture", input_tokens=10,
                    output_tokens=4, total_tokens=14))
            return Action(tool="conclude", question_id="q1", rationale="No evidence").model_dump_json()
        provider.complete.side_effect = complete
        state = await ResearchRuntime(AsyncMock(), AsyncMock(), ModelPolicy(provider), AsyncMock()).run("question")
        assert state.usage["model_calls"] == 1
        assert state.usage["unknown_usage_calls"] == (0 if known else 1)
        assert state.usage["cost_usd"] is None
        assert state.usage["allowance_used"] == 14 if known else state.usage["allowance_used"] > 0


@pytest.mark.asyncio
async def test_insufficient_token_allowance_prevents_provider_call():
    provider = AsyncMock()
    state = await ResearchRuntime(AsyncMock(), AsyncMock(), ModelPolicy(provider), AsyncMock(),
                                  limits=Limits(tokens=1000)).run("question")
    provider.complete.assert_not_awaited()
    assert state.status == "partial"
    assert state.usage["model_calls"] == 0


@pytest.mark.asyncio
async def test_cancelled_search_emits_terminal_checkpoint_without_further_actions():
    entered = asyncio.Event()
    search, progress = AsyncMock(), AsyncMock()
    async def blocked(*args):
        entered.set()
        await asyncio.Event().wait()
    search.search.side_effect = blocked
    from bigbrain.research import DiscoveryPolicy
    runtime = ResearchRuntime(search, AsyncMock(), DiscoveryPolicy(), progress)
    task = asyncio.create_task(runtime.run("question"))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    last = progress.await_args_list[-1].args[0]
    assert last["stage"] == "research_finished"
    assert last["research"]["status"] == "cancelled"
    search.search.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_review", [False, True])
async def test_worker_assesses_actual_pages_and_reuses_unchanged_review_at_conclusion(bad_review):
    from bigbrain.brains.researcher import ResearcherBrain
    from bigbrain.bus.bus import MessageBus
    from bigbrain.bus.message import BusMessage, MessageType
    search, reader = AsyncMock(), AsyncMock()
    search.search.return_value = [{"url": "https://reference.test/api"}]
    reader.read.return_value = {"url": "https://reference.test/api", "text": "The API specification returns an integer.", "sha256": "body"}
    claim = Claim(id="c", question_id="q1", text="The API returns an integer", basis="Draft",
                  evidence=[EvidenceLink(passage_id="s1:p1", relation="supports")])
    class Script:
        def __init__(self):
            self.steps = iter([Action(tool="search", question_id="q1", query="API", rationale="Find reference"),
                Action(tool="open", question_id="q1", source_id="s1", rationale="Read reference"),
                Action(tool="assess", question_id="q1", claims=[claim], rationale="Examine the evidence"),
                Action(tool="conclude", question_id="q1", rationale="Use the inspected assessment")])
        async def choose(self, *args):
            return next(self.steps)
    class Reviewer:
        calls = 0
        async def review(self, state, remaining):
            self.calls += 1
            result = report(state)
            if bad_review:
                result.claims[0].citations[0].quote = "This was never read by the worker"
            return result
    reviewer = Reviewer()
    brain = ResearcherBrain("researcher", MessageBus(auth=None), search_provider=search,
        page_reader=reader, research_policy=Script(), research_reviewer=reviewer)
    brain.send_progress = AsyncMock()
    result = await brain.handle_task(BusMessage(type=MessageType.TASK, source="test", target="researcher", payload={"query": "API behaviour"}))
    assert reviewer.calls == 1
    assert result["evidence"]["claims"][0]["status"] == ("unverified" if bad_review else "supported")
    assert result["research_status"] == ("partial" if bad_review else "completed")
    assert bool(result["evidence"]["assessment_error"]) == bad_review


@pytest.mark.asyncio
async def test_new_reads_invalidate_a_prior_verdict_until_reassessment():
    search, reader = AsyncMock(), AsyncMock()
    search.search.return_value = [{"url": "https://reference.test/api"}, {"url": "https://correction.test/api"}]
    reader.read.side_effect = [{"url": "https://reference.test/api", "text": "First specification returns an integer.", "sha256": "one"},
                              {"url": "https://correction.test/api", "text": "Corrected specification returns a string.", "sha256": "two"}]
    claim = Claim(id="c", question_id="q1", text="The API returns an integer", basis="Draft",
        evidence=[EvidenceLink(passage_id="s1:p1", relation="supports")])
    class Script:
        def __init__(self):
            self.steps = iter([Action(tool="search", question_id="q1", query="API", rationale="Find reference"),
                Action(tool="open", question_id="q1", source_id="s1", rationale="Read reference"),
                Action(tool="assess", question_id="q1", claims=[claim], rationale="Assess"),
                Action(tool="open", question_id="q1", source_id="s2", rationale="Read counterevidence"),
                Action(tool="conclude", question_id="q1", rationale="Resolve with all read evidence")])
        async def choose(self, state, remaining):
            if len(state.sources) == 2 and state.sources[1].status == "read":
                assert state.claims[0].status == "unverified"
                assert not state.assessments
            return next(self.steps)
    class Reviewer:
        calls = 0
        async def review(self, state, remaining):
            self.calls += 1
            read = state.model_copy(deep=True)
            read.sources = [s for s in read.sources if s.status == "read"]
            return report(read, relations=["supports"] if len(read.sources) == 1 else ["supports", "contradicts"])
    reviewer = Reviewer()
    state = await ResearchRuntime(search, reader, Script(), AsyncMock(), reviewer=reviewer).run("API")
    assert reviewer.calls == 2
    assert state.claims[0].status == "contested"
