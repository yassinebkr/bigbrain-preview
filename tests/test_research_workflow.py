"""Finite production research journeys using scripted inference and real gates."""
import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from bigbrain.llm.conversation import current_conversation, conversation_scope
from bigbrain.llm.usage import UsageRecord, get_tracker
from bigbrain.research import Limits, ModelPolicy, ResearchRuntime
from tests.test_research_runtime import page

FACT = "The API returns an integer only for positive inputs."


class StageInference:
    def __init__(self, *, fail=None, recovery=False, fact=FACT, url="https://reference.test/api", invented=False,
                 report_usage=True):
        self.calls, self.fail, self.recovery = [], fail, recovery
        self.fact, self.url, self.invented = fact, url, invented
        self.report_usage = report_usage

    async def complete(self, prompt, **kwargs):
        data = json.loads(prompt.split("\n", 1)[1])
        name = kwargs["tool_schema"]["name"]
        self.calls.append((name, data, current_conversation.get()))
        if self.report_usage:
            get_tracker().record(UsageRecord(model_id="gpt-6-luna", provider="fixture",
                                            input_tokens=600, output_tokens=150, total_tokens=750))
        if self.fail == name:
            return "Invalid structured response"
        if name == "research_collectiondecision":
            if self.recovery and data.get('control_gaps'):
                return json.dumps({'requests': [{'tool': 'visit', 'question_id': 'q1',
                    'url': 'https://reference.test/qualification', 'rationale': 'Read the input restriction'}]})
            if data["state"]["sources"]:
                return json.dumps({"requests": []})
            return json.dumps({"requests": [{"tool": "visit", "question_id": "q1",
                "url": self.url, "rationale": "Read the official API definition"}]})
        if name == "research_draft":
            if not data["dossier"]["passages"]:
                return json.dumps({"dossier_sha256": data["dossier_sha256"], "claims": [],
                                   "remaining_gaps": ["The requested reference remains unread"]})
            passage = data["dossier"]["passages"][0]
            return json.dumps({"dossier_sha256": data["dossier_sha256"], "claims": [{
                "id": "c1", "question_id": "q1", "text": self.fact, "basis": "Inspected definition",
                "limitations": ["Positive inputs only"],
                "evidence": [{"passage_id": "invented" if self.invented else passage["id"], "relation": "supports"}]}]})
        draft = data["draft"]
        if not draft["claims"]:
            return json.dumps({"dossier_sha256": data["dossier_sha256"], "original_request_complete": False,
                "original_request_gaps": ["The requested reference remains unread"], "sources": [], "claims": [],
                "questions": [{"question_id": "q1", "complete": False, "claim_ids": [],
                               "rationale": "Access unavailable", "missing_evidence": ["Read reference"]}]})
        pid = draft["claims"][0]["evidence"][0]["passage_id"]
        source_ids = [s['id'] for s in data['dossier']['sources']]
        provenance = {sid: next(p['id'] for p in data['dossier']['passages']
                              if data['dossier']['passage_contexts'][p['context_ref']]['source_id'] == sid)
                      for sid in source_ids}
        result = {"dossier_sha256": data["dossier_sha256"],
            "original_request_complete": True, "sources": [{"source_id": sid, "kind": "primary",
                "nature": "documentation", "suitability": "suitable", "basis": "Official definition",
                "provenance_passage_id": provenance[sid]} for sid in source_ids],
            "claims": [{"claim_id": "c1", "relevant": True, "rationale": "Definition and condition retained",
                "considered_source_ids": source_ids, "citations": [{"passage_id": pid,
                    "relation": "supports", "direct": True, "explanation": "The definition states the behavior"}]}],
            "questions": [{"question_id": "q1", "complete": True, "claim_ids": ["c1"],
                "rationale": "Behavior and its input restriction established"}]}
        if self.recovery and sum(c[0] == 'research_control' for c in self.calls) == 1:
            result.update(original_request_complete=False, original_request_gaps=['Read the input restriction'],
                complement=[{'tool': 'visit', 'question_id': 'q1', 'url': 'https://reference.test/qualification',
                             'rationale': 'Read the input restriction'}])
        return json.dumps(result)


async def journey(provider, *, limits=None, **kwargs):
    reader, progress = AsyncMock(), AsyncMock()
    reader.read.return_value = page(FACT)
    runtime = ResearchRuntime(AsyncMock(), reader, ModelPolicy(provider), progress,
                              staged=True, limits=limits or Limits(seconds=120, pages=4), **kwargs)
    with conversation_scope("fixture-chat", "researcher"):
        state = await runtime.run("What does the documented API return and under which condition?",
                                  obligations=["Establish return type and the input restriction"])
    return state, runtime, progress


