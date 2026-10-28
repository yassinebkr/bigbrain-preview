"""Offline gates for grouped collection, continuation and scoped conclusions."""
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest

from bigbrain.research import (Action, Claim, CollectionRequest, EvidenceLink, Limits,
    Passage, Question, ResearchRuntime, ResearchState, Source)
from bigbrain.research_context import policy_view
from bigbrain.research_sessions import ResearchSessions, prepare_continuation
from bigbrain.front.decision import Delegate, ResearchInput, ResearchRoute
from bigbrain.research_assessment import (AssessmentReport, ClaimAssessment,
    CitationAssessment, QuestionAssessment, SourceAssessment, apply_assessment)


def action(tool, **kwargs):
    return Action(tool=tool, question_id="q1", rationale="Inspect the stated gap", **kwargs)


def batch(*requests):
    return action("batch", requests=[CollectionRequest.model_validate(
        r.model_dump(include=set(CollectionRequest.model_fields))) for r in requests])


class Policy:
    def __init__(self, *actions):
        self.actions = iter(actions)
        self.calls = 0

    async def choose(self, state, remaining):
        self.calls += 1
        return next(self.actions)


def page(url, text="Observed direct documentation. Conditions remain applicable."):
    return {"url": url, "text": text, "sha256": hashlib.sha256(text.encode()).hexdigest()}


def engine(policy, **kwargs):
    search, reader = AsyncMock(), AsyncMock()
    search.search.return_value = [{"url": "https://a.test/doc"}, {"url": "https://b.test/doc"}]
    reader.read.side_effect = lambda url, **kw: page(url)
    return ResearchRuntime(search, reader, policy, AsyncMock(), **kwargs)


@pytest.mark.asyncio
async def test_grouped_collection_matches_serial_evidence_with_one_less_decision():
    results = []
    for grouped in (False, True):
        reads = [action("open", source_id="s1"), action("open", source_id="s2")]
        policy = Policy(action("search", query="Exact objective"),
            *([batch(*reads)] if grouped else reads), action("conclude"))
        runtime = engine(policy)
        state = await runtime.run("Exact objective")
        results.append((policy.calls, [(p.source_id, p.text) for p in state.passages]))
        assert runtime.counts["pages"] == 2
    assert results[0][1] == results[1][1]
    assert results[0][0] == 4 and results[1][0] == 3


@pytest.mark.asyncio
async def test_entire_batch_rejected_before_any_io_if_aggregate_budget_exceeded():
    runtime = engine(Policy(action("search", query="objective"),
        batch(action("open", source_id="s1"), action("open", source_id="s2")), action("conclude")),
        limits=Limits(pages=1))
    state = await runtime.run("objective")
    runtime.reader.read.assert_not_awaited()
    assert runtime.counts["pages"] == 0
    assert state.observations[1].data["code"] == "action_not_allowed"


@pytest.mark.asyncio
async def test_batch_cannot_discover_and_open_a_fabricated_source_in_same_group():
    runtime = engine(Policy(batch(action("search", query="objective"), action("open", source_id="s1")),
                            action("conclude")))
    await runtime.run("objective")
    runtime.search.search.assert_not_awaited()
    runtime.reader.read.assert_not_awaited()


@pytest.mark.asyncio
async def test_grouped_reads_bound_concurrency_serialize_domains_and_emit_partial_results():
    runtime = engine(Policy(action("search", query="objective"),
        batch(action("open", source_id="s1"), action("open", source_id="s2"), action("open", source_id="s3")),
        action("conclude")), limits=Limits(parallelism=2))
    runtime.search.search.return_value += [{"url": "https://a.test/other"}]
    active, peak, hosts = 0, 0, set()
    async def read(url):
        nonlocal active, peak
        host = url.split('/')[2]
        assert host not in hosts
        hosts.add(host)
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(.01)
        active -= 1
        hosts.remove(host)
        return page(url)
    runtime.reader.read.side_effect = read
    await runtime.run("objective")
    assert peak == 2
    assert sum(c.args[0]["stage"] == "research_batch_observation" for c in runtime.progress.call_args_list) == 3


