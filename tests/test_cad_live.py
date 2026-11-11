"""Durable presentation identities survive process reconstruction and reject foreign readers."""

import json

import pytest

from bigbrain.cad_live import retain_progress, working_checkpoint
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