@pytest.mark.asyncio
async def test_complete_journey_shares_frozen_packet_and_isolates_roles():
    provider = StageInference()
    state, runtime, progress = await journey(provider)
    assert state.status == "completed", state.reason
    assert state.execution_outcome == "complete"
    assert state.answer_status == "complete"
    assert "Positive inputs only" in state.claims[0].limitations
    draft, control = provider.calls[-2:]
    assert draft[1]["dossier"] == control[1]["dossier"]
    assert 'basis' not in control[1]['draft']['claims'][0]
    assert 'status' not in control[1]['draft']['claims'][0]
    assert draft[2] != control[2]
    assert all(call[2][0] == "fixture-chat" for call in provider.calls)
    assert runtime.model_calls == 4
    assert state.assessments[0]["dossier_sha256"] == state.dossier["sha256"]
    assert progress.call_args.args[0]["stage"] == "research_finished"
    assert state.workflow["stage"] == "settle"


@pytest.mark.asyncio
async def test_consulted_evidence_can_close_when_next_decision_packet_is_too_large(monkeypatch):
    from bigbrain import research_workflow
    from bigbrain.research_context import InspectionBudgetExceeded
    original = research_workflow.policy_view
    def view(state, **kwargs):
        if state.passages:
            raise InspectionBudgetExceeded('Retained source metadata exceeds decision packet')
        return original(state, **kwargs)
    monkeypatch.setattr(research_workflow, 'policy_view', view)
    state, runtime, _ = await journey(StageInference())
    assert state.execution_outcome == 'complete', state.reason
    assert runtime.model_calls == 3
    assert state.assessments


@pytest.mark.asyncio
async def test_qualified_draft_above_old_byte_cutoff_reaches_control():
    class QualifiedDraft(StageInference):
        async def complete(self, prompt, **kwargs):
            raw = await super().complete(prompt, **kwargs)
            if kwargs['tool_schema']['name'] == 'research_draft':
                data = json.loads(raw)
                data['claims'][0]['limitations'].append('Bounded qualification. ' * 150)
                return json.dumps(data)
            return raw
    state, runtime, _ = await journey(QualifiedDraft())
    assert state.execution_outcome == 'complete', state.reason
    assert runtime.model_calls == 4
    assert len(state.claims[0].model_dump_json().encode()) > 3000


@pytest.mark.asyncio
@pytest.mark.parametrize("contract", ["research_collectiondecision", "research_draft", "research_control"])
async def test_invalid_output_settles_once_and_retains_observations(contract):
    state, _, progress = await journey(StageInference(fail=contract))
    assert state.status == "partial"
    assert state.workflow["stage"] == "settle"
    assert state.diagnostic
    assert sum(call.args[0]["stage"] == "research_finished" for call in progress.call_args_list) == 1
    assert not state.assessments
    if contract != "research_collectiondecision":
        assert state.passages


@pytest.mark.asyncio
async def test_control_omission_in_original_request_prevents_completion():
    class Incomplete(StageInference):
        async def complete(self, prompt, **kwargs):
            text = await super().complete(prompt, **kwargs)
            data = json.loads(text)
            if kwargs["tool_schema"]["name"] == "research_control":
                data.update(original_request_complete=False, original_request_gaps=["Second requested version remains unread"])
            return json.dumps(data)
    state, _, _ = await journey(Incomplete())
    assert state.execution_outcome == "partial"
    assert state.claims[0].status == "supported"
    assert state.original_request_coverage["gaps"] == ["Second requested version remains unread"]


