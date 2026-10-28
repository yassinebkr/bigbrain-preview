"""Direct native adapter keeps one lane and captures actual provider usage."""
import json

import pytest

from bigbrain.llm.conversation import conversation_scope, current_conversation
from bigbrain.research_direct import DirectDecision, DirectFinish, run_direct
from bigbrain.research_direct_model import DirectModelAdapter
from tests.test_research_direct_journey import conclusion, runtime, URL


class Provider:
    retains_conversation_context = True
    supports_research_action_bridge = True

    def __init__(self):
        self.scopes = []
        self.last_context_tokens = None

    async def complete(self, prompt, **kwargs):
        self.scopes.append(current_conversation.get())
        packet = json.loads(prompt.split('\n', 1)[1])
        if len(self.scopes) == 1:
            return json.dumps({'kind': 'acquire', 'requests': [{'tool': 'visit', 'url': URL,
                'question_id': 'q1', 'rationale': 'Inspect the supplied reference'}]})
        response = {'conclusion': conclusion(packet)}
        for finding in response['conclusion']['findings']:
            for citation in finding['citations']:
                citation.pop('receipt_id')
        for source in response['conclusion']['sources']:
            source['source_reference'] = source.pop('provenance_passage_id')
            source.pop('source_id')
            source.pop('provenance_quote', None)
        if kwargs['tool_schema']['name'] == 'research_directdecision':
            response['kind'] = 'finish'
        return json.dumps(response)


@pytest.mark.asyncio
async def test_native_adapter_reuses_one_conversation_lane_and_marks_unknown_usage():
    engine, _ = runtime()
    provider = Provider()
    adapter = DirectModelAdapter(engine, provider)
    with conversation_scope('test-owner-conversation', 'front'):
        result = await run_direct(engine, adapter)
    assert result.execution_outcome == 'complete', result.reason
    assert provider.scopes == [('test-owner-conversation', 'research-direct')] * 2
    assert result.usage['model_calls'] == 2
    assert result.usage['unknown_usage_calls'] == 2
    assert result.usage['direct_result']['independent_review'] == 'skipped'
    assert result.workflow['budget']['records'][0]['input_known'] is False
    assert result.usage['direct_result']['findings'][0]['citations'][0]['receipt_id']


def test_adapter_schema_has_exclusive_collection_shapes_and_explicit_finish_schema():
    engine, _ = runtime()
    adapter = DirectModelAdapter(engine, Provider())
    packet = {'working_set': {'questions': [{'id': 'q1'}], 'sources': [], 'passages': [], 'catalog': []}}
    adapter.forecast(packet, DirectDecision)
    schema = adapter.actor.protocol(DirectDecision)['tool_schema']['parameters']
    shapes = schema['$defs']['CollectionRequest']['anyOf']
    assert all('group_ids' not in shape['properties'] for shape in shapes)
    assert set(adapter.actor.protocol(DirectFinish)['tool_schema']['parameters']['properties']) == {'conclusion'}
    citation = schema['$defs']['DirectCitation']
    assert 'receipt_id' not in citation['properties']
    assert 'receipt_id' not in citation['required']


@pytest.mark.asyncio
async def test_native_empty_optional_focus_means_an_unfocused_read():
    class EmptyFocus(Provider):
        async def complete(self, prompt, **kwargs):
            raw = json.loads(await super().complete(prompt, **kwargs))
            for request in raw.get('requests', []):
                request['focus'] = ''
            return json.dumps(raw)
    engine, fetcher = runtime()
    state = await run_direct(engine, DirectModelAdapter(engine, EmptyFocus()))
    assert state.execution_outcome == 'complete', state.reason
    assert fetcher.calls == [URL]


@pytest.mark.asyncio
async def test_runtime_extracts_literal_citations_from_selected_handles():
    class HandlesOnly(Provider):
        async def complete(self, prompt, **kwargs):
            value = json.loads(await super().complete(prompt, **kwargs))
            for finding in (value.get('conclusion') or {}).get('findings', []):
                for citation in finding['citations']:
                    citation.pop('quote')
            return json.dumps(value)

    engine, _ = runtime()
    state = await run_direct(engine, DirectModelAdapter(engine, HandlesOnly()))
    assert state.execution_outcome == 'complete', state.reason
    citation = state.usage['direct_result']['findings'][0]['citations'][0]
    passage = next(p for p in state.passages if p.id == citation['passage_id'])
    assert passage.text[citation['start']:citation['end']] == citation['quote']


@pytest.mark.asyncio
async def test_out_of_window_citation_offsets_fail_before_acceptance():
    class ForeignSpan(Provider):
        async def complete(self, prompt, **kwargs):
            value = json.loads(await super().complete(prompt, **kwargs))
            for finding in (value.get('conclusion') or {}).get('findings', []):
                for citation in finding['citations']:
                    citation.pop('quote')
                    citation.update(start=0, end=999999)
            return json.dumps(value)

    engine, _ = runtime()
    state = await run_direct(engine, DirectModelAdapter(engine, ForeignSpan()))
    assert state.execution_outcome == 'failed'
    assert 'Citation span must fit' in state.diagnostic['message']


