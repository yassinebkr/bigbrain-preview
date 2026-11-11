"""Durable presentation identities survive process reconstruction and reject foreign readers."""

import json

import pytest

from bigbrain.cad_live import retain_progress, retained_activities, working_checkpoint
from bigbrain.cad_store import CadStore
from bigbrain.solidcraft import CadError


def test_progress_survives_store_recreation_and_keeps_run_scope(tmp_path):
    store = CadStore(tmp_path)
    document = store.create('conversation')
    progress = {'stage': 'cad_group_checkpoint', 'cad': {'sequence': 2, 'working': None}}
    context = {'session_id': 'conversation', 'task_id': 'run', 'subtask_id': 'construction'}
    retain_progress(store, document, 'conversation', context, progress)
    reopened = CadStore(tmp_path)
    root = reopened.authorize(document, 'conversation')
    recorded = json.loads((root / 'working-state.json').read_text())
    assert recorded['context'] == context
    assert recorded['progress'] == progress
    assert recorded['document_id'] == document
    assert working_checkpoint(reopened, document, 'conversation') is None
    assert len(retained_activities(reopened, 'conversation')) == 1
    assert retained_activities(reopened, 'foreign') == []
    resumed = {'stage': 'cad_group_checkpoint', 'cad': {'sequence': 1, 'working': None}}
    retain_progress(reopened, document, 'conversation', context, resumed)
    assert retained_activities(reopened, 'conversation')[0]['progress']['cad']['sequence'] == 3
    with pytest.raises(CadError, match='another conversation'):
        working_checkpoint(reopened, document, 'foreign')
    with pytest.raises(CadError, match='another conversation'):
        retain_progress(reopened, document, 'foreign', context, progress)


def test_checkpoint_head_symlink_is_rejected(tmp_path):
    store = CadStore(tmp_path / 'cad')
    document = store.create('conversation')
    root = store.authorize(document, 'conversation')
    (root / 'execution-checkpoints').mkdir()
    target = tmp_path / 'foreign.json'
    target.write_text('{}')
    (root / 'execution-checkpoints/head.json').symlink_to(target)
    with pytest.raises(CadError, match='identity changed'):
        working_checkpoint(store, document, 'conversation')


def test_retained_activity_reopens_cad_after_journal_rotation(tmp_path):
    from bigbrain.web.run_history import conversation_activity

    store = CadStore(tmp_path / 'cad')
    document = store.create('conversation')
    context = {'session_id': 'conversation', 'task_id': 'run', 'subtask_id': 'construction'}
    progress = {'stage': 'cad_group_checkpoint', 'cad': {
        'title': 'Plate', 'sequence': 1, 'working': None, 'status': 'modeling'}}
    retain_progress(store, document, 'conversation', context, progress)
    logs = tmp_path / 'logs'
    logs.mkdir()
    frames = conversation_activity(logs, 'conversation', float('inf'), cad_store=CadStore(store.root))
    assert [frame['payload']['event'] for frame in frames] == [
        'task.received', 'task.progress', 'task.failed']
    assert frames[1]['payload']['cad']['title'] == 'Plate'
    assert frames[1]['payload']['brain'] == 'cad_brain'
    assert 'redémarrage' in frames[2]['payload']['error']
    assert conversation_activity(logs, 'foreign', float('inf'), cad_store=store) == []
