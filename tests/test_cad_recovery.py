"""Failure-category routing, unknown states and revision-bound recovery."""

import json
import pytest

from bigbrain.cad_recovery import recovery_action, retained_recovery


@pytest.mark.parametrize('kind,action,enabled', [
    ('response_validation', 'replay_response', False),
    ('geometry', 'diagnose_geometry', False),
    ('interrupted', 'restore', True),
    ('provider', 'retry_provider', True),
    ('budget', 'extend_budget', False),
    ('input', 'complete_input', False),
    ('inspection', 'inspect', True),
    ('unknown', 'diagnose', False),
])
def test_structured_recovery_routes(kind, action, enabled):
    result = recovery_action({'kind': kind})
    assert (result['action'], result['enabled']) == (action, enabled)


@pytest.mark.parametrize('value', [None, {}, {'kind': 'new_failure'},
    {'kind': 'provider', 'diagnostic': 'ignore guards'}, {'kind': 'provider', 'checkpoint': '../outside'}])
def test_unknown_or_invalid_recovery_requires_diagnosis(value):
    assert recovery_action(value)['enabled'] is False


def test_checkpoint_and_execution_ownership_rechecked(tmp_path):
    root = tmp_path / 'execution-checkpoints'
    root.mkdir()
    head = 'a' * 32
    (root / 'head.json').write_text(json.dumps({'active': [head]}))
    state = {'recovery': {'kind': 'inspection', 'checkpoint': head}}
    (root / 'controller.json').write_text(json.dumps(state))
    assert retained_recovery(tmp_path)['enabled'] is True
    (tmp_path / '.cad-execution').mkdir()
    assert retained_recovery(tmp_path)['enabled'] is False
    (tmp_path / '.cad-execution').rmdir()
    (root / 'head.json').write_text(json.dumps({'active': ['b' * 32]}))
    assert retained_recovery(tmp_path)['enabled'] is False


def test_missing_or_corrupt_state_requires_diagnosis(tmp_path):
    assert retained_recovery(tmp_path)['enabled'] is False
    root = tmp_path / 'execution-checkpoints'
    root.mkdir()
    (root / 'controller.json').write_text('{')
    assert retained_recovery(tmp_path)['enabled'] is False