@pytest.mark.asyncio
async def test_deadline_cancels_all_batch_children_and_keeps_fast_evidence():
    runtime = engine(Policy(action("search", query="objective"),
        batch(action("open", source_id="s1"), action("open", source_id="s2"))), limits=Limits(seconds=.1))
    exited = asyncio.Event()
    async def read(url):
        if "a.test" in url:
            return page(url)
        try:
            await asyncio.Event().wait()
        finally:
            exited.set()
    runtime.reader.read.side_effect = read
    state = await runtime.run("objective")
    assert exited.is_set() and len(state.passages) == 1
    assert state.status == "partial" and state.diagnostic["code"] == "time_budget_exhausted"


@pytest.mark.asyncio
async def test_checkpointed_partial_batch_does_not_reread_completed_child_on_resume():
    store = ResearchSessions("default", "interrupted-chat")
    first = engine(Policy(action("search", query="objective"),
        batch(action("open", source_id="s1"), action("open", source_id="s2"))), limits=Limits(seconds=.1))
    async def read(url):
        if "a.test" in url:
            return page(url)
        await asyncio.Event().wait()
    first.reader.read.side_effect = read
    first.checkpoints = store
    with store.lease(first.research_id):
        state = await first.run("objective")
    assert len(state.pending_observations) == 1
    second = engine(Policy(action("open", source_id="s1"), action("open", source_id="s2"), action("conclude")))
    second.checkpoints = store
    with store.lease(first.research_id):
        resumed = await second.run("retry", continuation=store.load(first.research_id))
    second.reader.read.assert_awaited_once_with("https://b.test/doc")
    assert not resumed.pending_observations
    assert {p.source_id for p in resumed.passages} == {"s1", "s2"}


@pytest.mark.asyncio
async def test_continuation_preserves_objective_and_reads_only_missing_source():
    store = ResearchSessions("default", "conversation")
    first = engine(Policy(action("search", query="Original version 2"), action("open", source_id="s1"),
                          action("clarify", clarification="Continue later")))
    first.checkpoints = store
    with store.lease(first.research_id):
        old = await first.run("Original version 2")
    restored = store.load(first.research_id)
    second = engine(Policy(action("open", source_id="s2"), action("conclude")))
    second.checkpoints = store
    with store.lease(first.research_id):
        state = await second.run("reessaie", continuation=restored)
    assert state.objective == "Original version 2"
    assert state.research_id == old.research_id and state.attempt_id != old.attempt_id
    assert state.previous_attempts[0]["status"] == "clarification"
    second.search.search.assert_not_awaited()
    second.reader.read.assert_awaited_once_with("https://b.test/doc")
    assert {p.source_id for p in state.passages} == {"s1", "s2"}
    assert store.summaries()[0]["research_id"] == old.research_id
    assert store.load(old.research_id)[1] > restored[1]
    assert not ResearchSessions("default", "different-conversation").summaries()
    with pytest.raises(FileNotFoundError):
        ResearchSessions("other-workspace", "conversation").load(old.research_id)


def test_leases_invalid_id_and_stale_evidence_are_fail_closed():
    store = ResearchSessions("default", "s")
    rid = str(uuid4())
    with store.lease(rid):
        with pytest.raises(ValueError, match="active attempt"):
            with store.lease(rid):
                pass
    with store.lease(rid):
        pass
    with pytest.raises(ValueError):
        store.path("../../escape")
    state = ResearchState(objective="v2", questions=[Question(id="q1", text="v2", evidence_needed="exact version")],
        sources=[Source(id="s1", url="https://a.test", discovered_by="query", status="read",
                        consulted_at="2000-01-01T00:00:00+00:00")],
        passages=[Passage(id="p1", source_id="s1", text="Old snapshot")])
    assert prepare_continuation(state) == {"s1"}
    assert not state.passages and state.sources[0].status == "discovered"


def test_front_continuation_is_typed_not_keyword_routing():
    rid = str(uuid4())
    decision = Delegate(operation="delegate", reply="Je reprends", objective="Original objective",
        route=ResearchRoute(brain="researcher", payload=ResearchInput(type="research", resume_research_id=rid)))
    assert decision.task_payload()["route"]["payload"]["resume_research_id"] == rid
    with pytest.raises(ValueError, match="full research runtime"):
        ResearchInput(type="search_only", resume_research_id=rid)


