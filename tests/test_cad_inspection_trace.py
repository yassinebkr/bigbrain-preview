"""Inspection inference retains document correlation through provider failures."""

import asyncio
import json

import pytest

from bigbrain.cad_stages import CadConstruction, inspect_candidate
from bigbrain.llm.conversation import conversation_scope
from tests.test_cad_controller import definition
from tests.test_cad_workflow import construction_commands, construction_cut_intents, workflow


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', ['response', 'provider_error', 'timeout', 'cancelled'])
async def test_inspection_records_one_correlated_transport_outcome(tmp_path, outcome):
    class Provider:
        async def chat_complete(self, **kwargs):
            if outcome == 'provider_error':
                raise RuntimeError('private provider detail')
            if outcome == 'timeout':
                raise TimeoutError('private timeout detail')
            if outcome == 'cancelled':
                raise asyncio.CancelledError()
            return '{}'

    construction = CadConstruction(title='Plate', commands=construction_commands(), workflow=workflow(),
                                  cut_intents=construction_cut_intents())
    expected = {'response': ValueError, 'provider_error': RuntimeError,
                'timeout': TimeoutError, 'cancelled': asyncio.CancelledError}[outcome]
    with conversation_scope('inspection-session', 'worker:cad_brain'), pytest.raises(expected):
        await inspect_candidate(Provider(), definition(), construction, {}, stop_on_error=True,
                                correlation={'document_id': 'retained-document'})
    files = list((tmp_path / 'evidence' / 'inference').glob('*.jsonl'))
    assert len(files) == 1
    records = [json.loads(line) for line in files[0].read_text().splitlines()]
    assert [record['event'] for record in records] == ['call.started', 'call.finished']
    assert all(record['document_id'] == 'retained-document' for record in records)
    assert all(record['session_id'] == 'inspection-session' for record in records)
    assert all(record['phase'] == 'cad.inspection.planning' for record in records)
    assert records[-1]['outcome'] == {'response': 'completed', 'provider_error': 'failed',
                                      'timeout': 'deadline', 'cancelled': 'cancelled'}[outcome]
    assert 'private' not in files[0].read_text()


@pytest.mark.asyncio
async def test_rejected_inspection_retains_exact_revision_bound_response(tmp_path):
    from bigbrain.cad_execution import digest

    raw = '{"criteria": []}'
    class Provider:
        async def chat_complete(self, **kwargs):
            return raw

    construction = CadConstruction(title='Plate', commands=construction_commands(), workflow=workflow(),
                                  cut_intents=construction_cut_intents())
    definition_value = definition()
    with pytest.raises(ValueError):
        await inspect_candidate(Provider(), definition_value, construction,
            {'source_sha256': 'a' * 64}, stop_on_error=True, response_directory=tmp_path)
    saved = json.loads((tmp_path / 'inspection-response-1.json').read_text())
    assert saved['raw'] == raw and saved['source_sha256'] == 'a' * 64
    assert saved['definition_sha256'] == digest(definition_value.model_dump(mode='json'))
    assert saved['construction_sha256'] == digest(construction.model_dump(mode='json'))
    assert saved['attempt'] == 1
    assert len(saved['call_id']) == 32