@pytest.mark.asyncio
async def test_final_native_unused_null_fields_are_canonicalized():
    from bigbrain.research_direct_controller import DirectLimits
    class NullableUnused(Provider):
        async def complete(self, prompt, **kwargs):
            value = json.loads(await super().complete(prompt, **kwargs))
            if value.get('conclusion'):
                value.update(kind='finish', requests=None, windows=None,
                             clarification=None, catalog_source_id=None, catalog_offset=0)
            return json.dumps(value)

    engine, _ = runtime()
    state = await run_direct(engine, DirectModelAdapter(engine, NullableUnused()),
                             limits=DirectLimits(calls=2))
    assert state.execution_outcome == 'complete', state.reason
    assert len(state.usage['direct_wire_candidates']) == 2


@pytest.mark.asyncio
async def test_invalid_required_array_preserves_the_raw_candidate_for_diagnosis():
    class NullSources(Provider):
        async def complete(self, prompt, **kwargs):
            value = json.loads(await super().complete(prompt, **kwargs))
            if value.get('conclusion'):
                value['conclusion']['sources'] = None
            return json.dumps(value)

    engine, _ = runtime()
    state = await run_direct(engine, DirectModelAdapter(engine, NullSources()))
    assert state.execution_outcome == 'failed'
    assert state.diagnostic['type'] != 'TypeError'
    assert state.diagnostic['wire_candidate_artifact']['sha256']


@pytest.mark.asyncio
async def test_real_provider_usage_refresh_preserves_evidence_and_one_complement_gate():
    from copy import deepcopy
    class PartialThenInspect(Provider):
        def __init__(self):
            super().__init__()
            self.partial = None
            self.packets = []

        async def complete(self, prompt, **kwargs):
            packet = json.loads(prompt.split('\n', 1)[1])
            self.packets.append(packet)
            if len(self.packets) <= 2:
                value = json.loads(await super().complete(prompt, **kwargs))
                if len(self.packets) == 2:
                    value['conclusion']['questions'][0]['gaps'] = ['Inspect the qualification']
                    self.partial = deepcopy(value)
                return json.dumps(value)
            self.scopes.append(current_conversation.get())
            if len(self.packets) == 3:
                citation = self.partial['conclusion']['findings'][0]['citations'][0]
                return json.dumps({'kind': 'select', 'windows': [{
                    'passage_id': citation['passage_id'], 'start': 0,
                    'end': len(citation['quote'])}]})
            return json.dumps(self.partial)

    engine, _ = runtime()
    provider = PartialThenInspect()
    state = await run_direct(engine, DirectModelAdapter(engine, provider))
    assert state.execution_outcome == 'partial', state.reason
    assert state.workflow['budget']['calls'] == 4
    assert state.usage['direct_complement']['after_call'] == 2
    assert len(state.usage['direct_wire_candidates']) == 4
    assert provider.packets[2]['working_set']['original_request_gaps'] == ['Inspect the qualification']
    assert provider.packets[3]['working_set']['prior_findings']


@pytest.mark.asyncio
async def test_persistent_native_context_receives_each_observed_passage_once():
    from bigbrain.research_direct_context import ObservedPassages
    from bigbrain.research_direct_controller import CallReservation
    from tests.test_research_direct_journey import ScriptedAdapter
    engine, _ = runtime()
    await run_direct(engine, ScriptedAdapter())
    store = ObservedPassages()
    store.ingest(engine.state)
    packet = {'working_set': store.packet(engine.state)}
    class Capture(Provider):
        async def complete(self, prompt, **kwargs):
            self.scopes.append(json.loads(prompt.split('\n', 1)[1]))
            return json.dumps({'kind': 'clarify', 'clarification': 'Choose the intended scope'})
    provider = Capture()
    adapter = DirectModelAdapter(engine, provider)
    with conversation_scope('persistent-observations', 'research'):
        first = adapter.prepare(packet)
        assert first == adapter.prepare(packet)  # Forecasting leaves delivery unchanged.
        for _ in range(2):
            incoming, outgoing = adapter.forecast(packet, DirectDecision)
            await adapter.infer(packet, CallReservation('decide', incoming, outgoing), DirectDecision)
        references = adapter.actor.protocol(DirectFinish)['tool_schema']['parameters']['$defs']['SourceAssessment']
    assert provider.scopes[0]['working_set']['passages']
    assert provider.scopes[1]['working_set']['passages'] == []
    pid = packet['working_set']['passages'][0]['id']
    assert pid in provider.scopes[1]['working_set']['retained_passage_ids']
    assert pid in references['properties']['source_reference']['enum']
    # A second consultation keeps its own identity and shares observed content.
    original = engine.state.passages[0]
    engine.state.passages.append(original.model_copy(update={'id': original.id + '-again'}))
    store.ingest(engine.state)
    repeated = {'working_set': store.packet(engine.state,
        windows=[(original.id + '-again', 0, len(original.text))])}
    assert repeated['working_set']['duplicate_passages'] == 1
    with conversation_scope('persistent-observations', 'research'):
        update = json.loads(adapter.prepare(repeated).split('\n', 1)[1])
    assert update['working_set']['passages'] == []
    assert update['working_set']['passage_aliases']
    with conversation_scope('persistent-observations', 'research'):
        final = json.loads(adapter.prepare({**repeated, 'mode': 'finish_only'}).split('\n', 1)[1])
    assert final['working_set']['passages']
    assert final['working_set']['passages'][0]['text'] == repeated['working_set']['passages'][0]['text']
    assert 'Current final evidence snapshot' in final['working_set']['update_mode']
    finish_prompt = adapter.prepare({**repeated, 'mode': 'finish_only'})
    assert finish_prompt.startswith('Current phase: final evidence synthesis. Acquisition is closed.')
    assert 'Use acquire for' not in finish_prompt.split('\n', 1)[0]