def test_compact_context_retains_literal_packets_and_explicit_omissions():
    state = ResearchState(objective="calibration", questions=[Question(id="q1", text="calibration", evidence_needed="limits")])
    state.passages = [Passage(id=f"p{i}", source_id="s1", text="calibration limit and condition " + str(i) + " filler"*100,
                             context=[f"section{i}"]) for i in range(30)]
    state.claims = [Claim(id="c1", question_id="q1", text="A claim", basis="pending",
                         evidence=[EvidenceLink(passage_id="p29", relation="supports")])]
    view = policy_view(state, byte_limit=4500)
    assert len(json.dumps(view, ensure_ascii=False, separators=(',', ':')).encode()) <= 4500
    assert "p29" in {p["id"] for p in view["passages"]}
    assert view["context_scope"]["decision_omitted_passage_ids"]
    assert all(p["text"] == next(x.text for x in state.passages if x.id == p["id"]) for p in view["passages"])


def reviewed_state(complete):
    text = "Atlas version 2 documents the observed limit of 25 milliseconds."
    question = "Establish the version 2 limit" if complete else "Compare versions 1 and 2"
    state = ResearchState(objective=question, questions=[Question(
        id="q1", text=question, evidence_needed="Direct version-scoped documentation")],
        sources=[Source(id="s1", url="https://a.test/v2", discovered_by="query", status="read")],
        passages=[Passage(id="p1", source_id="s1", text=text)],
        claims=[Claim(id="c1", question_id="q1", text="Version 2 uses 25 milliseconds", basis="pending",
                      evidence=[EvidenceLink(passage_id="p1", relation="supports")])])
    report = AssessmentReport(sources=[SourceAssessment(source_id="s1", kind="primary", nature="documentation",
        suitability="suitable", basis="Direct documentation", provenance_passage_id="p1", provenance_quote=text)],
        claims=[ClaimAssessment(claim_id="c1", relevant=True, rationale="Direct version 2 evidence",
            considered_source_ids=["s1"], citations=[CitationAssessment(passage_id="p1", quote=text,
                relation="supports", explanation="Explicit value", direct=True)])],
        questions=[QuestionAssessment(question_id="q1", complete=complete, claim_ids=["c1"],
            missing_evidence=[] if complete else ["Version 1 was not read"], rationale="Declared coverage")])
    return state, report


def test_verified_claim_survives_incomplete_wider_question():
    state, report = reviewed_state(False)
    claims, audits = apply_assessment(state, report)
    assert claims[0].status == "supported" and not audits[0]["missing_evidence"]
    assert state.answer_status == "partial"
    assert state.question_coverage[0]["missing_evidence"] == ["Version 1 was not read"]


def test_missing_coverage_is_not_silently_complete_and_unknown_claim_ids_rejected():
    state, report = reviewed_state(True)
    report.questions = []
    apply_assessment(state, report)
    assert state.answer_status == "partial"
    state, report = reviewed_state(True)
    report.questions[0].claim_ids = ["invented"]
    with pytest.raises(ValueError, match="own unique"):
        apply_assessment(state, report)


def test_unverified_claim_cannot_establish_question_coverage():
    state, report = reviewed_state(True)
    report.claims[0].citations[0].direct = False
    claims, _ = apply_assessment(state, report)
    assert claims[0].status == "unverified" and state.answer_status == "partial"


@pytest.mark.asyncio
async def test_explicit_complete_coverage_allows_delivery_after_review():
    import time
    state, report = reviewed_state(True)
    reviewer = AsyncMock()
    # A provider-less fixture reviewer exercises the real deterministic gates.
    class Reviewer:
        async def review(self, state, remaining):
            return report
    runtime = engine(Policy(), reviewer=Reviewer())
    runtime.state, runtime.started = state, time.monotonic()
    await runtime.execute(state, action("conclude", claims=state.claims), runtime.counts, set(), 0)
    assert state.status == "completed" and state.answer_status == "complete"
    assert state.question_coverage[0]["status"] == "covered"


@pytest.mark.asyncio
async def test_current_assessment_reaches_conclusion_without_rebuilding_review():
    """A validated assessment can close even when a later envelope cannot fit."""
    state, report = reviewed_state(True)
    state.sources[0].consulted_at = datetime.now(timezone.utc).isoformat()
    class Reviewer:
        def __init__(self):
            self.reservations = 0
            self.reviews = 0
        def required_allowance(self, state):
            self.reservations += 1
            if state.assessments:
                raise ValueError("Independent inspection limit exceeded by a required original section")
            return 10
        async def review(self, state, remaining):
            self.reviews += 1
            return report
    reviewer = Reviewer()
    policy = Policy(action("assess", claims=state.claims), action("conclude"))
    runtime = engine(policy, reviewer=reviewer)
    state.research_id = runtime.research_id
    result = await runtime.run(state.objective, continuation=(state, 0))
    assert result.status == "completed" and result.answer_status == "complete"
    assert reviewer.reservations == reviewer.reviews == 1
    assert policy.calls == 2
    assert runtime.counts["reviews"] == 1
    changed = result.claims[0].model_copy(update={"text": "A different assertion"})
    assert not runtime.assessment_current([changed])
    result.questions[0].text += " with additional scope"
    assert not runtime.assessment_current()


