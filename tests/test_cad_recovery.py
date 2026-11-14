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


@pytest.mark.parametrize('kind', ['geometry', 'response_validation'])
@pytest.mark.parametrize('changed', ['none', 'bytes', 'checkpoint', 'contract', 'engine', 'ready', 'link', 'active'])
def test_geometry_resume_requires_hash_bound_native_diagnosis(tmp_path, changed, kind):
    import hashlib

    root = tmp_path / 'execution-checkpoints'
    root.mkdir()
    checkpoint, contract, engine = 'a' * 32, 'b' * 64, 'c' * 64
    head = {'active': [checkpoint], 'contract_sha256': contract, 'engine_sha256': engine}
    (root / 'head.json').write_text(json.dumps(head))
    diagnosis = {'checkpoint': checkpoint, 'contract_sha256': contract,
                 'engine_sha256': engine, 'resume_ready': True}
    if changed in ('checkpoint', 'contract', 'engine'):
        key = {'checkpoint': 'checkpoint', 'contract': 'contract_sha256', 'engine': 'engine_sha256'}[changed]
        diagnosis[key] = 'd' * len(diagnosis[key])
    if changed == 'ready':
        diagnosis['resume_ready'] = False
    path = root / 'offline-diagnosis-native.json'
    path.write_text(json.dumps(diagnosis))
    identity = hashlib.sha256(path.read_bytes()).hexdigest()
    state = {'contract_sha256': contract, 'recovery': {'kind': kind, 'checkpoint': checkpoint},
             'offline_diagnostics': [{'name': path.name, 'sha256': identity}]}
    (root / 'controller.json').write_text(json.dumps(state))
    if changed == 'bytes':
        path.write_text('{}')
    if changed == 'link':
        target = tmp_path / 'external.json'
        path.rename(target)
        path.symlink_to(target)
    if changed == 'active':
        (tmp_path / '.cad-execution').mkdir()
    result = retained_recovery(tmp_path)
    assert result['enabled'] is (changed == 'none')
    if changed == 'none':
        assert result['action'] == ('resume_diagnosed_geometry' if kind == 'geometry' else 'resume_diagnosed_proposal')
