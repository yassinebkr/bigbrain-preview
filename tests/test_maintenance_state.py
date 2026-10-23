"""Authoritative, paged maintenance facts; no LLM summary may rewrite them."""
import json

import pytest

from bigbrain.maintenance_state import MaintenanceState


def read(state, path='main.py', start=1, count=2, version='revision-a', total=8):
    state.observe('read', {'path': path}, {'path': path, 'sha256': version,
        'start': start, 'content': 'private-source-text\n' * count, 'total_lines': total}, f'obs-{start}')


def test_ranges_are_merged_and_actual_gaps_remain_visible():
    state = MaintenanceState(['main.py'])
    read(state, start=3, count=3)
    assert state.snapshot()['reads']['items'][0]['next_unread_line'] == 1
    read(state, start=1, count=3)
    row = state.snapshot()['reads']['items'][0]
    assert row['ranges'] == [[1, 5]]
    assert row['next_unread_line'] == 6
    read(state, start=6, count=3)
    assert state.snapshot()['reads']['items'][0]['complete'] is True
    assert 'private-source-text' not in json.dumps(state.export())


def test_patch_invalidates_old_read_coverage_and_stales_diagnostic():
    state = MaintenanceState(['main.py'])
    read(state, count=8)
    state.observe('diagnose', {}, {'status': 'failed'}, 'baseline')
    state.observe('patch', {'path': 'main.py'}, {'status': 'patched'}, 'patch')
    snapshot = state.snapshot()
    assert snapshot['patching_allowed'] is True  # baseline reproduced, not a final verdict
    assert snapshot['diagnostics'][0]['current_source_revision'] is False
    assert snapshot['reads']['items'][0]['stale'] is True
    assert snapshot['reads']['items'][0]['next_unread_line'] == 1
    read(state, count=2, version='revision-b')
    row = state.snapshot()['reads']['items'][0]
    assert row['ranges'] == [[1, 2]]
    assert row['stale'] is False
    assert row['next_unread_line'] == 3


def test_environment_ready_is_not_a_diagnostic_and_resolved_blockers_clear():
    state = MaintenanceState([])
    state.observe('diagnose', {}, {'status': 'inconclusive', 'reason': 'Interpreter missing'}, 'diag')
    state.observe('patch', {'path': 'main.py'}, {'status': 'tool_error',
        'code': 'diagnostic_required', 'reason': 'Reproduce first'}, 'rejected')
    state.observe('prepare_environment', {}, {'status': 'ready'}, 'env')
    assert state.snapshot()['patching_allowed'] is False
    assert state.snapshot()['environment']['observation_id'] == 'env'
    state.observe('diagnose', {}, {'status': 'failed'}, 'new-diag')
    assert state.snapshot()['patching_allowed'] is True
    assert all(b.get('code') != 'diagnostic_required' for b in state.snapshot()['blockers'])
    assert all(b.get('reason') != 'Interpreter missing' for b in state.snapshot()['blockers'])
    state.observe('diagnose', {}, {'status': 'passed'}, 'passed-diag')
    assert state.snapshot()['blocker_count'] == 0


def test_state_paging_and_durable_export_do_not_drop_older_facts():
    paths = [f'module{i}.py' for i in range(45)]
    state = MaintenanceState(paths)
    for path in paths:
        read(state, path=path)
    assert state.snapshot()['reads']['total'] == 45
    assert len(state.snapshot()['reads']['items']) == 20
    assert len(state.section('reads', 20)['items']) == 20
    assert len(state.section('reads', 40)['items']) == 5
    assert len(state.export()['sections']['reads']) == 45
    assert state.section('inventory', 40)['items'] == paths[40:]
    with pytest.raises(ValueError):
        state.section('reads', -1)
    with pytest.raises(ValueError):
        state.section('invented')


def test_verification_failure_is_not_cleared_by_reading_more_files():
    state = MaintenanceState(['main.py'])
    state.observe('verify', {}, {'success': False, 'error': 'Assertions missing',
        'verification': {'verdict': 'inconclusive'}}, 'verification')
    for _ in range(6):
        read(state)
    assert state.snapshot()['blockers'][0]['reason'] == 'Assertions missing'
    assert state.snapshot()['diagnostics'][0]['observation_id'] == 'verification'
    state.observe('verify', {}, {'success': True, 'verification': {'verdict': 'passed'}}, 'passed')
    assert state.snapshot()['blocker_count'] == 0


def test_malformed_review_cannot_break_runtime_diagnostic_state():
    state = MaintenanceState(['main.py'])
    state.observe('verify', {}, {'verification': {'verdict': 'inconclusive', 'failures': [
        {'stage': 'semantics', 'details': {'reason': 'Invalid model output', 'review': ['not', 'a', 'mapping']}}]}}, 'invalid')
    assert state.snapshot()['diagnostics'][0]['failed_stages'][0]['reason'] == 'Invalid model output'
    assert state.snapshot()['diagnostics'][0]['failed_stages'][0]['missing_evidence'] == []