@pytest.mark.asyncio
async def test_retained_current_review_closes_without_new_reservation():
    state, report = reviewed_state(True)
    state.sources[0].consulted_at = datetime.now(timezone.utc).isoformat()
    state.claims, state.assessments = apply_assessment(state, report)
    class Reviewer:
        def required_allowance(self, state):
            raise AssertionError("Validated evidence must reuse its review")
        async def review(self, state, remaining):
            raise AssertionError("Validated evidence must reuse its review")
    runtime = engine(Policy(action("conclude")), reviewer=Reviewer())
    state.research_id = runtime.research_id
    result = await runtime.run(state.objective, continuation=(state, 0))
    assert result.status == "completed" and result.answer_status == "complete"
    assert runtime.counts["reviews"] == 0


@pytest.mark.asyncio
async def test_attempt_failure_preserves_reviewed_claims_with_partial_terminal_answer():
    state, report = reviewed_state(True)
    state.sources[0].consulted_at = datetime.now(timezone.utc).isoformat()
    state.claims, state.assessments = apply_assessment(state, report)
    class FailingPolicy:
        async def choose(self, state, remaining):
            raise ValueError("Transport diagnostic")
    runtime = engine(FailingPolicy())
    state.research_id = runtime.research_id
    result = await runtime.run(state.objective, continuation=(state, 0))
    assert result.status == result.answer_status == "partial"
    assert result.claims[0].status == "supported"
    assert result.question_coverage[0]["status"] == "covered"
    terminal = runtime.progress.call_args_list[-1].args[0]
    assert terminal["stage"] == "research_finished"
    assert terminal["research"]["answer_status"] == "partial"


@pytest.mark.asyncio
async def test_changed_observation_never_reuses_old_passage_id_or_old_claim():
    runtime = engine(Policy(action("search", query="objective"), action("open", source_id="s1"),
        action("open", source_id="s1", refresh=True), action("conclude")))
    runtime.reader.read.side_effect = [page("https://a.test/doc", "Old observed content"),
                                     page("https://a.test/doc", "New observed content")]
    state = await runtime.run("objective")
    assert [p.id for p in state.passages] == ["s1:p2"]
    assert state.observations[1].data["passages"][0]["id"] == "s1:p1"
    assert "Old observed content" not in json.dumps(policy_view(state))


@pytest.mark.asyncio
async def test_fragment_aliases_do_not_create_duplicate_source_reads():
    runtime = engine(Policy(action("search", query="objective"), action("open", source_id="s1"), action("conclude")))
    runtime.search.search.return_value = [{"url": "https://a.test/doc#first"}, {"url": "https://a.test/doc#second"}]
    state = await runtime.run("objective")
    assert len(state.sources) == 1
    runtime.reader.read.assert_awaited_once_with("https://a.test/doc")


@pytest.mark.asyncio
async def test_real_worker_continuation_retains_identity_and_separate_attempt_usage(tmp_path):
    from bigbrain.brains.researcher import ResearcherBrain
    from bigbrain.bus.bus import MessageBus
    search, reader = AsyncMock(), AsyncMock()
    search.search.return_value = [{"url": "https://a.test/doc"}]
    reader.read.return_value = page("https://a.test/doc")
    bus = MessageBus(tmp_path / "bus", auth=None)
    brain = ResearcherBrain("researcher", bus, search_provider=search, page_reader=reader,
        research_policy=Policy(action("search", query="Original objective"), action("open", source_id="s1"), action("conclude")))
    brain._event_context = lambda: {"session_id": "owning-chat", "task_id": "run-one"}
    brain.send_progress = AsyncMock()
    first = await brain._full_research("Original objective", {})
    brain.research_policy = Policy(action("conclude"))
    second = await brain._full_research("retry", {"resume_research_id": first["research_id"]})
    assert second["query"] == "Original objective"
    assert second["research_id"] == first["research_id"]
    assert second["attempt_id"] != first["attempt_id"]
    assert second["evidence"]["previous_attempts"][0]["attempt_id"] == first["attempt_id"]
    assert search.search.await_count == reader.read.await_count == 1
    assert brain.send_progress.call_args_list[-2].args[0]["research"]["research_id"] == first["research_id"]
    await bus.close()