@pytest.mark.asyncio
async def test_cancellation_during_control_retains_draft_and_settles():
    entered = asyncio.Event()
    class Waiting(StageInference):
        async def complete(self, prompt, **kwargs):
            if kwargs["tool_schema"]["name"] == "research_control":
                entered.set()
                await asyncio.Event().wait()
            return await super().complete(prompt, **kwargs)
    reader, progress = AsyncMock(), AsyncMock()
    reader.read.return_value = page(FACT)
    runtime = ResearchRuntime(AsyncMock(), reader, ModelPolicy(Waiting()), progress, staged=True)
    task = asyncio.create_task(runtime.run("API definition"))
    await asyncio.wait_for(entered.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert runtime.state.execution_outcome == "cancelled"
    assert runtime.state.claims[0].status == "unverified"
    assert runtime.state.dossier
    assert runtime.state.workflow["stage"] == "settle"


@pytest.mark.asyncio
async def test_targeted_recovery_freezes_a_new_revision_and_settles_at_seven_calls():
    target = {"tool": "visit", "question_id": "q1", "url": "https://reference.test/qualification",
              "rationale": "Read the missing input restriction"}
    class Recovery(StageInference):
        reviews = 0
        async def complete(self, prompt, **kwargs):
            raw = await super().complete(prompt, **kwargs)
            data = json.loads(raw)
            name = kwargs['tool_schema']['name']
            if name == 'research_control':
                self.reviews += 1
                if self.reviews == 1:
                    data.update(original_request_complete=False, original_request_gaps=['Read the input restriction'],
                                complement=[target])
            elif name == 'research_collectiondecision' and self.reviews == 1:
                data = {'requests': [target]}
            return json.dumps(data)
    provider = Recovery()
    state, runtime, _ = await journey(provider)
    assert state.execution_outcome == 'complete', state.reason
    assert state.workflow['complement_used']
    assert runtime.model_calls == 7
    assert runtime.counts['reviews'] == 2
    assert state.assessment_error is None
    assert state.dossier['revision'] == 2
    drafts = [c[1] for c in provider.calls if c[0] == 'research_draft']
    assert drafts[0]['dossier_sha256'] != drafts[1]['dossier_sha256']
    assert state.workflow['budget']['input_units'] <= 32000
    assert state.workflow['budget']['output_units'] <= 4000


@pytest.mark.asyncio
@pytest.mark.parametrize('contract', ['research_collectiondecision', 'research_draft', 'research_control'])
async def test_deadline_in_each_model_stage_settles_once(contract):
    class Waiting(StageInference):
        async def complete(self, prompt, **kwargs):
            if kwargs['tool_schema']['name'] == contract:
                await asyncio.Event().wait()
            return await super().complete(prompt, **kwargs)
    state, _, progress = await journey(Waiting(), limits=Limits(seconds=.15))
    assert state.execution_outcome in {'blocked', 'partial'}
    assert state.diagnostic['code'] == 'deadline'
    assert state.workflow['stage'] == 'settle'
    assert sum(c.args[0]['stage'] == 'research_finished' for c in progress.call_args_list) == 1


@pytest.mark.asyncio
async def test_reported_output_overrun_prevents_validated_delivery():
    class Overrun(StageInference):
        async def complete(self, prompt, **kwargs):
            raw = await super().complete(prompt, **kwargs)
            get_tracker().record(UsageRecord(model_id='gpt-6-luna', provider='fixture',
                output_tokens=5000, total_tokens=5000))
            return raw
    state, _, _ = await journey(Overrun())
    assert state.diagnostic['code'] == 'budget'
    assert state.execution_outcome == 'blocked'
    assert state.workflow['budget']['logical_calls'] == 1


@pytest.mark.asyncio
async def test_unbounded_native_transport_blocks_before_using_subscription_quota():
    provider = StageInference()
    provider.retains_conversation_context = True
    state, runtime, _ = await journey(provider)
    assert state.execution_outcome == 'blocked'
    assert state.diagnostic['code'] == 'transport_context_unbounded'
    assert runtime.model_calls == 0
    assert not provider.calls


def test_retained_history_is_charged_again_on_each_lane_request():
    from bigbrain.research_workflow import WorkflowBudget, WorkflowPolicy, CollectionDecision
    provider = StageInference()
    provider.retains_conversation_context = True
    actor = WorkflowPolicy(provider, 'collect')
    budget = WorkflowBudget({'collect': 5000})
    incoming, output = budget.forecast(actor, 'A new request', CollectionDecision, 400)
    assert incoming > 5000
    budget.record(actor, incoming, output, [], 'ok')
    assert budget.forecast(actor, 'Another request', CollectionDecision, 400)[0] > incoming


@pytest.mark.asyncio
async def test_explicit_continuation_of_cancelled_attempt_can_complete():
    state, first, _ = await journey(StageInference())
    state.status, state.execution_outcome = 'cancelled', 'cancelled'
    # Fresh observations remain intact; only the attempt's terminal state is
    # reset by an explicit continuation through the runtime entry point.
    from datetime import datetime, timezone
    for source in state.sources:
        source.consulted_at = datetime.now(timezone.utc).isoformat()
    provider = StageInference()
    reader = AsyncMock()
    runtime = ResearchRuntime(AsyncMock(), reader, ModelPolicy(provider), AsyncMock(), staged=True,
                              limits=Limits(seconds=120))
    result = await runtime.run('retry', continuation=(state, first.revision))
    assert result.execution_outcome == 'complete', result.reason
    assert result.objective == state.objective
    reader.read.assert_not_awaited()


def test_generation_contract_rejects_a_foreign_passage_before_runtime_execution():
    import jsonschema
    from bigbrain.research_workflow import Draft, WorkflowPolicy
    actor = WorkflowPolicy(None, 'draft')
    actor.generation_scope = {'questions': ['q1'], 'sources': ['s1'], 'passages': ['p1'],
                              'claims': [], 'dossier': 'a' * 64}
    schema = actor.protocol(Draft)['tool_schema']['parameters']
    draft = Draft(dossier_sha256='a' * 64, claims=[{'id': 'c1', 'question_id': 'q1',
        'text': FACT, 'basis': 'Observed API definition',
        'evidence': [{'passage_id': 'p1', 'relation': 'supports'}]}]).model_dump(mode='json')
    jsonschema.Draft202012Validator(schema).validate(draft)
    draft['claims'][0]['evidence'][0]['passage_id'] = 'earlier-capture:p1'
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(draft)
