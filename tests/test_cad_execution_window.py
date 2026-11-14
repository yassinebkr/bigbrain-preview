"""Operator-selected execution windows are explicit in new confirmation contracts."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from bigbrain.cad_resources import proposal_execution_seconds
from bigbrain.cad_stages import CadDefinition
from tests.test_cad_drawings import drawing


@pytest.mark.parametrize('configured, expected', [(None, 600), ('3600', 3600), ('1200', 1200)])
def test_proposal_window_is_explicitly_configured(monkeypatch, configured, expected):
    if configured is None:
        monkeypatch.delenv('BIGBRAIN_CAD_EXECUTION_SECONDS', raising=False)
    else:
        monkeypatch.setenv('BIGBRAIN_CAD_EXECUTION_SECONDS', configured)
    assert proposal_execution_seconds() == expected


@pytest.mark.parametrize('configured', ['0', '-1', '3601', '1.5', 'unlimited'])
def test_invalid_windows_fail_before_construction(monkeypatch, configured):
    monkeypatch.setenv('BIGBRAIN_CAD_EXECUTION_SECONDS', configured)
    with pytest.raises(ValueError):
        proposal_execution_seconds()


@pytest.mark.asyncio
async def test_new_contract_records_operator_window_and_retained_contract_keeps_its_value(monkeypatch, tmp_path):
    from bigbrain.brains import cad_brain
    monkeypatch.setattr(cad_brain, 'solidcraft_executable', lambda: tmp_path / 'unused-native')
    from tests.test_cad_clarification import fixture
    _, session_id, _, data = fixture()
    old = CadDefinition(title='Support', objective='Create the support', drawing=data)
    monkeypatch.setenv('BIGBRAIN_CAD_EXECUTION_SECONDS', '3600')
    plan = await cad_brain.prepare_cad_plan(SimpleNamespace(entry=SimpleNamespace(vision=True)),
        {'session_id': session_id, 'drawing': data, 'user_request': 'Create the support'}, defer_construction=True)
    assert plan.execution_seconds == 3600
    assert '3600 secondes' in plan.contracts()[-1]
    restored = CadDefinition.model_validate_json(old.model_dump_json())
    assert restored.execution_seconds == 600
    assert restored.drawing == plan.drawing
    assert restored.max_repairs == plan.max_repairs
    with pytest.raises(ValidationError):
        CadDefinition.model_validate(plan.model_dump() | {'execution_seconds': 3601})
