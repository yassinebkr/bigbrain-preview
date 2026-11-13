"""Publication interruption preserves a measured recipe for inference-free recovery."""

import json
from types import SimpleNamespace

import pytest

from bigbrain.brains.cad_brain import CadBrain
from bigbrain.bus.bus import MessageBus
from bigbrain.cad_store import CadStore
from bigbrain.solidcraft import CadError
from bigbrain.verification.evidence import default_repository
from tests.test_cad_clarification import fixture
from tests.test_cad_controller import fixture_decision
from tests.test_cad_integration import prepared, task
from tests.test_cad_workflow import construction_commands, construction_cut_intents, workflow


@pytest.mark.asyncio
async def test_saved_inspection_resumes_without_model_or_rebuilding_checkpoint(tmp_path, cad_native_engine, monkeypatch):
    _, session_id, _, drawing = fixture()
    drawing['dimensions'][0].update(id='length', value=60)
    construction = {'title': 'Plate', 'commands': construction_commands(),
        'workflow': workflow().model_dump(mode='json'), 'cut_intents': construction_cut_intents('length')}
    inspection = {'title': 'Plate', 'criteria': [{'id': 'bounds', 'label': 'Envelope',
        'metric': 'dimensions_mm', 'expected': [60, 40, 6], 'dimension_bindings': {'length': 0}}]}
    class Provider:
        entry = SimpleNamespace(vision=True)
        def __init__(self, forbidden=False):
            self.forbidden = forbidden
            self.calls = []
        async def chat_complete(self, **kwargs):
            assert not self.forbidden, 'A saved inspection must resume without inference'
            self.calls.append(kwargs)
            if isinstance(kwargs['messages'][-1]['content'], list):
                return json.dumps(fixture_decision(kwargs, construction))
            return json.dumps(inspection)
    bus = MessageBus(tmp_path / 'bus', auth=None)
    try:
        plan, spec, _ = await prepared(bus, inspection, drawing=drawing, session_id=session_id)
        confirmed = default_repository().approve_spec(spec.design_id, plan_id=plan.id)
        publish = CadStore.publish
        def interrupted(*args, **kwargs):
            raise CadError('Interrupted publication')
        monkeypatch.setattr(CadStore, 'publish', interrupted)
        first = await CadBrain('cad_brain', bus, llm_provider=Provider()).handle_task(task(plan, confirmed))
        assert first['success'] is False and first['error'] == 'Interrupted publication'
        from bigbrain.cad_runs import CadRunCheckpoint
        retained = CadRunCheckpoint(CadStore(), confirmed, session_id).load()
        assert retained['kind'] == 'inspection'
        root = CadStore().directory(retained['document_id'])
        head = (root / 'execution-checkpoints/head.json').read_bytes()
        decisions = sorted((root / 'execution-checkpoints').glob('decision-*.json'))
        monkeypatch.setattr(CadStore, 'publish', publish)
        provider = Provider(forbidden=True)
        result = await CadBrain('cad_brain', bus, llm_provider=provider).handle_task(task(plan, confirmed))
        assert result['success'], result
        assert all(check['status'] == 'passed' for check in result['cad']['checks'])
        assert provider.calls == []
        assert (root / 'execution-checkpoints/head.json').read_bytes() == head
        assert sorted((root / 'execution-checkpoints').glob('decision-*.json')) == decisions
    finally:
        await bus.close()