def test_missing_original_artifact_invalidates_retained_citations():
    from bigbrain.research_acquisition import artifact, repository
    source = Source(id="s1", url="https://a.test/doc", discovered_by="query", status="read",
        consulted_at=datetime.now(timezone.utc).isoformat(), acquisition={"blocks_artifact": artifact(b"original", name="fixture")})
    repository().get_artifact(source.acquisition["blocks_artifact"]["sha256"])
    source.acquisition["blocks_artifact"]["sha256"] = "f"*64
    state = ResearchState(objective="Objective", questions=[Question(id="q1", text="Objective", evidence_needed="source")],
                          sources=[source], passages=[Passage(id="p1", source_id="s1", text="Old")])
    assert prepare_continuation(state) == {"s1"}
    assert not state.passages


def test_archived_captures_survive_age_and_explicit_freshness_still_expires():
    from bigbrain.research_acquisition import artifact
    raw = artifact(b'Captured reference', name='archived-reference.html')
    blocks = artifact(b'{"blocks": []}', name='archived-blocks.json')
    state = ResearchState(objective='Documented snapshot',
        questions=[Question(id='q1', text='Documented behavior', evidence_needed='Captured reference')],
        sources=[Source(id='s1', url='https://reference.test/versioned', discovered_by='query',
            status='read', content_sha256=raw['sha256'], consulted_at='2000-01-01T00:00:00+00:00',
            acquisition={'raw_artifact': raw, 'blocks_artifact': blocks})],
        passages=[Passage(id='p1', source_id='s1', text='Captured reference', observation_sha256=raw['sha256'])])
    assert prepare_continuation(state) == set()
    assert state.passages[0].text == 'Captured reference'
    assert state.sources[0].consulted_at == '2000-01-01T00:00:00+00:00'
    assert prepare_continuation(state, max_age_seconds=300) == {'s1'}
    assert not state.passages


@pytest.mark.asyncio
async def test_continuations_cannot_grow_source_catalogue_beyond_client_contract():
    from bigbrain.research import ResearchActionRejected, research_tools
    runtime = engine(Policy())
    state = ResearchState(objective="Objective", questions=[Question(id="q1", text="Objective", evidence_needed="sources")],
        sources=[Source(id=f"s{i}", url=f"https://a.test/{i}", discovered_by="old") for i in range(24)])
    runtime.state, runtime.started = state, __import__('time').monotonic()
    runtime.search.search.return_value = [{"url": f"https://new.test/{i}"} for i in range(5)]
    await runtime.execute(state, action("search", query="new"), runtime.counts, set(), 0)
    assert len(state.sources) == 25
    assert "search" not in research_tools(state, {"searches": 5})
    with pytest.raises(ResearchActionRejected, match="catalogue is full"):
        runtime.validate_action(state, action("search", query="another"), runtime.counts, set())


@pytest.mark.asyncio
async def test_frozen_corpus_grouping_gates_and_ranker_comparison():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("efficiency_benchmark", Path(__file__).with_name("research_efficiency_benchmark.py"))
    benchmark = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(benchmark)
    serial, grouped = await benchmark.run(False, samples=1), await benchmark.run(True, samples=1)
    for key, candidate in grouped["cases"].items():
        baseline = serial["cases"][key]
        assert candidate["metrics"]["critical_omissions"] == baseline["metrics"]["critical_omissions"]
        assert not candidate["metrics"]["invalid_evidence_documents"]
        assert not candidate["metrics"]["ungrounded_passage_documents"]
    for key in ("copies", "contradiction"):
        assert grouped["cases"][key]["policy_decisions"] < serial["cases"][key]["policy_decisions"]
        assert grouped["cases"][key]["decision_request_bytes"] < serial["cases"][key]["decision_request_bytes"]
    for comparison in grouped["selection_comparison"].values():
        assert comparison["bm25"]["critical_omissions"] == comparison["contextual"]["critical_omissions"]
